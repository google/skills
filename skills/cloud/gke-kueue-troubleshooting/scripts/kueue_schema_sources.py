#!/usr/bin/env python3
"""Schema source chain for the `gke-kueue-troubleshooting` skill.

`resolve_schema(request)` tries `SCHEMA_SOURCES` in order and returns the first
`SchemaResult`; when none yields a schema it returns the explicit
"unavailable" schema whose `_schema_notice` names every remedy:

  1. `from_bundle_crds`     — `CustomResourceDefinition` objects shipped in the
  bundle;
  2. `from_live_crds`       — the live cluster's CRDs (`live` mode, or forced);
  3. `from_git_tag`         — a local Kueue checkout at the release tag;
  4. `from_github_release`  — the upstream release manifests (cached per user).

Every source is `(request: SchemaRequest) -> SchemaResult | None`. The request
carries the version to load and a `SchemaAdapters` bundle of callables that do
the actual I/O (kubectl, git, HTTP, compile-with-KueueConfiguration), so this
module stays free of network/subprocess code and the callables remain
patchable on `kueue_schema`.
"""

from __future__ import annotations

import dataclasses
import os
from typing import Any, Callable

import kueue_schema_registry as registry
import kueue_version

CompileWithKcfg = Callable[[list[dict[str, Any]]], dict[str, Any]]


@dataclasses.dataclass(frozen=True)
class SchemaAdapters:
  """I/O entry points used by the sources; see `kueue_schema` for implementations."""

  fetch_live_crds: Callable[[], tuple[list[dict[str, Any]], str]]
  resolve_git_tag: Callable[[str], str]
  load_git_tag_schema: Callable[[str, str], tuple[dict[str, Any] | None, str]]
  fetch_github_crds: Callable[[str], tuple[list[dict[str, Any]], str]]
  compile_with_kcfg: CompileWithKcfg
  repo_dir: str = ""


@dataclasses.dataclass
class SchemaRequest:
  """Inputs, policy, and live-CRD error state for a schema resolution run."""

  short_api: str
  release_ver: str
  raw_items: list[dict[str, Any]]
  load_live_crds: bool
  allow_remote_fetch: bool
  adapters: SchemaAdapters
  live_crds_error: str = dataclasses.field(default="", init=False)

  @property
  def has_release(self) -> bool:
    return bool(self.release_ver) and self.release_ver != "unknown"


@dataclasses.dataclass(frozen=True)
class SchemaResult:
  """Resolved schema dictionary paired with its provenance label."""

  schema: dict[str, Any]
  source: str


SchemaSource = Callable[[SchemaRequest], "SchemaResult | None"]


def is_kueue_crd(obj: Any) -> bool:
  """True for a parsed `CustomResourceDefinition` whose group is under `kueue.x-k8s.io`."""
  return (
      isinstance(obj, dict)
      and obj.get("kind") == "CustomResourceDefinition"
      and "kueue.x-k8s.io" in str(((obj.get("spec") or {}).get("group")) or "")
  )


def from_bundle_crds(request: SchemaRequest) -> SchemaResult | None:
  """CRDs shipped inside the bundle (`raw_items`)."""
  bundled = [it for it in request.raw_items if is_kueue_crd(it)]
  if not bundled:
    return None
  return SchemaResult(
      request.adapters.compile_with_kcfg(bundled),
      f"bundled_crds({len(bundled)} CRDs, {request.short_api})",
  )


def from_live_crds(request: SchemaRequest) -> SchemaResult | None:
  """CRDs of the live cluster; records the failure reason on the request when none are returned."""
  if not request.load_live_crds:
    return None
  live_crds, err = request.adapters.fetch_live_crds()
  if live_crds:
    return SchemaResult(
        request.adapters.compile_with_kcfg(live_crds),
        f"live_cluster_crds({len(live_crds)} CRDs, {request.short_api})",
    )
  request.live_crds_error = (
      err or "`kubectl get crd` returned no kueue.x-k8s.io CRDs"
  )
  return None


def from_git_tag(request: SchemaRequest) -> SchemaResult | None:
  """A local Kueue checkout at the (closest) release tag."""
  if not request.has_release:
    return None
  matched_tag = request.adapters.resolve_git_tag(request.release_ver)
  if not matched_tag:
    return None
  tag_schema, tag_src = request.adapters.load_git_tag_schema(
      matched_tag, request.short_api
  )
  if not tag_schema:
    return None
  return SchemaResult(tag_schema, f"{tag_src}({request.short_api})")


def from_github_release(request: SchemaRequest) -> SchemaResult | None:
  """Upstream GitHub release manifests, cached per user under `schema_cache_dir()`."""
  if not request.has_release or not request.allow_remote_fetch:
    return None
  tag = kueue_version.normalize_release_tag(request.release_ver)
  cache_file = os.path.join(
      registry.schema_cache_dir(),
      f"crd_schema_github_{registry.safe_tag(tag)}_{request.short_api}.json",
  )
  cached = registry.read_cached_registry(cache_file)
  if cached is not None:
    return SchemaResult(
        cached, f"github_release_cache:{tag}({request.short_api})"
    )
  remote_crds, used_tag = request.adapters.fetch_github_crds(
      request.release_ver
  )
  if not remote_crds:
    return None
  compiled = request.adapters.compile_with_kcfg(remote_crds)
  registry.write_cached_registry(cache_file, compiled, request.short_api)
  return SchemaResult(
      compiled, f"github_release:{used_tag}({request.short_api})"
  )


SCHEMA_SOURCES: tuple[SchemaSource, ...] = (
    from_bundle_crds,
    from_live_crds,
    from_git_tag,
    from_github_release,
)


def _unavailable_reasons(request: SchemaRequest) -> list[str]:
  """Collects human-readable reasons why no schema source succeeded."""
  reasons: list[str] = []
  if request.live_crds_error:
    reasons.append(request.live_crds_error)
  else:
    reasons.append("no cluster access (mode is not `live`)")
  if not request.has_release:
    reasons.append("Kueue release version could not be detected")
    return reasons
  reasons.append(
      "no local Kueue checkout with tag"
      f" {kueue_version.normalize_release_tag(request.release_ver)}"
      + (
          ""
          if request.adapters.repo_dir
          else " (set GKE_KUEUE_TROUBLESHOOTING_KUEUE_REPO to use one)"
      )
  )
  if not request.allow_remote_fetch:
    reasons.append("remote schema download disabled (--no-remote-schema)")
  else:
    reasons.append("GitHub release manifests could not be fetched")
  return reasons


def unavailable_schema(request: SchemaRequest) -> SchemaResult:
  """Nothing reachable: say so explicitly instead of substituting a stale snapshot."""
  schema: dict[str, Any] = {
      "_schema_unavailable": True,
      "_config_schema_source": "unavailable",
      "_schema_notice": (
          "The Kueue schema for this incident is unavailable: "
          + "; ".join(_unavailable_reasons(request))
          + ". Diagnosis can continue from the incident data, but field-level"
          " schema checks are skipped and the model's built-in knowledge of"
          " Kueue may not match this release. To get release-exact checks"
          " provide one of: cluster access, `kubectl get crd -o json` output"
          " in the bundle, a local Kueue checkout"
          " (GKE_KUEUE_TROUBLESHOOTING_KUEUE_REPO), network access to GitHub,"
          " or an explicit --kueue-version when the release is unknown."
      ),
  }
  return SchemaResult(schema, "unavailable")


def resolve_schema(request: SchemaRequest) -> SchemaResult:
  """First `SchemaResult` from `SCHEMA_SOURCES`, else the unavailable schema."""
  for source in SCHEMA_SOURCES:
    result = source(request)
    if result is not None:
      return result
  return unavailable_schema(request)
