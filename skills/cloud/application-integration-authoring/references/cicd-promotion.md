# CI/CD Promotion Reference

This guide explains how to promote Application Integration versions across projects and environments (such as development, staging, and production) using `versions:download`, `versions:upload`, `versions:publish`, and Cloud Build.

- [What Travels in a Downloaded Version vs What Does Not](#what-travels-in-a-downloaded-version-vs-what-does-not): Lines 11-23
- [Environment Parameterization Pattern](#environment-parameterization-pattern): Lines 24-43
- [Step-by-Step Promotion Workflow](#step-by-step-promotion-workflow): Lines 44-103
- [Cloud Build Pipeline Example (`cloudbuild.yaml`)](#cloud-build-pipeline-example-cloudbuildyaml): Lines 104-155
- [Post-Promotion Checks and Rollout Gotchas](#post-promotion-checks-and-rollout-gotchas): Lines 156-161

## What Travels in a Downloaded Version vs What Does Not

Downloading an integration version (`GET .../versions/VERSION_ID:download?fileFormat=JSON`) produces a portable JSON representation, but external dependencies must be created separately in each target project.

| Included in `versions:download` JSON | NOT Included (Must Provision in Target Project) |
| :--- | :--- |
| `triggerConfigs` (trigger types, IDs, properties) | Regional client provisioning (`clients:provision` or `google_integrations_client`) |
| `taskConfigs` (tasks, parameters, edges, retry policies) | Integration Connectors connections (`google_integration_connectors_connection`) |
| `integrationParameters` (inputs, outputs, defaults) | Authentication profiles (`projects.locations.authConfigs` or `google_integrations_auth_config`) |
| `integrationConfigParameters` (config variable definitions) | Run-as service account IAM resources and role bindings (`roles/iam.serviceAccountUser`) |
| `runAsServiceAccount` (**travels in JSON, but must be rewritten** to the target environment's run-as service account email before uploading) | Functional test cases (`versions.testCases` — download/upload separately) |
| `errorCatcherConfigs`, `cloudLoggingDetails`, `description` | - |

## Environment Parameterization Pattern

1. **Use config variables (`CONFIG_<NAME>`) and per-environment `RUN_AS_SA` settings**:
   - Externalize environment-specific backend URLs, project IDs, Pub/Sub topic paths, and Integration Connectors connection names as `CONFIG_<NAME>` in `integrationConfigParameters`.
   - Because `IntegrationVersion.runAsServiceAccount` travels in `versions:download` JSON with the source environment's service account email, store `RUN_AS_SA` alongside `configParameters` in each per-environment config file (for example, `configs/staging.json` and `configs/prod.json`), rewrite `.runAsServiceAccount` before uploading, and pass `{configParameters}` to `versions:publish` (**gotcha**: keys in `configParameters` must **exactly match** a key in `integrationConfigParameters`, backticks included, such as `` "`CONFIG_target_url`" ``; unknown keys are **silently ignored**, not rejected—publish returns 200 and the default stays):
     ```json
     {
       "RUN_AS_SA": "order-workflow-sa@my-staging-project.iam.gserviceaccount.com",
       "configParameters": {
         "`CONFIG_backend_url`": "https://staging-api.example.com",
         "`CONFIG_pubsub_topic`": "projects/my-staging-project/topics/orders"
       }
     }
     ```
2. **Never store secrets in config variables**:
   - Config variables are stored and exported in plain text, and variable masking does not redact downloaded files.
   - Store secrets in regional authentication profiles (`authConfigs`) or fetch them at runtime with the Secret Manager access task.
3. **Know the connector limitation**:
   - Config variables cannot configure Integration Connectors entity operations or actions. Keep connection names and schemas aligned across environments.

## Step-by-Step Promotion Workflow

### Step 1: Export from the Source Environment

Download the verified version from the development project and save the inner `.content` JSON to your repository:

```bash
TOKEN="$(gcloud auth print-access-token)"
curl -sS -H "Authorization: Bearer ${TOKEN}" \
  "https://integrations.googleapis.com/v1/projects/SOURCE_PROJECT_ID/locations/LOCATION/integrations/INTEGRATION_NAME/versions/VERSION_ID:download?fileFormat=JSON" \
  | jq -r '.content' > integrations/INTEGRATION_NAME/integration.json
```

### Step 2: Prepare the Target Environment

Before running the promotion pipeline in `TARGET_PROJECT_ID`:

- Enable `integrations.googleapis.com`, `connectors.googleapis.com`, and `secretmanager.googleapis.com`.
- Provision `LOCATION` in `TARGET_PROJECT_ID` (see the `application-integration-basics` skill).
- Create the required Integration Connectors connections, authentication profiles (`authConfigs`), and the integration's target run-as service account (`RUN_AS_SA`) in `TARGET_PROJECT_ID` (`IntegrationVersion.runAsServiceAccount` travels in `versions:download` JSON and must be rewritten to `RUN_AS_SA` before uploading).
- Grant the CI runner service account (such as the Cloud Build service account):
  - Grant `roles/integrations.integrationEditor` (covers `versions:upload` and `versions:publish`); `roles/integrations.integrationDeployer` alone can publish but cannot upload (it holds `integrations.integrationVersions.list`, `get`, and `deploy`, not `integrations.integrationVersions.create`, which `versions:upload` needs)
  - `roles/iam.serviceAccountUser` on the integration's `runAsServiceAccount` (required for the principal publishing or testing the version whenever `runAsServiceAccount` is set)

### Step 3: Upload and Publish in the Target Environment

Before uploading to `TARGET_PROJECT_ID`, rewrite `.runAsServiceAccount` in the downloaded JSON to the target environment's run-as service account (`RUN_AS_SA`). Calling `versions:upload` creates `INTEGRATION_NAME` automatically in `TARGET_PROJECT_ID` if it does not exist yet (or adds a new `DRAFT` version if it already exists), so no separate "create integration beforehand" step is needed. Because `versions:upload` creates a `DRAFT`, follow it with `versions:publish` to activate the uploaded version with the target environment's `configParameters`. Confirm the exact commands and payloads with the user before running any upload or publish call interactively.

```bash
set -euo pipefail
TOKEN="$(gcloud auth print-access-token)"
BASE_URL="https://integrations.googleapis.com/v1/projects/TARGET_PROJECT_ID/locations/LOCATION/integrations/INTEGRATION_NAME"
RUN_AS_SA="$(jq -r '.RUN_AS_SA' configs/prod.json)"

# 1. Rewrite runAsServiceAccount for the target environment and wrap into UploadIntegrationVersionRequest
jq --arg sa "${RUN_AS_SA}" '.runAsServiceAccount = $sa' \
  integrations/INTEGRATION_NAME/integration.json > /tmp/integration.env.json

UPLOAD_PAYLOAD="$(jq -n --rawfile content /tmp/integration.env.json \
  '{content: $content, fileFormat: "JSON"}')"

# 2. Upload the DRAFT version (creates INTEGRATION_NAME if it does not exist yet) and extract its VERSION_ID (confirm with user before running)
VERSION_NAME="$(curl -sS --fail-with-body -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${UPLOAD_PAYLOAD}" \
  "${BASE_URL}/versions:upload" \
  | jq -r '.integrationVersion.name')"
VERSION_ID="${VERSION_NAME##*/}"
[[ -n "${VERSION_ID}" && "${VERSION_ID}" != "null" ]] || { echo "upload failed: ${VERSION_NAME}" >&2; exit 1; }

# 3. Publish the uploaded version with environment-specific configParameters (keys must exactly match integrationConfigParameters keys, backticks included, or unknown keys are silently ignored; confirm with user before running)
PUBLISH_PAYLOAD="$(jq '{configParameters}' configs/prod.json)"
curl -sS --fail-with-body -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${PUBLISH_PAYLOAD}" \
  "${BASE_URL}/versions/${VERSION_ID}:publish"
```

## Cloud Build Pipeline Example (`cloudbuild.yaml`)

This Cloud Build pipeline rewrites `.runAsServiceAccount` to `_RUN_AS_SA`, uploads `integration.env.json` to `_INTEGRATION_NAME` in `_TARGET_PROJECT_ID` (`versions:upload` creates `_INTEGRATION_NAME` automatically if it does not exist yet, or adds a new `DRAFT` version if it does), and publishes that `DRAFT` using `_CONFIG_FILE`. Trigger it after pull request approval or release tag creation.

```yaml
steps:
  - name: "gcr.io/google.com/cloudsdktool/google-cloud-cli:slim"
    entrypoint: "bash"
    args:
      - "-c"
      - |
        set -euo pipefail
        apt-get update -qq && apt-get install -y -qq jq >/dev/null

        TOKEN="$$(gcloud auth print-access-token)"
        BASE_URL="https://integrations.googleapis.com/v1/projects/${_TARGET_PROJECT_ID}/locations/${_LOCATION}/integrations/${_INTEGRATION_NAME}"

        echo "Rewriting runAsServiceAccount to ${_RUN_AS_SA} and uploading ${_INTEGRATION_NAME} to ${_TARGET_PROJECT_ID} (${_LOCATION})..."
        jq --arg sa "${_RUN_AS_SA}" '.runAsServiceAccount = $$sa' "${_INTEGRATION_FILE}" > /tmp/integration.env.json
        UPLOAD_PAYLOAD="$$(jq -n --rawfile content /tmp/integration.env.json '{content: $$content, fileFormat: "JSON"}')"
        UPLOAD_RESP="$$(curl -sS --fail-with-body -X POST \
          -H "Authorization: Bearer $${TOKEN}" \
          -H "Content-Type: application/json" \
          -d "$${UPLOAD_PAYLOAD}" \
          "$${BASE_URL}/versions:upload")"

        VERSION_NAME="$$(echo "$${UPLOAD_RESP}" | jq -r '.integrationVersion.name')"
        VERSION_ID="$${VERSION_NAME##*/}"
        [[ -n "$${VERSION_ID}" && "$${VERSION_ID}" != "null" ]] || { echo "upload failed: $${VERSION_NAME}" >&2; exit 1; }
        echo "Created draft version: $${VERSION_ID}"

        echo "Publishing version $${VERSION_ID} with ${_CONFIG_FILE}..."
        PUBLISH_PAYLOAD="$$(jq '{configParameters}' "${_CONFIG_FILE}")"
        curl -sS --fail-with-body -X POST \
          -H "Authorization: Bearer $${TOKEN}" \
          -H "Content-Type: application/json" \
          -d "$${PUBLISH_PAYLOAD}" \
          "$${BASE_URL}/versions/$${VERSION_ID}:publish"
        echo "Published version $${VERSION_ID} successfully."

substitutions:
  _TARGET_PROJECT_ID: "PROJECT_ID"
  _LOCATION: "us-central1"
  _INTEGRATION_NAME: "INTEGRATION_NAME"
  _INTEGRATION_FILE: "integrations/INTEGRATION_NAME/integration.json"
  _CONFIG_FILE: "configs/staging.json"
  _RUN_AS_SA: "order-workflow-sa@PROJECT_ID.iam.gserviceaccount.com"

options:
  logging: CLOUD_LOGGING_ONLY
```

## Post-Promotion Checks and Rollout Gotchas

- **Eventual consistency (up to 10 minutes)**: After `versions:publish` succeeds, the previous `ACTIVE` version can continue handling traffic for up to 10 minutes while the new version propagates across the region.
- **Suspended executions are canceled**: Publishing a new version automatically cancels all suspended executions (`Suspend` or `Approval` tasks) waiting on the previous version. Check `executions.list?filter=state%3DSUSPENDED` before promoting to production if long-running pauses are active.
- **Version cap (100 versions max)**: Each integration supports at most 100 versions. In high-frequency CI pipelines, archive old unused snapshots with `DELETE .../versions/OLD_VERSION_ID` (confirm with the user before deleting any version interactively) so uploads do not fail at the 100-version limit.
- **Smoke testing**: After promotion, run an API trigger smoke check via `integrations:execute` (reading `outputParameters` and verifying `executionDetails.state` and per-task states via `executions.list?filter=execution_id%3D%22EXECUTION_ID%22`) or upload and run functional test cases via `versions.testCases:execute`.
