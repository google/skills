# BigQuery Graph Schema Design Guide

This guide covers the creation and optimization of property graphs in BigQuery.

## Creating a Property Graph (DDL)

The `CREATE PROPERTY GRAPH` statement defines the logical graph over existing tables.

```sql
CREATE PROPERTY GRAPH `project.dataset.graph_name`
NODE TABLES (
  `project.dataset.nodes_table`
    KEY (id_column)
    LABEL MyLabel
    PROPERTIES (col1, col2) -- Optional: list specific columns or use PROPERTIES ALL
)
EDGE TABLES (
  `project.dataset.edges_table`
    KEY (edge_id)
    SOURCE KEY (from_id) REFERENCES nodes_table (id_column)
    DESTINATION KEY (to_id) REFERENCES nodes_table (id_column)
    LABEL MyRelationship
    PROPERTIES ALL
);
```

## Schema Best Practices

### 1. Data Modeling
- **Entities as Nodes**: Any object with a unique identity should be a node.
- **Relationships as Edges**: Any interaction or connection between entities should be an edge.
- **Properties vs. Edges**: Use properties for metadata (e.g., `user.signup_date`). Use edges for structural connections (e.g., `user -[Purchased]-> product`).

### 2. Performance Optimization
- **Clustering**: Cluster the underlying node and edge tables by their keys (IDs, Source IDs, Destination IDs). This significantly improves the performance of `GRAPH_TABLE` traversals.
- **Partitioning**: If your data has a temporal component (e.g., transaction logs), partition underlying tables by date.
- **Key Uniqueness**: Ensure keys are unique and non-null in the underlying tables. BigQuery Graph assumes integrity; violations can lead to incorrect results or query failures.

### 3. Logical Structure
- **Labels**: Use descriptive labels (e.g., `Customer`, `Order`, `LineItem`). A table can be mapped to multiple labels if needed.
- **Reusability**: You can define multiple graphs over the same set of underlying tables for different use cases.

## Limitations
- Graphs and underlying tables must reside in the same region.
- Property graphs are logical views; they do not store a separate copy of the data.
