---
name: bigquery-graph-basics
description: Use for creating and managing BigQuery graphs, writing Graph Query Language (GQL) queries, optimizing graph schemas, and visualizing graph results in BigQuery Studio or external tools.
---

# BigQuery Graph Basics

BigQuery Graph lets you use the analytical power of BigQuery to perform graph analysis on a large scale. When you model your data as a graph with nodes and edges, you can use Graph Query Language (GQL) to find complex, hidden relationships between data points that would be challenging to find using SQL.

You can create node and edge tables directly from tables or views that store entities and relationships between entities. You don't need to modify your existing workflows or replicate your data to use it in graph queries.

BigQuery Graph supports a graph query interface compatible with the ISO GQL standard and the ISO Property Graph Queries (SQL/PGQ) standard. This provides you with interoperability between relational and graph models by combining well-established SQL capabilities with the expressiveness of graph pattern matching.

## Core Workflows

### 1. Creating a Property Graph
When asked to set up a graph, follow these steps:
- Identify node and edge tables.
- Define keys and relationships.
- Use `CREATE PROPERTY GRAPH`.
- **Reference**: See [schema_design.md](references/schema_design.md) for DDL patterns and best practices.

### 2. Querying with GQL
When asked to perform graph queries:
- **Direct GQL Syntax (Preferred)**: Use the top-level `GRAPH` statement.
- Formulate patterns using ASCII-art syntax `(n)-[e]->(m)`.
- Use `MATCH`, `WHERE`, and `RETURN` clauses.
- **Reference**: See [gql_syntax.md](references/gql_syntax.md) for detailed syntax and example queries.

### 3. Optimization and Best Practices
- Advise on clustering underlying tables by keys.
- Recommend bounding variable-length paths (e.g., `*1..5`) to avoid performance issues.
- **Reference**: See [schema_design.md](references/schema_design.md) for performance tips.

### 4. Visualizing Results
- **BigQuery Studio**: Results MUST be returned using `TO_JSON` for the Graph tab to function correctly.
- Provide Python snippets for `pyvis` or `networkx` for custom visualizations.
- **Reference**: See [visualization_guide.md](references/visualization_guide.md) for tools and interactive examples.

## Quick Start Examples

### Define a Social Graph
```sql
CREATE PROPERTY GRAPH `my_dataset.social_graph`
NODE TABLES ( `my_dataset.users` KEY (uid) LABEL User )
EDGE TABLES ( `my_dataset.follows` SOURCE KEY (follower) REFERENCES users (uid) DESTINATION KEY (followed) REFERENCES users (uid) LABEL Follows );
```

### Direct GQL Query for Visualization
```sql
GRAPH `my_dataset.social_graph`
MATCH (n)-[e]->(m)
RETURN TO_JSON(n) as source, TO_JSON(e) as edge, TO_JSON(m) as target
LIMIT 100
```

## Important Notes
- Always remind the user that graphs and tables must be in the same region.
- Property graphs are logical views; updates to tables are immediately visible.
- Avoid `GRAPH_TABLE` unless specifically needing to JOIN graph results with standard SQL tables.
