#!/usr/bin/env python3
"""Kueue cluster-state snapshot compaction for the `gke-kueue-troubleshooting` skill.

Collects the Kueue admission graph (Workloads, LocalQueues, ClusterQueues,
Cohorts,
ResourceFlavors, AdmissionChecks, ProvisioningRequestConfigs, Topologies, the
controller ConfigMap) plus the Jobs, Pods, Events and Nodes around it, and
emits:

  * `active_api_schema_reference` — CRD / KueueConfiguration schema for the
  detected
    Kueue release (see `kueue_schema.py`), so the agent writes remediation YAML
    in
    the right API version;
  * `derived_graph_diagnostics` — neutral, mechanically derived facts
  (inventory,
    Warning events, quota arithmetic, label matching, configuration values). The
    script never ranks causes or prescribes report content;
  * `kueue_graph_objects` — sanitised, compacted objects, priority-ordered and
  capped
    by `--max-output-bytes`.

`--action explain --kind <Kind[.field.path]>` answers schema questions for the
detected version using the loaded schema (live CRDs in `live` mode, or
offline/cached schemas in `offline_data` / `logs_archive`).

Sources (`--mode`): `live` via `kubectl`, `offline_data` from a directory of
manifests, `logs_archive` (no manifests) delegates to `trace_logs.py`. No cloud
SDKs or provider CLIs are used.

Module map: `snapshot_loaders.py` reads, sanitises, filters and groups objects
and maintains the ledger; `snapshot_facts.py` holds the fact emitters;
`k8s_objects.py` provides tolerant accessors for Kubernetes dicts. This module
keeps the CLI, the fact orchestrator and the stdout digest budget.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from typing import Any

import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
  sys.path.insert(0, SCRIPT_DIR)

# pylint: disable=g-import-not-at-top,wrong-import-position,g-bad-import-order
import k8s_objects
import kueue_schema
import report_output
import snapshot_facts
import snapshot_loaders

# pylint: enable=g-import-not-at-top,wrong-import-position,g-bad-import-order

FactContext = snapshot_facts.FactContext
LedgerInputs = snapshot_loaders.LedgerInputs
LoadError = snapshot_loaders.LoadError
compact_managed_fields = k8s_objects.compact_managed_fields
filter_and_sort_snapshot_items = snapshot_loaders.filter_and_sort_snapshot_items
group_bulk_objects = snapshot_loaders.group_bulk_objects
load_items = snapshot_loaders.load_items
load_static_items = snapshot_loaders.load_static_items
sample_bulk_groups = snapshot_loaders.sample_bulk_groups
sanitize_and_compact_object = snapshot_loaders.sanitize_and_compact_object
update_ledger = snapshot_loaders.update_ledger
_event_timestamp = k8s_objects.event_timestamp

__all__ = [
    "FactContext",
    "LedgerInputs",
    "LoadError",
    "compact_managed_fields",
    "compute_derived_diagnostics",
    "compute_derived_facts",
    "filter_and_sort_snapshot_items",
    "group_bulk_objects",
    "load_items",
    "load_static_items",
    "main",
    "sample_bulk_groups",
    "sanitize_and_compact_object",
    "update_ledger",
]

_parse_quantity = report_output.parse_quantity

# Order in which keyed facts receive ids when the per-source cap applies
# (lower = earlier). Grouped Warning events come last because they are the
# most numerous and usually restate a condition already listed.
_FACT_PRIORITY = {
    "condition": 0,
    "config": 0,
    "provreq": 1,
    "workload-pods": 1,
    "pod-status": 1,
    "job-spec": 1,
    "unreferenced-ac": 1,
    "nodeselector": 1,
    "tas-domains": 1,
    "node-cond": 1,
    "queue-chain": 1,
    "podset-flavor": 2,
    "cohort-overcommit": 2,
    "fair-sharing": 2,
    "cohort-layout": 3,
    "deletion": 3,
    "workload-lifecycle": 4,
    "inventory": 4,
    "event": 6,
}

_YAML_WIDTH = 100000


class _PyFullDumper(yaml.SafeDumper):
  """Safe YAML dumper that writes every object out in full.

  The stock dumper turns an object that is referenced twice into `&id001` /
  `*id001`. That is fine in the digest, which is read as a whole, but not in
  the full report, which is read by line range: the anchor is usually outside
  the range.
  """

  def ignore_aliases(self, data: Any) -> bool:
    return True


class _CFullDumper(getattr(yaml, "CSafeDumper", yaml.SafeDumper)):
  """`_PyFullDumper` on the libyaml emitter."""

  def ignore_aliases(self, data: Any) -> bool:
    return True


# libyaml is used when PyYAML was built with it. Both emitters write the same
# text for ordinary manifests and equivalent YAML otherwise (they differ on
# mapping keys that are empty, 128 or more characters long or not printable
# ASCII, and on where a string longer than the line width is folded).
_use_libyaml = hasattr(yaml, "CSafeDumper")


def _dumper(aliases: bool) -> Any:
  if aliases:
    return yaml.CSafeDumper if _use_libyaml else yaml.SafeDumper
  return _CFullDumper if _use_libyaml else _PyFullDumper


def _dump(payload: Any, aliases: bool = False) -> str:
  """YAML text of `payload`; `aliases` keeps `&id001` anchors for shared objects (digest only)."""
  global _use_libyaml  # pylint: disable=global-statement
  try:
    return yaml.dump(
        payload, Dumper=_dumper(aliases), sort_keys=False, width=_YAML_WIDTH
    )
  except (UnicodeError, yaml.YAMLError):
    if not _use_libyaml:
      raise
  # libyaml refuses what the Python emitter escapes (a lone surrogate from a
  # JSON `\ud800` escape). The switch is kept for the rest of the run, so the
  # sizes measured while trimming and the printed text come from one emitter.
  _use_libyaml = False
  return yaml.dump(
      payload, Dumper=_dumper(aliases), sort_keys=False, width=_YAML_WIDTH
  )


# ---------------------------------------------------------------------------
# Derived facts
# ---------------------------------------------------------------------------


def compute_derived_diagnostics(items: list[dict[str, Any]]) -> list[str]:
  """Returns the derived facts as plain strings (see `compute_derived_facts`)."""
  return [text for _, text in compute_derived_facts(items)]


def compute_derived_facts(
    items: list[dict[str, Any]],
) -> list[tuple[str | None, str]]:
  """Computes neutral, verifiable facts about the Kueue admission graph.

  Every entry is `(key, statement)`. The statement is derived mechanically from
  the snapshot (counts, status conditions, quota arithmetic, label matching,
  configuration values) plus, where useful, one sentence of version-independent
  Kueue API semantics. `key` is non-None for facts the report is expected to
  classify explicitly (conditions, Warning events, deletions, request/flavor
  mismatches); it groups equivalent facts so they share one id. The function
  does NOT rank causes, recommend fixes, or tell the reader what to include in
  or exclude from a report — interpretation is left to the diagnosing agent.

  The sections live in `snapshot_facts.FACT_EMITTERS`; their order is the
  order of the facts in the digest.

  Args:
    items: Raw Kubernetes object mappings in the snapshot.

  Returns:
    Ordered `(group_key_or_none, fact_statement)` tuples.
  """
  ctx = FactContext.from_items(items)
  for emit in snapshot_facts.FACT_EMITTERS:
    try:
      emit(ctx)
    except Exception as exc:  # pylint: disable=broad-exception-caught
      # One malformed object stops its own section only; the facts of every
      # other section (and those this one had already added) are kept.
      ctx.add(None, _unavailable_note(getattr(emit, "__name__", ""), exc))
  return ctx.notes


def _unavailable_note(section: str, exc: Exception) -> str:
  detail = " ".join(f"{type(exc).__name__}: {exc}".split())[:300]
  scope = f" ({section})" if section else ""
  return (
      f"DERIVED_DIAGNOSTICS_UNAVAILABLE{scope}: {detail}; the facts of this"
      " section are incomplete"
  )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
      description=(
          "Compacts Kueue cluster state (live or from a bundle) into a"
          " schema-annotated snapshot with derived facts."
      )
  )
  _add_selection_arguments(parser)
  _add_schema_and_output_arguments(parser)
  report_output.add_ignore_namespaces_argument(parser)
  return parser


def _add_selection_arguments(parser: argparse.ArgumentParser) -> None:
  """Source mode, action and object selection flags."""
  parser.add_argument(
      "--mode",
      choices=["live", "offline_data", "logs_archive"],
      default=report_output._env(  # pylint: disable=protected-access
          "GKE_KUEUE_TROUBLESHOOTING_MODE", "KUEUE_DIAGNOSE_MODE", "live"
      ),
      help=(
          "live: kubectl; offline_data: directory of YAML/JSON manifests (+"
          " optional logs/); logs_archive: no manifests available, delegates to"
          " trace_logs.py"
      ),
  )
  parser.add_argument(
      "--action",
      choices=["snapshot", "list", "get", "events", "explain"],
      default="",
      help=(
          "Action: 'snapshot', 'list', 'get', 'events', or 'explain' (queries"
          " version-aware Kueue CRD schema)."
      ),
  )
  parser.add_argument(
      "--kind",
      default="all",
      help=(
          "Kubernetes resource kind (or dotted field path for --action explain,"
          " e.g. ClusterQueue.spec.preemption)"
      ),
  )
  parser.add_argument("--name", default="", help="Resource name (for get)")
  parser.add_argument(
      "-n",
      "--namespace",
      dest="namespace",
      default="",
      help="Optional namespace",
  )
  parser.add_argument(
      "--data-path",
      "--source",
      dest="data_path",
      default=report_output._env(  # pylint: disable=protected-access
          "GKE_KUEUE_TROUBLESHOOTING_DATA_PATH", "KUEUE_DIAGNOSE_DATA_PATH"
      ),
      help=(
          "Path to a directory (or single file) of YAML/JSON manifests for"
          " offline_data"
      ),
  )
  report_output.add_ledger_path_argument(
      parser, "Optional path to coverage_ledger.json", "--ledger"
  )


def _add_schema_and_output_arguments(parser: argparse.ArgumentParser) -> None:
  """Kueue version / schema source flags and the stdout budget."""
  report_output.add_kueue_version_arguments(parser, live_crds=True)
  report_output.add_no_remote_schema_argument(parser)
  report_output.add_kueue_namespace_argument(
      parser,
      "Namespace where the Kueue controller and kueue-manager-config live"
      " (default kueue-system)",
  )
  report_output.add_max_output_bytes_argument(
      parser,
      48000,
      "Cap on the stdout digest (schema field lists, then lowest-priority"
      " objects are dropped); the complete snapshot is always written to"
      " full_report_file next to the ledger",
  )


def _print_error(message: str, next_step: str) -> int:
  return report_output.emit_error(message, next_step, render=_dump)


def _live_crds_arg(args: argparse.Namespace) -> bool | None:
  return True if args.load_live_crds else None


def _is_snapshot_request(args: argparse.Namespace, action: str) -> bool:
  return action == "snapshot" or args.kind.lower() == "all"


def _resolve_action(args: argparse.Namespace) -> str:
  if args.action:
    return args.action
  if args.kind.lower() in ("all", "snapshot", ""):
    return "snapshot"
  if args.kind.lower() in ("event", "events"):
    return "events"
  if args.name:
    return "get"
  return "get" if args.kind else "snapshot"


def run_explain(args: argparse.Namespace) -> int:
  """`--action explain`: prints the schema of a Kind / field path for the detected Kueue version."""
  ledger_vinfo = None
  if (
      args.ledger_path
      and os.path.exists(args.ledger_path)
      and not args.kueue_version
      and not args.api_version
  ):
    ledger_vinfo = report_output.load_ledger(args.ledger_path, strict=True).get(
        "detected_kueue_version"
    )
  vinfo = ledger_vinfo or kueue_schema.detect_target_kueue_version(
      mode=args.mode,
      data_path=args.data_path,
      explicit_release_version=args.kueue_version,
      explicit_api_version=args.api_version,
      kueue_namespace=args.kueue_namespace,
  )
  out_str = yaml.safe_dump(
      kueue_schema.explain_schema_path(
          args.kind,
          version_info=vinfo,
          load_live_crds=_live_crds_arg(args),
      ),
      sort_keys=False,
  )
  sys.stdout.write(out_str)
  return 0


def _run_logs_archive(args: argparse.Namespace) -> int:
  """Delegates `logs_archive` mode to `trace_logs.py` when no manifests exist."""
  trace_script = os.path.join(SCRIPT_DIR, "trace_logs.py")
  cmd = [
      sys.executable,
      trace_script,
      "--mode",
      args.mode,
      "--kueue-namespace",
      args.kueue_namespace,
  ]
  if args.data_path:
    cmd.extend(["--data-path", args.data_path])
  if args.ledger_path:
    cmd.extend(["--ledger-path", args.ledger_path])
  if args.kueue_version:
    cmd.extend(["--kueue-version", args.kueue_version])
  if args.api_version:
    cmd.extend(["--api-version", args.api_version])
  res = subprocess.run(cmd, capture_output=True, text=True, check=False)
  sys.stdout.write(res.stdout)
  if res.returncode != 0:
    sys.stderr.write(res.stderr)
  return res.returncode


# ---------------------------------------------------------------------------
# list / get / events
# ---------------------------------------------------------------------------


def _condition_summary(cond: dict[str, Any]) -> str:
  message = str(cond.get("message") or "")[:120]
  return (
      f"{cond.get('type')}={cond.get('status')}({cond.get('reason')}:"
      f" {message})"
  )


def _list_summary_rows(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """Builds compact kind/namespace/name/conditions rows for the list action."""
  summary_rows = []
  for x in (sanitize_and_compact_object(x) for x in raw_items):
    if not isinstance(x, dict):
      continue
    m = k8s_objects.metadata(x)
    summary_rows.append({
        "kind": x.get("kind"),
        "namespace": m.get("namespace", ""),
        "name": m.get("name", ""),
        "conditions": [
            _condition_summary(c) for c in k8s_objects.conditions(x)
        ],
    })
  return summary_rows


def _compact_keep_dups(obj: dict[str, Any]) -> dict[str, Any]:
  compacted = sanitize_and_compact_object(obj)
  if isinstance(obj, dict) and obj.get("_yaml_duplicate_keys"):
    return {"_yaml_duplicate_keys": obj["_yaml_duplicate_keys"], **compacted}
  return compacted


def _print_and_record(out_str: str, inputs: LedgerInputs) -> int:
  """Prints the output and records it in the ledger; a failure of one does not skip the other."""
  ledger_error = ""
  try:
    sys.stdout.write(out_str)
  finally:
    try:
      update_ledger(inputs)
    except OSError as exc:
      ledger_error = f"{type(exc).__name__}: {exc}"
  if ledger_error:
    sys.stderr.write(
        f"coverage ledger {inputs.ledger_path!r} was not updated:"
        f" {ledger_error}\n"
    )
    return 1
  return 0


def run_list_get_events(
    args: argparse.Namespace, action: str, raw_obj: dict[str, Any]
) -> int:
  """Prints compacted objects for `list`, `get` and `events` and records them in the ledger."""
  if isinstance(raw_obj, dict) and raw_obj.get("kind") == "List":
    raw_items = k8s_objects.dict_items(raw_obj.get("items"))
    for warning in k8s_objects.as_list(raw_obj.get("_warnings")):
      sys.stderr.write(f"warning: {warning}\n")
    if action == "list":
      out_str = _dump(_list_summary_rows(raw_items))
    else:
      out_str = _dump([_compact_keep_dups(x) for x in raw_items])
  else:
    out_str = _dump(_compact_keep_dups(raw_obj))
  return _print_and_record(
      out_str,
      LedgerInputs(
          args.ledger_path,
          action if action != "snapshot" else "get",
          raw_obj,
          out_str,
      ),
  )


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------


class _DigestBuilder:
  """Assembles the snapshot payload (full report and stdout digest share the layout)."""

  def __init__(
      self, schema_ref: dict[str, Any], derived_notes: list[str], warnings: Any
  ) -> None:
    self.schema_ref = schema_ref
    self.derived_notes = derived_notes
    self.warnings = warnings

  def payload(
      self, groups: dict[str, Any], objects: list[dict[str, Any]]
  ) -> dict[str, Any]:
    """Returns the ordered snapshot dictionary for the full report or digest."""
    # Most decision-relevant sections first: agent harnesses often show only
    # the head (and tail) of a command's stdout.
    out: dict[str, Any] = {
        "detected_kueue_version": self.schema_ref.get("_detected_kueue_version")
    }
    if self.schema_ref.get("_schema_notice"):
      out["schema_notice"] = self.schema_ref["_schema_notice"]
    out["derived_graph_diagnostics"] = self.derived_notes
    if groups:
      out["bulk_object_groups"] = groups
    out |= {
        "kueue_graph_objects": objects,
        "active_api_schema_reference": self.schema_ref,
    }
    if self.warnings:
      out["warnings"] = self.warnings
    return out


def _namespace_of(obj: Any) -> str:
  ns = k8s_objects.metadata(obj).get("namespace")
  return ns if isinstance(ns, str) else ""


def _scoped_snapshot_items(
    args: argparse.Namespace, raw_items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
  """Keeps cluster-scoped objects, relevant cluster-level Events, and objects in `--namespace` / `--kueue-namespace`."""
  if not args.namespace:
    return raw_items
  scoped = [
      x
      for x in raw_items
      if not _namespace_of(x)
      or _namespace_of(x) in (args.namespace, args.kueue_namespace)
      or (
          str(x.get("kind") or "") == "Event"
          and snapshot_loaders._event_is_relevant(x)  # pylint: disable=protected-access
      )
  ]
  has_ns_match = any(_namespace_of(x) == args.namespace for x in raw_items)
  return scoped if has_ns_match else raw_items


def _fact_input_items(
    args: argparse.Namespace,
    unfiltered_items: list[dict[str, Any]],
    shown_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
  """Items the derived facts are computed from: the displayed ones plus healthy workload Pods.

  The display filter drops Running/Succeeded Pods without failures to keep
  the digest small. Facts that relate a Workload to its Pods need them, so
  they are added back for fact computation only. Pods of platform add-on
  namespaces stay out, as does everything else the filter removed (add-on
  Events, other ConfigMaps), and a `--namespace` scope that applied to the
  display applies here too.

  Args:
    args: Parsed CLI arguments (`namespace`, `kueue_namespace`).
    unfiltered_items: Every loaded object.
    shown_items: The filtered, scoped objects of the digest.

  Returns:
    `shown_items` followed by the hidden healthy Pods in scope.
  """
  shown = {id(x) for x in shown_items}
  scoped = bool(args.namespace) and any(
      _namespace_of(x) == args.namespace for x in shown_items
  )
  hidden_pods = [
      x
      for x in unfiltered_items
      if k8s_objects.kind(x) == "Pod"
      and id(x) not in shown
      and not report_output.is_managed_addon_namespace(_namespace_of(x))
      and (
          not scoped
          or _namespace_of(x) in (args.namespace, args.kueue_namespace)
      )
  ]
  return shown_items + hidden_pods


_MAX_SKIPPED_SHOWN = 8


def _coverage_gap_notes(raw_obj: dict[str, Any]) -> list[str]:
  """The pinned line naming sources the loader could not read (empty when it read everything).

  It carries the `BUNDLE_COVERAGE:` prefix, which the digest trimmer never
  drops: without it a kind that could not be listed reads as a kind with no
  objects.

  Args:
    raw_obj: The loaded `kind: List` with optional `_skipped_sources`.

  Returns:
    Zero or one derived-fact line.
  """
  skipped = [
      str(s)[:120] for s in k8s_objects.as_list(raw_obj.get("_skipped_sources"))
  ]
  if not skipped:
    return []
  shown = "; ".join(skipped[:_MAX_SKIPPED_SHOWN])
  if len(skipped) > _MAX_SKIPPED_SHOWN:
    shown += f"; ... {len(skipped) - _MAX_SKIPPED_SHOWN} more"
  return [
      f"BUNDLE_COVERAGE: partial snapshot, {len(skipped)} source(s) not"
      f" loaded: {shown}. Objects from these sources are missing from every"
      " fact and object list in this output, and their absence here says"
      " nothing about the cluster; the load errors are listed under warnings."
  ]


def _detect_schema(
    args: argparse.Namespace,
    present_kinds: set[str],
    unfiltered_items: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
  """(detected Kueue version info, active schema reference) for the snapshot."""
  detected_vinfo = kueue_schema.detect_target_kueue_version(
      mode=args.mode,
      raw_items=unfiltered_items,
      data_path=args.data_path,
      explicit_release_version=args.kueue_version,
      explicit_api_version=args.api_version,
  )
  schema_ref = kueue_schema.get_active_schema_reference(
      present_kinds,
      version_info=detected_vinfo,
      raw_items=unfiltered_items,
      load_live_crds=_live_crds_arg(args),
  )
  if isinstance(schema_ref.get("_detected_kueue_version"), dict):
    detected_vinfo.update(schema_ref["_detected_kueue_version"])
  return detected_vinfo, schema_ref


def _tagged_derived_notes(
    ledger_path: str, raw_items: list[dict[str, Any]]
) -> list[str]:
  """Derived facts with `[S<n>]` ids assigned to keyed facts in `_FACT_PRIORITY` order."""
  try:
    keyed_facts = compute_derived_facts(raw_items)
  except Exception as exc:  # pylint: disable=broad-exception-caught
    # A malformed Kubernetes object must not abort snapshot generation.
    keyed_facts = [(None, _unavailable_note("", exc))]
  tracked = sorted(
      ((k, t) for k, t in keyed_facts if k),
      key=lambda kt: _FACT_PRIORITY.get(kt[0].split(":", 1)[0], 9),
  )
  fact_ids = report_output.register_facts(ledger_path, "S", tracked)
  return [report_output.tag(fact_ids, k, t) for k, t in keyed_facts]


class _DigestTrimmer:
  """Trim steps for the stdout digest, applied by `report_output.apply_output_cap`.

  Each step removes one notch from the lowest-value part of the digest and
  returns True when it removed something; `dropped` records what went, in the
  order the steps ran, for the `truncated` note.
  """

  def __init__(self, digest: dict[str, Any]):
    self.digest = digest
    self.dropped: dict[str, Any] = {}
    self._groups: dict[str, list[Any]] = {}

  def steps(self) -> list[report_output.TrimStep]:
    # Least valuable first: per-kind schema field lists, grouped bulk objects
    # (rarest signatures at the tail), priority-sorted graph objects, and as a
    # last resort untagged derived facts (tagged [S<n>] facts always stay).
    return [
        self.compact_schema_fields,
        *(self._bulk_group_step(key) for key in ("events", "pods", "nodes")),
        self.drop_graph_objects,
        self.drop_untagged_notes,
    ]

  def compact_schema_fields(self, digest: dict[str, Any]) -> bool:
    if "active_api_schema_reference.valid_fields" in self.dropped:
      return False
    slim, n_slim = report_output.compact_schema_reference(
        digest["active_api_schema_reference"]
    )
    if not n_slim:
      return False
    digest["active_api_schema_reference"] = slim
    self.dropped["active_api_schema_reference.valid_fields"] = n_slim
    return True

  def _bulk_group_step(self, group_key: str) -> report_output.TrimStep:
    """Returns a trim step that drops a quarter of one bulk object group list."""

    def step(digest: dict[str, Any]) -> bool:
      groups = self._groups.get(group_key)
      if groups is None:
        groups = list(
            (digest.get("bulk_object_groups") or {}).get(group_key) or []
        )
      if not groups:
        return False
      notch = max(1, len(groups) // 4)
      groups = groups[:-notch]
      self._groups[group_key] = groups
      dropped_key = f"bulk_object_groups.{group_key}"
      self.dropped[dropped_key] = self.dropped.get(dropped_key, 0) + notch
      digest["bulk_object_groups"][group_key] = groups + [
          {"omitted_groups": self.dropped[dropped_key]}
      ]
      return True

    return step

  def drop_graph_objects(self, digest: dict[str, Any]) -> bool:
    objects = digest["kueue_graph_objects"]
    if len(objects) <= 1:
      return False
    notch = max(1, len(objects) // 10)
    digest["kueue_graph_objects"] = objects[:-notch]
    self.dropped["kueue_graph_objects"] = (
        self.dropped.get("kueue_graph_objects", 0) + notch
    )
    return True

  def drop_untagged_notes(self, digest: dict[str, Any]) -> bool:
    """Drops a batch of untagged derived facts while keeping all [S<n>] facts."""
    notes = digest["derived_graph_diagnostics"]
    already = self.dropped.get("derived_graph_diagnostics", 0)
    if (
        notes
        and isinstance(notes[-1], str)
        and notes[-1].startswith("... ")
        and already
    ):
      notes = notes[:-1]
    notes, removed = report_output.shrink_untagged_notes(
        notes, step=max(1, len(notes) // 10)
    )
    if not removed:
      return False
    self.dropped["derived_graph_diagnostics"] = already + removed
    digest["derived_graph_diagnostics"] = notes + [
        report_output.untagged_trailer(
            self.dropped["derived_graph_diagnostics"], "derived facts"
        )
    ]
    return True

  def truncation_note(
      self, report_file: str, max_output_bytes: int
  ) -> dict[str, Any] | None:
    """Builds the truncation metadata block if any digest items were dropped."""
    if not self.dropped:
      return None
    dropped_notes = self.dropped.get("derived_graph_diagnostics", 0)
    if not dropped_notes:
      facts_state = "derived_graph_diagnostics is complete"
    else:
      facts_state = (
          f"derived_graph_diagnostics lost {dropped_notes} untagged facts"
          " (every [S<n>] fact is kept)"
      )
    return report_output.truncation_note(
        report_file,
        max_output_bytes,
        self.dropped,
        f"This is a digest; {facts_state}. Dropped items are the"
        " lowest-priority objects and the rarest Node/Pod/Event groups. Fetch"
        " a specific object with --action get --kind <kind> --name <name>"
        " --namespace <ns> (--namespace is not needed for cluster-scoped"
        " kinds), re-run with --namespace <ns>, or open full_report_file by"
        " line range for one object — do not read the whole file. Do not"
        " parse the ledger.",
    )


def _yaml_size(payload: Any) -> int:
  """Byte size of `payload` as the digest prints it (anchors for shared objects)."""
  return len(_dump(payload, aliases=True).encode("utf-8"))


def _aliasable(value: Any) -> bool:
  """True for values the YAML dumper anchors when it meets the same object twice."""
  return not (
      value is None
      or isinstance(value, (str, bytes, bool, int, float))
      or (isinstance(value, tuple) and not value)
  )


# One measured piece of the digest: (key path, is a list entry, value).
_Unit = tuple[tuple[str, ...], bool, Any]
# Above this many shared objects anchor names may grow past `id999`, and a
# piece dumped on its own would no longer have the width it has in the digest.
_MAX_FAST_ANCHORS = 900


class _DigestSizer:
  """Exact byte size of the digest YAML without re-serialising it for every trim step.

  The digest is cut into units: each top-level section, and each entry of a
  list a trim step shortens. In block style the dump of a mapping or sequence
  is the concatenation of the dumps of its entries, so a unit that shares no
  object with another unit has the same text wherever it is dumped; it is
  dumped once, under the keys it has in the digest, and its size is cached.
  Units that do share an object (the dumper writes `&id001` once and `*id001`
  afterwards) are dumped together, in digest order, and that dump is cached
  per set of units. The sizes add up to the size of the real dump as long as
  trim steps replace lists by shorter ones and never edit a unit in place.
  """

  GROUPS_KEY = "bulk_object_groups"

  def __init__(self) -> None:
    self._sizes: dict[tuple[Any, ...], int] = {}
    self._parts: dict[tuple[Any, ...], tuple[int, list[_Unit]]] = {}
    # Everything whose id() is part of a cache key stays referenced, so an id
    # is never reused by a newer object.
    self._pinned: list[Any] = []
    self._owners: dict[int, list[tuple[Any, ...]]] = {}
    self._shared: set[tuple[Any, ...]] = set()
    self._registered: set[tuple[Any, ...]] = set()
    self._anchors = 0

  def __call__(self, digest: dict[str, Any]) -> int:
    sections = list(self._sections(digest))
    for section in sections:
      self._register_section(*section)
    if self._anchors > _MAX_FAST_ANCHORS or not sections:
      return _yaml_size(digest)
    total = self._frame_size(
        tuple(p for p, v in sections if isinstance(v, list) and v)
    )
    together: list[_Unit] = []
    for section in sections:
      size, shared = self._section_part(*section)
      total += size
      together.extend(shared)
    if together:
      total += self._memo(
          ("together", *map(self._key, together)),
          lambda: self._joint_size(together),
      )
    return total

  def _sections(self, digest: dict[str, Any]) -> Any:
    """Yields `(key path, value)` for every section; bulk groups count one per group."""
    for key, value in digest.items():
      if key != self.GROUPS_KEY or not isinstance(value, dict):
        yield (key,), value
      elif value and all(isinstance(g, list) and g for g in value.values()):
        for group_key, group in value.items():
          yield (key, group_key), group
      else:
        # Not the shape the trim steps maintain: measured as one unit, and
        # as a fresh copy, since the steps edit this mapping in place.
        yield (key,), dict(value)

  def _section_units(self, path: tuple[str, ...], value: Any) -> list[_Unit]:
    if isinstance(value, list) and value:
      return [(path, True, entry) for entry in value]
    return [(path, False, value)]

  def _key(self, unit: _Unit) -> tuple[Any, ...]:
    path, in_list, value = unit
    return path, in_list, value if isinstance(value, str) else id(value)

  def _memo(self, key: tuple[Any, ...], compute: Any) -> int:
    if key not in self._sizes:
      self._sizes[key] = compute()
    return self._sizes[key]

  def _register_section(self, path: tuple[str, ...], value: Any) -> None:
    """Registers every aliasable unit inside one digest section."""
    seen_key = ("section", path, id(value))
    if seen_key in self._registered:
      return
    self._registered.add(seen_key)
    self._pinned.append(value)
    in_section: set[tuple[Any, ...]] = set()
    for unit in self._section_units(path, value):
      key = self._key(unit)
      if key in in_section and _aliasable(unit[2]):
        # The same object twice in one list: the second entry is an alias.
        self._anchors += key not in self._shared
        self._shared.add(key)
      in_section.add(key)
      self._register(unit)

  def _register(self, unit: _Unit) -> None:
    """Records which aliasable objects the unit holds and which units share one."""
    key = self._key(unit)
    if key in self._registered:
      return
    self._registered.add(key)
    seen: set[int] = set()
    stack = [unit[2]]
    while stack:
      node = stack.pop()
      if not _aliasable(node):
        continue
      if id(node) in seen:
        self._anchors += 1
        continue
      seen.add(id(node))
      owners = self._owners.setdefault(id(node), [])
      owners.append(key)
      if len(owners) > 1:
        self._anchors += len(owners) == 2
        self._shared.update(owners)
      if isinstance(node, dict):
        stack.extend(k for k in node if not isinstance(k, str))
        stack.extend(node.values())
      elif isinstance(node, (list, tuple, set, frozenset)):
        stack.extend(node)

  def _section_part(
      self, path: tuple[str, ...], value: Any
  ) -> tuple[int, list[_Unit]]:
    """(bytes of the section's unshared units, its units that share objects)."""
    part_key = (path, id(value), len(self._shared))
    if part_key not in self._parts:
      units = self._section_units(path, value)
      shared = [u for u in units if self._key(u) in self._shared]
      size = sum(
          self._memo(("unit", *self._key(u)), lambda u=u: self._joint_size([u]))
          for u in units
          if self._key(u) not in self._shared
      )
      self._parts[part_key] = (size, shared)
    return self._parts[part_key]

  def _skeleton(
      self, units: list[_Unit], sentinel_only: bool
  ) -> dict[str, Any]:
    """A digest-shaped mapping holding `units`; each of their lists ends with a `0` sentinel."""
    out: dict[str, Any] = {}
    lists: list[list[Any]] = []
    for path, in_list, value in units:
      parent = out
      for key in path[:-1]:
        parent = parent.setdefault(key, {})
      if not in_list:
        if not sentinel_only:
          parent[path[-1]] = value
      elif path[-1] not in parent:
        parent[path[-1]] = [] if sentinel_only else [value]
        lists.append(parent[path[-1]])
      elif not sentinel_only:
        parent[path[-1]].append(value)
    for entries in lists:
      entries.append(0)
    return out

  def _joint_size(self, units: list[_Unit]) -> int:
    """Bytes `units` take in the digest: their joint dump minus the key lines and sentinels around them."""
    base = self._skeleton(units, sentinel_only=True)
    return _yaml_size(self._skeleton(units, sentinel_only=False)) - (
        _yaml_size(base) if base else 0
    )

  def _frame_size(self, list_paths: tuple[tuple[str, ...], ...]) -> int:
    """Bytes of the key lines above the digest's non-empty lists."""
    if not list_paths:
      return 0

    def measure() -> int:
      units: list[_Unit] = [(p, True, 0) for p in list_paths]
      one = self._skeleton(units, sentinel_only=True)
      two = self._skeleton(units + units, sentinel_only=False)
      # `one` holds one sentinel per list, `two` three.
      return (3 * _yaml_size(one) - _yaml_size(two)) // 2

    return self._memo(("frame", list_paths), measure)


def _trim_to_budget(
    digest: dict[str, Any], max_output_bytes: int, report_file: str, size: Any
) -> str:
  """Applies digest trim steps under `size` and returns the dumped digest YAML."""
  trimmer = _DigestTrimmer(digest)
  report_output.apply_output_cap(
      digest,
      max_output_bytes,
      trimmer.steps(),
      note=lambda: trimmer.truncation_note(report_file, max_output_bytes),
      size=size,
      skip_if_fits=False,
  )
  return _dump(digest, aliases=True)


def _fit_digest_to_budget(
    digest: dict[str, Any], max_output_bytes: int, report_file: str
) -> str:
  """Shrinks the digest until it fits `max_output_bytes` and returns the YAML to print."""
  # Trim steps replace top-level values and bulk group lists, so this shallow
  # copy is enough to start over.
  pristine = {
      k: dict(v) if k == _DigestSizer.GROUPS_KEY and isinstance(v, dict) else v
      for k, v in digest.items()
  }
  sizer = _DigestSizer()
  text = _trim_to_budget(digest, max_output_bytes, report_file, sizer)
  if sizer(digest) == len(text.encode("utf-8")):
    return text
  # The piecewise sizes did not add up to the real dump (a shape the sizer
  # does not model). Trim again, measuring the whole digest at every step.
  digest.clear()
  digest.update(pristine)
  return _trim_to_budget(digest, max_output_bytes, report_file, _yaml_size)


def run_snapshot(args: argparse.Namespace, raw_obj: dict[str, Any]) -> int:
  """Builds the full report and the budgeted stdout digest from a `kind: List` of raw objects."""
  unfiltered_items = k8s_objects.dict_items(raw_obj.get("items"))
  raw_items = filter_and_sort_snapshot_items(unfiltered_items)
  present_kinds = {str(x.get("kind", "")) for x in raw_items if x.get("kind")}
  raw_items = _scoped_snapshot_items(args, raw_items)
  detected_vinfo, schema_ref = _detect_schema(
      args, present_kinds, unfiltered_items
  )
  # Facts see the healthy Pods the display filter hides; the object lists
  # below do not.
  derived_notes = _coverage_gap_notes(raw_obj) + _tagged_derived_notes(
      args.ledger_path, _fact_input_items(args, unfiltered_items, raw_items)
  )
  compacted_items = [sanitize_and_compact_object(x) for x in raw_items]
  ungrouped_items, bulk_groups = group_bulk_objects(compacted_items)
  builder = _DigestBuilder(schema_ref, derived_notes, raw_obj.get("_warnings"))
  # The full report (and therefore the quote ledger) keeps every object and
  # every member name; only the stdout digest is grouped and sampled.
  full_out_str = _dump(builder.payload(bulk_groups, compacted_items))
  report_file = report_output.write_full_report(
      args.ledger_path, "snapshot", full_out_str, "yaml"
  )
  digest = {
      "full_report_file": report_file,
      **builder.payload(sample_bulk_groups(bulk_groups), ungrouped_items),
  }
  out_str = _fit_digest_to_budget(digest, args.max_output_bytes, report_file)
  return _print_and_record(
      out_str,
      LedgerInputs(
          args.ledger_path,
          "get",
          raw_obj,
          full_out_str,
          detected_version=detected_vinfo,
      ),
  )


def main() -> int:
  args = build_parser().parse_args()
  report_output.apply_ignore_namespaces(args)
  report_output.apply_no_remote_schema(args)
  report_output.apply_kueue_namespace(args)
  if args.action == "explain":
    return run_explain(args)
  if args.mode == "logs_archive":
    return _run_logs_archive(args)
  action = _resolve_action(args)
  try:
    raw_obj = load_items(args.mode, args, action)
  except LoadError as exc:
    return _print_error(exc.message, exc.next_step)
  if (
      isinstance(raw_obj, dict)
      and raw_obj.get("kind") == "List"
      and _is_snapshot_request(args, action)
  ):
    return run_snapshot(args, raw_obj)
  return run_list_get_events(args, action, raw_obj)


if __name__ == "__main__":
  sys.exit(main())
