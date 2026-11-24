# Query Performance Queries

Telemetry and SQL queries for evaluating individual and aggregate job
performance, discovering comparable job executions, analyzing slot consumption,
identifying query/stage bottlenecks, inspecting table-level job activity, and
verifying BI Engine / metadata cache (cmeta) acceleration.

## Table of Contents

-   [Single Job Performance & Stage Bottleneck Flags](#single-job-performance-stage-bottleneck-flags)
    (Lines 27-76)
-   [REST API Single-Job Point-Lookup & Stage Bottlenecks](#rest-api-single-job-point-lookup-stage-bottlenecks)
    (Lines 77-98)
-   [Finding Comparable Jobs](#finding-comparable-jobs) (Lines 99-130)
-   [BI Engine Acceleration Usage](#bi-engine-acceleration-usage) (Lines
    131-153)
-   [Table Metadata Cache (cmeta) Usage](#table-metadata-cache-cmeta-usage)
    (Lines 154-180)
-   [Search Index Usage](#search-index-usage) (Lines 181-209)
-   [Materialized View Rewrite Usage](#materialized-view-rewrite-usage) (Lines
    210-245)
-   [Query Performance Variance & Outlier Discovery](#query-performance-variance-outlier-discovery)
    (Lines 246-280)
-   [Stage Row Expansion, Shuffle Spill & Join Insights](#stage-row-expansion-shuffle-spill-join-insights)
    (Lines 281-341)

## Single Job Performance & Stage Bottleneck Flags

Retrieve execution duration, queuing delay, compute usage, bytes processed,
historical average duration, and stage bottleneck flags for a specific job.

```sql
SELECT
  job_id,
  user_email,
  state,
  creation_time,
  start_time,
  end_time,
  TIMESTAMP_DIFF(end_time, start_time, MILLISECOND) AS duration_ms,
  TIMESTAMP_DIFF(start_time, creation_time, MILLISECOND) AS pending_ms,
  total_slot_ms,
  ROUND(
    SAFE_DIVIDE(
      total_slot_ms, TIMESTAMP_DIFF(end_time, start_time, MILLISECOND)),
    1) AS avg_slots_used,
  total_bytes_processed,
  total_bytes_billed,
  reservation_id,
  query_info.performance_insights.avg_previous_execution_ms
    AS avg_previous_execution_ms,
  query_info.performance_insights.avg_previous_slot_ms AS avg_previous_slot_ms,
  query_info.performance_insights.avg_previous_bytes_processed
    AS avg_previous_bytes_processed,
  query_info.performance_insights.num_previous_successful_jobs
    AS num_previous_successful_jobs,
  (
    SELECT LOGICAL_OR(slot_contention)
    FROM
      UNNEST(
        query_info.performance_insights.stage_performance_standalone_insights)
  ) AS has_slot_contention,
  (
    SELECT LOGICAL_OR(insufficient_shuffle_quota)
    FROM
      UNNEST(
        query_info.performance_insights.stage_performance_standalone_insights)
  ) AS has_insufficient_shuffle_quota,
  error_result.message AS error_message
FROM
  `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE
  creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
  AND job_id = '{job_id}';
```

## REST API Single-Job Point-Lookup & Stage Bottlenecks

Use the REST API for fast, zero-SQL point-lookups to extract stage-level
execution graphs, wait ratios, and performance insights.

```bash
bq show --location={location} -j {project_id}:{job_id}
```

Key fields in JSON response:

-   `statistics.query.performanceInsights`: Execution bottleneck diagnostics
    (e.g., `stagePerformanceStandaloneInsights[].slotContention`,
    `stagePerformanceStandaloneInsights[].insufficientShuffleQuota`,
    `stagePerformanceChangeInsights[].inputDataChange`,
    `avgPreviousExecutionMs`).
-   `statistics.query.queryPlan[]`: Stage-by-stage stats including `slotMs`,
    `shuffleOutputBytes`, `shuffleOutputBytesSpilled`, `recordsRead`,
    `recordsWritten`, `computeMsAvg`, `computeMsMax`, `waitMsAvg`, `waitMsMax`,
    `computeRatioAvg`, `computeRatioMax`, `waitRatioAvg`, `waitRatioMax`,
    `readRatioAvg`, `readRatioMax`, `writeRatioAvg`, `writeRatioMax`.

## Finding Comparable Jobs

Use `query_info.query_hashes.normalized_literals` to discover past runs of the
same query template and rank by duration to find fast baseline executions.

```sql
SELECT
  job_id,
  creation_time,
  TIMESTAMP_DIFF(end_time, start_time, MILLISECOND) AS duration_ms,
  total_slot_ms,
  ROUND(SAFE_DIVIDE(total_slot_ms, TIMESTAMP_DIFF(end_time, start_time, MILLISECOND)), 1)
    AS avg_slots_used,
  total_bytes_processed,
  total_bytes_billed,
  reservation_id,
  (
    SELECT LOGICAL_OR(slot_contention)
    FROM UNNEST(query_info.performance_insights.stage_performance_standalone_insights)
  ) AS has_slot_contention
FROM
  `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE
  creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 14 DAY)
  AND (statement_type != 'SCRIPT' OR statement_type IS NULL)
  AND state = 'DONE'
  AND query_info.query_hashes.normalized_literals = '{target_normalized_hash}'
ORDER BY
  duration_ms ASC
LIMIT 20;
```

## BI Engine Acceleration Usage

Verify whether queries leveraged BI Engine memory acceleration and diagnose
acceleration rejection reasons.

```sql
SELECT
  job_id,
  creation_time,
  total_slot_ms,
  bi_engine_statistics.bi_engine_mode,
  bi_engine_statistics.acceleration_mode,
  bi_engine_statistics.bi_engine_reasons
FROM
  `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE
  creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 3 DAY)
  AND bi_engine_statistics IS NOT NULL
ORDER BY
  creation_time DESC
LIMIT 50;
```

## Table Metadata Cache (cmeta) Usage

Inspect whether queries leveraged table metadata caching (`cmeta`), check
staleness, and diagnose why metadata caching was unused.

```sql
SELECT
  job_id,
  creation_time,
  total_slot_ms,
  t.table_reference.project_id AS table_project_id,
  t.table_reference.dataset_id AS table_dataset_id,
  t.table_reference.table_id,
  t.unused_reason,
  t.explanation,
  t.staleness_seconds,
FROM
  `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT,
  UNNEST(metadata_cache_statistics.table_metadata_cache_usage) AS t
WHERE
  creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 3 DAY)
  AND (statement_type != 'SCRIPT' OR statement_type IS NULL)
ORDER BY
  creation_time DESC
LIMIT 50;
```

## Search Index Usage

Verify whether queries used a search index (`index_usage_mode` is `UNUSED`,
`PARTIALLY_USED`, or `FULLY_USED`) and diagnose why an index was not used.
`index_unused_reasons` is populated only for `UNUSED` and `PARTIALLY_USED`, so
the `LEFT JOIN` keeps `FULLY_USED` jobs in the result.

```sql
SELECT
  job_id,
  creation_time,
  total_slot_ms,
  total_bytes_processed,
  search_statistics.index_usage_mode,
  unused_reason.code AS unused_reason_code,
  unused_reason.base_table.table_id AS base_table_id,
  unused_reason.index_name
FROM
  `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
LEFT JOIN
  UNNEST(search_statistics.index_unused_reasons) AS unused_reason
WHERE
  creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 3 DAY)
  AND search_statistics IS NOT NULL
ORDER BY
  creation_time DESC
LIMIT 50;
```

## Materialized View Rewrite Usage

Verify whether queries used a materialized view (`chosen`), including queries
that smart tuning rewrote from the base tables, and diagnose why a candidate
view was rejected (`rejected_reason`, for example `NO_DATA`, `COST`, or
`BASE_TABLE_DATA_CHANGE`). A view that is not listed in
`materialized_view_statistics` did not match the query shape. If many views are
considered, the list might be incomplete. Automatic refresh jobs have
`materialized_view_refresh` in the job ID, so the query excludes them; to see
refresh cost instead, query `JOBS_BY_PROJECT` in the view's project without the
`UNNEST`, filter on `job_id LIKE '%materialized_view_refresh_%'`, and read
`total_slot_ms`, `total_bytes_processed`, and
`materialized_view_statistics.materialized_view[SAFE_OFFSET(0)].rejected_reason`.

```sql
SELECT
  job_id,
  creation_time,
  total_slot_ms,
  total_bytes_processed,
  mv.table_reference.dataset_id AS mv_dataset_id,
  mv.table_reference.table_id AS mv_table_id,
  mv.chosen,
  mv.estimated_bytes_saved,
  mv.rejected_reason
FROM
  `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT,
  UNNEST(materialized_view_statistics.materialized_view) AS mv
WHERE
  creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 3 DAY)
  AND job_id NOT LIKE '%materialized_view_refresh_%'
ORDER BY
  creation_time DESC
LIMIT 50;
```

## Query Performance Variance & Outlier Discovery

Identify queries that experienced the highest execution variance compared to
their historical baseline duration (`avg_previous_execution_ms`).

```sql
SELECT
  job_id,
  user_email,
  reservation_id,
  creation_time,
  ROUND(TIMESTAMP_DIFF(end_time, start_time, MILLISECOND) / 1000.0, 1) AS duration_sec,
  ROUND(query_info.performance_insights.avg_previous_execution_ms / 1000.0, 1)
    AS baseline_avg_duration_sec,
  ROUND(
    SAFE_DIVIDE(
      TIMESTAMP_DIFF(end_time, start_time, MILLISECOND),
      query_info.performance_insights.avg_previous_execution_ms),
    2) AS variance_ratio,
  total_slot_ms,
  total_bytes_billed
FROM
  `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE
  creation_time
    BETWEEN TIMESTAMP('{target_start_timestamp}')
    AND TIMESTAMP('{target_end_timestamp}')
  AND state = 'DONE'
  AND (statement_type != 'SCRIPT' OR statement_type IS NULL)
  AND query_info.performance_insights.avg_previous_execution_ms IS NOT NULL
ORDER BY
  variance_ratio DESC
LIMIT 50;
```

## Stage Row Expansion, Shuffle Spill & Join Insights

Unnest `job_stages` in `INFORMATION_SCHEMA.JOBS_BY_PROJECT` across recent jobs
(or filter by `job_id = '{job_id}'` for a single job) to detect join row
explosions (`records_written >> records_read` caused by missing `ON` conditions,
unintentional `CROSS JOIN`s, or non-selective/many-to-many join predicates),
shuffle spills to disk (`shuffle_output_bytes_spilled > 0`), worker scheduling
wait delays (`wait_ratio_avg`, `wait_ms_avg`), and engine-surfaced join/skew
insights (`high_cardinality_joins`, `partition_skew`). Note that `job_stages` is
empty for queries that read from tables with row-level access policies.

```sql
SELECT
  j.job_id,
  j.user_email,
  j.creation_time,
  j.total_slot_ms,
  stage.id AS stage_id,
  stage.name AS stage_name,
  stage.records_read,
  stage.records_written,
  ROUND(
    SAFE_DIVIDE(stage.records_written, NULLIF(stage.records_read, 0)), 2)
    AS row_expansion_ratio,
  stage.shuffle_output_bytes,
  stage.shuffle_output_bytes_spilled,
  stage.slot_ms AS stage_slot_ms,
  stage.wait_ratio_avg,
  stage.wait_ratio_max,
  stage.wait_ms_avg,
  stage.wait_ms_max,
  stage.compute_ratio_avg,
  stage.compute_ratio_max,
  stage.compute_ms_avg,
  stage.compute_ms_max,
  insight.slot_contention,
  insight.insufficient_shuffle_quota,
  insight.high_cardinality_joins,
  insight.partition_skew
FROM
  `{project_id}`.`region-{region}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT AS j,
  UNNEST(j.job_stages) AS stage
LEFT JOIN
  UNNEST(
    j.query_info.performance_insights.stage_performance_standalone_insights)
    AS insight
  ON stage.id = insight.stage_id
WHERE
  j.creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
  AND j.job_type = 'QUERY'
  AND j.state = 'DONE'
  AND (
    stage.records_written > stage.records_read * 10
    OR stage.shuffle_output_bytes_spilled > 0
    OR ARRAY_LENGTH(insight.high_cardinality_joins) > 0
    OR ARRAY_LENGTH(insight.partition_skew.skew_sources) > 0)
ORDER BY
  row_expansion_ratio DESC,
  stage.slot_ms DESC
LIMIT 50;
```
