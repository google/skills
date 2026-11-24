---
name: bigquery-troubleshooting
metadata:
  version: "1.1.2"
  category: BigDataAndAnalytics
  publisher: google
description: >-
  Provides diagnostic workflows and step-by-step root-cause analysis
  procedures for actively broken, failing, or slow BigQuery jobs, execution
  graph and query plan stage bottlenecks, system performance issues, or
  unexpectedly expensive workloads. Use when interpreting symptoms, isolating
  bottlenecks, diagnosing cost spikes (on-demand query spend, capacity slot
  autoscaling, storage growth), execution graph stages or substep variables,
  identifying root causes, and determining remediation steps. Don't use for
  writing or optimizing SQL, proactive capacity planning, or storage layout
  design (use bigquery-optimization), or when the user already knows which
  telemetry they want and just needs the query (use bigquery-observability).
---

# BigQuery Troubleshooting

## Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read [Usage Attribution](references/attribution.md). For commands executed
directly in the terminal (never in generated scripts, Terraform, or user code),
prefix `gcloud` with
`CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:bigquery-troubleshooting)"`
and append `agent-skills/1.0 (skill:bigquery-troubleshooting)` to `User-Agent` headers.

## Prerequisites & Environment Setup

Before running diagnostic queries or investigating incident telemetry:

1.  **Google Cloud SDK**: Ensure the
    [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) is installed
    and configured.
2.  **Project Selection**: Set the active Google Cloud project:

    ```bash
    gcloud config set project {project_id}
    ```

3.  **API Enablement**: Ensure BigQuery and Cloud Monitoring APIs are enabled:

    ```bash
    gcloud services enable bigquery.googleapis.com monitoring.googleapis.com
    ```

4.  **Authentication**: Authenticate the environment:
    *   CLI commands (`bq show -j`): `gcloud auth login`
    *   SDKs and automated diagnostic scripts:
        `gcloud auth application-default login`
    *   Service accounts: Set
        `GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"`

5.  **Billing & IAM Roles**:
    *   Verify an active Google Cloud Billing account is attached to
        `{project_id}`.
    *   Ensure appropriate IAM roles:
        *   `roles/bigquery.jobUser`: Executing diagnostic queries and
            inspecting your own jobs via CLI (`bq show -j`, `bq ls -j`);
            pair with read roles below to query `INFORMATION_SCHEMA`.
        *   `roles/bigquery.user`: Querying user-scoped job telemetry
            (`JOBS_BY_USER`, `JOBS_TIMELINE_BY_USER`) and executing
            diagnostic queries (supersedes `roles/bigquery.jobUser`).
        *   `roles/bigquery.metadataViewer`: Inspecting table, dataset,
            and storage metadata (`TABLE_STORAGE`,
            `TABLE_STORAGE_USAGE_TIMELINE`, `TABLES`,
            `SCHEMATA_OPTIONS`).
        *   `roles/bigquery.resourceViewer` or `roles/bigquery.admin`:
            Inspecting any user's job (`bq show -j`), project-, folder-,
            or organization-level jobs at the matching resource scope,
            and reservation, capacity commitment, and assignment
            telemetry on the reservations administration project.
            Enabling `TABLE_STORAGE` opt-in via `ALTER PROJECT` requires
            `roles/bigquery.admin`.
        *   `roles/monitoring.viewer`: Reading Cloud Monitoring metrics.
        *   `roles/billing.viewer` (on the Cloud Billing account):
            Viewing Cloud Billing reports and SKU cost attribution.

6.  **Companion Skills Installation**:
    This skill is part of a 3-pillar operations suite (`bigquery-observability`,
    `bigquery-optimization`, `bigquery-troubleshooting`). If any companion skill
    is not yet installed in your environment, install the full suite:

    ```bash
    npx skills add google/skills --skill bigquery-observability --skill bigquery-optimization --skill bigquery-troubleshooting
    ```

    *(If `bigquery-observability` is not installed, use the self-contained
    baseline formulas and query templates provided directly in the reference
    sections below).*

## Workflow

1.  **Scope & Symptom Identification:** Identify the primary symptom, target
    `project_id`, `region`, `reservation_id`, or `job_id`, and domain
    (Performance, Compute Cost, or Storage Cost). If the request falls outside
    incident diagnosis or asks for a sibling domain, follow **Routing
    Boundaries** below.
2.  **Telemetry Tool Selection:** Follow the tool-selection guidance in the
    [BigQuery observability skill](../bigquery-observability)
    (`bigquery_observability`) to select the appropriate telemetry interface
    (REST API `bq show --location={location} -j {project_id}:{job_id}` for
    single-job stage bottlenecks vs. `INFORMATION_SCHEMA` for system-wide
    factors). Diagnostic workflows, symptom-to-cause mappings, key
    tables/fields, CLI triage commands, and remediation levers are fully defined
    in this skill. For pre-composed SQL query templates and full schema
    dictionaries, consult `bigquery-observability`.
3.  **Open-Ended Triage (Stage 1 Baseline Scan & Conversational Gate):** When
    the user inquiry is open-ended or vague (e.g. *"Why is BigQuery slow
    today?"* or *"Why did my bill spike?"*), execute a bounded high-level
    baseline scan to isolate the affected domain before drilling into deep-dive
    diagnostics:
    *   **Bounded Initial Scan:** Follow the baseline scan guidance in the
        corresponding domain reference under **Domain References**. Ensure
        initial queries are strictly bounded (e.g. 7-day Period-over-Period with
        partition and job-type filters; for unspecified cost spikes, scan the 3
        primary vectors: On-Demand TiB, Capacity slot-hours, and Storage GiB) to
        keep diagnostic telemetry overhead minimal.
    *   **Conversational Gate:** Factually summarize high-level baseline
        findings first and propose 2–3 focused drill-down options rather than
        dumping downstream sub-vector queries unsolicited.
4.  **Domain Deep Dive & Comparative Analysis:** Execute the step-by-step
    diagnostic workflow defined in the corresponding domain reference file
    listed under **Domain References** below, then run the corresponding query
    from the [BigQuery observability skill](../bigquery-observability) following
    its `INFORMATION_SCHEMA` best practices to isolate the root cause via
    comparative analysis against a normal baseline.

## Performance Context: The Relativity of "Slow"

Performance is relative. Always approach performance troubleshooting as a
comparative exercise: identify a comparable past execution, compare the
statistics, and isolate which dimension shifted between a fast baseline and the
slow execution:

-   **Data Processed:** Data volume increase, partition/cluster pruning changes,
    data skew, input record amplification.
-   **Underlying Definitions:** View changes, schema modifications.
-   **System Contention:** Noisy neighbors, saturated capacity (>95% slot
    utilization), idle slot availability, concurrent query spikes.
-   **Configuration Changes:** Slot capacity/autoscale max slots changes,
    expired capacity commitments, idle slot setting changes, or reservation
    reassignments.

## Cost Context: The 4-Step Diagnostic Funnel

Cost troubleshooting requires tracing physical resource consumption (Slot-Hours,
TiB Billed, GiB Stored) rather than fluctuating contract rates:

1.  **Gather:** Determine scope and pull 7-day PoP (or explicit MoM / 180-day)
    baseline metrics.
2.  **Isolate:** Pinpoint whether spend surged from query volume, a single
    "Bully Query", BQML 50x multipliers, uncovered PAYG baselines, autoscaling
    bursts, 90-day storage timer resets, or physical Fail-Safe retention drain.
3.  **Explain:** Correlate with administrative events
    (`INFORMATION_SCHEMA.RESERVATION_CHANGES`,
    `INFORMATION_SCHEMA.CAPACITY_COMMITMENT_CHANGES_BY_PROJECT`,
    `INFORMATION_SCHEMA.SCHEMATA_OPTIONS`, or actor `user_email` /
    `query_hash`).
4.  **Remediate:** Deliver actionable levers (partition filter enforcement,
    query caps, commitment purchases, or Time Travel reduction).

## Domain References

### Performance Troubleshooting

-   **Resource Contention & Performance Slowness**
    (`references/performance_resource_contention.md`): Diagnostic workflows for
    isolating single-job stage bottlenecks (`slot_contention`, `spill_to_disk`),
    cohort baseline comparisons (`normalized_literals`), incident window
    discovery, 1-second reservation slot saturation, timeframe contention
    comparisons, fleet performance variance, and table-level concurrency.
-   **Capacity & Configuration Changes**
    (`references/performance_config_changed.md`): Diagnostic workflows for
    auditing reservation `slot_capacity` and `autoscale.max_slots` edits,
    tracking active capacity commitment timelines, diagnosing reservation
    assignment modifications, and evaluating autoscaling headroom saturation.
-   **Execution Graph & Query Plan Troubleshooting**
    (`references/query_plan_execution_graph.md`): Diagnostic workflows for
    investigating single-job stage bottlenecks (`bq show` point-lookups),
    isolating slowest stages (`end_ms - start_ms`), diagnosing join explosions
    (`records_written >> records_read`, `high_cardinality_joins`), shuffle
    spills (`shuffle_output_bytes_spilled`), and partition skew, substep
    intermediate variable disambiguation (`$1`, `$2`), mandatory bytes scanned
    vs records read corrections, and UI execution graph grounding concepts.

### Cost Troubleshooting

-   **On-Demand Compute Costs** (`references/cost_compute_ondemand.md`):
    Diagnostic workflows for unpartitioned runaway scans (the "Bully Query"),
    hidden Row-Level Security (RLS) redaction gaps, BigQuery ML (BQML) 50x model
    training rate multipliers, and user/service account query quotas.
-   **Capacity (Editions) Compute Costs**
    (`references/cost_compute_capacity.md`): Diagnostic workflows for uncovered
    baseline slot penalties (baseline > commitments), reservation baseline
    reductions triggering autoscale surges (`RESERVATION_BASELINE_CHANGED`),
    autoscaler thrashing from batch cron spikes, and serverless Apache Spark
    stored procedure slot-hours.
-   **Storage Footprint & Retention Costs** (`references/cost_storage.md`):
    Diagnostic workflows for historical partition 90-day timer resets (the DML
    trap), unpartitioned table active data traps, physical Time Travel and
    Fail-Safe churn on daily overwrites, and dropped table Fail-Safe drain
    periods.

## Routing Boundaries

If a user request shifts outside incident diagnosis during troubleshooting,
execute the corresponding handoff:

*   **SQL Query Optimizations:** When the user asks to optimize the SQL query
    (e.g., rewriting joins or eliminating `SELECT *`), hand off to
    `bigquery-optimization`.
*   **Raw Telemetry & Schema Retrieval:** When the user asks for standalone
    `INFORMATION_SCHEMA` queries without an active performance regression or
    incident (e.g. general telemetry queries), hand off to
    `bigquery-observability`.
*   **Proactive Capacity & Storage Planning:** When the user requests future
    reservation sizing, commitment purchasing, or storage billing model
    evaluations, hand off to `bigquery-optimization`.
