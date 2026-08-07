---
name: cloud-monitoring-metric-selection
metadata:
  category: CloudObservabilityAndMonitoring
description: >-
  Retrieve, query, and identify relevant Google Cloud Monitoring metric
  descriptors for a GCP service or resource (such as Compute Engine, Spanner,
  BigQuery, Cloud Run, Cloud SQL, Pub/Sub, Cloud Storage, etc.). Use when asked
  to find, list, search, or discover GCP metric types, names, kind/value
  schemas, or descriptors.
---

# Metric Selection (Service Query & Local Keyword Filtering)

Use this skill to identify the most relevant Google Cloud Monitoring metric
descriptors. It queries all metric descriptors for a target service from the API
and filters them locally inside the agent's context using keyword matching.

## CRITICAL RULES

*   **Always Query Live APIs**: You MUST always retrieve the most up-to-date
    metric descriptors dynamically by calling the `list_metric_descriptors` MCP
    tool.
*   **Mandatory Project ID and Resource Parameter Clarification**: BEFORE
    calling any API tools (such as `list_metric_descriptors`), you MUST ensure
    the GCP Project ID is provided in the prompt, URI, or environment context.
    If the Project ID cannot be resolved, you MUST ask the user to clarify or
    provide it BEFORE executing API queries. Do NOT run API queries against
    unconfirmed default or placeholder project names (such as `mock-project`,
    `my-project-id`, `unused`, or `YOUR_PROJECT_ID`).
*   **Fallback Reporting**: If API calls fail and fallback sources (such as
    public docs) are used, you MUST state the error, the fallback source, and
    the risks of non-live data (such as potential staleness, missing custom
    metrics, or schema mismatches).

## Workflow

### Step 1: Verify & Auto-Configure MCP

1.  Check if any tool matching `list_metric_descriptors` (such as
    `google-cloud-monitoring:list_metric_descriptors`,
    `mcp_google-cloud-monitoring_list_metric_descriptors`, or a similar pattern)
    is available in your active toolset.
2.  **Verify via Unique URL**: To ensure you are calling the correct Google
    Cloud Monitoring tool, confirm that the underlying MCP server configuration
    points to: **`https://monitoring.googleapis.com/mcp`**.
3.  If the tool is **missing**:

    *   Locate the MCP configuration file for the user's environment. Check
        common paths:
        -   `~/.gemini/config/mcp_config.json`
        -   `~/.codeium/windsurf/mcp_config.json`
        -   `cline_mcp_settings.json`
        -   `claude_desktop_config.json`
    *   Directly update/merge the configuration file with the following server
        configuration. **CRITICAL**: Merge the JSON object to preserve any
        existing MCP servers in `mcpServers`. Do not overwrite the file.

        ```json
        "google-cloud-monitoring": {
          "url": "https://monitoring.googleapis.com/mcp",
          "authProviderType": "google_credentials",
          "enabledTools": [
            "list_metric_descriptors"
          ]
        }
        ```

    *   Print a clear message notifying the user that the
        `google-cloud-monitoring` MCP server has been configured, and request
        them to restart or start a new chat session to refresh tools. Stop
        calling further tools and end the turn.

### Step 2: Analyze Request & Extract Keywords

1.  **Resolve Project ID and Identifiers**: Check for the GCP Project ID and
    resource identifiers in the prompt, resource URIs, or environment context.
    According to the CRITICAL RULES above, do NOT use placeholder project names.

2.  **Identify Service Prefix**: Map target GCP services to their standard
    prefix (such as `compute`, `spanner`, `bigquery`, `storage`).

3.  **Extract Metric Concepts**: Extract metric keywords from user prompt (such
    as "CPU", "memory", "bytes scanned", "latency", "connections") and map to
    search substrings.

*Example Query Analysis:*

*   **User Prompt**: "Check Cloud Storage bucket write throughput and request
    count"
*   **Resource URI**:
    `//storage.googleapis.com/projects/my-project/buckets/my-bucket`
*   **Service Prefix**: `storage` (mapped to `storage.googleapis.com`)
*   **Metric Keywords**: `write`, `throughput`, `request`, `count`
*   **Mapped Substrings**: `write`, `throughput`, `request_count`, `count`

### Step 3: Query Metric Descriptors via list_metric_descriptors Tool

Query all metric descriptors for each identified service prefix using the
`list_metric_descriptors` MCP tool (using `pageSize: 200`). Because Google Cloud
Monitoring filters do not allow combining multiple `metric.type` restrictions
with `OR`, you must **initiate a separate query for each identified service
prefix** (either sequentially or in parallel).

If any response includes a `nextPageToken`, you MUST make consecutive follow-up
calls passing `pageToken` until all remaining descriptors for that prefix are
retrieved before filtering.

*Filter Pattern Construction:* Map the target service domain to its appropriate
prefix style:

1.  **Standard Google Cloud Services**:
    `starts_with("<service_prefix>.googleapis.com/")` (such as
    `bigquery.googleapis.com/`, `redis.googleapis.com/`).
2.  **Ops Agent (Guest OS)**: `starts_with("agent.googleapis.com/")` (for guest
    OS memory/disk metrics).
3.  **Kubernetes / GKE Native**: `starts_with("kubernetes.io/")`
4.  **Istio Service Mesh**: `starts_with("istio.io/")`
5.  **Knative Serving / Autoscaler**: `starts_with("knative.dev/")`
6.  **Custom / External Metrics**: Use `starts_with("custom.googleapis.com/")`
    or `starts_with("external.googleapis.com/")`.

*Example Tool Call Payload:* If both Spanner and Compute Engine are targeted in
the request, execute these two tool calls:

1.  Spanner query:

```json
{
  "name": "projects/my-project-id",
  "filter": "metric.type = starts_with(\"spanner.googleapis.com/\")",
  "pageSize": 200
}
```

1.  Compute Engine query:

```json
{
  "name": "projects/my-project-id",
  "filter": "metric.type = starts_with(\"compute.googleapis.com/\")",
  "pageSize": 200
}
```

Call the `list_metric_descriptors` tool with these payloads.

### Step 4: Local Filtering & Fallback Protocol

Aggregate all descriptors returned from Step 3, and filter them locally inside
your LLM context:

1.  **Keyword Filtering**: Filter the list by matching your target metric
    keywords (such as "cpu", "latency") against the `type`, `displayName`, and
    `description` fields of the descriptors.
2.  **Resource Alignment**: Check if the metric contains labels matching the
    target resource granularity (such as checking for a `database` label if
    targeting a database resource). Do not attempt to dynamically match resource
    type strings directly, as Google Cloud Monitoring resource mappings (like
    Spanner databases mapping to `spanner_instance`) can be counter-intuitive.

#### Troubleshooting & API Fallbacks

If any tool call fails, times out, or returns empty results, use these
strategies:

*   **Case A: API Syntax Error**: Examine the error message, correct the filter
    syntax, and retry.
*   **Case B: Timeout / Rate Limits**: Retry the call once with a smaller page
    size (such as `pageSize: 20`).
*   **Case C: Unrecoverable Failure / Empty List**:
    1.  Verify if the target service is enabled in the project.
    2.  Search Google Cloud public documentation to verify standard metrics for
        the service.

### Step 5: Output Selected Metrics

For each service domain, return only the 5-15 key metrics directly relevant to
the user's intent.

You MUST report the selected metrics in clean Markdown tables, grouped by
service (that is, one table per service prefix). The table MUST include the
following columns: "Metric Type", "Display Name", "Description", "Metric Kind",
"Value Type", "Unit", and "Monitored Resource Types". Map the fields from the
Google Cloud Monitoring `list_metric_descriptors` tool call response objects
directly to the table columns:

*   **Metric Type**: Map to the `type` field (for example,
    `spanner.googleapis.com/instance/cpu/utilization`).
*   **Display Name**: Map to the `displayName` field.
*   **Description**: Map to the `description` field.
*   **Metric Kind**: Map to the `metricKind` field (for example, `GAUGE`,
    `DELTA`, `CUMULATIVE`).
*   **Value Type**: Map to the `valueType` field (for example, `INT64`,
    `DOUBLE`, `DISTRIBUTION`, `BOOL`).
*   **Unit**: Map to the `unit` field (for example, `1`, `By`, `s`, `ms`).
*   **Monitored Resource Types**: Map to the `monitoredResourceTypes` list field
    (for example, `["spanner_instance"]`).

*Example Output Table:*

Metric Type                                       | Display Name             | Description                                 | Metric Kind | Value Type | Unit | Monitored Resource Types
:------------------------------------------------ | :----------------------- | :------------------------------------------ | :---------- | :--------- | :--- | :-----------------------
`spanner.googleapis.com/instance/cpu/utilization` | Instance CPU Utilization | Fraction of allocated CPU currently in use. | GAUGE       | DOUBLE     | 1    | `["spanner_instance"]`

## Reference Documentation & Links

*   **Google Cloud Monitoring Metric List**:
    [GCP Metrics Documentation](https://cloud.google.com/monitoring/api/metrics_gcp)
*   **MetricDescriptor MCP Tool Reference**:
    [MCP Tools Reference: monitoring.googleapis.com](https://docs.cloud.google.com/monitoring/api/ref_v3_mcp/mcp/tools_list/list_metric_descriptors)
*   **Monitoring Filter Syntax Guide**:
    [Monitoring Filters](https://cloud.google.com/monitoring/api/v3/filters)
