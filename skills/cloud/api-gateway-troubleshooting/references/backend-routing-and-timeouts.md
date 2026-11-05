# Routing, size limits, backend errors, timeouts, and CORS

-   [404 Not Found](#404-not-found): Lines 10-47
-   [Request and header size limits](#request-and-header-size-limits): Lines 49-59
-   [502 and 503](#502-and-503): Lines 61-70
-   [504 and slow responses](#504-and-slow-responses): Lines 72-105
-   [CORS](#cors): Lines 107-119
-   [Streaming and gRPC notes](#streaming-and-grpc-notes): Lines 121-129

## 404 Not Found

Read `responseDetails` first (see [triage-and-logs.md](triage-and-logs.md)).

**`via_upstream`, and no matching entry in the Cloud Run request log.** The
Cloud Run service's ingress setting is probably blocking the gateway, or the
service's default `run.app` URL is disabled while the gateway's `address`
still uses it. With
ingress set to *Internal*, only the sources listed on the ingress page can reach
the service, and requests from other sources can't reach it at the `run.app`
URL, a custom URL, or a custom domain
([Cloud Run ingress](https://docs.cloud.google.com/run/docs/securing/ingress.md.txt)).
Cloud Run documents that requests blocked by these ingress settings, or sent
to a disabled `run.app` URL, get `404` and don't appear in its request log
([Cloud Run troubleshooting](https://docs.cloud.google.com/run/docs/troubleshooting.md.txt)).
Read the `run.googleapis.com/ingress` annotation to confirm. Fix, after
approval: `gcloud run services update {service} --ingress=all
--region={backend_region} --project={backend_project}`, and keep the service
private through IAM: grant `roles/run.invoker` to the gateway's service account
only (see [auth-errors.md](auth-errors.md)).

**`via_upstream`, and the backend logged the `404`.** The backend received a
path it doesn't serve. Check path translation in `x-google-backend`
([OpenAPI 2.0 extensions](https://docs.cloud.google.com/api-gateway/docs/oasv2-extensions.md.txt)):

| Where `x-google-backend` is set | Default `path_translation` | Effect |
| :--- | :--- | :--- |
| Top level of the spec | `APPEND_PATH_TO_ADDRESS` | The request path is appended to `address`. |
| On an operation | `CONSTANT_ADDRESS` | The request goes to `address` as-is, and path parameters are sent as query parameters. |

**Produced by the gateway.** By default, API Gateway serves only the methods
listed in the OpenAPI document (`x-google-allow: configured` in OpenAPI 2.0),
so the request's path or method is probably missing from the API config that
the gateway serves. Print the deployed OpenAPI document (see
[triage-and-logs.md](triage-and-logs.md#inspect-the-deployed-api-config)) and
compare its paths, methods, and base path with the request. Confirm the gateway
serves the config you expect by comparing the config ID in
`jsonPayload.apiConfig` with the gateway's `apiConfig`.

## Request and header size limits

API Gateway allows requests up to 32 megabytes, responses up to 32 megabytes
(streamed and chunked responses are exempt), and 60 kilobytes of request
headers. gRPC transcoding requests and responses are limited to 1 megabyte
each. The backend may have lower limits
([Quotas and limits](https://docs.cloud.google.com/api-gateway/docs/quotas.md.txt)).
The docs list these limits but not the status codes returned when a limit is
exceeded, so confirm from the response body and `responseDetails`. Compare the
request's body and header sizes with the limits, then suggest smaller payloads,
fewer or smaller headers, or streaming for large responses.

## 502 and 503

-   **`via_upstream`:** the backend returned the error. Troubleshoot the
    backend directly, starting with its own request logs; this skill's scope
    ends once the backend is identified.
-   **Produced by the gateway:** the gateway, not the backend, generated the
    error. Check that `address` uses `https` for serverless backends, that the
    backend host resolves, and that the backend is healthy in its own logs and
    metrics. If all three hold and the errors continue, escalate (see
    [limits-and-escalation.md](limits-and-escalation.md)).

## 504 and slow responses

-   **Deadline.** The default backend `deadline` is 15.0 seconds. It can be
    raised up to 3600 seconds, but a non-streaming gateway rejects values above
    600 seconds when the gateway is created or updated, not when the API config
    is created
    ([OpenAPI 2.0 extensions](https://docs.cloud.google.com/api-gateway/docs/oasv2-extensions.md.txt)).
    Check `effectiveStreamingMode` before you propose a value above 600. The
    docs don't name the status code returned when the deadline expires, and a
    `504` with `via_upstream` can come from the backend's own request
    timeout instead.
-   **Default fix.** On a non-streaming gateway, set `deadline` to at most 600
    seconds in a new API config and deploy it with `gateways update`. Requests
    that need longer require a new streaming-enabled gateway, which gets a new
    hostname that callers must switch to (see
    [Streaming and gRPC notes](#streaming-and-grpc-notes)). Give the commands
    for the existing gateway even when you also propose a new gateway.
-   **Trade-off.** The docs warn that long deadlines can overload the proxy with
    TCP connections when the backend is slow, and short deadlines can make
    expensive requests fail consistently. Propose the smallest deadline that
    covers the backend's normal response time.
-   **Backend timeout.** The backend's own request timeout also limits the
    response. For example, the streaming guide notes that a Cloud Run service
    deployed with `--timeout 600` ends its streams after 10 minutes, so a
    3,600-second deadline also needs `--timeout 3600` on the service.
-   **Streaming endpoints.** On an SSE or chunked-transfer path, the deadline
    bounds the whole response, so a stream is cut when it elapses. On a gRPC
    or WebSocket endpoint, it bounds the gap between messages
    ([OpenAPI 2.0 extensions](https://docs.cloud.google.com/api-gateway/docs/oasv2-extensions.md.txt),
    [Configure streaming](https://docs.cloud.google.com/api-gateway/docs/streaming-configure.md.txt)).
-   **Cold starts.** After 15 to 20 minutes without traffic, the first
    requests can see added latency. If latency persists after warm-up, check the
    backend's request logs
    ([Troubleshooting overview](https://docs.cloud.google.com/api-gateway/docs/troubleshoot.md.txt)).

## CORS

To let the backend handle CORS, including `OPTIONS` preflight requests, turn on
CORS pass-through, then make sure the backend answers preflight requests with
the right `Access-Control-*` headers:

| OpenAPI version | Setting |
| :--- | :--- |
| 2.0 | Top-level `x-google-endpoints` with `allowCors: True` ([extensions](https://docs.cloud.google.com/api-gateway/docs/oasv2-extensions.md.txt)) |
| 3.x | `allowCors: true` in the `x-google-endpoint` extension on the server ([extensions](https://docs.cloud.google.com/api-gateway/docs/oasv3-extensions.md.txt)) |

After the change, create a new API config and deploy it, then repeat the
browser request and inspect the preflight response.

## Streaming and gRPC notes

-   You can't update a gateway to change its streaming mode; create a new
    gateway, which gets a new hostname
    ([Deploy an API to a gateway](https://docs.cloud.google.com/api-gateway/docs/deploying-api.md.txt)).
-   Gateways with streaming enabled can't sit behind a load balancer or
    serverless NEG, so they can't use custom domains during Public Preview
    ([Configure streaming](https://docs.cloud.google.com/api-gateway/docs/streaming-configure.md.txt)).
-   Terraform can't enable streaming yet.
