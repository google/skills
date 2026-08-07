---
name: spanner-basics
metadata:
  category: Databases
description: >-
  Assists in provisioning instances and databases, designing performant schemas, and querying data in Spanner. Use when designing primary keys, writing SQL queries or client library code, or diagnosing performance issues.
---

# Spanner Basics

This skill provides core workflows and guidance for administering and developing with Google Cloud Spanner, a fully managed, mission-critical database service offering global transactional consistency and automatic, synchronous replication for high availability.

## Core Principles

-   **Performance First:** Spanner scales horizontally. Efficiency is tied to
    Primary Key design. Always warn against using monotonically increasing/decreasing
    values (like sequential timestamps) as the first part of a primary key to avoid hotspots.
-   **Schema Design:** Prefer interleaved tables for strongly related parent-child data
    that is frequently accessed together.

## Safety

> [!CAUTION] **CRITICAL INSTRUCTION:** You MUST obtain explicit user confirmation before making any non-emulator database changes (DML or DDL) or destructive operations (such as dropping tables, indexes, or any other Spanner resources). Do not execute them automatically; instead, output the command (e.g., `gcloud spanner databases ddl update`) and ask for explicit user approval.
> When database access is unavailable or authentication fails, do not block on trying to verify the existence of the instance, database, or table. Assume the provided resources exist and directly generate the DDL commands.

## Common Workflows

### Schema Evolution & DDL

1.  Use `gcloud spanner databases ddl update` to apply schema updates (such as CREATE, ALTER, or DROP tables and indexes).
2.  Reference [schema-design.md](references/schema-design.md) for guidelines on primary key selection and interleaved tables.

### Diagnosing Performance Issues

1.  Use `SPANNER_SYS` tables to identify slow or resource-intensive queries.
2.  For example, query `SPANNER_SYS.QUERY_STATS_TOP_HOUR` to find queries with the highest CPU usage.

## Reference Directory

- [Core Concepts](references/core-concepts.md): Explanation of Spanner internals, architecture, and design.
- [CLI Usage](references/cli-usage.md): Essential `gcloud spanner` command-line operations for managing instances and databases.
- [IAM Security](references/iam-security.md): Roles, permissions, and data governance best practices for Spanner.
- [Client Library Usage](references/client-library-usage.md): Using Google Cloud client libraries for Spanner (Java, Go, Python, Node.js).
- [Terraform Usage](references/terraform-usage.md): Infrastructure as Code examples for provisioning Spanner instances and databases.
- [MCP Usage](references/mcp-usage.md): Using the Spanner remote MCP server.
- [PostgreSQL Dialect](references/postgresql-dialect.md): Best practices and examples for using the PostgreSQL interface in Spanner.
- [Schema Design](references/schema-design.md): Guidelines on primary key selection and interleaved tables for performance.

If you need product information that's not found in these references, use the
`search_documents` tool of the Developer Knowledge MCP server.
