# BigQuery Troubleshooting: Resource Contention & Performance Slowness

This reference guide provides root-cause mapping and remediation strategies for
BigQuery job and workload slowness. Each section connects the observed symptom
to potential root causes and points to the corresponding query in
`bigquery-observability`.

## Table of Contents

-   [Diagnostic Workflows by Symptom & Root Cause](#diagnostic-workflows-by-symptom-root-cause)
    (Lines 29-182)
    -   [1. Single-Job Stage Bottleneck Diagnosis & REST API Triage](#1-single-job-stage-bottleneck-diagnosis-rest-api-triage)
        (Lines 31-64)
    -   [2. Cohort Baseline Comparison (`normalized_literals`)](#2-cohort-baseline-comparison-normalized_literals)
        (Lines 66-84)
    -   [3. Incident Window Discovery & Timeline Degradation](#3-incident-window-discovery-timeline-degradation)
        (Lines 86-104)
    -   [4. Reservation Slot Saturation (1-Second Resolution)](#4-reservation-slot-saturation-1-second-resolution)
        (Lines 106-124)
    -   [5. Target vs. Baseline Timeframe Comparison](#5-target-vs-baseline-timeframe-comparison)
        (Lines 126-145)
    -   [6. Fleet Performance Variance & Outlier Discovery](#6-fleet-performance-variance-outlier-discovery)
        (Lines 147-164)
    -   [7. Table-Level Activity & Lock Contention](#7-table-level-activity-lock-contention)
        (Lines 166-182)
-   [Remediation & Optimization Strategies](#remediation-optimization-strategies)
    (Lines 184-198)

## Diagnostic Workflows by Symptom & Root Cause

### 1. Single-Job Stage Bottleneck Diagnosis & REST API Triage

-   **When to Use / Symptoms**: A specific query is slow or stalled, and you
    need to isolate whether delay occurred in pending queueing or during active
    stage execution.
-   **Potential Root Causes**: Slot starvation during execution stages, join row
    explosions (`records_written >> records_read` from cross joins or non-unique
    keys on both sides of a join), shuffle memory exhaustion
    (`shuffleOutputBytesSpilled`), unpruned input scans, or stage skew.
-   **Key Telemetry & Tables**:
    -   **CLI Triage**: `bq show --location={location} --format=prettyjson -j
        {project_id}:{job_id}` to inspect `statistics.query.timeline` for
        `activeUnits` vs `pendingUnits`, and `statistics.query.queryPlan` for
        stage-level compute and shuffle skew.
    -   **Table**: `INFORMATION_SCHEMA.JOBS_BY_PROJECT` (or
        `JOBS_BY_ORGANIZATION`).
    -   **Filters**: `job_id = 'JOB_ID'`, `project_id = 'PROJECT_ID'`,
        `creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)`.
    -   **Key Fields**: `total_slot_ms`, `total_bytes_billed`,
        `total_bytes_processed`, `job_stages` (`records_read`,
        `records_written`, `shuffle_output_bytes_spilled`, `slot_ms`,
        `wait_ratio_avg`, `wait_ratio_max`, `wait_ms_avg`, `wait_ms_max`,
        `read_ratio_avg`, `compute_ratio_avg`, `write_ratio_avg`),
        `query_info.performance_insights.stage_performance_standalone_insights`,
        `query_info.resource_warning_details`.
-   **Diagnostic Procedure & Telemetry**: See the `bigquery-observability` skill
    (`references/job_performance_queries.md`, section "REST API Single-Job
    Point-Lookup & Stage Bottlenecks") for fast CLI triage (`bq show -j`), the
    section "Single Job Performance & Stage Bottleneck Flags" for single-job SQL
    bottleneck analysis, and the section "Stage Row Expansion, Shuffle Spill &
    Join Insights" for multi-job `UNNEST(job_stages)` analysis. For
    execution-plan stage diagnosis of join explosions, shuffle spills, and
    partition skew, see
    [query_plan_execution_graph.md](query_plan_execution_graph.md#3-join-explosion-shuffle-spill-partition-skew-diagnosis).

### 2. Cohort Baseline Comparison (`normalized_literals`)

-   **When to Use / Symptoms**: A recurring scheduled query suddenly took 5x-10x
    longer than usual, and you need to compare it against healthy historical
    runs.
-   **Potential Root Causes**: Data volume growth, partition/cluster pruning
    regressions, schema/view definition updates, or multi-tenant system
    contention.
-   **Key Telemetry & Tables**:
    -   **Table**: `INFORMATION_SCHEMA.JOBS_BY_PROJECT`.
    -   **Filters**: `query_info.query_hashes.normalized_literals =
        'TARGET_NORMALIZED_LITERALS'`, `creation_time >=
        TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 14 DAY)`.
    -   **Key Fields**: `start_time`, `end_time`, `total_slot_ms`,
        `total_bytes_processed`, `total_bytes_billed`, `error_result`,
        `query_info.query_hashes.normalized_literals`.
-   **Diagnostic Procedure & Telemetry**: See the `bigquery-observability` skill
    (`references/job_performance_queries.md`, section "Finding Comparable
    Jobs").

### 3. Incident Window Discovery & Timeline Degradation

-   **When to Use / Symptoms**: Multiple users report slowness or queueing
    across a project/reservation, but the exact onset timeframe is unknown.
-   **Potential Root Causes**: Sudden query concurrency surges, batch pipeline
    arrivals, or unannounced capacity changes.
-   **Key Telemetry & Tables**:
    -   **Table**: `INFORMATION_SCHEMA.JOBS_TIMELINE_BY_PROJECT`.
    -   **Filters**: `period_start BETWEEN 'TARGET_START' AND 'TARGET_END'`,
        `job_creation_time BETWEEN TIMESTAMP_SUB('TARGET_START', INTERVAL 2 DAY)
        AND 'TARGET_END'`, `(statement_type != 'SCRIPT' OR statement_type IS
        NULL)`.
    -   **Key Fields**: `window_minute` (`TIMESTAMP_TRUNC(period_start,
        MINUTE)`), `slot_usage` (`ROUND(SUM(period_slot_ms) / 1000.0 / 60.0,
        1)`), `job_concurrency` (`ROUND(COUNT(*) / 60.0, 1)`),
        `project_queue_length` (`ROUND(COUNTIF(state = 'PENDING') / 60.0, 1)`).
-   **Diagnostic Procedure & Telemetry**: See the `bigquery-observability` skill
    (`references/resource_contention_queries.md`, section "Per-Minute Project
    Slot Usage, Concurrency & Queue Timeline").

### 4. Reservation Slot Saturation (1-Second Resolution)

-   **When to Use / Symptoms**: Queries spend excessive time in `PENDING` state
    or experience degraded execution times in a shared reservation.
-   **Potential Root Causes**: Multi-tenant reservation saturation, noisy
    neighbor workloads consuming capacity, or insufficient idle slot borrowing.
-   **Key Telemetry & Tables**:
    -   **Table**: `INFORMATION_SCHEMA.RESERVATIONS_TIMELINE_BY_PROJECT` joined
        with `JOBS_TIMELINE_BY_PROJECT`.
    -   **Filters**: `period_start BETWEEN 'TARGET_START' AND 'TARGET_END'`,
        `admin_project_id = 'ADMIN_PROJECT_ID'`, `reservation_id =
        'RESERVATION_ID'`.
    -   **Key Fields**: `is_autoscale_saturated`,
        `pct_time_autoscale_saturated`, `avg_baseline_slots`,
        `avg_autoscale_slots`, `avg_total_max_capacity`,
        `avg_borrowed_idle_slots`.
-   **Diagnostic Procedure & Telemetry**: See the `bigquery-observability` skill
    (`references/resource_contention_queries.md`, section "Reservation Maximum
    Utilization & Slot Saturation Timeline (1-Second Resolution)").

### 5. Target vs. Baseline Timeframe Comparison

-   **When to Use / Symptoms**: Systematic performance degradation across an
    entire reservation during a known incident window.
-   **Potential Root Causes**: Macro-level compute demand growth, fleet-wide
    data increases, or reduced idle slot availability from neighboring
    reservations.
-   **Key Telemetry & Tables**:
    -   **Table**: `INFORMATION_SCHEMA.JOBS_TIMELINE_BY_PROJECT`.
    -   **Parameters**: Compare Target timeframe (`TARGET_START` to
        `TARGET_END`) against Baseline timeframe (`BASELINE_START` to
        `BASELINE_END`, e.g., same hours on prior day or prior week).
    -   **Key Metrics**: Compare aggregated `total_slot_ms`,
        `total_bytes_processed`, `job_concurrency`, and `queue_length`.
-   **Diagnostic Procedure & Telemetry**: Compare total compute consumed, data
    volume scanned, and job counts between the degraded Target timeframe and a
    healthy Baseline timeframe (e.g., same hours on the prior day or week) using
    the query in the `bigquery-observability` skill
    (`references/resource_contention_queries.md`, section "Per-Minute Project
    Slot Usage, Concurrency & Queue Timeline").

### 6. Fleet Performance Variance & Outlier Discovery

-   **When to Use / Symptoms**: Need to identify which specific queries
    experienced the highest relative slowdown or locate high-slot "bully"
    queries.
-   **Potential Root Causes**: Unoptimized ad-hoc queries consuming unfair slot
    shares, or queries with high data skew.
-   **Key Telemetry & Tables**:
    -   **Table**: `INFORMATION_SCHEMA.JOBS_BY_PROJECT`.
    -   **Filters**: `creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(),
        INTERVAL 1 DAY)`, `(statement_type != 'SCRIPT' OR statement_type IS
        NULL)`.
    -   **Key Fields**: Grouped by `query_info.query_hashes.normalized_literals`
        to compute `job_count`, `avg_duration_ms`, `p90_duration_ms`,
        `stddev_duration_ms`, `max_duration_ms`, `avg_slot_ms`, `max_slot_ms`.
-   **Diagnostic Procedure & Telemetry**: See the `bigquery-observability` skill
    (`references/job_performance_queries.md`, section "Query Performance
    Variance & Outlier Discovery").

### 7. Table-Level Activity & Lock Contention

-   **When to Use / Symptoms**: Queries accessing a specific table or dataset
    stop responding, queue, or run slowly.
-   **Potential Root Causes**: Concurrent DML/DDL write lock serialization,
    frequent partition modifications, or read amplification.
-   **Key Telemetry & Tables**:
    -   **Table**: `INFORMATION_SCHEMA.JOBS_BY_PROJECT`.
    -   **Filters**: `destination_table.table_id = 'TARGET_TABLE'` OR `EXISTS
        (SELECT 1 FROM UNNEST(referenced_tables) rt WHERE rt.table_id =
        'TARGET_TABLE')`, `state IN ('RUNNING', 'PENDING')`.
    -   **Key Fields**: `job_id`, `statement_type` (`MERGE`, `UPDATE`, `INSERT`,
        `DELETE`), `start_time`, `state`, `user_email`, `query`.
-   **Diagnostic Procedure & Telemetry**: Filter `JOBS_BY_PROJECT` on
    `referenced_tables` or `destination_table` (following best practices in the
    `bigquery-observability` skill) to inspect concurrent write operations
    (`MERGE`, `UPDATE`, `INSERT`) competing for table locks.

## Remediation & Optimization Strategies

-   **Slot Contention & Saturation**: Increase `autoscale.max_slots` on the
    reservation, configure reservation priority, or isolate heavy batch queries
    into a dedicated reservation.
-   **Stage Bottlenecks & Shuffle Spill**: Check join conditions to avoid
    unintentional `CROSS JOIN`s or non-unique keys on both sides of a join, use
    a `GROUP BY` clause to pre-aggregate join inputs before joining, optimize
    join ordering (broadcast smaller tables with `HASH` joins), partition or
    cluster large tables to prune shuffle volume, and eliminate unneeded columns
    (see
    [query_plan_execution_graph.md](query_plan_execution_graph.md#3-join-explosion-shuffle-spill-partition-skew-diagnosis)).
-   **Queueing / Pending Slowness**: Increase reservation baseline capacity,
    adjust target job concurrency, or stagger scheduled query start times to
    avoid top-of-the-hour arrival spikes.
