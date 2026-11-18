# Teradata to BigQuery Parquet Type Mapping & Export Reference

This reference defines the type-safe projection rules used by
`export_teradata_tables_template.py` (`bigquery-migration-data-exporter`) and
the `pyarrow` Parquet schema mapping for downstream Teradata Parquet streaming.

## Contents

-   [1. End-to-End Teradata Parquet Export Architecture][s1]: Lines 21-45
-   [2. Teradata Data Type Mapping Matrix][s2]: Lines 48-76
-   [3. Critical Implementation Details][s3]: Lines 80-114
-   [4. Generated Teradata Export SQL Example][s4]: Lines 118-134

[s1]: #1-end-to-end-teradata-parquet-export-architecture
[s2]: #2-teradata-data-type-mapping-matrix
[s3]: #3-critical-implementation-details
[s4]: #4-generated-teradata-export-sql-example

--------------------------------------------------------------------------------

## 1. End-to-End Teradata Parquet Export Architecture

Unlike Snowflake (`COPY INTO 'gcs://...'`) or Databricks (`INSERT OVERWRITE
DIRECTORY`), Teradata does not have a single universal SQL statement for
unloading arbitrary on-prem or cloud Vantage tables directly to Cloud Storage
without TPT/NOS infrastructure.

Instead, the migration pipeline separates SQL generation from database
execution:

1.  **SQL Generation (`bigquery-migration-data-exporter` —
    `export_teradata_tables_template.py`)**: Reads BigQuery Migration Service
    (BQMS) `translation_output/metadata/config/*.yaml` or the Teradata
    extraction `metadata.zip` (`dbc.TablesV.csv`, `dbc.ColumnsV.csv`) and emits
    pure Teradata `SELECT` statements with explicit `CAST`/`TRIM` expressions,
    `-- Unload Table: <DB>.<TABLE> -> Parquet` markers, and `-- Required
    Columns:` nullability metadata.
2.  **SQL Execution & Parquet Streaming**: A downstream Python script connects
    to Teradata by using the Python `teradatasql` driver, executes each
    generated `SELECT`, maps `cursor.description` to an explicit
    `pyarrow.schema`, streams batches to Snappy-compressed Parquet part files
    (`./data_unload/<DB>/<TABLE>/part-*.snappy.parquet`, or
    `./data_unload/<TABLE>/part-*.snappy.parquet` when unqualified), and uploads
    them to Cloud Storage.

--------------------------------------------------------------------------------

## 2. Teradata Data Type Mapping Matrix

<!-- disableFinding(LINE_OVER_80) -->

| Teradata Source Type | `dbc.ColumnsV` Code | BQMS `sourceType` | Parquet / Arrow Type | BigQuery Target Type | Export SQL Projection (`format_column_cast`) | Rationale & Validation Notes |
| :------------------- | :------------------ | :---------------- | :------------------- | :------------------- | :------------------------------------------- | :--------------------------- |
| **`BYTEINT`** | `I1` | `TINYINT` | `INT64` (`pa.int64()`) | **`INT64`** | `CAST(col AS BIGINT) AS col` | Direct 1:1 64-bit integer load. |
| **`SMALLINT`** | `I2` | `SMALLINT` | `INT64` (`pa.int64()`) | **`INT64`** | `CAST(col AS BIGINT) AS col` | Direct 1:1 64-bit integer load. |
| **`INTEGER`** | `I` | `INTEGER` | `INT64` (`pa.int64()`) | **`INT64`** | `CAST(col AS BIGINT) AS col` | Direct 1:1 64-bit integer load. |
| **`BIGINT`** | `I8` | `BIGINT` | `INT64` (`pa.int64()`) | **`INT64`** | `CAST(col AS BIGINT) AS col` | Direct 1:1 64-bit integer load. |
| **`DECIMAL(p, s)`** *(where `p - s <= 29, s <= 9`)* | `D` | `NUMERIC` | `DECIMAL(p, s)` (`pa.decimal128(p, s)`) | **`NUMERIC(29+s, s)`** | `CAST(col AS DECIMAL(p, s)) AS col` | Preserves exact fixed scale; loads directly into `NUMERIC`. |
| **`DECIMAL(p, s)`** *(where `p - s > 29` or `s > 9`, for example, `DECIMAL(38,0)` or `DECIMAL(38,12)`)* | `D` | `NUMERIC` | `DECIMAL(p, s)` (`pa.decimal128(p, s)`) | **`BIGNUMERIC`** | `CAST(col AS DECIMAL(p, s)) AS col` | Requires `--decimal_target_types=NUMERIC --decimal_target_types=BIGNUMERIC --decimal_target_types=STRING` on `bq load`. |
| **`NUMBER(p, s)`** *(bounded)* | `N` | `NUMERIC` | `DECIMAL(p, s)` (`pa.decimal128(p, s)`) | **`NUMERIC`** / **`BIGNUMERIC`** | `CAST(col AS DECIMAL(p, s)) AS col` | Preserves exact precision and scale (or `CAST(col AS BIGINT)` when `TargetType` is `INT64`). |
| **`NUMBER` / `NUMBER(*)`** *(unbounded; `precision=-128` in `dbc.ColumnsV`)* | `N` | `NUMERIC` | `DECIMAL(38, 9)` (`pa.decimal128(38, 9)`) | **`NUMERIC(29)`** / **`BIGNUMERIC`** | `CAST(col AS DECIMAL(38, 9)) AS col` | Unbounded `NUMBER` reports `precision=40, scale=0` in `cursor.description` even when storing fractional values; `DECIMAL(38, 9)` supports `<= 29` integer digits (`38 - scale`; `scale=38` leaves `0` integer digits) and `9` fractional digits (configurable by using `--unbounded-number-scale 0..38` or `CAST(col AS VARCHAR(64))` for arbitrary scale; note that `--unbounded-number-scale > 9` or `VARCHAR` promotes the column to `BIGNUMERIC` or `STRING` during `bq load`, which requires matching target DDL types when loading into pre-created tables with `--replace=false`). |
| **`FLOAT` / `REAL` / `DOUBLE PRECISION`** | `F` | `DOUBLE` | `DOUBLE` (`pa.float64()`) | **`FLOAT64`** | `CAST(col AS FLOAT) AS col` | Standard IEEE-754 64-bit float. |
| **`DATE`** | `DA` | `DATE` | `DATE` (`pa.date32()`) | **`DATE`** | `CAST(col AS DATE) AS col` | Days since `1970-01-01`; supports `0001-01-01`..`9999-12-31`. |
| **`TIME(n)`** | `AT` | `TIME` | `TIME_MICROS` (`pa.time64('us')`) | **`TIME`** | `CAST(col AS TIME(6)) AS col` | Normalizes `TIME(0)`..`TIME(6)` to microsecond precision. |
| **`TIME(n) WITH TIME ZONE`** | `TZ` | `TIMETZ` | `TIME_MICROS` (`pa.time64('us')`) | **`TIME`** | `CAST((col AT TIME ZONE 'GMT') AS TIME(6)) AS col` | Normalizes to UTC and strips `tzinfo` (`pyarrow.time64` rejects tz-aware `datetime.time`), matching BQMS target `TIME`. |
| **`TIMESTAMP(n)`** | `TS` | `TIMESTAMP` | `TIMESTAMP_MICROS` (`pa.timestamp('us')`) | **`TIMESTAMP`** / **`DATETIME`** | `CAST(col AS TIMESTAMP(6)) AS col` | Microsecond precision; loads into BigQuery `TIMESTAMP` or `DATETIME`. |
| **`TIMESTAMP(n) WITH TIME ZONE`** | `SZ` | `TIMESTAMPTZ` | `TIMESTAMP_MICROS` (`pa.timestamp('us')`) | **`TIMESTAMP`** | `CAST((col AT TIME ZONE 'GMT') AS TIMESTAMP(6)) AS col` | Converts to UTC inside Teradata and emits a naive UTC `TIMESTAMP(6)`. |
| **`CHAR(n)` / `GRAPHIC(n)`** *(`LATIN`, `UNICODE`, or `GRAPHIC`)* | `CF`, `GF` | `CHAR` | `UTF8` (`pa.string()`) | **`STRING`** | `TRIM(TRAILING FROM col) AS col` | Teradata pads `CHAR(n)` (and `CHAR(n) UNICODE` to `2n` to `3n` byte length); `TRIM(TRAILING)` prevents trailing-space mismatches against BigQuery `STRING`. |
| **`VARCHAR(n)` / `VARGRAPHIC(n)` / `CLOB`** | `CV`, `GV`, `CO` | `VARCHAR`, `CLOB` | `UTF8` (`pa.string()`) | **`STRING`** | `col AS col` | Preserves intentional trailing spaces on variable-length strings. |
| **`BYTE(n)` / `VARBYTE(n)` / `BLOB`** | `BF`, `BV`, `BO` | `BINARY`, `VARBINARY`, `BLOB` | `BYTE_ARRAY` (`pa.binary()`) | **`BYTES`** | `col AS col` | Raw byte sequence; never cast `BYTE` to `VARCHAR` (Teradata raises a syntax/type error). |
| **`JSON`** | `JN` | `JSON` | `UTF8` (`pa.string()`) | **`JSON`** / **`STRING`** | `CAST(col AS CLOB) AS col` | Serializes Teradata `JSON` to a UTF-8 JSON text string. |
| **`PERIOD(DATE)` / `PERIOD(TIMESTAMP)`** | `PD`, `PT`, `PZ`, `PS`, `PM` | `PERIOD_*` | `UTF8` (`pa.string()`) | **`RANGE<DATE>`** / **`RANGE<TIMESTAMP>`** / **`STRING`** | `CAST(col AS VARCHAR(100)) AS col` | Parquet has no native `RANGE` logical type; exported as formatted period text `'(start, end)'`. |
| **`INTERVAL ...`** | `YR`, `YM`, `MO`, `DY`, `DH`, `DM`, `DS`, `HR`, `HM`, `HS`, `MI`, `MS`, `SC` | `INTERVAL` | `UTF8` (`pa.string()`) | **`INTERVAL`** / **`STRING`** | `TRIM(CAST(col AS VARCHAR(100))) AS col` | Teradata prefixes positive interval strings with a leading sign space (for example, `' 12-11'`); `TRIM` removes it. |
| **`XML` / `ST_GEOMETRY` / `UDT` / `ARRAY`** | `XM`, `UT`, `A1`, `AN` | `XML`, `UDT`, `ARRAY` | `UTF8` (`pa.string()`) | **`STRING`** / **`GEOGRAPHY`** | `CAST(col AS VARCHAR(32000)) AS col` | Serialized as UTF-8 text (`VARCHAR(32000)` fits both `LATIN` and `UNICODE`; WKT for `ST_GEOMETRY`). |

<!-- enableFinding(LINE_OVER_80) -->

--------------------------------------------------------------------------------

## 3. Critical Implementation Details

1.  **`cursor.description` Nullability on Cast Expressions**: The `teradatasql`
    driver reports `null_ok=True` on raw nullable table columns, but reports
    `null_ok=False` on **every** `CAST(...)` or `TRIM(...)` projection
    expression. To preserve exact column nullability in the Parquet schema,
    `export_teradata_tables_template.py` emits a `-- Required Columns:
    col1,col2` comment above each `SELECT` listing only columns where
    `dbc.ColumnsV.Nullable = 'N'` (or BQMS `notNull: true`). The executor reads
    that marker and sets `pa.field(name, dtype, nullable=name.lower() not in
    required_columns)`.
2.  **`--decimal_target_types` for High-Precision `DECIMAL(38, s)`**: Parquet
    `DECIMAL(p, s)` columns where `p - s > 29` or `s > 9` (such as `DECIMAL(38,
    0)` or `DECIMAL(38, 12)`) exceed BigQuery's 29-integer-digit /
    9-fractional-digit `NUMERIC` limit. Pass `--decimal_target_types=NUMERIC
    --decimal_target_types=BIGNUMERIC --decimal_target_types=STRING` to `bq
    load` so BigQuery widens those columns to `BIGNUMERIC` automatically.
3.  **Dirty-Read Export Concurrency (`LOCKING ROW FOR ACCESS`)**: Each generated
    query starts with `LOCKING ROW FOR ACCESS` so large table exports do not
    acquire read locks that block concurrent Teradata writers. Remove `LOCKING
    ROW FOR ACCESS` in `_build_select_query()` if strict serializable read locks
    are required.
4.  **UTF-8 Session Encoding (`CHARACTER SET UNICODE`)**: The `teradatasql`
    Python driver defaults to UTF-8 session encoding (`charset='UTF8'`), which
    preserves non-ASCII `CHAR`/`VARCHAR CHARACTER SET UNICODE` characters
    end-to-end into Parquet. Note that Teradata's JDBC driver defaults to
    `ASCII` and replaces non-ASCII characters with `'?'` unless `CHARSET=UTF8`
    is explicitly set on the JDBC connection.
5.  **Cross-Type `TargetType` Overrides**: `format_column_cast()` converts
    integer, `FLOAT64`, `NUMERIC`, `BIGNUMERIC`, `DATE`, `TIME`, `DATETIME`,
    and `TIMESTAMP` targets. `STRING`, `JSON`, `BYTES`, and `BOOL` targets
    keep the default projection in the matrix above, so numeric, datetime,
    and `BYTE` / `VARBYTE` / `BLOB` columns keep their type. For a different
    conversion, edit the template's `# CUSTOMIZE: Custom Type Projections`
    hook.

--------------------------------------------------------------------------------

## 4. Generated Teradata Export SQL Example

```sql
-- -----------------------------------------------------------------------------
-- Unload Table: SALES_DB.ORDERS -> Parquet
-- -----------------------------------------------------------------------------
-- Required Columns: o_orderkey,o_custkey
LOCKING ROW FOR ACCESS
SELECT
  CAST(o_orderkey AS BIGINT) AS o_orderkey,
  CAST(o_custkey AS BIGINT) AS o_custkey,
  TRIM(TRAILING FROM o_orderstatus) AS o_orderstatus,
  CAST(o_totalprice AS DECIMAL(15,2)) AS o_totalprice,
  CAST(o_orderdate AS DATE) AS o_orderdate,
  CAST((o_created_tz AT TIME ZONE 'GMT') AS TIMESTAMP(6)) AS o_created_tz
FROM SALES_DB.ORDERS;
```
