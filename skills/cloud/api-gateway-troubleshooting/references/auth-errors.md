# 401 and 403 errors

-   [Find the hop that failed](#find-the-hop-that-failed): Lines 9-19
-   [Gateway rejected the caller: API keys](#gateway-rejected-the-caller-api-keys): Lines 21-65
-   [Gateway rejected the caller: JWTs](#gateway-rejected-the-caller-jwts): Lines 67-91
-   [Backend rejected the gateway](#backend-rejected-the-gateway): Lines 93-168
-   [Fixes to avoid](#fixes-to-avoid): Lines 170-174

## Find the hop that failed

A request crosses two hops, and each has its own credentials:

| Hop | Credential | Evidence |
| :--- | :--- | :--- |
| Caller to gateway | API key or JWT defined in the API config | Gateway log entry whose `responseDetails` isn't `via_upstream` |
| Gateway to backend | ID token minted for the gateway's service account | Gateway log entry with `responseDetails` set to `via_upstream` |

Read the log entry first (see [triage-and-logs.md](triage-and-logs.md)). Don't
change IAM on the backend for a caller-side failure, or the reverse.

## Gateway rejected the caller: API keys

When an API config requires an API key, a request without one gets an error
like the one the API Gateway quickstart shows
([Secure traffic with gcloud](https://docs.cloud.google.com/api-gateway/docs/secure-traffic-gcloud.md.txt)):

```
UNAUTHENTICATED:Method doesn't allow unregistered callers (callers without established identity). Please use API Key or other form of API consumer identity to call this API.
```

Check, in order
([Authenticate with API keys](https://docs.cloud.google.com/api-gateway/docs/authenticate-api-keys.md.txt)):

1.  **The key is sent where the spec expects it** (header or query parameter
    name in the security definition).
2.  **The key's project can use the API.** API Gateway rejects requests unless
    the API key was generated in the gateway's project or in another project
    where the API's managed service is enabled. Get the managed service name,
    then check whether it's enabled in the key's project:

    ```bash
    gcloud api-gateway apis describe {api_id} --project={project_id} --format="value(managedService)"
    gcloud services list --enabled --project={consumer_project} \
        --filter="config.name={managed_service}"
    ```

    The fix, after approval, is
    `gcloud services enable {managed_service} --project={consumer_project}`.
    The person who runs it needs `roles/serviceusage.serviceUsageAdmin` in the
    consumer project and `roles/servicemanagement.serviceConsumer` on the
    managed service, which the API owner grants
    ([API access overview](https://docs.cloud.google.com/api-gateway/docs/api-access-overview.md.txt)).
3.  **The key's restrictions allow the call.** API restrictions must include
    the managed service, and application restrictions (IP addresses, referrers,
    apps) must match the caller
    ([Manage API keys](https://docs.cloud.google.com/docs/authentication/api-keys.md.txt)).
    Managing keys needs `roles/serviceusage.apiKeysAdmin`.
4.  **The security requirements are supported.** The OpenAPI 2.0 and 3.x
    limitations pages say that API Gateway doesn't support alternative (logical
    OR) security requirements when one of them is an API key; API key and JWT
    can only be combined with AND
    ([OpenAPI 2.0 limitations](https://docs.cloud.google.com/api-gateway/docs/openapi-limitations.md.txt),
    [OpenAPI 3.x limitations](https://docs.cloud.google.com/api-gateway/docs/openapi-v3-limitations.md.txt)).

Refer to keys by key ID or display name only. Never print a key value.

## Gateway rejected the caller: JWTs

Don't ask for the token: it's a live credential. Ask the user to decode its
header and payload on their own machine (both are base64url-encoded) and paste
only the `iss`, `aud`, `exp`, and `iat` claims. If they paste a token anyway,
don't repeat it. Compare the claims with the security definition
([Authenticate users with JWT](https://docs.cloud.google.com/api-gateway/docs/authenticating-users-jwt.md.txt)):

| Claim | Must match |
| :--- | :--- |
| `iss` | `x-google-issuer` (OpenAPI 2.0) or the issuer in `x-google-auth` (OpenAPI 3.x) |
| `aud` | `x-google-audiences` (2.0) or `audiences` (3.x), which are optional. When they aren't set, the OpenAPI 2.0 extensions page says `aud` should match the document's `host` field, and the JWT page says API Gateway accepts JWTs whose `aud` is `https://SERVICE_NAME`. If the token fits neither, set the audiences explicitly. |
| `exp` | A required claim; check that the token hasn't expired |
| Signature | A key published at `x-google-jwks_uri` (2.0) or `jwksUri` (3.x) |

Also check:

-   Each security definition must use a different issuer.
-   Method-level security settings override API-level settings.
-   The `jwks_queries` log shows whether the gateway could fetch the signing
    keys ([Platform logs](https://docs.cloud.google.com/api-gateway/docs/platform-logging.md.txt)).

If the response body names the failing check, quote it verbatim (redacted) and
map it to the table above. Don't infer meanings for messages that the public
docs don't describe.

## Backend rejected the gateway

`via_upstream` means the backend returned the `401` or `403`. Work through the
causes that match the backend type
([Securing backend services](https://docs.cloud.google.com/api-gateway/docs/securing-backend-services.md.txt)):

| Backend | Gateway service account needs |
| :--- | :--- |
| Cloud Run | `roles/run.invoker` (or a role with `run.routes.invoke`) on the service |
| Cloud Run functions | An invoker binding on the function. The API Gateway page names `roles/cloudfunctions.invoker`; the current [Cloud Run functions access page](https://docs.cloud.google.com/functions/docs/securing/managing-access-iam.md.txt) grants `roles/run.invoker` on the function with `gcloud run services add-iam-policy-binding`. Read the function's IAM policy first; if neither binding exists, propose the role from the access page that matches how the function is deployed, and ask the user if that's unclear. |
| App Engine behind IAP | `IAP-secured Web App User`, plus the extra permissions listed on the page, and a `jwt_audience` override (see below) |

1.  **Missing invoker role.** Read the backend's IAM policy (see
    [triage-and-logs.md](triage-and-logs.md#inspect-the-backend)). Cloud Run
    documents the messages its callers see
    ([Cloud Run troubleshooting](https://docs.cloud.google.com/run/docs/troubleshooting.md.txt)),
    for example `HTTP 403: Forbidden: Your client does not have permission to
    get URL from this server.` Fix, after approval, on the one service:

    ```bash
    gcloud run services add-iam-policy-binding {service} \
        --region={backend_region} \
        --member=serviceAccount:{service_account_email} \
        --role=roles/run.invoker --project={backend_project}
    ```

2.  **Wrong audience.** If an operation doesn't set `jwt_audience` or
    `disable_auth`, the gateway sets the token audience to the backend
    `address`
    ([OpenAPI 2.0 extensions](https://docs.cloud.google.com/api-gateway/docs/oasv2-extensions.md.txt)).
    App Engine and IAP expect their OAuth client ID instead, so those backends
    need `jwt_audience` (`jwtAudience` in
    [OpenAPI 3.x](https://docs.cloud.google.com/api-gateway/docs/oasv3-extensions.md.txt)).
    Set only one of `jwt_audience` and `disable_auth`.
3.  **Deleted or disabled service account.** Right after the account is deleted
    or disabled, the gateway may log `401` with `via_upstream`, and callers may
    also get `500` with no gateway log entry at all
    ([Troubleshooting overview](https://docs.cloud.google.com/api-gateway/docs/troubleshoot.md.txt)).
    Check with `gcloud iam service-accounts describe {service_account_email}`.
    Then read the gateway log from just before the `500`s began, without a
    status filter, and quote any `401` entries with `via_upstream` as evidence
    of when the account stopped working.
    Fix, after approval: re-enable a disabled account with
    `gcloud iam service-accounts enable {service_account_email}`, or create a
    new API config with
    `--backend-auth-service-account={active_service_account_email}` (an active
    account that has the invoker role) and deploy it with `gateways update`.
4.  **Backend is a Google Cloud API (`*.googleapis.com`).** These APIs require
    an access token and reject the ID token that the gateway sends to other
    backends, so it depends on the gateway's `effectiveStreamingMode`
    ([Securing backend services](https://docs.cloud.google.com/api-gateway/docs/securing-backend-services.md.txt)):
    -   `EFFECTIVE_STREAMING_MODE_DISABLED`: the gateway doesn't support calling
        Google Cloud APIs, and calls can fail with `401`. Tell the user this is
        a product limitation of non-streaming gateways.
    -   `EFFECTIVE_STREAMING_MODE_ENABLED`: the gateway sends an access token
        for its service account, with only the `cloud-platform` scope, to
        backends whose host ends in `.googleapis.com` or `.vertexai.goog`.
        Grant that service account the role that the target API requires. A
        backend with `disable_auth` (`disableAuth` in OpenAPI 3.x) gets no
        token. A streaming gateway that doesn't send access tokens yet switches
        at the next gateway rollout, or right away after an update to a new API
        config.

    For model routing to Agent Platform endpoints such as
    `aiplatform.googleapis.com`, the gateway's service account needs
    `roles/aiplatform.user`
    ([Configure model routing](https://docs.cloud.google.com/api-gateway/docs/model-routing-configure.md.txt)).
5.  **Backend reads the caller's JWT.** When backend authentication is on and
    the caller sent `Authorization`, the gateway copies it to
    `X-Forwarded-Authorization` and replaces `Authorization` with its own ID
    token. If the API config doesn't define JWT authentication, the backend
    must verify the JWT from `X-Forwarded-Authorization` itself. If it does,
    the JWT page says the gateway sends the authentication result in
    `X-Apigateway-Api-Userinfo` (the OpenAPI 2.0 extensions page names
    `X-Endpoint-API-UserInfo` instead). For changes to this setup, hand off
    to `api-gateway-backend-security-and-rate-limiting`.

## Fixes to avoid

-   Don't set `disable_auth: true` unless the backend allows unauthenticated
    calls by design, or it needs the caller's original `Authorization` header
    and can't use `X-Forwarded-Authorization`.
