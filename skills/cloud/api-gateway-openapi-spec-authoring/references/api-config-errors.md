# API Config Errors and Silent Behaviors

- [Errors from api-configs create](#errors-from-api-configs-create): Lines 8-65
- [Silent Behaviors](#silent-behaviors): Lines 67-82

`gcloud api-gateway api-configs create` returns the first problems that it finds. Fix every error in the output, run `python3 scripts/validate_apigw_openapi.py --spec={spec_file}` again, and then create a new API config.

## Errors from api-configs create

Match a part of the error text. The text in braces changes with the spec. Some errors have one text for OpenAPI 3.x and another text for OpenAPI 2.0.

| Error text | Cause | Fix |
| --- | --- | --- |
| `The 'x-google-management' extension is only supported in OpenAPI 2.x, please replace it with 'x-google-api-management'.` | An OpenAPI 2.0 metrics and quota block in an OpenAPI 3.x spec. | Move the metrics and limits into `x-google-api-management` as maps. See [Extension Mapping Table](openapi-2-to-3-migration.md#extension-mapping-table). |
| `The 'x-google-endpoints' extension is only supported in OpenAPI 2.x, please replace it with 'servers[*].x-google-endpoint'.` | An OpenAPI 2.0 endpoint block. | Move the settings to one `servers` entry with `x-google-endpoint`, and remove `name`. |
| `The 'x-google-api-name' extension is only supported in OpenAPI 2.x, please replace it with 'x-google-api-management.apiName'.` | An OpenAPI 2.0 API name. | Move the value to `x-google-api-management.apiName`. |
| `The '{extension}' extension is only supported in OpenAPI 2.x, please replace it with 'x-google-auth.{field}'.` | `x-google-issuer`, `x-google-jwks_uri`, `x-google-audiences`, `x-google-jwt-locations`, `x-issuer`, or `x-jwks_uri` on a security scheme. | Nest the values in `x-google-auth` (`issuer`, `jwksUri`, `audiences` as a list, `jwtLocations`). |
| `The 'x-google-allow' extension is only supported in OpenAPI 2.x.` | `x-google-allow` in an OpenAPI 3.x spec. | Remove it, and list every path. See the `x-google-allow` row of the [Swagger 2.0 Construct Conversion Map](openapi-2-to-3-migration.md#swagger-20-construct-conversion-map). |
| `The '{extension}' extension is only supported in OpenAPI 2.x, please replace it with 'x-google-api-management.backends'.` | `x-google-backend-url` or `x-google-backend-deadline` on an operation. At the root, API Gateway ignores them. | Define the backend in `x-google-api-management.backends`, with `address` and `deadline`, and set `x-google-backend` to its name. |
| `The 'x-security' extension is only supported in OpenAPI 2.x, please replace it with 'OpenAPI security'.` | `x-security` at the root or on an operation. | Use the OpenAPI `security` field. |
| `The '{extension}' extension is only supported in OpenAPI 2.x.` | `x-google-deprecated` or `x-google-experimental-authorization`. | Follow the "Other OpenAPI 2.0 extensions" row of the [Extension Mapping Table](openapi-2-to-3-migration.md#extension-mapping-table). |
| `Extension x-google-api-management cannot be converted into proto type` | A field that OpenAPI 3.x does not support, such as `valueType`, `metricKind`, `unit`, or `name` from OpenAPI 2.0, or both `jwtAudience` and `disableAuth` on one backend. The `Details` text names the field. | Remove the field. A metric has only `displayName`. A limit has only `metric` and `values`. Set only one of `jwtAudience` and `disableAuth`. |
| `Extension x-google-backend does not have a valid value. {value} is not defined in x-google-api-management.` | An inline `x-google-backend` object (the OpenAPI 2.0 form), a name that `backends` does not define, or an `x-google-api-management` block that failed to parse. | Fix the `cannot be converted into proto type` error first, if there is one. Define the backend in `x-google-api-management.backends`, and set `x-google-backend` to its name. |
| `Extension {extension} was specified at a path level, which is not supported.` | `x-google-backend`, `x-google-backend-url`, or `x-google-backend-deadline` on a path item. | Set `x-google-backend` at the root or on each operation. Move a URL or a deadline to a backend in `x-google-api-management.backends`. |
| `has no backend configured at the operation or API level` | An operation without an operation-level or root `x-google-backend`. | Set a root `x-google-backend`, or set `x-google-backend` on the operation. |
| `Address field in extension x-google-backend must use the HTTP or HTTPS protocol` or `is not a valid URL` | A backend `address` that is not an HTTP(S) URL. | Use the full `https://` URL of the backend. |
| `Backend URL ... cannot route requests to localhost`, `by IP Address`, `to a metadata server`, or `to an internal address` | A backend `address` with `localhost`, an IP address, a metadata server, or an `.internal` hostname. | Use a public hostname, such as the Cloud Run service URL. |
| `hostname must have more than one part to be fully qualified` | A backend `address` with a one-part hostname, often a `{placeholder}` that you did not replace. | Use the fully qualified hostname of the backend. |
| `Backend URL ... hostname contains a segment larger than 63 characters` | A hostname label longer than 63 characters. | Use a shorter hostname. |
| `Protocol field in extension x-google-backend must be 'http/1.1' or 'h2'` | Another `protocol` value. | Use `http/1.1` or `h2`. |
| `Protocol field in extension x-google-backend is only configurable to 'h2' for 'https' backends` | `protocol: h2` with an `http://` address. | Use an `https://` address, or `http/1.1`. |
| `Quota Extension for method '{method}' references undefined metric(s) '{metric}'` | An `x-google-quota` metric that `x-google-api-management.metrics` does not define. | Define the metric, or fix the name. Keep the name that the current API config uses. |
| `Metric rule defined on metric '{metric}', but has no quota limits defined.` | An `x-google-quota` metric without a quota limit. | Add a limit for the metric in `x-google-api-management.quota.limits`. |
| `Metric '{metric}' referenced by quota limit '{limit}' does not exist.` | A quota limit that names an undefined metric. | Define the metric, or fix the name in the limit. |
| `Schema has multiple types defined. More than one type is not supported, please define only one type.` | An OpenAPI 3.1 type list, such as `type: ["string", "null"]`. | Give the schema one `type`. |
| `OpenAPI spec has more than one server with x-google-endpoint extension.` | Two or more `servers` entries with `x-google-endpoint`. | Keep `x-google-endpoint` on one entry. |
| `server url '{url}' ... relative path starting with '/'` | A server URL without a scheme that does not start with `/`, such as `v1`. | Use `/v1` or an `https://` URL. |
| `is ill formed and cannot be parsed due to invalid server url` | A server variable, such as `https://{region}.example.com/v1`, or a space in the server URL. | Replace each `{variable}` with its value. |
| `has a server url '{url}' with a custom port. Custom ports are not supported.` | A port in the server URL. | Remove the port. |
| `Service name must be provided either explicitly or in OpenAPI 'host' value.` | A relative server URL in an API that uses a managed service that you chose. | Use `url: https://{managed_service}{base_path}`. |
| `'$ref' fields must be local references and cannot contain an external URL.` | A `$ref` to a URL. | Copy the schema into `components.schemas`, and use `#/components/schemas/{name}`. If you cannot get the schema, ask the user for it. |
| `Type definition reference path '{ref}' must begin with '#/components/schemas/'` | A schema `$ref` with another path, such as `#/definitions/{name}` from OpenAPI 2.0. | Move the schema to `components.schemas`, and use `#/components/schemas/{name}`. |
| `Security Scheme '{name}' that does not exist` | A `security` requirement that names an undefined scheme. | Define the scheme in `components.securitySchemes`, or fix the name. |
| `Combining API key and OAuth security requirements with a logical OR is not supported.` | A `security` list with an API key in only some alternatives, such as `[{firebase: []}, {api_key: []}]`. | Put the API key in every alternative, or in none. |
| `Optional OAuth security requirement is not supported.` | An empty requirement (`{}`) with a JWT scheme, such as `[{firebase: []}, {}]`. | Remove `{}`, or use it only with API key schemes. |
| `contains multiple security definitions` ... `that get logically ANDed` | Two JWT schemes in one requirement object. | Put each JWT scheme in its own requirement object (OR). |
| `required property 'responses' not found` (OpenAPI 3.x) or `missing required properties (["responses"])` (OpenAPI 2.0) | An operation without `responses`. | Add the responses that the backend returns. |
| `Operation does not have the required 'operationId' field` | An operation without `operationId`. | Give the operation a unique `operationId`. |
| `has duplicate entry` or `is considered equivalent to operationId` | Two equal `operationId` values, or two values that are equal after API Gateway removes the characters other than letters, digits, and underscores and capitalizes the first letter, such as `getItem` and `GetItem`. | Make the `operationId` values differ after that change. |
| `unrecognized input at '{'` or `expected '}'` | A path variable that is not a whole segment, such as `/items/prefix_{id}` or `/{a}{b}`. | Make each variable a whole segment. |
| `Declared path parameter {name} needs to be defined as a path parameter` | A path variable without a parameter with `in: path`, or a `{name=*}` or `{name=**}` path from OpenAPI 2.0. | Add a parameter with `name: {name}`, `in: path`, and `required: true`. For `{name=**}`, write `{name}`, and set `x-google-parameter: {pattern: "**"}` on the parameter. |
| `Parameter is defined in the parameters list but is not in the path.` | A parameter with `in: path` that the path does not contain. | Remove the parameter, or add `{name}` to the path. |
| `Parameter names must start with a letter` (OpenAPI 3.x) or `parameter name contains invalid characters` (OpenAPI 2.0) | A path variable name that does not start with a letter, or that has other characters. | Use letters, digits, underscores, dots, and dashes, and start with a letter. |
| `Parameter names cannot exceed 30 characters.` (OpenAPI 3.x) or `is too long (max length: 100)` (OpenAPI 2.0) | A path variable name that is too long. | Shorten the name. |
| `Too many path parameters. Maximum allowed is 15` (OpenAPI 3.x) or `exceeds maximum allowed parameters of 60` (OpenAPI 2.0) | A path with too many path parameters. | Use fewer path parameters, or split the operation. |
| `paths must be 512 characters or less` | A path that is too long. | Shorten the path. |
| `Only ** is supported.` or `must be the last segment in the path because it uses pattern: **` | An `x-google-parameter` pattern other than `**`, or `**` on a parameter that is not the last segment. | Use `pattern: "**"` only on the last path segment. |
| `does not have a value in the enumeration ["path"]` | A parameter with `in: body` or `in: formData` from OpenAPI 2.0. | Move the body or form data to `requestBody`. |
| `JWKS ... cannot route requests to localhost` | An `x-google-auth.jwksUri` that breaks the backend address rules, such as `localhost`. | Use the public key URL of the token issuer. |
| `JWKS provider "{name}" is missing a JWKS URI` | A `type: oauth2` security scheme without `x-google-auth.jwksUri`, also a scheme that no operation uses. | Set `jwksUri` in `x-google-auth`, or remove the unused scheme. |
| `which exceeds the maximum of 600 seconds supported by this Gateway` | A backend `deadline` above 600 seconds. `gateways create` or `gateways update` returns this error, not `api-configs create`. | Set `deadline` to 600 or less. A streaming gateway accepts up to 3600. |
| `string found, object expected` | Often a YAML alias to a mapping (`*anchor`). | Replace the alias with a `$ref`, or copy the mapping. |
| `Invalid API name '{name}'` | An `apiName` that is not a lowercase letter followed by at most 39 lowercase letters or digits. | Use a name such as `orders`. |
| `OpenAPI files includes conflicting API versions` | Two files in one API config with the same `apiName`, or without `apiName`, and the same major version. | Merge the files, or give each file its own `x-google-api-management.apiName`. |
| `maximum allowed number of 50 files` or `maximum allowed size of 10MB` | Too many or too large OpenAPI files. | Merge or shrink the files. |

## Silent Behaviors

API Gateway accepts these specs without an error, but does not do what the author often expects. The validator script reports the first row as an error and the other rows as warnings.

| Spec | What API Gateway does | Fix |
| --- | --- | --- |
| `x-google-quota` at the root or on a path item | Ignores it in OpenAPI 3.x. No quota applies. | Set `x-google-quota` on each operation. |
| An operation-level `x-google-backend` whose backend has no `pathTranslation` | Uses `CONSTANT_ADDRESS`: it sends each request to the `address` unchanged, and sends path parameters as query parameters. | Set `pathTranslation: APPEND_PATH_TO_ADDRESS` on the backend if the backend routes by path. |
| A Cloud Run `address` with a path, and no `jwtAudience` | Sends an ID token whose audience is the full address. Cloud Run rejects the token. | Set `jwtAudience` to the service URL without the path. |
| `servers` entries without `x-google-endpoint` | Ignores them, and applies no base path. | Add `x-google-endpoint: {}` to the entry with the base path. |
| `allowCors: true` | Passes CORS requests to the backend. It does not add CORS headers. | Make the backend answer preflight `OPTIONS` requests and add the CORS headers. |
| OAuth scopes in a security scheme | Does not check them. | Check the scopes in the backend. |
| An API key scheme with a name other than `x-api-key` in a header, or `key` or `api_key` in the query | Ignores the scheme. Operations that require only this scheme accept calls without a key. | Use one of the supported names and locations. |
| `x-google-quota` on an operation that does not require an API key | Accepts calls without an API key, and cannot identify the consumer project that the quota counts. | Require an API key in every security alternative of the operation. |

API Gateway also does not check required parameters, parameter types, or request body schemas. It forwards each request, so the backend must validate the input.
