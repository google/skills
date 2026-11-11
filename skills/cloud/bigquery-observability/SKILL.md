---
name: bigquery-observability
metadata:
  version: "1.2.2"
  category: BigDataAndAnalytics
description: >-
  Provides data-retrieval best practices, tool selection guidance, and
  performant SQL query syntax for BigQuery telemetry across INFORMATION_SCHEMA,
  Cloud Monitoring, and the REST API. Use when the telemetry to fetch is already
  known, selecting telemetry tools, writing performant INFORMATION_SCHEMA
  queries, retrieving telemetry for diagnosing single-job performance
  bottlenecks, investigating slot contention, job concurrency and queue latency,
  analyzing reservation capacity, utilization and autoscaling saturation, or
  auditing capacity-based and on-demand compute and storage resource billable
  usage. Don't use for root-cause diagnosis or symptom troubleshooting when the
  cause is unknown (use bigquery-troubleshooting first), or for writing or
  optimizing business logic SQL (use bigquery-optimization).
---

# BigQuery Observability

## Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read [Usage Attribution](references/attribution.md). For commands executed
directly in the terminal (never in generated scripts, Terraform, or user code),
prefix `gcloud` with
`CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:bigquery-observability)"`
and append `agent-skills/1.0 (skill:bigquery-observability)` to `User-Agent` headers.

## Tool Selection

<!-- mdformat off -->

| Tool | Primary Use Cases | Strengths & Capabilities | When to Avoid / Limitations |
| --- | --- | --- | --- |
| **`INFORMATION_SCHEMA` (`I_S`)** | Historical analysis, cohort comparison (`normalized_literals`), discovery of fast/slow windows, reservation/project timelines, multi-job aggregates, cost/billing tracing. | Flexible SQL querying across `JOBS`, `JOBS_TIMELINE`, and `RESERVATIONS`; supports custom time windows and grouping. | Avoid for high-frequency real-time polling or single-job point-lookups (can consume slots and take seconds to execute). |
| **REST API (`jobs.api` / `reservation.api`)** | Single-job point-lookup, real-time stage bottleneck diagnosis, automated pipeline status checks, reservation/capacity commitment configuration inspection (`reservations.get`, `reservations.list`). | Zero-SQL overhead, fast REST/CLI point-lookups (`bq show -j`, `bq show --reservation`), instant access to `performanceInsights`, `queryPlan`, and structural metadata. | Avoid for aggregate analysis across thousands of jobs, cross-project historical comparison, or system timeline aggregations. |
| **`Cloud Monitoring` (Metrics Explorer / Charts)** | Real-time alerting, fleet-wide dashboards, continuous slot utilization tracking, high-level SLA/SLO monitoring. | Out-of-the-box charts for slot utilization, query throughput, `PENDING` queue depth, and execution latency; low-latency alerting without running queries. | Avoid for SQL-level debugging, individual query text inspection, or stage-level execution detail. |

<!-- mdformat on -->

## Prerequisites & Environment Setup

Before retrieving telemetry or running observability queries, ensure the
Google Cloud environment and project are configured:

1.  **Google Cloud SDK**: Ensure the
    [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) is installed
    and configured.
2.  **Project Selection**: Set the active Google Cloud project:

    ```bash
    gcloud config set project {project_id}
    ```

3.  **API Enablement**: Ensure the BigQuery and Cloud Monitoring APIs are
    enabled:

    ```bash
    gcloud services enable bigquery.googleapis.com monitoring.googleapis.com
    ```

4.  **Authentication**: Authenticate the environment:
    *   CLI queries and `bq` commands: `gcloud auth login`
    *   SDKs and automated client tools:
        `gcloud auth application-default login`
    *   Service accounts: Set
        `GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"`

5.  **Billing & IAM Roles**:
    *   Verify an active Google Cloud Billing account is attached to
        `{project_id}`.
    *   Ensure appropriate IAM roles:
        *   `roles/bigquery.jobUser`: Running telemetry queries.
        *   `roles/bigquery.resourceViewer` or `roles/bigquery.admin`:
            Organization-level jobs and reservation telemetry.
        *   `roles/monitoring.viewer`: Cloud Monitoring metrics.

6.  **Companion Skills Installation**:
    This skill is part of a 3-pillar operations suite (`bigquery-observability`,
    `bigquery-optimization`, `bigquery-troubleshooting`). If any companion skill
    is not yet installed in your environment, install the full suite:

    ```bash
    npx skills add google/skills --skill bigquery-observability --skill bigquery-optimization --skill bigquery-troubleshooting
    ```

## Workflow

1.  **Single-Job Point-Lookup (Zero-SQL Overhead):** For single-job slowness or
    inspection, always prioritize the REST API or CLI (`bq show -j`) first. It
    provides zero-SQL overhead and fast point-lookups for internal stage
    bottlenecks (`performanceInsights`, `queryPlan`, shuffle spill).

    ```bash
    bq show --location={location} -j {project_id}:{job_id}
    ```

2.  **Diagnostic Transition Logic:** If no job-level issues are found (e.g. no
    clear internal bottlenecks), the investigation should transition to
    system-level `INFORMATION_SCHEMA` queries (such as `JOBS_TIMELINE` or
    `RESERVATIONS_TIMELINE`) to check for broader issues like slot contention,
    queueing delay, or noisy neighbors.

## Best Practices for Writing `INFORMATION_SCHEMA` Queries

Every query against a BigQuery `INFORMATION_SCHEMA` view must be qualified with
either a **region qualifier** or a **dataset qualifier**, optionally prefixed by
a **project qualifier**.

### Qualification Syntax & Scope Matching

1.  **Region-Qualified Syntax:**

    ```googlesql
    `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.{view}
    ```

    *Example:* `` `my-project`.`region-us`.INFORMATION_SCHEMA.JOBS``

    *Applies to:* Regional telemetry views (`JOBS*`, `JOBS_TIMELINE*`,
    `RESERVATIONS*`, `CAPACITY_COMMITMENTS*`, `TABLE_STORAGE*`,
    `STREAMING_TIMELINE*`). The client query execution location MUST match the
    `region-{region}` qualifier (or BigQuery throws: `Not found: Table
    {project_id}:region-{region}.INFORMATION_SCHEMA.{view} was not found in
    location {location}`).

2.  **Dataset-Qualified Syntax:**

    ```googlesql
    `{project_id}`.`{dataset_id}`.INFORMATION_SCHEMA.{view}
    ```

    *Example:* `` `my-project`.`analytics`.INFORMATION_SCHEMA.TABLES``

    *Applies to:* Dataset-scoped views (`PARTITIONS`, `SEARCH_INDEXES*`).
    Never use `region-` with dataset views.

3.  **Dual-Scoped Views:** Views like `TABLES`, `COLUMNS`, `COLUMN_FIELD_PATHS`,
    `VIEWS`, `ROUTINES`, and `VECTOR_INDEXES` can be qualified with either
    `{dataset_id}` or `region-{region}` depending on whether dataset or
    region-wide analysis is required.

4.  **Project Qualifier (`{project_id}`):** Optional. If omitted, queries
    default to the project in which the query is executing. Specifying a project
    qualifier on organization-level views (e.g. `JOBS_BY_ORGANIZATION`) has no
    impact on results.

### Principle of Least Privilege & Scope Selection

When constructing `INFORMATION_SCHEMA` queries, **always select the scope and
view variant with the least IAM permission requirement** that satisfies the
analytical need:

1.  **User-Level over Project-Level (`_BY_USER`):** When diagnosing queries or
    sessions executed by the current user, use `_BY_USER` (e.g. `JOBS_BY_USER`,
    `SESSIONS_BY_USER`). This requires only `bigquery.jobs.list` (granted via
    `roles/bigquery.user` or `roles/bigquery.jobUser`), avoiding the need for
    `bigquery.jobs.listAll` or `roles/bigquery.admin`.
2.  **Dataset-Level over Region/Project-Level:** When querying table metadata,
    columns, or views for a specific dataset, qualify with `{dataset_id}` rather
    than `region-{region}` when project-level metadata access is restricted.
    Dataset-scoped queries require permissions only on that target dataset.
3.  **Project-Level over Org/Folder-Level (`_BY_PROJECT`):** Always start with
    project-scoped views before escalating to `_BY_FOLDER` or
    `_BY_ORGANIZATION`. Folder and organization queries require broad folder/org
    IAM permissions (`bigquery.jobs.listAll` or `bigquery.tables.list` at the
    Org/Folder node).
4.  **Metadata Roles over Data Roles:** For table and storage introspection,
    prefer `roles/bigquery.metadataViewer` (which provides `bigquery.tables.get`
    and `bigquery.tables.list`) over `roles/bigquery.dataViewer` or
    `roles/bigquery.dataOwner` when data read access (`bigquery.tables.getData`)
    is not needed. (Note: `INFORMATION_SCHEMA.PARTITIONS` uniquely requires
    `bigquery.tables.getData`).

### Execution Guardrails & Query Invariants

*   **Mandatory Partition & Time Filtering:** Always filter on `creation_time`
    (e.g., `creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 3
    DAY)`) or `usage_date` to avoid full metadata table scans.
*   **Script Wrapper Exclusion:** Add `AND (statement_type != 'SCRIPT' OR
    statement_type IS NULL)` when aggregating compute spend to avoid
    double-counting parent scripts and child jobs.
*   **Column Pruning:** Never use `SELECT *` against `INFORMATION_SCHEMA`; only
    project required columns.
*   **Dry Run & Cost Estimation:** Use a dry run (`bq query --dry_run
    --use_legacy_sql=false "{query}"` or API `dryRun=true`) before executing
    complex queries, multi-view joins, or large scans to validate syntax and
    estimate `totalBytesProcessed` at zero cost.
*   **Empty Regional Scope (0 Rows):** If the execution location matches the
    qualifier, but the project has no datasets or jobs in that region, the query
    succeeds and returns **0 rows**. Never assume 0 rows means 0 usage—always
    verify the target dataset locations.
*   **Non-Hierarchical Region Scope:** Region qualifiers are not hierarchical.
    Multi-regions do not encompass single regions (e.g. `region-us` returns only
    multi-region `US` metadata and does not include single regions like
    `region-us-central1`).
*   **No Multi-Region Aggregation in SQL:** Region qualifiers cannot be joined
    cross-region in a single query (e.g. `region-us` cannot join `region-eu`).
*   **Uncached Execution & Minimum Scan Size:** `INFORMATION_SCHEMA` query
    results are never cached. On-demand queries incur a minimum of 10 MB of data
    processing charges per execution.

## Domain References & SQL Queries

### Telemetry Query Guides

*   **On-Demand Compute: Billed Bytes**
    (`references/compute_ondemand_billable.md`): Authoritative Golden CTE
    (`bytes_billed_cte`), timezone-aligned billing date extraction (PST8PDT),
    BQML CREATE_MODEL 50x multiplier rules, script wrapper deduplication, and
    row-level security (RLS) masking checks.
*   **Capacity Compute: Billable Slots & Commitments**
    (`references/compute_capacity_billable.md`): Query templates for auditing
    billable capacity hours across 1-Year/3-Year commitments, uncovered baseline
    PAYG slots, and dynamic autoscaling hours.
*   **Storage Footprints & Usage (Bytes Stored)**
    (`references/storage_footprints.md`): Storage snapshot queries, compression
    ratio calculations, Time Travel / Fail-Safe churn, daily average GiB
    time-integrals, billing model evaluation, and search index coverage.

### Performance & Troubleshooting Guides

*   **Job Performance Queries** (`references/job_performance_queries.md`):
    Queries for evaluating individual and aggregate job performance, stage
    bottleneck flags, comparable jobs via normalized literals
    (`query_info.query_hashes.normalized_literals`), BI Engine acceleration,
    metadata cache (cmeta) acceleration, search index usage, materialized view
    rewrite usage, and execution variance outliers.
*   **Resource Contention Queries**
    (`references/resource_contention_queries.md`): Queries for diagnosing slot
    contention, queue latency, per-minute concurrency/queue timelines, and
    1-second reservation slot saturation.
*   **Capacity & Configuration Queries**
    (`references/capacity_and_configuration_queries.md`): Queries for evaluating
    second-by-second baseline/max capacity ceilings, autoscaling saturation
    timelines, and auditing configuration changes
    (`RESERVATION_CHANGES_BY_PROJECT`, `ASSIGNMENT_CHANGES_BY_PROJECT`).

### Schema Dictionaries (Column Definitions & Units)

*   **Compute & Capacity Schema Dictionary** (`references/schema_compute.md`):
    Complete column dictionary, physical units, and least-privilege IAM roles
    for all compute, job, session, reservation, capacity commitment, and
    assignment views (`JOBS*`, `JOBS_TIMELINE*`, `SESSIONS_BY_USER`,
    `SESSIONS_BY_PROJECT`, `RESERVATIONS*`, `RESERVATION_CHANGES*`,
    `RESERVATIONS_TIMELINE*`, `CAPACITY_COMMITMENTS*`,
    `CAPACITY_COMMITMENT_CHANGES_BY_PROJECT`, `ASSIGNMENTS*`,
    `ASSIGNMENT_CHANGES_BY_PROJECT`).
*   **Storage & Data Catalog Schema Dictionary**
    (`references/schema_storage.md`): Complete column dictionary, physical
    units, and least-privilege IAM roles for all table storage, partition,
    column, snapshot, dataset, constraint, and replication views
    (`TABLE_STORAGE*`, `TABLE_STORAGE_USAGE_TIMELINE*`, `TABLES*`,
    `TABLE_OPTIONS`, `COLUMNS`, `COLUMN_FIELD_PATHS`, `PARTITIONS`, `VIEWS`,
    `MATERIALIZED_VIEWS`, `TABLE_SNAPSHOTS`, `TABLE_CONSTRAINTS`,
    `KEY_COLUMN_USAGE`, `SCHEMATA*`, `SCHEMATA_OPTIONS`, `SCHEMATA_REPLICAS*`,
    `SCHEMATA_LINKS`, `SHARED_DATASET_USAGE`).
*   **Platform, Governance & Ingestion Schema Dictionary**
    (`references/schema_others.md`): Complete column dictionary, physical units,
    and least-privilege IAM roles for all remaining views including Access
    Control (`OBJECT_PRIVILEGES`), Streaming Ingestion
    (`STREAMING_TIMELINE_BY_PROJECT*`, `WRITE_API_TIMELINE_BY_PROJECT*`),
    Configuration Options (`PROJECT_OPTIONS*`, `EFFECTIVE_PROJECT_OPTIONS`,
    `ORGANIZATION_OPTIONS*`, `ORGANIZATION_OPTIONS_CHANGES`), Insights &
    Recommendations (`RECOMMENDATIONS*`, `INSIGHTS`), and Indexes/BI
    Engine/Routines (`SEARCH_INDEXES*`, `SEARCH_INDEX_COLUMNS`,
    `SEARCH_INDEX_OPTIONS`, `VECTOR_INDEXES*`, `VECTOR_INDEX_COLUMNS`,
    `VECTOR_INDEX_OPTIONS`, `BI_CAPACITIES`, `BI_CAPACITY_CHANGES`, `ROUTINES*`,
    `ROUTINE_OPTIONS`, `PARAMETERS`).
