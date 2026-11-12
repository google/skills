---
name: bigquery-migration-validator
metadata:
  version: "1.0.0"
  category: BigDataAndAnalytics
  publisher: google
description: >-
  Validates that tables migrated to BigQuery match their source (Teradata,
  Snowflake, Oracle, Redshift, Databricks, PostgreSQL, SQL Server, MySQL,
  MariaDB, Hive, Impala, Vertica) with the BigQuery Migration Service (BQMS)
  validation tool: schema and data type comparison, column aggregate
  comparison, and row-level data comparison. Use when generating or editing a
  validation config, running a validation, choosing sampling or partitioning,
  fixing connection or driver errors, or investigating validation results in
  BigQuery and Cloud Storage to decide which mismatches to fix. Don't use for
  SQL translation (use bigquery-migration-sql-translator), extracting source
  database catalog metadata or query logs, generating SQL scripts (such as COPY
  INTO) or exporting or unloading source tables to Parquet on Cloud Storage,
  loading staged files into BigQuery (such as bq load), or general BigQuery
  query failures and tuning (use bigquery-troubleshooting or
  bigquery-optimization).
---

# BigQuery Migration Validator

The validation tool compares a source table with its migrated BigQuery table. It
runs in two halves:

1.  **Client (this machine)**: Reads the config, queries the source database,
    and stages a row sample, source aggregates, and run metadata in Cloud
    Storage. It then starts a BigQuery Migration workflow for each table and
    exits.
2.  **Backend (Google Cloud, asynchronous)**: Loads the staged sample into
    BigQuery, compares it with the target table, and writes the results to
    BigQuery and Cloud Storage.

Results do not exist when the command exits. Wait for the workflow to finish
before reading them (Section 4).

## Usage attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Before you begin

1.  **Google Cloud CLI and project**: Ensure the
    [Google Cloud CLI][gcloud_install] is installed, verify that the Google
    Cloud project has an active Cloud Billing account, and configure the target
    project (check regional service availability at
    [Google Cloud locations][cloud_locations] when choosing `--location` for
    validation workflows):

    ```bash
    gcloud config set project PROJECT_ID
    ```

2.  **Enable the APIs** (ask the user before enabling APIs): BigQuery
    (`bigquery.googleapis.com`), BigQuery Migration
    (`bigquerymigration.googleapis.com`), Cloud Storage
    (`storage.googleapis.com`), and Secret Manager
    (`secretmanager.googleapis.com`, when reading source passwords from Secret
    Manager):

    ```bash
    gcloud services enable \
        bigquery.googleapis.com \
        bigquerymigration.googleapis.com \
        storage.googleapis.com
    # Only when source passwords come from Secret Manager:
    gcloud services enable secretmanager.googleapis.com
    ```

3.  **Local runtime, authentication, and IAM permissions** (ask before
    installing software):

    *   **Runtime and drivers**: Java 11 or later (JRE 11+) first on `PATH`, the
        `bqms` gcloud component (installed on first use or with
        `gcloud components install bqms`), local network access to the source
        database, and vendor JDBC driver JARs for Teradata (`terajdbc4.jar`),
        Vertica (`vertica-jdbc.jar`), Impala, and DuckDB in `./drivers` or
        `BQMS_DRIVER_DIR` when required (other JDBC drivers download on first
        use; see [connections and drivers](references/connections.md)).
    *   **Google Cloud credentials and IAM**: Authenticate the Google Cloud CLI
        and Application Default Credentials with `gcloud auth login` and
        `gcloud auth application-default login` (or set
        `GOOGLE_APPLICATION_CREDENTIALS` for a service account). The identity
        needs write access to the staging Cloud Storage bucket
        (`roles/storage.objectAdmin`), permission to create BigQuery Migration
        workflows (`roles/bigquerymigration.editor`), and permission to run
        BigQuery jobs and write validation results in the target project and,
        if set, the `results.projectId` project (`roles/bigquery.dataEditor`
        and `roles/bigquery.jobUser`). With Secret Manager passwords, it also
        needs `roles/secretmanager.secretAccessor` on the secret, or
        `roles/iam.serviceAccountTokenCreator` on the service account named in
        `secretImpersonateServiceAccount` (which then needs the accessor role).

4.  **Cost and cleanup**: Review
    [Google Cloud Pricing](https://cloud.google.com/pricing) for BigQuery, Cloud
    Storage, and Secret Manager. Staged samples in Cloud Storage contain source
    rows. When validation is complete, ask the user before deleting the staged
    run directory (a `gcs_paths` entry in `run_state.json`) and any per-run
    tables they no longer need (list them as in the
    [results reference](references/results.md), Section 5). Deleting the run
    directory also deletes the backend reports stored there (`results.json`,
    `validation_summary.txt`, `column_details.txt`, `queries.sql`) and
    `sample_metadata.json`, so `run_history.gcs_uri` no longer resolves;
    say so and offer to copy the reports locally first:

    ```bash
    gcloud storage cp GCS_RUN_PATH/results.json \
        GCS_RUN_PATH/validation_summary.txt GCS_RUN_PATH/column_details.txt \
        GCS_RUN_PATH/queries.sql LOCAL_DIR/
    gcloud storage rm --recursive GCS_RUN_PATH
    bq rm -f -t RESULTS_PROJECT:DATASET.TABLE_NAME
    ```

## 1. What gets compared

Pillar        | `--validation-types` | Compares                                                                                                                    | Coverage
:------------ | :------------------- | :-------------------------------------------------------------------------------------------------------------------------- | :-------
**Schema**    | `schema`             | Column presence, mapping, and data type compatibility (one of 9 compatibility notes)                                        | All columns
**Aggregate** | `aggregate`          | Column statistics per type (`COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `SUM_LENGTH`, ...), computed per partition, then rolled up | 100% of rows (pushed down)
**Data**      | `data`               | Cell-by-cell values joined on comparison keys, with a distance per mismatched cell                                          | Sampled or full rows

With `--validation-types` omitted, all three run. With `--validation-types` set
(for example `--validation-types=schema,aggregate`), only the listed types run.
Query (code) validation is not available in this tool.

Each pillar catches what the others miss. Aggregates cover every row cheaply but
cannot see offsetting errors (one row +5, another -5). Row sampling sees those
but only in the sample. Run both for sign-off.

## 2. Quick start

Both validation commands run in the **alpha** release track through the Google
Cloud CLI, which calls the `bqms` component (Java 11+ required). Arguments after
`--` are forwarded unchanged to the validation client.

> [!IMPORTANT]
> The commands are in the alpha track. If gcloud reports an invalid choice or
> unknown command, ask the user before running `gcloud components update` (or
> `gcloud components install alpha bqms`). If the Google Cloud CLI was
> installed with a system package manager such as `apt` or `yum`, the
> component manager is disabled; have the user upgrade `google-cloud-cli`
> through that package manager instead. If the command is still unavailable,
> stop and point the user to the [CLI reference](references/cli.md) and the
> [installation guide][gcloud_install] rather than retrying.

```bash
# 1. Generate per-table configs offline from extractor metadata or BQMS
#    translation output (writes ./validation_config/).
gcloud alpha bq migration validation configure \
    --metadata=dwh-migration-oracle-metadata.zip \
    --target-dataset=warehouse \
    --output=validation_config

# 2. Edit validation_config/connections.yaml (check the source dialect;
#    set the target dataset) and settings.yaml (googleCloudStorage.gcsPath),
#    then run schema and aggregate checks first.
gcloud alpha bq migration validation run validation_config/ \
    --location=us --validation-types=schema,aggregate

# 3. Run row-level comparison, optionally on a subset of tables.
gcloud alpha bq migration validation run validation_config/ \
    --location=us --validation-types=data --tables=orders
```

Then wait for the workflows (Section 4) and investigate (Section 5).

Every answer that runs or recommends `validation run` must tell the user that
the comparison finishes later in a BigQuery Migration workflow, that exit code 0
does not mean the data matched, and how to check the workflow before reading
results. Users who skip this read an empty or stale results dataset as a pass.

## 3. Configure

Settings come from YAML (modular `validation_config/` directory or one
`validation-config.yaml`), then CLI flags. The essentials:

*   `connections`: a `source` and a BigQuery `target`. The target needs
    `projectId` and `dataset`; without `dataset` the run fails, even when every
    `targetTable.name` is fully qualified. `configure` can scaffold the wrong
    source `dialect` (for example `snowflake` for PostgreSQL metadata), so
    check it and its properties before the first run. Connection names are
    letters and digits only; a name with `_` or `-` fails config validation. If
    the user asks for such a name, drop the separators (for example `sales-db`
    becomes `salesdb`) and tell them why, because the name also forms the
    environment variable prefix. Keep secrets out of YAML: use
    `BQMS_VALIDATION_<CONNECTION>_PASSWORD` or a Secret Manager reference (see
    [connections and drivers](references/connections.md)). Never ask the user
    to type a password into the conversation and never echo one. For commands
    you run yourself, use a Secret Manager reference (`passwordSecret` or
    `BQMS_VALIDATION_<CONNECTION>_PASSWORD_SECRET`); give plaintext `export`
    lines only for the user to run in their own terminal.
*   `googleCloudStorage.gcsPath`: required staging bucket (`gs://bucket/path`,
    no trailing slash). Results artifacts also land here.
*   Per table: `sourceTable` and `targetTable` (each with `name` and, under
    `sourceTable`, `comparisonKeys`: the columns that uniquely identify a row
    for the validation join when the table has no primary key — explain that
    `comparisonKeys` only control how validation matches rows, so no database
    primary key or schema change is needed; `configure` fills them in only
    when the metadata includes primary keys), `columnSettings` (exclusions,
    transforms, tolerances), `sampleSize`, and `partitioning`.
*   `results.dataset` and optional `results.projectId`: BigQuery dataset and
    project for results (defaults `validation_results` and the target
    connection's project). Query results where these point.

Details: [configuration reference](references/configuration.md).

## 4. Run and wait

1.  Run `gcloud alpha bq migration validation run`. Exit code 1 means a config
    or source-side failure; read the error and fix it. Exit code 0 means the
    samples were staged (or that usage was printed for a bad forwarded flag;
    check the output). Mismatches never change the exit code.
2.  Confirm a workflow started. The client prints a workflow name per table and
    writes `run_state.json` (run ID, Cloud Storage paths, workflow names,
    results dataset) to `--output-dir` (default `/tmp/validation_outputs`,
    passed after `--`). If it instead prints "Could not initiate BigQuery
    Migration validation workflow", fix the cause it reports (usually
    permissions or the API not enabled) and re-run, or create the workflow from
    the console link it prints.
3.  Poll until the workflow finishes:

    ```bash
    gcloud bq migration-workflows describe WORKFLOW_NAME
    ```

    Or check `run_history.status` in the results dataset; `IN_PROGRESS` means
    the backend is still working.

## 5. Investigate results

Results are in three places. Pick by question, not by habit:

Surface                                        | Audience       | Grain                                          | Use for
:--------------------------------------------- | :------------- | :--------------------------------------------- | :------
BigQuery results dataset                       | Agents, humans | Run, slice (partition), column, aggregate, row | All investigation; the only source for per-partition and per-row detail
Cloud Storage `results.json`                   | Agents         | One run (whole table)                          | Quick status of one table without BigQuery access; execution times
`validation_summary.txt`, `column_details.txt` | Humans         | One run                                        | Show the user; do not parse
Web UI                                         | Humans         | All of the above, visual                       | Point the user to it if the printed link is a real URL

Investigate by zooming in one level at a time, stopping as soon as the cause is
clear:

1.  **All tables**: Latest run per table with status, row deltas, and mismatch
    counts. Errors first, then the largest mismatch counts.
2.  **One table, by pillar**: Schema compatibility, then failed aggregates, then
    missing rows, then per-column mismatch statistics.
3.  **Partitions**: Per-slice metrics show whether mismatches are local (one day
    or range: a failed load) or everywhere (a systematic conversion).
4.  **Rows**: Group mismatched cells by column and distance, then read a few
    rows to confirm the pattern.
5.  **Fix and re-run narrowly**: Pass `--tables` and `-- --where`, then compare
    the new run with the old one.

Then zoom back out: say which tables pass, which have explained differences, and
which need a fix in the migration itself. A narrower re-run (some
`--validation-types`, or `--where`) becomes the table's latest run without
covering the rest; a table passes only when every pillar and the whole table
passed.

Queries, field names, and decision rules for each level:
[investigation workflow](references/investigation.md). What every status, field,
and table means: [results reference](references/results.md).

## 6. Reference guides

Guide                                                         | Read when
:------------------------------------------------------------ | :--------
[CLI reference](references/cli.md)                            | Installing, running, flags, exit codes, workflow status
[Configuration reference](references/configuration.md)        | Writing or auditing YAML, keys, transforms, tolerances
[Connections and drivers](references/connections.md)          | Credentials, Secret Manager, JDBC drivers, JDBC URLs
[Sampling and partitioning](references/performance_tuning.md) | Sample sizes, partitioned runs, wide tables, concurrency
[Results reference](references/results.md)                    | Statuses, `results.json`, BigQuery tables and views, distances
[Investigation workflow](references/investigation.md)         | Step-by-step drill-down queries and decision rules
[Dialects and types](references/dialect_mapping.md)           | Default aggregates, type compatibility, dialect quirks
[Troubleshooting](references/troubleshooting.md)              | Mismatch signatures and their config fixes, run errors

## 7. Operating principles

1.  **Read-only**: Validation only runs `SELECT` on the source and target. Never
    modify source or target data to make a validation pass.
2.  **Mismatches are findings, not failures**: A run that finishes with
    mismatches (`COMPLETED_WITH_MISMATCHES`) succeeded and found differences.
    Reserve "failed" for `ERROR` runs and non-zero exit codes.
3.  **Explain before excluding**: Do not add `exclude`, tolerances, or
    transforms to hide a difference until the row-level evidence shows it is a
    representation difference (padding, precision, empty string versus NULL) and
    not lost or wrong data. Say which one it is.
4.  **Protect row data**: Mismatch tables hold real customer values. Query
    aggregates and small samples (`LIMIT`), and do not paste bulk row values
    into the conversation unless the user asks.
5.  **Edit the user's config in place**: When the user names a config file, read
    it, change only what the task needs, and keep everything else as written:
    table names (including dataset or schema prefixes), `comparisonKeys`,
    filters, and settings. Do not normalize or shorten existing names. A changed
    `targetTable.name` points the comparison at a different table, and a dropped
    `comparisonKeys` changes what counts as a missing row, so either silently
    changes what is validated. If something existing looks wrong, say so instead
    of changing it.

[cloud_locations]: https://cloud.google.com/about/locations
[gcloud_install]: https://cloud.google.com/sdk/docs/install
