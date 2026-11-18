# Oracle to BigQuery Parquet Type Mapping & Export Reference

This reference defines the type-safe projection rules used by
`export_oracle_tables_template.py` (`bigquery-migration-data-exporter`) and the
`pyarrow` Parquet schema mapping for downstream Oracle Parquet streaming.

## Contents

-   [1. End-to-End Oracle Parquet Export Architecture][s1]: Lines 19-44
-   [2. Oracle Data Type Mapping Matrix][s2]: Lines 45-71
-   [3. Critical Implementation Details][s3]: Lines 72-114
-   [4. Generated Oracle Export SQL Example][s4]: Lines 115-135

[s1]: #1-end-to-end-oracle-parquet-export-architecture
[s2]: #2-oracle-data-type-mapping-matrix
[s3]: #3-critical-implementation-details
[s4]: #4-generated-oracle-export-sql-example

## 1. End-to-End Oracle Parquet Export Architecture

Unlike Snowflake (`COPY INTO 'gcs://...'`) or Databricks (`INSERT OVERWRITE
DIRECTORY`), standard Oracle Database (11g, 12c, 19c, 21c, 23ai on-premises or
Compute Engine) does not provide a native SQL statement that unloads arbitrary
relational tables to Parquet on local disk or Cloud Storage
(`DBMS_CLOUD.EXPORT_DATA` is Autonomous Database-only).

Instead, the migration pipeline separates SQL generation from database
execution:

1.  **SQL Generation (`bigquery-migration-data-exporter` —
    `export_oracle_tables_template.py`)**: Reads BigQuery Migration Service
    (BQMS) `translation_output/metadata/config/*.yaml` or the Oracle extraction
    `metadata.zip` (`tables.csv`, `columns.csv`) and emits pure Oracle `SELECT`
    statements with explicit `CAST`/`RTRIM`/`TRUNC` expressions, `-- Unload
    Table: <SCHEMA>.<TABLE> -> Parquet` markers, and `-- Required Columns:`
    nullability metadata.
2.  **SQL Execution & Parquet Streaming**: A downstream Python script connects
    to Oracle by using the pure-Python `python-oracledb` driver in thin mode (no
    Oracle Instant Client required), executes each generated `SELECT`, maps
    `cursor.description` to an explicit `pyarrow.schema`, streams batches to
    Snappy-compressed Parquet part files
    (`./data_unload/[<SCHEMA>/]<TABLE>/part-*.snappy.parquet`), and uploads them
    to Cloud Storage.

## 2. Oracle Data Type Mapping Matrix

<!-- disableFinding(LINE_OVER_80) -->

Oracle Source Type                                                                   | `ALL_TAB_COLUMNS` `DATA_TYPE`                               | BQMS `sourceType` (`name` / `genericName`)                  | Parquet / Arrow Type                                                   | BigQuery Target Type                                 | Export SQL Projection (`format_column_cast`)                                                                 | Rationale & Validation Notes
:----------------------------------------------------------------------------------- | :---------------------------------------------------------- | :---------------------------------------------------------- | :--------------------------------------------------------------------- | :--------------------------------------------------- | :----------------------------------------------------------------------------------------------------------- | :---------------------------
**`NUMBER(p, 0)`** *(where `1 <= p <= 19`)* / **`SMALLINT`**                         | `NUMBER`                                                    | `NUMBER` / `NUMERIC` (`scale: 0`)                           | `INT64` (`pa.int64()`)                                                 | **`INT64`**                                          | `CAST(col AS NUMBER(19, 0)) AS col`                                                                          | Casting to `NUMBER(19, 0)` pins `cursor.description` to `(precision=19, scale=0)`, which the executor maps to `pa.int64()` so `bq load` creates a native `INT64` column matching BQMS DDL.
**`NUMBER(p, 0)`** *(where `20 <= p <= 38`)* / **`INTEGER`**                         | `NUMBER`                                                    | `NUMBER` / `NUMERIC` (`scale: 0`)                           | `DECIMAL(p, 0)` (`pa.decimal128(p, 0)`)                                | **`INT64`** / **`NUMERIC(p)`** / **`BIGNUMERIC(p)`** | `CAST(col AS NUMBER(p, 0)) AS col` *(or `CAST(col AS NUMBER(19, 0))` if target is `INT64`)*                  | Exceeds signed 64-bit integer precision (`> 19` digits); preserved as exact `DECIMAL128(p, 0)`.
**`NUMBER(p, s)`** *(where `s > 0`, `p - s <= 29`, `s <= 9`)*                        | `NUMBER`                                                    | `NUMBER` / `NUMERIC`                                        | `DECIMAL(p, s)` (`pa.decimal128(p, s)`)                                | **`NUMERIC(p, s)`**                                  | `CAST(col AS NUMBER(p, s)) AS col`                                                                           | Preserves exact decimal precision and scale; loads directly into BigQuery `NUMERIC`.
**`NUMBER(p, s)`** *(where `p - s > 29` or `s > 9`, for example, `NUMBER(38, 10)`)*  | `NUMBER`                                                    | `NUMBER` / `NUMERIC`                                        | `DECIMAL(p, s)` (`pa.decimal128(p, s)`)                                | **`BIGNUMERIC(p, s)`**                               | `CAST(col AS NUMBER(p, s)) AS col`                                                                           | Requires `--decimal_target_types=NUMERIC --decimal_target_types=BIGNUMERIC --decimal_target_types=STRING` on `bq load`.
**`NUMBER(p, s)`** *(negative scale `s < 0`, for example, `NUMBER(10, -2)`)*         | `NUMBER`                                                    | `NUMBER` / `NUMERIC`                                        | `INT64` or `DECIMAL(p+\|s\|, 0)`                                       | **`INT64`** / **`NUMERIC`** / **`BIGNUMERIC`**       | `CAST(col AS NUMBER(19, 0))` *(if `p+\|s\| <= 19`)* or `CAST(col AS NUMBER(min(p+\|s\|, 38), 0))`            | Negative scale rounds to `10^\|s\|` left of the decimal point (`p + \|s\|` integer digits, `0` fractional digits); normalizing to scale `0` avoids PyArrow negative-scale decimal errors.
**`NUMBER` / `NUMBER(*)`** *(unconstrained; `DATA_PRECISION=NULL, DATA_SCALE=NULL`)* | `NUMBER`                                                    | `NUMBER` / `NUMERIC` (`precision: 38`, no `scale`)          | `DECIMAL(38, 9)` (`pa.decimal128(38, 9)`) or `DOUBLE` (`pa.float64()`) | **`NUMERIC`** / **`BIGNUMERIC`** / **`FLOAT64`**     | `CAST(col AS NUMBER(38, 9)) AS col` *(or `CAST(col AS BINARY_DOUBLE)` if target is `FLOAT64`)*               | Unconstrained Oracle `NUMBER` returns `(precision=0, scale=-127)` in `cursor.description`; casting to `NUMBER(38, 9)` supports `<= 29` integer digits and `9` fractional digits (configurable by using `--unbounded-number-scale 0..38`).
**`FLOAT(b)`** / **`BINARY_FLOAT`** / **`BINARY_DOUBLE`**                            | `FLOAT`, `BINARY_FLOAT`, `BINARY_DOUBLE`                    | `FLOAT`, `BINARY_FLOAT`, `BINARY_DOUBLE`                    | `DOUBLE` (`pa.float64()`)                                              | **`FLOAT64`**                                        | `CAST(col AS BINARY_DOUBLE) AS col`                                                                          | Oracle `FLOAT(126)` is a binary-precision subtype of `NUMBER` and returns `DB_TYPE_NUMBER` unless cast; casting to `BINARY_DOUBLE` emits native IEEE-754 64-bit float (`DB_TYPE_BINARY_DOUBLE` -> `pa.float64()` -> BigQuery `FLOAT64`).
**`DATE`**                                                                           | `DATE`                                                      | `DATE` (`genericName: DATE` / `DATETIME`)                   | `TIMESTAMP_MICROS` (`pa.timestamp('us')`) or `DATE` (`pa.date32()`)    | **`DATETIME`** / **`DATE`**                          | `CAST(col AS TIMESTAMP(6)) AS col` *(default / `DATETIME`)* or `TRUNC(col) AS col` *(when target is `DATE`)* | Oracle `DATE` carries a `YYYY-MM-DD HH24:MI:SS` time component and BQMS translates it to `DATETIME` by default; `CAST(col AS TIMESTAMP(6))` preserves the time-of-day as `pa.timestamp('us')`. When `targetType` is `DATE`, `TRUNC(col)` strips time-of-day to `pa.date32()`.
**`TIMESTAMP(n)`**                                                                   | `TIMESTAMP(6)`                                              | `TIMESTAMP` (`genericName: DATETIME`)                       | `TIMESTAMP_MICROS` (`pa.timestamp('us')`)                              | **`DATETIME`** / **`TIMESTAMP`**                     | `CAST(col AS TIMESTAMP(6)) AS col`                                                                           | Truncates/pads `TIMESTAMP(0..9)` to microsecond precision (`TIMESTAMP(6)`) so `python-oracledb` and PyArrow serialize microsecond timestamps without nanosecond truncation errors.
**`TIMESTAMP(n) WITH TIME ZONE`**                                                    | `TIMESTAMP(6) WITH TIME ZONE`                               | `TIMESTAMP WITH TIME ZONE` (`genericName: TIMESTAMP`)       | `TIMESTAMP_MICROS` (`pa.timestamp('us')`)                              | **`TIMESTAMP`**                                      | `CAST(SYS_EXTRACT_UTC(col) AS TIMESTAMP(6)) AS col`                                                          | Converts any time zone offset or named region (for example, `'America/Los_Angeles'` or `'UTC'`) to UTC on the Oracle server and returns a microsecond `TIMESTAMP(6)`. Avoids `python-oracledb` thin-mode `DPY-3022: named time zones are not supported in thin mode`.
**`TIMESTAMP(n) WITH LOCAL TIME ZONE`**                                              | `TIMESTAMP(6) WITH LOCAL TIME ZONE`                         | `TIMESTAMP WITH LOCAL TIME ZONE` (`genericName: TIMESTAMP`) | `TIMESTAMP_MICROS` (`pa.timestamp('us')`)                              | **`TIMESTAMP`** / **`DATETIME`**                     | `CAST(SYS_EXTRACT_UTC(CAST(col AS TIMESTAMP WITH TIME ZONE)) AS TIMESTAMP(6)) AS col`                        | Converts the session-local value to `TIMESTAMP WITH TIME ZONE` and extracts UTC, so the export doesn't depend on the session `TIME_ZONE`; truncates to microsecond precision (`TIMESTAMP(6)`).
**`CHAR(n)`** / **`NCHAR(n)`**                                                       | `CHAR`, `NCHAR`                                             | `CHAR`, `NCHAR`                                             | `UTF8` (`pa.string()`)                                                 | **`STRING`**                                         | `RTRIM(col) AS col`                                                                                          | Oracle right-pads fixed-width `CHAR(n)` / `NCHAR(n)` with spaces; `RTRIM(col)` strips trailing pad spaces to match BigQuery `STRING`. Pass `--keep-char-padding` to preserve padding.
**`VARCHAR2(n)`** / **`NVARCHAR2(n)`** / **`CLOB`** / **`NCLOB`** / **`LONG`**       | `VARCHAR2`, `NVARCHAR2`, `CLOB`, `NCLOB`, `LONG`            | `VARCHAR2`, `NVARCHAR2`, `CLOB`, `NCLOB`                    | `UTF8` (`pa.string()`)                                                 | **`STRING`**                                         | `col AS col`                                                                                                 | Preserves intentional trailing spaces on variable-length strings; the executor fetches `CLOB`/`NCLOB` values directly as UTF-8 strings (`oracledb.defaults.fetch_lobs = False`, with a `v.read()` fallback).
**`RAW(n)`** / **`BLOB`** / **`LONG RAW`** / **`BFILE`**                             | `RAW`, `BLOB`, `LONG RAW`, `BFILE`                          | `RAW`, `BLOB`                                               | `BYTE_ARRAY` (`pa.binary()`)                                           | **`BYTES`**                                          | `col AS col`                                                                                                 | Emits raw byte sequences (`DB_TYPE_RAW` / `DB_TYPE_BLOB` -> `pa.binary()` -> BigQuery `BYTES`).
**`ROWID`** / **`UROWID`**                                                           | `ROWID`, `UROWID`                                           | `ROWID`, `UROWID`                                           | `UTF8` (`pa.string()`)                                                 | **`STRING`**                                         | `ROWIDTOCHAR(col) AS col` (`ROWID`) / `CAST(col AS VARCHAR2(256)) AS col` (`UROWID`)                         | Serializes physical (`ROWID`) and logical (`UROWID`) row addresses to standard character strings.
**`INTERVAL YEAR(p) TO MONTH`** / **`INTERVAL DAY(p) TO SECOND(s)`**                 | `INTERVAL YEAR(2) TO MONTH`, `INTERVAL DAY(2) TO SECOND(6)` | `INTERVAL YEAR TO MONTH`, `INTERVAL DAY TO SECOND`          | `UTF8` (`pa.string()`)                                                 | **`STRING`**                                         | `TRIM(CAST(col AS VARCHAR2(100))) AS col`                                                                    | `python-oracledb` raises `DPY-3007` on `INTERVAL YEAR TO MONTH` in thin mode unless converted to string, and maps `INTERVAL DAY TO SECOND` to `datetime.timedelta`; `TRIM(CAST(col AS VARCHAR2(100)))` serializes both cleanly as ANSI interval strings.
**`XMLTYPE`**                                                                        | `XMLTYPE`                                                   | `XMLTYPE`                                                   | `UTF8` (`pa.string()`)                                                 | **`STRING`**                                         | `XMLSERIALIZE(CONTENT col AS CLOB) AS col`                                                                   | Serializes Oracle `XMLTYPE` to UTF-8 XML text (`CLOB`).
**`JSON`** *(Oracle 21c+)*                                                           | `JSON`                                                      | `JSON`                                                      | `UTF8` (`pa.string()`)                                                 | **`JSON`** / **`STRING`**                            | `JSON_SERIALIZE(col RETURNING CLOB) AS col`                                                                  | Serializes native binary OSON `JSON` to UTF-8 JSON text.

<!-- enableFinding(LINE_OVER_80) -->

## 3. Critical Implementation Details

1.  **Why `SYS_EXTRACT_UTC(col)` is Required for `TIMESTAMP WITH TIME ZONE` in
    `python-oracledb` Thin Mode**: When an Oracle `TIMESTAMP WITH TIME ZONE`
    column contains a named time zone region rather than a numeric `+HH:MM`
    offset, `python-oracledb` thin mode raises `DPY-3022: named time zones are
    not supported in thin mode` unless a full `tzdata` package is negotiated.
    Projecting `CAST(SYS_EXTRACT_UTC(col) AS TIMESTAMP(6)) AS col` converts the
    timestamp to UTC on the Oracle server and transmits a plain 11-byte
    `TIMESTAMP(6)` over the wire, which loads into BigQuery `TIMESTAMP` with
    zero timezone drift.
2.  **Why `FLOAT(126)` Must Be Cast to `BINARY_DOUBLE`**: In Oracle, `FLOAT(p)`
    is stored internally as a `NUMBER` with binary precision `p` (`1..126`), so
    `ALL_TAB_COLUMNS` reports `DATA_TYPE = 'FLOAT', DATA_PRECISION = 126,
    DATA_SCALE = NULL`. Without an explicit cast, `python-oracledb` sees
    `DB_TYPE_NUMBER (precision=126, scale=-127)` instead of a float. Casting
    `CAST(col AS BINARY_DOUBLE)` produces `DB_TYPE_BINARY_DOUBLE` ->
    `pa.float64()` -> BigQuery `FLOAT64`.
3.  **Distinguishing Unconstrained `NUMBER` vs. `NUMBER(38, 0)` in Metadata**:
    In `columns.csv`, unconstrained `NUMBER` has empty `DATA_PRECISION` and
    `DATA_SCALE` (whereas `INTEGER` has empty `DATA_PRECISION` and `DATA_SCALE =
    0`). In BQMS `translation_output/metadata/config/*.yaml`, unconstrained
    `NUMBER` has `precision: 38` and no `scale` key (`scale: None`), whereas
    `INTEGER` or `NUMBER(38, 0)` has explicit `scale: 0`. `format_column_cast()`
    checks `precision` and `scale` to distinguish unconstrained `NUMBER`
    (`CAST(col AS NUMBER(38, 9))`) from integer `NUMBER(p, 0)` (`CAST(col AS
    NUMBER(19, 0))` for `p <= 19` or `CAST(col AS NUMBER(p, 0))` for `p >= 20`).
4.  **Filtering `DBA.TabColumns.csv` / `columns.csv` by Physical Base Tables**:
    Oracle's `ALL_TAB_COLUMNS` / `DBA_TAB_COLUMNS` view includes columns for
    both physical tables and views, as well as `BIN$...` Recycle Bin objects,
    `NESTED = 'YES'` tables, and `SECONDARY = 'Y'` domain-index tables.
    `load_metadata_from_zip()` and `_filter_tables_to_export()` cross-reference
    `DBA.Tables.csv` / `ALL.Tables.csv` (`DROPPED`, `SECONDARY`, `NESTED`, and
    `BIN$...` prefixes) or `tables.csv` (`TableType = 'BASE TABLE'` / `'TABLE'`)
    so only physical base tables are exported.
5.  **Cross-Type `TargetType` Overrides**: `format_column_cast()` converts
    integer, `FLOAT64`, `NUMERIC`, `BIGNUMERIC`, `DATETIME`, and `TIMESTAMP`
    targets, and `DATE` targets on `DATE` / `TIMESTAMP` columns. Other
    targets, such as `STRING`, `JSON`, or `BYTES` on numeric, datetime, or
    `RAW` columns, keep the default projection in the matrix above. If the
    BigQuery table needs a different conversion, edit the template's
    `# CUSTOMIZE: Custom Type Projections` hook.

## 4. Generated Oracle Export SQL Example

```sql
-- -----------------------------------------------------------------------------
-- Unload Table: SALES_SCHEMA.ITEM -> Parquet
-- -----------------------------------------------------------------------------
-- Required Columns: I_ITEM_SK,I_ITEM_ID
SELECT
  CAST(I_ITEM_SK AS NUMBER(19, 0)) AS I_ITEM_SK,
  RTRIM(I_ITEM_ID) AS I_ITEM_ID,
  CAST(I_REC_START_DATE AS TIMESTAMP(6)) AS I_REC_START_DATE,
  CAST(I_REC_END_DATE AS TIMESTAMP(6)) AS I_REC_END_DATE,
  I_ITEM_DESC AS I_ITEM_DESC,
  CAST(I_CURRENT_PRICE AS NUMBER(7, 2)) AS I_CURRENT_PRICE,
  CAST(I_WHOLESALE_COST AS NUMBER(7, 2)) AS I_WHOLESALE_COST,
  CAST(I_MEASURE_PRECISE AS BINARY_DOUBLE) AS I_MEASURE_PRECISE,
  CAST(I_EXACT_VALUATION AS NUMBER(38, 10)) AS I_EXACT_VALUATION,
  I_PRODUCT_SPEC_CLOB AS I_PRODUCT_SPEC_CLOB,
  I_THUMBNAIL_HASH AS I_THUMBNAIL_HASH
FROM SALES_SCHEMA.ITEM;
```
