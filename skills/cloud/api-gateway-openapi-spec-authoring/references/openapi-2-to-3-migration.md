# OpenAPI 2.0 to 3.x Migration for API Gateway

- [Migration Steps](#migration-steps): Lines 9-18
- [Extension Mapping Table](#extension-mapping-table): Lines 20-35
- [Extension Examples](#extension-examples): Lines 37-151
- [Swagger 2.0 Construct Conversion Map](#swagger-20-construct-conversion-map): Lines 153-170
- [Complete Converted Example](#complete-converted-example): Lines 172-384

## Migration Steps

1. Get the OpenAPI 2.0 spec: the file in the user's repository, or the spec of the active API config of the gateway (see step 1 of the workflow in `SKILL.md`). If the spec has no `x-google-backend`, ask the user for the backend URL. Do not invent an address.
2. Convert the standard fields. The conversion utility in [Swagger Editor](https://editor-next.swagger.io/) changes `swagger` to `openapi`, `securityDefinitions` to `components.securitySchemes`, `definitions` to `components.schemas`, and `in: body` parameters to `requestBody`. To convert by hand, use the [Swagger 2.0 Construct Conversion Map](#swagger-20-construct-conversion-map).
3. Move each Google extension with the [Extension Mapping Table](#extension-mapping-table). **Rationale:** a converter leaves every `x-google-*` extension in its OpenAPI 2.0 form, and API Gateway rejects most of them in an OpenAPI 3.x spec.
4. Add `x-google-endpoint: {}` to the `servers` entry that has the base path. **Rationale:** a converter writes `servers` without `x-google-endpoint`, and API Gateway ignores such entries, so calls to the base path return HTTP 404.
5. Set `pathTranslation` on every backend. Keep the behavior of the OpenAPI 2.0 spec: OpenAPI 2.0 has the same defaults (`APPEND_PATH_TO_ADDRESS` for a root backend, `CONSTANT_ADDRESS` for an operation-level backend).
6. Run `python3 scripts/validate_apigw_openapi.py --spec={spec_file}`. Fix every error. Fix every warning, or tell the user why you keep it.

Reference: [Modify a gateway to use OpenAPI 3.x](https://docs.cloud.google.com/api-gateway/docs/migrate-oasv3.md.txt)

## Extension Mapping Table

| Feature | OpenAPI 2.0 | OpenAPI 3.x | Required change |
| --- | --- | --- | --- |
| Backends | Inline `x-google-backend` object at the root or on an operation, with `snake_case` fields (`address`, `jwt_audience`, `disable_auth`, `path_translation`, `deadline`, `protocol`) | Root `x-google-api-management.backends.{backend_name}` with `camelCase` fields (`address`, `jwtAudience`, `disableAuth`, `pathTranslation`, `deadline`, `protocol`) + `x-google-backend: {backend_name}` | Define one named backend for each distinct backend object, and replace each object with the name. Compare all fields, not only `address`. If the root and an operation use the same object without `path_translation`, define two backends: one with `APPEND_PATH_TO_ADDRESS` for the root, and one with `CONSTANT_ADDRESS` for the operation. API Gateway rejects an inline object in OpenAPI 3.x. |
| JWT authentication | `x-google-issuer`, `x-google-jwks_uri`, `x-google-audiences` (a comma-separated string), and `x-google-jwt-locations` on the security definition. Older specs use `x-issuer` and `x-jwks_uri`. | `x-google-auth: {issuer, jwksUri, audiences, jwtLocations}` in `components.securitySchemes.{scheme_name}` | Nest the values in `x-google-auth`. Change `audiences` to a YAML list: split the string at the commas, and remove the spaces. In each JWT location, `value_prefix` becomes `valuePrefix`. |
| API key | `securityDefinitions` entry with `type: apiKey` | `components.securitySchemes` entry with `type: apiKey` | No change other than the move. |
| Metrics and quota limits | `x-google-management.metrics` and `quota.limits` lists, with `name`, `valueType`, `metricKind`, `unit`, and `values: {STANDARD: N}` | `x-google-api-management.metrics` and `quota.limits` maps, keyed by name, with `values: N` | Make each list a map keyed by the old `name`. Keep only `displayName` on each metric, and only `metric` and `values` on each limit. API Gateway rejects the other fields, such as `valueType`, `metricKind`, and `unit`, and it uses the unit `1/min/{project}`. Keep each metric name exactly the same. |
| Quota cost | `x-google-quota: {metricCosts: {metric_name: cost}}` | `x-google-quota: {metric_name: cost}` on each operation | Remove the `metricCosts` wrapper. In OpenAPI 3.x, API Gateway ignores `x-google-quota` at the root or path level. |
| Base path | `basePath` | `servers: [{url: {basePath}, x-google-endpoint: {}}]` | Make sure that one `servers` entry has `x-google-endpoint`, even an empty `{}`. A converter does not add it. |
| Endpoint and CORS | Root `x-google-endpoints: [{name, allowCors}]` | `servers: [{url, x-google-endpoint: {allowCors}}]` | Move `allowCors` (and `target`, if set) to one `servers` entry, and remove `name`. |
| API name | `x-google-api-name` | `x-google-api-management.apiName` | Move the value. |
| Catch-all routing | `x-google-allow: all` | Not supported | Remove it, and list every path. To forward every other path as OpenAPI 2.0 did, see the `x-google-allow` row of the [Swagger 2.0 Construct Conversion Map](#swagger-20-construct-conversion-map). |
| Other OpenAPI 2.0 extensions | `x-google-deprecated`, `x-google-experimental-authorization`, `x-google-backend-url`, `x-google-backend-deadline`, and `x-security` | Not supported | Remove `x-google-deprecated` and `x-google-experimental-authorization`. Move a backend URL or deadline to `x-google-api-management.backends`, and move `x-security` to the OpenAPI `security` field. |

Reference: [OpenAPI 3.x extensions in API Gateway](https://docs.cloud.google.com/api-gateway/docs/oasv3-extensions.md.txt)

## Extension Examples

Backend, OpenAPI 2.0:

```yaml
x-google-backend:
  address: https://orders-abc123-uc.a.run.app
  path_translation: APPEND_PATH_TO_ADDRESS
```

Backend, OpenAPI 3.x:

```yaml
x-google-api-management:
  backends:
    orders-backend:
      address: https://orders-abc123-uc.a.run.app
      pathTranslation: APPEND_PATH_TO_ADDRESS
x-google-backend: orders-backend
```

JWT scheme, OpenAPI 2.0:

```yaml
securityDefinitions:
  firebase:
    type: oauth2
    flow: implicit
    authorizationUrl: ""
    x-google-issuer: "https://securetoken.google.com/{firebase_project_id}"
    x-google-jwks_uri: "https://www.googleapis.com/service_accounts/v1/metadata/x509/securetoken@system.gserviceaccount.com"
    x-google-audiences: "{firebase_project_id}"
```

JWT scheme, OpenAPI 3.x:

```yaml
components:
  securitySchemes:
    firebase:
      type: oauth2
      flows:
        implicit:
          authorizationUrl: ""
          scopes: {}
      x-google-auth:
        issuer: "https://securetoken.google.com/{firebase_project_id}"
        jwksUri: "https://www.googleapis.com/service_accounts/v1/metadata/x509/securetoken@system.gserviceaccount.com"
        audiences:
          - "{firebase_project_id}"
```

Quota, OpenAPI 2.0:

```yaml
x-google-management:
  metrics:
    - name: read-requests
      displayName: Read requests
      valueType: INT64
      metricKind: DELTA
  quota:
    limits:
      - name: read-limit
        metric: read-requests
        unit: "1/min/{project}"
        values:
          STANDARD: 600
paths:
  /orders:
    get:
      x-google-quota:
        metricCosts:
          read-requests: 1
```

Quota, OpenAPI 3.x:

```yaml
x-google-api-management:
  metrics:
    read-requests:
      displayName: Read requests
  quota:
    limits:
      read-limit:
        metric: read-requests
        values: 600
paths:
  /orders:
    get:
      x-google-quota:
        read-requests: 1
```

Endpoint, base path, and API name, OpenAPI 2.0:

```yaml
basePath: /v1
x-google-endpoints:
  - name: "orders-api-1a2b3c.apigateway.{project_id}.cloud.goog"
    allowCors: true
x-google-api-name: orders
```

Endpoint, base path, and API name, OpenAPI 3.x:

```yaml
servers:
  - url: /v1
    x-google-endpoint:
      allowCors: true
x-google-api-management:
  apiName: orders
```

## Swagger 2.0 Construct Conversion Map

| Swagger 2.0 construct | OpenAPI 3.x for API Gateway |
| --- | --- |
| `host`, `basePath: /v1`, and `schemes` | `servers: [{url: /v1, x-google-endpoint: {}}]`. Remove `host` and `schemes`. Use `url: https://{managed_service}/v1` instead if the API uses a managed service that you chose, and not the default `*.apigateway.{project_id}.cloud.goog` service, because API Gateway then reads the service name from the URL host. Use it also if the user shares the spec with API consumers. `{managed_service}` is the output of `gcloud api-gateway apis describe {api_id} --project={project_id} --format="value(managedService)"`. |
| Root `x-google-backend` object | A named backend in `x-google-api-management.backends` + root `x-google-backend: {backend_name}`. |
| Operation `x-google-backend` object | A named backend + operation `x-google-backend: {backend_name}`. If the object has no `path_translation`, set `pathTranslation: CONSTANT_ADDRESS` to keep the OpenAPI 2.0 behavior. Do not share this backend with the root if the root object has no `path_translation` either. |
| `in: body` parameter | `requestBody.content.application/json.schema`. |
| `in: formData` parameters | `requestBody` with the `application/x-www-form-urlencoded` or `multipart/form-data` media type. |
| Parameter `type`, `format`, and `items` | Move them into the parameter `schema`. |
| `collectionFormat: csv` | `style: form` and `explode: false` (query), or `style: simple` (path or header), with an array `schema` of a primitive type. API Gateway does not check or split the value. The backend gets the comma-separated string and must parse it. |
| `definitions` and `#/definitions/{name}` | `components.schemas` and `#/components/schemas/{name}`. |
| Root `parameters` and `responses` | `components.parameters` and `components.responses`. |
| `securityDefinitions` | `components.securitySchemes`. An oauth2 `flow: implicit` with `authorizationUrl: {url}` becomes `flows: {implicit: {authorizationUrl: {url}, scopes: {}}}`. Map `accessCode` to `authorizationCode`, `application` to `clientCredentials`, and `password` to `password`, and keep `tokenUrl`. |
| `consumes` and `produces` | The media types in `requestBody.content` and in each `responses.{code}.content`. |
| Response `schema` | `responses.{code}.content.application/json.schema`. You can quote each status code key, such as `"200"`, to keep the keys strings. |
| Path template `{name=**}` | `{name}`, with `x-google-parameter: {pattern: "**"}` on the path parameter. OpenAPI 3.x rejects the `{name=*}` and `{name=**}` syntax. |
| `x-google-allow: all` | Remove it. To keep the OpenAPI 2.0 behavior, add a path such as `/{path}` whose `path` parameter has `in: path`, `required: true`, and `x-google-parameter: {pattern: "**"}`. Add one operation for each of `get`, `post`, `put`, `patch`, and `delete`, each with a unique `operationId` and `security: []`. **Rationale:** OpenAPI 2.0 passed these calls to the backend without an API key or a JWT. Remove `security: []` only if the user wants the gateway to check credentials on these paths. |

## Complete Converted Example

The OpenAPI 2.0 input has a base path, a root Cloud Run backend, an operation-level Cloud Run functions backend, an API key, a Firebase JWT, a quota, and `x-google-allow`:

```yaml
swagger: "2.0"
info:
  title: Inventory API
  version: 1.2.0
host: "inventory-api-1a2b3c.apigateway.{project_id}.cloud.goog"
basePath: /v1
schemes:
  - https
x-google-allow: all
x-google-backend:
  address: https://inventory-abc123-uc.a.run.app
  path_translation: APPEND_PATH_TO_ADDRESS
  deadline: 30.0
x-google-management:
  metrics:
    - name: read-requests
      displayName: Read requests
      valueType: INT64
      metricKind: DELTA
  quota:
    limits:
      - name: read-limit
        metric: read-requests
        unit: "1/min/{project}"
        values:
          STANDARD: 600
securityDefinitions:
  api_key:
    type: apiKey
    name: key
    in: query
  firebase:
    type: oauth2
    flow: implicit
    authorizationUrl: ""
    x-google-issuer: "https://securetoken.google.com/{firebase_project_id}"
    x-google-jwks_uri: "https://www.googleapis.com/service_accounts/v1/metadata/x509/securetoken@system.gserviceaccount.com"
    x-google-audiences: "{firebase_project_id}"
security:
  - api_key: []
paths:
  /items/{itemId}:
    get:
      operationId: getItem
      x-google-quota:
        metricCosts:
          read-requests: 1
      parameters:
        - name: itemId
          in: path
          required: true
          type: string
      responses:
        200:
          description: The item.
          schema:
            $ref: "#/definitions/Item"
  /items:
    post:
      operationId: createItem
      security:
        - api_key: []
          firebase: []
      parameters:
        - name: item
          in: body
          required: true
          schema:
            $ref: "#/definitions/Item"
      responses:
        200:
          description: The created item.
          schema:
            $ref: "#/definitions/Item"
  /reports/daily:
    get:
      operationId: getDailyReport
      x-google-backend:
        address: "https://us-central1-{project_id}.cloudfunctions.net/dailyReport"
      responses:
        200:
          description: The daily report.
definitions:
  Item:
    type: object
    required:
      - sku
    properties:
      sku:
        type: string
      quantity:
        type: integer
        format: int32
```

The OpenAPI 3.x output:

```yaml
openapi: 3.0.4
info:
  title: Inventory API
  version: 1.2.0
servers:
  - url: /v1
    x-google-endpoint: {}
x-google-api-management:
  backends:
    inventory-backend:
      address: https://inventory-abc123-uc.a.run.app
      pathTranslation: APPEND_PATH_TO_ADDRESS
      deadline: 30.0
    daily-report-fn:
      address: "https://us-central1-{project_id}.cloudfunctions.net/dailyReport"
      pathTranslation: CONSTANT_ADDRESS
  metrics:
    read-requests:
      displayName: Read requests
  quota:
    limits:
      read-limit:
        metric: read-requests
        values: 600
x-google-backend: inventory-backend
security:
  - api_key: []
components:
  securitySchemes:
    api_key:
      type: apiKey
      name: key
      in: query
    firebase:
      type: oauth2
      flows:
        implicit:
          authorizationUrl: ""
          scopes: {}
      x-google-auth:
        issuer: "https://securetoken.google.com/{firebase_project_id}"
        jwksUri: "https://www.googleapis.com/service_accounts/v1/metadata/x509/securetoken@system.gserviceaccount.com"
        audiences:
          - "{firebase_project_id}"
  schemas:
    Item:
      type: object
      required:
        - sku
      properties:
        sku:
          type: string
        quantity:
          type: integer
          format: int32
paths:
  /items/{itemId}:
    get:
      operationId: getItem
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
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Item"
  /items:
    post:
      operationId: createItem
      security:
        - api_key: []
          firebase: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/Item"
      responses:
        "200":
          description: The created item.
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Item"
  /reports/daily:
    get:
      operationId: getDailyReport
      x-google-backend: daily-report-fn
      responses:
        "200":
          description: The daily report.
```

What changed:

- `x-google-allow` is gone. The spec lists every path that clients call. Requests to other paths now return HTTP 404. In OpenAPI 2.0, they went to the backend without an API key.
- `host`, `basePath`, and `schemes` became one `servers` entry with `x-google-endpoint`.
- Each inline `x-google-backend` object became a named backend. The Cloud Run functions backend sets `pathTranslation: CONSTANT_ADDRESS`, which is the OpenAPI 2.0 default for an operation-level backend.
- The metrics and limits became maps without `valueType`, `metricKind`, and `unit`, and `x-google-quota` lost its `metricCosts` wrapper. The metric name `read-requests` did not change. `getItem` keeps its API key requirement from the root `security`, because API Gateway uses the API key to identify the consumer project for the quota.
- The JWT settings moved into `x-google-auth`, and `audiences` became a list.
- `in: body` became `requestBody`, `definitions` became `components.schemas`, and each response schema moved into `content`.
