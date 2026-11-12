---
name: application-integration-authoring
metadata:
  version: "1.0.3"
  category: ApplicationDevelopment
description: >-
  Builds, versions, publishes, tests, and executes Google Cloud Application Integration
  workflows through the REST API and Python discovery client, and promotes versions across
  environments. Use when listing integrations, downloading or uploading integration versions
  as JSON, configuring API triggers or config variables, publishing drafts, invoking
  integrations, or automating CI/CD promotion. Do not use for initial region provisioning
  and IAM setup (use application-integration-basics) or diagnosing failed runs and logs (use application-integration-troubleshooting).
---

# Application Integration Authoring

Google Cloud Application Integration workflows are authored, versioned, published, and executed programmatically through the REST API (`https://integrations.googleapis.com/v1/...`) or the discovery-based Google API Python client (`googleapiclient.discovery.build("integrations", "v1")`).

There is no `gcloud integrations` command group, no Google-managed MCP server for Application Integration, and no documented Terraform resource for integrations or versions. Use `gcloud` only for authentication, enabling APIs, and IAM bindings. Use Terraform only for region provisioning (`google_integrations_client`), authentication profiles (`google_integrations_auth_config`), and Integration Connectors (`google_integration_connectors_connection`).

For initial project setup, region provisioning, and IAM role definitions, use the `application-integration-basics` skill. For diagnosing failed or stuck runs, execution logs, and quota errors, use the `application-integration-troubleshooting` skill.

## Attribution

**MUST READ**: Before executing any `gcloud` command, REST API call, or Python
discovery-client call, you MUST read
[Usage Attribution](references/attribution.md). For commands executed directly
in the terminal (never in generated scripts, Terraform, ADK agents, or user
code), prefix `gcloud` with
`CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:application-integration-authoring)"`
and add `agent-skills/1.0 (skill:application-integration-authoring)` to the
`User-Agent` header of `curl` requests.

## Safety and Confirmation Rules

- **Read-only operations run freely**: `integrations.list`, `integrations:search`, `versions.list`, `versions.get`, `versions:download`, `authConfigs.list`, and `executions.list`.
- **Confirm before any state change or execution**: Before creating, uploading, patching, publishing, unpublishing, testing, executing, scheduling, or deleting an integration or version, or modifying IAM or auth configs, show the exact command and payload to the user and get explicit confirmation.
- **Host changes require approval.** Before installing packages (`pip install`) or changing global gcloud or credential state (`gcloud config set ...` such as `auth/impersonate_service_account`, `gcloud auth application-default login` / `set-quota-project`), show the exact command and wait for the user's approval.
- **Never store secrets in config variables**: Config variables (`CONFIG_*`) are stored and exported in plain text. Always use authentication profiles (`projects.locations.authConfigs`) or the Secret Manager access task for credentials.

## Prerequisites Checklist

1. **Install Google Cloud CLI**: Follow [Install the Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt) if `gcloud` is not installed.
2. **Billing and project**: Ensure the Google Cloud project has an active billing account attached (required even when usage stays within the free tier), then set the target project (changes global gcloud state; get the user's approval first):
   ```bash
   gcloud config set project PROJECT_ID
   ```
3. **Enable required APIs**:
   ```bash
   gcloud services enable integrations.googleapis.com connectors.googleapis.com secretmanager.googleapis.com
   ```
4. **Provision the region**: Application Integration is regional: confirm the target region is supported on [Application Integration locations](https://docs.cloud.google.com/application-integration/docs/locations.md.txt) and use `us-central1` as a well-supported default when the user has no preference. The region is the `LOCATION` in every REST path; no `gcloud` default-region setting applies to Application Integration. The target `LOCATION` must be provisioned via the Cloud console or `POST .../clients:provision` before authoring integrations (see `application-integration-basics`).
5. **Authenticate**:
   - For `curl`: run `gcloud auth login` (changes host or credential state; get the user's approval first) and pass `-H "Authorization: Bearer $(gcloud auth print-access-token)"`.
   - For the Python client (install with `pip install "google-api-python-client>=2.100.0,<3" "google-auth>=2.20.0,<3"`): run `gcloud auth application-default login` and `gcloud auth application-default set-quota-project PROJECT_ID` (or set `GOOGLE_APPLICATION_CREDENTIALS` for a service account) (changes host or credential state; get the user's approval first).
   - For service account impersonation: run `gcloud config set auth/impersonate_service_account SA_EMAIL` (requires `roles/iam.serviceAccountTokenCreator`) (changes host or credential state; get the user's approval first).
6. **Verify IAM roles**:
   - Create, upload, or edit drafts: `roles/integrations.integrationEditor` (covers `versions:upload`, which needs `integrations.integrationVersions.create`, and `versions:publish`)
   - Publish or unpublish: `roles/integrations.integrationDeployer` or `roles/integrations.integrationEditor` (`roles/integrations.integrationDeployer` alone can publish an existing version but cannot upload via `versions:upload`), plus `roles/integrations.serviceAgent` granted to the Application Integration service agent (`service-PROJECT_NUMBER@gcp-sa-integrations.iam.gserviceaccount.com`)
   - Invoke integrations: `roles/integrations.integrationInvoker`
   - Act as the run-as service account: integrations created on or after October 15, 2026 with any trigger other than an API or Private trigger (for example Schedule, Cloud Scheduler, Cloud Pub/Sub, Salesforce, or Connector Event; Private triggers are exempt like API triggers, so a sub-integration whose only trigger is Private can be published without `runAsServiceAccount`) cannot be tested or published unless `runAsServiceAccount` is set (and region governance requires it for all integrations); whenever `runAsServiceAccount` is set, the user publishing or testing the version needs `roles/iam.serviceAccountUser` on it (and at runtime, the invoking caller or trigger service account needs `roles/iam.serviceAccountUser` on it).

## Decision Flow

| Goal | Action | Endpoint / Method |
| :--- | :--- | :--- |
| Inspect existing integrations in a region | List integrations, then list versions | `GET .../integrations` then `GET .../versions` |
| Export an integration version to source control | Download version JSON | `GET .../versions/VERSION_ID:download?fileFormat=JSON` |
| Create an integration or add a new `DRAFT` version from JSON | Upload version JSON (creates the integration if it does not exist, or adds a new `DRAFT` version; still needs `:publish`) | `POST .../integrations/INTEGRATION_NAME/versions:upload` |
| Create a brand-new integration and fail on a name clash | Create first `DRAFT` version with `newIntegration=true` (returns `ALREADY_EXISTS` if `INTEGRATION_NAME` already exists) | `POST .../integrations/INTEGRATION_NAME/versions?newIntegration=true` |
| Edit an existing `DRAFT` version | Check `lockHolder`, then patch or upload | `PATCH .../versions/VERSION_ID?updateMask=...` |
| Edit an `ACTIVE` (published) integration | Upload or create a new `DRAFT` version | `POST .../integrations/INTEGRATION_NAME/versions:upload` |
| Externalize environment-specific URLs or IDs | Define `CONFIG_<NAME>` and supply at publish | `integrationConfigParameters` + `versions:publish` |
| Store API keys, OAuth credentials, or certs | Create an authentication profile | `POST .../authConfigs` |
| Test an integration before production | Publish to a non-production project and invoke `:execute` | `POST .../versions/VERSION_ID:publish` then `POST .../integrations/INTEGRATION_NAME:execute` |
| Deploy a `DRAFT` to serve live traffic | Publish version with `configParameters` | `POST .../versions/VERSION_ID:publish` |
| Invoke a published integration synchronously | Call `:execute` with `api_trigger/TRIGGER_NAME` | `POST .../integrations/INTEGRATION_NAME:execute` |
| Invoke a published integration asynchronously | Call `:schedule` with `scheduleTime` | `POST .../integrations/INTEGRATION_NAME:schedule` |
| Promote a version across projects (CI/CD) | Download JSON -> Upload to target -> Publish | `:download` -> `:upload` -> `:publish` |

See [references/rest-api-cheatsheet.md](references/rest-api-cheatsheet.md) for full request parameters, query filters, and IAM permissions for each method.

## Core Authoring Workflow

### 1. List Integrations and Download a Version

List integrations in `LOCATION` and list versions for a specific `INTEGRATION_NAME`:

```bash
TOKEN="$(gcloud auth print-access-token)"

# List integrations in the region
curl -sS -H "Authorization: Bearer ${TOKEN}" \
  "https://integrations.googleapis.com/v1/projects/PROJECT_ID/locations/LOCATION/integrations?pageSize=50"

# List versions (ordered by most recently modified)
curl -sS -H "Authorization: Bearer ${TOKEN}" \
  "https://integrations.googleapis.com/v1/projects/PROJECT_ID/locations/LOCATION/integrations/INTEGRATION_NAME/versions?orderBy=last_modified_time%20desc"
```

Download a specific version (`VERSION_ID` is the UUID at the end of the version's `name` field) as portable JSON:

```bash
curl -sS -H "Authorization: Bearer ${TOKEN}" \
  "https://integrations.googleapis.com/v1/projects/PROJECT_ID/locations/LOCATION/integrations/INTEGRATION_NAME/versions/VERSION_ID:download?fileFormat=JSON" \
  | jq -r '.content' > integration-version.json
```

### 2. Understand the `IntegrationVersion` Structure

An `IntegrationVersion` JSON object contains four primary arrays and version-level settings:

- `triggerConfigs`: Entry points that start the workflow. Each entry requires a unique `triggerNumber`, plus `triggerType` (such as `API` or `PRIVATE_TRIGGER`), optional `triggerId` (auto-generated from `properties` if omitted; for API triggers: `api_trigger/TRIGGER_NAME`), and `startTasks` pointing to the first `taskId`.
- `taskConfigs`: Units of work. Each entry needs `task` (the task type, such as `EmailTask` in the public upload sample, or `FieldMappingTask` in a discovery enum description), a unique `taskId`, `parameters`, `nextTasks`, and optional `failurePolicy` or `errorCatcherId`.
- `integrationParameters`: Input, output, and transient variables (`key`, `dataType` such as `STRING_VALUE` or `JSON_VALUE`, `inputOutputType` of `IN`, `OUT`, `IN_OUT`, or `IN_OUT_TYPE_UNSPECIFIED`, and `defaultValue`).
- `integrationConfigParameters`: Environment-specific config variable definitions (`parameter` with key `` `CONFIG_<NAME>` `` and `parameter.defaultValue`; a top-level `value` in uploaded or created draft JSON is discarded, so per-environment values go in `configParameters` at publish).
- `runAsServiceAccount`: Dedicated user-managed service account email. When set and no authentication profile (`authConfig`) is configured on the task, it is used to generate the auth token for Connector (`Connectors`), REST (`Call REST Endpoint`), and Cloud Function tasks; an authentication profile configured on the task takes precedence over `runAsServiceAccount`.

Always use `triggerConfigs`, `taskConfigs`, and `integrationParameters`. Never use `triggerConfigsInternal`, `taskConfigsInternal`, or `integrationParametersInternal` because they are deprecated. See [references/integration-version-json.md](references/integration-version-json.md) for field schemas, `ValueType` shapes, and a minimal `IntegrationVersion` JSON template.

### 3. Create or Upload a `DRAFT` Version

Each integration allows up to 100 versions and 100 tasks, and `INTEGRATION_NAME` can be at most 64 characters. Calling `versions:upload` creates a new `DRAFT` version—creating the integration automatically if `INTEGRATION_NAME` does not exist yet, or adding the next `DRAFT` version if it already exists (for example, uploading onto version 5 creates version 6). The uploaded version is in `DRAFT` state and still requires `versions:publish` to serve traffic. Use `POST .../versions?newIntegration=true` (passing an `IntegrationVersion` JSON body) only when you explicitly want the call to fail with `ALREADY_EXISTS` if `INTEGRATION_NAME` already exists.

```bash
# Upload integration-version.json as a new DRAFT version
PAYLOAD="$(jq -n --rawfile content integration-version.json '{content: $content, fileFormat: "JSON"}')"

curl -sS --fail-with-body -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}" \
  "https://integrations.googleapis.com/v1/projects/PROJECT_ID/locations/LOCATION/integrations/INTEGRATION_NAME/versions:upload"
```

Capture the new `VERSION_ID` from `.integrationVersion.name` in the response (`projects/PROJECT_ID/locations/LOCATION/integrations/INTEGRATION_NAME/versions/VERSION_ID`).

### 4. Version States and Edit-Lock Rules

| State | Meaning | Editable? | Can Serve Triggers? |
| :--- | :--- | :--- | :--- |
| `DRAFT` | Version actively being edited; its edit lock is held by its author (`lockHolder` email) for 15 minutes from the last update | Yes (only by `lockHolder`) | No |
| `ACTIVE` | Published version serving live traffic | No | Yes |
| `SNAPSHOT` | Prior draft (when another author takes over in the console) or unpublished version (`PREVIOUSLY_PUBLISHED`) | No | No |
| `ARCHIVED` | Soft-deleted via `versions.delete` (no undelete; listed as `DELETED` on the Integration versions documentation page) | No | No |

- **Edit-lock enforcement**: A `DRAFT` version's edit lock is held by its author (`lockHolder`). Calling `versions:publish` or `versions.delete` on a `DRAFT` fails if the caller is not the `lockHolder` (`versions:publish` and `versions.delete` release any existing lock when they succeed).
- **No v1 lock-takeover API**: `takeoverEditLock` does **not** exist on `projects.locations.integrations.versions` in the v1 REST API (it only exists on `versions.testCases`). If a `DRAFT` is locked by another user, wait 15 minutes from `updateTime` for the lock to expire automatically, or click **Take Over** in the Cloud console (which converts the existing draft to `SNAPSHOT` and creates a new `DRAFT`).

### 5. Config Variables vs Authentication Profiles

- **Config variables (`CONFIG_<NAME>`)**: Use for non-secret environment values (backend hostnames, Pub/Sub topics, connection names). Define them in `integrationConfigParameters` on the draft (putting any default in `parameter.defaultValue`, because a top-level `value` on a draft is discarded) and pass their per-environment values in `configParameters` when calling `versions:publish`. **Gotcha**: Keys in `configParameters` at publish must **exactly match** a key in `integrationConfigParameters`, backticks included (for example, `` "`CONFIG_target_url`" ``); unknown keys are **silently ignored**, not rejected (`versions:publish` returns 200 and the default stays). Config variables cannot configure Integration Connectors entity operations or actions.
- **Authentication profiles (`authConfigs`)**: Use for API keys, OAuth 2.0 credentials, JWTs, OIDC tokens, SSL/TLS certificates, and service accounts. Auth profiles are regional resources (`projects/PROJECT_ID/locations/LOCATION/authConfigs/AUTH_CONFIG_ID`) and are **not** included when you download an integration version. Create them in each target project via `POST .../authConfigs` or Terraform `google_integrations_auth_config`.

### 6. Test, Publish, and Unpublish

- **Recommended testing path**: Test integrations by publishing the version in a non-production project (`versions:publish`) and invoking `integrations:execute` there.
  - **Note on `integrations:test`**: The v1 REST API includes `POST .../integrations/INTEGRATION_NAME:test` for testing a `DRAFT`, which requires `TestIntegrationsRequest.clientId` ("Required. This is used to identify the client on whose behalf the event will be executed."), but the public documentation does not specify what value to pass. Do not invent a `clientId` value; publish to a non-production project and call `:execute` instead. (Draft testing also cannot run `Approval`, `Suspend`, or `Timer` tasks, and Call REST Endpoint authentication profile changes only take effect after publishing.)
- **Publish (`versions:publish`)**: Deploys the version as `ACTIVE` and releases any edit lock (fails if the version is already `ACTIVE` or `ARCHIVED`, or if it is a `DRAFT` whose `lockHolder` differs from the caller). Any previously `ACTIVE` version is automatically unpublished, and dependent services switch to the newly published version.
  - **Gotcha**: Publishing a new version automatically cancels all suspended executions of the previous version.
  - **Gotcha**: Due to eventual consistency, the previous version can continue running for up to 10 minutes after a new version is published.
- **Unpublish (`versions:unpublish`)**: Moves the `ACTIVE` version to `SNAPSHOT` (tagged `PREVIOUSLY_PUBLISHED`; fails if the version is not `ACTIVE`) and stops triggers and dependent services.

```bash
# Publish VERSION_ID and supply config variable values (keys must exactly match integrationConfigParameters keys, backticks included; unknown keys are silently ignored)
curl -sS --fail-with-body -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -d '{"configParameters": {"`CONFIG_backend_url`": "https://api.example.com"}}' \
  "https://integrations.googleapis.com/v1/projects/PROJECT_ID/locations/LOCATION/integrations/INTEGRATION_NAME/versions/VERSION_ID:publish"
```

### 7. Execute (Sync) vs Schedule (Async)

Only an `ACTIVE` (published) version can be invoked via `execute` or `schedule`. For API triggers, `triggerId` is always `api_trigger/TRIGGER_NAME` (where `TRIGGER_NAME` is at most 64 characters). Passing `-` as `INTEGRATION_NAME` in `execute` runs all published integrations in that region that share the `triggerId`.

| Method | Mode | Max Timeout | Max API Input | Key Request Fields | Key Response Fields |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `integrations:execute` | Sync | 2 minutes | 8 MB | `triggerId`, `inputParameters`, `requestId`, `doNotPropagateError` | `executionId`, `outputParameters`, `parameters` |
| `integrations:schedule` | Async | 10 minutes | Not documented | `triggerId`, `scheduleTime` (RFC 3339), `inputParameters`, `requestId`, `userGeneratedExecutionId` | `executionInfoIds[]` |

- **Reading `outputParameters` and `executionId`**: In `ExecuteIntegrationsResponse`, `executionId` identifies the run, and `outputParameters` is a JSON object of output variables (system-generated keys such as `` `ExecutionId` `` are wrapped in backticks).
- **HTTP 200 does not prove every task succeeded**: If `doNotPropagateError` is `true`, or a task uses failure policy `IGNORE` or `NONE` with an alternate path, the HTTP call returns `200 OK` even when a task failed. Always verify the execution record via `executions.list?filter=execution_id="EXECUTION_ID"` (checking `executionDetails.state`, each task's `taskExecutionState`, and `ErrorInfo` in `Execution.responseParameters`; when `doNotPropagateError` is `true`, errors are also returned in event parameters as `PostWithTriggerIdExecutionException`). Do not rely on the legacy/deprecated `executionFailed` field.

See [references/triggers-and-execution.md](references/triggers-and-execution.md) for all trigger types, `ValueType` input formatting, OpenAPI spec generation, and suspension lifting and approval resolution.

## End-to-End Version and API Workflow Examples

In downloaded and uploaded `IntegrationVersion` JSON, an `EmailTask` uses four customer-visible parameter keys inside `taskConfigs[].parameters`: `"To"` (`stringArray` of recipient addresses), `"Subject"` (`stringValue`), `"BodyFormat"` (`stringValue`, such as `"PLAIN_TEXT"`), and `"TextBody"` (`stringValue`). Both runnable examples below also set `"runAsServiceAccount": "RUN_AS_SA"` (replace `RUN_AS_SA` with your dedicated service account email, such as `order-workflow-sa@PROJECT_ID.iam.gserviceaccount.com`; projects with governance require a run-as service account to publish, and the caller needs `roles/iam.serviceAccountUser` on it). Executing an `EmailTask` sends a real email, so always confirm the recipient address (`RECIPIENT_EMAIL`) and each state-changing command (upload, publish, and execute) with the user before running.

### Example 1: Upload, Publish, and Invoke Workflow with `curl`

This example uploads a runnable `IntegrationVersion` JSON (`versions:upload` creates `INTEGRATION_NAME` automatically if it does not exist yet, or adds a new `DRAFT` version if it does), publishes the draft, and invokes `:execute`. The caller must hold `roles/iam.serviceAccountUser` on `RUN_AS_SA` (projects with governance require a run-as service account to publish). Because `EmailTask` sends real email, confirm `RECIPIENT_EMAIL` and get user confirmation before running the upload, publish, and execute calls.

```bash
set -euo pipefail
export PROJECT_ID="my-project"
export LOCATION="us-central1"
export INTEGRATION_NAME="order-webhook"
export TRIGGER_NAME="order_api"
TOKEN="$(gcloud auth print-access-token)"
BASE_URL="https://integrations.googleapis.com/v1/projects/${PROJECT_ID}/locations/${LOCATION}"

# 1. Write an IntegrationVersion JSON file (set RUN_AS_SA and confirm RECIPIENT_EMAIL with user first; caller needs roles/iam.serviceAccountUser on RUN_AS_SA)
cat <<'EOF' > /tmp/version.json
{
  "description": "API-triggered order notification integration",
  "runAsServiceAccount": "RUN_AS_SA",
  "triggerConfigs": [
    {
      "label": "API Trigger",
      "triggerType": "API",
      "triggerNumber": "1",
      "triggerId": "api_trigger/order_api",
      "properties": {"Trigger name": "order_api"},
      "startTasks": [{"taskId": "1"}]
    }
  ],
  "taskConfigs": [
    {
      "task": "EmailTask",
      "taskId": "1",
      "displayName": "Send Email",
      "taskExecutionStrategy": "WHEN_ALL_SUCCEED",
      "parameters": {
        "To": {"key": "To", "value": {"stringArray": {"stringValues": ["RECIPIENT_EMAIL"]}}},
        "Subject": {"key": "Subject", "value": {"stringValue": "Order notification for $orderId$"}},
        "BodyFormat": {"key": "BodyFormat", "value": {"stringValue": "PLAIN_TEXT"}},
        "TextBody": {"key": "TextBody", "value": {"stringValue": "Processing order $orderId$."}}
      }
    }
  ],
  "integrationParameters": [
    {
      "key": "orderId",
      "dataType": "STRING_VALUE",
      "inputOutputType": "IN_OUT",
      "defaultValue": {"stringValue": "ORD-0000"}
    }
  ]
}
EOF

# 2. Upload as a new DRAFT version — creates INTEGRATION_NAME if it does not exist yet (confirm with user first)
UPLOAD_BODY="$(jq -n --rawfile content /tmp/version.json '{content: $content, fileFormat: "JSON"}')"
VERSION_NAME="$(curl -sS --fail-with-body -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${UPLOAD_BODY}" \
  "${BASE_URL}/integrations/${INTEGRATION_NAME}/versions:upload" \
  | jq -r '.integrationVersion.name')"
VERSION_ID="${VERSION_NAME##*/}"
[[ -n "${VERSION_ID}" && "${VERSION_ID}" != "null" ]] || { echo "upload failed: ${VERSION_NAME}" >&2; exit 1; }

# 3. Publish the DRAFT version (confirm with user first)
curl -sS --fail-with-body -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{}' \
  "${BASE_URL}/integrations/${INTEGRATION_NAME}/versions/${VERSION_ID}:publish"

# 4. Invoke the published version synchronously — sends a real email to RECIPIENT_EMAIL (confirm with user first)
curl -sS --fail-with-body -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -H "X-Server-Timeout: 120" \
  -d "{
    \"triggerId\": \"api_trigger/${TRIGGER_NAME}\",
    \"inputParameters\": {
      \"orderId\": {\"stringValue\": \"ORD-1001\"}
    }
  }" \
  "${BASE_URL}/integrations/${INTEGRATION_NAME}:execute" \
  | jq '{executionId, outputParameters}'
```

### Example 2: Python Discovery Client Workflow (Built from the API Reference)

No official Python sample is published on `docs.cloud.google.com`; the following workflow is built from the v1 API discovery document (`google-api-python-client`). The caller must hold `roles/iam.serviceAccountUser` on `RUN_AS_SA` (projects with governance require a run-as service account to publish). Because `EmailTask` sends real email, confirm `RECIPIENT_EMAIL` and each state-changing call (`upload`, `publish`, `execute`) with the user before running. Install dependencies first with `pip install "google-api-python-client>=2.100.0,<3" "google-auth>=2.20.0,<3"` (changes host or credential state; get the user's approval first).

```python
import json
from googleapiclient.discovery import build

PROJECT_ID = "PROJECT_ID"
LOCATION = "LOCATION"
INTEGRATION_NAME = "INTEGRATION_NAME"
TRIGGER_NAME = "TRIGGER_NAME"
RECIPIENT_EMAIL = "RECIPIENT_EMAIL"
parent = f"projects/{PROJECT_ID}/locations/{LOCATION}"
integration_path = f"{parent}/integrations/{INTEGRATION_NAME}"

service = build("integrations", "v1")
integrations_api = service.projects().locations().integrations()
versions_api = integrations_api.versions()

# 1. List existing integrations (read-only)
listed = integrations_api.list(parent=parent, pageSize=20).execute()
for item in listed.get("integrations", []):
    print(item["name"], "active=", item.get("active"))

# 2. Upload a DRAFT version — creates INTEGRATION_NAME if it does not exist yet (set RUN_AS_SA and confirm RECIPIENT_EMAIL and action with user before running; caller needs roles/iam.serviceAccountUser on RUN_AS_SA)
version_dict = {
    "description": "API-triggered order notification integration",
    "runAsServiceAccount": "RUN_AS_SA",
    "triggerConfigs": [{
        "label": "API Trigger",
        "triggerType": "API",
        "triggerNumber": "1",
        "triggerId": f"api_trigger/{TRIGGER_NAME}",
        "properties": {"Trigger name": TRIGGER_NAME},
        "startTasks": [{"taskId": "1"}],
    }],
    "taskConfigs": [{
        "task": "EmailTask",
        "taskId": "1",
        "displayName": "Send Email",
        "taskExecutionStrategy": "WHEN_ALL_SUCCEED",
        "parameters": {
            "To": {"key": "To", "value": {"stringArray": {"stringValues": [RECIPIENT_EMAIL]}}},
            "Subject": {"key": "Subject", "value": {"stringValue": "Order notification for $orderId$"}},
            "BodyFormat": {"key": "BodyFormat", "value": {"stringValue": "PLAIN_TEXT"}},
            "TextBody": {"key": "TextBody", "value": {"stringValue": "Processing order $orderId$."}},
        },
    }],
    "integrationParameters": [{
        "key": "orderId",
        "dataType": "STRING_VALUE",
        "inputOutputType": "IN_OUT",
        "defaultValue": {"stringValue": "ORD-0000"},
    }],
}
upload_resp = versions_api.upload(
    parent=integration_path,
    body={"content": json.dumps(version_dict), "fileFormat": "JSON"},
).execute()
version_name = upload_resp["integrationVersion"]["name"]

# 3. Publish the DRAFT version (confirm with user before running)
versions_api.publish(
    name=version_name,
    body={"configParameters": {}},
).execute()

# 4. Invoke the published version synchronously — sends a real email to RECIPIENT_EMAIL (confirm with user before running)
exec_resp = integrations_api.execute(
    name=integration_path,
    body={
        "triggerId": f"api_trigger/{TRIGGER_NAME}",
        "inputParameters": {"orderId": {"stringValue": "ORD-1001"}},
    },
).execute()
print("executionId:", exec_resp.get("executionId"))
print("outputParameters:", exec_resp.get("outputParameters"))
```

## Common Task Gotchas and Limits

- **Data limits**: Total cumulative integration data (including inputs and outputs) is capped at 30 MB. Above 10 MB, local execution logging is automatically disabled.
- **Data Mapping**: Input and output types must match (cast with `TO_STRING`, `TO_INT`, and so on). Always set a fallback value or null inputs fail the task.
- **Call REST Endpoint**: Reaches the public internet only (cannot reach VPC-internal hosts). Fails on HTTP 4xx and 5xx responses. Request max 20 MB, response max 34 MB, max 100 concurrent calls.
- **JavaScript**: Uses the V8 engine (Rhino was deprecated January 24, 2025). Never remove the `executesScript(event)` entrypoint. Max script request size is 25 MB.
- **Connectors task**: Requires an active Integration Connectors connection (billed separately). Timeout is 3 minutes; Application Integration quotas cap data to and from connections at 8 MB (Integration Connectors quotas list a 10 MB Connectors task payload limit; response max 20 MB).
- **Approval vs Suspend**: Approval tasks can be approved or rejected via `POST .../executions/EXECUTION_ID/suspensions/SUSPENSION_ID:resolve` with body `{"suspension": {"eventExecutionInfoId": "EXECUTION_ID", "integration": "INTEGRATION_NAME", "taskId": "TASK_ID", "state": "LIFTED"}}` (or `"REJECTED"`), which is the same call the Cloud console Approve/Reject buttons make and requires `integrations.suspensions.resolve`. Suspend tasks are resumed via `POST .../integrations/INTEGRATION_NAME/executions/EXECUTION_ID/suspensions/SUSPENSION_ID:lift` (where `-` can replace `INTEGRATION_NAME` and either `EXECUTION_ID` or `SUSPENSION_ID`, provided at least one of `EXECUTION_ID` or `SUSPENSION_ID` is concrete; accepts an optional `suspensionResult` defaulting to `Resolved`), which requires `integrations.suspensions.lift`. Listing suspensions (`suspensions.list`) requires `integrations.suspensions.list`. All three permissions are included in `roles/integrations.suspensionResolver` (and `roles/integrations.integrationAdmin`); resuming also requires `roles/iam.serviceAccountUser` on the integration's run-as service account, requires user confirmation first, and runs the remainder of the execution in async mode.
- **Loops and Sub-integrations**: For Each Loop and While Loop allow up to 8,000 iterations; For Each Parallel allows up to 10,000 iterations (default parallelism 50). For sub-integration calls (`Call Integration`, `For Each Loop`, `For Each Parallel`), child responses/output parameters are returned to the parent only in `SYNC` mode (`ASYNC` calls return no output parameters); avoid `SYNC` mode if the sub-integration exceeds 2 minutes or includes an Approval task.

See [references/tasks-and-gotchas.md](references/tasks-and-gotchas.md) for the full task catalog, limits, variable reference syntax, and retry strategies.

## Promoting Between Environments (CI/CD)

To promote an integration from development to staging or production:

1. Externalize environment-specific values (endpoints, project IDs, connection names) as `CONFIG_<NAME>` config variables.
2. Provision the target region, run-as service account, Integration Connectors connections, and authentication profiles (`authConfigs`) in the target project first (these infrastructure resources are not created by version uploads).
3. Download the tested version JSON (`versions:download?fileFormat=JSON`), commit it to Git alongside per-environment config files, rewrite `.runAsServiceAccount` to the target environment's run-as service account (`jq --arg sa "$RUN_AS_SA" '.runAsServiceAccount = $sa' integration.json > integration.env.json`) before uploading, and run `versions:upload` + `versions:publish` from Cloud Build or your CI runner (`versions:upload` creates the integration automatically in the target project if it does not exist yet, producing a `DRAFT` that `:publish` activates).

See [references/cicd-promotion.md](references/cicd-promotion.md) for the complete promotion checklist and a ready-to-use Cloud Build pipeline.

## Cleanup and Cost Management

- **Pricing**: An active billing account must be attached to the project even when usage stays within the monthly free tier. Application Integration offers a monthly free tier for executions, data processed, and Google service connector nodes, after which executions, data processed, and Integration Connectors nodes incur charges. Review current thresholds and rates on the [Application Integration pricing page](https://cloud.google.com/application-integration/pricing) and estimate costs with the Google Cloud Pricing Calculator.
- **Unpublish to stop triggers**: Run `POST .../versions/VERSION_ID:unpublish` (after user confirmation) to stop scheduled, Pub/Sub, or API triggers from firing.
- **Delete versions or integrations**: `DELETE .../versions/VERSION_ID` archives a single version (deleting all versions deletes the integration). `DELETE .../integrations/INTEGRATION_NAME` permanently deletes the integration and all its versions.
- **Connector nodes**: Unpublishing or deleting an integration does not delete Integration Connectors connections. Delete unused connections at `https://console.cloud.google.com/connectors/connections` to stop hourly node charges.

## Reference Guides

- [Usage Attribution](references/attribution.md): Usage attribution for `gcloud` CLI commands, direct `curl` REST calls, and Python discovery-client snippets run in the terminal.
- [REST API Cheatsheet](references/rest-api-cheatsheet.md): v1 and v2 endpoints, parameters, filters, and IAM permissions.
- [IntegrationVersion JSON Reference](references/integration-version-json.md): Schema for `triggerConfigs`, `taskConfigs`, `integrationParameters`, `ValueType`, and config variables.
- [Triggers and Execution Reference](references/triggers-and-execution.md): Trigger types, `triggerId` formats, `:execute` vs `:schedule`, OpenAPI generation, and lifting or resolving suspensions.
- [Tasks and Gotchas Reference](references/tasks-and-gotchas.md): Task-by-task rules, quotas, variable reference syntax, and error handling strategies.
- [CI/CD Promotion Reference](references/cicd-promotion.md): Cross-project promotion checklist, environment config pattern, and Cloud Build workflow.
