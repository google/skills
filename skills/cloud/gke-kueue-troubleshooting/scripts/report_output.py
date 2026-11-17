"""Shared output helpers for the gke-kueue-troubleshooting scripts.

Agent harnesses show only a limited window of a command's stdout (commonly
8–30 KB, often head + tail with the middle cut out). The scripts therefore:

* always write the complete report to a file next to the ledger
  (``<ledger_dir>/gke-kueue-troubleshooting-reports/<stem>-<utc
  timestamp>.<ext>``), and
* print a digest ordered most-important-first whose size is bounded by
  ``--max-output-bytes``; the first key of the digest is ``full_report_file``
  so the reader can open the dropped parts with a file viewer.

Nothing here depends on third-party packages.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys
import tempfile
from typing import Any, Callable

REPORT_DIR_NAME = "gke-kueue-troubleshooting-reports"
_SCHEMA_META_KEYS = ("_detected_kueue_version",)

# Namespaces whose objects are platform housekeeping and never part of a Kueue
# admission path. Only the upstream Kubernetes namespaces are built in; add
# provider or in-house add-on namespaces with --ignore-namespaces or the
# GKE_KUEUE_TROUBLESHOOTING_IGNORE_NAMESPACES environment variable
# (comma-separated).
_UPSTREAM_ADDON_NAMESPACES = frozenset(
    {"kube-system", "kube-node-lease", "kube-public"}
)


def _env(primary: str, legacy: str = "", default: str = "") -> str:
  """Reads `primary` env var first, falling back to `legacy`, then `default`."""
  val = os.getenv(primary, "").strip()
  if val:
    return val
  if legacy:
    val = os.getenv(legacy, "").strip()
    if val:
      return val
  return default


def ignored_namespaces() -> frozenset[str]:
  """Operator-supplied namespaces to treat as platform add-ons (env var, comma-separated)."""
  raw = _env(
      "GKE_KUEUE_TROUBLESHOOTING_IGNORE_NAMESPACES",
      "KUEUE_DIAGNOSE_IGNORE_NAMESPACES",
  )
  return frozenset(x.strip() for x in raw.split(",") if x.strip())


def is_managed_addon_namespace(namespace: str | None) -> bool:
  """Returns True for upstream `kube-*` or operator-ignored add-on namespaces.

  The namespace Kueue runs in (`--kueue-namespace` /
  GKE_KUEUE_TROUBLESHOOTING_NAMESPACE, default kueue-system) is never treated as
  an add-on namespace.

  Args:
    namespace: Kubernetes namespace name to check.

  Returns:
    True if `namespace` is a managed add-on namespace, False otherwise.
  """
  kueue_ns = _env(
      "GKE_KUEUE_TROUBLESHOOTING_NAMESPACE",
      "KUEUE_DIAGNOSE_NAMESPACE",
      "kueue-system",
  )
  if not namespace or namespace == kueue_ns:
    return False
  return (
      namespace in _UPSTREAM_ADDON_NAMESPACES
      or namespace in ignored_namespaces()
  )


def add_kueue_version_arguments(parser, *, live_crds: bool = False) -> None:
  """--kueue-version / --api-version (+ --load-live-crds) with the shared env defaults."""
  parser.add_argument(
      "--kueue-version",
      default=_env(
          "GKE_KUEUE_TROUBLESHOOTING_KUEUE_VERSION",
          "KUEUE_DIAGNOSE_KUEUE_VERSION",
      ),
      help="Explicit Kueue release version override (e.g. v0.10.0, v0.19.4)",
  )
  parser.add_argument(
      "--api-version",
      default=_env(
          "GKE_KUEUE_TROUBLESHOOTING_API_VERSION", "KUEUE_DIAGNOSE_API_VERSION"
      ),
      help="Explicit Kueue API version override (e.g. v1beta1, v1beta2)",
  )
  if live_crds:
    parser.add_argument(
        "--load-live-crds",
        action="store_true",
        help=(
            "Force loading OpenAPI v3 schemas from the live cluster's CRDs"
            " (default in --mode live)"
        ),
    )


def add_no_remote_schema_argument(parser) -> None:
  parser.add_argument(
      "--no-remote-schema",
      action="store_true",
      help=(
          "Never download release schemas (same as"
          " GKE_KUEUE_TROUBLESHOOTING_NO_REMOTE_SCHEMA=1)"
      ),
  )


def apply_no_remote_schema(args) -> None:
  """Exports --no-remote-schema so every module (and child process) honours it."""
  if getattr(args, "no_remote_schema", False):
    os.environ["GKE_KUEUE_TROUBLESHOOTING_NO_REMOTE_SCHEMA"] = "1"
    os.environ["KUEUE_DIAGNOSE_NO_REMOTE_SCHEMA"] = "1"


def add_kueue_namespace_argument(parser, help_text: str) -> None:
  parser.add_argument(
      "--kueue-namespace",
      default=_env(
          "GKE_KUEUE_TROUBLESHOOTING_NAMESPACE",
          "KUEUE_DIAGNOSE_NAMESPACE",
          "kueue-system",
      ),
      help=help_text,
  )


def apply_kueue_namespace(args) -> None:
  """Exports --kueue-namespace so the noise rules never drop Kueue's own namespace."""
  if getattr(args, "kueue_namespace", ""):
    os.environ["GKE_KUEUE_TROUBLESHOOTING_NAMESPACE"] = args.kueue_namespace
    os.environ["KUEUE_DIAGNOSE_NAMESPACE"] = args.kueue_namespace


def add_ledger_path_argument(parser, help_text: str, *aliases: str) -> None:
  parser.add_argument(
      "--ledger-path",
      *aliases,
      dest="ledger_path",
      default=_env(
          "GKE_KUEUE_TROUBLESHOOTING_LEDGER_PATH", "KUEUE_DIAGNOSE_LEDGER_PATH"
      ),
      help=help_text,
  )


def add_max_output_bytes_argument(
    parser, default_bytes: int, help_text: str
) -> None:
  parser.add_argument(
      "--max-output-bytes",
      type=int,
      default=int(
          _env(
              "GKE_KUEUE_TROUBLESHOOTING_MAX_OUTPUT_BYTES",
              "KUEUE_DIAGNOSE_MAX_OUTPUT_BYTES",
              str(default_bytes),
          )
      ),
      help=help_text,
  )


def load_ledger(ledger_path: str, *, strict: bool = True) -> Any:
  """Loads the ledger JSON file, or returns a fresh empty ledger if unreadable.

  With `strict` (default) a stored value that is not a mapping is also replaced
  by the empty ledger; the lenient form returns whatever was stored.

  Args:
    ledger_path: Path to the ledger JSON file.
    strict: Whether non-dict JSON values are replaced with an empty ledger.

  Returns:
    The parsed ledger mapping (or stored JSON value when `strict=False`).
  """
  empty: dict[str, Any] = {
      "referenced": [],
      "inspected": [],
      "tool_outputs": [],
  }
  if not os.path.exists(ledger_path):
    return empty
  try:
    with open(ledger_path, "r", encoding="utf-8") as f:
      data = json.load(f)
  except (OSError, json.JSONDecodeError):
    return empty
  if strict and not isinstance(data, dict):
    return empty
  return data


def emit_error(
    message: str, next_step: str, *, render, stderr_prefix: str = ""
) -> int:
  """Prints `{error, next_step}` with the caller's renderer and the message on stderr; returns 1."""
  sys.stdout.write(render({"error": message, "next_step": next_step}))
  sys.stderr.write(f"{stderr_prefix}{message}\n")
  return 1


def add_ignore_namespaces_argument(parser) -> None:
  """Registers --ignore-namespaces; the value is exported so every module sees it."""
  parser.add_argument(
      "--ignore-namespaces",
      default=_env(
          "GKE_KUEUE_TROUBLESHOOTING_IGNORE_NAMESPACES",
          "KUEUE_DIAGNOSE_IGNORE_NAMESPACES",
      ),
      help=(
          "Comma-separated namespaces of platform add-ons to treat as noise in"
          " addition to kube-system, kube-public and kube-node-lease (same as"
          " GKE_KUEUE_TROUBLESHOOTING_IGNORE_NAMESPACES)"
      ),
  )


def apply_ignore_namespaces(args) -> None:
  if getattr(args, "ignore_namespaces", ""):
    os.environ["GKE_KUEUE_TROUBLESHOOTING_IGNORE_NAMESPACES"] = (
        args.ignore_namespaces
    )
    os.environ["KUEUE_DIAGNOSE_IGNORE_NAMESPACES"] = args.ignore_namespaces


_QUANTITY_SUFFIX = {
    "m": 1e-3,
    "k": 1e3,
    "M": 1e6,
    "G": 1e9,
    "T": 1e12,
    "P": 1e15,
    "Ki": 2**10,
    "Mi": 2**20,
    "Gi": 2**30,
    "Ti": 2**40,
    "Pi": 2**50,
}


def parse_quantity(value: Any) -> float | None:
  """Parses a Kubernetes quantity (`8`, `500m`, `2Gi`, `1k`) into a float; None if unparsable."""
  if value is None or isinstance(value, bool):
    return None
  if isinstance(value, (int, float)):
    return float(value)
  s = str(value).strip()
  m = re.fullmatch(r"([0-9]*\.?[0-9]+)([a-zA-Z]*)", s)
  if not m:
    return None
  num, suffix = m.group(1), m.group(2)
  if not suffix:
    return float(num)
  if suffix in _QUANTITY_SUFFIX:
    return float(num) * _QUANTITY_SUFFIX[suffix]
  return None


def fmt_num(x: float) -> str:
  return str(int(x)) if float(x).is_integer() else f"{x:g}"


def fmt_quantity(x: float | None, resource: str) -> str:
  """Formats a parsed quantity for humans: memory/storage-like resources in Gi, everything else as a number."""
  if x is None:
    return "n/a"
  if resource in ("memory", "ephemeral-storage") or resource.endswith(
      "storage"
  ):
    if x == 0:
      return "0Gi"
    for unit, power in (("Pi", 50), ("Ti", 40), ("Gi", 30)):
      v = x / 2**power
      if v >= 1:
        return f"{v:.6g}{unit}"
    return f"{x / 2**20:.6g}Mi"
  return fmt_num(x)


def report_dir_for(ledger_path: str | None) -> str:
  """Returns the directory where full reports are written for this ledger."""
  if ledger_path:
    base = os.path.dirname(os.path.abspath(ledger_path))
  else:
    base = tempfile.gettempdir()
  return os.path.join(base, REPORT_DIR_NAME)


def write_full_report(
    ledger_path: str | None, stem: str, text: str, ext: str
) -> str:
  """Atomically writes `text` to a new, uniquely named report file and returns its path."""
  out_dir = report_dir_for(ledger_path)
  os.makedirs(out_dir, exist_ok=True)
  stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
  path = os.path.join(out_dir, f"{stem}-{stamp}.{ext}")
  tmp = f"{path}.tmp"
  with open(tmp, "w", encoding="utf-8") as f:
    f.write(text)
  os.replace(tmp, path)
  return path


def compact_schema_reference(
    schema_ref: dict[str, Any],
) -> tuple[dict[str, Any], int]:
  """Drops per-kind `valid_fields` lists, keeping version info and invariants.

  The full field lists stay in the full report and are available via
  `snapshot.py --action explain --kind <Kind>`.

  Args:
    schema_ref: Active API schema reference mapping keyed by Kind.

  Returns:
    A `(compacted_copy, dropped_kind_count)` tuple.
  """
  if not isinstance(schema_ref, dict):
    return schema_ref, 0
  out: dict[str, Any] = {}
  dropped = 0
  for kind, body in schema_ref.items():
    if kind in _SCHEMA_META_KEYS or not isinstance(body, dict):
      out[kind] = body
      continue
    slim = {k: v for k, v in body.items() if k != "valid_fields"}
    if "valid_fields" in body:
      slim["valid_fields"] = (
          f"<{len(body['valid_fields'])} fields omitted; see full_report_file"
          f" or `snapshot.py --action explain --kind {kind}`>"
      )
      dropped += 1
    out[kind] = slim
  return out, dropped


def truncation_note(
    full_report_file: str,
    max_output_bytes: int,
    dropped: dict[str, Any],
    hint: str,
) -> dict[str, Any]:
  """Builds the standard `truncated` block appended to a budgeted digest."""
  return {
      "dropped_items": dropped,
      "max_output_bytes": max_output_bytes,
      "full_report_file": full_report_file,
      "hint": hint,
  }


# A trim step shrinks the digest by one notch (drop a few list entries, halve a
# dict, compact a sub-document) and returns True; it returns False when it has
# nothing left to remove. Steps record what they dropped themselves (closures
# over a shared bookkeeping object) so the caller can build the `truncated`
# note from it.
TrimStep = Callable[[dict[str, Any]], bool]

# Room reserved for the `truncated` note appended once shrinking is done, and
# the smallest budget a digest is ever shrunk to.
_TRUNCATION_NOTE_RESERVE = 1500
_MIN_DIGEST_BUDGET = 1000


def serialized_size(payload: Any) -> int:
  """Size in bytes of `payload` as the scripts print it (`json.dumps(indent=2)`)."""
  return len(json.dumps(payload, indent=2).encode("utf-8"))


def apply_output_cap(
    payload: dict[str, Any],
    max_bytes: int,
    trim_steps: list[TrimStep],
    note: Callable[[], dict[str, Any] | None] | None = None,
    *,
    size: Callable[[Any], int] = serialized_size,
    skip_if_fits: bool = True,
) -> dict[str, Any]:
  """Shrinks `payload` in place until its serialised size fits `max_bytes`.

  Applies each step in `trim_steps` repeatedly until the budget (`max_bytes`
  minus room for `truncated`) is met or all steps are exhausted, then stores
  `note()` under `payload["truncated"]` if non-empty.

  Args:
    payload: Digest dictionary to shrink in place.
    max_bytes: Maximum allowed serialised byte size.
    trim_steps: Ordered callables that each remove one notch and return True.
    note: Optional zero-arg builder for the `truncated` metadata block.
    size: Byte-size measurer matching the caller's output format.
    skip_if_fits: Return `payload` untouched if it already fits `max_bytes`.

  Returns:
    The mutated `payload` dictionary.
  """
  if skip_if_fits and size(payload) <= max_bytes:
    return payload
  budget = max(_MIN_DIGEST_BUDGET, max_bytes - _TRUNCATION_NOTE_RESERVE)
  for step in trim_steps:
    while size(payload) > budget and step(payload):
      pass
    if size(payload) <= budget:
      break
  block = note() if note is not None else None
  if block:
    payload["truncated"] = block
  return payload


_TAGGED_RE = re.compile(r"^\[[SL]\d+\]")


_PINNED_NOTE_PREFIXES = (
    "BUNDLE_COVERAGE:",
    "LOG_COVERAGE:",
    "SNAPSHOT_INVENTORY:",
    "KUEUECONFIGURATION_FACTS:",
    "PROVISIONINGREQUESTCONFIG_FACTS",
    "ADMISSIONCHECK_FACTS",
    "FAIR_SHARING_ARITHMETIC",
    "WORKLOAD_LIFECYCLE:",
    "WORKLOAD_TIMELINE:",
    "WORKLOAD_TERMINAL_EVENT:",
    "CLUSTERQUEUE_FACTS",
    "NODE_TAINT_FACTS",
    "NODE_CONDITION_FACTS",
)


def shrink_untagged_notes(
    notes: list[str], step: int = 1
) -> tuple[list[str], int]:
  """Removes up to `step` untagged, non-pinned notes from the tail of `notes`.

  Tagged facts (`[S<n>]`/`[L<n>]`) and pinned coverage/config headers are never
  removed.

  Args:
    notes: Fact strings in display order.
    step: Maximum number of removable untagged notes to drop.

  Returns:
    A `(shrunk_notes, removed_count)` tuple.
  """
  out = list(notes)
  removed = 0
  idx = len(out) - 1
  while idx >= 0 and removed < step:
    note = out[idx]
    if (
        isinstance(note, str)
        and not _TAGGED_RE.match(note)
        and not note.startswith("...")
        and not note.startswith(_PINNED_NOTE_PREFIXES)
    ):
      del out[idx]
      removed += 1
    idx -= 1
  return out, removed


def untagged_trailer(removed: int, what: str) -> str:
  """Trailer line appended to a shrunk fact list."""
  return (
      f"... {removed} untagged {what} omitted from this digest (all tagged"
      " facts kept); see full_report_file"
  )


# ---------------------------------------------------------------------------
# Fact ids
#
# Each script tags the facts a report must explicitly classify (status
# conditions, Warning events, deletions, audit mutations, log-derived facts)
# with a short id such as ``[S3]`` (snapshot) or ``[L7]`` (trace_logs). The id
# -> fact mapping is stored in the ledger under ``facts`` so that
# ``validate_report.py`` can check that every id appears under
# ``#### Root Cause`` or ``#### Ruled Out``. Ids are stable across re-runs of a
# script within one investigation: the same ``key`` always maps to the same id.
# ---------------------------------------------------------------------------

MAX_TRACKED_FACTS_PER_SOURCE = 18
MAX_TRACKED_FACTS_TOTAL = 28


def _load_ledger(ledger_path: str) -> dict[str, Any]:
  return load_ledger(ledger_path, strict=True)


def _save_ledger(ledger_path: str, ledger: dict[str, Any]) -> None:
  os.makedirs(os.path.dirname(os.path.abspath(ledger_path)), exist_ok=True)
  tmp_path = f"{ledger_path}.tmp"
  with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump(ledger, f, indent=2)
  os.replace(tmp_path, ledger_path)


def _fact_core(key: str) -> str:
  """The part of a key that is comparable across sources (drops the category prefix)."""
  return key.split(":", 1)[1] if ":" in key else key


def register_facts(
    ledger_path: str | None,
    prefix: str,
    facts: list[tuple[str, str]],
    max_tracked: int = MAX_TRACKED_FACTS_PER_SOURCE,
    max_total: int = MAX_TRACKED_FACTS_TOTAL,
) -> dict[str, str]:
  """Assigns capped, stable ids to `(key, text)` facts in `ledger_path` and returns `{key: id}`."""
  ledger = _load_ledger(ledger_path) if ledger_path else {}
  all_existing = [
      f for f in ledger.get("facts", []) if isinstance(f, dict) and "key" in f
  ]
  existing = [
      f for f in all_existing if str(f.get("id", "")).startswith(prefix)
  ]
  by_key = {str(f["key"]): str(f["id"]) for f in existing}
  by_core = {_fact_core(str(f["key"])): str(f["id"]) for f in all_existing}
  next_num = len(existing) + 1
  mapping: dict[str, str] = {}
  new_entries: list[dict[str, Any]] = []
  for key, text in facts:
    if key in mapping:
      continue
    if key in by_key:
      mapping[key] = by_key[key]
      continue
    core = _fact_core(key)
    if core in by_core:
      mapping[key] = by_core[core]
      continue
    if (
        len(by_key) + len(new_entries) >= max_tracked
        or len(all_existing) + len(new_entries) >= max_total
    ):
      continue
    fid = f"{prefix}{next_num}"
    next_num += 1
    mapping[key] = fid
    by_core[core] = fid
    new_entries.append({"id": fid, "key": key, "text": text[:600]})
  if ledger_path and new_entries:
    ledger.setdefault("facts", []).extend(new_entries)
    _save_ledger(ledger_path, ledger)
  return mapping


def tag(mapping: dict[str, str], key: str | None, text: str) -> str:
  """Prefixes `text` with its fact id when the key is tracked."""
  if key and key in mapping:
    return f"[{mapping[key]}] {text}"
  return text


_QUOTED_RE = re.compile(r"\"[^\"]*\"|'[^']*'|`[^`]*`")
_HEXISH_RE = re.compile(r"\b[a-z0-9]*[0-9][a-z0-9]{4,}\b")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def fact_group_key(
    category: str, kind: str, reason: str, message: str, width: int = 72
) -> str:
  """Builds a shape-normalised grouping key for a message-bearing fact.

  Quoted strings, hex-like suffixes, and numbers are masked before taking the
  first `width` characters so equivalent messages share one fact id.

  Args:
    category: Fact category prefix (e.g. `event`, `logerr`).
    kind: Involved Kubernetes object kind, or empty string.
    reason: Event or condition reason string.
    message: Raw message text to normalise.
    width: Maximum normalised message prefix length.

  Returns:
    The composite `<category>:<kind>:<reason>:<normalised_prefix>` key.
  """
  norm = _QUOTED_RE.sub("<q>", message)
  norm = _HEXISH_RE.sub("<id>", norm)
  norm = _NUMBER_RE.sub("#", norm)
  norm = re.sub(r"\s+", " ", norm).strip().lower()
  return f"{category}:{kind}:{reason}:{norm[:width]}"
