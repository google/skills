# Ingress Architecture: Self-Managed Gateways, Rewrites, and Mesh

This reference details production patterns for ingress into
Gemini platform workloads, including Two-Tier and Single-Tier Self-Managed
Ingress Gateways, URL Map host/path rewrites, API management integration, and
Agent2Agent protocol (A2A protocol) mesh networking.

--------------------------------------------------------------------------------

## Table of Contents

-   [1. Self-Managed Ingress Gateway Architecture](#1-self-managed-ingress-gateway-architecture): Lines 22-88
-   [2. Ingress Traffic Flow and URL Map Rewriting](#2-ingress-traffic-flow-and-url-map-rewriting): Lines 89-201
-   [3. Routing Strategy: Hostname vs Path-Prefix](#3-routing-strategy-hostname-vs-path-prefix): Lines 202-220
-   [4. Policy Enforcement Matrix: IAP and Model Armor](#4-policy-enforcement-matrix-iap-and-model-armor): Lines 221-234
-   [5. Workload Ingress and Apigee API Management](#5-workload-ingress-and-apigee-api-management): Lines 235-259
-   [6. Private CA `TrustConfig` and Internal Regional ALB for Cloud Run MCP](#6-private-ca-trustconfig-and-internal-regional-alb-for-cloud-run-mcp): Lines 260-335
-   [7. Ingress ALB Service Extensions (`LbTrafficExtension` / Envoy `ext_proc`)](#7-ingress-alb-service-extensions-lbtrafficextension-envoy-ext_proc): Lines 336-451

--------------------------------------------------------------------------------

## 1. Self-Managed Ingress Gateway Architecture

Exposing internal Agent Runtime (`reasoningEngines`) workloads directly to
external clients without an ingress gateway creates inconsistent access control,
unmonitored endpoints, and prevents custom corporate domain branding.

A Self-Managed Ingress Gateway provides:

-   Custom enterprise hostnames (`https://agent-a.example.com`) and edge TLS
    termination.
-   Fine-grained Identity-Aware access control (IAP) and Context-Aware Access
    (CAA) policies.
-   Inline AI payload security (Model Armor prompt inspection and response
    sanitization).
-   Protocol, host, and path rewriting for Agent Runtime (`reasoningEngines`)
    streaming and synchronous queries.

### Two-Tier vs. Single-Tier Gateway Architecture

```mermaid
graph TB
    subgraph Client Space
        Client[Enterprise Users / Applications]
    end

    subgraph Tier 1: Public Front Door (Consumer Project)
        ExtALB[Global External Application Load Balancer<br/>• Single Anycast IP<br/>• Client TLS / SNI Termination<br/>• Edge Cloud Armor / Coarse IAP<br/>• Hostname Routing]
        PSC_NEG1[Regional PSC NEG<br/>global access mode]
        ExtALB --> PSC_NEG1
    end

    subgraph Tier 2: Per-Agent Ingress (Producer / Governance Project)
        SA[PSC Service Attachment]
        IntALB[Regional Internal Application Load Balancer<br/>• Per-Agent IAP & CAA Enforcement<br/>• URL Map Host & Path Rewrite<br/>• Model Armor Service Extensions ext_proc]
        PSC_NEG2[PSC NEG to Google APIs<br/>psc_target_service: REGION-aiplatform.googleapis.com]

        PSC_NEG1 -->|Private Service Connect| SA
        SA --> IntALB
        IntALB --> PSC_NEG2
    end

    subgraph Google Managed Tenant
        RE[Agent Runtime (reasoningEngines / ADK Agent)]
        PSC_NEG2 -->|Private VPC Egress| RE
    end

    Client -->|HTTPS agent-a.example.com| ExtALB
```

### Architectural Comparison Matrix (Single-Tier vs. Two-Tier Ingress)

-   **Single-Tier Ingress Gateway** (Single External ALB -> PSC NEG targeting
    regional AI Platform API directly): Gateway and all agents must reside in
    the same project and share a single IAP policy and URL map. Lowest cost and
    latency (~5–10 ms single hop), best for single-project deployments with
    unified policies.
-   **Two-Tier Ingress Gateway** (Recommended for Multi-Team — **Tier 1 Global
    External Application Load Balancer** with **Cloud Armor and IAP** fanning
    out over a Regional PSC NEG + PSC Service Attachment to **Tier 2 Regional
    Internal Application Load Balancers**): Tier 1 and Tier 2 run in separate
    projects; Tier 1 enforces global anycast TLS termination, **edge Cloud Armor
    WAF/DDoS protection, and coarse-grained IAP**, while producer teams own Tier
    2 Regional Internal ALBs, per-agent IAP policies, Model Armor templates, and
    URL Map host/path rewrites independently (~15–25 ms across two hops).

--------------------------------------------------------------------------------

## 2. Ingress Traffic Flow and URL Map Rewriting

### Step-by-Step Two-Tier Request Flow

1.  **Tier 1 Global External ALB (TLS, Cloud Armor and IAP)**: Client resolves
    `agent-a.example.com` to Tier 1's global anycast IP. The Tier 1 **Global
    External Application Load Balancer** terminates TLS using Server Name
    Indication (SNI) and enforces **edge Cloud Armor** security policies and
    **IAP** authentication.
2.  **Tier 1 Host Routing**: Tier 1 URL map matches `Host: agent-a.example.com`
    and routes to the dedicated backend service.
3.  **PSC Traversal (Regional PSC NEG -> Service Attachment)**: The Tier 1
    backend service forwards traffic through its Regional PSC NEG (`global`
    access mode) to the Tier 2 PSC Service Attachment.
4.  **Tier 2 Regional Internal ALB**: The Service Attachment forwards the
    request to the Tier 2 **Regional Internal Application Load Balancer**
    forwarding rule in the producer/governance project.
5.  **Tier 2 Per-Agent IAP and Model Armor**: Evaluates per-agent IAP/Context-Aware
    Access (device posture, IP location) and invokes Model Armor Service
    Extensions (`ext_proc`).
6.  **Tier 2 URL Map Rewriting**: Updates headers and paths required by Agent
    Runtime:
    -   `Host` rewritten to `${REGION}-aiplatform.googleapis.com`
    -   Path prefix `/chat` rewritten to
        `/v1/projects/{AGENT_PROJECT_NUMBER}/locations/{REGION}/reasoningEngines/{RE_ID}:streamQuery`
7.  **Model Armor Inspection (Service Extensions)**: Envoy `ext_proc` sends the
    prompt payload to Model Armor. Prompt injections or jailbreaks trigger
    immediate `HTTP 403` rejection.
8.  **PSC to Google APIs**: The rewritten request routes across Tier 2's Google
    APIs PSC NEG to the regional Agent Runtime (`aiplatform.googleapis.com`)
    backend.
9.  **Execution and Egress Sanitization**: The Agent Runtime executes and streams
    responses. The return payload is sanitized by Model Armor (PII masking)
    before returning to the client.

### Tier 2 URL Map (`tier2-urlmap.yaml`) and Provisioning Commands

```yaml
# tier2-urlmap.yaml (use numeric ${AGENT_PROJECT_NUMBER} in pathPrefixRewrite)
name: tier2-re-urlmap
defaultService: projects/${PRODUCER_PROJECT_ID}/regions/${REGION}/backendServices/tier2-re-backend
hostRules:
  - hosts:
      - "agent-a.example.com"
    pathMatcher: agent-matcher
pathMatchers:
  - name: agent-matcher
    defaultService: projects/${PRODUCER_PROJECT_ID}/regions/${REGION}/backendServices/tier2-re-backend
    pathRules:
      - paths:
          - /chat
          - /stream
        service: projects/${PRODUCER_PROJECT_ID}/regions/${REGION}/backendServices/tier2-re-backend
        routeAction:
          urlRewrite:
            hostRewrite: "${REGION}-aiplatform.googleapis.com"
            pathPrefixRewrite: "/v1/projects/${AGENT_PROJECT_NUMBER}/locations/${REGION}/reasoningEngines/${RE_ID}:streamQuery"
      - paths:
          - /query
        service: projects/${PRODUCER_PROJECT_ID}/regions/${REGION}/backendServices/tier2-re-backend
        routeAction:
          urlRewrite:
            hostRewrite: "${REGION}-aiplatform.googleapis.com"
            pathPrefixRewrite: "/v1/projects/${AGENT_PROJECT_NUMBER}/locations/${REGION}/reasoningEngines/${RE_ID}:query"
```

```bash
# Tier 2 Producer Project (${PRODUCER_PROJECT_ID}): Proxy-Only Subnet, Google APIs PSC NEG, Internal ALB & PSC Service Attachment
gcloud compute networks subnets create "tier2-proxy-only-subnet" --project="${PRODUCER_PROJECT_ID}" \
  --network="${PRODUCER_VPC}" --region="${REGION}" --range="10.129.0.0/23" --purpose="REGIONAL_MANAGED_PROXY" --role="ACTIVE"
gcloud compute networks subnets create "tier2-psc-nat-subnet" --project="${PRODUCER_PROJECT_ID}" \
  --network="${PRODUCER_VPC}" --region="${REGION}" --range="10.129.2.0/24" --purpose="PRIVATE_SERVICE_CONNECT"
gcloud compute network-endpoint-groups create "psc-aiplatform-neg" --project="${PRODUCER_PROJECT_ID}" \
  --region="${REGION}" --network-endpoint-type="private-service-connect" --psc-target-service="${REGION}-aiplatform.googleapis.com"
# Note: Add --iap=enabled ONLY if authenticating via Google IAP; omit --iap=enabled when Tier 1 ext_proc injects an STS OAuth access token for Agent Runtime
gcloud compute backend-services create "tier2-re-backend" --project="${PRODUCER_PROJECT_ID}" \
  --region="${REGION}" --load-balancing-scheme="INTERNAL_MANAGED" --protocol="HTTPS"
gcloud compute backend-services add-backend "tier2-re-backend" --project="${PRODUCER_PROJECT_ID}" \
  --region="${REGION}" --network-endpoint-group="psc-aiplatform-neg" --network-endpoint-group-region="${REGION}"
gcloud compute url-maps import "tier2-re-urlmap" --project="${PRODUCER_PROJECT_ID}" --region="${REGION}" --source="tier2-urlmap.yaml" --quiet
gcloud compute target-https-proxies create "tier2-re-https-proxy" --project="${PRODUCER_PROJECT_ID}" \
  --region="${REGION}" --url-map="tier2-re-urlmap" --certificate-manager-certificates="${TIER2_CERT_NAME}"
gcloud compute forwarding-rules create "tier2-re-fwd-rule" --project="${PRODUCER_PROJECT_ID}" \
  --region="${REGION}" --load-balancing-scheme="INTERNAL_MANAGED" --network="${PRODUCER_VPC}" \
  --subnet="${PRODUCER_SUBNET}" --target-https-proxy="tier2-re-https-proxy" --target-https-proxy-region="${REGION}" --ports=443
gcloud compute service-attachments create "tier2-re-service-attachment" --project="${PRODUCER_PROJECT_ID}" \
  --region="${REGION}" --producer-forwarding-rule="tier2-re-fwd-rule" --connection-preference="ACCEPT_AUTOMATIC" --nat-subnets="tier2-psc-nat-subnet"

# Tier 1 Consumer Front-Door Project (${FRONTDOOR_PROJECT_ID}): Global External ALB (with Edge Cloud Armor & IAP) -> PSC NEG -> Tier 2 Service Attachment
gcloud compute network-endpoint-groups create "tier1-to-tier2-psc-neg" --project="${FRONTDOOR_PROJECT_ID}" \
  --region="${REGION}" --network-endpoint-type="private-service-connect" \
  --psc-target-service="projects/${PRODUCER_PROJECT_ID}/regions/${REGION}/serviceAttachments/tier2-re-service-attachment" \
  --network="${FRONTDOOR_VPC}" --subnet="${FRONTDOOR_SUBNET}"
gcloud compute backend-services create "tier1-ext-backend" --project="${FRONTDOOR_PROJECT_ID}" \
  --global --load-balancing-scheme="EXTERNAL_MANAGED" --protocol="HTTPS" \
  --security-policy="${CLOUD_ARMOR_POLICY}" \
  --iap=enabled,oauth2-client-id="${IAP_CLIENT_ID}",oauth2-client-secret="${IAP_CLIENT_SECRET}"
gcloud compute backend-services add-backend "tier1-ext-backend" --project="${FRONTDOOR_PROJECT_ID}" \
  --global --network-endpoint-group="tier1-to-tier2-psc-neg" --network-endpoint-group-region="${REGION}"
gcloud compute url-maps create "tier1-ext-urlmap" --project="${FRONTDOOR_PROJECT_ID}" --default-service="tier1-ext-backend"
gcloud compute target-https-proxies create "tier1-ext-https-proxy" --project="${FRONTDOOR_PROJECT_ID}" \
  --url-map="tier1-ext-urlmap" --ssl-certificates="${TIER1_SSL_CERT}"
gcloud compute forwarding-rules create "tier1-ext-fwd-rule" --project="${FRONTDOOR_PROJECT_ID}" \
  --global --load-balancing-scheme="EXTERNAL_MANAGED" --target-https-proxy="tier1-ext-https-proxy" --ports=443

# Grant Edge & Backend IAM (Workforce Pool / Service Account roles/aiplatform.user; add roles/iap.httpsResourceAccessor if using IAP)
gcloud projects add-iam-policy-binding "${PRODUCER_PROJECT_ID}" \
  --member="principalSet://iam.googleapis.com/locations/global/workforcePools/${WORKFORCE_POOL_ID}/*" --role="roles/aiplatform.user"
gcloud projects add-iam-policy-binding "${PRODUCER_PROJECT_ID}" --member="${EXT_PROC_IDENTITY}" --role="roles/aiplatform.user"
```

--------------------------------------------------------------------------------

## 3. Routing Strategy: Hostname vs Path-Prefix

1.  **Hostname Routing (Recommended)**:
    -   Each agent has a unique FQDN: `finance-agent.example.com`,
        `hr-agent.example.com`.
    -   **Advantages**: Complete domain isolation, clean mapping to DNS and TLS
        SAN certificates, straightforward per-agent IAP binding.
2.  **Path-Prefix Routing**:
    -   Single domain `agents.example.com` with routes `/finance/*` and `/hr/*`.
    -   **Operational Footgun**: Tier 1 must strip the path prefix (such as
        rewriting `/finance/chat` to `/chat`) **and** either rewrite the `Host`
        header to the Tier 2 per-agent hostname (`agent-a.example.com`) or
        include `"agents.example.com"` in Tier 2's `host_rule.hosts`; otherwise,
        Tier 2 misses the `agent-matcher` host rule or receives nested paths
        that conflict with the destination Agent Runtime `:streamQuery` path
        rewrite.

--------------------------------------------------------------------------------

## 4. Policy Enforcement Matrix: IAP and Model Armor

-   **Transport Security (`TLS 1.3 / mTLS` at Tier 1 and Tier 2)**: Terminates
    public HTTPS at the edge and enforces private mTLS across PSC.
-   **Identity and Access (`Identity-Aware Proxy (IAP)` at Tier 1 or Tier 2)**:
    Validates workforce principal, Context-Aware Access (CAA) device context,
    and IAM `roles/iap.httpsResourceAccessor`. Deploying at Tier 2 allows
    independent per-agent policies.
-   **AI Payload Inspection (`Model Armor via Service Extensions` at Tier 2
    Internal ALB)**: Real-time `ext_proc` gRPC callout inspecting prompts for
    jailbreaks/injections and sanitizing responses for PII/DLP leaks.

--------------------------------------------------------------------------------

## 5. Workload Ingress and Apigee API Management

### Workload Ingress (mTLS and SPIFFE Trust Federation)

For machine-to-agent ingress across clouds, terminate transport-level mTLS at
the Ingress ALB using Certificate Manager with Private CA trust configs, and map
external machine OIDC tokens or SPIFFE X.509 SVIDs into Google Cloud principals
using **Workload Identity Federation** (`WorkloadIdentityPool`), while using
**Workforce Identity Federation** (`WorkforcePool`) for human workforce users
(`EntraID`, `Okta`, `Ping`).

### Apigee X API Management Inline Integration (Northbound and Southbound Private)

1.  **Northbound Ingress Governance**: Place Apigee X in front of the Ingress
    Gateway to validate external consumer JWTs, enforce spike arrest/quotas, and
    route over Southbound PSC into the Tier 2 Regional Internal ALB.
2.  **Southbound Tool and MCP Mediation (`Agent Gateway -> Apigee X Private ->
    Cloud Run / Google MCP / Internal APIs`)**: Egress Agent Gateway enforces
    UAP CEL and Model Armor first, then routes over the PSC-I network attachment
    into an **Apigee X Private Endpoint** (`PSC Endpoint Attachment` inside the
    Governance or Tool Spoke VPC) for protocol mediation, API key / 3LO token
    injection, and rate limiting.

--------------------------------------------------------------------------------

## 6. Private CA `TrustConfig` and Internal Regional ALB for Cloud Run MCP

When an enterprise requires custom Private CA leaf certificates
(`*.internal.example.com`) rather than standard Google-managed certificates on
internal Cloud Run MCP servers:

1.  **Why a Regional Internal ALB Is Required**: Native Cloud Run (`*.run.app`)
    terminates TLS at the Cloud Run ingress edge using Google-managed
    certificates. To serve a custom Private CA certificate, front the Cloud Run
    service with an `INTERNAL_MANAGED` Regional Internal Application Load
    Balancer backed by a `SERVERLESS` Network Endpoint Group and a Private Cloud
    DNS zone peered via the ACT's `dnsPeeringConfig` (using a Certificate
    Manager self-managed certificate or Private CA certificate issuance config).
2.  **Preserving Public Root Trust (`PUBLICLY_TRUSTED_ROOTS`)**: When attaching
    a Certificate Manager `TrustConfig` to an Agent Connectivity Template's
    `tlsConfig`, always set `additionalRoots = "PUBLICLY_TRUSTED_ROOTS"`.
    Setting `NO_ADDITIONAL_ROOTS` in `ALL_TRAFFIC` mode strips the WebPKI root
    bundle and breaks outbound TLS handshakes to Google APIs
    (`aiplatform.googleapis.com`).
3.  **Handling Empty `:authority` on Serverless NEGs (`defaultService`, Wildcard `"*"` Host Rule and Mandatory IAP/mTLS)**:
    When an `INTERNAL_MANAGED` Regional Internal ALB fronts a Cloud Run
    Serverless NEG, configure the URL Map `defaultService` and include the
    wildcard `"*"` alongside `"{mcp_internal_fqdn}"` in `hostRules[].hosts`
    (`--hosts="${MCP_INTERNAL_FQDN},*"`, since Compute Engine `HostRule` schema
    regex only accepts RFC-1034 hostnames or `"*"`). Because `defaultService`
    and `"*"` match requests with empty `:authority` / `Host` headers, **always
    enforce transport and IAM authentication (`--iap=enabled` with
    `roles/iap.egressor` and/or `ServerTlsPolicy` mTLS)** on the Internal ALB so
    omitting `Host` never bypasses access control:

```bash
export PROJECT_ID="gov-hub-proj" MCP_PROJECT_ID="mcp-spoke-proj" REGION="us-central1"
export TRUST_CONFIG_ID="enterprise-private-ca-trust" MCP_SERVICE_NAME="mcp-server-prod"
export MCP_VPC="mcp-spoke-vpc" MCP_SUBNET="mcp-ilb-subnet" MCP_ILB_IP="10.20.10.10"
export MCP_INTERNAL_FQDN="mcp.internal.example.com" MCP_INTERNAL_CERT="mcp-internal-private-cert"

# 1. Import Certificate Manager TrustConfig in ${REGION} (reference in ACT tlsConfig with additionalRoots: PUBLICLY_TRUSTED_ROOTS so WebPKI roots for aiplatform.googleapis.com are preserved)
cat <<EOF > trust-config.yaml
trustStores:
  - trustAnchors:
      - pemCertificate: |
          -----BEGIN CERTIFICATE-----
          ...Enterprise Private Root CA PEM...
          -----END CERTIFICATE-----
EOF
gcloud certificate-manager trust-configs import "${TRUST_CONFIG_ID}" \
  --project="${PROJECT_ID}" --location="${REGION}" --source="trust-config.yaml"

# 2. Because native Cloud Run (*.run.app) uses Google-managed certificates, front Cloud Run with a Serverless NEG and Regional INTERNAL_MANAGED ALB (with IAP enabled; --protocol="HTTP" is required by GCE for Serverless NEGs)
gcloud compute network-endpoint-groups create "mcp-serverless-neg" \
  --project="${MCP_PROJECT_ID}" --region="${REGION}" \
  --network-endpoint-type="serverless" --cloud-run-service="${MCP_SERVICE_NAME}"
gcloud compute backend-services create "mcp-internal-backend" \
  --project="${MCP_PROJECT_ID}" --region="${REGION}" \
  --load-balancing-scheme="INTERNAL_MANAGED" --protocol="HTTP" \
  --iap=enabled,oauth2-client-id="${IAP_CLIENT_ID}",oauth2-client-secret="${IAP_CLIENT_SECRET}"
gcloud compute backend-services add-backend "mcp-internal-backend" \
  --project="${MCP_PROJECT_ID}" --region="${REGION}" \
  --network-endpoint-group="mcp-serverless-neg" --network-endpoint-group-region="${REGION}"
# Configure defaultService + wildcard "*" hostRule alongside ${MCP_INTERNAL_FQDN} (requires IAP and/or ServerTlsPolicy mTLS)
gcloud compute url-maps create "mcp-internal-urlmap" \
  --project="${MCP_PROJECT_ID}" --region="${REGION}" --default-service="mcp-internal-backend"
gcloud compute url-maps add-path-matcher "mcp-internal-urlmap" \
  --project="${MCP_PROJECT_ID}" --region="${REGION}" --path-matcher-name="mcp-matcher" \
  --default-service="mcp-internal-backend" --new-hosts="${MCP_INTERNAL_FQDN},*"
gcloud compute target-https-proxies create "mcp-internal-https-proxy" \
  --project="${MCP_PROJECT_ID}" --region="${REGION}" --url-map="mcp-internal-urlmap" \
  --certificate-manager-certificates="${MCP_INTERNAL_CERT}"
gcloud compute forwarding-rules create "mcp-internal-fwd-rule" \
  --project="${MCP_PROJECT_ID}" --region="${REGION}" --load-balancing-scheme="INTERNAL_MANAGED" \
  --network="${MCP_VPC}" --subnet="${MCP_SUBNET}" --address="${MCP_ILB_IP}" \
  --target-https-proxy="mcp-internal-https-proxy" --target-https-proxy-region="${REGION}" --ports=443
```

--------------------------------------------------------------------------------

## 7. Ingress ALB Service Extensions (`LbTrafficExtension` / Envoy `ext_proc`)

When an Application Load Balancer (ALB) requires custom header mutation,
external token exchange (`sts.googleapis.com/v1/token`), or custom request
authentication before forwarding to a Google Cloud backend
(`aiplatform.googleapis.com` or Cloud Run), attach a **Service Extensions
`LbTrafficExtension`** (`ext_proc` gRPC callout).

### 7.1 GA `LbTrafficExtension` YAML Schema and `gcloud service-extensions lb-traffic-extensions import`

> [!IMPORTANT] **Location Scope and HTTP/2 Callout Backend**: `gcloud
> service-extensions lb-traffic-extensions` uses `import <name>
> --location=<location> --source=<file.yaml>`. For a **Global External
> Application Load Balancer** (`EXTERNAL_MANAGED` with global forwarding rules),
> use `--location="global"` and reference `global/forwardingRules/...` and
> `global/backendServices/...` (configured with `--protocol=HTTP2`); for a
> **Regional Internal Application Load Balancer** (`INTERNAL_MANAGED`), use
> `--location="${REGION}"` and `regions/${REGION}/...`.

```yaml
# lb-traffic-extension.yaml (Global External ALB: --location=global; use regions/${REGION}/... for Regional Internal ALB)
name: ext-proc-token-exchange
loadBalancingScheme: EXTERNAL_MANAGED
forwardingRules:
  - https://www.googleapis.com/compute/v1/projects/${PROJECT_ID}/global/forwardingRules/${FORWARDING_RULE_NAME}
extensionChains:
  - name: token-exchange-chain
    matchCondition:
      celExpression: 'true'
    extensions:
      - name: ext-proc-auth-swap
        authority: ext-proc.internal.example.com
        service: https://www.googleapis.com/compute/v1/projects/${PROJECT_ID}/global/backendServices/${EXT_PROC_BACKEND_SERVICE}
        supportedEvents:
          - REQUEST_HEADERS
        timeout: 1.0s
        failOpen: false
```

```bash
gcloud compute backend-services create "${EXT_PROC_BACKEND_SERVICE}" --project="${PROJECT_ID}" \
  --global --load-balancing-scheme="EXTERNAL_MANAGED" --protocol="HTTP2" --health-checks="${EXT_PROC_HC}"
gcloud service-extensions lb-traffic-extensions import ext-proc-token-exchange \
  --location="global" \
  --source="lb-traffic-extension.yaml" \
  --project="${PROJECT_ID}"
```

### 7.2 Envoy `ext_proc` Credential Caching, STS Federation and Fail-Closed Header Mutation

When implementing a Python `ExternalProcessorServicer`:

1.  **Fail Closed on Missing or Malformed Bearer Tokens**: Return an immediate
    `HTTP 401` `ImmediateResponse` (`StatusCode.Unauthorized`) whenever
    `Authorization: Bearer <token>` is absent or empty.
2.  **Thread-Safe Credential Caching and Connection Pooling**: Reuse a persistent
    `httpx.Client(timeout=0.4)` and cache federated STS tokens from
    `https://sts.googleapis.com/v1/token` (`expiry - 60s`, keyed by SHA-256
    token digest) so callouts stay well within Envoy's `timeout: 1.0s`. For OIDC
    Workforce Identity Federation (`Okta`, `EntraID`, `Ping`), pass
    `"subject_token_type": "urn:ietf:params:oauth:token-type:id_token"` (or
    `"urn:ietf:params:oauth:token-type:jwt"` for generic workload JWTs).
3.  **Preserving Upstream Caller Context**: Replace `Authorization` with the
    Google Cloud STS access token for edge IAM (`roles/aiplatform.user` or
    `roles/run.invoker`) and copy the caller's original token into
    `X-Forwarded-User-Authorization` using `HeaderValue(key=..., raw_value=...)`
    with `OVERWRITE_IF_EXISTS_OR_ADD`. Pair this inbound exchange with **Agent
    Identity Auth Manager (`AuthProvider`)** for outbound `2LO`/`3LO` tool calls
    (`references/agent_runtime_and_identity.md` Section 6.2):

```python
import hashlib, json, threading, time, urllib.parse, httpx
from envoy.config.core.v3 import base_pb2
from envoy.service.ext_proc.v3 import external_processor_pb2 as ep_pb2

_STS_CLIENT = httpx.Client(timeout=0.4)
_STS_LOCK = threading.Lock()
_STS_CACHE: dict[str, tuple[str, float]] = {}

def exchange_workforce_token_via_sts(idp_jwt: str, workforce_pool_provider: str, user_project: str = "") -> str:
  digest = hashlib.sha256(f"{workforce_pool_provider}:{idp_jwt}".encode("utf-8")).hexdigest()
  now = time.time()
  if (cached := _STS_CACHE.get(digest)) and now < cached[1] - 60:
    return cached[0]
  provider_path = workforce_pool_provider.strip().removeprefix("//iam.googleapis.com/").lstrip("/")
  payload = {
      "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
      "audience": f"//iam.googleapis.com/{provider_path}",
      "scope": "https://www.googleapis.com/auth/cloud-platform",
      "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
      "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
      "subject_token": idp_jwt,
  }
  if user_project:
    payload["options"] = json.dumps({"userProject": user_project})
  resp = _STS_CLIENT.post("https://sts.googleapis.com/v1/token", content=urllib.parse.urlencode(payload), headers={"Content-Type": "application/x-www-form-urlencoded"})
  resp.raise_for_status()
  body = resp.json()
  with _STS_LOCK:
    _STS_CACHE[digest] = (str(body["access_token"]), now + float(body.get("expires_in", 3600)))
  return str(body["access_token"])

def build_ext_proc_header_mutation(original_auth: str, gcp_token: str) -> ep_pb2.HeaderMutation:
  return ep_pb2.HeaderMutation(
      set_headers=[
          base_pb2.HeaderValueOption(
              header=base_pb2.HeaderValue(key="X-Forwarded-User-Authorization", raw_value=original_auth.encode("utf-8")),
              append_action=base_pb2.HeaderValueOption.OVERWRITE_IF_EXISTS_OR_ADD,
          ),
          base_pb2.HeaderValueOption(
              header=base_pb2.HeaderValue(key="Authorization", raw_value=f"Bearer {gcp_token}".encode("utf-8")),
              append_action=base_pb2.HeaderValueOption.OVERWRITE_IF_EXISTS_OR_ADD,
          ),
      ]
  )
```
