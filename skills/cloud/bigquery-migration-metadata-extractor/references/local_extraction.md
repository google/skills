# Local Extraction

`--run-mode=local` is the default: the command runs the DWH migration extractor
on this machine, connects to the database over this machine's network, and
writes the ZIP to `--output`. The recipes use a Cloud Storage path; local mode
also accepts a local file or directory path. It is the only mode that supports
vendor-licensed JDBC drivers.

## Contents

-   [Prerequisites](#prerequisites): Lines 15-54
-   [Recipes](#recipes): Lines 55-180
-   [Troubleshooting](#troubleshooting): Lines 181-193

## Prerequisites

1.  **Java 11 or later** on `PATH`; the extractor is a JVM program and the
    command refuses older Java versions. Set `JAVA_OPTS` to pass extra JVM
    options (for example `-Xmx4g`). Ask the user before installing Java.
2.  **The `bqms` gcloud component**, which contains the extractor. Ask the user
    before installing it. The extract command offers to install it, but
    without a terminal that prompt fails, so after the user agrees run `gcloud
    components install bqms --quiet` before the extraction. If gcloud was
    installed with `apt` or `yum`, install the `google-cloud-cli-bqms` package
    with that package manager instead.
3.  **Network access** from this machine to the database host and port. Test it
    first (for example `nc -vz {host} {port}`).
4.  **JDBC drivers**: the local extractor ships without JDBC drivers, and the
    `bqms` launcher downloads the drivers for `snowflake*`, `redshift*`,
    `postgresql`, `greenplum*`, `oracle*`, `sqlserver`, and `mysql` when you
    omit `--driver` (behind a proxy, set `HTTPS_PROXY`). For `teradata*`,
    `netezza`, and `vertica*`, download the vendor JAR and pass it after `--`
    with `--driver=/path/a.jar[,/path/b.jar]`.
5.  **A read-only database user** that can read the system catalog (and the
    query history views for `*-logs` connectors).
6.  **Application Default Credentials** for writing to a `gs://` `--output`.
    Check with `gcloud auth application-default print-access-token
    >/dev/null`; if it fails, run `gcloud auth application-default login`.
    Check that the bucket exists with `gcloud storage buckets describe
    gs://{bucket}`. The command itself checks that the bucket is owned by the
    current project (or `--expected-owner`) and is not public before it starts
    the extractor. That check needs `storage.buckets.list` on the owner
    project (for example `roles/storage.bucketViewer`), plus
    `storage.buckets.getIamPolicy` on the bucket (`roles/storage.admin`) unless
    public access prevention is enforced on it; object-level access alone is
    not enough.
7.  **The password response file** from SKILL.md Section 4
    (`./extractor-secret.yaml`), or the user's existing one in place.
8.  **A scratch working directory**: every run writes a `progress.log.TIMESTAMP`
    file to the current directory, so run the command from a scratch folder.

Delete `./extractor-secret.yaml` after the run if you created it for the
extraction; leave a file the user supplied in place.

## Recipes

All recipes use `metadata extract` except the query logs ones, which use
`query-logs extract`. gcloud flags come before `--`; database flags after.

### Snowflake catalog metadata

```bash
gcloud alpha bq migration metadata extract \
    --connector=snowflake \
    --output="gs://{bucket}/snowflake_metadata/" \
    -- \
    --host="{account_identifier}.snowflakecomputing.com" \
    --user="{db_user}" \
    --database="{db_name}" \
    --warehouse="{db_warehouse}" \
    --role="{db_role}" \
    @./extractor-secret.yaml
```

Pass `--warehouse` and `--role`; they apply to the extractor's session only. Do
not run `ALTER USER ... SET DEFAULT_WAREHOUSE` on shared accounts. For
Migration Assessment, pass `--assessment` and omit `--database` and `--schema`
(the `snowflake` connector rejects combining `--assessment` with `--database` or
`--schema`).

### Snowflake query logs

```bash
gcloud alpha bq migration query-logs extract \
    --connector=snowflake-logs \
    --output="gs://{bucket}/snowflake_logs/" \
    -- \
    --host="{account_identifier}.snowflakecomputing.com" \
    --user="{db_user}" \
    --warehouse="{db_warehouse}" \
    --role="{db_role}" \
    --query-log-start="2026-09-01" \
    --query-log-end="2026-10-01" \
    @./extractor-secret.yaml
```

`--query-log-start` is inclusive and `--query-log-end` is exclusive. Use
`--query-log-days=N` for the most recent N days instead.

### Teradata metadata for Migration Assessment

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

For query logs use `query-logs extract` with `--connector=teradata-logs`
(Teradata 15 and later) or `teradata14-logs`, the same `--driver`, and a query
log window.

### Oracle metadata

```bash
gcloud alpha bq migration metadata extract \
    --connector=oracle \
    --output="gs://{bucket}/oracle_metadata/" \
    -- \
    --host="{oracle_host}" \
    --port=1521 \
    --oracle-service="{service_name}" \
    --user="{db_user}" \
    @./extractor-secret.yaml
```

Use `--oracle-sid` instead of `--oracle-service` for SID-based connections. The
`bqms` launcher downloads the Oracle driver; add
`--driver="{path_to}/ojdbc8.jar"` only to use a specific JAR.

### Amazon Redshift metadata

```bash
gcloud alpha bq migration metadata extract \
    --connector=redshift \
    --output="gs://{bucket}/redshift_metadata/" \
    -- \
    --host="{cluster_name}.{xyz}.{region}.redshift.amazonaws.com" \
    --port=5439 \
    --database="{db_name}" \
    --user="{db_user}" \
    @./extractor-secret.yaml
```

For query logs use `query-logs extract` with `--connector=redshift-raw-logs` and
a query log window.

### PostgreSQL metadata

PostgreSQL has no query logs connector, and `--assessment` does not change its
output.

```bash
gcloud alpha bq migration metadata extract \
    --connector=postgresql \
    --output="gs://{bucket}/postgres_metadata/" \
    -- \
    --host="{postgres_host}" \
    --port=5432 \
    --database="{db_name}" \
    --user="{db_user}" \
    @./extractor-secret.yaml
```

The connector extracts only the first `--database` and ignores `--schema`, so
run it once per database, each with its own `--output`. `functions-11.csv`,
`aggregates-11.csv`, and `types.csv` list only objects visible on the session
`search_path` (`"$user", public` by default), so functions and types in other
schemas are missing. To include them, replace `--host`, `--port`, and
`--database` with a JDBC URL that sets `currentSchema`:

```text
    --url="jdbc:postgresql://{postgres_host}:5432/{db_name}?currentSchema={schema1},{schema2},public" \
```

## Troubleshooting

Symptom                                                                         | Cause and fix
:------------------------------------------------------------------------------ | :------------
`Invalid choice: 'migration'` or unknown command                                | Use the alpha track (`gcloud alpha bq migration ...`). If that still fails, ask the user, then update the Google Cloud CLI (`gcloud components update`, or upgrade the `google-cloud-cli` package with `apt` or `yum` if gcloud was installed that way).
`unrecognized arguments: --host=...`                                            | Database flags go after `--`.
`Connector '...' is a query-logs connector` (or `is a metadata connector`)      | Use `query-logs extract` for `*-logs` connectors and `metadata extract` for the rest.
`BigQuery Migration Extractor failed with exit code 1`, ZIP exists              | Some required tasks failed; the ZIP still holds everything that succeeded plus `*.exception.txt` entries. List them with `unzip -l archive.zip '*.exception.txt'`. A failure is harmless when a version-suffixed fallback (for example `functions-11.csv`) succeeded.
`JDBC driver encountered communication error` / connection refused or timed out | The host or port is unreachable from this machine. Check VPN, firewall, and allowlists; test with `nc -vz`.
`ClassNotFoundException` or "driver required"                                   | A Teradata, Netezza, or Vertica connector is missing `--driver` (after `--`), or the `bqms` launcher printed a warning that it could not download the driver (behind a proxy, set `HTTPS_PROXY`); pass `--driver`.
Authentication errors                                                           | Check the user, the response file (`password: '...'`, single-quoted), and connector-specific settings such as Snowflake `--role`.
Empty or missing query logs                                                     | The window is outside the source's retention, or the user lacks access to the query history views.
`gs://` output is 22 bytes while the extractor is running                       | The extractor streams the ZIP to Cloud Storage and writes a 22-byte placeholder first. Wait for the command to exit before reading it.
