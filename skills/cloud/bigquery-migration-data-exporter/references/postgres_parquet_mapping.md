# PostgreSQL to BigQuery Parquet Type Mapping & Export Reference

This reference defines the type-safe projection rules used by
`export_postgres_tables_template.py` (`bigquery-migration-data-exporter`) and
the `pyarrow` Parquet schema mapping for downstream PostgreSQL Parquet
streaming.

## Contents

-   [1. End-to-End PostgreSQL Parquet Export Architecture][s1]: Lines 20-43
-   [2. PostgreSQL Data Type Mapping Matrix][s2]: Lines 44-71
-   [3. Critical Implementation Details][s3]: Lines 72-104
-   [4. Generated PostgreSQL Export SQL Example][s4]: Lines 106-126

[s1]: #1-end-to-end-postgresql-parquet-export-architecture
[s2]: #2-postgresql-data-type-mapping-matrix
[s3]: #3-critical-implementation-details
[s4]: #4-generated-postgresql-export-sql-example

## 1. End-to-End PostgreSQL Parquet Export Architecture

Standard PostgreSQL (`COPY ... TO`) exports text, CSV, or PostgreSQL-proprietary
binary streams, not Apache Parquet files, and requires superuser privileges for
server-side file output. To guarantee zero type drift and schema-aligned
BigQuery ingestion, the migration pipeline separates SQL generation from
database execution:

1.  **SQL Generation (`bigquery-migration-data-exporter` —
    `export_postgres_tables_template.py`)**: Reads BigQuery Migration Service
    (BQMS) `translation_output/metadata/config/*.yaml` or the PostgreSQL
    extraction `metadata.zip` (`is_columns_private.csv` and
    `pg_views_private.csv`, or `tables.csv` and `columns.csv`) and emits pure
    PostgreSQL `SELECT` statements with explicit `CAST`/`RTRIM` expressions, `--
    Unload Table: <SCHEMA>.<TABLE> -> Parquet` markers, and `-- Required
    Columns:` nullability metadata.
2.  **SQL Execution & Parquet Streaming**: A downstream Python script connects
    to PostgreSQL by using `psycopg2`, sets session `TIME ZONE 'UTC'`, streams
    rows in batches (`fetchmany`), maps `cursor.description` (`type_code` OID,
    `precision`, `scale`) to an explicit `pyarrow.schema`, writes
    Snappy-compressed Parquet part files
    (`./data_unload/[<SCHEMA>/]<TABLE>/part-*.snappy.parquet`), and uploads them
    to Cloud Storage.

## 2. PostgreSQL Data Type Mapping Matrix

<!-- disableFinding(LINE_OVER_80) -->

PostgreSQL Source Type                                                                                                                                                                                       | `information_schema` `data_type` / `udt_name`                            | BQMS `sourceType` (`name` / `genericName`)                            | Parquet / Arrow Type                                | BigQuery Target Type                           | Export SQL Projection (`format_column_cast`)                                          | Rationale & Validation Notes
:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :----------------------------------------------------------------------- | :-------------------------------------------------------------------- | :-------------------------------------------------- | :--------------------------------------------- | :------------------------------------------------------------------------------------ | :---------------------------
**`SMALLINT`** / **`INTEGER`** / **`BIGINT`** / **`SMALLSERIAL`** / **`SERIAL`** / **`BIGSERIAL`** / **`OID`**                                                                                               | `smallint` (`int2`), `integer` (`int4`), `bigint` (`int8`), `oid`        | `SMALLINT`, `INTEGER`, `BIGINT`, `OID`                                | `INT64` (`pa.int64()`)                              | **`INT64`**                                    | `CAST(col AS BIGINT) AS col`                                                          | Widens 16-bit and 32-bit integers and unsigned 32-bit `OID`s to 64-bit signed `BIGINT` (`OID 20` -> `pa.int64()` -> BigQuery `INT64`).
**`NUMERIC(p, 0)`** / **`DECIMAL(p, 0)`** *(where `1 <= p <= 38`)*                                                                                                                                           | `numeric`                                                                | `NUMERIC` (`scale: 0`)                                                | `DECIMAL(p, 0)` (`pa.decimal128(p, 0)`)             | **`NUMERIC`** / **`BIGNUMERIC`** / **`INT64`** | `CAST(col AS NUMERIC(p, 0)) AS col` *(or `CAST(col AS BIGINT)` if target is `INT64`)* | Preserves exact decimal precision `NUMERIC(p, 0)` (`pa.decimal128(p, 0)`), which `bq load` maps to `NUMERIC` (`p <= 29`) or `BIGNUMERIC` (`30 <= p <= 38`).
**`NUMERIC(p, s)`** / **`DECIMAL(p, s)`** *(where `s > 0`, `p - s <= 29`, `s <= 9`)*                                                                                                                         | `numeric`                                                                | `NUMERIC`                                                             | `DECIMAL(p, s)` (`pa.decimal128(p, s)`)             | **`NUMERIC(p, s)`**                            | `CAST(col AS NUMERIC(p, s)) AS col`                                                   | Preserves exact precision and scale in `cursor.description` (`OID 1700`) and loads directly into BigQuery `NUMERIC`.
**`NUMERIC(p, s)`** / **`DECIMAL(p, s)`** *(where `p - s > 29` or `s > 9`, `p <= 38`)*                                                                                                                       | `numeric`                                                                | `NUMERIC`                                                             | `DECIMAL(p, s)` (`pa.decimal128(p, s)`)             | **`BIGNUMERIC(p, s)`**                         | `CAST(col AS NUMERIC(p, s)) AS col`                                                   | Requires `--decimal_target_types=NUMERIC --decimal_target_types=BIGNUMERIC --decimal_target_types=STRING` on `bq load`.
**`NUMERIC(p, s)`** *(negative scale `s < 0`, for example, `NUMERIC(10, -2)` in PostgreSQL 15+)*                                                                                                             | `numeric`                                                                | `NUMERIC`                                                             | `DECIMAL(min(p+\|s\|, 38), 0)` (`pa.decimal128`)    | **`NUMERIC`** / **`BIGNUMERIC`**               | `CAST(col AS NUMERIC(min(p+\|s\|, 38), 0)) AS col`                                    | Negative scale rounds to `10^\|s\|` left of the decimal point (`p + \|s\|` integer digits, `0` fractional digits). Casting to scale `0` avoids two's-complement negative scale encoding (`2048 + s`) in `atttypmod` and PyArrow negative-scale errors.
**`NUMERIC`** / **`DECIMAL`** *(unconstrained; `numeric_precision=NULL, numeric_scale=NULL`)*                                                                                                                | `numeric`                                                                | `NUMERIC` (`precision: None, scale: None`)                            | `DECIMAL(38, 9)` (`pa.decimal128(38, 9)`)           | **`NUMERIC`** / **`BIGNUMERIC`**               | `CAST(col AS NUMERIC(38, 9)) AS col`                                                  | Unconstrained PostgreSQL `NUMERIC` returns `precision=None, scale=None` (`atttypmod = -1`); casting to `NUMERIC(38, 9)` supports `<= 29` integer digits and `9` fractional digits (configurable by using `--unbounded-number-scale 0..38`).
**`MONEY`**                                                                                                                                                                                                  | `money`                                                                  | `MONEY`                                                               | `DECIMAL(38, 2)` (`pa.decimal128(38, 2)`)           | **`BIGNUMERIC`** / **`NUMERIC`**               | `CAST(col AS NUMERIC(38, 2)) AS col`                                                  | PostgreSQL `money` formats values with locale currency symbols (`$1,234.56`) over text wire protocol (`OID 790`); casting to `NUMERIC(38, 2)` strips currency symbols cleanly on the server.
**`REAL`** / **`FLOAT4`** / **`DOUBLE PRECISION`** / **`FLOAT8`**                                                                                                                                            | `real` (`float4`), `double precision` (`float8`)                         | `REAL`, `DOUBLE PRECISION`                                            | `DOUBLE` (`pa.float64()`)                           | **`FLOAT64`**                                  | `CAST(col AS DOUBLE PRECISION) AS col`                                                | Widens 32-bit `REAL` (`float4`) to 64-bit IEEE-754 `DOUBLE PRECISION` (`OID 701` -> `pa.float64()` -> BigQuery `FLOAT64`) and preserves `NaN` / `±Infinity`.
**`BOOLEAN`**                                                                                                                                                                                                | `boolean` (`bool`)                                                       | `BOOLEAN`                                                             | `BOOLEAN` (`pa.bool_()`)                            | **`BOOL`**                                     | `col AS col`                                                                          | Maps directly to `bool` (`OID 16` -> `pa.bool_()` -> BigQuery `BOOL`).
**`DATE`**                                                                                                                                                                                                   | `date`                                                                   | `DATE`                                                                | `DATE` (`pa.date32()`)                              | **`DATE`**                                     | `col AS col`                                                                          | Maps directly to `datetime.date` (`OID 1082` -> `pa.date32()` -> BigQuery `DATE`). A `TIMESTAMP` target projects `CAST((CAST(col AS TIMESTAMP) AT TIME ZONE 'UTC') AS TIMESTAMP(6) WITH TIME ZONE) AS col` (midnight UTC, whatever the session `TimeZone`).
**`TIME(p) [WITHOUT TIME ZONE]`** / **`TIME(p) WITH TIME ZONE`** (`timetz`)                                                                                                                                  | `time without time zone` (`time`), `time with time zone` (`timetz`)      | `TIME`, `TIMETZ`                                                      | `TIME_MICROS` (`pa.time64('us')`)                   | **`TIME`**                                     | `CAST(col AS TIME(6)) AS col`                                                         | Normalizes `TIME(0..6)` and `TIMETZ` to microsecond wall-clock precision (`OID 1083` -> `pa.time64('us')` -> BigQuery `TIME`).
**`TIMESTAMP(p) [WITHOUT TIME ZONE]`**                                                                                                                                                                       | `timestamp without time zone` (`timestamp`)                              | `TIMESTAMP` (`genericName: DATETIME`)                                 | `TIMESTAMP_MICROS` (`pa.timestamp('us')`)           | **`DATETIME`** / **`TIMESTAMP`**               | `CAST(col AS TIMESTAMP(6) WITHOUT TIME ZONE) AS col` *(default / `DATETIME`)* or `CAST((CAST(col AS TIMESTAMP) AT TIME ZONE 'UTC') AS TIMESTAMP(6) WITH TIME ZONE) AS col` *(when target is `TIMESTAMP`)*                                  | Emits naive `datetime.datetime` (`OID 1114` -> `pa.timestamp('us', tz=None)`, `isAdjustedToUTC=false`), which `bq load` maps to BigQuery `DATETIME`. A `TIMESTAMP` target reads the naive value as UTC, independent of the session `TimeZone`.
**`TIMESTAMP(p) WITH TIME ZONE`** (`timestamptz`)                                                                                                                                                            | `timestamp with time zone` (`timestamptz`)                               | `TIMESTAMPTZ` / `TIMESTAMP WITH TIME ZONE` (`genericName: TIMESTAMP`) | `TIMESTAMP_MICROS` (`pa.timestamp('us', tz='UTC')`) | **`TIMESTAMP`** / **`DATETIME`**               | `CAST(col AS TIMESTAMP(6) WITH TIME ZONE) AS col` *(default / `TIMESTAMP`)* or `CAST((col AT TIME ZONE 'UTC') AS TIMESTAMP(6) WITHOUT TIME ZONE) AS col` *(when target is `DATETIME`, the UTC wall clock)*                                     | Normalizes `timestamptz` to microsecond precision (`OID 1184` -> `pa.timestamp('us', tz='UTC')`, `isAdjustedToUTC=true`), loading cleanly into BigQuery `TIMESTAMP` with zero timezone offset drift.
**`INTERVAL`**                                                                                                                                                                                               | `interval`                                                               | `INTERVAL`                                                            | `UTF8` (`pa.string()`)                              | **`STRING`**                                   | `CAST(col AS TEXT) AS col`                                                            | `psycopg2` cannot parse `YEAR`/`MONTH` intervals into `datetime.timedelta`; casting `CAST(col AS TEXT)` emits canonical text (`1 year 2 mons 3 days 04:05:06`).
**`CHAR(n)`** / **`CHARACTER(n)`** / **`BPCHAR`**                                                                                                                                                            | `character` (`bpchar`)                                                   | `CHAR`, `CHARACTER`                                                   | `UTF8` (`pa.string()`)                              | **`STRING`**                                   | `RTRIM(col) AS col`                                                                   | PostgreSQL blank-pads fixed-width `CHAR(n)` (`bpchar`); `RTRIM(col)` strips trailing pad spaces to match BigQuery `STRING`. Pass `--keep-char-padding` to preserve padding.
**`VARCHAR(n)`** / **`TEXT`**                                                                                                                                                                                | `character varying` (`varchar`), `text`                                  | `VARCHAR`, `TEXT`                                                     | `UTF8` (`pa.string()`)                              | **`STRING`**                                   | `col AS col`                                                                          | Preserves intentional trailing spaces on variable-length strings (`OID 1043` / `25` -> `pa.string()`).
**`BYTEA`**                                                                                                                                                                                                  | `bytea`                                                                  | `BYTEA`                                                               | `BYTE_ARRAY` (`pa.binary()`)                        | **`BYTES`**                                    | `col AS col`                                                                          | `psycopg2` decodes hex `bytea` (`OID 17`) to `memoryview`, which the executor converts by using `bytes(v)` into `pa.binary()` -> BigQuery `BYTES`.
**`JSON`** / **`JSONB`**                                                                                                                                                                                     | `json`, `jsonb`                                                          | `JSON`, `JSONB`                                                       | `UTF8` (`pa.string()`)                              | **`JSON`** / **`STRING`**                      | `CAST(col AS TEXT) AS col`                                                            | Serializes `json` (`OID 114`) and binary `jsonb` (`OID 3802`) as UTF-8 JSON text (`OID 25` -> `pa.string()`), which `bq load` ingests into both BigQuery `JSON` and `STRING` columns.
**`UUID`** / **`XML`** / **`INET`** / **`CIDR`** / **`MACADDR`** / **`MACADDR8`** / **`BIT(n)`** / **`VARBIT(n)`** / **`TSVECTOR`** / **`TSQUERY`** / **`PG_LSN`** / **Geometric** / **Range** / **`ARRAY`** | `uuid`, `xml`, `inet`, `cidr`, `macaddr`, `bit`, `ARRAY`, `USER-DEFINED` | `UUID`, `XML`, `INET`, `STRING`, `ARRAY`                              | `UTF8` (`pa.string()`)                              | **`STRING`**                                   | `CAST(col AS TEXT) AS col`                                                            | Normalizes PostgreSQL network, bit-string, geometric, range, XML, UUID, array, and enum types to `TEXT` (`OID 25`) so `psycopg2` returns `str` -> `pa.string()` -> BigQuery `STRING`.

<!-- enableFinding(LINE_OVER_80) -->

## 3. Critical Implementation Details

1.  **Why PostgreSQL 15+ Negative `NUMERIC(p, -s)` Scales Must Be Decoded and
    Normalized to Scale `0`**: PostgreSQL 15+ allows negative scales in
    `NUMERIC(p, -s)` (for example, `NUMERIC(10, -2)`), and `information_schema`
    masks `((typmod - 4) & 0x7ff)` without sign extension, reporting
    `numeric_scale = 2046` (`2048 - 2`). Because Parquet and PyArrow do not
    support negative decimal scales, `_decode_pg_scale()` decodes `1024 <= scale
    < 2048` back to `scale - 2048` and `format_column_cast()` widens the
    precision to `min(p + |s|, 38)` with scale `0` (`CAST(col AS NUMERIC(p +
    |s|, 0))`).
2.  **Why `MONEY` Must Be Cast to `NUMERIC(38, 2)`**: PostgreSQL's `money` type
    (`OID 790`) formats values over the text protocol using `lc_monetary` (for
    example, `'$1,234.56'` or `'($50.00)'`), which `psycopg2` returns as a
    formatted `str`. Casting `CAST(col AS NUMERIC(38, 2))` in the `SELECT`
    projection performs a lossless server-side conversion to `NUMERIC(38, 2)`
    (`OID 1700` -> `decimal.Decimal` -> `pa.decimal128(38, 2)` -> BigQuery
    `BIGNUMERIC`).
3.  **Restoring Exact `NUMERIC(p, s)` and `NOT NULL` Metadata When Using BQMS
    YAML Configs**: BQMS `translate_metadata` for PostgreSQL emits a generic
    placeholder (`precision: 18, scale: 0`) for `NUMERIC` columns in
    `metadata/config/*.yaml`. Pass the extractor `metadata.zip`
    (`is_columns_private.csv`) with `--metadata-zip` alongside
    `--translation-metadata-dir` (local or `gs://`), or place it next to a
    local `translated_output/`, and `load_metadata_from_dir()` enriches the
    YAML column metadata with the exact catalog precision, scale, and `NOT
    NULL` constraints.
4.  **Filtering System Catalog Schemas and Views**: PostgreSQL extraction zips
    (`postgresql-metadata.zip`) include `is_columns_private.csv` (which contains
    both base tables and views) and `pg_views_private.csv`, as well as
    `pg_catalog` and `information_schema`. `load_metadata_from_zip()` and
    `_filter_tables_to_export()` cross-reference `pg_views_private.csv` and
    exclude `_SYSTEM_SCHEMAS` so only physical user base tables are exported.

## 4. Generated PostgreSQL Export SQL Example

```sql
-- -----------------------------------------------------------------------------
-- Unload Table: public.item -> Parquet
-- -----------------------------------------------------------------------------
-- Required Columns: i_item_sk,i_item_id
SELECT
  CAST(i_item_sk AS BIGINT) AS i_item_sk,
  RTRIM(i_item_id) AS i_item_id,
  i_rec_start_date AS i_rec_start_date,
  i_rec_end_date AS i_rec_end_date,
  i_item_desc AS i_item_desc,
  CAST(i_current_price AS NUMERIC(7, 2)) AS i_current_price,
  CAST(i_wholesale_cost AS NUMERIC(7, 2)) AS i_wholesale_cost,
  CAST(i_measure_precise AS DOUBLE PRECISION) AS i_measure_precise,
  CAST(i_exact_valuation AS NUMERIC(38, 10)) AS i_exact_valuation,
  CAST(i_product_spec_json AS TEXT) AS i_product_spec_json,
  i_thumbnail_bytes AS i_thumbnail_bytes
FROM public.item;
```
