---
name: spanner-graph-schema-best-practices
metadata:
  version: "1.0.0"
  category: Databases
description: >-
  Designs, reviews, and optimizes physical table schemas, indexes, and graph
  topologies for Spanner Graph on Google Cloud. Use when creating a new Spanner
  Graph schema, selecting node and edge primary key types, optimizing forward,
  reverse, or per-node Top-K edge traversals, designing interleaved node or edge
  tables and covering indexes, configuring cascading deletes and row deletion
  policies (TTL), evaluating schematized versus schemaless dynamic label graphs,
  or folding 1:1 and N:1 edges into node tables. Don't use for tuning GQL query
  syntax or execution plans without schema changes (use
  spanner-graph-query-tuning), or when creating a zero-change graph overlay on
  existing relational tables (use spanner-relational-to-graph).
---

# Spanner Graph Schema Design & Topology Best Practices

Design and optimize physical table layouts, primary keys, secondary indexes, and
graph topologies for **Spanner Graph** (`CREATE PROPERTY GRAPH`) to maximize
performance.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Safety & Verification Rules

- **Obtain Confirmation Before Mutating Remote Databases**: Do not execute
  `gcloud spanner databases ddl update`, `create`, or `delete` against a remote
  Spanner instance without explicit user confirmation, because DDL mutations on
  live databases can trigger long-running schema backfills or break production
  queries. Always validate candidate DDL on the local Spanner Emulator first or
  output the DDL commands for user approval.
- **Obtain Confirmation Before Changing the Cloud Environment**: Ask the user
  before running `gcloud services enable`, changing the active project or
  billing account, or creating or deleting Spanner instances, because these
  commands change the user's Google Cloud environment and can incur costs.
- **Inspect Live Catalog Read-Only**: When reviewing an existing Spanner
  database, export the schema with `gcloud spanner databases ddl describe
  {database_id} --instance={instance_id} --project={project_id}` rather than
  guessing column types or key orders.

## Prerequisites & Cloud Environment Setup

Before running `gcloud spanner` or emulator commands, verify that the
environment meets these Google Cloud requirements (see `spanner-basics` for
general Spanner instance provisioning and MCP setup):

1. **Google Cloud SDK & Static DDL Fallback**: Verify whether the CLI is
   installed (do not install `gcloud` without explicit user permission; see
   [Install the gcloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt)).
   If `gcloud` or the local emulator is unavailable, generate and review the
   Spanner Graph DDL statically using the rules and reference templates below.
2. **Project, Billing & API Enablement**: Configure the target project (`gcloud
   config set project {project_id}`), ensure an active billing account is
   attached (required even when provisioning a free trial instance; see
   [Spanner pricing](https://cloud.google.com/spanner/pricing) and
   [Google Cloud pricing](https://cloud.google.com/pricing)), and, after the
   user confirms, enable the API:
   ```bash
   gcloud services enable spanner.googleapis.com --project={project_id}
   ```
3. **Authentication**: Authenticate with `gcloud auth login` (interactive CLI),
   `gcloud auth application-default login` (local SDKs), or
   `GOOGLE_APPLICATION_CREDENTIALS` (service accounts).
4. **Required Identity and Access Management (IAM) Roles (Least Privilege)**:
   - `roles/spanner.databaseReader` (or `roles/spanner.viewer`) to inspect DDL
     via `gcloud spanner databases ddl describe`.
   - `roles/spanner.databaseAdmin` to create databases or apply schema updates
     (`gcloud spanner databases ddl update`).
5. **Region & Instance Configuration**: When creating a new instance, select a
   supported regional or multi-region configuration such as
   `regional-us-central1` (`gcloud config set spanner/instance {instance_id}`;
   see [Instance configurations](https://docs.cloud.google.com/spanner/docs/instance-configurations.md.txt)
   and [Cloud locations](https://cloud.google.com/about/locations)).

## Terminology Glossary

Use these canonical terms consistently when reasoning about and explaining
Spanner Graph schemas:

Term | Definition
--- | ---
**Node table** | A physical Spanner table projected in `NODE TABLES` of `CREATE PROPERTY GRAPH`; each row is one node.
**Edge table** | A physical table (or a node table projected a second time under an alias) listed in `EDGE TABLES`; each row is one directed edge from `SOURCE KEY` to `DESTINATION KEY`.
**Node type / Edge type** | One node or edge table projection in the property graph, identified by its name or alias (for example, `IpCard AS HasCard` is an edge type).
**Label** | The query-time name attached to a node or edge type via `LABEL` (static) or `DYNAMIC LABEL` (schemaless). One type can declare multiple labels, and one label can be shared by multiple types.
**Property** | A column or scalar SQL expression (for example, `CAST(...)` or `LOWER(...)`) exposed on a node or edge type via `PROPERTIES (...)` or `DYNAMIC PROPERTIES`.
**Folded edge** | A `many-to-{0,1}` or `many-to-1` edge stored as a foreign-key column on the source node table, projected via `{node_table} AS {edge_type}` instead of a separate edge table.
**1:N containment child node** | A node table interleaved in its parent node table (`INTERLEAVE IN PARENT`) because each child is owned by exactly one parent; it serves as both a node type and the parent-to-child edge type.
**Remote interleaved index** | A secondary index on an edge table co-located with the destination node table via `INTERLEAVE IN {dest_node_table}` (no `PARENT` keyword) to accelerate reverse traversal.
**Hub / super node** | A node with thousands or millions of incoming or outgoing edges.

## Core Schema Design Workflow

Follow this 5-step workflow when designing a new Spanner Graph schema or
optimizing an existing one.

**MUST READ**: Steps 1–4 below are abbreviated summaries that include only
short structural DDL snippets. The complete decision rules, trade-offs, and
full multi-table `CREATE TABLE`, `CREATE INDEX`, and `CREATE PROPERTY GRAPH`
examples live in the reference guides; before recommending or generating DDL,
read [Topology & Edge Folding](references/topology-and-edge-folding.md) (for
Steps 1–2) and
[Edge Traversal & Indexing](references/edge-traversal-and-indexing.md) (for
Steps 3–4).

### Step 1: Choose Schematized vs. Schemaless Data Management

Select the graph storage model based on schema stability and query patterns.
Read the *Compare schema types* section of the official
[Spanner Graph schema design best practices](https://docs.cloud.google.com/spanner/docs/graph/best-practices-designing-schema.md.txt)
alongside [Topology & Edge Folding](references/topology-and-edge-folding.md)
for the full decision matrix:

Option | Best For | Key Mechanism
--- | --- | ---
**Schematized (Default)** | Stable domain models, strong type enforcement, non-JSON native types (`TIMESTAMP`, `INT64`, `NUMERIC`), and single-type quantified paths | Separate typed node/edge tables with explicit `LABEL` and `PROPERTIES (col1, col2)` declarations
**Schemaless (Hybrid Properties Design)** | Many node or edge types that are impractical to maintain as separate tables, frequently evolving schemas, polymorphic edges that connect many different node types, or latency-sensitive quantified path queries (`-{1, 3}->`) that span multiple node or edge labels | Single node table and single edge table using `DYNAMIC LABEL (label)` and `DYNAMIC PROPERTIES (properties)`, plus an explicit `PROPERTIES (...)` list that keeps any frequently filtered or indexed columns as typed static properties alongside the `JSON` payload

If the user hasn't already described their schema and workload, ask before
choosing: how many node and edge types they need to maintain (for example, more
than 50 node types and 150 edge types), and whether latency-sensitive queries
traverse multiple labels (for example, `-[:Transfer|Withdraw]->{1, 3}`) across a
large number of intermediate paths (for example, more than 10,000).

Store `DYNAMIC LABEL` values in lowercase and enforce it with
`CHECK (label = LOWER(label))`. Rows with uppercase or mixed-case label values
silently get no dynamic label and drop out of labeled `MATCH` patterns (query
labels themselves are case-insensitive).

### Step 2: Optimize Physical Primary Keys & Topology Restructuring

Before creating secondary indexes, optimize the physical table topology so
common traversals execute as local primary-key prefix seeks instead of
distributed joins. Read
[Topology & Edge Folding](references/topology-and-edge-folding.md) for full
multi-table DDL examples and apply these rules:

1. **Re-Key Standalone Edge Tables by `(src_id, dst_id, [edge_id])`, Enforce
   `NOT NULL`, and Prefer `INT64` / Native `UUID` Keys**:
   - Avoid using a synthetic `PRIMARY KEY (edge_id)` as the leading key column
     on an edge table, because outgoing traversals from a source node cannot
     seek on `src_id` and must scan the entire table or rely on a secondary
     index.
   - Define `PRIMARY KEY ({src_key_cols}, {dst_key_cols}, [{uniquifier_col}])`,
     declare all primary key and endpoint foreign key columns `NOT NULL` (which
     eliminates null-check branches in execution plans), and interleave the edge
     table into the source node table (`INTERLEAVE IN PARENT {source_node_table}
     ON DELETE CASCADE`):

     ```sql
     CREATE TABLE AccountTransfer (
       src_id      INT64 NOT NULL,
       dst_id      INT64 NOT NULL,
       transfer_id INT64 NOT NULL,
     ) PRIMARY KEY (src_id, dst_id, transfer_id),
       INTERLEAVE IN PARENT Account ON DELETE CASCADE;
     ```

   - Prefer `INT64` keys (bit-reversed sequence or random/hashed `INT64`) for
     node and edge keys on traversal-heavy graphs. If you need UUIDs, use the
     native `UUID` type rather than `STRING(36)`: 36-byte string keys widen
     secondary indexes and make multi-hop joins slower and more CPU-intensive
     than 8-byte `INT64` or 16-byte native `UUID` keys.
2. **Advanced — Co-Locate Strict 1:N Containment Child Node Tables
   (`INTERLEAVE IN PARENT`)**:
   - **Cardinality Guardrail — Strict `1:N` Containment Only**: Use this
     advanced technique only when each child node is owned by exactly one
     parent node and cannot exist without it (strict `1:N` physical
     containment, such as `IpCard` belonging to one `IpNode`, or `Subnet`
     belonging to one `Vpc`). If the relationship is many-to-many (`M:N`)—for
     example, an `IpCard` or `Vrf` that can connect to multiple `IpNode`s—or
     the child is an independent entity, **never** interleave the child node
     table under the other node table; keep both as standalone node tables and
     model the relationship as a dedicated edge table interleaved in the source
     node table (Step 2.1). Confirm the cardinality with the user before
     applying this layout.
   - When strict `1:N` containment applies, prefix the child node's primary key
     with the parent's primary key and declare `INTERLEAVE IN PARENT
     {parent_node_table}`. This co-locates parent and child nodes in the same
     storage split AND lets the child table serve directly as the
     parent-to-child edge type without a separate edge table:

     ```sql
     CREATE TABLE IpCard (
       ip_id   STRING(64) NOT NULL,
       card_id STRING(64) NOT NULL,
     ) PRIMARY KEY (ip_id, card_id),
       INTERLEAVE IN PARENT IpNode ON DELETE CASCADE;
     -- In CREATE PROPERTY GRAPH:
     -- NODE TABLES (IpNode KEY (ip_id), IpCard KEY (ip_id, card_id))
     -- EDGE TABLES (IpCard AS HasCard SOURCE KEY (ip_id) REFERENCES IpNode (ip_id)
     --   DESTINATION KEY (ip_id, card_id) REFERENCES IpCard (ip_id, card_id))
     ```

   - **Always Reference the Full Composite Key**: Because interleaving changes
     the child node's primary key to `({parent_key}, {child_key})`, always
     declare `KEY ({parent_key}, {child_key})` on the child node table and list
     every key column in any `SOURCE KEY` or `DESTINATION KEY` referencing it.
     Referencing only `{child_key}` against a 2-column `KEY` is accepted by
     Spanner and silently matches every row sharing that partial key.
3. **Fold `many-to-{0,1}` and `many-to-1` Edges into the Source Node Table**:
   - When each source node has **at most one** outgoing edge of a given type to
     a target node (`many-to-{0,1}` or `many-to-1`, such as
     `(IpNode)-[:ipOnOptical]->(OpticalNode)`), store the target key
     (`optical_node_id`) as a column directly on the source node table and
     project that table in both `NODE TABLES` (`IpNode`) and `EDGE TABLES`
     (`IpNode AS IpOnOpticalEdge`). A `NULL` target key means the node has no
     such edge (`many-to-0`):

     ```sql
     CREATE TABLE IpNode (
       ip_id           STRING(64) NOT NULL,
       optical_node_id STRING(64),
       FOREIGN KEY (optical_node_id) REFERENCES OpticalNode (optical_node_id),
     ) PRIMARY KEY (ip_id);
     -- In CREATE PROPERTY GRAPH:
     -- EDGE TABLES (IpNode AS IpOnOpticalEdge
     --   SOURCE KEY (ip_id) REFERENCES IpNode (ip_id)
     --   DESTINATION KEY (optical_node_id) REFERENCES OpticalNode (optical_node_id)
     --   LABEL ipOnOptical)
     ```

     Folding removes a separate edge table to maintain and write. The query
     speedup is modest and appears only when a query filters on or returns
     source-node properties, because the node and its edge come from the same
     row; key-only traversals perform the same as with an interleaved edge
     table.
   - **Enforce the Folded Foreign Key, Never `ON DELETE CASCADE`**: Declare the
     target-key column as an enforced foreign key to the target node table so it
     can't point to a missing node. `ON DELETE CASCADE` on this foreign key
     would delete the source node rows, not just their edges; to delete a
     target node, first set the referencing target keys to `NULL`. Use
     `NOT ENFORCED` only for target node tables in datasets with high-degree hub
     nodes, after confirming the trade-off with the user (see Step 3).
   - **Cardinality Guardrail — Do Not Fold `M:N` Edges into Node Tables**: Never
     fold a many-to-many (`M:N`) edge into a node table by adding `target_id` to
     the node's primary key, because doing so duplicates the node row for every
     connected target and corrupts node-level aggregations like
     `MATCH (n:Node) RETURN COUNT(n)`. Keep `M:N` relationships in a dedicated
     edge table interleaved in the source node table.
4. **Consolidate 1:1 Subtype Nodes & Fold 1:1 Intermediate Pass-Through Hops**:
   - Merge fragmented 1:1 subtype tables (e.g., `RouterNode`, `SwitchNode`,
     `FirewallNode` sharing the same entity key) into a unified node table (such
     as `DeviceNode`) with a type discriminator column (such as `device_type`).
   - If there is no need to model an intermediate pass-through node type in the
     graph, fold 1:1 pass-through intermediate tables (such as a `CableNode`
     table where each cable only connects two `Router` endpoints via
     `Router <-[:terminatedBy]- CableNode -[:terminatedBy]-> Router`) directly
     into a single edge table so each router-to-router step is 1 hop instead of
     2. Doing so leaves the intermediate node type (`CableNode`) out of the
     graph schema: its attributes become edge properties, it can no longer be
     matched as a node (`MATCH (c:CableNode)`), and it cannot have edges of its
     own. **Confirm with the user that this is desired before choosing this
     model** (see Section 5.2 of
     [Topology & Edge Folding](references/topology-and-edge-folding.md) for the
     before-and-after comparison):

     ```sql
     CREATE TABLE Router (
       router_id STRING(64) NOT NULL,
       site_name STRING(128),
     ) PRIMARY KEY (router_id);

     -- Each cable becomes one edge row between its two routers.
     CREATE TABLE CableLink (
       router_id      STRING(64) NOT NULL,
       peer_router_id STRING(64) NOT NULL,
       cable_id       STRING(64) NOT NULL,
       capacity_gbps  INT64,
       FOREIGN KEY (peer_router_id) REFERENCES Router (router_id),
     ) PRIMARY KEY (router_id, peer_router_id, cable_id),
       INTERLEAVE IN PARENT Router ON DELETE CASCADE;

     CREATE OR REPLACE PROPERTY GRAPH CableGraph
       NODE TABLES (Router)
       EDGE TABLES (
         CableLink
           SOURCE KEY (router_id) REFERENCES Router (router_id)
           DESTINATION KEY (peer_router_id) REFERENCES Router (router_id)
           LABEL cableLink PROPERTIES (cable_id, capacity_gbps)
       );
     -- One router-to-router hop: MATCH (a:Router)-[:cableLink]->(b:Router)
     ```

5. **Align Shared Label Properties and Graph-Wide Property Types**:
   - When multiple node or edge tables share the same `LABEL`, expose the exact
     same property names and SQL data types across every table declaring that
     label. Moreover, across the **entire property graph** (even between
     unrelated labels or between nodes and edges), any property with the same
     exposed name must have the same SQL data type (`The property declaration of
     'id' has type conflicts...`). Use column aliases or scalar SQL expressions
     such as `CAST({col} AS {target_type}) AS {property_name}` in
     `PROPERTIES (...)` when underlying column types differ.

### Step 3: Optimize Forward & Reverse Edge Traversals

Configure physical co-location, foreign keys, and covering indexes for all
remaining edge tables as detailed in
[Edge Traversal & Indexing](references/edge-traversal-and-indexing.md):

1. **Forward Traversal (`(src)-[e]->(dst)`)**:
   - Interleave the edge table into the source node table (`INTERLEAVE IN PARENT
     {source_node_table} ON DELETE CASCADE`) and add a `FOREIGN KEY
     ({dst_key_cols}) REFERENCES {dest_node_table} ({dst_key_cols})` on the
     destination key so the Spanner query optimizer can prune the destination
     node table scan when queries only need the destination key:

     ```sql
     CREATE TABLE PersonOwnAccount (
       person_id   INT64 NOT NULL,
       account_id  INT64 NOT NULL,
       create_time TIMESTAMP,
       FOREIGN KEY (account_id) REFERENCES Account (id),
     ) PRIMARY KEY (person_id, account_id),
       INTERLEAVE IN PARENT Person ON DELETE CASCADE;
     ```

   - For target node tables in datasets with high-degree **hub / super nodes**
     (where individual target nodes receive thousands or millions of concurrent
     incoming edges), consider a table-level informational foreign key (`NOT
     ENFORCED`, configured on the table's `FOREIGN KEY` constraint rather than
     per individual node) to avoid write lock contention on hub rows during
     concurrent edge inserts while preserving optimizer join elimination.
     Confirm this trade-off with the user first: informational foreign keys
     don't prevent dangling edges, and because the optimizer uses them by
     default, queries can return results that don't match the data if an edge
     points to a missing node. Keep the foreign key enforced when the user needs
     strict referential integrity.
2. **Reverse (`(dst)<-[e]-(src)`) & Any-Direction (`(a)-[e]-(b)`) Traversal**:
   - Create a **Remote Interleaved Index** keyed by
     `({dst_key_cols}, {src_key_cols})` with a `STORING ({edge_properties})`
     clause and `INTERLEAVE IN {dest_node_table}` (without the `PARENT`
     keyword):

     ```sql
     CREATE INDEX {edge_table}ByDst
     ON {edge_table} ({dst_id}, {src_id})
     STORING ({edge_prop_1}, {edge_prop_2}),
     INTERLEAVE IN {dest_node_table};
     ```

   - **Note on `INTERLEAVE IN PARENT` vs. `INTERLEAVE IN`**: While
     `INTERLEAVE IN PARENT` on a child table requires exact column *name*,
     type, and order matching, `INTERLEAVE IN {dest_node_table}` on a secondary
     index (Remote Index) uses *positional type matching*—so `{dst_id}`
     co-locates in `{dest_node_table}`'s split even when the column name
     differs from `{dest_node_table}`'s primary key name.
   - **Store Non-Key Edge Columns by Default**: Including `{src_id}` in the
     index key and, by default, adding all non-key edge columns to the `STORING`
     clause (matching the Spanner Graph UI modeler behavior) enables a 100%
     index-only scan without back-joining to the base edge table. If the edge
     table has many or wide columns, discuss with the user which frequently
     accessed edge properties to keep in `STORING`.
   - **Undirected Queries on Directed Edges (`-[e:Transfers]-{1,4}`)**: Keep
     plain any-direction traversal backed by the reverse index above. Don't add
     a second swapped-key reverse edge type in `CREATE PROPERTY GRAPH` for
     performance: querying it as a label union
     (`-[:Transfers|ReverseTransfer]->{1,3}`) forces Spanner to evaluate a union
     across two edge types at every hop, which is slower than
     `-[:Transfers]-{1,3}`.
   - **Mutually Symmetric Relationships (`Friend`, `Peer`) Stored as Directed
     Pairs**: When an application stores each symmetric relationship as two
     directed rows (`(user_a, user_b)` and `(user_b, user_a)` in one
     transaction) under `PRIMARY KEY (src_id, dst_id)`, always query with
     directed `-[:Friend]->` so outgoing traversals seek a single primary-key
     prefix (especially beneficial on high-degree nodes). Never query a
     double-stored edge table with undirected `-[:Friend]-`: because both
     `(A, B)` and `(B, A)` exist in the table, an undirected pattern matches
     both rows and returns every neighbor twice (and full-scans the table if no
     reverse index exists).

### Step 4: Add Property-Filtering Indexes & Prevent Dangling Edges

By default, initial schema creation only requires primary keys and
topology/reverse-traversal indexes (Steps 2–3); you do not need to index node or
edge properties up front. Add the property-filtering indexes in items 1–2 below
only when the user's queries filter (`WHERE` / `FILTER`) or sort (`ORDER BY ...
LIMIT k`) on specific non-key properties (see Section 3 of
[Edge Traversal & Indexing](references/edge-traversal-and-indexing.md)):

1. **Node Property Filtering Indexes**: Create secondary indexes on node
   columns frequently used in `WHERE` / `FILTER` clauses. Use `WHERE {col} IS
   NOT NULL` (NULL-filtered index) for sparse properties to save storage and
   write overhead:

   ```sql
   CREATE INDEX AccountByNickName ON Account (nick_name) STORING (is_blocked);
   CREATE INDEX AccountByCloseTime ON Account (close_time) WHERE close_time IS NOT NULL;
   ```

2. **Edge Property Filtering & Per-Node Top-K Indexes**:
   - For forward or reverse traversal with edge property filters, lead the index
     with the traversal endpoint key followed by the filtered column, and
     interleave into the endpoint node table.
   - For per-node Top-K queries (`ORDER BY e.{ts} DESC LIMIT k` from an anchored
     node) on high-degree nodes, index `({src_id}, {ts} DESC)` with `STORING` so
     Spanner pushes `LIMIT k` directly into the index scan and reads only `k`
     index rows instead of sorting the full adjacency list:

     ```sql
     -- Forward filter on (src_id, create_time)
     CREATE INDEX PersonOwnAccountByTime
       ON PersonOwnAccount (person_id, create_time), INTERLEAVE IN Person;
     -- Per-node Top-K by create_time DESC
     CREATE INDEX AccountTransferByTimeDesc
       ON AccountTransferAccount (src_id, create_time DESC) STORING (amount),
       INTERLEAVE IN Account;
     ```

   - Never list the edge table's primary key columns in `STORING`; they are
     already part of every index and Spanner rejects the DDL.
3. **Referential Integrity & TTL (`ROW DELETION POLICY`)**:
   - Prevent dangling edges (edges pointing to deleted nodes) using `INTERLEAVE
     IN PARENT {source_node_table} ON DELETE CASCADE` and `FOREIGN KEY ... ON
     DELETE CASCADE` on the destination node.
   - **Same-Node-Type Edge Exception**: When an edge connects two nodes of the
     **same** table (e.g., `Account -> Account` in `AccountTransferAccount`),
     Spanner does not allow combining `INTERLEAVE IN PARENT Account ON DELETE
     CASCADE` with a second `ON DELETE CASCADE` foreign key to `Account`. If
     symmetric cascading deletes are required when either endpoint is deleted,
     make the edge table standalone (not interleaved) with two enforced
     `FOREIGN KEY ... REFERENCES Account (id) ON DELETE CASCADE` constraints.
   - When adding a `ROW DELETION POLICY (OLDER_THAN({timestamp_col}, INTERVAL
     {n} DAY))` to a node table, ensure all attached edge tables either cascade
     deletes (`ON DELETE CASCADE`) or use informational foreign keys (`NOT
     ENFORCED`, which leaves dangling edges for the application to clean up),
     because Spanner rejects node TTL policies if enforced non-cascading child
     edges block expiration.

### Step 5: Validate Schema DDL & Tear Down Temporary Resources

Validate the generated DDL against the real Spanner engine whenever possible
before presenting it as final:

1. **Preferred — Validate on a User-Confirmed Spanner Instance**: Ask the user
   whether they have a Spanner instance (for example, a development or test
   instance) where you may create a temporary, empty database, and confirm the
   instance and database name before creating anything (creating a database
   can incur costs). Apply the complete schema (tables, indexes, and `CREATE
   PROPERTY GRAPH`) to that empty database:
   ```bash
   gcloud spanner databases create {temp_database_id} \
     --instance={instance_id} --project={project_id} \
     --ddl-file={schema_file}
   ```
   Never apply unvalidated DDL to an existing database that contains data.
2. **Fallback — Local Spanner Emulator**: If no Spanner instance is available,
   follow the official
   [Spanner Emulator guide](https://docs.cloud.google.com/spanner/docs/emulator.md.txt)
   to start or connect to the local emulator (if it isn't installed, ask the
   user before installing it). Create an isolated `gcloud` configuration
   (`gcloud config configurations create emulator --no-activate`) and pass
   `--configuration=emulator` on every validation command so DDL never reaches a
   real instance, then apply the schema with `gcloud spanner databases create
   {database_id} --instance={instance_id} --ddl-file={schema_file}
   --configuration=emulator`. Because the emulator doesn't reproduce every
   engine-specific validation, tell the user that emulator validation is a
   best-effort check and recommend re-validating on a real instance before
   production use. If neither `gcloud` nor the emulator is available, verify
   the DDL statically against the checklist below.
3. If the compiler reports errors (such as mismatched shared label properties,
   invalid key arity in `SOURCE KEY` / `DESTINATION KEY`, or conflicting
   `ON DELETE CASCADE` constraints on same-type nodes), fix the DDL and re-run
   until validation succeeds.
4. **Clean Up Temporary Validation Resources**: Delete the temporary validation
   database when finished (`gcloud spanner databases delete {temp_database_id}
   --instance={instance_id} --quiet`, adding `--configuration=emulator` for the
   emulator; also delete any temporary emulator instance with `gcloud spanner
   instances delete {instance_id} --quiet --configuration=emulator`) so the
   user doesn't incur ongoing storage charges.
5. Run through the **Schema Verification Checklist** below before returning the
   final DDL.

## Schema Verification Checklist

- [ ] **No Monotonic Primary Keys & Compact Key Types**: Node and standalone
      edge primary keys avoid sequential timestamps or auto-incrementing
      integers as the first key part (prefer random/bit-reversed `INT64` or
      native `UUID` over `STRING(36)`).
- [ ] **Edge Key Prefix & Co-Location**: Dedicated `M:N` edge tables use
      `PRIMARY KEY ({src_key}, {dst_key}, ...)` and `INTERLEAVE IN PARENT
      {source_node_table}`.
- [ ] **Interleaved Child Nodes Are Strict 1:N**: Node tables interleaved in
      another node table (`INTERLEAVE IN PARENT`) represent strict `1:N`
      containment; `M:N` relationships between node types use a dedicated edge
      table instead.
- [ ] **Folded Pass-Through Node Types Are User-Confirmed**: Any 1:1
      intermediate node type folded into an edge table (and therefore absent
      from the graph schema) was explicitly confirmed with the user.
- [ ] **Cardinality-Safe Edge Folding**: Only `many-to-{0,1}` and `many-to-1`
      edges are folded into source node tables via `Table AS Edge`; all `M:N`
      edges remain in separate edge tables so node row counts (`COUNT(n)`) are
      never inflated, and folded target-key columns use enforced foreign keys
      without `ON DELETE CASCADE`.
- [ ] **Reverse Traversal Index Coverage**: Every edge traversed in reverse
      (`<-[e]-`) or any direction (`-[e]-`) has a secondary index on
      `({dst_key}, {src_key})` with `STORING (...)` (and `INTERLEAVE IN
      {dest_node_table}` when key prefixes align).
- [ ] **Destination Join Elimination**: Edge tables define foreign keys on
      `DESTINATION KEY` columns (enforced by default; `NOT ENFORCED` only for
      hub nodes after the user accepts the dangling-edge risk).
- [ ] **Shared Label Uniformity**: Any `LABEL` shared across multiple tables
      exposes identical property names and data types (using `CAST` where
      needed).
- [ ] **Dangling Edge & TTL Safety**: `ON DELETE CASCADE` and `ROW DELETION
      POLICY` rules are consistent across parent nodes and attached edges.

## Reference Guides

- [Edge Traversal & Indexing](references/edge-traversal-and-indexing.md):
  Complete DDL patterns for forward interleaving, destination foreign keys,
  reverse covering `STORING` indexes, property-filtering indexes, same-node-type
  cascades, and TTL policies.
- [Topology & Edge Folding](references/topology-and-edge-folding.md): Decision
  matrix for schematized vs. schemaless graphs, multi-table label alignment, 1:N
  node hierarchy interleaving, 1:1 subtype consolidation, and cardinality-safe
  `many-to-{0,1}` / `many-to-1` edge folding.
- [Official Spanner Graph Schema Design Best Practices](https://docs.cloud.google.com/spanner/docs/graph/best-practices-designing-schema.md.txt):
  Google Cloud documentation for Spanner Graph physical schema design.

If you need product information that's not found in these references, use the
`search_documents` tool of the Developer Knowledge MCP server.
