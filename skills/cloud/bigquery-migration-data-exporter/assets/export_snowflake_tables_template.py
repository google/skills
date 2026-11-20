#!/usr/bin/env python3
r"""Template Script for Generating Type-Safe Snowflake COPY INTO Export SQL Files.

This asset template script provides a reference implementation for generating
type-safe Snowflake SQL export scripts (.sql) directly from BQMS
translation_output/metadata configs or metadata.zip archives. It has zero JDBC
or database connector dependencies.

Usage Pattern:
  Copy `assets/export_snowflake_tables_template.py` from this skill's directory
  (`<SKILL_DIR>`, the directory containing `SKILL.md`) into your
  working directory (for example, `./export_snowflake_tables.py`). Run the copy
  as-is for standard export SQL generation, and prioritize modifying the marked
  `# CUSTOMIZE:` extension points if your environment requires custom type
  projections, stage options, or table filtering. Sections marked
  `# DEFAULT SCAFFOLDING` can be kept unchanged unless deeper orchestration
  adjustments are needed.

Dependencies:
  pip install pyyaml==6.0.2

Usage Examples:
    # Copy the template from this skill's directory to your working directory:
    cp <SKILL_DIR>/assets/export_snowflake_tables_template.py \
        ./export_snowflake_tables.py

    # 1. Generate a unified Snowflake COPY INTO SQL file that unloads to Cloud
    #    Storage (Snowflake requires a storage integration for gcs:// URLs):
    python3 ./export_snowflake_tables.py \
        --translation-metadata-dir gs://my-bucket/translation_output/metadata/ \
        --stage-path 'gcs://my-bucket/data_unload/' \
        --storage-integration my_gcs_integration \
        --output-sql snowflake_export.sql

    # 2. Generate per-table Snowflake COPY INTO SQL files in a directory:
    python3 ./export_snowflake_tables.py \
        --translation-metadata-dir ./translated_output/metadata \
        --stage-path '@~/bqms_export/' \
        --output-dir ./export_sql
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

import yaml


# ==============================================================================
# 1. File & Metadata Loading Functions (DEFAULT SCAFFOLDING)
# ==============================================================================
# DEFAULT SCAFFOLDING: Deterministic metadata loading and archive parsing.


def read_file_or_gcs(path_or_uri: str) -> bytes:
  """Reads content from a local file path or a Cloud Storage URI.

  Args:
    path_or_uri: Local file path or Cloud Storage URI (starts with 'gs://').

  Returns:
    The content of the file as bytes.

  Raises:
    FileNotFoundError: If the local file does not exist.
    RuntimeError: If gcloud storage fails to read from Cloud Storage.
  """
  if path_or_uri.startswith("gs://"):
    cmd = ["gcloud", "storage", "cat", path_or_uri]
    try:
      return subprocess.check_output(cmd)
    except subprocess.CalledProcessError as e:
      raise RuntimeError(
          f"Failed to read from Cloud Storage '{path_or_uri}': {e}"
      ) from e
    except FileNotFoundError as e:
      raise RuntimeError(
          f"Cannot read '{path_or_uri}': the gcloud CLI was not found. Install"
          " the Google Cloud CLI, or download the file and pass a local path."
      ) from e
  else:
    if not os.path.exists(path_or_uri):
      raise FileNotFoundError(f"Local file not found: '{path_or_uri}'")
    with open(path_or_uri, "rb") as f:
      return f.read()


def _run_gcloud_copy(cmd: list[str], uri: str) -> None:
  """Runs a `gcloud storage cp` command, surfacing its stderr on failure."""
  try:
    subprocess.run(cmd, capture_output=True, check=True)
  except FileNotFoundError as e:
    raise RuntimeError(
        f"Cannot copy '{uri}': the gcloud CLI was not found. Install the"
        " Google Cloud CLI, or copy the files locally and pass a local path."
    ) from e
  except subprocess.CalledProcessError as e:
    stderr = (e.stderr or b"").decode("utf-8", errors="replace").strip()
    raise RuntimeError(
        f"Failed to copy from Cloud Storage '{uri}' (exit code"
        f" {e.returncode}): {stderr or e}"
    ) from e


def load_metadata_from_zip(
    zip_bytes: bytes,
) -> dict[str, list[dict[str, str]]]:
  """Extracts table and column metadata from a metadata.zip archive.

  Reads tables-au.csv (or tables.csv) and columns-au.csv (or columns.csv)
  contained within the zipped metadata payload.

  Args:
    zip_bytes: Raw bytes of the metadata zip archive.

  Returns:
    A dictionary containing 'tables' and 'columns' lists of records.
  """
  result: dict[str, list[dict[str, str]]] = {"tables": [], "columns": []}

  with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
    by_base = {os.path.basename(n).lower(): n for n in z.namelist()}
    for key, candidates in (
        ("tables", ("tables-au.csv", "tables.csv")),
        ("columns", ("columns-au.csv", "columns.csv")),
    ):
      member = next((by_base[c] for c in candidates if c in by_base), None)
      if member:
        with z.open(member) as fh:
          reader = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig"))
          result[key] = list(reader)

  return result


def _str_or_empty(value: object) -> str:
  """Converts a metadata value to a stripped string, mapping None to ''."""
  return "" if value is None else str(value).strip()


def load_metadata_from_config_dir(
    config_dir: str,
) -> dict[str, list[dict[str, str]]]:
  """Loads table/column metadata from BQMS metadata/config/*.yaml files.

  Args:
    config_dir: Local path to the BQMS metadata config directory.

  Returns:
    A dictionary containing 'tables' and 'columns' metadata parsed from YAMLs.
  """
  result: dict[str, list[dict[str, str]]] = {"tables": [], "columns": []}
  if not os.path.isdir(config_dir):
    return result

  for root, _, files in os.walk(config_dir):
    for f in sorted(files):
      if f.endswith(".yaml") or f.endswith(".yml"):
        fpath = os.path.join(root, f)
        try:
          with open(fpath, "r", encoding="utf-8") as yf:
            cfg = yaml.safe_load(yf)
        except (yaml.YAMLError, OSError):
          continue

        if not isinstance(cfg, dict):
          continue

        src_name = cfg.get("sourceName", "")
        parts = src_name.split(".") if src_name else []
        db = parts[0] if len(parts) > 2 else ""
        # BQMS writes __DEFAULT_DATABASE__ when the source database is unknown;
        # leave it empty so --default-database or the session database applies.
        if db == "__DEFAULT_DATABASE__":
          db = ""
        schema = (
            parts[1] if len(parts) > 2 else (parts[0] if len(parts) > 1 else "")
        )
        table = parts[-1] if parts else f.rsplit(".", 1)[0].upper()

        is_view = not bool(
            cfg.get("externalTableName") or cfg.get("externalTableDdlPath")
        )
        result["tables"].append({
            "TableCatalog": db,
            "TableSchema": schema,
            "TableName": table,
            "TableType": "VIEW" if is_view else "BASE TABLE",
        })

        for idx, col in enumerate(cfg.get("columns") or [], start=1):
          if not isinstance(col, dict):
            continue
          col_name = col.get("sourceName", "")
          # `sourceType: null` / `targetType: null` load as None; treat them
          # as empty instead of the literal string "None".
          src_type = col.get("sourceType") or {}
          tgt_type = col.get("targetType") or {}
          src = src_type if isinstance(src_type, dict) else {}
          tgt = tgt_type if isinstance(tgt_type, dict) else {}

          # Prefer the raw Snowflake type (`name`, such as TIMESTAMP_LTZ or
          # VARIANT) over the BQMS genericName (TIMESTAMPTZ or JSON), which
          # drops the time zone kind.
          gen_name = (
              str(src.get("name") or src.get("genericName") or "VARCHAR")
              if isinstance(src_type, dict)
              else str(src_type)
          )
          precision = _str_or_empty(src.get("precision"))
          scale = _str_or_empty(src.get("scale"))

          tgt_name = (
              _str_or_empty(tgt.get("name"))
              if isinstance(tgt_type, dict)
              else str(tgt_type)
          )

          result["columns"].append({
              "TableCatalog": db,
              "TableSchema": schema,
              "TableName": table,
              "ColumnName": col_name,
              "OrdinalPosition": str(idx),
              "DataType": gen_name,
              "NumericPrecision": precision,
              "NumericScale": scale,
              "TargetType": tgt_name,
          })

  return result


def _find_config_dir(dir_path: str) -> str | None:
  """Locates the directory containing BQMS table YAML configurations."""
  metadata_config = os.path.join(dir_path, "metadata", "config")
  if os.path.isdir(metadata_config):
    return metadata_config

  plain_config = os.path.join(dir_path, "config")
  if os.path.isdir(plain_config):
    return plain_config

  for _, _, files in os.walk(dir_path):
    for f in files:
      if f.endswith(".yaml") or f.endswith(".yml"):
        return dir_path

  return None


def load_metadata_from_dir(dir_path: str) -> dict[str, list[dict[str, str]]]:
  """Discovers and extracts metadata from a directory or embedded zip archive.

  Scans for BQMS YAML configuration directories ('metadata/config' or 'config')
  and falls back to any embedded metadata zip archives if no YAML files are
  found.

  Args:
    dir_path: Local filesystem path to inspect.

  Returns:
    A dictionary containing 'tables' and 'columns' lists of records.
  """
  config_dir = _find_config_dir(dir_path)
  if config_dir:
    res = load_metadata_from_config_dir(config_dir)
    if res["tables"] and res["columns"]:
      return res

  for root, _, files in os.walk(dir_path):
    for f in files:
      if f.endswith(".zip") and "metadata" in f:
        with open(os.path.join(root, f), "rb") as zf:
          return load_metadata_from_zip(zf.read())

  return {"tables": [], "columns": []}


def _resolve_and_load_metadata(
    path_or_uri: str | None,
) -> dict[str, list[dict[str, str]]]:
  """Resolves local or Cloud Storage metadata and loads metadata dicts."""
  if not path_or_uri:
    return {"tables": [], "columns": []}

  if path_or_uri.startswith("gs://"):
    if path_or_uri.endswith(".zip"):
      zip_bytes = read_file_or_gcs(path_or_uri)
      return load_metadata_from_zip(zip_bytes)
    temp_dir = tempfile.mkdtemp(prefix="bqms_meta_")
    try:
      cmd = [
          "gcloud",
          "storage",
          "cp",
          "-r",
          path_or_uri.rstrip("/") + "/*",
          temp_dir,
      ]
      _run_gcloud_copy(cmd, path_or_uri)
      return load_metadata_from_dir(temp_dir)
    finally:
      shutil.rmtree(temp_dir, ignore_errors=True)
  elif os.path.isdir(path_or_uri):
    return load_metadata_from_dir(path_or_uri)
  else:
    zip_bytes = read_file_or_gcs(path_or_uri)
    return load_metadata_from_zip(zip_bytes)


def _table_key(meta: dict[str, str]) -> tuple[str, str, str]:
  """Returns the upper-cased (database, schema, table) key for a record."""
  return (
      _str_or_empty(meta.get("TableCatalog")).upper(),
      _str_or_empty(meta.get("TableSchema")).upper(),
      _str_or_empty(meta.get("TableName")).upper(),
  )


def _group_and_sort_columns(
    columns: list[dict[str, str]],
) -> tuple[
    dict[tuple[str, str, str], list[dict[str, str]]],
    dict[str, list[dict[str, str]]],
]:
  """Groups columns by (database, schema, table) and by table name, sorted."""
  columns_by_qualified_table: dict[
      tuple[str, str, str], list[dict[str, str]]
  ] = {}
  columns_by_table: dict[str, list[dict[str, str]]] = {}

  for col in columns:
    columns_by_qualified_table.setdefault(_table_key(col), []).append(col)

  for (_, _, tbl), cols in columns_by_qualified_table.items():
    cols.sort(
        key=lambda x: (
            int(x.get("OrdinalPosition", "0"))
            if x.get("OrdinalPosition", "").isdigit()
            else 9999
        )
    )
    if tbl not in columns_by_table:
      columns_by_table[tbl] = cols

  return columns_by_qualified_table, columns_by_table


def _lookup_table_columns(
    table_key: tuple[str, str, str],
    columns_by_qualified_table: dict[
        tuple[str, str, str], list[dict[str, str]]
    ],
    resolved_key: tuple[str, str, str] | None = None,
) -> list[dict[str, str]]:
  """Finds a table's columns by (database, schema, table), then looser keys.

  Args:
    table_key: Upper-cased (database, schema, table) key as written in the table
      metadata.
    columns_by_qualified_table: Columns grouped by upper-cased key.
    resolved_key: Optional key with --default-database / --default-schema filled
      in, matching the FROM clause.

  Returns:
    The matching columns, or an empty list (SELECT *) when no single match.
  """
  for key in (table_key, resolved_key):
    if key and columns_by_qualified_table.get(key):
      return columns_by_qualified_table[key]
  db_name, schema_name, tbl_name = resolved_key or table_key
  # Fall back to a looser match only when one side omits the database or
  # schema name, and only when exactly one table matches. Never borrow columns
  # from a same-named table in a different database or schema.
  matches = [
      cand
      for (
          col_db,
          col_schema,
          col_tbl,
      ), cand in columns_by_qualified_table.items()
      if cand
      and col_tbl == tbl_name
      and (col_schema == schema_name or not col_schema or not schema_name)
      and (col_db == db_name or not col_db or not db_name)
  ]
  return matches[0] if len(matches) == 1 else []


# CUSTOMIZE: Table & Row Filtering — Edit _filter_tables_to_export() to add
# custom schema/table inclusion or exclusion rules.
def _resolved_table_key(
    meta: dict[str, str],
    default_database: str | None = None,
    default_schema: str | None = None,
) -> tuple[str, str, str]:
  """Returns the table key with the CLI database and schema defaults applied."""
  db_name, schema_name, tbl_name = _table_key(meta)
  return (
      db_name or _str_or_empty(default_database).upper(),
      schema_name or _str_or_empty(default_schema).upper(),
      tbl_name,
  )


def _filter_tables_to_export(
    raw_tables: list[dict[str, str]],
    columns_by_table: dict[str, list[dict[str, str]]],
    columns_by_qualified_table: (
        dict[tuple[str, str, str], list[dict[str, str]]] | None
    ) = None,
    default_database: str | None = None,
    default_schema: str | None = None,
) -> list[dict[str, str]]:
  """Drops views and deduplicates tables by (database, schema, table)."""
  tables_to_export: list[dict[str, str]] = []
  seen_exported_tables: set[tuple[str, str, str]] = set()

  if raw_tables:
    for t in raw_tables:
      table_key = _resolved_table_key(t, default_database, default_schema)
      tbl_type = t.get("TableType", "").upper()
      if tbl_type and "VIEW" in tbl_type:
        continue
      if table_key in seen_exported_tables:
        continue
      seen_exported_tables.add(table_key)
      tables_to_export.append(t)
  elif columns_by_qualified_table:
    # No table list (for example, columns.csv without tables.csv): keep every
    # (database, schema, table) group, with the names as written in metadata.
    for cols in columns_by_qualified_table.values():
      if not cols:
        continue
      entry = {"TableName": _str_or_empty(cols[0].get("TableName"))}
      for field in ("TableCatalog", "TableSchema"):
        if _str_or_empty(cols[0].get(field)):
          entry[field] = _str_or_empty(cols[0].get(field))
      tables_to_export.append(entry)
  else:
    candidate_tables = list(columns_by_table.keys()) if columns_by_table else []
    for tbl_name in candidate_tables:
      if ("", "", tbl_name) in seen_exported_tables:
        continue
      seen_exported_tables.add(("", "", tbl_name))
      tables_to_export.append({"TableName": tbl_name})

  return tables_to_export


# ==============================================================================
# 2. Type-Safe SQL Generation Logic
# ==============================================================================

_VALID_IDENT_REGEX = re.compile(r"^[A-Z_][A-Z0-9_$]*$")
_PARAM_TYPE_REGEX = re.compile(
    r"^(?P<base>[A-Z_]+)\s*\(\s*(?P<p>\d+)(?:\s*,\s*(?P<s>\d+))?\s*\)$"
)
_DATETIME_PREFIXES = ("DATETIME", "TIMESTAMP")
_INT_TYPES = frozenset(
    ("INT", "INTEGER", "BIGINT", "SMALLINT", "TINYINT", "BYTEINT")
)
_INT_TARGET_TYPES = frozenset(
    ("INT64", "INT", "INTEGER", "BIGINT", "SMALLINT", "TINYINT", "BYTEINT")
)
_FLOAT_TYPES = frozenset(
    ("FLOAT", "FLOAT4", "FLOAT8", "DOUBLE", "DOUBLE PRECISION", "REAL")
)
_TIMESTAMP_PREFIXES = (
    "TIMESTAMP",
    "TIMESTAMP_LTZ",
    "TIMESTAMP_TZ",
    "TIMESTAMP_NTZ",
    "DATETIME",
)
_BOOLEAN_TYPES = frozenset(("BOOLEAN", "BOOL"))
_BINARY_TYPES = frozenset(("BINARY", "VARBINARY", "BYTES"))
_VARIANT_TYPES = frozenset(("VARIANT", "OBJECT", "ARRAY", "JSON"))
# Time zone-aware spellings (including the BQMS genericName TIMESTAMPTZ) that
# are converted to UTC before the TIMESTAMP_NTZ cast.
_TZ_TIMESTAMP_ALIASES = {
    "TIMESTAMPTZ": "TIMESTAMP_TZ",
    "TIMESTAMP WITH TIME ZONE": "TIMESTAMP_TZ",
    "TIMESTAMPLTZ": "TIMESTAMP_LTZ",
    "TIMESTAMP WITH LOCAL TIME ZONE": "TIMESTAMP_LTZ",
}
_NUMBER_TYPES = frozenset(("NUMBER", "DECIMAL", "NUMERIC"))
# Snowflake reserved keywords; upper-case identifiers matching these are quoted:
# https://docs.snowflake.com/en/sql-reference/reserved-keywords
_SNOWFLAKE_RESERVED = frozenset((
    "ACCOUNT",
    "ALL",
    "ALTER",
    "AND",
    "ANY",
    "AS",
    "BETWEEN",
    "BY",
    "CASE",
    "CAST",
    "CHECK",
    "COLUMN",
    "CONNECT",
    "CONNECTION",
    "CONSTRAINT",
    "CREATE",
    "CROSS",
    "CURRENT",
    "CURRENT_DATE",
    "CURRENT_TIME",
    "CURRENT_TIMESTAMP",
    "CURRENT_USER",
    "DATABASE",
    "DELETE",
    "DISTINCT",
    "DROP",
    "ELSE",
    "EXISTS",
    "FALSE",
    "FOLLOWING",
    "FOR",
    "FROM",
    "FULL",
    "GRANT",
    "GROUP",
    "GSCLUSTER",
    "HAVING",
    "ILIKE",
    "IN",
    "INCREMENT",
    "INNER",
    "INSERT",
    "INTERSECT",
    "INTO",
    "IS",
    "ISSUE",
    "JOIN",
    "LATERAL",
    "LEFT",
    "LIKE",
    "LOCALTIME",
    "LOCALTIMESTAMP",
    "MINUS",
    "NATURAL",
    "NOT",
    "NULL",
    "OF",
    "ON",
    "OR",
    "ORDER",
    "ORGANIZATION",
    "QUALIFY",
    "REGEXP",
    "REVOKE",
    "RIGHT",
    "RLIKE",
    "ROW",
    "ROWS",
    "SAMPLE",
    "SCHEMA",
    "SELECT",
    "SET",
    "SOME",
    "START",
    "TABLE",
    "TABLESAMPLE",
    "THEN",
    "TO",
    "TRIGGER",
    "TRUE",
    "TRY_CAST",
    "UNION",
    "UNIQUE",
    "UPDATE",
    "USING",
    "VALUES",
    "VIEW",
    "WHEN",
    "WHENEVER",
    "WHERE",
    "WINDOW",
    "WITH",
))


# DEFAULT SCAFFOLDING: Identifier quoting helper.
def quote_ident(ident: str) -> str:
  """Quotes an identifier with double quotes if needed for Snowflake.

  Identifiers starting with digits, containing lowercase or special characters,
  or matching reserved words are safely enclosed in double quotes.

  Args:
    ident: The raw SQL identifier string.

  Returns:
    The properly quoted or unquoted identifier.
  """
  if not ident:
    return ""
  if len(ident) >= 2 and ident.startswith('"') and ident.endswith('"'):
    # Already quoted: re-escape any bare inner double quotes.
    inner = ident[1:-1].replace('""', '"').replace('"', '""')
    return f'"{inner}"'
  if (
      ident[0].isdigit()
      or not _VALID_IDENT_REGEX.match(ident)
      or ident in _SNOWFLAKE_RESERVED
  ):
    escaped = ident.replace('"', '""')
    return f'"{escaped}"'
  return ident


def _to_int(value: object) -> int | None:
  """Parses a non-negative integer metadata value, preserving integer 0."""
  text = _str_or_empty(value)
  return int(text) if text.isdigit() else None


def _escape_sql_literal(value: str) -> str:
  """Escapes backslashes and single quotes for a Snowflake string literal."""
  return value.replace("\\", "\\\\").replace("'", "''")


def _sanitize_comment_token(value: str) -> str:
  """Replaces control characters so SQL line comments stay single-line."""
  return re.sub(r"[\x00-\x1f\x7f]+", " ", str(value)).strip()


# CUSTOMIZE: Custom Type Projections — Edit format_column_cast() to add custom
# data type mappings, precision bounds, or JSON/geography serialization formats.
def format_column_cast(
    col: dict[str, str], target_bq_type: str | None = None
) -> str:
  """Generates a type-safe Snowflake projection expression for Parquet export.

  Applies explicit type casting (for example, TO_VARCHAR for VARIANT/JSON,
  TIMESTAMP_NTZ(6) for timestamps, DECIMAL(p, s) for numerics) to guarantee
  zero type drift during downstream BigQuery ingestion.

  Args:
    col: Column metadata dictionary containing DataType, NumericPrecision, etc.
    target_bq_type: Optional target BigQuery type override.

  Returns:
    A SQL projection expression string, such as 'CAST(ID AS BIGINT) AS ID'.
  """
  col_raw = str(col.get("ColumnName") or "").strip()
  col_name = quote_ident(col_raw)
  raw_data_type = str(col.get("DataType") or "").upper().strip()
  precision = _to_int(col.get("NumericPrecision"))
  scale = _to_int(col.get("NumericScale"))

  param_match = _PARAM_TYPE_REGEX.match(raw_data_type)
  if param_match:
    data_type = param_match.group("base")
    if precision is None:
      precision = int(param_match.group("p"))
    if scale is None:
      if param_match.group("s") is not None:
        scale = int(param_match.group("s"))
      elif data_type in _NUMBER_TYPES:
        scale = 0
  else:
    data_type = re.split(r"[(\s]", raw_data_type, maxsplit=1)[0].strip()
  # TIMESTAMPTZ, TIMESTAMP(9) WITH LOCAL TIME ZONE, etc. keep the
  # CONVERT_TIMEZONE('UTC', ...) projection of TIMESTAMP_TZ / TIMESTAMP_LTZ.
  tz_key = " ".join(re.sub(r"\(\s*\d+\s*\)", " ", raw_data_type).split())
  data_type = _TZ_TIMESTAMP_ALIASES.get(tz_key, data_type)

  target = target_bq_type or col.get("TargetType")

  if target:
    tgt = target.upper().strip()
    tgt_base = re.split(r"[(<]", tgt, maxsplit=1)[0].strip()
    if any(tgt.startswith(p) for p in _DATETIME_PREFIXES):
      if data_type in ("TIMESTAMP_TZ", "TIMESTAMP_LTZ"):
        return (
            f"CAST(CONVERT_TIMEZONE('UTC', {col_name}) AS TIMESTAMP_NTZ(6))"
            f" AS {col_name}"
        )
      return f"CAST({col_name} AS TIMESTAMP_NTZ(6)) AS {col_name}"
    if tgt.startswith("JSON"):
      return f"TO_VARCHAR({col_name}) AS {col_name}"
    if tgt_base in _INT_TARGET_TYPES:
      return f"CAST({col_name} AS BIGINT) AS {col_name}"
    if tgt.startswith("FLOAT") or tgt.startswith("DOUBLE"):
      return f"CAST({col_name} AS DOUBLE) AS {col_name}"
    if tgt.startswith("BYTES"):
      return f"CAST({col_name} AS BINARY) AS {col_name}"
    if (
        tgt.startswith("NUMERIC")
        or tgt.startswith("BIGNUMERIC")
        or tgt.startswith("DECIMAL")
    ):
      # Snowflake DECIMAL(p, s) requires 1 <= p <= 38 and 0 <= s <= p.
      if precision is not None:
        p_val = min(max(precision, 1), 38)
      elif data_type in _INT_TYPES and not tgt.startswith("BIGNUMERIC"):
        # BigQuery NUMERIC (alias DECIMAL) holds at most 29 integer digits.
        p_val = 29
      else:
        p_val = 38
      if scale is not None:
        s_val = min(scale, p_val)
      elif data_type in _INT_TYPES:
        s_val = 0
      else:
        s_val = min(9, p_val)
      return f"CAST({col_name} AS DECIMAL({p_val}, {s_val})) AS {col_name}"
    if tgt.startswith("STRING"):
      if data_type in ("TIMESTAMP_TZ", "TIMESTAMP_LTZ"):
        # CONVERT_TIMEZONE returns TIMESTAMP_TZ, which uses the session's
        # TIMESTAMP_TZ_OUTPUT_FORMAT (FF6) set in the script header.
        return f"TO_VARCHAR(CONVERT_TIMEZONE('UTC', {col_name})) AS {col_name}"
      return f"TO_VARCHAR({col_name}) AS {col_name}"
    if tgt in _BOOLEAN_TYPES:
      return f"CAST({col_name} AS BOOLEAN) AS {col_name}"
    if tgt in ("DATE", "TIME"):
      cast_type = "DATE" if tgt == "DATE" else "TIME(6)"
      if data_type in ("TIMESTAMP_TZ", "TIMESTAMP_LTZ"):
        return (
            f"CAST(CONVERT_TIMEZONE('UTC', {col_name}) AS {cast_type})"
            f" AS {col_name}"
        )
      return f"CAST({col_name} AS {cast_type}) AS {col_name}"

  if data_type in _VARIANT_TYPES:
    return f"TO_VARCHAR({col_name}) AS {col_name}"

  if data_type in _INT_TYPES:
    return f"CAST({col_name} AS BIGINT) AS {col_name}"

  if data_type in _NUMBER_TYPES:
    p_val = (
        min(precision, 38) if precision is not None and precision > 0 else 38
    )
    if scale is None:
      # Cap the default fractional scale at the precision (DECIMAL(5, 9) is
      # invalid in Snowflake).
      s_val = min(9, p_val)
      return f"CAST({col_name} AS DECIMAL({p_val}, {s_val})) AS {col_name}"
    if scale == 0:
      if precision is not None and 1 <= precision <= 19:
        return f"CAST({col_name} AS BIGINT) AS {col_name}"
      return f"CAST({col_name} AS DECIMAL({p_val}, 0)) AS {col_name}"
    s_val = min(scale, p_val)
    return f"CAST({col_name} AS DECIMAL({p_val}, {s_val})) AS {col_name}"

  if data_type in _FLOAT_TYPES:
    return f"CAST({col_name} AS DOUBLE) AS {col_name}"

  if data_type in ("TIMESTAMP_TZ", "TIMESTAMP_LTZ"):
    return (
        f"CAST(CONVERT_TIMEZONE('UTC', {col_name}) AS TIMESTAMP_NTZ(6))"
        f" AS {col_name}"
    )

  if any(data_type.startswith(t) for t in _TIMESTAMP_PREFIXES):
    return f"CAST({col_name} AS TIMESTAMP_NTZ(6)) AS {col_name}"

  if data_type == "TIME":
    return f"CAST({col_name} AS TIME(6)) AS {col_name}"

  if data_type == "DATE":
    return f"CAST({col_name} AS DATE) AS {col_name}"

  if data_type in _BOOLEAN_TYPES:
    return f"CAST({col_name} AS BOOLEAN) AS {col_name}"

  # Keep BINARY/VARBINARY as raw bytes (Parquet BYTE_ARRAY -> BigQuery BYTES);
  # a VARCHAR cast would hex-encode values per BINARY_OUTPUT_FORMAT.
  if data_type in _BINARY_TYPES:
    return f"CAST({col_name} AS BINARY) AS {col_name}"

  return f"CAST({col_name} AS VARCHAR) AS {col_name}"


# DEFAULT SCAFFOLDING: Table name qualification helper.
def _build_qualified_table_name(
    table_meta: dict[str, str],
    default_database: str = "",
    default_schema: str = "",
) -> str:
  """Builds a quoted fully-qualified table name (such as MY_DB.MY_SCHEMA.MY_TBL).

  Args:
    table_meta: Table metadata dictionary containing TableName, TableCatalog,
      etc.
    default_database: Fallback database name if omitted in table_meta.
    default_schema: Fallback schema name if omitted in table_meta.

  Returns:
    The quoted fully-qualified table identifier string.
  """
  tbl_name = table_meta.get("TableName", "")
  db_name = table_meta.get("TableCatalog") or default_database or ""
  schema_name = table_meta.get("TableSchema") or default_schema or ""

  if db_name and schema_name:
    return (
        f"{quote_ident(db_name)}."
        f"{quote_ident(schema_name)}.{quote_ident(tbl_name)}"
    )
  elif schema_name:
    return f"{quote_ident(schema_name)}.{quote_ident(tbl_name)}"
  return quote_ident(tbl_name)


# CUSTOMIZE: Stage & Storage Configuration — Edit _build_copy_into_query() to
# customize COPY INTO FILE_FORMAT options (MAX_FILE_SIZE, compression codecs,
# encryption flags) or add WHERE predicates. Pass the storage integration name
# with --storage-integration instead of editing this function.
def _build_copy_into_query(
    table_meta: dict[str, str],
    columns: list[dict[str, str]],
    stage_target: str,
    default_database: str = "",
    default_schema: str = "",
    storage_integration: str | None = None,
) -> str:
  """Builds the COPY INTO Parquet SQL statement for a single table."""
  if stage_target.startswith("'gs://"):
    stage_target = "'gcs://" + stage_target[len("'gs://") :]
  elif stage_target.startswith("gs://"):
    stage_target = "gcs://" + stage_target[len("gs://") :]
  qualified_src = _build_qualified_table_name(
      table_meta, default_database, default_schema
  )

  if columns:
    col_projections = [f"      {format_column_cast(c)}" for c in columns]
    select_body = ",\n".join(col_projections)
    query_from = f"(\n    SELECT\n{select_body}\n    FROM {qualified_src}\n  )"
  else:
    query_from = qualified_src

  integration_clause = (
      f"\n  STORAGE_INTEGRATION = {storage_integration}"
      if storage_integration
      else ""
  )

  return f"""COPY INTO {stage_target}
FROM {query_from}{integration_clause}
FILE_FORMAT = (
  TYPE = PARQUET
  COMPRESSION = SNAPPY
)
HEADER = TRUE
OVERWRITE = TRUE
MAX_FILE_SIZE = 104857600;"""


# DEFAULT SCAFFOLDING: Primary SQL script generator and orchestration.
def generate_export_sql(
    metadata_path_or_uri: str | None = None,
    stage_path: str = "",
    default_database: str | None = None,
    default_schema: str | None = None,
    storage_integration: str | None = None,
    metadata_zip_path_or_uri: str | None = None,
) -> str:
  """Generates the primary Snowflake COPY INTO Parquet SQL script.

  Args:
    metadata_path_or_uri: Path or Cloud Storage URI to translation metadata
      directory or zip.
    stage_path: Destination internal stage or Cloud Storage stage path.
    default_database: Optional fallback database name if omitted in metadata.
    default_schema: Optional fallback schema name if omitted in metadata.
    storage_integration: Optional Snowflake STORAGE_INTEGRATION name for Cloud
      Storage/S3.
    metadata_zip_path_or_uri: Optional path or Cloud Storage URI to a
      metadata.zip archive.

  Returns:
    A complete, formatted Snowflake SQL script string ready for execution.
  """
  path_to_use = metadata_path_or_uri or metadata_zip_path_or_uri
  metadata = _resolve_and_load_metadata(path_to_use)
  columns_by_qualified_table, columns_by_table = _group_and_sort_columns(
      metadata.get("columns", [])
  )
  tables_to_export = _filter_tables_to_export(
      metadata.get("tables", []),
      columns_by_table,
      columns_by_qualified_table=columns_by_qualified_table,
      default_database=default_database,
      default_schema=default_schema,
  )
  generator_name = (
      os.path.basename(sys.argv[0]) if sys.argv and sys.argv[0] else ""
  ) or "export_snowflake_tables_template.py"

  sql_lines = [
      "-- " + "=" * 77,
      "-- Snowflake to Parquet Type-Safe Data Export Script",
      f"-- Generated by bigquery-migration-data-exporter / {generator_name}",
      "-- " + "=" * 77,
      "",
      "-- Ensure clean Parquet export settings",
      "ALTER SESSION SET TIME_OUTPUT_FORMAT = 'HH24:MI:SS.FF6';",
      (
          "ALTER SESSION SET TIMESTAMP_NTZ_OUTPUT_FORMAT = 'YYYY-MM-DD"
          " HH24:MI:SS.FF6';"
      ),
      (
          "ALTER SESSION SET TIMESTAMP_TZ_OUTPUT_FORMAT = 'YYYY-MM-DD"
          " HH24:MI:SS.FF6 TZHTZM';"
      ),
      "",
  ]

  clean_stage = stage_path.strip().strip("'").rstrip("/")
  if clean_stage.startswith("gs://"):
    clean_stage = "gcs://" + clean_stage[len("gs://") :]
  # Prefix stage subpaths and labels with the database only when the metadata
  # spans several databases, so identical SCHEMA.TABLE names in different
  # databases do not overwrite each other's unload location. Tables without a
  # TableCatalog count as --default-database, matching the FROM clause.
  fallback_db = _str_or_empty(default_database)
  multi_database = (
      len(
          {
              _str_or_empty(t.get("TableCatalog")).upper()
              or fallback_db.upper()
              for t in tables_to_export
          }
          - {""}
      )
      > 1
  )
  for t in tables_to_export:
    tbl_name = t.get("TableName", "")
    db_name = _str_or_empty(t.get("TableCatalog")) or fallback_db
    schema_name = t.get("TableSchema") or default_schema or ""
    cols = _lookup_table_columns(
        _table_key(t),
        columns_by_qualified_table,
        resolved_key=_resolved_table_key(t, default_database, default_schema),
    )

    path_parts = [schema_name, tbl_name] if schema_name else [tbl_name]
    if multi_database and db_name:
      path_parts.insert(0, db_name)
    subpath = "/".join(path_parts)
    stage_root = clean_stage or "@~/bqms_export"
    dest_uri = "'" + _escape_sql_literal(f"{stage_root}/{subpath}/") + "'"
    stmt = _build_copy_into_query(
        t,
        cols,
        stage_target=dest_uri,
        default_database=default_database or "",
        default_schema=default_schema or "",
        storage_integration=storage_integration,
    )
    table_label = ".".join(_sanitize_comment_token(p) for p in path_parts)
    divider = "-- " + "-" * 77
    sql_lines.append(
        f"{divider}\n-- Unload Table: {table_label} ->"
        f" Parquet\n{divider}\n{stmt}\n"
    )

  return "\n".join(sql_lines)


# ==============================================================================
# 3. CLI Main Router (DEFAULT SCAFFOLDING)
# ==============================================================================
# DEFAULT SCAFFOLDING: CLI argument parser and SQL file writer entrypoint.


def _parse_args(args: list[str] | None = None) -> argparse.Namespace:
  """Builds and parses CLI arguments for Snowflake Parquet export SQL generation."""
  parser = argparse.ArgumentParser(
      description=(
          "Snowflake Parquet Export SQL Generator (outputs .sql scripts)."
      )
  )
  parser.add_argument(
      "--translation-metadata-dir",
      "--translation-output",
      "--metadata-dir",
      "--config-dir",
      "--metadata-zip",
      dest="metadata_path",
      required=True,
      help=(
          "Path or Cloud Storage URI to translation_output/metadata directory,"
          " config directory, or metadata.zip archive"
      ),
  )
  parser.add_argument(
      "--stage-path",
      default="",
      help=(
          "Destination stage or Cloud Storage URI (for example,"
          " 'gcs://my-bucket/data_unload/' or '@~/bqms_export/'). Defaults to"
          " '@~/bqms_export/'."
      ),
  )
  parser.add_argument(
      "--output-sql",
      help="File path to write the unified export SQL script",
  )
  parser.add_argument(
      "--output-dir",
      help="Directory to write individual per-table *_export.sql files",
  )
  parser.add_argument(
      "--default-database",
      default=os.environ.get("SNOWFLAKE_DATABASE", ""),
      help="Fallback source database name when omitted in metadata",
  )
  parser.add_argument(
      "--default-schema",
      default=os.environ.get("SNOWFLAKE_SCHEMA", ""),
      help="Fallback source schema name when omitted in metadata",
  )
  parser.add_argument(
      "--storage-integration",
      help=(
          "Snowflake STORAGE_INTEGRATION name for Cloud Storage/S3. Required"
          " when --stage-path is a 'gcs://' (or 'gs://') URL, because"
          " Snowflake authorizes direct unloads to private Cloud Storage"
          " buckets only through a storage integration."
      ),
  )
  return parser.parse_args(args)


def _sanitize_sql_filename(label: str, used_filenames: set[str]) -> str:
  """Builds a safe, collision-free per-table SQL filename."""
  unquoted = label.replace('"', "").strip()
  safe_parts = [
      re.sub(r"[^A-Za-z0-9_-]+", "_", p.strip()).strip("_") or "table"
      for p in unquoted.split(".")
      if p.strip()
  ]
  stem = "_".join(safe_parts) if safe_parts else "table"
  filename = f"{stem}_export.sql"
  if filename.upper() in used_filenames and len(safe_parts) > 1:
    filename = f"{'__'.join(safe_parts)}_export.sql"
  idx = 2
  base_stem = filename[: -len("_export.sql")]
  while filename.upper() in used_filenames:
    filename = f"{base_stem}_{idx}_export.sql"
    idx += 1
  used_filenames.add(filename.upper())
  return filename


def _write_table_sql_files(sql: str, output_dir: str) -> list[str]:
  """Splits the unified SQL script and writes individual table SQL files."""
  os.makedirs(output_dir, exist_ok=True)
  divider = "-- " + "-" * 77
  stmts = sql.split(f"{divider}\n-- Unload Table: ")
  session_lines = [
      line
      for line in stmts[0].splitlines()
      if line.strip().upper().startswith("ALTER SESSION")
  ]
  session_header = "\n".join(session_lines) + "\n\n" if session_lines else ""

  written_paths: list[str] = []
  used_filenames: set[str] = set()
  for chunk in stmts[1:]:
    table_label = chunk.split(" -> Parquet")[0].strip()
    filename = _sanitize_sql_filename(table_label, used_filenames)
    table_sql = f"{session_header}{divider}\n-- Unload Table: {chunk}"
    tbl_path = os.path.join(output_dir, filename)
    with open(tbl_path, "w", encoding="utf-8") as f:
      f.write(table_sql)
    written_paths.append(tbl_path)
    print(f"Generated table export SQL: {tbl_path}")
  return written_paths


def main() -> None:
  """CLI entrypoint for the Snowflake Parquet export SQL generator."""
  args = _parse_args()

  stage_lower = args.stage_path.strip().strip("'").lower()
  if (
      stage_lower.startswith(("gcs://", "gs://"))
      and not args.storage_integration
  ):
    print(
        "WARNING: --stage-path is a Cloud Storage URL but"
        " --storage-integration is not set. Snowflake requires a"
        " STORAGE_INTEGRATION to authorize direct 'gcs://' unloads to"
        " private buckets.",
        file=sys.stderr,
    )

  sql = generate_export_sql(
      metadata_path_or_uri=args.metadata_path,
      stage_path=args.stage_path,
      default_database=args.default_database,
      default_schema=args.default_schema,
      storage_integration=args.storage_integration,
  )

  if args.output_sql:
    out_dir = os.path.dirname(os.path.abspath(args.output_sql))
    if out_dir:
      os.makedirs(out_dir, exist_ok=True)
    with open(args.output_sql, "w", encoding="utf-8") as f:
      f.write(sql)
    print(f"Generated unified Snowflake export script: {args.output_sql}")

  if args.output_dir:
    _write_table_sql_files(sql, args.output_dir)

  if not args.output_sql and not args.output_dir:
    print(sql)


if __name__ == "__main__":
  main()
