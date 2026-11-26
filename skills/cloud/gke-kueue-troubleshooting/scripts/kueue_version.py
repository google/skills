#!/usr/bin/env python3
"""Kueue release / API version detection for the `gke-kueue-troubleshooting` skill.

`detect_target_kueue_version()` runs a fixed chain of detectors
(`VERSION_DETECTORS`) over one `VersionDetection` context. Every detector
returns an ordered list of `VersionClue`s; the chain adopts a clue only when the
field it supports (`release_version`, `short_api`, `config_short_api`) is still
unknown, and records the clue's `source` string in `detection_sources` in the
order the clues were produced. The precedence is therefore:

  1. explicit overrides (arguments, then
  `GKE_KUEUE_TROUBLESHOOTING_KUEUE_VERSION` /
     `GKE_KUEUE_TROUBLESHOOTING_API_VERSION`);
  2. Kubernetes objects (controller Deployment/Pod labels and image tags, the
     `kueue-manager-config` ConfigMap, apiVersions of Kueue objects), scanned
     once in list order so the sources interleave exactly as the objects do;
  3. controller log lines (passed in, or the first 400 lines of the bundle's
     controller log files): `gitVersion`, `config.kueue.x-k8s.io/<ver>` and the
     dominant `kueue.x-k8s.io/<ver>`;
  4. the live `Deployment/kueue-controller-manager` (`live` mode only, and only
     when no release version was found so far);
  5. the API version inferred from the release (`<= v0.15` -> `v1beta1`).

Anything still unknown afterwards falls back to the config API version or to
`v1beta2` (`default:v1beta2` is recorded only when no source was found at all).
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import stat
import subprocess
from typing import Any, Callable

import k8s_objects

_SEMVER_SUFFIX = (
    r"(?:-[a-zA-Z0-9_]+(?:[.-][a-zA-Z0-9_]+)*)?"
    r"(?:\+[a-zA-Z0-9_]+(?:[.-][a-zA-Z0-9_]+)*)?"
)
_IMAGE_TAG_RE = re.compile(
    rf"kueue[^:\s]{{0,128}}:(v[0-9]+\.[0-9]+\.[0-9]+{_SEMVER_SUFFIX})"
)
_LABEL_VERSION_RE = re.compile(
    rf"^v?[0-9]+\.[0-9]+(?:\.[0-9]+)?{_SEMVER_SUFFIX}$"
)
_CONFIG_API_RE = re.compile(
    r"config\.kueue\.x-k8s\.io/(v1(?:alpha|beta)[0-9]+)"
)
_CONFIGMAP_API_RE = re.compile(
    r"apiVersion:\s*config\.kueue\.x-k8s\.io/(v1(?:alpha|beta)[0-9]+)"
)
_GIT_VERSION_RE = re.compile(
    rf'"gitVersion"\s*:\s*"(v[0-9]+\.[0-9]+\.[0-9]+{_SEMVER_SUFFIX})"'
)
_LOG_API_RE = re.compile(
    r"(?:(?<!config\.)kueue\.x-k8s\.io/|io\.x-k8s\.kueue\.)(v1beta[12])\b"
)
_KUEUE_OBJECT_KINDS = (
    "ClusterQueue",
    "LocalQueue",
    "Workload",
    "ResourceFlavor",
    "AdmissionCheck",
    "ProvisioningRequestConfig",
)
_BUNDLE_LOG_HEAD_LINES = 400
_LIVE_DEPLOYMENT_TIMEOUT_SECONDS = 4

RELEASE_VERSION = "release_version"
SHORT_API = "short_api"
CONFIG_SHORT_API = "config_short_api"


def normalize_short_api_version(api_ver: str) -> str:
  """Extracts short version (`v1beta1`, `v1beta2`, `v1alpha1`) from an apiVersion string."""
  if not api_ver:
    return ""
  s = api_ver.strip()
  if "/" in s:
    s = s.rsplit("/", 1)[-1]
  return s


def normalize_release_tag(release_version: str) -> str:
  """`0.19.4` -> `v0.19.4`; empty, `unknown`, or malformed -> ``."""
  norm = (release_version or "").strip()
  if not norm or norm == "unknown":
    return ""
  if not norm.startswith("v") and re.search(r"^[0-9]+\.[0-9]+", norm):
    norm = f"v{norm}"
  if not _LABEL_VERSION_RE.fullmatch(norm):
    return ""
  return norm


def _label_release(labels: dict[str, Any], *keys: str) -> str:
  """Release version from the first non-empty label among `keys`, `v`-prefixed; `` if absent."""
  lbl_ver = ""
  for key in keys:
    lbl_ver = str(labels.get(key) or "").strip()
    if lbl_ver:
      break
  if lbl_ver and _LABEL_VERSION_RE.match(lbl_ver):
    return lbl_ver if lbl_ver.startswith("v") else f"v{lbl_ver}"
  return ""


def _container_images(pod_spec: dict[str, Any]) -> list[str]:
  return [
      str(c.get("image") or "")
      for c in k8s_objects.dict_items(pod_spec.get("containers"))
  ]


def _pod_spec(item: dict[str, Any], kind: str) -> dict[str, Any]:
  """Pod spec of a Deployment (`spec.template.spec`) or a Pod (`spec`); `{}` for any other shape."""
  spec = k8s_objects.spec(item)
  if kind != "Deployment":
    return spec
  template = k8s_objects.as_dict(spec.get("template"))
  return k8s_objects.as_dict(template.get("spec"))


@dataclasses.dataclass(frozen=True)
class VersionClue:
  """One piece of version evidence: target field, value, and source entry."""

  field: str
  value: str
  source: str


@dataclasses.dataclass
class VersionDetectionInputs:
  """Arguments of `detect_target_kueue_version()` after env defaults."""

  mode: str = "live"
  raw_items: list[dict[str, Any]] = dataclasses.field(default_factory=list)
  log_lines: list[str] = dataclasses.field(default_factory=list)
  data_path: str = ""
  explicit_release_version: str = ""
  explicit_api_version: str = ""
  kueue_namespace: str = "kueue-system"


@dataclasses.dataclass
class VersionDetection:
  """Detection context holding inputs and clues established so far."""

  inputs: VersionDetectionInputs
  release_version: str = ""
  short_api: str = ""
  config_short_api: str = ""
  sources: list[str] = dataclasses.field(default_factory=list)

  def known(self, name: str) -> str:
    return str(getattr(self, name))

  def adopt(self, clues: list[VersionClue]) -> None:
    """Takes the first clue per field, recording its source; later clues for a known field are dropped."""
    for clue in clues:
      if clue.value and not self.known(clue.field):
        setattr(self, clue.field, clue.value)
        self.sources.append(clue.source)


VersionDetector = Callable[[VersionDetection], list[VersionClue]]


def detect_from_explicit(ctx: VersionDetection) -> list[VersionClue]:
  """Explicit overrides: arguments first, then the `GKE_KUEUE_TROUBLESHOOTING_*` / `KUEUE_DIAGNOSE_*` env vars."""
  clues: list[VersionClue] = []
  release = (
      ctx.inputs.explicit_release_version
      or os.getenv("GKE_KUEUE_TROUBLESHOOTING_KUEUE_VERSION", "").strip()
      or os.getenv("KUEUE_DIAGNOSE_KUEUE_VERSION", "").strip()
  )
  if release:
    clues.append(
        VersionClue(
            RELEASE_VERSION, release, f"explicit:release_version={release}"
        )
    )
  short_api = normalize_short_api_version(
      ctx.inputs.explicit_api_version
      or os.getenv("GKE_KUEUE_TROUBLESHOOTING_API_VERSION", "").strip()
      or os.getenv("KUEUE_DIAGNOSE_API_VERSION", "").strip()
  )
  if short_api:
    clues.append(
        VersionClue(SHORT_API, short_api, f"explicit:api_version={short_api}")
    )
  return clues


def _controller_workload_clues(
    item: dict[str, Any], kind: str
) -> list[VersionClue]:
  """Label then image-tag clues from a `kueue-controller-manager` Deployment or Pod."""
  clues: list[VersionClue] = []
  lbl_release = _label_release(
      k8s_objects.labels(item), "app.kubernetes.io/version", "version"
  )
  if lbl_release:
    clues.append(
        VersionClue(
            RELEASE_VERSION, lbl_release, f"{kind.lower()}_label:{lbl_release}"
        )
    )
  for img in _container_images(_pod_spec(item, kind)):
    m_img = _IMAGE_TAG_RE.search(img)
    if m_img:
      clues.append(
          VersionClue(
              RELEASE_VERSION,
              m_img.group(1),
              f"{kind.lower()}_image:{m_img.group(1)}",
          )
      )
  return clues


def _configmap_clue(item: dict[str, Any]) -> list[VersionClue]:
  cfg_text = str(
      k8s_objects.as_dict(item.get("data")).get(k8s_objects.KUEUE_CONFIG_KEY)
      or ""
  )
  m_cfg = _CONFIGMAP_API_RE.search(cfg_text)
  if not m_cfg:
    return []
  return [
      VersionClue(
          CONFIG_SHORT_API,
          m_cfg.group(1),
          f"configmap:config.kueue.x-k8s.io/{m_cfg.group(1)}",
      )
  ]


@dataclasses.dataclass
class _ObjectApiTally:
  """Tallies observed Kueue object API versions and cohort spec fields."""

  counts: dict[str, int] = dataclasses.field(default_factory=dict)
  has_v1beta1_cohort_field: bool = False
  has_v1beta2_cohort_name_field: bool = False

  def observe(self, item: dict[str, Any], kind: str, api_ver: str) -> None:
    sv = normalize_short_api_version(api_ver)
    if sv in ("v1beta1", "v1beta2"):
      self.counts[sv] = self.counts.get(sv, 0) + 1
    spec = item.get("spec") or {}
    if kind == "ClusterQueue" and isinstance(spec, dict):
      if "cohort" in spec and "cohortName" not in spec:
        self.has_v1beta1_cohort_field = True
      elif "cohortName" in spec:
        self.has_v1beta2_cohort_name_field = True

  def clues(self) -> list[VersionClue]:
    if self.counts:
      best = max(sorted(self.counts.keys()), key=lambda k: self.counts[k])
      return [
          VersionClue(SHORT_API, best, f"k8s_objects:kueue.x-k8s.io/{best}")
      ]
    if self.has_v1beta1_cohort_field and not self.has_v1beta2_cohort_name_field:
      return [
          VersionClue(SHORT_API, "v1beta1", "clusterqueue_spec:cohort->v1beta1")
      ]
    return []


def detect_from_objects(ctx: VersionDetection) -> list[VersionClue]:
  """One pass over the snapshot / bundle objects, in list order (the source order follows the objects)."""
  clues: list[VersionClue] = []
  tally = _ObjectApiTally()
  for it in ctx.inputs.raw_items:
    if not isinstance(it, dict):
      continue
    kind = str(it.get("kind") or "")
    api_ver = str(it.get("apiVersion") or "")
    name = str(k8s_objects.metadata(it).get("name") or "")
    if kind in ("Deployment", "Pod") and "kueue-controller-manager" in name:
      clues.extend(_controller_workload_clues(it, kind))
    api_group, api_sep, _ = api_ver.partition("/")
    if (
        kind in _KUEUE_OBJECT_KINDS
        and api_sep
        and (
            api_group == "kueue.x-k8s.io"
            or api_group.endswith(".kueue.x-k8s.io")
        )
    ):
      tally.observe(it, kind, api_ver)
    if kind == "ConfigMap" and name == "kueue-manager-config":
      clues.extend(_configmap_clue(it))
  clues.extend(tally.clues())
  return clues


def _bundle_log_head(data_path: str) -> list[str]:
  """The first lines of the controller log files a bundle may ship, in the fixed candidate order."""
  lines: list[str] = []
  root_real = os.path.realpath(data_path)
  logs_dir = os.path.join(data_path, "logs")
  candidates = [
      os.path.join(data_path, "kueue-controller-manager.log"),
      os.path.join(data_path, "kueue_logs.jsonl"),
  ]
  if not os.path.islink(logs_dir):
    candidates.insert(0, os.path.join(logs_dir, "kueue-controller-manager.log"))
  for candidate_log in candidates:
    try:
      if not stat.S_ISREG(os.lstat(candidate_log).st_mode):
        continue
      cand_real = os.path.realpath(candidate_log)
      if os.path.commonpath([root_real, cand_real]) != root_real:
        continue
    except (OSError, ValueError):
      continue
    try:
      with open(candidate_log, "r", encoding="utf-8", errors="replace") as f:
        for _ in range(_BUNDLE_LOG_HEAD_LINES):
          ln = f.readline()
          if not ln:
            break
          lines.append(ln)
    except OSError:
      # An unreadable candidate is skipped; the next one may still be readable.
      pass
  return lines


def detect_from_logs(ctx: VersionDetection) -> list[VersionClue]:
  """Controller log lines: `gitVersion`, the config API version and the dominant Kueue API version."""
  all_lines = list(ctx.inputs.log_lines)
  data_path = ctx.inputs.data_path
  if (
      data_path
      and os.path.isdir(data_path)
      and (not ctx.release_version or not ctx.short_api)
  ):
    all_lines.extend(_bundle_log_head(data_path))
  clues: list[VersionClue] = []
  seen_release = seen_config = False
  api_counts: dict[str, int] = {}
  for ln in all_lines:
    if not seen_release and ("gitVersion" in ln or "v0." in ln):
      m_git = _GIT_VERSION_RE.search(ln)
      if m_git:
        seen_release = True
        clues.append(
            VersionClue(
                RELEASE_VERSION,
                m_git.group(1),
                f"controller_log:gitVersion={m_git.group(1)}",
            )
        )
    if not seen_config:
      m_c = _CONFIG_API_RE.search(ln)
      if m_c:
        seen_config = True
        clues.append(
            VersionClue(
                CONFIG_SHORT_API,
                m_c.group(1),
                f"controller_log:config.kueue.x-k8s.io/{m_c.group(1)}",
            )
        )
    for m_k in _LOG_API_RE.finditer(ln):
      api_counts[m_k.group(1)] = api_counts.get(m_k.group(1), 0) + 1
  if api_counts:
    best = max(sorted(api_counts.keys()), key=lambda k: api_counts[k])
    clues.append(VersionClue(SHORT_API, best, f"logs:kueue.x-k8s.io/{best}"))
  return clues


def _live_controller_deployment(namespace: str) -> dict[str, Any] | None:
  """Fetches the live `kueue-controller-manager` Deployment JSON, or None."""
  try:
    res = subprocess.run(
        [
            "kubectl",
            "get",
            "deployment",
            "kueue-controller-manager",
            "-n",
            namespace,
            "-o",
            "json",
            "--ignore-not-found=true",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=_LIVE_DEPLOYMENT_TIMEOUT_SECONDS,
    )
    if res.returncode == 0 and res.stdout.strip():
      dep = json.loads(res.stdout)
      return dep if isinstance(dep, dict) else None
  except (OSError, subprocess.SubprocessError, ValueError):
    # No kubectl, no access or no JSON (`json.JSONDecodeError` is a
    # ValueError): the live Deployment is not a source.
    pass
  return None


def detect_from_live_deployment(ctx: VersionDetection) -> list[VersionClue]:
  """`live` mode only: the controller Deployment's version label and image tag (skipped once a release is known)."""
  if ctx.inputs.mode != "live" or ctx.release_version:
    return []
  dep = _live_controller_deployment(ctx.inputs.kueue_namespace)
  if dep is None:
    return []
  clues: list[VersionClue] = []
  lbl_release = _label_release(
      k8s_objects.labels(dep), "app.kubernetes.io/version"
  )
  if lbl_release:
    clues.append(
        VersionClue(
            RELEASE_VERSION, lbl_release, f"live_deployment_label:{lbl_release}"
        )
    )
  for img in _container_images(_pod_spec(dep, "Deployment")):
    m_img = _IMAGE_TAG_RE.search(img)
    if m_img:
      clues.append(
          VersionClue(
              RELEASE_VERSION,
              m_img.group(1),
              f"live_deployment_image:{m_img.group(1)}",
          )
      )
  return clues


def detect_from_release(ctx: VersionDetection) -> list[VersionClue]:
  """Kueue v0.1 through v0.15 store `v1beta1`; v0.16+ store `v1beta2`."""
  if ctx.short_api or not ctx.release_version:
    return []
  m_minor = re.search(r"^v?0\.([0-9]+)", ctx.release_version)
  if not m_minor:
    return []
  short_api = "v1beta1" if int(m_minor.group(1)) <= 15 else "v1beta2"
  return [
      VersionClue(
          SHORT_API,
          short_api,
          f"inferred_from_release:{ctx.release_version}->{short_api}",
      )
  ]


VERSION_DETECTORS: tuple[VersionDetector, ...] = (
    detect_from_explicit,
    detect_from_objects,
    detect_from_logs,
    detect_from_live_deployment,
    detect_from_release,
)


def _finalize(ctx: VersionDetection) -> dict[str, Any]:
  if not ctx.short_api:
    ctx.short_api = (
        ctx.config_short_api
        if ctx.config_short_api in ("v1beta1", "v1beta2")
        else "v1beta2"
    )
    if not ctx.sources:
      ctx.sources.append("default:v1beta2")
  if not ctx.config_short_api:
    ctx.config_short_api = ctx.short_api
  return {
      "release_version": ctx.release_version or "unknown",
      "api_version": f"kueue.x-k8s.io/{ctx.short_api}",
      "short_api_version": ctx.short_api,
      "config_api_version": f"config.kueue.x-k8s.io/{ctx.config_short_api}",
      "detection_sources": ctx.sources,
      "mode": ctx.inputs.mode,
  }


def run_version_detection(inputs: VersionDetectionInputs) -> dict[str, Any]:
  """Applies `VERSION_DETECTORS` in order and returns the `detected_kueue_version` dict."""
  ctx = VersionDetection(inputs=inputs)
  for detector in VERSION_DETECTORS:
    ctx.adopt(detector(ctx))
  return _finalize(ctx)


def detect_target_kueue_version(
    mode: str = "live",
    raw_items: list[dict[str, Any]] | None = None,
    log_lines: list[str] | None = None,
    data_path: str = "",
    explicit_release_version: str = "",
    explicit_api_version: str = "",
    kueue_namespace: str = "",
) -> dict[str, Any]:
  """Detects the target Kueue release version and active API versions from cluster, bundle, or logs."""
  inputs = VersionDetectionInputs(
      mode=mode,
      raw_items=list(raw_items or []),
      log_lines=list(log_lines or []),
      data_path=data_path,
      explicit_release_version=explicit_release_version,
      explicit_api_version=explicit_api_version,
      kueue_namespace=(
          kueue_namespace
          or os.getenv("GKE_KUEUE_TROUBLESHOOTING_NAMESPACE", "").strip()
          or os.getenv("KUEUE_DIAGNOSE_NAMESPACE", "").strip()
          or "kueue-system"
      ),
  )
  return run_version_detection(inputs)
