# Edge Traversal, Indexing, and Lifecycle Best Practices

## Table of Contents

- [1. Optimizing Forward Edge Traversal](#1-optimizing-forward-edge-traversal): Lines 12-77
- [2. Optimizing Reverse and Any-Direction Edge Traversal](#2-optimizing-reverse-and-any-direction-edge-traversal): Lines 81-149
- [3. Secondary Indexes for Node and Edge Property Filtering](#3-secondary-indexes-for-node-and-edge-property-filtering): Lines 153-205
- [4. Preventing Dangling Edges and Configuring TTL](#4-preventing-dangling-edges-and-configuring-ttl): Lines 209-280

---

## 1. Optimizing Forward Edge Traversal

Forward edge traversal follows outgoing edges from a source node to a
destination node:

```sql
GRAPH FinGraph
MATCH (p:Person {id: @person_id})-[o:Owns]->(a:Account)
RETURN a.id AS account_id;
```

Optimize both hops of forward traversal (source-to-edge and
edge-to-destination):

### 1.1 Source-to-Edge: Composite Primary Key & `INTERLEAVE IN PARENT`

Prefix the edge table's primary key with the source node's primary key and
interleave the edge table into the source node table. This physically co-locates
outgoing edge rows on the same storage split as their parent source node,
converting source-to-edge lookup into a local primary-key prefix seek.

### 1.2 Edge-to-Destination: Foreign Keys & Hub-Node Protection

Add a foreign key constraint from the edge's destination key column(s) to the
destination node table's primary key. When a query only references the
destination node's key (e.g., `RETURN a.id`), Spanner's query optimizer uses the
foreign key guarantee to eliminate the destination node table join entirely.

- **Standard Nodes (Enforced Foreign Key, the Default)**: Prevents dangling
  edges at write time and enables destination join elimination.
- **Target Node Tables in Datasets with High-Degree Hub / Super Nodes (`NOT
  ENFORCED` Informational Foreign Key)**:
  When a target node table contains hub nodes that receive high-concurrency edge
  writes (e.g., a popular account, router, or tag with millions of incoming
  edges), enforced foreign keys can cause read-write lock contention on those
  destination rows. Adding `NOT ENFORCED` on the table's `FOREIGN KEY`
  constraint (note: `NOT ENFORCED` is configured at the table level, not per
  individual node row) avoids write-path lock contention while still enabling
  optimizer join elimination, but it doesn't prevent dangling edges. Because
  the optimizer uses informational foreign keys by default, queries can return
  results that don't match the data if an edge points to a missing node.
  Confirm with the user that the application can tolerate this before choosing
  `NOT ENFORCED`; some customers require enforced foreign keys.

```sql
CREATE TABLE Person (
  id   INT64 NOT NULL,
  name STRING(MAX),
) PRIMARY KEY (id);

CREATE TABLE Account (
  id          INT64 NOT NULL,
  create_time TIMESTAMP,
  close_time  TIMESTAMP,
) PRIMARY KEY (id);

-- NOT ENFORCED is shown for an Account table with high-degree hub nodes, after
-- the user accepted the dangling-edge risk; omit it (the default) when strict
-- write-time referential integrity is required.
CREATE TABLE PersonOwnAccount (
  id          INT64 NOT NULL,
  account_id  INT64 NOT NULL,
  create_time TIMESTAMP,
  CONSTRAINT FK_Account FOREIGN KEY (account_id)
    REFERENCES Account (id) NOT ENFORCED,
) PRIMARY KEY (id, account_id),
  INTERLEAVE IN PARENT Person ON DELETE CASCADE;
```

---

## 2. Optimizing Reverse and Any-Direction Edge Traversal

Reverse edge traversal (`(dst)<-[e]-(src)`) and undirected/any-direction
traversal (`(a)-[e]-(b)`) cannot use an edge table's `(src_id, dst_id)` primary
key prefix directly:

```sql
GRAPH FinGraph
MATCH (a:Account {id: @account_id})<-[o:Owns]-(p:Person)
RETURN p.id AS person_id, o.create_time AS owned_since;
```

Without a reverse index, Spanner must perform a full table scan of the edge
table.

### 2.1 Covering Reverse Index with `STORING` and `INTERLEAVE IN`

Create a secondary index on the edge table keyed by the destination node key
(followed by the source node key), store all non-key edge columns in
`STORING (...)` by default (matching the Spanner Graph UI modeler behavior, or
discuss with the user which subset of frequently accessed edge columns to store
if the table has many wide columns), and interleave the index into the
destination node table when the destination key matches the destination node's
primary key:

```sql
CREATE INDEX AccountOwnedByPerson
ON PersonOwnAccount (account_id, id)
STORING (create_time),
INTERLEAVE IN Account;
```

Why each clause matters:

- **Key `(account_id, id)`**: Allows Spanner to seek directly on `account_id`
  and obtain the source key `id` directly from the index key.
- **`STORING (create_time)`**: Makes the index covering for queries that project
  or filter on `o.create_time`, avoiding a back-join (`ApplyJoin`) to the base
  `PersonOwnAccount` table.
- **`INTERLEAVE IN Account` (Remote Interleaved Index)**: Physically co-locates
  the reverse index entries in the same storage split as the destination
  `Account` row. Unlike `INTERLEAVE IN PARENT` on base tables (which requires
  exact column *name*, type, and order matching and enforces referential
  integrity), `INTERLEAVE IN {dest_node_table}` on a secondary index uses
  **positional type matching** (`account_id` matches `Account(id)` by data type
  and key position without requiring identical column names). If the destination
  node table is itself interleaved under a different parent whose key is not
  present in the edge table, omit `INTERLEAVE IN` on the index and create a
  global covering index `ON EdgeTable (dst_id, src_id) STORING (...)`.

### 2.2 Bidirectional Quantified Paths & `NOT NULL` Key Hygiene

1. **Declare All Primary Key and Endpoint Foreign Key Columns `NOT NULL`**:
   - Always mark `id`, `src_id`, and `dst_id` columns as `NOT NULL`. This allows
     the Spanner optimizer to eliminate null-handling branches across multi-hop
     joins.
2. **Undirected Quantified Paths and Symmetric Relationships**:
   - For deep undirected traversals (`-[e:Transfers]-{1,4}`), use plain
     any-direction matching backed by the reverse index from Section 2.1. Don't
     add a swapped-key reverse edge type for performance: querying it as a
     label union (`-[:Transfers|ReverseTransfer]->{1,3}`) evaluates a union of
     two edge types at every hop, which is slower than
     `-[:Transfers]-{1,3}` for identical results.
   - For inherently symmetric relationships (friend, peer, connected-to), store
     both directions (insert X->Y and Y->X in the same transaction) and query
     with directed `->` so outgoing traversals seek a single primary-key prefix.
     This is faster than single storage plus a reverse index and `-[]-` on
     high-degree start nodes, and about the same on low-degree nodes. Never
     query doubled edges with `-[]-`: every neighbor is returned twice, and
     without a reverse index on the doubled table the traversal full-scans it.

---

## 3. Secondary Indexes for Node and Edge Property Filtering

### 3.1 Filtering Nodes by Non-Key Properties

When queries filter nodes by non-key properties (such as `nick_name`, `status`,
or `site_name`), create a secondary index on the filtered column(s) and include
frequently projected properties in `STORING`:

```sql
CREATE TABLE Account (
  id          INT64 NOT NULL,
  create_time TIMESTAMP,
  close_time  TIMESTAMP,
  is_blocked  BOOL,
  nick_name   STRING(MAX),
) PRIMARY KEY (id);

-- Standard property filter index
CREATE INDEX AccountByNickName
ON Account (nick_name)
STORING (is_blocked);

-- NULL-filtered index for sparse properties (saves storage and write I/O)
CREATE INDEX AccountByCloseTime
ON Account (close_time)
WHERE close_time IS NOT NULL;
```

### 3.2 Filtering and Ordering Edges by Properties During Traversal

When queries filter edges by a property (such as `create_time >= @min_time` or
`status = 'ACTIVE'`) or fetch the Top-K edges per node (`ORDER BY e.create_time
DESC LIMIT k`) while traversing from an anchored node, create a composite index
starting with the traversal endpoint key followed by the filtered or ordered
edge property:

Direction / Pattern | Query Pattern | Recommended Index DDL
--- | --- | ---
**Forward Filter** | `(p:Person {id: @id})-[o:Owns WHERE o.create_time >= @t]->(a:Account)` | `CREATE INDEX PersonOwnAccountByTime ON PersonOwnAccount (id, create_time), INTERLEAVE IN Person;`
**Reverse Filter** | `(a:Account {id: @id})<-[o:Owns WHERE o.create_time >= @t]-(p:Person)` | `CREATE INDEX AccountOwnedByPersonByTime ON PersonOwnAccount (account_id, create_time), INTERLEAVE IN Account;`
**Forward Top-K (`ORDER BY ... DESC LIMIT k`)** | `(a:Account {id: @id})-[t:Transfers]->(b:Account) RETURN b.id, t.amount ORDER BY t.create_time DESC LIMIT 10` | `CREATE INDEX AccountTransferByTimeDesc ON AccountTransferAccount (id, create_time DESC) STORING (amount), INTERLEAVE IN Account;`

For high-degree hub nodes, the **Forward Top-K** index changes the execution
plan from a `Sort Limit` over the full adjacency list to a `Limit` directly over
`IndexScan`, so the query reads only `k` index rows instead of every edge of
the hub.

> [!IMPORTANT]
> Never list primary key columns of the indexed table in `STORING`. Every index
> already carries the table's primary key columns (`id` and `account_id` here),
> and Spanner rejects the DDL: `Index AccountOwnedByPersonByTime specifies
> stored column id which is a key of table PersonOwnAccount`. Only `STORING`
> non-key columns.

---

## 4. Preventing Dangling Edges and Configuring TTL

A *dangling edge* (an edge whose source or destination node no longer exists)
degrades query performance and violates graph integrity.

### 4.1 Edges Connecting Different Node Types (`Person -> Account`)

Combine `INTERLEAVE IN PARENT ... ON DELETE CASCADE` (for the source node) with
an enforced `FOREIGN KEY ... ON DELETE CASCADE` (for the destination node):

```sql
CREATE TABLE PersonOwnAccount (
  id          INT64 NOT NULL,
  account_id  INT64 NOT NULL,
  create_time TIMESTAMP,
  CONSTRAINT FK_Account FOREIGN KEY (account_id)
    REFERENCES Account (id) ON DELETE CASCADE,
) PRIMARY KEY (id, account_id),
  INTERLEAVE IN PARENT Person ON DELETE CASCADE;
```

### 4.2 Edges Connecting the Same Node Type (`Account -> Account`)

When an edge connects two nodes of the **same** table (such as transfers
between two `Account` rows), Spanner does not permit combining `INTERLEAVE IN
PARENT Account ON DELETE CASCADE` with a second `FOREIGN KEY ... REFERENCES
Account ON DELETE CASCADE` on the same table. Choose based on your deletion
requirements:

- **Option A — Strict Bidirectional Delete Cascade (No Dangling Edges)**: Do
  **not** interleave the edge table into `Account`. Instead, define two enforced
  foreign keys with `ON DELETE CASCADE` on both `id` and `to_id`:
  ```sql
  CREATE TABLE AccountTransferAccount (
    id           INT64 NOT NULL,
    to_id        INT64 NOT NULL,
    amount       FLOAT64,
    create_time  TIMESTAMP NOT NULL,
    CONSTRAINT FK_FromAccount FOREIGN KEY (id)
      REFERENCES Account (id) ON DELETE CASCADE,
    CONSTRAINT FK_ToAccount FOREIGN KEY (to_id)
      REFERENCES Account (id) ON DELETE CASCADE,
  ) PRIMARY KEY (id, to_id, create_time);
  ```
- **Option B — Maximum Forward Traversal Locality (Application-Managed Target
  Cleanup)**: Interleave `AccountTransferAccount` into `Account` (`INTERLEAVE IN
  PARENT Account ON DELETE CASCADE`) and use an informational foreign key (`NOT
  ENFORCED`) on `to_id`, cleaning up incoming edges in application logic or via
  TTL before deleting target accounts.

### 4.3 Time-to-Live (`ROW DELETION POLICY`) on Nodes and Edges

When configuring `ROW DELETION POLICY` on a node table, configure attached edge
tables so expired nodes can be garbage-collected without foreign-key violations:

```sql
CREATE TABLE Account (
  id          INT64 NOT NULL,
  create_time TIMESTAMP,
  close_time  TIMESTAMP,
) PRIMARY KEY (id),
  ROW DELETION POLICY (OLDER_THAN(close_time, INTERVAL 90 DAY));

CREATE TABLE AccountTransferAccount (
  id          INT64 NOT NULL,
  to_id       INT64 NOT NULL,
  amount      FLOAT64,
  create_time TIMESTAMP NOT NULL,
) PRIMARY KEY (id, to_id, create_time),
  INTERLEAVE IN PARENT Account ON DELETE CASCADE,
  ROW DELETION POLICY (OLDER_THAN(create_time, INTERVAL 3650 DAY));
```
