#!/usr/bin/env python3
r"""Template Script for Generating Type-Safe PostgreSQL Export SQL Files.

This asset template script provides a reference implementation for generating
type-safe PostgreSQL SELECT export scripts (.sql) directly from BQMS
translation_output/metadata configs or a PostgreSQL extractor metadata.zip
(is_columns_private.csv and pg_views_private.csv, or generic tables.csv and
columns.csv). It has zero JDBC or database connector dependencies.

PostgreSQL COPY ... TO cannot write Parquet directly to Cloud Storage
and requires superuser privileges for server-side file output. The export
therefore happens in two steps:

  1. This script emits one explicit-cast SELECT per table. The casts pin every
     column to a PostgreSQL SQL type whose `psycopg2` cursor metadata and
     Parquet representation BigQuery loads without drift (SMALLINT/INTEGER/
     BIGINT -> BIGINT -> INT64, NUMERIC(p,s) -> DECIMAL128 -> NUMERIC/
     BIGNUMERIC, MONEY -> NUMERIC(38,2) -> BIGNUMERIC, REAL/DOUBLE PRECISION ->
     DOUBLE PRECISION -> FLOAT64, DATE -> DATE, TIME/TIMETZ -> TIME(6) -> TIME,
     TIMESTAMP -> TIMESTAMP(6) WITHOUT TIME ZONE -> DATETIME, TIMESTAMPTZ ->
     TIMESTAMP(6) WITH TIME ZONE -> TIMESTAMP, CHAR/BPCHAR padding trimmed via
     RTRIM, and JSON/JSONB/XML/UUID/INET/CIDR/MACADDR/INTERVAL -> TEXT).
  2. A downstream Python execution script runs each SELECT via the `psycopg2`
     driver, derives the Arrow schema from `cursor.description`, and writes
     Snappy Parquet files under ./data_unload/[<SCHEMA>/]<TABLE>/.

Usage Pattern:
  Copy `assets/export_postgres_tables_template.py` from this skill's directory
  (`<SKILL_DIR>`, the directory containing `SKILL.md`) into your
  working directory (e.g., `./export_postgres_tables.py`). Run the copy as-is
  for standard export SQL generation, and prioritize modifying the marked
  `# CUSTOMIZE:` extension points if your environment requires custom type
  projections, row filters, or schema/table filtering. Sections marked
  `# DEFAULT SCAFFOLDING` can be kept unchanged unless deeper orchestration
  adjustments are needed.

Dependencies:
  pip install pyyaml==6.0.2

Usage Examples:
    # Copy the template from this skill's directory to your working directory:
    cp <SKILL_DIR>/assets/export_postgres_tables_template.py \
        ./export_postgres_tables.py

    # 1. Generate per-table PostgreSQL export SQL files from BQMS output:
    python3 ./export_postgres_tables.py \
        --translation-metadata-dir ./translated_output/metadata \
        --default-schema public \
        --output-dir ./export_sql

    # 2. Generate a unified export SQL file straight from the extractor zip:
    python3 ./export_postgres_tables.py \
        --metadata-zip gs://my-bucket/postgresql-metadata.zip \
        --schema public \
        --output-sql postgres_export.sql
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

_SYSTEM_SCHEMAS = frozenset((
    "pg_catalog",
    "pg_internal",
    "information_schema",
    "pg_toast",
))


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
  """Trims whitespace around PostgreSQL catalog CSV fields."""
  return (value or "").strip()


def _decode_pg_scale(scale: int | None) -> int | None:
  """Decodes PostgreSQL 15+ negative NUMERIC scale from information_schema.

  In PostgreSQL 15+, information_schema._pg_numeric_scale masks
  ((typmod - 4) & 0x7ff) without sign extension, so negative scales such as
  NUMERIC(10, -2) are reported as 2046 (2048 - 2).

  Args:
    scale: Raw numeric scale integer or None.

  Returns:
    Signed numeric scale integer or None.
  """
  if scale is not None and 1024 <= scale < 2048:
    return scale - 2048
  return scale


def _decode_pg_scale_str(scale_str: str) -> str:
  """Decodes a numeric scale string if it encodes a PG 15+ negative scale."""
  s = _strip(scale_str)
  if s.lstrip("-").isdigit():
    val = _decode_pg_scale(int(s))
    return str(val) if val is not None else ""
  return s


def load_metadata_from_zip(
    zip_bytes: bytes,
) -> dict[str, list[dict[str, str]]]:
  """Extracts table and column metadata from a PostgreSQL metadata.zip.

  Reads is_columns_private.csv and pg_views_private.csv (falls back to generic
  tables.csv and columns.csv) and normalizes rows to the shared TableCatalog/
  TableSchema/TableName/ColumnName/DataType record shape. Pairing
  is_columns_private.csv with pg_views_private.csv ensures views and system
  catalogs are excluded so only physical user base tables are exported.

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

    tables_fn, table_rows = _rows(["tables.csv"])
    views_fn, view_rows = _rows(["pg_views_private.csv", "views.csv"])
    columns_fn, column_rows = _rows(["is_columns_private.csv", "columns.csv"])

  view_keys: set[tuple[str, str, str]] = set()
  if views_fn:
    for r in view_rows:
      v_cat = _strip(r.get("table_catalog") or r.get("TableCatalog"))
      v_schema = _strip(
          r.get("schemaname") or r.get("table_schema") or r.get("TableSchema")
      )
      v_name = _strip(
          r.get("viewname") or r.get("table_name") or r.get("TableName")
      )
      if v_name:
        # Exact case: PostgreSQL keeps quoted identifiers case-sensitive, so
        # a view "Report" must not hide a base table report.
        view_keys.add((v_cat, v_schema, v_name))

  if tables_fn == "tables.csv" and table_rows:
    for r in table_rows:
      t_dict = {k: _strip(v) for k, v in r.items() if k is not None}
      t_schema = _strip(t_dict.get("TableSchema") or t_dict.get("table_schema"))
      t_name = _strip(t_dict.get("TableName") or t_dict.get("table_name"))
      t_cat = _strip(t_dict.get("TableCatalog") or t_dict.get("table_catalog"))
      t_type = _strip(
          t_dict.get("TableType") or t_dict.get("table_type") or "BASE TABLE"
      ).upper()
      # tables.csv rows carry their own TableType, so only a view in the
      # same database reclassifies them.
      if (t_cat, t_schema, t_name) in view_keys:
        t_type = "VIEW"
      result["tables"].append({
          "TableCatalog": t_cat,
          "TableSchema": t_schema,
          "TableName": t_name,
          "TableType": t_type,
      })

  seen_tables: set[tuple[str, str, str]] = set()
  if columns_fn:
    for r in column_rows:
      schema = _strip(r.get("table_schema") or r.get("TableSchema"))
      if schema.lower() in _SYSTEM_SCHEMAS:
        continue
      tbl_name = _strip(r.get("table_name") or r.get("TableName"))
      catalog = _strip(r.get("table_catalog") or r.get("TableCatalog"))
      is_nullable = (
          _strip(
              r.get("is_nullable") or r.get("Nullable") or r.get("NULLABLE")
          ).upper()
          or "YES"
      )
      not_null = is_nullable in ("NO", "N", "FALSE")
      raw_dt = _strip(r.get("data_type") or r.get("DataType")).upper()
      udt_name = _strip(r.get("udt_name")).upper()
      if raw_dt == "USER-DEFINED" and udt_name:
        data_type = udt_name
      else:
        data_type = raw_dt

      radix = _strip(r.get("numeric_precision_radix"))
      if radix == "10" or data_type in ("NUMERIC", "DECIMAL", "DEC", "NUMBER"):
        num_prec = _strip(
            r.get("numeric_precision") or r.get("NumericPrecision")
        )
        num_scale = _decode_pg_scale_str(
            _strip(r.get("numeric_scale") or r.get("NumericScale"))
        )
      else:
        num_prec = ""
        num_scale = ""

      result["columns"].append({
          "TableCatalog": catalog,
          "TableSchema": schema,
          "TableName": tbl_name,
          "ColumnName": _strip(r.get("column_name") or r.get("ColumnName")),
          "OrdinalPosition": _strip(
              r.get("ordinal_position") or r.get("OrdinalPosition")
          ),
          "DataType": data_type,
          "ColumnLength": _strip(
              r.get("character_maximum_length") or r.get("ColumnLength")
          ),
          "NumericPrecision": num_prec,
          "NumericScale": num_scale,
          "Nullable": "N" if not_null else "Y",
          "ExplicitNotNull": "Y" if not_null else "N",
      })
      if not table_rows and (catalog, schema, tbl_name) not in seen_tables:
        seen_tables.add((catalog, schema, tbl_name))
        # pg_views_private.csv has no database column, so its views match
        # the same schema.table in any database.
        is_view = any(
            (cat, schema, tbl_name) in view_keys for cat in (catalog, "")
        )
        result["tables"].append({
            "TableCatalog": catalog,
            "TableSchema": schema,
            "TableName": tbl_name,
            "TableType": "VIEW" if is_view else "BASE TABLE",
        })

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
      # PostgreSQL names in BQMS are __DEFAULT_DATABASE__.schema.table or
      # db.schema.table or schema.table.
      schema = parts[-2] if len(parts) >= 2 else ""
      table = parts[-1] if parts else f.rsplit(".", 1)[0]

      catalog = (
          parts[0]
          if len(parts) >= 3 and parts[0] != "__DEFAULT_DATABASE__"
          else ""
      )

      # Views are recreated, not exported; skipping them here keeps a view
      # from shadowing a same-named table in another database.
      if not (cfg.get("externalTableName") or cfg.get("externalTableDdlPath")):
        continue
      result["tables"].append({
          "TableCatalog": catalog,
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
        # Prefer raw PostgreSQL type name ('timestamp without time zone',
        # 'time with time zone', 'money', 'bytea', 'uuid', 'inet', etc.).
        data_type = raw_code or generic_name
        raw_prec = src.get("precision")
        raw_scale = src.get("scale")
        # For MONEY, BQMS sets sourceType: {name: 'money', precision: 2}.
        if data_type == "MONEY":
          num_prec = ""
          num_scale = ""
        else:
          num_prec = str(raw_prec) if raw_prec is not None else ""
          num_scale = (
              _decode_pg_scale_str(str(raw_scale))
              if raw_scale is not None
              else ""
          )

        col_entry = {
            "TableCatalog": catalog,
            "TableSchema": schema,
            "TableName": table,
            "ColumnName": col.get("sourceName", ""),
            "OrdinalPosition": str(idx),
            "DataType": data_type,
            "NumericPrecision": num_prec,
            "NumericScale": num_scale,
            "Nullable": "N" if col.get("notNull") else "Y",
            "ExplicitNotNull": "Y" if col.get("notNull") else "N",
        }
        # Persist the BQMS target type so format_column_cast() honors INT64 /
        # NUMERIC / BIGNUMERIC / FLOAT64 / DATETIME / TIMESTAMP overrides.
        tgt_type = col.get("targetType") or {}
        tgt_name = (
            (
                str(tgt_type.get("name") or "")
                if isinstance(tgt_type, dict)
                else str(tgt_type)
            )
            .strip()
            .upper()
        )
        if tgt_name:
          col_entry["TargetType"] = tgt_name
        result["columns"].append(col_entry)

  return result


def _enrich_yaml_columns_from_zip(
    yaml_meta: dict[str, list[dict[str, str]]],
    zip_meta: dict[str, list[dict[str, str]]],
) -> None:
  """Enriches BQMS YAML column metadata with extractor zip catalog details.

  BQMS translate_metadata for PostgreSQL emits a generic placeholder
  (precision=18, scale=0) for NUMERIC columns and omits notNull in
  metadata/config/*.yaml. When an extractor metadata.zip is present alongside
  the config directory, this function restores the exact precision, scale, and
  NOT NULL constraints from is_columns_private.csv.

  Args:
    yaml_meta: Metadata dictionary loaded from BQMS YAML config files.
    zip_meta: Metadata dictionary loaded from extractor metadata.zip.
  """
  # Match (database, schema, table, column) with exact identifier case first
  # (PostgreSQL keeps quoted names like "Report" distinct from report); fall
  # back to a case-insensitive match in a compatible database (same name, or
  # either one empty) only when it is unambiguous.
  def _cat(row: dict[str, str]) -> str:
    return _strip(row.get("TableCatalog")).lower()

  def _key(row: dict[str, str]) -> tuple[str, str, str]:
    return (
        _strip(row.get("TableSchema")),
        _strip(row.get("TableName")),
        _strip(row.get("ColumnName")),
    )

  zip_cols: dict[tuple[str, str, str, str], dict[str, str]] = {}
  zip_cols_lower: dict[tuple[str, ...], list[dict[str, str]]] = {}
  for zc in zip_meta.get("columns", []):
    zip_cols[(_cat(zc),) + _key(zc)] = zc
    lower_key = tuple(k.lower() for k in _key(zc))
    zip_cols_lower.setdefault(lower_key, []).append(zc)

  for yc in yaml_meta.get("columns", []):
    y_cat = _cat(yc)
    zc = zip_cols.get((y_cat,) + _key(yc))
    if not zc:
      candidates = [
          c
          for c in zip_cols_lower.get(tuple(k.lower() for k in _key(yc)), [])
          if not y_cat or not _cat(c) or _cat(c) == y_cat
      ]
      zc = candidates[0] if len(candidates) == 1 else None
    if not zc:
      continue
    if zc.get("ExplicitNotNull") == "Y":
      yc["ExplicitNotNull"] = "Y"
      yc["Nullable"] = "N"
    if (
        yc.get("DataType") in ("NUMERIC", "DECIMAL", "DEC", "NUMBER")
        and yc.get("NumericPrecision") == "18"
        and yc.get("NumericScale") == "0"
    ):
      yc["NumericPrecision"] = zc.get("NumericPrecision", "")
      yc["NumericScale"] = zc.get("NumericScale", "")
      # BQMS may map the (18, 0) placeholder to INT64; drop that target when
      # the restored type has a fractional part or more than 18 digits, so
      # the NUMERIC(p, s) projection keeps the decimals.
      prec = yc["NumericPrecision"]
      fits_int64 = (
          yc["NumericScale"] == "0" and prec.isdigit() and 1 <= int(prec) <= 18
      )
      if yc.get("TargetType") == "INT64" and not fits_int64:
        yc.pop("TargetType", None)


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


def _find_nearby_metadata_zip(
    dir_path: str, search_parents: bool = True
) -> str | None:
  """Searches dir_path and sibling metadata/ directories for a metadata zip.

  Args:
    dir_path: Directory holding the BQMS YAML configs.
    search_parents: Also search metadata/ next to dir_path and its parent. Set
      to False for temporary download directories.

  Returns:
    The path to the first metadata zip found, or None.
  """
  abs_dir = os.path.abspath(dir_path)
  search_roots = [abs_dir]
  if search_parents:
    search_roots += [
        os.path.join(os.path.dirname(abs_dir), "metadata"),
        os.path.join(os.path.dirname(os.path.dirname(abs_dir)), "metadata"),
    ]
  for sroot in search_roots:
    if not os.path.isdir(sroot):
      continue
    for root, _, files in os.walk(sroot):
      for f in sorted(files):
        if f.endswith(".zip") and "metadata" in f.lower():
          return os.path.join(root, f)
  return None


def load_metadata_from_dir(
    dir_path: str,
    zip_bytes: bytes | None = None,
    search_parents: bool = True,
) -> dict[str, list[dict[str, str]]]:
  """Discovers metadata in a directory (BQMS YAML configs or embedded zip).

  Args:
    dir_path: Local translation metadata or config directory.
    zip_bytes: Optional extractor metadata.zip content (from --metadata-zip)
      used to enrich YAML columns. When omitted, a nearby metadata zip is
      searched for instead.
    search_parents: Allow the nearby-zip search to look in metadata/ directories
      next to dir_path and its parent.

  Returns:
    A dictionary containing 'tables' and 'columns' metadata.
  """
  config_dir = _find_config_dir(dir_path)
  if config_dir:
    res = load_metadata_from_config_dir(config_dir)
    if res["tables"] and res["columns"]:
      if zip_bytes is not None:
        _enrich_yaml_columns_from_zip(res, load_metadata_from_zip(zip_bytes))
        return res
      zip_path = _find_nearby_metadata_zip(
          dir_path, search_parents=search_parents
      )
      if zip_path:
        try:
          with open(zip_path, "rb") as zf:
            zip_meta = load_metadata_from_zip(zf.read())
          _enrich_yaml_columns_from_zip(res, zip_meta)
        except (OSError, zipfile.BadZipFile):
          pass
      return res

  if zip_bytes is not None:
    return load_metadata_from_zip(zip_bytes)

  for root, _, files in os.walk(dir_path):
    for f in files:
      if f.endswith(".zip") and "metadata" in f:
        with open(os.path.join(root, f), "rb") as zf:
          return load_metadata_from_zip(zf.read())

  return {"tables": [], "columns": []}


def _resolve_and_load_metadata(
    path_or_uri: str | None,
    metadata_zip_path_or_uri: str | None = None,
) -> dict[str, list[dict[str, str]]]:
  """Resolves local or Cloud Storage metadata path/zip and loads metadata.

  Args:
    path_or_uri: Translation metadata directory, config directory, or zip.
    metadata_zip_path_or_uri: Optional extractor metadata.zip. Used on its own
      when path_or_uri is empty, or to enrich YAML configs from path_or_uri.

  Returns:
    A dictionary containing 'tables' and 'columns' metadata.
  """
  zip_bytes = (
      read_file_or_gcs(metadata_zip_path_or_uri)
      if metadata_zip_path_or_uri
      else None
  )
  if not path_or_uri:
    if zip_bytes is not None:
      return load_metadata_from_zip(zip_bytes)
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
      # The temp dir lives under the shared temp root, so never search its
      # parent directories for a metadata zip.
      return load_metadata_from_dir(
          temp_dir, zip_bytes=zip_bytes, search_parents=False
      )
  if os.path.isdir(path_or_uri):
    return load_metadata_from_dir(path_or_uri, zip_bytes=zip_bytes)
  return load_metadata_from_zip(read_file_or_gcs(path_or_uri))


def _ordinal(col: dict[str, str]) -> int:
  pos = str(col.get("OrdinalPosition", ""))
  return int(pos) if pos.isdigit() else 999999


def _select_databases(
    metadata: dict[str, list[dict[str, str]]],
    databases: list[str] | None = None,
) -> dict[str, list[dict[str, str]]]:
  """Keeps one database's copy of each schema.table.

  A PostgreSQL connection reads one database and the generated SQL is
  schema-qualified, so same-named tables from several databases in one BQMS
  config directory (db1.public.orders and db2.public.orders) can't share a
  script. Tables from databases outside `databases` are dropped (tables without
  a database qualifier are kept). When a schema.table still appears under more
  than one database, the first one is kept and a warning names the others.

  Args:
    metadata: Metadata dictionary with 'tables' and 'columns' lists.
    databases: Optional database allow-list (case-insensitive).

  Returns:
    The metadata dictionary restricted to one database per schema.table.
  """
  wanted = {d.lower() for d in databases} if databases else None

  def _key(row: dict[str, str]) -> tuple[str, str]:
    return (_strip(row.get("TableSchema")), _strip(row.get("TableName")))

  def _wanted(cat: str) -> bool:
    return not wanted or not cat or cat.lower() in wanted

  rows = metadata.get("tables", [])
  if wanted:
    # An exact --database match wins over a table without a database.
    rows = sorted(
        rows, key=lambda t: _strip(t.get("TableCatalog")).lower() not in wanted
    )
  chosen: dict[tuple[str, str], str] = {}
  duplicated: set[tuple[str, str]] = set()
  tables: list[dict[str, str]] = []
  for t in rows:
    cat = _strip(t.get("TableCatalog"))
    if not _wanted(cat):
      continue
    key = _key(t)
    if key in chosen and chosen[key].lower() != cat.lower():
      print(
          f"WARNING: Skipping {cat}.{key[0]}.{key[1]}: {key[0]}.{key[1]} was"
          f" already loaded from database '{chosen[key]}'; pass --database to"
          " choose which database to export.",
          file=sys.stderr,
      )
      duplicated.add(key)
      continue
    chosen.setdefault(key, cat)
    tables.append(t)

  def _same_db(c: dict[str, str]) -> bool:
    chosen_cat = chosen.get(_key(c), "").lower()
    col_cat = _strip(c.get("TableCatalog")).lower()
    if chosen_cat == col_cat:
      return True
    # A database-less table or column matches any database, unless the
    # schema.table has copies in several databases.
    return _key(c) not in duplicated and not (chosen_cat and col_cat)

  columns = [
      c
      for c in metadata.get("columns", [])
      if _wanted(_strip(c.get("TableCatalog"))) and _same_db(c)
  ]
  return {"tables": tables, "columns": columns}


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
      if schema.lower() in _SYSTEM_SCHEMAS and (
          not schemas or schema.upper() not in schemas
      ):
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
      if schema.lower() in _SYSTEM_SCHEMAS and (
          not schemas or schema.upper() not in schemas
      ):
        continue
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
      if schema.lower() in _SYSTEM_SCHEMAS and (
          not schemas or schema.upper() not in schemas
      ):
        continue
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

# PostgreSQL folds unquoted identifiers to lowercase, so only lowercase names
# stay unquoted; mixed-case or uppercase catalog names are double-quoted to
# keep their exact case.
_VALID_IDENT_REGEX = re.compile(r"^[a-z_][a-z0-9_$]*$")

# PostgreSQL reserved words that commonly appear as column or table names in
# migrated schemas. Anything matching is double-quoted.
_POSTGRES_RESERVED = frozenset((
    "ALL",
    "ANALYSE",
    "ANALYZE",
    "AND",
    "ANY",
    "ARRAY",
    "AS",
    "ASC",
    "ASYMMETRIC",
    "AUTHORIZATION",
    "BINARY",
    "BOTH",
    "CASE",
    "CAST",
    "CHECK",
    "COLLATE",
    "COLUMN",
    "CONCURRENTLY",
    "CONSTRAINT",
    "CREATE",
    "CROSS",
    "CURRENT_CATALOG",
    "CURRENT_DATE",
    "CURRENT_ROLE",
    "CURRENT_SCHEMA",
    "CURRENT_TIME",
    "CURRENT_TIMESTAMP",
    "CURRENT_USER",
    "DEFAULT",
    "DEFERRABLE",
    "DESC",
    "DISTINCT",
    "DO",
    "ELSE",
    "END",
    "EXCEPT",
    "FALSE",
    "FETCH",
    "FOR",
    "FOREIGN",
    "FREEZE",
    "FROM",
    "FULL",
    "GRANT",
    "GROUP",
    "HAVING",
    "ILIKE",
    "IN",
    "INITIALLY",
    "INNER",
    "INTERSECT",
    "INTO",
    "IS",
    "ISNULL",
    "JOIN",
    "LATERAL",
    "LEADING",
    "LEFT",
    "LIKE",
    "LIMIT",
    "LOCALTIME",
    "LOCALTIMESTAMP",
    "NATURAL",
    "NOT",
    "NOTNULL",
    "NULL",
    "OFFSET",
    "ON",
    "ONLY",
    "OR",
    "ORDER",
    "OUTER",
    "OVERLAPS",
    "PLACING",
    "PRIMARY",
    "REFERENCES",
    "RETURNING",
    "RIGHT",
    "SELECT",
    "SESSION_USER",
    "SIMILAR",
    "SOME",
    "SYMMETRIC",
    "TABLE",
    "TABLESAMPLE",
    "THEN",
    "TO",
    "TRAILING",
    "TRUE",
    "UNION",
    "UNIQUE",
    "USER",
    "USING",
    "VARIADIC",
    "VERBOSE",
    "WHEN",
    "WHERE",
    "WINDOW",
    "WITH",
))

_INT_TYPES = frozenset((
    "SMALLINT",
    "INT2",
    "INTEGER",
    "INT",
    "INT4",
    "BIGINT",
    "INT8",
    "SERIAL",
    "SMALLSERIAL",
    "BIGSERIAL",
    "SERIAL2",
    "SERIAL4",
    "SERIAL8",
    "TINYINT",
    "BYTEINT",
    "INT64",
    "OID",
))
_NUMBER_TYPES = frozenset(("NUMERIC", "DECIMAL", "DEC", "NUMBER", "BIGNUMERIC"))
_MONEY_TYPES = frozenset(("MONEY",))
_FLOAT_TYPES = frozenset((
    "REAL",
    "FLOAT4",
    "DOUBLE PRECISION",
    "FLOAT8",
    "FLOAT",
    "DOUBLE",
    "FLOAT64",
))
_BOOL_TYPES = frozenset(("BOOLEAN", "BOOL"))
_DATE_TYPES = frozenset(("DATE",))
_TIME_TYPES = frozenset(("TIME", "TIME WITHOUT TIME ZONE"))
_TIMETZ_TYPES = frozenset(("TIMETZ", "TIME WITH TIME ZONE"))
_TIMESTAMP_TYPES = frozenset((
    "TIMESTAMP",
    "TIMESTAMP WITHOUT TIME ZONE",
    "DATETIME",
))
_TIMESTAMP_TZ_TYPES = frozenset((
    "TIMESTAMPTZ",
    "TIMESTAMP WITH TIME ZONE",
))
_CHAR_TYPES = frozenset(("CHAR", "CHARACTER", "BPCHAR", "NCHAR"))
_VARCHAR_TYPES = frozenset((
    "VARCHAR",
    "CHARACTER VARYING",
    "TEXT",
    "CITEXT",
    "NAME",
    "STRING",
    "NVARCHAR",
))
_BYTE_TYPES = frozenset(("BYTEA", "BINARY", "VARBINARY", "BYTES"))
_TEXT_CAST_TYPES = frozenset((
    "JSON",
    "JSONB",
    "XML",
    "UUID",
    "INET",
    "CIDR",
    "MACADDR",
    "MACADDR8",
    "INTERVAL",
    "BIT",
    "BIT VARYING",
    "VARBIT",
    "TSVECTOR",
    "TSQUERY",
    "PG_LSN",
    "TXID_SNAPSHOT",
    "PG_SNAPSHOT",
    "POINT",
    "LINE",
    "LSEG",
    "BOX",
    "PATH",
    "POLYGON",
    "CIRCLE",
    "INT4RANGE",
    "INT8RANGE",
    "NUMRANGE",
    "TSRANGE",
    "TSTZRANGE",
    "DATERANGE",
    "ARRAY",
    "USER-DEFINED",
))


# DEFAULT SCAFFOLDING: Identifier quoting helper.
def quote_ident(ident: str) -> str:
  """Double-quotes a PostgreSQL identifier when it is not a plain name.

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
  if not _VALID_IDENT_REGEX.match(ident) or ident.upper() in _POSTGRES_RESERVED:
    escaped = ident.replace('"', '""')
    return f'"{escaped}"'
  return ident


_PARAM_TYPE_REGEX = re.compile(
    r"^(?P<base>[A-Z0-9_ ]+?)\s*\(\s*(?P<p>-?\d+|\*)"
    r"(?:\s*,\s*(?P<s>-?\d+))?\s*\)\s*(?P<rest>.*)$"
)


def _to_int(value: str | None) -> int | None:
  value = str(value or "").strip()
  return int(value) if value.lstrip("-").isdigit() else None


def _normalize_data_type(
    raw_type: str, precision: int | None, scale: int | None
) -> tuple[str, int | None, int | None]:
  """Normalizes a PostgreSQL DATA_TYPE string into (base_type, p, s)."""
  dt = " ".join(raw_type.upper().split())
  scale = _decode_pg_scale(scale)
  if dt.startswith("INTERVAL"):
    return "INTERVAL", precision, scale
  if dt.endswith("[]") or dt.startswith("_"):
    return "ARRAY", precision, scale
  m = _PARAM_TYPE_REGEX.match(dt)
  if m:
    base = f"{m.group('base').strip()} {m.group('rest').strip()}".strip()
    if precision is None and m.group("p") != "*":
      precision = _to_int(m.group("p"))
    if scale is None and m.group("s") is not None:
      scale = _decode_pg_scale(_to_int(m.group("s")))
    # In PostgreSQL SQL, NUMERIC(p) with a single argument means NUMERIC(p, 0).
    if base in _NUMBER_TYPES and precision is not None and scale is None:
      scale = 0
    return base, precision, scale
  return dt, precision, scale


# CUSTOMIZE: Custom Type Projections -- Edit format_column_cast() to change
# how a PostgreSQL type is projected before Parquet serialization (e.g. keep
# CHAR padding, widen unconstrained NUMERIC scale, or cast NUMERIC(p,0) to
# BIGINT when targeting INT64).
def format_column_cast(
    col: dict[str, str],
    target_bq_type: str | None = None,
    rtrim_char: bool = True,
    unbounded_number_scale: int = 9,
) -> str:
  """Generates a type-safe PostgreSQL projection expression for Parquet export.

  The executor derives the Parquet schema from `cursor.description`, so the
  SQL projection here determines both the PyArrow type and the BigQuery column
  type compatible with `bq load --source_format=PARQUET`:

    SMALLINT / INTEGER / BIGINT / SERIAL -> CAST AS BIGINT        -> INT64
    NUMERIC(p, 0)                        -> CAST AS NUMERIC(p, 0) -> NUMERIC
    NUMERIC(p, s > 0)                    -> CAST AS NUMERIC(p, s) -> NUMERIC
    NUMERIC(p, s < 0)                    -> CAST AS NUMERIC(p+|s|, 0) -> NUMERIC
    NUMERIC (unconstrained)              -> CAST AS NUMERIC(38, 9) -> BIGNUMERIC
    MONEY                                -> CAST AS NUMERIC(38, 2) -> BIGNUMERIC
    REAL / DOUBLE PRECISION              -> CAST AS DOUBLE PRECISION -> FLOAT64
    BOOLEAN                              -> col                   -> BOOL
    DATE                                 -> col                   -> DATE
    TIME / TIMETZ                        -> CAST AS TIME(6)       -> TIME
    TIMESTAMP WITHOUT TIME ZONE          -> CAST AS TIMESTAMP(6) WITHOUT TZ
    TIMESTAMP WITH TIME ZONE             -> CAST AS TIMESTAMP(6) WITH TZ
    CHAR(n) / CHARACTER(n) / BPCHAR      -> RTRIM(col)            -> STRING
    VARCHAR / TEXT                       -> col                   -> STRING
    BYTEA                                -> col                   -> BYTES
    JSON / JSONB / XML / UUID / INET /
    CIDR / MACADDR / INTERVAL / BIT      -> CAST AS TEXT          -> STRING/JSON

  Args:
    col: Column metadata dict containing ColumnName, DataType, etc.
    target_bq_type: Optional BigQuery target type override.
    rtrim_char: Strip CHAR(n)/BPCHAR trailing pad spaces (BigQuery STRING has no
      fixed-width semantics, so padded values would mismatch in validation).
    unbounded_number_scale: Fractional scale for unconstrained NUMERIC columns
      (default 9, supporting up to 29 integer digits).

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

  # When the BQMS target already matches the source type family, keep the
  # default projection below (preserves CHAR(n)/BPCHAR RTRIM for STRING targets
  # and keeps YAML output identical to metadata.zip output).
  if (
      (explicit_base == "DATE" and data_type in _DATE_TYPES)
      or (explicit_base in ("BOOL", "BOOLEAN") and data_type in _BOOL_TYPES)
      or (
          explicit_base == "STRING"
          and (data_type in _CHAR_TYPES or data_type in _VARCHAR_TYPES)
      )
      or (explicit_base == "BYTES" and data_type in _BYTE_TYPES)
  ):
    explicit_base = ""

  # Honor explicit target_bq_type overrides first.
  if explicit_base:
    if explicit_base in (
        "INT64",
        "INTEGER",
        "BIGINT",
        "SMALLINT",
        "TINYINT",
        "BYTEINT",
    ):
      return f"CAST({col_name} AS BIGINT) AS {col_name}"
    if explicit_base in ("FLOAT64", "FLOAT", "DOUBLE"):
      return f"CAST({col_name} AS DOUBLE PRECISION) AS {col_name}"
    if explicit_base in ("BOOL", "BOOLEAN"):
      return f"CAST({col_name} AS BOOLEAN) AS {col_name}"
    if explicit_base == "DATE":
      return f"CAST({col_name} AS DATE) AS {col_name}"
    if explicit_base == "TIME":
      return f"CAST({col_name} AS TIME(6)) AS {col_name}"
    # AT TIME ZONE 'UTC' keeps timestamp <-> timestamptz conversions
    # independent of the session TimeZone.
    if explicit_base == "DATETIME":
      src = (
          f"({col_name} AT TIME ZONE 'UTC')"
          if data_type in _TIMESTAMP_TZ_TYPES
          else col_name
      )
      return f"CAST({src} AS TIMESTAMP(6) WITHOUT TIME ZONE) AS {col_name}"
    if explicit_base == "TIMESTAMP":
      src = (
          f"(CAST({col_name} AS TIMESTAMP) AT TIME ZONE 'UTC')"
          if data_type in _TIMESTAMP_TYPES or data_type in _DATE_TYPES
          else col_name
      )
      return f"CAST({src} AS TIMESTAMP(6) WITH TIME ZONE) AS {col_name}"
    if explicit_base in ("STRING", "JSON"):
      return f"CAST({col_name} AS TEXT) AS {col_name}"
    if explicit_base == "BYTES":
      return f"CAST({col_name} AS BYTEA) AS {col_name}"
    if explicit_base in ("NUMERIC", "DECIMAL"):
      if data_type in _MONEY_TYPES:
        return f"CAST({col_name} AS NUMERIC(38, 2)) AS {col_name}"
      if scale is not None and scale > 0:
        s_val = min(scale, 38)
        p_val = min(max(precision or 29, s_val, 1), 38)
        return f"CAST({col_name} AS NUMERIC({p_val}, {s_val})) AS {col_name}"
      if scale is not None and scale <= 0:
        p_val = min(max((precision or 29) + abs(scale), 1), 38)
        return f"CAST({col_name} AS NUMERIC({p_val}, 0)) AS {col_name}"
      return (
          f"CAST({col_name} AS NUMERIC(38, {default_unb_scale})) AS {col_name}"
      )
    if explicit_base == "BIGNUMERIC":
      if data_type in _MONEY_TYPES:
        return f"CAST({col_name} AS NUMERIC(38, 2)) AS {col_name}"
      if scale is not None and scale > 0:
        s_val = min(scale, 38)
        p_val = min(max(precision or 38, s_val, 1), 38)
        return f"CAST({col_name} AS NUMERIC({p_val}, {s_val})) AS {col_name}"
      if scale is not None and scale <= 0:
        return f"CAST({col_name} AS NUMERIC(38, 0)) AS {col_name}"
      return (
          f"CAST({col_name} AS NUMERIC(38, {default_unb_scale})) AS {col_name}"
      )

  if data_type in _INT_TYPES:
    return f"CAST({col_name} AS BIGINT) AS {col_name}"

  if data_type in _MONEY_TYPES:
    return f"CAST({col_name} AS NUMERIC(38, 2)) AS {col_name}"

  if data_type in _NUMBER_TYPES:
    if scale is None:
      return (
          f"CAST({col_name} AS NUMERIC(38, {default_unb_scale})) AS {col_name}"
      )
    if scale < 0:
      eff_p = min(max((precision or 29) + abs(scale), 1), 38)
      return f"CAST({col_name} AS NUMERIC({eff_p}, 0)) AS {col_name}"
    if scale == 0:
      p_val = min(max(precision or 29, 1), 38)
      return f"CAST({col_name} AS NUMERIC({p_val}, 0)) AS {col_name}"
    s_val = min(scale, 38)
    p_val = min(max(precision or 38, s_val, 1), 38)
    return f"CAST({col_name} AS NUMERIC({p_val}, {s_val})) AS {col_name}"

  if data_type in _FLOAT_TYPES:
    return f"CAST({col_name} AS DOUBLE PRECISION) AS {col_name}"

  if data_type in _BOOL_TYPES or data_type in _DATE_TYPES:
    return f"{col_name} AS {col_name}"

  if data_type in _TIME_TYPES or data_type in _TIMETZ_TYPES:
    return f"CAST({col_name} AS TIME(6)) AS {col_name}"

  if data_type in _TIMESTAMP_TYPES:
    return f"CAST({col_name} AS TIMESTAMP(6) WITHOUT TIME ZONE) AS {col_name}"

  if data_type in _TIMESTAMP_TZ_TYPES:
    return f"CAST({col_name} AS TIMESTAMP(6) WITH TIME ZONE) AS {col_name}"

  if data_type in _CHAR_TYPES:
    if rtrim_char:
      return f"RTRIM({col_name}) AS {col_name}"
    return f"{col_name} AS {col_name}"

  if data_type in _VARCHAR_TYPES or data_type in _BYTE_TYPES:
    return f"{col_name} AS {col_name}"

  if data_type in _TEXT_CAST_TYPES:
    return f"CAST({col_name} AS TEXT) AS {col_name}"

  return f"CAST({col_name} AS TEXT) AS {col_name}"


# DEFAULT SCAFFOLDING: Table name qualification helper.
def _build_qualified_table_name(
    table_meta: dict[str, str], default_schema: str = ""
) -> str:
  """Builds a quoted schema.table name."""
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
  """Builds the explicit-cast SELECT statement for a single PostgreSQL table.

  Args:
    table_meta: Table metadata dictionary with TableSchema and TableName.
    columns: Ordered list of column metadata dictionaries for the table.
    default_schema: Fallback schema name when TableSchema is empty.
    rtrim_char: Whether to RTRIM fixed-width CHAR(n)/BPCHAR columns.
    unbounded_number_scale: Fractional scale for unconstrained NUMERIC columns.

  Returns:
    A complete PostgreSQL SELECT statement ending with a semicolon.
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
    metadata_zip_path_or_uri: str | None = None,
    databases: list[str] | None = None,
) -> str:
  """Generates the unified PostgreSQL export SQL script.

  Each table section is introduced by a divider and a
  `-- Unload Table: <SCHEMA>.<TABLE> -> Parquet` marker that the executor uses
  to name the ./data_unload/[<SCHEMA>/]<TABLE>/ output directory.

  Args:
    metadata_path_or_uri: Path or Cloud Storage URI to translation metadata dir
      or zip.
    default_schema: Fallback schema when metadata omits it.
    schemas: Optional schema allow-list (case-insensitive).
    rtrim_char: Strip CHAR(n)/BPCHAR trailing pad spaces.
    unbounded_number_scale: Fractional scale for unconstrained NUMERIC columns.
    metadata_zip_path_or_uri: Optional path or Cloud Storage URI to an extractor
      metadata.zip. Used alone, or alongside metadata_path_or_uri to restore
      exact NUMERIC(p, s) and NOT NULL details in BQMS YAML configs.
    databases: Optional database allow-list (case-insensitive), matched against
      the database part of 3-part metadata names.

  Returns:
    A complete PostgreSQL SQL script string.
  """
  all_metadata = _resolve_and_load_metadata(
      metadata_path_or_uri, metadata_zip_path_or_uri
  )
  metadata = _select_databases(all_metadata, databases)
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
  if not tables and (schema_filter or databases):
    rows = all_metadata.get("tables", []) or all_metadata.get("columns", [])
    available = sorted(
        {_strip(t.get("TableSchema")) or _strip(default_schema) for t in rows}
    )
    dbs = sorted({_strip(t.get("TableCatalog")) for t in rows} - {""})
    print(
        "WARNING: No tables match the --schema/--database filters. Available"
        f" schemas: {', '.join(s for s in available if s) or '(none)'};"
        f" databases: {', '.join(dbs) or '(none)'}.",
        file=sys.stderr,
    )
  generator_name = (
      os.path.basename(sys.argv[0]) if sys.argv and sys.argv[0] else ""
  ) or "export_postgres_tables_template.py"

  lines = [
      "-- " + "=" * 77,
      "-- PostgreSQL to Parquet Type-Safe Data Export Script",
      f"-- Generated by bigquery-migration-data-exporter / {generator_name}",
      "-- Execute via psycopg2 and stream results to Snappy Parquet",
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
  """Builds and parses CLI arguments for PostgreSQL export SQL generation."""
  parser = argparse.ArgumentParser(
      description="PostgreSQL Parquet Export SQL Generator (outputs .sql)."
  )
  parser.add_argument(
      "--translation-metadata-dir",
      "--translation-output",
      "--metadata-dir",
      "--config-dir",
      dest="metadata_path",
      help=(
          "Path or Cloud Storage URI to translation_output/metadata directory"
          " or config directory"
      ),
  )
  parser.add_argument(
      "--metadata-zip",
      dest="metadata_zip",
      help=(
          "Path or Cloud Storage URI to a PostgreSQL extractor metadata.zip."
          " Use it alone, or with --translation-metadata-dir to restore exact"
          " NUMERIC(p, s) and NOT NULL details in the BQMS YAML configs"
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
      dest="default_schema",
      default=os.environ.get("PG_SCHEMA", ""),
      help="Fallback source schema name (exact case) when omitted in metadata",
  )
  parser.add_argument(
      "--schema",
      action="append",
      dest="schemas",
      help="Only export tables in this schema (repeatable)",
  )
  parser.add_argument(
      "--database",
      action="append",
      dest="databases",
      help=(
          "Only export tables from this PostgreSQL database (repeatable),"
          " matched against the database part of 3-part metadata names;"
          " tables without a database qualifier are kept"
      ),
  )
  parser.add_argument(
      "--keep-char-padding",
      action="store_true",
      help="Do not RTRIM CHAR(n)/BPCHAR columns",
  )
  parser.add_argument(
      "--unbounded-number-scale",
      type=int,
      default=9,
      help=(
          "Decimal scale (0..38) for unconstrained NUMERIC columns"
          " (default: 9, supporting up to 29 integer digits)"
      ),
  )
  parsed = parser.parse_args(args)
  if not parsed.metadata_path and not parsed.metadata_zip:
    parser.error(
        "one of --translation-metadata-dir or --metadata-zip is required."
    )
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
  """CLI entrypoint for the PostgreSQL Parquet export SQL generator."""
  args = _parse_args()
  sql = generate_export_sql(
      metadata_path_or_uri=args.metadata_path,
      default_schema=args.default_schema,
      schemas=args.schemas,
      rtrim_char=not args.keep_char_padding,
      unbounded_number_scale=args.unbounded_number_scale,
      metadata_zip_path_or_uri=args.metadata_zip,
      databases=args.databases,
  )
  if (args.schemas or args.databases) and "-- Unload Table:" not in sql:
    sys.exit("ERROR: No tables to export; check --schema/--database.")
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
