---
name: bigquery-migration-data-exporter
metadata:
  version: "1.0.0"
  category: BigDataAndAnalytics
  publisher: google
description: >-
  Generates type-safe, schema-aligned database data export SQL files (.sql) for
  Snowflake, Databricks, Teradata, Oracle, and PostgreSQL directly from
  BigQuery Migration Service (BQMS) translation_output/metadata
  configs, exporting into target file formats (such as Parquet). Use when
  generating source database export SQL scripts for BigQuery ingestion without
  connecting to the source database. Don't use for executing SQL against source
  databases or streaming/staging exported files, extracting source database
  catalog metadata, translating SQL queries or DDL schemas (use
  bigquery-migration-sql-translator), loading staged Parquet files into
  BigQuery, or running post-migration data validation.
---

# BigQuery Migration Data Exporter

This skill coordinates the generation of type-aware data export SQL scripts
(`.sql` files) for source data warehouses (such as Snowflake, Databricks,
Teradata, Oracle, and PostgreSQL) into target file formats (such as
**BigQuery-aligned Parquet files**), guided by dialect and format specifications
in the **`references/`** directory.

All templates in this skill are **pure SQL generators with zero JDBC or database
connector dependencies**.

> [!TIP]
> Point directly to the BigQuery Migration Service (BQMS)
> **`translation_output/metadata`** directory (local path or Cloud Storage URI).
> It automatically discovers all physical tables and target BigQuery logical
> types from `metadata/config/*.yaml`.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Before you begin

1.  **Google Cloud CLI & Project Setup**: When reading translation outputs or
    metadata archives from `gs://` Cloud Storage URIs, ensure the
    [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) is
    installed, verify that your Google Cloud project has an active Cloud Billing
    account attached, and configure the target project:

    ```bash
    gcloud config set project {project_id}
    ```

2.  **Enable the API**: When reading metadata from Cloud Storage (`gs://`), ask
    the user before enabling APIs, then enable the Cloud Storage API
    (`storage.googleapis.com`):

    ```bash
    gcloud services enable storage.googleapis.com
    ```

3.  **Authentication & Required Identity and Access Management (IAM) Roles**:
    Authenticate with `gcloud auth login` and `gcloud auth application-default
    login` (or set `GOOGLE_APPLICATION_CREDENTIALS` for service account
    authentication). Verify that your identity or service account has
    `roles/storage.objectViewer` (Storage Object Viewer) on any Cloud Storage
    bucket holding input metadata. Creating a staging bucket requires
    `roles/storage.admin` (Storage Admin) on the Google Cloud project, and
    deleting staged files requires `roles/storage.objectAdmin` (Storage Object
    Admin) on the staging bucket.

4.  **Python Environment**: The generator templates require Python 3.9 or
    later. Ask the user for confirmation before installing Python packages,
    then install PyYAML in a virtual environment (generator templates have
    zero JDBC or database connector dependencies):

    ```bash
    pip install pyyaml==6.0.2
    ```

5.  **Region, Cost & Cleanup**: Ask the user for confirmation before creating
    a new Cloud Storage bucket for staging exported Parquet files (`gcloud
    storage buckets create gs://{bucket} --location={region}`), and default to
    `us-central1` unless your target BigQuery dataset uses another region
    (co-locate buckets with your dataset; see
    [Google Cloud locations](https://cloud.google.com/about/locations)). Review
    [Google Cloud Pricing](https://cloud.google.com/pricing) before staging
    large exports. After BigQuery ingestion, temporary staged Parquet prefixes
    can be removed with `gcloud storage rm -r gs://{bucket}/{export_prefix}`.
    This deletion is permanent: run it only after the user explicitly confirms
    the exact URI, and never with an empty `{export_prefix}` (which would delete
    every object in the bucket).

6.  **Snowflake Storage Integration**: To unload Snowflake tables directly to a
    private Cloud Storage bucket (`--stage-path 'gcs://...'`), Snowflake
    requires a [storage integration][snowflake_gcs_integration] that grants its
    service account access to the bucket. Ask the user for the integration name
    and pass it with the `--storage-integration` flag, which adds a
    `STORAGE_INTEGRATION` clause to each generated `COPY INTO` statement.
    Unloads to a Snowflake stage (for example, `@~/bqms_export/` or a named
    external stage) don't need this flag.

--------------------------------------------------------------------------------

## 1. Direct Consumption of Translation Output Metadata

`bigquery-migration-data-exporter` consumes the native BigQuery Migration
Service (BQMS) metadata translation output:
`translation_output/metadata/config/<database>/<schema>/<table_name>.yaml`

Each configuration file specifies:

1.  `sourceName`: Fully qualified source table name.
2.  `columns`: Source data types, precision, scale, and BigQuery target types.
3.  Table versus view: A config with neither `externalTableName` nor
    `externalTableDdlPath` describes a view, which is recreated as a SQL view
    and isn't exported. The Databricks generator also honors an explicit
    `TableType` field when present.

--------------------------------------------------------------------------------

## 2. Format-Guided Type-Safe Export Fundamentals

A plain unguided `COPY INTO @stage FROM table` or `SELECT *` often fails during
BigQuery ingestion (`bq load`) due to serializer discrepancies (for example,
`VARIANT` JSON encoding, `CHAR(n)` fixed-width space padding, unbounded
Teradata/Oracle/PostgreSQL `NUMBER`/`NUMERIC` scale truncation, PostgreSQL
`MONEY` locale currency formatting, Oracle `DATE` time-of-day components, or
timestamp nanosecond ticks).

To ensure zero type drift and clean BigQuery ingestion, apply type-aware
projections guided by the target format and dialect specifications in the
**`references/`** directory. While Parquet is the standard and recommended
format for BigQuery batch ingestion due to columnar compression and strict
typing, the export structure adapts based on target format requirements.

For Parquet data exports, the core rules are summarized below; the mapping
references listed after them hold the full per-dialect type matrices:

1.  **Session Parameters (Snowflake)**:

    ```sql
    ALTER SESSION SET TIME_OUTPUT_FORMAT = 'HH24:MI:SS.FF6';
    ALTER SESSION SET TIMESTAMP_NTZ_OUTPUT_FORMAT = 'YYYY-MM-DD HH24:MI:SS.FF6';
    ALTER SESSION SET TIMESTAMP_TZ_OUTPUT_FORMAT = 'YYYY-MM-DD HH24:MI:SS.FF6 TZHTZM';
    ```
2.  **Semi-Structured / JSON (`VARIANT`, `OBJECT`, `STRUCT`, `MAP`, `ARRAY`,
    `JSON`, `JSONB`, `XMLTYPE`, `XML`, `UUID`, `INET`)**:

    *   Snowflake: `TO_VARCHAR(col) AS col`.
    *   Databricks / Spark SQL: `TO_JSON(col) AS col` for `MAP` (and for
        `STRUCT`/`ARRAY` when targeting `JSON` or `STRING`; native passthrough
        `col` when targeting `RECORD`/`ARRAY`); `CAST(col AS STRING) AS col` for
        `VARIANT`/`JSON`/`INTERVAL`.
    *   Teradata: `CAST(col AS CLOB) AS col`.
    *   Oracle: `JSON_SERIALIZE(col RETURNING CLOB) AS col` for 21c+ native
        `JSON`, and `XMLSERIALIZE(CONTENT col AS CLOB) AS col` for `XMLTYPE`.
    *   PostgreSQL: `CAST(col AS TEXT) AS col` for `JSON`, `JSONB`, `XML`,
        `UUID`, `INET`, `CIDR`, `MACADDR`, `INTERVAL`, `BIT`, and `ARRAY`.
3.  **Decimals, Numbers, Integers & Floats**:

    *   `NUMBER(p, s)` / `DECIMAL(p, s)` / `NUMERIC(p, s)` with `s > 0` →
        `CAST(col AS DECIMAL(p, s)) AS col` (or `CAST(col AS NUMBER(p, s)) AS
        col` in Oracle, or `CAST(col AS NUMERIC(p, s)) AS col` in PostgreSQL).
    *   Unbounded or unconstrained `NUMBER` / `NUMBER(*)` / `NUMERIC` /
        `DECIMAL` → `CAST(col AS DECIMAL(38, 9)) AS col` in Snowflake and
        Teradata, `CAST(col AS NUMBER(38, 9)) AS col` in Oracle, or `CAST(col AS
        NUMERIC(38, 9)) AS col` in PostgreSQL (supports `<= 29` integer digits
        and `9` fractional digits by default; override scale in Teradata,
        Oracle, and PostgreSQL by using `--unbounded-number-scale`); PostgreSQL
        `MONEY` → `CAST(col AS NUMERIC(38, 2)) AS col`.
    *   `TINYINT` / `BYTEINT` / `SMALLINT` / `INT` / `INTEGER` / `BIGINT` /
        `SERIAL` → `CAST(col AS BIGINT) AS col`. In Oracle, `SMALLINT` →
        `CAST(col AS NUMBER(19, 0)) AS col` and the ANSI `NUMBER(38)` aliases
        `INT` / `INTEGER` → `CAST(col AS NUMBER(38, 0)) AS col`. Scale-0
        decimals with a `TargetType` of `INT64` project as 64-bit integers;
        the mapping references list which `NUMBER(p, 0)` / `DECIMAL(p, 0)`
        precisions become 64-bit integers by default.
    *   Databricks / Snowflake `FLOAT` / `REAL` → `CAST(col AS DOUBLE) AS col`;
        PostgreSQL `REAL` / `DOUBLE PRECISION` → `CAST(col AS DOUBLE PRECISION)
        AS col`; Oracle `BINARY_FLOAT` / `BINARY_DOUBLE` / `FLOAT(p)` →
        `CAST(col AS BINARY_DOUBLE) AS col` (widens to 64-bit IEEE-754
        `FLOAT64`).
4.  **Temporal (`DATE`, `TIME`, `TIMESTAMP`, `TIMESTAMP_NTZ`, `TIMESTAMP WITH
    TIME ZONE`)**:

    *   Snowflake: `CAST(col AS TIMESTAMP_NTZ(6)) AS col` and
        `CAST(CONVERT_TIMEZONE('UTC', col) AS TIMESTAMP_NTZ(6)) AS col`.
    *   Databricks / Spark SQL: `CAST(col AS TIMESTAMP) AS col` when targeting
        `TIMESTAMP`, or leave `TIMESTAMP_NTZ` uncast when targeting BigQuery
        `DATETIME`. `TIMESTAMP_NTZ` to `TIMESTAMP` casts (and back) use the
        session time zone, so run the scripts in a UTC session (see the
        [Databricks reference][databricks_map]).
    *   Teradata: `CAST(col AS TIMESTAMP(6)) AS col`, `CAST((col AT TIME ZONE
        'GMT') AS TIMESTAMP(6)) AS col`, and `CAST((col AT TIME ZONE 'GMT') AS
        TIME(6)) AS col`.
    *   Oracle: `CAST(col AS TIMESTAMP(6)) AS col` for `DATE` and
        `TIMESTAMP(p)` (or `TRUNC(col) AS col` when `DATE` explicitly targets
        BigQuery `DATE`), `CAST(SYS_EXTRACT_UTC(col) AS TIMESTAMP(6)) AS col`
        for `TIMESTAMP WITH TIME ZONE`, and `CAST(SYS_EXTRACT_UTC(CAST(col AS
        TIMESTAMP WITH TIME ZONE)) AS TIMESTAMP(6)) AS col` for `TIMESTAMP WITH
        LOCAL TIME ZONE` (UTC, whatever the session time zone).
    *   PostgreSQL: `CAST(col AS TIME(6)) AS col` for `TIME` and `TIMETZ`,
        `CAST(col AS TIMESTAMP(6) WITHOUT TIME ZONE) AS col` for `TIMESTAMP
        [WITHOUT TIME ZONE]`, and `CAST(col AS TIMESTAMP(6) WITH TIME ZONE) AS
        col` for `TIMESTAMPTZ` / `TIMESTAMP WITH TIME ZONE`.
5.  **Fixed-Width Character Padding (`CHAR(n)` / `NCHAR(n)` / `BPCHAR` /
    `GRAPHIC(n)`)**: `TRIM(TRAILING FROM col) AS col` (Teradata) or `RTRIM(col)
    AS col` (Oracle and PostgreSQL) to strip fixed-width trailing pad spaces.
6.  **Explicit Target Types**: A BigQuery `TargetType` from the BQMS config
    (for example a schema override to `INT64`, `NUMERIC`, `DATE`, or
    `TIMESTAMP`) wins over the source-type defaults above so the Parquet
    column matches the BigQuery DDL. Cross-type overrides that a template
    doesn't convert keep the default projection: `STRING`, `JSON`, and
    `BYTES` in Oracle and Teradata (text columns stay text, binary columns
    stay bytes, and numeric or datetime columns keep their type); `BOOL` in
    Teradata and Oracle; `TIME` in Oracle and Databricks; `DATE` on Oracle
    columns other than `DATE` / `TIMESTAMP`; and targets other than numeric
    or `STRING` on Databricks `DECIMAL` columns. If `bq load` reports a type
    mismatch, edit the template's `# CUSTOMIZE: Custom Type Projections`
    hook.

> [!IMPORTANT]
> Always consult the **`references/`** directory
> (**[Snowflake Parquet mapping reference][snowflake_map]**,
> **[Databricks and Spark SQL Parquet mapping reference][databricks_map]**,
> **[Teradata Parquet mapping reference][teradata_map]**,
> **[Oracle Parquet mapping reference][oracle_map]**, and
> **[PostgreSQL Parquet mapping reference][postgres_map]**) to
> verify type conversions, formatting options, and dialect-specific export
> syntax.

--------------------------------------------------------------------------------

## 3. Asset Templates & Agent Workflow

This skill provides pure-Python SQL generator asset templates in `assets/` (with
no JDBC or warehouse driver dependencies):

*   [Snowflake export SQL generator template][snowflake_exporter_template]
    (`assets/export_snowflake_tables_template.py`)
*   [Databricks export SQL generator template][databricks_exporter_template]
    (`assets/export_databricks_tables_template.py`)
*   [Teradata export SQL generator template][teradata_exporter_template]
    (`assets/export_teradata_tables_template.py`)
*   [Oracle export SQL generator template][oracle_exporter_template]
    (`assets/export_oracle_tables_template.py`)
*   [PostgreSQL export SQL generator template][postgres_exporter_template]
    (`assets/export_postgres_tables_template.py`)

### Agent Workflow: Copy, Conditionally Customize, and Generate SQL

1.  **Copy the Asset Template**: Copy `assets/<template_name>_template.py` from
    this skill's directory (`<SKILL_DIR>`) into your working directory (copy the
    file; do not paste or re-type the template contents into the response).
    `<SKILL_DIR>` is the directory containing this `SKILL.md`:

    ```bash
    # For Snowflake:
    cp <SKILL_DIR>/assets/export_snowflake_tables_template.py ./export_snowflake_tables.py

    # For Databricks:
    cp <SKILL_DIR>/assets/export_databricks_tables_template.py ./export_databricks_tables.py

    # For Teradata:
    cp <SKILL_DIR>/assets/export_teradata_tables_template.py ./export_teradata_tables.py

    # For Oracle:
    cp <SKILL_DIR>/assets/export_oracle_tables_template.py ./export_oracle_tables.py

    # For PostgreSQL:
    cp <SKILL_DIR>/assets/export_postgres_tables_template.py ./export_postgres_tables.py
    ```

2.  **Conditionally Customize Extension Points**: Run the copy as-is. Modify it
    only if one of the following applies (prefer editing the marked `#
    CUSTOMIZE:` sections; `# DEFAULT SCAFFOLDING` sections can be kept unchanged
    unless deeper orchestration adjustments are needed):

    *   **Custom Type Projections (`# CUSTOMIZE: Custom Type Projections`)**:
        Adjust `format_column_cast()` in `export_snowflake_tables.py`,
        `export_databricks_tables.py`, `export_teradata_tables.py`,
        `export_oracle_tables.py`, or `export_postgres_tables.py` for
        non-standard data types, custom precision bounds, or special
        JSON/geography serialization formats.
    *   **Stage & Storage Configuration (`# CUSTOMIZE: Stage & Storage
        Configuration`)**: Customize `COPY INTO` file format options
        (`MAX_FILE_SIZE`, compression codecs, or encryption flags) in
        `_build_copy_into_query()` or Spark SQL `INSERT OVERWRITE DIRECTORY`
        options in `_build_insert_overwrite_query()`. Pass Snowflake storage
        integration names with the `--storage-integration` flag instead of
        editing the template.
    *   **Table & Row Filtering (`# CUSTOMIZE: Table & Row Filtering` / `#
        CUSTOMIZE: Row Filters`)**: Add custom `WHERE` clauses, partition
        predicates, or custom schema/table inclusion/exclusion filters in
        `_filter_tables_to_export()`, `_build_select_query()`, or
        `load_tables_from_metadata_path()`.

3.  **Generate the Export SQL Files**: Run the copied script with `python3`
    (`python3 ./export_snowflake_tables.py`,
    `python3 ./export_databricks_tables.py`,
    `python3 ./export_teradata_tables.py`, `python3 ./export_oracle_tables.py`,
    or `python3 ./export_postgres_tables.py`) to output a unified `.sql` script
    (`--output-sql`) and/or per-table `*_export.sql` scripts (`--output-dir`).

4.  **Check the Output**: Confirm the script exited with status `0`, report
    any `WARNING:` lines from stderr (such as skipped duplicate tables), and
    check that the number of `-- Unload Table:` markers (or `*_export.sql`
    files) matches the tables you expect to export.

--------------------------------------------------------------------------------

### A. Snowflake Export SQL Generator (`./export_snowflake_tables.py`)

#### 1. Generate Unified Export SQL Script (`--output-sql`)

Unloading directly to Cloud Storage (`gcs://`) requires a Snowflake storage
integration (see [Before you begin](#before-you-begin)):

```bash
python3 ./export_snowflake_tables.py \
    --translation-metadata-dir gs://my-bucket/translation_output/metadata/ \
    --stage-path 'gcs://my-bucket/data_unload/' \
    --storage-integration my_gcs_integration \
    --output-sql export_snowflake_to_parquet.sql
```

#### 2. Generate Per-Table Export SQL Files (`--output-dir`)

```bash
python3 ./export_snowflake_tables.py \
    --translation-metadata-dir ./translated_output/metadata \
    --stage-path '@~/bqms_export/' \
    --output-dir ./export_sql
```

When the tables span more than one Snowflake database (tables whose metadata
omits the database count as `--default-database`), the generator
prefixes each unload subpath, `-- Unload Table:` label, and per-table file name
with the database (for example, `@~/bqms_export/<DB>/<SCHEMA>/<TABLE>/`) so that
identically named `<SCHEMA>.<TABLE>` pairs don't overwrite each other.

Snowflake resolves unquoted identifiers to uppercase, so names that aren't
uppercase are double-quoted to keep their exact case. Pass `--default-database`
and `--default-schema` exactly as the catalog stores them (usually uppercase,
such as `ANALYTICS`).

### B. Databricks Export SQL Generator (`./export_databricks_tables.py`)

Generates catalog-agnostic 2-part `<schema>.<table>` Spark SQL `INSERT OVERWRITE
DIRECTORY ... USING PARQUET` (or standalone `SELECT` by using `--export-mode
select`) scripts (`.sql`) with explicit type-safe projections for all discovered
Delta / Spark tables. Leave `--catalog` unset so the generated `.sql` files work
across both Unity Catalog and `hive_metastore` (activated by using `USE CATALOG`
on the target Spark or Databricks session at execution time), or pass `--catalog
<CATALOG>` for explicit 3-part table qualification. `--catalog` also exports
only the tables of that catalog when the metadata names catalogs (3-part YAML
`sourceName` values or the extractor `metadata.zip`); the generator exits with
an error that lists the available catalogs when it matches none of them:

```bash
python3 ./export_databricks_tables.py \
    --translation-metadata-dir ./translated_output/metadata \
    --stage-path '/tmp/databricks_export' \
    --output-sql export_databricks_to_parquet.sql \
    --output-dir ./export_sql
```

### C. Teradata Export SQL Generator (`./export_teradata_tables.py`)

Generates explicit-cast Teradata `SELECT` scripts (`.sql`) with `-- Unload
Table: <DB>.<TABLE> -> Parquet` and `-- Required Columns:` markers consumed by
downstream Python Parquet streaming scripts (for example, by using `teradatasql`
and `pyarrow`). Use `--default-database <DB>` as a fallback qualifier when
metadata omits `TableSchema` (defaults to `$TERADATA_DATABASE`), `--database
<DB>` (repeatable) as an allow-list filter to export only specific databases
(the generator exits with an error when it leaves no tables),
`--unbounded-number-scale <S>` to adjust the fractional scale for unbounded
`NUMBER` / `NUMBER(*)` columns (default `9`), and `--keep-char-padding` if
fixed-width `CHAR(n)` trailing spaces must be preserved instead of trimmed:

```bash
# 1. Generate per-table Teradata export SQL files from BQMS translation output:
python3 ./export_teradata_tables.py \
    --translation-metadata-dir ./translated_output/metadata \
    --default-database my_db \
    --output-dir ./export_sql

# 2. Generate a unified export SQL script from a Teradata extractor metadata.zip:
python3 ./export_teradata_tables.py \
    --metadata-zip gs://my-bucket/teradata_metadata/dwh-migration-teradata-metadata.zip \
    --database my_db \
    --output-sql teradata_export.sql
```

### D. Oracle Export SQL Generator (`./export_oracle_tables.py`)

Generates explicit-cast Oracle `SELECT` scripts (`.sql`) with `-- Unload Table:
<SCHEMA>.<TABLE> -> Parquet` and `-- Required Columns:` markers consumed by
downstream Python Parquet streaming scripts (for example, by using
`python-oracledb` and `pyarrow`). Use `--default-schema <SCHEMA>` as a fallback
qualifier when metadata omits `TableSchema` (defaults to `$ORACLE_SCHEMA`),
`--schema <SCHEMA>` (repeatable) as an allow-list filter to export only specific
schemas, `--unbounded-number-scale <S>` to adjust the fractional scale for
unconstrained `NUMBER` columns (default `9`), and `--keep-char-padding` if
fixed-width `CHAR(n)` / `NCHAR(n)` trailing spaces must be preserved instead of
trimmed. Identifiers that aren't uppercase are double-quoted to keep their exact
case, so pass `--default-schema` exactly as the catalog stores it (usually
uppercase, such as `HR`):

```bash
# 1. Generate per-table Oracle export SQL files from BQMS translation output:
python3 ./export_oracle_tables.py \
    --translation-metadata-dir ./translated_output/metadata \
    --default-schema MY_SCHEMA \
    --output-dir ./export_sql

# 2. Generate a unified export SQL script from an Oracle extractor metadata.zip:
python3 ./export_oracle_tables.py \
    --metadata-zip gs://my-bucket/oracle_metadata/dwh-migration-oracle-metadata.zip \
    --schema MY_SCHEMA \
    --output-sql oracle_export.sql
```

### E. PostgreSQL Export SQL Generator (`./export_postgres_tables.py`)

Generates explicit-cast PostgreSQL `SELECT` scripts (`.sql`) with `-- Unload
Table: <SCHEMA>.<TABLE> -> Parquet` and `-- Required Columns:` markers consumed
by downstream Python Parquet streaming scripts (for example, by using `psycopg2`
and `pyarrow`). Use `--default-schema <SCHEMA>` as a fallback qualifier when
metadata omits `TableSchema` (defaults to `$PG_SCHEMA`), `--schema <SCHEMA>`
(repeatable) as an allow-list filter to export only specific schemas,
`--database <DB>` (repeatable) to keep only one database's tables when the
metadata spans several PostgreSQL databases (the generator exits with an error
when `--schema` / `--database` leave no tables),
`--unbounded-number-scale <S>` to adjust the fractional scale for unconstrained
`NUMERIC` columns (default `9`), and `--keep-char-padding` if fixed-width
`CHAR(n)` / `BPCHAR` trailing spaces must be preserved instead of trimmed.
Identifiers that aren't lowercase are double-quoted to keep their exact case,
so pass `--default-schema` exactly as the catalog stores it (usually lowercase,
such as `public`). BQMS YAML configs record PostgreSQL `NUMERIC` columns as a
`NUMERIC(18, 0)` placeholder, so pass the extractor `--metadata-zip` together
with `--translation-metadata-dir` (example 3) to restore exact `NUMERIC(p, s)`
and `NOT NULL` details:

```bash
# 1. Generate per-table PostgreSQL export SQL files from BQMS translation output:
python3 ./export_postgres_tables.py \
    --translation-metadata-dir ./translated_output/metadata \
    --default-schema public \
    --output-dir ./export_sql

# 2. Generate a unified export SQL script from a PostgreSQL extractor metadata.zip:
python3 ./export_postgres_tables.py \
    --metadata-zip gs://my-bucket/postgres_metadata/postgresql-metadata.zip \
    --schema public \
    --output-sql postgres_export.sql

# 3. Combine BQMS translation output with the extractor metadata.zip:
python3 ./export_postgres_tables.py \
    --translation-metadata-dir ./translated_output/metadata \
    --metadata-zip gs://my-bucket/postgres_metadata/postgresql-metadata.zip \
    --default-schema public \
    --output-dir ./export_sql
```

--------------------------------------------------------------------------------

## 4. Generated SQL Pattern

### Snowflake COPY INTO Pattern

```sql
ALTER SESSION SET TIME_OUTPUT_FORMAT = 'HH24:MI:SS.FF6';
ALTER SESSION SET TIMESTAMP_NTZ_OUTPUT_FORMAT = 'YYYY-MM-DD HH24:MI:SS.FF6';
ALTER SESSION SET TIMESTAMP_TZ_OUTPUT_FORMAT = 'YYYY-MM-DD HH24:MI:SS.FF6 TZHTZM';

COPY INTO 'gcs://my-bucket/data_unload/RAW_POS/MENU/'
FROM (
    SELECT
      CAST(MENU_ID AS BIGINT) AS MENU_ID,
      CAST(COST_OF_GOODS_USD AS DECIMAL(38, 4)) AS COST_OF_GOODS_USD,
      TO_VARCHAR(MENU_ITEM_HEALTH_METRICS_OBJ) AS MENU_ITEM_HEALTH_METRICS_OBJ
    FROM MY_DB.RAW_POS.MENU
  )
  STORAGE_INTEGRATION = my_gcs_integration
FILE_FORMAT = (
  TYPE = PARQUET
  COMPRESSION = SNAPPY
)
HEADER = TRUE
OVERWRITE = TRUE
MAX_FILE_SIZE = 104857600;
```

### Databricks, Teradata, Oracle, and PostgreSQL Patterns

Section 4 of the [Databricks][databricks_map], [Teradata][teradata_map],
[Oracle][oracle_map], and [PostgreSQL][postgres_map] mapping references shows
the complete generated script: Spark SQL `INSERT OVERWRITE DIRECTORY ... USING
PARQUET SELECT ...` for Databricks, and explicit-cast `SELECT ...` statements
(`LOCKING ROW FOR ACCESS SELECT ...` in Teradata) with `-- Unload Table:` and
`-- Required Columns:` markers for the others.

[snowflake_exporter_template]: assets/export_snowflake_tables_template.py
[databricks_exporter_template]: assets/export_databricks_tables_template.py
[teradata_exporter_template]: assets/export_teradata_tables_template.py
[oracle_exporter_template]: assets/export_oracle_tables_template.py
[postgres_exporter_template]: assets/export_postgres_tables_template.py
[snowflake_map]: references/snowflake_parquet_mapping.md
[databricks_map]: references/databricks_parquet_mapping.md
[teradata_map]: references/teradata_parquet_mapping.md
[oracle_map]: references/oracle_parquet_mapping.md
[postgres_map]: references/postgres_parquet_mapping.md
[snowflake_gcs_integration]: https://docs.snowflake.com/en/user-guide/data-load-gcs-config
