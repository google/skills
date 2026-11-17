---
name: cloud-trace-querying
metadata:
  version: "1.0.3"
  category: CloudObservabilityAndMonitoring
description: >-
  Query Cloud Trace spans, filter by latency thresholds or error status,
  correlate distributed traces with Cloud Logging, and diagnose latency bottlenecks
  across Google Cloud services. Use when investigating slow requests, analyzing trace
  hierarchies, or resolving latency regressions. Do NOT use for querying non-GCP
  telemetry or database query optimization outside Cloud Trace.
---

# Cloud Trace Querying Skill (`cloud-trace-querying`)

This skill equips the agent to interact with Cloud Trace by providing standard query patterns, diagnostic workflows for latency and errors, and tools to fetch and inspect trace hierarchies.

> [!IMPORTANT]
> **AUTONOMOUS TOOL EXECUTION MANDATE**:
> You MUST execute the tool scripts directly in bash to query telemetry.
> Do NOT just describe query strings or write Python scripts. Run the provided bash tools directly and report the exact results.

## Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read [Usage Attribution](references/attribution.md). For commands executed
directly in the terminal (never in generated scripts, Terraform, or user code),
prefix `gcloud` with
`CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:cloud-trace-querying)"`
and append `agent-skills/1.0 (skill:cloud-trace-querying)` to `User-Agent` headers.

## Prerequisites & Setup
1. **Google Cloud SDK**: Verify `gcloud` is installed ([Installation Guide](https://docs.cloud.google.com/sdk/docs/install-sdk)).
2. **Authentication**: Authenticate CLI and application default credentials:
   ```bash
   gcloud auth login && gcloud auth application-default login
   ```
3. **Project & Billing**: Identify the target `<PROJECT_ID>` (from the user's prompt or via `bash scripts/get_trace_project/run.sh`), ensure an active billing account is attached, and configure the project if not already set:
   ```bash
   gcloud config set project <PROJECT_ID>
   ```
4. **API Enablement**: Verify Cloud Trace and Cloud Logging APIs are enabled:
   ```bash
   gcloud services enable cloudtrace.googleapis.com logging.googleapis.com
   ```

## Quickstart Workflows

### 1. Identify Google Cloud Project ID
If the user specified a Google Cloud project ID in their prompt, use it.

If they did not, ALWAYS determine the Google Cloud project ID by running:

```bash
bash scripts/get_trace_project/run.sh
```

### 2. Search Traces (Latency & Errors)
To find traces matching specific criteria, such as a root span of `/v1/booking/book` with a duration of at least 1.5s:

```bash
bash scripts/search_traces/run.sh --filter 'root:/v1/booking/book latency:1.5s' --projects '<PROJECT_ID>'
```

*Note: `--filter` is required. To list traces without specific filtering, pass `--filter ''` or `--filter 'root:'`.*
*Filter syntax: The Cloud Trace API uses `latency:<duration>` (such as `latency:1.5s` for duration >= 1.5s), which corresponds to "Span duration" in Trace Explorer.*
*The script outputs JSON where each cluster's `examples` array contains sample trace objects with `trace_id`, `duration_seconds`, span count, and error status.*

### 3. Fetch Entire Trace Hierarchy
To view all spans and status codes/labels within a trace:

```bash
bash scripts/fetch_entire_trace/run.sh --trace-id '<TRACE_ID>' --project '<PROJECT_ID>'
```

### 4. Fetch Correlated Application Logs
To retrieve application log entries correlated with a trace ID:

```bash
bash scripts/fetch_related_logs/run.sh --trace-id '<TRACE_ID>' --trace-projects '<PROJECT_ID>'
```

*Application log entries are useful when inspecting stack traces, exception messages, and log events emitted during span execution. When diagnosing errors or service crashes, inspect the returned log entries for `severity: "ERROR"` to confirm root causes or uncover unhandled exceptions.*
*Note: `fetch_related_logs` queries the default log scope (`_Default`), searching across configured log views in the target project. An empty response can occur if: (1) no log entries match the criteria, (2) the caller lacks IAM permissions to view the matching entries, or (3) matching entries reside in log views outside the searched log scope.*

### 5. Fetch Specific Trace Span
To inspect attributes and metadata of a single span within a trace:

```bash
bash scripts/fetch_trace_span/run.sh --trace-id '<TRACE_ID>' --span-id '<SPAN_ID>' --project '<PROJECT_ID>'
```

### 6. Generate Cloud Console Deep Links
To generate direct Cloud Console URLs for browser inspection of traces or correlated logs:

```bash
bash scripts/generate_links/run.sh --trace-id '<TRACE_ID>' --project '<PROJECT_ID>' [--span-id '<SPAN_ID>']
```

### 7. Format Output
- **Terminal / CLI**: Render span trees as indented ASCII timelines using `|--`.
- **UI Presentation**: Render as A2UI JSON graph structures when requested for UI.

### 8. Upstream Service Error Handling
If the Cloud Trace API or Cloud Logging API returns an upstream HTTP service error (such as `500 Internal Server Error`, `503 Service Unavailable`, or `GoogleAPICallError`), report the upstream service outage directly to the user. Do not attempt to inspect virtual environments, modify internal scripts, or debug local libraries.

## Reference Documentation
- **Master Index**: [Reference Documentation Index](./references/index.md)

### Operational Workflows
- [Troubleshoot Latency Workflow](./references/troubleshoot-latency.md)
- [Correlated Logs Workflow](./references/correlated-logs.md)
- [Trace Querying Decision Tree](./references/decision-tree.md)
- [Console Deep Links](./references/console-deep-links.md)
- [Workflows Overview](./references/workflows-overview.md)

### Query Syntax & Tools
- [Filter Syntax](./references/filter-syntax.md) (`root:`, `latency:`, `+span:`, `error:true`)
- [API Limits and Constraints](./references/api-limits.md)
- [Observability Analytics (BigQuery SQL)](./references/querying-observability-analytics.md)
- [Cloud Trace MCP Tools](./references/querying-mcp.md)

### Semantic Conventions
- [Conventions Overview](./references/conventions.md)
- [OpenTelemetry Core](./references/conventions-otel.md)
- [OpenTelemetry HTTP](./references/conventions-otel-http.md)
- [OpenTelemetry gRPC & RPC](./references/conventions-otel-grpc.md)
- [OpenTelemetry GenAI](./references/conventions-otel-genai.md)
- [GCP App Hub & Service Conventions](./references/conventions-gcp.md)
- [GCP Legacy Labels](./references/conventions-gcp-legacy.md)

### Concepts & Architecture
- [Observability Scopes](./references/observability-scopes.md)
- [Distributed Traces Concept](./references/concepts-trace.md)
- [Spans Concept](./references/concepts-span.md)
- [Logs-to-Trace Correlation](./references/logs-trace-correlation.md)
- [Knowledge Overview](./references/knowledge-overview.md)

### Templates & Assets
- [ASCII Formatting Templates](./assets/formatting/ascii)
- [A2UI Formatting Templates](./assets/formatting/a2ui)
- [Query Scenarios](./assets/queries)

## Official Documentation Links
- [Cloud Trace Documentation](https://docs.cloud.google.com/trace/docs)
- [Finding and Viewing Traces](https://docs.cloud.google.com/trace/docs/finding-traces)
- [OpenTelemetry Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/)
