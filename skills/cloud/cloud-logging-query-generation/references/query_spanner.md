# Spanner LQL queries

## Example queries

### Cloud Spanner logs for a specific Spanner instance

**Variables to replace:** `<SPANNER_INSTANCE>`

```lql
resource.type="spanner_instance" AND
resource.labels.instance_id="<SPANNER_INSTANCE>"
```
