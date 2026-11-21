---
name: api-gateway-backend-security-and-rate-limiting
metadata:
  version: "1.0.1"
  category: Security
description: >-
  Secures and rate limits backend services behind Google Cloud API Gateway
  across OpenAPI 2.0 and OpenAPI 3.0.x API configurations, including MCP-enabled
  gateways. Use when configuring API key or JWT authentication, locking down
  Cloud Run or Cloud Run functions backends with a gateway service account,
  reading authenticated claims from X-Apigateway-Api-Userinfo, setting per-project
  request quotas, or diagnosing HTTP 429 and HTTP 500 Service Control Quota
  errors. Do not use for Apigee, GKE Gateway API, Cloud Load Balancing custom
  domain setup, or LLM model routing.
---

# API Gateway Backend Security and Rate Limiting

This skill configures client authentication, gateway-to-backend authentication, and per-project rate limits (quotas) for Google Cloud API Gateway across OpenAPI 2.0 (`swagger: "2.0"`) and OpenAPI 3.0.x (`openapi: 3.0.4`), including gateways with Model Context Protocol (MCP) enabled (Public Preview).

## Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read [Usage Attribution](references/attribution.md). For commands executed
directly in the terminal (never in generated scripts, Terraform, or user code),
prefix `gcloud` with
`CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:api-gateway-backend-security-and-rate-limiting)"`
and append `agent-skills/1.0 (skill:api-gateway-backend-security-and-rate-limiting)` to `User-Agent` headers.

## Prerequisites

1. **Install the Google Cloud CLI and Python 3.10+ YAML parser:**
   - Install or update the [Google Cloud SDK](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt).
   - Install `PyYAML` for the quota metric validation script:
     ```bash
     pip install "PyYAML>=6.0,<7.0"
     ```
2. **Authenticate your environment:**
   - Local CLI session: `gcloud auth login`
   - Application Default Credentials (SDKs): `gcloud auth application-default login`
   - Service account key file (if required by CI): set `GOOGLE_APPLICATION_CREDENTIALS={key_file_path}`
3. **Select or create a project, verify billing, and pick a supported gateway location:**
   - Select an existing project (`gcloud config set project {project_id}`) or create one (`gcloud projects create {project_id}` as an escape hatch).
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
   - For the gateway service account to invoke the backend: `roles/run.invoker` (Cloud Run or 2nd gen functions) or `roles/cloudfunctions.invoker` (1st gen functions)

## Decision Matrix: Client Authentication, Backend Security, and Quotas

Select the layer that matches the security requirement:

| Goal | Mechanism to Configure | Key Constraint | Detailed Reference |
| --- | --- | --- | --- |
| Identify the calling consumer project for quotas and billing | API key (`x-api-key` header convention; `key` query parameter escape hatch) | NEVER rely on an API key alone to authenticate end-user identity. **Rationale:** API keys identify a Google Cloud project rather than a user, and clients can extract them. | [Client Authentication](references/client-authentication.md) |
| Authenticate end users or calling services | JWT (`oauth2` scheme with `x-google-issuer` / `x-google-jwks_uri` in OAS 2.0, or `x-google-auth` in OAS 3.x) | Operation-level `security` overrides root `security`. Include `api_key: []` and the JWT scheme in the same security requirement object when an endpoint needs both user identity and quotas. | [Client Authentication](references/client-authentication.md) |
| Block direct calls to the backend service | Dedicated gateway service account (`--backend-auth-service-account`) + `roles/run.invoker` + backend `--no-allow-unauthenticated` | Roll out the gateway config with `--backend-auth-service-account` BEFORE setting `--no-allow-unauthenticated` on a live backend to avoid `403` downtime. | [Backend Security](references/backend-security.md) |
| Rate limit requests per consumer project (`1/min/{project}`) | `x-google-management` (OAS 2.0) or `x-google-api-management` (OAS 3.x) + `x-google-quota` | NEVER rename or remove a quota metric when creating a new API config while any gateway of the API runs an older config referencing that metric. **Rationale:** Creating the config immediately overwrites API-wide quotas and causes `HTTP 500 Failed to call Service Control Quota` on older gateways. | [Quotas and Rate Limiting](references/quotas-and-rate-limiting.md) |
| Secure MCP `tools/list` and `tools/call` on `/mcp` (Public Preview) | `x-google-api-management.mcp.tools-list.security` (exactly one JWT or API key scheme) + operation `security` and `x-google-mcp-tool: false` | `x-google-mcp-tool: false` hides an operation from MCP only; the underlying REST route remains live unless secured or removed. | [MCP Traffic Security](references/mcp-traffic-security.md) |

## Execution Workflow and Validation Loop

Follow this zero-downtime sequence when authoring or updating an API Gateway security or quota configuration:

1. **Create the gateway service account and grant backend invoker permissions:**
   - Follow Steps 1–3 of [Backend Security](references/backend-security.md) to create `{gateway_sa_name}` and request human approval before granting `roles/run.invoker` on `{backend_service}`.
   - Update backend handler code to decode verified user claims from `X-Apigateway-Api-Userinfo` (`base64url`-encoded JSON) instead of `Authorization`.
2. **Author the OpenAPI authentication and quota definitions:**
   - Use the OpenAPI 2.0 or OpenAPI 3.0.x templates and provider tables in [Client Authentication](references/client-authentication.md) and [Quotas and Rate Limiting](references/quotas-and-rate-limiting.md).
   - If the specification enables MCP (`x-google-api-management.mcp`), configure exactly one JWT or API key scheme on `tools-list` (also list a JWT scheme in the root `security` list), and review operation opt-outs using [MCP Traffic Security](references/mcp-traffic-security.md).
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
   - Follow Steps 4–5 of [Backend Security](references/backend-security.md) to run `gcloud api-gateway api-configs create` and `gcloud api-gateway gateways update` (request human approval before updating a production gateway), enable the API's `managedService` in consumer projects ([Client Authentication](references/client-authentication.md)), and then restrict `{backend_service}` with `--no-allow-unauthenticated`.
   - Verify that direct calls to the backend `*.run.app` URL return `403`, unauthenticated calls to the gateway `defaultHostname` return `401`, and authenticated calls return `200`.

## Pre-Deployment Checklist

- [ ] Dedicated `{gateway_sa_name}` is granted `roles/run.invoker` (or `roles/cloudfunctions.invoker`), and `--no-allow-unauthenticated` is applied after the gateway config is active.
- [ ] Backend code decodes `X-Apigateway-Api-Userinfo` for user claims.
- [ ] Security enforcement does not depend solely on a load balancer or Google Cloud Armor in front of the gateway, because the gateway's `defaultHostname` (`*.gateway.dev`) cannot be disabled.
- [ ] Every quota-enforced operation requires an API key (`api_key: []`), and the API's `managedService` is enabled and allowed on the API key in each consumer project.
- [ ] `python3 scripts/check_quota_metrics.py` returns `status: "PASS"` (exit code `0`) against active gateway configs or all baseline specs before `api-configs create`.
- [ ] If MCP is enabled, `x-google-api-management.mcp.tools-list.security` names exactly one JWT or API key scheme (a JWT scheme is also in the root `security` list), and administrative endpoints are secured on REST in addition to `x-google-mcp-tool: false`.

## Resource Cleanup

To avoid ongoing charges when tearing down a test or staging environment, request human approval and delete the gateway, all API configs, the API, and the service account in dependency order:

```bash
gcloud api-gateway gateways delete {gateway_id} --location={region} --project={project_id}
gcloud api-gateway api-configs delete {config_id} --api={api_id} --project={project_id}
gcloud api-gateway apis delete {api_id} --project={project_id}
gcloud iam service-accounts delete {gateway_sa_name}@{project_id}.iam.gserviceaccount.com --project={project_id}
```
