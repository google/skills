# BigQuery Troubleshooting: Storage Footprint & Billing Models

This reference guide provides root-cause mapping and remediation strategies for
BigQuery storage cost increases, dataset footprint growth, and billing model
transitions. It focuses strictly on BigQuery Managed Storage billable usage
(Logical vs. Physical storage billing models, native tables, partitions, Time
Travel, and Fail-Safe; external data sources and Cloud Storage buckets are
excluded). Each section connects the observed symptom to potential root causes
and points to the corresponding query in `bigquery-observability`.

## Table of Contents

-   [1. 4-Step Diagnostic Funnel](#1-4-step-diagnostic-funnel) (Lines 31-107)
-   [2. Diagnostic Workflows by Symptom & Root Cause](#2-diagnostic-workflows-by-symptom-root-cause)
    (Lines 109-251)
    -   [Scenario 1: Historical Partition Timer Reset (The DML Trap)](#scenario-1-historical-partition-timer-reset-the-dml-trap)
        (Lines 111-138)
    -   [Scenario 2: The Unpartitioned Table Active Trap](#scenario-2-the-unpartitioned-table-active-trap)
        (Lines 140-163)
    -   [Scenario 3: Time Travel & Fail-Safe Churn on Physical Billing](#scenario-3-time-travel-fail-safe-churn-on-physical-billing)
        (Lines 165-191)
    -   [Scenario 4: Deleted Table / Dataset "Phantom Spend" & Long-Term Promotion](#scenario-4-deleted-table-dataset-phantom-spend-long-term-promotion)
        (Lines 193-233)
    -   [Scenario 5: Table Clones and Snapshots Overestimation](#scenario-5-table-clones-and-snapshots-overestimation)
        (Lines 235-251)
-   [3. Execution Limitations & Footguns](#3-execution-limitations-footguns)
    (Lines 253-289)
-   [4. Telemetry & Data Retrieval Reference](#4-telemetry-data-retrieval-reference)
    (Lines 291-308)

## 1. 4-Step Diagnostic Funnel

When investigating storage cost questions (e.g., *"Why did my storage bill
increase?"*, *"Why is storage spend higher than expected?"*):

1.  **Step 1: Context Resolution & Baseline Scan (Gather)**

    *   **Scope Resolution:** Identify the target `project_id`, `region`, and
        dataset scope.
    *   **Time Window & Baseline:** Default to a standard **7-day
        Period-over-Period (PoP)** window comparing the last 7 days against the
        preceding 7 days (`CURRENT_DATE() - 7` to `CURRENT_DATE() - 14`) if
        unspecified; otherwise evaluate the user's requested timeframe against
        its corresponding prior baseline period
        (`INFORMATION_SCHEMA.TABLE_STORAGE_USAGE_TIMELINE` retains 90 days).
    *   **Baseline Scan (Historical Trend vs. Current Snapshot):**
        *   **Billing Trend & Invoice Audit:** Query
            `INFORMATION_SCHEMA.TABLE_STORAGE_USAGE_TIMELINE` as the absolute
            source of truth for historical 7-day PoP / 30-day billing trends
            (calculates daily average GiB across Active vs. Long-Term tiers;
            note that physical Time Travel and Fail-Safe are integrated into
            total active physical usage).
        *   **Physical Breakdown Snapshot:** Query
            `INFORMATION_SCHEMA.TABLE_STORAGE` for a real-time point-in-time
            snapshot providing the detailed breakdown of physical storage
            components (`current_physical_bytes`, `time_travel_physical_bytes`,
            `fail_safe_physical_bytes`, and `deleted` table drain).
    *   **Zero-Row Test & Opt-In Status Check:** If the baseline query returns 0
        rows or fails with an enablement error, STOP. Do not compute aggregates
        over an empty set. Check whether the project has enabled storage
        collection by checking `enable_info_schema_storage` in
        `INFORMATION_SCHEMA.EFFECTIVE_PROJECT_OPTIONS` (see **Telemetry & Data
        Retrieval Reference** below for schema and field definitions):
        *   **If Enabled (`option_value = 'true'`):** Opt-in is active. If 0
            rows returned from `INFORMATION_SCHEMA.TABLE_STORAGE`, verify the
            target region and confirm that datasets exist in that location.
        *   **If Not Enabled (0 rows returned or `option_value != 'true'`):**
            Storage metrics collection is disabled. Inform the user to enable it
            by setting the DDL option
            `region-{location}.enable_info_schema_storage = TRUE` (via `ALTER
            PROJECT` or `ALTER ORGANIZATION`).
        *   **Zero-Opt-In Fallback:** Because full historical
            `INFORMATION_SCHEMA.TABLE_STORAGE` data takes ~24 hours to populate
            post-enablement, conduct immediate triage using
            `INFORMATION_SCHEMA.PARTITIONS` and
            `INFORMATION_SCHEMA.SCHEMATA_OPTIONS` (which report partition byte
            sizes and dataset billing models without requiring
            `enable_info_schema_storage` opt-in).
    *   **Report Factually:** State the baseline vs. current storage volume and
        percentage growth before diagnosing root causes.

2.  **Step 2: Vector Decomposition & Anomaly Isolation (Isolate)**

    *   Determine if growth stems from:
        *   **Active Logical Growth:** Mature data failing to reach 90 unmutated
            days (unpartitioned table trap or unscoped DML timer resets).
        *   **Physical Retention Churn:** Time Travel and Fail-Safe blocks
            accumulating from daily `WRITE_TRUNCATE` or batch overwrites.
        *   **Dropped Table Fail-Safe Drain:** Deleted tables continuing to
            incur physical Fail-Safe charges during the 7-day drain period.

3.  **Step 3: Event & Configuration Correlation (Explain Root Cause)**

    *   Correlate the isolated sub-vector with lifecycle and DDL events:
        *   Query `INFORMATION_SCHEMA.SCHEMATA_OPTIONS` for billing model
            switches (between `LOGICAL` and `PHYSICAL`) or TTL changes.
        *   Query `INFORMATION_SCHEMA.PARTITIONS` for recent
            `last_modified_time` updates on historical partitions.
        *   Query `INFORMATION_SCHEMA.TABLE_STORAGE` with `WHERE deleted = TRUE`
            to inspect deleted tables actively draining Fail-Safe bytes.

4.  **Step 4: Actionable Remediation & Customer Levers (Remediate)**

    *   Deliver concrete, immediate mitigation levers (e.g. reducing Time Travel
        to 48 hours, partitioning unpartitioned tables, isolating mutable
        columns, or switching billing models) as detailed in the matching
        scenario below.

## 2. Diagnostic Workflows by Symptom & Root Cause

### Scenario 1: Historical Partition Timer Reset (The DML Trap)

*   **When to Use / Symptoms:** An abrupt doubling of storage spend on
    historical tables with zero data volume additions.
*   **Potential Root Causes:** BigQuery automatically discounts storage by 50%
    (Long-Term pricing) when a partition has not been modified for 90
    consecutive days. If an unscoped `UPDATE`, `DELETE`, or `MERGE` query
    touches even a single row in an old partition, that partition's
    `last_modified_time` updates to current timestamp, instantly resetting the
    90-day timer back to day zero and reverting to full-price Active storage.
*   **Key Telemetry & Tables:**
    *   **Table:** `INFORMATION_SCHEMA.PARTITIONS`.
    *   **Filters:** `table_name = 'TARGET_TABLE'`, `last_modified_time >=
        TIMESTAMP_SUB(...)`.
    *   **Key Fields:** `partition_id`, `last_modified_time`,
        `total_logical_bytes`, `storage_tier` (`ACTIVE`, `LONG_TERM`).
*   **Diagnostic Procedure & Telemetry:** Inspect
    `INFORMATION_SCHEMA.PARTITIONS` for partitions older than 90 days where
    `last_modified_time` was updated within the last 7 days (following guidance
    in **Telemetry & Data Retrieval Reference** below). Sort by
    `total_logical_bytes` descending to isolate high-impact tables.
*   **Remediation & Actions:**
    *   Add partition pruning predicates (e.g., `WHERE _PARTITIONDATE >=
        DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)`) to all recurring ETL
        pipelines.
    *   Isolate frequently mutated columns (e.g., `status`, `updated_at`) into a
        separate unpartitioned lookup table so historical fact partitions remain
        unmutated.

### Scenario 2: The Unpartitioned Table Active Trap

*   **When to Use / Symptoms:** Multi-year-old historical datasets remain billed
    at 100% Active rates with 0% Long-Term discount.
*   **Potential Root Causes:** Unpartitioned tables track a single table-level
    `last_modified_time`. When daily ETL appends or inserts new rows, BigQuery
    updates the timestamp for the entire table. As a result, no historical data
    ever reaches 90 unmutated days.
*   **Key Telemetry & Tables:**
    *   **Table:** `INFORMATION_SCHEMA.TABLE_STORAGE`.
    *   **Filters:** `creation_time < TIMESTAMP_SUB(CURRENT_TIMESTAMP(),
        INTERVAL 90 DAY)`.
    *   **Key Fields:** `table_name`, `active_logical_bytes`,
        `long_term_logical_bytes`.
*   **Diagnostic Procedure & Telemetry:** Inspect
    `INFORMATION_SCHEMA.TABLE_STORAGE` for mature tables where `creation_time`
    is >90 days old (following guidance in **Telemetry & Data Retrieval
    Reference** below). Flag tables where `long_term_logical_bytes = 0` and
    `active_logical_bytes > 0`.
*   **Remediation & Actions:**
    *   Partition the table by ingestion time or date/timestamp (`CREATE TABLE
        ... PARTITION BY DATE(event_timestamp)`).
    *   Once partitioned, all partitions older than 90 days immediately drop to
        the 50% discounted Long-Term rate.

### Scenario 3: Time Travel & Fail-Safe Churn on Physical Billing

*   **When to Use / Symptoms:** Physical storage costs are significantly higher
    than logical storage despite good data compression.
*   **Potential Root Causes:** Under Physical storage billing, billable storage
    includes active data plus **Time Travel** (2–7 days) and **Fail-Safe** (7
    days non-configurable). If the workload runs daily `WRITE_TRUNCATE`,
    `CREATE OR REPLACE TABLE`, or heavy batch updates, replaced physical blocks
    accumulate in Time Travel and Fail-Safe billed at active physical rates.
*   **Key Telemetry & Tables:**
    *   **Table:** `INFORMATION_SCHEMA.TABLE_STORAGE`.
    *   **Key Fields:** `active_physical_bytes`, `time_travel_physical_bytes`,
        `fail_safe_physical_bytes`.
*   **Diagnostic Procedure & Telemetry:** See **Telemetry & Data Retrieval
    Reference** below to compare active physical bytes against total restorable
    churn (`time_travel_physical_bytes + fail_safe_physical_bytes`) and flag
    datasets where the churn ratio `(time_travel + fail_safe) / active` exceeds
    1.0.
*   **Remediation & Actions:**
    *   Reduce dataset Time Travel to 2 days (`ALTER SCHEMA {dataset_id} SET
        OPTIONS (max_time_travel_hours = 48);`).
    *   Avoid full-table truncates; use partition-level drops (`DROP PARTITION`)
        or incremental merges.
    *   If churn remains >1.0 and compression is below 2x, switch the dataset
        back to `LOGICAL` billing in the
        [Cloud Console Dataset Details Page](https://console.cloud.google.com/bigquery?project={project_id}&p={project_id}&d={dataset_id}&page=dataset)
        (after the 14-day lock-in expires).

### Scenario 4: Deleted Table / Dataset "Phantom Spend" & Long-Term Promotion

*   **When to Use / Symptoms:** A user deletes a large table or dataset in a
    physical storage billing dataset, but storage charges continue or even
    increase on the Cloud Billing invoice.
*   **Potential Root Causes:**
    *   *Time Travel & Fail-Safe Retention:* In physical billing, deleted data
        is retained for the duration of the configured Time Travel window (2–7
        days) plus an additional 7 days for Fail-Safe recovery. During this
        entire retention window, deleted blocks contribute to billable active
        physical storage even though the table no longer appears in the console
        or `INFORMATION_SCHEMA.TABLES` (it remains visible in
        `INFORMATION_SCHEMA.TABLE_STORAGE` with `deleted = TRUE`).
    *   *Long-Term to Active Promotion:* If the deleted data was in long-term
        physical storage, deletion causes this data to move into active physical
        storage during the Time Travel and Fail-Safe windows. Because active
        physical storage costs approximately 2 times more than long-term
        physical storage, deleting a dataset or table in physical billing model
        can cause a temporary spike in daily storage charges.
    *   *Logical Billing Contrast:* Under logical storage billing, dropped
        tables never incur charges for Time Travel or Fail-Safe; billable
        logical storage drops to 0 immediately upon deletion.
*   **Key Telemetry & Tables:**
    *   **Tables:** `INFORMATION_SCHEMA.SCHEMATA_OPTIONS`,
        `INFORMATION_SCHEMA.TABLE_STORAGE`.
    *   **Filters:** `deleted = TRUE`.
    *   **Key Fields:** `table_name`, `table_deletion_time`,
        `fail_safe_physical_bytes`, `time_travel_physical_bytes`.
*   **Diagnostic Procedure & Telemetry:** Check
    `INFORMATION_SCHEMA.SCHEMATA_OPTIONS` for `storage_billing_model`. If
    `PHYSICAL`, query `INFORMATION_SCHEMA.TABLE_STORAGE` with `WHERE deleted =
    TRUE` to view all deleted tables currently draining Time Travel and
    Fail-Safe bytes (see **Telemetry & Data Retrieval Reference** below). Query
    `INFORMATION_SCHEMA.JOBS` with `statement_type IN ('DROP_TABLE',
    'DROP_SCHEMA')` to confirm drop execution timestamp and actor.
*   **Remediation & Actions:**
    *   Explain the 9–14 day drain window factually to the user; charges will
        terminate once the Time Travel plus 7-day Fail-Safe window elapses.
    *   To minimize deletion costs for physical billing model datasets in the
        future, lower the dataset Time Travel window to 2 days
        (`max_time_travel_hours = 48`) before deleting large tables.

### Scenario 5: Table Clones and Snapshots Overestimation

*   **When to Use / Symptoms:** Raw table size queries report massive storage
    volumes that do not match the lower billed amount on the invoice.
*   **Potential Root Causes:** Table clones and snapshots report storage bytes
    equal to the full base table size in `INFORMATION_SCHEMA.TABLE_STORAGE`.
    However, BigQuery **only bills for modified or added delta blocks**.
*   **Key Telemetry & Tables:**
    *   **Tables:** `INFORMATION_SCHEMA.TABLE_STORAGE_USAGE_TIMELINE`,
        `INFORMATION_SCHEMA.TABLE_SNAPSHOTS`.
    *   **Key Fields:** `billable_total_logical_usage`, `base_table_name`.
*   **Diagnostic Procedure & Telemetry:** See **Telemetry & Data Retrieval
    Reference** below to query true billed storage deltas in
    `INFORMATION_SCHEMA.TABLE_STORAGE_USAGE_TIMELINE`, and check
    `INFORMATION_SCHEMA.TABLE_SNAPSHOTS` to verify base table lineage.
*   **Remediation & Actions:**
    *   Reassure the customer that unmutated cloned blocks are free of charge.

## 3. Execution Limitations & Footguns

*   **Timeline View Delay (48–72h):**
    `INFORMATION_SCHEMA.TABLE_STORAGE_USAGE_TIMELINE` has a 48–72 hour
    settlement lag. Use `INFORMATION_SCHEMA.TABLE_STORAGE` for real-time
    investigation, and use `INFORMATION_SCHEMA.TABLE_STORAGE_USAGE_TIMELINE` for
    historical 30-day billing reconciliation (ignoring the last 3 days).
*   **14-Day Cooldown (Hard Lock-in):** Once a dataset's storage billing model
    is changed between `LOGICAL` and `PHYSICAL`, it **cannot be changed again
    for 14 days**. Always verify compression ratios and churn rates over a full
    7-day cycle before switching.
*   **Opt-In & Access Requirements:** Querying
    `INFORMATION_SCHEMA.TABLE_STORAGE` requires `bigquery.tables.get` and
    `bigquery.tables.list` (`roles/bigquery.metadataViewer`). On
    non-grandfathered projects/orgs, data collection also requires opt-in via
    ``ALTER PROJECT `{project_id}` SET OPTIONS
    (`region-{region}.enable_info_schema_storage` = TRUE)`` (or
    `ALTER ORGANIZATION`), which requires `bigquery.config.update`
    (`roles/bigquery.admin`, not `roles/bigquery.resourceAdmin`). Historical
    data takes ~24 hours to populate post-enablement. For immediate triage
    without waiting for backfill, use `INFORMATION_SCHEMA.PARTITIONS` and
    `INFORMATION_SCHEMA.SCHEMATA_OPTIONS`, which do not require opt-in.
*   **BigLake Managed Storage:** BigLake Apache Iceberg table metadata appears
    in `INFORMATION_SCHEMA.TABLE_STORAGE` with `table_type = 'BASE TABLE'`, but
    actual file storage resides in customer Cloud Storage buckets and is
    excluded from BigQuery billable storage usage. To strictly isolate native
    BigQuery billable storage, filter
    `WHERE managed_table_type IS NULL OR managed_table_type = 'NATIVE'` directly
    on `INFORMATION_SCHEMA.TABLE_STORAGE`.
*   **Monthly Proration & Short Month Effect (February Daily Spikes):** BigQuery
    storage is priced at a fixed monthly rate per GiB. Google Cloud Billing
    calculates daily charges by prorating the monthly rate over the exact number
    of days in that calendar month (`daily_rate = monthly_rate /
    days_in_month`). For constant storage volume, daily billed spend appears
    ~10.7% higher in a 28-day February than in 31-day months. Always inspect
    underlying storage byte volume in `INFORMATION_SCHEMA` before diagnosing an
    apparent daily cost jump.

## 4. Telemetry & Data Retrieval Reference

If the `bigquery-observability` skill is available in your workspace, refer to
its shared telemetry references for canonical query templates and schema
dictionaries. All essential diagnostic workflows, formulas, and remediation
levers are self-contained within this guide.

*   **Table, Storage & Dataset Schemas:** See the `bigquery-observability` skill
    (`references/schema_storage.md`, section "3. Storage Footprint, Partitions &
    Table Metadata Views" and section "4. Datasets, Replication & Sharing
    Views") for `INFORMATION_SCHEMA.TABLE_STORAGE`,
    `INFORMATION_SCHEMA.TABLE_STORAGE_USAGE_TIMELINE`,
    `INFORMATION_SCHEMA.PARTITIONS`, and `INFORMATION_SCHEMA.SCHEMATA_OPTIONS`
    schemas.
*   **Project Option Schemas:** See the `bigquery-observability` skill
    (`references/schema_others.md`, section "10. Project & Organization
    Configuration Views") for `INFORMATION_SCHEMA.EFFECTIVE_PROJECT_OPTIONS`
    field definitions.
