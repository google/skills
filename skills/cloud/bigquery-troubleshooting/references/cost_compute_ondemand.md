# BigQuery Troubleshooting: On-Demand Compute Spend & Query Scans

This reference guide provides root-cause mapping and remediation strategies for
BigQuery On-Demand compute cost spikes, query scan volume growth, and runaway
queries. It focuses strictly on On-Demand compute billable usage
(`total_bytes_billed` converted to TiB in `INFORMATION_SCHEMA.JOBS`). Each
section connects the observed symptom to potential root causes and points to the
corresponding query in `bigquery-observability`.

## Table of Contents

-   [1. 4-Step Diagnostic Funnel](#1-4-step-diagnostic-funnel) (Lines 28-81)
-   [2. Diagnostic Workflows by Symptom & Root Cause](#2-diagnostic-workflows-by-symptom-root-cause)
    (Lines 83-269)
    -   [Scenario 1: The Bully Query (Unpartitioned Runaway Scan)](#scenario-1-the-bully-query-unpartitioned-runaway-scan)
        (Lines 85-146)
    -   [Scenario 2: Hidden RLS Redacted Costs](#scenario-2-hidden-rls-redacted-costs)
        (Lines 148-183)
    -   [Scenario 3: BQML Model Training Rates](#scenario-3-bqml-model-training-rates)
        (Lines 185-211)
    -   [Scenario 4: User / Service Account Bursting & Missing Quotas](#scenario-4-user-service-account-bursting-missing-quotas)
        (Lines 213-237)
    -   [Scenario 5: Querying Very Small Tables (10 MiB Minimum Billed Data Floor)](#scenario-5-querying-very-small-tables-10-mib-minimum-billed-data-floor)
        (Lines 239-269)
-   [3. Telemetry & Data Retrieval Reference](#3-telemetry-data-retrieval-reference)
    (Lines 271-294)

## 1. 4-Step Diagnostic Funnel

When investigating on-demand compute cost questions (e.g., *"Why did our
on-demand query bill spike?"*, *"Who scanned the most data last week?"*, or
Month-over-Month comparisons):

1.  **Step 1: Context Resolution & Baseline Scan (Gather)**

    *   **Scope Resolution:** Identify the target `project_id`, `region`, and
        requested analysis timeframe.
    *   **Time Window & Baseline:** Default to a standard **7-day
        Period-over-Period (PoP)** window comparing the last 7 days against the
        preceding 7 days (`CURRENT_DATE() - 7` to `CURRENT_DATE() - 14`) if
        unspecified; otherwise evaluate the user's requested timeframe against
        its corresponding prior baseline period (`INFORMATION_SCHEMA.JOBS`
        retains 180 days).
    *   **Baseline Scan:** Query `INFORMATION_SCHEMA.JOBS` for total billed TiB
        aligned to Pacific Time (`PST8PDT`).
    *   **Compute Model Check & Zero-Row Test:** If the baseline query returns 0
        rows, STOP. Do not compute aggregates over an empty set. Automatically
        check if the project runs on Capacity/Editions (inspect `reservation_id`
        in `INFORMATION_SCHEMA.JOBS` or check `INFORMATION_SCHEMA.ASSIGNMENTS`).
        If assigned to a reservation, route to
        `references/cost_compute_capacity.md`. Otherwise, prompt the user to
        confirm the active region and project scope before proceeding.
    *   **Report Factually:** State the percentage increase and the exact TiB
        volume movement before diagnosing root causes.

2.  **Step 2: Vector Decomposition & Anomaly Isolation (Isolate)**

    *   Deconstruct total billed bytes across:
        *   **Query Frequency / Volume:** An increase in total executed jobs
            across automated pipelines.
        *   **The Bully Query:** A single expensive query scanning terabytes or
            petabytes unconstrained.
        *   **BQML Model Training:** `CREATE MODEL` operations under On-Demand
            pricing that bill processed bytes at specialized model training
            rates.
        *   **Hidden RLS Redactions:** Queries against Row-Level Security tables
            returning `NULL` in `total_bytes_billed`.

3.  **Step 3: Event & Query Correlation (Explain Root Cause)**

    *   Group `INFORMATION_SCHEMA.JOBS` by `user_email`,
        `query_info.query_hashes.normalized_literals`, and `statement_type` (and
        include `project_id` when querying organization or folder views).
    *   Identify the top contributing queries, executing actors (user or service
        account), and execution timestamps.

4.  **Step 4: Actionable Remediation & Customer Levers (Remediate)**

    *   Deliver concrete, immediate mitigation levers (enforcing partition
        filters, setting query billing caps, and optimizing query syntax) as
        detailed in the matching scenario below.

## 2. Diagnostic Workflows by Symptom & Root Cause

### Scenario 1: The Bully Query (Unpartitioned Runaway Scan)

*   **When to Use / Symptoms:** A sudden spike in daily On-Demand billed bytes
    attributable to a few single massive queries scanning large volumes of data
    unconstrained.
*   **Potential Root Causes:** Sub-optimal query design in general, including
    missing partition pruning predicates (`WHERE _PARTITIONDATE >= ...`),
    missing cluster filters, unconstrained `SELECT *` scans, non-selective or
    cross joins, or repeated full-table scans across multi-terabyte tables.
*   **Key Telemetry & Tables:**
    *   **Table:** `INFORMATION_SCHEMA.JOBS_BY_PROJECT` (or
        `INFORMATION_SCHEMA.JOBS`), `INFORMATION_SCHEMA.COLUMNS`,
        `INFORMATION_SCHEMA.TABLE_OPTIONS`.
    *   **Filters:** `job_type = 'QUERY'`, `statement_type != 'SCRIPT'`,
        `creation_time >= TIMESTAMP_SUB(...)`.
    *   **Key Fields:** `project_id` (crucial for org/folder-level views),
        `job_id`, `user_email`, `total_bytes_billed`, `total_bytes_processed`,
        `referenced_tables`, `statement_type`,
        `query_info.query_hashes.normalized_literals` (in `JOBS_BY_PROJECT`);
        `table_name`, `column_name`, `data_type`, `is_partitioning_column`,
        `clustering_ordinal_position` (in `COLUMNS`); `option_name =
        'require_partition_filter'`, `option_value` (in `TABLE_OPTIONS`).
*   **Diagnostic Procedure & Telemetry:** See **Telemetry & Data Retrieval
    Reference** below to calculate canonical billed TiB, account for BQML
    multipliers, and sort by spend descending:
    1.  **Query-Template Spend Attribution:** Group `JOBS_BY_PROJECT` by
        `query_info.query_hashes.normalized_literals` to sum job-level
        `total_bytes_billed` and `total_bytes_processed` (and project
        `ANY_VALUE(referenced_tables)`) without double-counting multi-table
        joins.
    2.  **Candidate Table Discovery & Partitioning Audit:** Unnest
        `referenced_tables` to identify which tables those high-scan queries
        touch (do not sum job-level bytes across joined tables; cross-check
        actual table size via `total_logical_bytes` in
        `INFORMATION_SCHEMA.TABLE_STORAGE`), then query
        `INFORMATION_SCHEMA.COLUMNS` and `INFORMATION_SCHEMA.TABLE_OPTIONS` to
        verify whether each referenced table has `DATE`, `TIMESTAMP`,
        `DATETIME`, or `INT64` integer-range partitioning, clustering columns,
        and `require_partition_filter = 'true'`.
*   **Remediation & Actions:**
    *   **Partition & Cluster Unpartitioned Tables:** Unpartitioned tables
        cannot be converted in place or replaced via `OR REPLACE` with a
        different kind of partitioning; use `CREATE TABLE ... PARTITION BY ...
        CLUSTER BY ... AS SELECT * FROM ...` (CTAS) to create a new partitioned
        and clustered table (or `DROP` and recreate it). For table partitioning
        and clustering design, refer to the `bigquery-optimization` skill.
    *   **Enforce Partition Filtering:** Require partition filters on large
        partitioned tables:
        *   *DDL:* `ALTER TABLE {dataset_id}.{table_id} SET OPTIONS
            (require_partition_filter = true);`
        *   *CLI:* `bq update --require_partition_filter=true
            {project_id}:{dataset_id}.{table_id}`
    *   **Set Query Billing Caps:** Set a maximum byte limit to prevent rogue
        scans:
        *   *CLI:* `bq query --use_legacy_sql=false
            --maximum_bytes_billed=107374182400 "{sql_query}"` (e.g., 100 GB
            cap).
        *   *Client Libraries:* Set `job_config.maximum_bytes_billed =
            107374182400` in `QueryJobConfig`.
    *   **Optimize Query Syntax:** Add partition pruning filters, filter or
        aggregate by clustered columns (such as high-cardinality columns), and
        select only required columns instead of `SELECT *`.

### Scenario 2: Hidden RLS Redacted Costs

*   **When to Use / Symptoms:** Queries return `NULL` in `total_bytes_billed` in
    `INFORMATION_SCHEMA.JOBS`, causing standard sum queries to undercount spend
    and creating an apparent discrepancy with the Cloud Billing invoice.
*   **Potential Root Causes:** Row-Level Security (RLS) policies are active on
    the scanned tables. BigQuery hides sensitive statistics
    (`total_bytes_billed`, `total_bytes_processed`, partitions processed, and
    `job_stages`) on all queries against tables with row-level access policies
    to prevent side-channel inference.
*   **Key Telemetry & Tables:**
    *   **Tables:** `INFORMATION_SCHEMA.JOBS` (audit active row access policies
        and filter predicates via `INFORMATION_SCHEMA.ROW_ACCESS_POLICIES` —
        note that Analytics Hub linked datasets return zero rows without error,
        so check the publisher source dataset instead — or list policies and
        grantees with `bq ls --row_access_policies {dataset_id}.{table_id}`).
    *   **Filters:** `job_type = 'QUERY'`, `total_bytes_billed IS NULL`,
        `(error_result IS NULL OR error_result.reason = 'stopped')`.
    *   **Key Fields:** `project_id` (for org/folder-level views), `job_id`,
        `user_email`, `referenced_tables` (`total_bytes_processed` is also
        `NULL` in `INFORMATION_SCHEMA.JOBS` when RLS is active).
*   **Diagnostic Procedure & Telemetry:** Count the volume of redacted queries
    in `INFORMATION_SCHEMA.JOBS` where `total_bytes_billed IS NULL` and
    `(error_result IS NULL OR error_result.reason = 'stopped')`. See **Telemetry
    & Data Retrieval Reference** below to audit active row access policies on
    referenced tables.
*   **Remediation & Actions:**
    *   **Audit Logs or Separate Base Tables:** No IAM permission or role
        unmasks `total_bytes_billed` in `INFORMATION_SCHEMA.JOBS` when a
        referenced table has row-level access policies. Project Owners can view
        bytes processed in Cloud Audit Logs, or route trusted full-table ETL/BI
        pipelines to separate raw base tables that have no row-level access
        policies.
    *   **Reconcile with Billing Reports:** Use Google Cloud Billing Reports
        grouped by SKU (`Analysis`) to track complete financial invoice amounts
        including RLS-redacted queries.

### Scenario 3: BQML Model Training Rates

*   **When to Use / Symptoms:** Billed bytes or invoice costs are significantly
    higher than scanned bytes for specific queries due to machine learning
    training workloads.
*   **Potential Root Causes:** In On-Demand pricing, `CREATE MODEL` operations
    for certain built-in ML algorithms (such as Deep Neural Networks, Matrix
    Factorization, or AutoML) are billed at specialized rates on processed
    bytes.
*   **Key Telemetry & Tables:**
    *   **Table:** `INFORMATION_SCHEMA.JOBS`.
    *   **Filters:** `statement_type = 'CREATE_MODEL'`.
    *   **Key Fields:** `project_id` (for org/folder-level views), `job_id`,
        `user_email`, `total_bytes_processed`, `total_bytes_billed`,
        `statement_type`.
*   **Diagnostic Procedure & Telemetry:** Filter `INFORMATION_SCHEMA.JOBS` for
    `statement_type = 'CREATE_MODEL'` (following guidance in **Telemetry & Data
    Retrieval Reference** below) to evaluate model training byte volume and
    isolate top model training queries.
*   **Remediation & Actions:**
    *   **Pre-materialize Training Sets:** Filter and materialize feature
        datasets into intermediate tables to minimize repeated full table scans
        during iterative training.
    *   **Evaluate Capacity Model:** For frequent or heavy ML model training,
        evaluate whether running workloads under BigQuery Editions (where model
        training consumes slot capacity rather than on-demand byte multipliers)
        is more cost-effective.

### Scenario 4: User / Service Account Bursting & Missing Quotas

*   **When to Use / Symptoms:** A sudden day-over-day spike in total billed
    bytes spread across hundreds or thousands of automated queries from a
    specific identity.
*   **Potential Root Causes:** Newly deployed CI/CD pipeline, unthrottled
    notebook, or automated script executing high-concurrency unpruned queries.
*   **Key Telemetry & Tables:**
    *   **Table:** `INFORMATION_SCHEMA.JOBS`.
    *   **Key Fields:** `project_id`, `user_email`, `creation_time`,
        `total_bytes_billed`, `query_info.query_hashes.normalized_literals`.
*   **Diagnostic Procedure & Telemetry:** Group `INFORMATION_SCHEMA.JOBS` by
    `user_email` and daily date partition to isolate the identity driving the
    surge (following guidance in **Telemetry & Data Retrieval Reference**
    below). Group by `query_info.query_hashes.normalized_literals` for that user
    to identify the specific bursting script.
*   **Remediation & Actions:**
    *   **Configure Cloud Quotas:** Set custom daily query usage limits in the
        Google Cloud Console under **IAM & Admin** > **Quotas & System
        Limits** > **BigQuery API**:
        *   `Query usage per day` (project-level cap).
        *   `Query usage per day per user` (prevents a single rogue script from
            exhausting the budget).
    *   **Project Workload Isolation:** Separate automated pipelines from ad-hoc
        analytical users into separate GCP projects with distinct quota limits.

### Scenario 5: Querying Very Small Tables (10 MiB Minimum Billed Data Floor)

*   **When to Use / Symptoms:** Queries against very small tables (even
    kilobyte-sized reference or status tables) result in disproportionately high
    on-demand compute charges.
*   **Potential Root Causes:** Under BigQuery On-Demand pricing, the minimum
    billed processed data per referenced table in a query is **10 MiB**,
    regardless of actual table size. Likewise, the minimum billed processed data
    per query is **10 MiB**. Automated loops, health probes, or ETL scripts
    querying tiny lookup tables hundreds of times per hour accumulate billable
    bytes rapidly (e.g. 10,000 queries = ~100 GB billed).
*   **Key Telemetry & Tables:**
    *   **Tables:** `INFORMATION_SCHEMA.JOBS`, `INFORMATION_SCHEMA.TABLES`.
    *   **Key Fields:** `project_id`, `job_id`, `user_email`,
        `total_bytes_billed`, `total_bytes_processed`, `referenced_tables`.
*   **Diagnostic Procedure & Telemetry:** Filter `INFORMATION_SCHEMA.JOBS` for
    queries where `total_bytes_billed = 10485760` (10 MiB) or where
    `total_bytes_processed < 10485760` but `total_bytes_billed = 10485760`
    (following guidance in **Telemetry & Data Retrieval Reference** below).
    Count the frequency of these small queries and inspect `referenced_tables`
    to isolate the target lookup tables.
*   **Remediation & Actions:**
    *   **Application-Side Caching:** Cache lookup or configuration tables in
        application memory or Memorystore rather than querying BigQuery
        repeatedly.
    *   **Batch Invocations:** Consolidate frequent individual lookups into
        batched queries using `IN (...)` or joins.
    *   **Evaluate BigQuery Editions:** For workloads that require
        high-frequency lightweight lookups, route the project to BigQuery
        Editions, where compute is billed by slot capacity rather than per-query
        10 MiB minimums.

## 3. Telemetry & Data Retrieval Reference

If the `bigquery-observability` skill is available in your workspace, refer to
its shared telemetry references for canonical query templates and schema
dictionaries. All essential diagnostic workflows, formulas, and remediation
levers are self-contained within this guide.

*   **On-Demand Billed Bytes & Daily Spend:** See the `bigquery-observability`
    skill (`references/compute_ondemand_billable.md`, section "CORE RULE: The
    Golden Base CTE (bytes_billed_cte)") for the canonical bytes billed CTE with
    BQML multipliers and timezone alignment.
*   **Table Partitioning, Clustering & Filter Enforcement Audit:** See the
    `bigquery-observability` skill (`references/storage_footprints.md`, section
    "Table Partitioning, Clustering & Filter Enforcement Audit") to inspect
    `INFORMATION_SCHEMA.COLUMNS` and `INFORMATION_SCHEMA.TABLE_OPTIONS` for
    partitioning columns, clustering columns, and `require_partition_filter`.
*   **Job Metadata:** See the `bigquery-observability` skill
    (`references/schema_compute.md`, section "1. Jobs & Compute Telemetry
    Views") for `INFORMATION_SCHEMA.JOBS` view schema.
*   **Security & Access Policies:** See the `bigquery-observability` skill
    (`references/schema_others.md`, section
    "`INFORMATION_SCHEMA.ROW_ACCESS_POLICIES`") for auditing active row-level
    access policies and filter predicates via SQL, or inspecting grantees with
    `bq ls --row_access_policies` / `rowAccessPolicies.getIamPolicy`.
