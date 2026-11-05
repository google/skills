# Triage, logs, and inspection commands

-   [Identify the gateway](#identify-the-gateway): Lines 13-47
-   [Read the gateway logs](#read-the-gateway-logs): Lines 49-84
-   [When the logs are empty](#when-the-logs-are-empty): Lines 86-99
-   [Metrics](#metrics): Lines 101-106
-   [Inspect the deployed API config](#inspect-the-deployed-api-config): Lines 108-128
-   [Inspect the backend](#inspect-the-backend): Lines 130-161

All commands are read-only. Prefix each `gcloud` command as described in
[attribution.md](attribution.md).

## Identify the gateway

Match the request host against the `defaultHostname` of each gateway. The
release notes put it plainly: to get a gateway's URL, read its
`defaultHostname` property. Hostnames come in these shapes
([Configure streaming](https://docs.cloud.google.com/api-gateway/docs/streaming-configure.md.txt),
[Deploy an API to a gateway](https://docs.cloud.google.com/api-gateway/docs/deploying-api.md.txt)):

| Gateway | `defaultHostname` shape |
| :--- | :--- |
| Non-streaming | `{gateway_id}-{hash}.{region_code}.gateway.dev`, for example `my-gateway-a12bcd345e67f89g0h.uc.gateway.dev`. The deploy and streaming pages name the parts differently, so match the whole hostname. |
| Streaming, and model-routing gateways that got the newer format (possible for gateways created on or after September 3, 2026) | `{gateway_id}-{project_number}.{region}.gateway.dev` |
| Older streaming gateways, and model-routing gateways created earlier | A `*.run.app` hostname, kept permanently |

A `run.app` host can therefore be a gateway, not a Cloud Run service. Check
`gateways list` before you treat it as Cloud Run.

**Custom domain.** A custom domain's DNS A or AAAA record points at a global
external (or classic) Application Load Balancer. Its serverless NEG targets a
gateway, or several gateways through a URL mask, in the NEG's own region and
the load balancer's project
([Use a custom domain](https://docs.cloud.google.com/api-gateway/docs/using-custom-domains.md.txt),
[Load balancing for API Gateway](https://docs.cloud.google.com/api-gateway/docs/gateway-load-balancing.md.txt)).
To trace it, match the domain's IP address to a forwarding rule, then find the
NEG and the gateway it targets:

```bash
gcloud compute forwarding-rules list --project={project_id}
gcloud compute network-endpoint-groups list --project={project_id}
gcloud compute network-endpoint-groups describe {neg_name} --region={region} --project={project_id}
```

**Streaming mode.** `gateways describe` reports `effectiveStreamingMode`; see
[backend-routing-and-timeouts.md](backend-routing-and-timeouts.md#streaming-and-grpc-notes)
for what it limits.

## Read the gateway logs

API Gateway writes these platform logs. The first three use the
`apigateway.googleapis.com/Gateway` resource; produced API logs use
`resource.type="api"`
([Platform logs](https://docs.cloud.google.com/api-gateway/docs/platform-logging.md.txt)):

| Log | Use it for |
| :--- | :--- |
| `apigateway.googleapis.com%2Frequests` | One entry per request: status, latency, `responseDetails`, sizes |
| `apigateway.googleapis.com%2Fjwks_queries` | Failed or successful fetches of the JWT signing keys (`x-google-jwks_uri`) |
| `apigateway.googleapis.com%2Fservice_control_queries` | Written only when a Service Control `check` or `report` call fails (API keys, quota) |
| Produced API logs (`resource.type="api"`) | All gateways that serve one managed service |

Base filter (add one of the lines below it):

```
resource.type="apigateway.googleapis.com/Gateway"
resource.labels.gateway_id="{gateway_id}"
resource.labels.location="{region}"
```

| Goal | Extra filter line |
| :--- | :--- |
| One status code | `httpRequest.status={status_code}` |
| A time window | `timestamp>="{start_utc}" AND timestamp<="{end_utc}"` |
| JWT key fetches | `logName="projects/{project_id}/logs/apigateway.googleapis.com%2Fjwks_queries"` |
| Service Control failures | `logName="projects/{project_id}/logs/apigateway.googleapis.com%2Fservice_control_queries"` |
| Quota rejections | `jsonPayload.responseDetails="service_control_quota_error"` |

Run it with `gcloud logging read '{filter}' --project={project_id}
--freshness=1h --limit=20`. For the `requests` log, add the `--format` field
list from step 4 of SKILL.md. In each entry, `jsonPayload.apiConfig` and
`jsonPayload.apiMethod` identify the API config and method that served the
request
([Troubleshooting overview](https://docs.cloud.google.com/api-gateway/docs/troubleshoot.md.txt)).

## When the logs are empty

-   **Required APIs missing.** When the API responds but the logs have no data,
    the usual cause is that not all of `apigateway.googleapis.com`,
    `servicemanagement.googleapis.com`, and `servicecontrol.googleapis.com` are
    enabled.
-   **Client got `500` and there's no entry.** The gateway's service account
    may be deleted or disabled; see [auth-errors.md](auth-errors.md).
-   **Logs excluded.** A log sink exclusion filter can drop entries before
    they're stored; check the project's sinks
    ([Routing overview](https://docs.cloud.google.com/logging/docs/routing/overview.md.txt)).
-   **Wrong scope.** Recheck the project, region, and gateway ID from step 2.
-   **The request never reached the gateway.** See
    [networking-domains-tls.md](networking-domains-tls.md).

## Metrics

In Metrics Explorer, select **API Gateway > Proxy > Request Count**, and group
by `response_code_class`, `api_config`, `gateway_id`, or `location` to see when
errors started and which API config was serving
([Monitoring your API](https://docs.cloud.google.com/api-gateway/docs/monitoring.md.txt)).

## Inspect the deployed API config

List an API's configs, newest first:

```bash
gcloud api-gateway api-configs list --api={api_id} --project={project_id} \
  --format="table(name.basename(),createTime:sort=1:reverse)"
```

Print the OpenAPI document a config was created from. The `tr` step is needed
because the `contents` field is base64url encoded:

```bash
gcloud api-gateway api-configs describe {config_id} --api={api_id} --project={project_id} \
  --view=FULL --format="value(openapiDocuments[0].document.contents)" \
  | tr '_-' '/+' | base64 --decode
```

Get the API's managed service name (used for API keys and produced API logs)
with `gcloud api-gateway apis describe {api_id} --project={project_id}
--format="value(managedService)"`.

## Inspect the backend

Find the service account that the gateway uses to call backends:

```bash
gcloud api-gateway api-configs describe {config_id} --api={api_id} --project={project_id} \
  --format="value(gatewayServiceAccount)"
```

The value has the form `projects/-/serviceAccounts/{service_account_email}`.
If it's empty, rerun the command with `--view=FULL`. Pass only the email to
`gcloud iam service-accounts describe {service_account_email}`.

For a Cloud Run backend, read its ingress annotation
(`run.googleapis.com/ingress`) and its IAM policy:

```bash
gcloud run services describe {service} --region={backend_region} --project={backend_project} --format=yaml
gcloud run services get-iam-policy {service} --region={backend_region} --project={backend_project}
```

To check whether a request reached Cloud Run, read its request log:

```bash
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="{service}" AND log_name="projects/{backend_project}/logs/run.googleapis.com%2Frequests" AND httpRequest.status={status_code}' \
  --project={backend_project} --freshness=1h --limit=20 \
  --format="json(timestamp,httpRequest.status,httpRequest.latency,httpRequest.requestUrl)"
```

Cloud Run documents that a request blocked by ingress settings returns `404`
and doesn't appear in this log
([Cloud Run troubleshooting](https://docs.cloud.google.com/run/docs/troubleshooting.md.txt)).
