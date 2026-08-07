# Agent Identity — Debugging Reference

Reference for diagnosing "who is this request from?" issues on Gemini Enterprise
Agent Platform / Agent Runtime (Reasoning Engines).

Primary source:
<https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/agent-identity-overview>
(mirrored at <https://docs.cloud.google.com/iam/docs/agent-identity-overview>)

## Table of Contents

-   [TL;DR for debugging](#tldr-for-debugging) (Lines 37-74)
-   [What "agent identity" means (vs service account, vs principal set)](#what-agent-identity-means-vs-service-account-vs-principal-set)
    (Lines 75-106)
-   [Identity format and trust domains](#identity-format-and-trust-domains)
    (Lines 107-139)
-   [Principal set forms (for IAM policy debugging)](#principal-set-forms-for-iam-policy-debugging)
    (Lines 140-162)
-   [How identities are created and bound to ReasoningEngines](#how-identities-are-created-and-bound-to-reasoningengines)
    (Lines 163-232)
-   [How to inspect / enumerate the identity at runtime](#how-to-inspect-enumerate-the-identity-at-runtime)
    (Lines 233-287)
-   [Token format / what shows up in logs](#token-format-what-shows-up-in-logs)
    (Lines 288-322)
-   [Required roles for the identity to function](#required-roles-for-the-identity-to-function)
    (Lines 323-369)
-   [Granting roles — exact gcloud commands](#granting-roles-gcloud) (Lines
    370-427)
-   [Common debugging scenarios](#common-debugging-scenarios) (Lines 428-499)
-   [Code: pulling the bound token via ADC inside the agent](#code-pulling-the-bound-token-via-adc-inside-the-agent)
    (Lines 500-525)
-   [Quick reference — useful URLs](#quick-reference-urls) (Lines 526-549)

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
    per-org or per-orgless-project and looks like
    `agents.global.org-<ORG_ID>.system.id.goog` or
    `agents.global.project-<PROJECT_NUMBER>.system.id.goog`.
-   The Agent Runtime SDK uses Application Default Credentials, which on the
    runtime automatically pull the Agent Identity token from the metadata server
    — no explicit code is required for it to take effect.
-   A new agent gets `roles/aiplatform.agentDefaultAccess` and
    `roles/aiplatform.agentContextEditor` only. For most real-world tools you
    must additionally grant: `roles/aiplatform.expressUser`,
    `roles/serviceusage.serviceUsageConsumer`, `roles/browser`,
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

Source: <https://docs.cloud.google.com/iam/docs/agent-identity-overview>

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

--------------------------------------------------------------------------------

## Identity format and trust domains

Source: <https://docs.cloud.google.com/iam/docs/agent-identity-overview>

SPIFFE ID (used internally / inside the X.509 SAN):

```
spiffe://<TRUST_DOMAIN>/resources/<SERVICE>/<RESOURCE_PATH>
```

IAM principal identifier (what you put in policies):

```
principal://<TRUST_DOMAIN>/resources/<SERVICE>/<RESOURCE_PATH>
```

Concrete examples:

-   Agent Runtime:
    `principal://agents.global.org-123456789012.system.id.goog/resources/aiplatform/projects/9876543210/locations/us-central1/reasoningEngines/my-test-agent`
-   Gemini Enterprise:
    `principal://agents.global.org-123456789012.system.id.goog/resources/discoveryengine/projects/9876543210/locations/global/collections/default_collection/engines/my-test-agent`

Trust domain (auto-provisioned when the Agent Platform API is first enabled):

-   Org present: `agents.global.org-<ORGANIZATION_ID>.system.id.goog`
-   Orgless project: `agents.global.project-<PROJECT_NUMBER>.system.id.goog`

Source:
<https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-identity>

--------------------------------------------------------------------------------

## Principal set forms (for IAM policy debugging)

Source: <https://docs.cloud.google.com/iam/docs/principal-identifiers>

Scope                               | Identifier
:---------------------------------- | :---------
Single agent                        | `principal://<TRUST_DOMAIN>/resources/<SERVICE>/<RESOURCE_PATH>`
All agents in a trust domain        | `principalSet://<TRUST_DOMAIN>/*`
All agents in a project             | `principalSet://<TRUST_DOMAIN>/attribute.platformContainer/aiplatform/projects/<PROJECT_NUMBER>`
All agents in an org                | `principalSet://agents.global.org-<ORG_ID>.system.id.goog/attribute.platform/aiplatform`
DIY agents (workload identity pool) | `principal://iam.googleapis.com/projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL>/subject/ns/<NS>/sa/<SA>`

Tips when debugging:

-   If you see
    `principalSet://...attribute.platformContainer/aiplatform/projects/<num>` in
    a binding, that is *all* agents in that project. A binding here grants every
    agent in the project the role — useful for shared roles (logging/quota), bad
    for sensitive resources.
-   The `attribute.platform/aiplatform` set covers an *entire org*.

--------------------------------------------------------------------------------

## How identities are created and bound to ReasoningEngines

Source:
<https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-identity>
Source:
<https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1beta1/projects.locations.reasoningEngines>

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
<https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-identity>

### Read the effective identity (authoritative)

The `spec.effectiveIdentity` field on the ReasoningEngine GET response is the
single source of truth. Possible shapes (per the REST reference):

-   `service-{project}@gcp-sa-aiplatform-re.googleapis.com` — `SERVICE_AGENT`
-   `{name}@{project}.gserviceaccount.com` — `SERVICE_ACCOUNT`
-   `agents.global.{org}.system.id.goog/resources/aiplatform/projects/{project}/locations/{location}/reasoningEngines/{re}`
    — `AGENT_IDENTITY`

Example REST response excerpt:

```json
{
  "spec": {
    "effectiveIdentity": "agents.global.org-ORGANIZATION_ID.system.id.goog/resources/aiplatform/projects/PROJECT_ID/locations/LOCATION/reasoningEngines/AGENT_ENGINE_ID"
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
<https://docs.cloud.google.com/access-context-manager/docs/caa-agent-security>
Source:
<https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-identity>

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
<https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-identity>

### Granted automatically on create

-   `roles/aiplatform.agentDefaultAccess` — basic project-wide logging, model
    calling.
-   `roles/aiplatform.agentContextEditor` — limit to the agent's own sessions,
    memories, sandboxes.

### Recommended baseline (grant manually before/after deploy)

| Role                                      | Why                         |
| :---------------------------------------- | :-------------------------- |
| `roles/aiplatform.expressUser`            | Inference, sessions, memory |
:                                           : access                      :
| `roles/serviceusage.serviceUsageConsumer` | Use project quota + Agent   |
:                                           : Platform SDK                :
| `roles/browser`                           | Basic Cloud functionality   |
:                                           : (resource enumeration)      :
| `roles/logging.logWriter`                 | Write logs from the agent   |
| `roles/monitoring.metricWriter`           | Emit metrics                |
| `roles/cloudapiregistry.viewer`           | Look up tools via Cloud API |
:                                           : Registry                    :

### Tool-/MCP-specific (often missed)

-   `roles/iamconnectors.user` on the auth-provider resource — required for the
    agent to use auth manager / OAuth providers. Source:
    <https://docs.cloud.google.com/iam/docs/troubleshoot-auth-manager>
-   `roles/iap.egressor` — for any IAP-protected egress (e.g.
    agent-to-MCP-server, agent-to-agent through Agent Gateway). Bound at the
    gateway/endpoint, not on the agent. Source:
    <https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/assign-identity-iam>

### Service-account mode (legacy default)

Default SA:
`service-<PROJECT_NUMBER>@gcp-sa-aiplatform-re.iam.gserviceaccount.com` with
`roles/aiplatform.reasoningEngineServiceAgent`. Custom SAs additionally need
`roles/storage.objectViewer` (read user GCS) and `roles/aiplatform.user` (use
Agent Runtime extensions).

--------------------------------------------------------------------------------

## Granting roles — exact gcloud commands {#granting-roles-gcloud}

Source:
<https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-identity>

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
# Repeat for browser, expressUser, cloudapiregistry.viewer, logging.logWriter, monitoring.metricWriter.
```

### All agents in an orgless project

```bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="principalSet://agents.global.project-PROJECT_NUMBER.system.id.goog/attribute.platformContainer/aiplatform/projects/PROJECT_NUMBER" \
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

Source: <https://docs.cloud.google.com/iam/docs/troubleshoot-auth-manager>

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
  "policy": {
    "bindings": [
      {
        "role": "roles/iap.egressor",
        "members": [
          "principal://agents.global.org-123456789012.system.id.goog/resources/aiplatform/projects/9876543210/locations/us-central1/reasoningEngines/my-test-agent"
        ]
      }
    ]
  }
}
```

Apply with `gcloud beta iap web set-iam-policy ...
--resource-type=agent-registry` or `--endpoint=ENDPOINT_ID` depending on target.

### Agent can't use an auth provider (auth manager)

Verify `roles/iamconnectors.user` is granted to the agent identity on the
auth-provider resource.

### OIDC / OAuth issuer reachability

`.well-known/openid-configuration` and JWKS endpoints must be publicly
reachable; otherwise auth manager cannot validate the third-party provider.

--------------------------------------------------------------------------------

## Code: pulling the bound token via ADC inside the agent

Source: <https://docs.cloud.google.com/iam/docs/auth-agent-own-identity>

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

## Quick reference — useful URLs {#quick-reference-urls}

-   Agent identity overview (govern):
    <https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/agent-identity-overview>
-   Agent identity overview (IAM mirror):
    <https://docs.cloud.google.com/iam/docs/agent-identity-overview>
-   Agent identity in runtime (create / list / grant):
    <https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-identity>
-   Setup identity & permissions:
    <https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime/setup>
-   Manage agent access (SA mode):
    <https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/manage-agent-access>
-   Principal identifiers (table of all forms):
    <https://docs.cloud.google.com/iam/docs/principal-identifiers>
-   ReasoningEngineSpec REST reference:
    <https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1beta1/projects.locations.reasoningEngines>
-   Context-Aware Access for agents (mTLS / DPoP):
    <https://docs.cloud.google.com/access-context-manager/docs/caa-agent-security>
-   Auth manager troubleshooting (401 / connectors role):
    <https://docs.cloud.google.com/iam/docs/troubleshoot-auth-manager>
-   Auth using agent's own identity (ADC sample):
    <https://docs.cloud.google.com/iam/docs/auth-agent-own-identity>
-   Assign identity IAM policies (IAP egressor examples):
    <https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/assign-identity-iam>
