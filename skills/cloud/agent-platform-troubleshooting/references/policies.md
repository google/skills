# Agent Platform Policies — Debugging Reference

Reference for diagnosing IAM, IAP, and Agent Gateway policy denials in the
**Google Cloud Gemini Enterprise Agent Platform**. Read this when an agent gets
a 403, when an MCP/agent/endpoint call is silently dropped, or when a freshly
applied policy "doesn't take."

Agent Gateway enforces governance across five complementary policy layers:

1.  **Network Security `AuthzPolicy` (`networksecurity.googleapis.com` `v1` / `v1beta1`)**:
    Gateway attachment and traffic-phase dispatcher supporting L7 `httpRules`
    (including native MCP method/tool matching), L4 SNI `networkRules` (`gcloud beta`),
    delegated `CUSTOM` service extensions (`REQUEST_AUTHZ` and `CONTENT_AUTHZ`),
    and `DENY_BY_DEFAULT` fallback enforcement.
2.  **IAM Unified Access Policy (UAP / Policy V2, `iam.googleapis.com/v3`) & Legacy IAM v1**:
    Agent-to-Anywhere (egress) identity and destination authorization evaluated
    by IAP (`service: iap.googleapis.com`, `iapPolicyVersion: "V2"` vs. legacy
    `"V1"` `roles/iap.egressor`).
3.  **Model Armor Content Security (`CONTENT_AUTHZ`)**: Inline prompt/response
    screening and Sensitive Data Protection (SDP) redaction across Client-to-Agent
    (ingress) and Agent-to-Anywhere (egress) flows.
4.  **Semantic Governance Policies (SGP)**: Context-aware natural-language
    constraints and user-intent alignment evaluated by the LLM in the semantic
    governance policy engine on non-streaming LLM requests.
5.  **Extensible Policies (`ExtensionBinding` / `ProducerExtension`, Preview) &
    Token Management Policies (Preview)**: Simplified 1P/2P/3P `ext_proc`
    bindings and shared LLM token quota enforcement returning HTTP `429`.

## Table of Contents

-   [TL;DR for debugging](#tldr-for-debugging): Lines 50-157
-   [1. UAP (Policy V2) vs. Legacy IAM v1 Architecture](#1-uap-policy-v2-vs-legacy-iam-v1-architecture): Lines 158-223
-   [2. UAP Core Architectural Constructs](#2-uap-core-architectural-constructs): Lines 224-310
-   [3. Runtime Evaluation Pipeline & Mathematical Invariants](#3-runtime-evaluation-pipeline--mathematical-invariants): Lines 311-378
-   [4. Deep CEL Attribute Reference](#4-deep-cel-attribute-reference): Lines 379-489
-   [5. The 3-Tier Organizational Security Model](#5-the-3-tier-organizational-security-model): Lines 490-697
-   [6. Legacy IAM v1 Reference (Backward Compatibility)](#6-legacy-iam-v1-reference-backward-compatibility): Lines 698-729
-   [7. Observability, Auditing, & Dry-Run Operations](#7-observability-auditing--dry-run-operations): Lines 730-784
-   [8. Production Edge Cases & Architectural Gotchas](#8-production-edge-cases--architectural-gotchas): Lines 785-885
-   [9. Quick Command Cheat Sheet](#9-quick-command-cheat-sheet): Lines 886-927
-   [10. Debugging Flowchart](#10-debugging-flowchart): Lines 928-962
-   [11. Network Security AuthzPolicy: L7 HTTP/MCP Rules, L4 networkRules, & DENY_BY_DEFAULT](#11-network-security-authzpolicy-l7-httpmcp-rules-l4-networkrules--deny_by_default): Lines 963-1073
-   [12. Model Armor Content Security Policies (CONTENT_AUTHZ)](#12-model-armor-content-security-policies-content_authz): Lines 1074-1102
-   [13. Semantic Governance Policies (SGP)](#13-semantic-governance-policies-sgp): Lines 1103-1173
-   [14. Extensible Policies: ExtensionBinding & ProducerExtension (Preview)](#14-extensible-policies-extensionbinding--producerextension-preview): Lines 1174-1207
-   [15. Token Management Policies (Preview — HTTP 429)](#15-token-management-policies-preview--http-429): Lines 1208-1222

--------------------------------------------------------------------------------

## TL;DR for debugging

1.  **Check Policy Architecture First (`V1` vs `V2`)**:

    -   In Gateway metadata: Check if the attached IAP `AuthzExtension` specifies
        `iapPolicyVersion: "V2"`. Without this key, the gateway defaults to
        legacy V1 shadow-resource evaluation. Active blocking is enabled by
        omitting `iamEnforcementMode` (or setting `iamEnforcementMode: "ENFORCE"`,
        never `"ENFORCED"`).
    -   In Cloud Audit Logs (`protoPayload.serviceName="iap.googleapis.com"`):
        Check `protoPayload.metadata.iapPolicyVersion`. If lowercase `"v2"`,
        diagnose UAP `AccessPolicy` and `PolicyBinding` resources. If absent or
        `"v1"`, diagnose legacy IAM v1 bindings on Agent Registry entries.

2.  **The UAP Permission MUST be FQDN**: In UAP access policy rules
    (`operation.permissions`), the permission MUST be specified in full FQDN
    format: **`iap.googleapis.com/resources.egressViaIAP`** (Agent-to-Anywhere
    egress). Using the short form `iap.resources.egressViaIAP` causes the IAM
    policy compiler to reject the policy, even though Cloud Audit Logs record
    `protoPayload.authorizationInfo.permission="iap.resources.egressViaIAP"`
    (V2) or `"iap.webServiceVersions.egressViaIAP"` (V1).

3.  **UAP Policy Bindings Target Resource Manager Nodes**: `PolicyBinding`
    targets must be canonical Resource Manager URIs using numeric IDs (e.g.
    `//cloudresourcemanager.googleapis.com/projects/${PROJECT_NUMBER}` or
    `//cloudresourcemanager.googleapis.com/folders/${FOLDER_ID}`). Passing
    gateway or registry resource names causes
    `INVALID_TARGET_FULL_RESOURCE_NAME`.

4.  **UAP Invariants: Absolute DENY Precedence & Additive ALLOW Aggregation**:

    -   **Absolute DENY Precedence**: If ANY matching rule across Org, Folder,
        or Project evaluates to DENY, the request is immediately rejected (HTTP
        403). There are NO deny exceptions.
    -   **Additive ALLOW Aggregation**: Permissions granted at Org/Folder level
        cannot be narrowed or revoked by Project developers.

5.  **Mandatory CEL Null-Dereference Guard**: When an agent calls non-tool MCP
    methods (`prompts/list`, `resources/read`), the `tool` object inside
    `mcp_server` is `null`. A CEL condition dereferencing `.tool.name` or
    `.tool.annotations.*` without verifying the method crashes Gatekeeper with a
    CEL evaluation error. Always prepend:
    `(destination.agent_registry.mcp_server.method == 'tools')`.

6.  **Avoid Blanket Unregistered DENY (Container Boot Crash)**: Never configure
    an Org or Folder-level rule with `(destination.is_registered == false)` and
    `effect: DENY`. Reasoning Engine containers boot by contacting public
    endpoints (`telemetry.mtls.googleapis.com`). An absolute DENY causes
    container boot crashes. Rely instead on Gateway default-deny.

7.  **Zendesk / REST Path Extensions (`.json`)**: Strict prefix matching in
    unregistered UAP rules (e.g. `.startsWith('/api/v2/tickets')`) leaves
    vulnerabilities to sibling paths (e.g. `/api/v2/tickets_export`), while
    exact matching on `/api/v2/tickets` breaks SDK clients that append `.json`
    (`/api/v2/tickets.json`). Match exact paths, `/` subpaths, `.json`, and `?`
    query strings explicitly.

8.  **Org Policy Blocker
    (`constraints/iam.managed.disableAccessPolicyBinding`)**: If creating a
    policy binding fails with `CUSTOM_ORG_POLICY_VIOLATION`, an Org Admin must
    set an Org Policy V2 override setting `enforce: false` at the target CRM
    level using the exact singular constraint name
    `constraints/iam.managed.disableAccessPolicyBinding` (some documentation
    pages contain a plural typo `disableAccessPolicyBindings` that `gcloud org-policies`
    rejects). Allow **~30–60 seconds** for IAM policy/binding propagation.

9.  **Terraform Binding Destruction Race**: Simultaneous destruction of
    `PolicyBinding` and `AccessPolicy` fails with `400 FAILED_PRECONDITION:
    Access policy is referenced by active policy binding(s)` due to IAM
    replication latency (10–30 s). Destroy scripts must poll GET the binding URL
    until HTTP 404 is confirmed before deleting the policy.

10. **Legacy IAM v1 Fallback**: In legacy v1, outbound agent traffic is
    authorized by granting `roles/iap.egressor` directly on the Agent Registry
    resource (`gcloud iap web set-iam-policy --resource-type=agent-registry`).
    Do NOT use `roles/iap.tunnelResourceAccessor` or web ingress roles.

11. **Omit `loadBalancingScheme` & Use `gcloud beta` for L4 `networkRules`**:
    Never set `target.loadBalancingScheme` on `AuthzPolicy` resources targeting
    `agentGateways/*` (causes `INVALID_ARGUMENT`). L4 `networkRules` require
    `gcloud beta network-security authz-policies import`, allow `snis` only (no
    `ports` or HTTP fields), and bypass L7 IAP/UAP, Model Armor, and SGP
    inspection on matched TLS tunnels.

12. **Native MCP `AuthzPolicy` `ALLOW` Rules Require `MATCH_BASE_PROTOCOL_METHODS`**:
    `httpRules[].to.operations[].mcp` defaults `baseProtocolMethodsOption` to
    `SKIP_BASE_PROTOCOL_METHODS`. Every MCP `ALLOW` rule must explicitly set
    `baseProtocolMethodsOption: MATCH_BASE_PROTOCOL_METHODS` so `initialize` and
    `ping` handshakes succeed.

13. **Model Armor Distinct Service Agents & 60s Stream Deadline**: Ingress
    (`CLIENT_TO_AGENT`, ADK `streamQuery` only) runs as
    `service-${AGENT_PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com`;
    egress (`AGENT_TO_ANYWHERE`) runs as
    `service-${GATEWAY_PROJECT_NUMBER}@gcp-sa-dep.iam.gserviceaccount.com`.
    Envoy enforces a hard 60-second total stream deadline on `CONTENT_AUTHZ`
    callouts — exclude `>60s` streams or gRPC channels via `httpRules` to avoid
    `Stream removed` errors.

14. **SGP Non-Streaming CEL Filter & Metadata Map Overwrite**: Scope SGP
    `CONTENT_AUTHZ` policies with a `when` CEL filter using `.contains()` on
    non-streaming LLM paths (`:generateContent`, `:rawPredict`, `/v1/messages`,
    `/chat/completions`). Updating `AuthzExtension` metadata (`import` or
    `updateMask=metadata`) replaces the entire map — always pass all active keys
    (`sgpEnforcementMode`, `sgpUserIntentMatching`) together.

--------------------------------------------------------------------------------

## 1. UAP (Policy V2) vs. Legacy IAM v1 Architecture

```
+-------------------------------------------------------------------------------+
| Legacy IAM v1 Model (Monolithic & Per-Resource)                               |
|                                                                               |
|   Resource (e.g. Storage Bucket, IAP Web Backend Shadow Resource)             |
|   └── IAM Policy                                                              |
|       └── Bindings: [Role: roles/iap.egressor, Members: [principal://...]]   |
|                                                                               |
|   Limitations:                                                                |
|   - Policy is physically glued to the target resource / shadow resource.      |
|   - Zero reusability across projects or folders.                              |
|   - Synthetic shadow resources: projects/123/iap_web/compute/services/...     |
|   - Coarse-grained network/L7 attributes.                                     |
+-------------------------------------------------------------------------------+

                                      │
                                      ▼

+-------------------------------------------------------------------------------+
| Unified Access Policy (UAP / Policy V2) Model (Decoupled & Hierarchical)      |
|                                                                               |
|      +──────────────────────────+          +───────────────────────────+      |
|      │   CRM Hierarchy Node     │          │       AccessPolicy        │      |
|      │ (Org, Folder, Project)   │          │ (Reusable Rule Definition)│      |
|      +─────────────┬────────────+          +─────────────┬─────────────+      |
|                    │                                     │                    |
|                    │               binds to              │                    |
|                    └──────────────► ◄────────────────────┘                    |
|                                     │                                         |
|                          +──────────┴──────────+                              |
|                          │    PolicyBinding    │                              |
|                          │ target: CRM Node    │                              |
|                          │ policy: AccessPolicy│                              |
|                          +─────────────────────+                              |
+-------------------------------------------------------------------------------+
```

### Architectural Comparison Matrix

| Feature        | Legacy IAM v1              | Unified Access Policy (UAP / Policy V2)                                        |
: Dimension      :                            :                                                                                :
| :------------- | :------------------------- | :----------------------------------------------------------------------------- |
| **Coupling**   | **Tightly Coupled**:       | **Decoupled**: Standalone first-class objects referenced by multiple bindings. |
:                : Policies live inside       :                                                                                :
:                : individual resource        :                                                                                :
:                : metadata.                  :                                                                                :
| **Attachment   | Concrete service resources | Canonical Resource Manager nodes:                                              |
: Target**       : or synthetic shadow        : `//cloudresourcemanager.googleapis.com/{organizations|folders|projects}/{ID}`. :
:                : resources (`iap_web`).     :                                                                                :
| **Rule         | Primitive                  | Explicit `effect: ALLOW` or `effect: DENY`, target FQDN permissions, and deep  |
: Capabilities** : Role-to-Principal bindings : L7 CEL conditions.                                                             :
:                : with basic contextual      :                                                                                :
:                : conditions.                :                                                                                :
| **Evaluation   | Unordered role evaluation; | Unified evaluation pipeline: Org → Folder → Project                            |
: Order**        : Deny policies exist as a   : with **strict absolute DENY precedence** and **additive ALLOW aggregation**.   :
:                : separate API               :                                                                                :
:                : (`iam.googleapis.com/v2`). :                                                                                :
| **Enforcement  | Binary (always enforced).  | Dual-mode: **`DRY_RUN`** (audit log simulation) or **`ENFORCE`** / omitted     |
: Modes**        :                            : (active blocking).                                                             :
| **Workload     | Static service accounts    | Extends natively to ephemeral **Workload Identity Federation for Agents**      |
: Targets**      : and human users.           : (`principal\://agents.global.org-...`).                                        :

--------------------------------------------------------------------------------

## 2. UAP Core Architectural Constructs

UAP is comprised of two core resources in the `iam.googleapis.com/v3` (`v3beta`) API:

### 2.1 AccessPolicy (`iam.googleapis.com/v3/.../accessPolicies`)

An `AccessPolicy` is a versioned container of authorization rules defining
*what* is permitted or forbidden, *for whom*, and *under what conditions*.

**`gcloud` Rules Array File (`rules.json` passed to `--details-rules=rules.json`)**:

```json
[
  {
    "description": "Permit access to registered corporate tools",
    "effect": "ALLOW",
    "principals": [
      "principalSet://agents.global.org-112233445566.system.id.goog/attribute.platform/aiplatform"
    ],
    "operation": {
      "permissions": [
        "iap.googleapis.com/resources.egressViaIAP"
      ]
    },
    "conditions": {
      "iap.googleapis.com": {
        "title": "allow_registered_mcp",
        "description": "Matches registered corporate MCP servers",
        "expression": "(destination.is_registered == true) && (destination.agent_registry.resource_type == 'MCP_SERVER')"
      }
    }
  }
]
```

```bash
gcloud iam access-policies create platform-egress-policy \
  --details-rules=rules.json \
  --project="${PROJECT_ID}" \
  --location=global \
  --display-name="Platform Egress Policy"
```

> **Note:** **REST API vs. `gcloud` vs. Terraform Schema Differences**:
> - **`gcloud iam access-policies create --details-rules=`**: Expects a top-level JSON array `[ { ... } ]` of rule objects (there is no `--file` flag).
> - **REST API (`POST https://iam.googleapis.com/v3beta/{parent}/locations/global/accessPolicies?accessPolicyId={id}`)**: Wraps the rules array inside `{"displayName": "...", "details": {"rules": [ ... ]}}`. Both `gcloud` JSON and REST JSON use **singular** `"operation": {"permissions": [...]}` and **plural service-keyed map** `"conditions": {"iap.googleapis.com": { ... }}`.
> - **Terraform (`google_iam_{organization,folder,project}_access_policy` in `google` / `google-beta`)**: Uses HCL blocks `details { rules { operation { permissions = [...] } conditions { service = "iap.googleapis.com" expression = "..." } } }` (singular `operation`, plural `conditions`; `title` is not supported), paired with plural `google_iam_{organizations,folders,projects}_policy_binding`.

#### Key Properties:

-   **`effect`**: Either `ALLOW` or `DENY` (an `AccessPolicy` must contain at least one rule).
-   **`principals`**: SPIFFE agent identity strings (`principal://...`) or principal sets (`principalSet://...`). Never pass `urn:agent:...` catalog URNs here.
-   **`operation.permissions`**: Fully Qualified Domain Name (FQDN) format: `iap.googleapis.com/resources.egressViaIAP` (Agent-to-Anywhere egress).
-   **`conditions["iap.googleapis.com"].expression`**: Common Expression Language (CEL) boolean predicate.

### 2.2 PolicyBinding (`iam.googleapis.com/v3/.../policyBindings`)

A `PolicyBinding` attaches an `AccessPolicy` to a specific Resource Manager node. Allow **~30–60 seconds** after creating or updating a binding or policy for IAM control-plane propagation.

```json
{
  "displayName": "Bind Platform Egress to Engineering Folder",
  "target": {
    "resource": "//cloudresourcemanager.googleapis.com/folders/123456789012"
  },
  "policy": "folders/123456789012/locations/global/accessPolicies/platform-egress-policy",
  "policyKind": "ACCESS"
}
```

```bash
gcloud iam policy-bindings create bind-platform-egress \
  --location=global \
  --project="${PROJECT_ID}" \
  --policy-kind=access \
  --policy="projects/${PROJECT_ID}/locations/global/accessPolicies/platform-egress-policy" \
  --target-resource="//cloudresourcemanager.googleapis.com/projects/${PROJECT_NUMBER}"
```

-   **`target.resource` (`--target-resource`)**: Canonical Resource Manager URI:
    -   Org: `//cloudresourcemanager.googleapis.com/organizations/${ORG_ID}`
    -   Folder: `//cloudresourcemanager.googleapis.com/folders/${FOLDER_ID}`
    -   Project: `//cloudresourcemanager.googleapis.com/projects/${PROJECT_NUMBER}` (numeric project number).
-   **`policyKind` (`--policy-kind`)**: `ACCESS` in JSON/REST (`access` in `gcloud`).

--------------------------------------------------------------------------------

## 3. Runtime Evaluation Pipeline & Mathematical Invariants

```
+-----------------------------------------------------------------------------------+
| 1. Workload Egress                                                                |
|    Agent container issues outbound request (e.g. HTTP GET /api/v2/tickets.json)   |
|    Injected proxy environment directs traffic to Envoy / Agent Gateway.           |
+------------------------------------------┬----------------------------------------+
                                           │
                                           ▼
+-----------------------------------------------------------------------------------+
| 2. PEP Interception & Gatekeeper Resolution                                       |
|    - IAP Authz Extension intercepts the request (Envoy ext_authz).               |
|    - Gatekeeper verifies caller's SPIFFE/OIDC Agent Identity token.               |
|    - Gatekeeper queries Agent Registry:                                           |
|      * If target matches registry: sets destination.is_registered = true          |
|      * If target not cataloged:   sets destination.is_registered = false         |
|    - Populates request attributes into the destination CEL context.               |
+------------------------------------------┬----------------------------------------+
                                           │
                                           ▼
+-----------------------------------------------------------------------------------+
| 3. PDP Traversal: IAM CheckPolicy()                                               |
|    IAM traverses the CRM hierarchy top-down or bottom-up:                         |
|           Organization (organizations/112233445566)                              |
|                 │                                                                 |
|                 ▼                                                                 |
|           Folder (folders/123456789012)                                           |
|                 │                                                                 |
|                 ▼                                                                 |
|           Project (projects/9876543210)                                           |
|    - Evaluates all active PolicyBindings attached to all nodes in the path.       |
+------------------------------------------┬----------------------------------------+
                                           │
                                           ▼
+-----------------------------------------------------------------------------------+
| 4. Evaluation Logic Engine                                                        |
|    [Step A: Check for Absolute DENY]                                              |
|    Did ANY matching rule across Org, Folder, or Project evaluate to DENY?         |
|    ├── YES ──► REJECT IMMEDIATELY (HTTP 403 Forbidden / PERMISSION_DENIED)       |
|    └── NO                                                                         |
|         │                                                                         |
|         ▼                                                                         |
|    [Step B: Aggregate Additive ALLOWs]                                            |
|    ALLOW_effective = ALLOW_project ∪ ALLOW_folder ∪ ALLOW_org                     |
|    Did AT LEAST ONE rule match with effect: ALLOW?                                |
|    ├── YES ──► PERMIT REQUEST (Forward to backend target)                         |
|    └── NO  ──► DEFAULT-DENY (HTTP 403 Forbidden)                                  |
+-----------------------------------------------------------------------------------+
```

### The Two Mathematical Invariants of UAP

1.  **Absolute DENY Precedence**:
    `Decision = DENY` if `∃ r ∈ (Rules_org ∪ Rules_folder ∪ Rules_project)` such that `Match(r) ∧ r.effect == DENY`.
    There are **no deny exceptions** in UAP. If an Org-level rule denies a
    destination, no project developer or platform admin can override or bypass
    that denial.

2.  **Additive ALLOW Aggregation**:
    `ALLOW_effective = ALLOW_org ∪ ALLOW_folder ∪ ALLOW_project`.
    Permissions granted at higher levels cannot be narrowed, scoped down, or
    revoked by lower tiers. If a Platform Admin allows a domain at the Folder
    level, an individual Project Developer cannot block an agent from accessing
    it unless an explicit `DENY` rule is added.

--------------------------------------------------------------------------------

## 4. Deep CEL Attribute Reference

UAP evaluates CEL expressions within the `iap.googleapis.com` namespace rooted
at the `destination` object.

```
                              destination
                                   │
         ┌─────────────────────────┴─────────────────────────┐
         ▼                                                   ▼
   is_registered == true                               is_registered == false
         │                                                   │
   agent_registry                                       unregistered
   ├── resource_type                                    ├── host
   ├── location                                         ├── path
   ├── project_id                                       └── method
   ├── endpoint.name
   ├── mcp_server.name
   ├── mcp_server.method
   ├── mcp_server.tool.name
   ├── mcp_server.tool.annotations.read_only_hint
   ├── mcp_server.tool.annotations.destructive_hint
   ├── mcp_server.tool.annotations.idempotent_hint
   ├── mcp_server.tool.annotations.open_world_hint
   ├── mcp_server.prompt.name
   ├── mcp_server.resource.name
   └── agent.name
```

### 4.1 Registered Destinations (`destination.is_registered == true`)

Populated when the target is cataloged in the Gemini Enterprise **Agent
Registry**.

> **Important:** String functions (`.startsWith()`, `.endsWith()`, `.contains()`) are **NOT** supported on any `destination.agent_registry.*` attribute, and regex `.matches()` is **NOT** supported on any UAP CEL attribute. Registered string attributes support **only `==`, `!=`, and `in`**.

| Attribute | Type | Supported Operators | Purpose / Example |
| :--- | :--- | :--- | :--- |
| `destination.is_registered` | bool | `==`, `!=` | Root guard. Must be verified before accessing sub-attributes. |
| `destination.agent_registry.resource_type` | string | `==`, `!=`, `in` | Resource type: `'ENDPOINT'`, `'MCP_SERVER'`, `'AGENT'`, `'SKILL'`. |
| `destination.agent_registry.location` | string | `==`, `!=`, `in` | Region of the registry resource (`'global'`, `'us-central1'`). |
| `destination.agent_registry.project_id` | string | `==`, `!=`, `in` | Host project ID of the registry entry (`'prod-agent-hub'`). |
| `destination.agent_registry.endpoint.name` | string | `==`, `!=`, `in` | Full resource name: `'projects/{p}/locations/{l}/endpoints/{name}'`. |
| `destination.agent_registry.mcp_server.name` | string | `==`, `!=`, `in` | Full resource name: `'projects/{p}/locations/{l}/mcpServers/{name}'`. |
| `destination.agent_registry.mcp_server.method` | string | `==`, `!=`, `in` | MCP protocol method family: `'tools'`, `'prompts'`, `'resources'`. |
| `destination.agent_registry.mcp_server.tool.name` | string | `==`, `!=`, `in` | Specific tool name being executed (e.g., `'updateTicket'`). |
| `destination.agent_registry.mcp_server.tool.annotations.read_only_hint` | bool | `==`, `!=` | `true` if tool is declared read-only by tool author. |
| `destination.agent_registry.mcp_server.tool.annotations.destructive_hint` | bool | `==`, `!=` | `true` if tool performs irreversible mutations. |
| `destination.agent_registry.mcp_server.tool.annotations.idempotent_hint` | bool | `==`, `!=` | `true` if repeated identical calls have no additional effect. |
| `destination.agent_registry.mcp_server.tool.annotations.open_world_hint` | bool | `==`, `!=` | `true` if tool interacts with external open-world entities. |
| `destination.agent_registry.mcp_server.prompt.name` | string | `==`, `!=`, `in` | MCP prompt name (must guard with `mcp_server.method == 'prompts'`). |
| `destination.agent_registry.mcp_server.resource.name` | string | `==`, `!=`, `in` | MCP resource name/URI (must guard with `mcp_server.method == 'resources'`). |
| `destination.agent_registry.agent.name` | string | `==`, `!=`, `in` | Full resource name of target agent for Agent-to-Agent egress. |

> **Warning:** **Null Dereference Guard Pattern**: When an agent calls a non-tool MCP method (such as `prompts/list` or `resources/read`), the `tool` message inside `mcp_server` is `null` (and similarly `prompt` or `resource` is `null` on `tools/*` calls). Dereferencing `.tool.*`, `.prompt.name`, or `.resource.name` without checking `mcp_server.method` first crashes Gatekeeper with a CEL evaluation error.
>
> **Mandatory pattern**:
>
> ```cel
> (destination.agent_registry.mcp_server.method == 'tools') && (destination.agent_registry.mcp_server.tool.annotations.read_only_hint == true)
> ```

### 4.2 Unregistered Destinations (`destination.is_registered == false`)

Populated when an agent calls an external IP, public URL, SaaS endpoint, or
uncataloged GCP service.

| Attribute | Type | Supported Operators | Purpose / Example |
| :--- | :--- | :--- | :--- |
| `destination.unregistered.host` | string | `==`, `!=`, `in`, `.startsWith()`, `.endsWith()`, `.contains()` | Target host FQDN: `'acme.zendesk.com'`, `'api.github.com'`. (No `.matches()` regex.) |
| `destination.unregistered.path` | string | `==`, `!=`, `in`, `.startsWith()`, `.endsWith()`, `.contains()` | Request URI path: `'/api/v2/tickets.json'`. |
| `destination.unregistered.method` | string | `==`, `!=`, `in` | HTTP verb: `'GET'`, `'POST'`, `'PUT'`, `'DELETE'`. |

> **Important:** **Tool Annotations Unavailable on Unregistered Endpoints**: Unregistered endpoints do NOT possess semantic annotations (`read_only_hint`, `destructive_hint`). The proxy only sees raw L7 wire data (host, path, method). Restricting read-only behavior on unregistered endpoints must be enforced via HTTP methods (`destination.unregistered.method == 'GET'`).

### 4.3 Cloud Console Parenthesization Rule

To ensure the Google Cloud Console UI parses and renders UAP rules as standard
interactive resources (Endpoint, MCP Server, Agent) rather than raw CEL text
fallbacks, **each CEL clause MUST be wrapped in parentheses**:

```cel
(destination.agent_registry.endpoint.name == 'projects/123/locations/us-central1/endpoints/my-ep') && (destination.agent_registry.location == 'us-central1')
```

### 4.4 Principal Identity Grammar

```cel
// 1. Single Agent Runtime Agent (Organization-backed project):
principal://agents.global.org-${ORG_ID}.system.id.goog/resources/aiplatform/projects/${PROJECT_NUMBER}/locations/${LOCATION}/reasoningEngines/${ENGINE_ID}

// 2. Single Agent Runtime Agent (Orgless project — uses proj-${PROJECT_NUMBER}):
principal://agents.global.proj-${PROJECT_NUMBER}.system.id.goog/resources/aiplatform/projects/${PROJECT_NUMBER}/locations/${LOCATION}/reasoningEngines/${ENGINE_ID}

// 3. Single Gemini Enterprise App Agent:
principal://agents.global.org-${ORG_ID}.system.id.goog/resources/discoveryengine/projects/${PROJECT_NUMBER}/locations/${LOCATION}/collections/default_collection/engines/${APP_ID}/assistants/default_assistant/agents/${AGENT_ID}

// 4. All Agents across the entire Organization:
principalSet://agents.global.org-${ORG_ID}.system.id.goog/*

// 5. All Agent Runtime (aiplatform) Agents in the Organization:
principalSet://agents.global.org-${ORG_ID}.system.id.goog/attribute.platform/aiplatform

// 6. All Agents scoped to a specific consumer Project:
principalSet://agents.global.org-${ORG_ID}.system.id.goog/attribute.platformContainer/aiplatform/projects/${PROJECT_NUMBER}
```

> **Note:** Never use `urn:agent:...` catalog URNs in IAM UAP `principals` — URN strings are used only in Agent Registry metadata and `ExtensionBinding.matchConditions`.

--------------------------------------------------------------------------------

## 5. The 3-Tier Organizational Security Model

```
=================================================================================
TIER 1: SECURITY ADMIN (ORGANIZATION SCOPE)
Scope: organizations/${ORG_ID}
Goal: Enterprise Perimeter Guardrails & Telemetry Survival
---------------------------------------------------------------------------------
Rules:
  [ALLOW] Essential Container Telemetry (telemetry.mtls.googleapis.com)
  [DENY]  Unapproved Commercial LLMs (api.openai.com, api.anthropic.com)
=================================================================================
                                │
                                ▼
=================================================================================
TIER 2: PLATFORM ADMIN (FOLDER SCOPE)
Scope: folders/${FOLDER_ID}
Goal: Shared Corporate Defaults & Developer Autonomy Baselines
---------------------------------------------------------------------------------
Rules:
  [ALLOW] Registered Google Cloud APIs (.../endpoints/googleapis)
  [ALLOW] Corporate Intranet Apex & Subdomains (*.corp.example.com)
  [ALLOW] Central Read-Only MCP Tools (read_only_hint == true)
=================================================================================
                                │
                                ▼
=================================================================================
TIER 3: AGENT DEVELOPER (PROJECT SCOPE)
Scope: projects/${PROJECT_NUMBER}
Goal: Granular, Least-Privilege Workload Authorizations
---------------------------------------------------------------------------------
Rules:
  [ALLOW] Mutating Tool updateTicket on Registered Jira MCP Server
  [ALLOW] Strict Zendesk Ticket API (/api/v2/tickets.json, GET/POST/PUT)
  [ALLOW] Scoped GitHub Org Query (/repos/my-org/, GET/POST)
=================================================================================
```

### Concrete Terraform Implementation (`google-beta` provider)

> **Important:** In the `google-beta` Terraform provider (`iam3`), `AccessPolicy`
> resources use **singular** hierarchy nouns (`google_iam_{organization,folder,project}_access_policy`)
> with `details { rules { effect, operation { ... }, conditions { service, expression } } }`
> (`title` is not supported in `conditions`), whereas CRM `PolicyBinding`
> resources use **plural** hierarchy nouns (`google_iam_{organizations,folders,projects}_policy_binding`)
> with `policy_kind = "ACCESS"` and `target { resource = "..." }`. Both the
> `AccessPolicy` **and** its `PolicyBinding` are required for enforcement (and
> `constraints/iam.managed.disableAccessPolicyBinding` must not be enforced on
> the target hierarchy node).

```hcl
# ------------------------------------------------------------------------------
# TIER 1: Organization Guardrails + Organization PolicyBinding
# ------------------------------------------------------------------------------
resource "google_iam_organization_access_policy" "org_guardrails" {
  provider         = google-beta
  organization     = var.org_id
  location         = "global"
  access_policy_id = "org-security-guardrails"
  display_name     = "Organization Security Guardrails"

  details {
    rules {
      description = "ALLOW: Essential telemetry for Reasoning Engine boot"
      effect      = "ALLOW"
      principals  = ["principalSet://agents.global.org-${var.org_id}.system.id.goog/attribute.platform/aiplatform"]
      operation {
        permissions = ["iap.googleapis.com/resources.egressViaIAP"]
      }
      conditions {
        service    = "iap.googleapis.com"
        expression = "(destination.is_registered == false) && (destination.unregistered.host in ['telemetry.mtls.googleapis.com', 'cloudlogging.googleapis.com', 'monitoring.googleapis.com'])"
      }
    }

    rules {
      description = "DENY: Prevent data exfiltration to unauthorized commercial LLMs"
      effect      = "DENY"
      principals  = ["principalSet://agents.global.org-${var.org_id}.system.id.goog/*"]
      operation {
        permissions = ["iap.googleapis.com/resources.egressViaIAP"]
      }
      conditions {
        service    = "iap.googleapis.com"
        expression = "(destination.is_registered == false) && (destination.unregistered.host in ['api.openai.com', 'api.anthropic.com', 'api.cohere.ai'])"
      }
    }
  }
}

resource "time_sleep" "wait_org_access_policy" {
  create_duration = "60s"
  depends_on      = [google_iam_organization_access_policy.org_guardrails]
}

resource "google_iam_organizations_policy_binding" "org_guardrails_binding" {
  provider          = google-beta
  depends_on        = [time_sleep.wait_org_access_policy]
  organization      = var.org_id
  location          = "global"
  policy_binding_id = "org-security-guardrails-binding"
  display_name      = "Bind Organization Security Guardrails"
  policy_kind       = "ACCESS"
  policy            = "organizations/${var.org_id}/locations/global/accessPolicies/${google_iam_organization_access_policy.org_guardrails.access_policy_id}"

  target {
    resource = "//cloudresourcemanager.googleapis.com/organizations/${var.org_id}"
  }
}

# ------------------------------------------------------------------------------
# TIER 2: Folder Platform Defaults + Folder PolicyBinding
# ------------------------------------------------------------------------------
resource "google_iam_folder_access_policy" "folder_defaults" {
  provider         = google-beta
  folder           = var.folder_id
  location         = "global"
  access_policy_id = "folder-platform-defaults"
  display_name     = "Folder Platform Defaults"

  details {
    rules {
      description = "ALLOW: Read-only tools on registered corporate MCP servers"
      effect      = "ALLOW"
      principals  = ["principalSet://agents.global.org-${var.org_id}.system.id.goog/attribute.platform/aiplatform"]
      operation {
        permissions = ["iap.googleapis.com/resources.egressViaIAP"]
      }
      conditions {
        service    = "iap.googleapis.com"
        expression = "(destination.is_registered == true) && (destination.agent_registry.resource_type == 'MCP_SERVER') && (destination.agent_registry.project_id == 'corp-tools-hub') && (destination.agent_registry.mcp_server.method == 'tools') && (destination.agent_registry.mcp_server.tool.annotations.read_only_hint == true)"
      }
    }
  }
}

resource "time_sleep" "wait_folder_access_policy" {
  create_duration = "60s"
  depends_on      = [google_iam_folder_access_policy.folder_defaults]
}

resource "google_iam_folders_policy_binding" "folder_defaults_binding" {
  provider          = google-beta
  depends_on        = [time_sleep.wait_folder_access_policy]
  folder            = var.folder_id
  location          = "global"
  policy_binding_id = "folder-platform-defaults-binding"
  display_name      = "Bind Folder Platform Defaults"
  policy_kind       = "ACCESS"
  policy            = "folders/${var.folder_id}/locations/global/accessPolicies/${google_iam_folder_access_policy.folder_defaults.access_policy_id}"

  target {
    resource = "//cloudresourcemanager.googleapis.com/folders/${var.folder_id}"
  }
}

# ------------------------------------------------------------------------------
# TIER 3: Project Agent-Specific Workload Policy + Project PolicyBinding
# ------------------------------------------------------------------------------
resource "google_iam_project_access_policy" "project_workload_egress" {
  provider         = google-beta
  project          = var.project_id
  location         = "global"
  access_policy_id = "support-bot-egress"
  display_name     = "Support Bot Workload Egress Policy"

  details {
    rules {
      description = "ALLOW: Specific ticket operations with verb constraints"
      effect      = "ALLOW"
      # var.reasoning_engine_id MUST be the numeric ReasoningEngine resource ID
      principals = [
        "principal://agents.global.org-${var.org_id}.system.id.goog/resources/aiplatform/projects/${var.project_number}/locations/us-central1/reasoningEngines/${var.reasoning_engine_id}"
      ]
      operation {
        permissions = ["iap.googleapis.com/resources.egressViaIAP"]
      }
      conditions {
        service    = "iap.googleapis.com"
        expression = "(destination.is_registered == false) && (destination.unregistered.host == 'acme.zendesk.com') && ((destination.unregistered.path == '/api/v2/tickets') || (destination.unregistered.path == '/api/v2/tickets.json') || (destination.unregistered.path.startsWith('/api/v2/tickets/')) || (destination.unregistered.path.startsWith('/api/v2/tickets?')) || (destination.unregistered.path.startsWith('/api/v2/tickets.json?'))) && (destination.unregistered.method in ['GET', 'POST', 'PUT'])"
      }
    }
  }
}

resource "time_sleep" "wait_project_access_policy" {
  create_duration = "60s"
  depends_on      = [google_iam_project_access_policy.project_workload_egress]
}

resource "google_iam_projects_policy_binding" "project_workload_egress_binding" {
  provider          = google-beta
  depends_on        = [time_sleep.wait_project_access_policy]
  project           = var.project_id
  location          = "global"
  policy_binding_id = "support-bot-egress-binding"
  display_name      = "Bind Support Bot Workload Egress Policy"
  policy_kind       = "ACCESS"
  policy            = "projects/${var.project_id}/locations/global/accessPolicies/${google_iam_project_access_policy.project_workload_egress.access_policy_id}"

  target {
    resource = "//cloudresourcemanager.googleapis.com/projects/${var.project_number}"
  }
}
```

--------------------------------------------------------------------------------

## 6. Legacy IAM v1 Reference (Backward Compatibility)

In deployments where the Gateway AuthzExtension does NOT specify
`iapPolicyVersion: "V2"`, IAP operates in legacy V1 mode:

### 6.1 Assigning `roles/iap.egressor`

Apply bindings using `gcloud iap web set-iam-policy`:

```bash
# Registry-wide scope (top-level {"bindings": [...]} JSON without a "policy" wrapper)
gcloud iap web set-iam-policy agents-iap-policy.json \
  --project=PROJECT_ID \
  --resource-type=agent-registry \
  --region=REGION

# Specific MCP Server scope (--resource-type=agent-registry is still mandatory; pass catalog UUID)
gcloud iap web set-iam-policy mcp-iap-policy.json \
  --project=PROJECT_ID \
  --resource-type=agent-registry \
  --region=REGION \
  --mcp-server=MCP_SERVER_UUID
```

### 6.2 Inspecting Legacy Policies

```bash
gcloud iap web get-iam-policy   --project=PROJECT_ID   --resource-type=agent-registry   --region=REGION
```

--------------------------------------------------------------------------------

## 7. Observability, Auditing, & Dry-Run Operations

### 7.1 Gateway AuthzExtension Configuration

In the Agent Gateway's IAP `AuthzExtension` metadata:

-   `iapPolicyVersion: "V2"`: **Mandatory** to activate UAP policy evaluation.
-   `iamEnforcementMode: "DRY_RUN"`: Evaluates complete hierarchy, logs
    decisions to Cloud Audit Logs, and permits traffic.
-   Omit `iamEnforcementMode` (or set `iamEnforcementMode: "ENFORCE"`, never
    `"ENFORCED"`): Actively blocks unapproved traffic with HTTP `403` / gRPC
    `PERMISSION_DENIED`.

### 7.2 Cloud Audit Log Schema (UAP)

Enable **Data Access (`DATA_READ`)** audit logs for `iap.googleapis.com` to record runtime UAP policy evaluations and denials:

```text
protoPayload.serviceName="iap.googleapis.com"
(protoPayload.authorizationInfo.permission="iap.resources.egressViaIAP" OR protoPayload.metadata.iapPolicyVersion="v2")
```

Example audit log payload:

```json
{
  "protoPayload": {
    "@type": "type.googleapis.com/google.cloud.audit.AuditLog",
    "serviceName": "iap.googleapis.com",
    "methodName": "CheckPolicy",
    "metadata": {
      "iapPolicyVersion": "v2",
      "iamEnforcementMode": "DRY_RUN",
      "policyEvaluationResults": [
        {
          "policy": "organizations/112233445566/locations/global/accessPolicies/org-security-guardrails",
          "evaluationResult": "ALLOWED"
        },
        {
          "policy": "folders/123456789012/locations/global/accessPolicies/folder-platform-defaults",
          "evaluationResult": "ALLOWED"
        },
        {
          "policy": "projects/9876543210/locations/global/accessPolicies/support-bot-egress",
          "evaluationResult": "ALLOWED"
        }
      ],
      "finalDecision": "ALLOWED"
    }
  }
}
```

--------------------------------------------------------------------------------

## 8. Production Edge Cases & Architectural Gotchas

### 1. The Blanket Unregistered DENY Boot Crash

-   **Trap**: An Org Admin configures:

    ```cel
    (destination.is_registered == false) // effect: DENY
    ```
-   **Consequence**: All Reasoning Engine containers crash during startup.
    Reasoning Engines emit container boot telemetry to
    `telemetry.mtls.googleapis.com`, which is an unregistered public endpoint.
    Because DENY is absolute, the agent fails to initialize.
-   **Fix**: Rely on the Agent Gateway's built-in default-deny architecture.
    Never write a generic DENY on `destination.is_registered == false`.

### 2. Sibling Path Prefix Escapes vs. Query Strings

-   **Trap**: Restricting an external API with `.startsWith('/api/v2/tickets')`.
-   **Consequence**: An attacker or compromised agent can access
    `/api/v2/tickets_export` or `/api/v2/tickets_delete_all` because both
    strings start with that prefix.
-   **Fix**: Enforce strict boundary delimiters and query parameters:

    ```cel
    ((destination.unregistered.path == '/api/v2/tickets') ||
     (destination.unregistered.path == '/api/v2/tickets.json') ||
     (destination.unregistered.path.startsWith('/api/v2/tickets/')) ||
     (destination.unregistered.path.startsWith('/api/v2/tickets?')) ||
     (destination.unregistered.path.startsWith('/api/v2/tickets.json?')))
    ```

### 3. Confused Deputy via Unanchored `project_id` Sets

-   **Trap**: Allowing `destination.agent_registry.resource_type == 'MCP_SERVER'` across an overly broad `project_id in [...]` list without anchoring the exact `mcp_server.name`.
-   **Consequence**: Any developer who registers a new MCP server inside one of those projects automatically satisfies the policy. (Note also that `mcp_server.name` does **not** support `.startsWith()` or `.endsWith()` — only `==`, `!=`, and `in`.)
-   **Fix**: Anchor both `project_id` and the exact canonical `mcp_server.name`:

    ```cel
    (destination.agent_registry.project_id == 'corp-tools-hub') &&
    (destination.agent_registry.mcp_server.name == 'projects/corp-tools-hub/locations/us-central1/mcpServers/jira-service')
    ```

### 4. Intranet Subdomain Wildcard Masking

-   **Trap**: A Platform Admin allows `*.corp.example.com` (unregistered
    intranet) at the Folder tier, and creates an MCP server named
    `tools.corp.example.com`.
-   **Consequence**: If a developer forgets to catalog `tools.corp.example.com`
    in Agent Registry, Gatekeeper flags `destination.is_registered = false`. The
    request falls through to the unregistered intranet ALLOW rule, completely
    bypassing all tool-level semantic checks (`read_only_hint`) and granting
    ambient access!
-   **Fix**: Host corporate MCP servers on a distinct domain namespace outside
    the intranet wildcard, or ensure registration is verified before deployment.

### 5. IAM Policy Binding Destruction Race Condition

-   **Trap**: Deleting a `PolicyBinding` and its `AccessPolicy` in Terraform at
    the same time.
-   **Consequence**: IAM Policy Control Plane has a 10–30 second replication
    delay. Terraform issues `DELETE AccessPolicy` while the binding deletion is
    still replicating, returning `400 FAILED_PRECONDITION: Access policy is
    referenced by active policy binding(s)`.
-   **Fix**: Destroy provisioners must poll GET the binding URL until HTTP 404
    is confirmed before deleting the AccessPolicy.

### 6. Organization Policy Constraint Blocker

-   **Trap**: `gcloud iam policy-bindings create` fails with
    `CUSTOM_ORG_POLICY_VIOLATION`.
-   **Root Cause**: Many Google Cloud organizations enforce
    `constraints/iam.managed.disableAccessPolicyBinding` by default. (Beware:
    some documentation pages misspell this in the plural as
    `disableAccessPolicyBindings`, which `gcloud org-policies` rejects.)
-   **Fix**: Apply an Org Policy V2 override setting `enforce: false` at the
    target CRM level, then wait **~30–60 seconds** for propagation before
    retrying `policy-bindings create`:

    ```bash
    gcloud org-policies set-policy --project=${PROJECT_ID} override.yaml
    # override.yaml:
    # name: projects/${PROJECT_ID}/policies/iam.managed.disableAccessPolicyBinding
    # spec:
    #   rules:
    #     - enforce: false
    ```

### 7. UAP Control-Plane & Console Error Reference

| Error Code / Symptom | Root Cause | Remediation |
| :--- | :--- | :--- |
| `POLICY_NOT_FOUND` (`HTTP 404`) | Policy ID missing in `--location=global` or wrong parent project/folder/org. | Run `gcloud iam access-policies list --project=${PROJECT_ID} --location=global` to confirm canonical policy name. |
| `TOO_MANY_ACCESS_POLICY_BINDINGS_PER_TARGET` | Target CRM node exceeded per-target policy binding quota. | Consolidate rules into a single `AccessPolicy` and delete redundant bindings on that target. |
| `TOO_MANY_ACCESS_POLICY_BINDINGS_TO_POLICY` | Single `AccessPolicy` bound to too many separate CRM targets. | Bind once at a higher Folder/Org node and discriminate workloads/destinations via `principals` and CEL conditions. |
| `TOO_MANY_CONDITIONS` | Rule exceeded Fine-Grained Access Control (FGAC) CEL condition complexity. | Combine host/method checks using `in [...]` lists or split logic across multiple rules inside the same `AccessPolicy`. |
| `HTTP 412 Precondition Failed` / `ABORTED` | Concurrent edit invalidated the `AccessPolicy` `etag`. | Re-run `gcloud iam access-policies describe` (`GET`) to obtain the latest `etag` before `update` / `PATCH`. |
| **Cannot delete the last rule in a policy** | An `AccessPolicy` must contain at least one rule. | Delete all referencing `PolicyBinding` resources first (poll `GET` until HTTP `404`), then delete the `AccessPolicy`. |

--------------------------------------------------------------------------------

## 9. Quick Command Cheat Sheet

### UAP (Policy V2) Commands

```bash
# List all policy bindings in a project (parent scope — note: `list` has NO --target/--target-resource flag)
gcloud iam policy-bindings list --project="${PROJECT_ID}" --location=global

# Search policy bindings attached to a specific CRM target resource URI
gcloud iam policy-bindings search-target-policy-bindings \
  --target="//cloudresourcemanager.googleapis.com/projects/${PROJECT_NUMBER}" \
  --project="${PROJECT_ID}" \
  --location=global

# Describe an Access Policy
gcloud iam access-policies describe "${POLICY_ID}" \
  --project="${PROJECT_ID}" \
  --location=global

# Tail UAP Audit Logs in Cloud Logging (Data Access + Policy Evaluation)
gcloud logging read \
  'protoPayload.serviceName="iap.googleapis.com" AND (protoPayload.authorizationInfo.permission="iap.resources.egressViaIAP" OR protoPayload.metadata.iapPolicyVersion="v2")' \
  --project="${PROJECT_ID}" --limit=20 --order=desc
```

### Legacy IAM v1 Commands

```bash
# Get IAM policy on Agent Registry
gcloud iap web get-iam-policy \
  --project="${PROJECT_ID}" \
  --resource-type=agent-registry \
  --region="${LOCATION}"

# Tail Legacy IAP Audit Logs
gcloud logging read \
  'protoPayload.serviceName="iap.googleapis.com"' \
  --project="${PROJECT_ID}" --limit=20 --order=desc
```

--------------------------------------------------------------------------------

## 10. Debugging Flowchart

```
                          ┌─────────────────────────────┐
                          │ Agent request denied (403)  │
                          └──────────────┬──────────────┘
                                         │
                                         ▼
                          ┌─────────────────────────────┐
                          │ Check IAP Audit Logs:       │
                          │ iapPolicyVersion == "v2"?   │
                          └───────┬─────────────┬───────┘
                              yes │             │ no (legacy v1)
                                  │             ▼
                                  │      ┌─────────────────────────────┐
                                  │      │ Check roles/iap.egressor    │
                                  │      │ on Agent Registry entry     │
                                  │      └─────────────────────────────┘
                                  ▼
         ┌─────────────────────────────────────────────────────────────┐
         │ Check policyEvaluationResults across Org, Folder, Project   │
         └──────────────────────────────┬──────────────────────────────┘
                                        │
                         ┌──────────────┴──────────────┐
                         ▼                             ▼
               Any rule evaluated to DENY?    No rules matched ALLOW?
                         │                             │
                         ▼                             ▼
             Identify denying rule         Verify destination.is_registered
             (Check for blanket DENY       and check CEL conditions
              or denylisted domain)        (Check null guard on .tool.*)
```

--------------------------------------------------------------------------------

## 11. Network Security AuthzPolicy: L7 HTTP/MCP Rules, L4 networkRules, & DENY_BY_DEFAULT

`AuthzPolicy` (`networksecurity.googleapis.com`) binds authorization rules and
delegated extensions directly to `agentGateways/*` resources.

### 11.1 Policy Evaluation Order & Mandatory Target Invariant

When multiple `AuthzPolicy` resources target the same Agent Gateway in
`REQUEST_AUTHZ`, Envoy evaluates them in strict priority order:

1.  **`CUSTOM`** (delegated `AuthzExtension`, such as IAP or custom `ext_proc`)
2.  **`DENY`** (explicit L7 `httpRules` or L4 `networkRules` deny)
3.  **`ALLOW`** (explicit L7 `httpRules` or L4 `networkRules` allow)
4.  **`DENY_BY_DEFAULT`** (flips fallback behavior from default-allow to default-deny; **cannot** contain `httpRules` or `networkRules`)
5.  Fallback default-allow (only if no `DENY_BY_DEFAULT` policy is attached; note Google-managed egress Agent Gateways already enforce registry/IAP default-deny).

> **Warning:** **Never Set `target.loadBalancingScheme` on Agent Gateways**:
> When `target.resources` references `projects/*/locations/*/agentGateways/*`,
> **omit `target.loadBalancingScheme`** (or leave it `LOAD_BALANCING_SCHEME_UNSPECIFIED`).
> Setting `loadBalancingScheme: INTERNAL_MANAGED` fails validation with
> `INVALID_ARGUMENT: Unsupported load balancing scheme: INTERNAL_MANAGED`.

### 11.2 Native MCP Attribute Rules (`baseProtocolMethodsOption`)

In `GA` (`gcloud network-security authz-policies import`), `httpRules[].to.operations[].mcp`
matches MCP JSON-RPC calls without external extensions.

-   **Critical Default Trap (`SKIP_BASE_PROTOCOL_METHODS`)**: By default,
    `baseProtocolMethodsOption` is `SKIP_BASE_PROTOCOL_METHODS` (which skips
    matching `initialize`, `completion/*`, `logging/*`, `notifications/*`, and
    `ping`). In a `DENY` policy this is safe, **but in an `ALLOW` policy coupled
    with `DENY_BY_DEFAULT`, leaving the default blocks the MCP `initialize`
    handshake with HTTP `403`!**
-   **Mandatory Fix for `ALLOW` Policies**: Explicitly set
    `baseProtocolMethodsOption: MATCH_BASE_PROTOCOL_METHODS`:

```yaml
name: allow-readonly-mcp-tools
target:
  resources:
    - "projects/${PROJECT_ID}/locations/${LOCATION}/agentGateways/${GATEWAY_NAME}"
policyProfile: REQUEST_AUTHZ
action: ALLOW
httpRules:
  - to:
      operations:
        - mcp:
            baseProtocolMethodsOption: MATCH_BASE_PROTOCOL_METHODS
            methods:
              - name: "tools/list"
              - name: "tools/call"
                params:
                  - exact: "get_ticket"
```

```bash
gcloud network-security authz-policies import allow-readonly-mcp-tools \
  --source=allow-readonly-mcp-tools.yaml \
  --location="${LOCATION}" \
  --project="${PROJECT_ID}"
```

### 11.3 L4 `networkRules` (SNI Passthrough & Explicit HTTPS Proxy Support)

When an Agent Runtime workload routes outbound traffic through an **explicit
corporate HTTPS forward proxy** (`HTTPS_PROXY=https://proxy.corp.internal:443`,
with explicit port `:443` and `NO_PROXY=.googleapis.com,googleapis.com,169.254.169.254,metadata.google.internal,localhost,127.0.0.1`),
the client sends an inner `HTTP CONNECT` tunnel over TLS to the proxy's SNI.
Without an L4 `networkRules` policy, Agent Gateway's L7 HTTP connection manager
terminates TLS and rejects nested `CONNECT` requests with **HTTP `404 Not Found`**.

Attaching an L4 `AuthzPolicy` with `networkRules` dispatches matching SNIs to
the gateway's `loopback_tls_network_authz` TCP/SNI listener:

```yaml
name: allow-explicit-proxy-sni
target:
  resources:
    - "projects/${PROJECT_ID}/locations/${LOCATION}/agentGateways/${GATEWAY_NAME}"
policyProfile: REQUEST_AUTHZ
action: ALLOW
networkRules:
  - from:
      sources:
        - ipBlocks:
            - prefix: "7.0.0.0"
              length: 8
            - prefix: "10.20.1.0"
              length: 24
    to:
      operations:
        - snis:
            - exact: "proxy.corp.internal"
```

```bash
# MUST use `gcloud beta` (v1beta1 schema); GA `v1` rejects `networkRules`
gcloud beta network-security authz-policies import allow-explicit-proxy-sni \
  --source=allow-explicit-proxy-sni.yaml \
  --location="${LOCATION}" \
  --project="${PROJECT_ID}"
```

**Strict L4 `networkRules` Schema & Security Trade-offs**:
-   **`gcloud beta` Required**: `networkRules` exists only in `v1beta1` (`gcloud beta network-security authz-policies import`).
-   **`snis` Only**: `networkRules[].to.operations[]` supports **only `snis`** (`exact`, `prefix`, `suffix`, `contains`, `ignoreCase`; max 10 SNIs per operation, max 5 `networkRules` per policy). Do **not** specify `ports` or any HTTP fields (`hosts`, `paths`, `methods`, `headerSet`, `mcp`), and never mix `httpRules` and `networkRules` in the same policy.
-   **Two-Plane Source IP Rule (`7.0.0.0/8` vs. Consumer PSC-I CIDR)**: `from.sources[].resources` is disallowed on Agent Gateway targets. Inside Agent Gateway's Envoy (`AuthzPolicy` `networkRules[].from.sources[].ipBlocks`), either **omit `from`** or include **both** `7.0.0.0/8` (the internal Agent Runtime → Gateway Envoy source range) and your consumer PSC-I subnet CIDR. Inside your **consumer VPC** (GCE ingress firewall rules and Squid `acl localnet src`), allow **only your consumer PSC-I Network Attachment subnet CIDR** (e.g., `10.20.1.0/24`) — packets entering your VPC via PSC-I are sourced from the PSC-I subnet, never `7.0.0.0/8`.
-   **L7 Governance Bypass Trade-off**: Traffic matching an L4 `networkRules` `ALLOW` rule bypasses L7 TLS termination at Agent Gateway — meaning **IAP/UAP, Model Armor, Semantic Governance Policies, and L7 `httpRules` are NOT evaluated** on traffic encapsulated inside that proxy tunnel (your downstream corporate proxy assumes L7 policy responsibility). Also note ACT `tlsConfig.trustConfig` is not applied to L4-bypassed tunnels; configure proxy CA trust inside the agent container (`SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE`).

--------------------------------------------------------------------------------

## 12. Model Armor Content Security Policies (`CONTENT_AUTHZ`)

Model Armor attaches to Agent Gateway via a `ServiceExtensions` `AuthzExtension`
(`service: modelarmor.${LOCATION}.rep.googleapis.com`) and a `NetworkSecurity`
`AuthzPolicy` with `policyProfile: CONTENT_AUTHZ` and `action: CUSTOM`.

### 12.1 Ingress vs. Egress Capabilities, Limits, & Distinct Service Agents

| Dimension | Client-to-Agent (Ingress) | Agent-to-Anywhere (Egress) |
| :--- | :--- | :--- |
| **Max `CONTENT_AUTHZ` Policies** | **1** per ingress gateway | **4** per egress gateway |
| **Service Agent Executing Callout** | **AI Platform Reasoning Engine SA**:<br>`service-${AGENT_PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com` | **Service Extensions SA**:<br>`service-${GATEWAY_PROJECT_NUMBER}@gcp-sa-dep.iam.gserviceaccount.com` |
| **Required IAM Roles** | • `roles/modelarmor.calloutUser` on **agent runtime project**<br>• `roles/modelarmor.user` on **Model Armor template project** | • `roles/modelarmor.calloutUser` + `roles/serviceusage.serviceUsageConsumer` on **gateway project**<br>• `roles/modelarmor.user` on **Model Armor template project** |
| **Sanitized Payloads** | **Only ADK `reasoningEngines.streamQuery`** requests & responses on Agent Runtime | • **MCP**: `tools/call`, `prompts/get`, MCP tool execution errors<br>• **A2A v1**: `SendMessage`, `AgentCard`, `GetExtendedAgentCard` (JSON-RPC & HTTP+JSON/REST)<br>• **OpenAI-compatible LLM**: non-streaming Chat Completions, Get chat messages, non-streaming Responses, Embeddings, Legacy Assistants/Threads/Messages, API errors |
| **Bypassed Without Sanitization** | Non-ADK payloads (e.g., LangChain), `query`, and `ReasoningEngine` error responses | • **MCP**: `tools/list`, `resources/*`, `notifications/*`, Streamable HTTP/SSE, protocol errors<br>• **A2A**: `<v1`, `SendStreamingMessage`, `GetTask`/`ListTasks`/`CancelTask`/`SubscribeToTask`, gRPC protobuf<br>• **OpenAI**: streaming SSE responses<br>• **Documents/PDFs**: unsupported in gateway integration (call Model Armor REST `sanitizeUserPrompt` directly) |

### 12.2 Sensitive Data Protection (SDP) Redaction Semantics

-   In-flight payload redaction requires template enforcement type **`INSPECT_AND_BLOCK`** plus advanced SDP settings with a de-identify template.
-   **Single- vs. Multi-Detector Rule**: If a payload violates **only** the SDP detector, Model Armor redacts the sensitive spans in-flight and forwards the request/response. If a payload violates **multiple detectors** (e.g., SDP + Prompt Injection), Model Armor **blocks the entire payload** without performing redaction.
-   Under `INSPECT_ONLY`, payloads pass unmodified (redaction applies only to Model Armor's own logs).

### 12.3 Hard 60-Second Stream Deadline & Runtime Gotchas

-   **Non-Configurable 60s Stream Deadline (`Stream removed`)**: While `AuthzExtension.timeout` configures individual callout RPC deadlines (`1s`–`10s`), Envoy enforces a **hard 60-second total stream lifetime** on `CONTENT_AUTHZ` processing. Long-running LLM generations, SSE streams, or outbound HTTP/2 gRPC channels routed through a `CONTENT_AUTHZ` policy terminate at 60 seconds with HTTP `500`/`504` or gRPC `UNKNOWN: Stream removed`. **Fix**: Scope `AuthzPolicy.httpRules` (hosts/paths/headers) so `CONTENT_AUTHZ` intercepts only targeted non-streaming tool/model endpoints and excludes long-lived gRPC/SSE streams.
-   **Body-Shape Inspection & Streaming Log Volume**: Model Armor matches protocol payloads by **JSON body structure**, not URL path alone. On ADK `streamQuery` responses, seeing multiple `CONTENT_MODIFIED` / per-chunk callout entries in gateway logs is expected frame-by-frame inspection behavior.

--------------------------------------------------------------------------------

## 13. Semantic Governance Policies (SGP)

Semantic Governance Policies evaluate proposed tool calls and model interactions
against **Natural Language Constraints (NLC)** and optional **User Intent
Alignment** using **the LLM in the semantic governance policy engine**.

### 13.1 Provisioning Prerequisites & Reserved Subnets

1.  **API, Supported Locations, & Regional Endpoint Override**: SGP is available in `us-central1`, `us-east1`, `us-east4`, `us-west1`, `europe-southwest1`, `europe-west1`, `europe-west4`, and `europe-west8`. Enable `aiplatform.googleapis.com` and point `gcloud` at the regional endpoint before running SGP engine/policy commands:
    ```bash
    gcloud config set api_endpoint_overrides/aiplatform "https://${LOCATION}-aiplatform.googleapis.com/"
    ```
2.  **Vertex AI Service Agent IAM**: Grant `service-${PROJECT_NUMBER}@gcp-sa-aiplatform.iam.gserviceaccount.com` `roles/compute.networkAdmin` and `roles/dns.admin` (plus `roles/cloudtrace.agent` when Cloud Trace is enabled) on the project.
3.  **Reserved CIDR Ranges**: The SGP engine reserves **`10.0.0.0/24`, `10.0.1.0/24`, and `10.0.2.0/24`** internally. Overlapping subnets in the peered VPC cause engine provisioning or connectivity failures.
4.  **Engine & Policy CLI**: Manage via `gcloud beta ai semantic-governance-policy-engine {update,describe,deprovision}` and `gcloud beta ai semantic-governance-policies {create,update,list,describe,delete}`.

### 13.2 Data-Plane `AuthzExtension` Metadata & Non-Streaming CEL `when` Filter

1.  **Mandatory Non-Streaming `when` CEL Filter**: SGP supports **non-streaming** JSON LLM calls across Gemini (`:generateContent`), Vertex AI (`:rawPredict`), Anthropic Messages (`/v1/messages`), and OpenAI Chat Completions (`/chat/completions`). The policy engine **does not support streamed model responses** (`:streamGenerateContent`, `:streamRawPredict`) — streamed calls return **no verdict or an error** (and produce zero evaluation entries in `logs/semantic-governance-policy`), so agents must invoke models **without streaming**. Excluding `application/grpc` is also mandatory so internal gRPC bootstrap calls (e.g., Cloud Resource Manager) do not crash agent startup. Because Envoy populates `request.path` **including query parameters** (e.g., `?alt=json`), always use `.contains()` rather than `.endsWith()`:

```yaml
name: sgp-content-authz-policy
target:
  resources:
    - "projects/${PROJECT_ID}/locations/${LOCATION}/agentGateways/${GATEWAY_NAME}"
policyProfile: CONTENT_AUTHZ
action: CUSTOM
httpRules:
  - when: "!request.headers['content-type'].startsWith('application/grpc') && (request.path.contains(':generateContent') || request.path.contains(':rawPredict') || request.path.contains('/v1/messages') || request.path.contains('/chat/completions'))"
customProvider:
  authzExtension:
    resources:
      - "projects/${PROJECT_ID}/locations/${LOCATION}/authzExtensions/${SGP_EXTENSION_NAME}"
```

2.  **`AuthzExtension.metadata` Keys & Wholesale Map Overwrite Trap**:
    -   `sgpEnforcementMode: "DRY_RUN"` (audit-only; omit key to enforce blocking).
    -   `sgpUserIntentMatching: "ENABLED"` or `"DISABLED"` (logs `sgpUserIntentMatchingMode` as `CONSTRAINTS_AND_INTENT`, `CONSTRAINTS_ONLY`, or `INTENT_ONLY`).
    -   **Trap**: Updating `AuthzExtension` via `gcloud service-extensions authz-extensions import` or REST `PATCH ...?updateMask=metadata` **replaces the entire `metadata` map**. Updating `sgpUserIntentMatching` without repeating `sgpEnforcementMode: "DRY_RUN"` immediately flips the gateway into active enforcement!

### 13.3 SGP Cloud Logging, Runtime Failure Modes, & Control-Plane Error Catalog

Query SGP data-plane evaluation logs in Cloud Logging:

```text
logName="projects/${PROJECT_ID}/logs/semantic-governance-policy"
```

-   **Runtime Log Fields & Failure Symptoms**: Inspect `jsonPayload.verdict`, `jsonPayload.evaluations[].rationale`, `jsonPayload.sgpUserIntentMatchingMode`, and `jsonPayload.token_usage`. If `logs/semantic-governance-policy` has **zero entries** or streamed LLM calls fail, verify the agent invokes models **without streaming** (`:generateContent` rather than `:streamGenerateContent`) and that `httpRules[].when` uses `.contains()`. If agent sessions fail with `FAILED_PRECONDITION`, verify `dnsPeeringConfig` on your ACT resolves the engine's private `dnsRecord` (`SGP_DNS_HOSTNAME`).
-   **Control-Plane Error Catalog (`aiplatform.googleapis.com` `ErrorInfo.reason`)**: Returned when running `gcloud beta ai semantic-governance-policies` or `semantic-governance-policy-engine`:

| Control-Plane Error Code (`Status`) | Root Cause & Action |
| :--- | :--- |
| `SEMANTIC_GOVERNANCE_POLICY_ALREADY_EXISTS` (`ALREADY_EXISTS`) | Policy ID already exists in project/location → choose a unique ID or use `semantic-governance-policies update`. |
| `SEMANTIC_GOVERNANCE_POLICY_ETAG_MISMATCH` (`ABORTED`) | Concurrent update invalidated `etag` → run `describe` to fetch the latest `etag` and retry `update`. |
| `SEMANTIC_GOVERNANCE_POLICY_AGENT_REQUIRED` (`INVALID_ARGUMENT`) | Missing `--agent` target → supply the full Agent Registry agent resource name. |
| `SEMANTIC_GOVERNANCE_POLICY_CONSTRAINT_REQUIRED` (`INVALID_ARGUMENT`) | Missing `--natural-language-constraint` → provide a non-empty natural-language constraint. |
| `SEMANTIC_GOVERNANCE_POLICY_AGENT_INVALID_NAME` (`INVALID_ARGUMENT`) | Malformed `--agent` path → use `projects/PROJECT_ID/locations/LOCATION/agents/agentregistry-...`. |
| `SEMANTIC_GOVERNANCE_POLICY_AGENT_UNSUPPORTED_REGION` (`INVALID_ARGUMENT`) | Agent resource location does not match policy location → register/deploy in the same supported SGP region. |
| `SEMANTIC_GOVERNANCE_POLICY_AGENT_NOT_FOUND` (`FAILED_PRECONDITION`) | Target agent not found in Agent Registry → verify with `gcloud agent-registry agents list --location=${LOCATION}`. |
| `SEMANTIC_GOVERNANCE_POLICY_AGENT_NOT_CONFIGURED` (`FAILED_PRECONDITION`) | Agent was not created with both `AGENT_IDENTITY` (`agents.global.*`) and `agent_gateway_config` → redeploy a new Reasoning Engine with both set at creation time. |
| `SEMANTIC_GOVERNANCE_POLICY_MCP_SERVER_NOT_FOUND` (`FAILED_PRECONDITION`) | Referenced MCP server missing in Agent Registry → verify with `gcloud agent-registry mcp-servers list --location=${LOCATION}`. |
| `SEMANTIC_GOVERNANCE_POLICY_MCP_SERVER_INVALID_NAME` (`INVALID_ARGUMENT`) | Malformed MCP server path → use `projects/PROJECT_ID/locations/LOCATION/mcpServers/agentregistry-...`. |
| `SEMANTIC_GOVERNANCE_POLICY_MCP_SERVER_UNSUPPORTED_REGION` (`INVALID_ARGUMENT`) | MCP server location does not match policy location (or is in an unsupported region) → align locations. |
| `SEMANTIC_GOVERNANCE_POLICY_REGISTRY_DENIED` (`PERMISSION_DENIED`) | Caller lacks Agent Registry read access or API is disabled → enable `agentregistry.googleapis.com` and grant `roles/agentregistry.viewer`. |
| `SEMANTIC_GOVERNANCE_POLICY_AGENT_REGISTRY_INVALID_NAME` (`INVALID_ARGUMENT`) | Malformed Agent Registry resource identifier in policy target/tool scope → verify exact `name` from `agent-registry {agents,mcp-servers} describe`. |
| `SEMANTIC_GOVERNANCE_POLICY_ENGINE_NOT_ENABLED_IN_REGION` (`FAILED_PRECONDITION`) | SGP engine not provisioned or not yet `ACTIVE` in `${LOCATION}` → run `gcloud beta ai semantic-governance-policy-engine update --location=${LOCATION}` and poll `describe` until `state: ACTIVE`. |
| `SEMANTIC_GOVERNANCE_POLICY_ENGINE_SERVICE_NOT_AVAILABLE_IN_LOCATION` (`FAILED_PRECONDITION`) | SGP is unavailable in the requested location → deploy in a supported SGP region (`us-central1`, `us-east1`, `us-east4`, `us-west1`, `europe-southwest1`, `europe-west1`, `europe-west4`, `europe-west8`) with `api_endpoint_overrides/aiplatform` set. |

--------------------------------------------------------------------------------

## 14. Extensible Policies: ExtensionBinding & ProducerExtension (Preview)

`ExtensionBinding` (`gcloud beta service-extensions extension-bindings import`)
provides a streamlined consumer attachment model replacing manual
`AuthzExtension` + `AuthzPolicy` pairs:

-   **1P Built-in Extensions**: Reference Google-managed endpoints directly via
    `producerExtension: "iap.googleapis.com"` or
    `producerExtension: "modelarmor.us.rep.googleapis.com"` (passing templates in
    `producerMetadata.model_armor_settings`) without creating a `ProducerExtension`.
-   **2P/3P Custom `ext_proc` Extensions**: Producers host an Envoy `ext_proc`
    gRPC service (e.g., Cloud Run with HTTP/2 + plaintext gRPC + unauthenticated
    ingress → Serverless NEG → Regional Internal ALB → PSC Service Attachment)
    and publish a `ProducerExtension` using the separate `--extension-settings-*` flags:
    ```bash
    gcloud beta service-extensions producer-extensions create PRODUCER_EXTENSION_NAME \
      --location="${LOCATION}" \
      --project="${PRODUCER_PROJECT}" \
      --phase=authz \
      --extension-settings-service="projects/${PRODUCER_PROJECT}/regions/${LOCATION}/serviceAttachments/${PSC_ATTACHMENT_NAME}" \
      --extension-settings-supported-events=request-headers,request-body,response-headers,response-body \
      --extension-settings-authority="ext.producer.example.com"
    ```
    Consumers then bind `producerExtension: "projects/${PRODUCER_PROJECT}/locations/${LOCATION}/producerExtensions/PRODUCER_EXTENSION_NAME"` after PSC project allowlisting.
-   **Match Conditions & Metadata Context**: `matchConditions` filter on
    `to.destination.resources` (`prefix: "urn:mcp"`, `prefix: "urn:agent"`) or
    `to.destination.hosts`. Custom `ext_proc` servers receive gateway/registry
    context in `ProcessingRequest.metadata_context` under
    `com.google.serviceextensions.invocation_info` (`binding_selector.{target, project_number, to_resource}`).
-   **Double-Invocation Gotcha**: `ExtensionBinding` can attach at either the
    gateway resource level (`target.resources`) or project scope (`target.scope.parent: "projects/${PROJECT_NUMBER}"`, `resourceTypes: "AGENT_GATEWAY"`). Attaching the **same** extension via both a project-scope `ExtensionBinding` and a gateway-level `ExtensionBinding` (or combining a project-scope `ExtensionBinding` with a gateway-bound `AuthzPolicy`) executes the extension **twice** on every matching request (see BKI #39).

--------------------------------------------------------------------------------

## 15. Token Management Policies (Preview — HTTP 429)

Token management policies enforce shared LLM token budgets (`input`, `output`,
and `cached` tokens) across Gemini, Anthropic, and OpenAI-compatible models on
self-managed Secure Web Proxy Agent Gateway deployments (for GKE and Cloud Run
agents).

-   **Strict Dependency & Teardown Order** (max **1** of each per project target scope):
    1.  Create `TokenAggregationPolicy` first (up to 10 first-match `rules` grouping traffic into a `tokenGroup`; unmatched traffic logs as `unmatched`).
    2.  Create `TokenBudgetPolicy` second (up to 10 `TokenPool` entries with `maxTokens`, `HOURLY` or `DAILY` midnight PT reset, `alertThreshold` e.g. `0.8`; non-targeted models log pool `undefined`).
    3.  Create `CostPerTokenPolicy` third (optional custom USD rates or discount for `gcp.token_management.token.estimated_cost`).
    -   **Teardown**: Delete in **strict reverse order**: `CostPerTokenPolicy` → `TokenBudgetPolicy` → `TokenAggregationPolicy`.
-   **Diagnosing Unexpected HTTP `429 Too Many Requests` vs. Quota Overshoot**:
    -   **Pre-flight block (`429`)**: When a pool's reconciled consumption reaches `maxTokens` and strict enforcement is active, pre-flight checks reject new LLM requests immediately with **HTTP `429`**. Distinguish gateway token-pool `429` from upstream Vertex AI/model quota `429` by checking `token_management_alert_logs` in Cloud Logging and `gen_ai.client.token.usage` in Cloud Monitoring.
    -   **Concurrent overshoot**: Because output tokens are reconciled *after* an LLM response completes, concurrent in-flight requests admitted just below `maxTokens` can temporarily exceed the budget before subsequent requests are throttled. Validate new budgets with `validateOnly: true` and `alertThreshold: 0.6`–`0.8` before enabling strict blocking.
