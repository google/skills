# MCP Traffic Security and Quotas Reference (Public Preview)

- [Authentication Model per MCP Method](#authentication-model-per-mcp-method): Lines 8-35
- [Tool Discovery Security (tools/list)](#tool-discovery-security-toolslist): Lines 37-96
- [Shared REST and MCP Quota Enforcement](#shared-rest-and-mcp-quota-enforcement): Lines 98-104
- [Sensitive Operations and Header Parameters on MCP](#sensitive-operations-and-header-parameters-on-mcp): Lines 106-115

## Authentication Model per MCP Method

Model Context Protocol (MCP) support on API Gateway is a **Public Preview** feature that requires an OpenAPI 3.x specification (`x-google-api-management.mcp`). It exposes a stateless JSON-RPC 2.0 endpoint at `POST https://{default_hostname}/mcp`, even when a `servers` base path is set (up to 1,000 tools per gateway, mutually exclusive with `x-google-model-router` in the same API config).

API Gateway applies distinct authentication rules to each MCP method:

| MCP Method | Default Authentication | Supported Security Schemes | Behavior |
| --- | --- | --- | --- |
| `initialize` | Unauthenticated | None | Handled directly by the gateway handshake layer; never reaches the backend. |
| `notifications/initialized` | Unauthenticated | None | Returns `HTTP 202 Accepted`; never reaches the backend. |
| `tools/list` | Unauthenticated by default | Exactly one JWT scheme (`oauth2` with `x-google-auth`) or one API key scheme (`apiKey`) | Configured via `x-google-api-management.mcp.tools-list.security`. `tools/list` reads an API key only from the `x-api-key` header, not from query parameters. |
| `tools/call` | Inherits operation security | JWT (`oauth2`) and API keys (`apiKey`) | Transcoded into the underlying REST request and subject to the exact `security` and `x-google-quota` rules of that OpenAPI operation. |

API Gateway reports an MCP authentication failure in the HTTP status, in the JSON-RPC `error` field of the body, or in both. Check both, because one case returns HTTP `200`:

| Method and scheme | Request | HTTP status | Body |
| --- | --- | --- | --- |
| `tools/list` with a JWT scheme | Missing or invalid token | `401`, with a `WWW-Authenticate` header | JSON-RPC error (today `-32000`) |
| `tools/list` with a JWT scheme | Token with a wrong audience | `403`, with a `WWW-Authenticate` header | JSON-RPC error (today `-32000`) |
| `tools/list` with an API key scheme | Missing key | `401` | JSON-RPC error, no tools |
| `tools/list` with an API key scheme | Invalid key | `200` (current behavior) | JSON-RPC error, no tools |
| `tools/call` | Credentials that fail the operation's `security` | `401` or `403` | A REST error (for example `{"code":401,"message":"Jwt is missing"}`) or a JSON-RPC result with `isError: true` |

Today the `tools/list` JSON-RPC error has code `-32000` and the message `Tool list response is invalid or has error status code.`, which does not name the cause. The code and the message can change, so check the HTTP status and the `WWW-Authenticate` header first. For a JWT failure, the `WWW-Authenticate` header points at the protected resource metadata.

If a gateway project is attached to Apigee API hub, MCP-enabled gateways are automatically published to API hub (`{api} (MCP)`) and Agent Registry.

Reference: [Configure Model Context Protocol](https://docs.cloud.google.com/api-gateway/docs/mcp-configure.md.txt)

## Tool Discovery Security (`tools/list`)

By default, `tools/list` is unauthenticated, which allows any caller that reaches the gateway URL to enumerate all tool names, descriptions, and JSON input schemas.

- In production environments, ALWAYS configure `x-google-api-management.mcp.tools-list.security` with a JWT or API key security scheme defined in `components.securitySchemes`. **Rationale:** Leaving `tools/list` unauthenticated exposes internal API capabilities and parameter schemas to unauthenticated callers.
- Name **exactly one** scheme under `tools-list.security`. **Rationale:** API Gateway rejects a `tools-list.security` block that names more than one scheme. An empty block (`security: {}`) passes config creation with no error and leaves `tools/list` unauthenticated, so check that the block names a scheme.
- Prefer a JWT scheme when agents must prove who they are. An API key identifies a consumer project rather than a caller, so use an API key scheme on `tools/list` when the tools already require that API key and caller identity is not needed.
- If you use a JWT scheme, list the same scheme in the root `security` list. **Rationale:** API Gateway rejects a config whose JWT `tools-list.security` scheme is missing from the root `security` list. The root entry also requires the JWT on every REST operation that does not set its own `security`, so tell the user before you deploy.
- If you use an API key scheme, define it with `in: header` and `name: x-api-key`. **Rationale:** `tools/list` reads API keys only from the `x-api-key` header, not from query parameters.
- Setting `x-google-api-management.mcp` to an object (to configure `tools-list`) automatically enables MCP globally for all eligible `GET`, `POST`, `PUT`, `PATCH`, and `DELETE` operations in the specification. Explicitly set `x-google-mcp-tool: false` on every operation that must not be exposed as an agent tool. Every exposed tool MUST resolve to a unique name matching `[A-Za-z0-9_.-]{1,128}` and a non-empty description.

```yaml
openapi: 3.0.4
info:
  title: Orders Service
  version: 1.0.0
x-google-api-management:
  mcp:
    tools-list:
      security:
        agent_jwt: []
  backends:
    orders-backend:
      address: https://{backend_service}-{hash}.a.run.app
      jwtAudience: https://{backend_service}-{hash}.a.run.app
x-google-backend: orders-backend
security:
  - agent_jwt: []
components:
  securitySchemes:
    agent_jwt:
      type: oauth2
      flows:
        implicit:
          authorizationUrl: ""
          scopes: {}
      x-google-auth:
        issuer: "https://accounts.google.com"
        jwksUri: "https://www.googleapis.com/oauth2/v3/certs"
        audiences:
          - "{oauth_client_id}"
```

For Google ID tokens that a service account gets with `gcloud auth print-identity-token --impersonate-service-account={caller_sa_email} --audiences={jwt_audience}`, set `audiences` to that same `{jwt_audience}` value. See the [Identity Provider JWT Settings Table](client-authentication.md#identity-provider-jwt-settings-table).

To require an API key on `tools/list` instead, name the API key scheme. An API key scheme does not need a root `security` entry:

```yaml
x-google-api-management:
  mcp:
    tools-list:
      security:
        api_key: []
components:
  securitySchemes:
    api_key:
      type: apiKey
      name: x-api-key
      in: header
```

## Shared REST and MCP Quota Enforcement

When an agent invokes a tool via `tools/call`, API Gateway transcodes the call into the underlying REST operation. The transcoded backend request is indistinguishable from a direct REST call, so backends cannot apply MCP-only logic.

- **Shared quota bucket:** Direct REST requests and MCP `tools/call` invocations against the same operation draw from the exact same `x-google-quota` metric and per-project quota limit.
- **Passing credentials from MCP clients:** If the underlying REST operation uses `x-google-quota` (which requires an API key) and `tools/list` requires a JWT (`agent_jwt`), the MCP client MUST send both headers (`Authorization: Bearer {jwt}` and `x-api-key: {api_key}`) on requests to `/mcp`. **Rationale:** Omitting `x-api-key` causes `tools/call` to fail the operation's API key and quota check, while omitting `Authorization` causes `tools/list` to fail with `401`. If `tools-list.security` names the API key scheme instead, the same `x-api-key` header also authenticates `tools/list`.
- **Higher cost for write tools:** Because agent loops can issue rapid tool retries, assign higher `x-google-quota` metric costs or separate lower-limit metrics (`write-requests`) to mutating `POST`, `PUT`, `PATCH`, and `DELETE` operations exposed as MCP tools.

## Sensitive Operations and Header Parameters on MCP

API Gateway does not emit MCP tool annotations such as `destructiveHint` or `readOnlyHint` in `tools/list` responses during Public Preview, and operations returning empty bodies (`HTTP 204`) are not supported as MCP tools.

1. Set `x-google-mcp-tool: false` on administrative, bulk-delete, or internal health-check operations so agents cannot discover or invoke them via `/mcp`.
2. NEVER treat `x-google-mcp-tool: false` as an access control boundary for the operation itself. **Rationale:** Setting `x-google-mcp-tool: false` only omits the operation from MCP `tools/list` and blocks `tools/call`, while the underlying REST path remains live and callable on the gateway URL unless secured with a strict `security` requirement or removed from the OpenAPI specification.
3. NEVER declare trust-bearing identity headers (such as a custom user ID or tenant role header) as OpenAPI `in: header` parameters on an MCP-exposed operation. **Rationale:** API Gateway exposes OpenAPI `header` parameters as top-level properties in the MCP tool `arguments` schema and injects the agent-supplied values into the backend HTTP request headers. (Parameters cannot bind to reserved system headers or headers starting with `x-google-`).
4. For destructive operations that intentionally remain exposed as MCP tools, state in `x-google-mcp-tool.description` when the agent is permitted to call the tool and that the action cannot be undone.

Reference: [OpenAPI 3.x feature limitations - MCP limitations](https://docs.cloud.google.com/api-gateway/docs/openapi-v3-limitations.md.txt)
