# Limits, quotas, unsupported features, and escalation

-   [Product limits](#product-limits): Lines 9-24
-   [429 from the API's own quota](#429-from-the-apis-own-quota): Lines 26-33
-   [Requesting a quota increase](#requesting-a-quota-increase): Lines 35-42
-   [Documented limitations](#documented-limitations): Lines 44-55
-   [Escalate to Cloud Customer Care](#escalate-to-cloud-customer-care): Lines 57-77

## Product limits

From [Quotas and limits](https://docs.cloud.google.com/api-gateway/docs/quotas.md.txt):

| Limit | Value |
| :--- | :--- |
| APIs | 50 total |
| API configs | 100 per API |
| Gateways | 50 per region |
| Request size | 32 megabytes |
| Response size | 32 megabytes; streamed and chunked responses are exempt |
| gRPC transcoding request or response | 1 megabyte |
| Request headers | 60 kilobytes |
| OpenAPI 3.x upload | 10 MB in total and 50 files ([OpenAPI 3.x limitations](https://docs.cloud.google.com/api-gateway/docs/openapi-v3-limitations.md.txt)) |

Quote limits from the live page when you answer, because they change.

## 429 from the API's own quota

A `429` with `jsonPayload.responseDetails="service_control_quota_error"` means
the caller exceeded one of the API's quota limits. The limits enforced for
every gateway are the ones in the most recently created API config
([Troubleshooting overview](https://docs.cloud.google.com/api-gateway/docs/troubleshoot.md.txt)).
Identify the method from `jsonPayload.apiMethod`, then hand off to the
`api-gateway-backend-security-and-rate-limiting` skill to change limits.

## Requesting a quota increase

Product quotas are adjusted through Cloud Quotas: in the Google Cloud console,
go to **IAM & Admin > Quotas & System Limits**, select the quota, and choose
**Edit**. Adjustment requests are subject to review, and if the console can't
submit the request, ask Cloud Customer Care
([Quotas and limits](https://docs.cloud.google.com/api-gateway/docs/quotas.md.txt)).
The user submits the request; don't submit it for them.

## Documented limitations

Explain these as product limitations rather than misconfigurations:

| Limitation | Source |
| :--- | :--- |
| Non-streaming gateways can't call Google Cloud APIs (`*.googleapis.com` backends can fail with `401`); streaming gateways can, with an access token that has only the `cloud-platform` scope | [Securing backend services](https://docs.cloud.google.com/api-gateway/docs/securing-backend-services.md.txt) |
| No ingress control settings; the gateway's own hostname can't be disabled | [Load balancing for API Gateway](https://docs.cloud.google.com/api-gateway/docs/gateway-load-balancing.md.txt) |
| Streaming gateways can't use a load balancer, serverless NEG, or custom domain (Public Preview) | [Configure streaming](https://docs.cloud.google.com/api-gateway/docs/streaming-configure.md.txt) |
| Streaming mode can't be changed after the gateway is created | [Deploy an API to a gateway](https://docs.cloud.google.com/api-gateway/docs/deploying-api.md.txt) |
| No partial-segment path templates; no OR between an API key and another scheme | [OpenAPI 2.0 limitations](https://docs.cloud.google.com/api-gateway/docs/openapi-limitations.md.txt) |
| Scopes, parameters, and schemas are accepted but not enforced | [OpenAPI 2.0 limitations](https://docs.cloud.google.com/api-gateway/docs/openapi-limitations.md.txt) |

## Escalate to Cloud Customer Care

Don't speculate about Google's internal systems. Draft the case text with this
evidence bundle, redact all credentials, and let the user file it at
[Cloud Customer Care](https://cloud.google.com/support):

```
Product: API Gateway
Project ID and number: {project_id} / {project_number}
Gateway ID and region: {gateway_id} / {region}
API ID and API config ID: {api_id} / {config_id}
Gateway hostname: {default_hostname}
Time window (UTC): {start_utc} to {end_utc}
Sample failing requests: {timestamp_utc} {method} {path} -> {status_code}
Log query used: gcloud logging read 'resource.type="apigateway.googleapis.com/Gateway" AND resource.labels.gateway_id="{gateway_id}" AND timestamp>="{start_utc}" AND timestamp<="{end_utc}"' --project={project_id} --limit=50 --format="json(timestamp,httpRequest.requestMethod,httpRequest.status,httpRequest.requestUrl,jsonPayload.responseDetails)"
responseDetails values: {response_details}
Failed operation IDs (control plane): {operation_ids}
Recent changes: {changes}
Steps already taken: {steps}
Reproduction (no credentials): curl -i https://{default_hostname}/{path}
```
