# Sampling, partitioning, and scale

How to size samples, split large tables, and keep wide tables within BigQuery
query limits.

## Contents

*   [1. Sample size](#1-sample-size): Lines 15-33
*   [2. Aggregates first](#2-aggregates-first): Lines 34-48
*   [3. Partitioned validation](#3-partitioned-validation): Lines 49-107
*   [4. Wide tables](#4-wide-tables): Lines 108-116
*   [5. Concurrency and memory](#5-concurrency-and-memory): Lines 117-125
*   [6. Timing information](#6-timing-information): Lines 126-132

## 1. Sample size

Row comparison samples rows at random. The chance of seeing at least one bad row
when a fraction `p` of rows is bad is `1 - (1 - p)^n` for `n` sampled rows.

`sampleSize`      | Detects with 99.9% confidence
:---------------- | :----------------------------
`70000` (default) | 1 bad row in 10,000
`700000`          | 1 bad row in 100,000

*   Tables (or slices) smaller than `sampleSize` are compared in full.
*   With `strategy: smart` (default), tables under 100,000 rows are always
    compared in full (`brute_force`).
*   When partitioned, `sampleSize` applies per slice, so total sampled rows grow
    with the number of slices.

Sampling cannot prove that no row is wrong. Aggregates cover every row; use
both, and say what confidence the sample gives when reporting a clean result.

## 2. Aggregates first

Aggregate checks run as push-down queries on both databases and cover 100% of
rows with little data movement. Run them first, together with the schema
check (type compatibility), which is cheap:

```bash
gcloud alpha bq migration validation run validation_config/ \
    --location=us --validation-types=schema,aggregate
```

If row counts differ by `k` rows in `N`, the error density is `k/N`. Size the
row sample from that (Section 1), or narrow the run with `-- --where` to the
affected range.

## 3. Partitioned validation

Large tables are split into slices. Each slice is sampled and compared
separately (sample, aggregates, row comparison), then the backend rolls the
slices up into whole-table results. Per-slice results stay available in
BigQuery, which is what makes local problems (one failed daily load) visible.

When a table is partitioned (first rule that applies):

1.  `disablePartitioning: true` or `--no-partition`: never.
2.  Strategy resolves to `brute_force` (small tables): never.
3.  A `partitioning` block is present: always.
4.  Row count above `partitioning.partitionSize` (default 1,000,000): yes.

Partition type (`partitioning.type`):

Type             | Splits by                                                                           | `partitionSize` unit
:--------------- | :---------------------------------------------------------------------------------- | :-------------------
`AUTO` (default) | Physical partitions for Oracle and partitioned Teradata tables, else integer ranges | as chosen
`INTEGER_RANGE`  | Ranges of an integer column                                                         | rows per slice (default 1,000,000)
`DATE_RANGE`     | Ranges of a date column                                                             | days per slice (default 30)
`PHYSICAL`       | The source table's own partitions                                                   | Not applicable

Daily partitions for a date-partitioned fact table:

```yaml
- sourceTable:
    name: logistics.shipments
    comparisonKeys: [shipment_id]
  targetTable:
    name: logistics_dw.shipments
  partitioning:
    type: DATE_RANGE
    column: ship_date
    partitionSize: 1          # one day per slice
  sampleSize: 10000           # per slice
  maxConcurrency: 4           # slices in parallel
```

*   `DATE_RANGE` is used only when configured; `AUTO` never picks it.
*   Choose the partition column the data was loaded by (load date, batch date),
    so a failed load maps to one slice.
*   `maxSlices` caps the slice count; the run fails with an error if the range
    needs more slices than allowed. Increase `partitionSize` or narrow the range
    with `whereClause`.
*   `rowsPerSlice` overrides the per-slice row limit.

When you configure partitioning, tell the user where per-slice results will be,
because that is why they asked for it:

*   BigQuery `run_metrics` rows with `slice_id` other than `'HEAD'` (one per
    slice; `source_partition_filter` in `metrics_json` names the range).
*   Per-slice tables
    `run_<run>_<slice>_{mismatches,mismatches_details,agg_joined}`.
*   `results.json` and the text summaries hold whole-table totals only.

The query for this is in the
[investigation workflow](investigation.md#3-partitions).

## 4. Wide tables

Tables with hundreds of columns produce comparison queries too large for
BigQuery. The tool splits columns into tiles of `maxColumnsPerTile` columns (100
by default) and compares each tile separately. If a wide table still fails with
a query complexity or resource error, lower `maxColumnsPerTile` (for example
50). Do not exclude columns to get under the limit; excluded columns are not
validated at all.

## 5. Concurrency and memory

*   `maxConcurrency` (per table) or `--max-concurrency N` (all tables): slices
    processed in parallel.
*   Source load grows with concurrency. Keep them low against busy production
    databases.
*   Large samples need client memory: pass `JAVA_OPTS=-Xmx8g` (or more) if the
    client runs out of heap.

## 6. Timing information

Source and target query times per run are in `results.json`
(`sourceExecutionTimeMs`, `targetExecutionTimeMs`); total duration is in
`validation_summary.txt` and `run_history` (`started_at`, `finished_at`).
`--performance` adds timing lines to the client log. There is no separate
performance report.
