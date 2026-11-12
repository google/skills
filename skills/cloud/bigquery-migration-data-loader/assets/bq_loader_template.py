#!/usr/bin/env python3
r"""Template Script for Automated BigQuery Dataset Provisioning, Parquet Loading, and View Deployment.

This asset template script provides a reference implementation that directly
consumes BQMS translation_output/metadata directories, provisions the target
BigQuery dataset if missing, executes concurrent bq load operations for staged
Parquet files (auto-creating native BigQuery tables), audits loaded row counts,
and deploys translated views from local or Cloud Storage translation output.

Usage Pattern:
  Copy `assets/bq_loader_template.py` from this skill's directory (`SKILL_DIR`,
  the directory containing `SKILL.md`) into your
  working directory (for example, `./bq_loader.py`). Run the copy as-is for standard
  ingestion, and prioritize modifying the marked `# CUSTOMIZE:` extension points
  if your project requires custom schema overrides, partitioning/clustering
  flags, custom view regex rewrites, retry policies, or custom post-load audit
  queries. Sections marked `# DEFAULT SCAFFOLDING` can be kept unchanged unless
  deeper orchestration adjustments are needed.

Dependencies:
  pip install pyyaml==6.0.2

Usage Examples:
    # Copy the template from this skill's directory to your working directory:
    cp SKILL_DIR/assets/bq_loader_template.py ./bq_loader.py

    # 1. Load native Parquet tables and deploy views directly from Cloud Storage
    #    translation output:
    python3 ./bq_loader.py \
        --project my-project-id \
        --dataset my_dataset \
        --location us-central1 \
        --translation-metadata-dir gs://my-bucket/translation_output/metadata/ \
        --parquet-base-uri gs://my-bucket/data_unload/ \
        --concurrency 8

    # 2. Load from local translation output directory:
    python3 ./bq_loader.py \
        --project my-project-id \
        --dataset my_dataset \
        --translation-metadata-dir TRANSLATION_OUTPUT/metadata \
        --parquet-base-uri gs://my-bucket/data_unload/ \
        --concurrency 4
"""

from __future__ import annotations

import argparse
import collections.abc
import concurrent.futures
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
from typing import Any

import yaml

# ==============================================================================
# 1. File & Metadata Discovery Helpers (DEFAULT SCAFFOLDING)
# ==============================================================================
# DEFAULT SCAFFOLDING: Deterministic Cloud Storage and local file helpers.

_PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.\-:]+$")
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_\-]+$")
_DATASET_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
_CREATE_TABLE_REGEX = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"`?(?:[A-Za-z0-9_.\-:]+`?\.`?){0,2}([A-Za-z0-9_\-]+)`?(?=\s|\(|;|$)",
    re.IGNORECASE,
)
# CUSTOMIZE: Custom View Rewriting & Deployment — Set to False if you
# pre-created tables from translated DDLs with native JSON columns (loaded with
# --replace=false). The wrap repairs LAX_*/STRING(JSON_QUERY(...)) calls when
# Parquet loads JSON source columns as STRING, but PARSE_JSON() accepts only
# STRING, so SAFE.PARSE_JSON() fails SQL analysis on native JSON columns.
_WRAP_JSON_QUERY_WITH_PARSE_JSON = True
_JSON_WRAP_PATTERN = re.compile(
    r"\b(lax_(?:float64|int64|bool|string)|string)\s*\(\s*json_query\s*\(\s*([^,]+?)\s*,\s*('[^']+'|\"[^\"]+\")\s*\)\s*\)",
    re.IGNORECASE,
)
_CREATE_VIEW_PATTERN = re.compile(
    r"\bCREATE\s+VIEW\b(?!\s+IF\s+NOT\s+EXISTS\b)", re.IGNORECASE
)
_MASK_TOKEN_PATTERN = re.compile(r"\ue000(\d+)\ue001")
_AUDIT_CHUNK_SIZE = 500


def read_file_or_gcs(path_or_uri: str) -> str:
  """Reads text content from a local file path or Cloud Storage URI.

  Args:
    path_or_uri: Local filesystem path or gs:// URI.

  Returns:
    The file text content decoded as UTF-8.

  Raises:
    subprocess.CalledProcessError: If reading from Cloud Storage fails.
    OSError: If reading from local filesystem fails.
  """
  if path_or_uri.startswith("gs://"):
    cmd = ["gcloud", "storage", "cat", path_or_uri]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return res.stdout
  with open(path_or_uri, "r", encoding="utf-8-sig", errors="replace") as f:
    return f.read()


def list_and_read_sql_files(dir_path_or_uri: str) -> dict[str, str]:
  """Discovers and reads SQL statement files from a local directory or Cloud Storage URI.

  Args:
    dir_path_or_uri: Local directory path or gs:// URI to search for SQL files.

  Returns:
    A dictionary mapping uppercase base filename (without .sql) to file content.
  """
  results: dict[str, str] = {}
  if dir_path_or_uri.startswith("gs://"):
    temp_dir = tempfile.mkdtemp(prefix="bq_views_")
    try:
      cmd = [
          "gcloud",
          "storage",
          "cp",
          "-r",
          f"{dir_path_or_uri.rstrip('/')}/**.sql",
          temp_dir,
      ]
      res = subprocess.run(cmd, capture_output=True, text=True, check=False)
      if res.returncode == 0:
        dir_path = pathlib.Path(temp_dir)
        for sql_path in sorted(dir_path.rglob("*.sql")):
          try:
            results[sql_path.stem.upper()] = sql_path.read_text(
                encoding="utf-8-sig", errors="replace"
            )
          except OSError as e:
            print(f"Warning: Failed to read SQL from file {sql_path}: {e}")
      else:
        # Fallback to single-file discovery if recursive wildcard copy fails
        ls_cmd = [
            "gcloud",
            "storage",
            "ls",
            "--recursive",
            f"{dir_path_or_uri.rstrip('/')}/**.sql",
        ]
        ls_res = subprocess.run(
            ls_cmd, capture_output=True, text=True, check=False
        )
        if ls_res.returncode == 0:
          uris = [
              line.strip()
              for line in ls_res.stdout.splitlines()
              if line.strip().endswith(".sql")
          ]
          for uri in uris:
            try:
              sql_text = read_file_or_gcs(uri)
              base_name = uri.rsplit("/", 1)[-1].rsplit(".", 1)[0].upper()
              results[base_name] = sql_text
            except (subprocess.SubprocessError, OSError) as e:
              print(
                  f"Warning: Failed to read SQL from Cloud Storage {uri}: {e}"
              )
    finally:
      shutil.rmtree(temp_dir, ignore_errors=True)
  else:
    dir_path = pathlib.Path(dir_path_or_uri)
    if dir_path.is_dir():
      for sql_path in sorted(dir_path.rglob("*.sql")):
        try:
          results[sql_path.stem.upper()] = sql_path.read_text(
              encoding="utf-8-sig", errors="replace"
          )
        except OSError as e:
          print(f"Warning: Failed to read SQL from file {sql_path}: {e}")
  return results


# CUSTOMIZE: Connection & CLI Wrapper — Edit ensure_dataset(),
# load_parquet_table(), or execute_sql() to pass custom bq CLI flags (for
# example, --default_kms_key in ensure_dataset(), or --destination_kms_key and
# --reservation_id in load_parquet_table() and execute_sql()).
def ensure_dataset(project_id: str, dataset_id: str, location: str) -> None:
  """Checks if the BigQuery dataset exists, creating it if missing.

  Args:
    project_id: Target Google Cloud project ID.
    dataset_id: Target BigQuery dataset ID.
    location: Geographic location where the dataset should reside.

  Raises:
    subprocess.CalledProcessError: If dataset creation command fails.
  """
  show_cmd = [
      "bq",
      "show",
      "--dataset",
      f"--project_id={project_id}",
      dataset_id,
  ]
  check = subprocess.run(show_cmd, capture_output=True, text=True, check=False)
  if check.returncode != 0:
    print(
        f"Dataset {project_id}:{dataset_id} not found. Creating in"
        f" {location}..."
    )
    mk_cmd = [
        "bq",
        "mk",
        "--dataset",
        f"--project_id={project_id}",
        f"--location={location}",
        dataset_id,
    ]
    subprocess.run(mk_cmd, check=True)
    print(f"Created dataset {project_id}:{dataset_id}")
  else:
    print(f"Dataset {project_id}:{dataset_id} already exists.")


def execute_sql(
    project_id: str,
    location: str,
    sql_text: str,
    max_rows: int | None = None,
) -> None:
  """Executes a SQL batch script against BigQuery using standard SQL syntax.

  Args:
    project_id: Target Google Cloud project ID.
    location: BigQuery job processing location.
    sql_text: SQL script content to execute.
    max_rows: Optional number of result rows to print (`bq query` prints at most
      100 rows by default).

  Raises:
    subprocess.CalledProcessError: If SQL execution fails.
  """
  cmd = [
      "bq",
      "query",
      f"--project_id={project_id}",
      f"--location={location}",
      "--use_legacy_sql=false",
  ]
  if max_rows is not None:
    cmd.append(f"--max_rows={max_rows}")
  subprocess.run(cmd, input=sql_text, text=True, check=True)


# DEFAULT SCAFFOLDING: Metadata staging, config discovery, and URI resolution.
def _stage_translation_metadata_dir(
    path_or_uri: str,
) -> tuple[str, str | None]:
  """Stages metadata to a local directory if the source is on Cloud Storage.

  Args:
    path_or_uri: Local directory path or Cloud Storage URI to
      translation_output/metadata.

  Returns:
    A tuple of (dir_to_scan, temp_dir) where temp_dir is populated if a
    temporary directory was created for Cloud Storage synchronization.

  Raises:
    subprocess.CalledProcessError: If copying from Cloud Storage fails.
    OSError: If the temporary directory cannot be populated.
  """
  if not path_or_uri.startswith("gs://"):
    return path_or_uri, None

  temp_dir = tempfile.mkdtemp(prefix="bqms_loader_meta_")
  try:
    cmd = [
        "gcloud",
        "storage",
        "cp",
        "-r",
        path_or_uri.rstrip("/") + "/*",
        temp_dir,
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return temp_dir, temp_dir
  except (subprocess.CalledProcessError, OSError) as e:
    print(f"Error: Failed to copy translation metadata from {path_or_uri}: {e}")
    stderr = getattr(e, "stderr", None)
    if isinstance(stderr, bytes):
      stderr = stderr.decode("utf-8", errors="replace")
    if stderr and stderr.strip():
      print(stderr.strip())
    shutil.rmtree(temp_dir, ignore_errors=True)
    raise


def _parse_config_yamls(
    dir_to_scan: str,
) -> tuple[
    list[dict[str, str]],
    list[dict[str, Any]],
    set[tuple[str, str, str]],
]:
  """Parses BQMS metadata config YAML files to discover tables and views.

  Args:
    dir_to_scan: Local path to the metadata directory.

  Returns:
    A tuple of (tables, views, seen_tables), where seen_tables holds uppercase
    (database, schema, table) keys.
  """
  config_dir = os.path.join(dir_to_scan, "metadata", "config")
  if not os.path.isdir(config_dir) and os.path.isdir(
      os.path.join(dir_to_scan, "config")
  ):
    config_dir = os.path.join(dir_to_scan, "config")
  elif not os.path.isdir(config_dir):
    config_dir = dir_to_scan

  tables: list[dict[str, str]] = []
  views: list[dict[str, Any]] = []
  seen_tables: set[tuple[str, str, str]] = set()
  seen_views: set[tuple[str, str, str]] = set()

  if not os.path.isdir(config_dir):
    return tables, views, seen_tables

  for root, _, files in os.walk(config_dir):
    for f in sorted(files):
      if not (f.endswith(".yaml") or f.endswith(".yml")):
        continue
      fpath = os.path.join(root, f)
      try:
        with open(fpath, "r", encoding="utf-8-sig") as yf:
          cfg = yaml.safe_load(yf) or {}
      except (yaml.YAMLError, OSError) as e:
        print(f"Warning: Failed to parse config YAML {fpath}: {e}")
        continue

      if not isinstance(cfg, dict):
        continue

      src_name = cfg.get("sourceName", "")
      parts = src_name.split(".") if src_name else []
      table_name = parts[-1] if parts else f.rsplit(".", 1)[0]
      schema_name = parts[-2] if len(parts) >= 2 else ""
      db_name = parts[0] if len(parts) >= 3 else ""

      is_table = bool(
          cfg.get("externalTableName") or cfg.get("externalTableDdlPath")
      )
      # Dedupe per (database, schema, name) so that same-named objects from
      # different databases or schemas reach the collision check in
      # run_loader().
      key = (db_name.upper(), schema_name.upper(), table_name.upper())
      if is_table:
        if key not in seen_tables:
          seen_tables.add(key)
          tables.append({
              "table": table_name,
              "schema": schema_name,
              "database": db_name,
          })
      else:
        if key not in seen_views:
          seen_views.add(key)
          views.append({
              "source": {
                  "database": db_name,
                  "schema": schema_name,
                  "view": table_name,
              },
              "target": {"view": table_name},
          })

  return tables, views, seen_tables


def _normalize_relation_part(text: str) -> str:
  """Normalizes a name the way BQMS escapes relations/ path segments.

  BQMS writes view DDLs to relations/db_<database>/schema_<schema>/<name>.sql,
  lowercasing each name and collapsing unsupported characters to "_" ("null"
  or "file" for a missing name).

  Args:
    text: Raw database, schema, or object name.

  Returns:
    The normalized name, or "" for a missing name.
  """
  name = re.sub(r"[^a-z0-9._+\-,@]", "_", (text or "").lower())
  name = re.sub(r"_+", "_", name).strip("_")
  return "" if name in ("null", "file") else name


def _scan_relation_views(
    dir_to_scan: str,
    known_views: list[dict[str, Any]],
) -> list[dict[str, Any]]:
  """Discovers view definitions from metadata relations SQL files.

  The database and schema of each view are derived from the
  relations/db_<database>/schema_<schema>/ subdirectories when present. A
  relation view is skipped only if it matches an already discovered view with
  the same name and compatible database and schema, so same-named views from
  different schemas reach the collision check in run_loader().

  Args:
    dir_to_scan: Local path to the metadata directory.
    known_views: Views already discovered from config YAML files.

  Returns:
    A list of newly discovered view manifest dictionaries.
  """
  relations_dir = os.path.join(dir_to_scan, "metadata", "relations")
  if not os.path.isdir(relations_dir) and os.path.isdir(
      os.path.join(dir_to_scan, "relations")
  ):
    relations_dir = os.path.join(dir_to_scan, "relations")

  views: list[dict[str, Any]] = []
  if not os.path.isdir(relations_dir):
    return views

  seen_keys = [
      tuple(
          _normalize_relation_part(v.get("source", {}).get(part, ""))
          for part in ("database", "schema", "view")
      )
      for v in known_views
  ]

  for root, _, files in os.walk(relations_dir):
    rel_parts = os.path.relpath(root, relations_dir).split(os.sep)
    db_name = next((p[3:] for p in rel_parts if p.startswith("db_")), "")
    schema_name = next(
        (p[7:] for p in rel_parts if p.startswith("schema_")), ""
    )
    db_name = "" if db_name in ("null", "file") else db_name
    schema_name = "" if schema_name in ("null", "file") else schema_name
    for f in sorted(files):
      if not f.endswith(".sql"):
        continue
      v_name = f.rsplit(".", 1)[0]
      fpath = os.path.join(root, f)
      try:
        with open(fpath, "r", encoding="utf-8-sig") as sf:
          txt = sf.read()
        if (
            "CREATE VIEW" in txt.upper()
            or "CREATE OR REPLACE VIEW" in txt.upper()
        ):
          key = tuple(
              _normalize_relation_part(p)
              for p in (db_name, schema_name, v_name)
          )
          if any(
              key[2] == k[2]
              and all(not a or not b or a == b for a, b in zip(key, k[:2]))
              for k in seen_keys
          ):
            continue
          seen_keys.append(key)
          views.append({
              "source": {
                  "database": db_name,
                  "schema": schema_name,
                  "view": v_name,
              },
              "target": {"view": v_name},
          })
      except OSError as e:
        print(f"Warning: Failed to read relation SQL {fpath}: {e}")

  return views


def _fallback_parse_tables_from_ddl(
    dir_to_scan: str,
    seen_tables: set[tuple[str, str, str]],
) -> list[dict[str, str]]:
  """Extracts table definitions from DDL files if config discovery is empty.

  Args:
    dir_to_scan: Local path to the metadata directory.
    seen_tables: Set of already discovered (database, schema, table) tuples in
      uppercase.

  Returns:
    A list of discovered table dictionaries with 'table' and 'schema' keys.
  """
  tables: list[dict[str, str]] = []
  for schema_fname in ("schema.sql", "tables.sql", "schema.ddl"):
    schema_file = os.path.join(dir_to_scan, schema_fname)
    if not os.path.isfile(schema_file):
      schema_file = os.path.join(dir_to_scan, "metadata", schema_fname)
    if os.path.isfile(schema_file):
      try:
        with open(schema_file, "r", encoding="utf-8-sig") as sf:
          schema_txt = sf.read()
        table_matches = _CREATE_TABLE_REGEX.findall(schema_txt)
        for tbl in table_matches:
          key = ("", "", tbl.upper())
          if key not in seen_tables:
            seen_tables.add(key)
            tables.append({"table": tbl, "schema": ""})
      except OSError as e:
        print(f"Warning: Failed to read schema file {schema_file}: {e}")

  return tables


def parse_manifest_from_translation_output(
    path_or_uri: str,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
  """Extracts physical tables and views directly from translation_output/metadata.

  Scans config YAML files and relation SQL files in a local directory or Cloud
  Storage URI to discover base table definitions and view mappings without
  requiring an explicit table.yaml manifest.

  Args:
    path_or_uri: Local directory path or Cloud Storage URI to
      translation_output/metadata.

  Returns:
    A tuple of (target_tables, target_views) where target_tables is a list of
    dictionaries with 'table' and 'schema' keys, and target_views is a list of
    view manifest dictionaries.

  Raises:
    subprocess.CalledProcessError: If copying metadata from Cloud Storage fails.
  """
  dir_to_scan, temp_dir = _stage_translation_metadata_dir(path_or_uri)
  try:
    tables, views, seen_tables = _parse_config_yamls(dir_to_scan)
    views.extend(_scan_relation_views(dir_to_scan, views))
    if not tables:
      tables.extend(_fallback_parse_tables_from_ddl(dir_to_scan, seen_tables))
    return tables, views
  finally:
    if temp_dir:
      shutil.rmtree(temp_dir, ignore_errors=True)


def resolve_parquet_uri(
    parquet_base_uri: str,
    table_name: str,
    schema_name: str | None = None,
) -> str:
  """Resolves the Cloud Storage URI or local path for a table's Parquet files.

  Checks both schema-prefixed (for example, {base}/{schema}/{table}/*.parquet)
  and flat (for example, {base}/{table}/*.parquet) directories, returning the
  schema path if present or the flat path otherwise.

  Args:
    parquet_base_uri: Base Cloud Storage URI or local directory containing
      Parquet chunks.
    table_name: Name of the table.
    schema_name: Optional source schema name.

  Returns:
    A wildcard URI or path to the table's Parquet files.
  """
  clean_base = parquet_base_uri.rstrip("/")
  if not schema_name:
    return f"{clean_base}/{table_name}/*.parquet"

  schema_subpath = f"{schema_name}/{table_name}"
  if clean_base.startswith("gs://"):
    probe_cmd = [
        "gcloud",
        "storage",
        "ls",
        f"{clean_base}/{schema_subpath}/**",
    ]
    check = subprocess.run(
        probe_cmd, capture_output=True, text=True, check=False
    )
    if check.returncode == 0 and check.stdout.strip():
      return f"{clean_base}/{schema_subpath}/*.parquet"
  else:
    local_schema_dir = os.path.join(clean_base, schema_name, table_name)
    if os.path.isdir(local_schema_dir):
      return f"{clean_base}/{schema_subpath}/*.parquet"

  return f"{clean_base}/{table_name}/*.parquet"


# CUSTOMIZE: Schema Overrides & Partitioning — Edit load_parquet_table() to add
# custom bq load flags (such as --time_partitioning_field, --clustering_fields,
# or explicit schema JSON files). By default:
#   - --decimal_target_types enables NUMERIC, BIGNUMERIC, and STRING target
#     types; BigQuery selects the smallest compatible type (NUMERIC ->
#     BIGNUMERIC -> STRING) based on each Parquet DECIMAL(p, s) column's
#     precision and scale (p - s <= 29, s <= 9 -> NUMERIC; p - s <= 38,
#     s <= 38 -> BIGNUMERIC; larger DECIMAL256 scales/precisions -> STRING).
#   - --replace=true overwrites/auto-creates the table from the Parquet schema
#     (Zero-DDL mode). If you pre-created tables from translated BQMS DDLs to
#     preserve target types like JSON, INTERVAL, or RANGE, either TRUNCATE
#     TABLE before loading with "--replace=false" (so reruns stay idempotent
#     and do not duplicate rows) or pass "--replace=true" with an explicit
#     "--schema".
def load_parquet_table(
    project_id: str,
    dataset_id: str,
    table_name: str,
    parquet_uri: str,
    location: str,
) -> None:
  """Loads Parquet files into a target BigQuery table.

  Args:
    project_id: Target Google Cloud project ID.
    dataset_id: Target BigQuery dataset ID.
    table_name: Destination table name.
    parquet_uri: Cloud Storage wildcard URI matching source Parquet files.
    location: BigQuery load job processing location.

  Raises:
    subprocess.CalledProcessError: If the bq load operation fails.
  """
  target_ref = f"{dataset_id}.{table_name}"
  # CUSTOMIZE: Add custom bq load flags (for example,
  # "--time_partitioning_field=...", "--clustering_fields=...") to the cmd list
  # below.
  cmd = [
      "bq",
      "load",
      f"--project_id={project_id}",
      f"--location={location}",
      "--source_format=PARQUET",
      "--replace=true",
      "--decimal_target_types=NUMERIC",
      "--decimal_target_types=BIGNUMERIC",
      "--decimal_target_types=STRING",
      target_ref,
      parquet_uri,
  ]
  print(f"---> Loading {target_ref} from {parquet_uri}...")
  subprocess.run(cmd, check=True)


# CUSTOMIZE: Post-Load Auditing — Edit audit_row_counts() to extend post-load
# verification with custom data integrity checks or column-level checksums.
def audit_row_counts(
    project_id: str, dataset_id: str, tables: list[str], location: str
) -> None:
  """Queries and displays row counts for all loaded tables in BigQuery.

  Args:
    project_id: Target Google Cloud project ID.
    dataset_id: Target BigQuery dataset ID.
    tables: List of table names to audit.
    location: BigQuery job processing location.

  Raises:
    ValueError: If project_id, dataset_id, or any table name is invalid.
    subprocess.CalledProcessError: If row count query execution fails.
  """
  if not tables:
    return
  if not _PROJECT_ID_PATTERN.fullmatch(
      project_id
  ) or not _DATASET_PATTERN.fullmatch(dataset_id):
    raise ValueError(
        f"Invalid project or dataset identifier: {project_id}:{dataset_id}"
    )

  union_queries = []
  for tbl in tables:
    if not _IDENTIFIER_PATTERN.fullmatch(tbl):
      raise ValueError(f"Invalid table identifier: {tbl}")
    union_queries.append(
        f"SELECT '{tbl}' AS table_name, count(*) AS row_count FROM"
        f" `{project_id}`.`{dataset_id}`.`{tbl}`"
    )
  print("\nAuditing BigQuery table row counts...")
  # BigQuery limits a query to 1,000 referenced tables, so audit in chunks and
  # print every row of each chunk (`bq query` prints 100 rows by default).
  for start in range(0, len(union_queries), _AUDIT_CHUNK_SIZE):
    chunk = union_queries[start : start + _AUDIT_CHUNK_SIZE]
    audit_sql = " UNION ALL\n".join(chunk) + " ORDER BY table_name;"
    execute_sql(project_id, location, audit_sql, max_rows=len(chunk))


# DEFAULT SCAFFOLDING: Quote- and comment-aware SQL scanning helpers.
def _scan_sql_segments(sql_text: str) -> list[tuple[str, str]]:
  """Splits SQL text into code, identifier, string, and comment segments.

  Recognizes GoogleSQL single-, double-, and triple-quoted string literals
  (with backslash escapes), backtick-quoted identifiers, `--` and `#` line
  comments, and `/* ... */` block comments.

  Args:
    sql_text: SQL text to scan.

  Returns:
    A list of (kind, text) tuples where kind is "code", "ident", "string", or
    "comment". Concatenating the texts reproduces sql_text.
  """
  segments: list[tuple[str, str]] = []
  n = len(sql_text)
  i = code_start = 0
  while i < n:
    ch = sql_text[i]
    if ch in ("'", '"'):
      kind = "string"
      quote = ch * 3 if sql_text.startswith(ch * 3, i) else ch
      end = i + len(quote)
      while end < n and not sql_text.startswith(quote, end):
        end += 2 if sql_text[end] == "\\" else 1
      end = min(end + len(quote), n)
    elif ch == "`":
      kind = "ident"
      end = i + 1
      while end < n and sql_text[end] != "`":
        end += 2 if sql_text[end] == "\\" else 1
      end = min(end + 1, n)
    elif ch == "#" or sql_text.startswith("--", i):
      kind = "comment"
      end = sql_text.find("\n", i)
      end = n if end == -1 else end
    elif sql_text.startswith("/*", i):
      kind = "comment"
      end = sql_text.find("*/", i + 2)
      end = n if end == -1 else end + 2
    else:
      i += 1
      continue
    if code_start < i:
      segments.append(("code", sql_text[code_start:i]))
    segments.append((kind, sql_text[i:end]))
    i = code_start = end
  if code_start < n:
    segments.append(("code", sql_text[code_start:]))
  return segments


def _split_sql_statements(sql_text: str) -> list[str]:
  """Splits a SQL script on semicolons outside literals and comments.

  Args:
    sql_text: SQL script text.

  Returns:
    A list of statements without trailing semicolons, skipping empty and
    comment-only chunks.
  """
  statements: list[str] = []
  current: list[str] = []
  has_code = False
  for kind, text in _scan_sql_segments(sql_text):
    if kind != "code":
      current.append(text)
      has_code = has_code or kind != "comment"
      continue
    for idx, piece in enumerate(text.split(";")):
      if idx > 0:
        if has_code:
          statements.append("".join(current).strip())
        current, has_code = [], False
      current.append(piece)
      has_code = has_code or bool(piece.strip())
  if has_code:
    statements.append("".join(current).strip())
  return statements


# CUSTOMIZE: Custom View Rewriting & Deployment — Edit deploy_views() or
# _rewrite_view_sql() to adjust view SQL regular expressions, cross-project
# dataset mappings, or multi-pass retry policies.
def deploy_views(project_id: str, location: str, views_sql: str) -> None:
  """Applies view DDLs with multi-pass dependency resolution if needed.

  Attempts to deploy all views in a single batch first. If dependency order
  errors occur (for example, view A depends on view B), falls back to iterative
  multi-pass execution until all views succeed or unresolved cycles remain.

  Args:
    project_id: Target Google Cloud project ID.
    location: BigQuery job processing location.
    views_sql: Concatenated SQL statements defining views.

  Raises:
    subprocess.CalledProcessError: If a fatal SQL execution error occurs.
  """
  if not views_sql.strip():
    return
  try:
    execute_sql(project_id, location, views_sql)
    print("All views deployed successfully in single batch.")
    return
  except subprocess.CalledProcessError:
    raw_statements = _split_sql_statements(views_sql)
    if not raw_statements:
      # Nothing to retry statement by statement; surface the batch error.
      raise
    print(
        "Encountered dependency order constraint during batch view deployment;"
        " compiling with multi-pass dependency resolution..."
    )

  pending = list(raw_statements)
  pass_num = 0
  max_passes = len(pending) + 2

  while pending and pass_num < max_passes:
    pass_num += 1
    failed = []
    progress = False
    for stmt in pending:
      try:
        execute_sql(project_id, location, stmt + "\n;")
        progress = True
      except subprocess.CalledProcessError:
        failed.append(stmt)

    if not progress and failed:
      print(
          f"Warning: Unable to resolve dependencies for {len(failed)} views in"
          f" pass {pass_num}."
      )
      execute_sql(project_id, location, failed[0] + "\n;")
      break
    pending = failed

  if not pending:
    print(
        f"All {len(raw_statements)} views successfully deployed across"
        f" {pass_num} passes."
    )


# DEFAULT SCAFFOLDING: Source namespace prefix extraction helper.
def _build_source_prefixes(
    manifest_entries: collections.abc.Iterable[dict[str, Any]],
) -> set[str]:
  """Extracts 1-part and 2-part source namespace prefixes from manifest entries.

  Args:
    manifest_entries: Iterable of table or view manifest mapping dictionaries.

  Returns:
    A set of source prefixes to match and replace in SQL definitions.
  """
  prefixes: set[str] = set()
  for entry in manifest_entries:
    src = entry.get("source", {})
    db = src.get("database")
    schema = src.get("schema")
    if db and schema:
      prefixes.update({
          f"{db}.{schema}.",
          f"`{db}`.`{schema}`.",
          f"`{db}`.{schema}.",
          f"{db}.`{schema}`.",
      })
    if schema:
      prefixes.update({f"{schema}.", f"`{schema}`."})
  return prefixes


# CUSTOMIZE: Custom View Rewriting & Deployment — Edit _rewrite_view_sql() to
# adjust view SQL regular expressions or cross-project dataset mapping rules.
def _rewrite_view_sql(
    sql_content: str,
    prefixes: collections.abc.Sequence[str],
    target_prefix: str,
) -> str:
  """Rewrites source table references in view SQL to point to target dataset.

  Source prefixes are replaced only outside string literals and comments, and
  plain `CREATE VIEW` statements become `CREATE OR REPLACE VIEW` so that reruns
  and multi-pass retries don't fail on views that already exist.

  Args:
    sql_content: Raw SQL string definition.
    prefixes: Ordered sequence of source prefix patterns to replace.
    target_prefix: Destination BigQuery dataset prefix (`project`.dataset).

  Returns:
    The rewritten SQL text.
  """
  # Drop trailing comments and statement semicolons (for example,
  # "SELECT 1; -- active") so callers can append their own delimiter.
  segments = _scan_sql_segments(sql_content)
  while segments and segments[-1][0] in ("code", "comment"):
    kind, text = segments[-1]
    trimmed = "" if kind == "comment" else text.rstrip(" \t\r\n\f\v;")
    if trimmed:
      segments[-1] = (kind, trimmed)
      break
    segments.pop()
  rewritten = "".join(text for _, text in segments).strip()
  # Mask string literals and comments so prefixes inside them stay unchanged.
  masked_literals: list[str] = []
  masked_parts: list[str] = []
  for kind, text in _scan_sql_segments(rewritten):
    if kind in ("string", "comment"):
      masked_parts.append(f"\ue000{len(masked_literals)}\ue001")
      masked_literals.append(text)
    else:
      masked_parts.append(text)
  rewritten = "".join(masked_parts)
  for pfx in prefixes:
    pattern = re.compile(
        r"(?<![a-zA-Z0-9_`.])" + re.escape(str(pfx)), re.IGNORECASE
    )
    rewritten = pattern.sub(f"{target_prefix}.", rewritten)
  rewritten = _CREATE_VIEW_PATTERN.sub("CREATE OR REPLACE VIEW", rewritten)
  rewritten = _MASK_TOKEN_PATTERN.sub(
      lambda m: masked_literals[int(m.group(1))], rewritten
  )
  if _WRAP_JSON_QUERY_WITH_PARSE_JSON:
    rewritten = _JSON_WRAP_PATTERN.sub(
        r"\1(SAFE.PARSE_JSON(json_query(\2, \3)))", rewritten
    )
  return rewritten


# DEFAULT SCAFFOLDING: View manifest matching and main loader orchestration.
def deploy_views_from_manifest(
    project_id: str,
    dataset_id: str,
    location: str,
    views_manifest: list[dict[str, Any]],
    translated_dir: str,
    tables_manifest: list[dict[str, Any]] | None = None,
) -> None:
  """Deploys views defined in manifest by matching and rewriting SQL files.

  Matches view definitions against translated SQL output files, rewrites source
  database/schema table and view prefixes to point to the target BigQuery
  dataset, and deploys the views in dependency order.

  Args:
    project_id: Target Google Cloud project ID.
    dataset_id: Target BigQuery dataset ID.
    location: BigQuery job processing location.
    views_manifest: List of view mappings parsed from manifest or configs.
    translated_dir: Directory or gs:// URI containing translated SQL files.
    tables_manifest: Optional list of table mappings for prefix extraction.

  Raises:
    subprocess.CalledProcessError: If view deployment fails.
  """
  if not views_manifest:
    return

  sql_by_name = list_and_read_sql_files(translated_dir)
  if not sql_by_name:
    print(f"No SQL files found in translated directory: {translated_dir}")
    return

  tgt_prefix = f"`{project_id}`.{dataset_id}"
  all_entries = views_manifest + (tables_manifest or [])
  sorted_prefixes = sorted(
      _build_source_prefixes(all_entries), key=len, reverse=True
  )

  view_statements: list[str] = []
  for v_entry in views_manifest:
    tgt = v_entry.get("target", {})
    src = v_entry.get("source", {})
    v_name = (
        tgt.get("view")
        or tgt.get("table")
        or src.get("view")
        or src.get("table")
        or ""
    )
    if not v_name:
      continue

    v_key = v_name.upper()
    sql_content = sql_by_name.get(v_key) or sql_by_name.get(
        f"DATA_VIEW_{v_key}"
    )
    if not sql_content:
      print(f"Note: View file for {v_name} not found in {translated_dir}.")
      continue

    rewritten = _rewrite_view_sql(sql_content, sorted_prefixes, tgt_prefix)
    if not _split_sql_statements(rewritten):
      print(f"Note: View file for {v_name} contains no SQL statements.")
      continue
    view_statements.append(rewritten)

  if not view_statements:
    print(
        "No matching view SQL files found for manifest views in"
        f" {translated_dir}."
    )
    return

  # Put each delimiter on its own line so a trailing inline `--` comment on a
  # statement's last line can't swallow it.
  deploy_views(project_id, location, "\n;\n".join(view_statements) + "\n;")


def _find_consolidated_views_sql(translated_dir: str) -> str | None:
  """Checks for a consolidated views.sql file in translated_dir."""
  for candidate in ("views.sql", "metadata/views.sql"):
    if translated_dir.startswith("gs://"):
      uri = f"{translated_dir.rstrip('/')}/{candidate}"
      probe = subprocess.run(
          ["gcloud", "storage", "ls", uri],
          capture_output=True,
          text=True,
          check=False,
      )
      if probe.returncode == 0 and probe.stdout.strip():
        return read_file_or_gcs(uri)
    else:
      fpath = os.path.join(translated_dir, candidate)
      if os.path.isfile(fpath):
        return read_file_or_gcs(fpath)
  return None


def _check_destination_collisions(
    objects: collections.abc.Iterable[dict[str, str]],
    dataset_id: str,
) -> None:
  """Fails fast if source objects share a destination name in the dataset.

  Tables and views share one namespace in a BigQuery dataset, and all
  discovered objects load into the single target dataset by unqualified name,
  so same-named objects from different source databases or schemas would
  overwrite or shadow each other.

  Args:
    objects: Discovered objects with "kind" ("table" or "view"), "name",
      "schema", and "database" keys.
    dataset_id: Target BigQuery dataset ID (used in the error message).

  Raises:
    ValueError: If two or more objects map to the same destination name.
  """
  by_name: dict[str, list[str]] = {}
  for obj in objects:
    name = obj.get("name", "")
    if not name:
      continue
    qualified = ".".join(
        p for p in (obj.get("database", ""), obj.get("schema", ""), name) if p
    )
    by_name.setdefault(name.upper(), []).append(
        f"{qualified} ({obj.get('kind', '')})"
    )
  collisions = {k: v for k, v in by_name.items() if len(v) > 1}
  if collisions:
    details = "; ".join(
        f"{name}: {', '.join(sources)}"
        for name, sources in sorted(collisions.items())
    )
    raise ValueError(
        "Multiple source tables or views map to the same name in dataset"
        f" {dataset_id}: {details}. Load each source schema into its own"
        " --dataset (by pointing --translation-metadata-dir at metadata that"
        " contains only that schema), or customize the template to use"
        " schema-prefixed destination names."
    )


def run_loader(
    project_id: str,
    dataset_id: str,
    location: str,
    parquet_base_uri: str,
    translated_dir: str,
    concurrency: int = 4,
) -> None:
  """Orchestrates end-to-end BigQuery loading pipeline.

  Auto-discovers tables and views from translation output metadata (failing
  fast on empty discovery or destination name collisions), provisions the
  target BigQuery dataset if necessary, concurrently loads staged Parquet
  files into native tables by using `bq load`, audits table row counts, and
  deploys translated views.

  Args:
    project_id: Target Google Cloud project ID.
    dataset_id: Target BigQuery dataset ID.
    location: BigQuery job processing location.
    parquet_base_uri: Base Cloud Storage URI containing staged Parquet files.
    translated_dir: Path or Cloud Storage URI to translation_output/metadata
      directory.
    concurrency: Number of concurrent workers for parallel bq load operations.

  Raises:
    ValueError: If project_id, dataset_id, or a discovered table name is
      invalid, no tables, views, or consolidated views.sql are discovered, or
      tables or views from different source databases or schemas map to the
      same destination name in the target dataset.
    FileNotFoundError: If a local translated_dir does not exist.
    subprocess.CalledProcessError: If copying metadata from Cloud Storage fails.
  """
  if not _PROJECT_ID_PATTERN.fullmatch(
      project_id
  ) or not _DATASET_PATTERN.fullmatch(dataset_id):
    raise ValueError(
        f"Invalid project or dataset identifier: {project_id}:{dataset_id}"
    )
  if not translated_dir.startswith("gs://") and not os.path.isdir(
      translated_dir
  ):
    raise FileNotFoundError(
        f"Translation metadata directory not found: {translated_dir}"
    )

  # 1. Discover tables and views from translation metadata
  target_tables, target_views = parse_manifest_from_translation_output(
      translated_dir
  )
  consolidated_views_sql = _find_consolidated_views_sql(translated_dir)
  # A comment-only views.sql counts as absent so that relations/ views still
  # deploy and empty discovery still fails fast.
  has_views_sql = bool(
      consolidated_views_sql and _split_sql_statements(consolidated_views_sql)
  )
  if not target_tables and not target_views:
    if not has_views_sql:
      raise ValueError(
          "No tables, views, or views.sql discovered in translation metadata"
          f" at {translated_dir}. Check that --translation-metadata-dir points"
          " to the BQMS translation_output/metadata directory."
      )
    print(
        "Warning: No tables or views discovered in translation metadata;"
        " deploying views.sql without source-prefix rewriting."
    )
  _check_destination_collisions(
      [
          {
              "kind": "table",
              "name": t.get("table", ""),
              "schema": t.get("schema", ""),
              "database": t.get("database", ""),
          }
          for t in target_tables
      ]
      + [
          {
              "kind": "view",
              "name": v.get("source", {}).get("view", ""),
              "schema": v.get("source", {}).get("schema", ""),
              "database": v.get("source", {}).get("database", ""),
          }
          for v in target_views
      ],
      dataset_id,
  )
  # Validate table names before any bq command mutates BigQuery.
  for t in target_tables:
    tbl = t.get("table", "")
    if tbl and not _IDENTIFIER_PATTERN.fullmatch(tbl):
      raise ValueError(f"Invalid table identifier: {tbl}")

  all_tables = [
      {
          "source": {
              "database": t.get("database", ""),
              "schema": t.get("schema", ""),
              "table": t.get("table", ""),
          },
          "target": {"table": t.get("table", "")},
      }
      for t in target_tables
  ]

  # 2. Ensure dataset exists
  ensure_dataset(project_id, dataset_id, location)

  # 3. Concurrently load Parquet files (auto-creates native tables)
  loaded_tables: list[str] = []
  if concurrency > 1 and len(target_tables) > 1:
    print(f"Loading tables concurrently with {concurrency} workers...")
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=concurrency
    ) as executor:
      future_to_table = {}
      for tbl_entry in target_tables:
        tbl = tbl_entry.get("table", "")
        schema = tbl_entry.get("schema", "")
        if not tbl:
          continue
        uri = resolve_parquet_uri(parquet_base_uri, tbl, schema)
        fut = executor.submit(
            load_parquet_table, project_id, dataset_id, tbl, uri, location
        )
        future_to_table[fut] = tbl

      for future in concurrent.futures.as_completed(future_to_table):
        tbl = future_to_table[future]
        try:
          future.result()
          loaded_tables.append(tbl)
        except subprocess.CalledProcessError as e:
          print(f"Failed to load table {tbl}: {e}")
          raise
  else:
    for tbl_entry in target_tables:
      tbl = tbl_entry.get("table", "")
      schema = tbl_entry.get("schema", "")
      if not tbl:
        continue
      uri = resolve_parquet_uri(parquet_base_uri, tbl, schema)
      try:
        load_parquet_table(project_id, dataset_id, tbl, uri, location)
        loaded_tables.append(tbl)
      except subprocess.CalledProcessError as e:
        print(f"Error loading table {tbl} from {uri}: {e}")
        raise

  # 4. Audit loaded table row counts
  if loaded_tables:
    audit_row_counts(project_id, dataset_id, sorted(loaded_tables), location)

  # 5. Deploy translated views (consolidated views.sql or decomposed relations)
  if has_views_sql:
    print("\nDeploying translated views from consolidated views.sql...")
    sorted_prefixes = sorted(
        _build_source_prefixes(target_views + all_tables),
        key=len,
        reverse=True,
    )
    rewritten_views_sql = (
        _rewrite_view_sql(
            consolidated_views_sql,
            sorted_prefixes,
            f"`{project_id}`.{dataset_id}",
        )
        + "\n;"
    )
    deploy_views(project_id, location, rewritten_views_sql)
  elif target_views:
    deploy_views_from_manifest(
        project_id=project_id,
        dataset_id=dataset_id,
        location=location,
        views_manifest=target_views,
        tables_manifest=all_tables,
        translated_dir=translated_dir,
    )


# ==============================================================================
# 2. CLI Main Router (DEFAULT SCAFFOLDING)
# ==============================================================================
# DEFAULT SCAFFOLDING: CLI argument parser and entrypoint.
def _parse_args(
    argv: collections.abc.Sequence[str] | None = None,
) -> argparse.Namespace:
  """Parses command-line arguments for the BigQuery loader CLI."""
  parser = argparse.ArgumentParser(
      description=(
          "Automates BigQuery data ingestion and view deployment directly from"
          " translation output."
      )
  )
  parser.add_argument(
      "--project", required=True, help="Target Google Cloud project ID"
  )
  parser.add_argument(
      "--dataset", required=True, help="Target BigQuery dataset ID"
  )
  parser.add_argument(
      "--location", default="us-central1", help="Target BigQuery location"
  )
  parser.add_argument(
      "--parquet-base-uri",
      "--parquet-uri",
      dest="parquet_base_uri",
      required=True,
      help="Cloud Storage base URI containing staged Parquet files",
  )
  parser.add_argument(
      "--translation-metadata-dir",
      "--translation-output",
      "--translated-dir",
      "--metadata-dir",
      dest="translated_dir",
      required=True,
      help=(
          "Local folder or Cloud Storage URI containing translation_output"
          " metadata (auto-discovers tables and views)"
      ),
  )
  parser.add_argument(
      "--concurrency",
      "--parallel-workers",
      type=int,
      default=4,
      help=(
          "Number of parallel workers for concurrent table loading (default: 4)"
      ),
  )
  return parser.parse_args(argv)


def main(argv: collections.abc.Sequence[str] | None = None) -> None:
  """Main entrypoint for the BigQuery loader CLI."""
  args = _parse_args(argv)
  run_loader(
      project_id=args.project,
      dataset_id=args.dataset,
      location=args.location,
      parquet_base_uri=args.parquet_base_uri,
      translated_dir=args.translated_dir,
      concurrency=args.concurrency,
  )


if __name__ == "__main__":
  main()
