# Querying Traces via MCP Tools

This page documents how to query and analyze traces using Model Context Protocol
(MCP) tools.

## Registered MCP Tools

When the Cloud Trace MCP server is configured and connected, the following tools
become available to the agent environment:

### 1. `list_traces`

*   **Description**: Lists traces in the target GCP project that match a v1
    filter query expression.
*   **Arguments**:
    *   `projectId` (string, required): ID of the Cloud project where the trace
        data is stored.
    *   `startTime` (string, required): Query start time (RFC 3339 timestamp).
    *   `endTime` (string, required): Query end time (RFC 3339 timestamp).
    *   `filter` (string, optional): The filter expression (e.g. `latency:2s`).
    *   `pageSize` (integer, optional): Maximum number of traces to return
        (default is 100).

### 2. `get_trace`

*   **Description**: Retrieves all spans associated with a specific trace ID.
*   **Arguments**:
    *   `projectId` (string, required): ID of the Cloud project where the trace
        data is stored.
    *   `traceId` (string, required): The 32-character hex trace ID.

## Guidance: Scripts vs. MCP Tools

*   **Use Local Script Utilities** (`search_traces`, `fetch_entire_trace`,
    `fetch_related_logs`) as the default entry point. Scripts are optimized to
    format results cleanly and filter out redundant fields, preventing context
    window bloat in the agent environment.
*   **Use MCP Tools** (`list_traces`, `get_trace`) if running in an external
    client environment without access to a local shell or script repository, or
    when using automated MCP tool registries that inject standard query actions.
    Note that MCP endpoints might have permissions/access in sandboxed
    environments that local scripts do not have access to.

## See Also

*   [Model Context Protocol for Cloud Trace - Google Cloud docs](https://docs.cloud.google.com/trace/docs/reference/mcp/mcp)
*   [Cloud Trace MCP `list_traces` Tool - Google Cloud docs](https://docs.cloud.google.com/trace/docs/reference/mcp/mcp/tools_list/list_traces.md.txt)
*   [Cloud Trace MCP `get_trace` Tool - Google Cloud docs](https://docs.cloud.google.com/trace/docs/reference/mcp/mcp/tools_list/get_trace.md.txt)
*   [Cloud Trace Query Syntax (v1)](./filter-syntax.md)
