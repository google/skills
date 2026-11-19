---
name: spanner-relational-to-graph
metadata:
  version: "1.0.0"
  category: Databases
description: >-
  Analyzes existing Spanner relational schemas on Google Cloud (DDL, foreign
  keys, interleaved tables, and junction tables) and generates
  `CREATE PROPERTY GRAPH` DDL statements (`NODE TABLES`, `EDGE TABLES`) without
  modifying underlying relational tables. Use when mapping existing Spanner
  tables to a Spanner Graph, identifying node and edge candidates from
  relational tables, creating SQL bridge views for implicit `ARRAY`/`JSON` or
  type-mismatched relationships, mapping polymorphic or self-referential tables,
  or troubleshooting `CREATE PROPERTY GRAPH` DDL compiler errors. Don't use for
  greenfield physical table design (use spanner-graph-schema-best-practices) or
  tuning slow ISO GQL queries (use spanner-graph-query-tuning).
---

# Spanner Relational-to-Property-Graph Schema Conversion

Convert an existing Spanner relational schema into a valid, production-ready
`CREATE OR REPLACE PROPERTY GRAPH` DDL definition while keeping existing
relational tables intact.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you MUST
read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Prerequisites & Cloud Environment Setup

When inspecting a live Spanner instance or verifying DDL (see `spanner-basics`
for general Spanner instance provisioning and MCP setup):

1. **Google Cloud SDK (`gcloud`)**: Ensure the CLI is installed (see
   [Install the Google Cloud SDK](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt)).
2. **Project, Billing & API**: Verify an active Google Cloud project with
   billing enabled (required even when provisioning a free trial instance) is
   configured (`gcloud config set project {project_id}`) and, after the user
   confirms, enable the Spanner API
   (`gcloud services enable spanner.googleapis.com`). Ask the user before
   changing the active project, billing, or enabled APIs, or creating or
   deleting instances, because these commands change the user's Google Cloud
   environment and can incur costs.
3. **Authentication & IAM Roles**: Authenticate via `gcloud auth login` or
   `gcloud auth application-default login` (or `GOOGLE_APPLICATION_CREDENTIALS`
   for service accounts). Listing instances/databases requires
   `roles/spanner.viewer`, inspecting DDL requires
   `roles/spanner.databaseReader`, and applying `CREATE VIEW` /
   `CREATE PROPERTY GRAPH` DDL requires `roles/spanner.databaseAdmin`.
4. **Instance Region & Pricing**: For sandbox test instances, default to
   `regional-us-central1` unless specified otherwise (see
   [Spanner instance configurations](https://docs.cloud.google.com/spanner/docs/instance-configurations.md.txt),
   [Google Cloud locations](https://cloud.google.com/about/locations),
   [Spanner pricing](https://cloud.google.com/spanner/pricing), and
   [Google Cloud pricing](https://cloud.google.com/pricing)).

---

## Core Principles

1. **Zero Data Duplication**: Spanner Graph maps existing relational tables or
   SQL views directly into graph nodes and edges via `CREATE PROPERTY GRAPH`
   metadata—without copying data or breaking existing SQL applications.
2. **Preserve Existing Tables**: Treat all existing relational tables as
   read-only inputs. Do not drop, rename, or alter existing columns or primary
   keys when adding a property graph view. If an implicit relationship requires
   key transformation (for example, unnesting an array or casting mismatched key
   types), define a new SQL bridge view
   (`CREATE VIEW ... SQL SECURITY INVOKER AS ...` by default, or
   `SQL SECURITY DEFINER` when row-level access control is needed) and bind the
   edge or node to that view.
3. **100% Table Accounting**: Account for every relational table in the input
   schema—either mapped into `NODE TABLES` / `EDGE TABLES` or explicitly listed
   as excluded (such as pure system audit logs, schema migration state tables,
   or unlinked lookup tables).

---

## Step-by-Step Conversion Workflow

### Step 1: Discover or Parse the Relational Schema

- **If the user provides DDL statements in the prompt**, parse all
  `CREATE TABLE`, `PRIMARY KEY`, `INTERLEAVE IN PARENT`, and `FOREIGN KEY`
  definitions directly.
- **If the user provides a live Spanner instance and database ID** (or a Google
  Cloud Console URL containing
  `instances/{instance_id}/databases/{database_id}?project={project_id}`),
  extract `project`, `instance`, and `database` and retrieve the live DDL using
  the read-only `gcloud` command:

  ```bash
  gcloud spanner databases ddl describe {database_id} \
    --instance={instance_id} \
    --project={project_id}
  ```

  - **Live-Database Safety Rule**: `gcloud spanner databases ddl describe` is
    read-only and safe to run automatically, whereas applying `CREATE VIEW` or
    `CREATE OR REPLACE PROPERTY GRAPH` via `gcloud spanner databases ddl update`
    mutates the live database—always ask for **explicit user confirmation**
    before running `gcloud spanner databases ddl update` (and state this
    confirmation requirement clearly in your response even if `ddl describe`
    fails due to missing credentials or network access).
  - See [references/cloud-spanner-guide.md](references/cloud-spanner-guide.md)
    for environment discovery, emulator setup, and verification workflows.

### Step 2: Classify Relational Tables into Nodes and Edges

Apply the structural classification rules in
[references/patterns.md](references/patterns.md):

1. **Core Entity Tables -> `NODE TABLES`**:
   - Tables representing domain nouns (`Users`, `Accounts`, `Products`,
     `Devices`, `Documents`) become node tables.
   - Use the table's full `PRIMARY KEY` as the node `KEY (...)`.
2. **Pure or Attributed M:N Junction Tables -> `EDGE TABLES`**:
   - Tables that link two entity keys (such as
     `ProjectAssignments(emp_id, project_id)` or `WireTransfers(transfer_id)`
     with `src_account_id` and `dst_account_id`) become edge tables.
   - If the table also represents an entity referenced by other tables (for
     example, `Orders` is a child of `Customers` and a parent of `OrderItems`),
     map `Orders` as **both** a `NODE TABLE` (`Orders AS OrderNode`) and an
     `EDGE TABLE` (`Orders AS PlacedOrder`).
3. **1:N Foreign Keys and Interleaved Parent-Child Tables -> `EDGE TABLES`
   (`Table AS Edge`)**:
   - An entity table `B` with a foreign key (or interleaved parent key prefix)
     referencing `A` can simultaneously act as a `NODE TABLE` (`B AS NodeB`) and
     an `EDGE TABLE` (`B AS EdgeBA`) connecting `B` to `A` (or `A` to `B`).
   - **Self-Referential Hierarchies**: A table like
     `Employees(emp_id, manager_id)` maps to `Employees AS Employee` in
     `NODE TABLES` and `Employees AS ReportsToEdge` in `EDGE TABLES`
     (`SOURCE KEY (emp_id) REFERENCES Employee(emp_id)` and
     `DESTINATION KEY (manager_id) REFERENCES Employee(emp_id)`).
4. **Implicit Relationships (Arrays, JSON, Polymorphic Keys) -> Bridge Views**:
   - When relationships are embedded in `ARRAY<INT64>` columns, JSON fields, or
     type-mismatched keys (`INT64` vs. `STRING`), create a SQL bridge view that
     flattens and projects `(edge_key, src_key, dst_key)` and register the view
     in `EDGE TABLES` with an explicit `KEY (...)`.
   - **View Security (`INVOKER` vs. `DEFINER`)**: Every Spanner view requires a
     `SQL SECURITY` clause. `SQL SECURITY INVOKER` is the common default when
     callers already hold permissions on the underlying tables, whereas
     `SQL SECURITY DEFINER` is supported when you need row-level / fine-grained
     access control so callers can query the graph view without direct
     base-table grants.
   - **View Key Uniqueness & `validate_element_key_uniqueness`**: By default,
     Spanner syntactically verifies that a view's declared `KEY` is unique
     (either a single base table's primary key or matched by `SELECT DISTINCT` /
     `GROUP BY`), failing otherwise with
     `cannot verify the specified element key ... is unique`. Use
     `SELECT DISTINCT` (or `GROUP BY` the key columns) when inputs can contain
     duplicate keys (such as duplicate elements inside an `ARRAY`); if you know
     the view's `KEY` is **already semantically unique** (for example, a
     key-preserving `JOIN` or `UNNEST(...) WITH OFFSET`), you can instead append
     `OPTIONS (validate_element_key_uniqueness = false)` to
     `CREATE PROPERTY GRAPH` to skip syntactic validation without extra
     `DISTINCT` / `GROUP BY` overhead (you remain responsible for ensuring keys
     are unique in data).

### Step 3: Decide Graph Scoping (Unified vs. Multi-Graph)

- **Default to 1 Unified Property Graph** when tables share a connected domain.
- **Recommend Multiple Property Graphs** only when the database contains
  completely disconnected business domains or exceeds ~12+ distinct node/edge
  types where domain-specific subgraphs improve query ergonomics.

### Step 4: Author the `CREATE OR REPLACE PROPERTY GRAPH` DDL

Follow the exact syntax and structural invariants in
[references/spanner-graph-ddl-syntax.md](references/spanner-graph-ddl-syntax.md)
and [references/structural-invariants.md](references/structural-invariants.md):

```sql
CREATE OR REPLACE PROPERTY GRAPH GraphName
  NODE TABLES (
    TableName AS NodeAlias
      KEY (pk_col1, pk_col2)
      LABEL NodeLabel
  )
  EDGE TABLES (
    EdgeTableName AS EdgeAlias
      KEY (edge_pk_col1, edge_pk_col2)
      SOURCE KEY (src_fk_col1) REFERENCES SourceNodeAlias(src_pk_col1)
      DESTINATION KEY (dst_fk_col1) REFERENCES DestNodeAlias(dst_pk_col1)
      LABEL EdgeLabel
  );
```

#### Critical DDL Invariants Checklist

- `NODE TABLES` must be declared **before** `EDGE TABLES`.
- Every `NodeAlias` and `EdgeAlias` must be **globally unique** across the
  entire `CREATE PROPERTY GRAPH` statement (if a table is used as both a node
  and an edge, give them distinct aliases, e.g., `Orders AS OrderNode` and
  `Orders AS PlacedOrderEdge`).
- **Decouple Edge Identity (`KEY`) from Endpoint Topology (`SOURCE KEY` /
  `DESTINATION KEY`)**:
  - `KEY (...)` uniquely identifies the edge row in the backing table or view
    (for example, `KEY (transfer_id)` or `KEY (src_id, dst_id, transfer_ts)`),
    while `SOURCE KEY` and `DESTINATION KEY` specify the endpoints. Spanner
    enforces uniqueness: on a table, a custom `KEY` must contain all primary key
    columns or match a `UNIQUE` index (so `KEY (src_id, dst_id, transfer_ts)` on
    a table whose primary key is `transfer_id` fails unless such an index
    exists). Rows where any `KEY`, `SOURCE KEY`, or `DESTINATION KEY` column is
    `NULL` are silently skipped by `MATCH`.
  - In `SOURCE KEY (...) REFERENCES NodeAlias(...)` and
    `DESTINATION KEY (...) REFERENCES NodeAlias(...)`, the target after
    `REFERENCES` must be the **`NodeAlias`** (not the underlying relational
    table name if an alias was used, and not the `LABEL` name), and the column
    count and data types must match the referenced node's `KEY` 1-to-1. Spanner
    does not always enforce the count: with an explicit column list it accepts a
    partial composite key, and each edge then silently matches every node
    sharing that value.
- **Property Exposure (Default `ALL COLUMNS` vs. Explicit `PROPERTIES (...)` /
  `NO PROPERTIES`)**:
  - By default, omitting the `PROPERTIES` clause (implicit
    `PROPERTIES ALL COLUMNS`) exposes all columns of the input table and is
    concise when a table has its own label and non-conflicting column types.
  - Use explicit `PROPERTIES (col1 [AS alias], ...)`,
    `PROPERTIES ALL COLUMNS EXCEPT (...)`, or `NO PROPERTIES` in four
    relational-conversion cases: (1) **cross-table property type conflicts**
    (aliasing colliding column names), (2) **shared `LABEL`s** across tables,
    (3) **dual `Table AS Node` + `Table AS Edge` or pure junction mappings**
    (`NO PROPERTIES` or edge-only columns so node attributes are not duplicated
    onto edges), and (4) **excluding internal/sensitive columns or avoiding
    duplicate exposure of a `DYNAMIC PROPERTIES (json_col)` column**
    (`PROPERTIES ALL COLUMNS EXCEPT (json_col)`).
  - If two elements share the same `LABEL` name, they must expose the **exact
    same set of property names and data types** under that label.
  - A property name must have **one data type across the whole graph**, even
    under different labels or on node vs. edge tables (for example, `id INT64`
    in one table and `id STRING` in another fails with
    `The property declaration of 'id' has type conflicts`). Alias
    (`id AS user_id`) or `CAST` one side.
- **Optional Reverse Edge Alias (Naming Only)**:
  - A single physical edge table can be registered a second time in
    `EDGE TABLES` under a reverse alias (swapping `SOURCE KEY` and
    `DESTINATION KEY`) when the domain needs a distinct directional label. Don't
    add one for performance: for undirected traversals use `-[e:LABEL]-` plus a
    reverse index; querying a swapped-key alias as a label union forces a union
    across two edge definitions at every hop, which is slower than `-[e:LABEL]-`
    on quantified paths.

### Step 5: Verify the DDL and Provide Recommendations

1. **Verify the DDL** (when a target Spanner database or local emulator is
   available; see
   [references/cloud-spanner-guide.md](references/cloud-spanner-guide.md)).
   Never apply DDL to a shared or production database without explicit user
   confirmation.
2. **Present a Structured 5-Part Deliverable** (modeled in
   [references/synthesized-conversions.md](references/synthesized-conversions.md)):
   - **Part 1: Graph Extension Summary & Mapping Matrix** (100% accounting of
     included and excluded tables).
   - **Part 2: Complete Executable Spanner Graph DDL** (any required
     `CREATE VIEW ... SQL SECURITY {INVOKER | DEFINER}` statements followed by
     `CREATE OR REPLACE PROPERTY GRAPH`).
   - **Part 3: Performance & Indexing Recommendations** (such as
     reverse-traversal secondary indexes
     `ON EdgeTable (dst_key, src_key) INTERLEAVE IN DestNodeTable` or
     `STORING (...)`, simplifying over-wide composite keys on junction tables,
     and high-degree hub foreign-key considerations).
   - **Part 4: Sample ISO GQL Queries** using
     `GRAPH GraphName MATCH ... RETURN ...` (see
     [references/gql-cheat-sheet.md](references/gql-cheat-sheet.md)).
   - **Part 5: Schema Verification Status**.

---

## Reference Documentation

- **[Spanner Discovery Guide](references/cloud-spanner-guide.md)**: Extracting
  DDL from Spanner via `gcloud`, parsing console URLs, and validating
  `CREATE PROPERTY GRAPH` on a sandbox or Spanner Emulator.
- **[Relational-to-Graph Mapping Patterns](references/patterns.md)**: Detailed
  rules for classifying entity tables, junction tables, interleaved hierarchies,
  self-referential FKs, polymorphic tables, and SQL bridge views.
- **[Spanner Graph DDL Syntax](references/spanner-graph-ddl-syntax.md)**: Exact
  BNF grammar and syntax rules for `CREATE PROPERTY GRAPH`, `NODE TABLES`,
  `EDGE TABLES`, `KEY`, and `PROPERTIES`.
- **[Structural Invariants](references/structural-invariants.md)**: How to
  prevent and fix the 8 most common Spanner Graph DDL mistakes (alias
  collisions, shared-label and graph-wide property type conflicts, partial or
  mismatched key references, unverifiable view keys, and custom key uniqueness),
  with the actual Spanner error messages.
- **[ISO GQL Cheat Sheet](references/gql-cheat-sheet.md)**: Quick syntax
  reference for writing valid Spanner Graph ISO GQL queries (`MATCH`,
  `WHERE`/`FILTER`, quantified paths `{m,n}`, `NEXT`, `RETURN`).
- **[Synthesized Examples](references/synthesized-conversions.md)**: Four
  complete relational-to-property-graph conversion examples (E-Commerce,
  Financial AML, Enterprise Org Matrix, and Threat Intelligence).
- **Official Spanner Graph Schema Design Documentation**:
  [Spanner Graph schema design best practices](https://docs.cloud.google.com/spanner/docs/graph/best-practices-designing-schema.md.txt)

If you need product information that's not found in these references, use the
`search_documents` tool of the Developer Knowledge MCP server.
