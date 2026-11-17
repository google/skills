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
detected version without touching the cluster.

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


def _dump(payload: Any) -> str:
  return yaml.safe_dump(payload, sort_keys=False, width=_YAML_WIDTH)


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
    emit(ctx)
  return ctx.notes


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


def _list_summary_rows(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """Builds compact kind/namespace/name/conditions rows for the list action."""
  summary_rows = []
  for x in (sanitize_and_compact_object(x) for x in raw_items):
    m = x.get("metadata") or {}
    st = x.get("status") or {}
    conds = [
        f"{c.get('type')}={c.get('status')}({c.get('reason')}:"
        f" {c.get('message', '')[:120]})"
        for c in st.get("conditions") or []
        if isinstance(c, dict)
    ]
    summary_rows.append({
        "kind": x.get("kind"),
        "namespace": m.get("namespace", ""),
        "name": m.get("name", ""),
        "conditions": conds,
    })
  return summary_rows


def _compact_keep_dups(obj: dict[str, Any]) -> dict[str, Any]:
  compacted = sanitize_and_compact_object(obj)
  if isinstance(obj, dict) and obj.get("_yaml_duplicate_keys"):
    return {"_yaml_duplicate_keys": obj["_yaml_duplicate_keys"], **compacted}
  return compacted


def run_list_get_events(
    args: argparse.Namespace, action: str, raw_obj: dict[str, Any]
) -> int:
  """Prints compacted objects for `list`, `get` and `events` and records them in the ledger."""
  if isinstance(raw_obj, dict) and raw_obj.get("kind") == "List":
    raw_items = list(raw_obj.get("items", []))
    if action == "list":
      out_str = _dump(_list_summary_rows(raw_items))
    else:
      out_str = _dump([_compact_keep_dups(x) for x in raw_items])
  else:
    out_str = _dump(_compact_keep_dups(raw_obj))
  update_ledger(
      LedgerInputs(
          args.ledger_path,
          action if action != "snapshot" else "get",
          raw_obj,
          out_str,
      )
  )
  sys.stdout.write(out_str)
  return 0


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


def _scoped_snapshot_items(
    args: argparse.Namespace, raw_items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
  """Keeps cluster-scoped objects, relevant cluster-level Events, and objects in `--namespace` / `--kueue-namespace`."""
  if not args.namespace:
    return raw_items
  scoped = [
      x
      for x in raw_items
      if not ((x.get("metadata") or {}).get("namespace"))
      or (x.get("metadata") or {}).get("namespace")
      in (args.namespace, args.kueue_namespace)
      or (
          str(x.get("kind") or "") == "Event"
          and snapshot_loaders._event_is_relevant(x)  # pylint: disable=protected-access
      )
  ]
  has_ns_match = any(
      (x.get("metadata") or {}).get("namespace") == args.namespace
      for x in raw_items
  )
  return scoped if has_ns_match else raw_items


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
    keyed_facts = [
        (None, f"DERIVED_DIAGNOSTICS_UNAVAILABLE: {type(exc).__name__}: {exc}")
    ]
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
        " a specific object with --action get --kind <kind> --name <name>,"
        " re-run with --namespace <ns>, or open full_report_file by line range"
        " for one object — do not read the whole file. Do not parse the"
        " ledger.",
    )


def _yaml_size(payload: Any) -> int:
  return len(_dump(payload).encode("utf-8"))


def _fit_digest_to_budget(
    digest: dict[str, Any], max_output_bytes: int, report_file: str
) -> str:
  """Shrinks the digest until it fits `max_output_bytes` and returns the YAML to print."""
  trimmer = _DigestTrimmer(digest)
  report_output.apply_output_cap(
      digest,
      max_output_bytes,
      trimmer.steps(),
      note=lambda: trimmer.truncation_note(report_file, max_output_bytes),
      size=_yaml_size,
      skip_if_fits=False,
  )
  return _dump(digest)


def run_snapshot(args: argparse.Namespace, raw_obj: dict[str, Any]) -> int:
  """Builds the full report and the budgeted stdout digest from a `kind: List` of raw objects."""
  unfiltered_items = list(raw_obj.get("items", []))
  raw_items = filter_and_sort_snapshot_items(unfiltered_items)
  present_kinds = {str(x.get("kind", "")) for x in raw_items if x.get("kind")}
  raw_items = _scoped_snapshot_items(args, raw_items)
  detected_vinfo, schema_ref = _detect_schema(
      args, present_kinds, unfiltered_items
  )
  derived_notes = _tagged_derived_notes(args.ledger_path, raw_items)
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
  update_ledger(
      LedgerInputs(
          args.ledger_path,
          "get",
          raw_obj,
          full_out_str,
          detected_version=detected_vinfo,
      )
  )
  sys.stdout.write(out_str)
  return 0


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
