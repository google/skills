# Firewall Rule Logging Analysis Reference

Use firewall logs (`compute.googleapis.com/firewall`) to verify if traffic is
allowed or denied.

## 🤖 Agent / Gemini CLI Instructions (MCP)

You should [CloudLoggingMCP](mcp-usage.md#cloudloggingmcp) for exploratory analysis or
[BigQueryMCP](mcp-usage.md#bigquerymcp) for high-volume trends. Fallback to the
CLI if the MCP tools are not available.

### 1. View Logs ([CloudLoggingMCP](mcp-usage.md#cloudloggingmcp))

**Tool**: `list_log_entries`

**Filter**:
```text
resource.type="gce_subnetwork"
logName="projects/{project_id}/logs/compute.googleapis.com%2Ffirewall"
```

Filter for denied packets:
```text
jsonPayload.rule_details.action="DENY"
```

### 2. Aggregate Trends ([BigQueryMCP](mcp-usage.md#bigquerymcp))

**Tool**: `query_sql`

**SQL Pattern**:
```sql
SELECT
  JSON_VALUE(jsonPayload.rule_details.reference) AS rule_name,
  COUNT(*) AS block_count
FROM `{project_id}.{dataset_id}._AllLogs`
WHERE
  log_name LIKE '%firewall%'
  AND JSON_VALUE(jsonPayload.rule_details.action) = 'DENY'
GROUP BY 1
ORDER BY block_count DESC
LIMIT 10
```

### 3. CLI Fallback

If MCP tools are unavailable, use the following `gcloud` and `bq` commands:

**View Logs (gcloud)**

```bash
gcloud logging read 'resource.type="gce_subnetwork" AND logName="projects/{project_id}/logs/compute.googleapis.com%2Ffirewall"' --project {project_id} --limit 10 --format json
```

To filter for denied packets:

```bash
gcloud logging read 'resource.type="gce_subnetwork" AND logName="projects/{project_id}/logs/compute.googleapis.com%2Ffirewall" AND jsonPayload.rule_details.action="DENY"' --project {project_id} --limit 10 --format json
```

**Aggregate Trends (bq)**

```bash
bq query --use_legacy_sql=false --project_id {project_id} '
SELECT
  JSON_VALUE(jsonPayload.rule_details.reference) AS rule_name,
  COUNT(*) AS block_count
FROM `{project_id}.{dataset_id}._AllLogs`
WHERE
  log_name LIKE "%firewall%"
  AND JSON_VALUE(jsonPayload.rule_details.action) = "DENY"
GROUP BY 1
ORDER BY block_count DESC
LIMIT 10
'
```

## Key Fields

-   `jsonPayload.rule_details.action`: `ALLOW` or `DENY`.
-   `jsonPayload.rule_details.reference`: The firewall rule name (e.g., `default-deny-all`).
-   `jsonPayload.connection.src_ip` / `dest_ip`: The source and destination of the connection.

## Common Use Cases

-   **Identify Blocks**: Find which `DENY` rule is causing connection failures.
-   **Security Audit**: Detect unexpected traffic patterns.
