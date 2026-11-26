---
name: api-gateway-backend-security-and-rate-limiting
metadata:
  version: "1.1.0"
  category: Security
description: >-
  Secures and rate limits backend services behind Google Cloud API Gateway
  across OpenAPI 2.0 and OpenAPI 3.x API configurations, including MCP-enabled
  gateways. Use when configuring API key or JWT authentication, locking down
  Cloud Run or Cloud Run functions backends with a gateway service account,
  reading authenticated claims from X-Apigateway-Api-Userinfo, setting
  per-project request quotas, or changing quota metrics without the HTTP 500
  "Failed to call Service Control Quota" error on older gateways. Do not use for
  finding the cause of failing requests from gateway logs, such as an
  unexplained HTTP 429 or 5xx (use api-gateway-troubleshooting), writing or
  migrating a whole spec (use api-gateway-openapi-spec-authoring), MCP tool
  setup (use api-gateway-mcp-server), Apigee, GKE Gateway API, Cloud Load
  Balancing custom domain setup, or LLM model routing.
---

<!-- disableFinding(LINE_OVER_80) -->

# API Gateway Backend Security and Rate Limiting

This skill configures client authentication, gateway-to-backend authentication, and per-project rate limits (quotas) for Google Cloud API Gateway across OpenAPI 2.0 (`swagger: "2.0"`) and OpenAPI 3.x (3.0.x and 3.1.x, such as `openapi: 3.0.4`), including gateways with Model Context Protocol (MCP) enabled (Public Preview).

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Prerequisites

1. **Install the Google Cloud CLI and Python 3.10+ YAML parser:**
   - If `gcloud` is not installed, give the user the [Google Cloud CLI install guide](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt). Do not install it yourself. Until it is installed, give the user the commands to run, and continue from the output that they paste.
   - If the gcloud CLI is old, ask the user before you run `gcloud components update`. An old gcloud CLI can fail when it uploads an OpenAPI 3.x spec.
   - Install `PyYAML` for the quota metric validation script. Ask the user before you install it:
     ```bash
     pip install "PyYAML>=6.0,<7.0"
     ```
2. **Authenticate your environment:**
   - Local CLI session: `gcloud auth login`
   - Application Default Credentials (SDKs): `gcloud auth application-default login`
   - Service account key file (if required by CI): set `GOOGLE_APPLICATION_CREDENTIALS={key_file_path}`
3. **Select or create a project, verify billing, and pick a supported gateway location:**
   - Ask the user which project to use, and use that ID as `{project_id}`. Pass `--project={project_id}` on every command. Do not run `gcloud config set project`, because it changes the default project for all other work of the user. If no project exists, create one with `gcloud projects create {project_id}` as an escape hatch.
   - Verify that an active billing account is linked to `{project_id}` (required even when staying within the [API Gateway pricing free tier](https://cloud.google.com/api-gateway/pricing)).
   - Use `us-central1` as the default `--location` for API Gateway commands. For the other supported regions, see [API Gateway deployment model](https://docs.cloud.google.com/api-gateway/docs/deployment-model.md.txt).
4. **Enable required Google Cloud APIs:**
   ```bash
   gcloud services enable \
     apigateway.googleapis.com \
     servicemanagement.googleapis.com \
     servicecontrol.googleapis.com \
     iam.googleapis.com \
     apikeys.googleapis.com \
     --project={project_id}
   ```
   API Gateway does not need the Cloud Run API. If the backend runs on Cloud Run, that API is already enabled in the backend's project.
5. **Verify required IAM roles:**
   - To manage API Gateway resources and enable services: `roles/apigateway.admin` and `roles/serviceusage.serviceUsageAdmin`
   - To create the gateway service account and attach it to an API config: `roles/iam.serviceAccountAdmin` and `roles/iam.serviceAccountUser`
   - To manage API keys in consumer projects: `roles/serviceusage.apiKeysAdmin`
   - To change the IAM policy of the Cloud Run backend (grant the invoker role, remove `allUsers`, and turn on the invoker IAM check): `roles/run.admin`, or another role with `run.services.get`, `run.services.getIamPolicy`, `run.services.setIamPolicy`, and `run.services.update`. For a 1st gen function backend: `roles/cloudfunctions.admin`
   - For the gateway service account to invoke the backend: `roles/run.invoker` (Cloud Run or 2nd gen functions) or `roles/cloudfunctions.invoker` (1st gen functions)

## Decision Matrix: Client Authentication, Backend Security, and Quotas

Select the layer that matches the security requirement:

| Goal | Mechanism to Configure | Key Constraint | Detailed Reference |
| --- | --- | --- | --- |
| Identify the calling consumer project for quotas and billing | API key in the `x-api-key` header (use the `key` or `api_key` query parameter only as an escape hatch) | NEVER rely on an API key alone to authenticate end-user identity. **Rationale:** API keys identify a Google Cloud project rather than a user, and clients can extract them. API Gateway ignores an API key scheme with any other name or location, with no error, and the operation then accepts calls with no key. | [Client Authentication](references/client-authentication.md) |
| Authenticate end users or calling services | JWT (`oauth2` scheme with `x-google-issuer` / `x-google-jwks_uri` in OAS 2.0, or `x-google-auth` in OAS 3.x) | Operation-level `security` overrides root `security`. Include `api_key: []` and the JWT scheme in the same security requirement object when an endpoint needs both user identity and quotas. | [Client Authentication](references/client-authentication.md) |
| Block direct calls to the backend service | Dedicated gateway service account (`--backend-auth-service-account`) + `roles/run.invoker` + remove public invoker bindings from the backend and turn on its invoker IAM check | Every gateway of the API MUST serve a config with `--backend-auth-service-account` BEFORE you remove `allUsers` from a live backend. Otherwise those gateways get `403` errors. | [Backend Security](references/backend-security.md) |
| Rate limit requests per consumer project (`1/min/{project}`) | `x-google-management` (OAS 2.0) or `x-google-api-management` (OAS 3.x) + `x-google-quota` | Require the API key in every security alternative of a quota operation. NEVER rename or remove a quota metric when creating a new API config while any gateway of the API runs an older config referencing that metric. **Rationale:** Creating the config immediately overwrites API-wide quotas and causes `HTTP 500 Failed to call Service Control Quota` on older gateways. | [Quotas and Rate Limiting](references/quotas-and-rate-limiting.md) |
| Secure MCP `tools/list` and `tools/call` on `/mcp` (Public Preview) | `x-google-api-management.mcp.tools-list.security` (exactly one JWT or API key scheme) + operation `security` and `x-google-mcp-tool: false` | `x-google-mcp-tool: false` hides an operation from MCP only; the underlying REST route remains live unless secured or removed. An empty `tools-list.security` map leaves `tools/list` open. | [MCP Traffic Security](references/mcp-traffic-security.md) |

## Execution Workflow and Validation Loop

Follow this zero-downtime sequence when authoring or updating an API Gateway security or quota configuration:

1. **Create the gateway service account and grant backend invoker permissions:**
   - Follow Steps 1–3 of [Backend Security](references/backend-security.md) to create `{gateway_sa_name}` and request human approval before granting `roles/run.invoker` on `{backend_service}`.
   - If operations authenticate a JWT, update backend handler code to decode verified user claims from `X-Apigateway-Api-Userinfo` (`base64url`-encoded JSON) instead of `Authorization`. API Gateway sends this header only for operations with JWT auth.
2. **Author the OpenAPI authentication and quota definitions:**
   - To write a whole spec, or to migrate a spec from OpenAPI 2.0 to 3.x, use the `api-gateway-openapi-spec-authoring` skill. If it is not installed, continue with this skill.
   - Use the OpenAPI 2.0 or OpenAPI 3.x templates and provider tables in [Client Authentication](references/client-authentication.md) and [Quotas and Rate Limiting](references/quotas-and-rate-limiting.md).
   - If the specification enables MCP (`x-google-api-management.mcp`), configure exactly one JWT or API key scheme on `tools-list` (also list a JWT scheme in the root `security` list), and review operation opt-outs using [MCP Traffic Security](references/mcp-traffic-security.md). To set up or name MCP tools, use the `api-gateway-mcp-server` skill. If it is not installed, see [Configure Model Context Protocol](https://docs.cloud.google.com/api-gateway/docs/mcp-configure.md.txt).
3. **Run the quota metric validation loop BEFORE running `api-configs create`:**
   - If neither the active specs nor `{candidate_openapi_spec}` define quota metrics (`x-google-management.metrics` or `x-google-api-management.metrics`), skip this step.
   - Request human approval before creating an API config that defines or modifies quotas, because `api-configs create` immediately replaces quota definitions across all gateways of the API.
   - By default, run `scripts/check_quota_metrics.py` against all active gateways deployed for `{api_id}` in `{project_id}`:
     ```bash
     python3 scripts/check_quota_metrics.py \
       --spec={candidate_openapi_spec} \
       --project={project_id} \
       --api={api_id}
     ```
   - Escape hatch for offline environments without `gcloud` access (pass `--baseline-spec` for every config currently served by a gateway of the API):
     ```bash
     python3 scripts/check_quota_metrics.py \
       --spec={candidate_openapi_spec} \
       --baseline-spec={previous_openapi_spec} \
       --dry-run
     ```
   - If `scripts/check_quota_metrics.py` exits with code `1` (`status: "FAIL"`), add the missing metrics and limits back to `{candidate_openapi_spec}`, move each `x-google-quota` listed in `ignored_quota_extensions` into the operations it applies to, and re-run the script until it exits with code `0` (`status: "PASS"`). If the user wants to remove a limit on purpose, confirm the removal with the user, because it removes that limit from every gateway of the API. If `skipped_configs` is not empty, tell the user that the script did not inspect those API configs (for example, gRPC configs), and check their quota metrics and limits manually. If it exits with code `2`, fix the problem printed to stderr: the CLI arguments, `gcloud` authentication, or an API config that the script cannot inspect.
4. **Create the API config, update the gateway, enable the managed service, and lock down the backend:**
   - Follow Steps 4–5 of [Backend Security](references/backend-security.md) to run `gcloud api-gateway api-configs create` and `gcloud api-gateway gateways update` (request human approval before updating a production gateway), enable the API's `managedService` in consumer projects ([Client Authentication](references/client-authentication.md)), and then lock down `{backend_service}` (remove public invoker bindings and turn on the invoker IAM check).
   - If `api-configs create` fails with an OpenAPI error, use the `api-gateway-openapi-spec-authoring` skill. If it fails with another error, such as an IAM or service account error, use the `api-gateway-troubleshooting` skill. If the skill is not installed, read the error text, and compare the spec with the templates in the references or the IAM roles in Prerequisites.
   - Verify that direct calls to the backend URL (`*.run.app`, or `*.cloudfunctions.net` for a 1st gen function) return `403`, unauthenticated calls to the gateway `defaultHostname` return `401`, and authenticated calls return `200`.
   - If you get another result, use the `api-gateway-troubleshooting` skill. If it is not installed, check which API config each gateway serves, and check the `roles/run.invoker` (or `roles/cloudfunctions.invoker`) binding of `{gateway_sa_name}` on `{backend_service}`.

## Pre-Deployment Checklist

- [ ] Dedicated `{gateway_sa_name}` is granted `roles/run.invoker` (or `roles/cloudfunctions.invoker`). Only after every gateway of the API serves a config with `--backend-auth-service-account`, public invoker bindings (`allUsers`, `allAuthenticatedUsers`) are removed and the invoker IAM check is on.
- [ ] If operations authenticate a JWT, backend code decodes `X-Apigateway-Api-Userinfo` for user claims.
- [ ] Security enforcement does not depend solely on a load balancer or Google Cloud Armor in front of the gateway, because the gateway's `defaultHostname` (`*.gateway.dev`) cannot be disabled.
- [ ] Every quota-enforced operation requires an API key (`api_key: []`) in every security alternative, and the API's `managedService` is enabled and allowed on the API key in each consumer project.
- [ ] `python3 scripts/check_quota_metrics.py` returns `status: "PASS"` (exit code `0`) against active gateway configs or all baseline specs before `api-configs create`.
- [ ] If MCP is enabled, `x-google-api-management.mcp.tools-list.security` names exactly one JWT or API key scheme (a JWT scheme is also in the root `security` list), and administrative endpoints are secured on REST in addition to `x-google-mcp-tool: false`.

## Resource Cleanup

To avoid ongoing charges when tearing down a test or staging environment, request human approval and delete the gateway, all API configs, and the API in dependency order:

```bash
gcloud api-gateway gateways delete {gateway_id} --location={region} --project={project_id}
gcloud api-gateway api-configs delete {config_id} --api={api_id} --project={project_id}
gcloud api-gateway apis delete {api_id} --project={project_id}
```

Delete the service account only if no other API config or gateway uses it. List the service account of every remaining API config in the project, and ask the user if other workloads use the account:

```bash
gcloud api-gateway api-configs list --project={project_id} --format="value(name,gatewayServiceAccount)"
```

If no remaining API config uses the account and the user confirms that no other workload uses it, delete it:

```bash
gcloud iam service-accounts delete {gateway_sa_name}@{project_id}.iam.gserviceaccount.com --project={project_id}
```

## Related skills

| Need | Skill |
| :--- | :--- |
| Write or migrate an OpenAPI spec, or fix an OpenAPI error from `api-configs create` | `api-gateway-openapi-spec-authoring` |
| Expose operations as MCP tools, or fix `/mcp` errors | `api-gateway-mcp-server` |
| Find why requests fail, including HTTP 401, 403, 429, and quota HTTP 500 errors | `api-gateway-troubleshooting` |
| Deploy or change the Cloud Run backend | `cloud-run-basics` |
| Put a load balancer, Cloud Armor, or a custom domain in front of the gateway | `google-cloud-global-frontend-configuration` |

If an API Gateway skill in this table is not installed, give the user this command to install the four API Gateway skills. Until it is installed, use the fallback in this skill.

```bash
npx skills add google/skills --skill api-gateway-mcp-server --skill api-gateway-backend-security-and-rate-limiting --skill api-gateway-openapi-spec-authoring --skill api-gateway-troubleshooting
```

For another skill in this table, give the user the same command with `--skill {skill_name}`.
