# Relational-to-Property-Graph Mapping Patterns

## Table of Contents

- [1. Entity vs. Junction Table Classification](#1-entity-vs-junction-table-classification):
  Lines 18-63
- [2. Interleaved Parent-Child Hierarchies and Foreign Keys](#2-interleaved-parent-child-hierarchies-and-foreign-keys):
  Lines 67-120
- [3. Self-Referential and Recursive Hierarchies](#3-self-referential-and-recursive-hierarchies):
  Lines 124-144
- [4. SQL Bridge Views for Implicit Relationships](#4-sql-bridge-views-for-implicit-relationships):
  Lines 148-208
- [5. Consolidated Multi-Typed and Polymorphic Entity Tables](#5-consolidated-multi-typed-and-polymorphic-entity-tables):
  Lines 212-232
- [6. Indexing and High-Degree Hub Node Recommendations](#6-indexing-and-high-degree-hub-node-recommendations):
  Lines 236-287

## 1. Entity vs. Junction Table Classification

### Pattern 1A: Core Entity Table (`NODE TABLE`)

- **Signals**: Has an independent single-column or composite primary key
  (`customer_id`, `account_id`, `(tenant_id, user_id)`), stores descriptive
  attributes, and is referenced by foreign keys or interleaved child tables.
- **Mapping**: Register in `NODE TABLES` with `KEY ({primary_key_columns})`.

### Pattern 1B: Pure M:N Junction Table (`EDGE TABLE` Only)

- **Signals**: Primary key is composed strictly of two foreign keys
  `(entity_a_id, entity_b_id)` (plus an optional timestamp or sequence number),
  and **no other table** references this table as a parent.
- **Mapping**: Register in `EDGE TABLES` only (`KEY (entity_a_id, entity_b_id)`,
  `SOURCE KEY (entity_a_id) REFERENCES EntityA(entity_a_id)`,
  `DESTINATION KEY (entity_b_id) REFERENCES EntityB(entity_b_id)`).

### Pattern 1C: Attributed Junction / Transaction Table (`EDGE TABLE` or Dual Node + Edge)

- **Signals**: Represents an event, transaction, or relationship with rich
  attributes (`WireTransfers`, `ProductReviews`, `ProjectAssignments`).
- **Mapping Decision**:
  - Map purely as an **`EDGE TABLE`** if no other table has a foreign key or
    interleave pointing to this table (for example, `WireTransfers` between two
    `BankAccounts`).
  - Map as **both a `NODE TABLE` and an `EDGE TABLE`** if downstream tables link
    to it (for example, `Orders` is linked from `Customers` and is the parent of
    `OrderItems`).

### Pattern 1D: Decoupled Edge Identity (`KEY`) vs. Endpoint Keys & Reverse Edge Aliasing

- **Edge Identity vs. Topology**: In Spanner Graph, `KEY (...)` identifies the
  unique edge row in the table (`KEY (transfer_id)` or
  `KEY (src_id, dst_id, transfer_id)`), whereas `SOURCE KEY` and
  `DESTINATION KEY` define the topological endpoints. `KEY` does not need to be
  identical to `(SOURCE KEY, DESTINATION KEY)`.
- **Reverse Edge Aliasing (Naming Only)**: A single physical edge table can be
  mapped twice in `EDGE TABLES` under distinct aliases (swapping `SOURCE KEY`
  and `DESTINATION KEY`, e.g., `AccountTransfers AS Debits` and
  `AccountTransfers AS Credits`) when the domain genuinely needs two directional
  labels. It is not a performance optimization: for undirected traversal use
  `-[e:LABEL]-` backed by a reverse index on `(dst_key, src_key)`; querying a
  swapped-key alias as a label union (`-[:E|E_REV]->{1,3}`) evaluates a union of
  two edge definitions at every hop, which is slower than `-[e:LABEL]-` for
  identical results.

---

## 2. Interleaved Parent-Child Hierarchies and Foreign Keys

### Pattern 2A: Interleaved Child Entity (`INTERLEAVE IN PARENT`)
In Spanner, parent-child ownership is frequently modeled via table interleaving
rather than an explicit `FOREIGN KEY` constraint:
```sql
CREATE TABLE Customers (
  customer_id INT64 NOT NULL,
  name STRING(100)
) PRIMARY KEY (customer_id);

CREATE TABLE Orders (
  customer_id INT64 NOT NULL,
  order_id INT64 NOT NULL,
  order_date DATE
) PRIMARY KEY (customer_id, order_id),
  INTERLEAVE IN PARENT Customers ON DELETE CASCADE;
```

- **Mapping**:
  - `Customers` -> `NODE TABLE` with `KEY (customer_id)`
  - `Orders` -> `NODE TABLE` (`Orders AS OrderNode`) with full composite
    `KEY (customer_id, order_id)`
  - `Orders` -> `EDGE TABLE` (`Orders AS PlacedOrder`) with:
    ```sql
    Orders AS PlacedOrder
      KEY (customer_id, order_id)
      SOURCE KEY (customer_id) REFERENCES Customer(customer_id)
      DESTINATION KEY (customer_id, order_id) REFERENCES OrderNode(customer_id, order_id)
      LABEL PLACED PROPERTIES (order_date)
    ```

- **Why**: Interleaving physically colocates `PlacedOrder` and `OrderNode` rows
  with their parent `Customer` split, making forward traversal
  `(c:Customer)-[:PLACED]->(o:Order)` a local split read. If queries or other
  edge tables look up `Orders` by `order_id` alone without `customer_id`,
  recommend `CREATE UNIQUE INDEX OrdersByOrderId ON Orders (order_id)` so those
  lookups do not full-scan `Orders` (and if downstream tables only carry
  `order_id`, either declare `KEY (order_id)` on `OrderNode` backed by that
  `UNIQUE` index or reference the full `(customer_id, order_id)` key).

### Pattern 2B: Standard 1:N Foreign Key (`Table AS Edge`)
When table `Accounts(account_id, owner_entity_id)` has a foreign key
`owner_entity_id REFERENCES Entities(entity_id)`:

- Register `Accounts AS Account` in `NODE TABLES` (`KEY (account_id)`).
- Register `Accounts AS OwnsAccountEdge` in `EDGE TABLES`:
  ```sql
  Accounts AS OwnsAccountEdge
    KEY (account_id)
    SOURCE KEY (owner_entity_id) REFERENCES Entity(entity_id)
    DESTINATION KEY (account_id) REFERENCES Account(account_id)
    LABEL OWNS NO PROPERTIES
  ```

---

## 3. Self-Referential and Recursive Hierarchies

When a table references its own primary key (for example,
`Employees(emp_id, manager_id)` or
`Categories(category_id, parent_category_id)`):

- Map the table once in `NODE TABLES` (`Employees AS Employee KEY (emp_id)`).
- Map the table again in `EDGE TABLES` with a distinct alias
  (`Employees AS ReportsToEdge`):
  ```sql
  Employees AS ReportsToEdge
    KEY (emp_id)
    SOURCE KEY (emp_id) REFERENCES Employee(emp_id)
    DESTINATION KEY (manager_id) REFERENCES Employee(emp_id)
    LABEL REPORTS_TO NO PROPERTIES
  ```

- Note: Rows where `manager_id IS NULL` (such as root/CEO nodes) remain valid
  nodes in `Employee`; Spanner Graph simply omits null-destination edges during
  edge traversal. By contrast, if a node or edge's own `KEY (...)` column is
  `NULL`, `MATCH` silently hides that element row altogether.

---

## 4. SQL Bridge Views for Implicit Relationships

Because existing relational tables should not be destructively altered, use SQL
bridge views whenever relationships are stored implicitly. Every Spanner view
requires a `SQL SECURITY` clause:

- **`SQL SECURITY INVOKER` (common default)**: Graph queries run with the
  invoking caller's permissions on the underlying relational tables.
- **`SQL SECURITY DEFINER`**: Use when enforcing row-level / fine-grained access
  control so callers can query the graph view without direct privileges on the
  base tables.

### Case 4A: Array of Foreign Keys (`ARRAY<INT64>` / `ARRAY<STRING>`)

If `Articles(article_id INT64, tag_ids ARRAY<INT64>)` stores foreign keys in an
array column, `ARRAY` columns cannot be used directly in `SOURCE KEY` or
`DESTINATION KEY`. Create an unnesting bridge view:

```sql
CREATE OR REPLACE VIEW ArticleTagEdgeView
SQL SECURITY INVOKER AS
SELECT DISTINCT
  a.article_id,
  tag_id
FROM Articles AS a,
UNNEST(a.tag_ids) AS tag_id
WHERE tag_id IS NOT NULL;
```

Then register `ArticleTagEdgeView` in `EDGE TABLES` with an explicit composite
`KEY (article_id, tag_id)`:

- **Strict key validation (default)**: Spanner verifies view element keys
  syntactically (either a single table's primary key or `SELECT DISTINCT` /
  `GROUP BY` over the key columns), failing otherwise with
  `cannot verify the specified element key (article_id, tag_id) is unique`. Keep
  `SELECT DISTINCT` (or `GROUP BY`) whenever raw array values can repeat.
- **Skipping syntactic validation
  (`OPTIONS (validate_element_key_uniqueness = false)`)**: When you know a
  view's `KEY` is **already semantically unique**—such as
  `UNNEST(a.tag_ids) AS tag_id WITH OFFSET AS pos` keyed on `(article_id, pos)`,
  or a `JOIN` that preserves primary-key uniqueness without `GROUP BY`—you can
  append `OPTIONS (validate_element_key_uniqueness = false)` to
  `CREATE PROPERTY GRAPH` instead of adding `DISTINCT` / `GROUP BY`. Ensure the
  key columns contain no duplicate rows in data, or `MATCH` can return duplicate
  graph elements.

### Case 4B: JSON Relationship Payloads

If foreign keys are nested inside a `JSON` column (`metadata.parent_device_id`),
project the scalar key in a bridge view (`SQL SECURITY INVOKER` or `DEFINER`)
using `INT64(JSON_QUERY(metadata, '$.parent_device_id'))` or
`JSON_VALUE(metadata, '$.parent_device_id')`.

### Case 4C: Mismatched Key Data Types (`INT64` vs. `STRING`)

If a legacy table stores `target_account_id` as `STRING(64)` while
`Accounts(account_id)` is `INT64`, create a bridge view (`SQL SECURITY INVOKER`
or `DEFINER`) using
`SAFE_CAST(target_account_id AS INT64) AS target_account_id_int64` and filter
`WHERE SAFE_CAST(target_account_id AS INT64) IS NOT NULL`.

---

## 5. Consolidated Multi-Typed and Polymorphic Entity Tables

Some schemas consolidate multiple domain types into a single table with a
composite primary key `(entity_type, entity_id)`:
```sql
CREATE TABLE Entities (
  entity_type STRING(50) NOT NULL,
  entity_id STRING(100) NOT NULL,
  display_name STRING(200)
) PRIMARY KEY (entity_type, entity_id);
```

- **Recommended Default Mapping**: Map `Entities` to a single unified node table
  (`Entities AS Entity` with `KEY (entity_type, entity_id)` and
  `LABEL Entity PROPERTIES (entity_type, entity_id, display_name)`) and match
  edges on the full 2-column key
  `(source_type, source_id) -> (target_type, target_id)`.
- **Optional Typed Subgraph Views**: If users require distinct node labels per
  type (`:Malware`, `:ThreatActor`), create `SQL SECURITY INVOKER` views
  filtered by `WHERE entity_type = '...'` and register each view as a separate
  node table.

---

## 6. Indexing and High-Degree Hub Node Recommendations

Always include physical performance recommendations alongside the derived
`CREATE PROPERTY GRAPH` DDL:

1. **Reverse Traversal Secondary Indexes (Remote Interleaved or Covering)**:
   - Every edge table whose primary key begins with `src_id` is fast for forward
     traversal (`(src)-[:EDGE]->(dst)`) but requires a full table scan for
     reverse traversal (`(dst)<-[:EDGE]-(src)`) unless indexed on `dst_id`.
   - Recommend either a **Remote Interleaved Index** co-located in the
     destination node table (`INTERLEAVE IN DestNodeTable`, which matches
     `dst_id` to `DestNodeTable`'s primary key positionally by type) or a
     covering index with `STORING`:
     ```sql
     -- Option A: Remote index physically co-located with the destination node table
     -- (if dst_id is nullable, use CREATE NULL_FILTERED INDEX because Spanner
     -- rejects non-NULL_FILTERED interleaved indexes on nullable columns)
     CREATE INDEX EdgeTableByDstSrc
     ON EdgeTable (dst_id, src_id),
     INTERLEAVE IN DestNodeTable;

     -- Option B: Global covering index storing frequently filtered edge properties
     CREATE INDEX EdgeTableByDstSrcCovering
     ON EdgeTable (dst_id, src_id)
     STORING (prop1, prop2);
     ```

2. **Simplify Over-Wide Composite Primary Keys on Junction Tables**:
   - Legacy relational junction tables sometimes include 4–6 status,
     source-system, or audit columns in the table `PRIMARY KEY`. Advise users
     that overly wide primary keys bloat secondary indexes and slow down edge
     joins; recommend keeping `PRIMARY KEY` to `(src_id, dst_id [, edge_id])`
     when evolving the physical schema.
3. **Interleaving vs. Bidirectional Cascading Deletes on Same-Node-Type Edges**:
   - When an edge connects two nodes of the same table (`Account -> Account`),
     explain the trade-off:
     - **Interleaving** (`INTERLEAVE IN PARENT Accounts`) maximizes forward
       traversal locality, OR
     - **Standalone table with two `FOREIGN KEY ... ON DELETE CASCADE`
       constraints** (one on `src_id`, one on `dst_id`) ensures deleting an
       account automatically deletes both its outgoing and incoming edges.
4. **High-Degree Hub Node Contention (`NOT ENFORCED` Foreign Keys)**:
   - In scale-free graphs where a single popular destination node receives
     thousands of concurrent edge inserts per second, enforced foreign keys can
     cause validation lock contention on the hub node row. Informational foreign
     keys (`FOREIGN KEY (...) REFERENCES ... NOT ENFORCED`) avoid that
     contention and still allow optimizer join elimination, but they don't
     prevent dangling edges, and because the optimizer uses them by default,
     queries can return results that don't match the data if an edge points to a
     missing node. Keep foreign keys enforced by default; recommend
     `NOT ENFORCED` only when write throughput on hub nodes is critical and the
     user confirms that the application can tolerate dangling edges.
