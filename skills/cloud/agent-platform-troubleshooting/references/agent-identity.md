# Agent Identity — Debugging Reference

Reference for diagnosing "who is this request from?" issues on Gemini Enterprise
Agent Platform / Agent Runtime (Reasoning Engines).

Primary source:
<https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/agent-identity-overview.md.txt>
(mirrored at <https://docs.cloud.google.com/iam/docs/agent-identity-overview.md.txt>)

## Table of Contents

-   [TL;DR for debugging](#tldr-for-debugging): Lines 27-69
-   [What "agent identity" means (vs service account, vs principal set)](#what-agent-identity-means-vs-service-account-vs-principal-set): Lines 70-112
-   [Identity format and trust domains](#identity-format-and-trust-domains): Lines 113-142
-   [Principal set forms (for IAM policy debugging)](#principal-set-forms-for-iam-policy-debugging): Lines 143-210
-   [How identities are created and bound to ReasoningEngines](#how-identities-are-created-and-bound-to-reasoningengines): Lines 211-280
-   [How to inspect / enumerate the identity at runtime](#how-to-inspect--enumerate-the-identity-at-runtime): Lines 281-335
-   [Token format / what shows up in logs](#token-format--what-shows-up-in-logs): Lines 336-370
-   [Required roles for the identity to function](#required-roles-for-the-identity-to-function): Lines 371-475
-   [Granting roles — exact gcloud commands](#granting-roles--exact-gcloud-commands): Lines 476-533
-   [Common debugging scenarios](#common-debugging-scenarios): Lines 534-646
-   [Code: pulling the bound token via ADC inside the agent](#code-pulling-the-bound-token-via-adc-inside-the-agent): Lines 647-672
-   [Quick reference — useful URLs](#quick-reference--useful-urls): Lines 673-700

--------------------------------------------------------------------------------

## TL;DR for debugging

-   An "agent identity" is a SPIFFE-based, per-agent principal — not a service
    account. It is bound 1:1 to the runtime resource (e.g. a single
    `reasoningEngines/<id>`).
-   The runtime can use one of three identity modes (`identityType` enum on
    `ReasoningEngineSpec`): `IDENTITY_TYPE_UNSPECIFIED` (legacy),
    `SERVICE_ACCOUNT`, or `AGENT_IDENTITY`. Default is service-account behavior.
-   The actual identity in use at runtime is exposed as `spec.effectiveIdentity`
    on the ReasoningEngine resource. Read this first.
-   IAM bindings use `principal://...` (single agent) and `principalSet://...`
    (group of agents in a trust domain / project / org). The trust domain is
    per-org or per-orgless-project and uses
    `agents.global.org-<ORG_ID>.system.id.goog` or
    `agents.global.proj-<PROJECT_NUMBER>.system.id.goog` (`proj-`, **never**
    `project-`).
-   The Agent Runtime SDK uses Application Default Credentials, which on the
    runtime automatically pull the Agent Identity token from the metadata server
    — no explicit code is required for it to take effect.
-   A new Agent Identity automatically receives
    `roles/aiplatform.agentDefaultAccess` and
    `roles/aiplatform.agentContextEditor`, which already cover core model
    inference, sessions, and memory. **Never** grant project-level
    `roles/aiplatform.expressUser` or `roles/aiplatform.user` to an Agent
    Identity (they permit deleting/modifying sibling `ReasoningEngine` resources
    and escalating privileges). For standard project quota/observability, grant
    only: `roles/serviceusage.serviceUsageConsumer`, `roles/browser`,
    `roles/logging.logWriter`, `roles/monitoring.metricWriter`,
    `roles/cloudapiregistry.viewer`.
-   A `401 UNAUTHENTICATED` from a Google Cloud API in an Agent-Identity-enabled
    runtime almost always means Context-Aware Access (mTLS / DPoP token-binding)
    is rejecting the call — not an IAM permission problem. Check binding /
    egress path before adding roles.
-   Service-account mode default is the Google-managed
    `service-<PROJECT_NUMBER>@gcp-sa-aiplatform-re.iam.gserviceaccount.com`
    (role: `roles/aiplatform.reasoningEngineServiceAgent`). To see it in the IAM
    page you must check "Include Google-provided role grants".
-   Logs show *both* the agent SPIFFE identity and the end-user identity when an
    agent is acting on behalf of a user; only the agent identity when acting on
    its own authority.

--------------------------------------------------------------------------------

## What "agent identity" means (vs service account, vs principal set)

Source: <https://docs.cloud.google.com/iam/docs/agent-identity-overview.md.txt>

Agent Identity provides cryptographic, SPIFFE-based identities for agents so
they can authenticate to MCP servers, Google Cloud APIs, the Agent Gateway, and
other agents.

Compared to service accounts:

Property                     | Service account | Agent Identity
:--------------------------- | :-------------- | :---------------------------
Shared across workloads      | Yes (default)   | No — 1 per agent resource
Impersonable by other agents | Yes (with role) | No
Long-lived keys allowed      | Yes             | No (system-managed only)
Token binding                | No              | Yes (X.509-bound, DPoP)
Identity scope               | Project         | Tied to runtime resource URI

Three things commonly get conflated when debugging — keep them distinct:

1.  **Service account** — `name@project.iam.gserviceaccount.com`. Used when
    `identityType` is unset or `SERVICE_ACCOUNT`. Granted via `serviceAccount:`
    IAM member.
2.  **Agent identity (single agent)** — a SPIFFE principal bound to one
    ReasoningEngine. Granted via `principal://<TRUST_DOMAIN>/resources/...`.
3.  **Principal set** — a group of agent identities (all agents in a project,
    trust domain, or org). Granted via `principalSet://<TRUST_DOMAIN>/...`. Used
    to apply common roles (logging, quota, model access) to many agents at once
    without per-agent bindings.

### Three-Identity Delegation Architecture

Across Client/Ingress, Agent Runtime/Broker, and Egress/Target Resource trust
boundaries, Google Cloud separates three distinct identity layers:

| Identity Layer | Boundary & Format | Security Role & Audit Behavior |
| :--- | :--- | :--- |
| **1. User identity** | Client → Agent (`CLIENT_TO_AGENT` OAuth / OIDC caller) | Identifies the human caller; evaluated by ingress IAP/UAP and Model Armor. |
| **2. Agent identity** | Agent → Gateway / Cloud APIs (`principal://agents.global.{org-ORG\|proj-NUM}.system.id.goog/resources/...`) | Cryptographic SPIFFE machine identity (24h auto-rotated X.509 cert + DPoP/CAA binding); brokers 2LO/API keys via Auth Manager when acting autonomously. |
| **3. Delegated identity** | Agent → Downstream tool on behalf of user (3LO token via Auth Manager) | Enforces the intersection of agent egress policy + user OAuth scopes; Cloud Audit Logs record **both** the agent SPIFFE identity and the end-user identity. |

--------------------------------------------------------------------------------

## Identity format and trust domains

Source: <https://docs.cloud.google.com/iam/docs/agent-identity-overview.md.txt> and
<https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/identity-delegation-architecture.md.txt>

-   **SPIFFE ID (X.509 SAN)**: `spiffe://<TRUST_DOMAIN>/resources/<SERVICE>/<RESOURCE_PATH>`
-   **IAM principal**: `principal://<TRUST_DOMAIN>/resources/<SERVICE>/<RESOURCE_PATH>`

Concrete runtime principal shapes (always use numeric `PROJECT_NUMBER`):

-   **Agent Runtime (`ReasoningEngine`)**:
    `principal://agents.global.org-123456789012.system.id.goog/resources/aiplatform/projects/9876543210/locations/us-central1/reasoningEngines/1234567890`
-   **Gemini Enterprise (`Engine`)**:
    `principal://agents.global.org-123456789012.system.id.goog/resources/discoveryengine/projects/9876543210/locations/global/collections/default_collection/engines/my-ge-app`
    *(Note: Gemini Enterprise custom/ADK agents may also authenticate with the configured project/custom Service Account depending on connector configuration.)*
-   **Cloud Run (`--identity-type=agent-identity`)**:
    `principal://agents.global.org-123456789012.system.id.goog/resources/run/projects/9876543210/locations/us-central1/services/my-agent-service`
-   **GKE (`iam.gke.io/spiffe-identity-type: agent-identity`)**:
    SPIFFE agent identity provisioned via the GKE SPIFFE controller.

Trust domain (auto-provisioned when the Agent Platform API is first enabled):

-   Org present: `agents.global.org-<ORGANIZATION_ID>.system.id.goog`
-   Orgless project: `agents.global.proj-<PROJECT_NUMBER>.system.id.goog` (`proj-`, **not** `project-`)

Source:
<https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-identity.md.txt>

--------------------------------------------------------------------------------

## Principal set forms (for IAM policy debugging)

Source: <https://docs.cloud.google.com/iam/docs/principal-identifiers.md.txt>

| Scope     | Identifier                                                                                                                       |
| :-------- | :------------------------------------------------------------------------------------------------------------------------------- |
| Single    | `principal://<TRUST_DOMAIN>/resources/<SERVICE>/<RESOURCE_PATH>`                                                                 |
: agent     :                                                                                                                                  :
| All       | `principalSet://<TRUST_DOMAIN>/*`                                                                                                |
: agents in :                                                                                                                                  :
: a trust   :                                                                                                                                  :
: domain    :                                                                                                                                  :
| All       | `principalSet://<TRUST_DOMAIN>/attribute.platformContainer/aiplatform/projects/<PROJECT_NUMBER>`                                 |
: agents in :                                                                                                                                  :
: a project :                                                                                                                                  :
| All       | `principalSet://agents.global.org-<ORG_ID>.system.id.goog/attribute.platform/aiplatform`                                         |
: agents in :                                                                                                                                  :
: an org    :                                                                                                                                  :
| DIY       | `principal://iam.googleapis.com/projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL>/subject/ns/<NS>/sa/<SA>` |
: agents    :                                                                                                                                  :
: (workload :                                                                                                                                  :
: identity  :                                                                                                                                  :
: pool)     :                                                                                                                                  :

Tips when debugging:

-   If you see
    `principalSet://...attribute.platformContainer/aiplatform/projects/<num>` in
    a binding, that is *all* agents in that project. A binding here grants every
    agent in the project the role — useful for shared roles (logging/quota), bad
    for sensitive resources.
-   The `attribute.platform/aiplatform` set covers an *entire org*.

### Principal Identifiers in Unified Access Policy (UAP / Policy V2)

Under **Unified Access Policy** (`iam.googleapis.com/v3` `AccessPolicy` and
`PolicyBinding`), principal identifiers are specified directly in the
`rules[].principals` array:

```yaml
# In AccessPolicy rule definition (singular 'operation', NOT 'operations'):
rules:
  - description: "Allow project agents to access registered weather service"
    principals:
      - "principalSet://agents.global.org-123456789012.system.id.goog/attribute.platformContainer/aiplatform/projects/9876543210"
      - "principal://agents.global.org-123456789012.system.id.goog/resources/aiplatform/projects/9876543210/locations/us-central1/reasoningEngines/1234567890"
    operation:
      permissions:
        - "iap.googleapis.com/resources.egressViaIAP"
```

Important rules for UAP principal matching:

1.  **Direct Principal vs. PrincipalSet**: You can specify either specific
    `principal://...` URIs or broad `principalSet://...` group URIs in the
    `principals` array.
2.  **Audit Log Correlation**: In Cloud Audit Logs
    (`protoPayload.authenticationInfo.principalSubject`), the runtime always
    logs the exact `principal://` URI of the calling agent, which satisfies
    either a direct `principal://` rule or a container-level `principalSet://`
    rule.
3.  **Service Accounts in UAP**: If an agent runs with a custom Service Account
    (`SERVICE_ACCOUNT` mode), the principal string in UAP is
    `serviceAccount:name@project.iam.gserviceaccount.com` (or
    `principal://iam.googleapis.com/projects/...`).

--------------------------------------------------------------------------------

## How identities are created and bound to ReasoningEngines

Source:
<https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-identity.md.txt>
Source:
<https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1beta1/projects.locations.reasoningEngines.md.txt>

The `IdentityType` enum on `ReasoningEngineSpec`:

-   `IDENTITY_TYPE_UNSPECIFIED` — same as `SERVICE_ACCOUNT`. Uses the
    `serviceAccount` field if set, else default Agent Runtime Service Agent.
-   `SERVICE_ACCOUNT` — same behavior as `IDENTITY_TYPE_UNSPECIFIED`; explicit.
-   `AGENT_IDENTITY` — uses Agent Identity. The `serviceAccount` field **must
    not be set** when this is selected.

### Create with Agent Identity (Python SDK)

```python
import vertexai
from vertexai import types
from vertexai.agent_engines import AdkApp

# v1beta1 is required for Agent Identity support
client = vertexai.Client(
    project=PROJECT_ID,
    location=LOCATION,
    http_options=dict(api_version="v1beta1"),
)

remote_app = client.agent_engines.create(
    agent=AdkApp(agent=agent),
    config={
        "display_name": "running-agent-with-identity",
        "identity_type": types.IdentityType.AGENT_IDENTITY,
        "requirements": ["google-cloud-aiplatform[adk,agent_engines]"],
        "staging_bucket": f"gs://{BUCKET_NAME}",
    },
)
print(f"Effective Identity: {remote_app.api_resource.spec.effective_identity}")
```

### Create identity-only (no agent code yet) so you can pre-grant IAM

```python
remote_app = client.agent_engines.create(
    config={"identity_type": types.IdentityType.AGENT_IDENTITY},
)
# Later: agent_engines.update(...) to add code.
```

### Other ways

-   ADK CLI: `echo '{"identity_type": "AGENT_IDENTITY"}' >
    .agent_engine_config.json; adk deploy ...`
-   Agents CLI: `agents-cli deploy --agent-identity`

### What gets auto-provisioned

-   A SPIFFE ID and matching X.509 certificate (rotated; valid 24 h).
-   `roles/aiplatform.agentDefaultAccess` (basic project logging + model calls).
-   `roles/aiplatform.agentContextEditor` (own sessions, memory, sandboxes).
-   A workload access token bound to the X.509 cert; an authorization DPoP
    proof; an entry in the agent identity pool.

> If `identity_type` is not configured, the runtime falls back to
> service-account mode — preserves backward compatibility for existing IaC
> deployments.

--------------------------------------------------------------------------------

## How to inspect / enumerate the identity at runtime

Source:
<https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-identity.md.txt>

### Read the effective identity (authoritative)

The `spec.effectiveIdentity` field on the ReasoningEngine GET response is the
single source of truth. Possible shapes (per the REST reference):

-   `service-{project_number}@gcp-sa-aiplatform-re.iam.gserviceaccount.com` — `SERVICE_AGENT`
-   `{name}@{project_id}.iam.gserviceaccount.com` — `SERVICE_ACCOUNT`
-   `agents.global.{org-ORG_ID|proj-PROJECT_NUMBER}.system.id.goog/resources/aiplatform/projects/{project_number}/locations/{location}/reasoningEngines/{re}`
    — `AGENT_IDENTITY`

Example REST response excerpt:

```json
{
  "spec": {
    "effectiveIdentity": "agents.global.org-ORGANIZATION_ID.system.id.goog/resources/aiplatform/projects/PROJECT_NUMBER/locations/LOCATION/reasoningEngines/AGENT_ENGINE_ID"
  }
}
```

### Google Cloud console

Google Cloud console -> Agent Platform Deployments. The "Identity" column lists
the agent identity for each deployed agent.

### gcloud / curl

REST: `GET projects/PROJECT/locations/LOCATION/reasoningEngines/ID` against the
v1beta1 endpoint, then read `spec.effectiveIdentity`.

```bash
curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://LOCATION-aiplatform.googleapis.com/v1beta1/projects/PROJECT/locations/LOCATION/reasoningEngines/ID" \
  | jq '.spec.effectiveIdentity, .spec.identityType, .spec.serviceAccount'
```

### From inside the agent's container

ADC will already be wired up — confirm with a one-shot tool call:

```python
from google.auth import default
creds, project_id = default()
# creds.service_account_email when SA mode; for AGENT_IDENTITY the credential
# is system-attested and tied to the metadata server. Use ADC to call any
# Google API; identity comes from the bound token.
```

--------------------------------------------------------------------------------

## Token format / what shows up in logs

Source:
<https://docs.cloud.google.com/access-context-manager/docs/caa-agent-security.md.txt>
Source:
<https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-identity.md.txt>

Agent Identity uses two artifacts (not a plain bearer JWT):

1.  **X.509 certificate** — issued under a Google-managed trust domain. Embeds
    the agent's SPIFFE ID. Used for mTLS to Agent Gateway.
2.  **Certificate-bound workload access token** — short-lived OAuth-style token
    *cryptographically bound* to the X.509 cert; carries an encrypted
    authorization DPoP proof.

Network/auth flow (when Agent Gateway is enabled):

-   Agent -> Agent Gateway: mTLS, certificate-bound token.
-   Agent Gateway -> Google Cloud API: DPoP (mTLS terminates at the gateway).
-   CAA verifies the authorization DPoP proof and the resource DPoP proof were
    signed with the same private key from the agent identity pool.

In Cloud Logging:

-   Agent acting on its own authority -> entry shows the agent's SPIFFE identity
    only.
-   Agent acting on behalf of an end user (via auth manager) -> entry shows
    *both* the agent identity and the end-user identity.

When grepping logs the SPIFFE identity will look like the
`agents.global.org-...system.id.goog/resources/aiplatform/...` form (no
`spiffe://` scheme on most log fields — it's the principal form).

--------------------------------------------------------------------------------

## Required roles for the identity to function

Source:
<https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-identity.md.txt>

### Granted automatically on create

-   `roles/aiplatform.agentDefaultAccess` — project logging and core model
    inference (`aiplatform.endpoints.predict`).
-   `roles/aiplatform.agentContextEditor` — scoped access to the agent's own
    sessions, memories, and sandboxes.

> **Warning:** **Least-Privilege Guardrail**: Do **NOT** grant project-level
> `roles/aiplatform.expressUser` or `roles/aiplatform.user` to an Agent Identity
> (`principal://` or `principalSet://`). Those roles grant
> `aiplatform.reasoningEngines.{create,delete,update}` across the entire project,
> allowing a compromised agent to overwrite or delete sibling agents and escalate
> privileges across A2A boundaries.

### Recommended baseline (grant manually before/after deploy)

| Role | Why |
| :--- | :--- |
| `roles/serviceusage.serviceUsageConsumer` | Consume project quota + Agent Platform SDK |
| `roles/browser` | Basic Google Cloud project/hierarchy metadata lookup |
| `roles/logging.logWriter` | Emit structured application logs |
| `roles/monitoring.metricWriter` | Emit metrics |
| `roles/cloudapiregistry.viewer` | Discover tools via Cloud API Registry |

### Least-Privilege Agent-to-Agent (A2A) Invocation (`agentInvoker` + IAM Deny)

When Agent A invokes Agent B on Agent Runtime, create a minimal custom role and
bind it **at resource scope on Agent B only** (never project-wide). Because
`gcloud` does not expose a `reasoning-engines` IAM subcommand, perform a
read-modify-write via the Vertex AI v1 REST `:getIamPolicy` and `:setIamPolicy`
methods (preserving existing `bindings` and `etag`):

```bash
gcloud iam roles create agentInvoker \
  --project=PROJECT_ID \
  --title="Agent Runtime Invoker" \
  --permissions="aiplatform.reasoningEngines.query,aiplatform.reasoningEngines.get"

# 1. Fetch existing resource-level IAM policy & etag on Agent B
curl -s -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  "https://LOCATION-aiplatform.googleapis.com/v1/projects/PROJECT_ID/locations/LOCATION/reasoningEngines/TARGET_AGENT_B_ID:getIamPolicy" \
  -d '{}'

# 2. Apply updated bindings + etag via REST :setIamPolicy (note: raw REST wraps "policy", unlike gcloud iap web)
curl -s -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  "https://LOCATION-aiplatform.googleapis.com/v1/projects/PROJECT_ID/locations/LOCATION/reasoningEngines/TARGET_AGENT_B_ID:setIamPolicy" \
  -d '{
    "policy": {
      "etag": "ETAG_FROM_GET_IAM_POLICY",
      "version": 3,
      "bindings": [
        {
          "role": "projects/PROJECT_ID/roles/agentInvoker",
          "members": [
            "principal://agents.global.org-ORGANIZATION_ID.system.id.goog/resources/aiplatform/projects/PROJECT_NUMBER/locations/LOCATION/reasoningEngines/CALLER_AGENT_A_ID"
          ]
        }
      ]
    }
  }'
```

For defense in depth, attach an Organization/Project **IAM Deny policy** denying
`aiplatform.googleapis.com/reasoningEngines.{create,delete,update}` to
`principalSet://agents.global.org-ORGANIZATION_ID.system.id.goog/*`.

### Tool, Gateway, & Cross-Project Roles (often missed)

-   `roles/iamconnectors.user` on the `AuthProvider` resource — required for Auth
    Manager 2LO/3LO token brokering.
-   **IAP egress through Agent Gateway**:
    -   **Policy V1 (`gcloud iap web`)**: `roles/iap.egressor`
        (`iap.webServiceVersions.egressViaIAP`) bound with
        `--resource-type=agent-registry`.
    -   **UAP Policy V2 (`iapPolicyVersion: "V2"`)**:
        `iap.googleapis.com/resources.egressViaIAP` in an `AccessPolicy` bound to
        the governance project/folder/org.
-   **Cross-project Agent Runtime → Central Agent Gateway**: In the central
    gateway project, grant the deploying user `networkservices.agentGateways.use`
    + `networkservices.agentGateways.get` (`roles/networkservices.viewer`), and
    grant the runtime project's AI Platform Service Agent
    (`service-RUNTIME_PROJECT_NUMBER@gcp-sa-aiplatform.iam.gserviceaccount.com`)
    `roles/networkservices.viewer` or a custom role (`ae_agw_cross_project_sa` /
    `ar_agw_cross_project_sa` with
    `networkservices.agentGateways.get,networkservices.operations.get`). Both
    runtime and gateway must reside in the **same region**.

### Service-account mode (legacy default)

Default SA:
`service-<PROJECT_NUMBER>@gcp-sa-aiplatform-re.iam.gserviceaccount.com`
(`roles/aiplatform.reasoningEngineServiceAgent`). Custom SAs require explicit
least-privilege roles (e.g., `roles/storage.objectViewer` on staging buckets).

--------------------------------------------------------------------------------

## Granting roles — exact gcloud commands

Source:
<https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-identity.md.txt>

### Single agent

```bash
gcloud RESOURCE_TYPE add-iam-policy-binding RESOURCE_ID \
  --member="principal://agents.global.org-ORGANIZATION_ID.system.id.goog/resources/aiplatform/projects/PROJECT_NUMBER/locations/LOCATION/reasoningEngines/AGENT_ENGINE_ID" \
  --role="ROLE_NAME"
```

### All agents in a project (with org)

```bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="principalSet://agents.global.org-ORGANIZATION_ID.system.id.goog/attribute.platformContainer/aiplatform/projects/PROJECT_NUMBER" \
  --role=roles/serviceusage.serviceUsageConsumer
# Repeat for browser, cloudapiregistry.viewer, logging.logWriter, monitoring.metricWriter.
```

### All agents in an orgless project (`proj-`, NOT `project-`)

```bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="principalSet://agents.global.proj-PROJECT_NUMBER.system.id.goog/attribute.platformContainer/aiplatform/projects/PROJECT_NUMBER" \
  --role="ROLE_NAME"
```

### All agents across an org

```bash
gcloud RESOURCE_TYPE add-iam-policy-binding RESOURCE_ID \
  --member="principalSet://agents.global.org-ORGANIZATION_ID.system.id.goog/attribute.platform/aiplatform" \
  --role="ROLE_NAME"
```

### List the roles attached to a deployed (SA-mode) agent

```bash
gcloud projects get-iam-policy PROJECT_ID_OR_NUMBER \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:PRINCIPAL" \
  --format="value(bindings.role)"
```

For Agent-Identity mode, filter against the principal string instead:

```bash
gcloud projects get-iam-policy PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:principal://agents.global.org-ORG.system.id.goog/resources/aiplatform/projects/PROJECT_NUMBER/locations/LOCATION/reasoningEngines/AGENT_ID" \
  --format="value(bindings.role)"
```

--------------------------------------------------------------------------------

## Common debugging scenarios

### "Who is this request from?" — start here

1.  `GET` the ReasoningEngine, read `spec.identityType` and
    `spec.effectiveIdentity`.
2.  If `identityType` is `AGENT_IDENTITY`, the principal in IAM/audit logs will
    be the SPIFFE-style `agents.global....`. If `SERVICE_ACCOUNT`, expect a
    `service-...@gcp-sa-aiplatform-re.iam.gserviceaccount.com` (default) or
    custom SA email.
3.  Search audit logs for that exact string.

### `401 UNAUTHENTICATED` from a Google Cloud API

Source: <https://docs.cloud.google.com/iam/docs/troubleshoot-auth-manager.md.txt>

```
{ "error": { "code": 401, "status": "UNAUTHENTICATED",
  "message": "Request had invalid authentication credentials..." } }
```

This is usually **Context-Aware Access** rejecting an unbound or shared token,
not a missing IAM role. Confirm:

-   The call originates from the deployed runtime container (not local dev).
-   mTLS / DPoP path is intact (see CAA flow in section 4).
-   If you must work around (NOT recommended in production), set
    `GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES=False` via
    `env_vars` on `agent_engines.create(...)`. This disables token binding.

### `403 PERMISSION_DENIED` after switching to AGENT_IDENTITY

The Agent Runtime Service Agent's project-wide grants do **not** transfer to the
per-agent identity. The agent has only the two default roles. Add baseline roles
via the principalSet binding, then per-agent grants for sensitive resources.

### IAP / Agent Gateway egress denied

You need an `roles/iap.egressor` binding on the IAP/endpoint with the agent
principal as `members`. Per the policy assignment doc:

```json
{
  "bindings": [
    {
      "role": "roles/iap.egressor",
      "members": [
        "principal://agents.global.org-123456789012.system.id.goog/resources/aiplatform/projects/9876543210/locations/us-central1/reasoningEngines/1234567890123456789"
      ]
    }
  ],
  "version": 3
}
```

> **Warning:** `gcloud iap web set-iam-policy` requires a top-level IAM `Policy`
> JSON object (`{"bindings": [...]}`). Do **NOT** wrap `"bindings"` inside
> `{"policy": ...}` (which is used only by raw REST `:setIamPolicy` calls) —
> passing `{"policy": ...}` to `gcloud iap web set-iam-policy` submits an empty
> policy and **silently wipes all existing IAP bindings**!

Apply with `gcloud iap web set-iam-policy policy.json --project=PROJECT_ID
--region=LOCATION --resource-type=agent-registry` (adding
`--endpoint=ENDPOINT_UUID`, `--mcp-server=MCP_UUID`, or `--agent=AGENT_UUID`
**alongside** `--resource-type=agent-registry` for per-resource scope; omitting
`--resource-type=agent-registry` targets `IAPWebLocation` `iap_web` and ignores
child flags).

### `403` Egress / Auth Error Calling an MCP Server on Cloud Run

Choose the pattern matching how the Cloud Run service is secured:

1.  **Standard Cloud Run IAM (`roles/run.invoker`) — Service Account Impersonation Required**:
    Direct Agent Identity (`principal://...`) to Cloud Run OIDC authentication is
    **not natively supported**. Configure the agent code to use **Service Account
    impersonation** (`google.auth.impersonated_credentials.IDTokenCredentials`) to
    mint an OIDC ID token for the Cloud Run URL:
    -   Grant **`roles/iam.serviceAccountTokenCreator`** to the Agent Identity on
        the target Service Account.
    -   Grant **`roles/run.invoker`** to that target Service Account on the Cloud
        Run service, and authorize egress to the Cloud Run URL in Agent Registry +
        IAP/UAP.
2.  **Preview — Cloud Run Native IAP for MCP Servers (`--iap --functional-type=mcp-server`)**:
    Deploy or update the Cloud Run MCP service with native IAP instead of
    application-layer SA impersonation:
    ```bash
    gcloud beta run deploy MCP_SERVICE_NAME \
      --image=IMAGE_URL --region=REGION \
      --allow-unauthenticated --iap --functional-type=mcp-server
    ```
    Grant `roles/run.invoker` on the Cloud Run service to the IAP service agent
    (`service-PROJECT_NUMBER@gcp-sa-iap.iam.gserviceaccount.com`), grant
    `roles/iap.httpsResourceAccessor` on `--resource-type=cloud-run
    --service=MCP_SERVICE_NAME`, and target the `.run.app` short URL
    (`https://MCP_SERVICE_NAME-PROJECT_NUMBER.REGION.run.app`).

### Workforce Identity Federation (WIF) Console Errors or `gcloud` `error 13`

Federated workforce identities have limited Preview support across Agent Gateway
and Agent Registry control planes. Running `gcloud network-services
agent-gateways import` or `gcloud agent-registry` commands as a WIF user can fail
with `error 13: an internal error has occurred` or `403`, and granting broader
IAM roles to the federated principal does **not** fix it. Authenticate with a
standard Cloud Identity or Google Workspace account (see BKI #36).

### Agent can't use an auth provider (Auth Manager) & OIDC issuer reachability

Verify `roles/iamconnectors.user` is granted to the agent identity on the
`AuthProvider` resource, and confirm `.well-known/openid-configuration` and JWKS
endpoints are publicly reachable.

--------------------------------------------------------------------------------

## Code: pulling the bound token via ADC inside the agent

Source: <https://docs.cloud.google.com/iam/docs/auth-agent-own-identity.md.txt>

```python
from google.auth import default
from google.cloud import vision

# ADC automatically retrieves the Agent Identity token from the
# metadata server. No code changes vs. SA mode.
creds, project_id = default()
client = vision.ImageAnnotatorClient(credentials=creds, project=project_id)
```

If you opt out of CAA (token sharing), set on deploy:

```python
config={
  "env_vars": {
    "GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES": False,
  },
}
```

--------------------------------------------------------------------------------

## Quick reference — useful URLs

-   Agent identity overview (govern):
    <https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/agent-identity-overview.md.txt>
-   Agent identity overview (IAM mirror):
    <https://docs.cloud.google.com/iam/docs/agent-identity-overview.md.txt>
-   Agent identity in runtime (create / list / grant):
    <https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-identity.md.txt>
-   Setup identity & permissions:
    <https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime/setup.md.txt>
-   Manage agent access (SA mode):
    <https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/manage-agent-access.md.txt>
-   Principal identifiers (table of all forms):
    <https://docs.cloud.google.com/iam/docs/principal-identifiers.md.txt>
-   ReasoningEngineSpec REST reference:
    <https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1beta1/projects.locations.reasoningEngines.md.txt>
-   Context-Aware Access for agents (mTLS / DPoP):
    <https://docs.cloud.google.com/access-context-manager/docs/caa-agent-security.md.txt>
-   Auth manager troubleshooting (401 / connectors role):
    <https://docs.cloud.google.com/iam/docs/troubleshoot-auth-manager.md.txt>
-   Auth using agent's own identity (ADC sample):
    <https://docs.cloud.google.com/iam/docs/auth-agent-own-identity.md.txt>
-   Configure IAM policies (IAP egressor examples):
    <https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/configure-iam-policies.md.txt>
-   Three-identity delegation architecture:
    <https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/identity-delegation-architecture.md.txt>
-   Secure Cloud Run MCP servers with IAP:
    <https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/iap-cloud-run-mcp.md.txt>
