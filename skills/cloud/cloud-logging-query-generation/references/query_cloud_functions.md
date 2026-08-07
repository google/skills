# Cloud Run Functions LQL queries

## Base schema and structural patterns

Cloud Functions logs differ significantly depending on whether you are targeting
1st Gen or 2nd Gen functions.

### 1st Gen Functions

*   **Resource Type**: `resource.type="cloud_function"`
*   **Log ID**: `log_id("cloudfunctions.googleapis.com/cloud-functions")`
*   **Execution Correlation**: To find all logs for a single execution, filter
    by `labels.execution_id="<EXECUTION_ID>"`.
*   **Targeting**: Filter by `resource.labels.function_name="<FUNCTION_NAME>"`
    and `resource.labels.region="<REGION>"`.

### 2nd Gen Functions (Cloud Run Functions)

Because 2nd Gen runs natively on Cloud Run infrastructure, its logs share the
standard Cloud Run schema and suffer from interleaved concurrency.

*   **Resource Type**: `resource.type="cloud_run_revision"`
*   **Log ID**: Use `log_id("run.googleapis.com/requests")` for invocation
    telemetry (latency, HTTP status codes, request URLs). Use
    `log_id("run.googleapis.com/stdout")` or
    `log_id("run.googleapis.com/stderr")` for application container output.
*   **Execution Correlation**: The most reliable way to correlate a single
    concurrent execution is via trace ID:
    `trace="projects/<PROJECT_ID>/traces/<TRACE_ID>"`. (Fallback:
    `labels.execution_id` only if the user's runtime SDK is explicitly injecting
    it).
*   **Targeting**: Filter by `resource.labels.service_name="<FUNCTION_NAME>"`
    and `resource.labels.location="<REGION>"`.

## Example queries

### Finds execution errors for 1st generation Cloud Functions.

**Variables to replace:** None

```lql
resource.type="cloud_function" AND
log_id("cloudfunctions.googleapis.com/cloud-functions") AND
severity >= ERROR
```

### Finds execution errors for 2nd generation Cloud Functions.

**Variables to replace:** None

```lql
resource.type="cloud_run_revision" AND
(log_id("run.googleapis.com/stdout") OR
 log_id("run.googleapis.com/stderr") OR
 log_id("run.googleapis.com/requests")) AND
severity >= ERROR
```
