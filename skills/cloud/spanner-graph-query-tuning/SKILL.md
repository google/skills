---
name: spanner-graph-query-tuning
metadata:
  version: "1.0.0"
  category: Databases
description: >-
  Tunes and troubleshoots Spanner Graph on Google Cloud ISO GQL queries and
  execution plans. Use when optimizing slow Spanner Graph GQL queries,
  diagnosing distributed cross apply versus hash join execution operators and
  index seek prefixes, eliminating multi-arm star query Cartesian products with
  chained query aggregation, bounding super-node fan-out, decorrelating slow
  subqueries or optional matches, optimizing deep quantified variable-length
  paths, or applying join method, index, and path factorization query hints.
  Don't use for relational-to-property-graph schema mapping over existing
  relational tables (use spanner-relational-to-graph) or physical schema,
  table, and interleaving design (use spanner-graph-schema-best-practices).
---

# Spanner Graph Query Tuning Best Practices

Optimizing ISO GQL queries on Spanner Graph requires aligning pattern matching
and path aggregation with Spanner's distributed query execution engine. Small
syntactic choices in `MATCH` and `NEXT` statements can mean the difference
between a targeted index seek (`SeekableKeySize: [N]`) and a full multi-way
cross apply over millions of intermediate paths.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you MUST
read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Prerequisites & Cloud Environment Setup

Before profiling or executing queries against a Spanner instance (see
`spanner-basics` for general Spanner instance provisioning and MCP setup):

1. **Google Cloud SDK (`gcloud`) & Static Analysis Fallback**: Verify whether
   the CLI is installed (do not install `gcloud` without explicit user
   permission; see
   [Install the Google Cloud SDK](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt)).
   If `gcloud` or live Spanner database access is unavailable, do not block on
   executing `gcloud spanner databases ddl describe` or
   `--query-mode=PROFILE`—instead, perform static GQL query analysis and
   rewrites directly using the user-provided query, DDL, or execution plan and
   the bundled `references/` guides.
2. **Project, Billing & API**: Verify an active Google Cloud project with
   billing enabled (required even when provisioning a free trial instance) is
   configured (`gcloud config set project {project_id}`) and, after the user
   confirms, enable the Spanner API
   (`gcloud services enable spanner.googleapis.com`). Ask the user before
   changing the active project, billing, or enabled APIs, because these commands
   change the user's Google Cloud environment and can incur costs.
3. **Authentication & Identity and Access Management (IAM) Roles**: Authenticate
   via `gcloud auth login` or `gcloud auth application-default login` (or
   `GOOGLE_APPLICATION_CREDENTIALS` for service accounts). Inspecting DDL and
   profiling queries requires `roles/spanner.databaseReader` (or
   `roles/spanner.databaseUser`) on `{database_id}`.
4. **Instance Region, Pricing & Teardown**: For test instances, default to
   `regional-us-central1` unless specified otherwise (see
   [Spanner instance configurations](https://docs.cloud.google.com/spanner/docs/instance-configurations.md.txt),
   [Google Cloud locations](https://cloud.google.com/about/locations),
   [Spanner pricing](https://cloud.google.com/spanner/pricing), and
   [Google Cloud pricing](https://cloud.google.com/pricing)). After benchmarking
   on temporary test resources, remind the user to delete temporary test
   databases
   (`gcloud spanner databases delete {database_id} --instance={instance_id}`) or
   test instances (`gcloud spanner instances delete {instance_id}`) so they do
   not incur ongoing Spanner compute and storage charges.

---

## Closed-Loop Query Profiling Workflow

Never apply join or index hints blindly. Always inspect the database DDL,
profile the baseline query, apply structural GQL rewrites first, validate
compilation with `PLAN`, and re-profile to verify latency and scanned rows:

1. **Fetch the schema DDL and profile the baseline query** using
   `gcloud spanner databases ddl describe` and
   `gcloud spanner databases execute-sql` with `--query-mode=PROFILE` (or
   `--query-mode=PLAN` if the baseline times out):

   ```bash
   gcloud spanner databases ddl describe {database_id} --instance={instance_id}

   gcloud spanner databases execute-sql {database_id} \
     --instance={instance_id} \
     --query-mode=PROFILE \
     --sql="GRAPH MyGraph MATCH ... RETURN ..."
   ```

2. **Inspect key execution plan metrics** (detailed in
   [references/profile-and-hints-guide.md](references/profile-and-hints-guide.md)):
   - **Join Type**: Check whether traversal steps use `Distributed Cross Apply`
     (nested-loop index seeks per input row) or `Hash Join` (set-based scan +
     build/probe).
   - **`SeekableKeySize` vs. `Residual Condition`**: In each `TableScan` or
     `IndexScan`, check whether predicates are pushed down into
     `SeekableKeySize: [N]` (index key seek) or evaluated after scanning as a
     `Residual Condition`.
   - **Row Amplification (`Rows Returned` vs. `Storage Read`)**: Identify which
     `MATCH` hop causes combinatorial path explosion before a downstream filter
     or `GROUP BY`.
3. **Apply structural GQL rewrites first** (see
   [Core ISO GQL Query Rewrite Rules](#core-iso-gql-query-rewrite-rules) and
   [references/gql-rewrite-patterns.md](references/gql-rewrite-patterns.md)) and
   validate syntax/compilation quickly with `--query-mode=PLAN`.
4. **Apply statement or element hints only if the optimizer chooses a suboptimal
   physical plan** (see
   [Hint Selection and Guardrails](#hint-selection-and-guardrails)), and re-run
   `--query-mode=PROFILE` to confirm improvement. If a hint degrades latency,
   revert it immediately.

---

## Core ISO GQL Query Rewrite Rules

Before adding optimizer hints, restructure the GQL query so the cardinality
stays small at every step:

### Rule 1: Start Traversals from the Lowest-Cardinality Anchor Node

Order your `MATCH` patterns so the most selective filter (such as
`WHERE n.id = @id` or a selective indexed property) appears **first** in the
pattern chain:

- **Prefer:**

  ```sql
  GRAPH FinGraph
  MATCH (p:Person {id: @person_id})-[o:Owns]->(a:Account)-[t:Transfers]->(b:Account)
  RETURN a.id AS account_id, b.id AS to_account_id, t.amount
  ```

- **Avoid:** Placing unselective patterns first or writing disconnected
  comma-separated patterns, which can delay selectivity application:

  ```sql
  GRAPH FinGraph
  MATCH (a:Account)-[t:Transfers]->(b:Account),
        (p:Person {id: @person_id})-[o:Owns]->(a:Account)
  RETURN a.id AS account_id, b.id AS to_account_id, t.amount
  ```

### Rule 2: Eliminate Multi-Arm Star Query Cartesian Explosions (3 Patterns)

When a query traverses multiple independent 1:N arms from a hub node (for
example, fetching a consumer's emails, phones, addresses, and accounts, or a
router's interfaces and alarms) in a single comma-separated `MATCH`, Spanner
produces an $M \times N \times K$ **Cartesian product** (or sequential
`DistributedOuterApply` joins with `OPTIONAL MATCH`). Choose one of three
remedies based on the required output shape:

1. **Chained `NEXT` + Early Aggregation or Nested `ARRAY { MATCH ... }`
   Subqueries**: Collapse each arm to 1 row per anchor node via `GROUP BY`
   across `NEXT` stages, or collect each 1:N arm into an array column.
   Subqueries cannot redeclare an outer graph variable, so bind a new variable
   and compare it to the outer one
   (`ARRAY { MATCH (n2)-[:HasEmail]->(e:Email) WHERE n2 = n RETURN e.addr }`).
2. **Factorized Execution Hint (`@{factorized_mode=factorize_both}`)**: When
   flat cross-product output rows are genuinely needed, attach
   `@{factorized_mode=factorize_both}` to the conditionally independent arms
   (`MATCH (a)-[e1]->(a1), @{factorized_mode=factorize_both}(a)-[e2]->(a2)`) so
   Spanner evaluates each branch once ($M + N + K$) before forming the final
   result. Return per-arm columns; with `RETURN COUNT(*)` Spanner rejects the
   hint (`A join in the query cannot be executed in factorized execution mode`).
   Because the final output still materializes the cross product, the hint
   usually gains little, while remedy 1 is much faster for aggregated results;
   prefer remedy 1 and keep the hint only if `PROFILE` shows a gain.
3. **Client-Side Parallel Query Decomposition**: When returning wide property
   lists across 4+ independent entity types for a cluster of anchor nodes,
   execute Query 1 to fetch the anchor/cluster node IDs, then issue concurrent
   1-hop queries (`WHERE n.id IN UNNEST(@anchor_ids)`) for each attribute branch
   in parallel.

### Rule 3: Always Specify Node and Edge Labels Across Every `MATCH` and `NEXT` Block

In schemas with multiple node or edge tables (polymorphic labels), omitting a
label (`MATCH (a)-[e]->(b)`) forces Spanner to generate a `Distributed Union`
across **all** node and edge tables in the property graph.

- **Even more critical across `NEXT`**: When passing a node variable `n` into a
  subsequent `NEXT MATCH (n)-[e:EdgeLabel]->(m:TargetLabel)` stage, **re-specify
  the label on the bound node variable**
  (`MATCH (n:SourceLabel)-[e:EdgeLabel]->(m:TargetLabel)`). Omitting
  `:SourceLabel` on `n` in the second `MATCH` can cause Spanner to scan
  unrelated node tables that share the same edge label.

### Rule 4: Avoid Redundant `NEXT` Self-Joins When Edge Endpoints Are Already Available

When a 1:1 or N:1 relationship has been folded into a node table
(`Table AS Edge`), or when you only need the destination key that is already
stored on the source node or edge row, do not chain an extra `NEXT MATCH` hop
that re-scans the same table by primary key just to project a key column or
check existence. Project the property directly in the initial `MATCH` stage.

### Rule 5: Bound Super-Node Fan-Out with `IS_FIRST` or Hub Exclusion, and Avoid Unbounded `OPTIONAL MATCH + LIMIT`

High-degree "super-nodes" (hub nodes with tens of thousands of incident edges)
can dominate query latency when a multi-hop traversal expands every neighbor.

- **Per-hop edge sampling inside quantified paths**: Use
  `FILTER IS_FIRST(@max_edges) OVER (PARTITION BY ...)` with
  `SOURCE_NODE_ID(selected_e)` inside an edge subquery:

  ```sql
  GRAPH FinGraph
  MATCH (a1:Account {is_blocked: true})
    -[e:Transfers WHERE e IN {
        MATCH -[selected_e:Transfers]->
        FILTER IS_FIRST(@max_edges) OVER (
          PARTITION BY SOURCE_NODE_ID(selected_e)
          ORDER BY selected_e.create_time DESC)
        RETURN selected_e
      }]->{1,5}(a2:Account)
  RETURN a1.id AS src_id, a2.id AS dst_id
  ```

- **Single-hop or midpoint sampling**: Use
  `FILTER IS_FIRST(@k) OVER (PARTITION BY a.id)` between hops.
- **Deterministic hub exclusion inside quantified paths**: When hub nodes (such
  as exchanges, payment processors, or shared system accounts) are not
  meaningful intermediaries, precompute a boolean `is_hub` flag on the node
  table and filter the expansion node at each step:
  `MATCH (src:Account {id: @id})((a:Account WHERE a.is_hub = FALSE)-[e:Transfers]->(b:Account)){1,3}(dst:Account)`.
  Both `IS_FIRST` and hub exclusion intentionally change result semantics to
  bound fan-out: `IS_FIRST` caps per-node degree by sampling edges
  (non-deterministic only when `ORDER BY` is omitted or has ties), whereas hub
  exclusion drops paths through hubs while deterministically returning all
  non-hub paths and avoiding hub neighborhood expansion at every hop. Note that
  hub exclusion requires maintaining `is_hub` and adds a node-property lookup
  per hop.
- **`OPTIONAL MATCH` + `ORDER BY` + `LIMIT` Pitfall**: Spanner cannot push
  `LIMIT` or index sort order through the `LEFT OUTER JOIN`
  (`DistributedOuterApply`) generated by `OPTIONAL MATCH`. Bound the optional
  expansion inside an `IS_FIRST` or an
  `ARRAY { MATCH (a2)-[e]->(x) WHERE a2 = a ORDER BY ... LIMIT k RETURN ... }`
  subquery, or use `MATCH` when optionality is not required.

### Rule 6: Seek Prefix Keys Instead of Post-Filtering

Ensure `WHERE` predicates match the leading columns of the node/edge primary key
or secondary index so the execution plan shows `SeekableKeySize: [1]` (or `[N]`)
rather than `SeekableKeySize: [0]` with a `Residual Condition`. Avoid wrapping
key columns in non-sargable functions (such as `CAST(n.id AS STRING) = @id` or
`LOWER(n.code) = @code`) unless backed by a generated column index.

### Rule 7: Optimize Deep Quantified Paths (`{m, n}`) via Lightweight Recursion, Late Materialization, and `factorize_left`

1. **Do not reference intermediate node group variables inside deep quantified
   paths**: Unreferenced intermediate node variables in
   `((v:Node)-[e:Edge]->(t:Node)){1, 10}` are pruned automatically, **but
   referencing `v` or `t`** (even for `ARRAY_TRANSFORM(t, n -> n.id)`, or
   binding `MATCH p = ...` and calling `NODES(p)`) forces `RecursiveScan` to
   scan `Node` at every hop and accumulate full `ARRAY<GRAPH_NODE>` structs
   (with all `Node` columns) in the recursion buffer. Instead, read intermediate
   endpoint keys from the edge group variable
   (`ARRAY_TRANSFORM(e, el -> el.to_id)`).
2. **Defer wide property lookups across multi-stage queries (late
   materialization)**: When grouping, ranking (`ORDER BY ... LIMIT`), or
   filtering reachable nodes across `NEXT` stages on wide node tables, carry
   only lightweight key columns (`dst.id`, satisfied from `e.to_id` via
   foreign-key join elimination without scanning `Node`) through intermediate
   stages, and join `(dst:Node)` in the final `NEXT` stage to fetch wide columns
   only for surviving keys.
3. **Deduplicate converging paths before target node lookup
   (`@{factorized_mode=factorize_left}`)**: When many multi-hop paths converge
   on the same destination nodes, attach `@{factorized_mode=factorize_left}`
   before the destination node
   (`-[e:Transfers]->{1,3}@{factorized_mode=factorize_left}(a2:Account)`) so
   Spanner deduplicates destination keys before probing the `Account` table.
   Return per-path or destination columns: with `RETURN COUNT(*)` Spanner
   rejects the hint
   (`A join in the query cannot be executed in factorized execution mode`). The
   payoff grows with the convergence ratio (at moderate convergence it mainly
   reduces destination lookups and rows scanned, with little change in latency),
   so confirm the gain with `PROFILE`.

### Rule 8: Avoid `ARRAY_AGG` with `IN UNNEST` and Correlated `EXISTS` Subquery Anti-Patterns

1. **Never pass node sets across `NEXT` via `ARRAY_AGG(n.id)` +
   `WHERE n.id IN UNNEST(ids)`**: Aggregating IDs into an array and unnesting
   them in the next stage forces a full table scan with per-row `ArrayUnnest`.
   Pass the bound node variable directly
   (`RETURN DISTINCT n NEXT MATCH (n:Label)...`).
2. **Decorrelate `EXISTS { MATCH ... }` subqueries via `OPTIONAL MATCH`**:
   Correlated `EXISTS` / `NOT EXISTS` subqueries inside `WHERE` (especially
   inside `OR` disjunctions or after `OPTIONAL MATCH`) often execute row-by-row
   via `CrossApply`. Note that a subquery cannot redeclare an outer graph
   variable (`NOT EXISTS { MATCH (a)-[:Transfers]->(b) }` fails with
   `redefining graph element variables in a subquery is not allowed`), and the
   accepted form `NOT EXISTS { MATCH (a2)-[:Transfers]->(b) WHERE a2 = a }` runs
   as an unpushed correlated `Anti-Semi Apply` that re-scans its node table for
   every outer row. Rewrite `NOT EXISTS` directly into
   `OPTIONAL MATCH (a)-[:Transfers]->(b) FILTER b IS NULL` (no `NEXT` needed
   unless following an aggregation like `GROUP BY`), which compiles into a
   set-based hash anti-semi join. For positive `EXISTS`, use `MATCH` and
   deduplicate with `FILTER IS_FIRST(1) OVER (PARTITION BY ...)` or `DISTINCT`
   if multiple edges can match per outer row.

---

## GQL Semantic & Syntax Guardrails

All GQL query rewrites must preserve these syntax and semantic invariants:

- **`WHERE` vs. `FILTER` with `OPTIONAL MATCH`**: Place predicates on optional
  pattern variables inside `OPTIONAL MATCH ... WHERE ...` (evaluated during the
  outer join). Placing them in a trailing `FILTER` clause filters the post-join
  table and silently turns the outer join into an inner join.
- **`ORDER BY` Placement**: In GQL, `ORDER BY` is ignored unless it is the final
  clause of the query (`RETURN ... ORDER BY score DESC LIMIT 10`) or is
  immediately followed by `LIMIT` (`ORDER BY score DESC LIMIT 10 RETURN ...`,
  not `ORDER BY score DESC RETURN ... LIMIT 10`).
- **Returning Graph Elements (Final Top-Level `RETURN` Only)**: Returning raw
  node, edge, or path variables (`RETURN n`) fails with
  `Returning expressions of type GRAPH_ELEMENT is not allowed` **only** when
  `RETURN` is the final statement of the top-level GQL query, because Spanner
  cannot return `GRAPH_ELEMENT` columns directly to the client. Intermediate
  `RETURN n NEXT ...` stages, `WITH n`, and subquery `RETURN`s (such as
  `e IN { MATCH -[selected_e:Transfers]-> ... RETURN selected_e }`) **do** allow
  raw graph elements—pass them directly and do **not** wrap intermediate
  variables in `TO_JSON(n)`. Project explicit properties (`RETURN n.id, n.name`)
  or `TO_JSON(n)` only in the final top-level `RETURN`.
- **Unique Output Column Names (`RETURN` and `WITH`)**: Every column in a
  `RETURN` or `WITH` statement needs a distinct name. `RETURN a.id, b.id` or
  `WITH a.id, b.id` fails with `Ambiguous name: id`; alias duplicates
  (`RETURN a.id AS src_id, b.id AS dst_id`).
- **Reserved Words as Labels**: `Order`, `Group`, and `Contains` (among other
  GQL/SQL keywords) must be escaped in backticks when used as labels or aliases
  (`` (o:`Order`) ``, `` -[:`Contains`]-> ``).
- **Carrying Values Across `NEXT`**: A column produced by a previous statement
  can be referenced only in the outermost `WHERE` of the next `MATCH`: write
  `MATCH (dst:Part) WHERE dst.part_id = target_part_id`, not
  `MATCH (dst:Part {part_id: target_part_id})`.

---

## Hint Selection and Guardrails

Use hints only after verifying with `--query-mode=PROFILE` that the default
optimizer plan is suboptimal. Full syntax and operator diagnostics are in
[references/profile-and-hints-guide.md](references/profile-and-hints-guide.md).

**Hint placement (verified on Spanner)**: element hints go *first* inside the
node or edge pattern (`(@{FORCE_INDEX=Idx} n:Label {...})`,
`-[@{FORCE_INDEX=Idx} e:Label]->`); `JOIN_METHOD` is a traversal hint placed
*between* elements (`-[e:Label]-> @{JOIN_METHOD=HASH_JOIN} (m:Label)`) or at
statement level before `GRAPH`. Writing a hint after the label
(`-[e:Label @{...}]->`) is a syntax error.

| Workload Pattern | Recommended Hint Strategy | Why |
| :--- | :--- | :--- |
| **Selective Anchor Traversal** (1 or a few starting nodes, 1–3 hops) | Default optimizer plan (`Distributed Cross Apply`), or element hint `(@{FORCE_INDEX=IdxName} n:Label ...)` if the wrong index is chosen | `Apply Join` performs targeted B-tree point seeks (`SeekableKeySize >= 1`) proportional only to the anchor fan-out. |
| **Unselective / Bulk Graph Traversal** (scanning a large fraction of nodes/edges across the graph) | Statement hint `@{JOIN_METHOD=HASH_JOIN}` before `GRAPH`, or traversal hint `-[e:Label]-> @{JOIN_METHOD=HASH_JOIN} (m:Label)`, only if `PROFILE` shows a `Distributed Cross Apply` probing millions of rows | Replaces millions of random per-row RPC index probes (`Distributed Cross Apply`) with sequential table/index scans and in-memory hash probes. The optimizer often picks a `Hash Join` for bulk scans automatically (where forcing `APPLY_JOIN` is slower). |
| **Selective Reverse Traversal (`<-[]-`)** | `<-[@{FORCE_INDEX=EdgeReverseIdx} e:EdgeLabel]-` (optionally with traversal hint `@{JOIN_METHOD=APPLY_JOIN}`) | Forces Spanner to seek the reverse secondary index on `(dest_id, src_id)` rather than scanning the forward edge table. |
| **Converging Linear / Quantified Paths** | `-[e:Edge]->{1,3}@{factorized_mode=factorize_left}(dst:Node)` (return per-path or destination columns, not `COUNT(*)`) | Deduplicates converging paths by destination key before looking up `dst` node properties. Pays off only at high convergence ratios; verify with `PROFILE`. |
| **Multi-Arm Star Pattern** (when flat cross-product output is needed) | `MATCH (a)-[e1]->(n1), @{factorized_mode=factorize_both}(a)-[e2]->(n2)` (return per-arm columns, not `COUNT(*)`) | Evaluates conditionally independent arms once ($M + N$) instead of via nested loops ($M \times N$). Prefer Rule 2 remedy 1 unless flat cross-product rows are required and `PROFILE` shows a gain. |

### Critical Hint Guardrails (When NOT to Use Hints)

1. **Do NOT force `@{JOIN_METHOD=HASH_JOIN}` on quantified variable-length path
   patterns (`-[e:Edge]->{1,3}`)** or when foreign-key / schema optimizations
   allow Spanner to eliminate intermediate node table joins. Overriding the join
   method inside quantified paths forces full-table build/probe scans at every
   recursion depth instead of expanding only the active frontier, which is much
   slower on anchored `{1,3}` traversals.
2. **Do NOT force `@{JOIN_METHOD=HASH_JOIN}` on highly selective point lookups**
   without an anchoring filter on the build side; a `Hash Join` without a
   selective build-side filter may scan the entire target table.
3. **Always verify with `PROFILE`**: If a hint increases `Total elapsed time` or
   `Rows scanned`, remove it immediately.

---

## Reference Guides

- **[GQL Rewrite Patterns](references/gql-rewrite-patterns.md)**: Detailed
  before-and-after ISO GQL query transformations for anchor ordering, chained
  `NEXT` early aggregation, label enforcement across `NEXT`, folded-edge
  projection, `IS_FIRST` and hub-exclusion super-node bounding, `OPTIONAL MATCH`
  subquery decorrelation, and quantified-path lightweight recursion and late
  materialization.
- **[PROFILE and Hints Guide](references/profile-and-hints-guide.md)**: How to
  read `gcloud spanner databases execute-sql --query-mode=PROFILE` output
  (`Distributed Cross Apply`, `Hash Join`, `SeekableKeySize`,
  `Residual Condition`) and exact syntax for statement-level, node-level, and
  edge-level hints.
- **Official Spanner Graph Query Tuning Documentation**:
  [Spanner Graph query tuning best practices](https://docs.cloud.google.com/spanner/docs/graph/best-practices-tuning-queries.md.txt)

If you need product information that's not found in these references, use the
`search_documents` tool of the Developer Knowledge MCP server.
