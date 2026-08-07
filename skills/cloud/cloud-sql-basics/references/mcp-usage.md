# Cloud SQL MCP Usage

Cloud SQL can be managed via the Model Context Protocol (MCP), which allows
agents to manage database instances, execute SQL queries, and automate backup or
migration workflows.

MCP is available via remote Google Cloud MCP servers and through local execution
with the MCP Toolbox.

## Google Cloud MCP for Cloud SQL

The Cloud SQL MCP server includes the following tools:

-   `clone_instance`: Creates a Cloud SQL instance as a clone of a source
    instance.
-   `create_backup`: Creates an on-demand backup of a Cloud SQL instance.
-   `create_instance`: Initiates the creation of a Cloud SQL instance.
-   `create_user`: Creates a database user for a Cloud SQL instance.
-   `execute_sql`: Executes any valid SQL statements (DDL, DCL, DQL, DML) on a
    Cloud SQL instance.
-   `execute_sql_readonly`: Safely executes read-only SQL queries on a Cloud
    SQL instance.
-   `get_instance`: Gets details and status of a Cloud SQL instance.
-   `get_operation`: Gets the status of a long-running operation in Cloud SQL.
-   `import_data`: Imports data into a Cloud SQL instance from Cloud Storage.
-   `list_instances`: Lists all Cloud SQL instances in a project.
-   `list_users`: Lists all database users for a Cloud SQL instance.
-   `postgres_upgrade_precheck`: Performs pre-checks before upgrading
    PostgreSQL engine versions.
-   `restore_backup`: Restores a backup to a Cloud SQL instance.
-   `update_instance`: Updates supported settings of a Cloud SQL instance.
-   `update_user`: Updates a database user for a Cloud SQL instance.

## Server Toolsets & IAM Requirements

-   **Full MCP Set Endpoint:** `https://sqladmin.googleapis.com/mcp` (Exposes
    all management, query, and backup tools).
-   **Read-Only Toolset Endpoint:**
    `https://sqladmin.googleapis.com/mcp/readonly` (Restricts access to
    read-only tools like `execute_sql_readonly`).
-   **Required IAM Role:** Using the Cloud SQL remote MCP server requires the
    `roles/mcp.toolUser` role in addition to Cloud SQL resource roles (e.g.,
    `roles/cloudsql.admin` or `roles/cloudsql.editor`).

## Setup Instructions

For remote server setup, see the documentation for:
-   [PostgreSQL MCP](https://docs.cloud.google.com/sql/docs/postgres/use-cloudsql-mcp.md.txt)
-   [MySQL MCP](https://docs.cloud.google.com/sql/docs/mysql/use-cloudsql-mcp.md.txt)
-   [SQL Server MCP](https://docs.cloud.google.com/sql/docs/sqlserver/use-cloudsql-mcp.md.txt)

## Supported Operations

Agents using the Cloud SQL MCP can:

-   Automate database schema migrations.
-   Create and restore instance backups on-demand.
-   Run engine version upgrade pre-checks (PostgreSQL).
-   Perform health checks and monitor operation logs.
-   Assist in debugging SQL performance issues using read-only or full SQL
    execution tools.

## MCP toolbox for databases

MCP toolbox for databases can be installed locally and provide various
predefined and custom tools for Cloud SQL. Read more about MCP Toolbox in the
documentation.

-   [Cloud SQL for PostgreSQL](https://mcp-toolbox.dev/integrations/cloud-sql-pg/source/)
-   [Cloud SQL for MySQL](https://mcp-toolbox.dev/integrations/cloud-sql-mysql/source/)
-   [Cloud SQL for SQL Server](https://mcp-toolbox.dev/integrations/cloud-sql-mssql/source/)

