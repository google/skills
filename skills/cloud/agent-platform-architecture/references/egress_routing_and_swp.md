# Egress Architecture: Routing, SWP, and gRPC Interception

This reference details the low-level data-plane routing mechanics for outbound
traffic from Gemini platform workloads, focusing on
Policy-Based Routing, Secure Web Proxy next-hop mode, and non-HTTP/2 gRPC
traversal.

--------------------------------------------------------------------------------

## Table of Contents

-   [1. Outbound Interception Pipeline (`ALL_TRAFFIC`)](#1-outbound-interception-pipeline-all_traffic): Lines 22-54
-   [2. Policy-Based Routing (PBR) vs Static Routes](#2-policy-based-routing-pbr-vs-static-routes): Lines 55-128
-   [3. Secure Web Proxy (SWP) NEXT_HOP_ROUTING_MODE](#3-secure-web-proxy-swp-next_hop_routing_mode): Lines 129-218
-   [4. Consuming gRPC Endpoints (Spanner / Google APIs)](#4-consuming-grpc-endpoints-spanner-google-apis): Lines 219-248
-   [5. Egress to Cloud Run / Cloud Functions (OIDC JWT and Header Conflict Invariant)](#5-egress-to-cloud-run-cloud-functions-oidc-jwt-and-header-conflict-invariant): Lines 249-293
-   [6. Mutual TLS (mTLS) Client Certificate Management](#6-mutual-tls-mtls-client-certificate-management): Lines 294-312
-   [7. Cross-Cloud and Hybrid Secure Web Proxy (SWP) mTLS Egress Hub](#7-cross-cloud-and-hybrid-secure-web-proxy-swp-mtls-egress-hub): Lines 313-371

--------------------------------------------------------------------------------

## 1. Outbound Interception Pipeline (`ALL_TRAFFIC`)

When the Agent Connectivity Template is set to `vpcEgress: ALL_TRAFFIC`,
outbound connections follow a deterministic multi-stage interception pipeline:

```mermaid
graph TD
    Agent[Reasoning Engine Container] -->|DNS Resolution| SyntheticDNS[Synthetic Resolver]
    SyntheticDNS -->|Returns 240.0.0.2| Agent
    Agent -->|TCP Connect 240.0.0.2:443| AGW_Proxy[Agent Gateway Envoy Proxy]
    AGW_Proxy -->|TLS SNI Inspection| SNICheck{SNI in Registry?}
    SNICheck -->|No Match (Policy V1)| Drop1[Drop: default_denied<br/>UNEXPECTED_EOF_WHILE_READING]
    SNICheck -->|No Match (UAP Policy V2:<br/>destination.is_registered == false)| IAPCheck{UAP / IAP Authz}
    SNICheck -->|Matched (destination.is_registered == true)| IAPCheck
    IAPCheck -->|Denied| Drop2[HTTP 403 / TLS Drop]
    IAPCheck -->|Allowed| PSC_I[PSC Network Attachment]
    PSC_I -->|Enters Consumer Subnet| PBR[Policy-Based Route (PBR)]
    PBR -->|Next-Hop Forwarding| SWP[Secure Web Proxy (NEXT_HOP)]
    SWP -->|Security Policy CEL| CloudNAT[Cloud NAT (Autogen)]
    CloudNAT -->|Egress with Static IP| Internet[External SaaS / APIs]
```

> [!NOTE] **IAM Policy V1 vs. UAP Policy V2 Unregistered SNI Behavior**: When
> the `AuthzExtension` uses legacy IAM Policy V1 (no `iapPolicyVersion = "V2"`),
> any SNI not cataloged in Agent Registry is immediately dropped at TLS
> termination with `default_denied` (`[SSL: UNEXPECTED_EOF_WHILE_READING]`).
> When `iapPolicyVersion = "V2"` is enabled, unregistered SNIs are evaluated by
> the IAP authorization engine against UAP rules matching `destination.is_registered == false`
> (using `destination.unregistered.host`, `.path`, and `.method`) before being
> allowed or dropped.

--------------------------------------------------------------------------------

## 2. Policy-Based Routing (PBR) vs Static Routes

Standard Google Cloud VPC routing has a critical limitation when intercepting
traffic from Network Attachments:

*   **Static Route Tag Incompatibility**: Static routes targeting an Internal
    Load Balancer (`--next-hop-ilb`) require network tags (`--tags`). However,
    Private Service Connect Interfaces (PSC-I) provisioned by Google-managed
    tenant projects **cannot have network tags attached**.
*   **PSC Route Target Prohibition**: Google Cloud route tables explicitly
    prohibit PSC forwarding rules or service attachments as next-hop targets.
*   **The PBR Solution**: Policy-Based Routing (PBR) routes traffic based on
    source IP range rather than network tags. By matching
    `--source-range=<PSCI_SUBNET_CIDR>` and `--destination-range=0.0.0.0/0`, PBR
    cleanly intercepts all egress exiting the Network Attachment and directs it
    to the SWP internal load balancer IP.

### PBR Resource Manifests

#### 1. Internal / Peered Route Bypass (`priority: 50`, Evaluated First)

To prevent internal RFC 1918 or peered non-RFC 1918 PUPI (`${PUPI_CIDR}`) VPC
destinations from being hair-pinned into the external Secure Web Proxy, place a
higher-priority (`priority: 50`, lower numerical value = evaluated first)
`DEFAULT_ROUTING` rule ahead of the `priority: 100` `0.0.0.0/0` SWP catch-all:

```yaml
# Canonical REST/YAML resource name requires /locations/global/policyBasedRoutes/
name: projects/${PROJECT_ID}/locations/global/policyBasedRoutes/pbr-psci-default-fallback-10
description: "Bypass SWP for RFC 1918 (10.0.0.0/8, plus priority 50 rules for 172.16.0.0/12 and 192.168.0.0/16)"
network: "projects/${PROJECT_ID}/global/networks/${VPC_NAME}"
priority: 50
filter:
  protocolVersion: IPV4
  srcRange: "${PSCI_SUBNET_CIDR}"    # REST/YAML field is srcRange (gcloud CLI flag is --source-range); must match PSC-I Subnet CIDR (/26+, such as 10.20.1.0/26)
  destRange: "10.0.0.0/8"           # Pair with priority: 50 for 172.16.0.0/12 and 192.168.0.0/16, priority: 51 for ${PUPI_CIDR} (PUPI), priority: 52 for 199.36.153.8/30 (PGA), and priority: 53 for 199.36.153.4/30 (VPC-SC)
  ipProtocol: ALL
nextHopOtherRoutes: DEFAULT_ROUTING
```

#### 2. Primary Policy-Based Route (PSC-I Public Egress to SWP, `priority: 100`)

```yaml
name: projects/${PROJECT_ID}/locations/global/policyBasedRoutes/pbr-psci-to-swp
description: "Steer PSC-I agent public egress to Secure Web Proxy internal IP"
network: "projects/${PROJECT_ID}/global/networks/${VPC_NAME}"
priority: 100
filter:
  protocolVersion: IPV4
  srcRange: "${PSCI_SUBNET_CIDR}"    # REST/YAML field is srcRange (gcloud CLI flag is --source-range)
  destRange: "0.0.0.0/0"
  ipProtocol: ALL
nextHopIlbIp: "${SWP_ILB_IP}"       # Internal IP of SWP Gateway in dedicated SWP subnet (such as 10.20.2.50)
```

```bash
export PROJECT_ID="host-vpc-proj" VPC_NAME="enterprise-shared-vpc"
export PSCI_SUBNET_CIDR="10.20.1.0/26" SWP_ILB_IP="10.20.2.50" PUPI_CIDR="198.51.100.0/24"
# For multi-VPC custom/PUPI route exchange (HOST_VPC / SPOKE_VPC peerings), see references/topologies_and_project_layouts.md Section 9.

for IDX_CIDR in "10:10.0.0.0/8" "172:172.16.0.0/12" "192:192.168.0.0/16"; do
  gcloud network-connectivity policy-based-routes create "pbr-psci-rfc1918-${IDX_CIDR%%:*}" \
    --project="${PROJECT_ID}" --network="projects/${PROJECT_ID}/global/networks/${VPC_NAME}" \
    --source-range="${PSCI_SUBNET_CIDR}" --destination-range="${IDX_CIDR#*:}" \
    --ip-protocol="ALL" --priority=50 --next-hop-other-routes="DEFAULT_ROUTING"
done
gcloud network-connectivity policy-based-routes create "pbr-psci-to-swp" \
  --project="${PROJECT_ID}" --network="projects/${PROJECT_ID}/global/networks/${VPC_NAME}" \
  --source-range="${PSCI_SUBNET_CIDR}" --destination-range="0.0.0.0/0" \
  --ip-protocol="ALL" --priority=100 --next-hop-ilb-ip="${SWP_ILB_IP}"
```

--------------------------------------------------------------------------------

## 3. Secure Web Proxy (SWP) NEXT_HOP_ROUTING_MODE

When deploying Secure Web Proxy behind an Agent Gateway Network Attachment:

1.  **Type and Routing Mode (Transparent PBR Next-Hop vs. Explicit Proxy Mode)**:
    When SWP operates as a **Transparent PBR Next-Hop** (`Section 3`), the
    Gateway resource must specify `type: SECURE_WEB_GATEWAY` and `routingMode:
    NEXT_HOP_ROUTING_MODE` (specifying `SECURE_WEB_PROXY` or omitting
    `routingMode` in PBR Next-Hop mode causes import failure). Conversely, when
    SWP operates in **Explicit Proxy / Cross-Cloud NLB Termination Mode**
    (`Section 7`), omit `routing_mode` and attach `certificate_urls` and
    `server_tls_policy`.
2.  **Dedicated SWP Subnet + Proxy-Only Subnet**: Place the SWP Gateway instance
    in its own regular RFC 1918 subnet (`10.20.2.0/24`, distinct from the
    PBR-intercepted PSC-I subnet `10.20.1.0/26` so SWP outbound packets are not
    re-intercepted by PBR), alongside a regional proxy-only subnet (sized to
    **at least `/26`**, such as `10.20.3.0/24`) with `purpose:
    REGIONAL_MANAGED_PROXY` and `role: ACTIVE`.
3.  **Autogenerated Cloud NAT**: SWP in `NEXT_HOP_ROUTING_MODE` automatically
    provisions an autogenerated router (`swg-autogen-router-{network_id}`) and
    Cloud NAT (`swg-autogen-nat`) with `natIpAllocateOption: AUTO_ONLY` and
    `ENDPOINT_TYPE_SWG`. Exclude the PSC-I subnet from any manual Cloud NAT via
    `LIST_OF_SUBNETWORKS` (never `ALL_SUBNETWORKS_ALL_IP_RANGES`); outbound
    calls reflect `swg-autogen-nat` IPs.

### Gateway Resource Definition

```yaml
name: projects/${PROJECT_ID}/locations/${REGION}/gateways/swp-egress-gateway
type: SECURE_WEB_GATEWAY
routingMode: NEXT_HOP_ROUTING_MODE
addresses: ["${SWP_ILB_IP}"]
ports: [443]
subnetwork: "projects/${PROJECT_ID}/regions/${REGION}/subnetworks/${SWP_SUBNET_NAME}"
network: "projects/${PROJECT_ID}/global/networks/${VPC_NAME}"
gatewaySecurityPolicy: "projects/${PROJECT_ID}/locations/${REGION}/gatewaySecurityPolicies/swp-security-policy"
```

### Gateway Security Policy and Rules

```yaml
name: projects/${PROJECT_ID}/locations/${REGION}/gatewaySecurityPolicies/swp-security-policy
description: "Egress policy for approved agent destinations"
```

```yaml
name: projects/${PROJECT_ID}/locations/${REGION}/gatewaySecurityPolicies/swp-security-policy/rules/deny-denylisted-llms
priority: 10
basicProfile: DENY
enabled: true
sessionMatcher: "host() in ['api.openai.com', 'api.anthropic.com', 'api.cohere.ai'] || host().endsWith('.openai.com') || host().endsWith('.anthropic.com') || host().endsWith('.cohere.ai')"
```

```yaml
# GatewaySecurityPolicy enforces implicit default-DENY for all unmatched hosts; priority 100 ALLOW permits only explicit approved FQDNs:
name: projects/${PROJECT_ID}/locations/${REGION}/gatewaySecurityPolicies/swp-security-policy/rules/allow-approved-domains
priority: 100
basicProfile: ALLOW
enabled: true
sessionMatcher: "host() == 'aiplatform.googleapis.com' || host() == 'aiplatform.mtls.googleapis.com' || host() == '${REGION}-aiplatform.googleapis.com' || host() == '${REGION}-aiplatform.mtls.googleapis.com' || host() == 'aiplatform.${REGION}.rep.googleapis.com' || host() == 'agentregistry.googleapis.com' || host() == 'agentidentity.googleapis.com' || host() == 'cloudresourcemanager.mtls.googleapis.com' || host() == 'iamcredentials.mtls.googleapis.com' || host() == 'telemetry.mtls.googleapis.com' || host() == 'trace.mtls.googleapis.com' || host() == 'logging.googleapis.com' || host() == 'monitoring.googleapis.com' || host() == 'cloudtrace.googleapis.com' || host() == 'telemetry.googleapis.com' || host() == 'spanner.googleapis.com' || host() == '${CLOUD_RUN_MCP_HOST}'"
```

```bash
gcloud network-security gateway-security-policies import swp-security-policy \
  --project="${PROJECT_ID}" --location="${REGION}" --source="swp-security-policy.yaml"
gcloud network-security gateway-security-policies rules import deny-denylisted-llms \
  --project="${PROJECT_ID}" --location="${REGION}" --gateway-security-policy="swp-security-policy" --source="deny-denylisted-llms.yaml"
gcloud network-security gateway-security-policies rules import allow-approved-domains \
  --project="${PROJECT_ID}" --location="${REGION}" --gateway-security-policy="swp-security-policy" --source="allow-approved-domains.yaml"
gcloud network-services gateways import swp-egress-gateway \
  --project="${PROJECT_ID}" --location="${REGION}" --source="swp-egress-gateway.yaml"
```

> [!IMPORTANT] **Explicit Google APIs FQDNs, PGA Bypass and `.googleapis.com`
> Wildcard Prohibition**: In `ALL_TRAFFIC` mode, ADK streaming queries
> initialize sessions via `POST
> https://{region}-aiplatform.mtls.googleapis.com/.../sessions`. Configure
> Private Cloud DNS CNAME routing for `*.googleapis.com` and `*.run.app` to
> `private.googleapis.com.` (`199.36.153.8/30`) or `restricted.googleapis.com.`
> (`199.36.153.4/30`) with `priority: 52..53` `DEFAULT_ROUTING` PBR bypasses so
> Google APIs and internal Cloud Run traffic route via Private Google Access,
> and list the explicit core Google APIs FQDNs, `spanner.googleapis.com`, and
> approved `${CLOUD_RUN_MCP_HOST}` in the SWP `sessionMatcher` (preceded by a
> `priority: 10` `DENY` rule for denylisted external LLM domains) rather than a
> broad `host().endsWith('.googleapis.com')` wildcard. Only append external test
> endpoints (`host() == 'api.ipify.org'` or `host() == 'api.weather.gov'`) in
> non-production validation environments when running NAT reflection probes.

--------------------------------------------------------------------------------

## 4. Consuming gRPC Endpoints (Spanner / Google APIs)

Google Cloud services accessed over binary gRPC (such as Spanner
`spanner.googleapis.com`) require special handling:

1.  **Upper-Case Protocol Binding**: Google APIs accessed over gRPC must be
    registered in Agent Registry with `protocolBinding: GRPC` (strictly
    uppercase). Using lowercase `grpc` or `JSONRPC` causes proxy rejection.
2.  **Unregistered Endpoint Fallback**: Agent Gateway's Envoy HTTP/2 trie does
    not parse arbitrary gRPC method `:path` prefixes (such as
    `/google.spanner.v1.Spanner/CreateSession`), classifying them as
    `agentGatewayInfo: {}`. To allow gRPC streams through IAP authorization without
    opening a broad `googleapis.com` wildcard, configure a UAP allow rule scoped
    to the exact gRPC service hostname: `((destination.is_registered == false)
    && (destination.unregistered.host == 'spanner.googleapis.com'))`.
3.  **SPIFFE Limitation on Data Plane**: Spanner data-plane APIs do NOT evaluate
    SPIFFE URIs (`principal://agents.global.org-...`), returning `403
    IAM_PERMISSION_DENIED`. The agent workload must use **Service Account
    Impersonation**:
    -   Grant the agent container's `principalSet` the role
        `roles/iam.serviceAccountTokenCreator` on an intermediate service
        account.
    -   Grant the intermediate service account `roles/spanner.databaseUser` on
        the Spanner database.
    -   In Python/ADK code, use Google Auth SDK
        `impersonated_credentials.Credentials` to mint an OAuth 2.0 token before
        initializing the Spanner client.

--------------------------------------------------------------------------------

## 5. Egress to Cloud Run / Cloud Functions (OIDC JWT and Header Conflict Invariant)

When an agent invokes an internal MCP server hosted on Cloud Run through Agent
Gateway, two authentication constraints apply:

1.  **Authorization Header Interception by Cloud Run Ingress**: Google Cloud
    Run's front-end proxy intercepts and validates the standard `Authorization:
    Bearer <ID_TOKEN>` header for Cloud Run IAM authentication
    (`roles/run.invoker`), stripping or rejecting it with HTTP 401/403 if an
    upstream user or application token is passed in that header.
    *   **Workaround A (`X-Serverless-Authorization`)**: Pass the Cloud Run IAM
        OIDC ID token in `X-Serverless-Authorization: Bearer <IAM_ID_TOKEN>` and
        keep upstream application/user credentials in `Authorization` (or vice
        versa).
    *   **Workaround B (Agent Identity Auth Manager)**: Configure Agent Identity
        Auth Manager to manage and inject Cloud Run invocation credentials over
        the wire at the Agent Gateway boundary.
2.  **Service Account Impersonation for OIDC ID Tokens**: Direct egress from
    Agent Identity (`principalSet://...`) cannot mint standard OIDC ID tokens
    directly; use Service Account Impersonation when minting an IAM OIDC token
    from ADK code:

```python
import google.auth
from google.auth import impersonated_credentials
import google.auth.transport.requests

default_creds, project_id = google.auth.default()
target_sa = f"cloud-run-invoker@{project_id}.iam.gserviceaccount.com"
target_creds = impersonated_credentials.Credentials(
    source_credentials=default_creds,
    target_principal=target_sa,
    target_scopes=["https://www.googleapis.com/auth/iam"],
)
id_creds = impersonated_credentials.IDTokenCredentials(
    target_credentials=target_creds,
    target_audience="https://custom-tool-service-xyz.a.run.app",
    include_email=True,
)
id_creds.refresh(google.auth.transport.requests.Request())
headers = {"X-Serverless-Authorization": f"Bearer {id_creds.token}"}
```

--------------------------------------------------------------------------------

## 6. Mutual TLS (mTLS) Client Certificate Management

When an Agent Gateway or runtime connects to upstream internal enterprise
endpoints or partner APIs requiring mTLS:

*   **Failure Symptom**: Gateway proxy load-balancer logs show connection drops
    or HTTP 403 errors with `jsonPayload.mtls.clientCertChainVerified: false`.
*   **Root Cause**: The client certificate associated with the gateway's
    `ClientTlsPolicy` in Certificate Manager is expired, invalid, or signed by a
    CA untrusted by the target server.
*   **Remediation**:
    1.  Inspect certificate validity and CA chain in Certificate Manager.
    2.  Issue a renewed X.509 certificate and update the target
        `ClientTlsPolicy` resource.
    3.  Ensure the destination server's trust store includes the root CA signing
        the gateway's client certificate.

--------------------------------------------------------------------------------

## 7. Cross-Cloud and Hybrid Secure Web Proxy (SWP) mTLS Egress Hub

When routing outbound or cross-cloud agent traffic (across Cloud Interconnect or
HA VPN to AWS, Azure, or on-premises endpoints) through a governed hub, enforce
a **two-stage egress pipeline** rather than bypassing SWP:

1.  **Stage 1 — Layer 7 URL Filtering via Next-Hop SWP (`NEXT_HOP_ROUTING_MODE`)**:
    Route outbound cross-cloud traffic from the Agent Gateway PSC-I subnet
    **through Next-Hop Secure Web Proxy** (via the priority `100` PBR rule in
    Section 2; do **not** bypass SWP with a `DEFAULT_ROUTING` PBR for cross-cloud
    endpoints) so SWP enforces Layer 7 hostname/URL allowlisting before traffic
    crosses the hybrid boundary.
2.  **Stage 2 — Mutual TLS Origination via `ClientTlsPolicy`, Regional Internal Proxy ALB and Hybrid NEG**:
    Forward approved traffic to a **Regional `INTERNAL_MANAGED` Proxy Load
    Balancer** VIP (`10.40.2.x`, outside the `/26` PSC-I subnet), whose
    `BackendService` originates mutual TLS using a Certificate Manager
    **`ClientTlsPolicy`** (and `BackendAuthenticationConfig`) to the Zonal
    **Hybrid Connectivity NEG (`NON_GCP_PRIVATE_IP_PORT`)** across Cloud
    Interconnect or HA VPN:

| Egress Hub Component | Resource / API Type | Mandatory Configuration Contract |
| :--- | :--- | :--- |
| **1. Subnets and Health-Check Firewall** | `compute.subnetworks` + `compute.firewalls` | Provision a PSC-I subnet (`/26`, `purpose=PRIVATE`), a dedicated VIP/SWP subnet (`10.40.2.0/24` — place the Internal ALB VIP outside the `/26` PSC-I range), an active Proxy-Only subnet (`10.40.10.0/23`, `purpose=REGIONAL_MANAGED_PROXY`, `role=ACTIVE`), and a firewall rule allowing health checks (`35.191.0.0/16,130.211.0.0/22`) and the proxy-only subnet. |
| **2. Zonal Hybrid NEG** | `compute.networkEndpointGroups` (`zonal`) | Create with `--network="${VPC_NAME}" --network-endpoint-type=non-gcp-private-ip-port --default-port=443` and attach remote cross-cloud endpoints via `--add-endpoint="ip=${REMOTE_IP},port=${REMOTE_PORT}"`. |
| **3. Private CA Trust Store and ACT DNS Peering** | `certificatemanager.trustConfigs` + `dnsPeeringConfig` | Peer the cross-cloud Private Cloud DNS domain via the ACT's `dnsPeeringConfig`, and load the enterprise Private CA root PEM into `TrustConfig` with `additionalRoots: PUBLICLY_TRUSTED_ROOTS` on the ACT `tlsConfig` (never `NO_ADDITIONAL_ROOTS` in `ALL_TRAFFIC` mode, which strips Google API WebPKI roots). |
| **4. Inbound mTLS Validation** | `networksecurity.serverTlsPolicies` | Set `mtlsPolicy.clientValidationMode = "REJECT_INVALID"` and `mtlsPolicy.clientValidationTrustConfig = "projects/${PROJECT_NUMBER}/locations/${REGION}/trustConfigs/${TRUST_CONFIG}"` (numeric `${PROJECT_NUMBER}` required). |
| **5. Outbound mTLS Origination** | `networksecurity.clientTlsPolicies` + `backendAuthenticationConfigs` | Configure a Certificate Manager **`ClientTlsPolicy`** (never embed client private keys in agent source code) and `BackendAuthenticationConfig` on the Next-Hop SWP -> Regional `INTERNAL_MANAGED` Proxy Load Balancer `BackendService` (`--tls-settings`) backed by the Hybrid NEG (`NON_GCP_PRIVATE_IP_PORT`). |

```bash
# 1. Create Zonal Hybrid Connectivity NEG (NON_GCP_PRIVATE_IP_PORT) for Cross-Cloud / On-Premises Endpoint
gcloud compute network-endpoint-groups create "hybrid-mtls-neg" \
  --project="${PROJECT_ID}" --zone="${ZONE}" --network="${VPC_NAME}" \
  --network-endpoint-type="non-gcp-private-ip-port" --default-port=8443
gcloud compute network-endpoint-groups update "hybrid-mtls-neg" \
  --project="${PROJECT_ID}" --zone="${ZONE}" --add-endpoint="ip=${REMOTE_IP},port=8443"

# 2. Configure Certificate Manager ClientTlsPolicy & BackendAuthenticationConfig for Outbound mTLS Origination
cat <<EOF > client-tls-policy.yaml
name: projects/${PROJECT_ID}/locations/${REGION}/clientTlsPolicies/hybrid-mtls-client-policy
clientCertificate:
  certificateProviderInstance:
    pluginInstance: projects/${PROJECT_ID}/locations/${REGION}/certificates/${CLIENT_CERT_NAME}
EOF
gcloud network-security client-tls-policies import "hybrid-mtls-client-policy" \
  --project="${PROJECT_ID}" --location="${REGION}" --source="client-tls-policy.yaml"
gcloud network-security backend-authentication-configs create "hybrid-mtls-auth-config" \
  --project="${PROJECT_ID}" --location="${REGION}" \
  --client-certificate="projects/${PROJECT_ID}/locations/${REGION}/certificates/${CLIENT_CERT_NAME}" \
  --trust-config="projects/${PROJECT_ID}/locations/${REGION}/trustConfigs/${TRUST_CONFIG_NAME}" \
  --well-known-roots="none"
gcloud compute backend-services create "hybrid-mtls-backend" \
  --project="${PROJECT_ID}" --region="${REGION}" \
  --load-balancing-scheme="INTERNAL_MANAGED" --protocol="HTTPS" --health-checks="${HC_NAME}" \
  --tls-settings="sni=${REMOTE_FQDN},authenticationConfig=//networksecurity.googleapis.com/projects/${PROJECT_ID}/locations/${REGION}/backendAuthenticationConfigs/hybrid-mtls-auth-config"
gcloud compute backend-services add-backend "hybrid-mtls-backend" \
  --project="${PROJECT_ID}" --region="${REGION}" \
  --network-endpoint-group="hybrid-mtls-neg" --network-endpoint-group-zone="${ZONE}" \
  --balancing-mode="RATE" --max-rate-per-endpoint=100
```
