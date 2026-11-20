# Spanner Schema Discovery & DDL Verification Guide

## 1. Extracting Parameters from Google Cloud Console URLs

If a user supplies a Google Cloud Console link to a Spanner database, extract
the target `{instance_id}`, `{database_id}`, and `{project_id}` directly from
the URL pattern:

- **URL Pattern**:
  `https://console.cloud.google.com/spanner/instances/{instance_id}/databases/{database_id}?project={project_id}`
  (or sub-paths such as `/schema`, `/graph`, `/query`).
- Extract:
  - `{instance_id}`: segment immediately following `/instances/`
  - `{database_id}`: segment immediately following `/databases/`
  - `{project_id}`: value of the `project=` query parameter

## 2. Discovering Relational Schema DDL via `gcloud`

1. **When `{project_id}`, `{instance_id}`, and `{database_id}` are known**,
   fetch the full relational schema DDL directly (requires
   `roles/spanner.databaseReader`):
   ```bash
   gcloud spanner databases ddl describe {database_id} \
     --instance={instance_id} \
     --project={project_id}
   ```

2. **When `{instance_id}` or `{database_id}` are omitted**, discover them
   interactively (requires `roles/spanner.viewer`):
   ```bash
   # Check current default project
   gcloud config get-value project

   # List Spanner instances in the project
   gcloud spanner instances list --project={project_id}

   # List databases in the target instance
   gcloud spanner databases list --instance={instance_id} --project={project_id}
   ```
   If multiple databases exist and the target is ambiguous, present the
   discovered list and ask the user which database to target before proceeding.

## 3. Safe DDL Verification Workflow

### Safety Guardrail for Live Databases

- **Read-Only Discovery**: `gcloud spanner databases ddl describe` and
  `gcloud spanner instances/databases list` are read-only and safe to run
  automatically.
- **Explicit Confirmation for Schema Updates**: Applying `CREATE VIEW` or
  `CREATE OR REPLACE PROPERTY GRAPH` via `gcloud spanner databases ddl update`
  mutates database metadata (requires `roles/spanner.databaseAdmin`). Always ask
  for explicit user confirmation before executing `ddl update` against a shared
  or production Spanner instance.

### Option A: Applying DDL on an Authorized Spanner Database
Once the user confirms target execution:
```bash
gcloud spanner databases ddl update {database_id} \
  --instance={instance_id} \
  --project={project_id} \
  --ddl="$(cat graph_schema.sql)"
```

### Option B: Hermetic Verification on the Local Spanner Emulator

Prefer Option A on a user-confirmed Spanner instance whenever one is available
(for example, applying the DDL to an empty development database on the same
instance), because the emulator doesn't reproduce every engine-specific
validation. Use the emulator only as a fallback when no Spanner instance is
available, and tell the user that emulator validation is a best-effort check
that should be repeated on a real instance before production use.

To validate the combined relational + property graph DDL without touching a
remote database, follow the official
[Spanner Emulator guide](https://docs.cloud.google.com/spanner/docs/emulator.md.txt)
(if the emulator isn't installed, ask the user before installing it). Create an
isolated `gcloud` configuration (`--no-activate`) and pass
`--configuration=emulator` on every command so verification never reaches a real
instance, apply the combined DDL via `gcloud spanner databases create` with
`--ddl-file=combined_schema_and_graph.sql`, and delete the temporary emulator
database and instance when finished.

### Smoke-Testing the Property Graph with GQL
After applying the DDL on a sandbox or emulator, run a lightweight 1-hop ISO GQL
query to confirm element bindings (on the emulator, replace
`--project={project_id}` with `--configuration=emulator`):
```bash
gcloud spanner databases execute-sql {database_id} \
  --instance={instance_id} \
  --project={project_id} \
  --sql="GRAPH MyGraph MATCH (n)-[e]->(m) RETURN LABELS(n)[SAFE_OFFSET(0)] AS src_label, LABELS(e)[SAFE_OFFSET(0)] AS edge_label, LABELS(m)[SAFE_OFFSET(0)] AS dst_label LIMIT 5"
```
