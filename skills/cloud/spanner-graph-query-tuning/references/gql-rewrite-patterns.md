# ISO GQL Query Rewrite Patterns for Spanner Graph

## Table of Contents

- [1. Anchor-First Pattern Ordering](#1-anchor-first-pattern-ordering): Lines
  22-49
- [2. Chained NEXT with Early Aggregation Instead of Multi-Arm Comma MATCH](#2-chained-next-with-early-aggregation-instead-of-multi-arm-comma-match):
  Lines 53-102
- [3. Explicit Node and Edge Labels Across NEXT Boundaries](#3-explicit-node-and-edge-labels-across-next-boundaries):
  Lines 106-135
- [4. Eliminating Redundant NEXT Self-Joins on Folded Edges](#4-eliminating-redundant-next-self-joins-on-folded-edges):
  Lines 139-163
- [5. Bounding Super-Node Fan-Out with IS_FIRST or Hub Exclusion](#5-bounding-super-node-fan-out-with-is_first-or-hub-exclusion):
  Lines 167-230
- [6. Eliminating `ARRAY_AGG` and `IN UNNEST` Anti-Pattern Across `NEXT`](#6-eliminating-array_agg-and-in-unnest-anti-pattern-across-next):
  Lines 234-267
- [7. Decorrelating `EXISTS` Subqueries via `OPTIONAL MATCH`](#7-decorrelating-exists-subqueries-via-optional-match):
  Lines 271-313
- [8. Deep Quantified Path Optimization: Lightweight Recursion and Late Materialization](#8-deep-quantified-path-optimization-lightweight-recursion-and-late-materialization):
  Lines 317-408

## 1. Anchor-First Pattern Ordering

Always place the node or edge pattern with the highest selectivity (smallest
number of matching rows) at the very beginning of the `MATCH` pattern.

### Anti-Pattern (Unselective Hop First)
```sql
GRAPH FinGraph
MATCH (a:Account)-[t:Transfers]->(b:Account),
      (p:Person {id: @person_id})-[o:Owns]->(a:Account)
WHERE t.amount > 1000
RETURN p.name, a.id AS account_id, b.id AS to_account_id, t.amount
```
Why it is slow: Comma-separated patterns or placing the unselective
`(a)-[t:Transfers]->(b)` hop first can cause the query planner to evaluate or
materialize a broader intermediate set before applying the single-row anchor
`p.id = @person_id`.

### Optimized Pattern (Single Connected Path Starting at Anchor)
```sql
GRAPH FinGraph
MATCH (p:Person {id: @person_id})-[o:Owns]->(a:Account)-[t:Transfers]->(b:Account)
WHERE t.amount > 1000
RETURN p.name, a.id AS account_id, b.id AS to_account_id, t.amount
```
Why it is fast: Spanner seeks `Person(id = @person_id)` directly
(`SeekableKeySize: [1]`), traverses interleaved or indexed `Owns` edges for that
single person, and expands only that person's `Transfers`.

---

## 2. Chained NEXT with Early Aggregation Instead of Multi-Arm Comma MATCH

When a query starts at an anchor node `a` and expands multiple independent 1:N
relationships—such as `(a)-[:HasDevice]->(d:Device)` and
`(a)-[:HasAlert]->(al:Alert)`—putting both arms in a single comma-separated
`MATCH` produces a **Cartesian product** (`|Devices| x |Alerts|`) per anchor
node.

### Anti-Pattern (Multi-Arm Comma MATCH Cartesian Explosion)
```sql
GRAPH NetworkGraph
MATCH (s:Site {region_id: @region_id})-[:HostsRouter]->(r:Router),
      (r)-[:HasInterface]->(i:Interface),
      (r)-[:HasAlarm]->(a:Alarm)
WHERE a.severity = 'CRITICAL'
RETURN r.router_id,
       COUNT(DISTINCT i.interface_id) AS interface_count,
       ARRAY_AGG(DISTINCT a.alarm_id) AS critical_alarms
GROUP BY r.router_id
```
Why it is slow: If a router has 200 interfaces and 50 critical alarms, the
single `MATCH` block generates `200 * 50 = 10,000` intermediate rows per router,
and then burns CPU deduplicating them with `COUNT(DISTINCT ...)` and
`ARRAY_AGG(DISTINCT ...)`.

### Optimized Pattern (Linear Chained NEXT with Per-Stage Aggregation)
```sql
GRAPH NetworkGraph
MATCH (s:Site {region_id: @region_id})-[:HostsRouter]->(r:Router)-[:HasAlarm]->(a:Alarm)
WHERE a.severity = 'CRITICAL'
RETURN r, ARRAY_AGG(a.alarm_id) AS critical_alarms
GROUP BY r

NEXT

MATCH (r:Router)-[:HasInterface]->(i:Interface)
RETURN r.router_id,
       COUNT(i.interface_id) AS interface_count,
       ANY_VALUE(critical_alarms) AS critical_alarms
GROUP BY r.router_id
```
Why it is fast:

1. Stage 1 filters routers down to only those with critical alarms
   (`WHERE a.severity = 'CRITICAL'`) and collapses the cardinality back to **1
   row per `r`** via `GROUP BY r`.
2. Stage 2 expands `:HasInterface` only once per surviving router, avoiding the
   `200 x 50` Cartesian product and eliminating expensive `DISTINCT`
   deduplication. (`critical_alarms` is carried with `ANY_VALUE` because Spanner
   does not allow `GROUP BY` on an `ARRAY` column.)

---

## 3. Explicit Node and Edge Labels Across NEXT Boundaries

When a variable `r` is bound in Stage 1 and passed via
`RETURN r NEXT MATCH (r)...` to Stage 2, always re-specify the node label on `r`
in Stage 2 (`MATCH (r:Router)...`) if the property graph contains multiple node
tables or shared edge labels.

### Anti-Pattern (Unlabeled Bound Node in NEXT Stage)
```sql
GRAPH NetworkGraph
MATCH (s:Site {site_id: @site_id})-[:HostsRouter]->(r:Router)
RETURN r
NEXT
MATCH (r)-[e:LocatedIn]->(z:Zone)
RETURN r.router_id, z.zone_name
```
Why it is slow: If `:LocatedIn` is an edge label shared by multiple source node
tables (`Router`, `Rack`, `Switch`), omitting `:Router` on `(r)` in the second
`MATCH` can cause Spanner to build a polymorphic union scan across all tables
that participate in `:LocatedIn`.

### Optimized Pattern (Explicit Labels in Every MATCH Stage)
```sql
GRAPH NetworkGraph
MATCH (s:Site {site_id: @site_id})-[:HostsRouter]->(r:Router)
RETURN r
NEXT
MATCH (r:Router)-[e:LocatedIn]->(z:Zone)
RETURN r.router_id, z.zone_name
```

---

## 4. Eliminating Redundant NEXT Self-Joins on Folded Edges

When an `N:1` or `1:1` edge is folded directly into a node table
(`Table AS Edge`) via a foreign-key column (for example, `Router.site_id`), and
a query only needs `site_id` (or needs to verify that `site_id IS NOT NULL`), do
not add a `NEXT MATCH` hop that joins back to `Site` unless you actually read
non-key properties from `Site`.

### Anti-Pattern (Unnecessary Extra Hop for Key Column)
```sql
GRAPH NetworkGraph
MATCH (r:Router {status: 'ACTIVE'})
RETURN r
NEXT
MATCH (r:Router)-[:InstalledAtSite]->(s:Site)
RETURN r.router_id, s.site_id
```

### Optimized Pattern (Direct Property Projection on Folded Key)
```sql
GRAPH NetworkGraph
MATCH (r:Router {status: 'ACTIVE'})
WHERE r.site_id IS NOT NULL
RETURN r.router_id, r.site_id
```

---

## 5. Bounding Super-Node Fan-Out with IS_FIRST or Hub Exclusion

In scale-free graphs, a small percentage of hub nodes ("super-nodes") may have
10,000+ incident edges. Expanding all incident edges of a super-node during
multi-hop path exploration can cause latency spikes and out-of-memory errors.

### Anti-Pattern (Unbounded Multi-Hop Expansion Through Hubs)
```sql
GRAPH FinGraph
MATCH (a1:Account {is_blocked: true})-[e:Transfers]->{1, 5}(a2:Account)
RETURN a1.id AS src_id, a2.id AS dst_id
```

### Optimized Pattern A: Per-Hop Edge Sampling Inside Quantified Paths (`FILTER IS_FIRST`)
```sql
GRAPH FinGraph
MATCH (a1:Account {is_blocked: true})
  -[e:Transfers WHERE e IN {
      MATCH -[selected_e:Transfers]->
      FILTER IS_FIRST(@max_edges) OVER (
        PARTITION BY SOURCE_NODE_ID(selected_e)
        ORDER BY selected_e.create_time DESC)
      RETURN selected_e
    }]->{1, 5}(a2:Account)
RETURN a1.id AS src_id, a2.id AS dst_id
```
Why it is fast: At each hop of the `{1, 5}` traversal, the subquery samples at
most `@max_edges` recent outgoing edges per source node
(`PARTITION BY SOURCE_NODE_ID(selected_e)`), preventing exponential fan-out
across high-degree accounts.

### Optimized Pattern B: Midpoint Node Sampling Across `NEXT`
```sql
GRAPH SocialGraph
MATCH (u:User {country: 'FR'})-[:Follows]->(influencer:User)
FILTER IS_FIRST(20) OVER (PARTITION BY u.user_id)
RETURN DISTINCT influencer

NEXT

MATCH (influencer:User)-[:Posted]->(p:Post)
FILTER IS_FIRST(10) OVER (PARTITION BY influencer.user_id ORDER BY p.created_at DESC)
RETURN influencer.user_id, p.post_id
LIMIT 500
```

### Optimized Pattern C: Deterministic Hub Exclusion Inside Quantified Paths
```sql
GRAPH FinGraph
MATCH (src:Account {id: @id})
      ((a:Account WHERE a.is_hub = FALSE)-[e:Transfers]->(b:Account)){1, 3}
      (dst:Account)
RETURN DISTINCT dst.id AS dst_id
```
Why and when to use it: When hub nodes (such as exchanges, clearinghouses, or
payment processors) are not meaningful intermediaries for the business question,
precomputing an `is_hub` boolean column on `Account` and filtering the expansion
node `a` inside the quantified step prevents traversal through hubs. Both
`IS_FIRST` and hub exclusion intentionally change result semantics to bound
fan-out: `IS_FIRST` caps per-node degree by sampling edges (non-deterministic
only when `ORDER BY` is omitted or has ties), whereas hub exclusion drops paths
through hubs while deterministically returning all non-hub paths and avoiding
hub neighborhood expansion at every hop. Caveats: the `is_hub` flag must be
maintained, and filtering `a.is_hub` adds a node lookup per hop.

---

## 6. Eliminating `ARRAY_AGG` and `IN UNNEST` Anti-Pattern Across `NEXT`

When passing matched nodes from one `NEXT` stage to the next, never aggregate
node IDs into an array only to filter by `WHERE n.id IN UNNEST(ids)` in the next
stage.

### Anti-Pattern (`ARRAY_AGG` + `IN UNNEST` Full Table Scan)
```sql
GRAPH SocialGraph
MATCH (p:Person {id: @person_id})-[:Knows]->{1, 2}(f:Person)
RETURN ARRAY_AGG(DISTINCT f.id) AS friend_ids

NEXT

MATCH (f:Person)-[:LocatedIn]->(c:City)
WHERE f.id IN UNNEST(friend_ids)
RETURN f.id, c.name
```
Why it is slow: Aggregating into `ARRAY_AGG` collapses the pipeline into a
single array row, and `WHERE f.id IN UNNEST(friend_ids)` in the next stage can
trigger a full table scan of `Person` with a per-row `ArrayUnnest` check instead
of index seeks.

### Optimized Pattern (Pass Bound Node Variable Directly Across `NEXT`)
```sql
GRAPH SocialGraph
MATCH (p:Person {id: @person_id})-[:Knows]->{1, 2}(f:Person)
RETURN DISTINCT f

NEXT

MATCH (f:Person)-[:LocatedIn]->(c:City)
RETURN f.id, c.name
```

---

## 7. Decorrelating `EXISTS` Subqueries via `OPTIONAL MATCH`

Correlated `EXISTS` or `NOT EXISTS` graph subqueries inside `WHERE` (especially
inside `OR` predicates or after `OPTIONAL MATCH`) often execute row-by-row via
`CrossApply`. Rewriting them with `OPTIONAL MATCH` allows set-based execution
without needing a separate `NEXT` stage.

### Anti-Pattern (Correlated `NOT EXISTS` Subquery in `WHERE`)
```sql
GRAPH FinGraph
MATCH (p:Person {country: 'US'})-[:Owns]->(a:Account)
WHERE NOT EXISTS {
  MATCH (a2:Account)-[:Transfers]->(b:Account {is_blocked: true})
  WHERE a2 = a
}
RETURN p.id AS person_id, a.id AS account_id
```
A subquery cannot redeclare the outer variable `a` (`MATCH (a)-[...]` inside
`EXISTS` is rejected with
`redefining graph element variables in a subquery is not allowed`), so it binds
`a2` and checks `a2 = a`. This form compiles but runs as an `Anti-Semi Apply`
that re-scans the subquery's `Account` table for every outer row: the `a2 = a`
correlation is not pushed into the subquery's node scan, so the query can time
out on large inputs.

### Optimized Pattern (`OPTIONAL MATCH` + `FILTER b IS NULL`)
```sql
GRAPH FinGraph
MATCH (p:Person {country: 'US'})-[:Owns]->(a:Account)
OPTIONAL MATCH (a)-[:Transfers]->(b:Account {is_blocked: true})
FILTER b IS NULL
RETURN p.id AS person_id, a.id AS account_id
```
Why it is fast: `OPTIONAL MATCH` chains directly after `MATCH` in the same
linear query (a preceding `NEXT` is needed only after an aggregation such as
`GROUP BY`), and Spanner decorrelates `OPTIONAL MATCH ... FILTER b IS NULL` into
a set-based **hash anti-semi join**. Here the trailing `FILTER b IS NULL` is the
intended anti-join check, not the `WHERE` vs. `FILTER` mistake (`SKILL.md`
`GQL Semantic & Syntax Guardrails`) where filtering a non-null property of `b`
in `FILTER` turns an outer join into an inner join. For a positive
`EXISTS { MATCH ... }` check, rewrite to `MATCH` and deduplicate with
`FILTER IS_FIRST(1) OVER (PARTITION BY ...)` or `RETURN DISTINCT` if multiple
edges can match per outer row.

---

## 8. Deep Quantified Path Optimization: Lightweight Recursion and Late Materialization

Unreferenced intermediate node variables inside
`((v:Part)-[e:Supplies]->(t:Part)){1, 8}` are pruned automatically by Spanner
Graph. Memory blowups and redundant wide-table scans in deep quantified paths
come from two distinct sources: **referencing** intermediate node group
variables inside recursion, and **carrying wide node properties** through
high-cardinality aggregations or multi-stage `NEXT` pipelines before filtering
or limiting.

### Pattern 8A: Project Hop Keys from Edge Group Variables Instead of Node Group Variables

#### Anti-Pattern (Referencing Intermediate Node Group Variable `t` in Recursion)
```sql
GRAPH SupplyChainGraph
MATCH (src:Part {part_id: @part_id})
      ((v:Part)-[e:Supplies]->(t:Part)){1, 8}
      (dst:Part)
RETURN dst.part_id,
       ARRAY_TRANSFORM(t, n -> n.part_id) AS hop_part_ids
```
Why it is slow: Even though `ARRAY_TRANSFORM` only projects `n.part_id`,
referencing the node group variable `t` (or binding `MATCH p = ...` and calling
`NODES(p)`) forces `RecursiveScan` to scan `Part` at every hop and accumulate
`ARRAY<GRAPH_NODE<Part>>` structs containing all columns of `Part` (including
wide columns such as `manufacturer_details`) in the recursion buffer.

#### Optimized Pattern (Read Hop Keys from Edge Group Variable `e`)
```sql
GRAPH SupplyChainGraph
MATCH (src:Part {part_id: @part_id})
      (()-[e:Supplies]->()){1, 8}
      (dst:Part)
RETURN dst.part_id,
       ARRAY_TRANSFORM(e, el -> el.dst_part_id) AS hop_part_ids
```
Why it is fast: Unreferenced intermediate nodes are pruned from `RecursiveScan`,
foreign-key join elimination satisfies `dst.part_id` directly from
`e.dst_part_id`, and recursion scans only the narrow `Supplies` edge table.

### Pattern 8B: Late Materialization of Wide Columns Across Multi-Stage `NEXT` Queries

#### Anti-Pattern (Carrying Wide Columns Through Aggregation and Ranking)
```sql
GRAPH SupplyChainGraph
MATCH (src:Part {part_id: @part_id})
      (()-[e:Supplies]->()){1, 8}
      (dst:Part)
RETURN dst.part_id,
       dst.part_name,
       dst.manufacturer_details,
       COUNT(1) AS path_count
GROUP BY dst.part_id, dst.part_name, dst.manufacturer_details
ORDER BY path_count DESC, dst.part_id
LIMIT 100
```
Why it is slow: Spanner probes `Part` across all converging paths before
grouping, carries wide columns (`part_name`, `manufacturer_details`) through
`GROUP BY` and `ORDER BY` (which also fails if `manufacturer_details` is a
non-groupable `JSON` or `ARRAY` column), and discards all but the top 100 rows.

#### Optimized Pattern (Aggregate & Limit on Keys First, Fetch Wide Columns in `NEXT`)
```sql
GRAPH SupplyChainGraph
MATCH (src:Part {part_id: @part_id})
      (()-[e:Supplies]->()){1, 8}
      (dst:Part)
RETURN dst.part_id AS target_part_id,
       COUNT(1) AS path_count
GROUP BY target_part_id
ORDER BY path_count DESC, target_part_id
LIMIT 100

NEXT

MATCH (dst:Part)
WHERE dst.part_id = target_part_id
RETURN dst.part_id,
       dst.part_name,
       dst.manufacturer_details,
       path_count
ORDER BY path_count DESC, dst.part_id
```
Note: a column from the previous statement (`target_part_id`) can be referenced
only in the outermost `WHERE` of the next `MATCH`, not inside a property filter
`{part_id: target_part_id}`.

Why it is fast: Both queries return the exact same top-100 rows, but Stage 1
satisfies `dst.part_id` directly from `e.dst_part_id` via foreign-key join
elimination (zero `Part` scans during recursion, grouping, and ranking), and
Stage 2 fetches wide `Part` properties via 100 point seeks only for the final
winners.
