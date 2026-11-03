# Standardized dbt Dialect Migration Patterns (Snowflake to BigQuery)

This reference guide provides "Before vs. After" code patterns that match the target code standard for BigQuery curated models.

## Table of Contents

- [1. File Structure Template](#1-file-structure-template): Lines 16-47
- [2. Comparison Patterns](#2-comparison-patterns): Lines 49-78
- [3. Array Handling & Casting Standards](#3-array-handling-casting-standards): Lines 79-109
- [4. Post-Hook Standards](#4-post-hook-standards): Lines 110-118
- [5. Datetime and Timestamp Standards for JSON Extractions](#5-datetime-and-timestamp-standards-for-json-extractions): Lines 119-141
- [6. BigQuery STRUCT (RECORD) vs. JSON Columns](#6-bigquery-struct-record-vs-json-columns): Lines 142-217
- [7. Snowflake Bracket Notation & BQMS `error_unimplemented`](#7-snowflake-bracket-notation-bqms-error_unimplemented): Lines 218-253
- [8. BQMS 16MB String Wrappers & `STRING()` Function Signature](#8-bqms-16mb-string-wrappers-string-function-signature): Lines 254-284

## 1. File Structure Template
Every model should follow this structural flow:

```sql
# Copyright 2026 Google. This software is provided as-is, without warranty or
# representation for any use or purpose. Your use of it is subject to your
# agreement with Google.

{{ config(...) }}

WITH raw_json AS (
    SELECT
        a.data as json_data,
        a._extracted_at,
        CAST(JSON_EXTRACT_SCALAR(a.data, '$.id') AS INT64) as primary_id,
        row_number() over (partition by JSON_EXTRACT_SCALAR(a.data, '$.id') order by a._extracted_at desc) as rn
    FROM {{ source('...', '...') }} as a
    {% if is_incremental() %}
    WHERE _extracted_at >= (SELECT MAX(_extracted_at) FROM {{ this }})
    {% endif %}
    QUALIFY rn = 1
),
transform_layer AS (
    SELECT
        primary_id,
        CAST(JSON_EXTRACT_SCALAR(json_data, '$.field_name') AS STRING) as field_name,
        CAST(JSON_EXTRACT_SCALAR(json_data, '$.is_active') AS BOOL) as is_active,
        _extracted_at
    FROM raw_json
)
SELECT * FROM transform_layer
```

## 2. Comparison Patterns

| Feature | Snowflake Source | Standardized BigQuery Target |
| :--- | :--- | :--- |
| **JSON Path** | `data:user:id::int` | `json_value(data, '$.user.id')` |
| **JSON Array Element** | `data:items[1]::varchar` | `json_value(data, '$.items[1]')` |
| **JSON Scalar (Numeric)** | `TRY_PARSE_JSON(json_col):val::number` | `cast(json_extract_scalar(safe.parse_json(cast(source.json_col as STRING)), '$.val') as NUMERIC)` |
| **Safe Cast (`TRY_CAST` / `TRY_TO_*`)** | `TRY_CAST(data:val::string AS INT)` | `safe_cast(json_value(data, '$.val') as INT64)` |
| **JSON Timestamp (ISO-8601 with Z)** | `TRY_PARSE_JSON(json_col):updated_at::TIMESTAMP_NTZ` | `cast(json_extract_scalar(safe.parse_json(cast(source.json_col as STRING)), '$.updated_at') as TIMESTAMP)` |
| **JSON Datetime (via Timestamp)** | `TRY_PARSE_JSON(json_col):updated_at::TIMESTAMP_NTZ` | `cast(cast(json_extract_scalar(safe.parse_json(cast(source.json_col as STRING)), '$.updated_at') as TIMESTAMP) as DATETIME)` |
| **JSON String Array** | `data:tags` | `json_extract_string_array(safe.parse_json(cast(source.data as STRING)), '$.tags')` |
| **JSON Object Array** | `data:items` | `json_extract_array(safe.parse_json(cast(source.data as STRING)), '$.items')` |
| **Array Column (Raw String)** | `arr_col::array` | `cast(source.arr_col as STRING) as arr_col` |
| **Array Column (Native Array)** | `arr_col::array` | `cast(source.arr_col as ARRAY<STRING>) as arr_col` |
| **Array Column (Stringified JSON)** | `arr_col::array` | `json_extract_string_array(source.arr_col) as arr_col` |
| **Null Strings** | `data:status::string` | `json_value(data, '$.status')` |
| **Boolean** | `data:active::boolean` | `json_value(data, '$.active')` |
| **Truncation** | `LEFT(comment, 2000)` | `SUBSTR(comment, 1, 2000)` |
| **Search** | `comment LIKE '%urgent%'` | `LOWER(comment) LIKE '%urgent%'` |
| **Array Explode** | `LATERAL FLATTEN(input => data:tags)` | `CROSS JOIN UNNEST(JSON_EXTRACT_ARRAY(data, '$.tags'))` |
| **Date Add** | `DATEADD(hour, 1, date)` | `DATE_ADD(CAST(date AS DATETIME), INTERVAL 1 HOUR)` |
| **Window Alias** | `SELECT id, ROW_NUMBER() OVER(PARTITION BY id...)` | `SELECT CAST(JSON_EXTRACT_SCALAR(data, '$.id') AS INT64) as id, ROW_NUMBER() OVER(PARTITION BY CAST(JSON_EXTRACT_SCALAR(data, '$.id') AS INT64)...)` |
| **STRUCT Field Access** | `struct_col:count::numeric` | `cast(source.struct_col.count as NUMERIC)` |
| **STRUCT Field Access (Named / Quoted)** | `obj_col:"id"::varchar` | `obj_col.id as obj_id` |
| **STRUCT Nested Access** | `struct_col:nested:flag` | `source.struct_col.nested.flag` |
| **JSON Escaped Path** | `json_col:"Field Name"::string` | `json_value(json_col, '$."Field Name"')` |
| **Bracket Notation (STRUCT)** | `record_col['status']::TEXT` | `cast(source.record_col.status as STRING)` |
| **Bracket Notation (JSON)** | `json_col['status']::TEXT` | `json_value(source.json_col, '$.status')` |
| **`ARRAY<STRUCT>` Element Access (Native)** | `col[0]:field::string` | `source.col[SAFE_OFFSET(0)].field` |
| **`ARRAY<STRUCT>` JSONPath (Serialized)** | `col[0]:field::string` | `json_value(to_json(source.col), '$[0].field')` |

## 3. Array Handling & Casting Standards
Snowflake allows untyped array casting (`column::array` / `ARRAY`), whereas BigQuery Standard SQL requires strongly typed arrays (e.g. `ARRAY<STRING>`, `ARRAY<JSON>`). BigQuery Migration Service (BQMS) defaults Snowflake untyped `::array` to `ARRAY<JSON>`, which can cause type mismatches if the BigQuery source table is not `ARRAY<JSON>`.

When standardizing array column casts in BigQuery models, determine the target expression depending on whether the column (e.g., `arr_col`) in the BigQuery source table is stored as a raw `STRING` or an `ARRAY<STRING>`:

1. **If column should be `STRING`**:
   If the BigQuery source table stores the data as a raw string:
   ```sql
   cast(source.arr_col as STRING) as arr_col,
   ```

2. **If column should be `ARRAY<STRING>`**:
   - **If `source.arr_col` is already an array in BigQuery**:
     ```sql
     cast(source.arr_col as ARRAY<STRING>) as arr_col,
     ```
   - **If `source.arr_col` is a stringified JSON array string in BigQuery**:
     ```sql
     json_extract_string_array(source.arr_col) as arr_col,
     ```

3. **When extracting array elements from a nested JSON / stringified JSON column**:
   - **Extracting array of strings (e.g. `data:tags`)**:
     ```sql
     json_extract_string_array(safe.parse_json(cast(source.data as STRING)), '$.tags') as tags,
     ```
   - **Extracting array of JSON objects**:
     ```sql
     json_extract_array(safe.parse_json(cast(source.data as STRING)), '$.items') as items,
     ```

## 4. Post-Hook Standards
When updating tables in a `post_hook`, always use explicit type casting in the `WHERE` clause:

**Incorrect**:
`where t.ticket_id = stage.id`

**Correct**:
`where CAST(t.ticket_id AS STRING) = CAST(stage.id AS STRING)`

## 5. Datetime and Timestamp Standards for JSON Extractions
In BigQuery Standard SQL, `CAST(string_expr AS DATETIME)` strictly requires strings formatted as `YYYY-[M]M-[D]D[ { |T}[H]H:[M]M:[S]S[.F_SCHEME]]` without any trailing timezone offsets or trailing `'Z'`. When parsing ISO-8601 UTC timestamp strings ending in `'Z'` (e.g. `'2026-09-07T17:04:54.811Z'`), BigQuery raises a runtime query error:
`Invalid datetime string "2026-09-07T17:04:54.811Z"`

Snowflake's `::TIMESTAMP_NTZ` cast is frequently converted by BQMS to `DATETIME`. When applied to JSON extractions, this produces invalid BigQuery queries.

### Standard Patterns
1. **Direct Timestamp Cast (Recommended)**:
   Always cast JSON timestamp strings to `TIMESTAMP`, which natively parses ISO-8601 strings with trailing `'Z'`:
   ```sql
   cast(JSON_EXTRACT_SCALAR(safe.parse_json(cast(source.json_col as STRING)), '$.updated_at') as TIMESTAMP) as updated_at
   ```

2. **When DATETIME Type is Mandated Downstream**:
   If the downstream table or dbt model strictly requires a `DATETIME` data type, first cast the string to `TIMESTAMP` and then cast the resulting `TIMESTAMP` to `DATETIME`:
   ```sql
   cast(cast(JSON_EXTRACT_SCALAR(safe.parse_json(cast(source.json_col as STRING)), '$.updated_at') as TIMESTAMP) as DATETIME) as updated_at
   ```

3. **Avoid Direct DATETIME Cast on JSON Extractions**:
   - **Incorrect**: `cast(JSON_EXTRACT_SCALAR(...) as DATETIME)` (fails on ISO-8601 strings ending in `'Z'`)
   - **Correct**: `cast(JSON_EXTRACT_SCALAR(...) as TIMESTAMP)` or `cast(cast(JSON_EXTRACT_SCALAR(...) as TIMESTAMP) as DATETIME)`

## 6. BigQuery STRUCT (RECORD) vs. JSON Columns
In Snowflake, both object maps and JSON are typically stored as `VARIANT` or `OBJECT` and accessed using colon notation (`col:field` or `col:sub:field`).

In BigQuery:
- Ingested tables (e.g. from MongoDB, Iceberg, or Datastream) often define nested objects as native BigQuery **`STRUCT`** (RECORD) types.
- Raw API tables often store semi-structured data as native **`JSON`** or stringified JSON (`STRING`).

### The Runtime Error
If a table column is a `STRUCT` or `ARRAY<STRUCT<...>>`, calling `JSON_VALUE()` directly on it causes the following BigQuery query failure:
```text
No matching signature for function JSON_VALUE
  Argument types: ARRAY<STRUCT<error STRING, code STRING, state STRING>>, STRING
  Signature: JSON_VALUE(STRING, [STRING])
    Argument 1: Unable to coerce type ARRAY<STRUCT<...>> to expected type STRING
  Signature: JSON_VALUE(JSON, [STRING])
    Argument 1: Unable to coerce type ARRAY<STRUCT<...>> to expected type JSON
```
In BigQuery, `CAST(struct AS JSON)` is also not supported (`Unable to coerce type STRUCT to expected type JSON`).

### Standard Patterns

1. **For BigQuery STRUCT Columns**:
   Use direct dot notation without `json_value`:
   ```sql
   -- Direct struct field access
   source.struct_col.name as struct_name,
   obj_col.id as obj_id,
   obj_col.name as obj_name,
   obj_col.type as obj_type,

   -- Struct field with explicit numeric cast
   cast(source.struct_col.count as NUMERIC) as struct_count,

   -- Nested struct field access
   source.struct_col.nested.flag as nested_flag,
   ```

2. **For BigQuery JSON Columns**:
   Use `json_value()` with standard JSONPath (Option A with double quotes for escaped characters/spaces):
   ```sql
   -- Standard field
   json_value(json_col, '$.created_date') as created_date,

   -- Field with space / special characters
   json_value(json_col, '$."Field Name"') as field_name,
   cast(json_value(json_col, '$."Total Value"') as FLOAT64) as total_value,
   ```

3. **For `ARRAY<STRUCT>` or `STRUCT` Columns**:
   If a column is typed as a native BigQuery `ARRAY<STRUCT<...>>` (arrays containing nested structs `[STRUCT(...)]`):

   - **Recommended: Native BigQuery Indexing (`SAFE_OFFSET`)**:
     Directly access the array element using `[SAFE_OFFSET(0)]` and the struct field using dot notation `.field`. This avoids JSON serialization overhead and handles empty arrays safely:
     ```sql
     -- Native BigQuery element & struct access (strongly typed, no JSON serialization)
     source.col[SAFE_OFFSET(0)].field as field,
     source.col[SAFE_OFFSET(0)].is_primary as is_primary,
     source.col[SAFE_OFFSET(0)].code as code
     ```

   - **Alternative: JSONPath via `TO_JSON`**:
     If evaluating dynamic JSONPath expressions, you **must** wrap the array in `to_json(...)` because `JSON_VALUE()` only accepts `STRING` or `JSON`:
     ```sql
     -- Correct: Wraps ARRAY<STRUCT> with to_json(...)
     json_value(to_json(source.col), '$[0].field') as field
     ```

   > **Note:** Calling `json_value(source.col, '$[0].field')` directly on an `ARRAY<STRUCT>` column without `to_json(...)` will fail with:
   > ```text
   > No matching signature for function JSON_VALUE
   >   Argument types: ARRAY<STRUCT<...>>, STRING
   >   Signature: JSON_VALUE(STRING, [STRING])
   >   Signature: JSON_VALUE(JSON, [STRING])
   > ```
   > Either replace with `source.col[SAFE_OFFSET(0)].field` or wrap with `to_json(source.col)`.

## 7. Snowflake Bracket Notation & BQMS `error_unimplemented`
In Snowflake, bracket indexing is overloaded for both array indexing (`arr[0]`) and object attribute access (`col['field']`).

### The BQMS Translation Defect
When BQMS encounters Snowflake object bracket notation `col['field']`, it attempts to interpret it as an array lookup opcode (`JsonFieldJsonNumericAsJsonOpcode`), causing translation failure and emitting:
```sql
substr(string(error_unimplemented(/* No implementation for JsonFieldJsonNumericAsJsonOpcode in BigQuery. */ source.COL, 'field')), 1, 16777216)
```
or for numeric/timestamp types:
```sql
cast(lax_float64(error_unimplemented(/* No implementation for JsonFieldJsonNumericAsJsonOpcode in BigQuery. */ source.COL, 'count')) as BIGNUMERIC)
cast(json_value(error_unimplemented(/* No implementation for JsonFieldJsonNumericAsJsonOpcode in BigQuery. */ source.COL, 'created')) as TIMESTAMP)
```
In BigQuery, `error_unimplemented` is not a valid SQL function and will fail immediately at query execution time.

### Automated Mitigation & Patterns
1. **Pre-processing (Snowflake -> Clean Snowflake)**:
   The migration pipeline rewrites bracket notation on identifiers `col['field']` to colon notation `col:field` prior to calling BQMS.
2. **Post-processing (BigQuery Cleanup)**:
   Any residual `error_unimplemented` functions are automatically cleaned:
   - For BigQuery **STRUCT** columns (e.g. `*_STRUCT`, `STRUCT_COL`, `*_RECORD`, `RECORD_COL`, `*_OBJ`, `OBJ_COL`):
     ```sql
     -- String
     cast(source.record_col.status as STRING) as status
     -- Numeric
     cast(source.obj_col.count as NUMERIC) as item_count
     -- Timestamp
     cast(source.obj_col.created_at as TIMESTAMP) as created_at
     -- Raw subfield / array
     source.record_col.tags as tags
     ```
   - For BigQuery **JSON** columns:
     ```sql
     json_value(source.json_col, '$.field')
     ```

## 8. BQMS 16MB String Wrappers & `STRING()` Function Signature

### The Runtime Error
```text
No matching signature for function STRING
  Argument types: STRING
  Signature: STRING(TIMESTAMP, [STRING])
    Argument 1: Unable to coerce type STRING to expected type TIMESTAMP
  Signature: STRING(DATE)
  Signature: STRING(TIME)
  Signature: STRING(DATETIME)
  Signature: STRING(JSON)
    Argument 1: Unable to coerce type STRING to expected type JSON
```

### Root Cause
BQMS translates Snowflake `::varchar` / `::text` (which have a 16MB maximum length in Snowflake) into length-limiting wrappers:
```sql
substr(string(col), 1, 16777216)
```
In BigQuery Standard SQL, `STRING()` is a type constructor specifically for temporal and JSON types (`TIMESTAMP`, `DATE`, `TIME`, `DATETIME`, `JSON`). BigQuery has no `STRING(STRING)` signature. When `col` is already a `STRING` (such as a CTE column, extracted struct field, or string scalar), calling `string(col)` throws a signature mismatch error.

### Rule & Pattern
Always replace `substr(string(col), 1, 16777216)` with clean BigQuery casting:
```sql
-- Incorrect:
substr(string(col_name), 1, 16777216) as col_name

-- Correct:
cast(col_name as STRING) as col_name
```
