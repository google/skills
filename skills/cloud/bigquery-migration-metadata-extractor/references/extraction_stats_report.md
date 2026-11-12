# Post-Extraction Verification & Statistics Reporting Specification

After an extraction completes (or whenever inspecting an extracted metadata or
query-log archive), run the extraction statistics script based on
`assets/extraction_stats_template.py` and print the crucial extraction summary
metrics to the user.

## Contents

-   [1. Prerequisites and dependencies][s1]: Lines 15-29
-   [2. Agent workflow and extension points][s2]: Lines 30-73
-   [3. Crucial Extracted Data to Present to the User][s3]: Lines 74-127
-   [4. Example Extraction Report][s4]: Lines 128-183

## 1. Prerequisites and dependencies

The script uses only the Python 3.9+ standard library (no third-party `pip`
packages required) and requires the Google Cloud SDK when reading archives
directly from `gs://` URIs:

```bash
# Authenticate Google Cloud SDK for gs:// URIs:
gcloud auth login && gcloud auth application-default login
```

*   **Google Cloud CLI (`gcloud`)**: Ensure the
    [Google Cloud CLI][gcloud_install] is installed and authenticated when
    inspecting extracted `.zip` archives on Cloud Storage (`gs://`).

## 2. Agent workflow and extension points

1.  **Copy the Asset Template**: Copy `assets/extraction_stats_template.py` from
    the skill directory (`<SKILL_DIR>`, the directory that contains `SKILL.md`)
    into your working directory:

    ```bash
    cp <SKILL_DIR>/assets/extraction_stats_template.py ./extraction_stats.py
    ```

2.  **Conditionally Customize Extension Points**: Run the copy as-is, or modify
    the marked `# CUSTOMIZE:` sections when needed (`# DEFAULT SCAFFOLDING`
    sections can be kept unchanged):

    *   **Custom Schema & Table Filtering (`# CUSTOMIZE: Custom Schema & Table
        Filtering`)**: Update `_EXCLUDED_SYSTEM_SCHEMAS` or
        `_should_include_schema()` if you need to exclude specific staging,
        scratch, or system schemas (e.g., `STAGING_TMP`) from migration totals.
    *   **Complex Data Type Classification (`# CUSTOMIZE: Complex Data Type
        Classification`)**: Update `_classify_special_data_types()` to flag
        additional custom data types that require special casting during
        downstream Parquet export or BigQuery SQL translation.
    *   **Custom Telemetry & Archive Validation Thresholds (`# CUSTOMIZE: Custom
        Telemetry & Archive Validation Thresholds`)**: Adjust
        `_MIN_VALID_ZIP_BYTES` or telemetry validation logic in
        `analyze_zip_archive()`.
    *   **Report Formatting & Output Channels (`# CUSTOMIZE: Report Formatting &
        Output Channels`)**: Customize `format_stats_report()` to alter table
        columns or add custom summary sections.

3.  **Execute the Script After Extraction**:

    ```bash
    # 1. Inspect a GCS extraction output directory or ZIP URI directly:
    python3 ./extraction_stats.py \
        --input "gs://{bucket}/snowflake_metadata/"

    # 2. Inspect a local metadata ZIP and write JSON + Markdown reports:
    python3 ./extraction_stats.py \
        --input ./dwh-migration-snowflake-metadata.zip \
        --output-json ./extraction_stats.json \
        --output-markdown ./extraction_stats.md
    ```

## 3. Crucial Extracted Data to Present to the User

After running `./extraction_stats.py`, present the following extraction metrics:

1.  **Archive Health & Run Telemetry**:
    *   Archive name, byte size (confirming `> 22` bytes so it is not an
        incomplete GCS NIO ZipFS placeholder), and file count.
    *   Extractor `overallStatus` (`SUCCESS`), task execution counts
        (`SUCCEEDED` / `SKIPPED` / `FAILED`), source `connector`, `host`, and
        compute `warehouse` from the run that wrote the archive. The
        `dumper-telemetry.jsonl` file accumulates every run made on the same
        machine, so the script picks the latest run (by start time, with
        offsets applied) whose connector matches
        `compilerworks-arguments.txt`.
2.  **Catalog Object Inventory Counts**:
    *   **Databases**: Count and names (e.g., `SALES_DB`).
    *   **Schemas**: Total schemas discovered vs. active schemas containing
        objects (e.g., `RAW_POS`, `RAW_CUSTOMER`, `HARMONIZED`, `ANALYTICS`).
    *   **Base Tables**: Count of physical tables (`TableType = BASE TABLE`).
    *   **Views (with DDL)**: Count of extracted view definitions from
        `views-au.csv` ready for BQMS SQL translation.
    *   **Columns, Functions & External Tables**: Total columns across all
        relations broken down into base-table columns (`base_table_columns`) and
        view columns (`view_columns`), plus counts of UDFs/stored procedures
        (`functions-au.csv`, `function_info.csv`, `dbc.FunctionsV.csv`) and
        external stage tables (`external_tables.csv`,
        `svv_external_tables.csv`).
    *   **Query History Logs** *(for `snowflake-logs` / query log archives)*:
        Number of query log partitions (`query_history*.csv`, `querytext*.csv`,
        `dwhassessment_*.csv`) and total historical queries extracted.
3.  **Total Data Volume & Per-Schema / Per-Table Breakdown**:
    *   Aggregate **Total Base Table Rows** (e.g., `3,600` rows) and **Total
        Base Table Bytes** (e.g., `227,840 B (222.50 KB)`).
    *   Per-schema breakdown table (`Schema`, `Base Tables`, `Views`, `Rows`,
        `Size`) and the Base Tables inventory (`Schema.Table`, `Rows`, `Size`,
        `Columns`, `Clustering Key`).
    *   For `bigquery` connector archives, the script reads `tables.jsonl`,
        counts top-level columns only, and shows `N/A` for rows and sizes
        because that connector does not record them (even when `tables.jsonl`
        is empty). `VIEW` and `MATERIALIZED_VIEW` entries count as views, with
        `viewQuery` as their DDL; `EXTERNAL` entries count as external tables;
        other types such as `SNAPSHOT` are not counted as tables or views.
        The script reads `tables.jsonl` only when the archive's connector (or
        `compilerworks-format.txt`) is `bigquery`, or when the archive names
        neither; `hiveql` archives also contain a `tables.jsonl`, in a
        different layout, which the script does not parse.
4.  **Extracted Views & Column Data Type Distribution**:
    *   List of extracted view names (`Schema.View`) and column data type counts
        (`TEXT`, `NUMBER`, `DATE`, `TIMESTAMP_NTZ`, `ARRAY`, `VARIANT`, etc.),
        highlighting special types (`NUMBER`, `TIMESTAMP_NTZ`, `ARRAY`,
        `VARIANT`, `SUPER`) that require type-safe casting during downstream
        Parquet export and SQL translation
        (`bigquery-migration-sql-translator`).

## 4. Example Extraction Report (Sample Snowflake Database)

```text
================================================================================
  BIGQUERY MIGRATION CLOUD EXTRACTOR - EXTRACTION REPORT
================================================================================

### Archive 1: `dwh-migration-snowflake-metadata.zip`
- **Archive Path / URI**: `gs://example-bucket/snowflake_metadata/dwh-migration-snowflake-metadata.zip`
- **Archive Validation**: VALID (10,559 B (10.31 KB), 13 files)
- **Archive Type**: `CATALOG_METADATA`
- **Extractor Run Status**: `SUCCESS` (Tasks: 12 succeeded, 6 skipped, 0 failed | Version: v1.7.0)
- **Source Connector & Host**: `snowflake` (`myorg-myaccount.snowflakecomputing.com`)
- **Compute Warehouse**: `MIGRATION_WH` (total warehouses in account: 4)
- **Extraction Timestamp**: `2026-08-11T00:54:12.805787467Z`

#### 1. Crucial Extracted Object Summary
| Metric | Count / Value | Details |
| :--- | :--- | :--- |
| **Databases** | 1 | `SALES_DB` |
| **Schemas** | 5 (4 with objects) | `ANALYTICS`, `HARMONIZED`, `PUBLIC`, `RAW_CUSTOMER`, `RAW_POS` |
| **Base Tables** | 8 | Total Rows: **3,600** (227,840 B (222.50 KB)) |
| **Views (with DDL)** | 7 | Ready for BQMS SQL translation |
| **Total Columns** | 214 | 86 in base tables, 128 in views; 8 distinct data types |
| **Functions / Procedures** | 0 | UDFs and stored procedures |
| **External Tables** | 0 | External stage tables |

#### 2. Per-Schema Object Breakdown
| Schema | Base Tables | Views | Total Base Rows | Total Base Size |
| :--- | ---: | ---: | ---: | ---: |
| `RAW_POS` | 8 | 0 | 3,600 | 227,840 B (222.50 KB) |
| `ANALYTICS` | 0 | 3 | 0 | 0 B |
| `HARMONIZED` | 0 | 3 | 0 | 0 B |
| `RAW_CUSTOMER` | 0 | 1 | 0 | 0 B |
| `PUBLIC` | 0 | 0 | 0 | 0 B |

#### 3. Base Tables Inventory (Showing 8 of 8)
| # | Schema.Table | Rows | Size | Columns | Clustering Key |
| ---: | :--- | ---: | ---: | ---: | :--- |
| 1 | `RAW_POS.COUNTRY` | 800 | 17,920 B (17.50 KB) | 7 | - |
| 2 | `RAW_POS.FRANCHISE` | 700 | 32,256 B (31.50 KB) | 7 | - |
| 3 | `RAW_POS.LOCATION` | 600 | 29,696 B (29.00 KB) | 7 | - |
| 4 | `RAW_POS.MENU` | 500 | 41,472 B (40.50 KB) | 11 | - |
| 5 | `RAW_POS.TRUCK` | 400 | 32,768 B (32.00 KB) | 14 | - |
| 6 | `RAW_POS.ORDER_HEADER` | 300 | 26,624 B (26.00 KB) | 16 | - |
| 7 | `RAW_POS.ORDER_DETAIL` | 200 | 12,288 B (12.00 KB) | 9 | - |
| 8 | `RAW_POS.CUSTOMER_LOYALTY` | 100 | 34,816 B (34.00 KB) | 15 | - |

#### 4. Extracted Views Inventory (7)
`ANALYTICS.CUSTOMER_LOYALTY_METRICS_V`, `ANALYTICS.MENU_V`, `ANALYTICS.ORDERS_V`, `HARMONIZED.CUSTOMER_LOYALTY_METRICS_V`, `HARMONIZED.MENU_V`, `HARMONIZED.ORDERS_V`, `RAW_CUSTOMER.CUSTOMER_LOYALTY`

#### 5. Column Data Type Distribution
- **All Data Types**: `TEXT`: 125, `NUMBER`: 74, `DATE`: 6, `TIMESTAMP_NTZ`: 3, `ARRAY`: 2, `TIME`: 2, `FLOAT`: 1, `VARIANT`: 1
- **Types Flagged for Type-Safe Parquet Cast / Translation**: `NUMBER` (74), `TIMESTAMP_NTZ` (3), `ARRAY` (2), `VARIANT` (1)
================================================================================
```

[gcloud_install]: https://cloud.google.com/sdk/docs/install
[s1]: #1-prerequisites-and-dependencies
[s2]: #2-agent-workflow-and-extension-points
[s3]: #3-crucial-extracted-data-to-present-to-the-user
[s4]: #4-example-extraction-report-sample-snowflake-database
