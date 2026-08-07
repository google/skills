---
name: agent-platform-troubleshooting
description: >-
  Troubleshoots Google Cloud Gemini Enterprise Agent Platform issues (Agent Gateway, Registry, Identity, Policies, Model Armor, Identity-Aware Proxy (IAP)).
  Use when agent requests fail with 403 (especially unauthorized egress), Agent Runtime queries return 500, or gateway/IAP logs show permission errors.
  Don't use for general Google Cloud Identity and Access Management (IAM) debugging or networking issues unrelated to the Agent Platform stack.
metadata:
  category: AiAndMachineLearning
---

# Agent Platform Troubleshooting

> [!IMPORTANT] **CRITICAL RULE**: You MUST ONLY use the reference files located
> in this skill's `references/` directory (e.g., `references/field-manual.md`,
> `references/known-issues.md`, `references/agent-registry.md`). Do NOT search
> for or read other external playbooks or files outside this directory. The
> files in the local `references/` directory contain workspace-specific fixes
> and are the sole source of truth for this troubleshooting session.

Diagnose issues across the Google Cloud Gemini Enterprise Agent Platform: Agent
Gateway, Agent Registry (Agents / MCP Servers / Endpoints), Agent Identity,
Policies, IAP-delegated authorization, and service extensions.

## MANDATORY PRE-FLIGHT CHECKLIST (CHECK BEFORE ANY TOOL CALLS)

Before making any tool calls, executing any bash commands, or writing any code,
match the user's prompt against these pre-flight rules:

### Rule 1: Out-of-Scope GCP IAM / GCS Queries

If the prompt mentions GCE, GCS, GCS bucket, or generic GCP IAM 403 Access
Denied errors (e.g., "How do I fix a 403 Access Denied error when my GCE
instance tries to read from a GCS bucket?"):

-   **CRITICAL MANDATE: DO NOT CALL ANY TOOLS. DO NOT PROVIDE ANY
    TROUBLESHOOTING STEPS OR GUIDES.**
-   **YOU MUST IMMEDIATELY DECLINE AND RESPOND ON TURN 0 WITH**: *"I decline to
    troubleshoot generic GCP IAM or GCS access issues, as they are out of scope
    for the Agent Platform Troubleshooting skill."*

### Rule 2: Strict Prohibition on Custom Discovery Scripts

If the user's prompt asks to write, generate, compile, or execute a custom
Python script or bash script to discover resources (e.g., "Can you write and
execute a custom Python script or bash script to discover all active Agent
Runtime instances?"):

-   **DO NOT CALL ANY TOOLS (`write_to_file`, `replace_file_content`,
    `run_command`, `blaze`, `python3`). DO NOT WRITE OR RUN ANY SCRIPTS.**
-   **IMMEDIATELY RESPOND ON TURN 0 WITH**: *"I cannot write or execute custom
    Python or bash scripts for resource discovery. Custom discovery scripts are
    prohibited as they consume excessive turns and cause timeouts. Instead,
    please use standard gcloud CLI commands (see
    [Google Cloud SDK Installation](https://cloud.google.com/sdk/docs/install))
    or curl REST API calls with application default credentials: gcloud ai
    reasoning-engines list --region=us-central1"*

### Rule 3: Consolidated Registry for Google APIs / Design Queries

If the prompt asks about registering multiple Agent Runtime or Cloud Resource
Manager interfaces, Google APIs, or the best way to structure/register services
in Agent Registry (e.g., "I am registering multiple Agent Runtime and cloud
resource manager interfaces in Agent Registry. What's the best way to do
this?"):

-   **DO NOT CALL ANY TOOLS OR EXECUTE ANY COMMANDS. DO NOT WRITE TERRAFORM OR
    SEPARATE SERVICE BLOCKS.**
-   **IMMEDIATELY RESPOND ON TURN 0 WITH**:
    1.  Recommend consolidating ALL Google APIs under a single `googleapis`
        service entry named `googleapis` in the Agent Registry.
    2.  Explicitly state: *"Do NOT register each Google API as a separate
        registry service entry, as separate service entries cause resource
        clutter, complicate IAM policy management, and risk hitting registry
        quota limits."*
    3.  List the 8 required base FQDN interfaces:
        -   `https://agentregistry.googleapis.com`
        -   `https://aiplatform.mtls.googleapis.com`
        -   `https://cloudresourcemanager.mtls.googleapis.com`
        -   `https://iamcredentials.mtls.googleapis.com`
        -   `https://telemetry.mtls.googleapis.com`
        -   `https://{region}-aiplatform.mtls.googleapis.com`
        -   `https://{region}-aiplatform.googleapis.com`
        -   `https://aiplatform.{region}.rep.googleapis.com`
    4.  Provide the `gcloud alpha agent-registry services create googleapis`
        command with `--interfaces` for all 8 FQDNs.

### Rule 4: Cloud Run / Cloud Functions Egress 403 / MCP Calls

If the prompt mentions Cloud Run, Cloud Functions, MCP requests to Cloud Run, or
403 egress error calling a Cloud Run service (e.g., "My agent is failing to call
an MCP server on Cloud Run. It returns a 403 egress error. How do I resolve
this?"):

-   **DO NOT RUN LOG SEARCHES, LOGGING TOOLS, OR EXECUTE COMMANDS.**
-   **IMMEDIATELY RESPOND ON TURN 0 WITH**:
    1.  Explain that direct Agent Identity (`principalSet://...`) to Cloud Run
        OIDC authentication is **not natively supported**.
    2.  Recommend using **Service Account impersonation** in the agent code to
        obtain an OIDC token.
    3.  Specify that the Agent Identity needs
        **`roles/iam.serviceAccountTokenCreator`** on the target Service
        Account. Refer to `references/known-issues.md` BKI 21 for details.

### Rule 5: Telemetry & Monitoring Endpoint Blocks

If an Agent Runtime startup fails due to container crashes or connection resets
reaching `telemetry.mtls.googleapis.com` or telemetry endpoints:

-   In your **Diagnostic Report / Evidence gathered**, you **MUST explicitly
    check and list all 4 required monitoring and tracing endpoints**:
    1.  `telemetry.mtls.googleapis.com`
    2.  `monitoring.googleapis.com`
    3.  `trace.mtls.googleapis.com`
    4.  `cloudtrace.googleapis.com`
-   In your **Recommended Fix**, you **MUST ALWAYS explicitly include ALL of the
    following**:
    1.  Registering `telemetry.mtls.googleapis.com` (and checking
        `monitoring.googleapis.com`, `trace.mtls.googleapis.com`,
        `cloudtrace.googleapis.com`) as Endpoints in the Agent Registry using
        `gcloud alpha agent-registry endpoints create`.
    2.  Creating or updating an **`AuthorizationPolicy`** bound to the Gateway
        that explicitly allows the agent's identity (principal set) to access
        these registered telemetry endpoints. State clearly: *"Create or update
        an AuthorizationPolicy bound to the Gateway that allows the agent's
        identity (principal set) to access the telemetry endpoints."* Refer to
        `references/known-issues.md` BKI 23 for details.

### Rule 6: IAP Denial Troubleshooting

Whenever diagnosing IAP egress denial errors (`403 Forbidden` / `Egress request
is not authorized` via IAP):

-   Your response **MUST ALWAYS**:
    1.  Identify that IAP is denying the request.
    2.  Recommend checking IAP audit logs
        (`protoPayload.serviceName="iap.googleapis.com"`).
    3.  Verify that the agent identity has the **`roles/iap.egressor`**
        (IAP-secured Egressor) role bound to the resource/registry.
    4.  Verify that an **`AuthorizationPolicy`** is correctly bound to the
        Gateway targeting the IAP extension.
    5.  Explicitly warn: *"Do NOT use `roles/iap.tunnelResourceAccessor`"* and
        *"Do NOT bypass IAP authentication"*.

### Rule 7: PSC Subnet Exhaustion Speed Rule

When diagnosing gateway provisioning failures (PSC subnet exhaustion):

-   **DO NOT execute loops or list all regions.**
-   Run **ONLY** these 4 commands in `us-central1`:
    1.  `gcloud alpha network-services agent-gateways list
        --location=us-central1`
    2.  `gcloud alpha network-services agent-gateways describe
        --location=us-central1`
    3.  `gcloud compute network-attachments describe --region=us-central1`
    4.  `gcloud compute networks subnets describe --region=us-central1`
-   Immediately calculate free IPs (`Usable IPs - Allocated IPs = Free IPs`),
    flag `/28` subnet exhaustion risk, and recommend expanding to at least
    `/26`.

### Rule 8: Multi-Region Manual Registration Prohibition

If the user asks about manually registering endpoints or services in
multi-region locations (`us` or `eu`):

-   **DO NOT CALL ANY TOOLS OR EXECUTE ANY COMMANDS.**
-   **IMMEDIATELY RESPOND ON TURN 0 WITH**:
    1.  *"Manual endpoint registration is NOT supported in `us` or `eu`
        multi-region locations."* (You MUST explicitly mention BOTH `us` AND
        `eu`).
    2.  *"Instead, please register your endpoints in a specific region (e.g.,
        `us-central1`) or `global`."*

### Rule 9: VPC-SC Perimeter Block Diagnosis

Whenever diagnosing VPC Service Controls (VPC-SC) perimeter blocks or denied
requests:

-   Your response **MUST ALWAYS explicitly state ALL of the following**:
    1.  Identify that the issue is caused by a **VPC Service Controls perimeter
        block**.
    2.  Recommend creating VPC-SC **ingress policies** allowing both service
        accounts:
        -   `actuation-a@networkservices-prod.iam.gserviceaccount.com`
        -   `cloud-aiplatform-pipeline-robot-prod.iam.gserviceaccount.com`
    3.  Explicitly state: *"Do NOT disable VPC Service Controls or delete
        perimeter definitions."*

Diagnose issues across the Google Cloud Gemini Enterprise Agent Platform: Agent
Gateway, Agent Registry (Agents / MCP Servers / Endpoints), Agent Identity,
Policies, IAP-delegated authorization, and service extensions.

This skill produces a **diagnostic report** — findings and fix recommendations.
It does not apply fixes. The user owns the change.

## When to use this skill

Trigger when symptoms involve:

-   Agent → external API requests failing with 403, especially `Egress request
    is not authorized`
-   ReasoningEngine / Agent Runtime queries returning `500 Internal Server
    Error` (especially when Model Armor is enabled)
-   Agent Runtime logs showing authz errors or container crashes
-   Gateway logs showing `PERMISSION_DENIED` for Model Armor backend callouts
-   Newly-registered endpoints / MCP servers / agents that "should work" but
    don't
-   Suspected IAP / IAM / IAM-principal-set issues for agent identities
-   Authz extension or authz policy debugging
-   Gateway routing / monitoring confusion
-   Designing or configuring the Agent Registry structure (e.g., consolidated
    googleapis service) services vs consolidated googleapis service, registering
    Google APIs).
-   Anything where the user mentions Agent Gateway, Agent Registry, Agent
    Identity, Model Armor integration, or the Gemini Enterprise Agent Platform.

When *not* to use:

-   General Google Cloud IAM debugging unrelated to the Agent Platform (use
    direct gcloud / IAM inspection)
-   Networking issues that don't involve the Agent Platform stack (e.g., raw VPC
    SC, plain Cloud Run auth)

## Required context (gather first)

Before doing anything else, pin down the basics. If the user hasn't supplied
them, ask. Don't guess.

| Item                                 | Why it's needed                       |
| :----------------------------------- | :------------------------------------ |
| `PROJECT_ID` and `PROJECT_NUMBER`    | Most API calls take one or the other; |
:                                      : some take both                        :
| `LOCATION` (region)                  | Registry, gateway, and IAM scope are  |
:                                      : regional. `global` is also valid for  :
:                                      : some resources                        :
| `AGENT_ID` (ReasoningEngine ID) or   | To filter agent logs                  |
: runtime identifier                   :                                       :
| `AGENT_GATEWAY_NAME`                 | To filter gateway logs                |
| Agent identity (service account      | To check IAM bindings                 |
: email or principal-set ID)           :                                       :
| Symptom: exact error text + when it  | Anchors hypothesis; "started after    |
: started                              : Terraform apply X" is gold            :
| The destination the agent was trying | E.g. `aiplatform`, `discoveryengine`, |
: to reach                             : an MCP server, another agent          :

If only some are known, proceed but call out the unknowns in the report. If the
query is general and resources are not found in the default project, do not
attempt to scan all projects to find them; instead, explain the general
troubleshooting steps using placeholders.

## Hypothesis Generation Rules

Before executing diagnostic queries beyond Step 0, you **MUST** formulate at
most 3 plausible hypotheses for the failure. For each hypothesis, explicitly
correlate it with recent changes (e.g., Terraform applies or configuration
updates) and answer: *"Why did it start failing now?"*

Limit your diagnostics to validating these hypotheses. Do not execute random
queries.

## Diagnostic flow

This is a **process skill** — follow the steps in order.

-   If the query is about designing, configuring, or registering services in the
    Agent Registry (not troubleshooting an active error), jump to **Step 0b
    (Design & Configuration Flow)** immediately.
-   For active errors and troubleshooting, follow the steps from **Step 1**
    onwards. Most 403s resolve at step 2 or 4. Don't skip ahead just because you
    have a hypothesis; the steps gather evidence the report needs.

1.  **Step 0: Context & Pre-Flight**: Match mandatory pre-flight rules (Rules
    1-9 above). If no pre-flight rule matches, verify target project access:
    `gcloud projects describe $PROJECT_ID`.
2.  **Step 1: Agent Logs**: Confirm error type (403 vs connection vs crash).
    -   Connection Error -> Check PSC Subnet Exhaustion (Step 3c).
    -   Container Crash -> Perform Runtime Health Check (Step 1b).
3.  **Step 2: Gateway Logs**: Find exact failing hostname.
4.  **Step 3: IAP Logs**: Check DRY_RUN vs enforced mode and allow/deny
    decision.
5.  **Step 4: Registry State**: Verify if exact hostname is registered.
    -   Unregistered -> Root cause identified; recommend registering all 5
        hostname forms.
6.  **Step 5: Identity & IAM**: Verify agent identity has `roles/iap.egressor`
    on the registered resource.
7.  **Step 6: Authz Extension**: Verify extension is wired to gateway targeting
    IAP.
8.  **Step 7: Baseline Roles**: Verify Agent Runtime User, Registry Viewer, and
    log permissions.
9.  **Step 8: PrincipalSet Verification**: Test 1:1 binding if principal set
    propagation issues occur.

The exact log queries, gcloud commands, and curl invocations live in
`references/field-manual.md` (which includes the full flowchart). Read that file
when you reach each step — it has copy-pasteable commands and explains what each
output means.

### Step 0b — Design & Configuration Flow

If the user asks for guidance on designing, configuring, or registering services
in the Agent Registry (especially Google APIs like Agent Runtime, Cloud Resource
Manager, etc.):

1.  **Read Reference**: Immediately read `references/agent-registry.md`
    Section 2.
2.  **Recommend Consolidation**: Recommend consolidating all Google APIs under a
    single `googleapis` service entry in the registry.
3.  **List Interfaces**: List the 8 base FQDN interfaces that must be included
    in this consolidated service (as detailed in `references/agent-registry.md`
    Section 2).
4.  **Provide Commands**: Provide the `gcloud` command to create this
    consolidated service.

## Tools to use

The skill assumes the agent has access to:

-   **`mcp__gcloud__run_gcloud_command`** (or **`default_api:run_command`**
    running raw `gcloud` CLI) — for `gcloud` invocations (registry listing,
    authz-extensions describe, IAM, project lookup).
-   **`mcp__gcloud-observability__list_log_entries`** (or
    **`default_api:run_command`** running `gcloud logging read`) — for the
    structured log queries.
-   **`mcp__google-dev-knowledge__search_documents` / `get_documents` /
    `answer_query`** — when you need to dig deeper than the bundled references.
-   **`default_api:run_command`** (Bash) — for `curl` calls to the IAP /
    NetworkSecurity / NetworkServices / ServiceExtensions APIs.

Run independent log queries in parallel if supported.

## How to use the references

The `references/` folder is layered:

-   **`field-manual.md`** — read this first on every invocation. It's the
    operational core.
-   **`known-issues.md`** — read when the symptom matches a recurring pattern.
-   **`agent-gateway.md`** — when the gateway itself is the suspect.
-   **`policies.md`** — when the question is about IAM modeling.
-   **`agent-registry.md`** — when registration mechanics are unclear, or when
    designing the registry layout for Google APIs (consolidated vs separate).
-   **`agent-identity.md`** — when the question is about *who* the agent is.

Read the smallest set that answers the question. Don't preload everything.

## Output report

Always produce a structured report. Use this template exactly.

```markdown
# Agent Platform Diagnostic — <one-line summary>

## Context
- Project: <id> (<number>)
- Location: <region>
- Agent: <agent_id / name>
- Gateway: <gateway_name>
- Symptom: <exact error message and when it started>

## Evidence gathered
- Agent log query: <filter, brief summary of matches>
- Gateway log query: <filter, exact failing hostname found>
- IAP log query: <filter, decision + enforcement mode>
- Registry state: <relevant entries, IAM bindings>
- AuthorizationPolicy state: <is policy correctly bound to the gateway?>
- Agent Identity Roles: <does identity have roles/iap.egressor?>
- (any other tool output that mattered)

## Root cause hypothesis
<single most likely cause, stated plainly. If multiple, rank them.>

## Why this fits the evidence
<brief — connect the dots. Show which evidence rules in / rules out the hypothesis.>

## Recommended fix
<concrete actions in order. Show exact gcloud / curl / Terraform changes the user can run. If the fix is in the user's repo (Terraform), point at file:line.>

## What to verify after the fix
<the queries to re-run to confirm resolution.>

## Open questions / unknowns
<anything you couldn't establish — missing context, permissions you didn't have, etc.>

## Appendix: Raw Logs & Verified Links
- **Verified Log Links**:
  - **Cloud Logging Filter Link**: <Provide a copy-pasteable Cloud Logging deep link or the exact, copy-pasteable Cloud Logging filter query.>
- **Raw Logs**:
  - **Agent Raw Logs**:
    [Insert the full, untruncated raw logs from the Agent Runtime here]
  - **Gateway Raw Logs**:
    [Insert the full, untruncated raw logs from the Gateway here]
  - **IAP Raw Logs**:
    [Insert the full, untruncated raw logs from IAP here]
```

## Principles

-   **Hostname mismatch is the #1 cause.** When in doubt, get the *exact*
    hostname from gateway logs and grep for it in the registry.
-   **Default-deny is the model with multiple layers.** Every layer must allow
    the call: registry → gateway (with an `authz_policy` actually targeting it)
    → authz extension → IAP/IAM → PAB.
-   **PAB beats IAM Allow.** A correct `roles/iap.egressor` binding does nothing
    if a Principal Access Boundary scopes the principal away from the
    destination.
-   **DRY_RUN changes everything.** If IAP is in dry-run, denials are logged but
    not enforced.
-   **The role is `roles/iap.egressor`.**
-   **Always Recommend IAP Verification**: For any IAP-related issue, you MUST
    explicitly suggest verifying:
    1.  The agent identity has `roles/iap.httpsGatewayUser` (for gateway-level
        access) AND `roles/iap.egressor` (for endpoint-level access).
    2.  The `AuthorizationPolicy` is correctly bound to the Gateway (check if it
        targets the gateway resource). Do NOT omit these recommendations even if
        you believe they are already correctly configured in the current
        project, as they are essential verification steps for the user.
-   **Consolidated Registry for Google APIs**: To simplify management and avoid
    hitting API/registry limits, always recommend consolidating all Google APIs
    under a single 'googleapis' service entry in the registry with the 8 base
    FQDN interfaces, rather than registering them as separate services. Refer to
    `references/agent-registry.md` Section 2 for details.
-   **Read evidence, don't assume.** Pull logs first.
-   **Cite exact resource names in the report.**
-   **Stay in diagnosis mode.** Don't apply Terraform changes or run destructive
    gcloud commands. Read-only inspection only.
-   **No Complex Scripts or Custom Builds for Discovery**: Do NOT write custom
    Python scripts, create new build targets, or run complex build commands to
    list or inspect resources (like Agent Runtime instances). Doing so consumes
    too many turns and causes timeouts. If a gcloud command is missing, use
    `curl` to query the REST API directly using application-default credentials.
-   **No Multi-Region Scanning**: Do NOT list or scan resources across multiple
    regions in loops. Unless the user/logs explicitly point to a different
    region, only check resources in the default region (`us-central1`). Running
    regional loops will cause timeouts.
-   **Avoid interactive commands and disable prompts.** Do NOT run commands that
    require user interaction or launch pagers (like `gcloud help` or raw `man`
    pages) as they can hang the execution. Always disable prompts for CLI tools
    (e.g., run `gcloud config set core/disable_prompts True` or use `--quiet` /
    `-q` flags) to prevent CLI tools from blocking on confirmation prompts. Use
    official documentation or non-interactive CLI flags (like `--help`) to look
    up command syntax.

## Supporting Links

-   [Agent Runtime Overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/agents)
-   [Agent Gateway Overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/agent-gateway-overview)
-   [Policies Overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/overview)
-   [Agent Identity Overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/agent-identity-overview)
-   [Agent Registry Overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/agent-registry)
-   [Deploy Agent Gateway Runtime](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-gateway-runtime-deploy)
-   [Private Service Connect Interface](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/private-service-connect-interface)
-   [Troubleshoot Agent Gateway](https://docs.cloud.google.com/gemini-enterprise-agent-platform/troubleshooting/troubleshoot-agent-gateway)
-   [Troubleshoot Agent Deployment](https://docs.cloud.google.com/gemini-enterprise-agent-platform/troubleshooting/agent-deployment)
-   [Troubleshoot Runtime Setup](https://docs.cloud.google.com/gemini-enterprise-agent-platform/troubleshooting/runtime-setup)
