# Investigating validation results

A drill-down procedure for deciding which differences matter and what to fix.
Field and table definitions are in the [results reference](results.md).

Placeholders: `PROJECT` is the results project (`results.projectId`, default
the target project), `DATASET` the results dataset (default
`validation_results`), `RUN_ID` a run ID from `run_history`, and `RUN_KEY` the
run ID as it appears in per-run table names, after the leading `run_`. Default
run IDs have no `run_` prefix (for example `20261026101500_8f3a`, giving
`run_20261026101500_8f3a_mismatches_details`); copy `RUN_KEY` from the table
list query in Section 5 of the [results reference](results.md).

## Contents

*   [0. Before starting](#0-before-starting): Lines 25-33
*   [1. All tables](#1-all-tables): Lines 35-94
*   [2. One table, by pillar](#2-one-table-by-pillar): Lines 96-164
*   [3. Partitions](#3-partitions): Lines 166-198
*   [4. Rows](#4-rows): Lines 200-241
*   [5. Diagnose](#5-diagnose): Lines 243-261
*   [6. Fix, re-run, compare](#6-fix-re-run-compare): Lines 263-285
*   [7. Report](#7-report): Lines 287-301

## 0. Before starting

*   Confirm that the backend finished: the workflow is done, or the run's
    `run_history.status` is no longer `IN_PROGRESS`.
*   Choose the surface. For one table and a quick status, `results.json` in the
    run directory is enough. For several tables, partitions, rows, or history,
    use BigQuery.
*   Query aggregates first and read rows last, with `LIMIT`. Mismatch tables
    contain customer data.

## 1. All tables

Latest run per table pair with the numbers that rank problems:

```sql
WITH latest AS (
  SELECT run_id, source_table, target_table, status, started_at, error_message
  FROM `PROJECT.DATASET.run_history`
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY source_table, target_table ORDER BY started_at DESC) = 1
),
head AS (
  SELECT run_id, metrics_json AS m
  FROM `PROJECT.DATASET.run_metrics`
  WHERE slice_id = 'HEAD'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY run_id ORDER BY timestamp DESC) = 1
)
SELECT
  l.source_table, l.target_table, l.run_id, l.status, l.error_message,
  CAST(JSON_VALUE(h.m, '$.source_total_row_count') AS INT64) AS src_rows,
  CAST(JSON_VALUE(h.m, '$.target_total_row_count') AS INT64) AS tgt_rows,
  CAST(JSON_VALUE(h.m, '$.source_only_row_count') AS INT64) AS missing_in_bq,
  CAST(JSON_VALUE(h.m, '$.target_only_row_count') AS INT64) AS extra_in_bq,
  CAST(JSON_VALUE(h.m, '$.mismatch_count') AS INT64) AS mismatched_rows,
  JSON_VALUE(h.m, '$.sample_coverage') AS sample_coverage,
  JSON_VALUE(h.m, '$.run_schema') AS ran_schema,
  JSON_VALUE(h.m, '$.run_aggregate') AS ran_aggregate,
  JSON_VALUE(h.m, '$.run_data') AS ran_data,
  JSON_VALUE(h.m, '$.source_partition_filter') AS where_filter
FROM latest l LEFT JOIN head h USING (run_id)
ORDER BY l.status = 'ERROR' DESC, mismatched_rows DESC;
```

Read the result in this order:

1.  `ERROR` runs: the comparison did not happen. Fix `error_message` causes
    first (permissions, missing target table, config); they are not data
    findings.
2.  Total row counts differ: rows were lost or added. Highest impact. The
    target count is filled in only when the aggregate pillar ran
    (`ran_aggregate`); data-only runs report `tgt_rows` as 0, which means not
    counted, not lost rows. Use a `--validation-types=schema,aggregate` run
    for row counts.
3.  Rows missing from BigQuery in the sample (`missing_in_bq`). Rows that
    exist only in BigQuery are not reported here (`extra_in_bq` stays 0); they
    show up only as a total row count or `COUNT` aggregate difference.
4.  Value mismatches (`mismatched_rows`).
5.  `HEALED` and `COMPLETED`: pass.

This shows only the latest run per table pair, not overall parity. A later
narrower re-run (only some `--validation-types`, or a `--where` range) replaces
an earlier full run here, and can hide a failure the full run found. Check the
scope: `ran_schema`, `ran_aggregate`, and `ran_data` say which pillars ran, and
a non-empty `where_filter` means only that range was compared. For a narrower
latest run, also read the earlier runs of that table in `run_history`.

Without BigQuery, read each table's `results.json` (`overallStatus`,
`sourceTotalRowCount`, `targetTotalRowCount`, `sourceOnlyRowCount`,
`targetOnlyRowCount`, `mismatchCount`). `targetTotalRowCount` is also 0 in
data-only runs.

## 2. One table, by pillar

Work through the pillars in this order. Each step can explain the next, so stop
when the cause is clear.

**Schema**: Columns whose types are not compatible:

```sql
SELECT JSON_VALUE(c, '$.name') AS col,
       JSON_VALUE(c, '$.compatibility') AS compatibility,
       JSON_VALUE(c, '$.source_type') AS source_type,
       JSON_VALUE(c, '$.target_type') AS target_type,
       CAST(JSON_VALUE(c, '$.mismatch_count') AS INT64) AS mismatches
FROM `PROJECT.DATASET.run_metrics`,
  UNNEST(JSON_QUERY_ARRAY(metrics_json, '$.column_metrics')) AS c
WHERE run_id = 'RUN_ID' AND slice_id = 'HEAD'
  AND JSON_VALUE(c, '$.compatibility') NOT IN ('COMPATIBLE', 'WIDENED', '')
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY JSON_VALUE(c, '$.name') ORDER BY timestamp DESC) = 1;
```

**Aggregates**: Failed checks cover 100% of rows, so they size the problem:

```sql
SELECT JSON_VALUE(a, '$.column_name') AS col,
       JSON_VALUE(a, '$.function') AS fn,
       JSON_VALUE(a, '$.source_value') AS source_value,
       JSON_VALUE(a, '$.target_value') AS target_value,
       JSON_VALUE(a, '$.diff') AS diff
FROM `PROJECT.DATASET.run_metrics`,
  UNNEST(JSON_QUERY_ARRAY(metrics_json, '$.aggregate_metrics')) AS a
WHERE run_id = 'RUN_ID' AND slice_id = 'HEAD'
  AND JSON_VALUE(a, '$.match_result') = 'false'
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY JSON_VALUE(a, '$.column_name'), JSON_VALUE(a, '$.function')
  ORDER BY timestamp DESC) = 1;
```

How to read failed aggregates:

*   `COUNT` of a column differs but table row counts match: `NULL` handling
    (empty strings, defaults).
*   Table `COUNT` differs: missing or extra rows; go to Section 3.
*   `SUM_LENGTH` differs, `COUNT` matches: padding or truncation.
*   `SUM`/`AVG` differ by a tiny relative amount: precision; differ a lot: wrong
    values or missing rows.
*   `MIN`/`MAX` differ: the boundary values (often time zone or truncation).

**Rows and columns**: Rows missing from BigQuery come from the HEAD metrics
(Section 1). Per-column value differences:

```sql
SELECT JSON_VALUE(c, '$.name') AS col,
       JSON_VALUE(c, '$.diff_method') AS method,
       CAST(JSON_VALUE(c, '$.mismatch_count') AS INT64) AS mismatches,
       CAST(JSON_VALUE(c, '$.min_diff') AS FLOAT64) AS min_diff,
       CAST(JSON_VALUE(c, '$.avg_diff') AS FLOAT64) AS avg_diff,
       CAST(JSON_VALUE(c, '$.max_diff') AS FLOAT64) AS max_diff
FROM `PROJECT.DATASET.run_metrics`,
  UNNEST(JSON_QUERY_ARRAY(metrics_json, '$.column_metrics')) AS c
WHERE run_id = 'RUN_ID' AND slice_id = 'HEAD'
  AND CAST(JSON_VALUE(c, '$.mismatch_count') AS INT64) > 0
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY JSON_VALUE(c, '$.name') ORDER BY timestamp DESC) = 1
ORDER BY mismatches DESC;
```

The same numbers are in `results.json` (`columnMismatchStats`, `aggregateStats`,
`columnTypeComparisons`).

## 3. Partitions

Only for partitioned runs (more than one `slice_id`). Shows whether a problem is
local or everywhere:

```sql
SELECT slice_id,
       JSON_VALUE(metrics_json, '$.source_partition_filter') AS slice_filter,
       JSON_VALUE(metrics_json, '$.overall_status') AS status,
       CAST(JSON_VALUE(metrics_json, '$.source_only_row_count') AS INT64)
         AS missing_in_bq,
       CAST(JSON_VALUE(metrics_json, '$.target_only_row_count') AS INT64)
         AS extra_in_bq,
       CAST(JSON_VALUE(metrics_json, '$.mismatch_count') AS INT64)
         AS mismatched_rows
FROM `PROJECT.DATASET.run_metrics`
WHERE run_id = 'RUN_ID' AND slice_id != 'HEAD'
QUALIFY ROW_NUMBER() OVER (PARTITION BY slice_id ORDER BY timestamp DESC) = 1
ORDER BY IFNULL(missing_in_bq, 0) + IFNULL(extra_in_bq, 0)
  + IFNULL(mismatched_rows, 0) DESC;
```

*   Problems concentrated in a few slices (one date range, one key range): a
    load or extract most likely failed for that range. Before re-loading,
    confirm the rows are really absent: look up a few missing keys from the
    run's `mismatches` table in both systems (Section 4), or compare that
    range's row counts directly. A filter or key difference on one range can
    look the same, and a re-load is expensive. Then re-load the range and re-run
    validation for that range only (Section 6). No config change.
*   Problems spread evenly across slices: a systematic conversion difference.
    Continue to Section 4 to identify it.

Per-slice aggregates are in `run_<run>_<slice>_agg_joined`.

## 4. Rows

Find the run's tables (Section 5 of the [results reference](results.md)), then
profile the mismatched cells before reading any rows:

```sql
SELECT column_name, failure_type, COUNT(*) AS cells,
       MIN(distance) AS min_d, MAX(distance) AS max_d,
       APPROX_TOP_COUNT(distance, 5) AS common_distances,
       COUNTIF(source_value IS NULL) AS src_null,
       COUNTIF(target_value IS NULL) AS tgt_null
FROM `PROJECT.DATASET.run_RUN_KEY_mismatches_details`
GROUP BY column_name, failure_type
ORDER BY cells DESC;
```

Then read a few examples of the top pattern:

```sql
SELECT __s_comparison_id, source_value, target_value, distance
FROM `PROJECT.DATASET.run_RUN_KEY_mismatches_details`
WHERE column_name = 'COLUMN' AND failure_type = 'DATA_DRIFT'
ORDER BY ABS(distance) DESC
LIMIT 10;
```

For rows missing from BigQuery, list keys from the `mismatches` table:

```sql
SELECT __s_comparison_id
FROM `PROJECT.DATASET.run_RUN_KEY_mismatches`
WHERE __source_only_row
LIMIT 20;
```

Check a few of those keys directly in the source and in BigQuery before
concluding rows are lost; a filter or key difference can look the same.

Rows that exist only in BigQuery never appear in the `mismatches` table, even
with `brute_force`. When the target row count or `COUNT` aggregate is higher,
find the extra keys with a direct anti-join: load the source comparison keys
into a BigQuery table, then select target rows whose key has no match there.

## 5. Diagnose

Pattern in the evidence                                                                | Likely cause                                           | Fix
:------------------------------------------------------------------------------------- | :----------------------------------------------------- | :--
One distance value dominates on a timestamp (for example 3.6e9 or 1.8e10 microseconds) | Time zone offset                                       | Align types or add a `transformExpression`; confirm which side is right
Tiny absolute numeric distances (for example 1e-8)                                     | Float versus decimal precision                         | `tolerance` on the column
`EDIT_DISTANCE` equals trailing space count, `SUM_LENGTH` differs                      | `CHAR(n)` padding                                      | `transform: TRIM`
One side `NULL`, other side `''`                                                       | Empty string versus `NULL` (Oracle)                    | `transform: EMPTY_TO_NULL`
Case-only differences                                                                  | Collation                                              | `transform: UPPER` or `LOWER`
`ROW` mismatches clustered in some slices                                              | Partial load or extract                                | Re-load the range
`ROW` mismatches spread evenly, total row counts match                                 | Wrong or non-unique comparison key, or filter mismatch | Fix `comparisonKeys` or `whereClause`
Large, varied numeric distances                                                        | Wrong values (bad transformation)                      | Fix the migration logic; do not tolerate
`NARROWED`/`LOSSY_CONVERSION` plus value mismatches                                    | DDL loses data                                         | Change the BigQuery column type

More signatures and config examples: [troubleshooting](troubleshooting.md).

A config fix (tolerance, transform, exclude) is right only for representation
differences. If values are actually wrong or missing, the fix belongs in the
migration, and the finding should be reported as a defect.

## 6. Fix, re-run, compare

1.  Change the config for the affected table and column only.
2.  Re-run just that table, and just the affected range when the problem is
    local:

    ```bash
    gcloud alpha bq migration validation run validation_config/ \
        --location=us --tables=shipments \
        -- --where="ship_date = '2025-11-02'"
    ```

3.  Compare the two runs per column:

    ```sql
    SELECT source_column_name, target_column_name, run_id, status, mismatch_count, run_timestamp
    FROM `PROJECT.DATASET.column_history`
    WHERE source_table = 'SOURCE_TABLE'
    ORDER BY source_column_name, run_timestamp DESC;
    ```

    `status` can be `MISMATCH` with `mismatch_count` 0 when only an aggregate
    failed, so rank columns by `mismatch_count`.

## 7. Report

Summarize from the top again (Section 1 query after the last runs):

*   Tables that pass (`COMPLETED`, `HEALED`), counted only when every pillar
    and the whole table passed: either the latest run covered all of them (no
    `where_filter`), or each earlier run of the missing pillars or ranges also
    passed.
*   Tables with explained, accepted differences, and the config that accepts
    them (tolerance, transform), with the evidence.
*   Tables with defects to fix in the migration: what, where (columns,
    partitions), how many rows, and example keys.
*   Runs that errored and why.
*   Where to look: the results dataset, the run directories, and the web UI
    link if the client printed a real URL (not a placeholder).
