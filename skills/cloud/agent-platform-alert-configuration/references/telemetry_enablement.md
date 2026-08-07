# Telemetry Status & Enablement Check Reference

## Required Telemetry Environment Variables

To successfully export evaluation traces, the agent's deployment spec MUST have
the following environment variables:

Environment Variable                                 | Required Value                                   | Description
---------------------------------------------------- | ------------------------------------------------ | -----------
`GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY`         | `"true"`                                         | Enables tracing and logging export.
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | `"EVENT_ONLY"` or `"SPAN_AND_EVENT"` or `"true"` | Captures message payloads for evaluation.
`OTEL_SEMCONV_STABILITY_OPT_IN`                      | `"gen_ai_latest_experimental"`                   | Opts into Gen AI semantic conventions.

## How to Enable Telemetry via Terraform

Update the `google_vertex_ai_reasoning_engine` resource's `deployment_spec.env`
blocks:

```hcl
resource "google_vertex_ai_reasoning_engine" "my_agent" {
  ...
  spec {
    deployment_spec {
      env {
        name  = "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY"
        value = "true"
      }
      env {
        name  = "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
        value = "EVENT_ONLY"
      }
      env {
        name  = "OTEL_SEMCONV_STABILITY_OPT_IN"
        value = "gen_ai_latest_experimental"
      }
    }
  }
}
```

## Telemetry and Data Generation Dependencies

Even if telemetry environment variables are configured on the agent, verify
these additional dependencies. Note that quality metrics will NOT populate, and
quality metrics alert policies and the Online Monitor should be skipped if the
decision is to NOT enable the required APIs:

1.  **API Enablement**: Ensure the following APIs are enabled in the GCP
    project:

    *   **Cloud Trace API**: `cloudtrace.googleapis.com` (needed for exporting
        spans)
    *   **Observability API**: `observability.googleapis.com` (needed for trace
        storage and SQL queries by the evaluator)

    *To check if they are enabled:*

    ```bash
    gcloud services list --enabled --project="{project_id}" \
      --filter="name:(cloudtrace.googleapis.com observability.googleapis.com)"
    ```

2.  **IAM Permissions**: The service account assigned to the agent (default or
    custom) MUST have the Cloud Trace Agent (`roles/cloudtrace.agent`) and Logs
    Writer (`roles/logging.logWriter`) roles.
