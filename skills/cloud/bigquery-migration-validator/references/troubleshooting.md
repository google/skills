# Troubleshooting

Run errors and mismatch signatures with their fixes. For the procedure that
finds these signatures, see the [investigation workflow](investigation.md).

## 1. Run errors

Symptom                                                              | Cause                                                                                                       | Fix
:------------------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------- | :--
Exit 1 with a config error                                           | Invalid YAML, connection name with `_` or `-`, `gcsPath` with trailing slash, `;` in a filter or name       | Fix the reported key
Exit 1: `dataset is required for BigQuery connection`                | `dataset` missing on the BigQuery target connection (required even with fully qualified table names)        | Add `dataset` to the target connection
Source connection fails; `connections.yaml` has the wrong `dialect`  | `configure` scaffolded another dialect (for example `snowflake` for PostgreSQL metadata)                    | Set the real `dialect` and its properties; see [connections](connections.md)
Exit 1 with a credentials error                                      | No Application Default Credentials, missing password variable, unreadable secret                            | `gcloud auth application-default login`; set `BQMS_VALIDATION_<CONN>_PASSWORD` or a secret reference
Driver not found                                                     | Teradata, Vertica, Impala, or DuckDB JAR missing (never downloaded), or downloads blocked for other drivers | Put the JAR in `./drivers` or `BQMS_DRIVER_DIR`; see [connections](connections.md)
"Could not initiate BigQuery Migration validation workflow" (exit 0) | No permission or API not enabled in the target project                                                      | Fix permissions, then re-run or create the workflow from the printed console link
Run `ERROR` with a missing table                                     | `targetTable.name` points at the wrong dataset (generated names override the connection dataset)            | Correct `targetTable.name`
Run `ERROR`, query too complex or resources exceeded                 | Very wide table                                                                                             | Lower `maxColumnsPerTile`; do not exclude columns
"Planned partition slice count exceeds maxSlices"                    | Range too large for `partitionSize`                                                                         | Increase `partitionSize`, raise `maxSlices`, or narrow `whereClause`
Client out of memory                                                 | Large sample or many slices in parallel                                                                     | `JAVA_OPTS=-Xmx8g`; lower `maxConcurrency` or `sampleSize`
No results after exit 0                                              | Backend still running                                                                                       | Wait for the workflow (see [CLI reference](cli.md#6-tracking-the-backend-workflow))
`results.json` missing, `run_history` row exists                     | Run in progress or failed before the final report                                                           | Check `run_history.status` and `error_message`

## 2. Mismatch signatures

### Row counts differ

*   **Evidence**: `source_total_row_count != target_total_row_count` in a run
    with the aggregate pillar (data-only runs report a target count of 0),
    `ROW` mismatches, or a failed table `COUNT`. Rows that exist only in
    BigQuery appear only in the counts, not as `ROW` mismatches.
*   **Causes**: one side filtered differently (`whereClause`), loads still
    running, rows deleted or inserted after migration, failed load of some
    partitions.
*   **Fix**: make filters equivalent on both sides; validate against a static
    snapshot or quiet window; use per-slice metrics to find failed ranges and
    re-load them.

### Rows reported missing, evenly spread

*   **Evidence**: many `__source_only_row` rows that a direct lookup finds in
    BigQuery, while total row counts match.
*   **Cause**: comparison keys are not unique, or key values differ in
    representation (padding, case, type).
*   **Fix**: correct `comparisonKeys`, add transforms to key columns, or use
    `useAllColumnsAsKey` for tables without a key.

### Floating-point or decimal precision

*   **Evidence**: tiny distances, `min_diff` around `1e-8`; often `HEALED`.
*   **Fix**:

    ```yaml
    columnSettings:
      columns:
        amount:
          tolerance: 0.001
    ```

### Padding

*   **Evidence**: `SUM_LENGTH` differs; edit distance equals trailing spaces.
*   **Fix**: `transform: TRIM` on the column.

### Empty string versus NULL

*   **Evidence**: column `COUNT` differs while row counts match; one side
    `NULL`, the other `''`.
*   **Fix**: `transform: EMPTY_TO_NULL` on the column. `TRIM` does not help.

    ```yaml
    columnSettings:
      columns:
        middle_name:
          transform: EMPTY_TO_NULL
    ```

### Time zone offset

*   **Evidence**: one dominant timestamp distance, a multiple of 3,600,000,000
    microseconds.
*   **Fix**: decide which side is correct. If BigQuery should store UTC, fix the
    load. If the difference is only representation, align types or add a
    `transformExpression`.

### Wrong values

*   **Evidence**: large, varied distances on numeric or string columns, failed
    `SUM`/`AVG`, no consistent pattern.
*   **Fix**: none in validation config. This is a migration defect; report the
    column, affected partitions, row count, and example keys.
