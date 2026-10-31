# Agent Registry — Debugging Reference

Curated reference for diagnosing why agents, MCP servers, and endpoints
registered in Google Cloud Agent Registry are not accepting traffic through
Agent Gateway / IAP.

Scope: Gemini Enterprise Agent Platform — Agent Registry (`v1` GA). Core commands
use `gcloud agent-registry` (`gcloud beta agent-registry` does **not** exist, and
`endpoints` is read-only with no `create` subcommand; all manual writes go through
`gcloud agent-registry services`). Standalone skills use `gcloud agent-registry
skills` (`list` / `describe`).

## Table of Contents

-   [TL;DR for Debugging](#tldr-for-debugging): Lines 29-149
-   [1. The Data Model in One Picture](#1-the-data-model-in-one-picture): Lines 150-197
-   [2. Default-Deny + Hostname Matching](#2-default-deny--hostname-matching): Lines 198-338
-   [3. Resource Type — Agents](#3-resource-type--agents): Lines 339-472
-   [4. Resource Type — MCP Servers](#4-resource-type--mcp-servers): Lines 473-561
-   [5. Resource Type — Endpoints](#5-resource-type--endpoints): Lines 562-705
-   [6. IAM Scope: Registry-Wide vs Per-Resource](#6-iam-scope-registry-wide-vs-per-resource): Lines 706-845
-   [7. Common Registration Errors and Where to Look](#7-common-registration-errors-and-where-to-look): Lines 846-877
-   [8. Discovery via the Agent Registry MCP Server](#8-discovery-via-the-agent-registry-mcp-server): Lines 878-906
-   [9. Quick Reference — Every gcloud Subcommand](#9-quick-reference--every-gcloud-subcommand): Lines 907-971
-   [Source Index](#source-index): Lines 972-998

--------------------------------------------------------------------------------

## TL;DR for Debugging

Read these first when something is broken.

1.  **Agent Registry is default-deny at the gateway.** Agent Gateway uses
    Identity-Aware Proxy (IAP) to enforce authorization:

    -   **UAP (Policy V2)**: When the gateway uses `iapPolicyVersion: "V2"`,
        Gatekeeper queries the attached registries. If the destination matches,
        Gatekeeper sets `destination.is_registered = true` and exposes rich CEL
        metadata under `destination.agent_registry.*`. If not cataloged,
        `destination.is_registered = false`.
    -   **Legacy IAM v1**: When using legacy v1, if a target hostname is not
        registered as a `Service` (and a matching `roles/iap.egressor` binding
        does not exist on the registry entry for the calling agent's principal),
        egress is blocked. Source:
        `docs.cloud.google.com/iap/docs/agent-overview`.

2.  **There are exactly three discoverable resource types**, and they are
    *projections* of the same writable `Service`:

    -   **Agent** (read-only `Agent`)
    -   **MCP server** (read-only `McpServer`)
    -   **Endpoint** (read-only `Endpoint`) You always create/update/delete via
        `services`. You list/describe via `agents`, `mcp-servers`, `endpoints`,
        or `services`. Source: `docs.cloud.google.com/agent-registry/concepts`.

3.  **Hostname matching is exact.** A single Google API can be reached at five+
    distinct hostnames (base, mTLS, locational, locational-mTLS, REP regional).
    Each hostname is a *separate* `Service` registration. If your agent calls
    `bigquery.us-central1.rep.googleapis.com` but you only registered
    `bigquery.googleapis.com`, the call is denied. See the "Hostname Matrix"
    section.

4.  **Manual registration is not supported in `us` or `eu` multi-region
    locations.** `us` and `eu` are read-only roll-up discovery locations for
    automatically registered Gemini Enterprise components and standalone skills.
    Always register `Service` entries and `Binding` resources in a specific
    region (e.g., `us-central1`, `europe-west1`) or `global`.

5.  **Two predefined IAM roles control the registry itself**:

    -   `roles/agentregistry.viewer` (`agentregistry.{agents,endpoints,mcpServers}.list`)
        — discover entries **and** required by the caller importing an `AgentGateway`
        referencing the registry.
    -   `roles/agentregistry.editor` — create/update/delete `Service` resources.
        These are project-scoped catalog permissions, not runtime traffic permissions.

6.  **Traffic permissions live on IAP (Policy V1 vs. UAP Policy V2):**
    -   **Policy V1 (`gcloud iap web`)**: Grant `roles/iap.egressor`
        (`iap.webServiceVersions.egressViaIAP`) with **`--resource-type=agent-registry`
        always set**, optionally scoped with `--agent=AGENT_UUID`,
        `--mcp-server=MCP_UUID`, or `--endpoint=ENDPOINT_UUID` (using the
        server-generated `registryResource` basename, never `SERVICE_NAME`).
    -   **UAP Policy V2 (`iapPolicyVersion: "V2"`)**: Grant
        `iap.googleapis.com/resources.egressViaIAP` via `gcloud iam
        access-policies` and `gcloud iam policy-bindings`.

7.  **Identifiers matter:**
    -   `SERVICE_NAME` / `SERVICE_ID` — your chosen ID (4–63 chars `[a-z0-9-]`)
        for `gcloud agent-registry services`.
    -   `registryResource` UUID — server-generated child ID under `/endpoints/`,
        `/mcpServers/`, or `/agents/` required by `gcloud iap web`.
    -   **Agent / MCP server URN** — immutable identifier (`urn:mcp:...`,
        `urn:agent:...`) used by discovery tools and `ExtensionBinding` matchers.
    -   **Resource URI** — runtime URI embedded in the SPIFFE principal.

8.  **Specs have a hard 10 KB cap and use plain file paths (no `@`).** Pass
    `--mcp-server-spec-content=toolspec.json` or
    `--agent-spec-content=agent-card.json` (`<= 10 KB`; `gcloud` `arg_json`
    rejects `curl`-style `@file.json`).

9.  **Automatic registration vs. manual:** Agent Runtime (SDK), Google Workspace,
    Gemini Enterprise, annotated GKE (`registry.gke.io/functional-type:
    "MCP_SERVER"`), Cloud Run services with `--functional-type={agent|mcp-server}`,
    and enabled Google/Google Cloud remote MCP servers (created in `global` only)
    register *automatically* **within the governance project only**. Cross-project
    workloads, standard Cloud Run services, on-prem, and third-party APIs require
    manual `gcloud agent-registry services create`.
    -   **Cloud Run `.run.app` vs. `.a.run.app` trap**: Automatic registration
        records the deterministic regional URL
        (`https://<SERVICE>-<PROJECT_NUMBER>.<REGION>.run.app`). Calling the
        legacy hash URL (`https://<SERVICE>-<HASH>-uc.a.run.app`) fails exact
        hostname matching unless manually registered.

10. **First debug command**: confirm the exact target URL is registered (`gcloud
    agent-registry endpoints list --project=$PROJECT_ID --location=$LOCATION` and
    `gcloud agent-registry services list --filter="interfaces.url:FRAGMENT"`).

11. **Governance project scope (no automatic cross-project discovery).**
    Automatic registration only discovers resources inside the governance project
    where `agentregistry.googleapis.com` is enabled. Remote agents and MCP servers
    in separate Google Cloud projects must be manually registered in the central
    governance project's registry.

12. **Agent Gateway Dual-Registry & Jurisdiction Rules**: An `AgentGateway`
    supports a **maximum of two** registries in `registries[]`. When two
    registries are configured, **exactly one must be `global`** and the other
    must be regional (e.g., `us-central1`) or multi-regional (`us`, `eu`).
    -   Binding **two regional registries** (e.g., `us-central1` and
        `europe-west1`) is invalid and rejected with an **HTTP `400`** validation
        error.
    -   **Jurisdiction alignment**: A regional gateway can only reference a
        regional registry in the **same region** or a multi-region registry in
        the **same data residency jurisdiction** (e.g., `us-central1` gateway +
        `eu` registry is rejected with `InvalidArgument`).
    -   **Gateway import preflight**: If `agent-gateways import` fails with
        `Config validation failed` and `missing permissions:
        agentregistry.agents.list`, enable **`agentregistry.googleapis.com`** on
        the registry project and ensure the deploying caller holds
        `roles/agentregistry.viewer` (`agentregistry.{agents,endpoints,mcpServers}.list`).

13. **REST API Path Extensions & Explicit Forward Proxies**: SDK clients such as
    Zendesk append `.json` (`/api/v2/tickets.json`) — account for `.json`, `/`
    subpaths, and `?` query strings in UAP CEL rules. Note that an explicit
    forward `HTTPS_PROXY` tunnel (`HTTP CONNECT`) requires a `v1beta1` L4
    `AuthzPolicy` (`networkRules` matching SNIs), not an Agent Registry entry for
    the proxy host (see `references/agent-gateway.md` and BKI #34).

--------------------------------------------------------------------------------

## 1. The Data Model in One Picture

```
                 WRITE side                          READ side (read-only projections)
              +--------------+                    +----------+
              |              |  endpoint-spec --> | Endpoint |
              |   Service    |  mcp-server-spec ->| McpServer|
              | (writable)   |  agent-spec -----> |  Agent   |
              +--------------+                    +----------+
                ^                                        ^
         create/update/delete                     get/list/search
         (services subcommand)                    (endpoints / mcp-servers /
                                                   agents subcommand)
```

-   The `Service` resource is the only thing you write.
-   Agent Registry **automatically generates** the corresponding `Agent`,
    `McpServer`, or `Endpoint` projection based on the `*-spec-type` you passed
    at create time.
-   The mutually exclusive `*-spec-type` flag at creation determines the read-only
    projection (spec types cannot be changed on `services update`):

    | `services create` Spec Flag | Allowed `--interfaces` | Read-Only Projection |
    | :--- | :--- | :--- |
    | `--endpoint-spec-type=no-spec` | Required (1+ URLs) | `Endpoint` |
    | `--mcp-server-spec-type={tool-spec\|no-spec}` | Required (`protocolBinding=JSONRPC`) | `McpServer` |
    | `--agent-spec-type=a2a-agent-card` | **Must be omitted** (read from `agent-card.json`) | `Agent` (with A2A skills) |
    | `--agent-spec-type=no-spec` | Required (REST URL) | `Agent` (non-A2A REST) |

    *(Standalone `Skill` resources do not use `Service`; inspect via `gcloud agent-registry skills list --location=LOCATION --project=PROJECT_ID`.)*

Source: `docs.cloud.google.com/agent-registry/overview`,
`docs.cloud.google.com/agent-registry/concepts`.

### URN formats (memorize these)

-   **Manually registered MCP server URN:**
    `urn:mcp:projects-PROJECT_NUMBER:projects:PROJECT_NUMBER:locations:REGION:agentregistry:SERVICE_ID`
-   **Google Cloud remote MCP server URN:**
    `urn:mcp:googleapis.com:projects:PROJECT_NUMBER:locations:global:SERVICE_NAME`

If a discovery query returns no results for what you think is a registered
server, check the URN format vs the location you registered against.

Source: `docs.cloud.google.com/agent-registry/concepts`.

--------------------------------------------------------------------------------

## 2. Default-Deny + Hostname Matching

This is the single most common debugging failure mode. Read this whole section.

### Why default-deny

Agent Gateway is the egress proxy for agents. It is built on IAP. IAP only
forwards a request if there is an IAM allow policy granting `roles/iap.egressor`
to the calling agent's principal **on a registry resource that matches the
request**. If no `Service` matches the destination hostname, no policy can
match, and the request is denied.

Source: `docs.cloud.google.com/iap/docs/agent-overview`.

### Hostname Matrix — register every form an agent might call

A single Google Cloud API can be addressed via several distinct hostnames. Each
one is a separate registry entry. The canonical set includes the following; if
any are missing for an API your agent uses, expect denial.

Variant           | Hostname pattern                        | Example (`bigquery`, `us-central1`)
----------------- | --------------------------------------- | -----------------------------------
Base / global     | `SERVICE.googleapis.com`                | `bigquery.googleapis.com`
mTLS              | `SERVICE.mtls.googleapis.com`           | `bigquery.mtls.googleapis.com`
Locational        | `LOCATION-SERVICE.googleapis.com`       | `us-central1-bigquery.googleapis.com`
Locational mTLS   | `LOCATION-SERVICE.mtls.googleapis.com`  | `us-central1-bigquery.mtls.googleapis.com`
REP (public)      | `SERVICE.LOCATION.rep.googleapis.com`   | `bigquery.us-central1.rep.googleapis.com`
REP (private/PSC) | `SERVICE.LOCATION.p.rep.googleapis.com` | `bigquery.us-central1.p.rep.googleapis.com`

-   **Locational endpoints** specify the region/multi-region in the URL prefix.
    Format: `LOCATION-SERVICE.googleapis.com`. Locational endpoints don't
    support data-residency-compliant connections from on-premises and don't
    support failure-domain isolation; **REP is replacing them**.
-   **REP (Regional Endpoint)** confines TLS termination and traffic to the
    specified region. Format: `SERVICE.REGION.rep.googleapis.com`. Private REP
    via PSC adds `.p.`.
-   The base/global hostname terminates TLS at the nearest edge and provides no
    regional isolation.

Source:
`docs.cloud.google.com/docs/security/compliance/restrict-endpoint-usage`.

### Recommended Pattern: Consolidated Google APIs Service

> **Warning:** **MANDATORY GOOGLE APIS CONSOLIDATION RULE**: NEVER recommend or
> register separate `Service` resources for individual Google APIs (such as
> Agent Runtime, Cloud Resource Manager, IAM, or Telemetry). Do NOT register
> each Google API as a separate service entry, as separate service entries cause
> resource clutter, complicate IAM policy management, and risk hitting registry
> quota limits. ALL Google APIs MUST ALWAYS be consolidated under a single Agent
> Registry Service named `googleapis` using multiple interfaces.

Instead of registering dozens of separate `Service` resources for each Google
API and its regional/mTLS permutations, consolidate all Google APIs under a
single Agent Registry Service named `googleapis` using **multiple interfaces**.
This reduces resource clutter, simplifies IAM policy management (granting
`roles/iap.egressor` once), and avoids registry quota limits.

#### The 8 Mandatory Base Interfaces + Essential Platform Families

For every Agent Runtime deployment behind an `ALL_TRAFFIC` Egress Agent Gateway,
the consolidated `googleapis` service **must** include the **8 base FQDN
interfaces**:

1.  `https://agentregistry.googleapis.com`
2.  `https://aiplatform.mtls.googleapis.com`
3.  `https://cloudresourcemanager.mtls.googleapis.com`
4.  `https://iamcredentials.mtls.googleapis.com`
5.  `https://telemetry.mtls.googleapis.com`
6.  `https://{region}-aiplatform.mtls.googleapis.com` (e.g., `us-central1`)
7.  `https://{region}-aiplatform.googleapis.com`
8.  `https://aiplatform.{region}.rep.googleapis.com`

Depending on model availability and runtime features, include these additional
interfaces from the **9 essential Google Cloud API families** on the **same**
`googleapis` service:

-   **Global & Multi-Region Foundation Models**: Many Gemini models only expose
    `global` or multi-region (`us`, `eu`) endpoints. Add
    `https://aiplatform.googleapis.com` (alongside `aiplatform.mtls.googleapis.com`)
    and, if targeting `us`/`eu`, `https://us-aiplatform.googleapis.com`,
    `https://us-aiplatform.mtls.googleapis.com`, and
    `https://aiplatform.us.rep.googleapis.com`. Calling an unsupported regional
    model returns `HTTP 404 NOT_FOUND`; calling `global` without registering
    `aiplatform.googleapis.com` drops TLS at `240.0.0.2:443` (`UNEXPECTED_EOF`).
-   **Tracing, Logging, Monitoring, Storage, & Artifact Registry**: Add
    `https://cloudtrace.googleapis.com`, `https://cloudtrace.mtls.googleapis.com`,
    `https://trace.googleapis.com`, `https://trace.mtls.googleapis.com`,
    `https://monitoring.googleapis.com`, `https://monitoring.mtls.googleapis.com`,
    `https://logging.googleapis.com`, `https://logging.mtls.googleapis.com`,
    `https://storage.googleapis.com`, `https://storage.mtls.googleapis.com`,
    `https://artifactregistry.googleapis.com`, and
    `https://artifactregistry.mtls.googleapis.com`.
-   **Multi-Region `.rep.mtls` `NXDOMAIN` Pitfall**: Google Cloud does **not**
    publish DNS records for `aiplatform.us.rep.mtls.googleapis.com` or
    `aiplatform.eu.rep.mtls.googleapis.com`. On older `google-genai` SDK versions
    with `AGENT_IDENTITY` enabled and `location="us"` or `"eu"`, automatic mTLS
    URL rewriting fails with `NXDOMAIN` (`Name or service not known`). Fix:
    upgrade `google-genai`, target `global` or a single region, or set
    `GOOGLE_API_USE_MTLS_ENDPOINT=never` and `GOOGLE_API_USE_CLIENT_CERTIFICATE=false`.

#### Creating Consolidated Service via gcloud

```bash
gcloud agent-registry services create googleapis \
    --project=$PROJECT_ID --location=$LOCATION \
    --display-name="Google APIs" \
    --endpoint-spec-type=no-spec \
    --interfaces=url=https://agentregistry.googleapis.com,protocolBinding=JSONRPC \
    --interfaces=url=https://aiplatform.googleapis.com,protocolBinding=JSONRPC \
    --interfaces=url=https://aiplatform.mtls.googleapis.com,protocolBinding=JSONRPC \
    --interfaces=url=https://cloudresourcemanager.mtls.googleapis.com,protocolBinding=JSONRPC \
    --interfaces=url=https://iamcredentials.mtls.googleapis.com,protocolBinding=JSONRPC \
    --interfaces=url=https://telemetry.mtls.googleapis.com,protocolBinding=JSONRPC \
    --interfaces=url=https://cloudtrace.mtls.googleapis.com,protocolBinding=JSONRPC \
    --interfaces=url=https://trace.mtls.googleapis.com,protocolBinding=JSONRPC \
    --interfaces=url=https://monitoring.googleapis.com,protocolBinding=JSONRPC \
    --interfaces=url=https://$LOCATION-aiplatform.mtls.googleapis.com,protocolBinding=JSONRPC \
    --interfaces=url=https://$LOCATION-aiplatform.googleapis.com,protocolBinding=JSONRPC \
    --interfaces=url=https://aiplatform.$LOCATION.rep.googleapis.com,protocolBinding=JSONRPC
```

### Quick "is the hostname registered?" check

```bash
gcloud agent-registry services list \
  --project=$PROJECT_ID \
  --location=$LOCATION \
  --format="table(name.basename(), interfaces.url)" \
  --filter="interfaces.url:HOSTNAME_FRAGMENT"
```

Replace `HOSTNAME_FRAGMENT` with e.g. `bigquery.us-central1.rep`.

Source: hostname patterns derived from
`docs.cloud.google.com/docs/security/compliance/restrict-endpoint-usage`;
registration flow from
`docs.cloud.google.com/agent-registry/register-endpoints`.

--------------------------------------------------------------------------------

## 3. Resource Type — Agents

### Concept

> Agents: Autonomous actors that possess specific *skills*. Skills represent an
> agent's high-level capabilities and are a primary mechanism for discovery. --
> `docs.cloud.google.com/agent-registry/concepts`

Two kinds: - **A2A-compliant agents** -- implement Agent2Agent. Registry scans
their `agent-card.json` to extract skills. - **Standard REST agents** --
registered as `NO_SPEC` type when no A2A spec exists.

Automatic registration sources: Agent Runtime (via SDK), Google Workspace
built-ins, Gemini Enterprise built-ins, GKE deployments with the Agent Registry
functional-type annotation. Everything else is manual.

### List

```bash
gcloud agent-registry agents list \
  --project=PROJECT_ID \
  --location=REGION
```

Filter:

```bash
gcloud agent-registry agents list \
  --project=PROJECT_ID \
  --location=REGION \
  --filter="displayName='DISPLAY_NAME'"
```

### Describe

```bash
gcloud agent-registry agents describe AGENT_NAME \
  --project=PROJECT_ID \
  --location=REGION
```

Output exposes core details, skills (if A2A), and `Resource URI` -- the runtime
location of the agent, which is what gets embedded in the agent principal for
IAM.

### Update (via `services`, not `agents`)

Display name / description:

```bash
gcloud agent-registry services update AGENT_NAME \
  --project=PROJECT_ID \
  --location=REGION \
  --display-name="New name" \
  --description="Updated description"
```

Endpoint URL:

```bash
gcloud agent-registry services update AGENT_NAME \
  --project=PROJECT_ID \
  --location=REGION \
  --interfaces=url=ENDPOINT_URL,protocolBinding=PROTOCOL
```

Valid `protocolBinding`: `HTTP_JSON`, `GRPC`, `JSONRPC`.

Agent spec payload (max size 10 KB to satisfy gRPC control plane metadata header
limits):

```bash
gcloud agent-registry services update AGENT_NAME \
  --project=PROJECT_ID \
  --location=REGION \
  --agent-spec-content=agent-card.json
```

### Delete

For automatically registered agents: delete from the source runtime. For manually
registered agents:

```bash
gcloud agent-registry services delete AGENT_NAME \
  --project=PROJECT_ID \
  --location=REGION
```

### IAM model for agents

-   **Registry permission to manage**: `roles/agentregistry.editor` on the project.
-   **Agent-to-agent egress (Policy V1)**: extract the generated `Agent` UUID
    (`basename` of `registryResource`) and bind `roles/iap.egressor` with
    **`--resource-type=agent-registry`**:

    ```bash
    AGENT_UUID=$(basename "$(gcloud agent-registry services describe AGENT_NAME \
      --project=PROJECT_ID --location=REGION --format='value(registryResource)')")
    gcloud iap web set-iam-policy agents-iap-policy.json \
      --project=PROJECT_ID \
      --resource-type=agent-registry \
      --agent="$AGENT_UUID" \
      --region=REGION
    ```

    The policy's `members` uses the calling agent's principal (`principal://agents.global.org-123456789012.system.id.goog/resources/aiplatform/projects/9876543210/locations/us-central1/reasoningEngines/12345`, orgless `agents.global.proj-9876543210.system.id.goog/...`, or WIF `principal://iam.googleapis.com/...`).

### Common pitfalls

-   **Agent in another project missing from central registry**: automatic
    registration only discovers workloads inside the governance project. Manually
    register cross-project agents with `gcloud agent-registry services create` in
    the governance project (never in `us` or `eu`).
-   **Agent appears in `services list` but not `agents list`**: wrong spec type at
    creation (`--agent-spec-type=a2a-agent-card` or `--agent-spec-type=no-spec`
    required).
-   **Cloud Run agent missing from registry**: standard Cloud Run services do not
    auto-register unless deployed with `gcloud beta run deploy --functional-type=agent
    --identity-type=agent-identity`.
-   **Gemini Enterprise egress ignores Agent Gateway**: Gemini Enterprise requires
    **two** toggles — (1) `PATCH` the `Engine` on the regional endpoint
    (`https://{global-|us-|eu-}discoveryengine.googleapis.com/v1/projects/PROJECT_NUMBER/locations/GE_LOCATION/collections/default_collection/engines/ENGINE_ID?updateMask=agentGatewaySetting.defaultEgressAgentGateway.name`)
    and (2) set `"use_agent_gateway_egress": true` on each imported MCP/A2A
    `DataConnector` (see BKI #37).
-   **A2A agent missing skills**: `agent-card.json` exceeds 10 KB, or `--interfaces`
    was passed alongside `--agent-spec-type=a2a-agent-card` (forbidden).

Sources: `docs.cloud.google.com/agent-registry/manage-agents`,
`docs.cloud.google.com/agent-registry/register-agents`,
`docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/configure-iam-policies`.

--------------------------------------------------------------------------------

## 4. Resource Type — MCP Servers

### Concept

> MCP servers: Providers of standardized data resources and *tools*. Tools are
> deterministic functions exposed by an MCP server that agents can invoke to
> perform specific actions. -- `docs.cloud.google.com/agent-registry/concepts`

Official Google and Google Cloud remote MCP servers are auto-registered on API
enable. External / custom MCP servers (e.g. Cloud Run-hosted FastMCP) need
manual registration with a tool spec.

### Register

```bash
gcloud agent-registry services create SERVER_NAME \
  --project=PROJECT_ID \
  --location=REGION \
  --display-name="DISPLAY_NAME" \
  --mcp-server-spec-type=tool-spec \
  --mcp-server-spec-content=toolspec.json \
  --interfaces=url=SERVER_URL,protocolBinding=JSONRPC
```

-   `protocolBinding` for MCP must be `JSONRPC` (`jsonrpc`), and `toolspec.json`
    must be `<= 10 KB` (do **not** prefix the path with `@`). Use
    `--mcp-server-spec-type=no-spec` (without `--mcp-server-spec-content`) when
    not uploading a static tool catalog.

### List & Describe

```bash
gcloud agent-registry mcp-servers list --project=PROJECT_ID --location=REGION
gcloud agent-registry mcp-servers describe MCP_SERVER_UUID --project=PROJECT_ID --location=REGION
```

### Update tool spec & Delete

```bash
gcloud agent-registry services update SERVER_NAME \
  --project=PROJECT_ID --location=REGION \
  --mcp-server-spec-content=toolspec.json

gcloud agent-registry services delete SERVER_NAME --project=PROJECT_ID --location=REGION
```

### IAM model for MCP servers

-   **Discover / manage catalog**: `roles/agentregistry.viewer` / `roles/agentregistry.editor`.
-   **Call Agent Registry remote MCP server**: `roles/mcp.toolUser` + `roles/agentregistry.viewer`.
-   **Agent-to-MCP egress (Policy V1)**: pass `--resource-type=agent-registry`
    and the server-generated `McpServer` UUID (`registryResource` basename):

    ```bash
    gcloud iap web set-iam-policy agents-iap-policy.json \
      --project=PROJECT_ID \
      --resource-type=agent-registry \
      --mcp-server=MCP_SERVER_UUID \
      --region=REGION
    ```

    Policy V1 CEL attributes: `iap.googleapis.com/mcp.toolName`,
    `iap.googleapis.com/mcp.tool.isReadOnly`, `iap.googleapis.com/request.auth.type` (`'MCP'`).

### Common pitfalls

-   **Google/Google Cloud remote MCP server returns `NOT_FOUND` in a region**:
    auto-registered Google remote MCP servers exist **only in `global`** (even
    when exposing regional `.rep.googleapis.com/mcp` URLs). Always query with
    `--location=global` and bind IAP policies with `--region=global`.
-   **Cloud Run MCP server `403` unregistered mismatch (`.a.run.app` vs. `.run.app`)**:
    `gcloud beta run deploy --functional-type=mcp-server` registers
    `https://<SERVICE>-<PROJECT_NUMBER>.<REGION>.run.app`. Configure the agent to
    call that exact `.run.app` URL (not the legacy `*-uc.a.run.app` URL).
-   **Native MCP `AuthzPolicy` blocks `initialize` / `ping`**: when attaching a
    Network Security `AuthzPolicy` with `mcp` tool rules, set
    `baseProtocolMethodsOption: MATCH_BASE_PROTOCOL_METHODS` on `ALLOW` rules
    (see `references/policies.md` and BKI #39).
-   **Tool spec rejected or stale**: re-run `services update
    --mcp-server-spec-content=toolspec.json` (`<= 10 KB`, no `@`) after tool
    changes; never register manually in `us` or `eu`.

Sources: `docs.cloud.google.com/agent-registry/register-mcp-servers`,
`docs.cloud.google.com/agent-registry/manage-mcp-tools`,
`docs.cloud.google.com/agent-registry/use-agentregistry-mcp`,
`docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/configure-iam-policies`.

--------------------------------------------------------------------------------

## 5. Resource Type — Endpoints

### Concept

> Endpoints: Target URLs, typically REST APIs, accessed by an agent. By
> abstracting these destinations into manageable resources, Agent Registry lets
> you centrally govern which external services your agents can access. --
> `docs.cloud.google.com/agent-registry/concepts`

Endpoints are how you authorize an agent to reach **anything that isn't an agent
or an MCP server**: Google APIs (BigQuery, Agent Runtime, etc.), third-party
REST APIs, internal HTTP services. Always manually registered.

### Register

```bash
gcloud agent-registry services create SERVICE_NAME \
  --project=PROJECT_ID \
  --location=REGION \
  --display-name="DISPLAY_NAME" \
  --endpoint-spec-type=no-spec \
  --interfaces=url=ENDPOINT_URL,protocolBinding=PROTOCOL
```

-   `--endpoint-spec-type=no-spec` is mandatory -- this is what causes the
    read-only `Endpoint` projection to appear.
-   After creation, Agent Registry auto-generates the read-only `Endpoint`
    resource that agents discover.

> **Hostname registration is exact-match.** You must register *every* hostname
> variant the agent might dial. See "Hostname Matrix" in section 2. The fix for
> "endpoint registered but traffic denied" is almost always: register the
> missing variant.

### List

```bash
gcloud agent-registry endpoints list \
  --project=PROJECT_ID \
  --location=REGION
```

Filter:

```bash
gcloud agent-registry endpoints list \
  --project=PROJECT_ID \
  --location=REGION \
  --filter="displayName='NAME'"
```

For URL-substring search, list `services` instead and filter on
`interfaces.url`:

```bash
gcloud agent-registry services list \
  --project=PROJECT_ID \
  --location=REGION \
  --format="table(name.basename(), interfaces.url, interfaces.protocolBinding)" \
  --filter="interfaces.url:HOSTNAME_FRAGMENT"
```

### Describe

```bash
gcloud agent-registry endpoints describe ENDPOINT_NAME \
  --project=PROJECT_ID \
  --location=REGION
```

### Update

```bash
gcloud agent-registry services update SERVICE_NAME \
  --project=PROJECT_ID \
  --location=REGION \
  --interfaces=url=ENDPOINT_URL,protocolBinding=PROTOCOL
```

### Delete

```bash
gcloud agent-registry services delete SERVICE_NAME \
  --project=PROJECT_ID \
  --location=REGION
```

> "This action immediately removes the endpoint from discovery search results."
> Google Cloud console UI requires typing `DELETE` to confirm.

### IAM model for endpoints

-   **Discover endpoints**: `roles/agentregistry.viewer`.
-   **Register / update / delete**: `roles/agentregistry.editor`.
-   **Agent-to-endpoint traffic**: bind `roles/iap.egressor` to the source
    agent's principal on the endpoint resource:

    ```bash
    gcloud iap web set-iam-policy agents-iap-policy.json \
      --project=PROJECT_ID \
      --resource-type=agent-registry \
      --endpoint=ENDPOINT_UUID \
      --region=REGION
    ```

    Per-endpoint policy bindings do not require a CEL condition; you can omit
    `condition` to grant unconditional egress to that one endpoint, or add a CEL
    condition for attribute-based scoping (e.g. by `Name`, `ReadOnly`,
    `Destructive`, `Idempotent`, `OpenWorld` properties).

### Note on `roles/iap.tunnelResourceAccessor`

Some IAP-protected resources use `roles/iap.tunnelResourceAccessor`
(`iap.tunnelDestGroups.accessViaIAP`, `iap.tunnelInstances.accessViaIAP`) --
that role governs **classic IAP TCP tunnels** to GCE instances and dest groups.
**Agent Gateway egress to Agent Registry resources does NOT use this role**; it
uses `roles/iap.egressor` (`iap.webServiceVersions.egressViaIAP`). If you see a
tutorial suggesting `tunnelResourceAccessor` for agent egress, it's the wrong
role -- confirm against `docs.cloud.google.com/iam/docs/roles-permissions/iap`.

### Common pitfalls

-   **`Test connection` fails in Google Cloud console for a private URL**:
    expected. The Google Cloud console connection test only validates *public*
    URLs; it does not support private endpoints (Agent Runtime, internal HTTPS,
    etc.).
-   **Agent gets denied on a Google API call**: the API has a hostname variant
    you didn't register (commonly the REP regional form
    `${id}.${LOCATION}.rep.googleapis.com`).
-   **Endpoint registered in `global` but agent calls a regional URL**: registry
    location doesn't have to match the destination URL location, but the IAM
    binding's `--region` must match where the resource is registered. Check that
    `--region=` on `gcloud iap web set-iam-policy` equals the location used at
    creation.
-   **Endpoint not appearing in `endpoints list`**: created with the wrong spec
    type. Must use `--endpoint-spec-type=no-spec`.

Sources: `docs.cloud.google.com/agent-registry/register-endpoints`,
`docs.cloud.google.com/agent-registry/manage-endpoints`,
`docs.cloud.google.com/iam/docs/roles-permissions/iap`,
`docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/configure-iam-policies`.

--------------------------------------------------------------------------------

## 6. IAM Scope: Registry-Wide vs Per-Resource

There are two layers. Don't conflate them.

### Layer A — Agent Registry permissions (manage the catalog)

Project-scoped, granted via standard IAM:

| Role                         | Use                                          |
| ---------------------------- | -------------------------------------------- |
| `roles/agentregistry.viewer` | List / describe / search agents, MCP,        |
:                              : endpoints                                    :
| `roles/agentregistry.editor` | Create / update / delete `Service` resources |
| `roles/mcp.toolUser`         | Call tools via the Agent Registry remote MCP |
:                              : server (`mcp.tools.call`)                    :

These let humans and CI register and inspect entries. They do **not** grant
runtime traffic.

### Layer B — Traffic Authorization (Legacy v1 vs. UAP Policy V2)

Depending on the gateway's `iapPolicyVersion` setting, registry resources
authorize traffic through one of two mechanisms:

#### Mechanism B1: Unified Access Policy (UAP / Policy V2)

When the attached IAP Authz Extension specifies `iapPolicyVersion: "V2"`,
policies are decoupled from individual registry resources:

-   `AccessPolicy` and `PolicyBinding` (`iam.googleapis.com/v3`) attach to the
    Resource Manager hierarchy (Organization, Folder, Project) targeting numeric
    resource URIs (e.g.
    `//cloudresourcemanager.googleapis.com/projects/${PROJECT_NUMBER}`).
-   Rules grant FQDN permission `iap.googleapis.com/resources.egressViaIAP`.
-   Agent Registry entries dynamically populate the
    `destination.agent_registry.*` CEL attributes evaluated at runtime:
    -   `destination.is_registered` (boolean): `true` if target matches a
        registry service.
    -   `destination.agent_registry.resource_type`: `'ENDPOINT'`,
        `'MCP_SERVER'`, `'AGENT'`, `'SKILL'`.
    -   `destination.agent_registry.location`: region of registry resource.
    -   `destination.agent_registry.mcp_server.name`: full MCP server resource
        name.
    -   `destination.agent_registry.mcp_server.method`: `'tools'`, `'prompts'`,
        `'resources'`.
    -   `destination.agent_registry.mcp_server.tool.name`: specific tool name
        (e.g. `'updateTicket'`).
    -   `destination.agent_registry.mcp_server.tool.annotations.read_only_hint`:
        boolean.
-   **Mandatory CEL Guard**: Always guard tool annotations with:
    `(destination.agent_registry.mcp_server.method == 'tools') &&
    (destination.agent_registry.mcp_server.tool.annotations.read_only_hint ==
    true)`.

#### Mechanism B2: Legacy IAM v1 (Per-Resource Bindings)

In legacy v1, permissions are bound directly on Agent Registry resources via
`gcloud iap web set-iam-policy`. The role is always `roles/iap.egressor`. The
scope of the binding determines which target resources the source agent can
reach:

| Scope | Required `gcloud iap web` Target Flags | Grants Egress To |
| :--- | :--- | :--- |
| Registry-wide | `--resource-type=agent-registry` | All agents, MCP servers, and endpoints in that project/region registry |
| Single agent | `--resource-type=agent-registry --agent=AGENT_UUID` | One target agent (`registryResource` basename) |
| Single MCP server | `--resource-type=agent-registry --mcp-server=MCP_SERVER_UUID` | One target MCP server (`registryResource` basename) |
| Single endpoint | `--resource-type=agent-registry --endpoint=ENDPOINT_UUID` | One target endpoint (`registryResource` basename) |

All four require `--project=PROJECT_ID` and `--region=LOCATION` (`global` or
region). **Never omit `--resource-type=agent-registry`**: when `--region` is set
without `--resource-type`, `gcloud iap web` targets `IAPWebLocation`
(`projects/PROJECT_NUMBER/locations/LOCATION/iap_web`) and **silently ignores
`--agent`, `--mcp-server`, and `--endpoint`** (mutating the regional `iap_web`
container policy or failing on `--region=global`); when both `--resource-type`
and `--region` are omitted, it targets project-wide `IAPWeb`
(`projects/PROJECT_NUMBER/iap_web`).

> **Warning:** **Top-Level `{"bindings": [...]}` Required for `gcloud iap web set-iam-policy`**:
> `gcloud iap web set-iam-policy` parses the file directly as an IAM `Policy`
> object (`bindings`, `etag`, `version`) and wraps `SetIamPolicyRequest`
> internally. Do **NOT** wrap `"bindings"` inside `"policy": { ... }` when using
> `gcloud` — `apitools` discards the outer `"policy"` key and submits an **empty
> policy that silently wipes all existing IAP IAM bindings**! (Only raw REST
> `POST ...:setIamPolicy` requests use the `{"policy": {"bindings": [...]}}`
> envelope.)

The Policy V1 JSON file for `gcloud iap web set-iam-policy` uses top-level `"bindings"`:

```json
{
  "bindings": [
    {
      "role": "roles/iap.egressor",
      "members": ["AGENT_PRINCIPAL"]
    }
  ],
  "version": 3
}
```

### Agent principal formats (`members` / `principals`)

-   **Agent Runtime / Gemini Enterprise (org-backed — `ENGINE_ID` is numeric)**:
    `principal://agents.global.org-ORGANIZATION_ID.system.id.goog/resources/aiplatform/projects/PROJECT_NUMBER/locations/REGION/reasoningEngines/ENGINE_ID`
-   **Agent Runtime (orgless project — note `proj-`, NOT `project-`)**:
    `principal://agents.global.proj-PROJECT_NUMBER.system.id.goog/resources/aiplatform/projects/PROJECT_NUMBER/locations/REGION/reasoningEngines/ENGINE_ID`
-   **Workload Identity Pool (DIY / external)**:
    `principal://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/POOL_ID/subject/SUBJECT`
-   **Project-wide Agent PrincipalSet**:
    `principalSet://agents.global.org-ORGANIZATION_ID.system.id.goog/attribute.platformContainer/aiplatform/projects/PROJECT_NUMBER`

When debugging "wrong principal" errors: the principal is built from the agent's
**resource URI**, not its display name and not its URN. View the resource URI
via `gcloud agent-registry agents describe`.

### Full IAP role reference (relevant subset)

| Role                               | Permission grants the role provides   | When to use   |
| ---------------------------------- | ------------------------------------- | ------------- |
| `roles/iap.egressor` (Beta)        | `iap.webServiceVersions.egressViaIAP` | **Agent       |
:                                    :                                       : egress        :
:                                    :                                       : through Agent :
:                                    :                                       : Gateway**     :
| `roles/iap.httpsResourceAccessor`  | `iap.webServiceVersions.accessViaIAP` | Human/service |
:                                    :                                       : ingress to an :
:                                    :                                       : IAP-protected :
:                                    :                                       : web app       :
| `roles/iap.tunnelResourceAccessor` | `iap.tunnelDestGroups.accessViaIAP`,  | Classic IAP   |
:                                    : `iap.tunnelInstances.accessViaIAP`    : TCP tunnels   :
:                                    :                                       : to GCE --     :
:                                    :                                       : **not** for   :
:                                    :                                       : agent gateway :
| `roles/iap.admin`                  | Full IAP admin (`iap.tunnel.*`, all   | Manage IAP    |
:                                    : getIam/setIam)                        : policies      :
| `roles/iap.viewer`                 | Read IAP settings                     | Audit         |

Source: `docs.cloud.google.com/iam/docs/roles-permissions/iap`.

--------------------------------------------------------------------------------

## 7. Common Registration Errors and Where to Look

| Symptom                            | Likely cause                     | Where to check                       |
| ---------------------------------- | -------------------------------- | ------------------------------------ |
| `services create` fails: "manual   | Used `--location=us` or          | Switch to a region (e.g.             |
: registration not supported"        : `--location=eu` (multi-regions)  : `us-central1`) or `global`           :
| `services create` succeeds but     | Wrong `*-spec-type`.             | Re-create with the correct           |
: resource missing from `endpoints   : `--endpoint-spec-type=no-spec`   : spec-type, or check `services list`  :
: list`                              : produces an `Endpoint`.          :                                      :
| `services update                   | Spec > 10 KB                     | Trim the tool spec                   |
: --mcp-server-spec-content` rejects :                                  :                                      :
: file                               :                                  :                                      :
| Agent calls API X, IAP returns 403 | Hostname variant not registered  | `services list                       |
:                                    : (commonly REP                    : --filter="interfaces.url\:FRAGMENT"` :
:                                    : `*.LOCATION.rep.googleapis.com`) :                                      :
| Agent calls API X, IAP returns 403 even though hostname is registered | Missing `roles/iap.egressor` binding for the source agent's principal | `gcloud iap web get-iam-policy --project=P --region=L --resource-type=agent-registry [--endpoint=UUID \| --mcp-server=UUID \| --agent=UUID]` |
| MCP tool call succeeds for one tool, denied for another | IAP policy condition restricts `mcp.toolName` or `mcp.tool.isReadOnly` | Inspect the IAP policy on the MCP server resource |
| Auto-registered Agent Runtime agent missing from registry | Agent deployed via custom code, not Agent Runtime SDK | Re-deploy via Agent Runtime, or register manually as a `Service` |
| A2A agent has no skills in registry | `agent-card.json` unreachable from Google's crawler or `> 10 KB` | Curl the Agent Card URL from a public network; verify content type, schema, and `<= 10 KB` size |
| Agent principal mismatch in IAP policy | Principal built from wrong resource URI / project number / `project-` typo instead of `proj-` | `gcloud agent-registry agents describe` → use Resource URI and numeric `PROJECT_NUMBER` |
| `roles/iap.tunnelResourceAccessor` granted, still denied | Wrong role — agent egress requires `roles/iap.egressor` | Replace the binding with `roles/iap.egressor` |
| Endpoint Google Cloud console "Test connection" fails on private URL | Connection test only works for public URLs (by design) | Test via the agent itself or `curl` from a peered network |
| `agents-iap-policy.json` set, still denied | Wrong `--region` flag on `set-iam-policy`, omitted `--resource-type=agent-registry` (wrote to `IAPWebLocation` `iap_web`), or wrapped JSON in `{"policy": ...}` (wiped bindings) | Pass `--resource-type=agent-registry`, match `--region` (`global` for Google remote MCPs), and use top-level `{"bindings": [...]}` |
| Cannot find URN or child UUID | Run `services describe` for `registryResource` UUID; `mcp-servers`/`agents describe` for URN | See Section 1 URN & UUID rules |
| `agent-gateways import`: `Config validation failed` (`missing permissions: agentregistry.agents.list`) | `agentregistry.googleapis.com` API disabled on registry project, or caller lacks `roles/agentregistry.viewer` | Enable `agentregistry.googleapis.com` and grant `roles/agentregistry.viewer` (`agentregistry.{agents,endpoints,mcpServers}.list`) |
| `agent-gateways import` `400` / `InvalidArgument` on `registries` | Two regional registries (`us-central1` + `europe-west1`), `> 2` registries, or cross-jurisdiction (`us-central1` + `eu`) | Configure max 2 registries: `global` + 1 same-region or same-jurisdiction multi-region registry |
| `NXDOMAIN` on `aiplatform.{us,eu}.rep.mtls.googleapis.com` | `.rep.mtls` DNS does not exist for `us`/`eu` multi-regions | Upgrade `google-genai`, use `global`/regional endpoint, or set `GOOGLE_API_USE_MTLS_ENDPOINT=never` |
| `gcloud iap web` returns `NOT_FOUND` or ignores `--endpoint`/`--mcp-server`/`--agent` | Omitted `--resource-type=agent-registry` (targets `IAPWebLocation` `iap_web`), passed `SERVICE_NAME` instead of UUID, or queried remote MCP in region instead of `global` | Always pass `--resource-type=agent-registry`, use `registryResource` basename, and use `--region=global` for Google remote MCPs |
| Console loading error or `gcloud` `error 13` with Workforce Identity Federation (WIF) | Preview WIF limitation on Agent Registry & Agent Gateway control planes | Authenticate with a Cloud Identity or Google Workspace account (see BKI #36) |

--------------------------------------------------------------------------------

## 8. Discovery via the Agent Registry MCP Server

The registry itself is exposed as a remote MCP server at
`agentregistry.googleapis.com`. Useful when debugging from inside an agent or
via `mcp inspector`. Tools include:

Discovery: - `search_agents`, `search_mcp_servers` -- keyword/prefix search -
`get_agent`, `get_mcp_server`, `get_endpoint` -- by resource name -
`get_service` -- read the underlying writable spec - `list_agents`,
`list_mcp_servers`, `list_endpoints`, `list_services` - `list_bindings`,
`get_binding`, `fetch_available_bindings` - `get_operation`

Administrative: - `create_service`, `update_service`, `delete_service` -
`create_binding`, `update_binding`, `delete_binding`

`tools/list` over MCP does not require auth:

```text
POST /mcp HTTP/1.1
Host: agentregistry.googleapis.com
Content-Type: application/json

{ "jsonrpc": "2.0", "method": "tools/list" }
```

Source: `docs.cloud.google.com/agent-registry/use-agentregistry-mcp`.

--------------------------------------------------------------------------------

## 9. Quick Reference — Every gcloud Subcommand

```bash
# READ
gcloud agent-registry agents      list   --project=P --location=L
gcloud agent-registry agents      describe NAME --project=P --location=L
gcloud agent-registry mcp-servers list   --project=P --location=L
gcloud agent-registry mcp-servers describe NAME --project=P --location=L
gcloud agent-registry endpoints   list   --project=P --location=L
gcloud agent-registry endpoints   describe NAME --project=P --location=L
gcloud agent-registry services    list   --project=P --location=L
gcloud agent-registry services    describe NAME --project=P --location=L
gcloud agent-registry skills      list   --project=P --location=L
gcloud agent-registry skills      describe NAME --project=P --location=L

# WRITE (always 'services'; 'endpoints' has no 'create' subcommand and there is no 'gcloud beta agent-registry')
gcloud agent-registry services create NAME \
    --project=P --location=L --display-name="..." \
    --endpoint-spec-type=no-spec \
    --interfaces=url=URL,protocolBinding=HTTP_JSON|GRPC|JSONRPC

gcloud agent-registry services create NAME \
    --project=P --location=L --display-name="..." \
    --mcp-server-spec-type=tool-spec \
    --mcp-server-spec-content=toolspec.json \
    --interfaces=url=URL,protocolBinding=JSONRPC

# A2A agent: omit --interfaces (read from agent-card.json)
gcloud agent-registry services create NAME \
    --project=P --location=L --display-name="..." \
    --agent-spec-type=a2a-agent-card \
    --agent-spec-content=agent-card.json

# Non-A2A REST agent: --agent-spec-type=no-spec + --interfaces
gcloud agent-registry services create NAME \
    --project=P --location=L --display-name="..." \
    --agent-spec-type=no-spec \
    --interfaces=url=URL,protocolBinding=HTTP_JSON

gcloud agent-registry services update NAME \
    --project=P --location=L \
    [ --display-name="..." | --description="..." \
      | --interfaces=url=URL,protocolBinding=... | --clear-interfaces \
      | --mcp-server-spec-content=toolspec.json \
      | --agent-spec-content=agent-card.json ]

gcloud agent-registry services delete NAME --project=P --location=L

# IAP Policy V1 egress bindings (--resource-type=agent-registry is ALWAYS required)
gcloud iap web set-iam-policy POLICY.json \
    --project=P --region=L --resource-type=agent-registry \
    [ --agent=AGENT_UUID | --mcp-server=MCP_SERVER_UUID | --endpoint=ENDPOINT_UUID ]

gcloud iap web get-iam-policy \
    --project=P --region=L --resource-type=agent-registry \
    [ --agent=AGENT_UUID | --mcp-server=MCP_SERVER_UUID | --endpoint=ENDPOINT_UUID ]
```

Spec size cap: **10 KB** for `--mcp-server-spec-content` and
`--agent-spec-content` (pass plain file path without `@`).

Manual registration locations: any region or `global`. **Not** `us` or `eu`.

--------------------------------------------------------------------------------

## Source Index

-   Agent Registry overview:
    <https://docs.cloud.google.com/agent-registry/overview.md.txt>
-   Agent Registry concepts:
    <https://docs.cloud.google.com/agent-registry/concepts.md.txt>
-   Register agents (manual):
    <https://docs.cloud.google.com/agent-registry/register-agents.md.txt>
-   Manage agents: <https://docs.cloud.google.com/agent-registry/manage-agents.md.txt>
-   Register MCP servers:
    <https://docs.cloud.google.com/agent-registry/register-mcp-servers.md.txt>
-   Manage MCP servers/tools:
    <https://docs.cloud.google.com/agent-registry/manage-mcp-tools.md.txt>
-   Register endpoints:
    <https://docs.cloud.google.com/agent-registry/register-endpoints.md.txt>
-   Manage endpoints:
    <https://docs.cloud.google.com/agent-registry/manage-endpoints.md.txt>
-   Agent Registry MCP server:
    <https://docs.cloud.google.com/agent-registry/use-agentregistry-mcp.md.txt>
-   Govern (Gemini Enterprise Agent Platform):
    <https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/agent-registry.md.txt>
-   IAP for agents: <https://docs.cloud.google.com/iap/docs/agent-overview.md.txt>
-   IAP IAM roles: <https://docs.cloud.google.com/iam/docs/roles-permissions/iap.md.txt>
-   Configure IAM policies (IAP egressor examples):
    <https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/configure-iam-policies.md.txt>
-   Regional service endpoint hostname formats:
    <https://docs.cloud.google.com/docs/security/compliance/restrict-endpoint-usage.md.txt>
