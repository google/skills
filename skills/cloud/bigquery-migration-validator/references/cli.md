# Validation CLI reference

Commands, flags, exit codes, and workflow tracking for the validation tool.

## Contents

*   [1. Installation](#1-installation): Lines 15-35
*   [2. Command shape](#2-command-shape): Lines 37-46
*   [3. validation configure](#3-validation-configure): Lines 48-111
*   [4. validation run](#4-validation-run): Lines 113-157
*   [5. Exit codes and output](#5-exit-codes-and-output): Lines 159-186
*   [6. Tracking the backend workflow](#6-tracking-the-backend-workflow): Lines 188-201
*   [7. Runtime environment](#7-runtime-environment): Lines 203-212

## 1. Installation

The validation commands belong to the Google Cloud CLI. They call the `bqms`
component, which bundles the validation client and the migration extractor.

*   **Java 11 or later** must be the first `java` on `PATH`. gcloud does not
    read `JAVA_HOME`; if an older `java` comes first, put the newer one ahead
    of it, for example `export PATH="$JAVA_HOME/bin:$PATH"`.
*   **Application Default Credentials** are required:
    `gcloud auth application-default login`. The identity needs write access to
    the staging bucket, BigQuery access in the target project, and permission to
    create BigQuery Migration workflows there.
*   The commands need the `alpha` and `bqms` components. Ask the user before
    installing or updating anything. gcloud offers to install `bqms` on first
    use; to install both explicitly, run
    `gcloud components install alpha bqms`. If the command group is missing,
    run `gcloud components update`. If the Google Cloud CLI was installed with
    a system package manager (`apt`, `yum`), the component manager is disabled:
    upgrade `google-cloud-cli` with that package manager instead. If the
    command group is still missing, stop and point the user to the
    [installation guide](https://cloud.google.com/sdk/docs/install).

## 2. Command shape

Both validation commands live under `gcloud alpha bq migration validation`.
gcloud flags come first; any validation client flags not exposed directly on
gcloud go after `--` and are forwarded unchanged to the client:

Command                                                                      | Purpose
:--------------------------------------------------------------------------- | :------
`gcloud alpha bq migration validation configure`                             | Write table configs from offline metadata
`gcloud alpha bq migration validation run CONFIG_PATH --location=LOCATION`   | Stage samples and start validation workflows

## 3. validation configure

```text
gcloud alpha bq migration validation configure --output=DIRECTORY
    [--metadata=PATH] [--tables-yaml=PATH[,...]]   # at least one; both allowed
    [--target-dataset=TARGET_DATASET] [--schemas=SCHEMA[,...]]
    [--tables=TABLE[,...]] [--force] [--endpoint-mode=ENDPOINT_MODE]
    [-- CLIENT_ARGS ...]
```

Builds per-table configs from offline metadata without connecting to the source
database. `--output` and at least one of `--metadata` or `--tables-yaml` are
required (both can be combined). With `--quiet` (or in non-interactive shells),
ambiguities resolve with defaults instead of prompting.

gcloud flags (before `--`):

Flag                         | Default       | Meaning
:--------------------------- | :------------ | :------
`--output DIRECTORY`         | required      | Output directory (for example `validation_config`)
`--metadata PATH`            | None          | Extractor metadata `.zip` (`dwh-migration-*-metadata.zip`) or a directory containing `.zip` archives and `tables.yaml` files
`--tables-yaml PATH[,...]`   | None          | BQMS translation `tables.yaml` mapping files or directories
`--target-dataset DATASET`   | source schema | BigQuery dataset for target table names
`--schemas S1,S2`            | None          | Only generate configuration for these source schemas
`--tables T1,T2`             | None          | Only generate configuration for these source tables
`--force`                    | None          | Overwrite existing configuration files in `--output`
`--endpoint-mode MODE`       | `global`      | `global`, `regional`, or `regional-preferred`

Client flags forwarded after `--`:

Flag                      | Default   | Meaning
:------------------------ | :-------- | :------
`--update`                | None      | Merge new metadata into existing table files, keeping manual edits
`--clean`                 | None      | Delete the output directory first
`--combine`, `-f FILE`    | None      | Write one combined file instead (`-f` implies `--combine`; default `validation-config.yaml`)
`--filter-file FILE`      | None      | Newline-separated table names or patterns (`#` comments)
`--target NAME`           | `target`  | Target connection for tables that do not name one

A non-empty `--output` directory is an error unless `--force` (before `--`) or
`--update` / `--clean` (after `--`) is given. Prefer `-- --update` once users
have edited the configs.

What generation fills in:

*   `comparisonKeys` from primary keys, only when the metadata includes them.
    PostgreSQL extractor archives carry no primary keys, so their table files
    get none. Add them by hand under `sourceTable` (see
    [comparison keys](configuration.md#4-comparison-keys)):

    ```yaml
    table:
      sourceTable:
        name: "salesdb.sales.orders"
        comparisonKeys: [order_id]
    ```

*   `exclude` for column types the comparison cannot handle.
*   `transform: TRIM` for padded character columns (`CHAR(n)`).
*   Fully qualified names (`schema.table`). These override the connection's
    default dataset or schema, so check that `targetTable.name` points at the
    intended BigQuery dataset.
*   Teradata metadata is parsed natively, including partitions and indexes.
    Other dialects use generic `tables.csv`/`columns.csv` parsing, so
    partition-aware split keys are not inferred for them.

## 4. validation run

```text
gcloud alpha bq migration validation run CONFIG_PATH [CONFIG_PATH ...]
    --location=LOCATION [--validation-types=TYPE[,...]]
    [--tables=TABLE[,...]] [--gcs-path=gs://...] [--labels=KEY=VALUE[,...]]
    [--endpoint-mode=ENDPOINT_MODE]
    [-- [--where=SQL] [--source-where=SQL] [--target-where=SQL]
        [--no-partition] [--max-concurrency=N] [--output-dir=DIR]
        [--extract-only] [--performance]]
```

`CONFIG_PATH` (one or more required positional values) may be a directory (such
as `validation_config/`, read recursively), a `.yaml`/`.yml` file (such as
`validation-config.yaml`), a glob pattern such as
`validation_config/databases/edw/sales/*.yaml`, or a `gs://` path to configs in
Cloud Storage.

gcloud flags (before `--`):

Flag                           | Meaning
:----------------------------- | :------
`--location LOCATION`          | Required. Location of the BigQuery Migration Service workflows (for example `us` or `europe-west1`)
`--validation-types TYPE[,...]`| Comma-separated list of `schema`, `aggregate`, `data` (default: all three)
`--tables TABLE[,...]`         | Only these tables (matches full source/target name or dot-separated suffix, for example, `orders` or `sales.orders`)
`--gcs-path gs://...`          | Override `googleCloudStorage.gcsPath`
`--labels KEY=VALUE[,...]`     | Labels attached to the validation run
`--endpoint-mode MODE`         | `global`, `regional`, or `regional-preferred`

Client flags forwarded after `--`:

Flag                               | Meaning
:--------------------------------- | :------
`--where SQL`                      | Filter applied to both sides; replaces table `whereClause`
`--source-where`, `--target-where` | Side-specific filters; replace the table's filter
`--no-partition`                   | Disable partitioned execution for every table
`--max-concurrency N`              | Slices processed in parallel; overrides table `maxConcurrency`
`--output-dir DIR`                 | Local output directory for `run_state.json` (default `/tmp/validation_outputs`)
`--extract-only`                   | Stage samples in Cloud Storage without starting backend workflows
`--json '{...}'`, `--json @FILE`   | Pass client arguments as JSON; overrides flags
`-v`, `-d`                         | Verbose or debug client logging (also derived from gcloud `--verbosity`)
`--performance`                    | Extra timing lines in the client log

`--where` style flags replace the configured filter outright; they do not add to
it. Pass them after `--` for quick narrow re-runs (one day, one key range).

## 5. Exit codes and output

Exit | Meaning                                                   | Action
:--- | :-------------------------------------------------------- | :-----
`0`  | Samples staged (workflows usually started)                | Check the output for a dispatch warning, then wait (Section 6)
`1`  | Config error, credentials error, or a source query failed | Read the error, fix, re-run

An unknown forwarded client flag or invalid `--json` payload prints client usage
and exits 0 without doing anything. Check that the output shows tables being
sampled.

Exit code 0 does not mean the data matched; the comparison has not run yet. If
workflow creation failed, the client still exits 0 and prints "Could not
initiate BigQuery Migration validation workflow" with a ready-to-run
`gcloud bq migration-workflows create` command and a Cloud console link. Fix the
cause (usually permissions or the BigQuery Migration API not enabled), then
re-run `validation run` or create the workflow from the console link.

The client writes `run_state.json` to `--output-dir`:

```json
{"run_id": "...", "gcs_path": "gs://...", "gcs_paths": ["gs://..."],
 "workflow_name": "projects/.../workflows/...", "workflow_names": ["..."],
 "bq_results": "PROJECT.validation_results", "ui_url": "..."}
```

Use it to find the workflow, the staged run directory, and the results dataset
without parsing logs.

## 6. Tracking the backend workflow

The client starts one BigQuery Migration workflow per table (display name
`validation_<run_id>`, in the `--location` passed to `validation run`). The
backend comparison runs there.

```bash
gcloud bq migration-workflows describe WORKFLOW_NAME
gcloud bq migration-workflows list --location=us --project=PROJECT
```

Wait until the workflow and its validation task are finished. A failed task
means the backend could not compare (for example, missing target table or
permissions); the error is in the workflow and in `run_history.error_message`.

## 7. Runtime environment

Variable                                                            | Effect
:------------------------------------------------------------------ | :-----
`PATH`                                                              | The first `java` on `PATH` is used (11+); gcloud ignores `JAVA_HOME`
`JAVA_OPTS`                                                         | Extra JVM flags, for example `-Xmx8g` for large samples
`HTTPS_PROXY`, `HTTP_PROXY`, `NO_PROXY`                             | Not converted for Java by gcloud; pass proxies in `JAVA_OPTS`, for example `-Dhttps.proxyHost=HOST -Dhttps.proxyPort=PORT`
`BQMS_VALIDATION_LOCATION`                                          | Set automatically from `--location` by `validation run`
`BQMS_VALIDATION_CONNECTIONS_PATH`, `BQMS_VALIDATION_SETTINGS_PATH` | Fallback shared `connections.yaml` / `settings.yaml`, used only when none is found in a parent directory
`BQMS_DRIVER_DIR`, `BQMS_AUTO_DOWNLOAD_DRIVERS`                     | JDBC driver location and download switch (see [connections](connections.md))
