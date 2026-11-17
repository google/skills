#!/usr/bin/env python3
"""Kueue controller log timeline compaction for the `gke-kueue-troubleshooting` skill.

Reads Kueue controller logs (and, when present, Kubernetes audit events and
Events),
compresses them into a milestone timeline and emits mechanically derived facts:

  * `active_api_schema_reference` — the CRD / KueueConfiguration schema for the
  Kueue
    release detected from the log stream (startup banner, `Configuration
    loaded`,
    audit `apiVersion`s), so clusterless diagnosis still uses version-exact
    fields;
  * `derived_log_diagnostics.derived_log_facts` — neutral facts (audit-logged
    deletions, strict decoding errors, TAS domain errors, resources missing from
    a
    ClusterQueue) with at most one sentence of version-independent Kueue
    semantics
    each. The script never ranks causes or prescribes report content.

Input sources (`--mode`):
  live          `kubectl logs` of the Kueue controller deployment.
  offline_data  a support-bundle directory (manifests + `logs/`).
  logs_archive  a file or directory of exported logs (or `-` for stdin) in any
                supported shape (see `log_envelopes.py`): raw controller output,
                `audit.k8s.io/v1` events, Kubernetes Events, or collector /
                cloud-logging envelopes.

No cloud SDKs or shell command wrappers are used; the only external tool is
`kubectl`, and only in `live` mode.

Module map: `log_facts.py` holds the record scanners and fact emitters behind
`_extract_derived_log_diagnostics`; `log_timeline.py` holds the milestone
timeline compression; this module keeps the CLI, the input sources, the ledger
append and the stdout digest cap.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import subprocess
import sys
from typing import Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
  sys.path.insert(0, SCRIPT_DIR)

# pylint: disable=g-import-not-at-top,wrong-import-position
import kueue_schema
import log_envelopes
import log_facts
import log_timeline
import report_output

# pylint: enable=g-import-not-at-top,wrong-import-position

# Names kept on this module for tests and sibling scripts; the implementations
# live in log_facts.py / log_timeline.py.
_MILESTONE_RE = log_timeline.MILESTONE_RE
HIGH_PRIORITY_RE = log_timeline.HIGH_PRIORITY_RE
compress_timeline = log_timeline.compress_timeline
KUEUE_LOG_LITERALS = log_facts.KUEUE_LOG_LITERALS
event_emitter = log_facts.event_emitter
is_external_emitter = log_facts.is_external_emitter
frameworks_from_config = log_facts.frameworks_from_config
_extract_derived_log_diagnostics = log_facts.extract_derived_log_diagnostics


# Objects whose log/audit records are housekeeping noise (Kueue's own optional
# components, the autoscaler status ConfigMap). Matched as substrings of the
# record text; nothing here changes the facts. Platform add-ons are not listed
# by name: records about objects in managed add-on namespaces are dropped by
# report_output.is_managed_addon_namespace (extend with --ignore-namespaces).
_NOISE_SUBSTRINGS = (
    "kueueviz",
    "certwatcher",
    "cluster-autoscaler-status",
)

_AUDIT_PATH_NAMESPACE_RE = re.compile(
    r"^\[Audit [^\]]*\]\s*\S*?/namespaces/([a-z0-9.-]+)/"
)


def _record_namespaces(d: dict[str, Any]) -> set[str]:
  """Namespaces the record is *about*: its object refs and, for audit rows, the request path."""
  found: set[str] = set()
  for key in (
      "objectRef",
      "involvedObject",
      "object",
      "workload",
      "localQueue",
      "job",
  ):
    ref = d.get(key)
    if isinstance(ref, dict) and ref.get("namespace"):
      found.add(str(ref["namespace"]))
    elif isinstance(ref, str) and "/" in ref:
      found.add(ref.split("/", 1)[0].strip())
  if d.get("namespace"):
    found.add(str(d["namespace"]))
  m = _AUDIT_PATH_NAMESPACE_RE.match(
      str(d.get("msg") or d.get("message") or "")
  )
  if m:
    found.add(m.group(1))
  return found


def _is_noise(line: str) -> bool:
  """Returns True for optional-component or platform add-on housekeeping lines.

  The namespace test looks only at the record's own object references and audit
  request path, never at free text such as error messages, and never drops the
  namespace Kueue itself runs in (`--kueue-namespace`).

  Args:
    line: Normalised log line text.

  Returns:
    True if the line should be filtered out as housekeeping noise.
  """
  low = line.lower()
  if any(tok in low for tok in _NOISE_SUBSTRINGS):
    return True
  stripped = line.lstrip()
  if not stripped.startswith("{"):
    return False
  try:
    d = json.loads(stripped)
  except (ValueError, TypeError):
    return False
  if not isinstance(d, dict):
    return False
  return any(
      report_output.is_managed_addon_namespace(ns)
      for ns in _record_namespaces(d)
  )


def _filter_lines(lines: list[str], workload_filter: str) -> list[str]:
  needle = workload_filter.lower()
  out: list[str] = []
  for ln in lines:
    if not ln or _is_noise(ln):
      continue
    if not needle or needle in ln.lower() or _MILESTONE_RE.search(ln):
      out.append(ln)
  return out


def extract_lines_from_live(
    workload_filter: str, tail_lines: int, kueue_namespace: str = "kueue-system"
) -> list[str]:
  """Reads controller logs (current and previous container) from the live cluster via kubectl."""
  lines: list[str] = []
  for extra_flag in ([], ["--previous"]):
    cmd = [
        "kubectl",
        "logs",
        "-n",
        kueue_namespace,
        "deployment/kueue-controller-manager",
        f"--tail={tail_lines}",
        *extra_flag,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode == 0 and res.stdout:
      lines.extend(
          log_envelopes.normalize_line(ln) for ln in res.stdout.splitlines()
      )
  return _filter_lines(lines, workload_filter)


def _is_log_file(fname: str) -> bool:
  low = fname.lower()
  return (
      low.endswith((".log", ".txt", ".jsonl", ".ndjson", ".json"))
      or "log" in low
  )


def extract_lines_from_bundle(
    data_path: str, workload_filter: str
) -> list[str]:
  """Reads and normalises log records from a file or directory of exported logs.

  Every file is passed through `log_envelopes.iter_records`, so raw controller
  output, `audit.k8s.io/v1` events, Kubernetes Events and collector /
  cloud-logging envelopes (JSON array, JSONL or plain lines) all yield the same
  record model.

  Args:
    data_path: File or directory path containing exported log files, or `-` to
      read exported log records from standard input.
    workload_filter: Optional substring filter for non-milestone lines.

  Returns:
    Filtered, normalised log record strings.
  """
  lines: list[str] = []
  if data_path == "-":
    raw_in = getattr(sys.stdin, "buffer", None)
    body = (
        raw_in.read().decode("utf-8", errors="replace")
        if raw_in is not None
        else sys.stdin.read()
    )
    lines.extend(log_envelopes.iter_records(body))
    return _filter_lines(lines, workload_filter)
  if not os.path.exists(data_path):
    return lines
  if os.path.isfile(data_path):
    files_to_read = [data_path]
  else:
    files_to_read = []
    for root, dirs, files in os.walk(data_path):
      dirs.sort()
      for fname in sorted(files):
        if _is_log_file(fname):
          files_to_read.append(os.path.join(root, fname))
  for fpath in files_to_read:
    try:
      with open(fpath, "r", encoding="utf-8", errors="replace") as f:
        body = f.read()
    except OSError:
      continue
    lines.extend(log_envelopes.iter_records(body))
  return _filter_lines(lines, workload_filter)


_LOG_FACT_PRIORITY = {"logfact": 0, "logerr": 1, "audit": 2}
_TAGGED_SECTIONS = (
    "derived_log_facts",
    "key_errors_and_events",
    "audit_resource_actions",
)


def _log_fact_rank(key: str) -> int:
  if key == "logfact:signature:controller-start":
    return 2
  return _LOG_FACT_PRIORITY.get(key.split(":", 1)[0], 9)


def tag_log_facts(
    result: dict[str, Any], ledger_path: str | None
) -> dict[str, str]:
  """Registers keyed log facts in the ledger and prefixes them with `[L<n>]` ids.

  Mutates `result["derived_log_diagnostics"]` in place, removes the `_keyed`
  side channel and returns the key -> id mapping.

  Args:
    result: Compressed timeline result dict containing `_keyed` entries.
    ledger_path: Optional path to the coverage ledger JSON file.

  Returns:
    Mapping of tracked fact keys to their assigned `L<n>` identifiers.
  """
  diag = result.get("derived_log_diagnostics") or {}
  keyed = diag.pop("_keyed", None) or {}
  tracked: list[tuple[str, str]] = []
  for section in _TAGGED_SECTIONS:
    tracked.extend((k, t) for k, t in keyed.get(section, []) if k)
  tracked.sort(key=lambda kt: _log_fact_rank(kt[0]))
  mapping = report_output.register_facts(ledger_path, "L", tracked)
  for section in _TAGGED_SECTIONS:
    if section in diag and section in keyed:
      diag[section] = [
          report_output.tag(mapping, k, t) for k, t in keyed[section]
      ]
  return mapping


# ---------------------------------------------------------------------------
# Coverage ledger
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class LedgerEntry:
  """What one trace_logs run contributes to the coverage ledger."""

  out_json: str
  raw_excerpts: list[str]
  raw_lines: list[str] | None = None

  def tool_output(self) -> str:
    """Full output, high-priority excerpts and the raw tail, capped for the ledger."""
    tail_raw = "\n".join((self.raw_lines or [])[-600:])
    combined = (
        self.out_json
        + "\n"
        + "\n".join(self.raw_excerpts)
        + ("\n" + tail_raw if tail_raw else "")
    )
    return combined[:250000]


def _load_ledger_lenient(ledger_path: str) -> dict[str, Any]:
  """The ledger as stored, or a fresh one when the file is missing or unreadable."""
  return report_output.load_ledger(ledger_path, strict=False)


def _merge_discovered_entities(ledger: dict[str, Any], out_json: str) -> None:
  """Marks ClusterQueues / ResourceFlavors named in the logs as referenced and inspected."""
  try:
    parsed_out = json.loads(out_json)
    diag_block = parsed_out.get("derived_log_diagnostics") or {}
    det_ver = (diag_block.get("active_api_schema_reference") or {}).get(
        "_detected_kueue_version"
    )
    if isinstance(det_ver, dict):
      ledger["detected_kueue_version"] = det_ver
    entities = diag_block.get("discovered_entities") or {}
    ref_set = set(ledger.get("referenced", []))
    insp_set = set(ledger.get("inspected", []))
    for cq in entities.get("cluster_queues", []):
      ref_set.add(f"clusterqueue/{cq}")
      insp_set.add(f"clusterqueue/{cq}")
    for rf in entities.get("resource_flavors", []):
      ref_set.add(f"resourceflavor/{rf}")
      insp_set.add(f"resourceflavor/{rf}")
    ledger["referenced"] = sorted(ref_set)
    ledger["inspected"] = sorted(insp_set)
  except Exception:  # pylint: disable=broad-except
    pass


def append_to_ledger(ledger_path: str | None, entry: LedgerEntry) -> None:
  """Appends trace_logs output and raw log excerpts to the coverage ledger."""
  if not ledger_path:
    return
  ledger = _load_ledger_lenient(ledger_path)
  _merge_discovered_entities(ledger, entry.out_json)
  outputs = ledger.get("tool_outputs", [])
  outputs.append(entry.tool_output())
  ledger["tool_outputs"] = outputs[-50:]
  ledger["raw_bytes_ingested"] = ledger.get("raw_bytes_ingested", 0) + len(
      entry.out_json.encode("utf-8")
  )
  os.makedirs(os.path.dirname(os.path.abspath(ledger_path)), exist_ok=True)
  tmp_path = f"{ledger_path}.tmp"
  with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump(ledger, f, indent=2)
  os.replace(tmp_path, ledger_path)


# ---------------------------------------------------------------------------
# Stdout digest cap
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _DigestTrim:
  """Bookkeeping shared by the trim steps of one digest."""

  diag: dict[str, Any]
  dropped: dict[str, int] = dataclasses.field(default_factory=dict)
  lost: dict[str, int] = dataclasses.field(default_factory=dict)


def _shrunk_list(key: str, seq: list[Any]) -> tuple[list[Any], int] | None:
  """One notch off a list section; None when nothing removable is left."""
  step = max(1, len(seq) // 4)
  if key == "compressed_timeline":
    mid = len(seq) // 2
    return seq[: mid - step // 2] + seq[mid + (step - step // 2) :], step
  if key == "audit_resource_actions":
    # Lines carrying a fact id ([L<n>]) must stay visible; drop untagged ones
    # from the tail.
    untagged = [
        i for i, line in enumerate(seq) if not str(line).startswith("[L")
    ]
    if not untagged:
      return None
    drop_idx = set(untagged[-step:])
    return [line for i, line in enumerate(seq) if i not in drop_idx], len(
        drop_idx
    )
  return seq[:-step], step


def _section_step(
    trim: _DigestTrim, key: str, holder: dict[str, Any]
) -> report_output.TrimStep:
  """Halves a dict section or removes a quarter of a list section per call."""

  def step(unused_payload: dict[str, Any]) -> bool:
    seq = holder.get(key)
    if isinstance(seq, dict):
      if len(seq) <= 2:
        return False
      holder[key] = dict(list(seq.items())[: max(2, len(seq) // 2)])
      trim.dropped[key] = trim.dropped.get(key, 0) + len(seq) - len(holder[key])
      return True
    if not isinstance(seq, list) or len(seq) <= 2:
      return False
    shrunk = _shrunk_list(key, seq)
    if shrunk is None:
      return False
    holder[key], removed = shrunk
    trim.dropped[key] = trim.dropped.get(key, 0) + removed
    return True

  return step


def _schema_step(trim: _DigestTrim) -> report_output.TrimStep:
  """Drops the per-kind `valid_fields` lists once."""
  applied = False

  def step(unused_payload: dict[str, Any]) -> bool:
    nonlocal applied
    if applied:
      return False
    applied = True
    slim, n_dropped = report_output.compact_schema_reference(
        trim.diag.get("active_api_schema_reference") or {}
    )
    if not n_dropped:
      return False
    trim.diag["active_api_schema_reference"] = slim
    trim.dropped["active_api_schema_reference.valid_fields"] = n_dropped
    return True

  return step


def _entity_step(
    trim: _DigestTrim, entities: dict[str, Any], key: str
) -> report_output.TrimStep:
  """Halves one discovered_entities list (never below 20) and appends a `+N more` marker."""
  state = {"seq": entities.get(key)}
  dkey = f"discovered_entities.{key}"

  def step(unused_payload: dict[str, Any]) -> bool:
    seq = state["seq"]
    if not isinstance(seq, list) or len(seq) <= 20:
      return False
    keep = max(20, len(seq) // 2)
    hidden = len(seq) - keep
    state["seq"] = seq[:keep]
    trim.dropped[dkey] = trim.dropped.get(dkey, 0) + hidden
    entities[key] = state["seq"] + [f"... (+{trim.dropped[dkey]} more)"]
    return True

  return step


def _untagged_step(
    trim: _DigestTrim, key: str, what: str
) -> report_output.TrimStep:
  """Removes untagged notes from the tail of a fact list; tagged [L<n>] lines always stay."""

  def step(unused_payload: dict[str, Any]) -> bool:
    seq = trim.diag.get(key)
    if not isinstance(seq, list):
      return False
    if trim.lost.get(key) and seq and str(seq[-1]).startswith("... "):
      seq = seq[:-1]
    seq, removed = report_output.shrink_untagged_notes(
        [str(x) for x in seq], step=max(1, len(seq) // 10)
    )
    if not removed:
      return False
    trim.lost[key] = trim.lost.get(key, 0) + removed
    trim.diag[key] = seq + [
        report_output.untagged_trailer(trim.lost[key], what)
    ]
    trim.dropped[key] = trim.lost[key]
    return True

  return step


def _digest_trim_steps(
    result: dict[str, Any], trim: _DigestTrim
) -> list[report_output.TrimStep]:
  """Trim steps in shrink order (see `_apply_output_cap`)."""
  diag = trim.diag
  steps: list[report_output.TrimStep] = [
      _section_step(trim, "compressed_timeline", result),
      _section_step(trim, "top_milestone_counts", result),
      _schema_step(trim),
      _section_step(trim, "high_priority_verbatim_log_excerpts", result),
      _section_step(trim, "audit_resource_actions", diag),
  ]
  entities = diag.get("discovered_entities") or {}
  for key in sorted(
      entities,
      key=lambda k: -len(entities[k]) if isinstance(entities[k], list) else 0,
  ):
    steps.append(_entity_step(trim, entities, key))
  steps.append(
      _untagged_step(trim, "key_errors_and_events", "key errors/events")
  )
  steps.append(_untagged_step(trim, "derived_log_facts", "log facts"))
  return steps


def _digest_truncation_note(
    trim: _DigestTrim, full_report_file: str, max_bytes: int
) -> dict[str, Any]:
  if trim.lost:
    facts_state = "; ".join(
        f"{k} lost {n} untagged entries (every [L<n>] fact is kept)"
        for k, n in trim.lost.items()
    )
  else:
    facts_state = "derived_log_facts and key errors are complete"
  return report_output.truncation_note(
      full_report_file,
      max_bytes,
      trim.dropped,
      f"This is a digest; {facts_state}. Open full_report_file with your file"
      " viewer (by line range) for the dropped timeline/sections, or re-run"
      " with --workload <name> to narrow the logs. Do not parse the ledger.",
  )


def _apply_output_cap(
    result: dict[str, Any], max_bytes: int, full_report_file: str = ""
) -> dict[str, Any]:
  """Returns the stdout digest: `result` shrunk until the JSON fits `max_bytes`.

  `full_report_file` (if given) is placed first so a reader can open the
  complete report. Tagged `[L<n>]` facts, the coverage fact and
  `detected_kueue_version` are never cut.

  Args:
    result: Full timeline result dictionary.
    max_bytes: Maximum serialised JSON byte budget.
    full_report_file: Optional path to the full report file on disk.

  Returns:
    The budgeted digest dictionary.
  """
  if full_report_file:
    result = {"full_report_file": full_report_file, **result}
  trim = _DigestTrim(diag=result.get("derived_log_diagnostics") or {})
  return report_output.apply_output_cap(
      result,
      max_bytes,
      _digest_trim_steps(result, trim),
      note=lambda: _digest_truncation_note(trim, full_report_file, max_bytes),
  )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _emit_error(message: str, next_step: str) -> int:
  return report_output.emit_error(
      message,
      next_step,
      render=lambda p: json.dumps(p, indent=2) + "\n",
      stderr_prefix="error: ",
  )


def _add_source_arguments(parser: argparse.ArgumentParser) -> None:
  """Where the logs come from (`--mode` and its per-mode inputs)."""
  parser.add_argument(
      "--mode",
      choices=["live", "offline_data", "logs_archive"],
      default=report_output._env(  # pylint: disable=protected-access
          "GKE_KUEUE_TROUBLESHOOTING_MODE", "KUEUE_DIAGNOSE_MODE", "live"
      ),
      help=(
          "live: kubectl logs; offline_data: support bundle dir; logs_archive:"
          " exported log file(s)"
      ),
  )
  parser.add_argument(
      "--workload",
      default="",
      help="Optional workload or queue name substring to focus on",
  )
  parser.add_argument(
      "--tail",
      type=int,
      default=20000,
      help="Max lines to read per container in live mode",
  )
  parser.add_argument(
      "--data-path",
      default=report_output._env(  # pylint: disable=protected-access
          "GKE_KUEUE_TROUBLESHOOTING_DATA_PATH", "KUEUE_DIAGNOSE_DATA_PATH"
      ),
      help=(
          "File or directory with manifests/logs (offline_data, logs_archive),"
          " or '-' to read exported logs from stdin in logs_archive mode"
      ),
  )


def _add_output_arguments(parser: argparse.ArgumentParser) -> None:
  """Ledger, schema-version overrides, controller namespace and the stdout digest cap."""
  report_output.add_ledger_path_argument(
      parser,
      "Path to the coverage ledger JSON shared by all scripts in one"
      " investigation",
  )
  report_output.add_kueue_version_arguments(parser)
  report_output.add_kueue_namespace_argument(
      parser,
      "Namespace of the Kueue controller deployment (default kueue-system)",
  )
  report_output.add_max_output_bytes_argument(
      parser,
      24000,
      "Cap on the stdout digest; the complete report is always written to"
      " full_report_file next to the ledger",
  )
  report_output.add_no_remote_schema_argument(parser)
  report_output.add_ignore_namespaces_argument(parser)


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
      description=(
          "Compacts Kueue controller logs (live, bundle or exported) into a"
          " milestone timeline and derived facts."
      )
  )
  _add_source_arguments(parser)
  _add_output_arguments(parser)
  return parser


# `(message, next_step)` as printed by `_emit_error`.
ReadError = tuple[str, str]

_EMPTY_BUNDLE_RESULT = {
    "total_scanned_lines": 0,
    "note": (
        "No controller log files or Kubernetes Event records are present in"
        " this static offline bundle; rely on snapshot.py output and"
        " derived_graph_diagnostics."
    ),
    "derived_log_diagnostics": {
        "derived_log_facts": [],
        "key_errors_and_events": [],
    },
}


def _read_live_lines(
    args: argparse.Namespace,
) -> tuple[list[str], ReadError | None]:
  """Reads live controller logs via kubectl or returns a ReadError."""
  lines = extract_lines_from_live(
      args.workload, args.tail, args.kueue_namespace
  )
  if not lines:
    return [], (
        (
            "no controller log lines read from"
            " deployment/kueue-controller-manager in namespace"
            f" {args.kueue_namespace!r}"
        ),
        (
            "Check `kubectl get deploy -A | grep kueue` and pass"
            " --kueue-namespace; or export logs to a file and use --mode"
            " logs_archive."
        ),
    )
  return lines, None


def _is_static_bundle(mode: str, data_path: str) -> bool:
  """An offline bundle made of manifests only (no logs to read is not an error)."""
  return (
      mode == "offline_data"
      and os.path.isdir(data_path)
      and any(
          fn.endswith((".yaml", ".yml", ".json"))
          for fn in os.listdir(data_path)
      )
  )


def _read_archive_lines(
    args: argparse.Namespace,
) -> tuple[list[str], ReadError | None]:
  """Reads exported or bundled log records from `--data-path` (or `-` stdin)."""
  data_path = args.data_path
  is_stdin = args.mode == "logs_archive" and data_path == "-"
  if not data_path or (not is_stdin and not os.path.exists(data_path)):
    return [], (
        f"data path not found: {data_path!r}",
        (
            "Pass --data-path <file or directory with exported logs> (or"
            " --data-path - in logs_archive mode; see"
            " references/log-sources.md)."
        ),
    )
  lines = extract_lines_from_bundle(data_path, args.workload)
  if not lines and (is_stdin or not _is_static_bundle(args.mode, data_path)):
    return [], (
        f"no log records recognised under {data_path!r}",
        (
            "Supported shapes: Kueue controller JSON lines, audit.k8s.io/v1"
            " events, Kubernetes Events, cloud-logging / collector envelopes"
            " (JSON array or JSONL). Check the export is not empty."
        ),
    )
  return lines, None


def read_lines(args: argparse.Namespace) -> tuple[list[str], ReadError | None]:
  """Reads the log lines for `args.mode`.

  Args:
    args: Parsed CLI arguments specifying mode, data path, and filters.

  Returns:
    `(lines, None)` on success, `([], (message, next_step))` on error, or
    `([], None)` for a static offline bundle that has no logs.
  """
  if args.mode == "live":
    return _read_live_lines(args)
  return _read_archive_lines(args)


def run(args: argparse.Namespace) -> int:
  """Executes `trace_logs` end-to-end for parsed CLI arguments."""
  report_output.apply_ignore_namespaces(args)
  report_output.apply_no_remote_schema(args)
  report_output.apply_kueue_namespace(args)
  lines, error = read_lines(args)
  if error:
    return _emit_error(*error)
  if not lines:
    print(json.dumps(_EMPTY_BUNDLE_RESULT, indent=2))
    return 0
  vinfo = kueue_schema.detect_target_kueue_version(
      mode=args.mode,
      log_lines=lines,
      data_path=args.data_path,
      explicit_release_version=args.kueue_version,
      explicit_api_version=args.api_version,
      kueue_namespace=args.kueue_namespace,
  )
  full_result = compress_timeline(lines, version_info=vinfo)
  tag_log_facts(full_result, args.ledger_path)
  full_json = json.dumps(full_result, indent=2)
  report_file = report_output.write_full_report(
      args.ledger_path, "trace-logs", full_json, "json"
  )
  append_to_ledger(
      args.ledger_path,
      LedgerEntry(
          full_json,
          full_result.get("high_priority_verbatim_log_excerpts", []),
          raw_lines=lines,
      ),
  )
  digest = _apply_output_cap(
      json.loads(full_json), args.max_output_bytes, full_report_file=report_file
  )
  print(json.dumps(digest, indent=2))
  return 0


def main() -> int:
  return run(build_parser().parse_args())


if __name__ == "__main__":
  sys.exit(main())
