#!/usr/bin/env python3
r"""Template Script for Generating Type-Safe Oracle Export SQL Files.

This asset template script provides a reference implementation for generating
type-safe Oracle SELECT export scripts (.sql) directly from BQMS
translation_output/metadata configs or an Oracle extractor metadata.zip
(DBA.Tables.csv / ALL.Tables.csv and DBA.TabColumns.csv / ALL.TabColumns.csv).
It has zero JDBC or database connector dependencies.

Oracle has no native SQL statement that unloads arbitrary relational tables to
Parquet on local disk or Cloud Storage (DBMS_CLOUD.EXPORT_DATA is
Autonomous Database-only). The export therefore happens in two steps:

  1. This script emits one explicit-cast SELECT per table. The casts pin every
     column to an Oracle SQL type whose `python-oracledb` cursor metadata and
     Parquet representation BigQuery loads without drift (NUMBER(1..19,0) ->
     NUMBER(19,0) -> INT64, NUMBER(p,s) -> DECIMAL128 -> NUMERIC/BIGNUMERIC,
     FLOAT/BINARY_FLOAT/BINARY_DOUBLE -> BINARY_DOUBLE -> FLOAT64,
     DATE -> TIMESTAMP(6) -> DATETIME, TIMESTAMP -> TIMESTAMP(6),
     TIMESTAMP WITH [LOCAL] TIME ZONE -> UTC TIMESTAMP(6), CHAR/NCHAR padding
     trimmed via RTRIM).
  2. A downstream Python execution script runs each SELECT via the
     `python-oracledb` driver, derives the Arrow schema from
     `cursor.description`, and writes Snappy Parquet files under
     ./data_unload/[<SCHEMA>/]<TABLE>/.

Usage Pattern:
  Copy `assets/export_oracle_tables_template.py` from this skill's directory
  (`<SKILL_DIR>`, the directory containing `SKILL.md`) into your
  working directory (e.g., `./export_oracle_tables.py`). Run the copy as-is
  for standard export SQL generation, and prioritize modifying the marked
  `# CUSTOMIZE:` extension points if your environment requires custom type
  projections, row filters, or schema/table filtering. Sections marked
  `# DEFAULT SCAFFOLDING` can be kept unchanged unless deeper orchestration
  adjustments are needed.

Dependencies:
  pip install pyyaml==6.0.2

Usage Examples:
    # Copy the template from this skill's directory to your working directory:
    cp <SKILL_DIR>/assets/export_oracle_tables_template.py \
        ./export_oracle_tables.py

    # 1. Generate per-table Oracle export SQL files from BQMS output:
    python3 ./export_oracle_tables.py \
        --translation-metadata-dir ./translated_output/metadata \
        --default-schema MY_SCHEMA \
        --output-dir ./export_sql

    # 2. Generate a unified export SQL file straight from the extractor zip:
    python3 ./export_oracle_tables.py \
        --metadata-zip gs://my-bucket/dwh-migration-oracle-metadata.zip \
        --schema MY_SCHEMA \
        --output-sql oracle_export.sql
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import os
import re
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


def _strip(value: str | None) -> str:
  """Trims whitespace around Oracle data dictionary CSV fields."""
  return (value or "").strip()


def load_metadata_from_zip(
    zip_bytes: bytes,
) -> dict[str, list[dict[str, str]]]:
  """Extracts table and column metadata from an Oracle extractor metadata.zip.

  Reads DBA.Tables.csv / ALL.Tables.csv and DBA.TabColumns.csv /
  ALL.TabColumns.csv (falls back to the generic tables.csv / columns.csv layout)
  and normalizes rows to the shared TableCatalog/TableSchema/TableName/
  ColumnName/DataType record shape. Note that DBA.TabColumns.csv in Oracle
  extractor archives contains columns for both base tables and views; pairing
  with DBA.Tables.csv ensures only physical base tables are exported.

  Args:
    zip_bytes: Raw bytes of the metadata zip archive.

  Returns:
    A dictionary containing 'tables' and 'columns' lists of records.
  """
  result: dict[str, list[dict[str, str]]] = {"tables": [], "columns": []}

  with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
    names = z.namelist()
    by_base = {os.path.basename(n).lower(): n for n in names}

    def _rows(candidates: list[str]) -> tuple[str | None, list[dict[str, str]]]:
      for c in candidates:
        member = by_base.get(c.lower())
        if member:
          with z.open(member) as fh:
            return c, list(
                csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig"))
            )
      return None, []

    tables_fn, table_rows = _rows(
        ["DBA.Tables.csv", "ALL.Tables.csv", "tables.csv"]
    )
    columns_fn, column_rows = _rows(
        ["DBA.TabColumns.csv", "ALL.TabColumns.csv", "columns.csv"]
    )

  if tables_fn in ("DBA.Tables.csv", "ALL.Tables.csv"):
    for r in table_rows:
      tbl_name = _strip(r.get("TABLE_NAME") or r.get("TableName"))
      dropped = _strip(r.get("DROPPED")).upper() == "YES"
      secondary = _strip(r.get("SECONDARY")).upper() == "Y"
      nested = _strip(r.get("NESTED")).upper() == "YES"
      is_recyclebin = tbl_name.startswith("BIN$")
      is_base = not (dropped or secondary or nested or is_recyclebin)
      result["tables"].append({
          "TableCatalog": "",
          "TableSchema": _strip(r.get("OWNER") or r.get("TableSchema")),
          "TableName": tbl_name,
          "TableType": "BASE TABLE" if is_base else "SECONDARY",
      })
  else:
    result["tables"] = [
        {k: _strip(v) for k, v in r.items() if k is not None}
        for r in table_rows
    ]

  if columns_fn in ("DBA.TabColumns.csv", "ALL.TabColumns.csv"):
    for r in column_rows:
      nullable = _strip(r.get("NULLABLE") or r.get("Nullable")).upper() or "Y"
      result["columns"].append({
          "TableCatalog": "",
          "TableSchema": _strip(r.get("OWNER") or r.get("TableSchema")),
          "TableName": _strip(r.get("TABLE_NAME") or r.get("TableName")),
          "ColumnName": _strip(r.get("COLUMN_NAME") or r.get("ColumnName")),
          "OrdinalPosition": _strip(
              r.get("COLUMN_ID") or r.get("OrdinalPosition")
          ),
          "DataType": _strip(r.get("DATA_TYPE") or r.get("DataType")).upper(),
          "ColumnLength": _strip(
              r.get("CHAR_LENGTH")
              or r.get("DATA_LENGTH")
              or r.get("ColumnLength")
          ),
          "NumericPrecision": _strip(
              r.get("DATA_PRECISION") or r.get("NumericPrecision")
          ),
          "NumericScale": _strip(r.get("DATA_SCALE") or r.get("NumericScale")),
          "Nullable": nullable,
          "ExplicitNotNull": "Y" if nullable == "N" else "N",
      })
  else:
    for r in column_rows:
      col_dict = {k: _strip(v) for k, v in r.items() if k is not None}
      if "ExplicitNotNull" not in col_dict:
        nullable = (
            _strip(col_dict.get("Nullable") or col_dict.get("NULLABLE")).upper()
            or "Y"
        )
        col_dict["ExplicitNotNull"] = "Y" if nullable == "N" else "N"
      result["columns"].append(col_dict)

  return result


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
  # (schema, table) -> database of the config already loaded for it.
  loaded_from: dict[tuple[str, str], str] = {}

  for root, dirs, files in os.walk(config_dir):
    dirs.sort()  # Deterministic order, so the first database wins.
    for f in sorted(files):
      if not (f.endswith(".yaml") or f.endswith(".yml")):
        continue
      try:
        with open(os.path.join(root, f), "r", encoding="utf-8") as yf:
          cfg = yaml.safe_load(yf)
      except (yaml.YAMLError, OSError):
        continue
      if not isinstance(cfg, dict):
        continue

      src_name = cfg.get("sourceName", "")
      parts = src_name.split(".") if src_name else []
      # Oracle names in BQMS are __DEFAULT_DATABASE__.SCHEMA.TABLE or
      # SCHEMA.TABLE.
      schema = parts[-2] if len(parts) >= 2 else ""
      table = parts[-1] if parts else f.rsplit(".", 1)[0]
      database = parts[0] if len(parts) >= 3 else ""
      # Views are recreated, not exported; skip them before they claim the
      # SCHEMA.TABLE slot of a table in another database.
      if not (cfg.get("externalTableName") or cfg.get("externalTableDdlPath")):
        continue
      # One Oracle connection can't read the same SCHEMA.TABLE from two
      # databases, and merging both configs would mix their columns.
      prior = loaded_from.setdefault((schema, table), database)
      if prior != database:
        print(
            f"WARNING: Skipping {src_name}: {schema}.{table} was already"
            f" loaded from database '{prior}'.",
            file=sys.stderr,
        )
        continue

      result["tables"].append({
          "TableCatalog": "",
          "TableSchema": schema,
          "TableName": table,
          "TableType": "BASE TABLE",
      })

      for idx, col in enumerate(cfg.get("columns") or [], start=1):
        if not isinstance(col, dict):
          continue
        src_type = col.get("sourceType") or {}
        src = (
            src_type
            if isinstance(src_type, dict)
            else {"genericName": src_type}
        )
        raw_code = str(src.get("name") or "").strip().upper()
        generic_name = str(src.get("genericName") or "").strip().upper()
        # Prefer raw Oracle type name ('DATE', 'NUMBER', 'TIMESTAMP(6)', etc.)
        # because BQMS sets genericName='DATETIME' for Oracle DATE.
        data_type = raw_code or generic_name
        tgt_type = col.get("targetType") or {}
        tgt = tgt_type if isinstance(tgt_type, dict) else {"name": tgt_type}
        tgt_name = str(tgt.get("name") or "").strip().upper()
        col_entry = {
            "TableCatalog": "",
            "TableSchema": schema,
            "TableName": table,
            "ColumnName": col.get("sourceName", ""),
            "OrdinalPosition": str(idx),
            "DataType": data_type,
            "NumericPrecision": str(src.get("precision", "")),
            "NumericScale": str(src.get("scale", "")),
            "Nullable": "N" if col.get("notNull") else "Y",
            "ExplicitNotNull": "Y" if col.get("notNull") else "N",
        }
        # Persist every BQMS target type so format_column_cast() honors
        # INT64 / NUMERIC / BIGNUMERIC / FLOAT64 / DATE / DATETIME overrides.
        if tgt_name:
          col_entry["TargetType"] = tgt_name
        result["columns"].append(col_entry)

  return result


def _find_config_dir(dir_path: str) -> str | None:
  """Locates the directory containing BQMS table YAML configurations."""
  for candidate in (
      os.path.join(dir_path, "metadata", "config"),
      os.path.join(dir_path, "config"),
  ):
    if os.path.isdir(candidate):
      return candidate
  for _, _, files in os.walk(dir_path):
    if any(f.endswith((".yaml", ".yml")) for f in files):
      return dir_path
  return None


def load_metadata_from_dir(dir_path: str) -> dict[str, list[dict[str, str]]]:
  """Discovers metadata in a directory (BQMS YAML configs or embedded zip)."""
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
  """Resolves local or Cloud Storage metadata path/zip and loads metadata."""
  if not path_or_uri:
    return {"tables": [], "columns": []}

  if path_or_uri.startswith("gs://"):
    if path_or_uri.endswith(".zip"):
      return load_metadata_from_zip(read_file_or_gcs(path_or_uri))
    with tempfile.TemporaryDirectory(prefix="bqms_meta_") as temp_dir:
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
  if os.path.isdir(path_or_uri):
    return load_metadata_from_dir(path_or_uri)
  return load_metadata_from_zip(read_file_or_gcs(path_or_uri))


def _ordinal(col: dict[str, str]) -> int:
  pos = str(col.get("OrdinalPosition", ""))
  return int(pos) if pos.isdigit() else 999999


def _group_and_sort_columns(
    columns: list[dict[str, str]],
) -> tuple[
    dict[tuple[str, str], list[dict[str, str]]],
    dict[str, list[dict[str, str]]],
]:
  """Groups columns by (schema, table) and table name, sorted by ordinal."""
  by_schema_table: dict[tuple[str, str], list[dict[str, str]]] = {}
  by_table: dict[str, list[dict[str, str]]] = {}
  for col in columns:
    key = (
        _strip(col.get("TableSchema")),
        _strip(col.get("TableName")),
    )
    by_schema_table.setdefault(key, []).append(col)
  for (_, tbl), cols in by_schema_table.items():
    cols.sort(key=_ordinal)
    by_table.setdefault(tbl, cols)
  return by_schema_table, by_table


def _lookup_table_columns(
    by_schema_table: dict[tuple[str, str], list[dict[str, str]]],
    raw_schema: str,
    schema: str,
    tbl: str,
) -> list[dict[str, str]]:
  """Finds a table's columns without borrowing them from another schema.

  Tries the metadata schema, then the --default-schema fallback, then columns
  recorded without a schema. A table without any schema only matches a
  same-named table when exactly one candidate exists; otherwise it gets no
  column projections and falls back to SELECT *.

  Args:
    by_schema_table: Column metadata keyed by (schema, table name).
    raw_schema: The schema recorded in the metadata for this table.
    schema: The effective schema after applying --default-schema.
    tbl: The table name.

  Returns:
    The table's column metadata, or an empty list when no unambiguous match
    exists.
  """
  for key in ((raw_schema, tbl), (schema, tbl), ("", tbl)):
    cols = by_schema_table.get(key)
    if cols:
      return cols
  if not schema:
    matches = [c for (_, t), c in by_schema_table.items() if t == tbl and c]
    if len(matches) == 1:
      return matches[0]
  return []


# CUSTOMIZE: Table & Row Filtering — Edit _filter_tables_to_export() to add
# custom schema/table inclusion or exclusion rules.
def _filter_tables_to_export(
    raw_tables: list[dict[str, str]],
    columns_by_table: dict[str, list[dict[str, str]]],
    schemas: set[str] | None = None,
    columns_by_schema_table: (
        dict[tuple[str, str], list[dict[str, str]]] | None
    ) = None,
    default_schema: str = "",
) -> list[dict[str, str]]:
  """Filters tables to export: drops views/system objects, applies filters.

  The schema allow-list and duplicate check use the effective schema
  (TableSchema, else default_schema), so schema-less entries match
  --schema and don't duplicate qualified entries for the same table.

  Args:
    raw_tables: Table rows from the metadata (may be empty).
    columns_by_table: Column metadata keyed by table name.
    schemas: Optional upper-cased schema allow-list.
    columns_by_schema_table: Column metadata keyed by (schema, table name), used
      when raw_tables is empty.
    default_schema: Fallback schema for entries without a TableSchema.

  Returns:
    The table entries to export, without duplicates.
  """
  out: list[dict[str, str]] = []
  seen: set[tuple[str, str]] = set()
  default_schema = _strip(default_schema)

  if raw_tables:
    for t in raw_tables:
      tbl = _strip(t.get("TableName"))
      schema = _strip(t.get("TableSchema")) or default_schema
      tbl_type = _strip(t.get("TableType")).upper()
      if tbl_type and tbl_type not in ("BASE TABLE", "TABLE"):
        continue
      if schemas and schema.upper() not in schemas:
        continue
      if (schema, tbl) in seen:
        continue
      seen.add((schema, tbl))
      out.append(t)
    out.sort(
        key=lambda t: (
            _strip(t.get("TableSchema")) or default_schema,
            _strip(t.get("TableName")),
        )
    )
  elif columns_by_schema_table:
    for raw_schema, tbl in sorted(columns_by_schema_table):
      schema = raw_schema or default_schema
      if schemas and schema.upper() not in schemas:
        continue
      if (schema, tbl) not in seen:
        seen.add((schema, tbl))
        out.append({"TableSchema": raw_schema, "TableName": tbl})
  else:
    for tbl in sorted(columns_by_table):
      cols = columns_by_table[tbl]
      raw_schema = _strip(cols[0].get("TableSchema")) if cols else ""
      schema = raw_schema or default_schema
      if schemas and schema.upper() not in schemas:
        continue
      if (schema, tbl) not in seen:
        seen.add((schema, tbl))
        entry = {"TableName": tbl}
        if raw_schema:
          entry["TableSchema"] = raw_schema
        out.append(entry)
  return out


# ==============================================================================
# 2. Type-Safe SQL Generation Logic
# ==============================================================================

_VALID_IDENT_REGEX = re.compile(r"^[A-Z][A-Z0-9_$#]*$")

# A subset of Oracle reserved words that commonly appear as column or table
# names in migrated schemas. Anything matching is double-quoted.
_ORACLE_RESERVED = frozenset((
    "ACCESS",
    "ADD",
    "ALL",
    "ALTER",
    "AND",
    "ANY",
    "AS",
    "ASC",
    "AUDIT",
    "BETWEEN",
    "BY",
    "CHAR",
    "CHECK",
    "CLUSTER",
    "COLUMN",
    "COMMENT",
    "COMPRESS",
    "CONNECT",
    "CREATE",
    "CURRENT",
    "DATE",
    "DECIMAL",
    "DEFAULT",
    "DELETE",
    "DESC",
    "DISTINCT",
    "DROP",
    "ELSE",
    "EXCLUSIVE",
    "EXISTS",
    "FILE",
    "FLOAT",
    "FOR",
    "FROM",
    "GRANT",
    "GROUP",
    "HAVING",
    "IDENTIFIED",
    "IMMEDIATE",
    "IN",
    "INCREMENT",
    "INDEX",
    "INITIAL",
    "INSERT",
    "INTEGER",
    "INTERSECT",
    "INTO",
    "IS",
    "LEVEL",
    "LIKE",
    "LOCK",
    "LONG",
    "MAXEXTENTS",
    "MINUS",
    "MLSLABEL",
    "MODE",
    "MODIFY",
    "NOAUDIT",
    "NOCOMPRESS",
    "NOT",
    "NOWAIT",
    "NULL",
    "NUMBER",
    "OF",
    "OFFLINE",
    "ON",
    "ONLINE",
    "OPTION",
    "OR",
    "ORDER",
    "PCTFREE",
    "PRIOR",
    "PUBLIC",
    "RAW",
    "RENAME",
    "RESOURCE",
    "REVOKE",
    "ROW",
    "ROWID",
    "ROWNUM",
    "ROWS",
    "SELECT",
    "SESSION",
    "SET",
    "SHARE",
    "SIZE",
    "SMALLINT",
    "START",
    "SUCCESSFUL",
    "SYNONYM",
    "SYSDATE",
    "TABLE",
    "THEN",
    "TO",
    "TRIGGER",
    "UID",
    "UNION",
    "UNIQUE",
    "UPDATE",
    "USER",
    "VALIDATE",
    "VALUES",
    "VARCHAR",
    "VARCHAR2",
    "VIEW",
    "WHENEVER",
    "WHERE",
    "WITH",
))

# Oracle INTEGER / INT are ANSI aliases for NUMBER(38) (scale 0), so they keep
# 38 integer digits instead of narrowing to NUMBER(19, 0).
_ANSI_INTEGER_TYPES = frozenset(("INTEGER", "INT"))
_INT_TYPES = frozenset((
    "SMALLINT",
    "BIGINT",
    "TINYINT",
    "BYTEINT",
    "INT64",
    "PLS_INTEGER",
    "BINARY_INTEGER",
))
_NUMBER_TYPES = frozenset(("NUMBER", "DECIMAL", "NUMERIC", "DEC", "BIGNUMERIC"))
_FLOAT_TYPES = frozenset((
    "FLOAT",
    "REAL",
    "DOUBLE PRECISION",
    "DOUBLE",
    "BINARY_FLOAT",
    "BINARY_DOUBLE",
    "FLOAT64",
))
_DATE_TYPES = frozenset(("DATE",))
_TIMESTAMP_TYPES = frozenset((
    "TIMESTAMP",
    "DATETIME",
))
_TIMESTAMP_LTZ_TYPES = frozenset((
    "TIMESTAMP WITH LOCAL TIME ZONE",
    "TIMESTAMPLTZ",
))
_TIMESTAMP_TZ_TYPES = frozenset((
    "TIMESTAMP WITH TIME ZONE",
    "TIMESTAMPTZ",
))
_CHAR_TYPES = frozenset(("CHAR", "NCHAR", "CHARACTER"))
_VARCHAR_TYPES = frozenset((
    "VARCHAR2",
    "NVARCHAR2",
    "VARCHAR",
    "NVARCHAR",
    "STRING",
    "CLOB",
    "NCLOB",
    "LONG",
))
_BYTE_TYPES = frozenset((
    "RAW",
    "LONG RAW",
    "BLOB",
    "BFILE",
    "BINARY",
    "VARBINARY",
    "BYTES",
))
_ROWID_TYPES = frozenset(("ROWID", "UROWID"))
_XML_TYPES = frozenset(("XMLTYPE", "SYS.XMLTYPE", "XML"))
_JSON_TYPES = frozenset(("JSON",))


# DEFAULT SCAFFOLDING: Identifier quoting helper.
def quote_ident(ident: str) -> str:
  """Double-quotes an Oracle identifier when it is not a plain name.

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
  if not _VALID_IDENT_REGEX.match(ident) or ident.upper() in _ORACLE_RESERVED:
    escaped = ident.replace('"', '""')
    return f'"{escaped}"'
  return ident


_PARAM_TYPE_REGEX = re.compile(
    r"^(?P<base>[A-Z0-9_ ]+?)\s*\(\s*(?P<p>-?\d+|\*)"
    r"(?:\s*,\s*(?P<s>-?\d+))?(?:\s+(?:BYTE|CHAR))?\s*\)\s*(?P<rest>.*)$"
)
_INTERVAL_YM_REGEX = re.compile(
    r"^INTERVAL\s+YEAR(?:\s*\(\d+\))?\s+TO\s+MONTH$"
)
_INTERVAL_DS_REGEX = re.compile(
    r"^INTERVAL\s+DAY(?:\s*\(\d+\))?\s+TO\s+SECOND(?:\s*\(\d+\))?$"
)


def _to_int(value: str | None) -> int | None:
  value = str(value or "").strip()
  return int(value) if value.lstrip("-").isdigit() else None


def _normalize_data_type(
    raw_type: str, precision: int | None, scale: int | None
) -> tuple[str, int | None, int | None]:
  """Normalizes an Oracle DATA_TYPE string into (base_type, p, s)."""
  dt = " ".join(raw_type.upper().split())
  if (
      _INTERVAL_YM_REGEX.match(dt)
      or _INTERVAL_DS_REGEX.match(dt)
      or dt.startswith("INTERVAL ")
  ):
    return "INTERVAL", precision, scale
  m = _PARAM_TYPE_REGEX.match(dt)
  if m:
    base = f"{m.group('base').strip()} {m.group('rest').strip()}".strip()
    if precision is None and m.group("p") != "*":
      precision = _to_int(m.group("p"))
    if scale is None and m.group("s") is not None:
      scale = _to_int(m.group("s"))
    # In Oracle, NUMBER(p) with a single argument means NUMBER(p, 0).
    if base in _NUMBER_TYPES and m.group("p") != "*" and scale is None:
      scale = 0
    return base, precision, scale
  return dt, precision, scale


def _ltz_to_utc(col_name: str) -> str:
  """Projects TIMESTAMP WITH LOCAL TIME ZONE as UTC TIMESTAMP(6).

  LOCAL TIME ZONE values render in the session time zone, so the explicit
  TIMESTAMP WITH TIME ZONE cast plus SYS_EXTRACT_UTC keeps the export
  independent of the session's TIME_ZONE setting.

  Args:
    col_name: The quoted column name.

  Returns:
    The SQL projection expression.
  """
  return (
      f"CAST(SYS_EXTRACT_UTC(CAST({col_name} AS TIMESTAMP WITH TIME ZONE))"
      f" AS TIMESTAMP(6)) AS {col_name}"
  )


# CUSTOMIZE: Custom Type Projections -- Edit format_column_cast() to change
# how an Oracle type is projected before Parquet serialization (e.g. keep CHAR
# padding, project DATE as TRUNC(col) for a BigQuery DATE, or widen NUMBER
# precision).
def format_column_cast(
    col: dict[str, str],
    target_bq_type: str | None = None,
    rtrim_char: bool = True,
    unbounded_number_scale: int = 9,
) -> str:
  """Generates a type-safe Oracle projection expression for Parquet export.

  The executor derives the Parquet schema from `cursor.description`, so the
  SQL projection here determines both the PyArrow type and the BigQuery column
  type created by `bq load --source_format=PARQUET`:

    NUMBER(1..19, 0) / SMALLINT         -> CAST AS NUMBER(19, 0)   -> INT64
    NUMBER(20..38, 0) / INTEGER / INT   -> CAST AS NUMBER(p, 0)    -> BIGNUMERIC
    NUMBER(p, s > 0)                    -> CAST AS NUMBER(p, s)    -> NUMERIC
    NUMBER(p, s < 0)                    -> CAST AS NUMBER(p+|s|,0) -> NUMERIC
    NUMBER (unconstrained)              -> CAST AS NUMBER(38, 9)   -> BIGNUMERIC
    FLOAT / REAL / BINARY_FLOAT/DOUBLE  -> CAST AS BINARY_DOUBLE   -> FLOAT64
    DATE                                -> CAST AS TIMESTAMP(6)    -> DATETIME
    TIMESTAMP(n)                        -> CAST AS TIMESTAMP(6)    -> TIMESTAMP
    TIMESTAMP(n) WITH [LOCAL] TIME ZONE -> SYS_EXTRACT_UTC TS(6)   -> TIMESTAMP
    CHAR(n) / NCHAR(n)                  -> RTRIM(col)              -> STRING
    VARCHAR2 / NVARCHAR2 / CLOB / NCLOB -> col                     -> STRING
    RAW / BLOB / BFILE                  -> col                     -> BYTES
    ROWID / UROWID                      -> ROWIDTOCHAR / VARCHAR2  -> STRING
    INTERVAL YEAR/DAY                   -> TRIM(CAST AS VARCHAR2)  -> STRING
    XMLTYPE                             -> XMLSERIALIZE AS CLOB    -> STRING
    JSON                                -> JSON_SERIALIZE AS CLOB  -> STRING

  Args:
    col: Column metadata dict containing ColumnName, DataType, etc.
    target_bq_type: Optional BigQuery target type override.
    rtrim_char: Strip CHAR(n)/NCHAR(n) trailing pad spaces (BigQuery STRING has
      no fixed-width semantics, so padded values would mismatch in validation).
    unbounded_number_scale: Fractional scale for unconstrained NUMBER /
      NUMBER(*) columns (default 9, supporting up to 29 integer digits).

  Returns:
    A SQL projection expression, e.g. 'CAST(SS_ITEM_SK AS NUMBER(19, 0)) AS
    SS_ITEM_SK'.
  """
  col_name = quote_ident(_strip(col.get("ColumnName")))
  data_type, precision, scale = _normalize_data_type(
      str(col.get("DataType") or ""),
      _to_int(col.get("NumericPrecision")),
      _to_int(col.get("NumericScale")),
  )
  if scale is None and (
      data_type in _ANSI_INTEGER_TYPES or data_type in _INT_TYPES
  ):
    scale = 0  # INTEGER / INT are NUMBER(38) aliases.
  explicit_target = (
      (target_bq_type or col.get("TargetType") or "").upper().strip()
  )
  explicit_base = (
      re.split(r"[(<]", explicit_target, maxsplit=1)[0].strip()
      if explicit_target
      else ""
  )

  if 0 <= unbounded_number_scale <= 38:
    default_unb_scale = unbounded_number_scale
  else:
    logging.warning(
        "Out-of-range unbounded_number_scale=%d (expected 0..38); falling back"
        " to 9.",
        unbounded_number_scale,
    )
    default_unb_scale = 9

  # Honor explicit target_bq_type overrides first. Other cross-type targets
  # (STRING, JSON, BYTES, BOOL, TIME, and DATE on columns other than DATE /
  # TIMESTAMP) keep the default projection below.
  if explicit_base:
    if explicit_base in (
        "INT64",
        "INTEGER",
        "BIGINT",
        "SMALLINT",
        "TINYINT",
        "BYTEINT",
    ):
      return f"CAST({col_name} AS NUMBER(19, 0)) AS {col_name}"
    if explicit_base in ("FLOAT64", "FLOAT", "DOUBLE"):
      return f"CAST({col_name} AS BINARY_DOUBLE) AS {col_name}"
    if explicit_base == "DATE" and (
        data_type in _DATE_TYPES or data_type in _TIMESTAMP_TYPES
    ):
      return f"TRUNC({col_name}) AS {col_name}"
    if explicit_base in ("DATETIME", "TIMESTAMP"):
      if data_type in _TIMESTAMP_TZ_TYPES:
        return (
            f"CAST(SYS_EXTRACT_UTC({col_name}) AS TIMESTAMP(6)) AS {col_name}"
        )
      if data_type in _TIMESTAMP_LTZ_TYPES:
        return _ltz_to_utc(col_name)
      return f"CAST({col_name} AS TIMESTAMP(6)) AS {col_name}"
    if explicit_base in ("NUMERIC", "DECIMAL"):
      if scale is not None and scale > 0:
        s_val = min(scale, 38)
        p_val = min(max(precision or 29, s_val, 1), 38)
        return f"CAST({col_name} AS NUMBER({p_val}, {s_val})) AS {col_name}"
      if scale is not None and scale <= 0:
        p_val = min(max((precision or 29) + abs(scale), 29), 38)
        return f"CAST({col_name} AS NUMBER({p_val}, 0)) AS {col_name}"
      return (
          f"CAST({col_name} AS NUMBER(38, {default_unb_scale})) AS {col_name}"
      )
    if explicit_base == "BIGNUMERIC":
      if scale is not None and scale > 0:
        s_val = min(scale, 38)
        p_val = min(max(precision or 38, s_val, 1), 38)
        return f"CAST({col_name} AS NUMBER({p_val}, {s_val})) AS {col_name}"
      if scale is not None and scale <= 0:
        return f"CAST({col_name} AS NUMBER(38, 0)) AS {col_name}"
      return (
          f"CAST({col_name} AS NUMBER(38, {default_unb_scale})) AS {col_name}"
      )

  if data_type in _ANSI_INTEGER_TYPES:
    return f"CAST({col_name} AS NUMBER(38, 0)) AS {col_name}"

  if data_type in _INT_TYPES:
    return f"CAST({col_name} AS NUMBER(19, 0)) AS {col_name}"

  if data_type in _NUMBER_TYPES:
    # Unconstrained NUMBER has precision=None, scale=None in DBA.TabColumns.csv
    # and precision=38, scale=None in BQMS metadata/config/*.yaml.
    if scale is None:
      return (
          f"CAST({col_name} AS NUMBER(38, {default_unb_scale})) AS {col_name}"
      )
    if scale < 0:
      eff_p = min((precision or 38) + abs(scale), 38)
      if eff_p <= 19:
        return f"CAST({col_name} AS NUMBER(19, 0)) AS {col_name}"
      return f"CAST({col_name} AS NUMBER({eff_p}, 0)) AS {col_name}"
    if scale == 0:
      if precision is not None and 1 <= precision <= 19:
        return f"CAST({col_name} AS NUMBER(19, 0)) AS {col_name}"
      p_val = min(max(precision or 38, 20), 38)
      return f"CAST({col_name} AS NUMBER({p_val}, 0)) AS {col_name}"
    # scale > 0
    s_val = min(scale, 38)
    p_val = min(max(precision or 38, s_val, 1), 38)
    return f"CAST({col_name} AS NUMBER({p_val}, {s_val})) AS {col_name}"

  if data_type in _FLOAT_TYPES:
    return f"CAST({col_name} AS BINARY_DOUBLE) AS {col_name}"

  if data_type in _DATE_TYPES:
    return f"CAST({col_name} AS TIMESTAMP(6)) AS {col_name}"

  if data_type in _TIMESTAMP_TYPES:
    return f"CAST({col_name} AS TIMESTAMP(6)) AS {col_name}"

  if data_type in _TIMESTAMP_TZ_TYPES:
    return f"CAST(SYS_EXTRACT_UTC({col_name}) AS TIMESTAMP(6)) AS {col_name}"

  if data_type in _TIMESTAMP_LTZ_TYPES:
    return _ltz_to_utc(col_name)

  if data_type in _CHAR_TYPES:
    if rtrim_char:
      return f"RTRIM({col_name}) AS {col_name}"
    return f"{col_name} AS {col_name}"

  if data_type in _VARCHAR_TYPES or data_type in _BYTE_TYPES:
    return f"{col_name} AS {col_name}"

  if data_type == "ROWID":
    return f"ROWIDTOCHAR({col_name}) AS {col_name}"

  if data_type in _ROWID_TYPES:
    return f"CAST({col_name} AS VARCHAR2(256)) AS {col_name}"

  if data_type == "INTERVAL":
    return f"TRIM(CAST({col_name} AS VARCHAR2(100))) AS {col_name}"

  if data_type in _XML_TYPES:
    return f"XMLSERIALIZE(CONTENT {col_name} AS CLOB) AS {col_name}"

  if data_type in _JSON_TYPES:
    return f"JSON_SERIALIZE({col_name} RETURNING CLOB) AS {col_name}"

  # SDO_GEOMETRY, ANYDATA, user-defined object types, etc.
  return f"CAST({col_name} AS VARCHAR2(4000)) AS {col_name}"


# DEFAULT SCAFFOLDING: Table name qualification helper.
def _build_qualified_table_name(
    table_meta: dict[str, str], default_schema: str = ""
) -> str:
  """Builds a quoted SCHEMA.TABLE name."""
  tbl = _strip(table_meta.get("TableName"))
  schema = _strip(table_meta.get("TableSchema")) or _strip(default_schema)
  return (
      f"{quote_ident(schema)}.{quote_ident(tbl)}"
      if schema
      else quote_ident(tbl)
  )


# CUSTOMIZE: Row Filters -- Edit _build_select_query() to add WHERE
# predicates (e.g. incremental extraction windows or partition filters).
def _build_select_query(
    table_meta: dict[str, str],
    columns: list[dict[str, str]],
    default_schema: str = "",
    rtrim_char: bool = True,
    unbounded_number_scale: int = 9,
) -> str:
  """Builds the explicit-cast SELECT statement for a single Oracle table.

  Args:
    table_meta: Table metadata dictionary with TableSchema and TableName.
    columns: Ordered list of column metadata dictionaries for the table.
    default_schema: Fallback schema/owner name when TableSchema is empty.
    rtrim_char: Whether to RTRIM fixed-width CHAR(n)/NCHAR(n) columns.
    unbounded_number_scale: Fractional scale for unconstrained NUMBER columns.

  Returns:
    A complete Oracle SELECT statement ending with a semicolon.
  """
  qualified = _build_qualified_table_name(table_meta, default_schema)
  if columns:
    body = ",\n".join(
        "  "
        + format_column_cast(
            c,
            rtrim_char=rtrim_char,
            unbounded_number_scale=unbounded_number_scale,
        )
        for c in columns
    )
  else:
    body = "  *"
  return f"SELECT\n{body}\nFROM {qualified};"


def _is_not_null(col: dict[str, str]) -> bool:
  """Returns True when a column is marked non-nullable in YAML or zip CSV."""
  if "ExplicitNotNull" in col:
    return str(col.get("ExplicitNotNull", "N")).strip().upper() == "Y"
  return str(col.get("Nullable", "Y")).strip().upper() == "N"


def _sanitize_comment_token(val: str) -> str:
  """Replaces control chars (CR, LF, NUL) so SQL comments stay single-line."""
  return re.sub(r"[\r\n\x00]+", " ", str(val)).strip()


# DEFAULT SCAFFOLDING: Primary SQL script generator and orchestration.
def generate_export_sql(
    metadata_path_or_uri: str | None = None,
    default_schema: str | None = None,
    schemas: list[str] | None = None,
    rtrim_char: bool = True,
    unbounded_number_scale: int = 9,
) -> str:
  """Generates the unified Oracle export SQL script.

  Each table section is introduced by a divider and a
  `-- Unload Table: <SCHEMA>.<TABLE> -> Parquet` marker that the executor uses
  to name the ./data_unload/[<SCHEMA>/]<TABLE>/ output directory.

  Args:
    metadata_path_or_uri: Path or Cloud Storage URI to translation metadata dir
      or zip.
    default_schema: Fallback schema/owner when metadata omits it.
    schemas: Optional schema allow-list (case-insensitive).
    rtrim_char: Strip CHAR(n)/NCHAR(n) trailing pad spaces.
    unbounded_number_scale: Fractional scale for unconstrained NUMBER columns.

  Returns:
    A complete Oracle SQL script string.
  """
  metadata = _resolve_and_load_metadata(metadata_path_or_uri)
  by_schema_table, by_table = _group_and_sort_columns(
      metadata.get("columns", [])
  )
  schema_filter = {s.upper() for s in schemas} if schemas else None
  tables = _filter_tables_to_export(
      metadata.get("tables", []),
      by_table,
      schema_filter,
      columns_by_schema_table=by_schema_table,
      default_schema=default_schema or "",
  )
  if not tables and schema_filter:
    available = sorted({
        _strip(t.get("TableSchema")) or _strip(default_schema)
        for t in metadata.get("tables", []) or metadata.get("columns", [])
    })
    print(
        "WARNING: No tables match the --schema filter. Available schemas:"
        f" {', '.join(s for s in available if s) or '(none)'}.",
        file=sys.stderr,
    )
  generator_name = (
      os.path.basename(sys.argv[0]) if sys.argv and sys.argv[0] else ""
  ) or "export_oracle_tables_template.py"

  lines = [
      "-- " + "=" * 77,
      "-- Oracle to Parquet Type-Safe Data Export Script",
      f"-- Generated by bigquery-migration-data-exporter / {generator_name}",
      "-- Execute via python-oracledb and stream results to Snappy Parquet",
      "-- " + "=" * 77,
      "",
  ]
  divider = "-- " + "-" * 77
  for t in tables:
    tbl = _strip(t.get("TableName"))
    raw_schema = _strip(t.get("TableSchema"))
    schema = raw_schema or _strip(default_schema)
    cols = _lookup_table_columns(by_schema_table, raw_schema, schema, tbl)
    stmt = _build_select_query(
        t,
        cols,
        default_schema or "",
        rtrim_char=rtrim_char,
        unbounded_number_scale=unbounded_number_scale,
    )
    label = _sanitize_comment_token(f"{schema}.{tbl}" if schema else tbl)
    lines.append(f"{divider}\n-- Unload Table: {label} -> Parquet\n{divider}")
    required = [
        _sanitize_comment_token(_strip(c.get("ColumnName")))
        for c in cols
        if _is_not_null(c) and _strip(c.get("ColumnName"))
    ]
    if required:
      lines.append(f"-- Required Columns: {','.join(required)}")
    lines.append(stmt + "\n")
  return "\n".join(lines)


# ==============================================================================
# 3. CLI Main Router (DEFAULT SCAFFOLDING)
# ==============================================================================
# DEFAULT SCAFFOLDING: CLI argument parser and SQL file writer entrypoint.


def _parse_args(args: list[str] | None = None) -> argparse.Namespace:
  """Builds and parses CLI arguments for Oracle export SQL generation."""
  parser = argparse.ArgumentParser(
      description="Oracle Parquet Export SQL Generator (outputs .sql)."
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
          " config directory, or Oracle extractor metadata.zip"
      ),
  )
  parser.add_argument(
      "--output-sql", help="File path to write the unified export SQL script"
  )
  parser.add_argument(
      "--output-dir",
      help="Directory to write individual per-table *_export.sql files",
  )
  parser.add_argument(
      "--default-schema",
      "--default-database",
      dest="default_schema",
      default=os.environ.get("ORACLE_SCHEMA", ""),
      help="Fallback source schema/owner name when omitted in metadata",
  )
  parser.add_argument(
      "--schema",
      "--database",
      action="append",
      dest="schemas",
      help=(
          "Only export tables in this schema/owner (repeatable); --database"
          " is an alias for the owner, not the Oracle service or PDB"
      ),
  )
  parser.add_argument(
      "--keep-char-padding",
      action="store_true",
      help="Do not RTRIM CHAR(n)/NCHAR(n) columns",
  )
  parser.add_argument(
      "--unbounded-number-scale",
      type=int,
      default=9,
      help=(
          "Decimal scale (0..38) for unconstrained NUMBER / NUMBER(*) columns"
          " (default: 9, supporting up to 29 integer digits)"
      ),
  )
  parsed = parser.parse_args(args)
  if not 0 <= parsed.unbounded_number_scale <= 38:
    parser.error("--unbounded-number-scale must be between 0 and 38.")
  return parsed


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
  chunks = sql.split(f"{divider}\n-- Unload Table: ")
  written: list[str] = []
  used_filenames: set[str] = set()
  for chunk in chunks[1:]:
    label = chunk.split(" -> Parquet")[0].strip()
    filename = _sanitize_sql_filename(label, used_filenames)
    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
      f.write(f"{divider}\n-- Unload Table: {chunk}")
    written.append(path)
    print(f"Generated table export SQL: {path}")
  return written


def main() -> None:
  """CLI entrypoint for the Oracle Parquet export SQL generator."""
  args = _parse_args()
  sql = generate_export_sql(
      metadata_path_or_uri=args.metadata_path,
      default_schema=args.default_schema,
      schemas=args.schemas,
      rtrim_char=not args.keep_char_padding,
      unbounded_number_scale=args.unbounded_number_scale,
  )
  if args.schemas and "-- Unload Table:" not in sql:
    sys.exit("ERROR: No tables to export; check --schema.")
  if args.output_sql:
    out_dir = os.path.dirname(os.path.abspath(args.output_sql))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.output_sql, "w", encoding="utf-8") as f:
      f.write(sql)
    print(f"Generated unified export SQL: {args.output_sql}")
  if args.output_dir:
    _write_table_sql_files(sql, args.output_dir)
  if not args.output_sql and not args.output_dir:
    print(sql)


if __name__ == "__main__":
  main()
