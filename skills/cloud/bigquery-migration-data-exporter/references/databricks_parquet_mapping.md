# Databricks / Spark SQL to BigQuery Parquet Type Mapping & Export Reference

This reference defines the type-safe Spark SQL projection rules used by
`export_databricks_tables_template.py` (`bigquery-migration-data-exporter`) and
the Parquet staging and Arrow streaming execution patterns for Databricks and
Apache Spark SQL.

## Contents

-   [1. End-to-End Databricks Parquet Export Architecture][s1]: Lines 22-49
-   [2. Databricks and Spark SQL Data Type Mapping Matrix][s2]: Lines 52-79
-   [3. Unity Catalog and Hive Metastore Portability][s3]: Lines 82-106
-   [4. Generated Spark SQL Pattern][s4]: Lines 109-138

[s1]: #1-end-to-end-databricks-parquet-export-architecture
[s2]: #2-databricks-and-spark-sql-data-type-mapping-matrix
[s3]: #3-unity-catalog-and-hive-metastore-portability
[s4]: #4-generated-spark-sql-pattern

--------------------------------------------------------------------------------

## 1. End-to-End Databricks Parquet Export Architecture

Databricks and Apache Spark SQL environments support two primary data export
topologies:

1.  **Catalog-Agnostic SQL Generation (`bigquery-migration-data-exporter` —
    `export_databricks_tables_template.py`)**: Reads BigQuery Migration Service
    (BQMS) `translation_output/metadata/config/*.yaml` (or extraction
    `metadata.zip` files containing `columns.csv`, `tables.jsonl`, or DDL `.sql`
    scripts) and emits type-safe Spark SQL statements using **catalog-agnostic
    2-part `<schema>.<table>` references** by default (or optional 3-part
    `<catalog>.<schema>.<table>` when `--catalog` is specified). This allows the
    exact same generated `.sql` files to execute against either **Unity
    Catalog** (such as `main` or `retail_catalog`) or the legacy **Hive
    Metastore** (`hive_metastore`).
2.  **SQL Execution & Parquet Staging**:
    *   **Databricks SQL Warehouse (Arrow Streaming)**: Issues ``USE CATALOG
        \`<catalog>\` `` on the session when a target catalog is configured,
        extracts the inner type-safe `SELECT` query, and streams Arrow batches
        (`cursor.fetchmany_arrow()` by using `databricks-sql-connector`)
        directly into Snappy-compressed `.snappy.parquet` files on local disk
        before syncing to Cloud Storage.
    *   **Cloud URIs / Unity Catalog Volumes / Spark Hive Thrift Server (`INSERT
        OVERWRITE DIRECTORY`)**: Executes `INSERT OVERWRITE DIRECTORY '...'
        USING PARQUET OPTIONS ('compression' = 'snappy') SELECT ...`, cleans
        non-Parquet sidecar files (`.crc`, `_SUCCESS`), and stages the Parquet
        chunks to Cloud Storage.

--------------------------------------------------------------------------------

## 2. Databricks and Spark SQL Data Type Mapping Matrix

<!-- disableFinding(LINE_OVER_80) -->

Databricks / Spark SQL Source Type                                                  | BQMS `sourceType`             | Parquet / Arrow Type                                          | BigQuery Target Type                  | Export SQL Projection (`format_column_cast`)               | Rationale & Validation Notes
:---------------------------------------------------------------------------------- | :---------------------------- | :------------------------------------------------------------ | :------------------------------------ | :--------------------------------------------------------- | :---------------------------
**`TINYINT` / `BYTE` / `BYTEINT`**                                                  | `TINYINT` / `BYTE`            | `INT64` (`pa.int64()`)                                        | **`INT64`**                           | `CAST(col AS BIGINT) AS col`                               | Widens 8-bit integer to 64-bit `INT64` to match BigQuery `INT64` target schema.
**`SMALLINT` / `SHORT`**                                                            | `SMALLINT` / `SHORT`          | `INT64` (`pa.int64()`)                                        | **`INT64`**                           | `CAST(col AS BIGINT) AS col`                               | Widens 16-bit integer to 64-bit `INT64` to match BigQuery `INT64` target schema.
**`INT` / `INTEGER`**                                                               | `INT` / `INTEGER`             | `INT64` (`pa.int64()`)                                        | **`INT64`**                           | `CAST(col AS BIGINT) AS col`                               | Widens 32-bit integer to 64-bit `INT64` to match BigQuery `INT64` target schema.
**`BIGINT` / `LONG`**                                                               | `BIGINT` / `LONG`             | `INT64` (`pa.int64()`)                                        | **`INT64`**                           | `CAST(col AS BIGINT) AS col`                               | Direct 1:1 64-bit integer load.
**`FLOAT` / `REAL`**                                                                | `FLOAT`                       | `DOUBLE` (`pa.float64()`)                                     | **`FLOAT64`**                         | `CAST(col AS DOUBLE) AS col`                               | Widens 32-bit IEEE-754 float to 64-bit `DOUBLE` in Parquet to standardize 64-bit floating-point representation with BigQuery `FLOAT64`.
**`DOUBLE`**                                                                        | `DOUBLE`                      | `DOUBLE` (`pa.float64()`)                                     | **`FLOAT64`**                         | `CAST(col AS DOUBLE) AS col`                               | Standard IEEE-754 64-bit floating-point.
**`DECIMAL(p, 0)`** *(target `INT64`, or `p <= 18` with target unset)*              | `DECIMAL` / `NUMERIC`         | `INT64` (`pa.int64()`)                                        | **`INT64`**                           | `CAST(col AS BIGINT) AS col`                               | Avoids decimal logical type wrapper when `p <= 18` (or the target BigQuery column is `INT64`); an explicit `FLOAT64` or `STRING` target casts to `DOUBLE` or `STRING` instead; `19 <= p <= 38` with `s = 0` stays `DECIMAL(p, 0)` for `NUMERIC` / `BIGNUMERIC`.
**`DECIMAL(p, s)` / `DEC(p, s)` / `NUMERIC(p, s)`** *(where `p - s <= 29, s <= 9`)* | `DECIMAL` / `NUMERIC`         | `DECIMAL(p, s)` (`pa.decimal128(p, s)`)                       | **`NUMERIC`**                         | `CAST(col AS DECIMAL(p, s)) AS col`                        | Preserves exact decimal precision and scale without IEEE-754 float drift.
**`DECIMAL(p, s)`** *(where `p - s > 29` or `s > 9`, for example, `DECIMAL(38, 10)`)* | `DECIMAL` / `BIGNUMERIC`      | `DECIMAL(p, s)` (`pa.decimal128(p, s)`)                       | **`BIGNUMERIC`**                      | `CAST(col AS DECIMAL(p, s)) AS col`                        | Requires `--decimal_target_types=NUMERIC --decimal_target_types=BIGNUMERIC --decimal_target_types=STRING` during `bq load`.
**`BOOLEAN`**                                                                       | `BOOLEAN`                     | `BOOLEAN` (`pa.bool_()`)                                      | **`BOOL`**                            | `CAST(col AS BOOLEAN) AS col`                              | Direct 1:1 boolean mapping.
**`DATE`**                                                                          | `DATE`                        | `DATE` (`pa.date32()`)                                        | **`DATE`**                            | `CAST(col AS DATE) AS col`                                 | Days since Unix epoch (`1970-01-01`).
**`TIMESTAMP`**                                                                     | `TIMESTAMP`                   | `TIMESTAMP_MICROS` (`pa.timestamp('us', tz='UTC')`)           | **`TIMESTAMP`**                       | `CAST(col AS TIMESTAMP) AS col`                            | Microsecond UTC instant; loads directly into BigQuery `TIMESTAMP`.
**`TIMESTAMP_NTZ`**                                                                 | `TIMESTAMP_NTZ` / `TIMESTAMP` | `TIMESTAMP_MICROS` (`isAdjustedToUTC=false` or `tz='UTC'`)    | **`DATETIME`** / **`TIMESTAMP`**      | `col` *(if `DATETIME`)* or `CAST(col AS TIMESTAMP) AS col` | When target is `DATETIME`, left uncast (`isAdjustedToUTC=false` maps to BigQuery `DATETIME`). When target is `TIMESTAMP` (or unset), cast to `TIMESTAMP` (run in a UTC session, for example with the SQL warehouse `TIMEZONE` parameter or `spark.sql.session.timeZone` set to `UTC`, for deterministic UTC conversion).
**`INTERVAL`** *(`YEAR TO MONTH` / `DAY TO SECOND`)*                                | `INTERVAL`                    | `UTF8` (`pa.string()`)                                        | **`STRING`**                          | `CAST(col AS STRING) AS col`                               | Spark `INTERVAL` types cannot be written to Parquet directly; serializes ANSI interval text to UTF-8 `STRING`.
**`STRING` / `VARCHAR(n)` / `CHAR(n)`**                                             | `STRING` / `VARCHAR` / `CHAR` | `UTF8` (`pa.string()`)                                        | **`STRING`**                          | `col`                                                      | Exported as UTF-8 `STRING`. Note: Since Spark 3.4 (`spark.sql.readSideCharPadding=true`), Spark right-pads `CHAR(n)` on read unless `RTRIM(col)` is projected or `spark.sql.readSideCharPadding=false`.
**`BINARY`**                                                                        | `BINARY`                      | `BYTE_ARRAY` (`pa.binary()`)                                  | **`BYTES`**                           | `CAST(col AS BINARY) AS col`                               | Raw byte sequence; maps directly to BigQuery `BYTES`.
**`MAP<K, V>`** *(and `STRUCT` / `ARRAY` when target is `JSON` or `STRING`)*        | `MAP` / `STRUCT` / `ARRAY`    | `UTF8` (`pa.string()`)                                        | **`JSON`** / **`STRING`**             | `TO_JSON(col) AS col`                                      | Native Parquet `MAP` is nested key/value records in BigQuery and `CAST(struct_col AS STRING)` emits non-JSON `{a, b}`; `TO_JSON(col)` guarantees valid RFC-8259 JSON text.
**`STRUCT<...>` / `ARRAY<...>`** *(when target is `RECORD` / `ARRAY` or unset)*     | `STRUCT` / `ARRAY`            | Parquet `GROUP` / `LIST` (`pa.struct(...)` / `pa.list_(...)`) | **`STRUCT` (`RECORD`)** / **`ARRAY`** | `col`                                                      | Native Parquet nested struct/list passthrough. Note: `bq load --source_format=PARQUET` requires `--parquet_enable_list_inference=true` for native `ARRAY` columns.
**`VARIANT` / `JSON`**                                                              | `VARIANT` / `JSON`            | `UTF8` (`pa.string()`)                                        | **`JSON`** / **`STRING`**             | `CAST(col AS STRING) AS col`                               | Serializes Spark 4.0+ / Databricks `VARIANT` values to UTF-8 JSON strings.

<!-- enableFinding(LINE_OVER_80) -->

--------------------------------------------------------------------------------

## 3. Unity Catalog and Hive Metastore Portability

By default, `export_databricks_tables_template.py` strips the leading catalog
identifier from 3-part `sourceName` entries (`<catalog>.<schema>.<table>` →
`<schema>.<table>`) so the generated `.sql` scripts are **catalog-agnostic**:

*   **Default (Catalog-Agnostic 2-Part SQL)**: Omit `--catalog` when running
    `export_databricks_tables.py`. At execution time, run ``USE CATALOG
    \`<catalog>\` `` on the Databricks session before executing each statement.
*   **Explicit 3-Part Qualification**: Pass `--catalog <catalog>` to
    `export_databricks_tables.py` if you want 3-part
    `<catalog>.<schema>.<table>` identifiers baked directly into the `FROM`
    clause. Metadata entries that name a different catalog are skipped (the
    `spark_catalog` placeholder matches any `--catalog`). Without `--catalog`,
    a `<schema>.<table>` that appears in more than one catalog is exported
    once, with a warning.
*   **Export Modes (`--export-mode`)**:
    *   `insert_overwrite` (default): Emits `INSERT OVERWRITE DIRECTORY '...'
        USING PARQUET OPTIONS ('compression' = 'snappy') SELECT ...;`. When
        connecting to a Databricks SQL Warehouse and targeting a local stage
        path, downstream execution scripts can strip the `INSERT OVERWRITE
        DIRECTORY` prefix and stream Arrow batches directly to Parquet.
    *   `select`: Emits standalone `SELECT ... FROM <schema>.<table>;`
        statements with `-- Unload Table: <schema>.<table> -> Parquet` headers.

--------------------------------------------------------------------------------

## 4. Generated Spark SQL Pattern

```sql
-- =============================================================================
-- Databricks / Spark SQL to Parquet Type-Safe Data Export Script
-- Generated by bigquery-migration-data-exporter / export_databricks_tables.py
-- NOTE: TIMESTAMP_NTZ <-> TIMESTAMP casts use the session time zone. Run
-- in a UTC session (SQL warehouse TIMEZONE or spark.sql.session.timeZone
-- set to UTC, or SET TIME ZONE 'UTC' first in a beeline session).
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Unload Table: retail_db.item -> Parquet
-- -----------------------------------------------------------------------------
INSERT OVERWRITE DIRECTORY '/tmp/databricks_export/item'
USING PARQUET
OPTIONS ('compression' = 'snappy')
SELECT
  CAST(i_item_sk AS BIGINT) AS i_item_sk,
  i_item_id,
  CAST(i_rec_start_date AS DATE) AS i_rec_start_date,
  CAST(i_current_price AS DECIMAL(7, 2)) AS i_current_price,
  CAST(i_wholesale_cost AS DECIMAL(18, 4)) AS i_wholesale_cost,
  CAST(i_exact_valuation AS DECIMAL(38, 10)) AS i_exact_valuation,
  CAST(i_weight_kg AS DOUBLE) AS i_weight_kg,
  CAST(i_created_at AS TIMESTAMP) AS i_created_at,
  CAST(i_local_updated_at AS TIMESTAMP) AS i_local_updated_at,
  CAST(i_thumbnail_hash AS BINARY) AS i_thumbnail_hash
FROM retail_db.item;
```
