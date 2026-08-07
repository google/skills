# App Hub Scope & Labels

> **CRITICAL NUANCE: Verify App Hub Labels!** Not all Google Cloud metrics apply
> App Hub labels in the exact same way. **Infrastructure Metrics:** Usually
> attached as system metadata (`metadata_system_apphub_...` in PromQL).
> **Instrumented Metrics:** When included, attached as metric labels like
> `apphub_application_id` or might not have them attached by default.
>
> **REQUIRED ACTION:** Because label support varies by resource type and metric,
> you **must not guess**. You must verify exactly which App Hub labels and
> PromQL mappings exist on that specific metric by reading the public
> documentation linked below before generating the final SLO configuration.
>
> For full public documentation on label mappings across logs, metrics, and
> traces, refer to:
> `https://docs.cloud.google.com/stackdriver/docs/observability/application-monitoring-labels.md.txt`

When configuring an SLO that scopes to an App Hub Application, Service, or
Workload and you have verified the labels exist, use the following standard
metadata labels as your group by fields in PromQL queries:

### App Hub Application Scope

If monitoring an entire App Hub Application, include these labels in your PromQL
`BY (...)` clause:

*   `metadata_system_apphub_host_project_id`
*   `metadata_system_apphub_location`
*   `metadata_system_apphub_application_id`

### App Hub Service Scope

If monitoring a specific App Hub Service, include these labels:

*   `metadata_system_apphub_host_project_id`
*   `metadata_system_apphub_location`
*   `metadata_system_apphub_application_id`
*   `metadata_system_apphub_service_id`

### App Hub Workload Scope

If monitoring a specific App Hub Workload, include these labels:

*   `metadata_system_apphub_host_project_id`
*   `metadata_system_apphub_location`
*   `metadata_system_apphub_application_id`
*   `metadata_system_apphub_workload_id`

**Example Usage**:

```promql
sum(rate(run_googleapis_com:request_count[5m])) BY (metadata_system_apphub_host_project_id, metadata_system_apphub_location, metadata_system_apphub_application_id, metadata_system_apphub_service_id)
```
