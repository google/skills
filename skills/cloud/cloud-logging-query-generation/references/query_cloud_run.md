# Cloud Run LQL queries

## Base schema and structural patterns

Cloud Run workloads are split into two primary paradigms: Services (which
respond to HTTP requests) and Jobs (which execute to completion). Determine
which resource is being targeted before querying.

### Core resource types

*   **Cloud Run Services (`cloud_run_revision`)**: Use this when querying logs
    for an HTTP-driven service deployed to Cloud Run.
*   **Cloud Run Jobs (`cloud_run_job`)**: Use this when querying logs for a
    batch or parallel execution pipeline deployed to Cloud Run.

### Log types (service invocations and stdout)

Cloud Run splits infrastructure routing telemetry away from the application's
actual standard streams:

*   **Ingress Telemetry**: Use `log_id("run.googleapis.com/requests")` to
    capture the HTTP metadata (status codes, latency, caller IP, URL) generated
    by the Cloud Run gateway receiving the request.
*   **Application Payload**: Use `log_id("run.googleapis.com/stdout")` or
    `log_id("run.googleapis.com/stderr")` to capture logs explicitly printed by
    the container.

### Execution correlation and concurrency

Cloud Run handles concurrent requests out of the box. Therefore, attempting to
correlate logs via a simple execution ID label is usually an anti-pattern.

*   **Trace ID**: To trace all `stdout`/`stderr` payloads belonging to a single
    specific HTTP `request` log, apply a filter matching the `trace` string.
    (For example: `trace="projects/<PROJECT_ID>/traces/<TRACE_ID>"`).

## Example queries

### Cloud Run logs for a specific job

**Variables to replace:** `<JOB_NAME>`

```lql
resource.type="cloud_run_job" AND
resource.labels.job_name="<JOB_NAME>"
```

### Cloud Run logs for a specific revision and service

**Variables to replace:** `<SERVICE_NAME>`

```lql
resource.type="cloud_run_revision" AND
resource.labels.service_name="<SERVICE_NAME>"
```
