# Agent Registry Architecture, MCP Services, and Multi-Project Federation

This reference details the design, TLS SNI inspection mechanics, consolidated
`googleapis` service patterns, manual cross-project MCP and Agent2Agent (A2A)
registration workflows, service catalog schemas, and automated federation engines
for **Agent Registry**.

--------------------------------------------------------------------------------

## Table of Contents

-   [1. Registry Architecture, TLS SNI Inspection, and Centralized Catalog Model](#1-registry-architecture-tls-sni-inspection-and-centralized-catalog-model): Lines 21-71
-   [2. Manual Cross-Project Registration Runbook](#2-manual-cross-project-registration-runbook): Lines 72-167
-   [3. Scoping, Identity Decision Matrix, and Critical CEL Guards](#3-scoping-identity-decision-matrix-and-critical-cel-guards): Lines 168-198
-   [4. The Consolidated `googleapis` Service Invariant](#4-the-consolidated-googleapis-service-invariant): Lines 199-293
-   [5. Automated Multi-Project Registry Federation](#5-automated-multi-project-registry-federation): Lines 294-329
-   [6. Agent Registry Taxonomy Metadata, Resource Labels and CI/CD Catalog Automation](#6-agent-registry-taxonomy-metadata-resource-labels-and-cicd-catalog-automation): Lines 330-342

--------------------------------------------------------------------------------

## 1. Registry Architecture, TLS SNI Inspection, and Centralized Catalog Model

The Agent Registry acts as the Service Directory and L7 routing table for the
Agent Gateway. When an Agent Connectivity Template operates in `ALL_TRAFFIC`
mode, outbound TCP connections from the Agent Runtime resolve to synthetic
Private Service Connect VIP `240.0.0.2:443`. The Gateway inspects the TLS Server
Name Indication (SNI) header:

-   Under IAM Policy V1 (when `iapPolicyVersion = "V2"` is not set), if the SNI
    does not match an authorized entry in Agent Registry, the connection is
    dropped immediately with `default_denied` (`[SSL:
    UNEXPECTED_EOF_WHILE_READING]`).
-   When UAP Policy V2 (`iapPolicyVersion = "V2"`) is enabled on the
    `AuthzExtension`, unregistered SNIs evaluate against UAP rules matching
    `destination.is_registered == false` (`destination.unregistered.host`)
    before being allowed or dropped.

```text
+-----------------------------------------------------------------------------------------+
| Agent Runtime -> Connects to synthetic VIP: 240.0.0.2:443                               |
+--------------------------------------------+--------------------------------------------+
                                             | (TLS SNI Inspection)
                                             v
+-----------------------------------------------------------------------------------------+
| Agent Gateway (Managed Envoy)                                                           |
|   • SNI Match: Evaluate UAP / IAP Egressor Policy (destination.is_registered == true)   |
|   • No Match (Policy V1): Reject with default_denied (UNEXPECTED_EOF_WHILE_READING)     |
|   • No Match (UAP V2): Evaluate destination.is_registered == false rules                |
+--------------------------------------------+--------------------------------------------+
                                             |
                        +--------------------+--------------------+
                        v                                         v
+-----------------------------------------------+ +---------------------------------------+
| Consolidated googleapis Service (Core FQDNs)  | | External REST & MCP Services (/mcp)   |
+-----------------------------------------------+ +---------------------------------------+
```

In enterprise governance architectures, the Agent Registry resides in the
**Centralized Governance Project (`AGW_PROJECT_ID`)** alongside the Agent
Gateway:

-   **Catalog Registration (Governance Plane)**: Service definitions, interface
    URLs, and OpenAPI/MCP tool specs are published into the central Agent
    Registry (`agentregistry.googleapis.com`).
-   **Access Authorization (Data Plane)**: Egress authorization is governed in
    the central project via UAP Policy V2 or `roles/iap.egressor`, while runtime
    invocation permissions (`roles/run.invoker`) are granted on backend compute
    resources (Cloud Run, GKE) in the producer project.

--------------------------------------------------------------------------------

## 2. Manual Cross-Project Registration Runbook

In Agent Registry, `mcp-servers`, `endpoints`, and `agents` are read-only
projections. All write operations target GA `gcloud agent-registry services`
(use GA `gcloud agent-registry` commands across all runbooks). In GA `gcloud iap
web add-iam-policy-binding`, resource type flags use singular names
(`--mcp-server`, `--agent`, `--endpoint`), never plural flag names
(`--mcp-servers`, `--agents`, `--endpoints`).

### 2.1 Cross-Project MCP Server Registration

> [!IMPORTANT] **MCP Protocol Binding and URL Invariants**: 1. Protocol binding in
> `gcloud` CLI MUST be **`JSONRPC`** (`HTTP_JSON` is rejected for MCP
> servers). 2. The interface URL path MUST end with **`/mcp`** (such as
> `https://${MCP_HOST}/mcp`). 3. MCP tool specifications
> (`--mcp-server-spec-content`) must stay under the **10 KB payload limit**.

```bash
# Option A: Register MCP Server with Tool Spec (< 10 KB)
gcloud agent-registry services create "${MCP_SERVICE_NAME}" \
  --project="${AGW_PROJECT_ID}" --location="${REGION}" \
  --display-name="${MCP_SERVICE_DISPLAY_NAME}" \
  --mcp-server-spec-type=tool-spec --mcp-server-spec-content="$(cat toolspec.json)" \
  --interfaces="protocolBinding=JSONRPC,url=https://${MCP_HOST}/mcp" --quiet

# Option B: Register MCP Server without Tool Spec (Dynamic Discovery)
gcloud agent-registry services create "${MCP_SERVICE_NAME}" \
  --project="${AGW_PROJECT_ID}" --location="${REGION}" \
  --display-name="${MCP_SERVICE_DISPLAY_NAME}" \
  --mcp-server-spec-type=no-spec \
  --interfaces="protocolBinding=JSONRPC,url=https://${MCP_HOST}/mcp" --quiet
```

### 2.2 Cross-Project Agent2Agent Protocol (A2A Protocol) Registration

-   **Option A (`--agent-spec-type=a2a-agent-card`)**: Target URL
    (`https://${REGION}-aiplatform.googleapis.com/v1/projects/${TARGET_PROJECT_NUMBER}/locations/${REGION}/reasoningEngines/${TARGET_ENGINE_ID}:query`
    or custom A2A ingress URL) is declared inside `agentspec.json`
    (`--interfaces` must be omitted when `--agent-spec-type=a2a-agent-card` is
    set).
-   **Option B (`--agent-spec-type=no-spec`)**: Pass the custom A2A proxy
    endpoint URL via
    `--interfaces="protocolBinding=JSONRPC,url=https://a2a-agent.internal.example.com/a2a"`.

```bash
gcloud agent-registry services create "${TARGET_AGENT_NAME}" \
  --project="${AGW_PROJECT_ID}" --location="${REGION}" \
  --display-name="${TARGET_AGENT_DISPLAY_NAME}" \
  --agent-spec-type=a2a-agent-card --agent-spec-content="$(cat agentspec.json)"
```

### 2.3 External REST and SaaS API Registration

External public REST APIs accessed by agent tools under Policy V1 (or registered
endpoints under Policy V2) are registered with `protocolBinding=HTTP_JSON` and
`--endpoint-spec-type=no-spec`:

```bash
gcloud agent-registry services create "ip-lookup-service" \
  --project="${AGW_PROJECT_ID}" --location="${REGION}" \
  --display-name="IP Lookup Service" --endpoint-spec-type=no-spec \
  --interfaces="protocolBinding=HTTP_JSON,url=https://api.ipify.org" --quiet
```

### 2.4 Server-Generated Resource ID Extraction and IAP Authorization

Agent Registry generates unique internal resource UUIDs (the last segment of
`registryResource`, such as `agentregistry-00000000-...`). IAP policy bindings
require this server-generated UUID and `roles/iap.egressor` (never the friendly
service name or `roles/iap.tunnelResourceAccessor`):

```bash
# 1. Extract Server-Generated Resource ID (via gcloud agent-registry mcp-servers describe or gcloud agent-registry services describe)
REGISTRY_RESOURCE=$(gcloud agent-registry mcp-servers describe "${MCP_SERVICE_NAME}" \
  --project="${AGW_PROJECT_ID}" --location="${REGION}" --format='value(registryResource)')
RESOURCE_ID=$(basename "${REGISTRY_RESOURCE}")

# 2. Grant roles/iap.egressor separating discovery (empty toolName) from specific tools/call invocation
gcloud iap web add-iam-policy-binding \
  --project="${AGW_PROJECT_ID}" --region="${REGION}" \
  --resource-type=agent-registry --mcp-server="${RESOURCE_ID}" \
  --member="principal://agents.global.org-${ORG_ID}.system.id.goog/resources/aiplatform/projects/${AE_PROJECT_NUMBER}/locations/${REGION}/reasoningEngines/${ENGINE_ID}" \
  --role="roles/iap.egressor" \
  --condition="^:^expression=(api.getAttribute('iap.googleapis.com/mcp.method', '') in ['initialize', 'tools/list'] && api.getAttribute('iap.googleapis.com/mcp.toolName', '') == '') || (api.getAttribute('iap.googleapis.com/mcp.method', '') == 'tools/call' && api.getAttribute('iap.googleapis.com/mcp.toolName', '') == 'get_weather'):title=AllowDiscoveryAndTool" \
  --quiet

# 3. Grant roles/iap.egressor to Agent Runtime Service Account
gcloud iap web add-iam-policy-binding \
  --project="${AGW_PROJECT_ID}" --region="${REGION}" \
  --resource-type=agent-registry --mcp-server="${RESOURCE_ID}" \
  --member="serviceAccount:service-${AE_PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com" \
  --role="roles/iap.egressor" --quiet
```

--------------------------------------------------------------------------------

## 3. Scoping, Identity Decision Matrix, and Critical CEL Guards

-   **Google APIs Endpoint** (`Project` or `Org` scope, `principalSet://`,
    `roles/iap.egressor`): Unconditional allow for registered `googleapis`.
-   **Internal MCP Server — Read-Only** (`Per-Agent` scope,
    `principal://.../reasoningEngines/ID`, `roles/iap.egressor`):
    -   IAP V1: `api.getAttribute('iap.googleapis.com/mcp.tool.isReadOnly',
        false) == true || api.getAttribute('iap.googleapis.com/mcp.toolName',
        '') == ''`
    -   UAP V2: `(destination.agent_registry.mcp_server.method == 'tools') &&
        (destination.agent_registry.mcp_server.tool.name == '' ||
        destination.agent_registry.mcp_server.tool.annotations.read_only_hint ==
        true)`
-   **Internal MCP Server — Read/Write** (`Per-Agent` scope,
    `principal://.../reasoningEngines/ID`, `roles/iap.egressor`): Specific tool
    allowlist plus empty `toolName` (`tool.name == ''`).
-   **Agent2Agent protocol (A2A)** (`Per-Agent` scope, `principal://` Calling
    Agent ID, `roles/iap.egressor`): Optional method filter.

### 3.1 Empty `toolName` and Null-Dereference Guards

During MCP `initialize` and `tools/list` handshakes, no specific tool name is
present (`""`), and during non-tool calls (`prompts/list`, `resources/read`),
`destination.agent_registry.mcp_server.tool` is null. Always check `method ==
'tools'` first and permit empty tool names (`tool.name == ''` in UAP Policy V2
or `api.getAttribute('iap.googleapis.com/mcp.toolName', '') == ''` in IAP V1).
See `references/governance_security_policies.md` Sections 2–4 for full UAP
Policy V2 templates.

--------------------------------------------------------------------------------

## 4. The Consolidated `googleapis` Service Invariant

> [!IMPORTANT] **Consolidated Registry Rule**: Never create fragmented, per-API
> service entries in Agent Registry. Consolidate all Google Cloud APIs under a
> **single service entry named `googleapis`**. Separate standalone Google API
> service entries fail Envoy route matching and evaluate as
> `unregisteredEndpoint` (`destination.is_registered == false`).

### 4.1 The 8 Required Base FQDN Interfaces (Plus Telemetry)

Every consolidated `googleapis` registry service must define the 8 mandatory
base Google API FQDNs plus the 9th telemetry mTLS endpoint:

1.  `https://agentregistry.googleapis.com`
2.  `https://aiplatform.googleapis.com`
3.  `https://aiplatform.mtls.googleapis.com`
4.  `https://cloudresourcemanager.mtls.googleapis.com`
5.  `https://iamcredentials.mtls.googleapis.com`
6.  `https://${REGION}-aiplatform.mtls.googleapis.com`
7.  `https://${REGION}-aiplatform.googleapis.com`
8.  `https://aiplatform.${REGION}.rep.googleapis.com`
9.  `https://telemetry.mtls.googleapis.com`

### 4.2 Additional Telemetry, Global/Multi-Region Model and Hostname Permutations

-   **Telemetry and Tracing Endpoints**: Include
    `https://monitoring.googleapis.com`, `https://trace.mtls.googleapis.com`,
    `https://cloudtrace.googleapis.com`, `https://logging.googleapis.com`, and
    `https://telemetry.googleapis.com` so OpenTelemetry and Cloud Logging
    exporters do not drop on container startup.
-   **Global and Multi-Region Foundation Models**: When using models via the
    `global` endpoint (such as `gemini-2.5-pro` with
    `GOOGLE_CLOUD_LOCATION="global"`) or cross-region `us-central1` models,
    include `https://us-aiplatform.googleapis.com`,
    `https://us-aiplatform.mtls.googleapis.com`,
    `https://aiplatform.us.rep.googleapis.com` (and `us-central1-aiplatform.*`
    when deployed outside `us-central1`).
-   **Hostname Permutation Matrix**: Agent Gateway matches SNI hostnames
    strictly across all 6 Google API forms: Base REST
    (`aiplatform.googleapis.com`), Base mTLS (`aiplatform.mtls.googleapis.com`),
    Locational REST (`${REGION}-aiplatform.googleapis.com`), Locational mTLS
    (`${REGION}-aiplatform.mtls.googleapis.com`), Regional REP
    (`aiplatform.${REGION}.rep.googleapis.com`), and Private PSC REP
    (`aiplatform.${REGION}.p.rep.googleapis.com`).
-   **10 KB Spec Limit, Dual-Registry Cap and Multi-Region Registration
    Prohibition**: `--mcp-server-spec-content` and `--agent-spec-content`
    enforce a hard **10 KB** limit. An Agent Gateway supports a **maximum of 2
    registries** (at most 1 `global` and 1 regional, referenced using numeric
    `uint64` project numbers; see `references/agent_gateway_and_act.md` Section
    3.4). Manual registration in multi-region locations (`--location=us` or
    `--location=eu`) is **unsupported** and returns HTTP 400; always register in
    a specific region (such as `us-central1` or `us-east4`) or `global`.

### 4.3 Canonical Consolidated `googleapis` Registration Command and Schema Rules

When registering Agent Registry services (`agentregistry.services`), provide
`serviceId`, `location`, one spec block (`endpointSpec`, `mcpServerSpec`, or
`agentSpec`), and `interfaces` entries (`url` and `protocolBinding` =
`"HTTP_JSON"`, `"JSONRPC"`, or `"GRPC"`). Use `"GRPC"` for binary HTTP/2 gRPC
endpoints (`spanner.googleapis.com`, `telemetry.mtls.googleapis.com`,
`trace.mtls.googleapis.com`) and `"HTTP_JSON"` for all `aiplatform*.googleapis.com`
REST endpoints:

```bash
gcloud agent-registry services create "googleapis" \
  --project="${PROJECT_ID}" \
  --location="${REGION}" \
  --display-name="Google Cloud APIs" \
  --description="Consolidated Google Cloud APIs catalog for Agent Gateway egress" \
  --endpoint-spec-type=no-spec \
  --interfaces="url=https://agentregistry.googleapis.com,protocolBinding=HTTP_JSON" \
  --interfaces="url=https://aiplatform.googleapis.com,protocolBinding=HTTP_JSON" \
  --interfaces="url=https://aiplatform.mtls.googleapis.com,protocolBinding=HTTP_JSON" \
  --interfaces="url=https://${REGION}-aiplatform.googleapis.com,protocolBinding=HTTP_JSON" \
  --interfaces="url=https://${REGION}-aiplatform.mtls.googleapis.com,protocolBinding=HTTP_JSON" \
  --interfaces="url=https://aiplatform.${REGION}.rep.googleapis.com,protocolBinding=HTTP_JSON" \
  --interfaces="url=https://us-aiplatform.googleapis.com,protocolBinding=HTTP_JSON" \
  --interfaces="url=https://us-aiplatform.mtls.googleapis.com,protocolBinding=HTTP_JSON" \
  --interfaces="url=https://aiplatform.us.rep.googleapis.com,protocolBinding=HTTP_JSON" \
  --interfaces="url=https://cloudresourcemanager.googleapis.com,protocolBinding=HTTP_JSON" \
  --interfaces="url=https://cloudresourcemanager.mtls.googleapis.com,protocolBinding=HTTP_JSON" \
  --interfaces="url=https://iamcredentials.googleapis.com,protocolBinding=HTTP_JSON" \
  --interfaces="url=https://iamcredentials.mtls.googleapis.com,protocolBinding=HTTP_JSON" \
  --interfaces="url=https://storage.googleapis.com,protocolBinding=HTTP_JSON" \
  --interfaces="url=https://telemetry.mtls.googleapis.com,protocolBinding=GRPC" \
  --interfaces="url=https://monitoring.googleapis.com,protocolBinding=HTTP_JSON" \
  --interfaces="url=https://trace.mtls.googleapis.com,protocolBinding=GRPC" \
  --interfaces="url=https://cloudtrace.googleapis.com,protocolBinding=HTTP_JSON" \
  --interfaces="url=https://logging.googleapis.com,protocolBinding=HTTP_JSON" \
  --interfaces="url=https://telemetry.googleapis.com,protocolBinding=HTTP_JSON" \
  --interfaces="url=https://spanner.googleapis.com,protocolBinding=GRPC"
```

--------------------------------------------------------------------------------

## 5. Automated Multi-Project Registry Federation

### 5.1 The Read-Through Invalidation and Anti-Entropy Pattern

Treat Cloud Audit Logs or Cloud Asset Inventory (CAI) feeds strictly as **cache
invalidation triggers**:

1.  **Folder Log Sink**: Catches `CreateService`, `UpdateService`, or
    `DeleteService` on `agentregistry.googleapis.com` across spoke projects
    (excluding `projects/${HUB_PROJECT_ID}/`, `projects/${HUB_PROJECT_NUMBER}/`,
    and the replicator service account email to prevent echo loops) and
    publishes to Pub/Sub with a dead-letter topic (`maxDeliveryAttempts = 5`).
2.  **Authoritative Spoke Read-Through and Validation**: A Cloud Run Replicator
    service calls `GetService` against the spoke
    (`projects/{spoke}/locations/{loc}/services/{spoke_service}`), verifies that
    the interface URL uses an approved FQDN (rejecting raw IP literals or
    blocklisted external domains so spoke registrations cannot bypass Org UAP
    guardrails), and upserts the federated service into the Central Hub Registry
    (`projects/{hub}/locations/{loc}/services/{spoke_project}--{spoke_service}`)
    using
    `updateMask=displayName,description,interfaces,agentSpec,mcpServerSpec,endpointSpec`
    and watermark comparison (`replicated_from_update_time=...`).
3.  **Hourly Anti-Entropy Sweep**: A Cloud Run Job (triggered by Cloud
    Scheduler) reconciles spoke `ListServices` / CAI against Hub records older
    than 2 hours (`updateTime < NOW - 2h`) before pruning deleted spoke services
    via `DeleteService`.

```bash
gcloud logging sinks create "agent-registry-events-sink" \
  "pubsub.googleapis.com/projects/${HUB_PROJECT_ID}/topics/agent-registry-events" \
  --folder="${FOLDER_ID}" --include-children \
  --log-filter="protoPayload.serviceName=\"agentregistry.googleapis.com\" AND protoPayload.methodName:(\"CreateService\" OR \"UpdateService\" OR \"DeleteService\") AND NOT protoPayload.resourceName:\"projects/${HUB_PROJECT_ID}/\" AND NOT protoPayload.resourceName:\"projects/${HUB_PROJECT_NUMBER}/\" AND NOT protoPayload.authenticationInfo.principalEmail=\"${REPLICATOR_SA_EMAIL}\""
```

--------------------------------------------------------------------------------

## 6. Agent Registry Taxonomy Metadata, Resource Labels and CI/CD Catalog Automation

1.  **Standardized Taxonomy Metadata and Resource Labels**: Attach standard Google
    Cloud resource labels (`labels = { env = "...", team = "...", cost_center =
    "...", owner = "..." }`) to underlying compute/runtime resources
    (`ReasoningEngine`, Cloud Run, GKE) and encode structured taxonomy metadata
    (`env=...;team=...;cost_center=...;owner=...`) into the Agent Registry
    `service_id` naming convention (`{team}-{env}-{service_name}`) and
    `--description` field.
2.  **Automated CI/CD Registration and Verification**: Combine declarative service
    definitions in spoke projects with the event-driven catalog replicator
    (Section 5) and gate promotion using the Post-Deployment Verification
    Checklist (`references/topologies_and_project_layouts.md` Section 10).
