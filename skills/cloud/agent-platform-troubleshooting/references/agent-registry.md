# Agent Registry — Debugging Reference

Curated reference for diagnosing why agents, MCP servers, and endpoints
registered in Google Cloud Agent Registry are not accepting traffic through
Agent Gateway / IAP.

Scope: Gemini Enterprise Agent Platform — Agent Registry (Preview). All commands
use `gcloud alpha agent-registry`.

## Table of Contents

-   [TL;DR for Debugging](#tldr-for-debugging) (Lines 33-108)
-   [1. The Data Model in One Picture](#1-the-data-model-in-one-picture) (Lines
    109-153)
-   [2. Default-Deny + Hostname Matching](#2-default-deny-hostname-matching)
    (Lines 154-261)
-   [3. Resource Type — Agents](#resource-type-agents) (Lines 262-400)
-   [4. Resource Type — MCP Servers](#resource-type-mcp-servers) (Lines 401-521)
-   [5. Resource Type — Endpoints](#resource-type-endpoints) (Lines 522-663)
-   [6. IAM Scope: Registry-Wide vs Per-Resource](#6-iam-scope-registry-wide-vs-per-resource)
    (Lines 664-752)
-   [7. Common Registration Errors and Where to Look](#7-common-registration-errors-and-where-to-look)
    (Lines 753-772)
-   [8. Discovery via the Agent Registry MCP Server](#8-discovery-via-the-agent-registry-mcp-server)
    (Lines 773-801)
-   [9. Quick Reference — Every gcloud Subcommand](#quick-reference-gcloud)
    (Lines 802-860)
-   [Source Index](#source-index) (Lines 861-887)

--------------------------------------------------------------------------------

## TL;DR for Debugging

Read these first when something is broken.

1.  **Agent Registry is default-deny at the gateway.** Agent Gateway uses
    Identity-Aware Proxy (IAP) to enforce IAM allow/deny policies bound to Agent
    Registry resources. If a target hostname is not registered as a `Service`
    (and a matching `roles/iap.egressor` binding does not exist for the calling
    agent's principal), egress is blocked. Source:
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
    locations.** Use a real region (e.g. `us-central1`) or `global`. Source:
    `docs.cloud.google.com/agent-registry/register-endpoints`.

5.  **Two predefined IAM roles control the registry itself**:

    -   `roles/agentregistry.viewer` — discover (list/describe).
    -   `roles/agentregistry.editor` — register/update/delete. These are
        project-scoped registry permissions, not traffic permissions.

6.  **Traffic permissions live on IAP, bound to registry resources.** The role
    that actually permits an agent to *use* a registered service is
    `roles/iap.egressor` (`iap.webServiceVersions.egressViaIAP`), bound via
    `gcloud beta iap web set-iam-policy` with one of:
    `--resource-type=agent-registry` (registry-wide), `--agent=`,
    `--mcp-server=`, or `--endpoint=` (per-resource). Source:
    `docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/assign-identity-iam`,
    `docs.cloud.google.com/iam/docs/roles-permissions/iap`.

7.  **Identifiers matter:**

    -   `SERVICE_NAME` / `SERVICE_ID` — your chosen short ID for the registry
        entry.
    -   **Agent identifier (URN)** and **MCP server identifier (URN)** —
        globally unique, immutable. Used by discovery tools and policy bindings.
    -   **Resource URI** — the actual runtime location (Cloud Run URL, Agent
        Runtime endpoint, GKE deployment). Different from the URN. Embedded in
        the agent principal for IAM.

8.  **Specs have a hard 10 KB cap.** `--mcp-server-spec-content` and
    `--agent-spec-content` files must be <= 10 KB. Larger specs silently fail
    validation.

9.  **Automatic registration vs manual:** Agent Runtime, Google Workspace,
    Gemini Enterprise, and annotated GKE deployments register *automatically*.
    Official Google/Google Cloud remote MCP servers register automatically when
    the API is enabled. Everything else (Cloud Run, on-prem, custom REST agents,
    third-party MCP) is *manual*.

10. **First debug command** is almost always: list the resource type and confirm
    the hostname permutation you expect is actually present. `gcloud alpha
    agent-registry endpoints list --project=$PROJECT_ID --location=$LOCATION`

11. **Boundary controls visibility.** Agents are only discoverable if they are
    hosted in a project that is within the defined **Agent Management Boundary**
    of the Management Project. If an agent is missing from the list, check the
    boundary configuration.

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
-   The `*-spec-type` parameter you use at creation determines which projection
    appears:

    Flag                               | Projection becomes
    ---------------------------------- | ------------------
    `--endpoint-spec-type=no-spec`     | `Endpoint`
    `--mcp-server-spec-type=tool-spec` | `McpServer`
    `--agent-spec-type=...` (e.g. A2A) | `Agent`

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

> [!CAUTION] **MANDATORY GOOGLE APIS CONSOLIDATION RULE**: NEVER recommend or
> register separate `Service` resources for individual Google APIs (such as
> Agent Runtime, Cloud Resource Manager, IAM, or Telemetry). Do NOT register
> each Google API as a separate service entry, as separate service entries cause
> resource clutter, complicate IAM policy management, and risk hitting registry
> quota limits. ALL Google APIs MUST ALWAYS be consolidated under a single Agent
> Registry Service named `googleapis` using multiple interfaces.

Instead of registering dozens of separate `Service` resources for each Google
API and its regional/mTLS permutations, it is highly recommended to
**consolidate all Google APIs under a single Agent Registry Service** (e.g.,
named `googleapis`) using **multiple interfaces**.

This reduces resource clutter, simplifies IAM policy management (you only need
to grant `roles/iap.egressor` on one resource), and avoids hitting registry
limits.

#### Recommended Base Interfaces

For a standard agent deployment, the consolidated `googleapis` service should
define at least the following interfaces:

-   `https://agentregistry.googleapis.com`
-   `https://aiplatform.mtls.googleapis.com`
-   `https://cloudresourcemanager.mtls.googleapis.com`
-   `https://iamcredentials.mtls.googleapis.com`
-   `https://telemetry.mtls.googleapis.com`
-   `https://{region}-aiplatform.mtls.googleapis.com` (replace `{region}` with
    your deployment region, e.g., `us-central1`)
-   `https://{region}-aiplatform.googleapis.com`
-   `https://aiplatform.{region}.rep.googleapis.com`

When debugging "agent can call X but not Y", first check that the hostname Y is
using matches one of the registered URLs **exactly**. A trailing slash, port,
scheme, or extra subdomain mismatch will cause denial.

#### Creating Consolidated Service via gcloud

```bash
gcloud alpha agent-registry services create googleapis \
    --project=$PROJECT_ID --location=$LOCATION \
    --display-name="Google APIs" \
    --endpoint-spec-type=no-spec \
    --interfaces=url=https://agentregistry.googleapis.com,protocolBinding=JSONRPC \
    --interfaces=url=https://aiplatform.mtls.googleapis.com,protocolBinding=JSONRPC \
    --interfaces=url=https://cloudresourcemanager.mtls.googleapis.com,protocolBinding=JSONRPC \
    --interfaces=url=https://iamcredentials.mtls.googleapis.com,protocolBinding=JSONRPC \
    --interfaces=url=https://telemetry.mtls.googleapis.com,protocolBinding=JSONRPC \
    --interfaces=url=https://$LOCATION-aiplatform.mtls.googleapis.com,protocolBinding=JSONRPC \
    --interfaces=url=https://$LOCATION-aiplatform.googleapis.com,protocolBinding=JSONRPC \
    --interfaces=url=https://aiplatform.$LOCATION.rep.googleapis.com,protocolBinding=JSONRPC
```

### Quick "is the hostname registered?" check

```bash
gcloud alpha agent-registry services list \
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

## 3. Resource Type — Agents {#resource-type-agents}

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
gcloud alpha agent-registry agents list \
  --project=PROJECT_ID \
  --location=REGION
```

Filter:

```bash
gcloud alpha agent-registry agents list \
  --project=PROJECT_ID \
  --location=REGION \
  --filter="displayName='DISPLAY_NAME'"
```

### Describe

```bash
gcloud alpha agent-registry agents describe AGENT_NAME \
  --project=PROJECT_ID \
  --location=REGION
```

Output exposes core details, skills (if A2A), and `Resource URI` -- the runtime
location of the agent, which is what gets embedded in the agent principal for
IAM.

### Update (via `services`, not `agents`)

Display name / description:

```bash
gcloud alpha agent-registry services update AGENT_NAME \
  --project=PROJECT_ID \
  --location=REGION \
  --display-name="New name" \
  --description="Updated description"
```

Endpoint URL:

```bash
gcloud alpha agent-registry services update AGENT_NAME \
  --project=PROJECT_ID \
  --location=REGION \
  --interfaces=url=ENDPOINT_URL,protocolBinding=PROTOCOL
```

Valid `protocolBinding`: `HTTP_JSON`, `GRPC`, `JSONRPC`.

Agent spec payload (max size 10 KB to satisfy gRPC control plane metadata header
limits):

```bash
gcloud alpha agent-registry services update AGENT_NAME \
  --project=PROJECT_ID \
  --location=REGION \
  --agent-spec-content=@AGENT_SPEC
```

### Delete

For automatically registered agents: delete from the source runtime -- registry
entry follows. For manually registered agents:

```bash
gcloud alpha agent-registry services delete AGENT_NAME \
  --project=PROJECT_ID \
  --location=REGION
```

> "This action removes the agent from search results and makes it undiscoverable
> to other tools."

### IAM model for agents

-   **Registry permission to manage**: `roles/agentregistry.editor` on the
    project.
-   **Traffic permission for an agent to talk to *this* agent (agent-to-agent
    egress)**: bind `roles/iap.egressor` to the *source* agent's principal on
    the *target* agent resource:

    ```bash
    gcloud beta iap web set-iam-policy agents-iap-policy.json \
      --project=PROJECT_ID \
      --agent=AGENT_ID \
      --region=REGION
    ```

    The policy file's `members` is the source agent's principal:

    -   Agent Runtime / Gemini Enterprise:
        `principal://TRUST_DOMAIN/AGENT_UNIQUE_IDENTIFIER` (e.g.
        `principal://agents.global.org-123456789012.system.id.goog/resources/aiplatform/projects/9876543210/locations/us-central1/reasoningEngines/my-test-agent`)
    -   DIY agents:
        `principal://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/AGENT_SERVICE_ACCOUNT_IDENTIFIER`

### Common pitfalls

-   **Agent registered but not discoverable**:
    *   Check you're querying the right project + location. Manual registration
        is rejected in `us`/`eu` multi-regions.
    *   Verify the agent's hosting project is within the **Agent Management
        Boundary** of the Management Project. If it is outside the boundary, the
        registry will not expose it. Check/update via `gcloud agent-registry
        boundary update`.
-   **Agent appears in `services list` but not `agents list`**: wrong
    `*-spec-type` at creation time. The projection only appears for the matching
    spec type.
-   **Agent "registered" in Agent Runtime but missing from registry**: automatic
    registration only happens for Agent Runtime SDK-deployed agents. A custom
    Cloud Run agent does **not** auto-register.
-   **A2A agent missing skills**: registry couldn't reach the agent's
    `agent-card.json` endpoint. Check the agent's published Agent Card URL is
    publicly reachable from Google's registration crawler.

Sources: `docs.cloud.google.com/agent-registry/manage-agents`,
`docs.cloud.google.com/agent-registry/register-agents`,
`docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/assign-identity-iam`.

--------------------------------------------------------------------------------

## 4. Resource Type — MCP Servers {#resource-type-mcp-servers}

### Concept

> MCP servers: Providers of standardized data resources and *tools*. Tools are
> deterministic functions exposed by an MCP server that agents can invoke to
> perform specific actions. -- `docs.cloud.google.com/agent-registry/concepts`

Official Google and Google Cloud remote MCP servers are auto-registered on API
enable. External / custom MCP servers (e.g. Cloud Run-hosted FastMCP) need
manual registration with a tool spec.

### Register

```bash
gcloud alpha agent-registry services create SERVER_NAME \
  --project=PROJECT_ID \
  --location=REGION \
  --display-name="DISPLAY_NAME" \
  --mcp-server-spec-type=tool-spec \
  --mcp-server-spec-content=@toolspec.json \
  --interfaces=url=SERVER_URL,protocolBinding=PROTOCOL
```

-   `PROTOCOL` for MCP is typically `JSONRPC`.
-   `toolspec.json` must be <= **10 KB**, conform to the MCP tool schema (name,
    description, optional annotations).

### List

```bash
gcloud alpha agent-registry mcp-servers list \
  --project=PROJECT_ID \
  --location=REGION
```

Useful filters: - `displayName='NAME'` - `mcpServerId='urn:mcp:SERVER_URN'`
(filter by URN -- see URN format in section 1)

### Describe

```bash
gcloud alpha agent-registry mcp-servers describe SERVER_NAME \
  --project=PROJECT_ID \
  --location=REGION
```

The describe output includes the tool catalog and an ADK code snippet to wire
the server into an agent.

### Update tool spec

Tool spec changes are not auto-detected -- re-upload when the server
adds/changes tools:

```bash
gcloud alpha agent-registry services update SERVER_NAME \
  --project=PROJECT_ID \
  --location=REGION \
  --mcp-server-spec-content=@TOOL_SPEC
```

### Delete

```bash
gcloud alpha agent-registry services delete SERVER_NAME \
  --project=PROJECT_ID \
  --location=REGION
```

### IAM model for MCP servers

-   **Discover MCP servers/tools**: `roles/agentregistry.viewer`.
-   **Update tool definitions / register**: `roles/agentregistry.editor`.
-   **Use the Agent Registry remote MCP server itself**: `roles/mcp.toolUser`
    for `mcp.tools.call`, plus the viewer role for discovery.
-   **Agent-to-MCP egress** (the actual traffic permission): bind
    `roles/iap.egressor` to the source agent's principal on the MCP server
    resource:

    ```bash
    gcloud beta iap web set-iam-policy agents-iap-policy.json \
      --project=PROJECT_ID \
      --mcp-server=MCP_SERVER_ID \
      --region=REGION
    ```

    CEL conditions can scope the binding to specific tools and to read-only or
    non-destructive calls. Documented condition attributes include:

    -   `iap.googleapis.com/mcp.toolName`
    -   `iap.googleapis.com/mcp.tool.isReadOnly`
    -   `iap.googleapis.com/request.auth.type` (e.g. `'MCP'`)

    Example condition expression:
    `api.getAttribute('iap.googleapis.com/mcp.toolName', '') == 'GitHubTool' &&
    api.getAttribute('iap.googleapis.com/mcp.tool.isReadOnly', false) == true &&
    api.getAttribute('iap.googleapis.com/request.auth.type', '') == 'MCP'`

### Common pitfalls

-   **Agent calls a tool, gets denied**: the IAP policy condition may restrict
    to `isReadOnly == true` while the tool is destructive, or `mcp.toolName`
    doesn't match.
-   **Tool added to MCP server but agents can't see it**: tool spec wasn't
    re-uploaded. `services update --mcp-server-spec-content` is mandatory after
    every server-side change.
-   **Spec upload silently rejected**: file > 10 KB.
-   **Manual registration error in `us` / `eu`**: not supported. Use a region or
    `global`.
-   **MCP server registered but appears under `services list` only, not
    `mcp-servers list`**: wrong spec type -- must be
    `--mcp-server-spec-type=tool-spec`.

Sources: `docs.cloud.google.com/agent-registry/register-mcp-servers`,
`docs.cloud.google.com/agent-registry/manage-mcp-tools`,
`docs.cloud.google.com/agent-registry/use-agentregistry-mcp`,
`docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/assign-identity-iam`.

--------------------------------------------------------------------------------

## 5. Resource Type — Endpoints {#resource-type-endpoints}

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
gcloud alpha agent-registry services create SERVICE_NAME \
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
gcloud alpha agent-registry endpoints list \
  --project=PROJECT_ID \
  --location=REGION
```

Filter:

```bash
gcloud alpha agent-registry endpoints list \
  --project=PROJECT_ID \
  --location=REGION \
  --filter="displayName='NAME'"
```

For URL-substring search, list `services` instead and filter on
`interfaces.url`:

```bash
gcloud alpha agent-registry services list \
  --project=PROJECT_ID \
  --location=REGION \
  --format="table(name.basename(), interfaces.url, interfaces.protocolBinding)" \
  --filter="interfaces.url:HOSTNAME_FRAGMENT"
```

### Describe

```bash
gcloud alpha agent-registry endpoints describe ENDPOINT_NAME \
  --project=PROJECT_ID \
  --location=REGION
```

### Update

```bash
gcloud alpha agent-registry services update SERVICE_NAME \
  --project=PROJECT_ID \
  --location=REGION \
  --interfaces=url=ENDPOINT_URL,protocolBinding=PROTOCOL
```

### Delete

```bash
gcloud alpha agent-registry services delete SERVICE_NAME \
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
    gcloud beta iap web set-iam-policy agents-iap-policy.json \
      --project=PROJECT_ID \
      --endpoint=ENDPOINT_ID \
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
    `--region=` on `gcloud beta iap web set-iam-policy` equals the location used
    at creation.
-   **Endpoint not appearing in `endpoints list`**: created with the wrong spec
    type. Must use `--endpoint-spec-type=no-spec`.

Sources: `docs.cloud.google.com/agent-registry/register-endpoints`,
`docs.cloud.google.com/agent-registry/manage-endpoints`,
`docs.cloud.google.com/iam/docs/roles-permissions/iap`,
`docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/assign-identity-iam`.

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

### Layer B — IAP egress permissions (let an agent actually send traffic)

Bound on Agent Registry resources via `gcloud beta iap web set-iam-policy`. The
role is always `roles/iap.egressor`. The scope of the binding determines which
target resources the source agent can reach:

| Scope             | gcloud target flag               | Grants egress to      |
| ----------------- | -------------------------------- | --------------------- |
| Registry-wide     | `--resource-type=agent-registry` | All agents + MCP      |
:                   :                                  : servers + endpoints   :
:                   :                                  : in the project's      :
:                   :                                  : registry              :
| Single agent      | `--agent=AGENT_ID`               | One target agent      |
| Single MCP server | `--mcp-server=MCP_SERVER_ID`     | One target MCP server |
| Single endpoint   | `--endpoint=ENDPOINT_ID`         | One target endpoint   |

All four take `--project=PROJECT_ID` and `--region=REGION` (or `--folder` /
`--organization` for higher-scoped binding).

The policy JSON is uniform:

```json
{
  "policy": {
    "bindings": [
      {
        "role": "roles/iap.egressor",
        "members": ["AGENT_PRINCIPAL"],
        "condition": { "title": "...", "expression": "..." }
      }
    ]
  }
}
```

Source:
`docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/assign-identity-iam`.

### Agent principal formats (the `members` value)

-   **Agent Runtime / Gemini Enterprise**:
    `principal://TRUST_DOMAIN/AGENT_UNIQUE_IDENTIFIER` Example:
    `principal://agents.global.org-123456789012.system.id.goog/resources/aiplatform/projects/9876543210/locations/us-central1/reasoningEngines/my-test-agent`

-   **DIY agents (Cloud Run, GKE, on-prem)**:
    `principal://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/AGENT_SERVICE_ACCOUNT_IDENTIFIER`
    Example:
    `principal://iam.googleapis.com/projects/1234567890/locations/global/workloadIdentityPools/my-agent-identity/subject/ns/default/sa/my-agent`

-   **Agent hierarchy (whole platform container)**:
    `principalSet://agents.global.org-ORGANIZATION_ID.system.id.goog/attribute.platformContainer/aiplatform/projects/1234`

When debugging "wrong principal" errors: the principal is built from the agent's
**resource URI**, not its display name and not its URN. View the resource URI
via `gcloud alpha agent-registry agents describe`.

### Full IAP role reference (relevant subset)

Role                               | Permission grants the role provides                                     | When to use
---------------------------------- | ----------------------------------------------------------------------- | -----------
`roles/iap.egressor` (Beta)        | `iap.webServiceVersions.egressViaIAP`                                   | **Agent egress through Agent Gateway**
`roles/iap.httpsResourceAccessor`  | `iap.webServiceVersions.accessViaIAP`                                   | Human/service ingress to an IAP-protected web app
`roles/iap.tunnelResourceAccessor` | `iap.tunnelDestGroups.accessViaIAP`, `iap.tunnelInstances.accessViaIAP` | Classic IAP TCP tunnels to GCE -- **not** for agent gateway
`roles/iap.admin`                  | Full IAP admin (`iap.tunnel.*`, all getIam/setIam)                      | Manage IAP policies
`roles/iap.viewer`                 | Read IAP settings                                                       | Audit

Source: `docs.cloud.google.com/iam/docs/roles-permissions/iap`.

--------------------------------------------------------------------------------

## 7. Common Registration Errors and Where to Look

Symptom                                                               | Likely cause                                                                                   | Where to check
--------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | --------------
`services create` fails: "manual registration not supported"          | Used `--location=us` or `--location=eu` (multi-regions)                                        | Switch to a region (e.g. `us-central1`) or `global`
`services create` succeeds but resource missing from `endpoints list` | Wrong `*-spec-type`. `--endpoint-spec-type=no-spec` produces an `Endpoint`.                    | Re-create with the correct spec-type, or check `services list`
`services update --mcp-server-spec-content` rejects file              | Spec > 10 KB                                                                                   | Trim the tool spec
Agent calls API X, IAP returns 403                                    | Hostname variant not registered (commonly REP `*.LOCATION.rep.googleapis.com`)                 | `services list --filter="interfaces.url:FRAGMENT"`
Agent calls API X, IAP returns 403 even though hostname is registered | Missing `roles/iap.egressor` binding for the source agent's principal                          | `gcloud beta iap web get-iam-policy --project= --region= --endpoint=...` (or `--mcp-server=`, `--agent=`, `--resource-type=agent-registry`)
MCP tool call succeeds for one tool, denied for another               | IAP policy condition restricts `mcp.toolName` or `mcp.tool.isReadOnly`                         | Inspect the IAP policy on the MCP server resource
Auto-registered Agent Runtime agent missing from registry             | Agent deployed via custom code, not Agent Runtime SDK                                          | Re-deploy via Agent Runtime, or register manually as a `Service`
A2A agent has no skills in registry                                   | `agent-card.json` unreachable from Google's crawler                                            | Curl the Agent Card URL from a public network; verify content type and schema
Agent principal mismatch in IAP policy                                | Principal built from wrong resource URI / project number / SA identifier                       | `gcloud alpha agent-registry agents describe` -> use Resource URI to construct
`roles/iap.tunnelResourceAccessor` granted, still denied              | Wrong role -- agent egress requires `roles/iap.egressor`                                       | Replace the binding
Endpoint Google Cloud console "Test connection" fails on private URL  | Connection test only works for public URLs (by design)                                         | Test via the agent itself or `curl` from a peered network
`agents-iap-policy.json` set, still denied                            | Wrong `--region` flag on `set-iam-policy` -- must match resource location                      | Re-issue with the correct `--region`
Cannot find URN for binding                                           | Use `mcp-servers describe` / `agents describe` and read the `name` field; format per section 1 | See URN formats in section 1

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

## 9. Quick Reference — Every gcloud Subcommand {#quick-reference-gcloud}

```bash
# READ
gcloud alpha agent-registry agents      list   --project=P --location=L
gcloud alpha agent-registry agents      describe NAME --project=P --location=L
gcloud alpha agent-registry mcp-servers list   --project=P --location=L
gcloud alpha agent-registry mcp-servers describe NAME --project=P --location=L
gcloud alpha agent-registry endpoints   list   --project=P --location=L
gcloud alpha agent-registry endpoints   describe NAME --project=P --location=L
gcloud alpha agent-registry services    list   --project=P --location=L
gcloud alpha agent-registry services    describe NAME --project=P --location=L

# WRITE  (always 'services'; the projection follows from --*-spec-type)
gcloud alpha agent-registry services create NAME \
    --project=P --location=L --display-name="..." \
    --endpoint-spec-type=no-spec \
    --interfaces=url=URL,protocolBinding=HTTP_JSON|GRPC|JSONRPC

gcloud alpha agent-registry services create NAME \
    --project=P --location=L --display-name="..." \
    --mcp-server-spec-type=tool-spec \
    --mcp-server-spec-content=@toolspec.json \
    --interfaces=url=URL,protocolBinding=JSONRPC

gcloud alpha agent-registry services create NAME \
    --project=P --location=L --display-name="..." \
    --agent-spec-content=@agent-card.json \
    --interfaces=url=URL,protocolBinding=HTTP_JSON

gcloud alpha agent-registry services update NAME \
    --project=P --location=L \
    [ --display-name="..." | --description="..." \
      | --interfaces=url=URL,protocolBinding=... \
      | --mcp-server-spec-content=@spec.json \
      | --agent-spec-content=@card.json ]

gcloud alpha agent-registry services delete NAME --project=P --location=L

# IAP egress policy bindings (separate API, separate gcloud surface)
gcloud beta iap web set-iam-policy POLICY.json \
    --project=P --region=L \
    [ --resource-type=agent-registry
    | --agent=AGENT_ID
    | --mcp-server=MCP_SERVER_ID
    | --endpoint=ENDPOINT_ID ]

gcloud beta iap web get-iam-policy \
    --project=P --region=L \
    [ same target flags ]
```

Spec size cap: **10 KB** for `--mcp-server-spec-content` and
`--agent-spec-content`.

Manual registration locations: any region or `global`. **Not** `us` or `eu`.

--------------------------------------------------------------------------------

## Source Index

-   Agent Registry overview:
    https://docs.cloud.google.com/agent-registry/overview
-   Agent Registry concepts:
    https://docs.cloud.google.com/agent-registry/concepts
-   Register agents (manual):
    https://docs.cloud.google.com/agent-registry/register-agents
-   Manage agents: https://docs.cloud.google.com/agent-registry/manage-agents
-   Register MCP servers:
    https://docs.cloud.google.com/agent-registry/register-mcp-servers
-   Manage MCP servers/tools:
    https://docs.cloud.google.com/agent-registry/manage-mcp-tools
-   Register endpoints:
    https://docs.cloud.google.com/agent-registry/register-endpoints
-   Manage endpoints:
    https://docs.cloud.google.com/agent-registry/manage-endpoints
-   Agent Registry MCP server:
    https://docs.cloud.google.com/agent-registry/use-agentregistry-mcp
-   Govern (Gemini Enterprise Agent Platform):
    https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/agent-registry
-   IAP for agents: https://docs.cloud.google.com/iap/docs/agent-overview
-   IAP IAM roles: https://docs.cloud.google.com/iam/docs/roles-permissions/iap
-   Assign identity / IAP egress policies:
    https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/assign-identity-iam
-   Regional service endpoint hostname formats:
    https://docs.cloud.google.com/docs/security/compliance/restrict-endpoint-usage
