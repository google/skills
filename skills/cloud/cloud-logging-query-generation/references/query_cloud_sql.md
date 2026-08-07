# Cloud SQL LQL queries

## Base schema and structural patterns

Cloud SQL logs use a unified resource type across all database engines but
drastically diverge in their specific `log_id` paths depending on whether the
instance is running MySQL, PostgreSQL, or SQL Server.

### Core resource type

*   **Cloud SQL Instance (`cloudsql_database`)**: universally use this resource
    type for all Cloud SQL operational and engine telemetry. Scope queries to a
    specific instance via `resource.labels.database_id="<DATABASE_ID>"`.

### Log divergence by engine

Cloud SQL does not abstract underlying database logs; it surfaces the native
engine streams directly into Cloud Logging:

*   **MySQL**: Targets `log_id("cloudsql.googleapis.com/mysql.err")` for
    critical engine errors and `log_id("cloudsql.googleapis.com/mysql")` for
    general output.
*   **PostgreSQL**: Consolidates output entirely under
    `log_id("cloudsql.googleapis.com/postgres.log")`.
*   **SQL Server**: Emits `log_id("cloudsql.googleapis.com/sqlserver.err")` for
    core engine telemetry and `log_id("cloudsql.googleapis.com/sqlagent.out")`
    for SQL Server Agent execution logs.

### Administrative control plane

*   **Audit Logs**: Query `log_id("cloudaudit.googleapis.com/activity")`
    alongside `resource.type="cloudsql_database"` to audit control plane
    operations (for example: instance creation, patching, scaling, or
    restarting).

## Example queries

### Cloud SQL audit logs

**Variables to replace:** `<DATABASE_ID>`

```lql
resource.type="cloudsql_database" AND
resource.labels.database_id="<DATABASE_ID>" AND
log_id("cloudaudit.googleapis.com/activity")
```

### Cloud SQL MySQL error logs

**Variables to replace:** None

```lql
resource.type="cloudsql_database" AND
log_id("cloudsql.googleapis.com/mysql.err")
```

### Cloud SQL MySQL-based databases

**Variables to replace:** `<DATABASE_ID>`

```lql
resource.type="cloudsql_database" AND
resource.labels.database_id="<DATABASE_ID>" AND
log_id("cloudsql.googleapis.com/mysql")
```

### Cloud SQL Postgres-based databases

**Variables to replace:** `<DATABASE_ID>`

```lql
resource.type="cloudsql_database" AND
resource.labels.database_id="<DATABASE_ID>" AND
log_id("cloudsql.googleapis.com/postgres.log")
```

### Cloud SQL SQL Server error logs

**Variables to replace:** None

```lql
resource.type="cloudsql_database" AND
log_id("cloudsql.googleapis.com/sqlserver.err")
```

### Cloud SQL SQL Server-based databases

**Variables to replace:** `<DATABASE_ID>`

```lql
resource.type="cloudsql_database" AND
resource.labels.database_id="<DATABASE_ID>" AND
log_id("cloudsql.googleapis.com/sqlagent.out")
```
