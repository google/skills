# Field manual: Agent Gateway / Registry / Identity / IAP

Practical debugging knowledge for the Google Cloud Gemini Enterprise Agent
Platform, distilled from real incident triage. Read this *before* diving into
the official docs — it covers the gotchas that the docs don't surface.

> **Tip:** **Check Known Issues First**: If the symptom matches a known pattern
> (e.g., startup failure, VPC-SC block, Cloud Run egress 403, explicit proxy 404,
> or DNS 2-hop `NXDOMAIN`), jump straight to `references/known-issues.md` — it
> indexes recurring failure modes by symptom.

## Table of Contents

-   [The mental model](#the-mental-model): Lines 26-121
-   [The single biggest gotcha: hostname permutations](#the-single-biggest-gotcha-hostname-permutations): Lines 122-153
-   [Recommended Registry Structure: Consolidated Google APIs](#recommended-registry-structure-consolidated-google-apis): Lines 154-191
-   [Metric Queries & Visualization](#metric-queries--visualization): Lines 192-228
-   [Diagnostic playbook](#diagnostic-playbook): Lines 229-1156
    -   [Steps 0–10: Core 403, Crash, PSC Exhaustion, ACT/NAT, UAP/IAM, Identity, Cross-Project, & Next-Hop SWP/PBR](#step-0--establish-context--disable-prompts): Lines 270-1074
    -   [Step 11: Explicit HTTPS Proxy Egress (`HTTPS_PROXY` + L4 `networkRules`)](#step-11--diagnose-explicit-https-proxy-egress-https_proxy--l4-networkrules): Lines 1075-1094
    -   [Step 12: Cloud DNS Peering (2-Hop Limit) & Cross-Project Shared VPC IAM](#step-12--diagnose-cloud-dns-peering-2-hop-limit--cross-project-shared-vpc-iam): Lines 1095-1122
    -   [Step 13: Private CA `TrustConfig` TLS Failures & ACT Immutability](#step-13--diagnose-private-ca-trustconfig-tls-failures--act-immutability): Lines 1123-1137
    -   [Step 14: SGP, Model Armor 60s Stream Timeouts, Native MCP Rules, & Cloud Trace](#step-14--diagnose-sgp-model-armor-60s-stream-timeouts-native-mcp-rules--cloud-trace): Lines 1138-1156
-   [Quick reference: the checks in order](#quick-reference-the-checks-in-order): Lines 1157-1179

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
4.  **IAP / IAM Policy Evaluation** — the agent's identity must be authorized by
    IAP:
    *   **IAM v1 (Legacy Policy Model)**: Evaluated when `iapPolicyVersion:
        "V1"` (or unset). The agent identity must have the **IAP egressor role**
        (`roles/iap.egressor`, display name "IAP-secured Egressor") directly
        bound on the registered resource shadow resource in IAP.
    *   **Unified Access Policy (UAP / Policy V2 / IAM v3)**: Evaluated when the
        gateway's IAP Authz Extension metadata specifies `iapPolicyVersion:
        "V2"`. Next-gen access control bound directly to Resource Manager
        hierarchy nodes (Organizations, Folders, Projects) via `PolicyBinding`
        (`iam.googleapis.com/v3`). Evaluates `AccessPolicy` rules with CEL
        expressions on deep attributes (`destination.agent_registry.*` or
        `destination.unregistered.*`). Follows strict evaluation invariants:
        absolute DENY precedence (cannot be overridden by downstream projects),
        and additive ALLOW aggregation across the CRM tree.
5.  **Principal Access Boundary (PAB)** — even with the IAM/UAP binding correct,
    a PAB policy on the principal set can restrict which resources it can reach.
    **PAB takes precedence over IAM Allow** — a correct egressor binding does
    nothing if a PAB scopes the principal away from the target.

**Implementation note.** Agent Gateway is built on a Google-managed Secure Web
Proxy instance that provides the egress-proxy capabilities. Customers don't
configure the proxy directly — its rules are derived from registry entries and
authz policies. Denials *can* originate at this proxy layer before IAP runs (no
IAP audit entry exists for those calls); those show up in load-balancer logs
(see Step 3b).

**Proxy Routing, TLS SNI & Agent Connectivity Templates (ACT):** Inside an Agent
Runtime container, outbound connections enter the gateway tunnel via synthetic
PSC VIP `CONNECT 240.0.0.2:443`. By default, Agent Gateway terminates or inspects
TLS, evaluates the inner SNI hostname against Agent Registry and `AuthzPolicy`
rules, and resolves public internet and standard non-VPC-SC Google API hostnames
using **public recursive DNS at the gateway proxy** (Cloud DNS peering via
`dnsPeeringConfig` is required **only** for private internal domains such as
`corp.internal.` or VPC-SC `googleapis.com.` mapped to `199.36.153.4/30`). If an
inner SNI hostname (e.g., `us-central1-aiplatform.googleapis.com`) is NOT
registered and no L4 `networkRules` policy matches, the proxy drops the request
with `default_denied` before IAP runs.

Under **VPC Service Controls (VPC-SC)**, Agent Gateway requires an **Agent
Connectivity Template (ACT)** configured with `vpcEgress: ALL_TRAFFIC`:

-   Traffic destined for external public APIs (e.g., `api.ipify.org`,
    `api.weather.gov`) traverses the gateway and egresses through the consumer
    VPC PSC-I Network Attachment subnet via **Cloud NAT** using static IPs. If
    Cloud NAT is missing or misconfigured, external traffic hangs or resets
    silently.
-   Traffic destined for Google APIs (e.g., Vertex AI, Cloud Run default domains
    `*.run.app`) routes through Private Google Access / Restricted Google Access
    without traversing public Cloud NAT.

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

*(Replace `{region}` with your actual region, e.g., `us-central1`.)*

-   **Global-only foundation models & `.rep.mtls` pitfall**: When calling global-only Gemini models, also add `https://aiplatform.googleapis.com` to the `googleapis` service. Never construct `aiplatform.{us,eu}.rep.mtls.googleapis.com` FQDNs (multi-region `.rep.mtls` DNS records do not exist and fail with `NXDOMAIN`).

### Other Services

If you are using additional Google Cloud APIs (or custom MCPs / separate engines), ensure their exact hostnames are included on the consolidated `googleapis` service (or registered as separate non-Google services):

-   `discoveryengine`
-   `logging`
-   `monitoring`
-   `oauth2`
-   `cloudtrace` and `trace`
-   `iap`
-   `modelarmor`

Missing any required API hostnames is the most common "agent works in dev, fails
in prod" cause.

## Metric Queries & Visualization

When diagnosing performance issues, latency spikes, or intermittent failures,
query and visualize relevant time-series metrics if you have monitoring access.
Note that the Google Cloud Console **Agent Gateway Observability** tab requires
upgrading the project's `_Default` log bucket to **Log Analytics** (`_AllLogs` view).

If the user reports "slowness" or "intermittent errors", visualize the trend
using a Mermaid `xychart-beta` chart in your diagnostic report.

### 1. Agent Gateway Egress QPS, Latency, & Error Rate

Query native Agent Gateway and underlying Secure Web Proxy metrics:

-   **Metrics**: `networkservices.googleapis.com/agentgateway/request_count`, `networkservices.googleapis.com/agentgateway/total_latencies`, `networkservices.googleapis.com/agentgateway/backend_latencies`, `networkservices.googleapis.com/agentgateway/iap_authz_request_count`, and `networkservices.googleapis.com/gateway/request_count`
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
        ┌──────────────────────────────────────────────────────┐
        │ 0. Establish context & Verify access                 │
        └──────────────────────────┬───────────────────────────┘
                                   ▼
        ┌──────────────────────────────────────────────────────┐
        │ 1. Pull agent logs — classify primary symptom:       │
        │  • Timeout / Reset       → 3c (PSC) & 3d (ACT / NAT) │
        │  • Crash / Traceback     → 1b (Runtime stderr / OOM) │
        │  • 404 on HTTPS_PROXY    → 11 (L4 networkRules SNI)  │
        │  • NXDOMAIN / Shared VPC → 12 (DNS 2-hop & Host IAM) │
        │  • Private CA TLS Error  → 13 (TrustConfig & Rebind) │
        │  • 60s Cutoff / SGP /429 → 14 (SGP / MA / Trace)     │
        │  • 403 Forbidden         → Continue to Step 2        │
        └──────────────────────────┬───────────────────────────┘
                                   ▼
        ┌──────────────────────────────────────────────────────┐
        │ 2. Pull gateway logs — find EXACT hostname called    │
        └──────────────────────────┬───────────────────────────┘
                                   ▼
        ┌──────────────────────────────────────────────────────┐
        │ 3. Pull IAP logs — Check V1 vs V2, DRY_RUN, decision │
        │    (If no IAP entry, check 3b proxy LB log)          │
        └──────────────────────────┬───────────────────────────┘
                                   ▼
        ┌──────────────────────────────────────────────────────┐
        │ 4. Is the EXACT hostname registered in Agent Registry│
        │    (agents / mcp-servers / endpoints)?               │
        └────────────┬─────────────────────────────┬───────────┘
                no   │                         yes │
                     ▼                             ▼
       ┌──────────────────────────┐  ┌──────────────────────────────┐
       │ Unregistered hostname    │  │ 5. Check IAM / UAP Policies  │
       │ permutation: register on │  │ 6. Authz extension & dual-reg│
       │ consolidated googleapis  │  │ 7. Agent Identity & PAB / CR │
       │ or custom Service entry. │  │ 8–10. Principal, X-Proj, SWP │
       └──────────────────────────┘  └──────────────────────────────┘
```

### Step 0 — Establish context & Disable prompts

Before running any diagnostics, ensure the gcloud CLI is installed (see
[Google Cloud SDK Installation](https://docs.cloud.google.com/sdk/docs/install.md.txt)),
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

    > **Important:** **Check Active Project First**: Always check the active
    > project first before checking any other user-supplied project:
    >
    > ```bash
    > ACTIVE_PROJ=$(gcloud config get-value project)
    > gcloud network-services agent-gateways list --location=us-central1 --project=$ACTIVE_PROJ
    > gcloud agent-registry agents list --location=us-central1 --project=$ACTIVE_PROJ
    > ```
    >
    > If you find the target resources in the active project, **proceed
    > immediately** and do NOT check other projects.

    If you cannot find the target resource (for example, the stuck gateway or
    the failing agent) in the active project:

    1.  **Never write or execute custom Python or bash discovery scripts** (or
        multi-project/multi-region `for` loops) to scan across projects or
        regions. Use individual `gcloud` CLI commands (or `curl` REST API calls
        authenticated with `gcloud auth application-default print-access-token`).
    2.  Check at most **1–2 explicit candidate projects** provided by the user
        in the target region (default `us-central1` if unspecified):

        ```bash
        gcloud network-services agent-gateways list --location=us-central1 --project=$CANDIDATE_PROJECT_ID
        gcloud agent-registry agents list --location=us-central1 --project=$CANDIDATE_PROJECT_ID
        ```

    3.  If you cannot locate any candidate resource within 2 turns, **stop
        searching** and write the diagnostic report using clear placeholders
        for resource names while providing the complete verification commands
        and PSC subnet IP calculation formulas.

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
        registered as Endpoints** (`gcloud agent-registry endpoints list --location=$LOCATION --project=$PROJECT_ID`),
        and provide the `gcloud agent-registry services create` command (using
        `--endpoint-spec-type=no-spec` and `--interfaces=url=https://...,protocolBinding=JSONRPC`)
        to register any missing endpoints.
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
    diagnose it), for any logs or findings where the agent is getting a 403 to
    an MCP server or endpoint, you must **check the IAP Egressor bindings on the
    matching resource in the registry first**:
    *   If there is no registry entry for the MCP server or endpoint, ensure
        there is one created.
    *   Ensure that the agent has the `roles/iap.egressor` role bound to the
        registry entry. If there are no permissions matching, tell the user to
        grant `roles/iap.egressor` against the registry entry.
    *   Verify that an `AuthorizationPolicy` is correctly bound to the Gateway.
4.  Include these prioritized troubleshooting steps for IAP denials (checking
    registry entries and `roles/iap.egressor` bindings first, checking IAP audit
    logs, and verifying Gateway policies) as recommended fixes, even if you
    couldn't verify them in the current log state.

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
# Retrieve recent gateway entries (exclude synthetic 240.0.0.2:443 CONNECT wrapper when inspecting inner L7 calls;
# omit the NOT clause if empty so pre-IAP default_denied routing drops remain visible):
gcloud logging read 'resource.type="networkservices.googleapis.com/Gateway" AND resource.labels.location="REGION" AND resource.labels.gateway_name="AGENT_GATEWAY_NAME" AND NOT jsonPayload.enforcedGatewaySecurityPolicy.hostname="240.0.0.2:443"' --project=PROJECT_ID --limit=50
```

The gateway log entry shows the actual hostname the request targeted. Write it
down — you will need it in Step 4.

**Model Armor & SGP Special Cases (High-Confidence Indicators):**
-   **Model Armor `PERMISSION_DENIED` (BKI 13)**: If `serviceExtensionInfo` shows `grpcStatus: "PERMISSION_DENIED"` on `modelarmor.*`, check gateway direction — Client-to-Agent ingress uses `service-${AGENT_PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com` whereas Agent-to-Anywhere egress uses `service-${GATEWAY_PROJECT_NUMBER}@gcp-sa-dep.iam.gserviceaccount.com` (see `references/known-issues.md` BKI #13).
-   **Model Armor 60s Stream Cutoff (BKI 13 / Step 14)**: If `grpcStatus` reports `UNKNOWN` / `DEADLINE_EXCEEDED` or `Stream removed` right at **60 seconds**, Envoy hit the non-configurable 60s `CONTENT_AUTHZ` stream deadline.
-   **Semantic Governance Policy Denial (BKI 38 / Step 14)**: Query `logName="projects/PROJECT_ID/logs/semantic-governance-policy"` for SGP `jsonPayload.verdict` and `jsonPayload.evaluations[].rationale` (note: streamed model calls return no verdict or an error).

### Step 3 — Check IAP allow/deny decision

> **Important:** **Data Access Logs & API Prerequisite**: IAP data-plane decisions are written to **Data Access audit logs** (`DATA_READ` type, disabled by default), and `iap.googleapis.com` must be enabled in the gateway project (`gcloud services list --enabled --filter="config.name:iap.googleapis.com" --project=$PROJECT_ID`). Verify audit config with:
>
> ```bash
> gcloud projects get-iam-policy $PROJECT_ID \
>   --filter="auditConfigs.service:iap.googleapis.com" \
>   --format="yaml(auditConfigs)"
> ```
>
> If empty or missing `DATA_READ` for `iap.googleapis.com`, enable it in **IAM → Audit Logs**.

Query both UAP Policy V2 (`iap.resources.egressViaIAP`) and legacy IAM v1
(`iap.webServiceVersions.egressViaIAP`) while excluding MCP base-protocol noise:

```text
protoPayload.serviceName="iap.googleapis.com"
(protoPayload.authorizationInfo.permission="iap.resources.egressViaIAP" OR protoPayload.authorizationInfo.permission="iap.webServiceVersions.egressViaIAP")
-protoPayload.metadata.mcp_attributes.base_protocol_method="true"
```

**Alternative (CLI Fallback):**

```bash
gcloud logging read 'protoPayload.serviceName="iap.googleapis.com" AND (protoPayload.authorizationInfo.permission="iap.resources.egressViaIAP" OR protoPayload.authorizationInfo.permission="iap.webServiceVersions.egressViaIAP") AND -protoPayload.metadata.mcp_attributes.base_protocol_method="true"' --project=PROJECT_ID --limit=50
```

What to read out of each entry:

-   **`protoPayload.authorizationInfo[].granted`** — `true` or `false`.
-   **`protoPayload.authenticationInfo.principalSubject`** — the SPIFFE /
    `principal://...` URI of the caller.
-   **`protoPayload.authorizationInfo[].resource`** — the registered resource
    the call resolved to.
-   **`labels."iap.googleapis.com/audited_resource_name"`** — if this is
    `unregisteredResource`, the destination hostname isn't in the registry. Go
    to Step 4.
-   **The policy version & enforcement mode** — in `AuthzExtension` (`name`,
    `service`, and `timeout` are all required on `import`), `iapPolicyVersion`
    is uppercase `"V2"` (logged lowercase `"v2"` in audit logs):

    ```yaml
    name: projects/PROJECT_ID/locations/LOCATION/authzExtensions/iap-authz-ext
    service: iap.googleapis.com
    failOpen: false
    timeout: 1s
    metadata:
      iamEnforcementMode: "DRY_RUN"  # omit (or set "ENFORCE", never "ENFORCED") for active blocking
      iapPolicyVersion: "V2"        # "V2" for UAP Policy V2; "V1" (or omit) for legacy IAM v1
    ```

    *   **In `DRY_RUN` mode**, denials are logged but the request proceeds. If
        your agent fails with a real `403` while IAP is in dry-run, check the
        gateway proxy load-balancer log (Step 3b) or the destination backend.
    *   **Under UAP (`iapPolicyVersion: "v2"`)**, check
        `protoPayload.metadata.policyEvaluationResults[]` and audit log entries.
        UAP logs will display the evaluation outcomes across the Resource
        Manager hierarchy (Organization, Folder, Project).
        *   If an **explicit DENY** matched anywhere in the hierarchy (e.g., at
            Org or Folder level), the request is rejected immediately, even if a
            project-level policy allows it.
        *   If **no ALLOW matched**, the request is denied by default-deny.
        *   Check for CEL attribute mismatches (e.g., calling an unregistered
            host when policies only allow `destination.agent_registry.*`, or
            path mismatches like missing `.json` extensions in REST API paths).

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

> **Note:** **CLIENT_TO_AGENT Gateways**: Both ingress (`CLIENT_TO_AGENT`) and
> egress (`AGENT_TO_ANYWHERE`) gateways can be stuck in provisioning. Ingress
> gateways do NOT populate the `agentGatewayCard` even when active, so check
> whether they are stuck by describing their network attachment and calculating
> subnet IPs.

1.  **Find the Agent Gateway Name** (if not provided): List the gateways in the
    project to find the one that is stuck or relevant:

    ```bash
    gcloud network-services agent-gateways list --location=$LOCATION --project=$PROJECT_ID
    ```

2.  **Identify the Network Attachment**: Describe the Agent Gateway to find the
    Network Attachment in use:

    ```bash
    gcloud network-services agent-gateways describe AGENT_GATEWAY_NAME --location=$LOCATION --project=$PROJECT_ID
    ```

    Look for `networkConfig.egress.networkAttachment` or
    `networkConfig.ingress.networkAttachment` (depending on gateway type).

3.  **Describe the Network Attachment**:

    ```bash
    gcloud compute network-attachments describe NETWORK_ATTACHMENT_NAME --region=$LOCATION --project=$PROJECT_ID
    ```

    Note the `subnetwork` field.

4.  **Inspect the Subnet**: Describe the subnet to check its IP range:

    ```bash
    gcloud compute networks subnets describe SUBNET_NAME --region=$LOCATION --project=$PROJECT_ID
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

### Step 3d — Diagnosing Agent Connectivity Template (ACT) & Network Routing

Under VPC Service Controls (VPC-SC), Agent Gateway relies on an **Agent
Connectivity Template (ACT)**. If the agent experiences timeouts, silent
connection hangs, or connection drops when attempting to reach public internet
endpoints or internal services, check the ACT and consumer network
configuration:

1.  **Inspect the Agent Connectivity Template**:

    ```bash
    gcloud network-services agent-connectivity-templates describe ACT_NAME \
      --location=$LOCATION --project=$PROJECT_ID
    ```

    Verify the `egressNetworkConfig.vpcEgress` mode:

    -   `vpcEgress: ALL_TRAFFIC`: Routes **all** outbound traffic (public
        internet, SaaS APIs, internal RFC 1918, and Google APIs) through the
        consumer VPC Network Attachment. **Mandatory for VPC Service Controls
        (VPC-SC).**
    -   `vpcEgress: PRIVATE_RANGES_ONLY`: Routes only private/restricted ranges
        (RFC 1918, RFC 6598 `100.64.0.0/10`, Class E `240.0.0.0/4`,
        `private.googleapis.com` `199.36.153.8/30`, and
        `restricted.googleapis.com` `199.36.153.4/30`) into the consumer VPC;
        standard Google APIs use Private Google Access and public internet
        traffic egresses directly from Agent Gateway.

2.  **Verify Consumer Cloud NAT for External Endpoints (BKI 28)**: When
    `vpcEgress: ALL_TRAFFIC` is enabled, external internet traffic (e.g.,
    `api.ipify.org`, `api.weather.gov`, third-party SaaS) traverses the gateway
    and exits through the consumer VPC PSC-I Network Attachment subnet.

    -   **Cloud NAT Requirement**: The consumer VPC **MUST** have a Cloud NAT
        gateway covering the PSC-I subnet range (with Private Google Access
        enabled on the subnet).
    -   If Cloud NAT is missing or does not cover the PSC-I subnet, TCP
        connections to external internet endpoints **hang silently or reset**
        without a proxy error log.
    -   Verify NAT status:

        ```bash
        gcloud compute routers nats list --router=$ROUTER_NAME --region=$LOCATION --project=$PROJECT_ID
        ```

3.  **Verify Cloud DNS Peering Scope (See Step 12)**: Agent Gateway resolves
    public internet domains and non-VPC-SC Google APIs via public recursive DNS
    at the gateway proxy **without** Cloud DNS peering. `dnsPeeringConfig` is
    required **only** for private internal domains (e.g., `corp.internal.`) or
    when enforcing VPC-SC (`googleapis.com.` mapped to
    `restricted.googleapis.com` `199.36.153.4/30` or internal PSC endpoints).

4.  **Ordered 7-Step Teardown & Dangling ACT References (BKI 30)**: Always
    delete resources in strict dependency order, polling each async operation
    to `404` before proceeding:
    1. Delete or unbind `ReasoningEngine` instances (`?force=true` on REST `DELETE` if active sessions/memories exist).
    2. Delete UAP `PolicyBinding` then `AccessPolicy` (`gcloud iam policy-bindings delete` → poll `404` → `gcloud iam access-policies delete`).
    3. Delete `AuthzPolicy`, `TelemetryPolicy`, and `ExtensionBinding` resources targeting the gateway.
    4. Delete `AuthzExtension` resources.
    5. Delete `AgentGateway` and poll `gcloud network-services agent-gateways describe` until `NOT_FOUND` (`404`).
    6. Delete `AgentConnectivityTemplate` (`gcloud network-services agent-connectivity-templates delete`), `TrustConfig`, and `NetworkAttachment`.
    7. Delete consumer Cloud NAT, subnets, and VPC.
    - If `AgentConnectivityTemplate` deletion still fails with
      `FAILED_PRECONDITION: Resource ... is already being used by resource(s) .../agentGateways/...`
      after Step 5 confirmed `404` and async producer cleanup has settled,
      unblock deployments immediately by creating a newly named
      `AgentConnectivityTemplate` and open a Google Cloud Support case citing
      the stuck `agentConnectivityTemplates` URI to purge the orphaned
      producer reference.

### Step 4 — Verify the hostname is registered (in the form the agent used)

List registry entries — pick the right resource type for the destination:

```bash
gcloud agent-registry endpoints list      --project=$PROJECT_ID --location=$LOCATION
gcloud agent-registry mcp-servers list    --project=$PROJECT_ID --location=$LOCATION
gcloud agent-registry agents list         --project=$PROJECT_ID --location=$LOCATION
```

Grep the output for the exact hostname from step 2. If it's missing, that's the
root cause.

### Step 5 — Verify IAM / UAP bindings on the registered resource

Depending on whether your gateway uses **IAM v1** or **Unified Access Policy
(UAP / Policy V2)** (determined by `iapPolicyVersion` in the Authz Extension),
verify the corresponding authorization bindings:

#### Option A: Unified Access Policy (UAP / Policy V2 / IAM v3)

In UAP, access policies are bound directly to the **Google Cloud Resource
Manager (CRM) hierarchy** (Project, Folder, or Organization) rather than IAP
shadow resources.

1.  **Search Policy Bindings Attached to the Target Project**:

    ```bash
    # List bindings owned by the project (note: `list` has NO --target flag)
    gcloud iam policy-bindings list --project="${PROJECT_ID}" --location=global

    # Search bindings targeting the project's CRM node
    gcloud iam policy-bindings search-target-policy-bindings \
      --target="//cloudresourcemanager.googleapis.com/projects/${PROJECT_NUMBER}" \
      --project="${PROJECT_ID}" \
      --location=global
    ```

2.  **Search Policy Bindings on Parent Folders / Organization**:

    ```bash
    # Folder level
    gcloud iam policy-bindings search-target-policy-bindings \
      --target="//cloudresourcemanager.googleapis.com/folders/${FOLDER_ID}" \
      --project="${PROJECT_ID}" \
      --location=global

    # Organization level
    gcloud iam policy-bindings search-target-policy-bindings \
      --target="//cloudresourcemanager.googleapis.com/organizations/${ORGANIZATION_ID}" \
      --project="${PROJECT_ID}" \
      --location=global
    ```

3.  **Inspect the Referenced AccessPolicy**:

    ```bash
    gcloud iam access-policies describe ACCESS_POLICY_ID \
      --project="${PROJECT_ID}" \
      --location=global
    ```

    *   Verify the rule uses the full FQDN permission:
        `iap.googleapis.com/resources.egressViaIAP`.
    *   Verify the agent's principal or principal set matches
        `rules[].principals` (watch for orgless `proj-${PROJECT_NUMBER}`, never `project-`).
    *   Inspect CEL conditions: check for null dereferences (`mcp_server.method == 'tools'`), unsupported `.startsWith()`/`.matches()` on `agent_registry.*`, missing `.json` extensions in unregistered REST API paths, or blanket `destination.is_registered == false` `DENY` rules that crash container boot.

4.  **Check for Org Policy Constraint Blockers (BKI 24)**: If `gcloud iam
    policy-bindings create` failed with `CUSTOM_ORG_POLICY_VIOLATION`, check
    whether `constraints/iam.managed.disableAccessPolicyBinding` is enforced:

    ```bash
    gcloud org-policies describe constraints/iam.managed.disableAccessPolicyBinding --project=$PROJECT_ID
    ```

    To unblock, apply an override disabling the constraint (`enforce: false`).
    Note: IAM access policies, bindings, and Org Policy overrides take **~30 to
    60 seconds** to propagate.

5.  **REST API Fallback for UAP Bindings**:

    ```bash
    curl -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
      "https://iam.googleapis.com/v3/projects/${PROJECT_ID}/locations/global/policyBindings"
    ```

#### Option B: IAM v1 (Legacy Policy Model)

In IAM v1, `roles/iap.egressor` is bound directly to the IAP shadow resource at
the registry or endpoint level:

##### Registry-level IAM policy

```bash
curl -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
  -d '{}' \
  -X POST "https://iap.googleapis.com/v1/projects/${PROJECT_NUMBER}/locations/${LOCATION}/iap_web/agentRegistry:getIamPolicy" \
  -H "Content-Type: application/json"
```

##### Per-endpoint IAM policy

```bash
curl -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
  -d '{}' \
  -X POST "https://iap.googleapis.com/v1/projects/${PROJECT_NUMBER}/locations/${LOCATION}/iap_web/agentRegistry/endpoints/${ENDPOINT_ID}:getIamPolicy" \
  -H "Content-Type: application/json"
```

##### Same call, but for global registry:

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
gcloud service-extensions authz-extensions list \
  --location=$LOCATION --project=$PROJECT_ID

gcloud service-extensions authz-extensions describe RESOURCE_NAME \
  --location=$LOCATION --project=$PROJECT_ID
```

#### Verify AuthorizationPolicy & AuthzExtension Wiring

1.  **Check `iapPolicyVersion` in Authz Extension**: Describe the Authz
    Extension and inspect the `metadata` map:

    ```bash
    gcloud service-extensions authz-extensions describe RESOURCE_NAME \
      --location=$LOCATION --project=$PROJECT_ID --format="yaml(metadata)"
    ```

    -   If using **UAP (Policy V2)**: `iapPolicyVersion` MUST be explicitly set
        to `"V2"`.
    -   If using **IAM v1**: `iapPolicyVersion` is `"V1"` or unset.
    -   Check `iamEnforcementMode`: `"DRY_RUN"` logs evaluations without
        blocking; omitting `iamEnforcementMode` (or setting `"ENFORCE"`, never
        `"ENFORCED"`) actively blocks.

2.  **Verify AuthorizationPolicy Binding**: Verify that the
    `AuthorizationPolicy` is correctly bound to your `Gateway` (and **omits
    `target.loadBalancingScheme`** when targeting `agentGateways/*`). If it is
    not bound, the authorization logic will not run on gateway traffic.

    -   Inspect the `AuthorizationPolicy` resource.
    -   Ensure the policy's target matches the gateway's name and location.

3.  **Verify Multi-Registry Gateway Constraints (BKI 26)**: Inspect the Agent
    Gateway description:

    ```bash
    gcloud network-services agent-gateways describe AGENT_GATEWAY_NAME \
      --location=$LOCATION --project=$PROJECT_ID --format="yaml(registries)"
    ```

    -   Network Services permits at most **2 registries** bound to an Agent
        Gateway.
    -   When 2 registries are configured, **exactly ONE must be `global`** and
        the second must be **`regional` (same region as gateway) or
        `multi-regional` (same jurisdiction, e.g., `us-central1` + `us`)**.
    -   Configuring two regional, two multi-regional, two global, or
        cross-jurisdiction registries is rejected with HTTP `400` /
        `InvalidArgument`.

#### List authz policies, agent gateways, and authz extensions via raw API

```bash
# authzPolicies (use v1beta1 if inspecting L4 networkRules; v1 for GA httpRules/CUSTOM)
curl -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
  "https://networksecurity.googleapis.com/v1beta1/projects/${PROJECT_ID}/locations/${LOCATION}/authzPolicies"

# agentGateways
curl -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
  "https://networkservices.googleapis.com/v1/projects/${PROJECT_ID}/locations/${LOCATION}/agentGateways"

# authzExtensions (hosted under networkservices.googleapis.com, NOT serviceextensions.googleapis.com)
curl -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
  "https://networkservices.googleapis.com/v1/projects/${PROJECT_ID}/locations/${LOCATION}/authzExtensions"
```

### Step 7 — Verify the agent identity has the baseline roles

The agent identity itself needs least-privilege baseline permissions on the
source side:

-   **Least-privilege check (`agentDefaultAccess` & `agentInvoker`)**: Deployed
    Agent Identities automatically receive `roles/aiplatform.agentDefaultAccess`
    and `roles/aiplatform.agentContextEditor`. Do **NOT** grant project-level
    `roles/aiplatform.user` or `roles/aiplatform.expressUser` to an Agent
    Identity (they allow modifying/deleting sibling `ReasoningEngine` instances);
    for A2A calls, bind a custom `agentInvoker` role
    (`aiplatform.reasoningEngines.{query,get}`) on the target engine only.
-   `roles/agentregistry.viewer` — to discover registered catalog entries and
    validate gateway bindings
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

# Inspect policy bindings attached to the project resource
gcloud iam policy-bindings search-target-policy-bindings \
  --location=global \
  --project="${PROJECT_ID}" \
  --target="//cloudresourcemanager.googleapis.com/projects/${PROJECT_NUMBER}"
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

### Step 9 — Cross-Project Runtime-to-Gateway Binding Verification

When an Agent Runtime (Reasoning Engine) in Project A (`AE_PROJECT_NUMBER`)
binds to an Agent Gateway in Centralized Governance Project B
(`AGW_PROJECT_ID`):

1.  **Check Deployer Caller Permissions:** Verify the deploying identity has
    `roles/networkservices.viewer` (or `networkservices.agentGateways.get` and
    `networkservices.agentGateways.use`) on the gateway in Project B:

    ```bash
    gcloud network-services agent-gateways describe GATEWAY_NAME \
      --project=AGW_PROJECT_ID \
      --location=REGION
    ```
2.  **Check Vertex AI Service Agent IAM in Gateway Project:** Ensure Project A's
    service agent is authorized in Project B:

    ```bash
    gcloud projects get-iam-policy AGW_PROJECT_ID \
      --flatten="bindings[].members" \
      --filter="bindings.members:service-AE_PROJECT_NUMBER@gcp-sa-aiplatform.iam.gserviceaccount.com" \
      --format="table(bindings.role)"
    ```

    Must have `roles/networkservices.viewer` or custom role
    `ae_agw_cross_project_sa`
    (`networkservices.agentGateways.get,networkservices.operations.get`).
3.  **Validate Regional Colocation Invariant:** Both the runtime and the gateway
    **MUST** be deployed in the exact same region (e.g. `us-central1`).
    Cross-region bindings fail control plane validation with `INVALID_ARGUMENT`.
4.  **Verify Context-Aware Access (CAA) Token Sharing Opt-Out:** Verify that the
    agent runtime was deployed with:
    `"GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES": False` Without
    this, bound token enforcement drops credentials during cross-project egress,
    returning `401 Context-Aware Access requirements are not met`.
5.  **Validate IAP Policy Target (Server-Generated Resource ID vs. Friendly
    Name):** Ensure IAP policies (`gcloud iap web add-iam-policy-binding --resource-type=agent-registry`)
    target the server-generated resource ID (`agentregistry-00000000-...`
    extracted via `registryResource`), NOT the friendly service name:

    ```bash
    gcloud agent-registry services describe MCP_SERVICE_NAME \
      --project=AGW_PROJECT_ID \
      --location=REGION \
      --format='value(registryResource)'
    ```
6.  **Verify Cross-Project VPC Service Controls (VPC-SC):** If Project A and
    Project B are in separate perimeters, ensure a perimeter bridge or
    ingress/egress rules cover `aiplatform.googleapis.com`,
    `networkservices.googleapis.com`, and `agentregistry.googleapis.com`.

### Step 10 — Diagnose Secure Web Proxy (SWP) and Policy-Based Routing (PBR) Egress

> **Note:** **Pattern A (Transparent Next-Hop SWP + PBR — This Step)** preserves full Agent Gateway L7 governance (IAP/UAP, Model Armor, SGP) before VPC next-hop inspection. If your Agent Runtime container instead sets `HTTPS_PROXY=https://proxy.corp.internal:443` to tunnel through an explicit forward proxy via L4 `networkRules`, jump to **Step 11**.

If the consumer VPC employs a downstream Secure Web Proxy (SWP) behind an Agent
Gateway Network Attachment for Layer 7 inspection:

1.  **Verify Next-Hop SWP Deployment Mode**: Confirm SWP is deployed directly in
    the consumer VPC with `type: SECURE_WEB_GATEWAY` and
    `routingMode: NEXT_HOP_ROUTING_MODE`. Do NOT attempt to use PSC Service
    Attachments (which only support explicit `HTTP CONNECT` proxies) or static
    routes (which fail because Network Attachments cannot bear VM instance tags).
2.  **Verify Policy-Based Routing (PBR) Matching**:
    Ensure a PBR exists with priority 200 matching source CIDR of the PSC-I subnet
    (`10.20.1.0/24`) and destination `0.0.0.0/0` routing to `--next-hop-ilb-ip=<SWP_IP>`:

    ```bash
    gcloud network-connectivity policy-based-routes create agw-psci-to-swp-pbr \
      --network=projects/PROJECT_ID/global/networks/VPC_NAME \
      --source-range=10.20.1.0/24 \
      --destination-range=0.0.0.0/0 \
      --next-hop-ilb-ip=10.20.1.250 \
      --priority=200 \
      --project=PROJECT_ID
    ```

    Ensure a default fallback PBR exists with priority 1000 routing to `DEFAULT_ROUTING`.
3.  **Verify Cloud NAT `ENDPOINT_TYPE_SWG` on Proxy Subnet**:
    Ensure the Cloud NAT covering the proxy-only subnet (`REGIONAL_MANAGED_PROXY`)
    includes `--endpoint-types=ENDPOINT_TYPE_VM,ENDPOINT_TYPE_SWG`. Without this,
    SWP proxy backends cannot establish outbound connections to the internet.
4.  **Verify GatewaySecurityPolicy CEL Allowlist**:
    Check SWP logs for `DENIED` decisions under `networkservices.googleapis.com/Gateway`.
    Verify that both external target domains and the regional AI Platform session
    endpoint (`<region>-aiplatform.mtls.googleapis.com`) are allowed in CEL rules:

    ```cel
    inUrlList(host(), ['api.weather.gov', 'api.ipify.org', 'REGION-aiplatform.mtls.googleapis.com'])
    ```

    Omission of the regional AI Platform endpoint breaks ADK streaming queries
    with HTTP 503 (`remote connection failure`).

### Step 11 — Diagnose Explicit HTTPS Proxy Egress (`HTTPS_PROXY` + L4 `networkRules`)

When an Agent Runtime container is configured with `HTTPS_PROXY=https://proxy.corp.internal:443` (explicit forward proxy over TLS) instead of transparent Next-Hop SWP:

1.  **Diagnose `HTTP 404 Not Found` (`CONNECT tunnel failed, response 404`)**:
    -   **Cause**: Agent Gateway's default L7 listener terminates outer TLS and rejects nested `HTTP CONNECT` requests with `404` when no L4 `networkRules` policy matches the proxy's SNI (or when the proxy listens on plaintext HTTP instead of TLS `:443`, or `:443` was omitted from `HTTPS_PROXY`).
    -   **Verify L4 `AuthzPolicy` (`v1beta1`) & Consumer Proxy ACLs**: Confirm an `AuthzPolicy` with `action: ALLOW` and `networkRules` matching the proxy's exact SNI is imported via **`gcloud beta`** (GA `gcloud` rejects `networkRules`), **omits `target.loadBalancingScheme`**, omits `ports`, and either omits `from` or includes `7.0.0.0/8` + PSC-I CIDR in `from.sources[].ipBlocks` (while consumer VPC firewall/Squid ACLs allow only the consumer PSC-I subnet CIDR, never `7.0.0.0/8`):
        ```bash
        gcloud beta network-security authz-policies describe ALLOW_PROXY_POLICY_NAME \
          --location=$LOCATION --project=$PROJECT_ID
        ```
2.  **Verify `NO_PROXY` / `no_proxy` Exclusions (Prevent Control-Plane Hair-Pinning)**:
    -   Inspect the Reasoning Engine's `deploymentSpec.env` and verify `NO_PROXY` and `no_proxy` exclude metadata and (where direct Google API routing is desired) Google APIs:
        `169.254.169.254,metadata.google.internal,localhost,127.0.0.1,.googleapis.com,googleapis.com`
    -   Missing `NO_PROXY` routes metadata or Vertex AI session/telemetry calls into the external corporate proxy, causing boot hangs or `403` authentication failures.
3.  **Verify Container-Side Private CA Trust**:
    -   ACT `tlsConfig.trustConfig` does **not** apply to L4-bypassed `loopback_tls_network_authz` tunnels. If the explicit proxy uses a private CA or performs TLS inspection, bundle both the proxy CA and system roots inside the agent container (`SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `GRPC_DEFAULT_SSL_ROOTS_FILE_PATH`).
4.  **Account for the L7 Governance Trade-Off**:
    -   Matching an L4 `networkRules` `ALLOW` rule bypasses L7 TLS termination at Agent Gateway, skipping IAP/UAP, Model Armor, SGP, and L7 `httpRules` on traffic inside that proxy tunnel. Use **Step 10 (Next-Hop SWP + PBR)** if both Agent Gateway L7 governance and downstream VPC proxy inspection are required.

### Step 12 — Diagnose Cloud DNS Peering (2-Hop Limit) & Cross-Project Shared VPC IAM

When private hostnames fail with `NXDOMAIN` / `503` or gateway/ACT creation fails with `PERMISSION_DENIED`, `INVALID_ARGUMENT`, or `Code 13`:

1.  **Inspect `AgentConnectivityTemplate` `dnsPeeringConfig`**:
    ```bash
    gcloud network-services agent-connectivity-templates describe $ACT_NAME \
      --location=$LOCATION --project=$PROJECT_ID --format="yaml(egressNetworkConfig)"
    ```
    -   Every entry in `dnsPeeringConfig.domains[]` must end with a trailing dot (e.g., `corp.internal.`, `googleapis.com.`).
    -   `dnsPeeringConfig.targetNetwork` is a single string URI (`projects/TARGET_VPC_PROJECT_ID/global/networks/VPC_NAME`) using the **Project ID** (not project number). Verify `networkAttachment`'s subnet belongs to the expected VPC (or a region supporting decoupled hub `targetNetwork`).
2.  **Check the 2-Hop Transitive DNS Peering Limit & Root `"."` Zone Trap**:
    ```bash
    gcloud dns managed-zones list --project=$TARGET_VPC_PROJECT_ID \
      --format="table(name,dnsName,visibility,peeringConfig.targetNetwork.networkUrl,forwardingConfig)"
    ```
    -   **2-Hop Limit**: Agent Gateway's tenant peering zone consumes **Hop 1** (`Tenant VPC → Attached Spoke VPC`). If the Attached Spoke VPC uses a Cloud DNS Peering Zone (**Hop 2**) pointing to a Central Hub VPC, **the Central Hub VPC MUST host an Authoritative Private Zone** (or resolve locally). Chaining to a *third* DNS Peering Zone returns `NXDOMAIN` / `SERVFAIL` (`503`).
    -   **Root `"."` Domain Trap**: Peering `"."` works **only** with a Cloud DNS **Private Forwarding Zone** pointing to an upstream recursive resolver. Configuring an **Authoritative** Private Zone for `"."` breaks all public internet and `*.googleapis.com` resolution with `NXDOMAIN`.
3.  **Verify Dual-Principal Cross-Project / Shared VPC IAM on `TARGET_VPC_PROJECT_ID`**:
    -   **Caller / Provisioning Identity**: Needs `roles/compute.networkViewer`, `roles/dns.reader`, `roles/networkconnectivity.regionalEndpointAdmin`, and `roles/networkconnectivity.consumerNetworkAdmin` (or `roles/viewer`) on the host project, plus `compute.networkAttachments.use` (`roles/compute.networkUser`) when referencing a host-project attachment.
    -   **Agent Gateway Service Agent (`service-${AGW_PROJECT_NUMBER}@gcp-sa-agentgateway.iam.gserviceaccount.com`)**: Needs `roles/dns.peer`, `roles/dns.reader`, and `roles/compute.networkViewer` plus `roles/compute.networkUser` (when Network Attachment is in the service project, recommended) OR `roles/compute.networkAdmin` (when Network Attachment is in the host project):
        ```bash
        gcloud projects get-iam-policy $TARGET_VPC_PROJECT_ID \
          --flatten="bindings[].members" \
          --filter="bindings.members:service-${AGW_PROJECT_NUMBER}@gcp-sa-agentgateway.iam.gserviceaccount.com" \
          --format="table(bindings.role)"
        ```

### Step 13 — Diagnose Private CA `TrustConfig` TLS Failures & ACT Immutability

When private HTTPS destinations or `*.googleapis.com` calls fail TLS verification after attaching a Certificate Manager `TrustConfig`:

1.  **Inspect `TrustConfig` & `additionalRoots`**:
    ```bash
    gcloud certificate-manager trust-configs describe $TRUST_CONFIG_NAME \
      --location=$LOCATION --project=$PROJECT_ID
    ```
    -   Confirm the `TrustConfig` is in the **exact same project and region** as the Agent Gateway and `AgentConnectivityTemplate`, and that target server certificates include a **Subject Alternative Name (SAN)** matching the hostname.
    -   **`*.googleapis.com` Breakage (`PUBLICLY_TRUSTED_ROOTS`)**: Check `egressNetworkConfig.tlsConfig.additionalRoots` on the ACT. If set to `NO_ADDITIONAL_ROOTS`, Agent Gateway rejects Google-signed certificates for `*.googleapis.com` and all public HTTPS APIs! Set `additionalRoots: PUBLICLY_TRUSTED_ROOTS`.
2.  **Apply Updates via New ACT + Gateway Rebind (Immutability Rule)**:
    -   `tlsConfig.trustConfig` is **immutable** on an existing `AgentConnectivityTemplate`, and attached Agent Gateways **do not pick up in-place `tlsConfig` edits**.
    -   **Fix**: Create a **new** `AgentConnectivityTemplate` (e.g., `act-v2`) referencing the **same** `networkAttachment` with the corrected `tlsConfig`, then re-import/update the `AgentGateway` YAML to point `agentConnectivityTemplate` to `act-v2`.

### Step 14 — Diagnose SGP, Model Armor 60s Stream Timeouts, Native MCP Rules, & Cloud Trace

1.  **Semantic Governance Policies (SGP)**:
    -   Query SGP data-plane evaluation logs (`verdict`, `evaluations[].rationale`, `token_usage`):
        ```bash
        gcloud logging read 'logName="projects/'$PROJECT_ID'/logs/semantic-governance-policy"' \
          --project=$PROJECT_ID --limit=20
        ```
    -   If streamed model calls (`:streamGenerateContent`, `:streamRawPredict`) return **no verdict or an error** (or produce zero entries in `logs/semantic-governance-policy`), invoke models **without streaming** and verify the `CONTENT_AUTHZ` `AuthzPolicy` includes the non-streaming `when` CEL filter using `.contains()` (`:generateContent`, `:rawPredict`, `/v1/messages`, `/chat/completions`) while excluding `application/grpc` (unexcluded gRPC crashes startup).
    -   If SGP unexpectedly began blocking in staging, inspect `gcloud service-extensions authz-extensions describe $EXT_NAME --location=$LOCATION --project=$PROJECT_ID --format="yaml(metadata)"` — updating `sgpUserIntentMatching` replaces the entire `metadata` map and wipes `sgpEnforcementMode: "DRY_RUN"` if omitted.
    -   If SGP policy/engine CLI commands return `SEMANTIC_GOVERNANCE_POLICY_AGENT_NOT_CONFIGURED` or `SEMANTIC_GOVERNANCE_POLICY_ENGINE_NOT_ENABLED_IN_REGION`, confirm the Reasoning Engine was created with `AGENT_IDENTITY` + `agent_gateway_config`, `service-${PROJECT_NUMBER}@gcp-sa-aiplatform.iam.gserviceaccount.com` has `roles/compute.networkAdmin` and `roles/dns.admin`, consumer VPC subnets avoid `10.0.0.0/24`–`10.0.2.0/24`, and the engine is `ACTIVE` (with ACT DNS peering resolving `dnsRecord`).
2.  **Model Armor (`CONTENT_AUTHZ`) `PERMISSION_DENIED` vs. 60s `Stream removed`**:
    -   **`PERMISSION_DENIED` (BKI 13)**: Check gateway direction! **Client-to-Agent (ingress)** requires `roles/modelarmor.calloutUser` (agent project) + `roles/modelarmor.user` (template project) on `service-${AGENT_PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com` (and sanitizes **only** ADK `streamQuery`). **Agent-to-Anywhere (egress)** requires `roles/modelarmor.calloutUser` + `roles/serviceusage.serviceUsageConsumer` (gateway project) + `roles/modelarmor.user` (template project) on `service-${GATEWAY_PROJECT_NUMBER}@gcp-sa-dep.iam.gserviceaccount.com`.
    -   **`500`/`504` or gRPC `UNKNOWN: Stream removed` at ~60s**: Envoy enforces a hard 60-second total stream deadline on `CONTENT_AUTHZ`. Narrow `AuthzPolicy.httpRules` to exclude long-running streams or gRPC channels.
3.  **Native MCP `AuthzPolicy` Handshake `403`**:
    -   If `AuthzPolicy` uses `httpRules[].to.operations[].mcp` with `action: ALLOW` and MCP clients fail on `initialize` or `ping`, set `baseProtocolMethodsOption: MATCH_BASE_PROTOCOL_METHODS` (default is `SKIP_BASE_PROTOCOL_METHODS`).
4.  **Missing Spans in Cloud Trace (`TelemetryPolicy` Preview)**:
    -   Verify `cloudtrace.googleapis.com` is enabled, `gcloud beta network-services telemetry-policies describe $POLICY_NAME --location=$LOCATION --project=$PROJECT_ID` targets the gateway with non-zero `samplingRate`, and **`roles/cloudtrace.agent`** is granted on the project to all three gateway service agents (`service-${PROJECT_NUMBER}@compute-system.iam.gserviceaccount.com`, `service-${PROJECT_NUMBER}@gcp-sa-networksecurity.iam.gserviceaccount.com`, `service-${PROJECT_NUMBER}@gcp-sa-agentgateway.iam.gserviceaccount.com`) plus the calling agent's workload SA (for parent spans).

## Quick reference: the checks in order

When triaging a `403` or connection failure, walk these in order:

1.  Confirm the error in the agent log (`403` vs. SSL Handshake Timeout vs. Connection Reset vs. Crash).
2.  Find the *exact hostname* in the gateway log (if `403`).
3.  Check IAP audit log: decision, principal, policy version (`iapPolicyVersion="v2"` vs. `"V1"`), `iamEnforcementMode`, and watch for `unregisteredResource`.
    -   3b. If no IAP audit entry, pull gateway proxy load-balancer log.
    -   3c. If SSL Handshake Timeout or Connection Reset, run the PSC Subnet Exhaustion Check (`subnets describe`, `/28` → `/26`).
    -   3d. If timeouts or silent connection drops to public internet under VPC-SC, verify Agent Connectivity Template (`vpcEgress: ALL_TRAFFIC` vs. `PRIVATE_RANGES_ONLY`) and Consumer Cloud NAT routing.
4.  Confirm exact hostname permutation is registered in Agent Registry (`googleapis` consolidated service + custom entries).
5.  Check IAM / UAP Policies on the target:
    -   IAM v1: Check `roles/iap.egressor` (`--resource-type=agent-registry`).
    -   UAP (Policy V2): Check CRM `PolicyBinding` (`search-target-policy-bindings`) and `AccessPolicy` across Project, Folder, and Org; check `constraints/iam.managed.disableAccessPolicyBinding` (~30–60s propagation).
6.  Check `AuthzExtension` (`iapPolicyVersion: "V2"` vs. `"V1"`), `AuthzPolicy` targets (omit `loadBalancingScheme`), and multi-registry constraints (max 2: 1 `global` + 1 same-region or same-jurisdiction multi-regional).
7.  Confirm least-privilege Agent Identity roles (no `expressUser` / `aiplatform.user`; use `agentInvoker` for A2A). 7b. Check PAB policies. 7c. Check Cloud Run egress auth (SA impersonation or `--iap --functional-type=mcp-server`).
8.  If behavior is flaky, test with a 1:1 `principal://` binding.
9.  If cross-project runtime binding (Project A → Gateway in Project B), verify deployer and service agent viewer permissions on Project B, regional colocation, CAA opt-out (`GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES: False`), and server-generated resource UUID in IAP bindings.
10. If routing egress through a transparent downstream Secure Web Proxy (SWP), verify `NEXT_HOP_ROUTING_MODE`, PBR priority 200 on PSC-I subnet to `--next-hop-ilb-ip`, Cloud NAT `ENDPOINT_TYPE_SWG`, and `GatewaySecurityPolicy` CEL allowlist.
11. If routing egress through an explicit corporate proxy (`HTTPS_PROXY=https://...:443` returning `404`), verify `gcloud beta` L4 `AuthzPolicy` (`networkRules` matching `snis`), `NO_PROXY`, container Private CA trust, and L7 bypass trade-offs.
12. If private DNS returns `NXDOMAIN` or Shared VPC setup fails, verify `dnsPeeringConfig` trailing dots, the **2-hop transitive DNS peering limit** (authoritative zone at Hop 2), root `"."` forwarding-only rule, and dual-principal Host Project IAM.
13. If Private CA `TrustConfig` breaks `*.googleapis.com` or edits fail to apply, set `additionalRoots: PUBLICLY_TRUSTED_ROOTS` on a **new** ACT and rebind the `AgentGateway`.
14. If requests fail at 60s (`Stream removed`), return no SGP verdict or error on streaming, block MCP `initialize`, or drop Cloud Trace spans, verify Model Armor `httpRules` scoping & ingress/egress SAs, SGP non-streaming invocation + `.contains()` CEL filter & full `metadata` map, MCP `MATCH_BASE_PROTOCOL_METHODS`, and `TelemetryPolicy` `roles/cloudtrace.agent` grants.
