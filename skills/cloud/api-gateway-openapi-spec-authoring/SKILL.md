---
name: api-gateway-openapi-spec-authoring
metadata:
  version: "1.1.0"
  category: ApplicationDevelopment
description: >-
  Writes, migrates, and fixes OpenAPI specs for Google Cloud API Gateway. Use
  when converting an OpenAPI 2.0 (Swagger) spec to OpenAPI 3.x, writing a new
  OpenAPI 3.x spec, or fixing a failed "gcloud api-gateway api-configs create",
  such as "extension is only supported in OpenAPI 2.x". Also use when quotas
  set with x-google-quota are never enforced, or when a backend receives path
  parameters as query parameters. Don't use for adding or debugging MCP tools
  (use api-gateway-mcp-server), adding or changing API key, JWT, or quota
  settings in a working spec, or backend lockdown (use
  api-gateway-backend-security-and-rate-limiting), failing requests or service
  account and concurrency errors (use api-gateway-troubleshooting), Cloud
  Endpoints, Apigee, or GKE Gateway API.
---

<!-- disableFinding(LINE_OVER_80) -->

# API Gateway OpenAPI Spec Authoring

API Gateway accepts API configs in OpenAPI 2.0, 3.0.x, and 3.1.x. The Google extensions in OpenAPI 3.x have a different structure from the OpenAPI 2.0 extensions:

- A required root `x-google-api-management` block names the backends.
- `x-google-backend` is a string that references one of these backends.
- The JWT settings move into `x-google-auth`. The metrics and quotas move into `x-google-api-management`.

Use this skill to migrate an OpenAPI 2.0 spec, write a new OpenAPI 3.x spec, or fix an API config that fails to create.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Prerequisites

1. **Install the tools:**
   - If the Google Cloud CLI is not installed, give the user the [install guide](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt). Do not install it yourself. Until it is installed, give the user the commands to run, and continue from the output that they paste. If the CLI is old, ask the user before you run `gcloud components update`. **Rationale:** an old CLI can fail when it uploads an OpenAPI 3.x API config.
   - Install Python 3.10 or later and PyYAML for the validator script. A JSON spec does not need PyYAML. Ask the user before you install it.
     ```bash
     pip install "PyYAML>=6.0,<7.0"
     ```
2. **Authenticate, and select the project, billing, and location:**
   - Run `gcloud auth login`.
   - Ask the user which project to use, and use that ID as `{project_id}`. If no project exists, create one with `gcloud projects create {project_id}`. Pass `--project={project_id}` on every `gcloud` command. Do not change the default project of the user with `gcloud config set project`.
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
| Authenticate callers | JWT: `type: oauth2` scheme with `x-google-auth` (`issuer`, `jwksUri`, `audiences`). API key: `type: apiKey` scheme with `x-api-key` in a header, or `key` or `api_key` in the query. | API Gateway does not check OAuth scopes. In a `security` list, put an API key in every alternative (OR) or in none. NEVER put two JWT schemes in one requirement object (AND). **Rationale:** API Gateway rejects these combinations. If the user asks for one of them, such as a JWT or an API key as alternatives, do not write it in the spec. Explain the rule, and write a supported option, such as an API key in every alternative or a separate path for each kind of caller. For API key, JWT provider, or backend lockdown setup beyond the spec, use the `api-gateway-backend-security-and-rate-limiting` skill. If it is not installed, use this row. | [Extensions and Limits](references/openapi-3-extensions-and-limits.md#security) |
| Add quotas | `x-google-api-management.metrics` and `quota.limits` + `x-google-quota: {metric_name: cost}` on each operation | NEVER rely on `x-google-quota` at the root or path level. **Rationale:** API Gateway ignores it there without an error, in OpenAPI 3.x and in OpenAPI 2.0. Require an API key on each operation that has a quota, and keep each metric name the same in every API config. For quota setup beyond the spec, use the `api-gateway-backend-security-and-rate-limiting` skill. If it is not installed, use this row. | [Extensions and Limits](references/openapi-3-extensions-and-limits.md#quotas) |
| Set the base path and CORS | One `servers` entry with `x-google-endpoint`, such as `url: /v1` | API Gateway ignores `servers` entries without `x-google-endpoint`. `allowCors: true` only passes CORS requests to the backend. **Rationale:** the gateway does not add CORS headers, so the backend must answer them. | [Extensions and Limits](references/openapi-3-extensions-and-limits.md#servers-base-path-and-cors) |
| Fix a failed `api-configs create` | Match the error text to the error table, and fix the spec. | Fix the spec before you retry, unless the error is about IAM or another `api-configs create` that runs. **Rationale:** API Gateway returns the same error for the same spec. For a service account, IAM, or concurrency error, use the `api-gateway-troubleshooting` skill. If it is not installed, read the [troubleshoot page](https://docs.cloud.google.com/api-gateway/docs/troubleshoot.md.txt), but do not grant the Editor role. | [API Config Errors](references/api-config-errors.md) |
| Expose operations as MCP tools, or fix `/mcp` errors | The `api-gateway-mcp-server` skill | MCP adds rules for tool names, descriptions, and `tools/list` security. If that skill is not installed, use this skill for the OpenAPI 3.x spec, and follow the [Configure MCP](https://docs.cloud.google.com/api-gateway/docs/mcp-configure.md.txt) guide for the MCP extensions. | - |

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
2. **Write or fix the spec:**
   - If the user only wants to fix a failed OpenAPI 2.0 spec and does not want to migrate it, keep it in OpenAPI 2.0, and fix it with the error table. The validator in step 3 checks only OpenAPI 3.x specs, so skip it for that spec.
   - For an OpenAPI 2.0 spec that you migrate, follow [OpenAPI 2.0 to 3.x Migration](references/openapi-2-to-3-migration.md), and compare your result with its complete converted example.
   - For a new spec, start from the template in [Extensions and Limits](references/openapi-3-extensions-and-limits.md#new-spec-template).
   - Set `openapi` to a 3.0.x or 3.1.x version. The examples use `3.0.4`. In OpenAPI 3.1, give each schema one `type`. **Rationale:** API Gateway rejects a type list such as `type: ["string", "null"]`.
   - Give every operation a unique `operationId` and a `responses` object, use only local `$ref` values, and do not use a YAML alias to a mapping or a sequence. **Rationale:** API Gateway rejects an operation without `operationId` or `responses`, two `operationId` values that give the same method name, such as `getItem` and `get-Item`, a `$ref` to a URL or to a file that the API config does not include, and such an alias. In OpenAPI 2.0, API Gateway rejects a file `$ref` also when the API config includes the file.
   - If the API uses MCP, use the `api-gateway-mcp-server` skill for the MCP extensions. Keep all MCP operations in one document. The MCP endpoint `/mcp` stays at the host root, and the `servers` base path does not change it.
3. **Run the deterministic validation loop on every OpenAPI 3.x spec that you write or change, before you answer or create the API config:**
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
   - Before `api-configs create`, if the spec has quota metrics, load the `api-gateway-backend-security-and-rate-limiting` skill, and run its `scripts/check_quota_metrics.py`. It compares the metrics of the new spec with the API configs that gateways serve. If that skill is not installed, keep every metric and its quota limit that a running API config uses.
   - For a new gateway, run `gcloud api-gateway gateways create {gateway_id}` with the same flags instead of `gateways update`. `api-configs create` creates the API if it does not exist.
   - If an operation requires an API key, enable the managed service of the API. Get its name with `gcloud api-gateway apis describe {api_id} --project={project_id} --format="value(managedService)"`, and then run `gcloud services enable {managed_service} --project={project_id}`. Also enable it in each project that creates API keys for the API.
   - Use a new config ID for each change, because you cannot change the spec of an existing API config.
   - Run one `api-configs create` at a time for each API, and wait for it to finish. A large API config can take up to ten minutes to create.
   - If `api-configs create` fails, find the error text in [API Config Errors](references/api-config-errors.md), fix the spec, and go back to step 3. For an OpenAPI 2.0 spec that you keep in 2.0, skip step 3 and create the API config again. For a service account, IAM, or concurrency error, use the `api-gateway-troubleshooting` skill. If it is not installed, read the [troubleshoot page](https://docs.cloud.google.com/api-gateway/docs/troubleshoot.md.txt), but do not grant the Editor role.
   - Keep the previous API config until the new one serves traffic. To roll back, run `gateways update` with the previous config ID.
6. **Verify the gateway:**
   - Run `gcloud api-gateway gateways describe {gateway_id} --location={region} --project={project_id} --format="value(state,defaultHostname)"`, and wait until the state is `ACTIVE`.
   - Send a request to each changed path at `https://{default_hostname}{base_path}{path}`, with the credential that the operation requires. Check that the backend receives the path and parameters that you expect.
   - An HTML `404 Page not found` means that the gateway is not ready. Check that the last create or update finished, and retry before you change the config. During a gateway update, some requests can still reach the previous API config. A JSON 404 (`The current request is not defined by this API.`) means that the active API config does not define the path.
   - For a 401, 403, 429, or 5xx response, or a timeout, after the deploy, use the `api-gateway-troubleshooting` skill. If it is not installed, read the [troubleshoot page](https://docs.cloud.google.com/api-gateway/docs/troubleshoot.md.txt). Do not grant the Editor role, and do not make the backend public, even if the page suggests it.

## Pre-Deployment Checklist

The items below apply to an OpenAPI 3.x spec. For an OpenAPI 2.0 spec that the user keeps in 2.0, check each changed setting against [API Config Errors](references/api-config-errors.md) instead.

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

## Related skills

| Need | Skill |
| :--- | :--- |
| Expose operations as MCP tools, or fix `/mcp` errors | `api-gateway-mcp-server` |
| Set up API keys, JWT providers, backend lockdown, or quota limits, and check quota metrics before `api-configs create` | `api-gateway-backend-security-and-rate-limiting` |
| Find why requests fail after the deploy, or fix a service account, IAM, or concurrency error from `api-configs create` | `api-gateway-troubleshooting` |

If an API Gateway skill in this table is not installed, give the user this command to install the four API Gateway skills. Until it is installed, use the fallback in this skill.

```bash
npx skills add google/skills --skill api-gateway-mcp-server --skill api-gateway-backend-security-and-rate-limiting --skill api-gateway-openapi-spec-authoring --skill api-gateway-troubleshooting
```
