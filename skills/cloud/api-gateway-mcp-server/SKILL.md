---
name: api-gateway-mcp-server
metadata:
  version: "1.0.1"
  category: AiAndMachineLearning
description: >-
  Configures Google Cloud API Gateway to act as a remote Model Context Protocol
  (MCP) server (Public Preview) that exposes REST APIs as agent tools over
  HTTP (POST /mcp). Use when migrating OpenAPI 2.0 specs
  to OpenAPI 3.x for MCP, annotating specs with x-google-api-management.mcp
  and x-google-mcp-tool, securing tools/list with JWTs or API keys,
  connecting Google ADK (McpToolset) or Apigee API hub and Agent Registry, or
  troubleshooting MCP JSON-RPC errors (-32601, -32602, -32000). Do not use for
  Apigee X proxy bundles, outbound LLM model routing, or GKE Gateway API.
---

# API Gateway Remote MCP Server (Public Preview)

This skill converts new or existing REST APIs on Google Cloud API Gateway into remote Model Context Protocol (MCP) servers (`POST https://{default_hostname}/mcp`, **Public Preview**). By annotating an OpenAPI 3.x (3.0.x or 3.1.x) specification with `x-google-api-management.mcp` and `x-google-mcp-tool`, API Gateway translates MCP JSON-RPC 2.0 requests (`initialize`, `notifications/initialized`, `tools/list`, `tools/call`) into standard HTTP REST requests to your backend while enforcing existing authentication and quota policies.

## Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read [Usage Attribution](references/attribution.md). For commands executed
directly in the terminal (never in generated scripts, Terraform, or user code),
prefix `gcloud` with
`CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:api-gateway-mcp-server)"`
and append `agent-skills/1.0 (skill:api-gateway-mcp-server)` to `User-Agent` headers.

## Prerequisites

1. **Install the Google Cloud CLI and the validator dependency:**
   - Install the [Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt). Then update it to the latest version with `gcloud components update`. An old CLI can fail when it uploads an OpenAPI 3.x API config.
   - Install Python 3.10 or later and `PyYAML` for the local OpenAPI MCP validator script:
     ```bash
     pip install "PyYAML>=6.0,<7.0"
     ```
2. **Authenticate your environment:**
   - Local CLI session: `gcloud auth login`
   - Application Default Credentials (SDKs / ADK): `gcloud auth application-default login`
3. **Select or create a project, confirm billing, and pick a supported gateway location:**
   - Select an existing project (`gcloud config set project {project_id}`) or create one (`gcloud projects create {project_id}`).
   - Confirm that an active billing account is linked to `{project_id}`. API Gateway has a free monthly allowance of API calls for each billing account, but you still need an active billing account to deploy. Calls above the allowance and network data transfer out are charged. For current prices, see [API Gateway pricing](https://cloud.google.com/api-gateway/pricing).
   - Use `us-central1` as the default `--location` for gateway commands. For the other supported regions, see [API Gateway deployment model](https://docs.cloud.google.com/api-gateway/docs/deployment-model.md.txt).
4. **Enable the required Google Cloud APIs:**
   ```bash
   gcloud services enable \
     apigateway.googleapis.com \
     servicemanagement.googleapis.com \
     servicecontrol.googleapis.com \
     --project={project_id}
   ```
   For API hub discovery (optional), enable the API hub API in the API hub host project: `gcloud services enable apihub.googleapis.com --project={hub_project_id}`. To query Agent Registry (optional), also run `gcloud services enable agentregistry.googleapis.com --project={project_id}`.
5. **Verify the IAM roles (use the most restrictive role for each step):**
   - To create and update the API, API configs, and gateways: API Gateway Admin (`roles/apigateway.admin`) on `{project_id}`. To run the `gcloud services enable` commands: Service Usage Admin (`roles/serviceusage.serviceUsageAdmin`) on that project.
   - To reference the gateway service account in an API config: Service Account User (`roles/iam.serviceAccountUser`) on `{gateway_sa_name}@{project_id}.iam.gserviceaccount.com`.
   - For a Cloud Run backend: grant the gateway service account the Cloud Run Invoker role (`roles/run.invoker`) on the service.
   - To mint test ID tokens as a caller service account: Service Account Token Creator (`roles/iam.serviceAccountTokenCreator`) on `{caller_sa_email}`.
   - Reference: [Configure the development environment](https://docs.cloud.google.com/api-gateway/docs/configure-dev-env.md.txt).

## Decision Matrix: MCP Server Configuration and Client Integration

| Task | Required Mechanism | Critical Guardrail | Detailed Reference |
| --- | --- | --- | --- |
| Migrate OpenAPI 2.0 (`swagger: "2.0"`) or author OpenAPI 3.x for MCP | Root `x-google-api-management.mcp` + named `backends` + operation-level `x-google-mcp-tool` | NEVER add MCP extensions to an OpenAPI 2.0 spec. **Rationale:** MCP is not supported for OpenAPI 2.0. Use OpenAPI 3.0.x or 3.1.x, and deploy the spec with `gcloud api-gateway api-configs create`. Keep all MCP operations in one OpenAPI document: if an API config has several documents, API Gateway serves the MCP tools of only one of them. | [OpenAPI 2.0 to 3.x Migration](references/openapi-v2-to-v3-mcp-migration.md) |
| Optimize tool names, descriptions, and schemas for LLM tool selection | `x-google-mcp-tool` (`name`, `description`, `false`) + described `requestBody` properties | Every operation MUST have an `operationId`, with or without MCP. Every exposed tool MUST resolve to a unique name that matches `[A-Za-z0-9_.-]{1,128}` (`x-google-mcp-tool.name`, or else the `operationId`), a non-empty description, and a non-empty response body (`HTTP 204` is unsupported). Only `GET`, `POST`, `PUT`, `PATCH`, and `DELETE` operations can be tools, and a gateway serves at most 1,000 tools. API Gateway rejects complex nested schemas when you create the API config, but a simple nested object body works. In OpenAPI 3.1, give each schema one `type`, because API Gateway also rejects a type list such as `type: ["string", "null"]`. Describe each property, and check each tool's `inputSchema` in `tools/list` after you deploy. | [OpenAPI Agent Tool Optimizer](references/openapi-agent-tool-optimizer.md) |
| Secure `tools/list` and hide internal/admin routes | `x-google-api-management.mcp.tools-list.security` (exactly one JWT or API key scheme; a JWT scheme is also listed in root `security`) + `x-google-mcp-tool: false` | `tools/list` is unauthenticated by default. It accepts one JWT scheme, or one API key scheme sent in the `x-api-key` header. API Gateway rejects a config whose JWT `tools-list.security` scheme is missing from the root `security` list, and that root entry also requires the JWT on every REST operation without its own `security`. If the root list already has an API key scheme, add the JWT to the same requirement object (AND): API Gateway does not support alternative (OR) requirements with an API key. An `mcp` object (for `tools-list`) also enables MCP for every eligible operation, so opt out each operation that agents must not use. `x-google-mcp-tool: false` hides a route from MCP only; keep REST `security` on admin routes. | [OpenAPI 2.0 to 3.x Migration](references/openapi-v2-to-v3-mcp-migration.md) |
| Connect Google ADK (`McpToolset`) and discover in API hub / Agent Registry | `McpToolset` (`StreamableHTTPConnectionParams`) + API hub project attachment | No separate registration step is needed. After you attach the API Gateway project to API hub, the MCP server appears in API hub as `{your_api} (MCP)` and in Agent Registry automatically. | [ADK and API Hub Discovery](references/adk-and-api-hub-discovery.md) |
| Verify `/mcp` JSON-RPC lifecycle and troubleshoot `-32601` / `-32602` / `-32000` errors | `POST https://{default_hostname}/mcp` with `MCP-Protocol-Version: 2025-11-25` | Keep `/mcp` at the host root: a `servers` base path (such as `/v2`) applies to REST paths only, and `{basepath}/mcp` returns HTTP 404. Nest JSON request bodies under `params.arguments.body` (`{"body": {...}}`). NEVER combine `x-google-api-management.mcp` with `x-google-model-router` in one config. **Rationale:** API Gateway does not allow MCP and model routing in the same API config. | [MCP Verification and Troubleshooting](references/mcp-limitations-and-troubleshooting.md) |

## Execution Workflow and Validation Loop

1. **Upgrade and annotate the OpenAPI 3.x specification:**
   - The references in this skill contain the conversion rules: the [Swagger 2.0 Construct Conversion Map](references/openapi-v2-to-v3-mcp-migration.md#swagger-20-construct-conversion-map) covers each Swagger 2.0 construct, and the [Complete Converted Example](references/openapi-v2-to-v3-mcp-migration.md#complete-converted-example) shows a finished spec with a Google ID token scheme. Use them before you search other sources.
   - Follow [OpenAPI 2.0 to 3.x Migration](references/openapi-v2-to-v3-mcp-migration.md) and [OpenAPI Agent Tool Optimizer](references/openapi-agent-tool-optimizer.md) to set `openapi` to a 3.0.x or 3.1.x version (the examples use `3.0.4`), remove unsupported OpenAPI 2.0 fields (`x-google-allow`), define `x-google-api-management.backends` (with `jwtAudience` or `disableAuth`), configure `x-google-api-management.mcp.tools-list.security` with exactly one JWT or API key scheme (add a JWT scheme to the root `security` list too, in the same requirement object as any API key scheme), author `x-google-mcp-tool` descriptions stating *when and why* to invoke each tool, and opt out administrative routes (`x-google-mcp-tool: false`).
   - Before you deploy, give the user a short summary that states each of these points, and get approval:
     - MCP is not supported for OpenAPI 2.0, so you converted the spec to OpenAPI 3.x.
     - Which operations you exposed as tools, and which you opted out with `x-google-mcp-tool: false`. Opted-out operations stay on REST.
     - If `tools/list` uses a JWT scheme, the root `security` entry makes every REST operation without its own `security` require the JWT. The gateway rejects REST callers without it.
     - The MCP endpoint is `https://{default_hostname}/mcp`, at the host root even when the spec sets a `servers` base path.
     - The limits that apply: only `GET`, `POST`, `PUT`, `PATCH`, and `DELETE` operations can be tools, a gateway serves at most 1,000 tools, request parameters must be primitive types, API Gateway rejects complex nested schemas and OpenAPI 3.1 type lists (such as `type: ["string", "null"]`) when you create the API config, tools cannot return `HTTP 204`, and MCP is stateless with UTF-8 text responses only.
   - Give the same points when the user only asks for the converted spec or for advice, without a deploy.
   - Preserve exact quota metric names in `x-google-api-management.metrics` across API configs so existing gateways do not fail with HTTP 500 `Failed to call Service Control Quota`.
2. **Run the deterministic MCP OpenAPI validation loop before creating the API config:**
   - Execute `scripts/validate_mcp_openapi.py` on `{candidate_openapi_spec}`:
     ```bash
     python3 scripts/validate_mcp_openapi.py --spec={candidate_openapi_spec}
     ```
   - If `scripts/validate_mcp_openapi.py` exits with code `1` (`status: "FAIL"`), fix every reported error in `{candidate_openapi_spec}` (such as OpenAPI 2.0 syntax, `x-google-allow`, path-level `x-google-mcp-tool`, undefined backend names, an operation without an `operationId`, missing descriptions, invalid or duplicate tool names, a header parameter with the reserved `x-google-` prefix, a `tools-list.security` scheme that is neither an `oauth2` JWT nor an `apiKey` scheme, a JWT `tools-list.security` scheme missing from the root `security` list, alternative (OR) security requirements with an API key, or an `x-google-model-router` operation in an MCP spec) and re-run the script until it exits with code `0` (`status: "PASS"`). If it exits with code `2`, fix the file path or YAML syntax error printed to stderr.
   - Read every warning (such as an `HTTP 204` response, a request parameter that is not a primitive type, or operations that an `mcp` object exposes by default). Fix it, or tell the user why you keep it.
3. **Create the API (if new), create the API config, deploy the gateway, and enable the managed service (request human approval before updating a production gateway):**
   ```bash
   gcloud api-gateway apis create {api_id} --project={project_id}

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

   gcloud services enable $(gcloud api-gateway apis describe {api_id} --project={project_id} --format="value(managedService)") --project={project_id}
   ```
    *(For a brand-new gateway, run `gcloud api-gateway gateways create {gateway_id} ...` instead of `gateways update`).*
   - Run one `api-configs create` at a time per API. Wait for it to finish before you start the next one, because API Gateway creates only one config for an API at a time. A complex API config can take up to ten minutes to create.
   - If clients use API keys from other projects, enable the managed service in each of those projects too. API Gateway rejects an API key unless the API is enabled in the project that created the key.
4. **Verify the JSON-RPC 2.0 lifecycle and connect ADK / API hub:**
   - Send every probe to `https://{default_hostname}/mcp`, even when the spec sets a `servers` base path.
   - An HTML `404 Page not found` means that the gateway may not be deployed correctly. Check that the gateway state is `ACTIVE` and that the last create or update finished, and retry before you change the config. During a gateway update, some requests can still reach the previous API config. A JSON 404 (`The current request is not defined by this API.`) means that the active config does not define the path.
   - If `tools/list` requires a JWT, mint a Google ID token whose audience is in `x-google-auth.audiences`: `gcloud auth print-identity-token --impersonate-service-account={caller_sa_email} --audiences={jwt_audience}`. If `tools/list` requires an API key, send it in the `x-api-key` header.
   - Run the `initialize`, `notifications/initialized`, `tools/list`, and `tools/call` verification probes in [MCP Verification and Troubleshooting](references/mcp-limitations-and-troubleshooting.md).
   - Connect Google ADK (`McpToolset`) and verify automatic catalog discovery in Apigee API hub (`{your_api} (MCP)`) and Agent Registry using [ADK and API Hub Discovery](references/adk-and-api-hub-discovery.md).

## Pre-Deployment Checklist

- [ ] Specification version is `openapi: 3.0.x` or `3.1.x` (not `swagger: "2.0"`), omits `x-google-allow`, and does not contain `x-google-model-router`.
- [ ] `python3 scripts/validate_mcp_openapi.py --spec={candidate_openapi_spec}` returns `status: "PASS"` (exit code `0`).
- [ ] Every operation has an `operationId`, and all MCP operations are in one OpenAPI document.
- [ ] `x-google-api-management.mcp.tools-list.security` names exactly one scheme: an `oauth2` JWT scheme with `x-google-auth` that the root `security` list also references, or an `apiKey` scheme with `in: header` and `name: x-api-key`.
- [ ] If `tools/list` uses a JWT scheme, the user knows that REST operations without their own `security` now require that JWT.
- [ ] Administrative, health-check, and `HTTP 204` endpoints are opted out with `x-google-mcp-tool: false`, and opted-out admin paths remain protected on REST.
- [ ] MCP clients call `https://{default_hostname}/mcp` (not `{basepath}/mcp`), nest `tools/call` JSON request bodies inside `params.arguments.body`, and send `MCP-Protocol-Version: 2025-11-25`.

## Resource Cleanup

To avoid ongoing charges when tearing down a test or staging environment, request human approval and delete the gateway, API config, API, and service account in dependency order:

```bash
gcloud api-gateway gateways delete {gateway_id} --location={region} --project={project_id}
gcloud api-gateway api-configs delete {config_id} --api={api_id} --project={project_id}
gcloud api-gateway apis delete {api_id} --project={project_id}
gcloud iam service-accounts delete {gateway_sa_name}@{project_id}.iam.gserviceaccount.com --project={project_id}
```
