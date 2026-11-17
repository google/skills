#!/usr/bin/env python3
"""Compiled Kueue schema registry: CRD documents -> compact per-Kind field trees.

Pure functions only (no network, no git, no kubectl):

  * `compile_crd_docs(crd_docs, target_short_ver, kcfg_fields_by_ver)` turns
  parsed
    `CustomResourceDefinition` documents into `{Kind: {apiVersion,
    kubectl_names,
    all_versions, top_level_spec_fields, spec_schema}}` plus a
    synthetic `KueueConfiguration` entry (not a CRD; its fields come from the
    published `kueue-config.<version>` reference page or the built-in defaults).
  * `read_cached_registry` / `write_cached_registry` persist compiled registries
    under `schema_cache_dir()` (`$GKE_KUEUE_TROUBLESHOOTING_CACHE_DIR`, else
    `$XDG_CACHE_HOME/gke-kueue-troubleshooting`).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from typing import Any, Iterable


def schema_cache_dir() -> str:
  """Per-user cache for downloaded/compiled schemas; never inside the skill directory."""
  base = (
      os.getenv("GKE_KUEUE_TROUBLESHOOTING_CACHE_DIR", "").strip()
      or os.getenv("KUEUE_DIAGNOSE_CACHE_DIR", "").strip()
  )
  if not base:
    xdg = os.getenv("XDG_CACHE_HOME", "").strip() or os.path.join(
        os.path.expanduser("~"), ".cache"
    )
    base = os.path.join(xdg, "gke-kueue-troubleshooting")
  try:
    os.makedirs(base, exist_ok=True)
    return base
  except OSError:
    fallback = os.path.join(
        tempfile.gettempdir(), "gke-kueue-troubleshooting-cache"
    )
    os.makedirs(fallback, exist_ok=True)
    return fallback


def safe_tag(tag: str) -> str:
  return re.sub(r"[^a-zA-Z0-9._-]", "_", tag)


DEFAULT_KCFG_FIELDS: dict[str, list[str]] = {
    "v1beta2": [
        "admissionFairSharing",
        "apiVersion",
        "clientConnection",
        "controller",
        "fairSharing",
        "featureGates",
        "health",
        "integrations",
        "internalCertManagement",
        "kind",
        "leaderElection",
        "manageJobsWithoutQueueName",
        "managedJobsNamespaceSelector",
        "metrics",
        "multiKueue",
        "namespace",
        "objectRetentionPolicies",
        "pprofBindAddress",
        "resources",
        "tls",
        "visibilityServer",
        "waitForPodsReady",
        "webhook",
    ],
    "v1beta1": [
        "admissionFairSharing",
        "apiVersion",
        "clientConnection",
        "controller",
        "fairSharing",
        "featureGates",
        "health",
        "integrations",
        "internalCertManagement",
        "kind",
        "leaderElection",
        "manageJobsWithoutQueueName",
        "managedJobsNamespaceSelector",
        "metrics",
        "multiKueue",
        "namespace",
        "objectRetentionPolicies",
        "pprofBindAddress",
        "queueVisibility",
        "resources",
        "tls",
        "waitForPodsReady",
        "webhook",
    ],
}


def _nested_properties(
    field_def: dict[str, Any], ftype: str, max_depth: int, depth: int
) -> tuple[str, dict[str, Any]]:
  """`("fields", tree)` for an object, `("item_fields", tree)` for an array of objects, else `("", {})`."""
  if ftype == "object" and "properties" in field_def:
    return "fields", _extract_openapi_properties(
        field_def, max_depth, depth + 1
    )
  items_def = field_def.get("items")
  if (
      ftype == "array"
      and isinstance(items_def, dict)
      and "properties" in items_def
  ):
    return "item_fields", _extract_openapi_properties(
        items_def, max_depth, depth + 1
    )
  return "", {}


def _field_info(
    field_def: dict[str, Any], max_depth: int, depth: int
) -> dict[str, Any]:
  """Builds the compact type, enum, and summary metadata for one field."""
  ftype = field_def.get("type", "object")
  desc = str(field_def.get("description") or "").strip().splitlines()
  info: dict[str, Any] = {"type": ftype}
  if field_def.get("enum"):
    info["enum"] = field_def["enum"]
  if desc and desc[0][:160]:
    info["summary"] = desc[0][:160]
  nested_key, nested = _nested_properties(field_def, ftype, max_depth, depth)
  if nested:
    info[nested_key] = nested
  return info


def _extract_openapi_properties(
    prop_schema: dict[str, Any], max_depth: int = 3, depth: int = 0
) -> dict[str, Any]:
  """Recursively compacts OpenAPI v3 properties into a concise field tree."""
  if not isinstance(prop_schema, dict) or depth >= max_depth:
    return {}
  props = prop_schema.get("properties") or {}
  return {
      field_name: _field_info(field_def, max_depth, depth)
      for field_name, field_def in sorted(props.items())
      if isinstance(field_def, dict)
  }


# Bump when the compiled schema shape changes so cached registries are rebuilt.
SCHEMA_FORMAT = 7

_HTML_HEADING_RE = re.compile(
    r"<h[23]\s+id=[^\s>]*?-([A-Za-z0-9_]+)><code>\1</code>"
)
_HTML_TBODY_RE = re.compile(r"<table[^>]*>.*?<tbody>(.*?)</tbody>", re.DOTALL)
_HTML_ROW_RE = re.compile(
    r"<tr>\s*<td><code>([^<]+)</code>(?:(?!</td).)*?<br>", re.DOTALL
)
_HTML_TYPE_LINK_RE = re.compile(r'href=["\']?#[^"\'>\s]*-([A-Za-z0-9_]+)["\']?')
# Nested-field tree used when the reference page is unavailable
# (`config_schema_source: builtin_defaults`).
DEFAULT_KCFG_NESTED: dict[str, dict[str, Any]] = {
    "v1beta2": {
        "waitForPodsReady": {
            "timeout": {},
            "blockAdmission": {},
            "recoveryTimeout": {},
            "requeuingStrategy": {
                "timestamp": {},
                "backoffLimitCount": {},
                "backoffBaseSeconds": {},
                "backoffMaxSeconds": {},
            },
        },
    },
    "v1beta1": {
        "waitForPodsReady": {
            "enable": {},
            "timeout": {},
            "blockAdmission": {},
            "recoveryTimeout": {},
            "requeuingStrategy": {
                "timestamp": {},
                "backoffLimitCount": {},
                "backoffBaseSeconds": {},
                "backoffMaxSeconds": {},
            },
        },
    },
}


def _html_type_tables(html_text: str) -> dict[str, list[tuple[str, str]]]:
  """Extracts `{TypeName: [(field_name, linked_type_or_empty), ...]}` from a kueue-config reference HTML page."""
  matches = list(_HTML_HEADING_RE.finditer(html_text))
  tables: dict[str, list[tuple[str, str]]] = {}
  for idx, m in enumerate(matches):
    tname = m.group(1)
    end = matches[idx + 1].start() if idx + 1 < len(matches) else len(html_text)
    tb = _HTML_TBODY_RE.search(html_text[m.end() : end])
    if not tb:
      continue
    rows: list[tuple[str, str]] = []
    for rm in _HTML_ROW_RE.finditer(tb.group(1)):
      fname = rm.group(1).strip()
      after = tb.group(1)[rm.end() : rm.end() + 600].split("</tr>", 1)[0]
      lm = _HTML_TYPE_LINK_RE.search(after)
      rows.append((fname, lm.group(1) if lm else ""))
    tables[tname] = rows
  return tables


def parse_kcfg_struct_tree_from_html(
    html_text: str, root: str = "Configuration", max_depth: int = 4
) -> dict[str, Any]:
  """Builds a nested `{field: {sub_field: {...}}}` tree for `root` from a published `kueue-config` reference HTML page."""
  tables = _html_type_tables(html_text)

  def _walk(
      type_name: str, depth: int, seen: tuple[str, ...]
  ) -> dict[str, Any]:
    rows = tables.get(type_name)
    if not rows or depth > max_depth or type_name in seen:
      return {}
    out: dict[str, Any] = {}
    for fname, linked in rows:
      if fname == "ControllerManager" or (
          fname.startswith("(") and "ControllerManager" in fname
      ):
        out.update(_walk("ControllerManager", depth, seen + (type_name,)))
        continue
      if fname in ("apiVersion", "kind") or fname.startswith("("):
        continue
      sub = (
          _walk(linked, depth + 1, seen + (type_name,))
          if linked in tables
          else {}
      )
      out[fname] = sub
    return out

  tree = _walk(root, 0, ())
  if isinstance(tree.get("integrations"), dict) and tree["integrations"]:
    tree["integrations"].setdefault(
        "podOptions", {"namespaceSelector": {}, "podSelector": {}}
    )
  return tree


def kcfg_fields_and_tree(html_text: str) -> dict[str, Any]:
  """Returns `{"fields": [...top-level...], "tree": {...nested...}}` for a `kueue-config` reference HTML page."""
  tree = parse_kcfg_struct_tree_from_html(html_text)
  fields = sorted({"apiVersion", "kind", *tree.keys()}) if tree else []
  return {"fields": fields, "tree": tree}


def _choose_crd_version(
    versions: list[Any], target_short_ver: str
) -> dict[str, Any] | None:
  """The requested version first; otherwise the storage version; otherwise the last one listed."""
  for v in versions:
    if isinstance(v, dict) and v.get("name") == target_short_ver:
      return v
  for v in versions:
    if isinstance(v, dict) and v.get("storage"):
      return v
  chosen = versions[-1]
  return chosen if isinstance(chosen, dict) else None


def _kubectl_names(names: dict[str, Any]) -> list[str]:
  """plural / singular / shortNames as `kubectl` accepts them (lower-cased, sorted, de-duplicated)."""
  return sorted({
      str(n).lower()
      for n in [
          names.get("plural"),
          names.get("singular"),
          *(names.get("shortNames") or []),
      ]
      if n
  })


def _compile_crd_entry(
    doc: dict[str, Any], target_short_ver: str
) -> tuple[str, dict[str, Any]] | None:
  """Compact registry entry `(Kind, entry)` for one Kueue CRD document, or None when it is not one."""
  spec = doc.get("spec") or {}
  group = spec.get("group", "kueue.x-k8s.io")
  names = spec.get("names") or {}
  kind = names.get("kind", "")
  versions = spec.get("versions") or []
  if "kueue.x-k8s.io" not in group or not kind or not versions:
    return None
  chosen_ver = _choose_crd_version(versions, target_short_ver)
  if chosen_ver is None:
    return None
  ver_name = chosen_ver.get("name", target_short_ver)
  open_api = (chosen_ver.get("schema") or {}).get("openAPIV3Schema") or {}
  spec_schema = (open_api.get("properties") or {}).get("spec") or {}
  spec_tree = _extract_openapi_properties(spec_schema, max_depth=3)
  return kind, {
      "apiVersion": f"{group}/{ver_name}",
      "kubectl_names": _kubectl_names(names),
      "all_versions": [
          f"{group}/{v.get('name')}"
          for v in versions
          if isinstance(v, dict) and v.get("name")
      ],
      "top_level_spec_fields": sorted(spec_tree.keys()),
      "spec_schema": spec_tree,
  }


def _kueue_configuration_entry(cfg_ver: str, cfg_entry: Any) -> dict[str, Any]:
  """Synthetic `KueueConfiguration` entry from a parsed Go tree (`{"fields", "tree"}`), a bare field list or the defaults."""
  cfg_tree: dict[str, Any] = {}
  if isinstance(cfg_entry, dict):
    cfg_fields = cfg_entry.get("fields") or []
    cfg_tree = cfg_entry.get("tree") or {}
  else:
    cfg_fields = cfg_entry or []
  if not cfg_fields:
    cfg_fields = DEFAULT_KCFG_FIELDS.get(
        cfg_ver, DEFAULT_KCFG_FIELDS["v1beta2"]
    )
  if not cfg_tree:
    cfg_tree = DEFAULT_KCFG_NESTED.get(cfg_ver, DEFAULT_KCFG_NESTED["v1beta2"])
  return {
      "apiVersion": f"config.kueue.x-k8s.io/{cfg_ver}",
      "all_versions": [
          "config.kueue.x-k8s.io/v1beta2",
          "config.kueue.x-k8s.io/v1beta1",
      ],
      "top_level_spec_fields": sorted(cfg_fields),
      "nested_fields": cfg_tree,
  }


def config_version_for(target_short_ver: str) -> str:
  """`config.kueue.x-k8s.io` version served by the release whose storage version is `target_short_ver`."""
  return "v1beta1" if target_short_ver == "v1beta1" else "v1beta2"


def compile_crd_docs(
    crd_docs: Iterable[dict[str, Any]],
    target_short_ver: str = "v1beta2",
    kcfg_fields_by_ver: dict[str, Any] | None = None,
) -> dict[str, Any]:
  """Compiles a list of parsed CRD YAML documents into a compact schema dict for `target_short_ver`."""
  registry: dict[str, Any] = {}
  for doc in crd_docs:
    if not isinstance(doc, dict):
      continue
    compiled = _compile_crd_entry(doc, target_short_ver)
    if compiled is not None:
      registry[compiled[0]] = compiled[1]
  cfg_ver = config_version_for(target_short_ver)
  registry["KueueConfiguration"] = _kueue_configuration_entry(
      cfg_ver, (kcfg_fields_by_ver or {}).get(cfg_ver)
  )
  return registry


def read_cached_registry(cache_file: str) -> dict[str, Any] | None:
  """Reads a compiled schema registry from `cache_file` if its format matches."""
  if not os.path.isfile(cache_file):
    return None
  try:
    with open(cache_file, "r", encoding="utf-8") as f:
      cached = json.load(f)
  except (OSError, json.JSONDecodeError):
    return None
  if (
      isinstance(cached, dict)
      and any(not k.startswith("_") for k in cached)
      and cached.get("_schema_format") == SCHEMA_FORMAT
      and cached.get("_target_short_ver")
  ):
    return cached
  return None


def write_cached_registry(
    cache_file: str, compiled: dict[str, Any], short_ver: str
) -> None:
  """Atomically writes a compiled schema registry to `cache_file`."""
  payload = dict(compiled)
  payload["_schema_format"] = SCHEMA_FORMAT
  payload["_target_short_ver"] = short_ver
  try:
    tmp_path = f"{cache_file}.tmp.{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
      json.dump(payload, f, indent=1)
    os.replace(tmp_path, cache_file)
  except OSError:
    pass
