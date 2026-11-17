#!/usr/bin/env python3
"""Version-aware Kueue CRD & KueueConfiguration schema registry for the `gke-kueue-troubleshooting` skill.

Automatically detects the exact running Kueue release version (e.g. `v0.10.0`,
`v0.15.0`, `v0.19.4`) and active API version (`kueue.x-k8s.io/v1beta1` vs
`kueue.x-k8s.io/v1beta2`, `config.kueue.x-k8s.io/v1beta1` vs `v1beta2`) from:
  1. Live clusters (`Deployment/kueue-controller-manager` image/labels, live
     `CustomResourceDefinition` schemas, and active Kueue objects).
  2. Offline support bundles (`Deployment`/`Pod` controller image tags, bundled
     CRDs, manifest `apiVersion`s, and `logs/`).
  3. Controller/Event/Audit logs (`"Initializing"` `gitVersion`, `"Configuration
  loaded"`
     `apiVersion`, audit-log resource `apiVersion`s, and Event
     `involvedObject`).

Loads the schema for the exact detected version from the first available source:
  1. `CustomResourceDefinition` objects shipped inside the support bundle
  (`offline_data`).
  2. The live cluster's CRDs (`kubectl get crd`) — default in `live` mode; the
  cluster
     is the authoritative schema for the release it runs, nothing is downloaded.
  3. A local Kueue checkout, when present (`git archive <tag>` via
     `GKE_KUEUE_TROUBLESHOOTING_KUEUE_REPO`).
  4. The upstream GitHub release (`releases/download/<tag>/manifests.yaml`),
  used when
     no CRDs are at hand (logs-only modes, bundles without CRDs). Enabled by
     default;
     set `GKE_KUEUE_TROUBLESHOOTING_NO_REMOTE_SCHEMA=1` for air-gapped
     environments.
  5. Nothing. When none of the above is reachable the schema is reported as
     `schema_source=unavailable` together with `schema_notice` explaining how to
     supply
     it; field-level validation is skipped and only `apiVersion` consistency
     with the
     detected release is checked. No approximate/stale schema is ever
     substituted.

`KueueConfiguration` is not a CRD and has no schema inside a cluster. Its field
tree is
parsed from the published `kueue-config.<version>` reference page
(`https://kueue.sigs.k8s.io/docs/reference/kueue-config.<version>/`, falling
back to
the built-in defaults), see `config_schema_source`.

Downloaded/compiled schemas are cached under
`$XDG_CACHE_HOME/gke-kueue-troubleshooting`
(override with `GKE_KUEUE_TROUBLESHOOTING_CACHE_DIR`); the skill directory is
never written to.

Module map: `kueue_version` (release/API detection), `kueue_schema_registry`
(CRD -> compact registry, cache), `kueue_schema_sources` (source chain),
`kueue_schema_yaml_checks` (remediation YAML checks). This module holds the
I/O adapters (kubectl, git, HTTP), the public entry points and the CLI.
"""

from __future__ import annotations

import argparse
import http.client
import io
import json
import os
import re
import subprocess
import sys
import tarfile
from typing import Any, Iterable
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
  sys.path.insert(0, SCRIPT_DIR)

# pylint: disable=g-import-not-at-top,wrong-import-position
import kueue_schema_registry as registry
import kueue_schema_sources as sources
import kueue_schema_yaml_checks as yaml_checks
import kueue_version
import report_output
import yaml

# pylint: enable=g-import-not-at-top,wrong-import-position

# Re-exported for tests and sibling modules reaching these via kueue_schema.
detect_target_kueue_version = kueue_version.detect_target_kueue_version
_normalize_release_tag = kueue_version.normalize_release_tag
_normalize_short_api_version = kueue_version.normalize_short_api_version
DEFAULT_KCFG_NESTED = registry.DEFAULT_KCFG_NESTED
_parse_kcfg_struct_tree_from_html = registry.parse_kcfg_struct_tree_from_html
schema_cache_dir = registry.schema_cache_dir

# Public upstream Kueue documentation root used for doc citations.
KUEUE_SOURCE_REF = "v0.20.0"
KUEUE_DOCS_ROOT = "https://kueue.sigs.k8s.io/docs"
KCFG_REF_URL = "https://kueue.sigs.k8s.io/docs/reference/kueue-config.{ver}/"


def cite(url: str) -> str:
  """Format an official public Kueue documentation URL citation."""
  if url.startswith("https://"):
    return url
  return f"{KUEUE_DOCS_ROOT}/{url.lstrip('/')}"


def _resolve_kueue_repo_dir() -> str:
  """Locates a local Kueue checkout, if configured or enclosing."""
  candidates = [
      os.getenv("GKE_KUEUE_TROUBLESHOOTING_KUEUE_REPO", ""),
      os.getenv("KUEUE_DIAGNOSE_KUEUE_REPO", ""),
      os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", "..", "..")),
  ]
  for cand in candidates:
    if cand and os.path.isdir(
        os.path.join(cand, "config", "components", "crd", "bases")
    ):
      return cand
  return ""


KUEUE_REPO_DIR = _resolve_kueue_repo_dir()
GITHUB_RELEASE_URL = (
    "https://github.com/kubernetes-sigs/kueue/releases/download/"
    "{tag}/manifests.yaml"
)
_SAFE_RELEASE_TAG_RE = re.compile(
    r"^v[0-9]+\.[0-9]+\.[0-9]+"
    r"(?:-[a-zA-Z0-9_]+(?:[.-][a-zA-Z0-9_]+)*)?"
    r"(?:\+[a-zA-Z0-9_]+(?:[.-][a-zA-Z0-9_]+)*)?$"
)
_ALLOWED_KCFG_VERSIONS = frozenset({"v1alpha1", "v1beta1", "v1beta2"})
_HTTP_TIMEOUT_SECONDS = 8
_GIT_TIMEOUT_SECONDS = 5
_KUBECTL_CRD_TIMEOUT_SECONDS = 20


def remote_schema_allowed() -> bool:
  """Returns True unless remote schema downloads are disabled via env."""
  val = (
      os.getenv("GKE_KUEUE_TROUBLESHOOTING_NO_REMOTE_SCHEMA", "").strip()
      or os.getenv("KUEUE_DIAGNOSE_NO_REMOTE_SCHEMA", "").strip()
  )
  return val.lower() not in ("1", "true", "yes")


# --- Local Kueue checkout (git) ---------------------------------------------


def _git_in_repo(
    args: list[str], timeout: int, text: bool = True
) -> subprocess.CompletedProcess[Any] | None:
  """Runs `git -C KUEUE_REPO_DIR <args>`, or returns None if unavailable."""
  if not KUEUE_REPO_DIR or not os.path.isdir(
      os.path.join(KUEUE_REPO_DIR, ".git")
  ):
    return None
  try:
    return subprocess.run(
        ["git", "-C", KUEUE_REPO_DIR, *args],
        capture_output=True,
        text=text,
        check=False,
        timeout=timeout,
    )
  except (OSError, subprocess.SubprocessError):
    return None


def _closest_tag(norm: str, tags: set[str]) -> str:
  """Matches exact tag, stripped suffix tag, or latest patch of same minor."""
  if norm in tags:
    return norm
  base_ver = norm.split("-")[0]
  if base_ver in tags:
    return base_ver
  # Try matching v0.minor.0 if patch is newer than local repo
  m = re.search(r"^(v[0-9]+\.[0-9]+)\.[0-9]+", base_ver)
  if m:
    minor_prefix = m.group(1)
    minor_candidates = sorted(
        t
        for t in tags
        if re.fullmatch(rf"{re.escape(minor_prefix)}\.[0-9]+", t)
    )
    if minor_candidates:
      return minor_candidates[-1]
  return ""


def _resolve_git_tag_in_kueue_repo(release_version: str) -> str:
  """Finds the exact or closest matching git tag in the local Kueue repo."""
  if not release_version:
    return ""
  res = _git_in_repo(["tag", "-l"], timeout=3)
  if res is None or res.returncode != 0:
    return ""
  return _closest_tag(
      _normalize_release_tag(release_version), set(res.stdout.splitlines())
  )


def _parse_git_archive(
    archive: bytes,
) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
  """CRD documents from a `git archive` tarball."""
  crd_docs: list[dict[str, Any]] = []
  try:
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
      for member in tar.getmembers():
        fobj = tar.extractfile(member) if member.isfile() else None
        if fobj is None:
          continue
        raw_text = fobj.read().decode("utf-8", errors="replace")
        if member.name.endswith(".yaml"):
          doc = yaml.safe_load(raw_text)
          if isinstance(doc, dict):
            crd_docs.append(doc)
  except (tarfile.TarError, yaml.YAMLError, OSError):
    return None
  return crd_docs, {}


def _storage_version(crd_docs: list[dict[str, Any]], kind: str) -> str:
  """Storage version declared by the CRD of `kind`, or empty if absent."""
  for doc in crd_docs:
    spec = doc.get("spec") or {}
    if (spec.get("names") or {}).get("kind") != kind:
      continue
    for v in spec.get("versions") or []:
      if isinstance(v, dict) and v.get("storage"):
        return str(v.get("name") or "")
  return ""


def _load_schema_from_git_tag(
    git_tag: str, preferred_short_ver: str = ""
) -> tuple[dict[str, Any] | None, str]:
  """Extracts CRDs for `git_tag` from a local Kueue checkout (cached)."""
  if not git_tag or not _SAFE_RELEASE_TAG_RE.fullmatch(git_tag):
    return None, ""
  eff_ver = preferred_short_ver or "auto"
  cache_file = os.path.join(
      schema_cache_dir(),
      f"crd_schema_checkout_{registry.safe_tag(git_tag)}_{eff_ver}.json",
  )
  cached = registry.read_cached_registry(cache_file)
  if cached is not None:
    return cached, f"local_checkout_cache:{git_tag}"
  res = _git_in_repo(
      ["archive", git_tag, "--", "config/components/crd/bases/"],
      timeout=_GIT_TIMEOUT_SECONDS,
      text=False,
  )
  if res is None or res.returncode != 0 or not res.stdout:
    return None, ""
  parsed = _parse_git_archive(res.stdout)
  if parsed is None or not parsed[0]:
    return None, ""
  crd_docs, kcfg_by_ver = parsed
  # Use storage version in this tag unless preferred_short_ver was forced.
  target_ver = (
      preferred_short_ver
      or _storage_version(crd_docs, "ClusterQueue")
      or "v1beta2"
  )
  compiled = registry.compile_crd_docs(crd_docs, target_ver, kcfg_by_ver)
  compiled["_config_schema_source"] = "builtin_defaults"
  registry.write_cached_registry(cache_file, compiled, target_ver)
  return compiled, f"local_checkout:{git_tag}"


# --- Live cluster (kubectl) --------------------------------------------------


def _kubectl(args: list[str]) -> subprocess.CompletedProcess[str]:
  """Runs `kubectl` with the CRD request timeout and returns its result."""
  return subprocess.run(
      ["kubectl", *args, f"--request-timeout={_KUBECTL_CRD_TIMEOUT_SECONDS}s"],
      capture_output=True,
      text=True,
      check=False,
      timeout=_KUBECTL_CRD_TIMEOUT_SECONDS + 5,
  )


def _crd_items(data: Any) -> list[dict[str, Any]]:
  """Extracts Kueue CRDs from decoded `kubectl get crd -o json` output."""
  if isinstance(data, dict) and data.get("kind") == "CustomResourceDefinition":
    items = [data]
  else:
    items = data.get("items") if isinstance(data, dict) else []
  return [it for it in items or [] if sources.is_kueue_crd(it)]


def _query_live_cluster_crds() -> tuple[list[dict[str, Any]], str]:
  """Lists and fetches `*.kueue.x-k8s.io` CRDs from the live cluster."""
  listed = _kubectl(["get", "crd", "-o", "name"])
  if listed.returncode != 0:
    return (
        [],
        (
            f"`kubectl get crd` failed (rc={listed.returncode}):"
            f" {listed.stderr.strip()[:300]}"
        ),
    )
  names = [
      ln.strip().split("/", 1)[-1]
      for ln in listed.stdout.splitlines()
      if ln.strip().endswith(".kueue.x-k8s.io")
  ]
  if not names:
    return [], "`kubectl get crd` lists no *.kueue.x-k8s.io CRDs"
  res = _kubectl(["get", "crd", *names, "-o", "json"])
  if res.returncode != 0 or not res.stdout.strip():
    return (
        [],
        (
            "`kubectl get crd <kueue crds> -o json` failed"
            f" (rc={res.returncode}): {res.stderr.strip()[:300]}"
        ),
    )
  crds = _crd_items(json.loads(res.stdout))
  if not crds:
    return [], "`kubectl get crd` output contained no kueue.x-k8s.io CRDs"
  return crds, ""


def _fetch_live_cluster_crds() -> tuple[list[dict[str, Any]], str]:
  """Queries the live cluster for `*.kueue.x-k8s.io` CRDs.

  Only the Kueue CRDs are fetched as JSON (names are listed first) so clusters
  with hundreds of CRDs do not hit the timeout.

  Returns:
    A `(crds, error)` tuple where `error` is empty on success, or a short
    reason (kubectl missing, timeout, RBAC denial, unparsable output) that the
    caller surfaces in the schema notice.
  """
  try:
    return _query_live_cluster_crds()
  except FileNotFoundError:
    return [], "kubectl is not installed or not on PATH"
  except subprocess.TimeoutExpired:
    return (
        [],
        f"`kubectl get crd` timed out after {_KUBECTL_CRD_TIMEOUT_SECONDS}s",
    )
  except (OSError, subprocess.SubprocessError) as exc:
    return [], f"`kubectl get crd` could not run: {exc}"
  except json.JSONDecodeError as exc:
    return [], f"`kubectl get crd -o json` output is not valid JSON: {exc}"


# --- GitHub (HTTP) -----------------------------------------------------------


def _http_get_text(url: str) -> str | None:
  """Fetches `url` text, returning None on any network or HTTP failure."""
  try:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "gke-kueue-troubleshooting-schema-loader/1.0"},
    )
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SECONDS) as resp:
      return resp.read().decode("utf-8", errors="replace")
  except (OSError, ValueError, http.client.HTTPException):
    return None


def _release_tag_candidates(release_version: str) -> list[str]:
  """Returns exact tag first, then tag without any pre-release/distro suffix."""
  tag = _normalize_release_tag(release_version)
  if not tag or not _SAFE_RELEASE_TAG_RE.fullmatch(tag):
    return []
  base = tag.split("-", 1)[0].split("+", 1)[0]
  if base == tag or not _SAFE_RELEASE_TAG_RE.fullmatch(base):
    return [tag]
  return [tag, base]


def _fetch_github_release_crds(
    release_version: str,
) -> tuple[list[dict[str, Any]], str]:
  """Fetches GitHub release `manifests.yaml` CRDs and the matched tag."""
  for tag in _release_tag_candidates(release_version):
    if not _SAFE_RELEASE_TAG_RE.fullmatch(tag):
      continue
    content = _http_get_text(GITHUB_RELEASE_URL.format(tag=tag))
    if content is None:
      continue
    try:
      docs = [
          doc
          for doc in yaml.safe_load_all(content)
          if sources.is_kueue_crd(doc)
      ]
    except yaml.YAMLError:
      continue
    if docs:
      return docs, tag
  return [], ""


# --- KueueConfiguration reference page ---------------------------------------


def _read_cached_kcfg(cache_file: str) -> tuple[dict[str, Any] | None, str]:
  """Loads a cached `KueueConfiguration` field tree when fresh and valid."""
  if not os.path.isfile(cache_file):
    return None, ""
  try:
    with open(cache_file, "r", encoding="utf-8") as f:
      cached = json.load(f)
  except (OSError, json.JSONDecodeError):
    return None, ""
  if (
      isinstance(cached, dict)
      and cached.get("fields")
      and cached.get("source")
      and cached.get("format") == registry.SCHEMA_FORMAT
  ):
    return {
        "fields": cached["fields"],
        "tree": cached.get("tree") or {},
    }, f"cache:{cached['source']}"
  return None, ""


def _write_cached_kcfg(
    cache_file: str, entry: dict[str, Any], source: str
) -> None:
  """Atomically writes a `KueueConfiguration` field tree to `cache_file`."""
  try:
    tmp_path = f"{cache_file}.tmp.{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
      json.dump(
          {**entry, "source": source, "format": registry.SCHEMA_FORMAT},
          f,
          indent=1,
      )
    os.replace(tmp_path, cache_file)
  except OSError:
    pass


def _fetch_kcfg_ref_html(
    cfg_short_ver: str, allow_remote: bool
) -> tuple[str | None, str]:
  """Published `kueue-config.<ver>` reference HTML and its source label."""
  if not allow_remote or cfg_short_ver not in _ALLOWED_KCFG_VERSIONS:
    return None, ""
  url = KCFG_REF_URL.format(ver=cfg_short_ver)
  html_text = _http_get_text(url)
  if html_text and "<code>Configuration</code>" in html_text:
    return html_text, f"reference_docs:kueue-config.{cfg_short_ver}"
  return None, ""


def load_kcfg_for_release(
    release_version: str, cfg_short_ver: str, allow_remote: bool | None = None
) -> tuple[dict[str, Any] | None, str]:
  """Loads the `KueueConfiguration` field tree from cache or reference docs.

  Args:
    release_version: Detected Kueue release version string.
    cfg_short_ver: Short config API version (`v1beta1` or `v1beta2`).
    allow_remote: Whether remote HTTP fetches are permitted (defaults to env).

  Returns:
    A `(entry, source)` tuple, or `(None, "")` when neither cache nor reference
    page is available (callers then use built-in defaults).
  """
  tag = _normalize_release_tag(release_version)
  if not tag or cfg_short_ver not in ("v1beta1", "v1beta2"):
    return None, ""
  if allow_remote is None:
    allow_remote = remote_schema_allowed()
  cache_file = os.path.join(
      schema_cache_dir(), f"kcfg_{registry.safe_tag(tag)}_{cfg_short_ver}.json"
  )
  cached, cached_source = _read_cached_kcfg(cache_file)
  if cached is not None:
    return cached, cached_source
  html_text, source = _fetch_kcfg_ref_html(cfg_short_ver, allow_remote)
  if not html_text:
    return None, ""
  entry = registry.kcfg_fields_and_tree(html_text)
  if not entry.get("fields"):
    return None, ""
  _write_cached_kcfg(cache_file, entry, source)
  return entry, source


# --- Public entry points -----------------------------------------------------


def _schema_adapters(
    compile_with_kcfg: sources.CompileWithKcfg,
) -> sources.SchemaAdapters:
  """Binds the source chain to this module's patchable I/O functions."""
  return sources.SchemaAdapters(
      fetch_live_crds=_fetch_live_cluster_crds,
      resolve_git_tag=_resolve_git_tag_in_kueue_repo,
      load_git_tag_schema=_load_schema_from_git_tag,
      fetch_github_crds=_fetch_github_release_crds,
      compile_with_kcfg=compile_with_kcfg,
      repo_dir=KUEUE_REPO_DIR,
  )


def load_schema_for_version(
    version_info: dict[str, Any] | None = None,
    raw_items: list[dict[str, Any]] | None = None,
    load_live_crds: bool | None = None,
    allow_remote_fetch: bool | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
  """Loads the CRD and `KueueConfiguration` schema matching `version_info`."""
  vinfo = dict(version_info or detect_target_kueue_version(raw_items=raw_items))
  short_api = vinfo.get("short_api_version") or _normalize_short_api_version(
      vinfo.get("api_version", "v1beta2")
  )
  cfg_short = (
      _normalize_short_api_version(str(vinfo.get("config_api_version") or ""))
      or short_api
  )
  release_ver = str(vinfo.get("release_version") or "").strip()
  env_mode = report_output._env(  # pylint: disable=protected-access
      "GKE_KUEUE_TROUBLESHOOTING_MODE", "KUEUE_DIAGNOSE_MODE"
  )
  mode = str(vinfo.get("mode") or env_mode or "")
  if load_live_crds is None:
    load_live_crds = mode == "live"
  if allow_remote_fetch is None:
    allow_remote_fetch = remote_schema_allowed()

  def _with_kcfg(crds: list[dict[str, Any]]) -> dict[str, Any]:
    kcfg, kcfg_src = load_kcfg_for_release(
        release_ver, cfg_short, allow_remote_fetch
    )
    compiled = registry.compile_crd_docs(
        crds, short_api, {cfg_short: kcfg} if kcfg else None
    )
    compiled["_config_schema_source"] = kcfg_src or "builtin_defaults"
    return compiled

  request = sources.SchemaRequest(
      short_api=short_api,
      release_ver=release_ver,
      raw_items=[it for it in raw_items or [] if isinstance(it, dict)],
      load_live_crds=load_live_crds,
      allow_remote_fetch=allow_remote_fetch,
      adapters=_schema_adapters(_with_kcfg),
  )
  result = sources.resolve_schema(request)
  vinfo["schema_source"] = result.source
  vinfo["config_schema_source"] = str(
      result.schema.get("_config_schema_source") or "builtin_defaults"
  )
  return result.schema, vinfo


def get_active_schema_reference(
    kinds: Iterable[str],
    version_info: dict[str, Any] | None = None,
    raw_items: list[dict[str, Any]] | None = None,
    load_live_crds: bool | None = None,
) -> dict[str, Any]:
  """Returns a compact, version-exact schema reference for the given resource kinds."""
  schema, resolved_vinfo = load_schema_for_version(
      version_info=version_info,
      raw_items=raw_items,
      load_live_crds=load_live_crds,
  )
  short_api = resolved_vinfo.get("short_api_version", "v1beta2")

  out: dict[str, Any] = {
      "_detected_kueue_version": {
          "release_version": resolved_vinfo.get("release_version", "unknown"),
          "api_version": resolved_vinfo.get(
              "api_version", f"kueue.x-k8s.io/{short_api}"
          ),
          "config_api_version": resolved_vinfo.get(
              "config_api_version", f"config.kueue.x-k8s.io/{short_api}"
          ),
          "schema_source": resolved_vinfo.get("schema_source", ""),
          "config_schema_source": resolved_vinfo.get(
              "config_schema_source", ""
          ),
          "detection_sources": resolved_vinfo.get("detection_sources", []),
      }
  }
  if schema.get("_schema_unavailable"):
    out["_schema_notice"] = schema.get("_schema_notice", "")
    return out
  requested = set(kinds)
  requested.update({"ClusterQueue", "KueueConfiguration"})
  for k in sorted(requested):
    if k == "ConfigMap":
      k = "KueueConfiguration"
    elif k == "_by_api_version":
      continue
    if k in schema and isinstance(schema[k], dict):
      entry = schema[k]
      out[k] = {
          "apiVersion": entry.get("apiVersion"),
          "valid_fields": entry.get("top_level_spec_fields", []),
      }
  return out


def _explain_kind(
    root_key: str, kind_entry: dict[str, Any], resolved_vinfo: dict[str, Any]
) -> dict[str, Any]:
  """Formats the top-level schema explanation dict for `root_key`."""
  return {
      "detected_kueue_version": resolved_vinfo,
      "kind": root_key,
      "apiVersion": kind_entry.get("apiVersion"),
      "all_versions_in_release": kind_entry.get("all_versions", []),
      "top_level_spec_fields": kind_entry.get("top_level_spec_fields"),
      "spec_schema": kind_entry.get("spec_schema", {}),
  }


def _walk_spec_schema(spec_schema: Any, segments: list[str]) -> tuple[Any, str]:
  """Descends `segments` through a compiled spec tree."""
  curr = spec_schema
  for seg in segments:
    if isinstance(curr, dict) and seg in curr:
      node = curr[seg]
      curr = node.get("fields") or node.get("item_fields") or node
    else:
      return curr, seg
  return curr, ""


def _explain_path(
    query: str,
    root_key: str,
    kind_entry: dict[str, Any],
    resolved_vinfo: dict[str, Any],
) -> dict[str, Any]:
  """Resolves a dotted field path under `root_key` in `kind_entry`."""
  parts = [p for p in query.strip().split(".") if p]
  search_parts = parts[2:] if parts[1] == "spec" else parts[1:]
  node, missing = _walk_spec_schema(
      kind_entry.get("spec_schema", {}), search_parts
  )
  out: dict[str, Any] = {
      "detected_kueue_version": resolved_vinfo,
      "kind": root_key,
      "apiVersion": kind_entry.get("apiVersion"),
      "queried_path": query,
  }
  if missing:
    out["error"] = (
        f"Field '{missing}' not found under {root_key} in"
        f" {kind_entry.get('apiVersion')} (release"
        f" {resolved_vinfo.get('release_version')})"
    )
    out["valid_sibling_fields"] = (
        sorted(node.keys()) if isinstance(node, dict) else []
    )
  else:
    out["schema"] = node
  return out


def explain_schema_path(
    query: str,
    version_info: dict[str, Any] | None = None,
    load_live_crds: bool | None = None,
) -> dict[str, Any]:
  """Explains a Kueue Kind or dotted field path for the exact target Kueue version."""
  schema, resolved_vinfo = load_schema_for_version(
      version_info=version_info, load_live_crds=load_live_crds
  )
  if schema.get("_schema_unavailable"):
    return {
        "detected_kueue_version": resolved_vinfo,
        "queried_path": query,
        "error": "schema unavailable",
        "schema_notice": schema.get("_schema_notice", ""),
    }
  available_kinds = sorted(k for k in schema.keys() if not k.startswith("_"))
  parts = [p for p in query.strip().split(".") if p]
  if not parts:
    return {
        "detected_kueue_version": resolved_vinfo,
        "available_kinds": available_kinds,
    }
  kind_lookup = {k.lower(): k for k in available_kinds}
  root_key = kind_lookup.get(parts[0].lower())
  if not root_key:
    return {
        "detected_kueue_version": resolved_vinfo,
        "error": f"Unknown Kind '{parts[0]}'",
        "available_kinds": available_kinds,
    }
  kind_entry = schema[root_key]
  if len(parts) == 1 or (len(parts) == 2 and parts[1] == "spec"):
    return _explain_kind(root_key, kind_entry, resolved_vinfo)
  return _explain_path(query, root_key, kind_entry, resolved_vinfo)


def validate_yaml_blocks_in_draft(
    draft_text: str, version_info: dict[str, Any] | None = None
) -> list[str]:
  """Validates YAML snippets in `#### Remediation` against the exact target Kueue version's schema."""
  schema, resolved_vinfo = load_schema_for_version(version_info=version_info)
  return yaml_checks.check_remediation_yaml(draft_text, schema, resolved_vinfo)


# --- CLI ---------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
  """Builds the CLI argument parser for `kueue_schema`."""
  parser = argparse.ArgumentParser(
      description=(
          "Detect running Kueue version and query version-exact Kueue CRD"
          " & KueueConfiguration schemas."
      )
  )
  parser.add_argument(
      "--detect",
      action="store_true",
      help="Detect the target Kueue release version and active API version",
  )
  parser.add_argument(
      "--explain",
      default="",
      help="Explain a Kind or field path (e.g. ClusterQueue.spec.preemption)",
  )
  parser.add_argument(
      "--mode",
      default=report_output._env(  # pylint: disable=protected-access
          "GKE_KUEUE_TROUBLESHOOTING_MODE", "KUEUE_DIAGNOSE_MODE", "live"
      ),
      choices=["live", "offline_data", "logs_archive"],
      help="Data mode for version detection",
  )
  parser.add_argument(
      "--data-path",
      default=report_output._env(  # pylint: disable=protected-access
          "GKE_KUEUE_TROUBLESHOOTING_DATA_PATH", "KUEUE_DIAGNOSE_DATA_PATH"
      ),
      help="Path to offline bundle or logs directory for version detection",
  )
  report_output.add_kueue_version_arguments(parser, live_crds=True)
  report_output.add_no_remote_schema_argument(parser)
  return parser


def main() -> int:
  """Runs the `kueue_schema` CLI entrypoint."""
  args = _build_parser().parse_args()
  report_output.apply_no_remote_schema(args)
  live_crds_arg: bool | None = True if args.load_live_crds else None

  vinfo = detect_target_kueue_version(
      mode=args.mode,
      data_path=args.data_path,
      explicit_release_version=args.kueue_version,
      explicit_api_version=args.api_version,
  )

  if args.detect:
    _, resolved = load_schema_for_version(
        version_info=vinfo, load_live_crds=live_crds_arg
    )
    print(json.dumps(resolved, indent=2))
    return 0

  if args.explain:
    explained = explain_schema_path(
        args.explain, version_info=vinfo, load_live_crds=live_crds_arg
    )
    print(json.dumps(explained, indent=2))
    return 0

  schema, resolved = load_schema_for_version(
      version_info=vinfo, load_live_crds=live_crds_arg
  )
  print(
      json.dumps(
          {
              "detected_kueue_version": resolved,
              "kinds": sorted(
                  k for k in schema.keys() if not k.startswith("_")
              ),
          },
          indent=2,
      )
  )
  return 0


if __name__ == "__main__":
  sys.exit(main())
