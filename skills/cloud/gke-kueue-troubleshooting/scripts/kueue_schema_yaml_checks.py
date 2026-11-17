#!/usr/bin/env python3
"""Checks of the YAML manifests under `#### Remediation` against a loaded Kueue schema.

`check_remediation_yaml(draft_text, schema, version_info)` is pure: it receives
the
compiled registry (see `kueue_schema_registry`) and the resolved version info
and
returns the warning strings `validate_report.py` reports as `schema_warnings`.
`kueue_schema.validate_yaml_blocks_in_draft` loads the schema and delegates
here.

Pipeline per fenced ```yaml block: decode (a `ConfigMap` additionally yields the
`controller_manager_config.yaml` document it embeds) -> per document: apiVersion
consistency -> field names (`KueueConfiguration` top-level + nested Go-struct
tree,
or `spec.*` of a CRD Kind, with the `cohort` / `cohortName` rename called out).
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any

import k8s_objects
import kueue_schema_registry as registry
import kueue_version
import yaml

_YAML_FENCE_RE = re.compile(r"```(?:yaml|yml)\s*(.*?)```", re.DOTALL)
_KUEUE_API_PREFIXES = ("kueue.x-k8s.io/", "config.kueue.x-k8s.io/")


@dataclasses.dataclass(frozen=True)
class YamlCheckContext:
  """Loaded schema and detected version against which documents are checked."""

  schema: dict[str, Any]
  short_api: str
  release_ver: str
  schema_unavailable: bool
  version_detected: bool

  @classmethod
  def from_schema(
      cls, schema: dict[str, Any], version_info: dict[str, Any]
  ) -> "YamlCheckContext":
    return cls(
        schema=schema,
        short_api=version_info.get("short_api_version", "v1beta2"),
        release_ver=version_info.get("release_version", "unknown"),
        schema_unavailable=bool(schema.get("_schema_unavailable")),
        version_detected=any(
            not str(src).startswith("default:")
            for src in version_info.get("detection_sources") or []
        ),
    )


def remediation_yaml_blocks(draft_text: str) -> list[str]:
  """Bodies of fenced yaml/yml blocks after the `#### Remediation` header."""
  if "#### Remediation" not in draft_text:
    return []
  rem_section = draft_text.split("#### Remediation", 1)[1]
  return _YAML_FENCE_RE.findall(rem_section)


def decode_yaml_block(block: str, warnings: list[str]) -> list[Any]:
  """Decodes YAML documents in `block`, expanding embedded ConfigMap configs.

  An undecodable block yields nothing; an undecodable embedded configuration
  appends a warning (the controller would fail to start on it).

  Args:
    block: Raw YAML text from one fenced remediation code block.
    warnings: Mutable list receiving syntax warnings for embedded configs.

  Returns:
    Decoded YAML documents, including any embedded controller configuration.
  """
  try:
    docs = list(yaml.safe_load_all(block))
  except yaml.YAMLError:
    return []
  expanded: list[Any] = []
  for doc in docs:
    expanded.append(doc)
    if not (
        isinstance(doc, dict) and str(doc.get("kind") or "") == "ConfigMap"
    ):
      continue
    data = doc.get("data")
    embedded = (
        data.get(k8s_objects.KUEUE_CONFIG_KEY)
        if isinstance(data, dict)
        else None
    )
    if not isinstance(embedded, str):
      continue
    try:
      expanded.extend(yaml.safe_load_all(embedded))
    except yaml.YAMLError:
      warnings.append(
          "ConfigMap data 'controller_manager_config.yaml' is not valid"
          " YAML; the controller will fail to start."
      )
  return expanded


def _registry_kind(kind: str, api_ver: str) -> str:
  """Maps `Configuration` under `config.kueue.x-k8s.io` to `KueueConfiguration`."""
  if kind == "Configuration" and (
      not api_ver or api_ver.startswith("config.kueue.x-k8s.io/")
  ):
    return "KueueConfiguration"
  return kind


def _api_version_only_warnings(
    kind: str, api_ver: str, ctx: YamlCheckContext
) -> list[str]:
  """Checks `apiVersion` alone when the schema is unavailable."""
  if (
      ctx.version_detected
      and api_ver.startswith(_KUEUE_API_PREFIXES)
      and kueue_version.normalize_short_api_version(api_ver) != ctx.short_api
  ):
    return [
        f"apiVersion '{api_ver}' for {kind} does not match the detected"
        f" API version {ctx.short_api} (release {ctx.release_ver}). Field names"
        " were not checked: schema unavailable."
    ]
  return []


def _api_version_warnings(
    kind: str, api_ver: str, entry: dict[str, Any], ctx: YamlCheckContext
) -> list[str]:
  """Checks `api_ver` against the target release's expected API versions."""
  expected_api = str(entry.get("apiVersion") or "")
  all_supported = set(entry.get("all_versions") or [expected_api])
  if not api_ver:
    return []
  if (
      ctx.short_api == "v1beta2"
      and "v1beta1" in api_ver
      and "v1beta2" in expected_api
  ):
    return [
        f"Outdated apiVersion '{api_ver}' for {kind}: target cluster"
        f" (release {ctx.release_ver}) uses '{expected_api}'."
    ]
  if ctx.short_api == "v1beta1" and api_ver not in all_supported:
    return [
        f"Unsupported apiVersion '{api_ver}' for {kind} in target Kueue"
        f" release {ctx.release_ver}: supported versions are"
        f" {sorted(all_supported)} (expected '{expected_api}')."
    ]
  return []


def _unknown_nested_config_fields(
    doc: dict[str, Any],
    tree: dict[str, Any],
    labels: tuple[str, str],
    path: str = "",
) -> list[str]:
  """Reports unknown nested fields in a `KueueConfiguration` document.

  Only blocks present in `tree` are descended into; a block whose tree entry is
  empty (`{}`) is a leaf or an unparsed type and is accepted as-is.

  Args:
    doc: Current mapping node within the `KueueConfiguration` document.
    tree: Reference nested field tree for the current level.
    labels: Tuple of `(expected_api, release_ver)` for warning messages.
    path: Dotted field prefix accumulated during recursion.

  Returns:
    Warning strings for unknown nested configuration fields.
  """
  expected_api, release_ver = labels
  out: list[str] = []
  for key, value in doc.items():
    sub_tree = tree.get(key)
    if not isinstance(sub_tree, dict) or not sub_tree:
      continue
    children = value if isinstance(value, list) else [value]
    for child in children:
      if not isinstance(child, dict):
        continue
      here = f"{path}{key}"
      for child_key in child:
        if child_key not in sub_tree:
          out.append(
              f"Unknown field '{here}.{child_key}' in KueueConfiguration for"
              f" {expected_api} (release {release_ver})."
              f" Valid fields under '{here}':"
              f" {sorted(sub_tree)}."
          )
      out.extend(
          _unknown_nested_config_fields(
              child, sub_tree, labels, path=f"{here}."
          )
      )
  return out


def _kueue_configuration_warnings(
    doc: dict[str, Any], entry: dict[str, Any], ctx: YamlCheckContext
) -> list[str]:
  """Checks top-level and nested field names of a `KueueConfiguration` doc."""
  expected_api = str(entry.get("apiVersion") or "")
  valid_top = set(entry["top_level_spec_fields"])
  warnings = [
      f"Unknown field '{k}' in KueueConfiguration for"
      f" {expected_api} (release {ctx.release_ver})."
      f" Valid fields: {sorted(valid_top)}."
      for k in doc
      if k not in valid_top
  ]
  cfg_short = (
      kueue_version.normalize_short_api_version(expected_api) or "v1beta2"
  )
  nested_tree = entry.get("nested_fields") or registry.DEFAULT_KCFG_NESTED.get(
      cfg_short, {}
  )
  warnings.extend(
      _unknown_nested_config_fields(
          doc, nested_tree, (expected_api, ctx.release_ver)
      )
  )
  return warnings


def _cohort_rename_warning(
    spec: dict[str, Any],
    valid_spec: set[str],
    expected_api: str,
    release_ver: str,
) -> list[str]:
  """Flags `spec.cohort` vs `spec.cohortName` mismatches for `ClusterQueue`."""
  if (
      "cohort" in spec
      and "cohortName" in valid_spec
      and "cohort" not in valid_spec
  ):
    return [
        "Deprecated field 'spec.cohort' in ClusterQueue YAML: use"
        f" 'spec.cohortName' in {expected_api} (release {release_ver})."
    ]
  if (
      "cohortName" in spec
      and "cohort" in valid_spec
      and "cohortName" not in valid_spec
  ):
    return [
        f"Field 'spec.cohortName' is not supported in {expected_api}"
        f" (release {release_ver}): use 'spec.cohort' in v1beta1."
    ]
  return []


def _spec_field_warnings(
    kind: str, doc: dict[str, Any], entry: dict[str, Any], ctx: YamlCheckContext
) -> list[str]:
  """Checks top-level `spec` fields of a Kueue CRD manifest against `entry`."""
  spec = doc.get("spec")
  if not isinstance(spec, dict):
    return []
  expected_api = str(entry.get("apiVersion") or "")
  valid_spec = set(entry.get("top_level_spec_fields") or [])
  warnings: list[str] = []
  if kind == "ClusterQueue":
    warnings.extend(
        _cohort_rename_warning(spec, valid_spec, expected_api, ctx.release_ver)
    )
  for k in spec:
    if valid_spec and k not in valid_spec and k not in ("cohort", "cohortName"):
      warnings.append(
          f"Unknown field 'spec.{k}' in {kind} ({expected_api}, release"
          f" {ctx.release_ver}). Valid spec fields: {sorted(valid_spec)}."
      )
  return warnings


def check_document(doc: Any, ctx: YamlCheckContext) -> list[str]:
  """Warnings for one decoded YAML document (non-mapping documents are ignored)."""
  if not isinstance(doc, dict):
    return []
  kind = str(doc.get("kind") or "")
  api_ver = str(doc.get("apiVersion") or "")
  if ctx.schema_unavailable:
    return _api_version_only_warnings(kind, api_ver, ctx)
  kind = _registry_kind(kind, api_ver)
  if not kind or kind.startswith("_") or kind not in ctx.schema:
    return []
  entry = ctx.schema[kind]
  warnings = _api_version_warnings(kind, api_ver, entry, ctx)
  if kind == "KueueConfiguration":
    warnings.extend(_kueue_configuration_warnings(doc, entry, ctx))
  else:
    warnings.extend(_spec_field_warnings(kind, doc, entry, ctx))
  return warnings


def check_remediation_yaml(
    draft_text: str, schema: dict[str, Any], version_info: dict[str, Any]
) -> list[str]:
  """All schema warnings for the YAML blocks under `#### Remediation`, in document order."""
  ctx = YamlCheckContext.from_schema(schema, version_info)
  warnings: list[str] = []
  for block in remediation_yaml_blocks(draft_text):
    for doc in decode_yaml_block(block, warnings):
      warnings.extend(check_document(doc, ctx))
  return warnings
