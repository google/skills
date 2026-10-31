---
name: agent-platform-troubleshooting
description: >-
  Troubleshoots Google Cloud Gemini Enterprise Agent Platform issues across Agent Gateway, Agent Connectivity Templates (ACT), Agent Registry, Agent Identity, Identity-Aware Proxy (IAP), Unified Access Policies (UAP), Model Armor, Semantic Governance Policies (SGP), Cloud DNS peering, Private CA TrustConfig, Next-Hop Secure Web Proxy (SWP), Explicit HTTPS Proxy (L4 AuthzPolicy), and Cloud Trace.
  Use when agent requests fail with 401/403/404/498/500/503 or Code 13, Egress request is not authorized, HTTP CONNECT fails with 404, Agent Runtime crashes on startup, or gateway/ACT/IAP/Model Armor/SGP configs fail validation.
  Don't use for general Google Cloud Identity and Access Management (IAM) debugging or networking issues unrelated to the Agent Platform stack.
metadata:
  version: "1.1.0"
  category: AiAndMachineLearning
---

# Agent Platform Troubleshooting

> **Important:** You MUST ONLY use the reference files located in this skill's
> `references/` directory (`references/field-manual.md`,
> `references/known-issues.md`, `references/agent-gateway.md`,
> `references/policies.md`, `references/agent-registry.md`,
> `references/agent-identity.md`). Do NOT search for or read external playbooks
> outside this directory.

Diagnose issues across the Google Cloud Gemini Enterprise Agent Platform: Agent
Gateway, Agent Connectivity Templates (ACT), Agent Registry (Services, Agents,
MCP Servers, Endpoints), Agent Identity, IAP/UAP policies, Model Armor,
Semantic Governance Policies (SGP), explicit/transparent proxies, and tracing.
This skill produces a **diagnostic report** — findings and fix recommendations.
It does not apply fixes; the user owns all mutations.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow [Usage Attribution](references/attribution.md). Prefix
direct terminal `gcloud` calls (never generated scripts, Terraform, or user
code) with
`CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:agent-platform-troubleshooting)"`
and append `agent-skills/1.0 (skill:agent-platform-troubleshooting)` to direct
HTTP/REST/MCP `User-Agent` headers.

## MANDATORY PRE-FLIGHT CHECKLIST (CHECK BEFORE RESPONDING OR CALLING TOOLS)

CRITICAL: Before generating ANY response or calling any tools, evaluate the
user's prompt against Rules 1–14. When a Turn-0 rule matches, execute its
directive immediately and STOP.

### Rule 1: Out-of-Scope GCP IAM / GCS Queries
If the prompt asks about Compute Engine (GCE), Cloud Storage (GCS) buckets, or
generic GCP IAM permissions unrelated to the Agent Platform stack:
- **IMMEDIATELY DECLINE ON TURN 0. DO NOT CALL ANY TOOLS OR GIVE IAM GUIDES.**
- Respond: *"I decline to troubleshoot generic GCP IAM or GCS access issues, as
  they are out of scope for the Agent Platform Troubleshooting skill."*

### Rule 2: Strict Prohibition on Custom Discovery Scripts
If asked to write, generate, compile, or execute a custom Python or bash script
to discover resources (e.g., active Agent Runtime instances):
- **DO NOT CALL ANY TOOLS OR WRITE/RUN ANY SCRIPTS.**
- **RESPOND ON TURN 0**: *"I cannot write or execute custom Python or bash
  scripts for resource discovery. Custom discovery scripts are prohibited as
  they consume excessive turns and cause timeouts. Instead, use standard gcloud
  CLI commands (see [Google Cloud SDK Installation](https://docs.cloud.google.com/sdk/docs/install.md.txt))
  or curl REST API calls with application default credentials:
  `gcloud agent-registry agents list --location=us-central1` or `curl -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" "https://us-central1-aiplatform.googleapis.com/v1/projects/PROJECT_ID/locations/us-central1/reasoningEngines"`"*

### Rule 3: Consolidated Registry for Google APIs / Design Queries
If asked about registering multiple Agent Runtime, Cloud Resource Manager, or
Google API interfaces, or structuring services in Agent Registry:
- **DO NOT CALL ANY TOOLS. RESPOND ON TURN 0 WITH**:
  1. Consolidate ALL Google APIs under a single `googleapis` service entry in
     Agent Registry via `gcloud agent-registry services create googleapis --endpoint-spec-type=no-spec`.
  2. Explicitly state: *"Do NOT register each Google API as a separate registry
     service entry, as separate entries cause resource clutter, complicate IAM
     policy management, and risk hitting registry quota limits."*
  3. List all 8 required base FQDN interfaces (plus global
     `https://aiplatform.googleapis.com` when calling global Gemini models):
     - `https://agentregistry.googleapis.com`
     - `https://aiplatform.mtls.googleapis.com`
     - `https://cloudresourcemanager.mtls.googleapis.com`
     - `https://iamcredentials.mtls.googleapis.com`
     - `https://telemetry.mtls.googleapis.com`
     - `https://{region}-aiplatform.mtls.googleapis.com`
     - `https://{region}-aiplatform.googleapis.com`
     - `https://aiplatform.{region}.rep.googleapis.com`
  4. Refer to `references/agent-registry.md` §2 for the full command.

### Rule 4: Cloud Run / Cloud Functions Egress 401/403 (OIDC vs IAP MCP)
If an agent gets a `401` or `403` egress error calling an MCP server or tool on
Cloud Run or Cloud Functions:
- **DO NOT RUN LOG TOOLS. RESPOND ON TURN 0 WITH**:
  1. Explain that direct Agent Identity (`principalSet://...` / `principal://...`)
     to standard Cloud Run OIDC authentication is **not natively supported**.
  2. Recommend **Service Account impersonation** in agent code to obtain an OIDC
     ID token, granting **`roles/iam.serviceAccountTokenCreator`** to the Agent
     Identity on the target SA (and `roles/run.invoker` to that SA on Cloud Run).
  3. Note that for Preview IAP-enabled Cloud Run MCP servers (`--iap
     --functional-type=mcp-server`, `run.app` short URL), authorize via IAP/UAP
     instead of `roles/run.invoker` (see `references/known-issues.md` BKI 21 and
     `references/agent-identity.md`).

### Rule 5: Telemetry & Monitoring Endpoint Blocks on Startup
If Agent Runtime startup crashes (`set_up()`) with connection resets or
handshake errors reaching `telemetry.mtls.googleapis.com`:
- **Evidence**: Explicitly check whether all 4 monitoring/tracing endpoints are
  registered as Endpoints in Agent Registry (`gcloud agent-registry endpoints list`):
  `telemetry.mtls.googleapis.com`, `monitoring.googleapis.com`,
  `trace.mtls.googleapis.com`, and `cloudtrace.googleapis.com`.
- **Recommended Fix**:
  1. Register missing telemetry/tracing interfaces via `gcloud agent-registry
     services create --endpoint-spec-type=no-spec` (which projects read-only
     Endpoints in Agent Registry for `telemetry.mtls.googleapis.com`,
     `monitoring.googleapis.com`, `trace.mtls.googleapis.com`, and
     `cloudtrace.googleapis.com`).
  2. Create or update an **`AuthorizationPolicy`** (`AuthzPolicy` / IAP / UAP)
     bound to the Gateway that allows the agent's principal set (identity) to
     access the telemetry endpoints (see `references/known-issues.md` BKI 23).

### Rule 6: IAP Denial Troubleshooting (`403` / `Egress request is not authorized`)
When logs or symptoms show `403` / `Egress request is not authorized` via IAP:
1. **Check IAP Egressor bindings on the registry entry FIRST** (`roles/iap.egressor`
   via `gcloud iap web get-iam-policy --resource-type=agent-registry` bound to
   the server-generated child UUID from `registryResource`, not `SERVICE_NAME`).
2. **Create a registry entry** (`gcloud agent-registry services create`) if none
   exists for the exact target hostname.
3. **Grant `roles/iap.egressor`** on the registry entry (IAM v1 — `set-iam-policy` requires top-level `{"bindings": [...]}` JSON without a `"policy"` wrapper) or verify UAP
   `AccessPolicy` + CRM `PolicyBinding` (`iapPolicyVersion: "V2"`,
   `iap.googleapis.com/resources.egressViaIAP`; see `references/policies.md` §2).
4. **Check IAP audit logs** (`protoPayload.serviceName="iap.googleapis.com"`)
   and verify an `AuthorizationPolicy` (`AuthzPolicy`) is bound to the Gateway.
5. **Explicitly warn**: *"Do NOT use `roles/iap.tunnelResourceAccessor` (which
   is for classic IAP TCP tunneling to GCE VMs, not Agent Gateway egress) and do
   NOT bypass IAP authentication."*

### Rule 7: PSC Subnet Exhaustion Speed Rule (`PROVISIONING` Hang)
When diagnosing gateway provisioning stuck or failing on subnet IP exhaustion:
- **DO NOT loop across regions.** Run ONLY in the target region (default `us-central1`):
  1. `gcloud network-services agent-gateways list --location=us-central1`
  2. `gcloud network-services agent-gateways describe <GW> --location=us-central1`
  3. `gcloud compute network-attachments describe <NA> --region=us-central1`
  4. `gcloud compute networks subnets describe <SUBNET> --region=us-central1`
- Check free IP count (`Usable - Allocated = Free`) **before** recommending any
  Network Attachment deletion; flag that a `/28` subnet is easily exhausted and
  recommend expanding the CIDR range to at least `/26` (`known-issues.md` BKI 19).

### Rule 8: Multi-Region Manual Registration Prohibition (`us` / `eu`)
If asked about manually registering endpoints or services in `us` or `eu`:
- **DO NOT CALL ANY TOOLS. RESPOND ON TURN 0**:
  1. *"Manual endpoint/service registration is NOT supported in `us` or `eu`
     multi-region locations (`us` and `eu` are read-only roll-up locations for
     auto-discovered resources)."* (Explicitly name BOTH `us` and `eu`.)
  2. *"Register manually in a specific region (e.g., `us-central1`) or `global`."*

### Rule 9: VPC Service Controls (VPC-SC) Perimeter & ACT `ALL_TRAFFIC`
When diagnosing VPC-SC perimeter blocks or external API hangs under VPC-SC:
1. Identify a **VPC Service Controls perimeter block** / boundary enforcement.
2. Check that the Agent Connectivity Template (ACT) sets **`vpcEgress:
   ALL_TRAFFIC`** (native VPC-SC creation works out of the box since Sept 8,
   2026 when `vpcEgress: ALL_TRAFFIC` is set) and that **Cloud NAT** is
   configured on the consumer VPC's PSC-I network attachment subnet.
3. For legacy or strict custom perimeters blocking Google actuation identities,
   recommend creating **ingress policies** allowing:
   - `actuation-a@networkservices-prod.iam.gserviceaccount.com`
   - `cloud-aiplatform-pipeline-robot-prod@system.gserviceaccount.com`
4. Explicitly state: *"Do NOT disable VPC Service Controls or delete perimeters."*
   Refer to `references/known-issues.md` BKI 18 & 28.

### Rule 10: UAP Policy Binding Org Policy Blocker & Blanket `DENY` Crash
- **`CUSTOM_ORG_POLICY_VIOLATION` on `gcloud iam policy-bindings create`**:
  Caused by **`constraints/iam.managed.disableAccessPolicyBinding`** (note: some
  docs misspell this plural). Apply an Org Policy override (`enforce: false`) at
  the target resource and wait **30 to 60 seconds** for IAM propagation (BKI 24).
- **Startup crash after UAP `destination.is_registered == false` `DENY`**:
  Explain that the blanket `DENY` blocked internal/unauthenticated SDK bootstrap
  and metadata calls (such as Cloud Resource Manager project lookups) during
  Reasoning Engine init; remove or scope the blanket `DENY` rule (BKI 5).

### Rule 11: Agent Gateway Dual-Registry & Jurisdiction Invariants
When configuring or validating `registries` on an Agent Gateway:
1. An Agent Gateway supports a **maximum of two registries**.
2. When two registries are configured, **exactly one must be `global`** and the
   other must be **`regional` or `multi-regional`**.
3. Binding two regional registries (e.g., `us-central1` + `europe-west1`), two
   multi-regionals, two globals, or a mismatched jurisdiction (e.g., `us-central1`
   gateway + `eu` registry) is invalid and rejected with an **HTTP 400**
   validation error (`references/agent-gateway.md` §4, BKI 26).

### Rule 12: Cross-Project Runtime-to-Gateway Binding Diagnosis
When Reasoning Engine in Project 1 fails to bind to a Gateway in Project 2:
1. **Deploying Identity**: Needs `networkservices.agentGateways.use` and
   `networkservices.agentGateways.get` (or `roles/networkservices.viewer`) in Project 2.
2. **Vertex AI Service Agent**: Grant `roles/networkservices.viewer` or custom
   role `ae_agw_cross_project_sa` (alias `ar_agw_cross_project_sa`) to
   `service-PROJECT_1_NUMBER@gcp-sa-aiplatform.iam.gserviceaccount.com` in Project 2.
3. **Regional Colocation**: Verify both runtime and gateway are in the **same region**.
4. **CAA Opt-Out**: Set `GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES`
   to `False` (`references/known-issues.md` BKI 10, `references/agent-gateway.md` §11).

### Rule 13: Downstream SWP + PBR vs. Explicit Forward HTTPS Proxy
Distinguish the two supported consumer-VPC proxy architectures:
- **Pattern A — Transparent Next-Hop SWP + PBR** (no client `HTTPS_PROXY` needed):
  1. Explain that **PSC endpoints cannot be route next-hops**, **SWP behind PSC
     Service Attachments only supports explicit proxy mode (not transparent
     next-hop mode)**, and **static routes cannot be used because Network
     Attachments cannot have VM network tags**.
  2. Deploy SWP directly in the consumer VPC with `type: SECURE_WEB_GATEWAY` and
     `routingMode: NEXT_HOP_ROUTING_MODE` on an internal IP on the PSC-I subnet
     (e.g., `10.20.1.250`), with a `/26` `REGIONAL_MANAGED_PROXY` `ACTIVE` subnet.
  3. Configure **Policy-Based Routing (PBR)** matching source CIDR `10.20.1.0/24`
     to `--next-hop-ilb-ip=10.20.1.250` (priority 200) + fallback PBR (1000).
  4. Create **Cloud NAT with `ENDPOINT_TYPE_SWG`** (`nats create ... --endpoint-types=ENDPOINT_TYPE_VM,ENDPOINT_TYPE_SWG`),
     and allowlist `<region>-aiplatform.mtls.googleapis.com` in SWP CEL (BKI 33).
- **Pattern B — Explicit Forward HTTPS Proxy (`HTTPS_PROXY` + L4 `AuthzPolicy`)**:
  1. Without L4 bypass, `HTTPS_PROXY=https://proxy.corp.internal:443` fails on
     `HTTP CONNECT` with **HTTP `404`** because Agent Gateway's L7 HTTP manager
     terminates TLS and rejects nested `CONNECT`.
  2. Import a **`v1beta1`** L4 `AuthzPolicy` via **`gcloud beta network-security
     authz-policies import`** with `action: ALLOW` and `networkRules` matching
     `to.operations[].snis` (omit `target.loadBalancingScheme` and `ports`; max 5 rules;
     omit `from` or include `7.0.0.0/8` + PSC-I CIDR in `from.sources[].ipBlocks`).
  3. Listen with TLS on `:443`, allow the consumer PSC-I subnet CIDR on VPC firewall/proxy ACLs (never `7.0.0.0/8`),
     set `NO_PROXY`/`no_proxy` to `.googleapis.com,googleapis.com,metadata.google.internal,169.254.169.254,localhost,127.0.0.1`,
     bundle `agentGatewayCard.rootCertificates` + Private CA in container env
     vars (`SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`), and warn L4 `ALLOW` bypasses
     L7 IAP/UAP, Model Armor, SGP, and `httpRules` for matched SNIs (BKI 34).

### Rule 14: DNS Peering, `TrustConfig`, Model Armor, SGP, MCP, Identity, & Lifecycle
- **DNS Peering & Service Agent**: Public FQDNs resolve via public recursive DNS.
  Private DNS requires `dnsPeeringConfig` (`domains` array with trailing `.`; ACT
  uses string `targetNetwork` only, whereas inline `AgentGateway.networkConfig.dnsPeeringConfig`
  also requires `targetProject`). Cloud DNS caps total peering hops at **2**
  (Gateway consumes Hop 1 → max 1 consumer peering hop; a 2nd hop fails preflight
  or returns `SERVFAIL` → `503`, BKI 35). Grant `roles/dns.peer`, `roles/dns.reader`,
  `roles/compute.networkViewer`, and `roles/compute.networkUser` to
  `service-GATEWAY_PROJECT_NUMBER@gcp-sa-agentgateway.iam.gserviceaccount.com`
  (and `compute.networkAttachments.use` to caller, BKI 9). Never use authoritative `"."` private root zones (`"."` requires a Cloud DNS Private Forwarding Zone).
- **Private CA `TrustConfig` & Immutable ACT**: Set `egressNetworkConfig.tlsConfig.trustConfig`
  **with `additionalRoots: PUBLICLY_TRUSTED_ROOTS`** (omitting breaks `*.googleapis.com`).
  ACT fields are immutable — create a new ACT and rebind via `PATCH` with
  `updateMask=agentConnectivityTemplate` (BKI 6).
- **Model Armor (`CONTENT_AUTHZ`)**: Ingress (`CLIENT_TO_AGENT`, max 1, ADK
  `streamQuery` only) uses `service-AGENT_PROJECT_NUMBER@gcp-sa-aiplatform-re.iam.gserviceaccount.com`;
  Egress (`AGENT_TO_ANYWHERE`, max 4) uses `service-GATEWAY_PROJECT_NUMBER@gcp-sa-dep.iam.gserviceaccount.com`.
  Scope `httpRules` `when` to exclude gRPC and streams **>60 seconds** (`Stream removed`, BKI 13).
- **Semantic Governance Policies (SGP)**: Uses `gcp-sa-aiplatform`, non-streaming
  LLM calls only, `.contains()` + `!request.headers['content-type'].startsWith('application/grpc')`
  in `when`, and full-map updates on `PATCH ?updateMask=metadata` so
  `sgpEnforcementMode: "DRY_RUN"` and `sgpUserIntentMatching` are preserved (BKI 38).
- **Native MCP, Identity, Trace, & Teardown**: Set `baseProtocolMethodsOption:
  MATCH_BASE_PROTOCOL_METHODS` on MCP `ALLOW` rules (BKI 39). Orgless trust
  domains use `agents.global.proj-PROJECT_NUMBER.system.id.goog` (`proj-`, never
  `project-`); never grant `roles/aiplatform.expressUser` or project-wide
  `roles/aiplatform.user` to Agent Identities. For Cloud Trace (`TelemetryPolicy`),
  always recommend enabling `cloudtrace.googleapis.com` (`gcloud services enable cloudtrace.googleapis.com`)
  and granting `roles/cloudtrace.agent` to `compute-system`, `gcp-sa-networksecurity`,
  and `gcp-sa-agentgateway` (see `references/agent-gateway.md` §8.3 and `references/field-manual.md` Step 14.4). Tear down in strict 7-step order
  (workloads → UAP bindings → `AuthzPolicy` → extensions → `AgentGateway` → ACT →
  VPC) and use unique gateway IDs if deletion tombstones collide (BKIs 25, 30).

## Quick Symptom Triage Matrix

| Symptom / Error | Primary Suspect | Reference |
| :--- | :--- | :--- |
| `403` / `Egress request is not authorized` | Unregistered FQDN, missing `roles/iap.egressor` / UAP binding, or PAB | Rules 4, 6; `references/policies.md` §2; BKIs 4, 7, 8, 15 |
| `HTTP 404` on `HTTP CONNECT` (`HTTPS_PROXY`) | Missing `gcloud beta` L4 `AuthzPolicy` (`networkRules` `snis`) | Rule 13B; `references/agent-gateway.md` §6.3; BKI 34 |
| `HTTP 498` immediately after binding runtime | Enforcing gateway bound before allowlisting essential platform APIs | `references/agent-gateway.md` §2; BKI 37 |
| `500` / `PERMISSION_DENIED` / `Stream removed` | Model Armor SA roles (`gcp-sa-dep` vs `gcp-sa-aiplatform-re`) or 60s stream cap | Rule 14; `references/policies.md` §12; BKI 13 |
| `503` / `NXDOMAIN` / `SERVFAIL` on private host | >2-hop DNS peering, authoritative `"."` zone, Packet Intercept, or SWP | Rules 13A, 14; `references/agent-gateway.md` §3, §6; BKIs 33, 35, 36 |
| `Config validation failed` / `PERMISSION_DENIED` on import | Disabled `agentregistry.googleapis.com`, missing caller/`gcp-sa-agentgateway` IAM, or bad NA URI | Rule 14; BKIs 9, 20, 26 |
| `HTTP 409 ABORTED` / `400 already being used` | Active control-plane LRO mutex (~2 min), tombstone collision, or reverse teardown | `references/agent-gateway.md` §9, §10; BKIs 25, 29, 30 |
| Startup crash (`reasoning_engine_stderr`) | Blocked telemetry/CRM bootstrap, UAP blanket `DENY`, or SGP gRPC interception | Rules 5, 10, 14; BKIs 1, 5, 17, 23, 38 |

## When to use this skill

Trigger on Agent Gateway, Agent Connectivity Templates (ACT), Agent Registry,
Agent Identity, IAP/UAP policies, Model Armor, Semantic Governance Policies
(SGP), SWP/Explicit Proxy egress, Private CA `TrustConfig`, Cloud DNS peering,
Cloud Trace `TelemetryPolicy`, or Gemini Enterprise / Agent Runtime / GKE /
Cloud Run gateway bindings. Do **not** use for generic Google Cloud IAM, GCS,
GCE, or networking issues unrelated to the Agent Platform stack.

## Required context & Hypothesis Rules

Gather `PROJECT_ID`, `PROJECT_NUMBER`, `LOCATION` (default `us-central1`),
`AGENT_ID`, `AGENT_GATEWAY_NAME`, Agent Identity (`principal://` or
`principalSet://`), exact error + timestamp, and target destination. If missing,
ask or state unknowns using placeholders — never scan across projects or loop
over regions. Before Step 1 queries, formulate **at most 3 hypotheses** anchored
to *"Why did it start failing now?"* (e.g., recent Terraform/config changes).

## Diagnostic flow

Follow in order (copy-paste commands in `references/field-manual.md`):
- **Step 0 — Pre-Flight & Access**: Evaluate Rules 1–14. Verify project access
  (`gcloud projects describe $PROJECT_ID`).
- **Step 1 — Agent & Startup Logs**: Classify error (`403`, `404 CONNECT`, `498`,
  `500`, `503`, crash, timeout). Check PSC subnet IPs, ACT `ALL_TRAFFIC` + Cloud
  NAT, and `agentGatewayCard.rootCertificates` CA trust.
- **Step 2 — Gateway Logs**: Query `networkservices.googleapis.com/Gateway`
  (filtering `-httpRequest.requestMethod="CONNECT"` when inspecting L7 requests)
  to find the exact failing SNI/hostname and `serviceExtensionsInfo`.
- **Step 3 — IAP / Model Armor / SGP Logs**: Check `iapPolicyVersion` (`V1` vs
  `V2`), `DRY_RUN` vs enforced, Model Armor callout status, or
  `logs/semantic-governance-policy` verdicts and rationales.
- **Step 4 — Registry State**: Verify exact hostname permutations in
  `gcloud agent-registry {services,endpoints,mcp-servers,agents} list` and
  confirm dual-registry + jurisdiction rules.
- **Step 5 — Identity & Policies**: Check `roles/iap.egressor` via
  `--resource-type=agent-registry` on the child UUID (V1), UAP
  `AccessPolicy`/`PolicyBinding` + `constraints/iam.managed.disableAccessPolicyBinding`
  (V2), PAB overrides, and least-privilege Agent Identity roles (`proj-` for orgless).
- **Step 6 — AuthzPolicy & Extensions**: Verify L4 `networkRules` vs L7
  `httpRules`, MCP `MATCH_BASE_PROTOCOL_METHODS`, Model Armor / SGP `when`
  exclusions, `ExtensionBinding` scope, and policy caps (max 4 egress, max 1 ingress `CONTENT_AUTHZ`).
- **Step 7 — Connectivity, DNS, & TLS**: Verify ACT `TrustConfig`
  (`PUBLICLY_TRUSTED_ROOTS`), `gcp-sa-agentgateway` IAM, <=2 DNS peering hops,
  no Packet Intercept on the consumer VPC, and SWP/Explicit Proxy settings.
- **Step 8 — PrincipalSet & Trace Verification**: Test 1:1 `principal://`
  binding if `principalSet://` lags; for Cloud Trace, enable `cloudtrace.googleapis.com`, verify `v1beta1` `TelemetryPolicy` (`telemetryTarget` referencing `agentGateways/*` and object `parentBasedSampling: {enabled: true, samplingRate: 1.0}`, never string `ENABLED`), and grant `roles/cloudtrace.agent` to `service-<PROJECT_NUMBER>@compute-system.iam.gserviceaccount.com`, `service-<PROJECT_NUMBER>@gcp-sa-networksecurity.iam.gserviceaccount.com`, and `service-<PROJECT_NUMBER>@gcp-sa-agentgateway.iam.gserviceaccount.com`.

## Tools & Layered References

Use `mcp__gcloud__run_gcloud_command` (or `gcloud --quiet`),
`mcp__gcloud-observability__list_log_entries` (or `gcloud logging read`),
`mcp__google-dev-knowledge__search_documents` / `get_documents` / `answer_query`,
and `curl` REST GETs, plus bundled references (load only the smallest set needed):
- [references/field-manual.md](references/field-manual.md) — read first for operational commands & log queries
- [references/known-issues.md](references/known-issues.md) — BKIs #1–#13, #15–#39 for fast pattern matches
- [references/agent-gateway.md](references/agent-gateway.md) — topologies, ACT, DNS, TLS, SWP/Explicit Proxy, Trace, teardown
- [references/policies.md](references/policies.md) — L4/L7 `AuthzPolicy`, MCP, UAP v3beta, Model Armor, SGP
- [references/agent-registry.md](references/agent-registry.md) — `services` vs projected `endpoints`, 9 API families, jurisdictions
- [references/agent-identity.md](references/agent-identity.md) — 3-identity delegation, Cloud Run OIDC vs IAP MCP, WIF

## Output report

Always produce a read-only diagnostic report using this exact structure:

```markdown
# Agent Platform Diagnostic — <one-line summary>

## Context
- Project: <id> (<number>) | Location: <region>
- Agent: <agent_id> | Gateway: <gateway_name>
- Symptom: <exact error message and when it started>

## Evidence gathered
- Agent log query: <filter, summary>
- Gateway log query: <filter, exact failing hostname / extension status>
- IAP / Policy log query: <filter, decision + enforcement mode>
- Registry & Policy state: <entries, AuthzPolicy bindings, roles/iap.egressor or UAP>

## Root cause hypothesis
<ranked root cause(s)>

## Why this fits the evidence
<connect log/config evidence to root cause>

## Recommended fix
<ordered gcloud / curl / YAML / Terraform changes for the user to apply>

## What to verify after the fix
<verification queries>

## Open questions / unknowns
<missing context or unverified items>

## Appendix: Raw Logs & Verified Links
- **Cloud Logging Filter**: <exact copy-pasteable filter or deep link>
- **Raw Logs**: <untruncated Agent, Gateway, and IAP/Policy log entries>
```

## Principles

- **Exact hostname match first**: Compare gateway log hostnames directly against Agent Registry.
- **Layered default-deny**: Registry → Gateway `AuthzPolicy` → Extension → IAP/UAP/Model Armor/SGP → PAB (PAB overrides IAM Allow).
- **L4 bypass vs L7 governance**: L4 `networkRules` enables `HTTP CONNECT` explicit proxies (`:443`) but bypasses L7 IAP, Model Armor, and SGP for matched SNIs.
- **Read-only, single-region, non-interactive**: Pull evidence first, never mutate resources, check `us-central1` unless logs indicate otherwise, and pass `--quiet`.

## Supporting Links

- [Agent Gateway Overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/agent-gateway-overview.md.txt)
- [Configure VPC Connectivity & DNS](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/set-up-vpc-connectivity.md.txt)
- [Delegate Authorization & MCP](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/delegate-authorization.md.txt)
- [Configure Model Armor](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/configure-model-armor.md.txt)
- [Configure Semantic Governance](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/configure-semantic-governance.md.txt)
- [Monitor & Trace Agent Gateway](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/monitor-agent-gateway.md.txt)
- [Deploy Agent Gateway Runtime](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-gateway-runtime-deploy.md.txt)
- [Troubleshoot Agent Gateway](https://docs.cloud.google.com/gemini-enterprise-agent-platform/troubleshooting/troubleshoot-agent-gateway.md.txt)
- [Troubleshoot IAM Policies (UAP)](https://docs.cloud.google.com/gemini-enterprise-agent-platform/troubleshooting/troubleshoot-iam-policies-uap.md.txt)
