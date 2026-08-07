# Managed Service for Apache Spark LQL queries

## Example queries

### Dataproc Apache Hadoop logs

**Variables to replace:** None

```lql
resource.type="cloud_dataproc_cluster" AND
jsonPayload.class:"org.apache.hadoop.mapreduce"
```
