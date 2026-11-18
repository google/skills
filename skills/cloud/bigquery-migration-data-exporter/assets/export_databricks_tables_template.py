#!/usr/bin/env python3
r"""Template Script for Generating Databricks/Spark SQL Parquet Export SQL.

This asset template script provides a reference implementation for generating
type-safe Databricks / Spark SQL Parquet export scripts (.sql) from BQMS
translation_output/metadata configs, schema DDLs, or metadata archives. It
supports both:
  1. `insert_overwrite` mode (`INSERT OVERWRITE DIRECTORY ... USING PARQUET
     OPTIONS ('compression' = 'snappy') SELECT ...`) for cloud storage URIs,
     Unity Catalog Volumes, or Spark Thrift Servers.
  2. `select` mode (explicit-cast `SELECT ... FROM ...;` with `-- Unload Table:`
     markers) for streaming Arrow/Parquet directly from Databricks SQL
     Warehouses via `databricks-sql-connector`.
Note: Downstream Databricks SQL Warehouse execution scripts can run EITHER
format (extracting the inner `SELECT` and streaming Arrow/Parquet batches when
an `INSERT OVERWRITE DIRECTORY` targets a local filesystem path).

Usage Pattern:
  Copy `assets/export_databricks_tables_template.py` from this skill's directory
  (`<SKILL_DIR>`, the directory containing `SKILL.md`) into your
  working directory (e.g., `./export_databricks_tables.py`). Run the copy as-is
  for standard export SQL generation, and prioritize modifying the marked
  `# CUSTOMIZE:` extension points if your environment requires custom type
  projections, stage options, or table filtering. Sections marked
  `# DEFAULT SCAFFOLDING` can be kept unchanged unless deeper orchestration
  adjustments are needed.

Dependencies:
  pip install pyyaml==6.0.2

Usage Examples:
    cp <SKILL_DIR>/assets/export_databricks_tables_template.py \
        ./export_databricks_tables.py

    # 1. Generate a unified Databricks Parquet export SQL file:
    python3 ./export_databricks_tables.py \
        --translation-metadata-dir ./translated_output/metadata \
        --stage-path '/tmp/databricks_export' \
        --output-sql databricks_export.sql

    # 2. Generate per-table Databricks Parquet export SQL files in a directory:
    python3 ./export_databricks_tables.py \
        --translation-metadata-dir ./translated_output/metadata \
        --stage-path '/tmp/databricks_export' \
        --output-dir ./export_sql
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any
import zipfile

import yaml


# ==============================================================================
# 1. File & Metadata Discovery Helpers (DEFAULT SCAFFOLDING)
# ==============================================================================
# DEFAULT SCAFFOLDING: Deterministic file reading and metadata discovery.

_SQL_TABLE_REGEX = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?TABLE\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?([^\s\(\;]+)",
    re.IGNORECASE,
)
_VALID_IDENT_REGEX = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PARAM_TYPE_REGEX = re.compile(
    r"^(?P<base>[A-Za-z0-9_]+)\s*\(\s*(?P<p>\d+)(?:\s*,\s*(?P<s>\d+))?\s*\)$"
)


def read_file_or_gcs(path_or_uri: str) -> bytes:
  """Reads content from a local file path or a Cloud Storage URI.

  Args:
    path_or_uri: Local file path or Cloud Storage URI (starts with 'gs://').

  Returns:
    The raw file content as bytes.

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


# DEFAULT SCAFFOLDING: Metadata directory resolution and YAML/SQL parsers.
def _resolve_metadata_dir(path_or_uri: str) -> tuple[str, str | None]:
  """Downloads Cloud Storage metadata if needed; returns (dir, temp_dir)."""
  if path_or_uri.startswith("gs://"):
    temp_dir = tempfile.mkdtemp(prefix="bqms_db_meta_")
    if path_or_uri.endswith((".zip", ".yaml", ".yml")):
      local_file = os.path.join(temp_dir, os.path.basename(path_or_uri))
      with open(local_file, "wb") as f:
        f.write(read_file_or_gcs(path_or_uri))
      return temp_dir, temp_dir
    cmd = [
        "gcloud",
        "storage",
        "cp",
        "-r",
        path_or_uri.rstrip("/") + "/*",
        temp_dir,
    ]
    _run_gcloud_copy(cmd, path_or_uri)
    return temp_dir, temp_dir
  if not os.path.exists(path_or_uri):
    # Only a missing `.../metadata` leaf falls back to its parent (for
    # example `translated_output/metadata` when the sibling layout is
    # used); any other missing path is a typo, not a directory to scan.
    trimmed = path_or_uri.rstrip("/")
    parent = os.path.dirname(trimmed)
    if (
        os.path.basename(trimmed).lower() == "metadata"
        and parent
        and os.path.isdir(parent)
    ):
      return parent, None
    raise FileNotFoundError(f"Metadata path not found: '{path_or_uri}'")
  return path_or_uri, None


def _find_config_dir(dir_to_scan: str) -> str:
  """Identifies the config directory containing table YAMLs."""
  config_dir = os.path.join(dir_to_scan, "metadata", "config")
  if not os.path.isdir(config_dir) and os.path.isdir(
      os.path.join(dir_to_scan, "config")
  ):
    return os.path.join(dir_to_scan, "config")
  elif not os.path.isdir(config_dir):
    return dir_to_scan
  return config_dir


# Placeholder catalog names that BQMS or Spark emit for the session catalog.
_PLACEHOLDER_CATALOGS = frozenset(("__default_database__", "spark_catalog"))


def _real_catalog(name: str) -> str:
  """Returns the catalog name, or '' for a session-catalog placeholder."""
  name = name.strip()
  return "" if name.lower() in _PLACEHOLDER_CATALOGS else name


def _warn_duplicate_table(name: str, source: str) -> None:
  """Warns that a schema.table already discovered was skipped."""
  # Generated SQL is 2-part (catalog-agnostic) unless --catalog is set, so a
  # same-named table from another catalog can't be exported alongside.
  print(
      f"WARNING: Skipping duplicate table {name} in {source};"
      " pass --catalog to choose which catalog to export.",
      file=sys.stderr,
  )


_VIEW_TABLE_TYPES = frozenset(
    ("VIEW", "VIRTUAL_VIEW", "MATERIALIZED_VIEW", "METRIC_VIEW")
)


def _parse_yaml_file(
    fpath: str,
    seen: set[tuple[str, str]],
    discovered: list[dict[str, Any]],
    catalog: str | None = None,
) -> None:
  """Parses a single BQMS config YAML file.

  Args:
    fpath: Path to the YAML file.
    seen: Lower-cased (schema, table) keys already discovered.
    discovered: List that new table entries are appended to.
    catalog: Optional --catalog filter. Tables whose 3-part sourceName names a
      different (non-placeholder) catalog are skipped.
  """
  try:
    with open(fpath, "r", encoding="utf-8") as yf:
      cfg = yaml.safe_load(yf)
  except (yaml.YAMLError, OSError):
    return

  if not isinstance(cfg, dict):
    return

  table_type = (
      str(cfg.get("TableType") or cfg.get("tableType") or "").strip().upper()
  )
  is_view = table_type in _VIEW_TABLE_TYPES or not bool(
      cfg.get("externalTableName") or cfg.get("externalTableDdlPath")
  )
  if is_view:
    return

  src_name = cfg.get("sourceName", "")
  parts = src_name.split(".") if src_name else []
  if len(parts) >= 2:
    schema = parts[-2]
    table = parts[-1]
  else:
    schema = "default"
    table = parts[0] if parts else os.path.basename(fpath).rsplit(".", 1)[0]
  src_catalog = _real_catalog(parts[-3]) if len(parts) >= 3 else ""
  if catalog and src_catalog and src_catalog.lower() != catalog.lower():
    return

  cols: list[dict[str, str]] = []
  for col in cfg.get("columns") or []:
    if not isinstance(col, dict):
      continue
    col_name = str(col.get("sourceName") or "")
    # `sourceType: null` / `targetType: null` load as None; treat them as empty
    # instead of the literal string "None".
    src_type = col.get("sourceType") or {}
    tgt_type = col.get("targetType") or {}
    # `genericName: null` or a missing genericName falls back to the source
    # `name`, so the column still gets a type-specific cast.
    gen_name = (
        str(src_type.get("genericName") or src_type.get("name") or "STRING")
        if isinstance(src_type, dict)
        else str(src_type)
    )
    precision = (
        str(src_type.get("precision", ""))
        if isinstance(src_type, dict) and src_type.get("precision") is not None
        else ""
    )
    scale = (
        str(src_type.get("scale", ""))
        if isinstance(src_type, dict) and src_type.get("scale") is not None
        else ""
    )
    tgt_name = (
        str(tgt_type.get("name") or "")
        if isinstance(tgt_type, dict)
        else str(tgt_type)
    )
    if col_name:
      cols.append({
          "ColumnName": col_name,
          "DataType": gen_name,
          "NumericPrecision": precision,
          "NumericScale": scale,
          "TargetType": tgt_name,
      })

  key = (schema.lower(), table.lower())
  if key in seen:
    _warn_duplicate_table(src_name or table, fpath)
    return
  seen.add(key)
  discovered.append({"schema": schema, "table": table, "columns": cols})


def _yaml_catalogs(config_dir: str) -> set[str]:
  """Returns the catalogs named by 3-part sourceName values of table YAMLs."""
  catalogs: set[str] = set()
  paths: list[str] = []
  if os.path.isfile(config_dir) and config_dir.endswith((".yaml", ".yml")):
    paths.append(config_dir)
  elif os.path.isdir(config_dir):
    for root, _, files in os.walk(config_dir):
      paths.extend(
          os.path.join(root, f) for f in files if f.endswith((".yaml", ".yml"))
      )
  for path in paths:
    try:
      with open(path, "r", encoding="utf-8") as yf:
        cfg = yaml.safe_load(yf)
    except (yaml.YAMLError, OSError, UnicodeDecodeError):
      continue
    if not isinstance(cfg, dict):
      continue
    if not (cfg.get("externalTableName") or cfg.get("externalTableDdlPath")):
      continue
    parts = str(cfg.get("sourceName") or "").split(".")
    if len(parts) >= 3 and _real_catalog(parts[-3]):
      catalogs.add(_real_catalog(parts[-3]))
  return catalogs


def _parse_tables_from_yaml_configs(
    config_dir: str, catalog: str | None = None
) -> list[dict[str, Any]]:
  """Parses table configurations from YAML metadata files."""
  discovered: list[dict[str, Any]] = []
  seen: set[tuple[str, str]] = set()

  if os.path.isfile(config_dir) and (
      config_dir.endswith(".yaml") or config_dir.endswith(".yml")
  ):
    _parse_yaml_file(config_dir, seen, discovered, catalog=catalog)
    return discovered

  if not os.path.isdir(config_dir):
    return discovered

  for root, dirs, files in os.walk(config_dir):
    dirs.sort()  # Deterministic order, so the first catalog wins.
    for f in sorted(files):
      if f.endswith(".yaml") or f.endswith(".yml"):
        _parse_yaml_file(
            os.path.join(root, f), seen, discovered, catalog=catalog
        )

  return discovered


def _extract_tables_from_sql_text(
    sql_text: str,
    seen: set[tuple[str, str]],
    discovered: list[dict[str, Any]],
) -> None:
  """Extracts schema and table pairs from SQL CREATE TABLE statements."""
  for match in _SQL_TABLE_REGEX.finditer(sql_text):
    raw_target = match.group(1).strip()
    parts = [p.strip().strip("`").strip('"') for p in raw_target.split(".")]
    schema = parts[-2] if len(parts) >= 2 else "default"
    table = parts[-1] if len(parts) >= 2 else parts[0]
    key = (schema.lower(), table.lower())
    if key not in seen:
      seen.add(key)
      discovered.append({"schema": schema, "table": table, "columns": []})


def _zip_view_keys(
    zf: zipfile.ZipFile, by_base: dict[str, str]
) -> set[tuple[str, str, str]]:
  """Returns lower-cased (catalog, schema, table) keys of views in a zip.

  The Databricks extractor records TableType in tables.csv (and lists views in
  views.csv); columns.csv has rows for both tables and views.

  Args:
    zf: The open metadata zip archive.
    by_base: The archive's entry names keyed by lower-cased basename.

  Returns:
    The set of view keys, with session-catalog placeholders as ''.
  """
  keys: set[tuple[str, str, str]] = set()
  for entry in ("tables.csv", "views.csv"):
    if entry not in by_base:
      continue
    text = zf.read(by_base[entry]).decode("utf-8-sig", errors="replace")
    for row in csv.DictReader(io.StringIO(text)):
      table_type = (row.get("TableType") or "").strip().upper()
      if entry == "tables.csv" and table_type not in _VIEW_TABLE_TYPES:
        continue
      keys.add((
          _real_catalog(row.get("TableCatalog") or "").lower(),
          (row.get("TableSchema") or "default").strip().lower(),
          (row.get("TableName") or "").strip().lower(),
      ))
  return keys


def _extract_tables_from_zip(
    zf: zipfile.ZipFile,
    seen: set[tuple[str, str]],
    discovered: list[dict[str, Any]],
    catalog: str | None = None,
    skipped_catalogs: set[str] | None = None,
) -> None:
  """Extracts tables and columns from a metadata zip archive.

  Args:
    zf: The open metadata zip archive.
    seen: Lower-cased (schema, table) keys already discovered.
    discovered: List that new table entries are appended to.
    catalog: Optional --catalog filter.
    skipped_catalogs: Collects the catalogs of rows that --catalog skipped.
  """
  skipped: set[str] = set()
  names = zf.namelist()
  by_base = {os.path.basename(n).lower(): n for n in names}
  initial_count = len(discovered)
  zip_name = zf.filename or "metadata zip"
  if "columns.csv" in by_base:
    text = zf.read(by_base["columns.csv"]).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    cols_by_key: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    orig_names: dict[tuple[str, str, str], tuple[str, str]] = {}
    view_keys = _zip_view_keys(zf, by_base)
    for row in reader:
      table_type = (row.get("TableType") or "").strip().upper()
      if table_type in _VIEW_TABLE_TYPES:
        continue
      row_cat = _real_catalog(row.get("TableCatalog") or "")
      if catalog and row_cat and row_cat.lower() != catalog.lower():
        skipped.add(row_cat)
        continue
      schema = (row.get("TableSchema") or "default").strip()
      table = (row.get("TableName") or "").strip()
      col_name = (row.get("ColumnName") or "").strip()
      if not (table and col_name):
        continue
      cat_key = (row_cat.lower(), schema.lower(), table.lower())
      if cat_key in view_keys:
        continue
      orig_names.setdefault(cat_key, (schema, table))
      cols_by_key.setdefault(cat_key, []).append({
          "ColumnName": col_name,
          "DataType": (
              (
                  row.get("FullDataType") or row.get("DataType") or "STRING"
              ).strip()
          ),
          "NumericPrecision": (row.get("NumericPrecision") or "").strip(),
          "NumericScale": (row.get("NumericScale") or "").strip(),
          "TargetType": "",
      })
    for cat_key, cols in cols_by_key.items():
      key = cat_key[1:]
      s_orig, t_orig = orig_names[cat_key]
      if key in seen:
        _warn_duplicate_table(f"{s_orig}.{t_orig}", f"{zip_name}/columns.csv")
        continue
      seen.add(key)
      discovered.append({"schema": s_orig, "table": t_orig, "columns": cols})
    if len(discovered) > initial_count:
      if skipped_catalogs is not None:
        skipped_catalogs.update(skipped)
      return

  if "tables.jsonl" in by_base:
    text = zf.read(by_base["tables.jsonl"]).decode(
        "utf-8-sig", errors="replace"
    )
    for line in text.splitlines():
      if not line.strip():
        continue
      try:
        obj = json.loads(line)
      except ValueError:
        continue
      if str(obj.get("type", "")).strip().upper() in _VIEW_TABLE_TYPES:
        continue
      obj_cat = _real_catalog(str(obj.get("catalogName") or ""))
      if catalog and obj_cat and obj_cat.lower() != catalog.lower():
        skipped.add(obj_cat)
        continue
      schema = str(obj.get("schemaName") or "default").strip()
      table = str(obj.get("name") or "").strip()
      if not table:
        continue
      cols: list[dict[str, str]] = []
      for f_entry in (obj.get("fields") or []) + (
          obj.get("partitionKeys") or []
      ):
        if isinstance(f_entry, dict) and f_entry.get("name"):
          cols.append({
              "ColumnName": str(f_entry["name"]),
              "DataType": str(f_entry.get("type") or "STRING"),
              "NumericPrecision": "",
              "NumericScale": "",
              "TargetType": "",
          })
      key = (schema.lower(), table.lower())
      if key in seen:
        _warn_duplicate_table(f"{schema}.{table}", f"{zip_name}/tables.jsonl")
        continue
      seen.add(key)
      discovered.append({"schema": schema, "table": table, "columns": cols})
    if len(discovered) > initial_count:
      if skipped_catalogs is not None:
        skipped_catalogs.update(skipped)
      return

  if skipped:
    # The zip names catalogs, so don't fall back to unfiltered DDL parsing.
    if skipped_catalogs is not None:
      skipped_catalogs.update(skipped)
    return
  for zname in sorted(names):
    if zname.endswith(".sql") and "view" not in zname.lower():
      sql_text = zf.read(zname).decode("utf-8", errors="replace")
      _extract_tables_from_sql_text(sql_text, seen, discovered)


def _parse_tables_from_sql_or_zip(
    dir_to_scan: str,
    catalog: str | None = None,
    skipped_catalogs: set[str] | None = None,
) -> list[dict[str, Any]]:
  """Fallback table discovery from DDL SQL files or metadata zip archives."""
  discovered: list[dict[str, Any]] = []
  seen: set[tuple[str, str]] = set()

  if os.path.isfile(dir_to_scan):
    if dir_to_scan.endswith(".sql"):
      with open(dir_to_scan, "r", encoding="utf-8") as sf:
        _extract_tables_from_sql_text(sf.read(), seen, discovered)
    elif dir_to_scan.endswith(".zip"):
      with zipfile.ZipFile(dir_to_scan, "r") as zf:
        _extract_tables_from_zip(
            zf, seen, discovered, catalog, skipped_catalogs
        )
    return discovered

  if not os.path.isdir(dir_to_scan):
    return discovered

  sql_paths: list[str] = []
  for root, dirs, files in os.walk(dir_to_scan):
    dirs.sort()  # Deterministic order, so the first catalog wins.
    for f in sorted(files):
      fpath = os.path.join(root, f)
      if f.endswith(".zip"):
        try:
          with zipfile.ZipFile(fpath, "r") as zf:
            _extract_tables_from_zip(
                zf, seen, discovered, catalog, skipped_catalogs
            )
        except (zipfile.BadZipFile, OSError):
          pass
      elif f.endswith(".sql") and "view" not in f.lower():
        sql_paths.append(fpath)
  # Loose DDL has no catalog, so skip it once a zip row was filtered out by
  # --catalog.
  if skipped_catalogs:
    return discovered
  for fpath in sql_paths:
    try:
      with open(fpath, "r", encoding="utf-8") as sf:
        sql_text = sf.read()
    except OSError:
      continue
    _extract_tables_from_sql_text(sql_text, seen, discovered)

  return discovered


# CUSTOMIZE: Table & Row Filtering — Edit load_tables_from_metadata_path() to
# add custom schema/table inclusion or exclusion filters.
def load_tables_from_metadata_path(
    path_or_uri: str,
    catalog: str | None = None,
) -> list[dict[str, Any]]:
  """Discovers tables to export from translation metadata, DDL, or zip archive.

  Inspects BQMS translated YAML configuration files first, falling back to
  sibling `metadata/` or parsing table DDLs from SQL files or zip archives.

  Args:
    path_or_uri: Local path or Cloud Storage URI to metadata directory, config
      dir, or DDLs.
    catalog: Optional catalog filter when reading multi-catalog metadata zips.

  Returns:
    A list of dictionaries each containing 'schema' and 'table' keys (and
    optional 'columns').
  """
  dir_to_scan, temp_dir = _resolve_metadata_dir(path_or_uri)
  skipped_catalogs: set[str] = set()
  try:
    config_dir = _find_config_dir(dir_to_scan)
    discovered_tables = _parse_tables_from_yaml_configs(
        config_dir, catalog=catalog
    )

    if catalog and not discovered_tables:
      yaml_catalogs = _yaml_catalogs(config_dir)
      if yaml_catalogs:
        # Don't fall back to unfiltered DDL parsing when YAML configs exist
        # but none of them is in the requested catalog.
        raise ValueError(
            f"--catalog {catalog} matches none of the BQMS YAML configs;"
            f" available catalogs: {', '.join(sorted(yaml_catalogs))}."
        )

    # A gs:// download lives under the shared temp root, so never scan its
    # parent's metadata/ directory.
    if not discovered_tables and os.path.isdir(dir_to_scan) and not temp_dir:
      parent_dir = os.path.dirname(os.path.abspath(dir_to_scan))
      sibling_meta_dir = os.path.join(parent_dir, "metadata")
      if os.path.isdir(sibling_meta_dir) and os.path.abspath(
          sibling_meta_dir
      ) != os.path.abspath(dir_to_scan):
        discovered_tables = _parse_tables_from_sql_or_zip(
            sibling_meta_dir, catalog, skipped_catalogs
        )

    if not discovered_tables:
      discovered_tables = _parse_tables_from_sql_or_zip(
          dir_to_scan, catalog, skipped_catalogs
      )
    if catalog and not discovered_tables and skipped_catalogs:
      raise ValueError(
          f"--catalog {catalog} matches no tables in the metadata zip;"
          f" available catalogs: {', '.join(sorted(skipped_catalogs))}."
      )

    return [
        {"schema": str(t["schema"]), "table": str(t["table"])}
        if not t.get("columns")
        else t
        for t in discovered_tables
    ]
  finally:
    if temp_dir:
      shutil.rmtree(temp_dir, ignore_errors=True)


# ==============================================================================
# 2. Type-Safe Spark SQL Generation Logic
# ==============================================================================


# Spark SQL keywords reserved in ANSI mode plus the NULL/TRUE/FALSE literals.
# Backticks are always valid, so quoting these is safe in default mode too.
_SPARK_RESERVED = frozenset((
    "ALL",
    "AND",
    "ANTI",
    "ANY",
    "AS",
    "AUTHORIZATION",
    "BETWEEN",
    "BOTH",
    "BY",
    "CASE",
    "CAST",
    "CHECK",
    "COLLATE",
    "COLUMN",
    "CONSTRAINT",
    "CREATE",
    "CROSS",
    "CURRENT_DATE",
    "CURRENT_TIME",
    "CURRENT_TIMESTAMP",
    "CURRENT_USER",
    "DELETE",
    "DISTINCT",
    "ELSE",
    "END",
    "ESCAPE",
    "EXCEPT",
    "EXISTS",
    "FALSE",
    "FETCH",
    "FILTER",
    "FOR",
    "FOREIGN",
    "FROM",
    "FULL",
    "GRANT",
    "GROUP",
    "HAVING",
    "IN",
    "INNER",
    "INSERT",
    "INTERSECT",
    "INTERVAL",
    "INTO",
    "IS",
    "JOIN",
    "LATERAL",
    "LEADING",
    "LEFT",
    "LIKE",
    "MINUS",
    "NATURAL",
    "NOT",
    "NULL",
    "OF",
    "OFFSET",
    "ON",
    "ONLY",
    "OR",
    "ORDER",
    "OUTER",
    "OVERLAPS",
    "PRIMARY",
    "REFERENCES",
    "RIGHT",
    "SELECT",
    "SEMI",
    "SESSION_USER",
    "SOME",
    "TABLE",
    "THEN",
    "TIME",
    "TO",
    "TRAILING",
    "TRUE",
    "UNION",
    "UNIQUE",
    "UNKNOWN",
    "UPDATE",
    "USER",
    "USING",
    "VALUES",
    "WHEN",
    "WHERE",
    "WINDOW",
    "WITH",
))


# BigQuery integer target type names (INT64 and its aliases).
_INT_TARGET_TYPES = frozenset(
    ("INT64", "INT", "INTEGER", "BIGINT", "SMALLINT", "TINYINT", "BYTEINT")
)

# Spark SQL decimal and character source type names.
_DECIMAL_SOURCE_TYPES = frozenset(
    ("DECIMAL", "DEC", "NUMERIC", "NUMBER", "BIGNUMERIC")
)
_STRING_SOURCE_TYPES = frozenset(("STRING", "VARCHAR", "CHAR"))
_INT_SOURCE_TYPES = frozenset((
    "BIGINT",
    "LONG",
    "INT",
    "INTEGER",
    "SMALLINT",
    "SHORT",
    "TINYINT",
    "BYTE",
    "BYTEINT",
))

# Comment lines written at the top of the unified script and of every per-table
# file. They stay comments (not `SET TIME ZONE 'UTC';`) because the SQL
# warehouse connector runs exactly one statement per call.
_SESSION_TIME_ZONE_NOTE = (
    "-- NOTE: TIMESTAMP_NTZ <-> TIMESTAMP casts use the session time zone. Run",
    "-- in a UTC session (SQL warehouse TIMEZONE or spark.sql.session.timeZone",
    "-- set to UTC, or SET TIME ZONE 'UTC' first in a beeline session).",
)


# DEFAULT SCAFFOLDING: Spark SQL identifier quoting helper.
def quote_ident(ident: str) -> str:
  """Quotes an identifier with backticks if needed for Spark SQL.

  Names that start with a digit, contain special characters, or match a
  reserved word or literal (such as `select` or `null`) are backtick-quoted.

  Args:
    ident: The raw SQL identifier string.

  Returns:
    The properly quoted or unquoted identifier.
  """
  if not ident:
    return ""
  if len(ident) >= 2 and ident.startswith("`") and ident.endswith("`"):
    # Already quoted: re-escape any bare inner backticks.
    inner = ident[1:-1].replace("``", "`").replace("`", "``")
    return f"`{inner}`"
  if (
      ident[0].isdigit()
      or not _VALID_IDENT_REGEX.match(ident)
      or ident.upper() in _SPARK_RESERVED
  ):
    escaped = ident.replace("`", "``")
    return f"`{escaped}`"
  return ident


# CUSTOMIZE: Custom Type Projections — Edit format_column_cast() to add custom
# Spark SQL column projections (e.g. TO_JSON for STRUCT/MAP/ARRAY, DECIMAL
# precision bounds, or timestamp formatting).
def format_column_cast(
    col: dict[str, str], target_bq_type: str | None = None
) -> str:
  """Generates a type-safe Spark SQL projection expression for export."""
  col_raw = str(col.get("ColumnName") or "").strip()
  col_name = quote_ident(col_raw)
  raw_data_type = str(col.get("DataType") or "").upper().strip()
  precision_str = str(col.get("NumericPrecision") or "").strip()
  scale_str = str(col.get("NumericScale") or "").strip()

  precision = int(precision_str) if precision_str.isdigit() else None
  scale = int(scale_str) if scale_str.isdigit() else None

  param_match = _PARAM_TYPE_REGEX.match(raw_data_type)
  if param_match:
    data_type = param_match.group("base")
    if precision is None:
      precision = int(param_match.group("p"))
    if scale is None:
      if param_match.group("s") is not None:
        scale = int(param_match.group("s"))
      elif data_type in ("DECIMAL", "DEC", "NUMERIC", "NUMBER"):
        scale = 0
  else:
    data_type = re.split(r"[<(\s]", raw_data_type, maxsplit=1)[0].strip()

  target = (target_bq_type or str(col.get("TargetType") or "")).upper().strip()

  if data_type == "MAP":
    return f"TO_JSON({col_name}) AS {col_name}"
  if data_type in ("STRUCT", "ARRAY") and (
      target.startswith("JSON") or target == "STRING"
  ):
    return f"TO_JSON({col_name}) AS {col_name}"
  if target.startswith("JSON") or data_type in ("VARIANT", "OBJECT", "JSON"):
    return f"CAST({col_name} AS STRING) AS {col_name}"
  if data_type.startswith("INTERVAL"):
    return f"CAST({col_name} AS STRING) AS {col_name}"

  # Explicit BigQuery target types (for example schema overrides) win over the
  # source-type defaults below. DECIMAL sources are handled in their own branch,
  # and same-family targets (a STRING column with a STRING target, or a
  # timestamp column with a TIMESTAMP / DATETIME target) keep the defaults.
  target_base = re.split(r"[(<]", target, maxsplit=1)[0].strip()
  is_timestamp = data_type.startswith("TIMESTAMP") or data_type == "DATETIME"
  if target_base and data_type not in _DECIMAL_SOURCE_TYPES:
    if target_base in _INT_TARGET_TYPES:
      return f"CAST({col_name} AS BIGINT) AS {col_name}"
    if target_base in ("FLOAT64", "FLOAT", "DOUBLE"):
      return f"CAST({col_name} AS DOUBLE) AS {col_name}"
    if target_base in ("BOOL", "BOOLEAN"):
      return f"CAST({col_name} AS BOOLEAN) AS {col_name}"
    if target_base == "DATE":
      return f"CAST({col_name} AS DATE) AS {col_name}"
    if target_base == "BYTES":
      return f"CAST({col_name} AS BINARY) AS {col_name}"
    if target_base in ("NUMERIC", "BIGNUMERIC", "DECIMAL"):
      # Parquet DECIMAL for a fixed-point BigQuery column; integers keep
      # scale 0. NUMERIC (alias DECIMAL) holds at most 29 integer digits.
      if data_type in _INT_SOURCE_TYPES:
        p_val = 38 if target_base == "BIGNUMERIC" else 29
        return f"CAST({col_name} AS DECIMAL({p_val}, 0)) AS {col_name}"
      return f"CAST({col_name} AS DECIMAL(38, 9)) AS {col_name}"
    if target_base == "STRING" and data_type not in _STRING_SOURCE_TYPES:
      return f"CAST({col_name} AS STRING) AS {col_name}"
    if target_base == "TIMESTAMP" and not is_timestamp:
      return f"CAST({col_name} AS TIMESTAMP) AS {col_name}"
    if target_base == "DATETIME" and not is_timestamp:
      return f"CAST({col_name} AS TIMESTAMP_NTZ) AS {col_name}"

  if data_type in _DECIMAL_SOURCE_TYPES:
    # An explicit BigQuery target type wins over the implicit BIGINT shortcut.
    if target.startswith(("FLOAT", "DOUBLE")):
      return f"CAST({col_name} AS DOUBLE) AS {col_name}"
    if target.startswith("STRING"):
      return f"CAST({col_name} AS STRING) AS {col_name}"
    if target in _INT_TARGET_TYPES:
      return f"CAST({col_name} AS BIGINT) AS {col_name}"
    if (
        scale == 0
        and precision is not None
        and precision <= 18
        and not target.startswith(("NUMERIC", "BIGNUMERIC", "DECIMAL"))
    ):
      return f"CAST({col_name} AS BIGINT) AS {col_name}"
    if scale is None:
      return f"{col_name}"
    # Spark DECIMAL(p, s) requires 1 <= p <= 38 and 0 <= s <= p.
    p_val = min(max(precision, 1), 38) if precision is not None else 38
    s_val = min(scale, p_val)
    return f"CAST({col_name} AS DECIMAL({p_val}, {s_val})) AS {col_name}"
  if data_type in _INT_SOURCE_TYPES:
    return f"CAST({col_name} AS BIGINT) AS {col_name}"
  if data_type in ("DOUBLE", "FLOAT", "REAL"):
    return f"CAST({col_name} AS DOUBLE) AS {col_name}"
  if data_type in ("TIMESTAMP_NTZ", "DATETIME"):
    if target == "DATETIME":
      return f"{col_name}"
    return f"CAST({col_name} AS TIMESTAMP) AS {col_name}"
  if data_type.startswith("TIMESTAMP"):
    if target == "DATETIME":
      return f"CAST({col_name} AS TIMESTAMP_NTZ) AS {col_name}"
    return f"CAST({col_name} AS TIMESTAMP) AS {col_name}"
  if data_type == "DATE":
    return f"CAST({col_name} AS DATE) AS {col_name}"
  if data_type in ("BOOLEAN", "BOOL"):
    return f"CAST({col_name} AS BOOLEAN) AS {col_name}"
  if data_type in ("BINARY", "VARBINARY", "BYTES"):
    return f"CAST({col_name} AS BINARY) AS {col_name}"
  return f"{col_name}"


def _sanitize_comment_token(value: str) -> str:
  """Replaces control characters so SQL line comments stay single-line."""
  return re.sub(r"[\x00-\x1f\x7f]+", " ", str(value)).strip()


# CUSTOMIZE: Stage & Storage Configuration — Edit
# _build_insert_overwrite_query() to customize the Spark SQL INSERT OVERWRITE
# DIRECTORY options (compression codec, WHERE filter predicates, or partition
# options).
def _build_insert_overwrite_query(
    schema: str,
    table_name: str,
    columns: list[dict[str, str]] | None = None,
    stage_path: str = "/tmp/databricks_export",
    include_schema_subpath: bool = False,
    catalog: str | None = None,
    export_mode: str = "insert_overwrite",
) -> str:
  """Builds the Spark SQL export statement for a table."""
  clean_stage = stage_path.strip().strip("'").rstrip("/")
  if include_schema_subpath and schema:
    target_dir = f"{clean_stage}/{schema}/{table_name}"
  else:
    target_dir = f"{clean_stage}/{table_name}"
  escaped_target_dir = target_dir.replace("'", "''")

  if catalog:
    qualified_src = (
        f"{quote_ident(catalog)}.{quote_ident(schema)}."
        f"{quote_ident(table_name)}"
    )
  else:
    qualified_src = f"{quote_ident(schema)}.{quote_ident(table_name)}"

  if columns:
    projections = ",\n  ".join(format_column_cast(c) for c in columns)
    select_clause = f"SELECT\n  {projections}\nFROM {qualified_src}"
  else:
    select_clause = f"SELECT * FROM {qualified_src}"

  if export_mode.lower() == "select":
    return (
        f"-- Target Directory: {_sanitize_comment_token(target_dir)}\n"
        f"{select_clause};"
    )

  return (
      f"INSERT OVERWRITE DIRECTORY '{escaped_target_dir}'\n"
      "USING PARQUET\n"
      "OPTIONS ('compression' = 'snappy')\n"
      f"{select_clause};"
  )


# DEFAULT SCAFFOLDING: Primary Databricks SQL script generator.
def generate_export_sql(
    metadata_path_or_uri: str,
    stage_path: str = "/tmp/databricks_export",
    catalog: str | None = None,
    export_mode: str = "insert_overwrite",
) -> str:
  """Generates the Databricks / Spark SQL Parquet export script (.sql).

  Args:
    metadata_path_or_uri: Path or Cloud Storage URI to translation metadata,
      config dir, or DDLs.
    stage_path: Destination directory path inside the Spark/Databricks
      environment (default: '/tmp/databricks_export').
    catalog: Optional Unity Catalog name to prefix 3-part table references.
    export_mode: 'insert_overwrite' (default) or 'select'.

  Returns:
    A complete, formatted Spark SQL script string ready for execution.
  """
  tables = load_tables_from_metadata_path(metadata_path_or_uri, catalog=catalog)
  generator_name = (
      os.path.basename(sys.argv[0]) if sys.argv and sys.argv[0] else ""
  ) or "export_databricks_tables_template.py"

  table_name_counts: dict[str, int] = {}
  for item in tables:
    t_lower = str(item.get("table") or "").lower()
    if t_lower:
      table_name_counts[t_lower] = table_name_counts.get(t_lower, 0) + 1

  colliding_tables = {t for t, count in table_name_counts.items() if count > 1}
  colliding_schemas = {
      str(item.get("schema") or "default").lower()
      for item in tables
      if str(item.get("table") or "").lower() in colliding_tables
  }

  sql_lines = [
      "-- " + "=" * 77,
      "-- Databricks / Spark SQL to Parquet Type-Safe Data Export Script",
      f"-- Generated by bigquery-migration-data-exporter / {generator_name}",
      *_SESSION_TIME_ZONE_NOTE,
      "-- " + "=" * 77,
      "",
  ]

  divider = "-- " + "-" * 77
  for item in tables:
    schema = str(item.get("schema") or "default")
    table_name = str(item.get("table") or "")
    if not table_name:
      continue
    cols = item.get("columns") or []
    t_lower = table_name.lower()
    has_collision = t_lower in colliding_tables or t_lower in colliding_schemas
    stmt = _build_insert_overwrite_query(
        schema=schema,
        table_name=table_name,
        columns=cols,
        stage_path=stage_path,
        include_schema_subpath=has_collision,
        catalog=catalog,
        export_mode=export_mode,
    )
    table_label = _sanitize_comment_token(f"{schema}.{table_name}")
    sql_lines.append(
        f"{divider}\n-- Unload Table: {table_label} ->"
        f" Parquet\n{divider}\n{stmt}\n"
    )

  return "\n".join(sql_lines)


def _sanitize_sql_filename(label: str, used_filenames: set[str]) -> str:
  """Builds a safe, collision-free per-table SQL filename."""
  unquoted = label.replace('"', "").replace("`", "").strip()
  safe_parts = [
      re.sub(r"[^A-Za-z0-9_-]+", "_", p.strip()).strip("_") or "table"
      for p in unquoted.split(".")
      if p.strip()
  ]
  stem = "_".join(safe_parts) if safe_parts else "table"
  filename = f"{stem}_export.sql"
  if filename.lower() in used_filenames and len(safe_parts) > 1:
    filename = f"{'__'.join(safe_parts)}_export.sql"
  idx = 2
  base_stem = filename[: -len("_export.sql")]
  while filename.lower() in used_filenames:
    filename = f"{base_stem}_{idx}_export.sql"
    idx += 1
  used_filenames.add(filename.lower())
  return filename


def _write_table_sql_files(sql: str, output_dir: str) -> list[str]:
  """Splits unified Spark SQL script and writes per-table SQL files."""
  os.makedirs(output_dir, exist_ok=True)
  divider = "-- " + "-" * 77
  stmts = sql.split(f"{divider}\n-- Unload Table: ")
  written_paths: list[str] = []
  used_filenames: set[str] = set()
  for chunk in stmts[1:]:
    table_label = chunk.split(" -> Parquet")[0].strip()
    filename = _sanitize_sql_filename(table_label, used_filenames)
    table_sql = (
        "\n".join(_SESSION_TIME_ZONE_NOTE)
        + f"\n{divider}\n-- Unload Table: {chunk}"
    )
    tbl_path = os.path.join(output_dir, filename)
    with open(tbl_path, "w", encoding="utf-8") as f:
      f.write(table_sql)
    written_paths.append(tbl_path)
    print(f"Generated table export SQL: {tbl_path}")
  return written_paths


# ==============================================================================
# 3. CLI Router (DEFAULT SCAFFOLDING CLI ROUTER)
# ==============================================================================
# DEFAULT SCAFFOLDING: CLI argument parser and SQL file writer entrypoint.
def _parse_args(args: list[str] | None = None) -> argparse.Namespace:
  """Builds and parses CLI arguments for Databricks export SQL generation."""
  parser = argparse.ArgumentParser(
      description=(
          "Databricks / Spark SQL Parquet Export SQL Generator (outputs .sql"
          " scripts)."
      )
  )
  parser.add_argument(
      "--translation-metadata-dir",
      "--translation-output",
      "--metadata-dir",
      "--config-dir",
      dest="metadata_path",
      required=True,
      help=(
          "Path or Cloud Storage URI to translation_output/metadata, config"
          " directory, or DDL metadata"
      ),
  )
  parser.add_argument(
      "--stage-path",
      "--export-dir",
      dest="stage_path",
      default="/tmp/databricks_export",
      help=(
          "Target directory path for Spark SQL INSERT OVERWRITE DIRECTORY"
          " (default: '/tmp/databricks_export')"
      ),
  )
  parser.add_argument(
      "--catalog",
      default=None,
      help=(
          "Optional Unity Catalog name for 3-part table qualification (leave"
          " unset for catalog-agnostic 2-part schema.table SQL)"
      ),
  )
  parser.add_argument(
      "--export-mode",
      choices=["insert_overwrite", "select"],
      default="insert_overwrite",
      help=(
          "SQL generation mode: 'insert_overwrite' (default, emits INSERT"
          " OVERWRITE DIRECTORY ... USING PARQUET SELECT ...) or 'select'"
          " (emits standalone SELECT ... statements)"
      ),
  )
  parser.add_argument(
      "--output-sql",
      help="File path to write the unified Databricks export SQL script",
  )
  parser.add_argument(
      "--output-dir",
      help="Directory to write individual per-table *_export.sql files",
  )
  return parser.parse_args(args)


def main() -> None:
  """CLI entrypoint for the Databricks Parquet export SQL generator."""
  args = _parse_args()

  try:
    sql = generate_export_sql(
        metadata_path_or_uri=args.metadata_path,
        stage_path=args.stage_path,
        catalog=args.catalog,
        export_mode=args.export_mode,
    )
  except ValueError as e:
    sys.exit(f"ERROR: {e}")

  if args.output_sql:
    out_dir = os.path.dirname(os.path.abspath(args.output_sql))
    if out_dir:
      os.makedirs(out_dir, exist_ok=True)
    with open(args.output_sql, "w", encoding="utf-8") as f:
      f.write(sql)
    print(f"Generated unified Databricks export script: {args.output_sql}")

  if args.output_dir:
    _write_table_sql_files(sql, args.output_dir)

  if not args.output_sql and not args.output_dir:
    print(sql)


if __name__ == "__main__":
  main()
