# Cloud Tasks LQL queries

## Example queries

### Cloud Tasks queue logs

**Variables to replace:** `<QUEUE_ID>`

```lql
resource.type="cloud_tasks_queue" AND
resource.labels.queue_id="<QUEUE_ID>"
```
