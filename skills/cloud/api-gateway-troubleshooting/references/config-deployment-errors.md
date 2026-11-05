# API config and gateway errors

-   [api-configs create fails](#api-configs-create-fails): Lines 9-47
-   [Quota metric conflicts across API configs](#quota-metric-conflicts-across-api-configs): Lines 49-74
-   [Deleting an API config fails](#deleting-an-api-config-fails): Lines 76-80
-   [gateways create or update fails](#gateways-create-or-update-fails): Lines 82-90
-   [gcloud api-gateway commands fail](#gcloud-api-gateway-commands-fail): Lines 92-97

## api-configs create fails

**Service account does not exist.** An error in this form means the config
needs an explicit backend service account
([Troubleshooting overview](https://docs.cloud.google.com/api-gateway/docs/troubleshoot.md.txt)):

```
ERROR: (gcloud.api-gateway.api-configs.create) FAILED_PRECONDITION:
Service Account "projects/-/serviceAccounts/service_account_email" does not exist
```

Rerun the command with
`--backend-auth-service-account={service_account_email}`. Without that flag,
API Gateway uses the project's default Compute Engine service account
(`{project_number}-compute@developer.gserviceaccount.com`), which is created
when the Compute Engine API is enabled. The person who creates or updates an
API config or a gateway needs `iam.serviceAccounts.actAs` on the account, which
the `roles/iam.serviceAccountUser` role includes
([Configure your development environment](https://docs.cloud.google.com/api-gateway/docs/configure-dev-env.md.txt)).

**The OpenAPI document is rejected.** Hand off errors about the OpenAPI
document, such as an unsupported extension or an invalid path, parameter,
server, or security requirement, to the `api-gateway-openapi-spec-authoring`
skill, which matches the error text and fixes the spec. If that skill isn't
installed, fix what the error message names, run
`python3 scripts/lint_openapi_for_gateway.py {spec_path}`, and fix the `ERROR`
findings
([OpenAPI 2.0 limitations](https://docs.cloud.google.com/api-gateway/docs/openapi-limitations.md.txt),
[OpenAPI 3.x limitations](https://docs.cloud.google.com/api-gateway/docs/openapi-v3-limitations.md.txt)).

**Two configs at once.** If a second config was started before the first
finished, one or both may not be usable in a gateway; create the config again
after the first finishes
([Create an API config](https://docs.cloud.google.com/api-gateway/docs/creating-api-config.md.txt)).

**Limits.** API Gateway allows 50 APIs, 100 API configs per API, and 50
gateways per region
([Quotas and limits](https://docs.cloud.google.com/api-gateway/docs/quotas.md.txt)).
Suggest deleting unused configs (after approval) before requesting more.

## Quota metric conflicts across API configs

Symptom: requests to quota-enforced methods fail with
`{"code":500,"message":"Failed to call Service Control Quota."}`, and the
gateway logs show `jsonPayload.responseDetails="service_control_quota_error"`
with `httpRequest.status=500`. The same `responseDetails` with status `429`
means a caller legitimately exceeded the quota
([Troubleshooting overview](https://docs.cloud.google.com/api-gateway/docs/troubleshoot.md.txt)).

Cause: quota metrics and limits apply to the whole API, and only the values
from the most recently created API config are enforced. A gateway that still
serves an older config fails if its methods charge a metric that the newest
config renamed or removed
([About quotas](https://docs.cloud.google.com/api-gateway/docs/quotas-overview.md.txt)).

Confirm by comparing the newest config with each config that a gateway still
serves (commands in
[triage-and-logs.md](triage-and-logs.md#inspect-the-deployed-api-config)).
The documented fixes, both changes that need approval:

1.  Update every gateway of the API to the most recently created API config.
2.  Create a new API config that declares every metric used by the configs
    still deployed.

For changes to quota definitions, hand off to the
`api-gateway-backend-security-and-rate-limiting` skill.

## Deleting an API config fails

A config that a gateway still uses can't be deleted. First deploy a different
config to the gateway, or delete the gateway
([Create an API config](https://docs.cloud.google.com/api-gateway/docs/creating-api-config.md.txt)).

## gateways create or update fails

-   **Deadline above 600 seconds.** A non-streaming gateway rejects it at create
    or update time, even though the API config was accepted. See
    [backend-routing-and-timeouts.md](backend-routing-and-timeouts.md#504-and-slow-responses).
-   **Streaming mode change.** You can't update a gateway to change its
    streaming mode; create a new gateway
    ([Deploy an API to a gateway](https://docs.cloud.google.com/api-gateway/docs/deploying-api.md.txt)).
-   **Gateway limit.** A region allows 50 gateways.

## gcloud api-gateway commands fail

Running `gcloud api-gateway` commands needs an up-to-date Google Cloud CLI and
the required services enabled
([Troubleshooting overview](https://docs.cloud.google.com/api-gateway/docs/troubleshoot.md.txt)).
Check the CLI version and the enabled services before you look further.
