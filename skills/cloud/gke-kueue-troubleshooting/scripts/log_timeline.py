"""Milestone timeline compression for the `gke-kueue-troubleshooting` skill.

Compresses raw log lines into runs of repeated milestone messages (admission,
eviction, preemption, requeue, configuration loading, ...) with repetition
counts, keeps a capped list of verbatim high-priority excerpts and attaches
the derived diagnostics produced by `log_facts`.
"""

from __future__ import annotations

import json
import re
from typing import Any

import log_facts

MILESTONE_RE = re.compile(
    r"admit|admission|evict|preempt|quota|requeue|re-queued|finish"
    r"|succeed|fail|delete|pending|inadmissible|stopped|strict decoding error"
    r"|unknown field|backoffBaseSeconds|ProvisioningRequest"
    r"|PodsReadyTimeout|EvictedDueToAdmissionCheck|AdmissionCheckUpdated|UpdatedAdmissionCheck|bad"
    r" parameters reference"
    r"|Updating the PodsReady condition|exceeding the PodsReady timeout"
    r"|localQueue doesn't exist|clusterQueue doesn't exist|no topology domains"
    r"|unavailable in ClusterQueue|taint|Insufficient|Configuration loaded"
    r"|BookingExpired"
    r"|context deadline exceeded|client-side throttling|rate limiter|leader"
    r" election|too many requests|unable to handle the request"
    r"|Initializing|gitVersion|Audit",
    re.IGNORECASE,
)

HIGH_PRIORITY_RE = re.compile(
    r"strict decoding error|unknown field|backoffBaseSeconds"
    r"|ProvisioningRequest.{0,400}(?:not"
    r" found|retry|fail|exhausted|expired|reached|not ready)"
    r"|EvictedDueToAdmissionCheck|AdmissionCheckUpdated|UpdatedAdmissionCheck"
    r"|inadmissible|StrictFIFO"
    r"|insufficient.{0,400}quota|couldn't assign flavors"
    r"|localQueue doesn't exist"
    r"|PodsReadyTimeout|EvictedDueToPodsReadyTimeout"
    r"|FailedScheduling|Insufficient cpu|no topology"
    r" domains|TopologyAwareScheduling"
    r"|BookingExpired"
    r"|context deadline exceeded|client-side throttling|rate limiter|leader"
    r" election|too many requests|unable to handle the request"
    r"|unavailable in ClusterQueue|taint|\[Audit (?:create|delete|patch|update)"
    r" (?:jobs|jobsets|namespaces|resourceflavors|clusterqueues|localqueues|configmaps)\]",
    re.IGNORECASE,
)

_TIMESTAMP_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?\b"
)

_MAX_HIGH_PRIORITY_EXCERPTS = 30
_PATTERN_WIDTH = 180
_LINE_WIDTH = 320
_HEAD_RUNS = 25


def _obj_name(value: Any) -> str:
  """Name from a logged object ref: {name, namespace} (klog ObjectRef) or a plain "ns/name" string."""
  if isinstance(value, dict):
    return str(value.get("name") or "")
  if isinstance(value, str):
    return value.rsplit("/", 1)[-1]
  return ""


def _first_truthy(
    parsed: dict[str, Any], keys: tuple[str, ...], default: Any = ""
) -> Any:
  """The first truthy `parsed[key]` in `keys`, else `default`."""
  for key in keys:
    if parsed.get(key):
      return parsed[key]
  return default


def _milestone_message(msg: str) -> str:
  """Formats a JSON log record into a pipe-delimited milestone summary."""
  if not msg.startswith("{"):
    return msg
  try:
    parsed = json.loads(msg)
  except (json.JSONDecodeError, RecursionError):
    return msg
  ts = _first_truthy(parsed, ("timestamp", "time", "ts"))
  body = _first_truthy(parsed, ("message", "msg", "textPayload"), default=msg)
  note = parsed.get("note") or ""
  err = parsed.get("error") or ""
  reason = parsed.get("reason") or ""
  wl = (
      parsed.get("workload")
      or _obj_name(parsed.get("object"))
      or _obj_name(parsed.get("involvedObject"))
      or ""
  )
  if isinstance(wl, dict):
    wl = wl.get("name", "")
  wl_str = f" | workload={wl}" if wl else ""
  reason_str = f" | reason={reason}" if reason else ""
  note_str = f" | note={note}" if (note and str(note) not in str(body)) else ""
  err_str = f" | error={err}" if err else ""
  return f"{ts} | {body}{reason_str}{wl_str}{note_str}{err_str}"


def _collect_milestones(
    lines: list[str],
) -> tuple[list[dict[str, Any]], dict[str, int], list[str]]:
  """Returns `(runs, pattern totals, high-priority excerpts)` over the milestone lines."""
  milestones: list[dict[str, Any]] = []
  totals: dict[str, int] = {}
  high_priority_excerpts: list[str] = []
  seen_hp: set[str] = set()
  for raw in lines:
    if not MILESTONE_RE.search(raw):
      continue
    if HIGH_PRIORITY_RE.search(raw):
      short_raw = raw.strip()[:400]
      if (
          short_raw not in seen_hp
          and len(high_priority_excerpts) < _MAX_HIGH_PRIORITY_EXCERPTS
      ):
        seen_hp.add(short_raw)
        high_priority_excerpts.append(short_raw)
    msg = _milestone_message(raw.strip())
    pattern = _TIMESTAMP_RE.sub("<TS>", msg)[:_PATTERN_WIDTH]
    totals[pattern] = totals.get(pattern, 0) + 1
    if milestones and milestones[-1]["pattern"] == pattern:
      milestones[-1]["count"] += 1
      milestones[-1]["last_line"] = msg[:_LINE_WIDTH]
    else:
      milestones.append(
          {"pattern": pattern, "count": 1, "first_line": msg[:_LINE_WIDTH]}
      )
  return milestones, totals, high_priority_excerpts


def _truncate_runs(
    milestones: list[dict[str, Any]], max_runs: int
) -> list[dict[str, Any]]:
  """Keeps the first 25 and the last `max_runs - 25` runs with a `truncated_runs` marker between."""
  if len(milestones) <= max_runs:
    return milestones
  head = milestones[:_HEAD_RUNS]
  tail = milestones[-(max_runs - _HEAD_RUNS) :]
  return head + [{"truncated_runs": len(milestones) - max_runs}] + tail


def compress_timeline(
    lines: list[str],
    max_runs: int = 120,
    version_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
  """Compresses raw log lines into milestone runs with repetition counts and key excerpts."""
  milestones, totals, high_priority_excerpts = _collect_milestones(lines)
  diag = log_facts.extract_derived_log_diagnostics(
      lines, version_info=version_info
  )
  schema_ref = diag.get("active_api_schema_reference") or {}
  result: dict[str, Any] = {
      "detected_kueue_version": schema_ref.get("_detected_kueue_version")
  }
  if schema_ref.get("_schema_notice"):
    result["schema_notice"] = schema_ref["_schema_notice"]
  result |= {
      "total_scanned_lines": len(lines),
      "distinct_milestone_patterns": len(totals),
      "derived_log_diagnostics": diag,
      "high_priority_verbatim_log_excerpts": high_priority_excerpts,
      "top_milestone_counts": dict(
          sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:20]
      ),
      "compressed_timeline": _truncate_runs(milestones, max_runs),
  }
  return result
