# BigQuery Troubleshooting: Performance & Configuration Changes

This reference guide provides root-cause mapping and remediation strategies for
performance degradation caused by reservation, commitment, or assignment
changes. Each section connects the observed symptom to potential root causes and
points to the corresponding audit query in `bigquery-observability`.

## Table of Contents

-   [Diagnostic Workflows by Symptom & Root Cause](#diagnostic-workflows-by-symptom-root-cause)
    (Lines 23-105)
    -   [1. Reservation Baseline & Autoscale Modifications](#1-reservation-baseline-autoscale-modifications)
        (Lines 25-45)
    -   [2. Active Capacity Commitment Timeline & Expiration](#2-active-capacity-commitment-timeline-expiration)
        (Lines 47-68)
    -   [3. Reservation Assignment Reconfigurations](#3-reservation-assignment-reconfigurations)
        (Lines 70-86)
    -   [4. Autoscaling Headroom Saturation & Capacity Ceilings](#4-autoscaling-headroom-saturation-capacity-ceilings)
        (Lines 88-105)
-   [Remediation & Recommendations](#remediation-recommendations) (Lines
    107-117)

## Diagnostic Workflows by Symptom & Root Cause

### 1. Reservation Baseline & Autoscale Modifications

-   **When to Use / Symptoms**: Sudden query queueing or slowness starting at a
    specific timestamp, and you suspect an uncoordinated or accidental
    reservation capacity reduction.
-   **Potential Root Causes**: `slot_capacity` lowered, `autoscale.max_slots`
    cap decreased, or reservation idle slot setting changed.
-   **Key Telemetry & Tables**:
    -   **Table**: `INFORMATION_SCHEMA.RESERVATION_CHANGES_BY_PROJECT` (in the
        reservation admin project and region).
    -   **Filters**: `reservation_name = 'RESERVATION_NAME'`,
        `change_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30
        DAY)`.
    -   **Key Fields**: `change_timestamp`, `action`, `reservation_name`,
        `slot_capacity` (new baseline slots), `autoscale.max_slots` (new
        autoscale cap), `user_email`.
-   **Diagnostic Procedure & Telemetry**: See the `bigquery-observability` skill
    (`references/capacity_and_configuration_queries.md`, section "Auditing
    Reservation & Assignment Configuration Changes", querying
    `RESERVATION_CHANGES_BY_PROJECT`) to audit modification timestamps, new slot
    capacities, and user emails.

### 2. Active Capacity Commitment Timeline & Expiration

-   **When to Use / Symptoms**: Reservation total slot capacity dropped suddenly
    without explicit edits to reservation objects, causing widespread job
    queueing.
-   **Potential Root Causes**: Annual or multi-year capacity commitment expired,
    was deleted, or failed to auto-renew.
-   **Key Telemetry & Tables**:
    -   **Table & CLI**:
        `INFORMATION_SCHEMA.CAPACITY_COMMITMENT_CHANGES_BY_PROJECT` or CLI
        command `bq show --capacity_commitment=true --location={location}
        {commitment_id}`.
    -   **Filters**: `change_timestamp >= TIMESTAMP_SUB(...)`,
        `capacity_commitment_id`.
    -   **Key Fields**: `change_timestamp`, `action`, `slot_count`,
        `commitment_plan` (e.g., `ANNUAL`, `THREE_YEAR`), `renewal_plan`,
        `user_email`.
-   **Diagnostic Procedure & Telemetry**: See the `bigquery-observability` skill
    (`references/capacity_and_configuration_queries.md`, section "Auditing
    Reservation & Assignment Configuration Changes", querying
    `CAPACITY_COMMITMENT_CHANGES_BY_PROJECT`) or inspect active commitments via
    REST CLI (`bq show --capacity_commitment`).

### 3. Reservation Assignment Reconfigurations

-   **When to Use / Symptoms**: Workload in a specific project or folder
    experiences degraded performance after administrative reorganization or
    migration.
-   **Potential Root Causes**: Project assignment moved to a different
    reservation with lower capacity.
-   **Key Telemetry & Tables**:
    -   **Table**: `INFORMATION_SCHEMA.ASSIGNMENT_CHANGES_BY_PROJECT`.
    -   **Filters**: `assignee_id = 'PROJECT_OR_FOLDER_ID'`,
        `change_timestamp >= TIMESTAMP_SUB(...)`.
    -   **Key Fields**: `change_timestamp`, `action`, `assignee_id`, `job_type`,
        `reservation_name`, `user_email`.
-   **Diagnostic Procedure & Telemetry**: See the `bigquery-observability` skill
    (`references/capacity_and_configuration_queries.md`, section "Auditing
    Reservation & Assignment Configuration Changes", querying
    `ASSIGNMENT_CHANGES_BY_PROJECT` filtered by `assignee_id`).

### 4. Autoscaling Headroom Saturation & Capacity Ceilings

-   **When to Use / Symptoms**: Bursty or concurrent queries experience
    unexpected throttling or queueing despite autoscaling being active.
-   **Potential Root Causes**: Workload demand exceeded the configured
    `autoscale.max_slots` ceiling, or slot borrowing was disabled
    (`ignore_idle_slots = TRUE`).
-   **Key Telemetry & Tables**:
    -   **Table**: `INFORMATION_SCHEMA.RESERVATIONS_TIMELINE_BY_PROJECT`.
    -   **Filters**: `period_start >= TIMESTAMP_SUB(...)`, `reservation_name =
        'RESERVATION_NAME'`.
    -   **Key Fields**: `slots_assigned` (baseline slots), `max_slots` (scaling
        cap), `autoscale.current_slots`, `autoscale.max_slots`,
        `per_second_details`, `scaling_mode` (`ALL_SLOTS`, `AUTOSCALE_ONLY`),
        `is_creation_region` (primary vs failover).
-   **Diagnostic Procedure & Telemetry**: See the `bigquery-observability` skill
    (`references/capacity_and_configuration_queries.md`, section "Reservation
    Slot Capacity & Autoscaling Saturation Timeline (1-Second Resolution)").

## Remediation & Recommendations

-   **Restore Autoscale Max Slot Limits**: Increase `autoscale.max_slots` on the
    reservation to accommodate peak bursty query traffic without queueing.
-   **Manage Commitment Auto-Renewal**: Ensure auto-renew is enabled on active
    capacity commitments to prevent unexpected capacity drop-offs.
-   **Isolate Critical Workloads**: Move latency-sensitive production queries to
    a dedicated reservation with guaranteed baseline slots and separate
    autoscale headroom.
-   **Enable Idle Slot Sharing**: Ensure `ignore_idle_slots` is set to `FALSE`
    unless strict multi-tenant isolation is required.
