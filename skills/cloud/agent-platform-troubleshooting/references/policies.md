# Agent Platform Policies — Debugging Reference

Reference for diagnosing IAM, IAP, and Agent Gateway policy denials in the
**Google Cloud Gemini Enterprise Agent Platform**. Read this when an agent gets
a 403, when an MCP/agent/endpoint call is silently dropped, or when a freshly
applied policy "doesn't take."

## Table of Contents

-   [TL;DR for debugging](#tldr-for-debugging) (Lines 27-95)
-   [1. What "policies" means in the Agent Platform](#1-what-policies-means-in-the-agent-platform)
    (Lines 96-157)
-   [2. Assigning agent identity in IAM](#2-assigning-agent-identity-in-iam)
    (Lines 158-365)
-   [3. Testing and verifying policies](#3-testing-and-verifying-policies)
    (Lines 366-496)
-   [4. Common 403 / "Egress request is not authorized" causes](#4-common-403-egress-request-is-not-authorized-causes)
    (Lines 497-619)
-   [5. The IAP egressor role — exact placement](#iap-egressor-role) (Lines
    620-656)
-   [6. Quick command cheat sheet](#6-quick-command-cheat-sheet) (Lines 657-705)
-   [7. Debugging flowchart](#7-debugging-flowchart) (Lines 706-769)
-   [8. Sources](#8-sources) (Lines 770-779)

--------------------------------------------------------------------------------

## TL;DR for debugging

1.  **Agent Gateway uses IAP under the hood.** Policy denials surface as either
    IAP 403s or as `protoPayload.serviceName="iap.googleapis.com"` audit log
    entries. Always start in the IAP audit logs, not the agent runtime logs.
    (Source: policies/overview, policies/test-policies)

2.  **The role that allows agent egress is `roles/iap.egressor`** (display name
    "IAP-secured Egressor"). If an agent gets `Egress request is not
    authorized`, it is missing this role on the target resource — every other
    diagnosis is downstream of this. (Source: policies/assign-identity-iam)

3.  **Policies bind to Agent Registry resources, not to the agent.** The binding
    is set on the *target* (the Agent Registry, an MCP server, a destination
    agent, or an endpoint). The *member* is the source agent's principal.
    (Source: policies/overview, IAP agent overview)

4.  **Three layers, all must allow:** (a) IAM allow/deny on the Agent Registry
    resource, (b) IAP ingress policy on the destination, (c) underlying resource
    IAM (e.g. `roles/run.invoker` on the Cloud Run MCP server for the IAP
    service agent). Missing any one produces a 403; the layers are NOT
    substitutes. (Source: policies/overview, policies/assign-identity-iam)

5.  **Start in `DRY_RUN` mode.** In DRY_RUN, IAP writes denial entries to Cloud
    Audit Logs without blocking traffic. This is the *only* way to enumerate
    what would break before flipping `ENFORCE`. (Source: policies/overview,
    policies/test-policies)

6.  **`principal://` is exact; `principalSet://` is a hierarchy.**
    `principal://` binds a single agent. `principalSet://` binds a class of
    agents (e.g. "all reasoning engines in project 1234"). PrincipalSet bindings
    are convenient but propagate more slowly and depend on the agent's container
    attribute being correctly stamped at registration. (Source:
    policies/assign-identity-iam)

7.  **Agent identity is SPIFFE-formatted.** Agent Runtime / Gemini Enterprise
    agents use a `principal://agents.global.org-<ORG_ID>.system.id.goog/...`
    URI; DIY (Cloud Run) agents use a workload-identity-pool URI. Mixing the two
    forms in a single binding is a common source of "I gave it the role and it
    still 403s." (Source: policies/assign-identity-iam)

8.  **CEL conditions are evaluated per-request.** A binding with a condition
    that references `mcp.toolName` or `mcp.tool.isReadOnly` will deny when the
    attribute is absent or false. Suspect conditions before suspecting bindings.
    (Source: policies/overview)

9.  **The Cloud Run MCP server itself needs `roles/run.invoker` granted to the
    IAP service agent**
    (`service-PROJECT_NUMBER@gcp-sa-iap.iam.gserviceaccount.com`). This is
    independent of the agent's `iap.egressor` binding. (Source:
    policies/assign-identity-iam)

10. **`gcloud beta iap web get-iam-policy` is your primary inspection tool.**
    Use `--resource-type=agent-registry` (or
    `--agent`/`--mcp-server`/`--endpoint`) to see the effective policy on the
    right scope. (Source: policies/test-policies)

11. **Model Armor integration requires additional data-plane permissions.** If
    Model Armor is enabled on the gateway, the gateway proxy executes callouts
    to the Model Armor service. This requires `roles/modelarmor.user`,
    `roles/modelarmor.calloutUser`, and
    `roles/serviceusage.serviceUsageConsumer` to be granted to the **Service
    Extensions Service Agent** (`gcp-sa-dep`) in the consumer project.
    Crucially, these must be granted to the **consumer project's own service
    agent**. Do NOT grant them to the tenant's service agents. See
    `known-issues.md §13` (BKI 13) for details.

--------------------------------------------------------------------------------

## 1. What "policies" means in the Agent Platform

Source:
<https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/overview>

Agent Platform layers **two complementary policy systems**:

### 1a. IAM Policies (allow / deny)

-   Enforced by **Agent Gateway** via **Identity-Aware Proxy (IAP)**.
-   Control agent-to-service communication (agent → MCP server, agent → agent,
    agent → endpoint).
-   Use standard IAM bindings (member / role / condition) but applied through
    the IAP API surface (`gcloud beta iap web set-iam-policy`).
-   **The role for outbound agent traffic is `roles/iap.egressor`.**
-   Conditions use CEL with agent-aware variables.

### 1b. Semantic Governance Policies (SGP)

-   A **natural language** policy layer that uses Natural Language Constraints
    (NLC) to align tool invocations with user intent and business rules.
-   Operates on the LLM call shape, not the network shape. Out of scope for most
    403-class debugging — if you're seeing a 403 on the wire, it is IAM or IAP,
    not SGP.

### 1c. The IAP enforcement plane

-   **mTLS** terminates at Agent Gateway. Both sides authenticate with X.509
    certificates provisioned for the agent identity.
-   **DPoP (Demonstrable Proof of Possession)** binds tokens to the certificate
    so a stolen token can't be replayed.
-   The agent's identity travels in the request (not just a bearer token); IAP
    evaluates the IAM policy on the destination resource against that identity.

### 1d. How they layer

For an agent call to succeed, **all three** of the following must allow:

```
[ Source Agent ]
       │
       │ mTLS + DPoP, identity = principal://...
       ▼
[ Agent Gateway / IAP ]   ← Layer 1: IAM allow policy on the Agent Registry
       │                              resource grants roles/iap.egressor
       │                              to the source agent's principal.
       │
       │ Forwarded request, signed by IAP service agent
       ▼
[ Underlying resource ]   ← Layer 2: IAP ingress policy on the destination
       │                              (MCP server / endpoint / agent).
       │
       │                  ← Layer 3: The destination's *native* IAM
       ▼                              (e.g. roles/run.invoker on a Cloud Run
                                      service granted to
                                      service-<PROJECT_NUMBER>@gcp-sa-iap.iam.gserviceaccount.com)
```

A missing role at **any** layer produces a 403. Always check all three.

--------------------------------------------------------------------------------

## 2. Assigning agent identity in IAM

Source:
<https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/assign-identity-iam>

### 2a. Identity formats — pick the right one

**Agent Runtime + Gemini Enterprise agents** (the managed runtimes):

```
principal://TRUST_DOMAIN/AGENT_UNIQUE_IDENTIFIER
```

Concrete example:

```
principal://agents.global.org-123456789012.system.id.goog/resources/aiplatform/projects/9876543210/locations/us-central1/reasoningEngines/my-test-agent
```

The `TRUST_DOMAIN` is per-organization:
`agents.global.org-<ORG_ID>.system.id.goog`.

**DIY agents (anything you deploy on Cloud Run, GKE, etc.):**

```
principal://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/AGENT_SERVICE_ACCOUNT_IDENTIFIER
```

Concrete example:

```
principal://iam.googleapis.com/projects/1234567890/locations/global/workloadIdentityPools/my-agent-identity/subject/ns/default/sa/my-agent
```

Note this is a **workload identity pool** principal, not a plain
`serviceAccount:foo@...` member. Granting the role to the bare service account
will **not** authorize the agent through Agent Gateway.

### 2b. Roles you (the operator) need to manage policies

| Role                                    | Purpose                           |
| --------------------------------------- | --------------------------------- |
| `roles/iap.admin`                       | Set/get IAP IAM policies          |
| `roles/agentregistry.viewer`            | Browse the agent registry         |
| `roles/resourcemanager.projectIamAdmin` | Manage project IAM bindings       |
| `roles/networksecurity.admin`           | Configure Agent Gateway network   |
:                                         : policies                          :
| `roles/serviceextensions.admin`         | Manage service extensions used by |
:                                         : Agent Gateway                     :

### 2c. Roles you grant to the agent

To authorize an agent to egress through Agent Gateway, you must grant two roles
to the agent's identity:

1.  **`roles/iap.httpsGatewayUser`** (IAP-secured Web App User): Typically
    required on the **Gateway resource**. This allows the agent to connect to
    the gateway itself.
2.  **`roles/iap.egressor`** (IAP-secured Egressor): Required on the **Agent
    Registry** (or specific target resource within the registry). This allows
    the agent to egress to the destination.

Both roles are required. Granting `roles/editor` or even `roles/owner` to the
agent's principal will not substitute — IAP specifically checks for these roles.

### 2d. Minimal binding (agent → all resources in the registry)

`agents-iap-policy.json`:

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

Apply at the **Agent Registry** scope:

```bash
gcloud beta iap web set-iam-policy agents-iap-policy.json \
  --project=PROJECT_ID \
  --resource-type=agent-registry \
  --region=REGION
```

The same command takes `--folder=FOLDER_ID` or `--organization=ORG_ID` instead
of `--project` if you want a wider scope.

### 2e. Per-resource binding (agent → one MCP server)

Same JSON shape, narrower scope:

```bash
gcloud beta iap web set-iam-policy mcp-iap-policy.json \
  --project=PROJECT_ID \
  --region=REGION \
  --mcp-server=MCP_SERVER_NAME
```

The available narrow flags are `--agent`, `--mcp-server`, `--endpoint`. Pick the
one that matches the destination type.

### 2f. Conditional binding (CEL) — restrict to read-only tool calls

```json
{
  "policy": {
    "bindings": [
      {
        "role": "roles/iap.egressor",
        "members": [
          "principal://agents.global.org-123456789012.system.id.goog/resources/aiplatform/projects/9876543210/locations/us-central1/reasoningEngines/ae-agent"
        ],
        "condition": {
          "title": "Allow AE Agent Read-Only Egress to GitHub MCP server",
          "description": "Only read-only GitHubTool calls",
          "expression": "api.getAttribute('iap.googleapis.com/mcp.toolName', '') == 'GitHubTool' && api.getAttribute('iap.googleapis.com/mcp.tool.isReadOnly', false) == true"
        }
      }
    ]
  }
}
```

Available CEL attributes (non-exhaustive):

-   `mcp.toolName` — the tool the agent is invoking
-   `mcp.resourceName`
-   `mcp.method`
-   `mcp.tool.isReadOnly` — boolean
-   `mcp.tool.isDestructive` — boolean
-   `mcp.tool.isIdempotent` — boolean
-   `mcp.tool.isOpenWorld` — boolean
-   `request.auth.type`

If a condition's expression evaluates to anything other than `true`, the binding
does not match and the request is denied (assuming no other matching binding
allows it).

### 2g. PrincipalSet bindings — when to use, when to avoid

`principalSet://` lets you bind a *set* of agents in one go. Example: every
reasoning engine under project 1234 in the org:

```json
{
  "policy": {
    "bindings": [
      {
        "role": "roles/iap.egressor",
        "members": [
          "principalSet://agents.global.org-ORGANIZATION_ID.system.id.goog/attribute.platformContainer/aiplatform/projects/1234"
        ]
      }
    ]
  }
}
```

**When to use PrincipalSet:**

-   Granting access to a class of agents you cannot enumerate up front (e.g. all
    agents the data-science org will ever deploy in project 1234).
-   Coarse-grained "this whole project's agents may call this MCP server."

**When PrincipalSet causes pain (debug accordingly):**

-   **Membership depends on attributes stamped at agent registration.** A new
    agent that didn't pick up `attribute.platformContainer` correctly will not
    be a member of the set, even if it "looks the same" as other agents. If a
    brand-new agent gets `Egress request is not authorized` while existing
    agents work, suspect the attribute stamp before suspecting the policy.
-   **Slower propagation than direct `principal://` bindings.** PrincipalSet
    membership is computed; direct principal bindings are matched. If you just
    added the binding and a request still fails, give it a few minutes and
    re-check before re-tweaking.
-   **No condition support for membership** — you can attach a CEL condition to
    the binding, but you can't use CEL to define who's in the set.
-   **Harder to audit.** Audit logs show the *concrete* principal of the caller,
    not the PrincipalSet that allowed it. To prove which binding authorized a
    given call, you have to manually re-derive set membership.

**Rule of thumb:** for a small fixed roster of agents, prefer multiple
`principal://` entries in one binding. Reach for `principalSet://` only when the
roster is open-ended.

### 2h. Granting Cloud Run MCP servers to the IAP service agent

A Cloud Run-backed MCP server is invoked **by IAP**, not by the agent directly.
IAP signs the forwarded request as the IAP service agent, so the Cloud Run
service must let that service agent in:

```bash
gcloud beta run services add-iam-policy-binding SERVICE_NAME \
  --member='serviceAccount:service-PROJECT_NUMBER@gcp-sa-iap.iam.gserviceaccount.com' \
  --role='roles/run.invoker'
```

If this is missing, the symptom is a 403 from Cloud Run that surfaces to the
agent as a generic upstream failure — and **the IAP audit log will look clean**,
because IAP itself authorized the call. This is the most common "my IAM policy
looks right but it still 403s" cause.

--------------------------------------------------------------------------------

## 3. Testing and verifying policies

Source:
<https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/test-policies>

### 3a. Always validate in DRY_RUN first

Agent Gateway has two enforcement modes:

-   **`DRY_RUN`** — IAP logs disallowed communications to Cloud Audit Logs but
    **does not** block them. Traffic flows. Use this to enumerate every binding
    you're missing before flipping the switch.
-   **`ENFORCE`** — Disallowed communications are blocked with a 403.

Workflow:

1.  Define your policies.
2.  Set the gateway to `DRY_RUN`.
3.  Exercise your agents (run real workloads or a test harness).
4.  Pull DRY_RUN denial entries from Cloud Audit Logs.
5.  Add bindings to cover legitimate denials. Repeat until clean.
6.  Flip to `ENFORCE`.

### 3b. Inspect the effective IAM policy

```bash
# Registry-wide
gcloud beta iap web get-iam-policy \
  --project=PROJECT_ID \
  --resource-type=agent-registry \
  --region=REGION

# Per resource
gcloud beta iap web get-iam-policy \
  --project=PROJECT_ID \
  --region=REGION \
  --mcp-server=MCP_SERVER_NAME
```

Compare the printed `bindings[]` to what you expect. The exact `members` string
must match the agent's principal URI **byte-for-byte** — a typo in the trust
domain or an off-by-one in the project number is enough to fail.

### 3c. Read the audit logs

The single most useful filter for any Agent Gateway / IAP debugging session:

```
protoPayload.serviceName="iap.googleapis.com"
```

Combined with `severity=ERROR` and a recent time window, this surfaces denials.
In the Logs Explorer:

```
protoPayload.serviceName="iap.googleapis.com"
severity>=WARNING
timestamp>="2026-05-12T00:00:00Z"
```

Useful payload fields to project on:

-   `protoPayload.authenticationInfo.principalEmail` — for SA-backed callers
-   `protoPayload.authenticationInfo.principalSubject` — for SPIFFE / workload
    identity callers (this is where the agent's `principal://...` ends up)
-   `protoPayload.authorizationInfo[].resource` — the destination
-   `protoPayload.authorizationInfo[].permission` — typically
    `iap.webServices.accessViaIAP` or an `iap.tunnel*` permission
-   `protoPayload.authorizationInfo[].granted` — boolean
-   `protoPayload.status.code` and `protoPayload.status.message` — the deny
    reason (this is where `Egress request is not authorized` shows up)
-   `protoPayload.metadata` — DRY_RUN entries land here with extra context
    including the binding(s) that *would* have been required

To filter to **policy-denied** entries specifically, the Logs Explorer "Log
name" facet has a `policy` denied audit log stream — select it from the Query
builder pane.

To see Data Access logs (read calls, etc.), Data Access audit logs must be
enabled for the service. The viewer needs `roles/logging.privateLogViewer` to
see them in the Google Cloud console.

### 3d. Trigger and observe — the standard egress test

```
1. From the source agent, make a call that targets the MCP server / agent /
   endpoint you're trying to authorize.
2. tail the audit logs:
     # Note: --limit=20 limits payload size to the 20 most recent entries to prevent terminal output truncation.
     gcloud logging read \
       'protoPayload.serviceName="iap.googleapis.com"' \
       --project=PROJECT_ID \
       --limit=20 \
       --order=desc
3. Find the entry matching your principal and target.
4. If granted=false, read status.message and authorizationInfo[].permission
   to identify the missing role.
```

### 3e. Trigger and observe — the standard ingress test

For ingress (an external client → an agent through IAP), the failure mode is
typically a 403 in the **client's** response, not in the audit logs.

```
1. Issue the request from the external client.
2. If you get HTTP 403 with body containing "You don't have access" or
   similar, IAP rejected it.
3. Check the IAP audit log filtered as described in section 3d.
4. Verify the client's identity has roles/iap.httpsResourceAccessor (for
   web/HTTP) or roles/iap.tunnelResourceAccessor (for tunnel) on the
   destination resource.
```

### 3f. IAM Policy Troubleshooter

For any single denial, the **IAM Policy Troubleshooter** answers "why was X
denied permission Y on resource Z?" by walking up the resource hierarchy and
listing every binding considered.

```
Google Cloud console → IAM & Admin → Policy Troubleshooter
  Principal:  <copy from authenticationInfo.principalSubject>
  Resource:   <full resource name from authorizationInfo.resource>
  Permission: iap.webServices.accessViaIAP   (or the specific iap.tunnel*)
```

For Agent Platform principals, paste the full `principal://...` URI as the
principal — Policy Troubleshooter accepts SPIFFE-formatted principals.

--------------------------------------------------------------------------------

## 4. Common 403 / "Egress request is not authorized" causes

Source: synthesis of all three docs.

The error message you'll see in the audit log is literally:

```
Egress request is not authorized
```

The following section details common symptom → root cause → fix scenarios:

### 4a. Missing `roles/iap.egressor` binding

**Symptom:** Audit log entry with `protoPayload.status.message = "Egress request
is not authorized"` and `authorizationInfo[].granted = false` for permission
`iap.webServices.accessViaIAP`.

**Cause:** The agent's principal has no `roles/iap.egressor` binding on the
destination (or on the Agent Registry containing it).

**Fix:** Add the binding at the appropriate scope — see §2d / §2e.

### 4b. Wrong principal format

**Symptom:** Same audit log line as in section 4a. `gcloud beta iap web
get-iam-policy` shows a binding "for the agent" but the binding actually has the
wrong member URI.

**Cause:** Bound `serviceAccount:my-agent@project.iam.gserviceaccount.com`
instead of the workload-identity-pool URI; or used the Agent Runtime
`principal://` format for a DIY agent (or vice versa); or the `TRUST_DOMAIN` has
the wrong `org-<ORG_ID>` segment; or the project number in the URI is wrong.

**Fix:** Re-derive the agent's principal from the docs (§2a) and replace the
member string verbatim.

### 4c. Cloud Run MCP server doesn't trust IAP

**Symptom:** IAP audit log shows the call was **allowed** (granted=true), but
the agent reports an upstream 403. Cloud Run logs show `The request was not
authenticated` or a missing `run.invoker` permission.

**Cause:** The IAP service agent
(`service-<PROJECT_NUMBER>@gcp-sa-iap.iam.gserviceaccount.com`) doesn't have
`roles/run.invoker` on the Cloud Run service backing the MCP server.

**Fix:**

```bash
gcloud beta run services add-iam-policy-binding SERVICE_NAME \
  --member='serviceAccount:service-PROJECT_NUMBER@gcp-sa-iap.iam.gserviceaccount.com' \
  --role='roles/run.invoker'
```

### 4d. CEL condition evaluates to false

**Symptom:** The binding *exists* and the principal *matches*, but the audit log
shows `granted=false` with metadata indicating a condition did not pass.

**Cause:** A condition like
`api.getAttribute('iap.googleapis.com/mcp.tool.isReadOnly', false) == true`
denies any call where the attribute is missing or the tool isn't tagged
read-only. New tools without the `isReadOnly` annotation hit this.

**Fix:** Either tag the tool correctly in the MCP server's manifest, or broaden
/ remove the condition for that binding.

### 4e. PrincipalSet doesn't include the agent

**Symptom:** Brand-new agent gets `Egress request is not authorized` even though
sibling agents in the same project succeed against the same target.

**Cause:** The PrincipalSet is keyed off `attribute.platformContainer` (or
similar) and the new agent doesn't have that attribute set. This usually means
the agent was registered with a non-standard identifier, or the registration is
incomplete.

**Fix:** Re-register the agent through the supported runtime; or, as a
short-term unblock, add a direct `principal://...` binding for that one agent to
confirm the rest of the policy plane is correct.

### 4f. Wrong scope on `set-iam-policy`

**Symptom:** Policy looks correct in the JSON, `gcloud` returns success, but the
call still 403s.

**Cause:** Bound the policy at `--resource-type=agent-registry` (registry-wide)
when the destination is governed by a per-resource policy that lacks the
binding; or conversely. Per-resource policies don't *inherit* from registry-
level policies — they replace them for that resource.

**Fix:** Decide on the scope. For the common case — "this agent should reach
everything in the registry" — set at `--resource-type=agent-registry` and ensure
no narrower per-resource policy is overriding it. Inspect with `get-iam-policy`
at *both* scopes.

### 4g. Wrong scope on the principal URI for Agent Runtime agents

**Symptom:** Audit log shows the principal is
`principal://...reasoningEngines/<engine-id>` but your binding has
`principal://...reasoningEngines/<wrong-engine-id>`.

**Cause:** Re-deployed the agent and got a new reasoning engine ID; the policy
still references the old one.

**Fix:** Look up the current reasoning engine ID (`gcloud ai reasoning-engines
list`) and update the binding member.

### 4h. ENFORCE flipped before DRY_RUN was clean

**Symptom:** Sudden burst of `Egress request is not authorized` on calls that
"used to work."

**Cause:** Gateway was just switched to `ENFORCE` and the DRY_RUN denial set was
never fully addressed.

**Fix:** Flip back to `DRY_RUN`, drain the denial backlog (`severity>=WARNING
protoPayload.serviceName="iap.googleapis.com"` over the last hour), add
bindings, re-flip.

--------------------------------------------------------------------------------

## 5. The IAP egressor role — exact placement {#iap-egressor-role}

Source:
<https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/assign-identity-iam>

The Agent Platform's egress role is `roles/iap.egressor`. Note this is **not**
the same role used for traditional IAP TCP forwarding (which is
`roles/iap.tunnelResourceAccessor`). Don't confuse the two:

| Role                               | Purpose                                 |
| ---------------------------------- | --------------------------------------- |
| `roles/iap.egressor`               | Authorizes an **agent** to egress       |
:                                    : through Agent Gateway. This is what you :
:                                    : want for Agent Platform.                :
| `roles/iap.tunnelResourceAccessor` | Authorizes a **user/SA** to use TCP/SSH |
:                                    : tunneling through IAP to a VM.          :
:                                    : Unrelated to Agent Gateway egress.      :
| `roles/iap.httpsResourceAccessor`  | Authorizes a user to access an          |
:                                    : IAP-protected web app (ingress).        :

**Where to grant `roles/iap.egressor`:**

-   **Registry-wide** (most common): bind at `--resource-type=agent-registry`
    with no narrower selector. The agent can then reach any registered MCP
    server / agent / endpoint in the registry.
-   **Per resource** (least privilege): bind with `--mcp-server=NAME` (or
    `--agent=NAME` / `--endpoint=NAME`). The agent can only reach that one
    resource.

The binding always lives on the **destination** scope — never on the source
agent. The source agent appears as the *member*, not as the resource.

You can also bind at `--folder=FOLDER_ID` or `--organization=ORG_ID` for
multi-project setups. Inheritance follows the standard IAM resource hierarchy.

--------------------------------------------------------------------------------

## 6. Quick command cheat sheet

```bash
# --- Inspect ---

# Effective policy on the registry
gcloud beta iap web get-iam-policy \
  --project=PROJECT_ID \
  --resource-type=agent-registry \
  --region=REGION

# Effective policy on one MCP server
gcloud beta iap web get-iam-policy \
  --project=PROJECT_ID \
  --region=REGION \
  --mcp-server=MCP_SERVER_NAME

# --- Apply ---

# Set policy registry-wide
gcloud beta iap web set-iam-policy agents-iap-policy.json \
  --project=PROJECT_ID \
  --resource-type=agent-registry \
  --region=REGION

# --- Cloud Run MCP server prerequisite ---

gcloud beta run services add-iam-policy-binding SERVICE_NAME \
  --member='serviceAccount:service-PROJECT_NUMBER@gcp-sa-iap.iam.gserviceaccount.com' \
  --role='roles/run.invoker' \
  --region=REGION

# --- Tail audit logs for denials ---

# Note: --limit=20 fetches the recent 20 warning/error audit events while avoiding output buffer truncation.
gcloud logging read \
  'protoPayload.serviceName="iap.googleapis.com" severity>=WARNING' \
  --project=PROJECT_ID \
  --limit=20 \
  --order=desc \
  --format='value(timestamp, protoPayload.authenticationInfo.principalSubject, protoPayload.authorizationInfo[0].resource, protoPayload.status.message)'

# --- Same, in Logs Explorer query language ---
# protoPayload.serviceName="iap.googleapis.com"
# severity>=WARNING
# timestamp>="2026-05-12T00:00:00Z"
```

--------------------------------------------------------------------------------

## 7. Debugging flowchart

```
Agent call fails / hangs
        │
        ▼
Is there an entry in the IAP audit log?
  (filter: protoPayload.serviceName="iap.googleapis.com")
        │
   ┌────┴────┐
  yes        no  ─► Check the *destination* IAM (Cloud Run roles/run.invoker
   │                for the IAP service agent), or the destination's own
   │                logs. IAP didn't reject the call; something downstream did.
   │                (Cause 4c.)
   ▼
Does it say "Egress request is not authorized"?
        │
   ┌────┴────┐
  yes        no  ─► Read status.message; usually a clear hint
   │                (token expired, mTLS handshake, DPoP mismatch, etc.).
   ▼
Does authorizationInfo[].granted == false?
        │
   ┌────┴────┐
  yes        no  ─► Granted but still failed → DRY_RUN entry; gateway
   │                logged what *would* be denied. No action required if
   │                you're in DRY_RUN intentionally.
   ▼
Get the principal from authenticationInfo.principalSubject.
Get the resource from authorizationInfo[0].resource.
        │
        ▼
gcloud beta iap web get-iam-policy on that resource scope.
        │
        ▼
Is there a binding for roles/iap.egressor with that exact principal
(or a principalSet that contains it)?
        │
   ┌────┴────┐
  no         yes
   │          │
   │          ▼
   │     Does the binding have a condition?
   │          │
   │     ┌────┴────┐
   │    yes        no  ─► Principal mismatch: typo, wrong format
   │     │                (Agent Runtime vs DIY), wrong project number,
   │     │                or PrincipalSet missing attribute. (Causes 4b, 4e, 4g.)
   │     ▼
   │  Evaluate the CEL with the actual request attributes.
   │  Does it return true?
   │     │
   │ ┌───┴───┐
   │ no     yes  ─► Should have allowed. Check scope: maybe a per-resource
   │ │              policy is overriding the registry-wide one. (Cause 4f.)
   │ ▼
   │ Condition is the cause. Fix the tool annotation or
   │ broaden the condition. (Cause 4d.)
   ▼
Add the missing binding. (Cause 4a.)
```

--------------------------------------------------------------------------------

## 8. Sources

-   Policies overview:
    <https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/overview>
-   Assign agent identity in IAM:
    <https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/assign-identity-iam>
-   Test policies:
    <https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/test-policies>
-   Agent Gateway and IAP overview (cross-ref):
    <https://docs.cloud.google.com/iap/docs/agent-overview>
