# Dataflow LQL queries

## Example queries

### Warnings or errors from Dataflow workers

**Variables to replace:** None

```lql
resource.type="dataflow_step"
log_id("dataflow.googleapis.com/worker")
severity >= WARNING
```
