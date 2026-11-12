#!/usr/bin/env python3
r"""Template Script for BigQuery Migration Metadata Extraction Statistics.

This asset template script inspects metadata and query-log ZIP archives
produced by `gcloud alpha bq migration {metadata,query-logs} extract` (such as
`dwh-migration-snowflake-metadata.zip` and `dwh-migration-snowflake-logs.zip`),
whether it ran locally or in the cloud, from either a local path or a Google
Cloud Storage (`gs://`) URI. It validates that the archive is not an incomplete
22-byte GCS NIO ZipFS placeholder, parses the extracted catalog files and
extractor telemetry across Snowflake, Redshift, Teradata, ANSI SQL, and
BigQuery dumps, and prints a structured summary of what was extracted.

Usage Pattern:
  Copy `assets/extraction_stats_template.py` from this skill's directory
  (`<SKILL_DIR>`, the directory containing `SKILL.md`) into your working
  directory (e.g., `./extraction_stats.py`). Run the copy as-is for
  standard post-extraction verification and reporting, and prioritize modifying
  the marked `# CUSTOMIZE:` extension points if your workflow requires custom
  schema/table filtering, custom complex data type rules, custom validation
  thresholds, or custom output formatting. Sections marked
  `# DEFAULT SCAFFOLDING` can be kept unchanged unless deeper orchestration
  adjustments are needed.

Dependencies:
  Uses the Python 3.9+ standard library only (no third-party pip packages
  required). Requires `gcloud` CLI when inspecting `gs://` URIs directly.

Usage Examples:
    # Copy the template from this skill's directory to your working directory:
    cp <SKILL_DIR>/assets/extraction_stats_template.py ./extraction_stats.py

    # 1. Inspect a GCS extraction output directory or ZIP URI directly:
    python3 ./extraction_stats.py \
        --input gs://my-bucket/snowflake_metadata/

    # 2. Inspect a local extracted metadata ZIP archive and export JSON/Markdown:
    python3 ./extraction_stats.py \
        --input ./dwh-migration-snowflake-metadata.zip \
        --output-json ./extraction_stats.json \
        --output-markdown ./extraction_stats.md
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime
import io
import json
import os
import re
import subprocess
import sys
from typing import Any
import zipfile

# Increase CSV field limit to safely parse multi-line view DDLs and query logs.
csv.field_size_limit(10 * 1024 * 1024)


# ==============================================================================
# 1. Extension Points: Filtering & Classification Rules (CUSTOMIZE)
# ==============================================================================


# CUSTOMIZE: Custom Schema & Table Filtering
_EXCLUDED_SYSTEM_SCHEMAS: set[str] = {
    "INFORMATION_SCHEMA",
    "PG_CATALOG",
    "PG_INTERNAL",
    "DBC",
    "SYSLIB",
    "SYSUDTLIB",
}


def _should_include_schema(schema_name: str) -> bool:
  """Determines whether a source schema should be included in catalog stats.

  Override this function or update `_EXCLUDED_SYSTEM_SCHEMAS` if you want to
  exclude system, staging, or scratch schemas (such as INFORMATION_SCHEMA,
  PG_CATALOG, DBC, or STAGING_TMP) from object counts.

  Args:
    schema_name: Source schema name from catalog CSVs.

  Returns:
    True if the schema should be included in the statistics report.
  """
  excluded = {s.strip().upper() for s in _EXCLUDED_SYSTEM_SCHEMAS}
  return schema_name.strip().upper() not in excluded


# CUSTOMIZE: Complex Data Type Classification
def _classify_special_data_types(
    data_type_counts: dict[str, int],
) -> dict[str, int]:
  """Identifies source column types requiring special migration attention.

  Flags semi-structured, high-precision numeric, and temporal types that need
  explicit casting or transformation during downstream Parquet export and
  BigQuery SQL translation.

  Args:
    data_type_counts: Mapping of uppercase source DataType to column count.

  Returns:
    Subset mapping of flagged data types to their column counts.
  """
  special_keywords = (
      "VARIANT",
      "ARRAY",
      "OBJECT",
      "SUPER",
      "GEOGRAPHY",
      "GEOMETRY",
      "NUMBER",
      "DECIMAL",
      "NUMERIC",
      "TIMESTAMP",
  )
  flagged: dict[str, int] = {}
  for dtype, count in data_type_counts.items():
    if any(kw in dtype.upper() for kw in special_keywords):
      flagged[dtype] = count
  return flagged


# CUSTOMIZE: Custom Telemetry & Archive Validation Thresholds
_MIN_VALID_ZIP_BYTES = 22


# ==============================================================================
# 2. Storage & Archive Discovery Helpers (DEFAULT SCAFFOLDING)
# ==============================================================================
# DEFAULT SCAFFOLDING: Local and GCS ZIP discovery and reading utilities.


def format_bytes(num_bytes: int) -> str:
  """Formats a byte count into a human-readable string."""
  if num_bytes < 1024:
    return f"{num_bytes:,} B"
  if num_bytes < 1024 * 1024:
    return f"{num_bytes:,} B ({num_bytes / 1024:.2f} KB)"
  if num_bytes < 1024 * 1024 * 1024:
    return f"{num_bytes:,} B ({num_bytes / (1024 * 1024):.2f} MB)"
  return f"{num_bytes:,} B ({num_bytes / (1024 * 1024 * 1024):.2f} GB)"


def discover_zip_sources(input_path_or_uri: str) -> list[str]:
  """Resolves a local path or GCS URI into one or more ZIP archive paths/URIs.

  Ignores temporary GCS NIO ZipFS staging files (`zipfstmp*.tmp`).

  Args:
    input_path_or_uri: Local file/directory path or `gs://` file/prefix URI.

  Returns:
    Sorted list of local paths or `gs://` URIs ending in `.zip`.

  Raises:
    FileNotFoundError: If no matching ZIP archives exist at the given path/URI.
  """
  if input_path_or_uri.startswith("gs://"):
    if input_path_or_uri.lower().endswith(".zip"):
      return [input_path_or_uri]
    prefix = input_path_or_uri.rstrip("/") + "/*.zip"
    cmd = ["gcloud", "storage", "ls", prefix]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
      raise FileNotFoundError(
          f"No .zip archives found under GCS URI '{input_path_or_uri}': "
          f"{res.stderr.strip()}"
      )
    uris = [
        line.strip()
        for line in res.stdout.splitlines()
        if line.strip().endswith(".zip")
        and "zipfstmp" not in os.path.basename(line.strip())
    ]
    if not uris:
      raise FileNotFoundError(
          f"No finalized .zip archives found under '{input_path_or_uri}'."
      )
    return sorted(uris)

  if not os.path.exists(input_path_or_uri):
    raise FileNotFoundError(f"Input path not found: '{input_path_or_uri}'")

  if os.path.isfile(input_path_or_uri):
    return [input_path_or_uri]

  found: list[str] = []
  for entry in sorted(os.listdir(input_path_or_uri)):
    if entry.endswith(".zip") and not entry.startswith("zipfstmp"):
      found.append(os.path.join(input_path_or_uri, entry))
  if not found:
    raise FileNotFoundError(
        f"No .zip archives found in directory: '{input_path_or_uri}'"
    )
  return found


def read_zip_bytes(path_or_uri: str) -> bytes:
  """Reads raw bytes of a ZIP archive from a local path or GCS URI."""
  if path_or_uri.startswith("gs://"):
    cmd = ["gcloud", "storage", "cat", path_or_uri]
    res = subprocess.run(cmd, capture_output=True, check=False)
    if res.returncode != 0:
      err = res.stderr.decode("utf-8", errors="replace").strip()
      raise RuntimeError(f"Failed to read GCS archive '{path_or_uri}': {err}")
    return res.stdout

  with open(path_or_uri, "rb") as f:
    return f.read()


# ==============================================================================
# 3. CSV & Telemetry Parsing Engine (DEFAULT SCAFFOLDING)
# ==============================================================================
# DEFAULT SCAFFOLDING: Escape-aware CSV reader and multi-dialect catalog parser.


def _find_zip_entry(zf: zipfile.ZipFile, candidates: list[str]) -> str | None:
  """Finds the first matching entry in a ZipFile (exact or basename match)."""
  entries = [info.filename for info in zf.infolist() if not info.is_dir()]
  entry_set = set(entries)
  for cand in candidates:
    if cand in entry_set:
      return cand
  lower_map = {os.path.basename(e).lower(): e for e in entries}
  for cand in candidates:
    match = lower_map.get(cand.lower())
    if match:
      return match
  return None


def _read_csv_from_zip(
    zf: zipfile.ZipFile, candidates: list[str]
) -> list[dict[str, str]]:
  r"""Reads the first matching CSV file from a ZipFile using escapechar='\\'.

  The extractor escapes embedded quotes inside multi-line view DDLs with
  backslashes (`\"`). Setting `escapechar='\\'` prevents misparsing multi-line
  SQL definitions into extra rows.

  Args:
    zf: Open `zipfile.ZipFile` instance.
    candidates: Ordered list of candidate entry filenames (e.g.
      `['tables-au.csv', 'tables.csv']`).

  Returns:
    List of row dictionaries parsed via `csv.DictReader`.
  """
  target = _find_zip_entry(zf, candidates)
  if not target:
    return []

  raw_text = zf.read(target).decode("utf-8-sig", errors="replace")
  reader = csv.DictReader(io.StringIO(raw_text), escapechar="\\")
  return [dict(row) for row in reader]


def _count_csv_rows_in_zip(zf: zipfile.ZipFile, entry_name: str) -> int:
  r"""Counts the data rows of a CSV entry without loading it into memory.

  Streams the entry with the same `escapechar='\\'` parsing as
  `_read_csv_from_zip()` and, like `csv.DictReader`, skips blank rows and does
  not count the header row.

  Args:
    zf: Open `zipfile.ZipFile` instance.
    entry_name: Exact entry name inside the archive.

  Returns:
    Number of data rows (0 for an empty file or a header-only file).
  """
  with zf.open(entry_name) as raw:
    text = io.TextIOWrapper(
        raw, encoding="utf-8-sig", errors="replace", newline=""
    )
    non_blank_rows = sum(1 for row in csv.reader(text, escapechar="\\") if row)
  return max(non_blank_rows - 1, 0)


def _get_field(row: dict[str, str], *keys: str) -> str:
  """Case-insensitive dictionary lookup returning a stripped string."""
  for k in keys:
    val = row.get(k)
    if val is not None and str(val).strip():
      return str(val).strip()
  lower_row = {
      str(rk).strip().lower(): str(rv).strip()
      for rk, rv in row.items()
      if rk is not None and rv is not None
  }
  for k in keys:
    val = lower_row.get(k.lower())
    if val:
      return val
  return ""


def _read_bigquery_tables_jsonl(
    zf: zipfile.ZipFile,
) -> tuple[
    bool, list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]
]:
  """Reads a `bigquery` connector `tables.jsonl` as table and column rows.

  The `bigquery` connector writes one JSON object per table (project, dataset,
  table, tableType, a nested schema, and `viewQuery` for views) instead of
  catalog CSVs. Each object is converted into the row shape used for the CSV
  catalogs so that the same counting logic applies:

  * `TABLE` becomes a base table; `VIEW` and `MATERIALIZED_VIEW` become views,
    with `viewQuery` as their DDL.
  * `EXTERNAL` tables are returned as external table rows. Like external tables
    in the CSV catalogs, they and their columns are not counted as base tables.
  * Other types (such as `SNAPSHOT` table snapshots) are kept in the table rows
    so that their columns are excluded, but are not counted as tables or views.

  Only top-level fields count as columns; nested `RECORD` subfields do not. The
  connector records no row counts or sizes.

  Args:
    zf: Open `zipfile.ZipFile` instance.

  Returns:
    Tuple of (found, table rows, column rows, external table rows). `found` is
    True when the archive has a `tables.jsonl` entry, even an empty one; the
    lists are empty without one.
  """
  target = _find_zip_entry(zf, ["tables.jsonl"])
  if not target:
    return False, [], [], []

  table_rows: list[dict[str, str]] = []
  col_rows: list[dict[str, str]] = []
  ext_rows: list[dict[str, str]] = []
  raw_text = zf.read(target).decode("utf-8-sig", errors="replace")
  for line in raw_text.splitlines():
    line = line.strip()
    if not line:
      continue
    try:
      record = json.loads(line)
    except json.JSONDecodeError:
      continue
    if not isinstance(record, dict):
      continue
    project = str(record.get("project") or "")
    dataset = str(record.get("dataset") or "")
    table = str(record.get("table") or "")
    if not dataset or not table:
      continue
    table_type = str(record.get("tableType") or "TABLE").upper()
    table_rows.append({
        "TableCatalog": project,
        "TableSchema": dataset,
        "TableName": table,
        "TableType": "BASE TABLE" if table_type == "TABLE" else table_type,
        "ViewDefinition": str(record.get("viewQuery") or ""),
    })
    if table_type == "EXTERNAL":
      ext_rows.append({
          "TableCatalog": project,
          "SchemaName": dataset,
          "TableName": table,
      })
    fields = record.get("schema")
    if not isinstance(fields, list):
      continue
    for field in fields:
      if not isinstance(field, dict):
        continue
      dtype = str(field.get("type") or "UNKNOWN").upper()
      if str(field.get("mode") or "").upper() == "REPEATED":
        dtype = f"ARRAY<{dtype}>"
      col_rows.append({
          "TableCatalog": project,
          "TableSchema": dataset,
          "TableName": table,
          "ColumnName": str(field.get("name") or ""),
          "DataType": dtype,
      })
  return True, table_rows, col_rows, ext_rows


_MIN_DATETIME = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)


def _parse_client_time(value: str) -> datetime.datetime | None:
  """Parses a telemetry `dumperRunStartClientTime` into an aware datetime.

  The extractor writes ISO-8601 timestamps with a `Z` or `+HH:MM` offset (and
  possibly a `[Region/City]` zone ID) and a variable number of fractional
  digits, which `datetime.fromisoformat()` only accepts from Python 3.11 on.

  Args:
    value: Raw timestamp string.

  Returns:
    Timezone-aware datetime (UTC if the value has no offset), or None if the
    value cannot be parsed.
  """
  text = re.sub(r"\[[^\]]*\]$", "", value.strip())
  if text[-1:] in ("Z", "z"):
    text = text[:-1] + "+00:00"
  parts = re.match(
      r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2})(:\d{2})?(?:[.,](\d+))?(.*)$", text
  )
  if not parts:
    return None
  fraction = (parts.group(3) or "").ljust(6, "0")[:6]
  text = f"{parts.group(1)}{parts.group(2) or ':00'}.{fraction}{parts.group(4)}"
  try:
    parsed = datetime.datetime.fromisoformat(text)
  except ValueError:
    return None
  if parsed.tzinfo is None:
    parsed = parsed.replace(tzinfo=datetime.timezone.utc)
  return parsed


def _select_archive_run(
    records: list[dict[str, Any]], archive_connector: str
) -> list[dict[str, Any]]:
  """Returns the telemetry records of the run that produced this archive.

  The extractor keeps one telemetry file per machine, adds every run to it (not
  always in time order), and copies the whole file into each archive. Only the
  run that wrote this archive may contribute fields such as host, warehouse, or
  user. A record with a start time opens a run; records without one continue
  the run opened before them, and records before the first start time are used
  only if no run has a start time. Runs whose connector matches
  `compilerworks-arguments.txt` are preferred, and among them the run with the
  latest start time (compared as timezone-aware datetimes) wins.

  Args:
    records: Parsed `dumper-telemetry.jsonl` records, in file order.
    archive_connector: Connector named in `compilerworks-arguments.txt`, or "".

  Returns:
    Records of the selected run, in file order (empty if there are none).
  """
  runs: dict[str, list[dict[str, Any]]] = {}
  current_start = ""
  for record in records:
    start = str(record.get("dumperRunStartClientTime") or "")
    if start:
      current_start = start
    runs.setdefault(current_start, []).append(record)
  candidates = {k: v for k, v in runs.items() if k} or runs

  def _run_connector(run: list[dict[str, Any]]) -> str:
    for record in run:
      payloads = record.get("payload")
      if isinstance(payloads, list) and payloads:
        first = payloads[0] if isinstance(payloads[0], dict) else {}
        summary = first.get("argumentSummary")
        if isinstance(summary, dict) and summary.get("connector"):
          return str(summary["connector"]).strip().lower()
    return ""

  wanted = archive_connector.strip().lower()
  if wanted:
    matching = {
        k: v for k, v in candidates.items() if _run_connector(v) == wanted
    }
    candidates = matching or candidates
  if not candidates:
    return []

  def _run_order(start: str) -> tuple[bool, datetime.datetime, str]:
    parsed = _parse_client_time(start) if start else None
    return (parsed is not None, parsed or _MIN_DATETIME, start)

  return candidates[max(candidates, key=_run_order)]


def _parse_dumper_telemetry(zf: zipfile.ZipFile) -> dict[str, Any]:
  """Extracts connector, host, status, and task counts from telemetry files."""
  telemetry: dict[str, Any] = {
      "format": "",
      "overall_status": "UNKNOWN",
      "connector": "",
      "host": "",
      "warehouse": "",
      "user": "",
      "databases_arg": [],
      "dumper_version": "",
      "run_start_time": "",
      "run_duration_minutes": 0,
      "tasks_succeeded": 0,
      "tasks_skipped": 0,
      "tasks_failed": 0,
      "warehouse_count": None,
  }

  fmt_entry = _find_zip_entry(zf, ["compilerworks-format.txt"])
  if fmt_entry:
    telemetry["format"] = (
        zf.read(fmt_entry).decode("utf-8", errors="replace").strip()
    )

  sf_entry = _find_zip_entry(zf, ["snowflake.yaml"])
  if sf_entry:
    sf_yaml = zf.read(sf_entry).decode("utf-8", errors="replace")
    match = re.search(r"warehouse_count:\s*(\d+)", sf_yaml)
    if match:
      telemetry["warehouse_count"] = int(match.group(1))

  # compilerworks-arguments.txt holds the arguments of the run that wrote this
  # archive; its connector also picks that run out of the shared telemetry.
  archive_args: dict[str, str] = {}
  args_entry = _find_zip_entry(zf, ["compilerworks-arguments.txt"])
  if args_entry:
    args_txt = zf.read(args_entry).decode("utf-8", errors="replace")
    for arg_name in ("connector", "host", "warehouse"):
      arg_match = re.search(rf"\b{arg_name}=([^,\s}}]+)", args_txt)
      if arg_match and arg_match.group(1) != "null":
        archive_args[arg_name] = arg_match.group(1)

  tel_entry = _find_zip_entry(zf, ["dumper-telemetry.jsonl"])
  if tel_entry:
    raw_lines = (
        zf.read(tel_entry).decode("utf-8", errors="replace").splitlines()
    )
    records: list[dict[str, Any]] = []
    for line in raw_lines:
      line = line.strip()
      if not line:
        continue
      try:
        parsed = json.loads(line)
      except json.JSONDecodeError:
        continue
      if isinstance(parsed, dict):
        records.append(parsed)
    records = _select_archive_run(records, archive_args.get("connector", ""))
    for record in records:
      if record.get("dumperRunStartClientTime"):
        telemetry["run_start_time"] = record["dumperRunStartClientTime"]
      meta = record.get("dumperMetadata", {})
      if isinstance(meta, dict) and meta.get("version"):
        telemetry["dumper_version"] = meta["version"]
      payloads = record.get("payload", [])
      if isinstance(payloads, list) and payloads:
        first = payloads[0] if isinstance(payloads[0], dict) else {}
        if first.get("overallStatus"):
          telemetry["overall_status"] = first["overallStatus"]
        if first.get("runDurationInMinutes") is not None:
          telemetry["run_duration_minutes"] = first["runDurationInMinutes"]
        task_summary = first.get("taskExecutionSummary")
        if isinstance(task_summary, list) and task_summary:
          telemetry["tasks_succeeded"] = 0
          telemetry["tasks_skipped"] = 0
          telemetry["tasks_failed"] = 0
          for task_stat in task_summary:
            if not isinstance(task_stat, dict):
              continue
            status = str(task_stat.get("status", "")).upper()
            count = int(task_stat.get("count", 0) or 0)
            if status == "SUCCEEDED":
              telemetry["tasks_succeeded"] += count
            elif status == "SKIPPED":
              telemetry["tasks_skipped"] += count
            elif status == "FAILED":
              telemetry["tasks_failed"] += count
        args_summary = first.get("argumentSummary", {})
        if isinstance(args_summary, dict):
          if args_summary.get("connector"):
            telemetry["connector"] = args_summary["connector"]
          if args_summary.get("host"):
            telemetry["host"] = args_summary["host"]
          if args_summary.get("warehouse"):
            telemetry["warehouse"] = args_summary["warehouse"]
          if args_summary.get("user"):
            telemetry["user"] = args_summary["user"]
          dbs = args_summary.get("database", [])
          if isinstance(dbs, list) and dbs:
            telemetry["databases_arg"] = [str(d) for d in dbs]

  for arg_name, arg_value in archive_args.items():
    if not telemetry[arg_name]:
      telemetry[arg_name] = arg_value

  return telemetry


def _safe_int(val: str | None) -> int:
  """Parses an integer string safely, returning 0 on empty or invalid input."""
  if not val:
    return 0
  try:
    return int(float(val.strip()))
  except (ValueError, TypeError):
    return 0


def analyze_zip_archive(path_or_uri: str, zip_bytes: bytes) -> dict[str, Any]:
  """Analyzes a Cloud Extractor ZIP payload and returns structured statistics.

  Supports Snowflake, Redshift, Teradata, ANSI SQL, and BigQuery catalog dumps
  as well as query history log archives.

  Args:
    path_or_uri: Source path or GCS URI of the archive.
    zip_bytes: Raw bytes of the `.zip` file.

  Returns:
    Dictionary containing archive validation status, telemetry metadata, object
    counts, row/byte volume totals, per-schema breakdown, base table details,
    view inventory, data type distribution, and query log statistics.
  """
  size_bytes = len(zip_bytes)
  is_zipfs_placeholder = size_bytes <= _MIN_VALID_ZIP_BYTES

  stats: dict[str, Any] = {
      "archive_path": path_or_uri,
      "archive_name": os.path.basename(path_or_uri.rstrip("/")),
      "size_bytes": size_bytes,
      "size_formatted": format_bytes(size_bytes),
      "is_valid_archive": False,
      "is_zipfs_placeholder": is_zipfs_placeholder,
      "validation_message": "",
      "archive_type": "UNKNOWN",
      "telemetry": {},
      "files_in_archive": [],
      "databases": [],
      "schemas": [],
      "counts": {
          "databases": 0,
          "schemas": 0,
          "active_schemas": 0,
          "base_tables": 0,
          "views": 0,
          "columns": 0,
          "base_table_columns": 0,
          "view_columns": 0,
          "functions": 0,
          "external_tables": 0,
          "query_log_files": 0,
          "query_log_entries": 0,
      },
      "volume": {
          "total_base_rows": 0,
          "total_base_bytes": 0,
          "total_base_bytes_formatted": "0 B",
          "available": True,
      },
      "schema_breakdown": [],
      "base_tables": [],
      "views": [],
      "data_type_distribution": {},
      "special_data_types": {},
  }

  if is_zipfs_placeholder:
    stats["validation_message"] = (
        f"INCOMPLETE ARCHIVE ({size_bytes} bytes <= {_MIN_VALID_ZIP_BYTES} B): "
        "Detected GCS NIO ZipFS empty placeholder header. The GCE extraction "
        "VM may still be running or terminated before flushing ZIP chunks."
    )
    return stats

  try:
    zf_ctx = zipfile.ZipFile(io.BytesIO(zip_bytes), "r")
  except zipfile.BadZipFile as e:
    stats["validation_message"] = f"CORRUPT ZIP ARCHIVE: {e}"
    return stats

  with zf_ctx as zf:
    namelist = sorted(
        info.filename for info in zf.infolist() if not info.is_dir()
    )
    stats["files_in_archive"] = namelist
    stats["is_valid_archive"] = True
    stats["validation_message"] = (
        f"VALID ({format_bytes(size_bytes)}, {len(namelist)} files)"
    )

    telemetry = _parse_dumper_telemetry(zf)
    stats["telemetry"] = telemetry

    # Parse catalog CSVs across Snowflake, Redshift, Teradata, and ANSI SQL
    db_candidates = [
        "databases-au.csv",
        "databases.csv",
        "database.csv",
        "dbc.DatabasesV.csv",
    ]
    db_entry = _find_zip_entry(zf, db_candidates)
    db_rows = _read_csv_from_zip(zf, db_candidates)
    schema_rows = _read_csv_from_zip(
        zf,
        ["schemata-au.csv", "schemata.csv"],
    ) + _read_csv_from_zip(zf, ["svv_external_schemas.csv"])
    table_rows = _read_csv_from_zip(
        zf,
        [
            "tables-au.csv",
            "tables.csv",
            "svv_tables.csv",
            "dbc.TablesV.csv",
        ],
    )
    rs_table_info_rows = _read_csv_from_zip(zf, ["svv_table_info.csv"])
    td_table_size_rows = _read_csv_from_zip(zf, ["dbc.TableSizeV.csv"])
    view_rows = _read_csv_from_zip(zf, ["views-au.csv", "views.csv"])
    col_rows = _read_csv_from_zip(
        zf,
        [
            "columns-au.csv",
            "columns.csv",
            "svv_columns.csv",
            "dbc.ColumnsV.csv",
            "dbc.Columns.csv",
        ],
    )
    func_rows = _read_csv_from_zip(
        zf,
        [
            "functions-au.csv",
            "functions.csv",
            "function_info.csv",
            "dbc.FunctionsV.csv",
        ],
    )
    ext_rows = _read_csv_from_zip(
        zf, ["external_tables.csv", "svv_external_tables.csv"]
    )

    # The bigquery connector writes tables.jsonl instead of catalog CSVs and
    # records no row counts or sizes, even when tables.jsonl is empty. Other
    # connectors (such as hiveql) write a tables.jsonl with a different layout,
    # so read it only when the archive names the bigquery connector (or names
    # no connector or format at all).
    archive_source = (
        str(telemetry.get("connector") or "").strip().lower()
        or str(telemetry.get("format") or "").strip().lower()
    )
    is_bigquery_archive = not archive_source or archive_source.startswith(
        "bigquery"
    )
    bq_found = False
    bq_table_rows: list[dict[str, str]] = []
    if is_bigquery_archive and not table_rows and not col_rows:
      bq_found, bq_table_rows, bq_col_rows, bq_ext_rows = (
          _read_bigquery_tables_jsonl(zf)
      )
      if bq_found:
        table_rows = bq_table_rows
        col_rows = bq_col_rows
        ext_rows = ext_rows + bq_ext_rows
    has_volume_stats = not bq_found

    # Build lookup maps for Redshift svv_table_info and Teradata dbc.TableSizeV
    rs_info_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    for info_r in rs_table_info_rows:
      r_db = _get_field(info_r, "database", "table_catalog")
      r_sch = _get_field(info_r, "schema", "table_schema")
      r_tbl = _get_field(info_r, "table", "table_name")
      if not r_tbl:
        continue
      size_mb = _safe_int(_get_field(info_r, "size"))
      info_entry = {
          "catalog": r_db,
          "schema": r_sch,
          "table": r_tbl,
          "row_count": _safe_int(
              _get_field(info_r, "tbl_rows", "estimated_visible_rows")
          ),
          "bytes": size_mb * 1024 * 1024,
          "clustering_key": _get_field(info_r, "sortkey1"),
      }
      rs_info_map[(r_db.upper(), r_sch.upper(), r_tbl.upper())] = info_entry
      rs_info_map.setdefault(("", r_sch.upper(), r_tbl.upper()), info_entry)
    # If svv_tables.csv is absent in a Redshift dump, synthesize table_rows
    if not table_rows and rs_table_info_rows:
      for info_r in rs_table_info_rows:
        table_rows.append({
            "TableCatalog": _get_field(info_r, "database"),
            "TableSchema": _get_field(info_r, "schema"),
            "TableName": _get_field(info_r, "table"),
            "TableType": "BASE TABLE",
        })

    td_size_map: collections.Counter[tuple[str, str]] = collections.Counter()
    for sz_r in td_table_size_rows:
      t_sch = _get_field(sz_r, "DataBaseName", "DatabaseName", "TableSchema")
      t_tbl = _get_field(sz_r, "TableName")
      perm_bytes = _safe_int(_get_field(sz_r, "CurrentPerm", "Bytes"))
      if t_sch and t_tbl:
        td_size_map[(t_sch.upper(), t_tbl.upper())] += perm_bytes

    # Parse query log CSVs if present
    log_prefixes = ("query_history", "querytext", "ddltext", "dwhassessment_")
    query_log_files = [
        fn
        for fn in namelist
        if os.path.basename(fn).lower().startswith(log_prefixes)
        and fn.lower().endswith(".csv")
    ]
    query_log_entries = sum(
        _count_csv_rows_in_zip(zf, qfn) for qfn in query_log_files
    )

    if query_log_files and not table_rows and not col_rows:
      stats["archive_type"] = "QUERY_LOGS"
    else:
      stats["archive_type"] = "CATALOG_METADATA"

    # Databases
    db_names_set: set[str] = set()
    # The Redshift, PostgreSQL, and Greenplum connectors write database.csv
    # with the database name in a `Name` column, including the template0 and
    # template1 template databases. Read `Name` only from that file so that
    # other dialects' database CSVs can't match it.
    is_pg_database_csv = (
        bool(db_entry) and os.path.basename(db_entry).lower() == "database.csv"
    )
    db_name_keys: tuple[str, ...] = (
        "DatabaseName",
        "DataBaseName",
        "database_name",
        "datname",
    )
    if is_pg_database_csv:
      db_name_keys += ("Name",)
    for r in db_rows:
      dname = _get_field(r, *db_name_keys)
      if not dname or not _should_include_schema(dname):
        continue
      if is_pg_database_csv and dname.lower() in ("template0", "template1"):
        continue
      db_names_set.add(dname)
    for info_v in rs_info_map.values():
      if info_v["catalog"]:
        db_names_set.add(info_v["catalog"])
    for bq_row in bq_table_rows:
      if bq_row["TableCatalog"]:
        db_names_set.add(bq_row["TableCatalog"])
    if not db_names_set and telemetry.get("databases_arg"):
      db_names_set.update(telemetry["databases_arg"])
    db_names = sorted(db_names_set)
    stats["databases"] = db_names

    # Schemas (normalized case-insensitively via per_schema)
    per_schema: dict[str, dict[str, Any]] = {}

    def _ensure_schema_entry(schema_name: str) -> dict[str, Any]:
      key = schema_name.upper()
      if key not in per_schema:
        per_schema[key] = {
            "schema": schema_name,
            "base_tables": 0,
            "views": 0,
            "rows": 0,
            "bytes": 0,
            "bytes_formatted": "0 B",
        }
      return per_schema[key]

    for r in schema_rows:
      sname = _get_field(
          r, "SchemaName", "schema_name", "schemaname", "DatabaseName"
      )
      if sname and _should_include_schema(sname):
        _ensure_schema_entry(sname)

    # Identify skipped non-table/non-view relations (e.g. Teradata macros/UDFs
    # or EXTERNAL/TEMPORARY/EVENT TABLE rows) so their columns are excluded from
    # column totals without colliding across catalogs.
    skipped_relations: set[tuple[str, str, str]] = set()
    skipped_relations_no_cat: set[tuple[str, str]] = set()
    included_relations: set[tuple[str, str, str]] = set()
    included_relations_no_cat: set[tuple[str, str]] = set()
    for t in table_rows:
      t_cat = _get_field(t, "TableCatalog", "table_catalog")
      t_schema = _get_field(
          t, "TableSchema", "table_schema", "DataBaseName", "DatabaseName"
      )
      t_name = _get_field(t, "TableName", "table_name")
      t_type = _get_field(t, "TableType", "table_type").upper()
      t_kind = _get_field(t, "TableKind", "table_kind").upper()
      if not t_name or not t_schema:
        continue
      is_skipped = False
      if t_kind and not t_type and t_kind not in ("T", "O", "V"):
        is_skipped = True
      elif any(k in t_type for k in ("EXTERNAL", "TEMPORARY", "EVENT")):
        is_skipped = True
      elif t_type and "VIEW" not in t_type and "TABLE" not in t_type:
        is_skipped = True
      if is_skipped:
        skipped_relations.add((t_cat.upper(), t_schema.upper(), t_name.upper()))
        skipped_relations_no_cat.add((t_schema.upper(), t_name.upper()))
      else:
        included_relations.add(
            (t_cat.upper(), t_schema.upper(), t_name.upper())
        )
        included_relations_no_cat.add((t_schema.upper(), t_name.upper()))

    # Columns per (catalog, schema, table) & DataType distribution
    col_count_by_table: collections.Counter[tuple[str, str, str]] = (
        collections.Counter()
    )
    col_count_by_table_no_cat: collections.Counter[tuple[str, str]] = (
        collections.Counter()
    )
    dtype_counter: collections.Counter[str] = collections.Counter()
    filtered_col_count = 0
    for c in col_rows:
      c_cat = _get_field(c, "TableCatalog", "table_catalog")
      c_schema = _get_field(
          c, "TableSchema", "table_schema", "DatabaseName", "DataBaseName"
      )
      c_table = _get_field(c, "TableName", "table_name")
      if not c_schema or not _should_include_schema(c_schema):
        continue
      c_key3 = (c_cat.upper(), c_schema.upper(), c_table.upper())
      c_key2 = (c_schema.upper(), c_table.upper())
      if c_key3 in skipped_relations or (
          c_key3 not in included_relations
          and c_key2 in skipped_relations_no_cat
          and (not c_cat or c_key2 not in included_relations_no_cat)
      ):
        continue
      filtered_col_count += 1
      if c_table:
        col_count_by_table[c_key3] += 1
        col_count_by_table_no_cat[c_key2] += 1
      dtype = _get_field(c, "DataType", "data_type", "ColumnType") or "UNKNOWN"
      if dtype:
        dtype_counter[dtype.upper()] += 1

    def _get_col_count(cat: str, schema: str, name: str) -> int:
      exact = col_count_by_table.get(
          (cat.upper(), schema.upper(), name.upper())
      )
      if exact is not None:
        return exact
      if not cat:
        return col_count_by_table_no_cat.get((schema.upper(), name.upper()), 0)
      return col_count_by_table.get(("", schema.upper(), name.upper()), 0)

    # Tables & Views breakdown
    base_tables: list[dict[str, Any]] = []
    views_from_tables_csv: dict[tuple[str, str, str], dict[str, Any]] = {}
    td_extra_functions = 0

    for t in table_rows:
      t_cat = _get_field(t, "TableCatalog", "table_catalog")
      t_schema = _get_field(
          t, "TableSchema", "table_schema", "DataBaseName", "DatabaseName"
      )
      t_name = _get_field(t, "TableName", "table_name")
      t_type = _get_field(t, "TableType", "table_type").upper()
      t_kind = _get_field(t, "TableKind", "table_kind").upper()
      if not t_name or not t_schema or not _should_include_schema(t_schema):
        continue

      # Teradata TableKind classification ('T'/'O' = Table, 'V' = View)
      if t_kind and not t_type:
        if t_kind in ("T", "O"):
          t_type = "BASE TABLE"
        elif t_kind == "V":
          t_type = "VIEW"
        elif t_kind in ("F", "U", "P", "E", "M"):
          td_extra_functions += 1
          continue
        else:
          continue

      if any(k in t_type for k in ("EXTERNAL", "TEMPORARY", "EVENT")):
        continue
      if t_type and "VIEW" not in t_type and "TABLE" not in t_type:
        continue

      s_entry = _ensure_schema_entry(t_schema)
      key3 = (t_cat.upper(), t_schema.upper(), t_name.upper())
      key2 = (t_schema.upper(), t_name.upper())

      if "VIEW" in t_type:
        req_ddl = _get_field(t, "ViewDefinition", "RequestText")
        views_from_tables_csv[key3] = {
            "catalog": t_cat,
            "schema": t_schema,
            "view": t_name,
            "full_name": f"{t_schema}.{t_name}",
            "column_count": _get_col_count(t_cat, t_schema, t_name),
            "has_ddl": bool(req_ddl),
        }
      else:
        rs_meta = rs_info_map.get(key3) or rs_info_map.get(
            ("", t_schema.upper(), t_name.upper()), {}
        )
        row_cnt = _safe_int(_get_field(t, "RowCount", "row_count"))
        if not row_cnt and rs_meta:
          row_cnt = rs_meta.get("row_count", 0)

        byte_cnt = _safe_int(_get_field(t, "Bytes", "bytes"))
        if not byte_cnt and rs_meta:
          byte_cnt = rs_meta.get("bytes", 0)
        if not byte_cnt and key2 in td_size_map:
          byte_cnt = td_size_map[key2]

        cluster_key = _get_field(t, "ClusteringKey", "clustering_key")
        if not cluster_key and rs_meta:
          cluster_key = rs_meta.get("clustering_key", "")

        col_cnt = _get_col_count(t_cat, t_schema, t_name)
        base_tables.append({
            "catalog": t_cat or rs_meta.get("catalog", ""),
            "schema": t_schema,
            "table": t_name,
            "full_name": f"{t_schema}.{t_name}",
            "row_count": row_cnt,
            "bytes": byte_cnt,
            "bytes_formatted": format_bytes(byte_cnt),
            "column_count": col_cnt,
            "clustering_key": cluster_key,
        })
        s_entry["base_tables"] += 1
        s_entry["rows"] += row_cnt
        s_entry["bytes"] += byte_cnt

    # Views from views-au.csv merged with VIEW rows from tables CSV
    views_list: list[dict[str, Any]] = []
    seen_views: set[tuple[str, str, str]] = set()
    seen_views_no_cat: set[tuple[str, str]] = set()
    for v in view_rows:
      v_cat = _get_field(v, "TableCatalog", "table_catalog")
      v_schema = _get_field(v, "TableSchema", "table_schema")
      v_name = _get_field(v, "TableName", "table_name")
      v_ddl = _get_field(v, "ViewDefinition", "view_definition")
      if not v_name or not v_schema or not _should_include_schema(v_schema):
        continue
      key3 = (v_cat.upper(), v_schema.upper(), v_name.upper())
      if key3 in seen_views:
        continue
      seen_views.add(key3)
      seen_views_no_cat.add((v_schema.upper(), v_name.upper()))
      s_entry = _ensure_schema_entry(v_schema)
      s_entry["views"] += 1
      views_list.append({
          "catalog": v_cat,
          "schema": v_schema,
          "view": v_name,
          "full_name": f"{v_schema}.{v_name}",
          "column_count": _get_col_count(v_cat, v_schema, v_name),
          "has_ddl": bool(v_ddl),
      })

    # Include any views from tables CSV that were not in views-au.csv
    for key3, v_entry in sorted(views_from_tables_csv.items()):
      cat_u, sch_u, name_u = key3
      already_seen = (
          key3 in seen_views
          or ("", sch_u, name_u) in seen_views
          or (not cat_u and (sch_u, name_u) in seen_views_no_cat)
      )
      if not already_seen:
        seen_views.add(key3)
        seen_views_no_cat.add((sch_u, name_u))
        s_entry = _ensure_schema_entry(v_entry["schema"])
        s_entry["views"] += 1
        views_list.append(v_entry)

    # Sort base tables by row_count descending, then bytes descending, then name
    base_tables.sort(
        key=lambda x: (-x["row_count"], -x["bytes"], x["full_name"])
    )
    views_list.sort(key=lambda x: x["full_name"])

    for s_entry in per_schema.values():
      s_entry["bytes_formatted"] = format_bytes(s_entry["bytes"])

    schema_breakdown = sorted(
        per_schema.values(),
        key=lambda s: (
            -(s["base_tables"] + s["views"]),
            -s["rows"],
            s["schema"],
        ),
    )
    active_schemas = [
        s for s in schema_breakdown if s["base_tables"] > 0 or s["views"] > 0
    ]

    total_rows = sum(t["row_count"] for t in base_tables)
    total_bytes = sum(t["bytes"] for t in base_tables)
    base_table_cols = sum(t["column_count"] for t in base_tables)
    view_cols = sum(v["column_count"] for v in views_list)
    views_with_ddl = sum(1 for v in views_list if v.get("has_ddl"))

    filtered_funcs = [
        fn_r
        for fn_r in func_rows
        if _should_include_schema(
            _get_field(
                fn_r,
                "FunctionSchema",
                "function_schema",
                "SchemaName",
                "DatabaseName",
                "Schema",
            )
        )
    ]
    filtered_exts = [
        ex_r
        for ex_r in ext_rows
        if _should_include_schema(
            _get_field(ex_r, "SchemaName", "schemaname", "table_schema")
        )
    ]

    sorted_dtypes = dict(
        sorted(dtype_counter.items(), key=lambda kv: (-kv[1], kv[0]))
    )
    special_dtypes = _classify_special_data_types(sorted_dtypes)

    normalized_schemas = sorted(s["schema"] for s in per_schema.values())
    stats["schemas"] = normalized_schemas
    stats["counts"] = {
        "databases": len(db_names),
        "schemas": len(normalized_schemas),
        "active_schemas": len(active_schemas),
        "base_tables": len(base_tables),
        "views": len(views_list),
        "views_with_ddl": views_with_ddl,
        "columns": filtered_col_count,
        "base_table_columns": base_table_cols,
        "view_columns": view_cols,
        "functions": len(filtered_funcs) + td_extra_functions,
        "external_tables": len(filtered_exts),
        "query_log_files": len(query_log_files),
        "query_log_entries": query_log_entries,
    }
    stats["volume"] = {
        "total_base_rows": total_rows,
        "total_base_bytes": total_bytes,
        "total_base_bytes_formatted": format_bytes(total_bytes),
        "available": has_volume_stats,
    }
    stats["schema_breakdown"] = schema_breakdown
    stats["base_tables"] = base_tables
    stats["views"] = views_list
    stats["data_type_distribution"] = sorted_dtypes
    stats["special_data_types"] = special_dtypes

  return stats


# ==============================================================================
# 4. Report Formatting & Output Channels (CUSTOMIZE)
# ==============================================================================


# CUSTOMIZE: Report Formatting & Output Channels
def format_stats_report(
    archive_stats_list: list[dict[str, Any]], top_tables: int = 25
) -> str:
  """Formats extracted archive statistics into a Markdown/console report.

  Customize this function to alter table columns, add downstream migration
  cost/complexity estimates, or adjust summary sections.

  Args:
    archive_stats_list: List of archive statistic dicts from
      `analyze_zip_archive()`.
    top_tables: Maximum number of base tables to list in the detailed table.

  Returns:
    Formatted multi-line Markdown report string.
  """
  lines: list[str] = []
  lines.append("=" * 80)
  lines.append("  BIGQUERY MIGRATION CLOUD EXTRACTOR - EXTRACTION REPORT")
  lines.append("=" * 80)

  for idx, st in enumerate(archive_stats_list, start=1):
    if idx > 1:
      lines.append("\n" + "-" * 80)
    lines.append(f"\n### Archive {idx}: `{st['archive_name']}`")
    lines.append(f"- **Archive Path / URI**: `{st['archive_path']}`")
    lines.append(f"- **Archive Validation**: {st['validation_message']}")

    if not st["is_valid_archive"]:
      continue

    tel = st.get("telemetry", {})
    connector = tel.get("connector") or tel.get("format") or "unknown"
    host = tel.get("host") or "N/A"
    warehouse = tel.get("warehouse") or "N/A"
    wh_cnt = tel.get("warehouse_count")
    wh_suffix = f" (total warehouses in account: {wh_cnt})" if wh_cnt else ""
    status = tel.get("overall_status") or "SUCCESS"
    dumper_ver = tel.get("dumper_version") or "N/A"
    start_time = tel.get("run_start_time") or "N/A"

    lines.append(f"- **Archive Type**: `{st['archive_type']}`")
    lines.append(
        f"- **Extractor Run Status**: `{status}` "
        f"(Tasks: {tel.get('tasks_succeeded', 0)} succeeded, "
        f"{tel.get('tasks_skipped', 0)} skipped, "
        f"{tel.get('tasks_failed', 0)} failed | Version: {dumper_ver})"
    )
    lines.append(f"- **Source Connector & Host**: `{connector}` (`{host}`)")
    lines.append(f"- **Compute Warehouse**: `{warehouse}`{wh_suffix}")
    lines.append(f"- **Extraction Timestamp**: `{start_time}`")

    cnt = st["counts"]
    vol = st["volume"]
    db_str = ", ".join(f"`{d}`" for d in st["databases"]) or "None"
    schema_str = ", ".join(f"`{s}`" for s in st["schemas"]) or "None"
    base_cols = cnt.get("base_table_columns", 0)
    view_cols = cnt.get("view_columns", 0)
    col_detail = (
        f"{base_cols:,} in base tables, {view_cols:,} in views; "
        f"{len(st['data_type_distribution'])} distinct data types"
    )
    views_total = cnt["views"]
    views_ddl = cnt.get("views_with_ddl", views_total)
    views_val = (
        f"{views_ddl} (of {views_total} total)"
        if views_ddl != views_total
        else f"{views_ddl}"
    )

    lines.append("\n#### 1. Crucial Extracted Object Summary")
    lines.append("| Metric | Count / Value | Details |")
    lines.append("| :--- | :--- | :--- |")
    lines.append(f"| **Databases** | {cnt['databases']} | {db_str} |")
    lines.append(
        f"| **Schemas** | {cnt['schemas']} "
        f"({cnt['active_schemas']} with objects) | {schema_str} |"
    )
    has_volume = vol.get("available", True)
    if has_volume:
      base_detail = (
          f"Total Rows: **{vol['total_base_rows']:,}** "
          f"({vol['total_base_bytes_formatted']})"
      )
    else:
      base_detail = "Rows and sizes are not recorded by this connector"
    lines.append(f"| **Base Tables** | {cnt['base_tables']} | {base_detail} |")
    lines.append(
        f"| **Views (with DDL)** | {views_val} | "
        "Ready for BQMS SQL translation |"
    )
    lines.append(f"| **Total Columns** | {cnt['columns']:,} | {col_detail} |")
    lines.append(
        f"| **Functions / Procedures** | {cnt['functions']} | "
        "UDFs and stored procedures |"
    )
    lines.append(
        f"| **External Tables** | {cnt['external_tables']} | "
        "External stage tables |"
    )
    if cnt["query_log_files"] > 0:
      lines.append(
          f"| **Query History Logs** | {cnt['query_log_entries']:,} queries | "
          f"Across {cnt['query_log_files']} log partition file(s) |"
      )

    if st["schema_breakdown"]:
      lines.append("\n#### 2. Per-Schema Object Breakdown")
      lines.append(
          "| Schema | Base Tables | Views | Total Base Rows | Total Base Size |"
      )
      lines.append("| :--- | ---: | ---: | ---: | ---: |")
      for sb in st["schema_breakdown"]:
        sb_rows = f"{sb['rows']:,}" if has_volume else "N/A"
        sb_size = sb["bytes_formatted"] if has_volume else "N/A"
        lines.append(
            f"| `{sb['schema']}` | {sb['base_tables']} | {sb['views']} | "
            f"{sb_rows} | {sb_size} |"
        )

    if st["base_tables"]:
      shown = st["base_tables"][:top_tables]
      lines.append(
          "\n#### 3. Base Tables Inventory "
          f"(Showing {len(shown)} of {len(st['base_tables'])})"
      )
      lines.append(
          "| # | Schema.Table | Rows | Size | Columns | Clustering Key |"
      )
      lines.append("| ---: | :--- | ---: | ---: | ---: | :--- |")
      for i, tb in enumerate(shown, start=1):
        ckey = f"`{tb['clustering_key']}`" if tb["clustering_key"] else "-"
        tb_rows = f"{tb['row_count']:,}" if has_volume else "N/A"
        tb_size = tb["bytes_formatted"] if has_volume else "N/A"
        lines.append(
            f"| {i} | `{tb['full_name']}` | {tb_rows} | "
            f"{tb_size} | {tb['column_count']} | {ckey} |"
        )

    if st["views"]:
      lines.append(f"\n#### 4. Extracted Views Inventory ({len(st['views'])})")
      view_names = [f"`{v['full_name']}`" for v in st["views"]]
      lines.append(", ".join(view_names[:40]))
      if len(view_names) > 40:
        lines.append(f"... and {len(view_names) - 40} more view(s).")

    if st["data_type_distribution"]:
      lines.append("\n#### 5. Column Data Type Distribution")
      dtype_items = [
          f"`{dt}`: {c:,}" for dt, c in st["data_type_distribution"].items()
      ]
      lines.append("- **All Data Types**: " + ", ".join(dtype_items))
      if st["special_data_types"]:
        spec_items = [
            f"`{dt}` ({c:,})" for dt, c in st["special_data_types"].items()
        ]
        lines.append(
            "- **Types Flagged for Type-Safe Parquet Cast / Translation**: "
            + ", ".join(spec_items)
        )

  lines.append("\n" + "=" * 80)
  return "\n".join(lines)


# ==============================================================================
# 5. CLI Entrypoint & Orchestration (DEFAULT SCAFFOLDING)
# ==============================================================================
# DEFAULT SCAFFOLDING: Command-line parsing and exit-code management.


def main(argv: list[str] | None = None) -> int:
  """Main CLI entrypoint for inspecting Cloud Extractor ZIP archives."""
  parser = argparse.ArgumentParser(
      description=(
          "Inspects BigQuery Migration Cloud Extractor ZIP archives and "
          "prints crucial catalog and volume statistics."
      )
  )
  parser.add_argument(
      "--input",
      required=True,
      help=(
          "Path to a local .zip archive, local directory containing .zip "
          "archives, or a GCS URI (e.g. gs://bucket/snowflake_metadata/)."
      ),
  )
  parser.add_argument(
      "--top-tables",
      type=int,
      default=25,
      help="Maximum number of base tables to print in detail (default: 25).",
  )
  parser.add_argument(
      "--output-json",
      default="",
      help="Optional path to write structured JSON statistics.",
  )
  parser.add_argument(
      "--output-markdown",
      default="",
      help="Optional path to write the formatted Markdown summary report.",
  )
  args = parser.parse_args(argv)

  zip_sources = discover_zip_sources(args.input)
  all_stats: list[dict[str, Any]] = []
  has_invalid = False

  for src in zip_sources:
    raw_bytes = read_zip_bytes(src)
    st = analyze_zip_archive(src, raw_bytes)
    if not st["is_valid_archive"]:
      has_invalid = True
    all_stats.append(st)

  report_text = format_stats_report(all_stats, top_tables=args.top_tables)
  print(report_text)

  if args.output_json:
    with open(args.output_json, "w", encoding="utf-8") as jf:
      json.dump({"archives": all_stats}, jf, indent=2)
    print(f"\n[INFO] Wrote JSON extraction statistics to: {args.output_json}")

  if args.output_markdown:
    with open(args.output_markdown, "w", encoding="utf-8") as mf:
      mf.write(report_text + "\n")
    print(f"[INFO] Wrote Markdown extraction report to: {args.output_markdown}")

  return 1 if has_invalid else 0


if __name__ == "__main__":
  sys.exit(main())
