# MCP Verification, Limitations, and Troubleshooting Reference

- [MCP Endpoint Verification with curl (JSON-RPC 2.0 Lifecycle)](#mcp-endpoint-verification-with-curl-json-rpc-20-lifecycle): Lines 7-93
- [JSON-RPC and HTTP Error Diagnosis on /mcp](#json-rpc-and-http-error-diagnosis-on-mcp): Lines 95-135
- [Mutual Exclusion with Model Routing and Preview Limits](#mutual-exclusion-with-model-routing-and-preview-limits): Lines 137-152

## MCP Endpoint Verification with `curl` (JSON-RPC 2.0 Lifecycle)

API Gateway exposes MCP over stateless HTTP `POST` at `https://{default_hostname}/mcp`. The `/mcp` path stays at the host root: a `servers` base path set with `x-google-endpoint` (such as `/v2`) applies to REST paths only, and `https://{default_hostname}/{basepath}/mcp` returns HTTP 404. Send the `MCP-Protocol-Version: 2025-11-25` header on every request after `initialize` (if omitted, the gateway falls back to `2025-03-26`).

### 1. Handshake (`initialize`)

`initialize` requires no authentication:

```bash
curl -sS -X POST "https://{default_hostname}/mcp" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2025-11-25",
      "capabilities": {},
      "clientInfo": {"name": "verify-client", "version": "1.0.0"}
    }
  }'
```

### 2. Acknowledge Handshake (`notifications/initialized`)

The gateway responds with `HTTP 202 Accepted`. Include the `MCP-Protocol-Version: 2025-11-25` header on `notifications/initialized` and on all later requests (`tools/list`, `tools/call`). If the header is omitted, API Gateway falls back to protocol version `2025-03-26`:

```bash
curl -i -sS -X POST "https://{default_hostname}/mcp" \
  -H "Content-Type: application/json" \
  -H "MCP-Protocol-Version: 2025-11-25" \
  -d '{"jsonrpc": "2.0", "method": "notifications/initialized"}'
```

### 3. Discover Tools (`tools/list`)

Include `Authorization: Bearer <token>` when `x-google-api-management.mcp.tools-list.security` names a JWT scheme, or `x-api-key: {api_key}` when it names an API key scheme (`tools/list` does not read API keys from query parameters).

For a test token, mint a Google ID token for a caller service account (you need `roles/iam.serviceAccountTokenCreator` on `{caller_sa_email}`). The token audience must be in the `x-google-auth.audiences` list of the JWT scheme in the API config's OpenAPI spec. If you do not have the spec file, print the spec of the config that the gateway serves:

```bash
config_id="$(gcloud api-gateway gateways describe {gateway_id} \
  --location={region} --project={project_id} \
  --format="value(apiConfig.basename())")"

gcloud api-gateway api-configs describe "${config_id}" \
  --api={api_id} --project={project_id} --view=FULL \
  --format="value(openapiDocuments[0].document.contents)" \
  | tr '_-' '/+' | base64 --decode
```

Then mint the token and list the tools:

```bash
jwt_token="$(gcloud auth print-identity-token \
  --impersonate-service-account={caller_sa_email} \
  --audiences={jwt_audience})"

curl -sS -X POST "https://{default_hostname}/mcp" \
  -H "Content-Type: application/json" \
  -H "MCP-Protocol-Version: 2025-11-25" \
  -H "Authorization: Bearer ${jwt_token}" \
  -d '{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}'
```

### 4. Invoke a Tool (`tools/call`)

Include the credentials required by the underlying REST operation (`x-api-key` and/or `Authorization: Bearer <token>`), and nest any JSON request body inside `arguments.body`:

```bash
curl -sS -X POST "https://{default_hostname}/mcp" \
  -H "Content-Type: application/json" \
  -H "MCP-Protocol-Version: 2025-11-25" \
  -H "x-api-key: {api_key}" \
  -H "Authorization: Bearer ${jwt_token}" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "get_order_status",
      "arguments": {"orderId": "ORD-10042"}
    }
  }'
```

Reference: [Configure Model Context Protocol - Verify MCP support](https://docs.cloud.google.com/api-gateway/docs/mcp-configure.md.txt)

## JSON-RPC and HTTP Error Diagnosis on `/mcp`

Most MCP errors return `HTTP 200` with a JSON-RPC `error` object, because many MCP clients fail at the HTTP transport layer on a non-200 response. The exceptions are `400`, `401`, `403`, `404`, `405`, and `413`. Check both the HTTP status and the JSON-RPC `error` field, then find the symptom in the tables below.

### Connection and routing

| What you see | Cause | Fix |
| --- | --- | --- |
| HTTP `404` with an HTML `Page not found` page | The gateway may not be deployed correctly, or a gateway create or update has not finished. | Check that the gateway state is `ACTIVE` (`gcloud api-gateway gateways describe {gateway_id} --location={region}`) and that the last operation finished. During an update, some requests can still reach the previous API config, so retry for a few minutes before you change the config. |
| HTTP `404` with the JSON message `The current request is not defined by this API.` | The request went to `{basepath}/mcp`, or the active API config does not enable MCP. | Send requests to `https://{default_hostname}/mcp` at the host root, and check that the deployed spec has `x-google-api-management.mcp`. |
| HTTP `405` `Method Not Allowed` | The client sent `GET` or `OPTIONS` to `/mcp`. | Send HTTP `POST` only. The gateway has no SSE `GET` stream and does not handle CORS preflight (`OPTIONS`) on `/mcp`. |
| HTTP `413` (transport body too large) | The raw HTTP request body is larger than the gateway transport limit. | Send a smaller request. |

### Authentication

| What you see | Cause | Fix |
| --- | --- | --- |
| HTTP `401` or `403`, JSON-RPC `-32000` `Tool list response is invalid or has error status code.` (JWT scheme on `tools/list`) | `401`: the JWT is missing or malformed. `403`: the JWT has a wrong audience. The message does not name the cause. Today every failed `tools/list` request returns this code and message. Both can change, so check the HTTP status first. | Send `Authorization: Bearer <token>` with an audience from `x-google-auth.audiences`. The `WWW-Authenticate` header points at the protected resource metadata. |
| HTTP `401` or `200`, JSON-RPC `-32000` `Tool list response is invalid or has error status code.` (API key scheme on `tools/list`) | `401`: the API key is missing, or the client sent it only as a query parameter. `200`: the API key is not valid. The code, the message, and the HTTP `200` are today's behavior and can change. | Send a valid key in the `x-api-key` header. Because an invalid key returns HTTP `200`, check the JSON-RPC `error` field as well as the HTTP status. |

### Protocol

| What you see | Cause | Fix |
| --- | --- | --- |
| HTTP `400`, JSON-RPC `-32700` (parse error) | The request body is not valid JSON. | Send valid JSON. |
| HTTP `200`, JSON-RPC `-32600` (invalid request) | The body is valid JSON but not a valid JSON-RPC request. | Set the required fields `jsonrpc`, `method`, and `id`. |
| HTTP `200`, JSON-RPC `-32601` `Method ... is not supported` | The client called a method that the gateway does not support, such as `resources/*`, `prompts/*`, `sampling/*`, `completion/*`, or `logging/*`. | Use only `initialize`, `notifications/initialized`, `ping`, `tools/list`, and `tools/call`. |
| HTTP `400`, JSON-RPC `-32602` `Unsupported protocol version` | A request after `initialize` sent an `MCP-Protocol-Version` header that the gateway does not support. `initialize` itself does not fail on an unknown `protocolVersion`: the gateway answers with `2025-11-25`. | Send `MCP-Protocol-Version: 2025-11-25`. |
| HTTP `200`, JSON-RPC `-32602` `Missing valid protocolVersion in initialize request` | The `initialize` params omit `protocolVersion`, or its value is not a string. | Send `"protocolVersion": "2025-11-25"` in the `initialize` params. |

### Tool calls

| What you see | Cause | Fix |
| --- | --- | --- |
| HTTP `200`, JSON-RPC `-32602` (unknown tool) | `params.name` does not match an exposed tool in the active API config, or the operation is opted out with `x-google-mcp-tool: false`. | Run `tools/list` again, and call a listed tool name. |
| HTTP `200`, JSON-RPC `-32602` (invalid tool arguments) | `params.arguments` misses required parameters, or the JSON request body is not nested inside `"body": { ... }`. | Pass path and query parameters as top-level arguments, and nest the request body under `arguments.body`. |
| HTTP `200`, `result.isError: true` | The backend returned a 4xx or 5xx error. | Read `result.content[0].text` for the backend's error body, and fix the request or the backend. |
| HTTP `200`, JSON-RPC `-32000` (body too large) | The backend response is larger than the size limit. | Return a smaller response, for example with paging. |
| HTTP `200`, JSON-RPC `-32000` `Server error` | An internal gateway error. It is not a backend error: backend errors return `result.isError: true`. | Retry. If the error continues, contact Cloud Customer Care. |

Reference: [Configure Model Context Protocol - Troubleshooting MCP failures](https://docs.cloud.google.com/api-gateway/docs/mcp-configure.md.txt)

## Mutual Exclusion with Model Routing and Preview Limits

- **Model Routing mutual exclusion:** NEVER set `x-google-api-management.mcp` and use `x-google-model-router` on an operation in the same OpenAPI specification. Model routers are defined in `x-google-api-management.ai.models.routing`. **Rationale:** API Gateway does not allow MCP and Model Routing in the same API config. If you need both an inbound `/mcp` server and an outbound LLM model router, deploy two separate API configs and gateways.
- **Stateless UTF-8 text only:** Session headers (`MCP-Session-Id`), SSE streaming, binary/multi-modal responses (such as raw PDF or image downloads; return a UTF-8 JSON object with a signed URL or opt out binary endpoints with `x-google-mcp-tool: false`), and empty `HTTP 204` responses are not supported in Public Preview.
- **Other Public Preview limits:**
  - JSON-RPC batch arrays are rejected. Send one JSON-RPC request in each HTTP `POST`.
  - The stdio transport is not supported. Clients connect over HTTP `POST` only.
  - OpenAPI 2.0 is not supported. Use OpenAPI 3.0.x or 3.1.x.
  - A gateway serves at most 1,000 MCP tools.
  - Tool declarations do not include annotations such as `destructiveHint` or `readOnlyHint`.
  - API Gateway rejects complex nested schemas when you create the API config. A simple nested object body works.
  - In OpenAPI 3.1, each schema needs one `type`. A type list such as `type: ["string", "null"]` fails config creation with `Schema has multiple types defined. More than one type is not supported, please define only one type.`

References:
- [Model Context Protocol overview - Limitations](https://docs.cloud.google.com/api-gateway/docs/mcp-overview.md.txt)
- [OpenAPI 3.x feature limitations - MCP limitations](https://docs.cloud.google.com/api-gateway/docs/openapi-v3-limitations.md.txt)
