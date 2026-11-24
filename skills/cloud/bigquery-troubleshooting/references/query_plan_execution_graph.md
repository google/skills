# BigQuery Troubleshooting: Execution Graph & Query Plan

This reference guide provides diagnostic workflows and grounding concepts for
investigating single-job performance bottlenecks, execution graphs, stage-level
operations, and query plan metrics in BigQuery.

## Table of Contents

-   [Diagnostic Workflows](#diagnostic-workflows) (Lines 21-112)
    -   [1. Single-Job Stage Bottleneck Triage & REST API Lookup](#1-single-job-stage-bottleneck-triage-rest-api-lookup)
        (Lines 23-43)
    -   [2. General Telemetry & Stage Metrics Cross-Reference](#2-general-telemetry-stage-metrics-cross-reference)
        (Lines 45-54)
    -   [3. Join Explosion, Shuffle Spill & Partition Skew Diagnosis](#3-join-explosion-shuffle-spill-partition-skew-diagnosis)
        (Lines 56-112)
-   [Execution Graph & UI Grounding Concepts](#execution-graph-ui-grounding-concepts)
    (Lines 114-160)
-   [Strict Disambiguation Invariants](#strict-disambiguation-invariants) (Lines
    162-183)

## Diagnostic Workflows

### 1. Single-Job Stage Bottleneck Triage & REST API Lookup

-   **When to Use / Symptoms**: A query is slow or stalled, and you need to
    isolate whether delay occurred during pending/queueing or within a specific
    execution stage.
-   **Diagnostic Procedure**:
    -   Use the REST API single-job point-lookup via `bq show
        --location={location} --format=prettyjson -j {project_id}:{job_id}` to
        retrieve detailed per-stage execution metrics, timeline events, and
        performance insights. See the `bigquery-observability` skill
        (`references/job_performance_queries.md`, section "REST API Single-Job
        Point-Lookup & Stage Bottlenecks") for the CLI command and field
        definitions.
    -   Inspect `statistics.query.queryPlan` for stage-level compute, input,
        output, and shuffle skew.
    -   **Bottleneck Determination**: Calculate stage duration as `duration =
        end_ms - start_ms`.
    -   **Optimization Target**: Clarify whether the user is optimizing for
        **Slot Time** (Reservations / Flat-rate / Editions) or **Bytes
        Processed** (On-demand pricing) to prioritize the corresponding
        bottleneck stages.

### 2. General Telemetry & Stage Metrics Cross-Reference

For full SQL schema dictionaries, physical units, and column definitions (such
as `records_read`, `records_written`, `shuffle_output_bytes_spilled`, and
`slot_ms` across `job_stages` and `INFORMATION_SCHEMA.JOBS`), see the
`bigquery-observability` skill:

-   `references/schema_compute.md` for raw telemetry metrics and column types.
-   `references/job_performance_queries.md` for SQL-based stage bottleneck
    analysis and historical baseline comparisons.

### 3. Join Explosion, Shuffle Spill & Partition Skew Diagnosis

-   **When to Use / Symptoms**: A query consumes excessive slot-hours, runs out
    of shuffle resources, or stalls in a `Join` or `Aggregate` stage due to
    unintentional `CROSS JOIN`s, missing or non-selective `ON` conditions,
    many-to-many row multiplication (`records_written >> records_read`), disk
    spill (`shuffle_output_bytes_spilled > 0`), or worker skew.
-   **Diagnostic Procedure**:
    -   Unnest `job_stages` and
        `query_info.performance_insights.stage_performance_standalone_insights`
        in `INFORMATION_SCHEMA.JOBS_BY_PROJECT` (see the
        `bigquery-observability` skill, `references/job_performance_queries.md`,
        section "Stage Row Expansion, Shuffle Spill & Join Insights") or inspect
        `statistics.query.queryPlan` and `statistics.query.performanceInsights`
        via `bq show --location={location} --format=prettyjson -j
        {project_id}:{job_id}`.
    -   **Row Expansion Check (`records_written` vs. `records_read`)**: Compare
        `stage.records_written` to `stage.records_read`
        (`SAFE_DIVIDE(stage.records_written, NULLIF(stage.records_read, 0))`)
        and inspect `insight.high_cardinality_joins` (`left_rows`, `right_rows`,
        `output_rows`, `step_index`) to identify stages where output rows
        drastically exceed input rows.
    -   **Join Condition & `CROSS JOIN` Check**: Inspect the query's `JOIN`
        conditions and the `JOIN` step details in the query plan (join pattern
        and join columns) for unintentional `CROSS JOIN`s (or comma cross
        joins), missing `ON` conditions, or non-selective/non-unique join keys
        on both sides of the join. Confirm a Cartesian product by counting rows
        per join key (`GROUP BY` the join key) on each side of the `JOIN`.
    -   **Shuffle Spill & Quota Check**: Check `stage.shuffle_output_bytes`,
        `stage.shuffle_output_bytes_spilled > 0`, and
        `insight.insufficient_shuffle_quota = TRUE` to identify stages spilling
        intermediate data to disk or starving for shuffle quota.
    -   **Wait vs. Skew Check**: Compare `stage.wait_ratio_avg` (`wait_ms_avg`)
        and `stage.wait_ratio_max` (`wait_ms_max`)—and check whether
        `wait_ms_max >> compute_ms_max` (`waitMsMax >> computeMsMax` in
        `queryPlan`)—to detect worker slot starvation and shard scheduling wait
        (`insight.slot_contention = TRUE`), and compare
        `stage.compute_ratio_max` (`compute_ms_max` / `computeMsMax`) against
        `stage.compute_ratio_avg` (`compute_ms_avg` / `computeMsAvg`) alongside
        `insight.partition_skew.skew_sources` (`stage_id`) to isolate hot keys
        overloading a single worker shard.
-   **Remediation & Actions**:
    -   **Eliminate Unintentional `CROSS JOIN`s & Use Selective Join Keys**:
        Ensure every `JOIN` specifies explicit `ON` conditions using selective
        join keys rather than an unintentional `CROSS JOIN` (or replace cross
        joins and self-joins with window functions where applicable).
    -   **Pre-Aggregate Join Inputs Before Joining**: Use a `GROUP BY` clause in
        a CTE to pre-aggregate data on the join key before the `JOIN` (or
        deduplicate non-unique keys) so non-unique keys on both sides do not
        multiply rows, and filter out `NULL` or skewed dummy keys (e.g., `WHERE
        customer_id IS NOT NULL AND customer_id != 'GUEST'`) before joining.
    -   **Filter Early & Order Joins Largest-First**: Push selective `WHERE`
        filters into each table before the `JOIN`, and place the largest table
        first (leftmost) and the smallest table second (rightmost) so BigQuery
        broadcasts the small table (`JOIN EACH WITH ALL`) instead of shuffling
        both inputs (`JOIN EACH WITH EACH`). For SQL rewrite patterns, refer to
        the `bigquery-optimization` skill.

## Execution Graph & UI Grounding Concepts

Base all terminology explanations and console visualization guidance on the
official definitions below:

-   **execution graph**: The visual representation of the query plan stages and
    steps in the BigQuery Console (see the
    [execution graph documentation][execution-graph-docs]).
-   **query plan**: The series of stages and steps BigQuery generates and
    executes to run a query (see the
    [query plan explanation documentation][query-plan-docs]).
-   **stage**: A single execution unit in a query plan containing multiple
    operations/steps executed by worker slots (see the
    [stage overview documentation][stage-overview-docs]).
-   **step**: An individual operation within a stage (such as `READ`, `WRITE`,
    `AGGREGATE`, `JOIN`, or `FILTER`; see the
    [per-stage step information documentation][step-info-docs]).
-   **substep / substep variables**: Intermediate sub-operations within a stage
    step passing data via intermediate variables (such as `$1`, `$2`). These
    variables are unique to that stage and pass expressions or intermediate
    aggregations between operations (see the
    [per-stage step information documentation][step-info-docs]).
-   **slowest stage / bottleneck**: The stage causing the highest latency or
    consuming the largest share of slot resources. Calculate duration as
    `end_ms - start_ms` (see the
    [stage overview documentation][stage-overview-docs]).
-   **summary panel**: Top-level summary panel in BigQuery Console displaying
    overall job duration, bytes processed, and slot usage (see the
    [query plan explanation documentation][query-plan-docs]).
-   **stage details panel**: Side panel in BigQuery Console displaying granular
    stage metrics, worker compute/wait breakdown, and operations (see the
    [execution graph navigation documentation][navigating-graph-docs]).
-   **input stage**: The predecessor stage that provides input data to the
    current stage (see the
    [execution graph documentation][execution-graph-docs]).
-   **output stage**: The successor stage that consumes data produced by the
    current stage (see the
    [execution graph documentation][execution-graph-docs]).
-   **parallel inputs**: The number of workers concurrently processing input
    partitions within a stage (see the
    [stage overview documentation][stage-overview-docs]).
-   **completed parallel inputs**: The number of worker tasks that have finished
    execution within a stage (see the
    [stage overview documentation][stage-overview-docs]).
-   **cache hit**: Indicates whether the query result was served from BigQuery
    cached results (0 bytes billed; see the
    [query plan explanation documentation][query-plan-docs]).

## Strict Disambiguation Invariants

-   **Mandatory Correction (Bytes Scanned in Stage)**: BigQuery **does NOT**
    track *Bytes Scanned* per individual stage. When asked, issue the
    correction:

    > ⚠️ **Correction**: BigQuery does not track *Bytes Scanned* per individual
    > stage. Instead, it tracks **Records Read** (the volume of input rows
    > processed by the stage).

-   **Substep Variables (`$1`, `$2`)**: When asked why steps contain `$` signs,
    clarify that these represent intermediate **substep variables** unique to
    that stage passing data between operations.

-   **Citation Requirement**: Always cite the official documentation link for
    every execution graph concept or metric discussed.

[execution-graph-docs]: https://cloud.google.com/bigquery/docs/query-plan-explanation#understand_the_execution_graph
[navigating-graph-docs]: https://cloud.google.com/bigquery/docs/query-plan-explanation#navigating_the_execution_graph
[query-plan-docs]: https://cloud.google.com/bigquery/docs/query-plan-explanation
[stage-overview-docs]: https://cloud.google.com/bigquery/docs/query-plan-explanation#stage-overview
[step-info-docs]: https://cloud.google.com/bigquery/docs/query-plan-explanation#per-stage_step_information
