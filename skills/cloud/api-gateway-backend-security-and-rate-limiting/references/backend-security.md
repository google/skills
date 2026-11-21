# Backend Security and Header Forwarding Reference

- [Gateway Service Account and Zero-Downtime Lockdown](#gateway-service-account-and-zero-downtime-lockdown): Lines 8-51
- [Backend Authentication Extensions (OpenAPI 2.0 vs 3.x)](#backend-authentication-extensions-openapi-20-vs-3x): Lines 53-84
- [Header Override and X-Apigateway-Api-Userinfo](#header-override-and-x-apigateway-api-userinfo): Lines 86-93
- [Default Gateway Hostname and Load Balancer Limitation](#default-gateway-hostname-and-load-balancer-limitation): Lines 95-102

## Gateway Service Account and Zero-Downtime Lockdown

API Gateway signs outbound backend requests with an OpenID Connect (OIDC) ID token generated for the gateway service account configured on the API config. Execute the steps below in order so existing gateways do not receive `403 Forbidden` responses while transitioning to an OIDC-secured backend:

1. Create a dedicated service account for the gateway. NEVER use the Compute Engine default service account (`{project_number}-compute@developer.gserviceaccount.com`) in production. **Rationale:** The Compute Engine default service account often carries broad project permissions (`roles/editor`), which violates least privilege.
   ```bash
   gcloud iam service-accounts create {gateway_sa_name} \
     --display-name="API Gateway backend invoker" \
     --project={project_id}
   ```
2. Grant the gateway service account only the invoker role on the target backend resource (request human approval before applying IAM bindings):
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
4. Create the API config with `--backend-auth-service-account` and roll it out to the gateway (note that only one API config can be created for a given API at a time, and config creation can take several minutes):
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
5. After the gateway is actively serving `{config_id}`, request human approval and restrict the backend service so that it rejects unauthenticated direct traffic (`--no-allow-unauthenticated`). **Rationale:** Locking down the backend before the gateway switches to `{config_id}` breaks live gateway traffic with `403` errors, whereas leaving `--allow-unauthenticated` enabled permanently lets callers invoke `*.run.app` directly and bypass API Gateway.
   ```bash
   gcloud run services update {backend_service} \
     --no-allow-unauthenticated \
     --region={region} \
     --project={project_id}
   ```

Reference: [Secure traffic to a service with the gcloud CLI](https://docs.cloud.google.com/api-gateway/docs/secure-traffic-gcloud.md.txt)

## Backend Authentication Extensions (OpenAPI 2.0 vs 3.x)

In OpenAPI 2.0, `x-google-backend` is an inline object with `snake_case` fields. In OpenAPI 3.x, you MUST define named backends inside the root `x-google-api-management.backends` map, and set `x-google-backend` to the string name of that backend. Use the documented `camelCase` field names (such as `jwtAudience` and `disableAuth`). **Rationale:** OpenAPI 3.x configs reject inline `x-google-backend` objects.

| Setting | OpenAPI 2.0 (`x-google-backend`) | OpenAPI 3.x (`x-google-api-management.backends.{name}`) | Behavior |
| --- | --- | --- | --- |
| Backend URL | `address` | `address` | Required target backend URL. |
| OIDC JWT Audience | `jwt_audience` | `jwtAudience` | Defaults to `address`. Set this field to the OAuth 2.0 client ID when the backend is protected by Identity-Aware Proxy (IAP) or runs on App Engine. |
| Disable Backend Auth | `disable_auth` | `disableAuth` | Defaults to `false`. Set to `true` to prevent the gateway proxy from obtaining and attaching an instance OIDC ID token (leaving any client `Authorization` header unreplaced by a gateway ID token). |
| Path Translation | `path_translation` | `pathTranslation` | Defaults to `APPEND_PATH_TO_ADDRESS` when `x-google-backend` is at the root level, and `CONSTANT_ADDRESS` when set at the operation level. |
| Deadline | `deadline` | `deadline` | Defaults to `15.0` seconds. Configurable up to `3600` seconds on streaming endpoints or `600` seconds on non-streaming gateways (values above `600` on non-streaming gateways are rejected at `gateways create` or `update` time). |
| Protocol | `protocol` | `protocol` | Defaults to `http/1.1`. Set to `h2` for gRPC backends or `http/1.1` for WebSocket backends. |

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
      deadline: 30.0
      protocol: http/1.1
x-google-backend: orders-backend
```

Reference: [OpenAPI 3.x extensions in API Gateway](https://docs.cloud.google.com/api-gateway/docs/oasv3-extensions.md.txt)

## Header Override and X-Apigateway-Api-Userinfo

When `x-google-backend` routes a request to a backend with backend authentication enabled, API Gateway overrides the incoming `Authorization` header with the gateway's own OIDC ID token so the backend (such as Cloud Run) can authenticate the gateway.

- Backends MUST read the end-user or client JWT claims from the `X-Apigateway-Api-Userinfo` header rather than the `Authorization` header. **Rationale:** The `Authorization` header received by the backend carries the gateway service account token, whereas `X-Apigateway-Api-Userinfo` contains the `base64url`-encoded JSON payload of the client JWT verified by API Gateway.
- Decode `X-Apigateway-Api-Userinfo` in the backend using standard `base64url` decoding (adding `=` padding if required by the language runtime) and parse the JSON claims (`sub`, `iss`, `aud`).

Reference: [Authenticate users with JWT - Receive authenticated results](https://docs.cloud.google.com/api-gateway/docs/authenticating-users-jwt.md.txt)

## Default Gateway Hostname and Load Balancer Limitation

API Gateway assigns every gateway a default hostname in `defaultHostname`, typically `https://{gateway_id}-{hash}.{region_code}.gateway.dev`. Read it with `gcloud api-gateway gateways describe {gateway_id} --location={region} --format="value(defaultHostname)"` instead of building it from the gateway name.

- API Gateway does not support ingress restriction settings to disable direct access to the gateway's `defaultHostname`.
- If you place an External Application Load Balancer, Google Cloud Armor policy, or Identity-Aware Proxy (IAP) in front of API Gateway via a serverless Network Endpoint Group (NEG), NEVER rely on the load balancer alone to block unauthorized requests. **Rationale:** Clients that discover the gateway's `defaultHostname` (`*.gateway.dev`) can send requests directly to the gateway and bypass the load balancer and Google Cloud Armor. Always enforce JWT or API key security in the API Gateway OpenAPI specification and IAM on the backend.

Reference: [Use a load balancer with API Gateway](https://docs.cloud.google.com/api-gateway/docs/gateway-load-balancing.md.txt)
