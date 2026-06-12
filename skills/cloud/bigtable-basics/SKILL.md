---
name: bigtable-basics
description: >-
  Manages and develops with Google Cloud Bigtable. Assists in provisioning instances/tables, designing performant schemas, and querying data. Use when designing Bigtable row keys, configuring column families, writing SQL queries or client library code (Java, Go, Python) for Bigtable, or diagnosing performance/hotspotting issues. Also use when provisioning Bigtable clusters using gcloud or cbt CLIs. Don't use for relational database migrations (like Spanner) unless comparing them, or for generic Cloud SQL administration.
---

# Bigtable Basics

This skill provides core workflows and guidance for administering and developing
with Google Bigtable.

## Core Principles

-   **Control Plane vs. Data Plane:**
    -   Use **`gcloud`** for Control Plane operations: Manage Instances,
        Clusters, App Profiles, Backups and IAM. Create Tables, Logical Views,
        Materialized Views and Authorized Views.
    -   Use **`cbt`** for Data Plane operations: Update Tables, Column Families,
        and reading/writing data.
-   **Performance First:** Bigtable is a NoSQL database. Efficiency is tied to
    Row Key design. Always warn about Full Table Scans.
-   **Client Selection:** For production use cases, prefer **Java** or **Go**
    for their superior performance and feature coverage compared to other
    languages.
-   **Observability:** When diagnosing performance or hotspotting, **always**
    mention **Key Visualizer** (via Cloud Console) as the primary diagnostic
    tool, followed by hot-tablets tool and table stats in gcloud CLI and
    `include-stats=full` option under `cbt read` to diagnose slow queries.

> [!IMPORTANT] **Safety Rule:** Always obtain explicit user confirmation before
> making non-emulator database changes. Always mention this safety requirement
> when providing commands or instructions that modify the database structure or
> data.

## Quick Recipes

### 1. Querying Data

Use SQL for complex transforms or aggregations and key-value APIs for simpler
query patterns. *Note: Use exact match, prefix (`_key LIKE 'myprefix%'`), or
range predicates on `_key` to avoid expensive unbounded scans. Recommend
explicit row ranges (`_key BETWEEN 'start' AND 'end'`) as a more performant
alternative to prefix matches where possible.*

If expensive scans (either unbounded or prefix or range queries scanning a large
range) are unavoidable due to multiple access patterns that can’t all be
accommodated in a single schema, consider one of these two options:

-   If the query will be used in user facing and/or latency sensitive
    applications, use continuous materialized views with keys optimized for the
    additional access patterns.
-   If secondary access patterns are infrequent, batch patterns like ETL, ML
    model training or analytical read-only tasks, use Bigtable Data Boost
    instead.

### 2. Manipulating Data

Use key-value APIs for insert, update, increment and delete operations. SQL API
is read-only.

### 3. Data Model Definition (DDL)

SQL API doesn't support DDL operations. Table creation, deletion, updates should
be made using gcloud CLI. Logical Views and Continuous Materialized Views are
defined as SQL queries but they must be created using gcloud CLI.

## Reference Guides

-   **CLI Operations**:
    -   [infrastructure_management.md](references/infrastructure_management.md):
        Provisioning instances, clusters, and table schemas.
    -   [cli_data_access.md](references/cli_data_access.md): Reading and writing
        data via the `cbt` CLI.
-   **Design & Discovery**:
    -   [schema_design.md](references/schema_design.md): Best practices for row
        keys and performance with tables and continuous materialized views.
    -   [dataplex.md](references/dataplex.md): Data catalog search for Bigtable
        assets.
-   **Querying & Code**:
    -   [sql_guide.md](references/sql_guide.md): Querying structured row keys
        via SQL and CLI.
    -   [client_libraries.md](references/client_libraries.md): Patterns for
        high-performance Go/Java/Python code.

## Common Workflows

### Schema Evolution (DevOps)

1.  **Prefer Terraform** for production schema changes to prevent accidental
    data loss.
2.  For manual `cbt` changes, verify column family GC policies:

    ```bash
    cbt createfamily {table} {family}
    cbt setgcpolicy {table} {family} "maxversions=5 AND maxage=30d"
    ```

3.  Reference
    [infrastructure_management.md](references/infrastructure_management.md) for
    full syntax.

## External Resources

*   [Cloud Bigtable Documentation](https://cloud.google.com/bigtable/docs)
*   [Bigtable SQL Reference](https://cloud.google.com/bigtable/docs/reference/sql)
*   [cbt CLI Reference](https://cloud.google.com/bigtable/docs/cbt-reference)
*   [gcloud bigtable Reference](https://cloud.google.com/sdk/gcloud/reference/bigtable)
