# Spanner Graph PROFILE Execution Plans and Hints Guide

## Table of Contents

- [1. Running and Reading PROFILE Execution Plans](#1-running-and-reading-profile-execution-plans):
  Lines 14-52
- [2. Diagnosing Join Operators: Apply Join vs. Hash Join](#2-diagnosing-join-operators-apply-join-vs-hash-join):
  Lines 56-87
- [3. Statement-Level, Node-Level, and Edge-Level Hint Syntax](#3-statement-level-node-level-and-edge-level-hint-syntax):
  Lines 91-160
- [4. Quantified Path and Foreign-Key Join Elimination Guardrails](#4-quantified-path-and-foreign-key-join-elimination-guardrails):
  Lines 164-199

## 1. Running and Reading PROFILE Execution Plans

To inspect the physical execution plan and runtime statistics of a Spanner Graph
GQL query, run:

```bash
gcloud spanner databases execute-sql {database_id} \
  --instance={instance_id} \
  --query-mode=PROFILE \
  --sql="GRAPH FinGraph MATCH (p:Person {id: 1})-[o:Owns]->(a:Account) RETURN a.id"
```

If a query is too slow to complete, replace `--query-mode=PROFILE` with
`--query-mode=PLAN` to inspect the estimated execution plan immediately without
executing the query.

### Key Plan Metrics to Inspect

1. **`SeekableKeySize: [N]` on `TableScan` / `IndexScan` (`Storage Read`)**:
   - Indicates how many prefix columns of the primary key or secondary index are
     bound as direct B-tree range seeks.
   - **`SeekableKeySize: [0]`** means Spanner is performing a **full scan** of
     the table or index and evaluating predicates afterward as a
     `Residual Condition`.
   - **`SeekableKeySize: [1]` (or `[2]`, `[3]`)** means Spanner seeks directly
     to the matching key prefix.
2. **`Residual Condition`**:
   - Filter expressions evaluated *after* rows are read from storage.
   - If a high-selectivity filter appears as a `Residual Condition` on a scan
     with `SeekableKeySize: [0]`, either the query is missing a secondary index
     on that property, the filter is on a non-leading key column, or the column
     is wrapped in a non-sargable expression.
3. **`Rows Returned` vs. `Rows Scanned` across Join Boundaries**:
   - Compare the row counts entering and leaving each `Cross Apply` or
     `Hash Join`.
   - If an intermediate join expands 500 anchor rows into 2,000,000 rows before
     a later `FilterScan` or `HashAggregate` collapses them back to 500 rows,
     reorder the `MATCH` pattern or split it with `NEXT` and early `GROUP BY`
     (see [gql-rewrite-patterns.md](gql-rewrite-patterns.md)).

---

## 2. Diagnosing Join Operators: Apply Join vs. Hash Join

Spanner Graph primarily executes pattern traversals using two physical join
families:

### `Local Distributed Cross Apply` / `Distributed Cross Apply` (`apply_join`)

- **How it works**: For each row produced by the left (outer) input, Spanner
  issues an index/table seek into the right (inner) input using the bound
  source/destination key.
- **When it excels**:
  - Selective traversals starting from 1 to a few thousand anchor nodes.
  - Traversals along interleaved child edge tables
    (`Local Distributed Cross Apply`), where parent and child rows reside in the
    same split.
- **Symptom of failure**: When the left input contains tens of thousands or
  millions of rows (for example, an unselective whole-graph scan or a
  high-fan-out multi-hop expansion), `Distributed Cross Apply` issues millions
  of point probes across splits, causing high CPU and network RPC latency.

### `Hash Join` (`hash_join`)

- **How it works**: Spanner scans the build side once, constructs an in-memory
  hash table, and streams the probe side through it.
- **When it excels**:
  - Bulk or unselective graph queries that touch a significant fraction of a
    node or edge table.
  - Multi-hop analytical aggregations across large subgraphs where sequential
    scans are much faster than millions of random B-tree lookups.
- **Symptom of failure**: When used on a highly selective lookup without a
  pushed-down filter on the scanned side, `Hash Join` may scan an entire
  multi-million-row table just to match 5 anchor rows.

---

## 3. Statement-Level, Node-Level, and Edge-Level Hint Syntax

Spanner Graph supports optimizer hints at the **statement/block level** and at
the **individual node or edge pattern level**.

### Statement-Level Join Method Hint

Applies to the whole query when placed before `GRAPH`:

```sql
@{JOIN_METHOD=HASH_JOIN}
GRAPH FinGraph
MATCH (a:Account)-[t:Transfers]->(b:Account)
WHERE a.Status = 'ACTIVE' AND t.amount > 10000
RETURN b.id, COUNT(t) AS high_value_inbound_count
GROUP BY b.id
```

### Element Hints (`@{FORCE_INDEX=...}`) and Traversal Hints (`@{JOIN_METHOD=...}`)

- **Element hints** go *first* inside a node pattern `(@{...} n:Label {...})` or
  edge pattern `-[@{...} e:Label]->`.
- **Traversal hints** (`JOIN_METHOD`) go *between* an edge pattern and the next
  node pattern: `-[e:Label]-> @{JOIN_METHOD=APPLY_JOIN} (m:Label)`.
- Writing a hint after the label (`(n:Label @{...})` or `-[e:Label @{...}]->`)
  is a syntax error (`Expected "]" but got "@"`).

```sql
GRAPH FinGraph
MATCH (@{FORCE_INDEX=PersonsByEmail} p:Person {email: @email})
      -[o:Owns]-> @{JOIN_METHOD=APPLY_JOIN}
      (a:Account)
      <-[@{FORCE_INDEX=AccountTransferAccountByDestSrc} t:Transfers]- @{JOIN_METHOD=APPLY_JOIN}
      (sender:Account)
RETURN sender.id AS sender_id, t.amount
```

### Common Element & Pattern Hints Reference

- `@{FORCE_INDEX=IndexName}` (element hint, first inside the pattern): Forces
  Spanner to scan the backing node or edge table via the specified secondary
  index (for example, a reverse-traversal covering index on
  `(dest_id, src_id)`).
- `@{FORCE_INDEX=_BASE_TABLE}`: Forces Spanner to scan the primary key of the
  base table instead of a secondary index (valid as an element hint or at
  statement level).
- `@{JOIN_METHOD=HASH_JOIN}`: Forces a hash join for the traversal step
  (traversal hint between elements, or statement level).
- `@{JOIN_METHOD=APPLY_JOIN}`: Forces an apply (nested-loop index lookup) join
  for the traversal step.
- `@{JOIN_METHOD=MERGE_JOIN}`: Forces a sort-merge join when both inputs are
  already ordered by the join key.
- `@{factorized_mode=factorize_left}`: Placed before a target node on a linear
  or quantified path
  (`-[e1:Transfers]->{1,3}@{factorized_mode=factorize_left}(a2:Account)`);
  deduplicates converging paths by destination key before probing the target
  node table. Return per-path or destination columns: with `RETURN COUNT(*)`
  Spanner rejects the hint. The gain depends on the convergence ratio (at
  moderate convergence it mainly reduces rows scanned, with little change in
  latency), so verify it with `PROFILE`.
- `@{factorized_mode=factorize_both}`: Placed on conditionally independent arms
  of a star query
  (`MATCH (a)-[e1]->(a1), @{factorized_mode=factorize_both}(a)-[e2]->(a2)`);
  evaluates each arm independently once ($M + N + K$) before forming the final
  output, avoiding nested-loop re-evaluation ($M \times N \times K$). Spanner
  rejects it when the query aggregates the cross product with `RETURN COUNT(*)`
  (`A join in the query cannot be executed in factorized execution mode`).
  Because the final output still materializes the cross product, prefer chained
  `NEXT` aggregation unless flat rows are needed and `PROFILE` shows an
  improvement.

---

## 4. Quantified Path and Foreign-Key Join Elimination Guardrails

### Guardrail 1: Do NOT Force Hints on Quantified Variable-Length Paths (`{m, n}`)

When executing variable-length quantified paths such as:

```sql
GRAPH NetworkGraph
MATCH (start:Device {device_id: @id})-[:ConnectedTo]->{1, 4}(target:Device)
RETURN DISTINCT target.device_id
```

Do **not** add a statement-level `@{JOIN_METHOD=HASH_JOIN}` (or a hash-join
traversal hint on the quantified hop) unless you have verified in `PROFILE` that
the entire table is being scanned at every depth. On anchored variable-length
paths, a forced hash join forces full-table build/probe scans at each recursion
depth instead of expanding only the active frontier via `Apply Join`, which
multiplies both rows scanned and latency.

### Guardrail 2: Preserve Foreign-Key Endpoint Join Elimination

When a query only projects or filters on the **key column** of a target node `b`
(for example, `MATCH (a:Account)-[t:Transfers]->(b:Account)` returning
`a.id AS src_id, b.id AS dst_id`), Spanner's optimizer can **eliminate the join
to the `Account` table for `b`** if the schema defines a `FOREIGN KEY` (enforced
or `NOT ENFORCED`) from `Transfers(dest_id)` to `Account(id)`, reading `b.id`
directly from `Transfers.dest_id`.

- Informational (`NOT ENFORCED`) foreign keys enable this optimization by
  default, but they don't prevent dangling edges: if an edge points to a missing
  node, queries that rely on the eliminated join can return results that don't
  match the data. Prefer enforced foreign keys, and confirm with the user before
  recommending a `NOT ENFORCED` one (see spanner-graph-schema-best-practices).
- Avoid adding element hints on `b` (`(@{...} b:Account)`) or referencing
  non-key properties of `b` when only `b.id` is needed, as they can force the
  optimizer to materialize the otherwise-eliminated `Account` table scan.
