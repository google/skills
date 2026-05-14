# BigQuery Graph Visualization Guide

Visualizing graphs helps in identifying clusters, influencers, and hidden patterns.

## Integrated Visualization: BigQuery Studio

BigQuery Studio provides a built-in graph explorer. To leverage the interactive **Graph** tab, results must be returned as JSON objects using the `TO_JSON` function within a direct `GRAPH` statement.

### Optimized Visualization Query
To see nodes and edges correctly in the Graph tab, use the following syntax:

```sql
GRAPH `project.dataset.graph_name`
MATCH (n)-[e]->(m)
RETURN TO_JSON(n) AS node_a, TO_JSON(e) AS edge, TO_JSON(m) AS node_b
LIMIT 100
```

1. **Run the query**: Execute the SQL above in BigQuery Studio.
2. **Switch to Graph View**: In the results pane, click the **Graph** tab.
3. **Explore**:
   - **Nodes**: Hover to see properties (from the JSON metadata).
   - **Edges**: Visualized as directed links.
   - **Layout**: Use the UI controls to change the layout (Force-directed, Circular, etc.).

## Why use TO_JSON?
BigQuery's Graph tab expects the full graph element structure to enable features like:
- **Property Inspection**: Seeing all metadata associated with a node/edge.
- **Label Recognition**: Automatic coloring based on labels.
- **Connectivity**: Using internal identifiers to maintain the graph structure in the canvas.

## External Visualization Tools
...
```

### 1. Looker / Looker Studio
- Use `GRAPH_TABLE` queries as data sources.
- While Looker is primarily tabular, you can use custom visualizations (D3.js, Network charts) to render the graph data.

### 2. Python Notebooks (Colab Enterprise / Vertex AI)
Use Python libraries for interactive visualization:
- **Pyvis**: Great for interactive, draggable graphs.
- **NetworkX**: For graph analysis and static plotting (with Matplotlib).
- **Graphistry**: For high-performance visualization of large graphs.

**Example Python Snippet:**
```python
from google.cloud import bigquery
import networkx as nx
from pyvis.network import Network

client = bigquery.Client()
query = """
SELECT source_node, target_node, weight
FROM GRAPH_TABLE(...)
"""
df = client.query(query).to_dataframe()

G = nx.from_pandas_edgelist(df, 'source_node', 'target_node', ['weight'])
net = Network(notebook=True)
net.from_nx(G)
net.show("graph.html")
```

## Best Practices for Visualization
- **Sub-sampling**: Avoid visualizing millions of nodes at once. Use GQL filters to isolate a specific neighborhood or community.
- **Sizing/Coloring**: Use properties (e.g., `amount`, `weight`) to scale node size or color edges to make patterns obvious.
- **Layouts**: Use force-directed layouts for general exploration and hierarchical layouts for tree-like structures (e.g., org charts).
