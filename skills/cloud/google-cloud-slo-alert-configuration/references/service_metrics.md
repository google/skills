# Service Metrics Mapping (SLI Types)

When determining the `ServiceLevelIndicator` (SLI), map the user's Google Cloud
resource and desired Google Cloud metric type to the correct Prometheus metric
type.

**IMPORTANT DOCUMENTATION LINK**: If the user's Google Cloud resource is not
listed below, you **MUST** use the `read_url_content` tool to fetch the live
infrastructure list from:
`https://docs.cloud.google.com/monitoring/docs/application-monitoring-services.md.txt`

### Cloud Run (`run.googleapis.com`)

*   **Availability (RatioSli):**
    *   `total_metric`: `run_googleapis_com:request_count`
    *   `bad_metric` filter: `response_code_class="5xx"`
*   **Latency (DistributionSli):**
    *   `distribution_metric`: `run_googleapis_com:request_latencies`

### Google Kubernetes Engine (GKE)

**Scenario A: Registered in App Hub (Preferred)**

For GKE deployments, StatefulSets, and DaemonSets registered in App Hub, use the
automatically generated SLIs:

*   **Availability (RatioSli):**
    *   `total_metric`: `service:server_request_count` (mapping for
        `service/server/request_count`)
    *   `bad_metric` filter: `response_code_class="5xx"`
*   **Latency (DistributionSli):**
    *   `distribution_metric`: `service:server_response_latencies` (mapping for
        `service/server/response_latencies`)

**Scenario B: Custom Telemetry (OTLP / Prometheus)**

If the user's apps, services, and workloads are not registered in App Hub, you
**MUST** ask the user for their exact metric names and failure filters if they
are not provided in the original request.

*Examples of potential metrics:*

*   **Prometheus / Istio:** `istio_requests_total` filter:
    `response_code=~"5.."`
*   **OTLP:** `http.server.request.duration` filter:
    `http.response.status_code=~"5.."`

### Vertex AI (`aiplatform.googleapis.com`)

*   **Availability (RatioSli):**
    *   `total_metric`:
        `aiplatform_googleapis_com:reasoning_engine_request_count` (Example for
        Reasoning Engine)
    *   `bad_metric` filter: `response_code=~"5.."`
