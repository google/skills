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
    deletions, configuration unknown-field errors, TAS domain errors, resources
    missing from a ClusterQueue) with at most one sentence of
    version-independent Kueue semantics each. The script never ranks causes or
    prescribes report content.

Input sources (`--mode`):
  live          `kubectl logs` of the Kueue controller deployment.
  offline_data  a support-bundle directory (manifests + `logs/`).
  logs_archive  a file or directory of exported logs in any supported shape
                (see `log_envelopes.py`): raw controller output,
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
from collections.abc import Sequence
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
  except (ValueError, TypeError, RecursionError):
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


_KUBECTL_LOGS_TIMEOUT_SECONDS = 120
_MAX_KUBECTL_ERROR_CHARS = 600


def _kubectl_logs(
    kueue_namespace: str, tail_lines: int, previous: bool
) -> tuple[str, str]:
  """`(stdout, error)` of one `kubectl logs` call on the controller deployment; `error` is '' on success."""
  cmd = [
      "kubectl",
      "logs",
      "-n",
      kueue_namespace,
      "deployment/kueue-controller-manager",
      f"--tail={tail_lines}",
  ]
  if previous:
    cmd.append("--previous")
  try:
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=_KUBECTL_LOGS_TIMEOUT_SECONDS,
    )
  except (OSError, subprocess.SubprocessError) as exc:
    return "", f"{type(exc).__name__}: {exc}"[:_MAX_KUBECTL_ERROR_CHARS]
  if res.returncode != 0:
    detail = (res.stderr or "").strip() or f"exit status {res.returncode}"
    return "", detail[:_MAX_KUBECTL_ERROR_CHARS]
  return res.stdout or "", ""


def _live_log_lines(
    tail_lines: int, kueue_namespace: str
) -> tuple[list[str], str]:
  """Normalised controller log lines, oldest first, and kubectl's error for the running container.

  The terminated container (`--previous`) is read before the running one, so
  that scanners which keep the latest value see the lines in the order they
  were written. A failing `--previous` call is expected when the container
  never restarted and is not reported.

  Args:
    tail_lines: Max lines to read per container.
    kueue_namespace: Namespace of the Kueue controller deployment.

  Returns:
    `(lines, error)`; `error` is '' when the running container was read.
  """
  lines: list[str] = []
  error = ""
  for previous in (True, False):
    out, err = _kubectl_logs(kueue_namespace, tail_lines, previous)
    lines.extend(log_envelopes.normalize_line(ln) for ln in out.splitlines())
    if not previous:
      error = err
  return lines, error


def extract_lines_from_live(
    workload_filter: str, tail_lines: int, kueue_namespace: str = "kueue-system"
) -> list[str]:
  """Reads controller logs (previous container, then the running one) from the live cluster via kubectl."""
  lines, _ = _live_log_lines(tail_lines, kueue_namespace)
  return _filter_lines(lines, workload_filter)


_LOG_EXTENSIONS = (".log", ".txt", ".jsonl", ".ndjson", ".json")
# Manifests, ledger side files and compressed archives are never log text.
_NON_LOG_EXTENSIONS = (
    ".yaml",
    ".yml",
    ".lock",
    ".tmp",
    ".gz",
    ".tgz",
    ".zip",
    ".tar",
    ".bz2",
    ".xz",
    ".zst",
)
_LOG_DIR_NAMES = ("log", "logs")
# `log` / `logs` as a whole token of the file name (`controller-log`,
# `kueue_logs.1`), not as a substring (`catalog`, `topologies`).
_LOG_TOKEN_RE = re.compile(r"(?:^|[^a-z0-9])logs?(?:[^a-z0-9]|$)")


def _is_log_file(fname: str, in_logs_dir: bool = False) -> bool:
  """Checks whether a bundle file should be read as logs.

  Args:
    fname: File name without its directory.
    in_logs_dir: Whether the file sits under a `logs/` directory, where files
      without an extension (one per pod) are log files as well.

  Returns:
    True when `fname` should be parsed as a log file.
  """
  low = fname.lower()
  if low.startswith(".") or low.endswith(_NON_LOG_EXTENSIONS):
    return False
  return (
      in_logs_dir
      or low.endswith(_LOG_EXTENSIONS)
      or bool(_LOG_TOKEN_RE.search(low))
  )


def _bundle_log_candidates(
    data_path: str, exclude_paths: frozenset[str] = frozenset()
) -> list[str]:
  """Log-named entries and symlinked subdirs under `data_path`, in stable order."""
  top = os.path.abspath(data_path)
  found: list[str] = []
  for root, dirs, files in os.walk(top):
    kept_dirs: list[str] = []
    for dname in sorted(dirs):
      if dname == report_output.REPORT_DIR_NAME:
        continue
      full_dir = os.path.join(root, dname)
      if os.path.islink(full_dir):
        found.append(full_dir)
      else:
        kept_dirs.append(dname)
    dirs[:] = kept_dirs
    rel_dirs = os.path.relpath(root, os.path.dirname(top)).lower().split(os.sep)
    in_logs_dir = any(part in _LOG_DIR_NAMES for part in rel_dirs)
    for fname in sorted(files):
      if not _is_log_file(fname, in_logs_dir):
        continue
      full_path = os.path.join(root, fname)
      if os.path.abspath(full_path) in exclude_paths:
        continue
      found.append(full_path)
  return found


def _bundle_log_files(
    data_path: str, exclude_paths: frozenset[str] = frozenset()
) -> list[str]:
  """Regular log files under `data_path` (or explicit file path), in stable order."""
  if os.path.isfile(data_path):
    # Operator named this path explicitly: follow a symlink to a regular file.
    return [os.path.realpath(data_path)]
  if not os.path.isdir(data_path):
    return []
  return [
      p
      for p in _bundle_log_candidates(data_path, exclude_paths)
      if report_output.is_regular_file(p)
  ]


def skipped_log_inputs(
    data_path: str, exclude_paths: frozenset[str] = frozenset()
) -> list[str]:
  """Log-named entries or symlinked subdirs skipped because they are non-regular."""
  if not data_path or data_path == "-" or not os.path.isdir(data_path):
    return []
  top = os.path.abspath(data_path)
  return [
      os.path.relpath(p, top)
      for p in _bundle_log_candidates(data_path, exclude_paths)
      if not report_output.is_regular_file(p)
  ]


def extract_bundle_records(
    data_path: str,
    workload_filter: str,
    exclude_paths: frozenset[str] = frozenset(),
) -> tuple[list[str], list[str]]:
  """Reads and normalises log records and reports unreadable JSON inputs.

  Every file is passed through `log_envelopes.extract_file_records`, so raw
  controller output, `audit.k8s.io/v1` events, Kubernetes Events and collector /
  cloud-logging envelopes (JSON array, JSONL or plain lines) all yield the same
  record model. Files that only yield dropped JSON fragments (such as truncated
  or concatenated pretty-printed JSON arrays) are returned in `unreadable` with
  zero lines counted.

  Args:
    data_path: File or directory path containing exported log files (`-` is
      accepted as a legacy stdin fallback).
    workload_filter: Optional substring filter for non-milestone lines.
    exclude_paths: Absolute file paths (such as the active ledger) to skip.

  Returns:
    `(filtered_lines, unreadable_inputs)`.
  """
  lines: list[str] = []
  unreadable: list[str] = []
  if data_path == "-":
    raw_in = getattr(sys.stdin, "buffer", None)
    body = (
        raw_in.read().decode("utf-8", errors="replace")
        if raw_in is not None
        else sys.stdin.read()
    )
    recs, is_unreadable = log_envelopes.extract_file_records(body)
    lines.extend(recs)
    if is_unreadable:
      unreadable.append("<stdin>")
    return _filter_lines(lines, workload_filter), unreadable
  if not os.path.exists(data_path):
    return lines, unreadable
  is_dir = os.path.isdir(data_path)
  top = os.path.abspath(data_path) if is_dir else ""
  for fpath in _bundle_log_files(data_path, exclude_paths):
    if not report_output.is_regular_file(fpath):
      continue
    try:
      with open(fpath, "r", encoding="utf-8", errors="replace") as f:
        body = f.read()
    except OSError:
      continue
    recs, is_unreadable = log_envelopes.extract_file_records(body)
    if is_unreadable:
      label = (
          os.path.relpath(fpath, top) if is_dir else os.path.basename(data_path)
      )
      unreadable.append(label)
      continue
    lines.extend(recs)
  return _filter_lines(lines, workload_filter), unreadable


def extract_lines_from_bundle(
    data_path: str,
    workload_filter: str,
    exclude_paths: frozenset[str] = frozenset(),
) -> list[str]:
  """Reads and normalises log records from a file or directory of exported logs."""
  lines, _ = extract_bundle_records(data_path, workload_filter, exclude_paths)
  return lines


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
  """Appends trace_logs output and raw log excerpts to the coverage ledger.

  The read-modify-write runs under the ledger lock
  (`report_output.mutate_ledger`), so a snapshot run that writes the same
  ledger at the same time loses no entry.

  Args:
    ledger_path: Path to the coverage ledger JSON file; falsy skips the write.
    entry: Output of this run.
  """
  if not ledger_path:
    return

  def mutate(ledger: dict[str, Any]) -> None:
    _merge_discovered_entities(ledger, entry.out_json)
    outputs = ledger.get("tool_outputs")
    outputs = list(outputs) if isinstance(outputs, list) else []
    outputs.append(entry.tool_output())
    ledger["tool_outputs"] = outputs[-50:]
    ingested = ledger.get("raw_bytes_ingested")
    ledger["raw_bytes_ingested"] = (
        ingested if isinstance(ingested, int) else 0
    ) + len(entry.out_json.encode("utf-8"))

  report_output.mutate_ledger(ledger_path, mutate, strict=False)


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


_MAX_REPORTED_INPUT_WARNINGS = 20


def _cap_input_list(
    items: Sequence[str], limit: int = _MAX_REPORTED_INPUT_WARNINGS
) -> list[str]:
  """Bounds `skipped_inputs` / `unreadable_inputs` with an accurate omitted marker."""
  if len(items) <= limit:
    return list(items)
  return list(items[:limit]) + [f"... {len(items) - limit} more omitted"]


def _input_warning_step(
    trim: _DigestTrim,
    holder: dict[str, Any],
    key: str,
    full_items: Sequence[str],
) -> report_output.TrimStep:
  """Halves a capped warning list (never below 2) while preserving the omitted count."""
  state = {"keep": min(len(full_items), _MAX_REPORTED_INPUT_WARNINGS)}
  total = len(full_items)

  def step(unused_payload: dict[str, Any]) -> bool:
    if key not in holder or state["keep"] <= 2:
      return False
    next_keep = max(2, state["keep"] // 2)
    if next_keep == state["keep"]:
      return False
    state["keep"] = next_keep
    holder[key] = _cap_input_list(full_items, next_keep)
    trim.dropped[key] = total - next_keep
    return True

  return step


def _digest_trim_steps(
    result: dict[str, Any],
    trim: _DigestTrim,
    raw_inputs: dict[str, list[str]],
) -> list[report_output.TrimStep]:
  """Trim steps in shrink order (see `_apply_output_cap`)."""
  diag = trim.diag
  steps: list[report_output.TrimStep] = [
      _section_step(trim, "compressed_timeline", result),
      _section_step(trim, "top_milestone_counts", result),
      _schema_step(trim),
      _section_step(trim, "high_priority_verbatim_log_excerpts", result),
      _section_step(trim, "audit_resource_actions", diag),
      _input_warning_step(
          trim, result, "skipped_inputs", raw_inputs.get("skipped_inputs", [])
      ),
      _input_warning_step(
          trim,
          result,
          "unreadable_inputs",
          raw_inputs.get("unreadable_inputs", []),
      ),
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
  raw_inputs: dict[str, list[str]] = {}
  for key in ("skipped_inputs", "unreadable_inputs"):
    if isinstance(result.get(key), list):
      raw_inputs[key] = list(result[key])
      result[key] = _cap_input_list(raw_inputs[key])
  trim = _DigestTrim(diag=result.get("derived_log_diagnostics") or {})
  return report_output.apply_output_cap(
      result,
      max_bytes,
      _digest_trim_steps(result, trim, raw_inputs),
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
      help="File or directory with manifests/logs (offline_data, logs_archive)",
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
  raw_lines, kubectl_error = _live_log_lines(args.tail, args.kueue_namespace)
  lines = _filter_lines(raw_lines, args.workload)
  if lines:
    return lines, None
  namespace_hint = (
      "Check `kubectl get deploy -A | grep kueue` and pass"
      " --kueue-namespace; or export logs to a file and use --mode"
      " logs_archive."
  )
  if not kubectl_error:
    return [], (
        (
            "no controller log lines read from"
            " deployment/kueue-controller-manager in namespace"
            f" {args.kueue_namespace!r}"
        ),
        namespace_hint,
    )
  access_hint = (
      "Check that kubectl is installed, that `kubectl config current-context`"
      " is reachable and that the account may read pods/log in that"
      " namespace; or export logs to a file and pass --mode logs_archive."
  )
  return [], (
      (
          "kubectl logs deployment/kueue-controller-manager in namespace"
          f" {args.kueue_namespace!r} failed: {kubectl_error}"
      ),
      namespace_hint if "(NotFound)" in kubectl_error else access_hint,
  )


def _is_static_bundle(mode: str, data_path: str) -> bool:
  """An offline bundle made of manifests only (no logs to read is not an error)."""
  if mode != "offline_data" or not os.path.isdir(data_path):
    return False
  for _, _, files in os.walk(data_path):
    if any(fn.lower().endswith((".yaml", ".yml", ".json")) for fn in files):
      return True
  return False


def _exclude_paths_for(args: argparse.Namespace) -> frozenset[str]:
  """Paths owned by the script itself (such as the active ledger) to skip."""
  ledger_path = getattr(args, "ledger_path", "")
  if not ledger_path:
    return frozenset()
  return frozenset({os.path.abspath(ledger_path)})


@dataclasses.dataclass(frozen=True)
class _ArchiveReadResult:
  lines: list[str]
  error: ReadError | None = None
  skipped: tuple[str, ...] = ()
  unreadable: tuple[str, ...] = ()


def _warn_unread_inputs(
    data_path: str, skipped: list[str], unreadable: list[str]
) -> None:
  """Logs actionable warnings to stderr for skipped symlinks or unreadable JSON files."""
  if skipped:
    sys.stderr.write(
        f"warning: {len(skipped)} log input(s) under {data_path!r} are"
        " symlinks or not regular files and were not read:"
        f" {', '.join(skipped[:5])}. Verify their targets before passing a"
        " trusted regular log file via --data-path or re-exporting them as"
        " regular files.\n"
    )
  if unreadable:
    sys.stderr.write(
        f"warning: {len(unreadable)} log input(s) under {data_path!r} could"
        " not be parsed as valid JSON/log records (for example truncated or"
        f" concatenated JSON arrays): {', '.join(unreadable[:5])}. Write each"
        " export to its own file in the directory and pass the directory via"
        " --data-path.\n"
    )


def _read_archive_result(args: argparse.Namespace) -> _ArchiveReadResult:
  """Reads exported or bundled log records plus skipped/unreadable diagnostics."""
  data_path = args.data_path
  is_stdin = args.mode == "logs_archive" and data_path == "-"
  if not data_path or (not is_stdin and not os.path.exists(data_path)):
    return _ArchiveReadResult(
        [],
        (
            f"data path not found: {data_path!r}",
            (
                "Pass --data-path <file or directory with exported logs> (see"
                " references/log-sources.md)."
            ),
        ),
    )
  exclude = _exclude_paths_for(args)
  lines, unreadable = extract_bundle_records(data_path, args.workload, exclude)
  skipped = [] if is_stdin else skipped_log_inputs(data_path, exclude)
  _warn_unread_inputs(data_path, skipped, unreadable)
  if not lines and (is_stdin or not _is_static_bundle(args.mode, data_path)):
    notes: list[str] = []
    if skipped:
      notes.append(f"{len(skipped)} symlinked or non-regular input(s) skipped")
    if unreadable:
      notes.append(
          f"{len(unreadable)} unreadable JSON input(s): "
          + ", ".join(unreadable[:5])
      )
    suffix = f" ({'; '.join(notes)})" if notes else ""
    next_step = (
        "Supported shapes: Kueue controller JSON lines, audit.k8s.io/v1"
        " events, Kubernetes Events, cloud-logging / collector envelopes"
        " (JSON array or JSONL). Check the export is not empty."
    )
    if unreadable:
      next_step = (
          "One or more files contained broken or concatenated JSON exports."
          " Write each export to its own file in a directory (never append"
          " JSON arrays into one file) and pass the directory via --data-path"
          " (see references/log-sources.md)."
      )
    return _ArchiveReadResult(
        [],
        (f"no log records recognised under {data_path!r}{suffix}", next_step),
        tuple(skipped),
        tuple(unreadable),
    )
  return _ArchiveReadResult(lines, None, tuple(skipped), tuple(unreadable))


def _read_archive_lines(
    args: argparse.Namespace,
) -> tuple[list[str], ReadError | None]:
  """Reads exported or bundled log records from `--data-path`."""
  res = _read_archive_result(args)
  return res.lines, res.error


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


def _empty_bundle_payload(
    skipped: Sequence[str], unreadable: Sequence[str], max_bytes: int = 0
) -> dict[str, Any]:
  """Builds the empty-bundle JSON payload, keeping warning lists within `max_bytes`."""
  empty = dict(_EMPTY_BUNDLE_RESULT)
  reasons: list[str] = []
  if skipped:
    reasons.append(
        f"{len(skipped)} log input(s) are symlinks or not regular files"
    )
  if unreadable:
    reasons.append(
        f"{len(unreadable)} log input(s) could not be parsed as valid"
        " JSON/log records"
    )
  if reasons:
    empty["note"] = (
        "; ".join(reasons)
        + " and were not read, so log evidence is not determinable from this"
        " run; verify symlink targets or re-export each filter to its own"
        " regular file before rerunning."
    )
  limit = _MAX_REPORTED_INPUT_WARNINGS
  while True:
    if skipped:
      empty["skipped_inputs"] = _cap_input_list(skipped, limit)
    if unreadable:
      empty["unreadable_inputs"] = _cap_input_list(unreadable, limit)
    if (
        max_bytes <= 0
        or limit <= 2
        or len(json.dumps(empty, indent=2).encode("utf-8")) <= max_bytes
    ):
      return empty
    limit = max(2, limit // 2)


def run(args: argparse.Namespace) -> int:
  """Executes `trace_logs` end-to-end for parsed CLI arguments."""
  report_output.apply_ignore_namespaces(args)
  report_output.apply_no_remote_schema(args)
  report_output.apply_kueue_namespace(args)
  if args.mode == "live":
    lines, error = _read_live_lines(args)
    skipped: Sequence[str] = ()
    unreadable: Sequence[str] = ()
  else:
    archive = _read_archive_result(args)
    lines, error = archive.lines, archive.error
    skipped, unreadable = archive.skipped, archive.unreadable
  if error:
    return _emit_error(*error)
  if not lines:
    empty = _empty_bundle_payload(skipped, unreadable, args.max_output_bytes)
    print(json.dumps(empty, indent=2))
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
  if skipped:
    full_result["skipped_inputs"] = list(skipped)
  if unreadable:
    full_result["unreadable_inputs"] = list(unreadable)
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
