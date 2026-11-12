# Validation results reference

What the backend writes, where, and what each status and field means. For the
order in which to read it, see the [investigation workflow](investigation.md).

## Contents

*   [1. Statuses](#1-statuses): Lines 18-37
*   [2. Where results live](#2-where-results-live): Lines 39-48
*   [3. Cloud Storage artifacts](#3-cloud-storage-artifacts): Lines 50-98
*   [4. BigQuery observability tables](#4-bigquery-observability-tables): Lines 100-142
*   [5. BigQuery per-run tables](#5-bigquery-per-run-tables): Lines 144-185
*   [6. Cloud Storage versus BigQuery](#6-cloud-storage-versus-bigquery): Lines 187-204
*   [7. Row and cell classification](#7-row-and-cell-classification): Lines 206-221
*   [8. Diff methods and distances](#8-diff-methods-and-distances): Lines 223-251
*   [9. Type compatibility notes](#9-type-compatibility-notes): Lines 253-271

## 1. Statuses

Status                      | Meaning                                                              | Report as
:-------------------------- | :------------------------------------------------------------------- | :--------
`COMPLETED`                 | Compared; everything matched within tolerance                        | Pass
`HEALED`                    | Compared; only negligible numeric noise remained (below)             | Pass, mention the noise
`COMPLETED_WITH_MISMATCHES` | Compared; differences found                                          | Finished with findings, not a failure
`ERROR`                     | The comparison itself failed (permissions, missing table, SQL error) | Run failure; read `error_message`
`SKIPPED`, `ESCALATED`      | Not compared, or handed off for review                               | Say so
`IN_PROGRESS`               | Backend still working                                                | Wait

`HEALED` replaces `COMPLETED_WITH_MISMATCHES` only when all of these hold: no
rows are missing on either side, every mismatched column's differences are
negligible (maximum difference below 1e-4, or mean below 1e-4 with standard
deviation below 1e-3), and every failed aggregate differs by less than 1e-6. It
typically means floating-point noise. If a user needs exact equality, look at
the mismatch counts anyway.

A partitioned run's overall status is the worst of its slices
(`COMPLETED_WITH_MISMATCHES` over `HEALED` over `COMPLETED`).

## 2. Where results live

Surface                     | Location                                                                        | Written
:-------------------------- | :------------------------------------------------------------------------------ | :------
Cloud Storage run directory | `<gcsPath>/validationOutputs/<table path>/<run_id>/`                            | Client (inputs) and backend (reports, at the end)
BigQuery results dataset    | `<results.projectId or target project>.<results.dataset or validation_results>` | Backend, during and after the run
Web UI                      | Link printed by the client                                                      | Reads BigQuery

The run directory path is also in `run_state.json` (`gcs_paths`) and in
`run_history.gcs_uri`.

## 3. Cloud Storage artifacts

Run directory contents:

File                                   | Writer  | Content
:------------------------------------- | :------ | :------
`<table>_sample_1.parquet` (or `.csv`) | Client  | Source row sample (under `slices/<id>/` when partitioned)
`source_aggregates.*`                  | Client  | Source-side aggregate values
`source_query_result.json`             | Client  | Source row counts and column metadata
`sample_metadata.json`                 | Both    | Run configuration handed to the backend
`manifest.jsonl`                       | Client  | Slice list for partitioned runs
`run.log`                              | Client  | Client log
`results.json`                         | Backend | Machine-readable run summary (below)
`validation_summary.txt`               | Backend | Human-readable run summary
`column_details.txt`                   | Backend | Human-readable per-column breakdown
`queries.sql`                          | Backend | Comparison SQL that ran

The four backend files are written once, when the whole run (all slices) has
finished. If they are missing, the run is still in progress or failed before the
end; check `run_history`.

### results.json

`{"startedAt", "finishedAt", "tables": {...}}`, where `tables` is a single
object for the run's table pair (not a list). Fields in `tables`:

Group      | Fields
:--------- | :-----
Status     | `overallStatus`, `errorMessage`, `strategy`, `runSchema`, `runAggregate`, `runData`
Identity   | `sourceTable`, `targetTable`, `sourceConnection`, `targetConnection`, `comparisonKeys`, `excludeColumns`, `labels`
Rows       | `sourceTotalRowCount`, `targetTotalRowCount`, `sourcePartitionRowCount`, `targetPartitionRowCount`, `sourcePartitionFilter`, `targetPartitionFilter`, `sourceRowsQueried`, `joinedRowCount`, `sourceOnlyRowCount`, `targetOnlyRowCount`, `rowLimit`
Sampling   | `samplesCollected`, `confidence`, `joinStability`
Mismatches | `mismatchCount`, `mismatchRate`, `contentCellMismatches`, `structuralCellMismatches`, `logicalRowMismatches`, `tableDataDriftCells`, `tableSchemaCells`, `tableRowCells`, `tableExactMatchCells`
Columns    | `columnsInComparison`, `sourceIncludedColumnCount`, `sourceExcludedColumnCount`, `columnTypeComparisons[]`, `typeSummary`, `structuralMismatchesPerColumn{}`
Per column | `columnMismatchStats{col: {mismatchCount, diffMethod, diffStats{min, max, avg, maxDelta, sumDelta, sumDeltaSq, rowCount, metricRowCount}}}`
Aggregates | `aggregateStats{"<col>_<FUNCTION>": {...}}`
Timing     | `sourceExecutionTimeMs`, `targetExecutionTimeMs`
SQL        | `sqlSections[]`

Read it with `gcloud storage cat RUN_DIR/results.json`. For partitioned runs it
holds the rolled-up totals only; per-partition numbers are only in BigQuery.

### validation_summary.txt and column_details.txt

Formatted for people: status per pillar, links to the BigQuery results and the
Cloud Storage directory, row counts, sample coverage, mismatch summary, type
differences, and per-column type compatibility, mismatch rate, distance
statistics, and aggregate table. Show them to the user or link them; read the
same numbers from `results.json` or BigQuery instead of parsing the text.

## 4. BigQuery observability tables

All in the results dataset. Query the views; the `_raw` tables back them.

Object                               | Grain                                     | Key columns
:----------------------------------- | :---------------------------------------- | :----------
`run_history` (view)                 | One row per run (one table pair)          | `run_id`, `status`, `started_at`, `finished_at`, `source_table`, `target_table`, `source_connection`, `target_connection`, `gcs_uri`, `config_hash`, `config_json`, `error_message`, `labels`
`run_metrics` (view)                 | One row per write per (run, slice)        | `run_id`, `slice_id`, `validation_pillar`, `status`, `timestamp`, `metrics_json`, plus projected scalar columns
`column_history`                     | One row per (run, column), whole run only | `run_id`, `source_table`, `target_table`, `source_column_name`, `target_column_name`, `status` (`MATCH`/`MISMATCH`), `mismatch_count`, `run_timestamp`
`run_history_raw`, `run_metrics_raw` | Storage behind the views                  | `history_json`, `metrics_json`

Rules for querying `run_metrics`:

*   **`slice_id = 'HEAD'`** is the whole-run row. Partitioned runs also have one
    row per slice (other `slice_id` values).
*   **Deduplicate**: Retries append rows. Keep the latest per (run, slice):
    `QUALIFY ROW_NUMBER() OVER (PARTITION BY run_id, slice_id ORDER BY timestamp
    DESC) = 1`.
*   **Read fields from `metrics_json`**: Some projected view columns are not
    populated. `JSON_VALUE(metrics_json, '$.<field>')` with the field names
    below always works. Numbers come back as strings; `CAST` them.

`metrics_json` fields (snake case): `overall_status`, `error_message`,
`source_table`, `target_table`, `source_total_row_count`,
`target_total_row_count`, `source_partition_row_count`,
`source_partition_filter`, `target_partition_filter`, `source_rows_queried`,
`joined_row_count`, `source_only_row_count`, `target_only_row_count`,
`mismatch_count`, `mismatch_rate`, `total_mismatches`, `logical_row_mismatches`,
`table_data_drift_cells`, `table_schema_cells`, `table_row_cells`,
`table_exact_match_cells`, `columns_in_comparison`, `sample_coverage`,
`confidence`, `join_stability`, `strategy`, `labels`, `finished_at`, and these
arrays:

*   `column_metrics[]`: `name`, `status`, `mismatch_count`, `diff_method`,
    `source_type`, `target_type`, `compatibility`, `structural_mismatch_count`,
    `min_diff`, `max_diff`, `avg_diff`, `max_delta`, `sum_delta`,
    `sum_delta_sq`, `row_count`, `metric_row_count`
*   `aggregate_metrics[]`: `column_name`, `function`, `source_value`,
    `target_value`, `diff`, `match_result`
*   `sql_sections[]`: `title`, `code`

`run_history.config_json` holds the effective table config, comparison keys,
column settings, and source and target column types for the run.

## 5. BigQuery per-run tables

Created in the results dataset for each run. Names use the run ID; partitioned
runs add the slice ID:

```text
run_<run>_<type>              # unpartitioned run, or run-level union table
run_<run>_<slice>_<type>      # one slice of a partitioned run
run_<run>[_<slice>]_agg_<type>
```

Names use the run ID as written by the backend. List them rather than
guessing. `RUN_KEY` is the run ID as it appears in these names, after the
leading `run_`. Default run IDs are a UTC timestamp and a 4-character suffix
with no `run_` prefix, such as `20261026101500_8f3a` (tables
`run_20261026101500_8f3a_<type>`). In `LIKE`, a distinctive part of it also
works, with any `-` written as `_` (an `_` matches any one character):

```sql
SELECT table_name, table_type
FROM `PROJECT.DATASET.INFORMATION_SCHEMA.TABLES`
WHERE table_name LIKE '%RUN_KEY%'
ORDER BY table_name;
```

Type                       | One row per                          | Columns
:------------------------- | :----------------------------------- | :------
`sample`                   | Staged source row (shared by slices) | Source columns as extracted
`joined`                   | Joined source/target row             | `s_<col>`, `t_<col>`
`mismatches`               | Row with at least one difference     | `__s_comparison_id`, `__t_comparison_id` (key structs), `__source_only_row`, `__target_only_row`, `s_<col>`, `t_<col>`, `<col>_status`, `<col>_distance`
`mismatches_details`       | Mismatched cell (unpivoted)          | `__s_comparison_id`, `__t_comparison_id`, `column_name`, `failure_type`, `source_value`, `target_value` (strings), `distance` (FLOAT64)
`agg_source`, `agg_target` | One row per side                     | `<col>_<FUNCTION>` values
`agg_joined`               | Aggregate check                      | `column_name`, `function`, `source_value`, `target_value`, `diff`, `match_result`

*   For partitioned runs, `run_<run>_<type>` (no slice) is a run-level table
    that unions all slices. Query it for the whole table and the slice tables
    for one partition.
*   `mismatches_details` is the easiest table to aggregate (one cell per row).
    Use `mismatches` when you need the whole row, or the other columns of a row,
    side by side.
*   In hash mode (`useAllColumnsAsKey`), `joined` and `mismatches` carry
    `row_hash`, `source_count`, and `target_count` instead of per-column values.

## 6. Cloud Storage versus BigQuery

Need                                    | `results.json`          | BigQuery
:-------------------------------------- | :---------------------: | :------:
Run status, row counts, mismatch totals | yes                     | yes (`run_metrics` HEAD)
Per-column statistics and type notes    | yes                     | yes (`column_metrics`)
Aggregate results                       | yes                     | yes (`aggregate_metrics`, `agg_joined`)
Per-partition (slice) metrics           | no                      | yes (`run_metrics` slice rows, slice tables)
Mismatched rows and cell values         | no                      | yes (`mismatches`, `mismatches_details`)
History across runs, trends per column  | no                      | yes (`run_history`, `column_history`)
All tables in one query                 | no (one file per table) | yes
Lifecycle while running, error details  | no (written at end)     | yes (`run_history.status`, `error_message`)
Effective config and column types       | partial                 | yes (`config_json`)
Source and target query times           | yes                     | no
Needs only Cloud Storage access         | yes                     | no

Use `results.json` for a fast single-table answer or when BigQuery access is
missing. Use BigQuery for anything comparative, per-partition, or row-level.

## 7. Row and cell classification

`<col>_status` and `failure_type` values:

Value         | Meaning                                                       | Typical cause
:------------ | :------------------------------------------------------------ | :------------
`ROW`         | The row exists on one side only (see row direction below)     | Missing load, filter difference, duplicates, deletes during migration
`SCHEMA`      | The column exists on one side only, or types are incompatible | DDL difference
`DATA_DRIFT`  | Row on both sides, value differs beyond tolerance             | Conversion, precision, padding, time zone, encoding
`EXACT_MATCH` | Equal (never in `mismatches_details`)                         | Not applicable

Row direction: `__source_only_row = TRUE` means missing in BigQuery;
`__target_only_row = TRUE` means present only in BigQuery. Rows that exist only
in BigQuery are not reported at row level, even with `brute_force`:
`target_only_row_count` stays 0 and no `__target_only_row` rows appear. They
show up only in the total row counts and aggregates such as `COUNT`.

## 8. Diff methods and distances

Results record the method as `<CATEGORY>_<METHOD>`: the BigQuery column's type
category (`NUMERIC`, `TEMPORAL`, `STRING`, `BYTES`, `BOOLEAN`, `JSON`) and the
`diffMethod` config value (`SUBTRACTION`, `EDIT_DISTANCE`, `LENGTH`,
`BITWISE_HAMMING_DISTANCE`, `IDENTITY`). Match on these recorded values in
`results.json` (`diffMethod`) and `column_metrics[]` (`diff_method`):

Recorded value                      | Default for                | `distance`
:---------------------------------- | :------------------------- | :---------
`NUMERIC_SUBTRACTION`               | Numeric                    | `target - source` (signed)
`TEMPORAL_SUBTRACTION`              | `DATE`                     | Absolute difference in days
`TEMPORAL_SUBTRACTION`              | `TIMESTAMP`, `DATETIME`    | Absolute difference in **microseconds**
`STRING_EDIT_DISTANCE`              | String                     | Edit distance between the two strings
`STRING_LENGTH`, `BYTES_LENGTH`     | (option for string, bytes) | Absolute length difference
`BYTES_BITWISE_HAMMING_DISTANCE`    | `BYTES`                    | `0` equal, `1` different
`BOOLEAN_IDENTITY`, `JSON_IDENTITY` | `BOOL`, `JSON`             | `NULL` (equal or not)

*   `UNSUPPORTED` means no diff method exists for the column's type (for
    example `TIME`); `HASH_MATCH` means hash mode (`useAllColumnsAsKey`), which
    has no per-column distance.
*   Floating-point columns ignore differences up to 5e-7 even without a
    tolerance.
*   `distance` is `NULL` when either value is `NULL`. A `NULL` on one side is
    still a mismatch; check `source_value`/`target_value`.
*   Column statistics (`min_diff`, `max_diff`, `avg_diff`) cover `DATA_DRIFT`
    cells only and are rounded to 8 decimal places.
*   A one-hour time zone shift shows as a distance of 3,600,000,000 on
    timestamps.

## 9. Type compatibility notes

The schema pillar classifies each column pair:

Note                | Schema pillar | Meaning
:------------------ | :------------ | :------
`COMPATIBLE`        | Pass          | Equivalent types
`WIDENED`           | Pass          | Target holds more (precision, scale, range)
`NARROWED`          | Fail          | Same family, target holds less; overflow or truncation possible
`COERCED`           | Fail          | Different representation, not necessarily lossy (for example `JSON` to `STRING`, `DATE` to `STRING`)
`LOSSY_CONVERSION`  | Fail          | Precision or time components can be lost (integer and float, decimal to float, decimal to integer, `TIMESTAMP` to `DATETIME`/`DATE`/`TIME`, `DATETIME` to `TIMESTAMP`)
`CHANGED_TYPE`      | Fail          | Incompatible families
`MISSING_IN_SOURCE` | Fail          | Column only in BigQuery
`MISSING_IN_TARGET` | Fail          | Column only in the source
`UNKNOWN`           | Fail          | Type could not be read

A schema finding does not mean values differ. Check the column's data mismatches
before recommending a DDL change: a `LOSSY_CONVERSION` column with zero
mismatches is a risk to note, not a defect found.
