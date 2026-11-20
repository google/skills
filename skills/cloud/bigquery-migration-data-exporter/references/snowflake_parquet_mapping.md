# Snowflake to Parquet Type Mapping Reference for BigQuery

This reference details the exact column casting and logical type mappings
required when exporting data from **Snowflake** to **Parquet** to ensure
clean ingestion into **BigQuery** without type drift, truncation, or
JSON deserialization errors.

## Contents

-   [1. Complete Type Mapping Matrix][s1]: Lines 20-40
-   [2. Essential Snowflake Session Parameters][s2]: Lines 44-55
-   [3. Recommended COPY INTO Parquet File Options][s3]: Lines 58-91

[s1]: #1-complete-type-mapping-matrix
[s2]: #2-essential-snowflake-session-parameters
[s3]: #3-recommended-copy-into-parquet-file-options

--------------------------------------------------------------------------------

## 1. Complete Type Mapping Matrix

<!-- disableFinding(LINE_OVER_80) -->

| Snowflake Source Type | Parquet Physical & Logical Type | BigQuery Target Type | Snowflake Export Cast Expression | Rationale & Ingestion Details |
| :-------------------- | :------------------------------ | :------------------- | :------------------------------- | :---------------------------- |
| **`VARIANT` / `OBJECT` / `ARRAY`** | `BYTE_ARRAY` (`UTF8` String) | **`JSON`** | `TO_VARCHAR(col) AS col` | BigQuery Parquet reader expects valid JSON-formatted UTF-8 strings to load directly into native `JSON` columns. Raw Snowflake binary objects fail ingestion. |
| **`NUMBER(P, S)`** *(where `S > 0`)* | `FIXED_LEN_BYTE_ARRAY` (`DECIMAL(P, S)`) | **`NUMERIC(P, S)`** *(where `P - S <= 29, S <= 9`)* or **`BIGNUMERIC(P, S)`** | `CAST(col AS DECIMAL(P, S)) AS col` | Preserves exact fractional scale without converting to floating-point `DOUBLE` (which introduces IEEE-754 precision loss). Pass `--decimal_target_types=NUMERIC --decimal_target_types=BIGNUMERIC --decimal_target_types=STRING` on `bq load` when `P - S > 29` or `S > 9`. |
| **`NUMBER(P, 0)`** *(where `1 <= P <= 19`)* / **`INT` / `BIGINT` / `SMALLINT` / `TINYINT` / `BYTEINT`** | `INT64` | **`INT64`** | `CAST(col AS BIGINT) AS col` | Prevents unnecessary decimal wrapper; loads directly as standard 64-bit integer. |
| **`NUMBER(P, 0)`** *(where `20 <= P <= 38`)* | `FIXED_LEN_BYTE_ARRAY` (`DECIMAL(P, 0)`) | **`NUMERIC(P)`** *(where `P <= 29`)* / **`BIGNUMERIC(P)`** / **`INT64`** | `CAST(col AS DECIMAL(P, 0)) AS col` *(or `CAST(col AS BIGINT)` if target is `INT64`)* | Exceeds signed 64-bit integer precision (`> 19` digits); preserved as exact `DECIMAL(P, 0)` when `TargetType` is unset so 20–38 digit integers do not overflow `BIGINT`. |
| **`NUMBER` / `DECIMAL` / `NUMERIC`** *(unconstrained; scale omitted)* | `FIXED_LEN_BYTE_ARRAY` (`DECIMAL(38, 9)`) | **`NUMERIC`** / **`BIGNUMERIC`** | `CAST(col AS DECIMAL(38, 9)) AS col` | Preserves up to `29` integer digits and `9` fractional digits without truncating scale when `TargetType` and `NumericScale` are omitted. |
| **`FLOAT` / `REAL` / `DOUBLE`** | `DOUBLE` | **`FLOAT64`** | `CAST(col AS DOUBLE) AS col` | Standard 64-bit floating point. |
| **`BOOLEAN`** | `BOOLEAN` | **`BOOL`** | `CAST(col AS BOOLEAN) AS col` | Direct 1:1 boolean mapping. |
| **`DATE`** | `INT32` (`DATE`) | **`DATE`** | `CAST(col AS DATE) AS col` | Days since Unix epoch (1970-01-01). |
| **`TIME` / `TIME(9)`** | `INT64` (`TIME_MICROS`) | **`TIME`** | `CAST(col AS TIME(6)) AS col` | Microseconds past midnight. Set session `TIME_OUTPUT_FORMAT = 'HH24:MI:SS.FF6'`. |
| **`TIMESTAMP_NTZ` / `TIMESTAMP_NTZ(9)`** | `INT64` (`TIMESTAMP_MICROS`) | **`DATETIME`** / **`TIMESTAMP`** | `CAST(col AS TIMESTAMP_NTZ(6)) AS col` | BigQuery supports microsecond precision. Avoids nanosecond overflow. |
| **`TIMESTAMP_TZ` / `TIMESTAMP_LTZ`** | `INT64` (`TIMESTAMP_MICROS`) | **`TIMESTAMP`** | `CAST(CONVERT_TIMEZONE('UTC', col) AS TIMESTAMP_NTZ(6)) AS col` | Normalized to UTC timestamp. |
| **`TEXT` / `VARCHAR` / `STRING` / `CHAR`** | `BYTE_ARRAY` (`UTF8`) | **`STRING`** | `CAST(col AS VARCHAR) AS col` | UTF-8 string encoding. |
| **`BINARY` / `VARBINARY`** | `BYTE_ARRAY` | **`BYTES`** | `CAST(col AS BINARY) AS col` | Raw byte sequence. |

<!-- enableFinding(LINE_OVER_80) -->

--------------------------------------------------------------------------------

## 2. Essential Snowflake Session Parameters

Before executing `COPY INTO`, set these session parameters to ensure uniform
microsecond and timestamp output formatting:

```sql
-- Ensure microsecond timestamp and time formatting
ALTER SESSION SET TIME_OUTPUT_FORMAT = 'HH24:MI:SS.FF6';
ALTER SESSION SET TIMESTAMP_NTZ_OUTPUT_FORMAT = 'YYYY-MM-DD HH24:MI:SS.FF6';
ALTER SESSION SET TIMESTAMP_TZ_OUTPUT_FORMAT = 'YYYY-MM-DD HH24:MI:SS.FF6 TZHTZM';
```

--------------------------------------------------------------------------------

## 3. Recommended COPY INTO Parquet File Options

```sql
COPY INTO 'gcs://my-bucket/path/TABLE_NAME/'
FROM (
  SELECT
    CAST(col1 AS BIGINT) AS col1,
    CAST(col2 AS DECIMAL(38, 4)) AS col2,
    TO_VARCHAR(col3) AS col3
  FROM MY_DB.MY_SCHEMA.TABLE_NAME
)
STORAGE_INTEGRATION = my_gcs_integration
FILE_FORMAT = (
  TYPE = PARQUET
  COMPRESSION = SNAPPY
)
HEADER = TRUE
OVERWRITE = TRUE
MAX_FILE_SIZE = 104857600; -- 100MB chunk size optimal for BigQuery parallel ingestion
```

### Key Option Rationale

*   **`STORAGE_INTEGRATION = my_gcs_integration`**: Required when unloading
    directly to a private `gcs://` bucket (Snowflake doesn't accept inline
    credentials for Cloud Storage). The generator emits this clause when you
    pass `--storage-integration`; omit it for Snowflake stage targets such as
    `@~/bqms_export/`.
*   **`COMPRESSION = SNAPPY`**: Standard high-throughput compression supported
    natively by BigQuery.
*   **`HEADER = TRUE`**: Embeds column names into Parquet file schema header.
*   **`OVERWRITE = TRUE`**: Ensures idempotency during re-runs.
*   **`MAX_FILE_SIZE = 104857600`** (100MB): Splits large tables into ~100MB
    partitions, allowing BigQuery parallel load slots to ingest concurrently.
