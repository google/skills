<!-- disableFinding(LINE_OVER_80) -->

# Backend Security and Header Forwarding Reference

- [Gateway Service Account and Zero-Downtime Lockdown](#gateway-service-account-and-zero-downtime-lockdown): Lines 10-66
- [Backend Authentication Extensions (OpenAPI 2.0 vs 3.x)](#backend-authentication-extensions-openapi-20-vs-3x): Lines 68-99
- [Header Override and X-Apigateway-Api-Userinfo](#header-override-and-x-apigateway-api-userinfo): Lines 101-109
- [Default Gateway Hostname and Load Balancer Limitation](#default-gateway-hostname-and-load-balancer-limitation): Lines 111-118

## Gateway Service Account and Zero-Downtime Lockdown

API Gateway signs outbound backend requests with an OpenID Connect (OIDC) ID token generated for the gateway service account configured on the API config. Execute the steps below in order so existing gateways do not receive `403 Forbidden` responses while transitioning to an OIDC-secured backend:

1. Create a dedicated service account for the gateway. NEVER use the Compute Engine default service account (`{project_number}-compute@developer.gserviceaccount.com`) in production. **Rationale:** The Compute Engine default service account often carries broad project permissions (`roles/editor`), which violates least privilege.
   ```bash
   gcloud iam service-accounts create {gateway_sa_name} \
     --display-name="API Gateway backend invoker" \
     --project={project_id}
   ```
2. Grant the gateway service account only the invoker role on the target backend resource (request human approval before applying IAM bindings). A change to the IAM policy of a Cloud Run service needs `roles/run.admin`, or another role with `run.services.setIamPolicy`:
   - **Cloud Run service or Cloud Run functions (2nd gen):** `roles/run.invoker`
     ```bash
     gcloud run services add-iam-policy-binding {backend_service} \
       --member="serviceAccount:{gateway_sa_name}@{project_id}.iam.gserviceaccount.com" \
       --role="roles/run.invoker" \
       --region={region} \
       --project={project_id}
     ```
   - **Cloud Run functions (1st gen):** `roles/cloudfunctions.invoker` (as used in legacy Cloud Functions setups).
3. Grant the deployment identity `roles/iam.serviceAccountUser` on `{gateway_sa_name}@{project_id}.iam.gserviceaccount.com` so it can attach the service account to an API config.
4. Create the API config with `--backend-auth-service-account` and roll it out to every gateway of the API (note that only one API config can be created for a given API at a time, and config creation can take several minutes):
   ```bash
   gcloud api-gateway api-configs create {config_id} \
     --api={api_id} \
     --openapi-spec={candidate_openapi_spec} \
     --backend-auth-service-account={gateway_sa_name}@{project_id}.iam.gserviceaccount.com \
     --project={project_id}

   gcloud api-gateway gateways update {gateway_id} \
     --api={api_id} \
     --api-config={config_id} \
     --location={region} \
     --project={project_id}
   ```
5. After every gateway of the API serves an API config with `--backend-auth-service-account`, request human approval and block unauthenticated direct calls to the backend. **Rationale:** A gateway that still serves an older config sends no ID token, or a token from a service account without the invoker role, so a lockdown before the switch breaks its live traffic with `403` errors. If you do not lock down the backend, callers can invoke `*.run.app` directly and bypass API Gateway.
   - For a 1st gen function backend, skip the Cloud Run commands in this step. Run `gcloud functions remove-iam-policy-binding {function_name} --member=allUsers --role=roles/cloudfunctions.invoker --region={region} --project={project_id}`. If the function also has an `allAuthenticatedUsers` binding, run it again with `--member=allAuthenticatedUsers`.
   - Remove the `allUsers` invoker binding:
     ```bash
     gcloud run services remove-iam-policy-binding {backend_service} \
       --member=allUsers \
       --role=roles/run.invoker \
       --region={region} \
       --project={project_id}
     ```
     If gcloud reports that the binding is not found, the service has no `allUsers` binding. Go to the next check.
   - If `gcloud run services get-iam-policy {backend_service} --region={region} --project={project_id}` shows an `allAuthenticatedUsers` invoker binding, remove it with the same command and `--member=allAuthenticatedUsers`. **Rationale:** That binding lets any Google Account call the backend directly.
   - For a Cloud Run or 2nd gen function backend, if the service has the invoker IAM check turned off (`gcloud run services describe {backend_service} --region={region} --project={project_id} --format=yaml` shows the annotation `run.googleapis.com/invoker-iam-disabled: 'true'`), turn the check on:
     ```bash
     gcloud run services update {backend_service} \
       --invoker-iam-check \
       --region={region} \
       --project={project_id}
     ```
   - Do not use `gcloud run services update --no-allow-unauthenticated`. `gcloud run deploy` has that flag, but `services update` does not.

Reference: [Secure traffic to a service with the gcloud CLI](https://docs.cloud.google.com/api-gateway/docs/secure-traffic-gcloud.md.txt)

## Backend Authentication Extensions (OpenAPI 2.0 vs 3.x)

In OpenAPI 2.0, `x-google-backend` is an inline object with `snake_case` fields. In OpenAPI 3.x, you MUST define named backends inside the root `x-google-api-management.backends` map, and set `x-google-backend` to the string name of that backend. Use the documented `camelCase` field names (such as `jwtAudience` and `disableAuth`). **Rationale:** OpenAPI 3.x configs reject inline `x-google-backend` objects.

These fields control the ID token that the gateway sends to the backend:

| Setting | OpenAPI 2.0 (`x-google-backend`) | OpenAPI 3.x (`x-google-api-management.backends.{name}`) | Behavior |
| --- | --- | --- | --- |
| OIDC JWT Audience | `jwt_audience` | `jwtAudience` | Defaults to the full `address` value. Set this field to the OAuth 2.0 client ID when the backend is protected by Identity-Aware Proxy (IAP) or runs on App Engine. For a Cloud Run revision tag URL (`https://{tag}---{service_host}`), set it to `https://{service_host}`. |
| Disable Backend Auth | `disable_auth` | `disableAuth` | Defaults to `false`. Set to `true` to prevent the gateway proxy from obtaining and attaching an instance OIDC ID token (leaving any client `Authorization` header unreplaced by a gateway ID token). |

Set at most one of `jwtAudience` and `disableAuth` (`jwt_audience` and `disable_auth` in OpenAPI 2.0) on a backend. API Gateway rejects a backend that sets both.

For the other backend fields (`address`, `pathTranslation`, `deadline`, and `protocol`), use the `api-gateway-openapi-spec-authoring` skill. If it is not installed, see the reference link below.

### OpenAPI 3.x Backend Example

```yaml
openapi: 3.0.4
info:
  title: Orders API
  version: 1.0.0
x-google-api-management:
  backends:
    orders-backend:
      address: https://{backend_service}-{hash}.a.run.app
      jwtAudience: https://{backend_service}-{hash}.a.run.app
      pathTranslation: APPEND_PATH_TO_ADDRESS
x-google-backend: orders-backend
```

Reference: [OpenAPI 3.x extensions in API Gateway](https://docs.cloud.google.com/api-gateway/docs/oasv3-extensions.md.txt)

## Header Override and X-Apigateway-Api-Userinfo

When `x-google-backend` routes a request to a backend with backend authentication enabled, API Gateway overrides the incoming `Authorization` header with the gateway's own OIDC ID token so the backend (such as Cloud Run) can authenticate the gateway.

- For an operation with JWT auth, backends MUST read the end-user or client JWT claims from the `X-Apigateway-Api-Userinfo` header rather than the `Authorization` header. **Rationale:** The `Authorization` header received by the backend carries the gateway service account token, whereas `X-Apigateway-Api-Userinfo` contains the `base64url`-encoded JSON payload of the client JWT verified by API Gateway.
- API Gateway sends `X-Apigateway-Api-Userinfo` only when the operation authenticated a JWT. An operation with only an API key, or with no `security`, gets no such header.
- Decode `X-Apigateway-Api-Userinfo` in the backend using standard `base64url` decoding (adding `=` padding if required by the language runtime) and parse the JSON claims (`sub`, `iss`, `aud`).

Reference: [Authenticate users with JWT - Receive authenticated results](https://docs.cloud.google.com/api-gateway/docs/authenticating-users-jwt.md.txt)

## Default Gateway Hostname and Load Balancer Limitation

API Gateway assigns every gateway a default hostname in `defaultHostname`, typically `https://{gateway_id}-{hash}.{region_code}.gateway.dev`. Read it with `gcloud api-gateway gateways describe {gateway_id} --location={region} --project={project_id} --format="value(defaultHostname)"` instead of building it from the gateway name.

- API Gateway does not support ingress restriction settings to disable direct access to the gateway's `defaultHostname`.
- If you place an External Application Load Balancer, Google Cloud Armor policy, or Identity-Aware Proxy (IAP) in front of API Gateway via a serverless Network Endpoint Group (NEG), NEVER rely on the load balancer alone to block unauthorized requests. **Rationale:** Clients that discover the gateway's `defaultHostname` (`*.gateway.dev`) can send requests directly to the gateway and bypass the load balancer and Google Cloud Armor. Always enforce JWT or API key security in the API Gateway OpenAPI specification and IAM on the backend.

Reference: [Use a load balancer with API Gateway](https://docs.cloud.google.com/api-gateway/docs/gateway-load-balancing.md.txt)
