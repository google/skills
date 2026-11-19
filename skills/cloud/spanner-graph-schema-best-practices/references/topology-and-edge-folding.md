# Advanced Graph Topology & Edge Folding Best Practices

## Table of Contents

- [1. Schematized vs. Schemaless (`DYNAMIC LABEL`) Decision Matrix](#1-schematized-vs-schemaless-dynamic-label-decision-matrix):
  Lines 18-121
- [2. Multi-Table Label Sharing & Property Alignment](#2-multi-table-label-sharing-property-alignment):
  Lines 125-158
- [3. Co-Locating 1:N Node Hierarchies (`INTERLEAVE IN PARENT`)](#3-co-locating-1n-node-hierarchies-interleave-in-parent):
  Lines 162-270
- [4. Folding `many-to-{0,1}` and `many-to-1` Edges into Node Tables](#4-folding-many-to-01-and-many-to-1-edges-into-node-tables):
  Lines 274-379
- [5. Consolidating 1:1 Subtype Nodes & Folding 1:1 Intermediate Hops](#5-consolidating-11-subtype-nodes-folding-11-intermediate-hops):
  Lines 383-487

---

## 1. Schematized vs. Schemaless (`DYNAMIC LABEL`) Decision Matrix

Spanner Graph supports both strongly-typed schematized definitions and flexible
schemaless definitions (`DYNAMIC LABEL` and `DYNAMIC PROPERTIES`).

### When to Choose Schemaless Over Schematized

While both models perform similarly on single-type traversals, **schemaless
designs can be faster when queries use quantified path patterns (`{m, n}`) that
span multiple node or edge types**, because all node types share one table and
all edge types share another:

```sql
-- Traverses multiple edge labels (Transfer|Withdraw) and untyped intermediate
-- nodes across 1 to 3 hops:
GRAPH FinGraph
MATCH p = (:Account {id: 1})-[:Transfer|Withdraw]->{1, 3}(:Account)
RETURN TO_JSON(p) AS path_json;
```

- **Why Schemaless Helps on Multi-Type Quantified Paths**: In a schematized
  design with separate tables per node/edge type, a quantified path spanning
  multiple types must union and join across every candidate node and edge table
  at each hop. A single-table schemaless design stores all nodes in one `Nodes`
  table and all edges in one `Edges` table using `DYNAMIC LABEL`, so each hop
  scans and joins a single node/edge table pair instead of many tables. The
  same applies to polymorphic edges, where one edge label connects several
  different node types:

```sql
CREATE TABLE GraphNodes (
  id         INT64 NOT NULL,
  label      STRING(MAX) NOT NULL,
  first_seen TIMESTAMP,
  properties JSON,
  -- Dynamic label values must be stored in lowercase (see the note below).
  CONSTRAINT GraphNodesLabelLowercase CHECK (label = LOWER(label)),
) PRIMARY KEY (id);

CREATE TABLE GraphEdges (
  id         INT64 NOT NULL,
  to_id      INT64 NOT NULL,
  edge_id    INT64 NOT NULL,
  label      STRING(MAX) NOT NULL,
  created_at TIMESTAMP,
  properties JSON,
  CONSTRAINT GraphEdgesLabelLowercase CHECK (label = LOWER(label)),
) PRIMARY KEY (id, to_id, edge_id),
  INTERLEAVE IN PARENT GraphNodes ON DELETE CASCADE;

-- Hybrid properties design: expose the columns that this workload frequently
-- filters or indexes on (here, first_seen and created_at) as typed static
-- properties through an explicit PROPERTIES list, and store evolving
-- attributes in the JSON column. Choose these columns per workload.
CREATE OR REPLACE PROPERTY GRAPH FlexibleGraph
  NODE TABLES (
    GraphNodes
      KEY (id)
      PROPERTIES (id, label, first_seen)
      DYNAMIC LABEL (label)
      DYNAMIC PROPERTIES (properties)
  )
  EDGE TABLES (
    GraphEdges
      KEY (id, to_id, edge_id)
      SOURCE KEY (id) REFERENCES GraphNodes (id)
      DESTINATION KEY (to_id) REFERENCES GraphNodes (id)
      PROPERTIES (id, to_id, edge_id, label, created_at)
      DYNAMIC LABEL (label)
      DYNAMIC PROPERTIES (properties)
  );
```

`PROPERTIES ALL COLUMNS EXCEPT (properties)` is an equivalent shorthand (used in
the Spanner documentation) that exposes every column except the `JSON` column.
Either form keeps the `JSON` column from being exposed twice, as a static
property and as dynamic properties.

- **Store dynamic label values in lowercase**: A row whose `label` column holds
  an uppercase or mixed-case value (`'Account'`) silently gets no dynamic
  label: `MATCH (n:Account)` skips it, and `LABELS(n)` returns only the table's
  default label. Labels in queries are case-insensitive (`:Account` matches a
  stored `'account'`). The `CHECK (label = LOWER(label))` constraints above
  reject bad writes; normalize existing data with `LOWER(label)` before adding
  them.

- **Confirm the Workload Before Choosing**: If the user hasn't already described
  their schema and queries, ask these questions before recommending a design:
  1. **How many node and edge types do you need to maintain?** With a large
     number of types (for example, more than 50 node types and 150 edge types),
     mapping each type to its own table becomes a maintenance burden; a
     schemaless design stores all node types in one table and all edge types in
     another.
  2. **Do existing queries traverse multiple labels?** For example,
     `-[:Transfer|Withdraw]->{1, 3}`, or label conjunctions and disjunctions in
     traversals. If such queries expand a large number of intermediate paths
     (for example, more than 10,000) and are latency-sensitive, consider a
     schemaless design.

- **When to Keep Schematized (Default)**: If quantified paths only traverse a
  single node type and a single edge type (e.g.,
  `(:Person)-[:Owns]->(:Account)-[:Transfer]->{1, 3}(:Account)`), or if your
  workload relies on native non-JSON column types and secondary indexes on
  typed columns, use a **schematized** design.

---

## 2. Multi-Table Label Sharing & Property Alignment

When multiple physical tables share a common graph `LABEL` (for example,
`EquipmentPort` and `OpticalPort` both exposing `LABEL Port`), Spanner Graph
enforces strict signature uniformity across all tables declaring that label:

1. **Identical Property Set**: Every table declaring the shared label must
   expose the exact same property names under that label.
2. **Identical Data Types (Including Graph-Wide Property Type Rule)**: Every
   property with the same exposed name across the **entire property graph**—even
   on unrelated labels or between node and edge tables—must have the exact same
   SQL data type (`The property declaration of 'id' has type conflicts...`). If
   underlying physical columns have different data types (e.g., `INT64` in one
   table and `STRING(64)` in another), alias the column names or use scalar
   SQL expressions such as `CAST` inside `PROPERTIES (...)` so the exposed
   graph property type matches across all tables:

```sql
CREATE OR REPLACE PROPERTY GRAPH NetworkGraph
  NODE TABLES (
    EquipmentPort
      KEY (equip_id, port_id)
      LABEL Port PROPERTIES (
        CAST(port_id AS STRING) AS port_identifier,
        bandwidth_gbps
      ),
    OpticalPort
      KEY (optical_node_id, port_code)
      LABEL Port PROPERTIES (
        port_code AS port_identifier,
        CAST(wavelength_gbps AS INT64) AS bandwidth_gbps
      )
  );
```

---

## 3. Co-Locating 1:N Node Hierarchies (`INTERLEAVE IN PARENT`)

> [!IMPORTANT]
> **Advanced technique: strict `1:N` containment only.** Interleave a node table
> under another node table only when each child node is owned by exactly one
> parent node and cannot exist without it (for example, each `IpCard` is
> physically installed in exactly one `IpNode`). If the relationship is
> many-to-many (`M:N`)—for example, an `IpCard` or `Vrf` that can be associated
> with multiple `IpNode`s—or the child is an independent entity that outlives
> its parent, **do not** make it an interleaved child: keep both node tables
> standalone and model the relationship as a dedicated edge table interleaved in
> the source node table. Confirm the cardinality with the user before applying
> this layout.

When a graph contains a strict `1:N` parent-child containment hierarchy between
two node types (for example, each `IpCard` belongs to one `IpNode`), model the
hierarchy using Spanner's physical table interleaving AND dual node/edge
projection. In this example, ports stay in their own table and reference their
card through a folded `many-to-1` foreign key (see
[Section 4](#4-folding-many-to-01-and-many-to-1-edges-into-node-tables)):

```sql
CREATE TABLE IpNode (
  ip_id     STRING(64) NOT NULL,
  site_name STRING(128),
) PRIMARY KEY (ip_id);

CREATE TABLE IpCard (
  ip_id     STRING(64) NOT NULL,
  card_id   STRING(64) NOT NULL,
  card_type STRING(64),
) PRIMARY KEY (ip_id, card_id),
  INTERLEAVE IN PARENT IpNode ON DELETE CASCADE;

-- Assumes port_id is globally unique. If port IDs are only unique within a
-- card (for example, eth0 on every card), the primary key must also include
-- the card's key: (ip_id, card_id, port_id).
CREATE TABLE IpPort (
  port_id     STRING(64) NOT NULL,
  ip_id       STRING(64) NOT NULL,
  card_id     STRING(64) NOT NULL,
  port_status STRING(32),
  CONSTRAINT FK_IpPort_IpCard FOREIGN KEY (ip_id, card_id)
    REFERENCES IpCard (ip_id, card_id),
) PRIMARY KEY (port_id);
```

Declare `IpCard` as both a **Node Table** and an **Edge Table** (the
parent-to-child edge), and declare `IpPort` the same way (the folded
card-to-port edge):

```sql
CREATE OR REPLACE PROPERTY GRAPH NetworkGraph
  NODE TABLES (
    IpNode KEY (ip_id),
    IpCard KEY (ip_id, card_id),
    IpPort KEY (port_id)
  )
  EDGE TABLES (
    IpCard AS HasCard
      KEY (ip_id, card_id)
      SOURCE KEY (ip_id) REFERENCES IpNode (ip_id)
      DESTINATION KEY (ip_id, card_id) REFERENCES IpCard (ip_id, card_id)
      LABEL hasCard,
    IpPort AS HasPort
      KEY (port_id)
      SOURCE KEY (ip_id, card_id) REFERENCES IpCard (ip_id, card_id)
      DESTINATION KEY (port_id) REFERENCES IpPort (port_id)
      LABEL hasPort
  );
```

- No separate `HasCard` or `HasPort` junction tables are needed.
- Traversing `(n:IpNode)-[:hasCard]->(c:IpCard)` reads contiguous rows in the
  same storage split, because each node's cards are stored next to it.
- **Reference the Full Composite Key**: Interleaving changes `IpCard`'s primary
  key to `(ip_id, card_id)`. Always query and reference an interleaved child
  node by its full composite `KEY (ip_id, card_id)` in `NODE TABLES`, `SOURCE
  KEY`, and `DESTINATION KEY`; referencing only a partial key against a
  multi-column node `KEY` is accepted by Spanner and silently duplicates edge
  matches.

### 3.1 Advanced: Interleaving a Third Level (Use with Caution)

You can also interleave `IpPort` under `IpCard` so that a node, its cards, and
its ports are stored together:

```sql
CREATE TABLE IpPort (
  ip_id       STRING(64) NOT NULL,
  card_id     STRING(64) NOT NULL,
  port_id     STRING(64) NOT NULL,
  port_status STRING(32),
) PRIMARY KEY (ip_id, card_id, port_id),
  INTERLEAVE IN PARENT IpCard ON DELETE CASCADE;
```

This speeds up traversals across the whole node-card-port hierarchy, but each
port is now identified by a key that combines three tables,
`(ip_id, card_id, port_id)`:

- Every edge that starts or ends at a port (for example, port-to-port links)
  must carry all three key columns for that endpoint, which widens edge tables
  and their indexes.
- Moving a port to another card changes its primary key, so the port row and
  every edge that references it must be deleted and re-inserted.

Confirm with the user that they accept these trade-offs before recommending a
third interleave level.

---

## 4. Folding `many-to-{0,1}` and `many-to-1` Edges into Node Tables

Separate physical edge tables are only necessary when an edge has **many-to-many
(`M:N`)** cardinality (or when an edge connects 1:N targets that cannot be
interleaved and carries multiple parallel edges between the same endpoints).

### 4.1 The Edge-Folding Optimization (`Table AS Node` + `Table AS Edge`)

Whenever a directed relationship `(Source)-[:REL]->(Target)` has
**`many-to-{0,1}`** or **`many-to-1`** cardinality (meaning each `Source` node
connects to **at most one** `Target` node for that relationship, or a `1:N`
relationship viewed from the `N` side), fold the edge directly into the
`Source` node table as a foreign-key column:

```sql
CREATE TABLE OpticalNode (
  optical_node_id STRING(64) NOT NULL,
  locality_name   STRING(128),
) PRIMARY KEY (optical_node_id);

-- Each IpNode sits on at most ONE OpticalNode (many-to-{0,1} / many-to-1):
-- fold the target optical_node_id directly into IpNode instead of creating an
-- IpOnOptical edge table. A NULL optical_node_id means the IpNode sits on no
-- OpticalNode (many-to-0); Spanner doesn't check foreign keys on rows whose
-- referencing column is NULL.
CREATE TABLE IpNode (
  ip_id           STRING(64) NOT NULL,
  site_name       STRING(128),
  optical_node_id STRING(64),
  CONSTRAINT FK_IpNode_OpticalNode FOREIGN KEY (optical_node_id)
    REFERENCES OpticalNode (optical_node_id),
) PRIMARY KEY (ip_id);

-- Create a covering index on the foreign key for reverse traversals
-- (OpticalNode)<-[:ipOnOptical]-(IpNode) and non-null forward scans.
-- NULL_FILTERED is required if you co-locate this index via
-- INTERLEAVE IN OpticalNode, because Spanner rejects non-NULL_FILTERED
-- interleaved indexes on nullable columns:
CREATE NULL_FILTERED INDEX IpNodeByOpticalNode
ON IpNode (optical_node_id, ip_id)
STORING (site_name),
INTERLEAVE IN OpticalNode;
```

- **Keep the Folded Foreign Key Enforced (Default)**: An enforced foreign key
  guarantees that every non-`NULL` `optical_node_id` points to an existing
  `OpticalNode`. Deleting an `OpticalNode` fails while any `IpNode` still
  references it; set those `optical_node_id` values to `NULL` (or delete the
  `IpNode` rows) first. Never add `ON DELETE CASCADE` to a folded-edge foreign
  key: it deletes the source `IpNode` rows, not just their edges.
- **Confirm Before Using `NOT ENFORCED`**: An informational foreign key
  (`REFERENCES OpticalNode (optical_node_id) NOT ENFORCED`) avoids write lock
  contention when many concurrent writes reference the same high-degree
  `OpticalNode`, but it doesn't prevent dangling edges. Because the query
  optimizer uses informational foreign keys by default, queries can return
  results that don't match the data if an `optical_node_id` points to a missing
  node. Ask the user whether they accept that risk before choosing
  `NOT ENFORCED`; some customers require enforced foreign keys.

Then project `IpNode` as **both** a node table and an edge table in `CREATE
PROPERTY GRAPH`:

```sql
CREATE OR REPLACE PROPERTY GRAPH NdtGraph
  NODE TABLES (
    OpticalNode
      KEY (optical_node_id)
      LABEL OpticalNode PROPERTIES (optical_node_id, locality_name),
    IpNode
      KEY (ip_id)
      LABEL IpNode PROPERTIES (ip_id, site_name, optical_node_id)
  )
  EDGE TABLES (
    IpNode AS IpOnOpticalEdge
      KEY (ip_id)
      SOURCE KEY (ip_id) REFERENCES IpNode (ip_id)
      DESTINATION KEY (optical_node_id) REFERENCES OpticalNode (optical_node_id)
      LABEL ipOnOptical PROPERTIES (site_name, optical_node_id)
  );
```

**Performance Gain**: In `MATCH (ip:IpNode)-[:ipOnOptical]->(opt:OpticalNode)`,
both `ip` and the `ipOnOptical` edge come from the same `IpNode` row, so Spanner
does not join `IpNode` to a separate `IpOnOptical` edge table. Compared with a
separate edge table interleaved in the source table, the gain is modest and only
appears when the query filters on or returns source-node properties; key-only
traversals perform the same. Folding still removes a table to maintain and
write.

### 4.2 Critical Cardinality Guardrail: NEVER Fold `M:N` Edges into Node Tables

> [!CAUTION]
> **Only fold `many-to-{0,1}` or `many-to-1` edges into a source node table.**
> Never fold a `many-to-many` (`M:N`) edge (or the `1`-to-`many` direction where
> a single source node has multiple target IDs) into a node table.

- **Why**: A relational node table requires one row per unique node entity
  (`PRIMARY KEY (node_id)`). If a node connects to multiple targets (`M:N`) and
  you add `target_id` to the node table's primary key (`PRIMARY KEY (node_id,
  target_id)`), the node row is **duplicated once per edge**.
- **Consequence**: Queries that count or aggregate nodes—such as
  `MATCH (n:Node) RETURN COUNT(n)` or degree aggregations—will return the
  **edge count** instead of the **node count**, producing silently wrong query
  results.
- **Rule**: Keep all `M:N` edges in a dedicated edge table (`PRIMARY KEY
  (src_id, dst_id, ...)`, `INTERLEAVE IN PARENT SourceNode`).

---

## 5. Consolidating 1:1 Subtype Nodes & Folding 1:1 Intermediate Hops

### 5.1 Consolidating Fragmented 1:1 Subtype Node Tables

Avoid splitting a single logical entity into multiple 1:1 subtype tables (for
example, a base `IpRouter` table plus separate `BorderRouter`, `ProviderEdge`,
and `ServiceEdge` tables joined 1:1 on `router_id`). Instead, consolidate them
into a single physical node table (such as `DeviceNode`) with a type
discriminator column (such as `device_role`) that queries filter on
(`MATCH (d:DeviceNode {device_role: 'BorderRouter'})`).

### 5.2 Folding 1:1 Intermediate Pass-Through Hops

In physical network, supply-chain, or financial schemas, relational models
often normalize binary links into intermediate node tables (e.g.,
`RouterA <-[:terminatedBy]- CableNode -[:terminatedBy]-> RouterB`, where each
`CableNode` only connects two endpoints). If queries routinely traverse from
endpoint to endpoint (`RouterA -> RouterB`), representing `CableNode` as an
intermediate node doubles the hop count of every path query (turning a 3-link
traversal into a 6-hop query).

> [!IMPORTANT]
> **Confirm with the user before folding.** Folding removes the intermediate
> node type from the graph schema entirely: `CableNode` attributes become
> properties of the `cableLink` edge, `MATCH (c:CableNode)` no longer works, and
> a cable can no longer be the endpoint of its own edges (for example,
> `(CableNode)-[:hasTicket]->(MaintenanceTicket)`). Only apply this pattern
> when there is no need to model the intermediate node type as a first-class
> node, and ask the user to confirm that before choosing it.

**Before**: each cable is a node, and each router-to-router hop takes two
`terminatedBy` edges:

```sql
CREATE TABLE Router (
  router_id STRING(64) NOT NULL,
  site_name STRING(128),
) PRIMARY KEY (router_id);

CREATE TABLE CableNode (
  cable_id      STRING(64) NOT NULL,
  capacity_gbps INT64,
  status        STRING(32),
) PRIMARY KEY (cable_id);

-- Each cable has exactly two terminations: cable_end 'A' and cable_end 'B'.
CREATE TABLE CableTermination (
  cable_id  STRING(64) NOT NULL,
  cable_end STRING(1) NOT NULL,
  router_id STRING(64) NOT NULL,
  CONSTRAINT FK_CableTermination_Router FOREIGN KEY (router_id)
    REFERENCES Router (router_id),
) PRIMARY KEY (cable_id, cable_end),
  INTERLEAVE IN PARENT CableNode ON DELETE CASCADE;

CREATE OR REPLACE PROPERTY GRAPH CableGraph
  NODE TABLES (Router, CableNode)
  EDGE TABLES (
    CableTermination AS TerminatedBy
      SOURCE KEY (cable_id) REFERENCES CableNode (cable_id)
      DESTINATION KEY (router_id) REFERENCES Router (router_id)
      LABEL terminatedBy
  );

-- One router-to-router hop:
-- MATCH (a:Router)<-[:terminatedBy]-(:CableNode)-[:terminatedBy]->(b:Router)
```

**After**: fold each cable into a single edge that connects its two routers
directly, with the cable's attributes stored as edge properties:

```sql
CREATE TABLE CableLink (
  router_id      STRING(64) NOT NULL,  -- cable end A (source)
  peer_router_id STRING(64) NOT NULL,  -- cable end B (destination)
  cable_id       STRING(64) NOT NULL,
  capacity_gbps  INT64,
  status         STRING(32),
  CONSTRAINT FK_CableLink_PeerRouter FOREIGN KEY (peer_router_id)
    REFERENCES Router (router_id),
) PRIMARY KEY (router_id, peer_router_id, cable_id),
  INTERLEAVE IN PARENT Router ON DELETE CASCADE;

CREATE OR REPLACE PROPERTY GRAPH CableGraph
  NODE TABLES (Router)
  EDGE TABLES (
    CableLink
      SOURCE KEY (router_id) REFERENCES Router (router_id)
      DESTINATION KEY (peer_router_id) REFERENCES Router (router_id)
      LABEL cableLink PROPERTIES (cable_id, capacity_gbps, status)
  );

-- One router-to-router hop:
-- MATCH (a:Router)-[l:cableLink]->(b:Router)
```

- Cables are physically bidirectional, so traverse `CableLink` in either
  direction with `-[:cableLink]-`, backed by a reverse index on
  `(peer_router_id, router_id)` (see
  [Edge Traversal & Indexing](edge-traversal-and-indexing.md)).
- If you need to support both legacy and new label names during migration,
  declare both labels on the same edge table (`LABEL IpLink PROPERTIES
  (cable_id, capacity_gbps) LABEL CableLink PROPERTIES (cable_id,
  capacity_gbps)`). Spanner Graph has no `SYNONYMS` clause; `LABEL IpLink
  SYNONYMS (CableLink)` is a syntax error.
