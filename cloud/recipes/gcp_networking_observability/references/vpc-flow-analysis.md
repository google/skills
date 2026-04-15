# VPC Flow Analysis Reference

Use VPC Flow Logs to analyze traffic patterns, volume, and latency.

## 🤖 Agent / Gemini CLI Instructions (MCP)

Agents should use [CloudLoggingMCP](mcp-usage.md#cloudloggingmcp) for exploratory analysis or
[BigQueryMCP](mcp-usage.md#bigquerymcp) for high-volume trends. Fallback to the
CLI if the MCP tools are not available.

### 1. View Logs ([CloudLoggingMCP](mcp-usage.md#cloudloggingmcp))

**Tool**: `list_log_entries`

**Filter**:
ALWAYS search for both VPC flow log sources:
```text
(logName:"projects/{project_id}/logs/compute.googleapis.com%2Fvpc_flows" OR
 logName:"projects/{project_id}/logs/networkmanagement.googleapis.com%2Fvpc_flows")
resource.type="gce_subnetwork"
```

### 2. Aggregate Trends ([BigQueryMCP](mcp-usage.md#bigquerymcp))

**Tool**: `query_sql`

**SQL Pattern**:
```sql
SELECT
  timestamp,
  JSON_VALUE(jsonPayload.connection.src_ip) AS src_ip,
  JSON_VALUE(jsonPayload.connection.dest_ip) AS dest_ip,
  CAST(JSON_VALUE(jsonPayload.bytes_sent) AS INT64) AS bytes_sent
FROM `{project_id}.{dataset_id}._AllLogs`
WHERE
  log_name IN (
    'projects/{project_id}/logs/compute.googleapis.com%2Fvpc_flows',
    'projects/{project_id}/logs/networkmanagement.googleapis.com%2Fvpc_flows'
  )
  AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
ORDER BY timestamp DESC
LIMIT 10
```

### 3. CLI Fallback

If MCP tools are unavailable, use the following `gcloud` and `bq` commands:

**View Logs (gcloud)**

```bash
gcloud logging read '(logName:"projects/{project_id}/logs/compute.googleapis.com%2Fvpc_flows" OR logName:"projects/{project_id}/logs/networkmanagement.googleapis.com%2Fvpc_flows") AND resource.type="gce_subnetwork"' --project {project_id} --limit 10 --format json
```

**Aggregate Trends (bq)**

```bash
bq query --use_legacy_sql=false --project_id {project_id} '
SELECT
  timestamp,
  JSON_VALUE(jsonPayload.connection.src_ip) AS src_ip,
  JSON_VALUE(jsonPayload.connection.dest_ip) AS dest_ip,
  CAST(JSON_VALUE(jsonPayload.bytes_sent) AS INT64) AS bytes_sent
FROM `{project_id}.{dataset_id}._AllLogs`
WHERE
  log_name IN (
    "projects/{project_id}/logs/compute.googleapis.com%2Fvpc_flows",
    "projects/{project_id}/logs/networkmanagement.googleapis.com%2Fvpc_flows"
  )
  AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
ORDER BY timestamp DESC
LIMIT 10
'
```

### Flow Analyzer (Visual Analysis)

For visual traffic analysis and identifying "top talkers," use the [Flow Analyzer](https://console.cloud.google.com/net-intelligence/flow-analyzer). It allows you to:

-   Visualize traffic flows between regions, VPCs, and instances.
-   Filter by source/destination dimensions.
-   Identify high-bandwidth or high-latency connections.

### Generic BigQuery Guidelines

-   **Schema Verification**: Before executing a BigQuery query, if you are uncertain of the casing (e.g., `jsonPayload` vs `json_payload`), you MUST run `bq show --schema <source>`.
-   **Latency Aggregation**: The primary field for RTT analysis in VPC Flow logs
    is `jsonPayload.round_trip_time.median_msec`. Ensure you filter by
    `reporter` (`SRC` or `DEST`) to avoid double-counting traffic volume.

## Key Fields

-   **src_ip / dest_ip**: Source and destination IP addresses.
-   **bytes_sent / packets_sent**: Volume of traffic.
-   **rtt_msec**: round_trip_time.median_msec, if available. The primary field
    for RTT aggregation in BigQuery.
-   **reporter**: Usually `src` or `dest` indicating which side logged the flow.
