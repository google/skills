# Standardized dbt Dialect Migration Patterns (Snowflake to BigQuery)

This reference guide provides "Before vs. After" code patterns that match the target code standard for BigQuery curated models.

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
        SAFE_CAST(JSON_EXTRACT_SCALAR(a.data, '$.id') AS INT64) as primary_id,
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
        SAFE_CAST(JSON_EXTRACT_SCALAR(json_data, '$.field_name') AS STRING) as field_name,
        SAFE_CAST(JSON_EXTRACT_SCALAR(json_data, '$.is_active') AS BOOL) as is_active,
        _extracted_at
    FROM raw_json
)
SELECT * FROM transform_layer
```

## 2. Comparison Patterns

| Feature | Snowflake Source | Standardized BigQuery Target |
| :--- | :--- | :--- |
| **JSON Path** | `data:user:id::int` | `SAFE_CAST(JSON_EXTRACT_SCALAR(data, '$.user.id') AS INT64)` |
| **Null Strings** | `data:status::string` | `SAFE_CAST(JSON_EXTRACT_SCALAR(data, '$.status') AS STRING)` |
| **Boolean** | `data:active::boolean` | `SAFE_CAST(JSON_EXTRACT_SCALAR(data, '$.active') AS BOOL)` |
| **Truncation** | `LEFT(comment, 2000)` | `SUBSTR(comment, 1, 2000)` |
| **Search** | `comment LIKE '%urgent%'` | `LOWER(comment) LIKE '%urgent%'` |
| **Array Explode** | `LATERAL FLATTEN(input => data:tags)` | `CROSS JOIN UNNEST(JSON_EXTRACT_ARRAY(data, '$.tags'))` |
| **Date Add** | `DATEADD(hour, 1, date)` | `DATE_ADD(SAFE_CAST(date AS DATETIME), INTERVAL 1 HOUR)` |
| **Window Alias** | `SELECT id, ROW_NUMBER() OVER(PARTITION BY id...)` | `SELECT SAFE_CAST(JSON_EXTRACT_SCALAR(data, '$.id') AS INT64) as id, ROW_NUMBER() OVER(PARTITION BY SAFE_CAST(JSON_EXTRACT_SCALAR(data, '$.id') AS INT64)...)` |

## 3. Post-Hook Standards
When updating tables in a `post_hook`, always use explicit type casting in the `WHERE` clause:

**Incorrect**:
`where t.ticket_id = stage.id`

**Correct**:
`where SAFE_CAST(t.ticket_id AS STRING) = SAFE_CAST(stage.id AS STRING)`
