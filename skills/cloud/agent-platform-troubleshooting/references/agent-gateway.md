# Agent Gateway — Debugging Reference

Curated from Google Cloud's Gemini Enterprise Agent Platform architecture.
Focused on what a debugger needs to triage failed requests, routing issues, and
provisioning blocks on Agent Gateway and Agent Connectivity Templates (ACT).

## Table of Contents

-   [TL;DR for debugging](#tldr-for-debugging): Lines 24-94
-   [1. Architecture & Control Plane](#1-architecture--control-plane): Lines 95-118
-   [2. Deployment Modes & Topologies](#2-deployment-modes--topologies): Lines 119-163
-   [3. Agent Connectivity Template (ACT), Cloud DNS Peering, & Private CA](#3-agent-connectivity-template-act-cloud-dns-peering--private-ca): Lines 164-290
-   [4. Dual-Registry Gateway Binding Rules](#4-dual-registry-gateway-binding-rules): Lines 291-340
-   [5. Cloud NAT & Egress IP Mechanics](#5-cloud-nat--egress-ip-mechanics): Lines 341-380
-   [6. Downstream Egress Proxies: Next-Hop SWP + PBR vs. Explicit HTTPS Proxy](#6-downstream-egress-proxies-next-hop-swp--pbr-vs-explicit-https-proxy): Lines 381-681
-   [7. Delegated Authorization, Model Armor, SGP, & Native MCP](#7-delegated-authorization-model-armor-sgp--native-mcp): Lines 682-742
-   [8. Logging, Monitoring, & Cloud Trace](#8-logging-monitoring--cloud-trace): Lines 743-808
-   [9. Common Failure Modes & Troubleshooting Guide](#9-common-failure-modes--troubleshooting-guide): Lines 809-825
-   [10. Reference Gateway, ACT Specifications, & Ordered Teardown](#10-reference-gateway-act-specifications--ordered-teardown): Lines 826-890
-   [11. Cross-Project Centralized Governance Architecture](#11-cross-project-centralized-governance-architecture): Lines 891-1018

--------------------------------------------------------------------------------

## TL;DR for debugging

1.  **Control Plane & Infrastructure**: Managed under Network Services
    (`networkservices.googleapis.com`). Google-managed Agent Gateway proxy
    infrastructure runs in Google-managed infrastructure outside your consumer
    project.

    > **Important:** All configuration changes, deployments, and debugging must
    > be performed strictly on consumer-project resources.

2.  **Native VPC-SC Support Mandates ACT in `ALL_TRAFFIC` Mode**: As of
    September 8, 2026, Agent Gateway creation inside a VPC-SC perimeter works
    natively out of the box when the gateway binds to an Agent Connectivity
    Template (ACT) configured with `vpcEgress: ALL_TRAFFIC`. In `ALL_TRAFFIC`
    mode, all outbound packets from runtime containers are captured and tunneled
    through the PSC-I Network Attachment into the consumer VPC.

3.  **The Cloud NAT Egress Prerequisite (Silent Black Hole)**: Under `vpcEgress:
    ALL_TRAFFIC`, external public Internet traffic exiting the PSC-I Network
    Attachment routes through the consumer VPC. The consumer VPC subnet **MUST**
    have Cloud NAT configured; otherwise outbound SaaS/REST calls hang and time out.

4.  **Google Front End (GFE) Bypass Exception**: Traffic directed to Google APIs
    or Cloud Run default domains (`*.run.app`) does NOT exit through Cloud NAT.
    Google's network routes Google IP ranges internally via Private Google Access.

5.  **Dual-Registry & Jurisdiction Invariants**: Agent Gateway supports linking
    up to **two** Agent Registries:
    -   Exactly **one** registry **MUST be `global`**.
    -   The second can be **`regional`** (e.g., `us-central1`) or
        **`multi-regional`** (`us` or `eu`, matching the gateway's geographic
        jurisdiction).
    -   Two regional registries, two multi-regional registries, or a
        cross-jurisdiction pairing (`us-central1` + `eu`) fails validation with HTTP `400`.

6.  **Concurrent Mutation Lock (`HTTP 409 ABORTED`) & Tombstones**: Submitting
    concurrent `PATCH`, `import`, or `delete` operations while an LRO is active
    on the same gateway aborts with `HTTP 409 ABORTED: unable to queue the
    operation` (~1.5–2 minutes). Reusing a recently deleted gateway name before
    cleanup finishes can also collide; poll LROs to completion or use a unique
    versioned gateway ID.

7.  **Multi-Runtime Sharing vs. In-Place Rebinding**: Multiple Agent Runtime
    (Reasoning Engine) instances in the same region **can** share a single
    `AGENT_TO_ANYWHERE` gateway (<https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/set-up-agent-gateway.md.txt>), provided gateway
    mutations are serialized and essential platform APIs are allowlisted before
    binding (binding an enforcing gateway before allowlisting APIs causes
    immediate **`HTTP 498`** failures).

8.  **Dependency-Ordered Teardown**: Delete bound workloads and UAP
    `PolicyBinding` resources first, then `AuthzPolicy` → `AuthzExtension` /
    `ExtensionBinding` / `TelemetryPolicy` → `AgentGateway` → `ACT` →
    `TrustConfig` / `NetworkAttachment` / VPC, polling each LRO to `done: true`
    before proceeding (see §10.3).

9.  **Private CA `TrustConfig`, 2-Hop DNS Peering, & Explicit HTTPS Proxy**:
    -   **Private CA (`TrustConfig` GA)**: Always set `additionalRoots:
        PUBLICLY_TRUSTED_ROOTS` alongside `tlsConfig.trustConfig`, and create a
        new ACT + `PATCH` the gateway (`updateMask=agentConnectivityTemplate`)
        when rotating trust configs.
    -   **Cloud DNS 2-Hop Limit**: Cloud DNS permits at most **2 peering hops
        total** (Agent Gateway consumes Hop 1 → max 1 consumer peering hop; a
        2nd consumer hop fails preflight or returns `SERVFAIL` → `503`).
    -   **Explicit HTTPS Proxy (`HTTPS_PROXY`)**: Requires a `v1beta1` L4
        `AuthzPolicy` (`gcloud beta network-security authz-policies import`)
        with `networkRules` matching `to.operations[].snis` (omitting
        `loadBalancingScheme` and `ports`); otherwise `HTTP CONNECT` fails with
        **`HTTP 404`** on the L7 listener (see §6.3).

--------------------------------------------------------------------------------

## 1. Architecture & Control Plane

Agent Gateway acts as the enterprise security gateway and Layer 7 policy
enforcement point for AI agent workloads:

-   **Client-to-Agent (ingress):** External clients reaching agents or tools on
    Google Cloud.
-   **Agent-to-Anywhere (egress):** Agents on Google Cloud reaching external
    services, APIs, MCP servers, or peer agents.

### Core Resource Types

| Type | Purpose |
| :--- | :--- |
| `networkservices.agentGateways` | Gateway resource governing Client-to-Agent (`CLIENT_TO_AGENT`) or Agent-to-Anywhere (`AGENT_TO_ANYWHERE`) traffic. |
| `networkservices.agentConnectivityTemplates` | Centralized VPC egress (`ALL_TRAFFIC` / `PRIVATE_RANGES_ONLY`), Private DNS peering, and Private CA `TrustConfig`. |
| `networksecurity.authzPolicies` | Attaches L7 `httpRules`/MCP rules, L4 `networkRules` (`v1beta1`), `CUSTOM` extensions, or `DENY_BY_DEFAULT` to gateways. |
| `networkservices.authzExtensions` / `serviceextensions.extensionBindings` | Attaches IAP/UAP, Model Armor, Semantic Governance Policies (SGP), or custom `ext_proc` extensions. |
| `networkservices.telemetryPolicies` | Preview distributed Cloud Trace sampling configuration (`gcloud beta network-services telemetry-policies`). |
| `certificatemanager.trustConfigs` | Private CA trust stores and self-signed leaf allowlists referenced by ACT `tlsConfig`. |
| `compute.networkAttachments` | PSC-Interface (PSC-I) attachment in the consumer VPC for private and `ALL_TRAFFIC` egress. |

--------------------------------------------------------------------------------

## 2. Deployment Modes & Topologies

### 2.1 Google-Managed vs. Self-Managed Topologies

-   **Google-Managed Agent Gateway**: Google operates the Envoy proxy fleet for
    Agent Runtime (Reasoning Engines), Gemini Enterprise apps, and IAP-protected
    Cloud Run MCP ingress (`governedAccessPath: AGENT_TO_ANYWHERE` or
    `CLIENT_TO_AGENT`).
-   **Self-Managed Agent Gateway (Secure Web Proxy)**: Customer-managed Secure
    Web Proxy instance in the consumer VPC governing GKE pods, Cloud Run jobs/services,
    and Token Management Policies (`TokenAggregationPolicy` / `TokenBudgetPolicy`).

### 2.2 Standard Mode (ACT + Consumer VPC) vs. Standalone Mode

-   **Standard Mode (Enterprise Isolated)**: Binds `agentConnectivityTemplate`
    with a consumer VPC `NetworkAttachment` (PSC-I), optional `dnsPeeringConfig`,
    and optional `tlsConfig.trustConfig`. Required for VPC-SC (`vpcEgress:
    ALL_TRAFFIC`), private RFC 1918 backends, deterministic Cloud NAT egress IPs,
    Next-Hop SWP, Explicit HTTPS Proxies, and Semantic Governance Policies (SGP).
-   **Standalone Mode (Google-Managed Public Egress)**: Omits the ACT and
    consumer VPC Network Attachment; governs public endpoints cataloged in Agent
    Registry over Google-managed networking (not supported for VPC-SC private egress).

### 2.3 Workload Binding Nuances & Bootstrap Sequencing (`HTTP 498`)

-   **Bootstrap Allowlist Order (`HTTP 498`)**: Before binding an Agent Runtime
    or Gemini Enterprise engine to an enforcing gateway (or flipping `DRY_RUN` to
    enforced), register the consolidated `googleapis` service (8 base FQDNs) and
    grant UAP/IAP egress permissions. Binding an enforcing gateway before
    allowlisting essential platform APIs causes immediate **`HTTP 498`** errors
    and startup crashes.
-   **Gemini Enterprise App Registration & Binding (`UpdateEngine`)**: Gemini
    Enterprise apps (`discoveryengine.googleapis.com`) register into Agent
    Registry and bind to an Agent Gateway via `PATCH .../engines/{ENGINE_ID}`
    (`UpdateEngine`). Agent Gateways are strictly regional (never `global`):
    deploy the gateway in `us-central1` for `global` or `us` Gemini Enterprise
    apps and in `europe-west1` for `eu` apps, paired with the matching single
    regional Agent Registry (`us-central1` or `europe-west1`), and remove the
    binding via `UpdateEngine` before deleting the gateway.
-   **Removing a Gateway from Agent Runtime**: Clear the runtime attachment via
    `PATCH .../reasoningEngines/{ID}?updateMask=agentGatewayConfig` with an empty
    `agentGatewayConfig: {}` body before deleting the gateway.

--------------------------------------------------------------------------------

## 3. Agent Connectivity Template (ACT), Cloud DNS Peering, & Private CA

The Agent Connectivity Template defines the compute model, network isolation,
and DNS topology for agent containers.

### 3.1 Egress Modes: `ALL_TRAFFIC` vs. `PRIVATE_RANGES_ONLY`

| Egress Mode               | Network Path      | VPC-SC        | Use Case     |
:                           :                   : Compatible?   :              :
| :------------------------ | :---------------- | :------------ | :----------- |
| **`ALL_TRAFFIC`**         | Outbound TCP/UDP  | **YES         | Enterprise   |
:                           : packets are       : (Mandatory)** : production   :
:                           : captured and      :               : environments :
:                           : tunneled through  :               : requiring    :
:                           : the PSC-I Network :               : VPC-SC       :
:                           : Attachment into   :               : perimeter    :
:                           : the consumer VPC. :               : compliance   :
:                           : External DNS      :               : and          :
:                           : queries resolve   :               : controlled   :
:                           : to synthetic PSC  :               : egress.      :
:                           : VIP               :               :              :
:                           : `240.0.0.2\:443`. :               :              :
| **`PRIVATE_RANGES_ONLY`** | Directs only RFC  | **NO**        | Dev/test     |
:                           : 1918 traffic      :               : workloads    :
:                           : (`10.0.0.0/8`,    :               : where public :
:                           : `172.16.0.0/12`,  :               : egress does  :
:                           : `192.168.0.0/16`) :               : not need VPC :
:                           : through PSC-I.    :               : inspection   :
:                           : Public internet   :               : or VPC-SC    :
:                           : traffic exits     :               : compliance.  :
:                           : directly from the :               :              :
:                           : Google runtime.   :               :              :

### 3.2 Consumer VPC Network Attachment (PSC-I) & Preflight Requirements

The Network Attachment bridges the Google-managed gateway fleet into the consumer VPC:

-   **Subnet Configuration**:
    -   `purpose: PRIVATE` with `privateIpGoogleAccess: true`.
    -   **Subnet Sizing**: Minimum `/26` (recommended `/24`). **Never use `/28`** —
        concurrent rollouts and dynamic PSC-I interfaces exhaust `/28` subnets.
    -   **No Consumer VPC Packet Intercept**: Do **not** attach a Network Security
        `InterceptDeploymentGroup` / Packet Intercept policy to the consumer VPC
        hosting the PSC-I subnet; intercepted gateway return packets drop with HTTP `503`.
-   **Attachment Settings**: `connectionPreference: ACCEPT_AUTOMATIC`, residing in
    the **exact same region** as the ACT and Agent Gateway (`projects/PROJECT_ID/regions/REGION/networkAttachments/NAME`).
-   **Mandatory IAM Grants**:
    1.  **Deploying Caller**: Needs `compute.networkAttachments.use` (e.g.,
        `roles/compute.networkAdmin` or custom role) on the Network Attachment;
        otherwise ACT/gateway import fails preflight validation.
    2.  **Gateway & Extension Service Agents on Subnet/Project**: Grant
        `roles/compute.networkUser` on the PSC-I subnet to **both**:
        -   `service-GATEWAY_PROJECT_NUMBER@gcp-sa-agentgateway.iam.gserviceaccount.com`
            (also grant `roles/compute.networkViewer` on the VPC host project)
        -   `service-GATEWAY_PROJECT_NUMBER@gcp-sa-dep.iam.gserviceaccount.com`

### 3.3 Cloud DNS Architecture, Peering Schemas, & 2-Hop Peering Limit

-   **Default Resolution**: Without `dnsPeeringConfig`, Agent Gateway resolves
    target hostnames using **public recursive DNS** only; private Cloud DNS zones
    in the consumer VPC are invisible until DNS peering is configured.
-   **Schema Difference — ACT vs. Inline `AgentGateway`**:
    -   **ACT (`egressNetworkConfig.dnsPeeringConfig`)**: Accepts **only**
        `domains` (YAML array of FQDNs **with trailing dots**, e.g., `["corp.internal."]`)
        and string `targetNetwork` (`projects/VPC_PROJECT_ID/global/networks/VPC_NAME` —
        **do NOT add `targetProject`**, and omit deprecated `accessTypes: [PRIVATE]`).
    -   **Inline `AgentGateway` (`networkConfig.dnsPeeringConfig`)**: Configured
        as a sibling of `networkConfig.egress` when not using an ACT; requires
        `domains`, `targetNetwork`, **and** `targetProject`.
-   **Mandatory DNS Peering Service Agent IAM**: Grant **`roles/dns.peer`** and
    **`roles/dns.reader`** (plus `roles/compute.networkViewer`) on the target
    VPC project to **`service-GATEWAY_PROJECT_NUMBER@gcp-sa-agentgateway.iam.gserviceaccount.com`**
    (do not grant only to `gcp-sa-networkservices`, which is not the Agent
    Gateway DNS peering identity).
-   **Cloud DNS 2-Hop Total Transitive Peering Limit (`SERVFAIL` → `503`)**:
    Cloud DNS supports at most **2 peering hops end-to-end**:
    `[Google-Managed Gateway VPC] --(Hop 1: ACT dnsPeeringConfig)--> [Consumer VPC A] --(Hop 2: Cloud DNS Peering)--> [Hub DNS VPC B]`.
    If `VPC B` peers a **3rd** hop to `VPC C` (`Gateway -> VPC A -> VPC B -> VPC C`),
    Cloud DNS drops transitive resolution: control-plane preflight either rejects
    the peering chain or runtime queries return `SERVFAIL` (surfaced by Envoy as
    `503 UF,URX` / `Upstream resolution failure`). **Fix**: Point
    `dnsPeeringConfig.targetNetwork` directly at the authoritative DNS Hub VPC
    (reducing hops to 1) or host an authoritative Cloud DNS forwarding/private
    zone directly in `VPC A` or `VPC B`.
-   **`"."` Root Zone Rule — Authoritative Forbidden (`NXDOMAIN`) vs. Private Forwarding Allowed**: Never peer to a
    VPC hosting a private **authoritative** Cloud DNS zone for `"."` (root) without
    explicit `*.googleapis.com` overrides — it shadows public & Private Google Access
    resolution with `NXDOMAIN` (`503`). By contrast, `domains: ["."]` is supported
    when the spoke VPC hosts a `"."` Cloud DNS **Private Forwarding Zone** forwarding
    queries to a hub resolver.

### 3.4 Private CA & Self-Signed TLS (`TrustConfig` — GA)

-   **When Needed**: Upstream private HTTPS endpoints or internal load balancers
    signed by an internal Private CA or self-signed certificate fail Envoy TLS
    verification (`CERTIFICATE_VERIFY_FAILED` / `503 UF`) unless trusted on the ACT.
-   **Configuration**: Create a Certificate Manager `TrustConfig` in the **same
    project and region** (`trustStores` for Private CA root/intermediate chains
    or `allowlistedCertificates` for self-signed leaf certs) and attach it under
    `egressNetworkConfig.tlsConfig`:

    ```yaml
    egressNetworkConfig:
      networkAttachment: projects/PROJECT_ID/regions/REGION/networkAttachments/agw-na
      vpcEgress: ALL_TRAFFIC
      tlsConfig:
        trustConfig: projects/PROJECT_NUMBER/locations/REGION/trustConfigs/private-ca-trust
        additionalRoots: PUBLICLY_TRUSTED_ROOTS
    ```

-   **Critical Trap 1 (`additionalRoots: PUBLICLY_TRUSTED_ROOTS`)**: Omitting
    `additionalRoots` defaults to `NO_ADDITIONAL_ROOTS`, stripping Mozilla/Google
    public WebPKI roots and immediately breaking TLS to all public APIs and
    `*.googleapis.com`!
-   **Critical Trap 2 (ACT Immutability)**: `tlsConfig.trustConfig`,
    `networkAttachment`, and `dnsPeeringConfig` cannot be mutated in-place on a
    bound ACT. Create a **new** ACT (`agw-act-v2`) and rebind the gateway via
    `PATCH .../agentGateways/{NAME}?updateMask=agentConnectivityTemplate` (or
    `gcloud network-services agent-gateways import`), then delete the old ACT.
-   **Runtime Container CA Bundle (`agentGatewayCard.rootCertificates`)**: For
    runtimes requiring explicit trust of the gateway's regional TLS inspection CA,
    extract `agentGatewayCard.rootCertificates` via `gcloud network-services
    agent-gateways describe GATEWAY_NAME --location=REGION --format="value(agentGatewayCard.rootCertificates)"`
    (there is no `export-cacerts` subcommand on `gcloud network-services`).

--------------------------------------------------------------------------------

## 4. Dual-Registry Gateway Binding Rules

Agent Gateway supports linking up to **two** Agent Registries in its
`registries` list:

```yaml
registries:
  - //agentregistry.googleapis.com/projects/PROJECT_NUMBER/locations/global
  - //agentregistry.googleapis.com/projects/PROJECT_NUMBER/locations/us-central1
```

> **Best-Practice Recommendation (Single Regional Registry):** Production
> deployments (including both Agent Runtime and Gemini Enterprise apps) should
> associate each `AgentGateway` with a **single regional Agent Registry
> instance** in the **same project and region** as the gateway
> (`//agentregistry.googleapis.com/projects/PROJECT_ID/locations/REGION`, using
> `us-central1` for `global` or `us` Gemini Enterprise apps and `europe-west1`
> for `eu` apps; both `PROJECT_ID` and numeric `PROJECT_NUMBER` are accepted).
> Multi-registry configurations remain permitted by the Network Services API
> validator up to the ceiling below.

### Network Services Validation Invariants

Agent Gateway control-plane validation enforces:

1.  **Cardinality**: Maximum of two registries are permitted (`<= 2`).
2.  **Mandatory Global Invariant**: If two registries are configured, **exactly
    one of them MUST be `global`**.
3.  **Second Registry Scope**: The second registry can be either **`regional`**
    (matching the gateway's exact region, e.g., `us-central1`) OR
    **`multi-regional`** (`us` or `eu`).
4.  **Jurisdiction Alignment**: A regional gateway in `us-*` cannot bind an `eu`
    multi-region registry, and an `europe-*` gateway cannot bind a `us`
    multi-region registry (`us` and `eu` are read-only roll-up views for
    auto-discovered resources; manual registration requires `global` or a
    concrete region).
5.  **Disallowed Configurations**:
    -   Two regional registries (e.g., `us-central1` + `europe-west1`): Rejected (`HTTP 400`).
    -   Two multi-regional registries (e.g., `us` + `eu`): Rejected (`HTTP 400`).
    -   One regional + one multi-regional (without `global`): Rejected (`HTTP 400`).
    -   Two global registries: Rejected (`HTTP 400`).

Validation error message on violation:

```text
maximum of two registries are supported. When it's two registries, one of them must be global, the other one can be either regional or multi-regional.
```

--------------------------------------------------------------------------------

## 5. Cloud NAT & Egress IP Mechanics

In `ALL_TRAFFIC` mode, outbound traffic behavior depends on the target domain:

```
[ Reasoning Engine ]
         │
         ▼ (Captured via PSC-I)
[ Consumer PSC-I Subnet ] ── (10.20.1.0/24)
         │
         ├─── Google APIs / *.run.app ──────► [ Private Google Access ] ──► [ GFE ]
         │
         └─── External Internet / SaaS ─────► [ Cloud Router + NAT ]   ──► [ Static IP: 203.0.113.10 ]
```

### 5.1 Routing Path

-   Packets exit the Network Attachment on the consumer subnet
    (`agw-psci-subnet`, e.g., `10.20.1.0/24`).
-   VPC route tables direct internet-bound CIDRs (`0.0.0.0/0`) through the
    default internet gateway via Cloud Router (`agw-nat-router`) and Cloud NAT
    (`agw-cloud-nat`).

### 5.2 Deterministic Static Egress IP

-   Outbound calls to external destinations (`api.weather.gov`, `api.ipify.org`,
    SaaS APIs) are Source-NAT'd (SNAT) to the Cloud NAT static regional IP
    (for example, `203.0.113.10` in `us-central1` or `198.51.100.20` in
    `europe-west1`) so external partners can allowlist a deterministic source IP.

### 5.3 Google Front End (GFE) Bypass Exception

-   Traffic directed to Google APIs or Cloud Run default domains (`*.run.app`)
    does **not** exit through Cloud NAT.
-   Google's Andromeda SDN intercepts traffic matching Google IP ranges and
    routes it internally to GFE via Private Google Access, bypassing the Cloud
    NAT static external IP.

--------------------------------------------------------------------------------

## 6. Downstream Egress Proxies: Next-Hop SWP + PBR vs. Explicit HTTPS Proxy

Enterprise consumer VPCs use one of two downstream proxy patterns behind an Agent
Gateway: **Pattern A (Transparent Next-Hop SWP + Policy-Based Routing)** when
full Layer 7 Agent Gateway governance must precede VPC egress without client
proxy settings, or **Pattern B (Explicit Forward HTTPS Proxy + L4 `AuthzPolicy`)**
when routing via `HTTPS_PROXY` to an explicit Squid/SWP/corporate proxy on `:443`.

### 6.1 Pattern A Platform Constraints & Routing Incompatibilities

1.  **PSC Endpoints Cannot Be Route Next-Hops**: Google Cloud route tables (both
    static routes and Policy-Based Routes) do **not** permit Private Service
    Connect (PSC) forwarding rules (`--load-balancing-scheme=""`) or service
    attachments as next hops.
2.  **SWP via PSC Service Attachment Lacks Next-Hop Mode**: Publishing Secure
    Web Proxy behind a PSC Service Attachment operates strictly in **Explicit
    Proxy Mode** (`HTTP CONNECT`). Transparent Layer 3/Layer 4 IP packets
    emerging from an Agent Gateway Network Attachment lack `HTTP CONNECT`
    framing (if an explicit proxy is required instead of Next-Hop SWP, configure
    `HTTPS_PROXY` plus a `v1beta1` L4 `AuthzPolicy` as shown in §6.3).
3.  **Static Route Tag Defect**: Next-hop routing mode with static routes
    requires VM network instance tags (`--tags`). Network Attachments
    (`compute network-attachments`) are consumer network interfaces, not VM
    instances, and cannot bear network tags. Consequently, static routes cannot
    match or steer traffic originating from an Agent Gateway Network Attachment.

### 6.2 The Working Architecture: Next-Hop SWP + Policy-Based Routing (PBR)

The only functional pattern for intercepting transparent egress from an Agent
Gateway Network Attachment is deploying Next-Hop SWP directly in the consumer VPC
and steering traffic via Policy-Based Routing:

```
[ Reasoning Engine ]
         │
         ▼ (ACT vpcEgress: ALL_TRAFFIC)
[ Agent Gateway ]
         │
         ▼ (PSC-I / Network Attachment, e.g. 10.20.1.0/24)
[ Consumer Subnet ]
         │
         ├──► [ Policy-Based Route (PBR) ] ── (Matches source: 10.20.1.0/24, dest: 0.0.0.0/0)
         │          │
         │          ▼ (Priority 200: next-hop-ilb-ip = 10.20.1.250)
         │    [ Next-Hop SWP Gateway (SECURE_WEB_GATEWAY) ]
         │          │
         │          ▼ (Proxy-Only Subnet: REGIONAL_MANAGED_PROXY /26)
         │    [ GatewaySecurityPolicy (L7 CEL Rules) ]
         │          │
         │          ▼ (Outbound Internet SNAT)
         │    [ Cloud NAT (ENDPOINT_TYPE_SWG) ]
         │          │
         │          ▼
         │    [ External Internet / Public APIs ]
         │
         └──► [ Fallback PBR (Priority 1000) ] ──► DEFAULT_ROUTING
```

#### 1. SWP Gateway Deployment

SWP must be deployed directly in the consumer VPC with `type: SECURE_WEB_GATEWAY`
and `routingMode: NEXT_HOP_ROUTING_MODE`, listening on an internal IP on the
PSC-I subnet (e.g. `10.20.1.250`):

> **Important:** The Network Services API requires `type: SECURE_WEB_GATEWAY`.
> Passing `type: SECURE_WEB_PROXY` is rejected by schema validation.

```yaml
# swp-gateway.yaml
name: projects/PROJECT_ID/locations/REGION/gateways/swp-gateway
type: SECURE_WEB_GATEWAY
routingMode: NEXT_HOP_ROUTING_MODE
addresses:
- 10.20.1.250
subnetwork: projects/PROJECT_ID/regions/REGION/subnetworks/agw-psci-subnet
gatewaySecurityPolicy: projects/PROJECT_ID/locations/REGION/gatewaySecurityPolicies/swp-policy
ports:
- 443
- 80
```

Import via GA gcloud CLI:

```bash
gcloud network-services gateways import swp-gateway \
  --source=swp-gateway.yaml \
  --location=REGION \
  --project=PROJECT_ID
```

#### 2. Envoy Proxy-Only Subnet Prerequisite

SWP runs on Envoy proxy instances managed within the consumer VPC. It requires a
dedicated proxy-only subnet in the target region:

```bash
gcloud compute networks subnets create swp-proxy-subnet \
  --purpose=REGIONAL_MANAGED_PROXY \
  --role=ACTIVE \
  --region=REGION \
  --network=VPC_NAME \
  --range=10.20.2.0/26 \
  --project=PROJECT_ID
```

#### 3. Policy-Based Routing (PBR) Configuration

Because Network Attachments cannot have VM network tags, routing must use PBR to
match traffic based on the source CIDR of the Network Attachment subnet:

-   **Primary PBR (`agw-psci-to-swp-pbr`, Priority 200)**: Matches source CIDR
    `10.20.1.0/24` (the PSC-I subnet where the Network Attachment resides) and
    destination `0.0.0.0/0`, steering traffic to the SWP internal IP:

    ```bash
    gcloud network-connectivity policy-based-routes create agw-psci-to-swp-pbr \
      --network=projects/PROJECT_ID/global/networks/VPC_NAME \
      --source-range=10.20.1.0/24 \
      --destination-range=0.0.0.0/0 \
      --next-hop-ilb-ip=10.20.1.250 \
      --priority=200 \
      --project=PROJECT_ID
    ```

-   **Default Fallback PBR (`agw-pbr-default-routing`, Priority 1000)**: Directs
    all non-matching or bypass traffic to default VPC routing:

    ```bash
    gcloud network-connectivity policy-based-routes create agw-pbr-default-routing \
      --network=projects/PROJECT_ID/global/networks/VPC_NAME \
      --destination-range=0.0.0.0/0 \
      --priority=1000 \
      --project=PROJECT_ID
    ```

#### 4. L7 Policy Enforcement (GatewaySecurityPolicy)

Security rules attached to the SWP Gateway evaluate outbound traffic using CEL
(Common Expression Language) expressions. Rules allow authorized domains and
deny unauthorized traffic with HTTP 403 or TLS connection drops:

```cel
inUrlList(host(), ['api.weather.gov', 'api.ipify.org', 'REGION-aiplatform.mtls.googleapis.com'])
```

Or explicit hostname equality:

```cel
host() == 'api.weather.gov' || host() == 'api.ipify.org' || host() == 'REGION-aiplatform.mtls.googleapis.com'
```

#### 5. Cloud NAT Interdependence (`ENDPOINT_TYPE_SWG`)

SWP Envoy proxy instances reside on the private proxy-only subnet and do not
possess external IP addresses. Outbound internet egress from SWP requires a
Cloud NAT gateway **created** with `ENDPOINT_TYPE_SWG` (`--endpoint-types` is
immutable and **not** supported on `gcloud compute routers nats update` — create
a new NAT gateway or recreate an existing VM-only NAT):

```bash
gcloud compute routers nats create agw-cloud-nat \
  --router=agw-nat-router \
  --region=REGION \
  --nat-all-subnet-ip-ranges \
  --auto-allocate-nat-external-ips \
  --endpoint-types=ENDPOINT_TYPE_VM,ENDPOINT_TYPE_SWG \
  --project=PROJECT_ID
```

> **Note:** In `NEXT_HOP_ROUTING_MODE`, the Google Cloud SWP control plane may
> autogenerate `swg-autogen-router-{network_id}` and `swg-autogen-nat` with
> `natIpAllocateOption: AUTO_ONLY` and `ENDPOINT_TYPE_SWG`. Outbound public IP
> queries (e.g. `api.ipify.org`) reflect the SWG NAT's auto-allocated public
> IPs rather than the VPC's manual Cloud NAT static IP, validating end-to-end
> traversal through SWP.

#### 6. The ADK Streaming Query Session Trap (HTTP 503)

In `ALL_TRAFFIC` ACT mode, Vertex AI Agent Development Kit (ADK) streaming
queries attempt to initialize session state via:

```text
POST https://<region>-aiplatform.mtls.googleapis.com/v1beta1/projects/.../locations/<region>/reasoningEngines/...:createSession
```

Because `ALL_TRAFFIC` forces all runtime egress through the Agent Gateway into
the Network Attachment, PBR intercepts and routes this session creation call to
SWP. If `<region>-aiplatform.mtls.googleapis.com` is omitted from the
GatewaySecurityPolicy allowlist, SWP rejects it (`default_denied`). This causes
ADK streaming queries to crash with:

```text
HTTP 503 Service Unavailable: remote connection failure
```

while direct, non-streaming `query()` calls (which do not create sessions)
continue to succeed. Always allowlist the regional aiplatform endpoint in SWP!

#### 7. Observability & Log Verification

SWP logs are emitted under resource type `networkservices.googleapis.com/Gateway`:

```
resource.type="networkservices.googleapis.com/Gateway"
resource.labels.gateway_name="swp-gateway"
resource.labels.location="REGION"
```

Verify `enforcedGatewaySecurityPolicy.matchedRules` with `action` (`ALLOWED` vs
`DENIED`), `tlsSniHostname`, `clientIp`, and `httpRequest.status`.

### 6.3 Pattern B: Explicit Forward HTTPS Proxy (`HTTPS_PROXY` + L4 `AuthzPolicy`)

Agent Runtime (Reasoning Engine) and containerized workloads **do** support
explicit forward HTTPS proxies (`HTTPS_PROXY=https://proxy.corp.internal:443`)
when Agent Gateway passes matching TLS SNIs through at Layer 4.

#### Why `HTTP CONNECT` Fails with `HTTP 404` by Default

By default, Agent Gateway's Envoy listener terminates TLS and passes decrypted
streams to an L7 HTTP connection manager (`loopback_tls`). When an SDK or `curl`
sends `CONNECT api.example.com:443 HTTP/1.1` inside the TLS session to an
explicit proxy, the L7 HTTP manager rejects nested `CONNECT` requests with
**`HTTP 404 Not Found`** (`curl: (56) CONNECT tunnel failed, response 404`).

#### Required 5-Part Configuration

1.  **Import a `v1beta1` L4 `AuthzPolicy` (`networkRules`)**: Route the proxy's
    SNI hostname to Agent Gateway's L4 TCP/SNI pass-through filter chain using
    **`gcloud beta`** (`networkRules` is available only in `v1beta1`, supports
    at most 5 rules and 10 `snis` per operation, is mutually exclusive with
    `httpRules`, and **must omit** both `target.loadBalancingScheme` and `ports`;
    either omit `from` or include **both** `7.0.0.0/8` and your PSC-I CIDR in
    `networkRules[].from.sources[].ipBlocks`, and never set `from.sources[].resources`
    on Agent Gateway targets):

    ```yaml
    # proxy-l4-authz-policy.yaml
    name: allow-explicit-proxy-l4
    policyProfile: REQUEST_AUTHZ
    action: ALLOW
    target:
      resources:
        - projects/PROJECT_ID/locations/REGION/agentGateways/AGENT_GATEWAY_NAME
    networkRules:
      - to:
          operations:
            - snis:
                - exact: "proxy.corp.internal"
    ```

    ```bash
    gcloud beta network-security authz-policies import allow-explicit-proxy-l4 \
      --source=proxy-l4-authz-policy.yaml \
      --location=REGION \
      --project=PROJECT_ID
    ```

2.  **Configure TLS Listener on Port `:443` & Consumer VPC / Proxy Source ACLs**:
    -   Agent Gateway forwards egress on `:443`; configure the explicit proxy
        (for example, Squid `https_port 443 tls-cert=...` or Explicit SWP on
        `:443`) with a DNS record resolvable via `dnsPeeringConfig`.
    -   **Two-Plane Source IP Rule**: In your **consumer VPC GCE ingress firewall**
        and **Squid `acl localnet src`**, allow **only your consumer PSC-I Network
        Attachment subnet CIDR** (e.g., `10.20.1.0/24` — packets exiting the
        PSC-I NIC into your VPC are sourced from the PSC-I subnet, never
        `7.0.0.0/8`). Use `7.0.0.0/8` **only** inside Agent Gateway's
        `AuthzPolicy` `networkRules[].from.sources[].ipBlocks` when `from` is set.

3.  **Set `HTTPS_PROXY` and Mandatory `NO_PROXY` Exclusions on the Agent**:
    -   `HTTPS_PROXY="https://proxy.corp.internal:443"` (and lowercase `https_proxy`)
    -   `NO_PROXY=".googleapis.com,googleapis.com,metadata.google.internal,169.254.169.254,localhost,127.0.0.1"`
        (and lowercase `no_proxy`). Omitting `169.254.169.254` /
        `metadata.google.internal` breaks ADC token fetches; omitting
        `.googleapis.com` tunnels Google API mTLS calls into the proxy.

4.  **Trust Both CAs Inside the Runtime Container**:
    Because L4 pass-through does **not** terminate TLS at Agent Gateway, ACT
    `tlsConfig.trustConfig` does **not** validate the explicit proxy's
    certificate. Combine `agentGatewayCard.rootCertificates` (for direct L7
    Google API/MCP calls) **and** your Private CA root (for the explicit proxy
    and any SSL-bumped upstream) into your container's CA bundle
    (`SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `GRPC_DEFAULT_SSL_ROOTS_FILE_PATH`).

5.  **Governance Trade-Off Warning**:
    Traffic matching an L4 `networkRules` `ALLOW` policy **bypasses Layer 7
    Agent Gateway governance** (IAP/UAP authorization, Model Armor
    `CONTENT_AUTHZ`, Semantic Governance Policies, and `httpRules`) for that
    proxy SNI. Enforce URL/domain filtering on the downstream proxy itself, or
    use Pattern A (Next-Hop SWP + PBR) if full L7 Agent Gateway inspection is
    required before VPC egress.

| Dimension | Pattern A: Transparent Next-Hop SWP + PBR (§6.2) | Pattern B: Explicit HTTPS Proxy + L4 `AuthzPolicy` (§6.3) |
| :--- | :--- | :--- |
| Container `HTTPS_PROXY` / `NO_PROXY` | None required (transparent L3/L4) | Required (`https://proxy:443` + `NO_PROXY` / `no_proxy`) |
| Agent Gateway Policy Layer | Full L7 (IAP/UAP, Model Armor, SGP, `httpRules`) | L4 SNI pass-through (`networkRules` bypasses L7 for proxy SNI) |
| Private CA Validation | Gateway ACT `tlsConfig.trustConfig` | Container trust bundle (`SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE`) |
| Routing Mechanism | Consumer VPC PBR → `NEXT_HOP_ROUTING_MODE` SWP + `ENDPOINT_TYPE_SWG` | Direct PSC-I routing + DNS peering to `:443` explicit proxy |

--------------------------------------------------------------------------------

## 7. Delegated Authorization, Model Armor, SGP, & Native MCP

Agent Gateway evaluates policies attached via `networksecurity.googleapis.com`
`authzPolicies` (never legacy `authorizationPolicies`). Always **omit
`target.loadBalancingScheme`** when targeting `agentGateways/*`.

### 7.1 Precedence, Profiles, & Cardinality Limits

-   **Evaluation Order (`REQUEST_AUTHZ`)**: `CUSTOM` → `DENY` → `ALLOW` →
    `DENY_BY_DEFAULT`. (`REQUEST_AUTHZ` executes before `CONTENT_AUTHZ`.)
-   **Policy Caps**: Egress (`AGENT_TO_ANYWHERE`) supports up to **4**
    `CONTENT_AUTHZ` policies; Ingress (`CLIENT_TO_AGENT`) supports at most **1**
    `CONTENT_AUTHZ` policy.

### 7.2 Native MCP `AuthzPolicy` (`MATCH_BASE_PROTOCOL_METHODS`)

When restricting MCP tools via `httpRules[].to.operations[].mcp`, `ALLOW` rules
**must** set `baseProtocolMethodsOption: MATCH_BASE_PROTOCOL_METHODS`. Leaving
the default (`SKIP_BASE_PROTOCOL_METHODS`) blocks MCP session handshakes
(`initialize`, `ping`, `notifications/initialized`) when paired with `DENY_BY_DEFAULT`.

### 7.3 IAP Unified Access Policy (UAP / Policy V2)

-   Set `iapPolicyVersion: "V2"` in the IAP `AuthzExtension` `metadata` (with
    optional `iamEnforcementMode: "DRY_RUN"`; omit `iamEnforcementMode` or set
    `"ENFORCE"` for active blocking).
-   Rules grant FQDN permission `iap.googleapis.com/resources.egressViaIAP`
    using singular `"operation"` and plural `"conditions": {"iap.googleapis.com": {...}}`
    (see `references/policies.md` §2).

### 7.4 Model Armor Content Security (`CONTENT_AUTHZ`)

-   **Ingress (`CLIENT_TO_AGENT`)**: Executes as
    **`service-AGENT_PROJECT_NUMBER@gcp-sa-aiplatform-re.iam.gserviceaccount.com`**
    (`roles/modelarmor.calloutUser` on agent project; `roles/modelarmor.user` on
    template project). Inspects ADK `reasoningEngines.streamQuery` payloads only.
-   **Egress (`AGENT_TO_ANYWHERE`)**: Executes as
    **`service-GATEWAY_PROJECT_NUMBER@gcp-sa-dep.iam.gserviceaccount.com`**
    (`roles/modelarmor.calloutUser` + `roles/serviceusage.serviceUsageConsumer`
    on gateway project; `roles/modelarmor.user` on template project).
-   **60-Second Stream Deadline**: Envoy enforces a hard **60-second total stream
    deadline** on `CONTENT_AUTHZ` callouts. Scope `httpRules[].when` to exclude
    `application/grpc` and streams >60s to avoid `Stream removed` / HTTP `500`/`504`.

### 7.5 Semantic Governance Policies (SGP)

-   Evaluates natural-language constraints and user intent via **the LLM in the
    semantic governance policy engine** (`gcloud beta ai semantic-governance-policy-engine` /
    `semantic-governance-policies`, running under
    `service-PROJECT_NUMBER@gcp-sa-aiplatform.iam.gserviceaccount.com`).
-   Requires `AGENT_IDENTITY` + `agent_gateway_config` at runtime creation, ACT +
    DNS peering (avoiding reserved SGP subnets `10.0.0.0/24`, `10.0.1.0/24`,
    `10.0.2.0/24`), non-streaming model invocation (streamed responses return no
    verdict or an error), and a non-streaming CEL `when` filter using `.contains()`:
    `"!request.headers['content-type'].startsWith('application/grpc') && (request.path.contains(':generateContent') || request.path.contains(':rawPredict') || request.path.contains('/v1/messages') || request.path.contains('/chat/completions'))"`.
-   **Wholesale `metadata` Overwrite Trap**: `PATCH .../authzExtensions/{NAME}?updateMask=metadata`
    (or `import`) replaces the entire `metadata` map — always supply all active
    keys (`sgpEnforcementMode: "DRY_RUN"`, `sgpUserIntentMatching`) together.

--------------------------------------------------------------------------------

## 8. Logging, Monitoring, & Cloud Trace

### 8.1 Monitored Resource & Log Analytics Prerequisite

Upgrade the `_Default` log bucket to **Log Analytics** to populate the Cloud
Console Agent Gateway Observability dashboard.

```text
resource.type="networkservices.googleapis.com/Gateway"
resource.labels.location="REGION"
resource.labels.gateway_name="AGENT_GATEWAY_NAME"
```

### 8.2 Inspecting L7 Decisions & Suppressing Outer `CONNECT 240.0.0.2:443` Noise

In ACT `ALL_TRAFFIC` mode, every connection logs an outer tunnel `CONNECT 240.0.0.2:443`
entry alongside the inner TLS-inspected request. Filter `-httpRequest.requestMethod="CONNECT"`
when triaging inner L7 status codes, or keep `CONNECT` when checking L4 pass-through:

```bash
# Inner L7 4xx/5xx decisions (suppressing outer 240.0.0.2:443 CONNECT entries)
gcloud logging read \
  'resource.type="networkservices.googleapis.com/Gateway" AND resource.labels.gateway_name="AGENT_GATEWAY_NAME" AND -httpRequest.requestMethod="CONNECT" AND httpRequest.status>=400' \
  --project=PROJECT_ID --limit=20 --freshness=1h --format=json

# Semantic Governance Policy (SGP) evaluation verdicts & rationales
gcloud logging read \
  'logName="projects/PROJECT_ID/logs/semantic-governance-policy"' \
  --project=PROJECT_ID --limit=20 --freshness=1h --format=json
```

### 8.3 Distributed Tracing with Cloud Trace (`TelemetryPolicy` — Preview)

1.  Always verify `cloudtrace.googleapis.com` is enabled (`gcloud services enable cloudtrace.googleapis.com`)
    and grant `roles/cloudtrace.agent` on the project to **all 3 platform service agents**
    (granting `roles/cloudtrace.agent` only to the runtime workload SA emits zero
    gateway spans; also grant to `service-PROJECT_NUMBER@gcp-sa-aiplatform.iam.gserviceaccount.com`
    if using SGP):
    -   `service-PROJECT_NUMBER@compute-system.iam.gserviceaccount.com`
    -   `service-PROJECT_NUMBER@gcp-sa-networksecurity.iam.gserviceaccount.com`
    -   `service-PROJECT_NUMBER@gcp-sa-agentgateway.iam.gserviceaccount.com`
2.  Import a schema-valid `TelemetryPolicy` via **`gcloud beta`**:

    ```yaml
    # tracing-policy.yaml
    name: "projects/PROJECT_ID/locations/REGION/telemetryPolicies/agw-trace-policy"
    displayName: "Tracing policy for Agent Gateway traffic"
    telemetryTarget:
      resources:
        - "//networkservices.googleapis.com/projects/PROJECT_ID/locations/REGION/agentGateways/AGENT_GATEWAY_NAME"
    tracingConfiguration:
      samplingRate: 1.0
      parentBasedSampling:
        enabled: true
        samplingRate: 1.0
    ```

    ```bash
    gcloud beta network-services telemetry-policies import agw-trace-policy \
      --source=tracing-policy.yaml \
      --location=REGION \
      --project=PROJECT_ID
    ```

--------------------------------------------------------------------------------

## 9. Common Failure Modes & Troubleshooting Guide

| Symptom | Root Cause | Remediation |
| :--- | :--- | :--- |
| Gateway mutation fails with `HTTP 409 ABORTED: unable to queue the operation` | Resource-level LRO mutex active from concurrent `PATCH`/`import`/`delete`, or recent gateway tombstone | Poll active LRO to completion (~1.5–2 min) before retrying; use a new gateway ID if recreating immediately after delete. |
| `HTTP 404` on `HTTP CONNECT` when using `HTTPS_PROXY` | Missing `v1beta1` L4 `AuthzPolicy` (`networkRules` `snis`); L7 HTTP manager rejects nested `CONNECT` | Import `ALLOW` `AuthzPolicy` with `networkRules[].to.operations[].snis` via `gcloud beta` (omit `loadBalancingScheme` & `ports`; see §6.3). |
| `HTTP 498` immediately after binding runtime to gateway | Enforcing gateway bound before allowlisting essential Google APIs (`googleapis` service + UAP/IAP policy) | Register the 8 base Google API FQDNs and verify UAP/IAP allow rules (or `DRY_RUN`) before binding the runtime. |
| Outbound SaaS calls hang/time out under ACT `ALL_TRAFFIC` | Consumer VPC PSC-I subnet lacks Cloud NAT | Deploy Cloud Router and Cloud NAT covering the PSC-I subnet. |
| `503` / `SERVFAIL` or `NXDOMAIN` on private or Google API hosts | >2 total Cloud DNS peering hops, missing `gcp-sa-agentgateway` `roles/dns.peer`, or authoritative `"."` private root zone | Limit peering to <=1 consumer hop (2 total), grant `roles/dns.peer` + `roles/dns.reader` to `gcp-sa-agentgateway`, and replace any authoritative `"."` private root zone with specific domain suffixes or a Cloud DNS Private Forwarding Zone. |
| TLS fails to `*.googleapis.com` after attaching `TrustConfig` | Omitted `additionalRoots: PUBLICLY_TRUSTED_ROOTS` on ACT `tlsConfig` | Create a new ACT including `additionalRoots: PUBLICLY_TRUSTED_ROOTS` and `PATCH` `agentConnectivityTemplate` on the gateway. |
| Private VPC backend returns `503` despite valid DNS, routes, & firewall | Network Security Packet Intercept (`InterceptDeploymentGroup`) enabled on consumer VPC | Move the Agent Gateway Network Attachment to a consumer VPC without Packet Intercept, or exclude the PSC-I subnet. |
| `ACT` or `AuthzExtension` deletion fails with `HTTP 400 ... already being used` | Child resources deleted out of order while `AgentGateway` or `AuthzPolicy` still references them | Follow the 7-step teardown sequence in §10.3, polling each deletion LRO to completion. Open a Google Cloud Support case if an orphaned backend reference persists after zero gateways remain. |
| Agent Runtime deletion fails with `HTTP 400 FAILED_PRECONDITION` | Active sessions or memories exist on the Reasoning Engine | Pass `?force=true` on the `DELETE .../reasoningEngines/{ID}?force=true` REST call. |
| REST API egress returns `403` on `/api/v2/tickets.json` | Unregistered UAP CEL rule matched `/api/v2/tickets` without `.json` / `?` variants | Match exact path, `.json`, `/` subpaths, and `?` query strings on `destination.unregistered.path`. |

--------------------------------------------------------------------------------

## 10. Reference Gateway, ACT Specifications, & Ordered Teardown

### 10.1 Agent Connectivity Template YAML (`act.yaml`)

```yaml
name: projects/PROJECT_ID/locations/REGION/agentConnectivityTemplates/agw-all-traffic-template
accessPath: AGENT_TO_ANYWHERE
deploymentModel: CENTRALIZED
egressNetworkConfig:
  networkAttachment: projects/PROJECT_ID/regions/REGION/networkAttachments/agw-network-attachment
  vpcEgress: ALL_TRAFFIC
  dnsPeeringConfig:
    domains:
      - corp.internal.
    targetNetwork: projects/PROJECT_ID/global/networks/agw-consumer-vpc
  tlsConfig:
    trustConfig: projects/PROJECT_NUMBER/locations/REGION/trustConfigs/private-ca-trust
    additionalRoots: PUBLICLY_TRUSTED_ROOTS
```

Import via GA CLI:

```bash
gcloud network-services agent-connectivity-templates import agw-all-traffic-template \
  --source=act.yaml \
  --location=REGION \
  --project=PROJECT_ID
```

### 10.2 Agent Gateway YAML (`gateway.yaml`)

```yaml
name: projects/PROJECT_ID/locations/REGION/agentGateways/agw-prod-gateway
agentConnectivityTemplate: projects/PROJECT_NUMBER/locations/REGION/agentConnectivityTemplates/agw-all-traffic-template
googleManaged:
  governedAccessPath: AGENT_TO_ANYWHERE
protocols:
  - MCP
registries:
  - //agentregistry.googleapis.com/projects/PROJECT_ID/locations/REGION
```

Import via GA CLI:

```bash
gcloud network-services agent-gateways import agw-prod-gateway \
  --source=gateway.yaml \
  --location=REGION \
  --project=PROJECT_ID
```

### 10.3 Dependency-Ordered 7-Step Public Teardown Sequence

Deleting resources out of order causes `HTTP 400 FAILED_PRECONDITION` (`already being used`). Always tear down in this order and wait for each LRO to finish:

1.  **Unbind or delete workloads**: Unbind (`?updateMask=agentGatewayConfig` / Gemini Enterprise `UpdateEngine`) or delete bound Reasoning Engines (`?force=true` if sessions exist).
2.  **Delete UAP `PolicyBinding` then `AccessPolicy`**: Poll `gcloud iam policy-bindings describe` until `404` (10–30s consistency window) before deleting `AccessPolicy`.
3.  **Delete `AuthzPolicy` resources**: Run `gcloud network-security authz-policies delete` (or `gcloud beta` for L4 `networkRules` policies) and wait for LRO completion *before* deleting extensions or gateways.
4.  **Delete `AuthzExtension`, `ExtensionBinding`, & `TelemetryPolicy`**: Remove extensions (`gcloud service-extensions authz-extensions delete` / `gcloud beta service-extensions extension-bindings delete`) and tracing policies (`gcloud beta network-services telemetry-policies delete`). (If Token Management Policies are used on self-managed SWP, delete `CostPerTokenPolicy` → `TokenBudgetPolicy` → `TokenAggregationPolicy`.)
5.  **Delete `AgentGateway`**: Run `gcloud network-services agent-gateways delete` and poll the operation to `done: true`.
6.  **Delete `AgentConnectivityTemplate`**: Run `gcloud network-services agent-connectivity-templates delete` only after `gcloud network-services agent-gateways list --location=REGION` confirms zero gateways reference it.
7.  **Delete `TrustConfig`, `NetworkAttachment`, Cloud NAT, & Subnet**: Clean up Certificate Manager and VPC networking resources last.

--------------------------------------------------------------------------------

## 11. Cross-Project Centralized Governance Architecture

Google Cloud's Gemini Enterprise Agent Platform supports cross-project bindings from Agent Runtimes (Vertex AI Reasoning Engines) in consumer projects to an Agent Gateway in a Centralized Governance Project.

### 11.1 Three-Tier Project Boundary Model

To separate policy authoring, network security, and runtime execution, enterprise deployments structure responsibilities across three distinct project tiers:

1.  **Centralized Governance Project (`AGW_PROJECT_ID`):**
    -   **Agent Registry (`agentregistry.googleapis.com`):** The authoritative catalog of vetted MCP tools, endpoints, and peer agents. Both Gateway and Registry **MUST** reside in this same project.
    -   **Agent Gateway (`networkservices.googleapis.com`):** The managed `AGENT_TO_ANYWHERE` gateway instance mediating all outbound agent traffic.
    -   **Model Armor Templates & IAP/UAP Policies:** Guardrails for request/response DLP inspection, prompt injection detection, and CEL-based authorization.
    -   **Network Infrastructure:** Egress VPC with a Private Service Connect (PSC-I) Network Attachment, Cloud NAT, and Private DNS peering.
2.  **Agent Runtime Projects (`AE_PROJECT_NUMBER`):**
    -   **Vertex AI Reasoning Engines:** Containerized agent execution environments deployed by product/application teams.
    -   **Cross-Project Gateway Binding:** Configured in `agentGatewayConfig.agentToAnywhereConfig.agentGateway` pointing directly to the central gateway resource.
    -   **No Local VPC Required:** Runtimes do not require local VPCs or interconnects; all private traffic tunnels into the governance project's network attachment.
3.  **MCP & Service Backend Projects (`MCP_PROJECT_ID`):**
    -   Host business logic, databases, or microservices (Cloud Run, GKE, Compute Engine). Services are explicitly registered into the central Agent Registry catalog.

### 11.2 Cross-Project IAM Requirements

To bind an Agent Runtime to an Agent Gateway in another project, permissions must be granted to both the deploying caller and the runtime project's service agent:

1.  **Deploying Principal (Developer EUC, Cloud Build, or CI/CD Service Account):**
    The caller invoking `client.agent_engines.create` or Vertex AI REST API must hold:
    -   `networkservices.agentGateways.get`
    -   `networkservices.agentGateways.use`
    (or role `roles/networkservices.viewer`) on `projects/AGW_PROJECT_ID/locations/REGION/agentGateways/GATEWAY_NAME`.
2.  **Vertex AI Service Agent:**
    Grant access to the runtime project's service agent on the governance project (`AGW_PROJECT_ID`):

    *Option A: Predefined Role (Network Services Viewer):*
    ```bash
    gcloud projects add-iam-policy-binding "AGW_PROJECT_ID" \
      --member="serviceAccount:service-AE_PROJECT_NUMBER@gcp-sa-aiplatform.iam.gserviceaccount.com" \
      --role="roles/networkservices.viewer"
    ```

    *Option B: Least-Privilege Custom Role (`ae_agw_cross_project_sa` / `ar_agw_cross_project_sa`):*
    ```bash
    gcloud iam roles create ae_agw_cross_project_sa \
      --project="AGW_PROJECT_ID" \
      --title="AE AGW Cross Project SA" \
      --description="Custom role for cross-project service agent to access Agent Gateways and Operations" \
      --permissions="networkservices.agentGateways.get,networkservices.operations.get" \
      --stage="GA"

    gcloud projects add-iam-policy-binding "AGW_PROJECT_ID" \
      --member="serviceAccount:service-AE_PROJECT_NUMBER@gcp-sa-aiplatform.iam.gserviceaccount.com" \
      --role="projects/AGW_PROJECT_ID/roles/ae_agw_cross_project_sa"
    ```

### 11.3 Agent Runtime Deployment Specification

Deploy the agent runtime referencing the central gateway and disabling bound token sharing via CAA opt-out:

```python
remote_agent = client.agent_engines.create(
    agent=local_agent,
    config={
        "agent_gateway_config": {
            "agent_to_anywhere_config": {
                "agent_gateway": (
                    "projects/AGW_PROJECT_ID/locations/REGION/agentGateways/AGENT_GATEWAY_TO_ANYWHERE_NAME"
                )
            },
        },
        "identity_type": types.IdentityType.AGENT_IDENTITY,
        "env_vars": {
            # Opt out of default Context-Aware Access (CAA) token binding to allow
            # token validation through cross-project gateway egress
            "GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES": False,
        },
    },
)
```

> **Warning:** **Regional Colocation Invariant:** The Agent Runtime and the Agent Gateway **MUST reside in the exact same Google Cloud region** (e.g., `us-central1`). Cross-region bindings fail control plane validation with `INVALID_ARGUMENT`.

### 11.4 Two-Tier Registry Authorization Model

1.  **Tier 1: Baseline Google APIs Access (Coarse-Grained via `principalSet://`):**
    All runtimes require baseline access to Google Cloud APIs for discovery, telemetry, and platform operations. Register the consolidated `googleapis` endpoint in the central registry and authorize runtimes using project-level or trust-domain-wide principal sets:
    -   *Project-Level Scope:* `principalSet://TRUST_DOMAIN/attribute.platformContainer/aiplatform/projects/AE_PROJECT_NUMBER`
    -   *Trust-Domain-Wide Scope:* `principalSet://TRUST_DOMAIN/*`
    -   *Role:* `roles/iap.egressor` on the Google APIs endpoint.
    > **Important:** **Folder-Level Syntax Limitation:** `attribute.platformContainer/aiplatform/folders/FOLDER_NUMBER` is **not an indexed attribute** in IAM SPIFFE URI evaluation. Scoping must strictly use project-level syntax or Principal Access Boundary (PAB) policies.
2.  **Tier 2: Granular MCP Tools & Peer Agents (Fine-Grained via `principal://`):**
    For sensitive business tools, grant `roles/iap.egressor` on the specific MCP server resource directly to the individual Reasoning Engine:
    `principal://TRUST_DOMAIN/resources/aiplatform/projects/AE_PROJECT_NUMBER/locations/REGION/reasoningEngines/ENGINE_ID`
    Optionally restrict with CEL conditions:
    ```cel
    api.getAttribute('iap.googleapis.com/mcp.tool.isReadOnly', false) == true || api.getAttribute('iap.googleapis.com/mcp.toolName', '') == ''
    ```

### 11.5 Server-Generated Resource ID Extraction Pattern

In Agent Registry, all write operations use `gcloud agent-registry services create`. However, IAP authorization policies **must be bound to the server-generated resource ID** (`agentregistry-00000000-...`), NOT the friendly service name:

```bash
# 1. Fetch server-generated resource ID
REGISTRY_RESOURCE=$(gcloud agent-registry services describe MCP_SERVICE_NAME \
  --project="AGW_PROJECT_ID" \
  --location="REGION" \
  --format='value(registryResource)')

RESOURCE_ID=$(basename "$REGISTRY_RESOURCE")

# 2. Grant roles/iap.egressor on iap_web/agentRegistry/mcpServers/{RESOURCE_ID}
# (Use agents.global.proj-AE_PROJECT_NUMBER.system.id.goog/... if orgless)
gcloud iap web add-iam-policy-binding \
  --project="AGW_PROJECT_ID" \
  --region="REGION" \
  --resource-type=agent-registry \
  --mcp-server="${RESOURCE_ID}" \
  --member="principal://agents.global.org-ORG_ID.system.id.goog/resources/aiplatform/projects/AE_PROJECT_NUMBER/locations/REGION/reasoningEngines/ENGINE_ID" \
  --role="roles/iap.egressor"
```

### 11.6 VPC Service Controls (VPC-SC) Perimeter Bridging

If the Centralized Governance Project (`AGW_PROJECT_ID`) and the Agent Runtime Projects (`AE_PROJECT_NUMBER`) reside in different VPC-SC service perimeters:
1.  Establish a **Perimeter Bridge** connecting both perimeters, OR
2.  Configure explicit **Ingress and Egress Rules** on both perimeters permitting cross-perimeter communication for:
    -   `aiplatform.googleapis.com`
    -   `networkservices.googleapis.com`
    -   `agentregistry.googleapis.com`
