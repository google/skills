# Connections, credentials, and drivers

How the validation tool connects to source databases and BigQuery.

## Contents

*   [1. Supported dialects](#1-supported-dialects): Lines 12-40
*   [2. Credentials](#2-credentials): Lines 42-106
*   [3. JDBC URLs](#3-jdbc-urls): Lines 108-117
*   [4. JDBC drivers](#4-jdbc-drivers): Lines 119-136

## 1. Supported dialects

`dialect` values: `teradata`, `snowflake`, `oracle`, `redshift`, `databricks`,
`postgresql`, `sqlserver` (alias `mssql`), `mysql`, `mariadb`, `hive`, `impala`,
`vertica`, `duckdb`, and `bigquery` (target).

When no connections exist yet, `validation configure` scaffolds
`connections.yaml` with the properties each dialect expects (host, port,
database, warehouse, role, and so on). Every property can also come from an
environment variable (Section 2).

Check the scaffolded source `dialect` before running. For a PostgreSQL
metadata archive, `configure` can scaffold `dialect: snowflake` with `account`
and `warehouse`; replace that block with the real dialect and its properties.
A PostgreSQL source with a BigQuery target:

```yaml
connections:
  source:
    dialect: postgresql
    host: pg.example.com
    port: 5432
    database: salesdb
    user: migrator              # password from env or Secret Manager
  target:
    dialect: bigquery
    projectId: my-project
    dataset: sales              # required
```

## 2. Credentials

Never write passwords into config files. The tool reads connection properties
from environment variables, which override YAML:

```text
BQMS_VALIDATION_<CONNECTION>_<PROPERTY>
```

`<CONNECTION>` is the connection name in uppercase. Lookup is case-insensitive.
Connection names may contain only letters and digits; a name such as `sales_db`
or `sales-db` is rejected with a config error before anything runs. Use
`salesdb` instead (environment prefix `BQMS_VALIDATION_SALESDB_`) and tell the
user about the rename.

```bash
export BQMS_VALIDATION_SOURCE_USER='migrator'
export BQMS_VALIDATION_SOURCE_PASSWORD='...'
export BQMS_VALIDATION_SNOWSRC_WAREHOUSE='REPORTING_WH'
```

Plaintext password exports like the one above are for the user to run in
their own terminal. An agent must never ask for a password in the conversation,
echo one, or export one in its own shell (transcripts keep it, and the variable
does not persist between separate commands). For commands the agent runs, use a
Secret Manager reference (`passwordSecret` or
`BQMS_VALIDATION_<CONN>_PASSWORD_SECRET`).

### Secret Manager

A password can be a Secret Manager reference instead of a value. The tool
resolves the password from the first of these that is set:

1.  env `BQMS_VALIDATION_<CONN>_PASSWORD` (cleartext or full reference)
2.  env `BQMS_VALIDATION_<CONN>_PASSWORD_SECRET` (any reference)
3.  YAML `password` (cleartext or full reference)
4.  YAML `passwordSecret` (any reference)

A full reference is `projects/P/secrets/S[/versions/V]` or `sm://P/S[/V]`.
`_PASSWORD` and `password` treat any other value as a literal password. Only
`_PASSWORD_SECRET` and `passwordSecret` also accept `P/S[/V]` or a bare secret
ID with optional `:version`. The version defaults to `latest`.

The secret's project comes from `BQMS_VALIDATION_<CONN>_SECRET_PROJECT_ID`, YAML
`secretProjectId`, `GOOGLE_CLOUD_PROJECT`, or `GCP_PROJECT`, in that order. To
read the secret as a service account, set
`BQMS_VALIDATION_<CONN>_SECRET_IMPERSONATE_SERVICE_ACCOUNT` or YAML
`secretImpersonateServiceAccount`.

```yaml
connections:
  source:
    dialect: snowflake
    account: ab98765.europe-west4.gcp
    user: migrator
    passwordSecret: sm://my-project/snowflake-migrator
    database: SALES
    schema: PUBLIC
```

### BigQuery target

The target uses Application Default Credentials. The BigQuery connection
requires `projectId` and `dataset` (even when table names are fully qualified),
and also accepts `impersonateServiceAccount` and `credentialsFile`.

## 3. JDBC URLs

Authentication modes that are not plain user and password (SSO, key pair, OAuth,
tokens) are usually set through JDBC URL parameters. Supply the full URL as the
`url` property, or as `BQMS_VALIDATION_<CONN>_URL` when it holds a token.

```text
jdbc:snowflake://ACCOUNT.snowflakecomputing.com/?authenticator=externalbrowser&role=SYSADMIN&warehouse=LOAD_WH
jdbc:databricks://HOST:443/default;transportMode=http;ssl=1;AuthMech=3;httpPath=HTTP_PATH
```

## 4. JDBC drivers

Drivers are downloaded on first use from Maven Central, checked against a pinned
SHA-256, and cached under `~/.cache/google-cloud-bqms/drivers`:

Downloaded automatically                                                              | Supplied by the user
:------------------------------------------------------------------------------------ | :-------------------
Oracle, Snowflake, Redshift, Databricks, PostgreSQL, SQL Server, MySQL, MariaDB, Hive | Teradata (`terajdbc4.jar`), Vertica (`vertica-jdbc.jar`), Impala (Cloudera Impala JDBC driver), DuckDB (DuckDB JDBC driver)

The BigQuery driver is bundled.

*   Put user-supplied JARs in `./drivers`, or point `BQMS_DRIVER_DIR` at their
    directory.
*   On machines without internet access, set `BQMS_AUTO_DOWNLOAD_DRIVERS=false`
    and place the JARs in the driver directory, or set `BQMS_MAVEN_MIRROR` to an
    internal Maven mirror.
*   A "driver not found" error for Teradata, Vertica, Impala, or DuckDB means
    the JAR is missing from the driver directory; it is never downloaded.
