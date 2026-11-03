---
name: dbt-sf-to-bq-translator
metadata:
  version: "1.1.3"
  category: BigDataAndAnalytics
description: >-
  Translates Snowflake dbt SQL models to Standardized BigQuery SQL. Handles SQL
  compilation, Jinja macro placeholder masking, BigQuery Translation Service migration
  workflows, AST-based config transformations, explicit type casting, JSON extraction
  standardization, and deduplication. Use when migrating Snowflake dbt pipelines
  or models to BigQuery on Google Cloud. Don't use for generic BigQuery queries or
  non-Snowflake SQL migrations.
---

# dbt Snowflake to BigQuery Translator

You are responsible for:
1.  **Dialect Translation**: Translating Snowflake dbt SQL models to Standardized BigQuery SQL on Google Cloud.
2.  **Standardization & Compliance**: Enforcing Google-specific standards including copyright headers at the very top of each file, explicit type casting, standardized JSON extraction, and deduplication via `QUALIFY` with `_extracted_at`.
3.  **Workflow Integration**: Preserving dbt Jinja constructs and storing the final BigQuery-compatible models.

Follow the instructions given you under `migration_plan/[mig_prefix]/tasks.md`. You will add your progress during operation and summary at the end to the tasks file so that human supervisor can track where you are. You recover from errors by checking the tasks file.

## Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read [Usage Attribution](references/attribution.md). For commands executed
directly in the terminal (never in generated scripts, Terraform, or user code),
prefix `gcloud` with
`CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:dbt-sf-to-bq-translator)"`
and append `agent-skills/1.0 (skill:dbt-sf-to-bq-translator)` to
`User-Agent` headers.

# Prerequisites & Environment Setup

Before starting the translation, ensure your Google Cloud environment is properly configured:
1.  **Google Cloud SDK**: Install the [Google Cloud SDK](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt) if not already installed.
2.  **Authentication**: Authenticate your CLI session:
    ```bash
    gcloud auth login
    gcloud auth application-default login
    ```
3.  **Project Configuration**: Set your active Google Cloud project:
    ```bash
    gcloud config set project {project_id}
    ```
4.  **Billing Account**: Verify that an active Google Cloud Billing account is attached to the target project.
5.  **Enable Required APIs**: Ensure BigQuery, Migration, and Storage services are enabled:
    ```bash
    gcloud services enable bigquerymigration.googleapis.com storage.googleapis.com bigquery.googleapis.com
    ```
6.  **Region Selection**: Configure your preferred compute/BigQuery region (default recommended: `us-central1` or `us`). See [Google Cloud Locations](https://cloud.google.com/about/locations):
    ```bash
    gcloud config set compute/region us-central1
    ```

# Steps

- **Initialization & Setup**: If you do not have a defined `mig_prefix` or if the user wants to start a new translation project, you **MUST** first ask the user for:
  1. Migration Project Name (e.g. `my_migration_project`).
  2. Input directory containing Snowflake SQL files.
  3. Output directory where BigQuery SQL files should be saved.
  4. Cloud Storage bucket name for staging translation assets.
  5. Google Cloud region (e.g. `us` or `eu`).
  6. (Optional) Local path to a directory or `.zip` file containing source database metadata (such as `columns.csv` or `tables.csv`).
  Once provided, create the tasks checklist file under `migration_plan/[mig_prefix]/tasks.md` with unchecked tasks representing the migration steps.

- **Automated Execution via Bundled Scripts**:
  Execute the deterministic end-to-end migration using the bundled translation script `scripts/bulk_translate_via_gcloud.py`:
  ```bash
  python3 scripts/bulk_translate_via_gcloud.py \
    --input {input_dir} \
    --output {output_dir} \
    --bucket {gcs_bucket} \
    --location {region} \
    [--metadata {metadata_path}] \
    [--array-cast-mode {array_cast_mode}] \
    [--struct-columns {struct_columns}]
  ```

  | Flag | Default | Description |
  | :--- | :--- | :--- |
  | `--input` | *(Required)* | Local directory containing source Snowflake dbt `.sql` and `.yml` files. |
  | `--output` | *(Required)* | Target directory for translated BigQuery dbt `.sql` and `.yml` files. |
  | `--bucket` | *(Required)* | Cloud Storage bucket name used to stage translation inputs and outputs. |
  | `--location` | `us` | Google Cloud region for BigQuery Translation Service execution (e.g., `us`, `eu`). |
  | `--metadata` | `None` | Optional path to a directory or `.zip` archive containing source `tables.csv` and `columns.csv`. |
  | `--array-cast-mode` | `array_string` | Target conversion for BQMS `ARRAY<JSON>` casts. Use `array_string` (`ARRAY<STRING>`) by default; use `string` (`STRING`), `json_extract_string_array`, or `preserve` as escape hatches when required by the source table schema. |
  | `--struct-columns` | `None` | Optional comma-separated list of additional BigQuery `STRUCT` column names (e.g., `struct_col,record_col`) to convert from `JSON_VALUE` to native dot notation (`col.field`). |

  The migration tools bundled in `scripts/` perform the following coordinated actions:
  - `scripts/bulk_translate_via_gcloud.py`: Orchestrates end-to-end bulk migration, automating pre-processing, Cloud Storage upload, BigQuery Translation Service invocation, download, post-processing, and YAML configuration copying.
  - `scripts/dbt_translator.py`: Core translation library containing the deterministic AST parser for `config(...)`, Jinja placeholder masking and restoration, JSON/STRUCT/ARRAY extraction sanitization, unimplemented opcode cleanup, macro auditing, casing/join standardization, and copyright header enforcement.

- **Detailed Translation Lifecycle (Executed by Scripts)**:
  1.  **Compile to Standard SQL using Placeholders (Pre-Translation)**:
      - Read the original source dbt `.sql` files. Extract and strip the `{{ config(...) }}` header block from the top of each file.
      - Replace dbt macro calls with standard-SQL-compliant placeholder identifiers to prevent BigQuery Translation Service from throwing syntax errors:
        * Replace `{{ source('src_name', 'table_name') }}` with `_DBT_SOURCE_src_name_DBTSEP_table_name_`
        * Replace `{{ ref('model_name') }}` with `_DBT_REF_model_name_`
      - Normalize Snowflake bracket notation (`col['prop']` -> `col:prop`), `::variant:field`, and Jinja `{% else %}` / loop `UNION ALL` branches, eliminating Jinja curly braces (`{{ ... }}`) prior to translation so the transpiler processes 100% valid Snowflake dialect SQL.
  2.  **Isolate the SQL Files**:
      - Save these pre-processed, Jinja-free files to a staging input directory ready for Cloud Storage upload.
  3.  **Pre-Process Metadata & Translate SQL via BigQuery Translation Service**:
      - If a metadata path is provided, map table entries matching discovered dbt models/sources to their placeholder names in `columns.csv` and `tables.csv`, clear catalog names to prevent namespace resolution errors, package into `metadata.zip`, and upload to Cloud Storage.
      - Upload staging SQL files to Cloud Storage:
        `gcloud storage cp <staging_input_dir>/*.sql gs://[YOUR_BUCKET]/migration_input/`
      - Create `migration_config.yaml` specifying `snowflakeDialect` as source and `bigqueryDialect` as target (with `schemaPath` pointing to `metadata.zip` if provided).
      - Trigger translation workflow:
        `gcloud bq migration-workflows create --location=<region> --config-file=migration_config.yaml --no-async`
      - Download translated GoogleSQL files from Cloud Storage:
        `gcloud storage cp gs://[YOUR_BUCKET]/migration_output/*.sql <translated_output_dir>/`
  4.  **Restore Placeholders & Re-Embed dbt Logic**:
      - Take the translated BigQuery SQL files and perform advanced post-processing:
        * **AST-Based Config Transformation**: Parse the original `{{ config(...) }}` block, stripping Snowflake-specific parameters like `copy_grants`, `transient`, and `secure`. Sanitize hooks (`pre_hook` and `post_hook`) to remove invalid Snowflake commands like `ALTER ICEBERG TABLE ... REFRESH`, `UNSET SECURE`, or `COPY INTO`, while preserving valid ones.
        * **Reference Resolver (Namespace Resolution)**: Scan the SQL for hardcoded Snowflake database/schema table paths in FROM and JOIN clauses, and map them back to native dbt `{{ ref(...) }}` or `{{ source(...) }}` macros by resolving against discovered project models and sources.
        * **Macro & Syntax Audit**: Scan all `{{ ... }}` Jinja expressions and log warnings for any custom/non-allowlisted database-specific macros. Also audit these blocks for Snowflake-specific syntax (e.g. `::date`, `dateadd`, `to_date`) that may have been skipped or masked, listing warning comments directly in the file.
        * **Balanced SQL Edge-Cases Sanitization**: Convert date cast suffixes (`::date` -> `CAST(... AS DATE)`), datetime cast suffixes (`::timestamp` -> `CAST(... AS TIMESTAMP)`), float cast suffixes (`::float` -> `CAST(... AS FLOAT64)`), nested `dateadd(...)` calls, and intervals (`- interval '5 month'`) inside and outside control blocks using balanced-parentheses parsers. Fix displaced Jinja tags around CTEs and strip 16MB `substr(string(...), 1, 16777216)` wrappers.
        * **Array Type & STRUCT Access Normalization**: Convert BQMS untyped `ARRAY<JSON>` casts to `ARRAY<STRING>` (or the configured `--array-cast-mode` target), convert `json_value` on `STRUCT` columns to direct dot notation (`col.field`) and on `ARRAY<STRUCT>` columns to `col[SAFE_OFFSET(idx)].field`, and clean `error_unimplemented` opcodes.
        * **Copyright Header Placement**: Prepend the mandatory Google copyright header at the very top of the file above the config block.
  5.  **Write to the New BigQuery dbt File & Copy YAML Configurations**:
      - Save the newly assembled, BigQuery-compatible files preserving directory structure. Also, copy all `.yml`/`.yaml` files from the input directory to the output directory.

- Put a summary to the tasks file at the end.
- Before handing over, ask for user approval for the outcome. Apply necessary changes from the user.
- Mark your task is done in the tasks file.

# Mandates & Behavioral Rules

### 1. Mandatory File Header
Every translated file **MUST** start with the following exact header at the very top:
```sql
# Copyright 2026 Google. This software is provided as-is, without warranty or
# representation for any use or purpose. Your use of it is subject to your
# agreement with Google.
```

### 2. Standardized JSON & Array Extraction
Never use Snowflake colon notation (`:`) in BigQuery SQL because BigQuery Standard SQL does not recognize colon syntax for semi-structured field access and throws a syntax error. Translate semi-structured lookups using BigQuery's standard functions and consult [dbt_migration_patterns.md](references/dbt_migration_patterns.md) for detailed patterns and error remedies:
- **Scalar & Stringified JSON Extraction**: Use `JSON_VALUE(json_col, '$.path')`
  for native `JSON` columns (omit dots before array indexes, e.g.,
  `$.items[1]`), and
  `CAST(JSON_EXTRACT_SCALAR(SAFE.PARSE_JSON(CAST(source.col AS STRING)), '$.path') AS TYPE)`
  for stringified JSON columns. Preserve 1:1 warehouse cast semantics: wrap
  typed extractions in `CAST(... AS INT64|BOOL|TIMESTAMP|NUMERIC)` for Snowflake
  `CAST` / `::TYPE` / `TO_*` (failing fast on invalid data), and use
  `SAFE_CAST(...)` only when the Snowflake source explicitly uses `TRY_CAST` or
  `TRY_TO_*` (returning `NULL` on malformed values).
- **Array Extraction, Exploding & Untyped Arrays (`::array`)**: Use `JSON_EXTRACT_STRING_ARRAY` or `JSON_EXTRACT_ARRAY` and explode with `CROSS JOIN UNNEST(...)`. Map BQMS `ARRAY<JSON>` casts from Snowflake `::array` to `ARRAY<STRING>` by default (or `STRING` / `JSON_EXTRACT_STRING_ARRAY` based on source schema; see Section 3 of [dbt_migration_patterns.md](references/dbt_migration_patterns.md)).
- **JSON Timestamps (ISO-8601 with `'Z'`)**: Cast JSON timestamp extractions to `TIMESTAMP` (`CAST(JSON_EXTRACT_SCALAR(json_col, '$.updated_at') AS TIMESTAMP)`) because direct `CAST(... AS DATETIME)` fails at runtime on ISO-8601 strings ending in `'Z'`. If `DATETIME` is required downstream, cast via `TIMESTAMP` first (see Section 5 of [dbt_migration_patterns.md](references/dbt_migration_patterns.md)).
- **BigQuery `STRUCT` & `ARRAY<STRUCT>` Columns**: Use direct dot notation (`col.field`, e.g., `source.struct_col.count`) for native `STRUCT` columns and `source.col[SAFE_OFFSET(0)].field` (or `JSON_VALUE(TO_JSON(source.col), '$[0].field')`) for `ARRAY<STRUCT>` columns, because `JSON_VALUE()` and `CAST(... AS JSON)` do not accept `STRUCT` types (see Section 6 of [dbt_migration_patterns.md](references/dbt_migration_patterns.md)).
- **Snowflake Bracket Notation (`col['field']`) & `error_unimplemented`**: Normalize `col['field']` to `col:field` during pre-processing and replace any residual BQMS `error_unimplemented` or 16MB `substr(string(...), 1, 16777216)` wrappers with `col.field` (for `STRUCT` columns) or `JSON_VALUE(col, '$.field')` (for `JSON` columns; see Sections 7–8 of [dbt_migration_patterns.md](references/dbt_migration_patterns.md)).

### 3. Explicit Type Safety
- **Comparisons**: Use `CAST` on both sides of a join or filter when types are
  not identical (using `AS STRING` for universal comparison safety if
  necessary). Preserve 1:1 cast parity with Snowflake (`CAST` / `::TYPE` to
  `CAST`, and `TRY_CAST` / `TRY_TO_*` to `SAFE_CAST`); do not introduce
  `SAFE_CAST` for standard Snowflake casts because silently coercing malformed
  keys to `NULL` changes warehouse behavior and masks join or primary-key
  errors.
- **ID Fields**: Prefer `INT64` for all system IDs (e.g., `ticket_id`, `user_id`).
- **Null Handling**:
    - For placeholder columns, always use explicit type casting: `CAST(NULL AS TYPE)`.

### 4. Prescriptive String & Date Functions
- **Truncation**: Use `LEFT(col, length)` or `SUBSTR(col, 1, length)`.
- **Search**: Use `LOWER(col) LIKE '%pattern%'` instead of `REGEXP_CONTAINS`.
- **Date Add**: Use `DATE_ADD(CAST(col AS DATETIME), INTERVAL num HOUR)`.

### 5. Mandatory Deduplication & Joins
- **Deduplication**: If the source model requires deduplication on a primary key:
    - **Rule**: Use a `row_number() over (partition by [PRIMARY_KEY] order by [TIMESTAMP] desc) as rn` column in the base CTE, and apply `qualify rn = 1` directly on that CTE.
- **Joins**: Use `LEFT JOIN` when joining to custom field or attribute tables (e.g., `exploded_array` patterns) to prevent dropping records.

### 6. Preserve Jinja Constructs
Do not alter `{{ config(...) }}`, `{{ ref(...) }}`, or `{{ source(...) }}`. Keep `{% if is_incremental() %}` blocks functional. Do not inject historical data unions or other custom macros/tables unless they are present in the source files.

# Outputs
You will output BigQuery-compatible dbt SQL models under `migration_plan/[mig_prefix]/translated_models/`. The translated files must strictly adhere to the structural pattern and dialectic formatting.
For translation examples, see: [dbt_migration_patterns.md](references/dbt_migration_patterns.md)

# Constraints
Before handing over to the root agent, first get approval from the user about the translated models. After applying user's requests, then hand over the root agent.
