# BigQuery Graph GQL Syntax Reference

This reference covers the Graph Query Language (GQL) supported by BigQuery.

## Direct GQL Execution (Recommended)
GQL queries should be executed directly as top-level statements in BigQuery. This is the modern and preferred way to interact with graphs.

### Visualization Syntax
To leverage the **Graph tab** in BigQuery Studio, you must return graph entities using `TO_JSON`.

```sql
GRAPH project.dataset.graph_name
MATCH (n)-[e]->(m)
RETURN TO_JSON(n) AS node_a, TO_JSON(e) AS edge, TO_JSON(m) AS node_b
LIMIT 100
```

## GQL Core Clauses

### MATCH
Used to specify the graph pattern to search for.
- **Node pattern**: `(variable:Label {property: value})`
- **Edge pattern**: `-[variable:Label]->`, `<-[variable:Label]-`, `-[variable:Label]-`
- **Relationship**: `(n1)-[e]->(n2)`

### WHERE
Filters nodes, edges, or paths.
- `WHERE n.age > 21`
- `WHERE e.weight >= 0.5`

### RETURN
Specifies the elements to return in the result set.
- `RETURN n.name AS name, e.type AS type` (Standard tabular result)
- `RETURN TO_JSON(n)` (Required for Graph visualization tab)

### NEXT
Used to chain multiple `MATCH` patterns.

## Advanced Patterns

### Variable-Length Paths (Quantified Path Patterns)
BigQuery GQL uses **Standard GQL Quantified Path Patterns**. Variable-length paths are defined by wrapping a pattern in parentheses followed by a quantifier like `{min, max}`.

**Note**: In quantified path patterns, variables within the parentheses (like `e` and `m` below) become **ARRAYS** of nodes/edges.

- **Length 1 to 3**: `MATCH (n1) ( -[e]-> (n2) ){1,3}`
- **Fixed length 3**: `MATCH (n1) ( -[e]-> (n2) ){3}`
- **Unbounded (at least 1)**: `MATCH (n1) ( -[e]-> (n2) )+`

### Filtering and Returning Path Arrays
When using quantified paths, use array functions to filter or access specific hops:

```sql
GRAPH project.dataset.graph
MATCH (src:Entity) ( -[e]-> (dest:Entity) ){1,5}
WHERE src.name = 'START_NODE' 
  AND dest[OFFSET(ARRAY_LENGTH(dest)-1)].type = 'TABLE' -- Filter last node
RETURN TO_JSON(src), TO_JSON(e), TO_JSON(dest)
```

### Multiple Matches
```gql
GRAPH project.dataset.graph
MATCH (a)-[:Knows]->(b)
MATCH (b)-[:Knows]->(c)
RETURN a.name, c.name
```

## Example Queries

### Finding Mutual Friends (Visualization Ready)
```sql
GRAPH `my_project.my_dataset.social_graph`
MATCH (u1:User)-[e1:Friend]->(common:User)<-[e2:Friend]-(u2:User)
WHERE u1.user_id = 1 AND u2.user_id = 2
RETURN TO_JSON(u1), TO_JSON(e1), TO_JSON(common), TO_JSON(e2), TO_JSON(u2)
```

## Integration with SQL (GRAPH_TABLE)
**Note**: Only use `GRAPH_TABLE` if you need to JOIN graph results with standard BigQuery tables. For exploration and visualization, use the `GRAPH` statement directly.

```sql
SELECT * FROM GRAPH_TABLE(
  `project.dataset.graph_name`
  MATCH (n)-[e]->(m)
  RETURN n.name AS source, m.name AS target
  COLUMNS(source, target)
)
```
