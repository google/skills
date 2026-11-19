# Spanner ISO GQL Cheat Sheet

## 1. Basic Query Structure

Every Spanner Graph query begins with `GRAPH {graph_name}` followed by one or
more `MATCH`, `FILTER`/`WHERE`, `LET`, `RETURN`, and optional `NEXT` clauses:

```sql
GRAPH ECommerceGraph
MATCH (c:Customer {country: 'US'})-[p:PLACED]->(o:`Order`)
WHERE o.total_usd > 100
RETURN c.customer_id, c.name, o.order_id, o.total_usd
ORDER BY o.total_usd DESC
LIMIT 20;
```

## 2. Node and Edge Pattern Syntax

- **Node pattern**: `(alias:Label {prop: value})`
- **Directed outgoing edge**: `-[edge_alias:EDGE_LABEL]->`
- **Directed incoming edge**: `<-[edge_alias:EDGE_LABEL]-`
- **Undirected / any-direction match**: `-[edge_alias:EDGE_LABEL]-`
  (`<-[e:LABEL]->` is not valid Spanner GQL syntax)
- **Label disjunction (OR)**: `(n:Customer|Vendor)` or
  `-[e:TRANSFERRED_TO|PAID]->`
- **Escaping reserved words**: Wrap labels that collide with SQL/GQL reserved
  keywords in backticks (for example, `` (o:`Order`) ``, `` (g:`Group`) ``).

## 3. Variable-Length Quantified Path Patterns (`{m, n}`)

To traverse between `m` and `n` hops along an edge pattern, append `{m, n}` to
the edge or parenthesized path pattern. In Spanner Graph, the upper bound `n`
must be a finite integer:

```sql
-- 1 to 4 hops along a reporting hierarchy
GRAPH EnterpriseOrgGraph
MATCH (emp:Employee)-[r:REPORTS_TO]->{1, 4}(mgr:Employee)
WHERE mgr.job_title = 'VP of Engineering'
RETURN emp.full_name AS employee_name, mgr.full_name AS manager_name, ARRAY_LENGTH(r) AS reporting_depth;
```

- Inside a quantified path `{m, n}`, the edge variable `r` is bound as a **group
  variable (`ARRAY` of edges)** across the matched path. Use `ARRAY_LENGTH(r)`
  to inspect hop count.
- Output column names must be unique: `RETURN emp.full_name, mgr.full_name`
  fails with `Ambiguous name: full_name`, so alias duplicates.

## 4. Chaining Multi-Stage Queries with `NEXT`

Use `NEXT` to pipe the output columns/variables of one GQL query stage into the
next stage (similar to a pipe operator), allowing per-stage aggregation and
filtering. `RETURN` must be the last statement of a stage, so filter on
aggregated columns at the start of the next stage:

```sql
GRAPH ECommerceGraph
MATCH (c:Customer)-[:PLACED]->(o:`Order`)
RETURN c, COUNT(o) AS order_count, SUM(o.total_usd) AS lifetime_spend
GROUP BY c

NEXT

FILTER order_count >= 5
MATCH (c:Customer)-[r:REVIEWED]->(p:Product)
WHERE r.rating >= 4
RETURN c.name, lifetime_spend, COUNT(p) AS high_rated_reviews
GROUP BY c.name, lifetime_spend
ORDER BY lifetime_spend DESC;
```

## 5. Inspecting Labels and Properties

- `LABELS(element_var)`: Returns an `ARRAY<STRING>` of labels attached to a node
  or edge variable.
- `PROPERTY_NAMES(element_var)`: Returns an `ARRAY<STRING>` of property names
  defined on the element.
- `TO_JSON(element_var)`: Serializes a graph node, edge, or path variable to
  `JSON`.

## 6. Combining GQL with SQL (`GRAPH_TABLE`)

To join Spanner Graph traversal results with standard SQL tables or subqueries,
wrap the GQL query inside `GRAPH_TABLE`:

```sql
SELECT gt.customer_id, gt.recommended_product, inv.stock_count
FROM GRAPH_TABLE(
  ECommerceGraph
  MATCH (c:Customer {customer_id: 42})-[:PLACED]->(:`Order`)-[:INCLUDES_ITEM]->(p:Product)
  RETURN c.customer_id, p.product_id, p.title AS recommended_product
) AS gt
JOIN Inventory AS inv ON gt.product_id = inv.product_id
WHERE inv.stock_count > 0;
```
