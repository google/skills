# OpenAPI 3.x Extensions and Limits in API Gateway

- [New Spec Template](#new-spec-template): Lines 11-69
- [x-google-api-management](#x-google-api-management): Lines 71-85
- [Backends](#backends): Lines 87-113
- [Security](#security): Lines 115-145
- [Quotas](#quotas): Lines 147-157
- [Servers, Base Path, and CORS](#servers-base-path-and-cors): Lines 159-167
- [Paths, Operations, and Schemas](#paths-operations-and-schemas): Lines 169-183

## New Spec Template

Replace each `{placeholder}`. The template has a Cloud Run backend, an API key on every operation, and one quota.

```yaml
openapi: 3.0.4
info:
  title: "{api_title}"
  version: 1.0.0
servers:
  - url: /v1
    x-google-endpoint: {}
x-google-api-management:
  backends:
    main-backend:
      address: "https://{cloud_run_service_url_host}"
      pathTranslation: APPEND_PATH_TO_ADDRESS
  metrics:
    read-requests:
      displayName: Read requests
  quota:
    limits:
      read-limit:
        metric: read-requests
        values: 600
x-google-backend: main-backend
security:
  - api_key: []
components:
  securitySchemes:
    api_key:
      type: apiKey
      name: x-api-key
      in: header
paths:
  /items/{itemId}:
    get:
      operationId: getItem
      summary: Get one item by ID.
      x-google-quota:
        read-requests: 1
      parameters:
        - name: itemId
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: The item.
```

With this template, a request to `/v1/items/42` reaches the backend as `/v1/items/42`, because `APPEND_PATH_TO_ADDRESS` keeps the base path. The Cloud Run service must serve the `/v1` paths.

API keys work only after you enable the managed service of the API:

1. Get the name of the managed service with `gcloud api-gateway apis describe {api_id} --project={project_id} --format="value(managedService)"`.
2. Run `gcloud services enable {managed_service} --project={project_id}`.
3. Enable the managed service also in each project that creates API keys for the API. **Rationale:** API Gateway rejects an API key unless the API is enabled in the project that created the key.

## x-google-api-management

Put this required extension at the root of the spec.

| Field | Required | Use |
| --- | --- | --- |
| `backends` | Yes | A map from each backend name to its settings. See [Backends](#backends). |
| `metrics` | No | A map from each quota metric name to `{displayName}`. See [Quotas](#quotas). |
| `quota` | No | `limits`: a map from each limit name to `{metric, values}`. See [Quotas](#quotas). |
| `apiName` | No | A name for the operations in this document: a lowercase letter, then at most 39 lowercase letters or digits, such as `orders`. API Gateway also accepts a dotted name of at most 40 characters, such as `example.orders`. API Gateway rejects two documents in one API config with the same `apiName` and the same major `info.version`. A document without `apiName` uses the name of the managed service, so give each document of an API config its own `apiName`. |
| `mcp` | No | Enables MCP tools. Use the `api-gateway-mcp-server` skill. |
| `ai` | No | Model routing. An API config cannot have both MCP and model routing. It also cannot have model-routing operations and other operations, in one file or across files. |
| `modelRouter` | No | The default model router of the API, for a request without an operation-level `x-google-model-router`. |

API Gateway rejects the whole block if it has another field, such as the OpenAPI 2.0 field `unit` on a quota limit.

## Backends

| Field | Default | Rules |
| --- | --- | --- |
| `address` | None | Required. An `https://` or `http://` URL with a fully qualified hostname. API Gateway rejects an IP address, `localhost`, a metadata server, an `.internal` hostname, and a hostname segment longer than 63 characters. |
| `jwtAudience` | The full `address`, with its path | The audience of the Google ID token that the gateway sends to the backend. Set it to the OAuth client ID for an App Engine or IAP backend. For a Cloud Run address that has a path, set it to the service URL without the path, because Cloud Run expects its service URL. |
| `disableAuth` | `false` | Set `true` only for a backend that does not check tokens. Then the gateway sends no ID token. Set only one of `jwtAudience` and `disableAuth`. |
| `pathTranslation` | `APPEND_PATH_TO_ADDRESS` for a root `x-google-backend`, `CONSTANT_ADDRESS` for an operation-level one | Always set it. If the root and an operation reference one backend without `pathTranslation`, each reference uses its own default. |
| `deadline` | `15.0` | Seconds to wait for a full response. Some gateways reject a value above `600` when you create or update the gateway. A streaming gateway accepts up to `3600`. |
| `protocol` | `http/1.1` | `http/1.1` or `h2`. Use `h2` only with an `https://` address. gRPC needs `h2`, and WebSockets need `http/1.1`. |

Path translation examples:

| `pathTranslation` | `address` | Server `url` | Request | Backend request |
| --- | --- | --- | --- | --- |
| `APPEND_PATH_TO_ADDRESS` | `https://inventory-abc123-uc.a.run.app` | none | `/items/42` | `https://inventory-abc123-uc.a.run.app/items/42` |
| `APPEND_PATH_TO_ADDRESS` | `https://inventory-abc123-uc.a.run.app` | `/v1` | `/v1/items/42` | `https://inventory-abc123-uc.a.run.app/v1/items/42` |
| `CONSTANT_ADDRESS` | `https://us-central1-{project_id}.cloudfunctions.net/getItem` | none | `/items/42` | `https://us-central1-{project_id}.cloudfunctions.net/getItem?itemId=42` |

The OpenAPI path in each row is `/items/{itemId}`.

- Use `APPEND_PATH_TO_ADDRESS` for a backend that routes by path, such as a Cloud Run service, a GKE service, or an App Engine app. The backend gets the full request path, with the base path.
- Use `CONSTANT_ADDRESS` for a backend that serves one operation at a fixed URL, such as a Cloud Run function.
- Set `x-google-backend` at the root or on an operation, never on a path item. **Rationale:** API Gateway rejects `x-google-backend` at the path level.
- For a Cloud Run backend that requires authentication, keep the default token, and grant the gateway service account the Cloud Run Invoker role (`roles/run.invoker`) on the service.

Reference: [OpenAPI 3.x extensions: Backends](https://docs.cloud.google.com/api-gateway/docs/oasv3-extensions.md.txt)

## Security

JWT scheme fields (`x-google-auth` in a `type: oauth2` security scheme):

| Field | Rules |
| --- | --- |
| `issuer` | The `iss` claim of the token, such as `https://accounts.google.com` for Google ID tokens or `https://securetoken.google.com/{firebase_project_id}` for Firebase. |
| `jwksUri` | Required, also in a scheme that no operation uses. The URL of the public keys, in JWK set or X509 format, such as `https://www.googleapis.com/oauth2/v3/certs` for Google ID tokens. API Gateway applies the same hostname rules as for a backend `address`. |
| `audiences` | A YAML list of the accepted `aud` values. |
| `jwtLocations` | A list of `{header, valuePrefix}` or `{query}` entries. By default, API Gateway reads the token from the `Authorization: Bearer` header, the `X-Goog-Iap-Jwt-Assertion` header, or the `access_token` query parameter. |

Give the scheme an OAuth flow, such as `flows: {implicit: {authorizationUrl: "", scopes: {}}}`. API Gateway reads the JWT settings only from `x-google-auth`. It adds a JWT provider for every `oauth2` scheme, also for a scheme that no operation uses, and it rejects a provider without `jwksUri`. Remove the `oauth2` schemes that you do not use, such as documentation-only schemes from a converter.

API key scheme: `type: apiKey` with `in: header` and `name: x-api-key`, or with `in: query` and `name: key` or `api_key`. API Gateway ignores every other API key scheme, with only a warning. Then an operation that requires only that scheme accepts calls without a key.

Security requirement rules:

| Rule | Example |
| --- | --- |
| AND of an API key and a JWT is supported. | `security: [{api_key: [], firebase: []}]` |
| AND of two JWT schemes is not supported. | Do not write `security: [{firebase: [], google_id_token: []}]`. |
| OR of JWT schemes is supported. | `security: [{firebase: []}, {google_id_token: []}]` |
| OR is supported only if every alternative has the API key, or none has it. | `security: [{api_key: [], firebase: []}, {api_key: [], google_id_token: []}]`. Do not write `security: [{firebase: []}, {api_key: []}]`. |
| Optional security (`{}`) works only for an API key. | `security: [{api_key: []}, {}]` |
| Every named scheme must exist in `components.securitySchemes`. | API Gateway rejects the API config otherwise. |

- The root `security` list applies to every operation that does not set its own `security`. To remove the root requirement from one operation, set `security: []` on it.
- API Gateway does not check OAuth scopes. Check scopes in the backend.
- API Gateway checks the token claims against the scheme. It does not check the IAM roles of the caller. A Google ID token scheme accepts every caller that can get a token with an accepted audience. To accept only some callers, check the claims in the backend: API Gateway forwards the JWT payload in the `X-Apigateway-Api-Userinfo` header.

Reference: [OpenAPI 3.x feature limitations](https://docs.cloud.google.com/api-gateway/docs/openapi-v3-limitations.md.txt)

## Quotas

1. Define each metric in `x-google-api-management.metrics`, such as `read-requests: {displayName: Read requests}`.
2. Define each limit in `x-google-api-management.quota.limits`, such as `read-limit: {metric: read-requests, values: 600}`. `values` is the number of requests per minute for each consumer Google Cloud project. Give each metric that an operation uses a limit, because API Gateway rejects a charged metric without a limit.
3. Set `x-google-quota: {read-requests: 1}` on each operation that counts against the metric. The value is the cost of one request. **Rationale:** in OpenAPI 3.x, API Gateway ignores `x-google-quota` at the root or path level, without an error, even where a documentation example shows it at the root.
4. Require an API key in every security alternative of each operation that has `x-google-quota`. **Rationale:** API Gateway uses the API key to identify the consumer project that the quota counts.
5. Keep the metric and limit names the same in every API config of the API. **Rationale:** metrics and limits apply to the whole API, and the newest API config replaces them. If you rename or remove a metric, a gateway that still serves an older API config returns HTTP 500 (`Failed to call Service Control Quota`) on its quota-enforced operations.

For per-consumer limits, consumer overrides, and HTTP 429 handling, use the `api-gateway-backend-security-and-rate-limiting` skill if it is installed.

Reference: [Quotas apply to the whole API](https://docs.cloud.google.com/api-gateway/docs/quotas-overview.md.txt)

## Servers, Base Path, and CORS

- Put `x-google-endpoint` on one `servers` entry. Its URL path is the base path of the API. **Rationale:** API Gateway permits only one such entry, and it ignores every `servers` entry without `x-google-endpoint`. With no such entry, the API has no base path.
- Use a relative URL, such as `url: /v1`. If the API has a managed service that you chose, and not the default `*.apigateway.{project_id}.cloud.goog` service, use `url: https://{managed_service}/v1`. **Rationale:** API Gateway reads the service name from the URL host for such an API.
- A relative URL must start with `/`. Do not set `url` to null, and do not use a custom port or a server variable such as `{region}`. **Rationale:** API Gateway rejects these URLs. An empty `url` or `/` gives no base path.
- If an API config has several OpenAPI files, give each file a server with the same `x-google-endpoint` settings and the same host, and give each file its own `apiName`. The base path can differ.
- `allowCors: true` makes API Gateway pass CORS requests, including preflight `OPTIONS` requests, to the backend. API Gateway does not add CORS headers. Make the backend answer each preflight request and add the CORS response headers.

Reference: [OpenAPI 3.x feature limitations: Servers](https://docs.cloud.google.com/api-gateway/docs/openapi-v3-limitations.md.txt)

## Paths, Operations, and Schemas

- Give every operation a unique `operationId` and a `responses` object. API Gateway removes the characters other than letters, digits, and underscores from each `operationId`, and capitalizes the first letter. The results must also be unique. For example, `getItem` and `GetItem` conflict, but `get_item` and `getItem` do not.
- Make each path variable a whole segment, such as `/items/{itemId}`. API Gateway rejects a partial segment, such as `/items/prefix_{id}` or `/{a}{b}`.
- Give each path variable a parameter with `in: path` and `required: true`.
- Start each variable name with a letter, and use only letters, digits, underscores, dots, and dashes, with at most 30 characters. Use at most 15 path parameters in a path. Keep the names unique after API Gateway converts them to snake_case: `bookId` and `book_id` conflict. Keep each path at 512 characters or less.
- For a variable that matches several segments, write `{name}` and set `x-google-parameter: {pattern: "**"}` on the parameter. Use it only on the last segment of the path. OpenAPI 3.x rejects `{name=*}` and `{name=**}`.
- Give each schema one `type`. API Gateway rejects an OpenAPI 3.1 type list, such as `type: ["string", "null"]`. In OpenAPI 3.0, use `nullable: true` for a field that can be null.
- Use a primitive type or an array of a primitive type for a request parameter. API Gateway rejects an object parameter.
- API Gateway does not check required parameters, parameter types, request bodies, or content types. It forwards each request to the backend, so the backend must validate the input.
- Use local references, such as `$ref: "#/components/schemas/Item"`. API Gateway rejects a `$ref` to a URL. Keep the schemas in the same file.
- Use `$ref` instead of YAML anchors and aliases. API Gateway rejects an alias to a mapping, and the error (`string found, object expected`) does not name the alias.
- Keep the files of one API config at 10 MB in total, and at most 50 files.

Reference: [OpenAPI 3.x feature limitations](https://docs.cloud.google.com/api-gateway/docs/openapi-v3-limitations.md.txt) and [Path templating](https://docs.cloud.google.com/api-gateway/docs/path-templating.md.txt)
