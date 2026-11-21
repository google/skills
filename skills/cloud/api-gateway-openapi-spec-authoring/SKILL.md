---
name: api-gateway-openapi-spec-authoring
metadata:
  version: "1.0.0"
  category: ApplicationDevelopment
description: >-
  Writes, migrates, and fixes OpenAPI specs for Google Cloud API Gateway. Use
  when converting an OpenAPI 2.0 (Swagger) spec to OpenAPI 3.x, writing a new
  OpenAPI 3.x spec, or fixing a failed "gcloud api-gateway api-configs create",
  such as "extension is only supported in OpenAPI 2.x". Also use when quotas
  set with x-google-quota are never enforced, or when a backend receives path
  parameters as query parameters. Don't use for adding or debugging MCP tools
  (use api-gateway-mcp-server), backend lockdown or HTTP 429 tuning (use
  api-gateway-backend-security-and-rate-limiting), Cloud Endpoints, Apigee, or
  GKE Gateway API.
---

# API Gateway OpenAPI Spec Authoring

API Gateway accepts API configs in OpenAPI 2.0, 3.0.x, and 3.1.x. The Google extensions in OpenAPI 3.x have a different structure from the OpenAPI 2.0 extensions:

- A required root `x-google-api-management` block names the backends.
- `x-google-backend` is a string that references one of these backends.
- The JWT settings move into `x-google-auth`. The metrics and quotas move into `x-google-api-management`.

Use this skill to migrate an OpenAPI 2.0 spec, write a new OpenAPI 3.x spec, or fix an API config that fails to create.

## Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read [Usage Attribution](references/attribution.md). For commands executed
directly in the terminal (never in generated scripts, Terraform, or user code),
prefix `gcloud` with
`CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:api-gateway-openapi-spec-authoring)"`
and append `agent-skills/1.0 (skill:api-gateway-openapi-spec-authoring)` to `User-Agent` headers.

## Prerequisites

1. **Install the tools:**
   - Install the [Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt). Then update it with `gcloud components update`. **Rationale:** an old CLI can fail when it uploads an OpenAPI 3.x API config.
   - Install Python 3.10 or later and PyYAML for the validator script. A JSON spec does not need PyYAML.
     ```bash
     pip install "PyYAML>=6.0,<7.0"
     ```
2. **Authenticate, and select the project, billing, and location:**
   - Run `gcloud auth login`.
   - Select a project with `gcloud config set project {project_id}`, or create one with `gcloud projects create {project_id}`.
   - Make sure that an active billing account is linked to `{project_id}`. API Gateway has a free monthly allowance of API calls, but it still needs an active billing account. For current prices, see [API Gateway pricing](https://cloud.google.com/api-gateway/pricing).
   - Use `us-central1` as the default `--location` for gateway commands. For the other supported regions, see [API Gateway deployment model](https://docs.cloud.google.com/api-gateway/docs/deployment-model.md.txt).
3. **Enable the required Google Cloud APIs:**
   ```bash
   gcloud services enable \
     apigateway.googleapis.com \
     servicemanagement.googleapis.com \
     servicecontrol.googleapis.com \
     --project={project_id}
   ```
4. **Verify the IAM roles (use the most restrictive role for each step):**
   - To create and update the API, API configs, and gateways: API Gateway Admin (`roles/apigateway.admin`) on `{project_id}`.
   - To run the `gcloud services enable` commands: Service Usage Admin (`roles/serviceusage.serviceUsageAdmin`) on `{project_id}`.
   - To reference the gateway service account in an API config: Service Account User (`roles/iam.serviceAccountUser`) on `{gateway_sa_email}`.
   - For a Cloud Run backend that requires authentication: grant `{gateway_sa_email}` the Cloud Run Invoker role (`roles/run.invoker`) on the service.

## Decision Matrix

| Task | Required Mechanism | Critical Guardrail | Detailed Reference |
| --- | --- | --- | --- |
| Migrate an OpenAPI 2.0 (`swagger: "2.0"`) config | Convert the standard fields, then move each Google extension to its OpenAPI 3.x form. | A converter such as Swagger Editor leaves every `x-google-*` extension in its OpenAPI 2.0 form. It also writes `servers` without `x-google-endpoint`, so the API loses its base path. **Rationale:** API Gateway rejects most OpenAPI 2.0 extensions in a 3.x spec with `The '{extension}' extension is only supported in OpenAPI 2.x`. | [OpenAPI 2.0 to 3.x Migration](references/openapi-2-to-3-migration.md) |
| Route requests to backends | Root `x-google-api-management.backends.{backend_name}` + `x-google-backend: {backend_name}` at the root or on an operation | Set `pathTranslation` on every backend. **Rationale:** the default is `APPEND_PATH_TO_ADDRESS` for a root `x-google-backend`, but `CONSTANT_ADDRESS` for an operation-level one. `CONSTANT_ADDRESS` sends every request to the address unchanged, and sends path parameters as query parameters. `APPEND_PATH_TO_ADDRESS` appends the full request path, with the base path. NEVER set `x-google-backend` on a path item: API Gateway rejects it. | [Extensions and Limits](references/openapi-3-extensions-and-limits.md#backends) |
| Authenticate callers | JWT: `type: oauth2` scheme with `x-google-auth` (`issuer`, `jwksUri`, `audiences`). API key: `type: apiKey` scheme with `x-api-key` in a header, or `key` or `api_key` in the query. | API Gateway does not check OAuth scopes. In a `security` list, put an API key in every alternative (OR) or in none. NEVER put two JWT schemes in one requirement object (AND). **Rationale:** API Gateway rejects these combinations. If the user asks for one of them, such as a JWT or an API key as alternatives, do not write it in the spec. Explain the rule, and write a supported option, such as an API key in every alternative or a separate path for each kind of caller. | [Extensions and Limits](references/openapi-3-extensions-and-limits.md#security) |
| Add quotas | `x-google-api-management.metrics` and `quota.limits` + `x-google-quota: {metric_name: cost}` on each operation | NEVER rely on `x-google-quota` at the root or path level. **Rationale:** in OpenAPI 3.x, API Gateway ignores it there without an error. Require an API key on each operation that has a quota, and keep each metric name the same in every API config. | [Extensions and Limits](references/openapi-3-extensions-and-limits.md#quotas) |
| Set the base path and CORS | One `servers` entry with `x-google-endpoint`, such as `url: /v1` | API Gateway ignores `servers` entries without `x-google-endpoint`. `allowCors: true` only passes CORS requests to the backend. **Rationale:** the gateway does not add CORS headers, so the backend must answer them. | [Extensions and Limits](references/openapi-3-extensions-and-limits.md#servers-base-path-and-cors) |
| Fix a failed `api-configs create` | Match the error text to the error table, and fix the spec. | Fix the spec before you retry, unless the error is about IAM or another `api-configs create` that runs. **Rationale:** API Gateway returns the same error for the same spec. | [API Config Errors](references/api-config-errors.md) |
| Expose operations as MCP tools | The `api-gateway-mcp-server` skill | MCP adds rules for tool names, descriptions, and `tools/list` security. If that skill is not installed, use this skill for the OpenAPI 3.x spec, and follow the [Configure MCP](https://docs.cloud.google.com/api-gateway/docs/mcp-configure.md.txt) guide for the MCP extensions. | - |

## Execution Workflow and Validation Loop

1. **Get the current spec:**
   - Use the spec file in the user's repository. If there is no file, find the active API config of the gateway:
     ```bash
     gcloud api-gateway gateways describe {gateway_id} --location={region} --project={project_id} --format="value(apiConfig)"
     ```
   - The output is `projects/{project}/locations/global/apis/{api_id}/configs/{config_id}`. Print the spec of that config:
     ```bash
     gcloud api-gateway api-configs describe {config_id} --api={api_id} --project={project_id} --view=FULL \
       --format="value(openapiDocuments[0].document.contents)" | tr '_-' '/+' | base64 --decode
     ```
   - gcloud prints the contents in URL-safe base64, so `tr` changes two characters before `base64 --decode`. If the config has more than one OpenAPI document, change `[0]` to `[1]`, `[2]`, and so on.
2. **Write the OpenAPI 3.x spec:**
   - For an OpenAPI 2.0 spec, follow [OpenAPI 2.0 to 3.x Migration](references/openapi-2-to-3-migration.md), and compare your result with its complete converted example.
   - For a new spec, start from the template in [Extensions and Limits](references/openapi-3-extensions-and-limits.md#new-spec-template).
   - Set `openapi` to a 3.0.x or 3.1.x version. The examples use `3.0.4`. In OpenAPI 3.1, give each schema one `type`. **Rationale:** API Gateway rejects a type list such as `type: ["string", "null"]`.
   - Give every operation a unique `operationId` and a `responses` object, and use only local `$ref` values. **Rationale:** API Gateway rejects an operation without `operationId` or `responses`, two `operationId` values that give the same method name, such as `getItem` and `get-Item`, and a `$ref` to a URL.
3. **Run the deterministic validation loop on every spec that you write or change, before you answer or create the API config:**
   ```bash
   python3 scripts/validate_apigw_openapi.py --spec={spec_file}
   ```
   - The script path is relative to the directory of this skill. If you only return the spec in your reply, write it to a temporary file, and run the script on that file before you answer.
   - If the script exits with code `1` (`"status": "FAIL"`), fix every error in `{spec_file}`, and run the script again. Continue until it exits with code `0` (`"status": "PASS"`).
   - If the script exits with code `2`, fix the file path or the YAML/JSON syntax error that stderr shows, or install PyYAML.
   - Read every warning, such as a backend without `pathTranslation`, a quota on an operation without an API key, or `allowCors`. Fix it, or tell the user why you keep it.
   - The script does not check every rule. A PASS means that it found none of the API Gateway problems that this skill describes. It does not check general OpenAPI validity, such as a `$ref` to a schema that does not exist. **Rationale:** only `api-configs create` in step 5 shows that API Gateway accepts the spec. Do not tell the user that the spec deploys because the script passed.
4. **Summarize the spec for the user, and get approval before you deploy.** State each of these points:
   - Each OpenAPI 2.0 extension that you moved or removed, such as `x-google-allow`, which OpenAPI 3.x does not support. Also state each other change, such as an added `operationId` or a fixed address.
   - The `pathTranslation` of each backend (`backend_path_translation` in the script output), and each operation whose path parameters now go to the backend as query parameters (`path_parameters_as_query`). With `APPEND_PATH_TO_ADDRESS`, the backend also receives the base path.
   - Which operations need a JWT or an API key, which backends receive an ID token and with which audience, and that API Gateway does not check OAuth scopes.
   - The quota metrics and limits, and that each metric name matches the current API config.
5. **Create a new API config and update the gateway** (request human approval before you update a production gateway):
   ```bash
   gcloud api-gateway api-configs create {new_config_id} \
     --api={api_id} \
     --openapi-spec={spec_file} \
     --backend-auth-service-account={gateway_sa_email} \
     --project={project_id}

   gcloud api-gateway gateways update {gateway_id} \
     --api={api_id} \
     --api-config={new_config_id} \
     --location={region} \
     --project={project_id}
   ```
   - For a new gateway, run `gcloud api-gateway gateways create {gateway_id}` with the same flags instead of `gateways update`. `api-configs create` creates the API if it does not exist.
   - If an operation requires an API key, enable the managed service of the API. Get its name with `gcloud api-gateway apis describe {api_id} --project={project_id} --format="value(managedService)"`, and then run `gcloud services enable {managed_service} --project={project_id}`. Also enable it in each project that creates API keys for the API.
   - Use a new config ID for each change, because you cannot change the spec of an existing API config.
   - Run one `api-configs create` at a time for each API, and wait for it to finish. A large API config can take up to ten minutes to create.
   - If `api-configs create` fails, find the error text in [API Config Errors](references/api-config-errors.md), fix the spec, and go back to step 3.
   - Keep the previous API config until the new one serves traffic. To roll back, run `gateways update` with the previous config ID.
6. **Verify the gateway:**
   - Run `gcloud api-gateway gateways describe {gateway_id} --location={region} --project={project_id} --format="value(state,defaultHostname)"`, and wait until the state is `ACTIVE`.
   - Send a request to each changed path at `https://{default_hostname}{base_path}{path}`, with the credential that the operation requires. Check that the backend receives the path and parameters that you expect.
   - An HTML `404 Page not found` means that the gateway is not ready. Check that the last create or update finished, and retry before you change the config. During a gateway update, some requests can still reach the previous API config. A JSON 404 (`The current request is not defined by this API.`) means that the active API config does not define the path.

## Pre-Deployment Checklist

- [ ] `openapi` is `3.0.x` or `3.1.x`, and the spec has no OpenAPI 2.0 extension, such as `x-google-management`, `x-google-endpoints`, `x-google-api-name`, `x-google-allow`, or `x-google-issuer` on a security scheme.
- [ ] `x-google-api-management.backends` defines every backend, every `x-google-backend` is a string that names one, and no path item sets `x-google-backend`.
- [ ] Every backend sets `pathTranslation`.
- [ ] Every operation has a unique `operationId` and a `responses` object, and each path variable has a parameter with `in: path` and `required: true`.
- [ ] Every `x-google-quota` is on an operation that requires an API key, and every metric name matches the current API config.
- [ ] At most one `servers` entry has `x-google-endpoint`, and its URL has no custom port.
- [ ] `python3 scripts/validate_apigw_openapi.py --spec={spec_file}` returns `"status": "PASS"` (exit code `0`).

## Resource Cleanup

To avoid ongoing charges when you tear down a test environment, request human approval, and delete the resources in dependency order:

```bash
gcloud api-gateway gateways delete {gateway_id} --location={region} --project={project_id}
gcloud api-gateway api-configs delete {config_id} --api={api_id} --project={project_id}
gcloud api-gateway apis delete {api_id} --project={project_id}
```
