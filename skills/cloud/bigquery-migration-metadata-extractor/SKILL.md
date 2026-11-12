---
name: bigquery-migration-metadata-extractor
metadata:
  version: "1.0.0"
  category: BigDataAndAnalytics
  publisher: google
description: >-
  Extracts database catalog metadata and query logs from data warehouses by
  running the DWH migration extractor locally or on a temporary Google Cloud VM
  through the BigQuery Migration Cloud Extractor (credentials held in Secret
  Manager), and inspects extracted `.zip` archives to report object and volume
  statistics. Use when extracting database metadata or query logs from
  Snowflake, Redshift, Teradata, Oracle, PostgreSQL, SQL Server, Hive, etc.,
  deciding between local and cloud (Cloud Extractor) extraction, or inspecting
  extracted dwh-migration-*.zip archives to print post-extraction statistics.
  Don't use for SQL dialect translation (use bigquery-migration-sql-translator),
  exporting table data to Parquet or CSV files (such as Snowflake `COPY INTO`
  unloads) or loading it into BigQuery (use the BigQuery Data Transfer Service
  or bigquery-basics), or validating migrated data.
---

# BigQuery Migration Metadata Extraction

Extraction runs the DWH migration extractor (`dwh-migration-dumper`) through two
gcloud commands to collect catalog DDL and query history—not table row data. If
the user wants to migrate table rows (such as Snowflake `COPY INTO` unloads),
ask whether they prefer the [BigQuery Data Transfer Service][bq_dts] (including
the [Snowflake connector][snowflake_dts]) or exporting to Cloud Storage and
loading with `bq load`. Both extract commands are in the **alpha** release
track:

Command                                        | Use for
:--------------------------------------------- | :------
`gcloud alpha bq migration metadata extract`   | Catalog metadata (metadata connectors)
`gcloud alpha bq migration query-logs extract` | Query history (`*-logs` connectors)

Both take the same arguments. gcloud flags come first; the extractor's own flags
come after `--` and are passed to the extractor unchanged:

```text
gcloud alpha bq migration {metadata|query-logs} extract \
    --connector=CONNECTOR --output=gs://BUCKET/PATH/ \
    [--run-mode=local|cloud] [cloud flags] \
    -- [EXTRACTOR FLAGS] [PASSWORD]
```

*   `--connector` and `--output` are required gcloud flags. `--output` is a
    Cloud Storage path (`gs://...`); local mode also accepts a local file or
    directory path. This skill uses Cloud Storage in both run modes.
*   `--run-mode=local` (the default) runs the extractor on this machine.
    `--run-mode=cloud` runs it on a temporary Compute Engine VM (the **BigQuery
    Migration Cloud Extractor**).
*   Database flags (`--host`, `--port`, `--user`, `--database`, `--schema`,
    `--warehouse`, `--role`, `--driver`, `--assessment`, `--query-log-*`, ...)
    go after `--`. Putting them before `--` is an error.
*   How the password is passed depends on the run mode (Section 4): an extractor
    response file (`@FILE`) in local mode, and `--password` read from a file in
    cloud mode. Never type a literal password.

> [!IMPORTANT]
> The commands are in the alpha track. If gcloud reports an invalid choice or
> unknown command, ask the user before updating the Google Cloud CLI, then
> retry. Update it with `gcloud components update`, or, if gcloud was installed
> with a system package manager such as `apt` or `yum` (which disables the
> component manager), upgrade the `google-cloud-cli` package with that package
> manager.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Before you begin

1.  **Google Cloud CLI, authentication, project, region, and zone**: Ensure the
    [Google Cloud CLI][gcloud_install] is installed, verify that the Google
    Cloud project has an active Cloud Billing account, authenticate with user
    and Application Default Credentials, and configure the target project, a
    default region such as `us-central1` (check regional service availability at
    [Google Cloud locations][cloud_locations]), and a zone in that region. Cloud
    mode takes the VM's zone from `--zone`, then `compute/zone`, then
    `us-central1-a`; it does not read `compute/region`:

    ```bash
    gcloud auth login
    gcloud auth application-default login
    gcloud config set project {project_id}
    gcloud config set compute/region {region}
    gcloud config set compute/zone {zone}
    ```

2.  **Output bucket**: This skill writes the ZIP archives to a Cloud Storage
    bucket (`--output`) that the project owns and that is not public, in both
    run modes. In both modes the command checks the bucket before it starts
    the extractor, so the caller needs `storage.buckets.list` on the bucket's
    project and `storage.buckets.getIamPolicy` on the bucket unless public
    access prevention is enforced on it. In local mode the Application Default
    Credentials also need to create objects in the bucket.

3.  **Run-mode prerequisites** (ask the user before installing software or
    enabling APIs):

    *   **Local mode (`--run-mode=local`)**: Java 11 or later (JRE 11+) on
        `PATH`, the `bqms` gcloud component, vendor JDBC driver JARs
        (`--driver`) when required, and local network access to the database;
        see the [local extraction guide](references/local_extraction.md).
        Without a terminal the extract command cannot prompt to install
        `bqms` and fails, so once the user agrees, install it first with
        `gcloud components install bqms --quiet` (for a gcloud installed with
        `apt` or `yum`, install the `google-cloud-cli-bqms` package instead).
    *   **Cloud mode (`--run-mode=cloud`)**:
        *   **APIs**: Compute Engine (`compute.googleapis.com`), Secret Manager
            (`secretmanager.googleapis.com`), Cloud Storage
            (`storage.googleapis.com`), and Cloud Logging
            (`logging.googleapis.com`).
        *   **Network and subnet**: A VPC `--network` and `--subnet` (default
            `default`) with routing to the database, and the VM's egress IP
            range allowlisted by the database. The VM also needs internet
            access to download the extractor and reach Google APIs: keep the
            default external IP, or with `--no-address` add Cloud NAT in the
            VM's region. A Cloud VPN or Cloud Interconnect route to the
            database does not replace it.
        *   **IAM permissions**: The caller needs roles to create the VM and
            the secret, for example Compute Admin (`roles/compute.admin`) and
            Secret Manager Admin (`roles/secretmanager.admin`), plus the
            bucket permissions in item 2. With a prepared
            `--gce-service-account`, the caller also needs Service Account User
            (`roles/iam.serviceAccountUser`) on that account, and the account
            itself needs the roles listed in the
            [cloud extraction guide](references/cloud_extraction.md).
        *   **Default service account**: Without `--gce-service-account`, every
            run creates or reuses
            `bqms-cloud-extractor@{project_id}.iam.gserviceaccount.com` and
            grants it nine project roles, including `roles/editor`,
            `roles/compute.admin`, and `roles/cloudkms.cryptoKeyDecrypter`.
            This needs Service Account Admin (`roles/iam.serviceAccountAdmin`)
            and Project IAM Admin (`roles/resourcemanager.projectIamAdmin`).
            Without a terminal, gcloud accepts its own "create it?" prompt, so
            get the user's explicit approval before you omit
            `--gce-service-account`; see the
            [cloud extraction guide](references/cloud_extraction.md).

4.  **Cost and cleanup**: Review
    [Google Cloud Pricing](https://cloud.google.com/pricing) for Compute Engine,
    Secret Manager, and Cloud Storage. After a cloud run, delete the run's
    Secret Manager secret (Section 5).

## 1. Choose the Run Mode

&nbsp;                   | `--run-mode=local` (default)                             | `--run-mode=cloud` (Cloud Extractor)
:----------------------- | :------------------------------------------------------- | :-----------------------------------
Where the extractor runs | This machine (needs a Java runtime)                      | Temporary Compute Engine VM
Network path to the DB   | This machine's network (VPN, on-prem, bastion)           | The VM's VPC; the DB must accept connections from it
JDBC drivers             | Any, including vendor JARs passed with `--driver`        | Only drivers bundled with the extractor; the VM has no vendor JARs and cannot read a local `--driver` path
Credentials              | `@FILE` response file read by the local extractor        | `--password` (read from a file) stored with the other extractor arguments in a Secret Manager secret that the VM reads
Failed extractor tasks   | Partial ZIP still lands in `--output`                    | No ZIP is uploaded; the run fails
Read next                | [local extraction guide](references/local_extraction.md) | [cloud extraction guide](references/cloud_extraction.md)

Pick **local** when any of these is true:

*   The connector needs a JDBC driver that the cloud VM does not have:
    `teradata`, `teradata-logs`, `teradata14-logs`, `oracle`, `oracle-logs`,
    `oracle-stats`, `sqlserver`, `mysql`, `netezza`, `vertica`, `vertica-logs`.
    Locally, the `bqms` launcher downloads the Oracle, SQL Server, and MySQL
    drivers itself (the local extractor ships without JDBC drivers, so the
    launcher also downloads the Snowflake, Redshift, PostgreSQL, and Greenplum
    drivers); Teradata, Netezza, and Vertica need `--driver` (Section 3).
*   The database is only reachable from the user's network (on-prem, VPN,
    private endpoint with no route from Google Cloud).
*   The user cannot create Compute Engine VMs, service accounts, or secrets in
    the project.
*   `--host` is `localhost`, `127.0.0.1`, `::1`, or a private address with no
    route from a Google Cloud VPC. Never use `--run-mode=cloud` for these; the
    VM cannot reach them (on the VM, `127.0.0.1` is the VM itself, even if the
    user says the address is routed). Ask for a routable address, or, if the
    user already accepted a fallback, run locally with the same `--output` and
    drop the cloud-only flags.

Pick **cloud** when the database is reachable from Google Cloud (Snowflake,
Redshift, BigQuery, cloud-hosted PostgreSQL/Greenplum, Hive metastore) and the
user wants nothing installed locally.

Tell the user which run mode you chose and why, for example that cloud mode
cannot load vendor JDBC drivers or reach a database that only the user's network
can reach.

## 2. Connectors and Commands

Each connector extracts **either** catalog metadata **or** query logs, so it
belongs to exactly one command. Run both commands to get both.

Source                | `metadata extract` connector                                                                          | `query-logs extract` connector
:-------------------- | :---------------------------------------------------------------------------------------------------- | :-----------------------------
Snowflake             | `snowflake` (or `snowflake-account-usage-metadata`, `snowflake-information-schema-metadata`)          | `snowflake-logs` (or `snowflake-account-usage-logs`, `snowflake-information-schema-logs`)
Amazon Redshift       | `redshift`                                                                                            | `redshift-raw-logs` (or `redshift-logs`, `redshift-serverless-logs`)
Teradata              | `teradata`                                                                                            | `teradata-logs` (version 15+), `teradata14-logs`
Oracle                | `oracle` (DDL), `oracle-stats` (workload statistics for assessment; window set by `--query-log-days`) | `oracle-logs`
Google BigQuery       | `bigquery`                                                                                            | `bigquery-logs`
Greenplum             | `greenplum`                                                                                           | `greenplum-logs`
Vertica               | `vertica`                                                                                             | `vertica-logs`
PostgreSQL            | `postgresql`                                                                                          | none
SQL Server / Azure    | `sqlserver`                                                                                           | none
MySQL                 | `mysql`                                                                                               | none
Netezza               | `netezza`                                                                                             | none
Apache Hive metastore | `hiveql`                                                                                              | none

> [!TIP]
> Catalog metadata is fast (minutes) and is all that SQL translation,
> schema creation, Parquet export, and static lineage need. Query logs take
> longer and are only needed for workload assessment or lineage of queries that
> are not stored as views (for example dbt or Airflow `INSERT ... SELECT` jobs).
> Always bound log extraction with `--query-log-start`/`--query-log-end` or
> `--query-log-days` (after `--`).

## 3. Flags

gcloud flags (before `--`):

Flag                                          | Run mode   | Meaning
:-------------------------------------------- | :--------- | :------
`--connector`                                 | both       | Required. Must match the command (Section 2).
`--output`                                    | both       | Required. `gs://BUCKET/PATH/` (or a `.zip` object path). Local mode also accepts a local file or directory path.
`--run-mode`                                  | both       | `local` (default) or `cloud`.
`--expected-owner`                            | both       | Project that must own the `--output` bucket (defaults to the current project).
`--endpoint-mode`                             | both       | Standard gcloud regional endpoint selection; leave unset unless the user asks.
`--project`                                   | both       | Standard gcloud project flag.
`--zone`, `--secret`, `--network`, and others | cloud only | See the [cloud extraction guide](references/cloud_extraction.md).

Extractor flags (after `--`):

Flag                                                       | Meaning
:--------------------------------------------------------- | :------
`--host`, `--port`, `--url`                                | Server address, or a full JDBC URL that overrides host and port.
`--user`, `@FILE`                                          | User, and a response file holding the password (Section 4).
`--database`, `--schema`                                   | Comma-separated lists to limit what is extracted. `postgresql` extracts only the first `--database` and ignores `--schema`; run it once per database, each with its own `--output`.
`--warehouse`, `--role`                                    | Snowflake session settings (set per session; never change user defaults).
`--assessment`                                             | Extra data for BigQuery Migration Assessment (omit `--database` and `--schema` when passing `--assessment` to `snowflake`, which rejects combining them). Only changes the output of `teradata`, `teradata-logs`, `redshift`, `redshift-raw-logs`, `snowflake`, `snowflake-logs`, `hiveql`, and `greenplum-logs`; other connectors ignore it.
`--query-log-start`, `--query-log-end`, `--query-log-days` | Query log window for `*-logs` connectors.
`--driver`                                                 | Vendor JDBC driver JAR(s) (required for `teradata*`, `vertica*`, and `netezza`; optional override when the local `bqms` launcher downloads the driver). Local mode only.

## 4. Credentials

Never type a literal password on the command line, and never ask the user to
paste it into the chat. Ask the user to run the password-file command below in
their own terminal, with `DB_PASSWORD` set there (for example with
`read -rs DB_PASSWORD && export DB_PASSWORD` in `bash` or `zsh`), or to create
the file another way, and to give you only its path. The commands stop with an
error instead of writing an empty password when `DB_PASSWORD` is unset. Which
mechanism to use depends on the run mode.

**Local mode: `@FILE` response file.** The local extractor reads `@FILE`
arguments as YAML response files and turns each key into a flag, so a file with
`password: ...` supplies `--password` without putting it on the command line.
Write it so only the user can read it, with the value single-quoted (any `'`
doubled) so special characters survive. This form works in `bash`, `zsh`, and
`sh` and assumes a single-line password:

```bash
: "${DB_PASSWORD:?DB_PASSWORD is not set}" && umask 077 && printf "password: '%s'\n" "$(printf '%s' "$DB_PASSWORD" | sed "s/'/''/g")" > ./extractor-secret.yaml
```

Pass `@./extractor-secret.yaml` after `--` (for a file outside the current
directory use an absolute path such as `@$HOME/path/file.yaml`; `@~/...` is not
expanded).

**Cloud mode: `--password` read from a file.** The CLI stores the extractor
arguments in Secret Manager exactly as given, and the VM runs the extractor with
them. The VM has none of your local files, so an `@FILE` argument fails there.
Put the password in a file only the user can read and pass it with command
substitution after `--`:

```bash
: "${DB_PASSWORD:?DB_PASSWORD is not set}" && umask 077 && printf '%s' "${DB_PASSWORD}" > ./db_password
```

```text
-- ... --password="$(cat ./db_password)"
```

The value then lives in the run's Secret Manager secret (delete it after the
run, Section 5) and is visible in this machine's process list while gcloud runs,
so use a machine only the user can access.

Delete the password file when done if you created it; leave a file the user
supplied in place.

## 5. Quick Start

Local (Teradata on-prem with the vendor driver):

```bash
gcloud alpha bq migration metadata extract \
    --connector=teradata \
    --output="gs://{bucket}/teradata_metadata/" \
    -- \
    --host="{teradata_host}" \
    --user="{db_user}" \
    --driver="{path_to}/terajdbc4.jar" \
    --assessment \
    @./extractor-secret.yaml
```

Cloud (Snowflake through the Cloud Extractor):

```bash
gcloud alpha bq migration metadata extract \
    --connector=snowflake \
    --output="gs://{bucket}/snowflake_metadata/{run_label}/" \
    --run-mode=cloud \
    --project="{project_id}" \
    --zone="{zone}" \
    --secret="bqms-extractor-creds-{run_label}" \
    -- \
    --host="{account_identifier}.snowflakecomputing.com" \
    --user="{db_user}" \
    --database="{db_name}" \
    --warehouse="{db_warehouse}" \
    --role="{db_role}" \
    --password="$(cat ./db_password)"
```

`--secret` is optional. Without it the CLI creates
`bqms-extractor-creds-run-EPOCH_SECONDS`, prints its name, and labels it
`goog-bqms-extractor-run-id`. If you pass `--secret`, use a new `{run_label}`
for every run: for a secret that already exists the CLI only adds a version,
and deleting that secret later would also delete its earlier versions.

Give every cloud run an `--output` prefix that holds no `.zip` yet, such as a
new `{run_label}` folder. gcloud reports success as soon as it finds any
non-empty `.zip` under `--output`, without checking when it was written. An
older archive there (from an earlier metadata, query-log, or local run) ends
the command at once with `Extraction complete` while the new VM is still
starting, and deleting the secret then breaks the real run. If the user names a
prefix, use it as given after checking that `gcloud storage ls
"gs://{bucket}/{path}/"` lists no `.zip`; otherwise propose a new sub-prefix.

Every answer that runs or recommends an extraction must include these steps, in
order, with their commands:

1.  Check the exit code and task summary (Section 6, step 1).
2.  Verify the output with the statistics template (Section 6, step 2): `cp
    <SKILL_DIR>/assets/extraction_stats_template.py ./extraction_stats.py &&
    python3 ./extraction_stats.py --input "gs://{bucket}/{path}/"`.
3.  After a cloud run, delete the run's Secret Manager secret once steps 1 and 2
    are done (or right away if the run failed), and say why: it still holds the
    database password. Delete the `--secret` name if you passed one: `gcloud
    secrets delete bqms-extractor-creds-{run_label} --project={project_id}
    --quiet`. Otherwise delete the auto-named
    `bqms-extractor-creds-run-EPOCH_SECONDS` secret the command printed, or find
    it with `gcloud secrets list
    --filter="labels.goog-bqms-extractor-run-id:*"`. Only delete secrets created
    for this run; if the user had you reuse an existing secret, record its
    newest version before the run and destroy only a version this run added.
    See the cleanup section of the
    [cloud extraction guide](references/cloud_extraction.md).
4.  Delete `extractor-secret.yaml` or `db_password` if you created it; leave a
    file the user supplied in place.

## 6. Check the Result

1.  **Exit code and task summary.** The extractor exits 1 when any required task
    fails. What that means depends on the run mode:

    *   **Local:** gcloud reports `BigQuery Migration Extractor failed with exit
        code 1`, but the extractor has already written the ZIP to `--output`,
        with a `*.exception.txt` entry for each failure. A ZIP present after
        this error is a partial success, not a reason to rerun.
    *   **Cloud:** the VM uploads the ZIP only when the extractor exits 0, so
        `Extraction complete` means success only if `--output` held no `.zip`
        before the run (Section 5). If any required task fails, nothing is
        uploaded and gcloud reports `Extraction finished, but no non-empty
        artifact was found`. Always tell the user both next steps: read the
        VM's logs to see why the extractor failed, and then either fix the
        cause and rerun, or rerun with `--run-mode=local`, which keeps the
        partial ZIP. gcloud prints a `gcloud logging read
        'resource.type="gce_instance" AND resource.labels.instance_id="..."'`
        command only when it finds error entries; otherwise query the logs by
        the VM name from the `Instance Link:` line (see Monitoring in the
        [cloud extraction guide](references/cloud_extraction.md)). Also delete
        the run's secret (Section 5).

    For a local partial ZIP, read the `N TASKS SUCCEEDED / N TASKS FAILED`
    summary and the exception entries (`unzip -l {archive}.zip
    '*.exception.txt'` lists the failed tasks; each file is long, so read just
    the error with `unzip -p {archive}.zip '{task}.exception.txt' | grep -m 3 -E
    '^\s*message:'`). A failure is harmless when a version-specific fallback of
    the same task succeeded; the fallback has a version suffix, for example
    `functions.csv.exception.txt` next to a populated `functions-11.csv` on
    PostgreSQL 11 and later.
2.  **Archive integrity and statistics.** Copy the
    [extraction statistics template][extraction_stats_template]
    (`<SKILL_DIR>/assets/extraction_stats_template.py`, where `<SKILL_DIR>` is
    the directory that contains this `SKILL.md`) into the working directory and
    run it on the ZIP, its folder, or the GCS prefix:

    ```bash
    cp <SKILL_DIR>/assets/extraction_stats_template.py ./extraction_stats.py
    python3 ./extraction_stats.py --input "gs://{bucket}/snowflake_metadata/"
    ```

    If the `gs://` form fails, copy the ZIP locally with `gcloud storage cp` and
    run the script on the local file.

    It rejects incomplete archives (22-byte placeholders) and reports the
    extractor telemetry status, counts of databases, schemas, base tables,
    views, and columns, total base table row counts and byte sizes, per-schema
    and per-table breakdowns, and the column data type distribution. See the
    [statistics report specification](references/extraction_stats_report.md)
    for the full report metrics and the `# CUSTOMIZE:` extension points (for
    example, editing `_EXCLUDED_SYSTEM_SCHEMAS` or `_should_include_schema()` to
    drop a `STAGING_TMP` schema).

> [!NOTE]
> The script computes object, row, and byte counts from the Snowflake, Redshift
> (`svv_*`), and Teradata (`dbc.*V`) catalog layouts, and table, view, and
> top-level column counts from the BigQuery `tables.jsonl` (rows and sizes show
> as `N/A` there because that connector does not record them). It reads the run
> status from `dumper-telemetry.jsonl` when the archive has one. For other
> layouts (for example PostgreSQL, Oracle, or the Hive `tables.jsonl`) it still
> validates the archive and reports the connector and host, but object counts
> are zero and the run status can show `UNKNOWN`. On PostgreSQL 11 and later it
> shows `FAILURE` because of the harmless `functions.csv` and `aggregates.csv`
> fallbacks (Section 6, step 1). Then use the task summary printed by the
> extract command for the run status, and count objects from the connector's
> own files (Section 7).

## 7. Output Archives

Unless `--output` names a `.zip` object, the extractor names the ZIP
`dwh-migration-{connector}-metadata.zip` for `metadata extract` connectors and
`dwh-migration-{connector}.zip` for `query-logs extract` connectors, whose names
already end in `-logs`: `snowflake` writes
`dwh-migration-snowflake-metadata.zip` and `snowflake-logs` writes
`dwh-migration-snowflake-logs.zip`. A few names differ (`oracle-stats` writes
`dwh-migration-oracle-stats.zip`; `hiveql`, and query logs extracted with
`--assessment`, add a `-YYYYMMDDTHHMMSS` timestamp), so list `--output` to find
the archive. Every archive contains `compilerworks-metadata.yaml` (extractor
version and arguments) plus connector-specific CSVs:

```text
dwh-migration-snowflake-metadata.zip
├── databases-au.csv            # Databases and owners
├── schemata-au.csv             # Schemas
├── tables-au.csv               # Tables, row counts, byte sizes
├── columns-au.csv              # Columns, ordinal positions, types, nullability
├── views-au.csv                # View DDL
├── functions-au.csv            # User-defined and external functions
├── external_tables.csv         # External stage tables
├── snowflake.yaml              # Assessment flag and warehouse count
├── compilerworks-metadata.yaml # Extractor version and flags
└── dumper-telemetry.jsonl      # Task timings

dwh-migration-snowflake-logs.zip
├── query_history_2026-08-05T000000Z.csv   # One file per rotation window
├── ...
└── compilerworks-metadata.yaml

dwh-migration-postgresql-metadata.zip
├── database.csv                # Databases on the server
├── is_columns_private.csv      # Columns of user tables and views
├── pg_views_private.csv        # User view DDL
├── functions-11.csv            # Functions on search_path (11+; drop pg_catalog)
├── aggregates-11.csv, types.csv, casts.csv
├── is_columns_generic.csv, pg_views_generic.csv   # System catalog objects
├── pg_user.csv                 # Roles and privileges (passwords masked)
├── *.csv.exception.txt         # One per failed task
└── compilerworks-{metadata.yaml,arguments.txt,version.txt,format.txt}
```

In PostgreSQL archives the `*_private.csv` files hold user objects and the
`*_generic.csv` files hold system objects. `is_columns_private.csv` includes
view columns; subtract the views in `pg_views_private.csv` to count base tables.
`functions-11.csv`, `aggregates-11.csv`, and `types.csv` list only objects
visible on the session `search_path` (`"$user", public` by default), so other
schemas' functions and types are missing. To include them, replace `--host`,
`--port`, and `--database` with
`--url="jdbc:postgresql://{host}:{port}/{db_name}?currentSchema={schema1},{schema2},public"`.

Archives never contain the database password: to confirm, check that
`compilerworks-arguments.txt` and `compilerworks-metadata.yaml` have no
`password` entry (scanning for the password value is unreliable when it is a
common word), but they do contain object DDL and role lists, and
`dumper-telemetry.jsonl` is copied from
`~/.cache/DWH-Dumper/all-dumper-telemetry.jsonl`, so it can hold connectors,
hosts, and errors from earlier extractor runs on the same machine. Treat them
as sensitive and keep them in a private bucket.

## 8. Downstream BigQuery Workflows

Each cloud run writes to its own `--output` prefix (Section 5). To hand the
archives over together, copy the finished ZIPs into one shared prefix, for
example `gcloud storage cp "gs://{bucket}/{run_prefix}/*.zip"
"gs://{bucket}/assessment/"`, and never use that shared prefix as a cloud
`--output`. Then:

1.  **BigQuery Migration Assessment**: direct the user to **BigQuery >
    Migration > Assessment** in the Google Cloud Console and give it the GCS
    prefix that holds the metadata (extracted with `--assessment`) and logs.
2.  **Batch SQL translation**: attach the metadata ZIP as schema context in
    **BigQuery > Migration > SQL translation**, or through the BigQuery
    Migration API / BQMS MCP tools (see `bigquery-migration-sql-translator`).
3.  **Table data transfer (out of scope)**: this skill extracts catalog metadata
    and query logs only. If the user asks to export or load table rows (such as
    Snowflake `COPY INTO` unloads), ask whether they want to use the
    [BigQuery Data Transfer Service][bq_dts] (including the
    [Snowflake transfer connector][snowflake_dts]) or export to Parquet/CSV in
    Cloud Storage and load with `bq load`.

[bq_dts]: https://docs.cloud.google.com/bigquery/docs/dts-introduction.md.txt
[cloud_locations]: https://cloud.google.com/about/locations
[extraction_stats_template]: assets/extraction_stats_template.py
[gcloud_install]: https://cloud.google.com/sdk/docs/install
[snowflake_dts]: https://docs.cloud.google.com/bigquery/docs/migration/snowflake-transfer.md.txt
