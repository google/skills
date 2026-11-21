# OpenAPI 2.0 to 3.x Migration and MCP Extension Reference

- [Why OpenAPI 3.x Is Required for MCP](#why-openapi-3x-is-required-for-mcp): Lines 11-18
- [OpenAPI 2.0 to 3.x Extension Mapping Table](#openapi-20-to-3x-extension-mapping-table): Lines 20-34
- [Swagger 2.0 Construct Conversion Map](#swagger-20-construct-conversion-map): Lines 36-54
- [Configuration of x-google-api-management.mcp and x-google-mcp-tool](#configuration-of-x-google-api-managementmcp-and-x-google-mcp-tool): Lines 56-132
- [Tool Discovery Security (tools/list) vs Tool Calls (tools/call)](#tool-discovery-security-toolslist-vs-tool-calls-toolscall): Lines 134-140
- [How MCP tools/call Arguments Map to REST Requests](#how-mcp-toolscall-arguments-map-to-rest-requests): Lines 142-148
- [Complete Converted Example](#complete-converted-example): Lines 150-251

## Why OpenAPI 3.x Is Required for MCP

Model Context Protocol (MCP) support in Google Cloud API Gateway (Public Preview) requires an OpenAPI 3.x specification: OpenAPI 3.0.x or 3.1.x. The examples in this reference use `openapi: 3.0.4`.

- NEVER add `x-google-api-management.mcp` or `x-google-mcp-tool` to an OpenAPI 2.0 (`swagger: "2.0"`) specification. **Rationale:** MCP is not supported for OpenAPI 2.0, and the MCP extensions are defined only for OpenAPI 3.x.
- If an existing gateway runs an OpenAPI 2.0 specification, start from the spec file in the user's repository. If there is no file, find the active config ID with `gcloud api-gateway gateways describe {gateway_id} --location={region} --project={project_id} --format="value(apiConfig.basename())"`, and print its spec with `gcloud api-gateway api-configs describe {config_id} --api={api_id} --project={project_id} --view=FULL --format=json | python3 -c 'import base64,json,sys; [print(base64.b64decode(d["document"]["contents"]).decode()) for d in json.load(sys.stdin)["openapiDocuments"]]'`. Then convert it with the [Swagger 2.0 Construct Conversion Map](#swagger-20-construct-conversion-map), and compare your result with the [Complete Converted Example](#complete-converted-example).

References: [Supported OpenAPI versions](https://docs.cloud.google.com/api-gateway/docs/openapi-overview.md.txt) and [Modify a gateway to use OpenAPI 3.x](https://docs.cloud.google.com/api-gateway/docs/migrate-oasv3.md.txt)

## OpenAPI 2.0 to 3.x Extension Mapping Table

Standard OpenAPI 2.0-to-3.0 converters update standard OpenAPI fields (`swagger` -> `openapi`, `securityDefinitions` -> `components.securitySchemes`), but leave Google extensions in their legacy OpenAPI 2.0 form. You MUST manually migrate those extensions according to this table:

| Feature | OpenAPI 2.0 (`swagger: "2.0"`) | OpenAPI 3.x | Required Structural Change |
| --- | --- | --- | --- |
| Backends | Inline `x-google-backend` object with `snake_case` fields (`jwt_audience`, `path_translation`, `disable_auth`) | Root `x-google-api-management.backends.{backend_name}` map with `camelCase` fields (`jwtAudience`, `pathTranslation`, `disableAuth`) + `x-google-backend: {backend_name}` string reference | Define named backends in `x-google-api-management.backends` (setting `jwtAudience` or `disableAuth`) and set `x-google-backend` to the string name. |
| JWT Auth | `x-google-issuer`, `x-google-jwks_uri`, `x-google-audiences` directly on the security scheme | `x-google-auth: { issuer, jwksUri, audiences, jwtLocations }` inside `components.securitySchemes.{name}` | Nest the JWT settings inside `x-google-auth`: `x-google-issuer` becomes `issuer`, `x-google-jwks_uri` becomes `jwksUri`, and the comma-separated `x-google-audiences` string becomes an `audiences` list. |
| Quotas | `x-google-management` arrays + `x-google-quota: { metricCosts: { ... } }` | `x-google-api-management.metrics` and `quota.limits` YAML maps + `x-google-quota: { {metric_name}: {cost} }` | Move metrics and limits into `x-google-api-management` as YAML maps (preserving exact metric names), and remove `valueType`, `metricKind`, and `unit`. Set each limit's `values` to a plain integer (no `STANDARD` key), and remove the `metricCosts` wrapper. |
| Endpoints (CORS) | `x-google-endpoints` | `servers` entry with `x-google-endpoint: { allowCors: true }` | Only one `servers` entry can carry `x-google-endpoint`. Remove the legacy `name` field. For `basePath`, see the [Swagger 2.0 Construct Conversion Map](#swagger-20-construct-conversion-map). |
| Route Catch-All | `x-google-allow` (`all` or `configured`) | Unsupported in OpenAPI 3.x | Remove `x-google-allow`. API Gateway does not support it in OpenAPI 3.x. |
| API Name | `x-google-api-name` | `x-google-api-management.apiName` | Move `x-google-api-name` into `x-google-api-management.apiName`. |
| MCP Server | Unsupported | `x-google-api-management.mcp` (root) and `x-google-mcp-tool` (operation level) | Enable MCP globally or per operation. |

Reference: [OpenAPI 3.x extensions in API Gateway](https://docs.cloud.google.com/api-gateway/docs/oasv3-extensions.md.txt)

## Swagger 2.0 Construct Conversion Map

Convert these standard Swagger 2.0 constructs as shown. Where a row says to ask the user, the choice belongs to the user.

| Swagger 2.0 construct | OpenAPI 3.x for API Gateway MCP |
| --- | --- |
| `basePath: /v2` (with or without `host`) | `servers: [{url: "https://{managed_service}/v2", x-google-endpoint: {}}]`, where `{managed_service}` is `gcloud api-gateway apis describe {api_id} --project={project_id} --format="value(managedService)"`. REST paths stay under `/v2`. MCP stays at `https://{default_hostname}/mcp`. |
| Root `x-google-backend: {address, path_translation}` | Named backend under `x-google-api-management.backends` (`address`, `pathTranslation`) + root `x-google-backend: {backend_name}`. For a Cloud Run backend, set `jwtAudience` to the Cloud Run service URL. |
| `in: body` parameter | `requestBody.content.application/json.schema`. |
| `definitions` and `#/definitions/{name}` | `components.schemas` and `#/components/schemas/{name}`. |
| `securityDefinitions` | `components.securitySchemes`. |
| `consumes` / `produces` | Move the media types into `requestBody.content` and `responses.content`. Use `application/json` for tool operations: `tools/call` sends the request body as JSON in `arguments.body`, and tool responses are limited to UTF-8 text. |
| `in: formData` (`application/x-www-form-urlencoded`) | `requestBody` with that media type. Recommendation: set `x-google-mcp-tool: false`, because MCP clients pass the request body as JSON in `arguments.body`. |
| `type: file` (file upload) | `requestBody` with `multipart/form-data` and a `type: string, format: binary` property. Recommendation: set `x-google-mcp-tool: false`, because MCP tool arguments are JSON values. |
| `collectionFormat` array parameter | API Gateway supports only primitive types in request parameters. Ask the user: keep the array for REST and set `x-google-mcp-tool: false`, or change the parameter to a primitive type (such as a comma-separated `string`) that the backend accepts. |
| `deprecated: true` operation | Keep it for REST. Ask the user before you expose it as a tool, because agents can start to depend on it. |
| Operation with only `4xx` responses | Add the success response that the backend returns, with its JSON schema. Tools cannot return an empty body (`HTTP 204`). |
| `DELETE` or other destructive operation | Ask the user before you expose it. If you expose it, warn in the tool description, because API Gateway does not emit `destructiveHint` annotations. |
| No `security` | Add the scheme that the user asks for to `x-google-api-management.mcp.tools-list.security`. If it is a JWT scheme, also list it in the root `security`. See [Complete Converted Example](#complete-converted-example). |

## Configuration of `x-google-api-management.mcp` and `x-google-mcp-tool`

You can enable MCP globally at the document root (`x-google-api-management.mcp: true` or object form) and customize or opt out individual operations using `x-google-mcp-tool` at the operation level.

- Place `x-google-mcp-tool` ONLY on individual HTTP operation objects (`get`, `post`, `put`, `patch`, `delete`). NEVER place `x-google-mcp-tool` at the path item level. **Rationale:** API Gateway rejects specifications that declare `x-google-mcp-tool` at the path level.
- Every operation MUST have an `operationId`, with or without MCP. **Rationale:** API Gateway rejects an API config that has an operation without an `operationId`.
- Every exposed operation MUST also have a configured backend (`x-google-backend` at root or operation level), a unique tool name that matches `[A-Za-z0-9_.-]{1,128}` (`x-google-mcp-tool.name`, or else the `operationId`), and a non-empty description (`x-google-mcp-tool.description`, operation `description`, or `summary`).
- Keep all MCP operations in one OpenAPI document. **Rationale:** If an API config has several OpenAPI documents, API Gateway serves the MCP tools of only one of them, and the tools of the other documents are missing without an error.

```yaml
openapi: 3.0.4
info:
  title: Orders API
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
      pathTranslation: APPEND_PATH_TO_ADDRESS
x-google-backend: orders-backend
components:
  securitySchemes:
    api_key:
      type: apiKey
      name: x-api-key
      in: header
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
security:
  - api_key: []
    agent_jwt: []
paths:
  /v1/orders/{orderId}:
    get:
      operationId: getOrderStatus
      summary: Get order status
      description: Returns fulfillment status, carrier tracking number, and ETA for an order.
      x-google-mcp-tool:
        name: get_order_status
        description: >-
          Look up the fulfillment status, carrier tracking number, and delivery ETA for a customer order.
          Call this tool when the user asks where an order is or needs the SKU before creating a return.
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Order details
  /v1/admin/orders/purge:
    delete:
      operationId: purgeOrders
      summary: Purge archived orders
      description: Administrative operation to purge archived order records.
      x-google-mcp-tool: false
      responses:
        "200":
          description: Purge status
```

Reference: [Configure Model Context Protocol](https://docs.cloud.google.com/api-gateway/docs/mcp-configure.md.txt)

## Tool Discovery Security (`tools/list`) vs Tool Calls (`tools/call`)

| MCP Method | Default Security | How to Configure | Critical Constraint |
| --- | --- | --- | --- |
| `initialize` and `notifications/initialized` | Unauthenticated | No configuration | These protocol lifecycle methods are always unauthenticated. |
| `tools/list` | Unauthenticated by default | `x-google-api-management.mcp.tools-list.security` (+ the same scheme in the root `security` list for a JWT scheme) | Must reference **exactly one** scheme in `components.securitySchemes`: a JWT scheme (`oauth2` with `x-google-auth`) or an API key scheme (`apiKey`). For a JWT scheme, the root `security` list MUST also reference it (API Gateway rejects the config otherwise), and that root entry also requires the JWT on every REST operation without its own `security`. If the root list has an API key scheme, put the JWT in the same requirement object (AND), because API Gateway does not support alternative (OR) requirements with an API key. For an API key scheme, use `in: header` and `name: x-api-key`, because `tools/list` reads API keys only from the `x-api-key` header. Configuring `mcp` as an object also enables MCP globally for all eligible operations. |
| `tools/call` | Inherits the operation's `security` requirement | Operation or root `security` block (`apiKey` and/or `oauth2` JWT) | Shares the exact same authentication and `x-google-quota` allocation as direct REST calls to that operation. |

## How MCP `tools/call` Arguments Map to REST Requests

When an MCP client invokes `tools/call`, API Gateway synthesizes the tool's `inputSchema` and maps `params.arguments` into the outbound HTTP REST request as follows:

1. **Path and query parameters (`in: path`, `in: query`):** Become top-level properties inside `params.arguments`, keyed by their exact OpenAPI parameter `name` (for example, `"arguments": {"orderId": "ORD-10042"}`).
2. **JSON request body (`requestBody`):** Nested under a single top-level property named `body` inside `params.arguments` (for example, `"arguments": {"orderId": "ORD-10042", "body": {"itemSku": "SKU-1", "reason": "DEFECTIVE"}}`). Passing body fields at the top level of `arguments` without the `body` wrapper fails validation with JSON-RPC error `-32602` (`Invalid tool arguments`).
3. **Header parameters (`in: header`):** Become top-level properties inside `params.arguments` and are injected as HTTP headers on the backend call. You cannot bind parameters to reserved system headers or headers starting with `x-google-`.

## Complete Converted Example

This example is a Swagger 2.0 API with `basePath: /v2`, a root `x-google-backend`, a `GET`, a `POST` with a body, and a `DELETE`, converted for MCP. To list or call tools, a caller needs a valid Google ID token whose audience is `{jwt_audience}`.

```yaml
openapi: 3.0.4
info:
  title: Petstore API
  version: 1.4.0
servers:
  - url: https://{managed_service}/v2
    x-google-endpoint: {}
x-google-api-management:
  mcp:
    tools-list:
      security:
        google_id_token: []
  backends:
    petstore-backend:
      address: https://{backend_service}-{project_number}.{region}.run.app
      jwtAudience: https://{backend_service}-{project_number}.{region}.run.app
      pathTranslation: APPEND_PATH_TO_ADDRESS
x-google-backend: petstore-backend
security:
  - google_id_token: []
components:
  securitySchemes:
    google_id_token:
      type: oauth2
      flows:
        implicit:
          authorizationUrl: ""
          scopes: {}
      x-google-auth:
        issuer: https://accounts.google.com
        jwksUri: https://www.googleapis.com/oauth2/v3/certs
        audiences:
          - "{jwt_audience}"
  schemas:
    Pet:
      type: object
      required: [name]
      properties:
        id: {type: integer, format: int64}
        name: {type: string, description: 'Pet name, for example "Buddy".'}
        status: {type: string, enum: [available, pending, sold]}
paths:
  /pet/{petId}:
    get:
      operationId: getPetById
      summary: Find pet by ID
      x-google-mcp-tool:
        name: get_pet
        description: >-
          Get one pet by its numeric ID. Use this when the user asks about a specific pet.
      parameters:
        - {name: petId, in: path, required: true, schema: {type: integer, format: int64}}
      responses:
        "200":
          description: The pet
          content:
            application/json:
              schema: {$ref: '#/components/schemas/Pet'}
    delete:
      operationId: deletePet
      summary: Delete a pet
      x-google-mcp-tool: false
      parameters:
        - {name: petId, in: path, required: true, schema: {type: integer, format: int64}}
      responses:
        "200":
          description: The pet was deleted
  /pet:
    post:
      operationId: addPet
      summary: Add a new pet to the store
      x-google-mcp-tool:
        name: add_pet
        description: >-
          Add a new pet to the store catalog. Use this when the user wants to list a new pet for sale.
      requestBody:
        required: true
        content:
          application/json:
            schema: {$ref: '#/components/schemas/Pet'}
      responses:
        "200":
          description: The created pet
          content:
            application/json:
              schema: {$ref: '#/components/schemas/Pet'}
```

Values to fill in:

- `{managed_service}`: `gcloud api-gateway apis describe {api_id} --project={project_id} --format="value(managedService)"`.
- `{jwt_audience}`: the audience that callers request when they mint a token, such as `https://{managed_service}`. Do not use an IP address or an internal address, because API Gateway does not accept them in the `aud` claim. A caller gets a matching token with `gcloud auth print-identity-token --impersonate-service-account={caller_sa_email} --audiences={jwt_audience}`. The token has `iss: https://accounts.google.com` and `aud: {jwt_audience}`.
- API Gateway checks the token claims against the scheme. It does not check the IAM permissions that you granted to the caller's service account. A Google ID token scheme accepts every caller that can get a Google ID token with this audience. To accept only one service account, check the `email` claim in the backend (API Gateway forwards the JWT payload in the `X-Apigateway-Api-Userinfo` header), or use a self-signed JWT with `issuer` set to the service account email.

References:
- [Using Google ID tokens to authenticate users](https://docs.cloud.google.com/api-gateway/docs/authenticating-users-googleid.md.txt)
- [Authentication between services](https://docs.cloud.google.com/api-gateway/docs/authenticate-service-account.md.txt)
