# BigQuery Troubleshooting: Capacity (Editions) Cost & Slot Allocation

This reference guide provides root-cause mapping and remediation strategies for
BigQuery Editions and capacity compute cost spikes (slot-hour usage, uncovered
baseline penalties, and autoscaler surges). It focuses strictly on
Capacity-based compute billable usage (Editions, Commitments, Baseline, and
Autoscaling slot-hours). Each section connects the observed symptom to potential
root causes and points to the corresponding audit query in
`bigquery-observability`.

## Table of Contents

-   [1. 4-Step Diagnostic Funnel](#1-4-step-diagnostic-funnel) (Lines 27-127)
-   [2. Diagnostic Workflows by Symptom & Root Cause](#2-diagnostic-workflows-by-symptom-root-cause)
    (Lines 129-259)
    -   [Scenario 1: Uncovered Baseline Slots Penalty & Commitment Expiration](#scenario-1-uncovered-baseline-slots-penalty-commitment-expiration)
        (Lines 131-168)
    -   [Scenario 2: Baseline Reduction Triggering Autoscale Surge](#scenario-2-baseline-reduction-triggering-autoscale-surge)
        (Lines 170-190)
    -   [Scenario 3: Reservation Autoscaler Thrashing & Concurrency Spikes](#scenario-3-reservation-autoscaler-thrashing-concurrency-spikes)
        (Lines 192-218)
    -   [Scenario 4: Unexpected "BigQuery Reservation API" Charges (Serverless & Managed Features)](#scenario-4-unexpected-bigquery-reservation-api-charges-serverless-managed-features)
        (Lines 220-259)
-   [3. Telemetry & Data Retrieval Reference](#3-telemetry-data-retrieval-reference)
    (Lines 261-278)

## 1. 4-Step Diagnostic Funnel

When investigating capacity / Edition cost questions (e.g., *"Why did my Edition
bill increase?"*, *"What is driving my reservation autoscale spend?"*, or
Month-over-Month comparisons):

1.  **Step 1: Context Resolution & Baseline Scan (Gather)**

    *   **Scope Resolution & Target Project:** Identify the target project,
        `region`, `edition` (Standard, Enterprise, Enterprise Plus), and
        analysis timeframe.
    *   **Time Window & Baseline:** Default to a standard **7-day
        Period-over-Period (PoP)** window comparing the last 7 days against the
        preceding 7 days (`CURRENT_DATE() - 7` to `CURRENT_DATE() - 14`) if
        unspecified; otherwise evaluate the user's requested timeframe against
        its corresponding prior baseline period
        (`INFORMATION_SCHEMA.RESERVATIONS_TIMELINE` and
        `INFORMATION_SCHEMA.CAPACITY_COMMITMENT_CHANGES_BY_PROJECT` retain 180
        days).
    *   **Baseline Scan:** Query `INFORMATION_SCHEMA.RESERVATIONS_TIMELINE` for
        total billed slot-hours across reservations.
    *   **Admin Project Resolution & Zero-Row Test:**
        *   If the user explicitly provided the `admin_project_id` (or if the
            project owns the reservations), execute capacity queries directly
            scoped to that admin project.
        *   If the baseline query returns 0 rows, STOP. Do not compute
            aggregates over an empty set. Execute the following triage:
            1.  *Query Running Project Check:* In BigQuery Editions,
                reservations and commitments are owned by an **Admin Project**,
                while queries run in separate **Assignee / Query Running
                Projects**. Check `reservation_id` in `INFORMATION_SCHEMA.JOBS`
                (formatted as
                `{admin_project_id}:{location}.{reservation_name}`) to resolve
                the true admin project, then re-run the scan scoped to
                `{admin_project_id}`.
            2.  *Compute Model Check:* If `reservation_id IS NULL` in
                `INFORMATION_SCHEMA.JOBS`, the project runs on On-Demand compute
                --> route to `references/cost_compute_ondemand.md`.
            3.  *Region & Scope Verification:* If unassigned, prompt the user to
                confirm the admin project ID and region.
    *   **Report Factually:** State the baseline vs. current slot-hour volume
        and percentage growth before diagnosing root causes.

2.  **Step 2: Vector Decomposition & Anomaly Isolation (Isolate)**

    *   Deconstruct capacity spend across the two reporting levels
        (Edition-Level Invoice Reconciliation vs. Reservation-Level Workload
        Breakdown):
        *   **Edition-Level Spend Attribution (Invoice Reconciliation):**
            Capacity commitments are purchased at the Edition tier (admin
            project) and pooled across all reservations in that Edition. Only at
            the Edition level can we reconcile invoice charges and attribute:
            *   *1-Year Committed Slot-Hours:* Slot capacity purchased under
                1-Year commitments, billed 24/7 at fixed discounted rates.
            *   *3-Year Committed Slot-Hours:* Slot capacity purchased under
                3-Year commitments, billed 24/7 at fixed discounted rates.
            *   *Uncovered Pay-As-You-Go (PAYG) Baseline Slot-Hours:* Configured
                baseline capacity across all reservations in the Edition that
                exceeds active commitments, billed 24/7 at variable hourly PAYG
                rates.
            *   *Autoscaled PAYG Slot-Hours:* Dynamic autoscaling slot-seconds
                aggregated across all reservations, billed at variable hourly
                PAYG rates.
        *   **Reservation-Level Workload Breakdown (Workload Attribution):**
            Individual reservations track query workload consumption without
            commitment attribution. Because commitments are pooled across the
            Edition, an individual reservation cannot determine whether its
            baseline is satisfied by commitments or PAYG:
            *   *Billable Baseline Slot-Hours:* Configured baseline capacity
                (`(slot_capacity * 60) / 3600.0` in the creation region where
                `is_creation_region = TRUE`).
            *   *Autoscaled Slot-Hours (PAYG):* Dynamic autoscaling consumed by
                queries (`period_autoscale_slot_seconds / 3600.0`), billed at
                hourly PAYG rates.

3.  **Step 3: Event & Configuration Correlation (Explain Root Cause)**

    *   Correlate the isolated sub-vector with chronological configuration
        events:
        *   Query `INFORMATION_SCHEMA.RESERVATION_CHANGES` for `action =
            'UPDATE'` (e.g. `slot_capacity` manually reduced, forcing workloads
            into autoscale), `autoscale.max_slots` modifications, or assignment
            changes.
        *   Query `INFORMATION_SCHEMA.CAPACITY_COMMITMENT_CHANGES_BY_PROJECT`
            for commitment expirations (`action = 'DELETE'`, `state =
            'DELETED'`), creations, or non-renewal (`renewal_plan = 'NONE'`).
        *   **Disaster Recovery (DR) Regional Impact:** Under BigQuery Managed
            DR (Enterprise Plus), standby baseline compute capacity in the
            secondary region is provided at **no additional charge**; baseline
            compute capacity is billed strictly in the creation region
            (`is_creation_region = TRUE`). In
            `INFORMATION_SCHEMA.RESERVATIONS_TIMELINE`, `slots_assigned` shifts
            to the secondary region during a failover event, but the billable
            baseline is always derived from `IF(is_creation_region,
            slot_capacity, 0)` regardless of failover.

4.  **Step 4: Actionable Remediation & Customer Levers (Remediate)**

    *   Deliver concrete, immediate mitigation levers (commitment purchases to
        cover steady baseline, autoscaler parameter adjustments, or workload
        isolation) as detailed in the matching scenario below.

## 2. Diagnostic Workflows by Symptom & Root Cause

### Scenario 1: Uncovered Baseline Slots Penalty & Commitment Expiration

*   **When to Use / Symptoms:** Configured reservation baseline capacity exceeds
    active purchased commitments, or a sudden capacity cost spike occurs with
    zero workload changes after a commitment expires or lapses auto-renewal.
*   **Potential Root Causes:**
    *   *Trigger 1 (Over-provisioned Baseline):* Baseline slots were increased
        in a reservation without purchasing matching 1-Year or 3-Year
        commitments at the Edition tier in the admin project.
    *   *Trigger 2 (Commitment Expiration / Lapsed Renewal):* An existing
        commitment expired (`renewal_plan = 'NONE'`). Because reservation
        `slot_capacity` (baseline slots) remained allocated, the slots silently
        reverted from discounted commitment pricing to 24/7 PAYG baseline
        billing.
*   **Key Telemetry & Tables:**
    *   **Baseline Slots View:** `INFORMATION_SCHEMA.RESERVATIONS_TIMELINE`
        (`slot_capacity`, `is_creation_region`, `period_start`, `edition`).
    *   **Commitment Changes View:**
        `INFORMATION_SCHEMA.CAPACITY_COMMITMENT_CHANGES_BY_PROJECT`
        (`slot_count`, `commitment_plan`, `renewal_plan`, `action`, `state`,
        `change_timestamp`).
*   **Diagnostic Procedure & Telemetry:** Query
    `INFORMATION_SCHEMA.CAPACITY_COMMITMENT_CHANGES_BY_PROJECT` for `action =
    'DELETE'`, `state = 'DELETED'`, or `renewal_plan = 'NONE'`, correlating
    `change_timestamp` with the spike date. See **Telemetry & Data Retrieval
    Reference** below to join
    `INFORMATION_SCHEMA.CAPACITY_COMMITMENT_CHANGES_BY_PROJECT` and
    `INFORMATION_SCHEMA.RESERVATIONS_TIMELINE`, reconcile baseline allocations
    against active commitments, and calculate uncovered baseline PAYG
    slot-hours.
*   **Remediation & Actions:**
    *   **Continuous 24/7 Workloads:** Purchase 1-Year or 3-Year Capacity
        Commitments (or re-enable auto-renewal) to cover 100% of baseline slots,
        capturing the 33%–50% discount. Manage commitments in the
        [Cloud Console Reservations Page](https://console.cloud.google.com/bigquery/admin/reservations?project={project_id}&region={region}).
    *   **Variable / Burst Workloads:** Reduce `slot_capacity` (baseline) to `0`
        and rely on **Autoscaling Slots** (`autoscale.max_slots`), which only
        incur charges when actively running queries.

### Scenario 2: Baseline Reduction Triggering Autoscale Surge

*   **When to Use / Symptoms:** Total billed slot-hours increase significantly
    after an administrator reduces reservation baseline capacity.
*   **Potential Root Causes:** Baseline slots were lowered (e.g. from 1,000 to
    200 slots via an `UPDATE` on `slot_capacity`), but steady ETL demand forced
    queries into Autoscaling Slots billed at variable PAYG rates, exceeding the
    original committed baseline cost.
*   **Key Telemetry & Tables:**
    *   **Tables:** `INFORMATION_SCHEMA.RESERVATION_CHANGES`,
        `INFORMATION_SCHEMA.RESERVATIONS_TIMELINE`.
    *   **Key Fields:** `action`, `slot_capacity`,
        `period_autoscale_slot_seconds`, `change_timestamp`.
*   **Diagnostic Procedure & Telemetry:** Query
    `INFORMATION_SCHEMA.RESERVATION_CHANGES` for `action = 'UPDATE'` to identify
    when `slot_capacity` was reduced. See **Telemetry & Data Retrieval
    Reference** below to correlate the drop in baseline capacity with surging
    autoscale slot-hours (`period_autoscale_slot_seconds`).
*   **Remediation & Actions:**
    *   Restore `slot_capacity` to cover predictable, steady ETL demand and
        cover the baseline with 1-Year or 3-Year commitments.

### Scenario 3: Reservation Autoscaler Thrashing & Concurrency Spikes

*   **When to Use / Symptoms:** High autoscaling slot-hour spend driven by
    short, frequent bursts of query concurrency.
*   **Potential Root Causes:** Bursty scheduled queries or concurrent BI
    refreshes cause the autoscaler to scale up to `autoscale.max_slots` (in
    increments of 50 slots). By default, autoscaled capacity is billed
    per-second with a 1-minute minimum duration (and a 60-second scale-down
    window), causing frequent short bursts to accumulate high slot-hour spend
    unless fluid scaling is enabled.
*   **Key Telemetry & Tables:**
    *   **Tables:** `INFORMATION_SCHEMA.RESERVATIONS_TIMELINE`,
        `INFORMATION_SCHEMA.JOBS`.
    *   **Key Fields:** `period_autoscale_slot_seconds`, `timeline`,
        `statement_type`, `creation_time`, `start_time`.
*   **Diagnostic Procedure & Telemetry:** Analyze hourly autoscaled slot-second
    distribution in `INFORMATION_SCHEMA.RESERVATIONS_TIMELINE` and correlate
    peak slot periods with `INFORMATION_SCHEMA.JOBS` concurrency to isolate
    top-of-the-hour batch arrivals (following guidance in **Telemetry & Data
    Retrieval Reference** below).
*   **Remediation & Actions:**
    *   Separate interactive BI dashboards from scheduled batch pipelines into
        dedicated reservations with tailored `autoscale.max_slots` caps.
    *   Stagger top-of-the-hour cron schedules to smooth out slot demand spikes.
    *   Evaluate opting into **fluid scaling** at the reservation level to
        enable true per-second billing with no minimum duration for bursty
        workloads.

### Scenario 4: Unexpected "BigQuery Reservation API" Charges (Serverless & Managed Features)

*   **When to Use / Symptoms:** A project with no active reservations (or on
    On-Demand) incurs charges under the service **"BigQuery Reservation API"**
    (billed as Standard or Enterprise Edition PAYG slot-hours).
*   **Potential Root Causes:** Serverless and managed BigQuery features
    provision dynamic compute capacity behind the scenes:
    1.  **BigQuery Studio / Colab Enterprise Notebooks:** Interactive Python/SQL
        sessions and cell executions run on managed runtimes billed as Standard
        or Enterprise Edition PAYG slot-hours.
    2.  **Stored Procedures for Apache Spark:** PySpark and Spark SQL procedures
        execute on serverless compute billed as Enterprise Edition PAYG
        slot-hours based on vCPU and RAM allocation.
    3.  **BigQuery Data Transfer Service (DTS):** Scheduled data ingestion
        pipelines utilize managed compute billed under the Reservation API
        service.
    4.  **BigLake Managed Tables (Apache Iceberg):** Automated background table
        maintenance (compaction, clustering, snapshot expiration) is billed at
        Enterprise Edition slot-hour rates.
*   **Key Telemetry & Procedures:**
    *   **Google Cloud Console Billing Isolation:**
        1.  Navigate to **Billing > Reports** in Google Cloud Console.
        2.  Set **Service** filter to `BigQuery Reservation API`.
        3.  Group by **Label**: `goog-bq-feature-type`.
        4.  Identify the exact driver by label value:
            *   `BQ_STUDIO_NOTEBOOK`: Interactive BigQuery Studio / Colab
                Enterprise notebook runtimes.
            *   `SPARK_PROCEDURE`: Stored procedures for Apache Spark.
            *   `DATA_TRANSFER_SERVICE`: BigQuery Data Transfer Service ingest
                pipelines.
            *   `BIGLAKE_ICEBERG`: Automated BigLake Iceberg table maintenance.
*   **Remediation & Actions:**
    *   **Cap Dynamic Compute:** Create a dedicated capacity reservation with an
        explicit `autoscale.max_slots` limit and assign the project/workloads to
        it to bound maximum hourly PAYG spend.
    *   **Configure Notebook Idle Timeouts:** Shorten the idle shutdown timeout
        in BigQuery Studio / Colab Enterprise settings to terminate inactive
        interactive runtimes.
    *   **Stagger Data Transfer Schedules:** Stagger DTS transfer runs to avoid
        accumulating simultaneous compute slot-hours during peak business hours.

## 3. Telemetry & Data Retrieval Reference

If the `bigquery-observability` skill is available in your workspace, refer to
its shared telemetry references for canonical query templates and schema
dictionaries. All essential diagnostic workflows, formulas, and remediation
levers are self-contained within this guide.

*   **Edition Invoicing & Commitments Reconciliation:** See the
    `bigquery-observability` skill (`references/compute_capacity_billable.md`,
    section "Edition Billable Slots Timeline") for canonical queries reconciling
    Edition-level commitments against `INFORMATION_SCHEMA.RESERVATIONS_TIMELINE`
    and breaking down per-reservation slot-hours.
*   **Capacity & Reservation View Schemas:** See the `bigquery-observability`
    skill (`references/schema_compute.md`, section "2. Capacity, Reservations &
    Commitments Views") for `INFORMATION_SCHEMA.RESERVATIONS`,
    `INFORMATION_SCHEMA.RESERVATIONS_TIMELINE`,
    `INFORMATION_SCHEMA.RESERVATION_CHANGES`, and
    `INFORMATION_SCHEMA.CAPACITY_COMMITMENTS` schemas.
