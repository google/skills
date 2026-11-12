# Validation configuration reference

How to write and audit validation configs.

## Contents

*   [1. Layout and precedence](#1-layout-and-precedence): Lines 14-45
*   [2. Top-level keys](#2-top-level-keys): Lines 47-84
*   [3. Table keys](#3-table-keys): Lines 86-111
*   [4. Comparison keys](#4-comparison-keys): Lines 113-135
*   [5. Column settings](#5-column-settings): Lines 137-175
*   [6. Aggregates and tolerances](#6-aggregates-and-tolerances): Lines 177-221

## 1. Layout and precedence

`gcloud alpha bq migration validation configure` writes a modular directory:

```text
validation_config/
├── connections.yaml                     # connections (+ optional Cloud Storage/results)
├── settings.yaml                        # googleCloudStorage, results, defaults
├── index.yaml
└── databases/<database>/<schema>/<table>.yaml   # one `table:` per file
```

A single `validation-config.yaml` holding everything also works.

How a table file finds its shared settings: the tool walks up from the table
file through parent directories, checking each for `connections.yaml`,
`validation_config/connections.yaml`, or `validation-config.yaml`. The env vars
`BQMS_VALIDATION_CONNECTIONS_PATH` and `BQMS_VALIDATION_SETTINGS_PATH` are only
fallbacks: they are read when no such file is found in any parent directory,
so a config file higher up the tree wins over them.

Order of precedence, lowest to highest:

1.  Root defaults (`tolerance`, `tolerances`, `aggregate`, `labels`), copied
    into every table.
2.  Table-level values.
3.  CLI flags (`--where` and similar replace the table filter; `--no-partition`
    disables partitioning everywhere).
4.  `--json` arguments.

Unknown keys are ignored silently, so a misspelled key has no effect. Check
spelling against this page when a setting seems ignored.

## 2. Top-level keys

```yaml
connections:
  source:                       # names: letters and digits only
    dialect: teradata
    host: td.example.com
    user: migrator              # password from env or Secret Manager
  target:
    dialect: bigquery
    projectId: my-project
    dataset: warehouse          # required; default for unqualified names

googleCloudStorage:
  gcsPath: gs://my-bucket/validation   # required; no trailing slash
  format: PARQUET               # PARQUET (default) or CSV
  compression: SNAPPY           # SNAPPY default for Parquet, GZIP for CSV

results:
  projectId: results-project    # optional; defaults to the target project
  dataset: validation_results   # results dataset in results.projectId

resultTtlHours: 168             # must be > 0
tables: [...]
```

*   Connection names must match `^[a-zA-Z0-9]+$` (no `_` or `-`).
*   The BigQuery target connection needs `projectId` and `dataset`. Without
    `dataset`, `validation run` fails with `dataset is required for BigQuery
    connection`, even when every `targetTable.name` is fully qualified.
*   At least one connection and one table are required.
*   Invalid `format`/`compression` values fall back to the defaults silently.
*   `results.projectId` and `results.dataset` are honored: results and per-run
    tables go to `results.projectId` (default: the target connection's
    project). When `billingProjectId` on the target BigQuery connection is unset
    or blank, BigQuery jobs are billed to `results.projectId` first and fall
    back to the target connection's `projectId`. `results.location` is accepted
    but ignored. Query results in that project, not in the target project.

## 3. Table keys

Key                                    | Default      | Meaning
:------------------------------------- | :----------- | :------
`sourceTable`                          | required     | `name`, `connection`, `comparisonKeys`, `whereClause`, `useAllColumnsAsKey`, `totalTableRowCount`
`targetTable`                          | source name  | Same keys as `sourceTable`
`whereClause`                          | None         | Filter for both sides when the side-specific one is blank
`columnSettings`                       | None         | Section 5
`aggregate`                            | per type     | Section 6
`sampleSize`                           | `70000`      | Rows sampled (per slice when partitioned)
`strategy`                             | `smart`      | `smart`, `sample`, `brute_force`
`partitioning`                         | auto         | `{type, column, partitionSize, rowsPerSlice}`; see [sampling and partitioning](performance_tuning.md)
`disablePartitioning`                  | `false`      | Never split this table
`physicalPartitions`                   | None         | Explicit physical partition list
`maxSlices`                            | `0` (no cap) | Upper bound on slices
`maxConcurrency`                       | `1`          | Slices of this table processed in parallel
`maxColumnsPerTile`                    | `100`        | Columns per comparison query for wide tables
`skipRandomization`                    | `false`      | Take rows in order instead of random sampling
`runSchema`, `runAggregate`, `runData` | None         | Per-table pillar switches
`labels`                               | None         | Key-value labels for the run

`strategy: smart` uses a full comparison (`brute_force`) below 100,000 rows and
sampling above. `brute_force` compares every source row and never partitions;
use it only for small tables or final sign-off of a critical table. With either
strategy, rows that exist only in BigQuery are not reported at row level; they
show up only in total row counts and aggregates such as `COUNT`.

## 4. Comparison keys

Comparison keys are the columns that uniquely identify a row on both sides.
Row-level comparison joins source and target on them, so they decide whether a
difference shows up as a changed value or as a missing row.

*   They work like a primary key but need no constraint in either database.
*   If the table has no unique key, list a composite key that is unique.
*   If no unique combination exists, set `useAllColumnsAsKey: true`. The
    comparison then counts identical rows (hash mode) and reports only rows
    present on one side, not column-level drift.
*   A non-unique key multiplies rows in the join and produces false mismatches.
*   Put `comparisonKeys` under `sourceTable` (or `targetTable`). It is a field
    of the table definition, not of the table entry, so a `comparisonKeys`
    placed directly on the entry does not set the keys.

```yaml
- sourceTable:
    name: retail.order_items
    comparisonKeys: [order_id, line_item_id]
  targetTable:
    name: warehouse.order_items
```

## 5. Column settings

```yaml
columnSettings:
  exclude: ['etl_*', 'blob_payload']     # glob patterns
  columns:
    account_status:
      transform: TRIM
    middle_name:
      transform: EMPTY_TO_NULL
    amount:
      tolerance: 0.01                    # row comparison: max |t - s|
      diffMethod: SUBTRACTION
    cust_id:
      targetColumn: customer_id          # renamed in BigQuery
    created_local:
      transformExpression: "DATETIME(created_local, 'America/New_York')"
```

Transform        | Applies                             | Use for
:--------------- | :---------------------------------- | :------
`TRIM`           | `TRIM(col)`                         | `CHAR(n)` padding
`UPPER`, `LOWER` | Case folding                        | Case-insensitive source collations
`EMPTY_TO_NULL`  | `NULLIF(CAST(col AS STRING), '')`   | Oracle-style empty string versus `NULL`
`NULL_TO_EMPTY`  | `COALESCE(CAST(col AS STRING), '')` | The reverse
`CAST_TO_STRING` | `CAST(col AS STRING)`               | Compare as text

*   Transforms are applied in BigQuery during comparison. Unknown transform
    names are ignored without an error.
*   `transformExpression` is a BigQuery SQL expression in which the column name
    is replaced by the column reference. It takes precedence over `transform`.
    Semicolons are rejected.
*   `exclude` is for unsupported types and columns that legitimately differ
    (load timestamps, surrogate keys). Do not exclude columns to work around
    query size limits; wide tables are split automatically
    (`maxColumnsPerTile`).
*   `diffMethod` overrides how distance is measured: `SUBTRACTION`, `LENGTH`,
    `EDIT_DISTANCE`, `BITWISE_HAMMING_DISTANCE`, `IDENTITY` (see
    [results reference](results.md)).

## 6. Aggregates and tolerances

Default aggregates per type:

Column type                             | Aggregates
:-------------------------------------- | :---------
Integer, `NUMERIC`, `BIGNUMERIC`        | `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`
Floating point                          | `COUNT`, `MIN`, `MAX`
`BOOLEAN`                               | `COUNT`, `COUNT_TRUE`, `COUNT_FALSE`, `COUNT_NULL`
String                                  | `COUNT`, `SUM_LENGTH`
`DATE`, `DATETIME`, `TIME`, `TIMESTAMP` | `MIN`, `MAX`, `COUNT`

String `MIN`/`MAX` are off by default because databases sort strings differently
(collation), which produces false mismatches. Add them per column only when
collations match.

Change the checks per column, so the source and target compute the same
functions:

```yaml
columnSettings:
  aggregate:
    tolerance: 0.001                  # default for all columns of this table
  columns:
    region_name:
      aggregate:
        functions: [COUNT, SUM_LENGTH, MIN, MAX]   # replaces the defaults
    unit_price:
      aggregate:
        tolerance: 0.01
```

Allowed functions: `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `SUM_LENGTH`,
`COUNT_TRUE`, `COUNT_FALSE`, `COUNT_NULL`. `aggregate.disabled: true` removes
the default checks (for a column or the whole table).

How tolerances are applied:

*   Tolerances are absolute (`|target - source| <= tolerance`), not relative.
*   For `SUM`, an inherited (root or table) tolerance is multiplied by the row
    count, so it acts as a per-row tolerance.
*   Date tolerances are in days; timestamp and time tolerances in seconds.
*   With no tolerance, `AVG` and floating-point aggregates allow a tiny relative
    error (about 1e-9); everything else must be exactly equal.
*   A per-column `aggregate.tolerance` overrides the table-level one.
