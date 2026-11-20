#!/usr/bin/env python3
r"""Template Script for Generating Type-Safe Teradata Export SQL Files.

This asset template script provides a reference implementation for generating
type-safe Teradata SELECT export scripts (.sql) directly from BQMS
translation_output/metadata configs or a Teradata extractor metadata.zip
(dbc.TablesV.csv / dbc.ColumnsV.csv). It has zero JDBC or database connector
dependencies.

Teradata has no native "unload to Parquet" statement (WRITE_NOS requires
Teradata 17.0+ with NOS configured, and FastExport emits text/binary files).
The export therefore happens in two steps:

  1. This script emits one explicit-cast SELECT per table. The casts pin every
     column to a type whose Parquet representation BigQuery loads without drift
     (BIGINT -> INT64, DECIMAL(p,s) -> NUMERIC/BIGNUMERIC, TIMESTAMP(6) ->
     TIMESTAMP/DATETIME, TIMESTAMP WITH TIME ZONE normalized to UTC, CHAR
     padding trimmed).
  2. A downstream Python execution script runs each SELECT via the
     `teradatasql` driver, derives the Arrow schema from the result-set
     metadata, and writes Snappy Parquet files under
     ./data_unload/[<DB>/]<TABLE>/.

Usage Pattern:
  Copy `assets/export_teradata_tables_template.py` from this skill's directory
  (`<SKILL_DIR>`, the directory containing `SKILL.md`) into your
  working directory (e.g., `./export_teradata_tables.py`). Run the copy as-is
  for standard export SQL generation, and prioritize modifying the marked
  `# CUSTOMIZE:` extension points if your environment requires custom type
  projections, row filters, or table filtering. Sections marked
  `# DEFAULT SCAFFOLDING` can be kept unchanged unless deeper orchestration
  adjustments are needed.

Dependencies:
  pip install pyyaml==6.0.2

Usage Examples:
    # Copy the template from this skill's directory to your working directory:
    cp <SKILL_DIR>/assets/export_teradata_tables_template.py \
        ./export_teradata_tables.py

    # 1. Generate per-table Teradata export SQL files from BQMS output:
    python3 ./export_teradata_tables.py \
        --translation-metadata-dir ./translated_output/metadata \
        --default-database my_db \
        --output-dir ./export_sql

    # 2. Generate a unified export SQL file straight from the extractor zip:
    python3 ./export_teradata_tables.py \
        --metadata-zip gs://my-bucket/metadata/dwh-migration-teradata-metadata.zip \
        --database my_db \
        --output-sql teradata_export.sql
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
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
  """Trims the fixed-width padding Teradata puts on dbc CHAR columns."""
  return (value or "").strip()


# Teradata dbc.TablesV.TableKind codes that hold exportable rows.
# T = table, O = table without primary index. Views (V), macros (M),
# procedures (P), join indexes (I), etc. are skipped.
_TERADATA_TABLE_KINDS = frozenset(("T", "O"))


def load_metadata_from_zip(
    zip_bytes: bytes,
) -> dict[str, list[dict[str, str]]]:
  """Extracts table and column metadata from a Teradata extractor metadata.zip.

  Reads dbc.TablesV.csv and dbc.ColumnsV.csv (falls back to the generic
  tables.csv / columns.csv layout) and normalizes rows to the shared
  TableCatalog/TableSchema/TableName/ColumnName/DataType record shape. Teradata
  has no catalog level, so TableCatalog is empty and the database is stored in
  TableSchema.

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

    tables_fn, table_rows = _rows(["dbc.TablesV.csv", "tables.csv"])
    columns_fn, column_rows = _rows(["dbc.ColumnsV.csv", "columns.csv"])

  if tables_fn == "dbc.TablesV.csv":
    for r in table_rows:
      kind = _strip(r.get("TableKind")).upper()
      result["tables"].append({
          "TableCatalog": "",
          "TableSchema": _strip(r.get("DataBaseName") or r.get("DatabaseName")),
          "TableName": _strip(r.get("TableName")),
          "TableType": "BASE TABLE" if kind in _TERADATA_TABLE_KINDS else kind,
      })
  else:
    result["tables"] = [
        {k: _strip(v) for k, v in r.items() if k is not None}
        for r in table_rows
    ]

  if columns_fn == "dbc.ColumnsV.csv":
    for r in column_rows:
      result["columns"].append({
          "TableCatalog": "",
          "TableSchema": _strip(r.get("DatabaseName") or r.get("DataBaseName")),
          "TableName": _strip(r.get("TableName")),
          "ColumnName": _strip(r.get("ColumnName")),
          # ColumnId is 1025-based per table; ordering is all that matters.
          "OrdinalPosition": _strip(r.get("ColumnId")),
          "DataType": _strip(r.get("ColumnType")).upper(),
          "ColumnLength": _strip(r.get("ColumnLength")),
          "NumericPrecision": _strip(r.get("DecimalTotalDigits")),
          "NumericScale": _strip(r.get("DecimalFractionalDigits")),
          "Nullable": _strip(r.get("Nullable")).upper() or "Y",
      })
  else:
    result["columns"] = [
        {k: _strip(v) for k, v in r.items() if k is not None}
        for r in column_rows
    ]

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

  for root, _, files in os.walk(config_dir):
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
      # Teradata names are DATABASE.TABLE; tolerate a leading catalog.
      schema = parts[-2] if len(parts) >= 2 else ""
      table = parts[-1] if parts else f.rsplit(".", 1)[0]

      is_view = not bool(
          cfg.get("externalTableName") or cfg.get("externalTableDdlPath")
      )
      result["tables"].append({
          "TableCatalog": "",
          "TableSchema": schema,
          "TableName": table,
          "TableType": "VIEW" if is_view else "BASE TABLE",
      })

      for idx, col in enumerate(cfg.get("columns") or [], start=1):
        if not isinstance(col, dict):
          continue
        src_type = col.get("sourceType") or {}
        tgt_type = col.get("targetType") or {}
        src = (
            src_type
            if isinstance(src_type, dict)
            else {"genericName": src_type}
        )
        tgt = tgt_type if isinstance(tgt_type, dict) else {"name": tgt_type}
        raw_code = str(src.get("name") or "").strip().upper()
        generic_name = str(src.get("genericName") or raw_code).strip().upper()
        if raw_code.startswith("NUMBER"):
          # Keep NUMBER(p): a precision-only DDL type means scale 0.
          data_type = raw_code
        elif raw_code == "N":
          data_type = "NUMBER"
        elif (
            _normalize_data_type(raw_code, None, None)[0]
            in _ALL_KNOWN_TERADATA_TYPES
        ):
          data_type = raw_code
        else:
          data_type = generic_name or raw_code
        result["columns"].append({
            "TableCatalog": "",
            "TableSchema": schema,
            "TableName": table,
            "ColumnName": col.get("sourceName", ""),
            "OrdinalPosition": str(idx),
            "DataType": data_type,
            "NumericPrecision": str(src.get("precision", "")),
            "NumericScale": str(src.get("scale", "")),
            "TargetType": str(tgt.get("name") or ""),
            "TargetPrecision": str(tgt.get("precision", "")),
            "TargetScale": str(tgt.get("scale", "")),
            "Nullable": "N" if col.get("notNull") else "Y",
        })

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
  """Resolves local or Cloud Storage metadata and loads metadata dicts."""
  if not path_or_uri:
    return {"tables": [], "columns": []}

  if path_or_uri.startswith("gs://"):
    if path_or_uri.endswith(".zip"):
      return load_metadata_from_zip(read_file_or_gcs(path_or_uri))
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
        col.get("TableSchema", "").upper(),
        col.get("TableName", "").upper(),
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
  """Finds a table's columns without borrowing them from another database.

  Tries the metadata database, then the --default-database fallback, then
  columns recorded without a database. A table without any database only
  matches a same-named table when exactly one candidate exists; otherwise it
  gets no column projections and falls back to SELECT *.

  Args:
    by_schema_table: Column metadata keyed by (database, table name).
    raw_schema: The database recorded in the metadata for this table.
    schema: The effective database after applying --default-database.
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
# custom database/table inclusion or exclusion rules.
def _filter_tables_to_export(
    raw_tables: list[dict[str, str]],
    columns_by_table: dict[str, list[dict[str, str]]],
    databases: set[str] | None = None,
    columns_by_schema_table: (
        dict[tuple[str, str], list[dict[str, str]]] | None
    ) = None,
    default_database: str = "",
) -> list[dict[str, str]]:
  """Filters tables to export: drops views/system objects, applies filters.

  The database allow-list and duplicate check use the effective
  database (TableSchema, else default_database), so database-less
  entries match --database and don't duplicate qualified entries.

  Args:
    raw_tables: Table rows from the metadata (may be empty).
    columns_by_table: Column metadata keyed by table name.
    databases: Optional upper-cased database allow-list.
    columns_by_schema_table: Column metadata keyed by (database, table name),
      used when raw_tables is empty.
    default_database: Fallback database for entries without a TableSchema.

  Returns:
    The table entries to export, without duplicates.
  """
  out: list[dict[str, str]] = []
  seen: set[tuple[str, str]] = set()
  default_db = _strip(default_database).upper()

  if raw_tables:
    for t in raw_tables:
      tbl = _strip(t.get("TableName")).upper()
      schema = _strip(t.get("TableSchema")).upper() or default_db
      tbl_type = _strip(t.get("TableType")).upper()
      if tbl_type and tbl_type != "BASE TABLE" and tbl_type != "TABLE":
        continue
      if databases and schema not in databases:
        continue
      if (schema, tbl) in seen:
        continue
      seen.add((schema, tbl))
      out.append(t)
  elif columns_by_schema_table:
    for raw_schema, tbl in columns_by_schema_table:
      schema = raw_schema or default_db
      if databases and schema not in databases:
        continue
      if (schema, tbl) not in seen:
        seen.add((schema, tbl))
        out.append({"TableSchema": raw_schema, "TableName": tbl})
  else:
    for tbl, cols in columns_by_table.items():
      raw_schema = _strip(cols[0].get("TableSchema")).upper() if cols else ""
      schema = raw_schema or default_db
      if databases and schema not in databases:
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

_VALID_IDENT_REGEX = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#]*$")

# Teradata reserved and restricted words (ANSI SQL and Teradata extensions)
# that can collide with column, table, or database names. Anything matching
# is double-quoted; Teradata names are not case-specific, so quoting a name
# never changes which object it resolves to.
_TERADATA_RESERVED = frozenset("""
    ABORT ABORTSESSION ABS ACCESS_LOCK ACCOUNT ACOS ACOSH ADD ADD_MONTHS ADMIN
    AFTER AGGREGATE ALL ALTER AMP AND ANSIDATE ANY AS ASC ASIN ASINH AT ATAN
    ATAN2 ATANH ATOMIC AUTHORIZATION AVE AVERAGE AVG BEFORE BEGIN BETWEEN
    BIGINT BINARY BLOB BOTH BT BUT BY BYTE BYTEINT BYTES CALL CASE
    CASESPECIFIC CASE_N CAST CD CHAR CHAR2HEXINT CHARACTER CHARACTERS
    CHARACTER_LENGTH CHARS CHAR_LENGTH CHECK CHECKPOINT CLASS CLOB CLOSE
    CLUSTER CM COALESCE COLLATION COLLECT COLUMN COMMENT COMMIT COMPRESS
    CONNECT CONSTRAINT CONSTRUCTOR CONSUME CONTAINS CONTINUE
    CONVERT_TABLE_HEADER CORR COS COSH COUNT COVAR_POP COVAR_SAMP CREATE CROSS
    CS CSUM CT CTCONTROL CUBE CURRENT CURRENT_DATE CURRENT_ROLE CURRENT_TIME
    CURRENT_TIMESTAMP CURRENT_USER CURSOR CV CYCLE DATABASE DATABLOCKSIZE DATE
    DATEFORM DAY DEALLOCATE DEC DECIMAL DECLARE DEFAULT DEFERRED DEGREES DEL
    DELETE DESC DETERMINISTIC DIAGNOSTIC DISABLED DISTINCT DO DOMAIN DOUBLE
    DROP DUAL DUMP DYNAMIC EACH ECHO ELSE ELSEIF ENABLED END EQ EQUALS ERROR
    ERRORFILES ERRORTABLES ESCAPE ET EXCEPT EXEC EXECUTE EXISTS EXIT EXP
    EXPAND EXPANDING EXPLAIN EXTERNAL EXTRACT FALLBACK FASTEXPORT FETCH FIRST
    FLOAT FOR FOREIGN FORMAT FOUND FREESPACE FROM FULL FUNCTION GE GENERATED
    GET GIVE GRANT GRAPHIC GROUP GROUPING GT HANDLER HASH HASHAMP HASHBAKAMP
    HASHBUCKET HASHROW HAVING HELP HOUR IDENTITY IF IMMEDIATE IN INCONSISTENT
    INDEX INITIATE INNER INOUT INPUT INS INSERT INSTANCE INSTEAD INT INTEGER
    INTEGERDATE INTERSECT INTERVAL INTO IS ITERATE JAR JOIN JOURNAL KEY
    KURTOSIS LANGUAGE LARGE LE LEADING LEAVE LEFT LEVEL LIKE LIMIT LN LOADING
    LOCAL LOCATOR LOCK LOCKING LOG LOGGING LOGON LONG LOOP LOWER LT MACRO MAP
    MAVG MAX MAXIMUM MCHARACTERS MDIFF MERGE METHOD MIN MINDEX MINIMUM MINUS
    MINUTE MLINREG MLOAD MOD MODE MODIFIES MODIFY MONITOR MONRESOURCE
    MONSESSION MONTH MSUBSTR MSUM MULTISET NAMED NATURAL NE NEW NEW_TABLE NEXT
    NO NONE NOT NOWAIT NULL NULLIF NULLIFZERO NUMERIC OBJECT OBJECTS
    OCTET_LENGTH OF OFF OLD OLD_TABLE ON ONLY OPEN OPTION OR ORDER ORDERING
    OUT OUTER OVER OVERLAPS OVERRIDE PARAMETER PASSWORD PERCENT PERCENT_RANK
    PERM PERMANENT POSITION PRECISION PREPARE PRESERVE PRIMARY PRIVILEGES
    PROCEDURE PROFILE PROTECTION PUBLIC QUALIFIED QUALIFY QUANTILE QUEUE
    RADIANS RANDOM RANGE_N RANK READS REAL RECURSIVE REFERENCES REFERENCING
    RELEASE RENAME REPEAT REPLACE REPLCONTROL REPLICATION REQUEST RESTART
    RESTORE RESULT RESUME RET RETRIEVE RETURN RETURNS REVALIDATE REVOKE RIGHT
    RIGHTS ROLE ROLLBACK ROLLFORWARD ROLLUP ROW ROWID ROWS ROW_NUMBER SAMPLE
    SAMPLEID SCROLL SECOND SEL SELECT SESSION SET SETRESRATE SETS SETSESSRATE
    SHOW SIN SINH SKEW SMALLINT SOME SOUNDEX SPECIFIC SPOOL SQL SQLEXCEPTION
    SQLTEXT SQLWARNING SQRT SS START STARTUP STATEMENT STATISTICS STDDEV_POP
    STDDEV_SAMP STEPINFO STRING_CS SUBSCRIBER SUBSTR SUBSTRING SUM SUMMARY
    SUSPEND TABLE TAN TANH TBL_CS TEMPORARY TERMINATE THEN THRESHOLD TIME
    TIMESTAMP TIMEZONE_HOUR TIMEZONE_MINUTE TITLE TO TOP TRACE TRAILING
    TRANSACTION TRANSACTIONTIME TRANSFORM TRANSLATE TRANSLATE_CHK TRIGGER TRIM
    TYPE UC UDTCASTAS UDTCASTLPAREN UDTMETHOD UDTTYPE UDTUSAGE UESCAPE
    UNDEFINED UNDO UNION UNIQUE UNTIL UNTIL_CHANGED UNTIL_CLOSED UPD UPDATE
    UPPER UPPERCASE USER USING VALIDTIME VALUE VALUES VARBYTE VARCHAR
    VARGRAPHIC VARIANT_TYPE VARYING VAR_POP VAR_SAMP VIEW VOLATILE WHEN WHERE
    WHILE WIDTH_BUCKET WITH WITHOUT WORK XMLPLAN YEAR ZEROIFNULL ZONE
""".split())

# dbc.ColumnsV.ColumnType codes (plus BQMS generic names) grouped by the
# projection they need. See "ColumnType" in the Teradata Data Dictionary.
_INT_TYPES = frozenset((
    "I1",
    "I2",
    "I",
    "I8",
    "BYTEINT",
    "TINYINT",
    "SMALLINT",
    "INTEGER",
    "INT",
    "BIGINT",
    "INT64",
))
_DECIMAL_TYPES = frozenset(("D", "DECIMAL", "NUMERIC", "BIGNUMERIC"))
_NUMBER_TYPES = frozenset(("N", "NUMBER"))
_FLOAT_TYPES = frozenset((
    "F",
    "FLOAT",
    "REAL",
    "DOUBLE",
    "DOUBLE PRECISION",
    "FLOAT64",
))
_DATE_TYPES = frozenset(("DA", "DATE"))
_TIME_TYPES = frozenset(("AT", "TIME"))
_TIME_TZ_TYPES = frozenset(("TZ", "TIMETZ", "TIME WITH TIME ZONE"))
_TIMESTAMP_TYPES = frozenset(("TS", "TIMESTAMP", "DATETIME"))
_TIMESTAMP_TZ_TYPES = frozenset((
    "SZ",
    "TIMESTAMPTZ",
    "TIMESTAMP WITH TIME ZONE",
))
_CHAR_TYPES = frozenset(("CF", "GF", "CHAR", "CHARACTER", "GRAPHIC"))
_VARCHAR_TYPES = frozenset((
    "CV",
    "GV",
    "VARCHAR",
    "CHARACTER VARYING",
    "CHAR VARYING",
    "LONG VARCHAR",
    "VARGRAPHIC",
    "STRING",
    "CO",
    "CLOB",
))
_BYTE_TYPES = frozenset((
    "BF",
    "BV",
    "BO",
    "BYTE",
    "VARBYTE",
    "BINARY",
    "VARBINARY",
    "BLOB",
    "BYTES",
))
_JSON_TYPES = frozenset(("JN", "JSON"))
_PERIOD_TYPES = frozenset((
    "PD",
    "PT",
    "PZ",
    "PS",
    "PM",
    "PERIOD_DATE",
    "PERIOD_TIME",
    "PERIOD_TIMETZ",
    "PERIOD_TIMESTAMP",
    "PERIOD_TIMESTAMPTZ",
))
_INTERVAL_TYPES = frozenset((
    "YR",
    "YM",
    "MO",
    "DY",
    "DH",
    "DM",
    "DS",
    "HR",
    "HM",
    "HS",
    "MI",
    "MS",
    "SC",
    "INTERVAL",
))
_DBC_COLUMN_TYPE_CODES = frozenset((
    "I1",
    "I2",
    "I",
    "I8",
    "D",
    "N",
    "F",
    "DA",
    "AT",
    "TZ",
    "TS",
    "SZ",
    "CF",
    "CV",
    "CO",
    "GF",
    "GV",
    "BF",
    "BV",
    "BO",
    "JN",
    "XM",
    "PD",
    "PT",
    "PZ",
    "PS",
    "PM",
    "YR",
    "YM",
    "MO",
    "DY",
    "DH",
    "DM",
    "DS",
    "HR",
    "HM",
    "HS",
    "MI",
    "MS",
    "SC",
    "A1",
    "AN",
    "UT",
    "DT",
))
_ALL_KNOWN_TERADATA_TYPES = (
    _DBC_COLUMN_TYPE_CODES
    | _INT_TYPES
    | _DECIMAL_TYPES
    | _NUMBER_TYPES
    | _FLOAT_TYPES
    | _DATE_TYPES
    | _TIME_TYPES
    | _TIME_TZ_TYPES
    | _TIMESTAMP_TYPES
    | _TIMESTAMP_TZ_TYPES
    | _CHAR_TYPES
    | _VARCHAR_TYPES
    | _BYTE_TYPES
    | _JSON_TYPES
    | _PERIOD_TYPES
    | _INTERVAL_TYPES
)


# DEFAULT SCAFFOLDING: Identifier quoting helper.
def quote_ident(ident: str) -> str:
  """Double-quotes a Teradata identifier when it is not a plain name.

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
  if not _VALID_IDENT_REGEX.match(ident) or ident.upper() in _TERADATA_RESERVED:
    escaped = ident.replace('"', '""')
    return f'"{escaped}"'
  return ident


_PARAM_TYPE_REGEX = re.compile(
    r"^(?P<base>[A-Z0-9_ ]+?)\s*\(\s*(?P<p>-?\d+|\*)"
    r"(?:\s*,\s*(?P<s>-?\d+))?\s*\)\s*(?P<rest>.*)$"
)
_COLUMN_ATTR_REGEX = re.compile(
    r"\s+(?:CHARACTER\s+SET\s+\S+|(?:NOT\s+)?CASESPECIFIC|UPPERCASE"
    r"|UNICODE|LATIN|KANJISJIS)\b"
)


def _to_int(value: str | None) -> int | None:
  value = str(value or "").strip()
  return int(value) if value.lstrip("-").isdigit() else None


def _normalize_data_type(
    raw_type: str, precision: int | None, scale: int | None
) -> tuple[str, int | None, int | None]:
  """Normalizes a Teradata type code or DDL string into (base_type, p, s)."""
  dt = " ".join(raw_type.upper().split())
  dt = _COLUMN_ATTR_REGEX.sub("", dt).strip()
  if dt.startswith("PERIOD") and "(" in dt:
    return (
        "PERIOD_TIMESTAMP" if "TIMESTAMP" in dt else "PERIOD_DATE",
        precision,
        scale,
    )
  if dt.startswith("INTERVAL "):
    return "INTERVAL", precision, scale
  m = _PARAM_TYPE_REGEX.match(dt)
  if m:
    rest = m.group("rest").strip()
    tz_suffix = " WITH TIME ZONE" if "TIME ZONE" in rest else ""
    base = f"{m.group('base').strip()}{tz_suffix}".strip()
    if precision is None and m.group("p") != "*":
      precision = _to_int(m.group("p"))
    if scale is None and m.group("s") is not None:
      scale = _to_int(m.group("s"))
    return base, precision, scale
  return dt, precision, scale


# CUSTOMIZE: Custom Type Projections — Edit format_column_cast() to change how
# a Teradata type is projected before Parquet serialization (e.g. keep CHAR
# padding, map PERIOD to BEGIN()/END() pairs, or widen DECIMAL precision).
def format_column_cast(
    col: dict[str, str],
    target_bq_type: str | None = None,
    rtrim_char: bool = True,
    unbounded_number_scale: int = 9,
) -> str:
  """Generates a type-safe Teradata projection expression for Parquet export.

  The executor derives the Parquet schema from the result-set metadata, so the
  CAST here is what decides the BigQuery column type:

    BYTEINT/SMALLINT/INTEGER/BIGINT -> CAST AS BIGINT   -> INT64
    DECIMAL(p,s)                    -> CAST AS DECIMAL  -> NUMERIC/BIGNUMERIC
    NUMBER(*)                       -> DECIMAL(38,9)    -> NUMERIC/BIGNUMERIC
    FLOAT/REAL/DOUBLE               -> CAST AS FLOAT    -> FLOAT64
    DATE                            -> CAST AS DATE     -> DATE
    TIME(n)                         -> CAST AS TIME(6)  -> TIME
    TIME(n) WITH TIME ZONE          -> UTC TIME(6)      -> TIME
    TIMESTAMP(n)                    -> TIMESTAMP(6)     -> TIMESTAMP
    TIMESTAMP(n) WITH TIME ZONE     -> UTC TIMESTAMP(6) -> TIMESTAMP
    CHAR(n)                         -> TRIM(TRAILING)   -> STRING
    VARCHAR / CLOB                  -> col              -> STRING
    BYTE / VARBYTE / BLOB           -> col              -> BYTES
    JSON                            -> CAST AS CLOB     -> STRING
    PERIOD                          -> VARCHAR(100)     -> STRING
    INTERVAL                        -> TRIM(VARCHAR)    -> STRING

  Args:
    col: Column metadata dict containing ColumnName, DataType, etc.
    target_bq_type: Optional BigQuery target type override.
    rtrim_char: Strip CHAR(n) trailing pad spaces (BigQuery STRING has no
      fixed-width semantics, so padded values would mismatch in validation).
    unbounded_number_scale: Fractional scale for unbounded NUMBER / NUMBER(*)
      columns (default 9, supporting up to 29 integer digits).

  Returns:
    A SQL projection expression, e.g. 'CAST(ss_item_sk AS BIGINT) AS
    ss_item_sk'.
  """
  col_name = quote_ident(_strip(col.get("ColumnName")))
  data_type, precision, scale = _normalize_data_type(
      str(col.get("DataType") or ""),
      _to_int(col.get("NumericPrecision")),
      _to_int(col.get("NumericScale")),
  )
  target_raw = (target_bq_type or col.get("TargetType") or "").upper().strip()
  target = re.split(r"[(<]", target_raw, maxsplit=1)[0].strip()

  # BQMS target types win when present: they are what the BigQuery DDL uses.
  # Other cross-type targets (STRING / JSON on non-text columns, BYTES, BOOL)
  # keep the default projection below.
  if target:
    if target in (
        "INT64",
        "INTEGER",
        "BIGINT",
        "SMALLINT",
        "TINYINT",
        "BYTEINT",
    ):
      return f"CAST({col_name} AS BIGINT) AS {col_name}"
    if target in ("FLOAT64", "FLOAT", "DOUBLE"):
      return f"CAST({col_name} AS FLOAT) AS {col_name}"
    if target == "DATE":
      return f"CAST({col_name} AS DATE) AS {col_name}"
    if target in ("TIMESTAMP", "DATETIME"):
      return (
          f"CAST(({col_name} AT TIME ZONE 'GMT') AS TIMESTAMP(6)) AS {col_name}"
          if data_type in _TIMESTAMP_TZ_TYPES
          else f"CAST({col_name} AS TIMESTAMP(6)) AS {col_name}"
      )
    if target in ("NUMERIC", "BIGNUMERIC", "DECIMAL") and (
        data_type not in _DECIMAL_TYPES and data_type not in _NUMBER_TYPES
    ):
      tgt_p = precision or _to_int(col.get("TargetPrecision"))
      tgt_s = scale if scale is not None else _to_int(col.get("TargetScale"))
      if tgt_p and 0 < tgt_p <= 38:
        p_val = tgt_p
      elif data_type in _INT_TYPES and target != "BIGNUMERIC":
        # BigQuery NUMERIC (alias DECIMAL) holds at most 29 integer digits.
        p_val = 29
      else:
        p_val = 38
      if tgt_s is not None and 0 <= tgt_s <= p_val:
        s_val = tgt_s
      else:
        s_val = 0 if data_type in _INT_TYPES else min(9, p_val)
      return f"CAST({col_name} AS DECIMAL({p_val},{s_val})) AS {col_name}"
    if target == "TIME":
      if data_type in _TIMESTAMP_TZ_TYPES or data_type in _TIME_TZ_TYPES:
        return f"CAST(({col_name} AT TIME ZONE 'GMT') AS TIME(6)) AS {col_name}"
      return f"CAST({col_name} AS TIME(6)) AS {col_name}"

  if data_type in _INT_TYPES:
    return f"CAST({col_name} AS BIGINT) AS {col_name}"

  if 0 <= unbounded_number_scale <= 38:
    default_unb_scale = unbounded_number_scale
  else:
    logging.warning(
        "Out-of-range unbounded_number_scale=%d (expected 0..38); falling back"
        " to 9.",
        unbounded_number_scale,
    )
    default_unb_scale = 9

  if data_type in _NUMBER_TYPES:
    # BQMS YAML configs record unconstrained NUMBER as precision 38 without a
    # scale; keep its fractional digits (TargetScale, else the unbounded
    # scale) unless the DDL type itself is NUMBER(p), which means scale 0.
    explicit_p_only = re.search(
        r"\(\s*\d+\s*\)", str(col.get("DataType") or "")
    )
    if scale is None and precision and not explicit_p_only:
      s_val = _to_int(col.get("TargetScale"))
      if s_val is None or not 0 <= s_val <= 38:
        s_val = default_unb_scale
      return f"CAST({col_name} AS DECIMAL(38,{s_val})) AS {col_name}"
    # NUMBER / NUMBER(*) report precision -128 or (40, 0) in dbc.ColumnsV.
    if precision and 0 < precision <= 38:
      s_val = scale if scale is not None and 0 <= scale <= precision else 0
      return f"CAST({col_name} AS DECIMAL({precision},{s_val})) AS {col_name}"
    if precision == 40 and scale == 0:
      s_val = default_unb_scale
    else:
      s_val = (
          scale if scale is not None and 0 <= scale <= 38 else default_unb_scale
      )
    return f"CAST({col_name} AS DECIMAL(38,{s_val})) AS {col_name}"

  if data_type in _DECIMAL_TYPES:
    if precision and precision < 0:
      return (
          f"CAST({col_name} AS DECIMAL(38,{default_unb_scale})) AS {col_name}"
      )
    p_val = precision if precision and 0 < precision <= 38 else 38
    s_val = scale if scale is not None and 0 <= scale <= p_val else 0
    return f"CAST({col_name} AS DECIMAL({p_val},{s_val})) AS {col_name}"

  if data_type in _FLOAT_TYPES:
    return f"CAST({col_name} AS FLOAT) AS {col_name}"

  if data_type in _DATE_TYPES:
    return f"CAST({col_name} AS DATE) AS {col_name}"

  if data_type in _TIME_TYPES:
    return f"CAST({col_name} AS TIME(6)) AS {col_name}"

  if data_type in _TIME_TZ_TYPES:
    return f"CAST(({col_name} AT TIME ZONE 'GMT') AS TIME(6)) AS {col_name}"

  if data_type in _TIMESTAMP_TYPES:
    return f"CAST({col_name} AS TIMESTAMP(6)) AS {col_name}"

  if data_type in _TIMESTAMP_TZ_TYPES:
    return (
        f"CAST(({col_name} AT TIME ZONE 'GMT') AS TIMESTAMP(6)) AS {col_name}"
    )

  if data_type in _CHAR_TYPES:
    if rtrim_char:
      return f"TRIM(TRAILING FROM {col_name}) AS {col_name}"
    return f"{col_name} AS {col_name}"

  if data_type in _VARCHAR_TYPES or data_type in _BYTE_TYPES:
    return f"{col_name} AS {col_name}"

  if data_type in _JSON_TYPES:
    return f"CAST({col_name} AS CLOB) AS {col_name}"

  if data_type in _PERIOD_TYPES:
    return f"CAST({col_name} AS VARCHAR(100)) AS {col_name}"

  if data_type in _INTERVAL_TYPES:
    return f"TRIM(CAST({col_name} AS VARCHAR(100))) AS {col_name}"

  # XML, ST_GEOMETRY, UDTs, etc. (32000 fits both LATIN and UNICODE VARCHAR)
  return f"CAST({col_name} AS VARCHAR(32000)) AS {col_name}"


# DEFAULT SCAFFOLDING: Table name qualification helper.
def _build_qualified_table_name(
    table_meta: dict[str, str], default_database: str = ""
) -> str:
  """Builds a quoted DATABASE.TABLE name."""
  tbl = _strip(table_meta.get("TableName"))
  db = _strip(table_meta.get("TableSchema")) or _strip(default_database)
  return f"{quote_ident(db)}.{quote_ident(tbl)}" if db else quote_ident(tbl)


# CUSTOMIZE: Row Filters — Edit _build_select_query() to add WHERE predicates
# (e.g. incremental extraction windows) or LOCKING modifiers.
def _build_select_query(
    table_meta: dict[str, str],
    columns: list[dict[str, str]],
    default_database: str = "",
    rtrim_char: bool = True,
    unbounded_number_scale: int = 9,
) -> str:
  """Builds the explicit-cast SELECT statement for a single table.

  LOCKING ROW FOR ACCESS allows dirty reads so the export never blocks (or is
  blocked by) concurrent writers; drop it if a consistent snapshot matters more.

  Args:
    table_meta: Table metadata dictionary with TableSchema and TableName.
    columns: Ordered list of column metadata dictionaries for the table.
    default_database: Fallback database name when TableSchema is empty.
    rtrim_char: Whether to TRIM(TRAILING) fixed-width CHAR(n) columns.
    unbounded_number_scale: Fractional scale for unbounded NUMBER columns.

  Returns:
    A complete Teradata SELECT statement ending with a semicolon.
  """
  qualified = _build_qualified_table_name(table_meta, default_database)
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
  return f"LOCKING ROW FOR ACCESS\nSELECT\n{body}\nFROM {qualified};"


def _sanitize_comment_token(value: str) -> str:
  """Replaces control characters so SQL line comments stay single-line."""
  return re.sub(r"[\x00-\x1f\x7f]+", " ", str(value)).strip()


# DEFAULT SCAFFOLDING: Primary SQL script generator and orchestration.
def generate_export_sql(
    metadata_path_or_uri: str | None = None,
    default_database: str | None = None,
    databases: list[str] | None = None,
    rtrim_char: bool = True,
    unbounded_number_scale: int = 9,
) -> str:
  """Generates the unified Teradata export SQL script.

  Each table section is introduced by a divider and a
  `-- Unload Table: <DB>.<TABLE> -> Parquet` marker that the executor uses to
  name the ./data_unload/[<DB>/]<TABLE>/ output directory.

  Args:
    metadata_path_or_uri: Path or Cloud Storage URI to translation metadata dir
      or zip.
    default_database: Fallback database when metadata omits it.
    databases: Optional database allow-list (case-insensitive).
    rtrim_char: Strip CHAR(n) trailing pad spaces.
    unbounded_number_scale: Fractional scale for unbounded NUMBER columns.

  Returns:
    A complete Teradata SQL script string.
  """
  metadata = _resolve_and_load_metadata(metadata_path_or_uri)
  by_schema_table, by_table = _group_and_sort_columns(
      metadata.get("columns", [])
  )
  db_filter = {d.upper() for d in databases} if databases else None
  tables = _filter_tables_to_export(
      metadata.get("tables", []),
      by_table,
      db_filter,
      columns_by_schema_table=by_schema_table,
      default_database=default_database or "",
  )
  if not tables and db_filter:
    rows = metadata.get("tables", []) or metadata.get("columns", [])
    available = sorted({_strip(t.get("TableSchema")) for t in rows} - {""})
    print(
        "WARNING: No tables match the --database filter. Available databases:"
        f" {', '.join(available) or '(none)'}.",
        file=sys.stderr,
    )
  generator_name = (
      os.path.basename(sys.argv[0]) if sys.argv and sys.argv[0] else ""
  ) or "export_teradata_tables_template.py"

  lines = [
      "-- " + "=" * 77,
      "-- Teradata to Parquet Type-Safe Data Export Script",
      f"-- Generated by bigquery-migration-data-exporter / {generator_name}",
      "-- Execute via teradatasql and stream results to Snappy Parquet",
      "-- " + "=" * 77,
      "",
  ]
  divider = "-- " + "-" * 77
  for t in tables:
    tbl = _strip(t.get("TableName"))
    raw_schema = _strip(t.get("TableSchema"))
    schema = raw_schema or _strip(default_database)
    cols = _lookup_table_columns(
        by_schema_table, raw_schema.upper(), schema.upper(), tbl.upper()
    )
    stmt = _build_select_query(
        t,
        cols,
        default_database or "",
        rtrim_char=rtrim_char,
        unbounded_number_scale=unbounded_number_scale,
    )
    label = _sanitize_comment_token(f"{schema}.{tbl}" if schema else tbl)
    lines.append(f"{divider}\n-- Unload Table: {label} -> Parquet\n{divider}")
    required = [
        _sanitize_comment_token(_strip(c.get("ColumnName")))
        for c in cols
        if _strip(c.get("Nullable") or "Y").upper() == "N"
        and _strip(c.get("ColumnName"))
    ]
    if required:
      # Consumed by the executor: marks these Parquet fields REQUIRED so they
      # load into the translated NOT NULL BigQuery columns.
      lines.append(f"-- Required Columns: {','.join(required)}")
    lines.append(stmt + "\n")
  return "\n".join(lines)


# ==============================================================================
# 3. CLI Main Router (DEFAULT SCAFFOLDING)
# ==============================================================================
# DEFAULT SCAFFOLDING: CLI argument parser and SQL file writer entrypoint.


def _parse_args(args: list[str] | None = None) -> argparse.Namespace:
  """Builds and parses CLI arguments for Teradata export SQL generation."""
  parser = argparse.ArgumentParser(
      description="Teradata Parquet Export SQL Generator (outputs .sql)."
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
          " config directory, or Teradata extractor metadata.zip"
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
      "--default-database",
      default=os.environ.get("TERADATA_DATABASE", ""),
      help="Fallback source database name when omitted in metadata",
  )
  parser.add_argument(
      "--database",
      action="append",
      dest="databases",
      help="Only export tables in this database (repeatable)",
  )
  parser.add_argument(
      "--keep-char-padding",
      action="store_true",
      help="Do not TRIM(TRAILING) CHAR(n) columns",
  )
  parser.add_argument(
      "--unbounded-number-scale",
      type=int,
      default=9,
      help=(
          "Decimal scale (0..38) for unbounded NUMBER / NUMBER(*) columns"
          " (default: 9, supporting up to 29 integer digits; 38 - scale"
          " integer digits; scale=38 leaves 0 integer digits)"
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
  """CLI entrypoint for the Teradata Parquet export SQL generator."""
  args = _parse_args()
  sql = generate_export_sql(
      metadata_path_or_uri=args.metadata_path,
      default_database=args.default_database,
      databases=args.databases,
      rtrim_char=not args.keep_char_padding,
      unbounded_number_scale=args.unbounded_number_scale,
  )
  if args.databases and "-- Unload Table:" not in sql:
    sys.exit("ERROR: No tables to export; check --database.")
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
