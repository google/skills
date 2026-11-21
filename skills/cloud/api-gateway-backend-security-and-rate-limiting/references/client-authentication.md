# Client Authentication Reference (API Keys and JWT)

- [API Key Configuration](#api-key-configuration): Lines 9-36
- [API Key Restrictions and Managed Service](#api-key-restrictions-and-managed-service): Lines 38-58
- [JWT Configuration in OpenAPI 2.0 and 3.x](#jwt-configuration-in-openapi-20-and-3x): Lines 60-111
- [Identity Provider JWT Settings Table](#identity-provider-jwt-settings-table): Lines 113-122
- [Security Composition and Override Rules](#security-composition-and-override-rules): Lines 124-136

## API Key Configuration

Use an API key to identify the calling Google Cloud consumer project for quota enforcement, billing, and usage tracking. Do not use an API key alone to authenticate end-user identity. **Rationale:** An API key identifies a Google Cloud project rather than a user or service principal, and callers can extract API keys from client applications.

Pass the API key in the `x-api-key` HTTP header as the standard convention. Use the `key` query parameter only as an escape hatch when the client cannot set custom HTTP headers. **Rationale:** URL query parameters appear in proxy logs, browser history, and access logs.

### OpenAPI 2.0 (`securityDefinitions`)

```yaml
securityDefinitions:
  api_key:
    type: "apiKey"
    name: "x-api-key"
    in: "header"
```

### OpenAPI 3.x (`components.securitySchemes`)

```yaml
components:
  securitySchemes:
    api_key:
      type: apiKey
      name: x-api-key
      in: header
```

Reference: [Authenticate with an API key](https://docs.cloud.google.com/api-gateway/docs/authenticate-api-keys.md.txt)

## API Key Restrictions and Managed Service

Before a consumer project can call an API with an API key, enable the managed service of the API in that consumer project and allow it on the API key:

1. Inspect the API to find its `managedService` value (note that a newly created managed service can take up to 30 minutes to appear in the Google Cloud API Library):
   ```bash
   gcloud api-gateway apis describe {api_id} --project={project_id} --format="value(managedService)"
   ```
2. Enable the managed service in the consumer project (`{consumer_project_id}`):
   ```bash
   gcloud services enable {managed_service_name} --project={consumer_project_id}
   ```
3. Add API restrictions and application restrictions to every production API key (request human approval before creating or updating production API keys). If a restricted API key gets HTTP `403` because its API restrictions do not include the API, add `{managed_service_name}` to the key's allowed API targets:
   ```bash
   gcloud services api-keys update {key_id} \
     --api-target=service={managed_service_name} \
     --project={consumer_project_id}
   ```
4. If you restrict an API key by HTTP referrer (website), you MUST include the URL scheme (`https://{domain}/*` instead of `{domain}/*`). **Rationale:** Unrestricted API keys can be used against any enabled API in the project, and referrer entries without a scheme fail validation.

Reference: [Restrict API keys](https://docs.cloud.google.com/docs/authentication/api-keys.md.txt)

## JWT Configuration in OpenAPI 2.0 and 3.x

Use JSON Web Tokens (JWTs) to authenticate end users or calling service accounts.

- You MUST specify `x-google-jwks_uri` (OpenAPI 2.0) or `x-google-auth.jwksUri` (OpenAPI 3.x) on every JWT security definition. **Rationale:** API Gateway requires the public key set URI to verify the signature of incoming JWTs and caches the JWKS for 5 minutes (publish rotated signing keys at least 5 minutes before signing traffic).
- Give each JWT security scheme a unique `issuer` value. **Rationale:** API Gateway routes token verification by matching the `iss` claim to a unique security definition.
- Required JWT claims are `iss`, `sub`, `aud`, `iat`, and `exp`. The `aud` claim cannot be an internal address or an IPv4/IPv6 address.
- `audiences` (`x-google-audiences` in OpenAPI 2.0) is optional. If omitted, API Gateway accepts JWTs whose `aud` claim matches `https://{service_name}`, where `{service_name}` is the API Gateway `managedService` name (`host` in OpenAPI 2.0 or `servers.url` with `x-google-endpoint` in OpenAPI 3.x). In OpenAPI 2.0, specify multiple audiences as a single comma-separated string (`"aud1,aud2"`); in OpenAPI 3.x, specify a YAML list.
- API Gateway validates JWT claims and signatures, but does not check IAM permissions of a calling service account and ignores OAuth `scopes` declared in the OpenAPI document.

### OpenAPI 2.0 JWT Definition

```yaml
securityDefinitions:
  service_jwt:
    authorizationUrl: ""
    flow: "implicit"
    type: "oauth2"
    x-google-issuer: "{service_account_email}"
    x-google-jwks_uri: "https://www.googleapis.com/robot/v1/metadata/x509/{service_account_email}"
    x-google-audiences: "https://{managed_service_name}"
```

### OpenAPI 3.x JWT Definition (`x-google-auth`)

In OpenAPI 3.x, place `issuer`, `jwksUri`, `audiences`, and `jwtLocations` inside `x-google-auth` and remove the `x-google-` field prefixes used in OpenAPI 2.0:

```yaml
components:
  securitySchemes:
    service_jwt:
      type: oauth2
      flows:
        implicit:
          authorizationUrl: ""
          scopes: {}
      x-google-auth:
        issuer: "{service_account_email}"
        jwksUri: "https://www.googleapis.com/robot/v1/metadata/x509/{service_account_email}"
        audiences:
          - "https://{managed_service_name}"
        jwtLocations:
          - header: X-Forwarded-Authorization
            valuePrefix: "Bearer "
          - query: auth_token
```

By default, API Gateway reads JWTs from `Authorization: Bearer `, `X-Goog-Iap-Jwt-Assertion`, or the `access_token` query parameter. Configure `jwtLocations` (`header` with optional `valuePrefix`, or `query`) only when the client sends the token in a custom header or query parameter.

References:
- [Authenticate users with JWT](https://docs.cloud.google.com/api-gateway/docs/authenticating-users-jwt.md.txt)
- [Authentication between services](https://docs.cloud.google.com/api-gateway/docs/authenticate-service-account.md.txt)

## Identity Provider JWT Settings Table

| Identity Provider | `issuer` (`x-google-issuer`) | `jwksUri` (`x-google-jwks_uri`) | `audiences` (`x-google-audiences`) |
| --- | --- | --- | --- |
| Firebase Authentication | `https://securetoken.google.com/{project_id}` | `https://www.googleapis.com/service_accounts/v1/metadata/x509/securetoken@system.gserviceaccount.com` | `{project_id}` |
| Auth0 | `https://{your_auth0_domain}/` (trailing slash required) | `https://{your_auth0_domain}/.well-known/jwks.json` | Auth0 API Identifier or Client ID |
| Okta | `https://{your_okta_domain}/oauth2/default` | `https://{your_okta_domain}/oauth2/default/v1/keys` | Okta Client ID or Audience |
| Google ID token (user sign-in with an OAuth client) | `https://accounts.google.com` | `https://www.googleapis.com/oauth2/v3/certs` | OAuth 2.0 Client ID |
| Google ID token for a service account (`gcloud auth print-identity-token --impersonate-service-account={caller_sa_email} --audiences={jwt_audience}`) | `https://accounts.google.com` | `https://www.googleapis.com/oauth2/v3/certs` | The same `{jwt_audience}` value. Any Google identity can mint such a token, so check the `email` claim in the backend (`X-Apigateway-Api-Userinfo`), or use the self-signed row to accept only one service account. |
| Service account self-signed JWT (`gcloud iam service-accounts sign-jwt`) | `{service_account_email}` | `https://www.googleapis.com/robot/v1/metadata/x509/{service_account_email}` | `https://{managed_service_name}` |

## Security Composition and Override Rules

**Operation-level `security` replaces root-level `security`:** If an operation declares its own `security` block with only a JWT scheme (`- service_jwt: []`), it overrides the document-level `security` block and removes any root `api_key` requirement. To preserve per-project quota tracking on an operation that overrides `security`, you MUST include `api_key: []` in the same security requirement object (`- api_key: []` and `service_jwt: []` together).

| Requirement Pattern | OpenAPI Syntax | Supported in API Gateway |
| --- | --- | --- |
| Require API key AND JWT (conjunction) | Single list item with two keys: `- api_key: []` and `service_jwt: []` in the same object | Yes. Use this pattern when an operation requires both user authentication and consumer project quota tracking. |
| Require JWT scheme A OR JWT scheme B (disjunction) | Two list items: `- jwt_a: []` followed by `- jwt_b: []` | Yes. Each scheme must have a distinct `issuer`. |
| Require JWT scheme A AND JWT scheme B (conjunction) | Single list item with two OAuth2 schemes | No. API Gateway does not support conjunctions of multiple OAuth2 schemes unless the additional scheme is an API key. |
| Require API key OR JWT (disjunction) | Two list items where one is an `apiKey` scheme | No. API Gateway rejects logical OR security requirements between an API key and another scheme. |
| Optional API key | `- {}` alongside `- api_key: []` | Yes (special-case exception for API keys only). Do not use `- {}` to make OAuth2/JWT optional. |

Reference: [OpenAPI 3.x feature limitations](https://docs.cloud.google.com/api-gateway/docs/openapi-v3-limitations.md.txt)
