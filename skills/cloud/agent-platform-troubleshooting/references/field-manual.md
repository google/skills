# Field manual: Agent Gateway / Registry / Identity / IAP

Practical debugging knowledge for the Google Cloud Gemini Enterprise Agent
Platform, distilled from real incident triage. Read this *before* diving into
the official docs — it covers the gotchas that the docs don't surface.

> [!TIP] **Check Known Issues First**: If the symptom matches a known pattern
> (e.g., startup failure, VPC-SC block, Cloud Run egress 403), jump straight to
> `references/known-issues.md` — it indexes the recurring failure modes by
> symptom.

## Table of Contents

-   [The mental model](#the-mental-model) (Lines 20-88)
-   [The single biggest gotcha: hostname permutations](#the-single-biggest-gotcha-hostname-permutations)
    (Lines 89-120)
-   [Recommended Registry Structure: Consolidated Google APIs](#recommended-registry-structure-consolidated-google-apis)
    (Lines 121-157)
-   [Metric Queries & Visualization](#metric-queries-visualization) (Lines
    158-194)
-   [Diagnostic playbook](#diagnostic-playbook) (Lines 195-525)
-   [Quick reference: the checks in order](#quick-reference-the-checks-in-order)
    (Lines 526-546)

## The mental model

The Agent Platform runs as **default-deny egress**. An agent (typically an Agent
Runtime instance) cannot talk to *anything* outside itself unless every layer
permits it:

1.  **Agent Registry** — the destination must be registered as an Endpoint, MCP
    Server, or Agent.
2.  **Agent Gateway** — intercepts the request (it sits in front of the agent's
    egress). Note: an `authz_policy` must explicitly target the gateway
    resource, otherwise the authz extension won't actually run.
3.  **Service-extension (delegated authz)** — the gateway calls IAP to make an
    allow/deny decision.
4.  **IAP / IAM** — the agent's identity must have the **IAP egressor role**
    (`roles/iap.egressor`, display name "IAP-secured Egressor") on the
    registered resource, or be in a principal set that does.
5.  **Principal Access Boundary (PAB)** — even with the IAM binding correct, a
    PAB policy on the principal set can restrict which resources it can reach.
    **PAB takes precedence over IAM Allow** — a correct egressor binding does
    nothing if a PAB scopes the principal away from the target.

**Implementation note.** Agent Gateway is built on a Google-managed Secure Web
Proxy instance that provides the egress-proxy capabilities. Customers don't
configure the proxy directly — its rules are derived from registry entries and
authz policies. Denials *can* originate at this proxy layer before IAP runs (no
IAP audit entry exists for those calls); those show up in load-balancer logs
(see Step 3b).

**Proxy Routing & TLS SNI:** The proxy performs TLS inspection and looks inside
the HTTPS call for the SNI hostname. In Private Service Connect (PSC)
environments, the client resolves APIs to internal VIPs, so the outer tunnel
request is naturally logged as `CONNECT 240.0.0.2:443`. This is expected. The
proxy intercepts this and evaluates routing based on the inner SNI hostname. If
the corresponding hostname (e.g., `us-central1-aiplatform.googleapis.com`) is
NOT registered, the proxy cannot route the traffic, resulting in a
`default_denied` action on the `CONNECT` request before IAP is ever reached.

### Don't confuse `roles/iap.egressor` with other IAP roles

The display name "IAP-secured Egressor" maps to **`roles/iap.egressor`** —
that's the role for Agent Gateway egress. Other IAP roles exist that are easy to
mistake for it but are unrelated:

| Role ID                            | Purpose            | Use for Agent      |
:                                    :                    : Gateway?           :
| :--------------------------------- | :----------------- | :----------------- |
| `roles/iap.egressor`               | Agent egress       | **Yes — this one** |
:                                    : through Agent      :                    :
:                                    : Gateway            :                    :
| `roles/iap.tunnelResourceAccessor` | TCP/SSH tunneling  | No                 |
:                                    : through IAP to a   :                    :
:                                    : VM                 :                    :
| `roles/iap.httpsResourceAccessor`  | Access to          | No                 |
:                                    : IAP-protected web  :                    :
:                                    : apps (ingress)     :                    :
| `roles/iap.tunnelDestGroupUser`    | Member of an IAP   | No                 |
:                                    : tunnel destination :                    :
:                                    : group              :                    :

Don't substitute. The IAP authz check explicitly looks for
`iap.webServiceVersions.egressViaIAP`, which only `roles/iap.egressor` grants
for the Agent Gateway path.

If any layer says no, the agent gets back a 403:

```
{'code': 403, 'message': "403 Forbidden. {'message': 'Egress request is not authorized.', 'status': 'Forbidden'}"}
```

## The single biggest gotcha: hostname permutations

A Google API like `aiplatform.googleapis.com` is reachable through *many*
hostnames. The agent might call any of them depending on the SDK version,
regional client config, or whether mTLS is in play:

Form                       | Example
:------------------------- | :--------------------------------------------
Base                       | `aiplatform.googleapis.com`
Base + mTLS                | `aiplatform.mtls.googleapis.com`
Locational                 | `us-central1-aiplatform.googleapis.com`
Locational + mTLS          | `us-central1-aiplatform.mtls.googleapis.com`
Regional REP (public)      | `aiplatform.us-central1.rep.googleapis.com`
Regional REP (private/PSC) | `aiplatform.us-central1.p.rep.googleapis.com`

**The gateway matches hostnames exactly.** If you registered only
`aiplatform.googleapis.com` but the SDK actually called
`us-central1-aiplatform.googleapis.com`, the request gets denied — even though
"the API is registered." When investigating a 403, *always* establish what
hostname the agent actually called, then verify that *exact* hostname is in the
registry.

A registration script typically looks like this (note all five permutations):

```bash
reg_svc "${id}"                   "${name}"                "https://${id}.googleapis.com"
reg_svc "${id}-mtls"              "${name} mTLS"           "https://${id}.mtls.googleapis.com"
reg_svc "${LOCATION}-${id}"       "${name} Locational"     "https://${LOCATION}-${id}.googleapis.com"
reg_svc "${LOCATION}-${id}-mtls"  "${name} Locational mTLS" "https://${LOCATION}-${id}.mtls.googleapis.com"
reg_svc "${id}-${LOCATION}-rep"   "${name} Regional (REP)" "https://${id}.${LOCATION}.rep.googleapis.com"
```

## Recommended Registry Structure: Consolidated Google APIs

To simplify management and reduce resource overhead, it is recommended to
register all Google APIs under a single `googleapis` service entry in the Agent
Registry using **multiple interfaces** (one for each required API hostname).

### Recommended Base Interfaces (Consolidated `googleapis` Service)

Your base `googleapis` service should include the following interfaces:

-   `https://agentregistry.googleapis.com`
-   `https://aiplatform.mtls.googleapis.com`
-   `https://cloudresourcemanager.mtls.googleapis.com`
-   `https://iamcredentials.mtls.googleapis.com`
-   `https://telemetry.mtls.googleapis.com`
-   `https://{region}-aiplatform.mtls.googleapis.com`
-   `https://{region}-aiplatform.googleapis.com`
-   `https://aiplatform.{region}.rep.googleapis.com`

*(Replace `{region}` with your actual region, e.g., `us-central1`)*

### Other Services

If you are not using the consolidated model, or are using additional services
(like custom MCPs or separate engines), make sure they are registered:

-   `discoveryengine`
-   `logging`
-   `monitoring`
-   `oauth2`
-   `trace`
-   `iap`
-   `modelarmor`

Missing any required API hostnames is the most common "agent works in dev, fails
in prod" cause.

## Metric Queries & Visualization

When diagnosing performance issues, latency spikes, or intermittent failures,
you can query and visualize relevant time-series metrics if you have monitoring
access.

If the user reports "slowness" or "intermittent errors", visualize the trend
using a Mermaid `xychart-beta` chart in your diagnostic report.

### 1. Agent Gateway Egress QPS & Error Rate

Query the Secure Web Proxy metrics for the gateway to see traffic volume and
error distribution:

-   **Metric**: `networkservices.googleapis.com/gateway/request_count`
-   **Breakby**: `response_code_class`, `gateway_name`

### 2. Agent Runtime Latency (p50/p90/p99)

Query the Agent Runtime latency to identify performance degradation:

-   **Metric**: `aiplatform.googleapis.com/reasoning_engine/query_latency`
-   **Breakby**: `reasoning_engine_id`, `location`

### 3. Visualizing with Mermaid

When presenting latency or error trends in the report, format them as a Mermaid
chart:

```mermaid
xychart-beta
    title "Gateway Latency (p90) last 24h"
    x-axis [00:00, 04:00, 08:00, 12:00, 16:00, 20:00]
    y-axis "Latency (ms)" 0 --> 1000
    line [120, 150, 850, 900, 140, 130]
```

## Diagnostic playbook

```
        ┌─────────────────────────────────────┐
        │ 0. Establish context & Verify access│
        └────────────────┬────────────────────┘
                         │
                         ▼
        ┌─────────────────────────────────────┐
        │ 1. Pull agent logs — confirm error  │
        │    (403 vs Connection vs Crash)     │
        └────────────────┬────────────────────┘
                         │
        ┌────────────────┴────────────────────┐
        │ Is it a Connection / Network error? │
        └───────┬──────────────────────┬──────┘
            no  │                  yes │
                │                      ▼
                │             ┌────────────────────────────────┐
                │             │ 3c. PSC Subnet Exhaustion Check│
                │             └────────────────────────────────┘
                ▼
        ┌─────────────────────────────────────┐
        │ Is it a Container Crash / Python    │
        │ Exception?                          │
        └───────┬──────────────────────┬──────┘
            no  │                  yes │
            (403)                      ▼
                │             ┌────────────────────────────────┐
                │             │ 1b. Runtime Health Check       │
                │             │     (Python dependencies,      │
                │             │      stderr logs, crash codes) │
                │             └────────────────────────────────┘
                ▼
        ┌─────────────────────────────────────┐
        │ 2. Pull gateway logs — find the     │
        │    EXACT hostname being called      │
        └────────────────┬────────────────────┘
                         │
                         ▼
        ┌─────────────────────────────────────┐
        │ 3. Pull IAP logs — DRY_RUN or       │
        │    enforced? Allow or deny?         │
        └────────────────┬────────────────────┘
                         │
                         ▼
        ┌─────────────────────────────────────┐
        │ 4. Is the EXACT hostname in the     │
        │    registry (any of agents /        │
        │    mcp-servers / endpoints)?        │
        └────────┬────────────────────┬───────┘
            no   │                yes │
                 ▼                    ▼
       ┌──────────────────┐   ┌─────────────────────────────┐
       │ Root cause:      │   │ 5. Does the agent identity  │
       │ unregistered     │   │    (or its principal set)   │
       │ hostname permu-  │   │    have IAP egressor on     │
       │ term. Recommend  │   │    the registered resource? │
       │ registering all  │   └────────┬────────────────────┘
       │ five forms.      │            │
       └──────────────────┘            ▼
                            ┌─────────────────────────────┐
                            │ 6. Authz extension wired to │
                            │    the gateway? Pointing at │
                            │    IAP?                     │
                            └────────┬────────────────────┘
                                     ▼
                            ┌─────────────────────────────┐
                            │ 7. Agent identity baseline  │
                            │    roles (Agent Runtime User, │
                            │    Registry Viewer, logs)   │
                            └────────┬────────────────────┘
                                     ▼
                            ┌─────────────────────────────┐
                            │ 8. PrincipalSet flakiness?  │
                            │    Recommend 1:1 binding    │
                            │    test                     │
                            └─────────────────────────────┘
```

### Step 0 — Establish context & Disable prompts

Before running any diagnostics, ensure the gcloud CLI is installed (see
[Google Cloud SDK Installation](https://cloud.google.com/sdk/docs/install)),
your environment is configured correctly, and prompts are disabled to prevent
commands from hanging:

1.  **Disable CLI Prompts**:

    ```bash
    gcloud config set core/disable_prompts True
    ```

2.  **Verify Project Access**:

    ```bash
    gcloud projects describe $PROJECT_ID
    ```

    If this fails, you cannot proceed with log gathering. Prompt the user for
    correct permissions or coordinates.

3.  **Discover the Correct Project (if resources are missing)**: If the active
    project (configured in `gcloud`) does not contain the expected Agent
    Gateways, Agent Runtime instances, or Registry entries, it may be the wrong
    project.

    > [!IMPORTANT] **Check Active Project First**: Always check the active
    > project first before scanning others:
    >
    > ```bash
    > ACTIVE_PROJ=$(gcloud config get-value project)
    > # Check for gateways
    > gcloud alpha network-services agent-gateways list --location=us-central1 --project=$ACTIVE_PROJ
    > # Check for agents
    > gcloud alpha agent-registry agents list --location=us-central1 --project=$ACTIVE_PROJ
    > ```
    >
    > If you find the target resources in the active project, **proceed
    > immediately** and do NOT scan other projects.

    If resources are not in the active project, check prioritized dev projects:
    `bash for proj in duncanjames-tf-dev duncanjames-agw-tf; do # Check gateways
    res_gw=$(gcloud alpha network-services agent-gateways list
    --location=us-central1 --project=$proj 2>&1) if [[ "$res_gw" == *"NAME"* ]];
    then echo "FOUND Gateways in project: $proj" echo "$res_gw" fi # Check
    agents res_ag=$(gcloud alpha agent-registry agents list
    --location=us-central1 --project=$proj 2>&1) if [[ "$res_ag" == *"NAME"* ]];
    then echo "FOUND Registry in project: $proj" echo "$res_ag" fi done`

    If you cannot find the target resource (e.g. the stuck gateway or the
    failing agent) in the default project:

    1.  **Do not scan more than 2 other projects** or spend more than 2 turns
        trying to locate it.
    2.  **Do not list operations, logs, or subnets across multiple regions or
        projects in loops.** If the region is not specified, check ONLY the
        default region (usually `us-central1`).
    3.  If you find candidate resources in other projects, **prioritize those in
        `duncanjames-tf-dev` or `duncanjames-agw-tf`**, especially if they have
        `tf-test` or `re-agent` in their name (e.g.,
        `ag-client-tf-test-re-agent-*` or `ag-anywhere-tf-test-re-agent-*`).
        **You MUST treat these as the target resources** and immediately proceed
        to describe them and calculate subnet IPs. Do not describe or scan
        gateways in other projects (like `next26-*` or `agw-showcase-*`) if
        these prioritized candidates are present.
    4.  If you cannot find any candidate resource within these limits, **stop
        searching** and proceed with writing the diagnostic report using
        placeholders for names, explaining the general troubleshooting steps
        (including the PSC subnet exhaustion calculation formulas).

    Once the project containing the resources is identified, use that
    `PROJECT_ID` for all subsequent steps.

### Step 0.4 — Special Handling for Telemetry (telemetry.mtls.googleapis.com) Issues

If the symptom or error logs involve **telemetry.mtls.googleapis.com** (e.g.,
connection reset, handshake error, or `certificate verify failed` during
startup/`set_up()`):

1.  This is a known issue that can be caused by Egress Gateway blocking (BKI 23)
    OR SSL CA trust issues (BKI 17).
2.  In your diagnostic report, **you MUST address both possibilities and
    unconditionally recommend the following actions (even if resources appear to
    be already configured in the dirty environment)**:
    *   **Verify/Perform Endpoint Registration**: Explain that
        `telemetry.mtls.googleapis.com` must be registered in the Agent
        Registry. **You MUST also explicitly suggest checking whether other
        required monitoring/tracing endpoints (such as
        `monitoring.googleapis.com` or `trace.mtls.googleapis.com`) are
        registered as Endpoints**, and provide the `gcloud alpha agent-registry
        endpoints create` commands for them.
    *   **Verify/Create Authorization Policy**: Explain that an
        `AuthorizationPolicy` must allow the agent's principal set to access the
        telemetry endpoint (by binding a `REQUEST_AUTHZ` policy with the IAP
        extension to the gateway). **You MUST recommend creating or updating
        this policy and provide the exact gcloud/Terraform configuration for
        it**, even if you see a policy already bound in the project.
    *   **Verify CA Trust**: Recommend configuring the agent's environment
        variables (`REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE`, and
        `GRPC_DEFAULT_SSL_ROOTS_FILE_PATH` pointing to
        `/etc/ssl/certs/ca-certificates.crt`) to ensure the Python/gRPC runtime
        trusts the gateway's TLS inspection CA.

### Step 0.5 — Mismatched Symptoms (Dirty Environments)

In shared evaluation or development projects, the logs you retrieve might
contain errors from previous, unrelated runs (e.g., finding an SSL `certificate
verify failed` error when the user is asking about IAP 403 errors).

If the logs you find do **not** match the symptom described in the user's prompt
(e.g., the user complains about "403 errors... logs mention IAP" but you find
"SSLError" and "no IAP logs"):

1.  **Do not ignore the user's prompt.** Do not assume your log findings are the
    only issue.
2.  In your diagnostic report, you MUST address the user's described symptom.
3.  Explain that while you found a different error in the active logs (and
    diagnose it), the user's described symptom (IAP denial) is typically caused
    by:
    *   Missing `roles/iap.egressor` or `roles/iap.httpsGatewayUser` on the
        agent identity.
    *   `AuthorizationPolicy` not being correctly bound to the Gateway.
4.  Include the general troubleshooting steps for IAP denials (checking IAP
    audit logs, verifying roles, checking policy bindings) as recommended fixes,
    even if you couldn't verify them in the current log state.

### Step 1 — Confirm the symptom in agent logs

Check the Agent Runtime logs for the error (403, SSL Handshake Timeout, or
Connection Reset):

```
resource.type="aiplatform.googleapis.com/ReasoningEngine"
resource.labels.location=$LOCATION
resource.labels.reasoning_engine_id=$AGENT_ID
(textPayload:"403" OR textPayload:"handshake operation timed out" OR textPayload:"Connection reset by peer" OR textPayload:"Network is unreachable")
```

**Alternative (CLI Fallback):**

```bash
# Note: --limit=10 limits output volume to capture recent error logs while preventing context overflow and command timeouts.
gcloud logging read 'resource.type="aiplatform.googleapis.com/ReasoningEngine" AND resource.labels.location="'$LOCATION'" AND resource.labels.reasoning_engine_id="'$AGENT_ID'" AND (textPayload:"403" OR textPayload:"handshake operation timed out" OR textPayload:"Connection reset by peer" OR textPayload:"Network is unreachable")' --project=$PROJECT_ID --limit=10
```

The error payload tells you *that* it failed.

-   If it is a **403**, continue with the standard Gateway/IAP flow (Step 2).
-   If it is an **SSL Handshake Timeout** or **Connection Reset/Network
    Unreachable**, suspect a PSC provisioning issue or subnet exhaustion. Skip
    to **Step 3c**.
-   If it is a **container crash**, **startup error**, or **Python exception**,
    proceed to **Step 1b**.

### Step 1b — Debugging Agent Runtime Crashes (Container Crashes & Python Exceptions)

If the agent logs (Step 1) show that the Agent Runtime container failed to start
or crashed during execution (instead of a 403 or network timeout), follow this
checklist:

#### 1. Pull stderr logs for Python exceptions

Query the stderr logs specifically to find traceback info:

```
resource.type="aiplatform.googleapis.com/ReasoningEngine"
resource.labels.location=$LOCATION
resource.labels.reasoning_engine_id=$AGENT_ID
logName="projects/$PROJECT_ID/logs/aiplatform.googleapis.com%2Freasoning_engine_stderr"
```

**Alternative (CLI Fallback):**

```bash
# Note: --limit=20 fetches a sufficient recent log sample to identify startup stack traces without flooding output or timing out.
gcloud logging read 'resource.type="aiplatform.googleapis.com/ReasoningEngine" AND resource.labels.location="'$LOCATION'" AND resource.labels.reasoning_engine_id="'$AGENT_ID'" AND logName="projects/'$PROJECT_ID'/logs/aiplatform.googleapis.com%2Freasoning_engine_stderr"' --project=$PROJECT_ID --limit=20
```

Look for common Python startup failures:

-   `ModuleNotFoundError` or `ImportError`: The uploaded agent code requires a
    package that was not specified in the deployment requirements.
-   `SyntaxError`: Syntax error in the uploaded Python files.
-   Initialization crashes in the `__init__` method of the agent class.

#### 2. Check for Resource Limit Exceeded (OOM)

If the container dies silently without a Python traceback, it may have been
killed by the runtime due to Out of Memory (OOM) or CPU limits.

-   Check if the requested resource limits (CPU/Memory) in `DeploymentSpec` are
    sufficient.
-   Look for container termination status if visible in the logs (e.g., exit
    code `137` usually indicates OOMKilled).

### Step 2 — Find the failing hostname in gateway logs

```
resource.type="networkservices.googleapis.com/Gateway"
resource.labels.location="REGION"
resource.labels.gateway_name="AGENT_GATEWAY_NAME"
```

**Alternative (CLI Fallback):**

```bash
# Note: --limit=50 retrieves recent gateway access entries for log inspection without triggering command timeouts.
gcloud logging read 'resource.type="networkservices.googleapis.com/Gateway" AND resource.labels.location="REGION" AND resource.labels.gateway_name="AGENT_GATEWAY_NAME"' --project=PROJECT_ID --limit=50
```

The gateway log entry shows the actual hostname the request was for. Write it
down — you'll need it in step 4.

**Model Armor Special Case (High-Confidence Indicator):** If the gateway log
contains `serviceExtensionInfo` with `grpcStatus: "PERMISSION_DENIED"`,
`backendTargetType: "BACKEND_SERVICE"`, and `backendTargetName` matching
`modelarmor.*`, this is a definitive, high-confidence indicator of a Model Armor
integration permission issue. Refer to **known-issues.md §13 (BKI 13)**
immediately for the exact role requirements and fix commands.

### Step 3 — Check IAP allow/deny decision

> [!IMPORTANT] **Data Access Logs Prerequisite**: IAP authorization decisions
> for the data-plane are logged to **Data Access audit logs** (`DATA_READ`
> type), which are **disabled by default** in Google Cloud. If the log query
> returns **no results**, you must verify if IAP audit logging is enabled. Check
> with:
>
> ```bash
> gcloud projects get-iam-policy $PROJECT_ID \
>   --filter="auditConfigs.service:iap.googleapis.com" \
>   --format="yaml(auditConfigs)"
> ```
>
> If the output is empty or missing `DATA_READ` for `iap.googleapis.com`, you
> must enable it in the Google Cloud console under **IAM -> Audit Logs**.

Narrow the noise by scoping to the egress permission and excluding base-protocol
MCP method noise:

```
protoPayload.serviceName="iap.googleapis.com"
protoPayload.authorizationInfo.permission="iap.webServiceVersions.egressViaIAP"
-protoPayload.metadata.mcp_attributes.base_protocol_method="true"
```

**Alternative (CLI Fallback):**

```bash
# Note: --limit=50 captures enough audit logs for trace analysis while limiting response size.
gcloud logging read 'protoPayload.serviceName="iap.googleapis.com" AND protoPayload.authorizationInfo.permission="iap.webServiceVersions.egressViaIAP" AND -protoPayload.metadata.mcp_attributes.base_protocol_method="true"' --project=PROJECT_ID --limit=50
```

What to read out of each entry:

-   **`protoPayload.authorizationInfo[].granted`** — `true` or `false`. The
    bottom-line allow/deny.
-   **`protoPayload.authenticationInfo.principalSubject`** — the SPIFFE /
    `principal://...` URI of the caller.
-   **`protoPayload.authorizationInfo[].resource`** — the registered resource
    the call resolved to.
-   **`labels."iap.googleapis.com/audited_resource_name"`** — if this is
    `unregisteredResource`, the destination hostname isn't in the registry. Go
    to Step 4.
-   **The enforcement mode** — is IAP in dry-run?

    ```yaml
    service: iap.googleapis.com
    failOpen: true
    timeout: 1s
    metadata:
      iamEnforcementMode: "DRY_RUN"
      iapPolicyVersion: "V1"
    ```

    In `DRY_RUN` mode, denials are logged but the request proceeds. If your
    agent is failing with a real 403 *and* IAP is in dry-run, the denial is
    coming from somewhere else — most often the gateway's underlying egress
    proxy (see Step 3b) or the destination service itself.

### Step 3b — If there's no IAP audit entry for the failing call, pull the gateway proxy load-balancer log

The gateway's underlying egress proxy can deny a request before IAP runs. The
denial is in the proxy's load-balancer log. The `SECURE_WEB_GATEWAY` label here
refers to the proxy implementation under the hood:

```
jsonPayload.@type="type.googleapis.com/google.cloud.loadbalancing.type.LoadBalancerLogEntry"
resource.labels.gateway_type="SECURE_WEB_GATEWAY"
```

**Alternative (CLI Fallback):**

```bash
# Note: --limit=50 limits output volume when querying load balancer log entries.
gcloud logging read 'jsonPayload.@type="type.googleapis.com/google.cloud.loadbalancing.type.LoadBalancerLogEntry" AND resource.labels.gateway_type="SECURE_WEB_GATEWAY"' --project=PROJECT_ID --limit=50
```

Key fields to inspect:

-   `httpRequest.status`: Look for `403`.
-   `jsonPayload.enforcedGatewaySecurityPolicy.hostname`: Look for
    `240.0.0.2:443` (expected under PSC).
-   `jsonPayload.enforcedGatewaySecurityPolicy.matchedRules`: Look for
    `default_denied`.
-   `jsonPayload.mtls.clientCertChainVerified`: Often `false` if connection
    dropped early.

If you see `240.0.0.2:443` under `hostname` and `default_denied` under
`matchedRules`, this is a routing drop. The proxy decrypted the tunnel but
failed to match the *inner* SNI hostname against the Agent Registry. Make sure
all required hostname permutations are registered.

### Step 3c — Diagnosing PSC Subnet Exhaustion

If you observe **SSL Handshake Timeouts** or **Connection Reset** in the agent
logs, or if the Agent Gateway deployment is failing/stuck, the Private Service
Connect (PSC) subnet might be out of IP addresses.

> [!NOTE] **CLIENT_TO_AGENT Gateways**: Both ingress (`CLIENT_TO_AGENT`) and
> egress (`AGENT_TO_ANYWHERE`) gateways can be stuck in provisioning. Ingress
> gateways do NOT populate the `agentGatewayCard` even when active, so you must
> check if they are stuck by describing their network attachment and calculating
> subnet IPs.

1.  **Find the Agent Gateway Name** (if not provided): List the gateways in the
    project to find the one that is stuck or relevant:

    ```bash
    gcloud alpha network-services agent-gateways list --location=$LOCATION --project=$PROJECT_ID
    ```

2.  **Identify the Network Attachment**: Describe the Agent Gateway to find the
    Network Attachment in use:

    ```bash
    gcloud alpha network-services agent-gateways describe AGENT_GATEWAY_NAME --location=$LOCATION --project=$PROJECT_ID
    ```

    Look for `networkConfig.egress.networkAttachment` or
    `networkConfig.ingress.networkAttachment` (depending on gateway type).

3.  **Describe the Network Attachment**:

    ```bash
    gcloud compute network-attachments describe NETWORK_ATTACHMENT_NAME --region=$LOCATION --project=$PROJECT_ID
    ```

    Note the `subnetwork` field.

4.  **Inspect the Subnet**: Describe the subnetwork to check its IP range:

    ```bash
    gcloud compute networks subnetworks describe SUBNET_NAME --region=$LOCATION --project=$PROJECT_ID
    ```

    Check the `ipCidrRange` (e.g., a `/28` subnet only has 16 IP addresses, and
    Google Cloud reserves 4, leaving only 12 for resources).

5.  **Check IP Usage and Calculate Free IPs**:

    *   Find the number of allocated IPs by looking at the `connectionEndpoints`
        list in the network attachment description from Step 2. Each endpoint in
        that list consumes one IP address.
    *   Calculate the number of usable IPs in the subnet based on its
        `ipCidrRange` (e.g., a `/28` subnet has 16 IPs, minus 4 reserved by
        Google Cloud = 12 usable IPs; a `/16` has 65536 IPs, minus 4 = 65532
        usable).
    *   Explicitly state the calculation in your report: `Usable IPs - Allocated
        IPs = Free IPs`.
    *   **Flag `/28` Exhaustion Risk**: Even if the current subnet has free IPs
        (or is larger, like `/16`), if you are diagnosing a stuck/failing
        gateway deployment, you **MUST** explicitly mention in your report that
        a `/28` subnet is too small and easily exhausted, and recommend
        expanding the CIDR range to at least `/26` as a best practice.

### Step 4 — Verify the hostname is registered (in the form the agent used)

List registry entries — pick the right resource type for the destination:

```bash
gcloud alpha agent-registry endpoints list      --project=$PROJECT_ID --location=$LOCATION
gcloud alpha agent-registry mcp-servers list    --project=$PROJECT_ID --location=$LOCATION
gcloud alpha agent-registry agents list         --project=$PROJECT_ID --location=$LOCATION
```

Grep the output for the exact hostname from step 2. If it's missing, that's the
root cause.

### Step 5 — Verify IAM bindings on the registered resource and gateway

To authorize egress, the agent's identity needs roles granted on both the
gateway and the registry resources:

1.  **Gateway Access**: The agent needs `roles/iap.httpsGatewayUser` to connect
    to the gateway. Verify or grant this role (often at the project level):

    ```bash
    gcloud projects add-iam-policy-binding $PROJECT_ID \
      --member="principalSet://agents.global.org-${ORG_ID}.system.id.goog/attribute.platformContainer/aiplatform/projects/${PROJECT_NUMBER}" \
      --role="roles/iap.httpsGatewayUser"
    ```

2.  **Registry/Destination Access**: The agent needs `roles/iap.egressor` on the
    registered resource. Bindings can live at the **registry level** or on a
    **specific resource**.

#### Registry-level IAM policy

```bash
curl -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
  -d '{}' \
  -X POST "https://iap.googleapis.com/v1/projects/${PROJECT_NUMBER}/locations/${LOCATION}/iap_web/agentRegistry:getIamPolicy" \
  -H "Content-Type: application/json"
```

#### Per-endpoint IAM policy

```bash
curl -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
  -d '{}' \
  -X POST "https://iap.googleapis.com/v1/projects/${PROJECT_NUMBER}/locations/${LOCATION}/iap_web/agentRegistry/endpoints/${ENDPOINT_ID}:getIamPolicy" \
  -H "Content-Type: application/json"
```

#### Same call, but for global registry:

```bash
curl -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
  -d '{"options": {"requestedPolicyVersion": 3}}' \
  -X POST "https://iap.googleapis.com/v1/projects/${PROJECT_NUMBER}/locations/global/iap_web/agentRegistry:getIamPolicy" \
  -H "Content-Type: application/json"
```

When reading the returned policy, look for a binding that matches the agent's
service account or principal set with role `roles/iap.egressor`.

### Step 6 — Inspect the gateway / authz extension wiring

#### List authz extensions

```bash
gcloud beta service-extensions authz-extensions list \
  --location=$LOCATION --project=$PROJECT_ID

gcloud beta service-extensions authz-extensions describe RESOURCE_NAME \
  --location=$LOCATION --project=$PROJECT_ID
```

#### Verify AuthorizationPolicy Binding

Verify that the `AuthorizationPolicy` is correctly bound to your `Gateway`. The
policy must target the gateway resource. If it is not bound, the authorization
logic will not be applied to the gateway traffic.

1.  Inspect the `AuthorizationPolicy` resource (retrieved from the API via
    `gcloud` if available).
2.  Ensure the policy's target matches the gateway's name and location.

#### List authz policies, agent gateways, and authz extensions via raw API

```bash
# authzPolicies
curl -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
  "https://networksecurity.googleapis.com/v1alpha1/projects/${PROJECT_ID}/locations/${LOCATION}/authzPolicies"

# agentGateways
curl -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
  "https://networkservices.googleapis.com/v1alpha1/projects/${PROJECT_ID}/locations/${LOCATION}/agentGateways"

# authzExtensions
curl -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
  "https://serviceextensions.googleapis.com/v1alpha1/projects/${PROJECT_ID}/locations/${LOCATION}/authzExtensions"
```

### Step 7 — Verify the agent identity has the baseline roles

The agent identity itself needs enough permissions to function on the source
side:

-   `roles/aiplatform.user` (Agent Runtime User) — to run the ReasoningEngine
-   Agent Registry viewer role — to know what's registered
-   `roles/logging.logWriter`, `roles/monitoring.metricWriter`, telemetry roles
    — observability
-   `roles/browser` — needed for `resourcemanager.projects.get` during SDK init.
    Without it, the ReasoningEngine fails startup with `Failed to convert
    project number to project ID` (see known-issues §1).
-   `roles/iap.httpsGatewayUser` (IAP-secured Web App User) and
    `roles/iap.egressor` (IAP-secured Egressor) — to ensure the agent is
    authorized to egress through IAP. **You MUST recommend verifying both roles
    and the AuthorizationPolicy binding in your report's fix/debugging
    section**:
    1.  `roles/iap.httpsGatewayUser` is typically required on the Gateway
        resource.
    2.  `roles/iap.egressor` is required on the target Registry/Endpoint.
    3.  Verify that the `AuthorizationPolicy` is correctly bound to the Gateway
        (ensure the policy targets the gateway resource). Do NOT omit these
        recommendations even if you believe they are already correctly
        configured, as they are essential verification steps for the user.

### Step 7b — Check Principal Access Boundary (PAB) policies

A PAB policy can override IAM Allow and restrict the resources the principal set
can reach.

```bash
# List org-wide PAB policies
gcloud iam principal-access-boundary-policies list \
  --organization="${ORGANIZATION_ID}" --location=global

# Find what's bound to the agent's principal set
gcloud iam policy-bindings search-target-policy-bindings \
  --project="${PROJECT_ID}" --target="${PRINCIPAL_SET}"
```

### Step 7c — Cloud Run / Functions Egress Authentication

If the destination is Cloud Run or Cloud Functions, direct OIDC authentication
using the default Agent Identity (`principalSet://...`) is not natively
supported by Cloud Run. The agent must use Service Account impersonation.

**You MUST recommend the following in your report if the destination is Cloud
Run:**

1.  Explain that direct Agent Identity to Cloud Run OIDC auth is unsupported.
2.  Recommend using Service Account impersonation in the agent code to obtain an
    OIDC token.
3.  Specify that the Agent Identity needs `roles/iam.serviceAccountTokenCreator`
    on the target Service Account (which in turn needs `roles/run.invoker` on
    the Cloud Run service). Refer to `references/known-issues.md` BKI 21 for
    details and code examples.

### Step 8 — PrincipalSet vs Principal

If permissions seem flaky, suspect the **PrincipalSet** binding. Move to a **1:1
Principal binding** (bind the specific service account directly) to verify.

## Quick reference: the checks in order

When triaging a 403 or connection failure, walk these in order:

1.  Confirm the error in the agent log (403 vs SSL Handshake Timeout vs
    Connection Reset).
2.  Find the *exact hostname* in the gateway log (if 403).
3.  Check IAP audit log: decision, principal, `iamEnforcementMode`, and watch
    for `unregisteredResource`. 3b. If no IAP audit entry, pull gateway proxy
    load-balancer log. 3c. If SSL Handshake Timeout or Connection Reset, run the
    PSC Subnet Exhaustion Check.

4.  Confirm hostname is registered.

5.  Check IAM on the registry/resource (`roles/iap.egressor`).

6.  Check authz extensions and policies.

7.  Confirm agent identity has baseline roles. 7b. Check PAB policies. 7c. Check
    Cloud Run egress auth (impersonation).

8.  If behavior is flaky, switch to direct Principal bindings.
