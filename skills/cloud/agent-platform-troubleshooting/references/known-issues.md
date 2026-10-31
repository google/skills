# Best Known Issues (BKIs) and limitations

Concrete failure modes that come up repeatedly with the Agent Platform —
symptoms and fixes. Read this when the symptom in front of you matches one of
these patterns; it's faster than walking the full diagnostic flow.

## Table of Contents

-   [1. ReasoningEngine startup: project ID conversion](#1-reasoningengine-startup-failed-to-convert-project-number-to-project-id): Lines 50-72
-   [2. ReasoningEngine startup: Assembly Service init](#2-reasoningengine-startup-assembly-service-failed-to-initialize): Lines 73-85
-   [3. Reasoning Engine Gateway Sharing Constraints, Pre-April 29, 2026 Instances, & SCC Threat Detection](#3-reasoning-engine-gateway-sharing-constraints-pre-april-29-2026-instances--scc-threat-detection): Lines 86-115
-   [4. 403 / Egress not authorized — missing authz_policy or UAP binding](#4-403--egress-request-is-not-authorized--missing-authz_policy-or-uap-binding): Lines 116-150
-   [5. IAP ENFORCE / Blanket DENY blocks Agent Runtime startup](#5-iap-enforce-mode--blanket-deny-blocks-agent-runtime-startup): Lines 151-180
-   [6. Private CA & Self-Signed TLS Destinations (TrustConfig, PUBLICLY_TRUSTED_ROOTS, & ACT Rebind)](#6-private-ca--self-signed-tls-destinations-fail-handshake-missing-trustconfig-or-publicly_trusted_roots): Lines 181-233
-   [7. Principal Access Boundary (PAB) override](#7-principal-access-boundary-pab-policies-overriding-iam-allow): Lines 234-269
-   [8. Gateway proxy denies before IAP](#8-gateway-proxy-denies-the-request-before-iap-runs): Lines 270-320
-   [9. Cross-Project / VPC Agent Gateway & ACT Import Failures (PERMISSION_DENIED, INVALID_ARGUMENT, or Code 13)](#9-cross-project--vpc-agent-gateway--act-import-failures-permission_denied-invalid_argument-or-code-13): Lines 321-396
-   [10. Cross-Project Runtime-to-Gateway Binding Failures](#10-cross-project-runtime-to-gateway-binding-failures-permission_denied-invalid_argument-or-caa-token-suppression): Lines 397-609
-   [11. RE Container Crash: Dependency Mismatch](#11-reasoning-engine-container-crash-python-dependency-mismatch--startup-exceptions): Lines 610-632
-   [12. mTLS Egress Failure: Expired Cert](#12-mtls-egress-failure-invalid-or-expired-client-certificate): Lines 633-654
-   [13. Model Armor Integration Fails with 500, PERMISSION_DENIED, or 60s Stream Termination](#13-model-armor-integration-fails-with-500-permission_denied-or-60-second-stream-termination-stream-removed): Lines 655-721
-   [15. Egress Blocked: Empty Registry IAM Policy](#15-egress-blocked-empty-agent-registry-iam-policy-403-forbidden): Lines 722-758
-   [16. RE deployment fails with Code 13](#16-reasoning-engine-deployment-fails-with-code-13-internal-error): Lines 759-807
-   [17. RE outbound SSL handshake failure (Egress Gateway)](#17-reasoning-engine-outbound-ssl-handshake-failure-certificate_verify_failed-with-egress-agent-gateway): Lines 808-862
-   [18. VPC-SC Perimeter Blocks Provisioning](#18-vpc-service-controls-vpc-sc-perimeter-blocks-agent-gateway-provisioning): Lines 863-964
-   [19. PSC Subnet Exhaustion Fails Deployment](#19-psc-subnet-exhaustion-fails-agent-gateway-deployment): Lines 965-1013
-   [20. Config Validation Failure: Missing Agent Registry API / Caller Permissions](#20-config-validation-failure-missing-agent-registry-api-enablement): Lines 1014-1052
-   [21. Agent Identity Egress to Cloud Run/Funcs (JWT issue)](#21-agent-identity-egress-to-cloud-run--functions-fails-with-401403-jwt-auth-issue): Lines 1053-1104
-   [22. Cross-Project Agent Not Visible in Central Registry](#22-cross-project-agent-or-mcp-server-not-visible-in-central-governance-registry): Lines 1105-1130
-   [23. Telemetry Egress Blocked by Egress Gateway](#23-telemetry-egress-blocked-by-egress-agent-gateway-startup-failure): Lines 1131-1178
-   [24. UAP Org Policy Blocker (disableAccessPolicyBinding)](#24-uap-org-policy-blocker-constraintsiammanageddisableaccesspolicybinding): Lines 1179-1213
-   [25. UAP Policy Binding Destruction Race Condition](#25-uap-policy-binding-destruction-race-condition-400-failed_precondition): Lines 1214-1234
-   [26. Agent Gateway Multi-Registry & Jurisdiction Validation Errors](#26-agent-gateway-multi-registry--jurisdiction-validation-errors): Lines 1235-1262
-   [27. CEL Null Dereference Crash on Non-Tool MCP Methods](#27-cel-null-dereference-crash-on-non-tool-mcp-methods): Lines 1263-1282
-   [28. ACT ALL_TRAFFIC Silent Outbound Hang (Missing Cloud NAT)](#28-act-all_traffic-silent-outbound-hang-missing-cloud-nat): Lines 1283-1307
-   [29. Agent Gateway Control-Plane Mutation Concurrency Lock (HTTP 409 ABORTED)](#29-agent-gateway-control-plane-mutation-concurrency-lock-http-409-aborted): Lines 1308-1325
-   [30. ACT Deletion Fails with 400 FAILED_PRECONDITION (already being used)](#30-act-deletion-fails-with-400-failed_precondition-already-being-used): Lines 1326-1358
-   [31. Reasoning Engine Deletion Preconditions (Active Sessions)](#31-reasoning-engine-deletion-preconditions-active-sessions-require-forcetrue): Lines 1359-1374
-   [32. REST API Path Matching Gotcha (.json and Query Strings)](#32-rest-api-path-matching-gotcha-json-extensions-and-query-strings): Lines 1375-1398
-   [33. Secure Web Proxy (SWP) & Policy-Based Routing (PBR) Egress Failures](#33-secure-web-proxy-swp--policy-based-routing-pbr-egress-failures): Lines 1399-1474
-   [34. Explicit Forward HTTPS Proxy (HTTP CONNECT) Fails with HTTP 404 or 403](#34-explicit-forward-https-proxy-http-connect-fails-with-http-404-or-403-through-agent-gateway): Lines 1475-1557
-   [35. Cloud DNS Transitive Peering Chain Exceeded (>2 Hops) or Authoritative Root Zone (".")](#35-cloud-dns-transitive-peering-chain-exceeded-2-hops-or-authoritative-root-zone--causing-servfail--nxdomain): Lines 1558-1603
-   [36. Consumer VPC Packet Intercept (HTTP 503) & Workforce/Workload Identity Federation Limits](#36-consumer-vpc-packet-intercept-http-503--workforce--workload-identity-federation-code-13--403-limits): Lines 1604-1639
-   [37. Immediate HTTP 498 After Binding Agent Runtime, or Gemini Enterprise UpdateEngine Failures](#37-immediate-http-498-after-binding-agent-runtime-to-gateway-or-gemini-enterprise-regional-updateengine-failures): Lines 1640-1673
-   [38. Semantic Governance Policy (SGP) Failures](#38-semantic-governance-policy-sgp-failures-startup-grpc-crash-streaming-bypass-missing-agent-in-picker-or-metadata-overwrite): Lines 1674-1727
-   [39. Native MCP AuthzPolicy Blocks Session Handshake (MATCH_BASE_PROTOCOL_METHODS)](#39-native-mcp-authzpolicy-blocks-session-handshake-initialize--ping-due-to-missing-match_base_protocol_methods--extensionbinding-double-invocation): Lines 1728-1785

--------------------------------------------------------------------------------

## 1. ReasoningEngine startup: "Failed to convert project number to project ID"

**Symptom:**

-   Log name: `aiplatform.googleapis.com/reasoning_engine_stderr`
-   Error text: `google.api_core.exceptions.Unknown: None` or `Failed to convert
    project number to project ID.`
-   Happens during ReasoningEngine startup, before any user code runs.

**Cause:** The ReasoningEngine's system identity (the principal set it runs
under) lacks `resourcemanager.projects.get`, which the Agent Runtime SDK needs
to resolve the project name during init.

**Fix:** Grant `roles/browser` to the ReasoningEngine principal set:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="principalSet://agents.global.org-${ORG_ID}.system.id.goog/attribute.platformContainer/aiplatform/projects/${PROJECT_NUMBER}" \
  --role="roles/browser"
```

--------------------------------------------------------------------------------

## 2. ReasoningEngine startup: "Assembly Service failed to initialize"

**Symptom:** `[1099] ERROR: Assembly Service failed to initialize.` in
`reasoning_engine_stderr`.

**Cause:** Generic "init failed" — usually a downstream symptom of either #1
(project-number resolution) or a runtime error in the agent's `set_up()` method.

**Investigation:** Pull all `severity=ERROR` from `reasoning_engine_stderr`
around the same timestamp; the actual root cause is in the same window.

--------------------------------------------------------------------------------

## 3. Reasoning Engine Gateway Sharing Constraints, Pre-April 29, 2026 Instances, & SCC Threat Detection

**Symptom:** Binding or updating a Reasoning Engine (Agent Runtime) to use an
Agent Gateway fails with `INVALID_ARGUMENT`, `FAILED_PRECONDITION`, or `Internal
error encountered` (`Code 13`).

**Causes & Platform Limits:**

1.  **Shared Gateway Per `(project, region)` Invariant**: Multiple Reasoning
    Engines in the same project and region **can** share an Agent Gateway,
    provided **every** bound Reasoning Engine in that `(project, region)` binds
    to the **exact same** egress and/or ingress gateway instance. Attempting to
    bind a second engine in the same region to a *different* gateway (`gateway-B`
    while `gateway-A` is active) fails.
2.  **Creation Date Cutoff (April 29, 2026)**: Reasoning Engines created before
    April 29, 2026 cannot be updated in-place to bind to an Agent Gateway and
    must be redeployed as new instances.
3.  **SCC Agent Engine Threat Detection Conflict**: Agent Gateway binding is
    incompatible with Security Command Center (SCC) Agent Engine Threat
    Detection in the same project.
4.  **Revision Traffic Requirement**: Updating `agent_gateway_config` on an
    existing Reasoning Engine requires 100% of traffic on the latest revision
    and archives prior revisions.

**Fix:** Bind all Reasoning Engines in a given `(project, region)` to the same
Agent Gateway, redeploy any pre-April 29, 2026 engines, and disable SCC Agent
Engine Threat Detection before attaching an Agent Gateway.

--------------------------------------------------------------------------------

## 4. 403 / "Egress request is not authorized" — missing `authz_policy` or UAP binding

**Symptom:** Audit logs show `GatekeeperAuthorizer.AuthorizeUser` returning
`Permission Denied` for `iap.webServiceVersions.egressViaIAP` or
`iap.googleapis.com/resources.egressViaIAP`.

**Cause:**

1.  **Missing AuthzPolicy Attachment**: The IAP authz extension exists, but no
    `authz_policy` targets the specific Agent Gateway (`target.resources[]`).
2.  **Missing or Misconfigured UAP Binding (Policy V2)**: When the gateway uses
    `iapPolicyVersion: "V2"`, no `PolicyBinding` binds an `AccessPolicy` to the
    target CRM node
    (`//cloudresourcemanager.googleapis.com/projects/${PROJECT_NUMBER}`), or the
    target resource was specified using the string project ID instead of the
    numeric project number.

**Fix:**

1.  Verify the `authz_policy` targets the gateway:

    ```bash
    gcloud network-security authz-policies list --location=${LOCATION}
    ```
2.  If using UAP, verify the policy binding targets the numeric project number:

    ```bash
    gcloud iam policy-bindings search-target-policy-bindings \
      --target="//cloudresourcemanager.googleapis.com/projects/${PROJECT_NUMBER}" \
      --project="${PROJECT_ID}" \
      --location=global
    ```

--------------------------------------------------------------------------------

## 5. IAP `ENFORCE` mode / Blanket DENY blocks Agent Runtime startup

**Symptom:** Agent Runtime instances fail to deploy or start, with 403s or
connection resets in startup logs (`reasoning_engine_stderr`).

**Cause:**

1.  **Default-Deny without Bootstrap Endpoints**: With IAP in `ENFORCE` mode on
    the Agent Gateway, all egress is denied by default — including bootstrap
    calls the agent runtime makes to `telemetry.mtls.googleapis.com`,
    `cloudresourcemanager`, `aiplatform`, `logging`, `monitoring`, etc.
2.  **Blanket Unregistered DENY in UAP**: An Org or Folder Admin created an
    explicit `effect: DENY` rule on `(destination.is_registered == false)`.
    Because DENY has absolute precedence and cannot be overridden by
    project-level rules, Reasoning Engine boot traffic to
    `telemetry.mtls.googleapis.com` is dropped immediately.

**Fix:**

-   Ensure all required monitoring/telemetry endpoints
    (`telemetry.mtls.googleapis.com`, `monitoring.googleapis.com`,
    `trace.mtls.googleapis.com`, `cloudtrace.googleapis.com`) are registered in
    the Agent Registry and permitted by policy.
-   **Never create a blanket DENY on `destination.is_registered == false`**.
    Rely on gateway default-deny instead.
-   Set IAP to `DRY_RUN` (`iamEnforcementMode: "DRY_RUN"`) to observe failing
    destinations without blocking container initialization.

--------------------------------------------------------------------------------

## 6. Private CA & Self-Signed TLS Destinations Fail Handshake (Missing `TrustConfig` or `PUBLICLY_TRUSTED_ROOTS`)

**Symptom:**

-   **Symptom A**: Outbound calls through Agent Gateway to internal MCP servers
    or private endpoints using Private CA or self-signed certificates fail TLS
    handshake verification.
-   **Symptom B**: After attaching a Certificate Manager `TrustConfig` to an
    Agent Connectivity Template (ACT), private endpoints succeed, **but all
    calls to `*.googleapis.com` and public HTTPS APIs suddenly fail TLS
    verification**.
-   **Symptom C**: Updating `tlsConfig` in-place on an existing ACT fails with
    an immutability error or does not take effect on the running gateway.

**Cause:**

1.  Private CA roots (via `trustStores`) or self-signed leaf certificates (via
    `allowlistedCertificates`) must be configured in a Certificate Manager
    `TrustConfig` in the **same project and region** and attached to
    `egressNetworkConfig.tlsConfig.trustConfig` on the ACT.
2.  When `trustConfig` is set without `additionalRoots: PUBLICLY_TRUSTED_ROOTS`,
    `additionalRoots` defaults to `NO_ADDITIONAL_ROOTS`, stripping Mozilla/Google
    public root CAs from the gateway proxy's trust store.
3.  `egressNetworkConfig.tlsConfig.trustConfig` is **immutable** on an existing
    ACT resource.

**Fix:**

1.  Create a regional Certificate Manager `TrustConfig` (`trustStores` for
    Private CA chains or `allowlistedCertificates` for self-signed leaf certs;
    target certs must contain a valid SAN).
2.  Create a **new** ACT (`act-v2.yaml`) referencing the `TrustConfig` **and**
    explicitly setting `additionalRoots: PUBLICLY_TRUSTED_ROOTS`:

    ```yaml
    name: projects/PROJECT_ID/locations/REGION/agentConnectivityTemplates/agw-act-v2
    accessPath: AGENT_TO_ANYWHERE
    deploymentModel: CENTRALIZED
    egressNetworkConfig:
      networkAttachment: projects/PROJECT_ID/regions/REGION/networkAttachments/agw-na
      vpcEgress: ALL_TRAFFIC
      tlsConfig:
        trustConfig: projects/PROJECT_NUMBER/locations/REGION/trustConfigs/private-ca-trust
        additionalRoots: PUBLICLY_TRUSTED_ROOTS
    ```

3.  Import the new ACT (`gcloud network-services agent-connectivity-templates
    import agw-act-v2 --source=act-v2.yaml --location=REGION`) and rebind the
    Agent Gateway (`agentConnectivityTemplate: .../agentConnectivityTemplates/agw-act-v2`)
    via `gcloud network-services agent-gateways import`.

--------------------------------------------------------------------------------

## 7. Principal Access Boundary (PAB) policies overriding IAM Allow

**Symptom:** Agent identity has the right egress permissions bound
(`roles/iap.egressor` under Policy V1 or `iap.googleapis.com/resources.egressViaIAP`
under UAP Policy V2) and the destination is registered, but calls still return `403`.

**Cause:** A Principal Access Boundary policy is restricting the scope of
resources the principal can access. **PAB policies take precedence over IAM
Allow and UAP policies** — even a valid egress grant does nothing if a PAB
blocks the target resource.

**Investigation:** List PAB policies and inspect policy bindings attached to the
target project resource (`--location=global` and a full CRM resource URI are
required):

```bash
# List org-wide PAB policies
gcloud iam principal-access-boundary-policies list \
  --organization="${ORGANIZATION_ID}" --location=global

# Inspect policy bindings attached to the project resource
gcloud iam policy-bindings search-target-policy-bindings \
  --location=global \
  --project="${PROJECT_ID}" \
  --target="//cloudresourcemanager.googleapis.com/projects/${PROJECT_NUMBER}"

# Inspect a specific PAB
gcloud iam principal-access-boundary-policies search-policy-bindings "${PAB_POLICY_ID}" \
  --organization="${ORGANIZATION_ID}" --location=global
```

**Fix:** Either widen the PAB to include the destination resource, or remove the
PAB binding from the agent's principal set if it shouldn't apply.

--------------------------------------------------------------------------------

## 8. Gateway proxy denies the request before IAP runs

**Symptom:** Requests fail with no IAP audit log entry — IAP never saw them.

**Cause:** The gateway's underlying egress proxy (a Google-managed Secure Web
Proxy instance) enforces a deny-by-default posture *before* IAP authz runs. When
the proxy itself denies a call, IAP doesn't get a chance to evaluate, so no IAP
audit-log entry is produced for that call.

**Specific Case: CONNECT to PSC VIP (`240.0.0.2:443`) with Default Denied** In
environments using Private Service Connect (PSC), clients resolve Google APIs to
internal VIPs (e.g., `240.0.0.2:443`). Consequently, the outer tunnel request is
logged as `CONNECT 240.0.0.2:443` in the proxy logs. **This is expected
behavior.** Because TLS inspection is enabled on the Secure Web Proxy (SWP), the
proxy intercepts this CONNECT tunnel and inspects the TLS handshake to extract
the actual SNI hostname (e.g., `us-central1-aiplatform.googleapis.com`) for
routing and policy evaluation. If the extracted SNI hostname is **not**
registered in the Agent Registry, the proxy cannot match the route. The proxy
then denies the connection, logging a `403` on the `CONNECT` request with
`hostname: 240.0.0.2:443` and matching the `default_denied` rule.

**Investigation:** Pull the gateway proxy load-balancer logs:

```
jsonPayload.@type="type.googleapis.com/google.cloud.loadbalancing.type.LoadBalancerLogEntry"
resource.labels.gateway_type="SECURE_WEB_GATEWAY"
```

**Alternative (CLI Fallback):**

```bash
gcloud logging read 'jsonPayload.@type="type.googleapis.com/google.cloud.loadbalancing.type.LoadBalancerLogEntry" AND resource.labels.gateway_type="SECURE_WEB_GATEWAY"' --project=PROJECT_ID --limit=50
```

Key fields to inspect in the match:

-   `httpRequest.status`: Look for `403`.
-   `jsonPayload.enforcedGatewaySecurityPolicy.hostname`: Look for
    `240.0.0.2:443` (expected PSC CONNECT target).
-   `jsonPayload.enforcedGatewaySecurityPolicy.matchedRules`: Look for
    `default_denied`.
-   `jsonPayload.mtls.clientCertChainVerified`: Often `false` because the
    handshake was interrupted on route match failure.

**Fix:** Identify the inner hostname the agent was attempting to reach (e.g.
`us-central1-aiplatform.googleapis.com`) and ensure ALL required hostname
permutations are registered in the Agent Registry. The proxy relies on these
registry entries to dynamically build its routing table.

--------------------------------------------------------------------------------

## 9. Cross-Project / VPC Agent Gateway & ACT Import Failures (`PERMISSION_DENIED`, `INVALID_ARGUMENT`, or `Code 13`)

**Symptom:**

-   During `gcloud network-services agent-connectivity-templates import` or
    `gcloud network-services agent-gateways import`, the command fails with:
    -   Structured preflight `PERMISSION_DENIED` or `INVALID_ARGUMENT` naming
        either **the caller** or **`service-GATEWAY_PROJECT_NUMBER@gcp-sa-agentgateway.iam.gserviceaccount.com`**, OR
    -   Synchronous `{"code": 13, "message": "an internal error has occurred"}`
        on unexpected downstream actuation failures.

**Cause:**

1.  **Dual-Principal Validation**: Cross-project Network Attachment and Cloud DNS
    peering validation checks **both** the caller identity (EUC / CI pipeline)
    **and** the Agent Gateway Control Plane Service Agent
    (`service-GATEWAY_PROJECT_NUMBER@gcp-sa-agentgateway.iam.gserviceaccount.com`).
2.  **Malformed `NetworkAttachment` URI**: Using `/locations/REGION/` instead of
    `/regions/REGION/` fails validation with `invalid network attachment URI`.
3.  **DNS `targetNetwork` & Zone Rules**: Every entry in `dnsPeeringConfig.domains[]`
    must end with a trailing dot (e.g., `corp.internal.`). Progressive regional
    rollout supports decoupling `dnsPeeringConfig.targetNetwork` from the
    `NetworkAttachment` VPC (pointing directly at a DNS Hub VPC); in regions not
    yet enabled, `targetNetwork` must match the `NetworkAttachment` VPC (with at
    most 1 customer Cloud DNS Peering Zone hop to the Hub VPC — see BKI #35).

**Fix:**

1.  **Grant Caller / Provisioning Permissions on the Host Network/DNS Project**:
    Grant `roles/compute.networkViewer`, `roles/dns.reader`,
    `roles/networkconnectivity.regionalEndpointAdmin`, and
    `roles/networkconnectivity.consumerNetworkAdmin` (or `roles/viewer`), plus
    `compute.networkAttachments.use` (`roles/compute.networkUser`) if the
    `NetworkAttachment` resides in the host project:

    ```bash
    gcloud projects add-iam-policy-binding TARGET_NETWORK_PROJECT_ID \
      --member="user:OPERATOR_EMAIL" \
      --role="roles/compute.networkViewer"

    gcloud projects add-iam-policy-binding TARGET_NETWORK_PROJECT_ID \
      --member="user:OPERATOR_EMAIL" \
      --role="roles/dns.reader"
    ```

2.  **Grant Agent Gateway Service Agent Permissions on the Host Network/DNS Project**
    (ensure `dns.googleapis.com` is enabled):

    ```bash
    # Grant roles/compute.networkUser (if NA is in service project, recommended)
    # or roles/compute.networkAdmin (if NA is in host project) + networkViewer:
    gcloud projects add-iam-policy-binding TARGET_NETWORK_PROJECT_ID \
      --member="serviceAccount:service-GATEWAY_PROJECT_NUMBER@gcp-sa-agentgateway.iam.gserviceaccount.com" \
      --role="roles/compute.networkUser"

    gcloud projects add-iam-policy-binding TARGET_NETWORK_PROJECT_ID \
      --member="serviceAccount:service-GATEWAY_PROJECT_NUMBER@gcp-sa-agentgateway.iam.gserviceaccount.com" \
      --role="roles/compute.networkViewer"

    # Grant DNS peer + reader on the target DNS project:
    gcloud projects add-iam-policy-binding TARGET_DNS_PROJECT_ID \
      --member="serviceAccount:service-GATEWAY_PROJECT_NUMBER@gcp-sa-agentgateway.iam.gserviceaccount.com" \
      --role="roles/dns.peer"

    gcloud projects add-iam-policy-binding TARGET_DNS_PROJECT_ID \
      --member="serviceAccount:service-GATEWAY_PROJECT_NUMBER@gcp-sa-agentgateway.iam.gserviceaccount.com" \
      --role="roles/dns.reader"
    ```

3.  Verify `connectionPreference: ACCEPT_AUTOMATIC` (or explicit project
    acceptance) on `projects/PROJECT_ID/regions/REGION/networkAttachments/NAME`,
    and verify `service-GATEWAY_PROJECT_NUMBER@gcp-sa-dep.iam.gserviceaccount.com`
    holds `roles/compute.networkUser` on the consumer PSC-I subnet.

--------------------------------------------------------------------------------

## 10. Cross-Project Runtime-to-Gateway Binding Failures: PERMISSION_DENIED, INVALID_ARGUMENT, or CAA Token Suppression

**Symptom:**

-   **Symptom A (Deployer PERMISSION_DENIED):** Calling Vertex AI
    `client.agent_engines.create(...)` or REST API in Project 1
    (`AE_PROJECT_ID`) referencing an Agent Gateway in Project 2
    (`AGW_PROJECT_ID`) fails synchronously with: `ERROR:
    (gcloud.ai.reasoning-engines.create) PERMISSION_DENIED: Permission
    'networkservices.agentGateways.use' denied on resource
    '//networkservices.googleapis.com/projects/AGW_PROJECT_ID/locations/REGION/agentGateways/GATEWAY_NAME'`
-   **Symptom B (Control-Plane INVALID_ARGUMENT):** Deployment fails with:
    `INVALID_ARGUMENT: Agent Gateway project in
    spec.deployment_spec.agent_gateway_config.agent_to_anywhere_config.agent_gateway
    must match the Vertex AI project.` or region mismatch `INVALID_ARGUMENT:
    Agent Gateway location in spec... must match the Vertex AI location.`
-   **Symptom C (CAA 401 Unauthenticated Egress):** Runtime container deploys
    successfully, but egress requests to external endpoints or MCP tools fail
    immediately with: `Error Code: "401", Error Details: "Context-Aware Access
    requirements are not met"` or `Request had invalid authentication
    credentials.`
-   **Symptom D (Proxy 403 PERMISSION_DENIED on MCP Tool / Service Name):**
    Egress through the gateway fails with HTTP 403 `PERMISSION_DENIED`, even
    though `roles/iap.egressor` was granted to the friendly service name in
    Agent Registry.
-   **Symptom E (Unsupported Folder-Level principalSet):** Policy binding using
    `principalSet://TRUST_DOMAIN/attribute.platformContainer/aiplatform/folders/FOLDER_NUMBER`
    fails silently or is rejected as an invalid principal identifier.
-   **Symptom F (VPC-SC Perimeter Block):** Egress calls fail with
    `VPC_SERVICE_CONTROLS_VIOLATION` across project boundaries.

**Cause:**

1.  **Regional Colocation & Shared-Gateway Invariants:** Cross-project binding
    (`spec.deploymentSpec.agentGatewayConfig.agentToAnywhereConfig.agentGateway`)
    is supported across Google Cloud projects, provided **both the runtime and
    the gateway reside in the exact same Google Cloud region** (e.g.,
    `us-central1`). Cross-region bindings are rejected with `INVALID_ARGUMENT`,
    and all bound runtimes in a given `(project, region)` must share the same
    gateway instance.
2.  **Missing Deployer and Service Agent IAM Permissions:**
    -   The **deploying principal** (user EUC, Cloud Build SA, or pipeline
        identity) must have `networkservices.agentGateways.use` and
        `networkservices.agentGateways.get` on the gateway in `AGW_PROJECT_ID`.
    -   The runtime project's **Vertex AI Service Agent**
        (`service-AE_PROJECT_NUMBER@gcp-sa-aiplatform.iam.gserviceaccount.com`)
        must hold `roles/networkservices.viewer` (or custom role
        `ae_agw_cross_project_sa` — also documented as `ar_agw_cross_project_sa`
        — with `networkservices.agentGateways.get` and
        `networkservices.operations.get`) on `AGW_PROJECT_ID`.
3.  **Context-Aware Access (CAA) Token Suppression:** By default, Google Cloud
    SDKs and `google-auth` enforce bound token protection. In cross-project
    egress, bound token requirements reject requests unless the runtime
    explicitly sets the environment variable
    `GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES: False`.
4.  **Friendly Service Name vs. Server-Generated Resource ID Trap:** In Agent
    Registry, services, endpoints, and mcp-servers are written via `gcloud
    agent-registry services create`. However, IAP authorization (`gcloud iap web
    add-iam-policy-binding`) must bind to the **server-generated resource ID**
    (`agentregistry-00000000-...`, extracted from the `registryResource` field),
    NOT the friendly service name (`[MCP_SERVICE_NAME]`). Binding to the
    friendly service name attaches the policy to a non-existent IAP resource.
5.  **SPIFFE principalSet Syntax Limitation:**
    `attribute.platformContainer/aiplatform/folders/FOLDER_NUMBER` is **not** an
    indexed attribute in IAM SPIFFE URI evaluation. Scoping must strictly use
    project-level syntax
    (`attribute.platformContainer/aiplatform/projects/PROJECT_NUMBER`) or
    trust-domain-wide syntax (`principalSet://TRUST_DOMAIN/*`), or use Principal
    Access Boundary (PAB) policies.
6.  **VPC Service Controls Perimeter Boundary:** If Project 1 (`AE_PROJECT_ID`)
    and Project 2 (`AGW_PROJECT_ID`) reside in different perimeters, perimeter
    bridging or bidirectional ingress/egress rules covering
    `aiplatform.googleapis.com`, `networkservices.googleapis.com`, and
    `agentregistry.googleapis.com` are required.

**Investigation:**

1.  **Check Deployer Permissions on Gateway:**

    ```bash
    gcloud network-services agent-gateways describe GATEWAY_NAME \
      --project=AGW_PROJECT_ID \
      --location=REGION
    ```

    If this fails with `PERMISSION_DENIED`, the deployer lacks read/use
    permissions.
2.  **Check Vertex AI Service Agent IAM on Gateway Project:**

    ```bash
    gcloud projects get-iam-policy AGW_PROJECT_ID \
      --flatten="bindings[].members" \
      --filter="bindings.members:service-AE_PROJECT_NUMBER@gcp-sa-aiplatform.iam.gserviceaccount.com" \
      --format="table(bindings.role)"
    ```

    Verify that `roles/networkservices.viewer` or custom role
    `ae_agw_cross_project_sa` is present.
3.  **Verify Runtime Region vs. Gateway Region:** Ensure both the Reasoning
    Engine runtime and the Agent Gateway are deployed in the same region.
4.  **Inspect Runtime CAA Environment Variable:** Inspect the Reasoning Engine
    deployment spec or Python definition. Verify that `env_vars` contains
    `"GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES": False`.
5.  **Verify IAP Binding Target Resource ID:**

    ```bash
    # Fetch the server-generated registryResource identifier
    gcloud agent-registry services describe MCP_SERVICE_NAME \
      --project=AGW_PROJECT_ID \
      --location=REGION \
      --format='value(registryResource)'
    ```

    Confirm that `gcloud iap web add-iam-policy-binding` used the trailing UUID
    (`agentregistry-00000000-...`) as `--mcp-server` or `--agent`, not the
    friendly name.
6.  **Check VPC-SC Status:** Confirm whether `AE_PROJECT_ID` and
    `AGW_PROJECT_ID` reside in the same VPC-SC perimeter or have perimeter
    ingress/egress rules allowing communication.

**Fix:**

1.  **Grant Deployer Permissions:** Grant `roles/networkservices.viewer` (or
    permissions `networkservices.agentGateways.use` and
    `networkservices.agentGateways.get`) to the deploying identity on
    `AGW_PROJECT_ID`:

    ```bash
    gcloud projects add-iam-policy-binding AGW_PROJECT_ID \
      --member="user:DEPLOYER_EMAIL" \
      --role="roles/networkservices.viewer"
    ```
2.  **Grant Vertex AI Service Agent Permissions:** Grant the Agent Runtime's
    service agent access to the governance project: *Option A (Standard Viewer
    Role):*

    ```bash
    gcloud projects add-iam-policy-binding AGW_PROJECT_ID \
      --member="serviceAccount:service-AE_PROJECT_NUMBER@gcp-sa-aiplatform.iam.gserviceaccount.com" \
      --role="roles/networkservices.viewer"
    ```

    *Option B (Least-Privilege Custom Role):*

    ```bash
    gcloud iam roles create ae_agw_cross_project_sa \
      --project="AGW_PROJECT_ID" \
      --title="AE AGW Cross Project SA" \
      --description="Custom role for cross-project service agent to access Agent Gateways and Operations" \
      --permissions="networkservices.agentGateways.get,networkservices.operations.get" \
      --stage="GA"

    gcloud projects add-iam-policy-binding AGW_PROJECT_ID \
      --member="serviceAccount:service-AE_PROJECT_NUMBER@gcp-sa-aiplatform.iam.gserviceaccount.com" \
      --role="projects/AGW_PROJECT_ID/roles/ae_agw_cross_project_sa"
    ```
3.  **Configure Runtime with CAA Opt-Out:** In the agent runtime deployment
    configuration:

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
                "GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES": (
                    False
                ),
            },
        },
    )
    ```
4.  **Bind IAP Role to the Server-Generated Resource ID:**

    ```bash
    REGISTRY_RESOURCE=$(gcloud agent-registry services describe MCP_SERVICE_NAME \
      --project=AGW_PROJECT_ID \
      --location=REGION \
      --format='value(registryResource)')
    RESOURCE_ID=$(basename "$REGISTRY_RESOURCE")

    AGENT_PRINCIPAL="principal://agents.global.org-ORG_ID.system.id.goog/resources/aiplatform/projects/AE_PROJECT_NUMBER/locations/REGION/reasoningEngines/ENGINE_ID"

    gcloud iap web add-iam-policy-binding \
      --project=AGW_PROJECT_ID \
      --region=REGION \
      --resource-type=agent-registry \
      --mcp-server="${RESOURCE_ID}" \
      --member="$AGENT_PRINCIPAL" \
      --role="roles/iap.egressor"
    ```
5.  **Use Valid principalSet Syntax:** For baseline Google APIs access, avoid
    folder-level scoping. Use project-level scoping:

    ```
    principalSet://agents.global.org-ORG_ID.system.id.goog/attribute.platformContainer/aiplatform/projects/AE_PROJECT_NUMBER
    ```

    or trust-domain-wide scoping:

    ```
    principalSet://agents.global.org-ORG_ID.system.id.goog/*
    ```

--------------------------------------------------------------------------------

## 11. Reasoning Engine Container Crash: Python Dependency Mismatch / Startup Exceptions

**Symptom:**

-   Log name: `aiplatform.googleapis.com/reasoning_engine_stderr`
-   Error text: `ModuleNotFoundError: No module named '...'` or `ImportError:
    cannot import name '...'` or Python tracebacks.
-   The Reasoning Engine fails to deploy or dies immediately after creation.

**Cause:** The Python code uploaded for the Reasoning Engine depends on external
packages that were not specified or incorrectly specified during deployment.

**Fix:**

1.  Identify the missing or mismatched package from the traceback in
    `reasoning_engine_stderr`.
2.  Update your `requirements.txt` file or the `requirements` parameter in your
    deployment script (e.g. `deploy_agent.py`) to include the correct package
    and version constraint.
3.  Re-deploy the Reasoning Engine.

--------------------------------------------------------------------------------

## 12. mTLS Egress Failure: Invalid or Expired Client Certificate

**Symptom:**

-   Gateway proxy load-balancer logs show connection drops or `403` errors.
-   Logs contain `jsonPayload.mtls.clientCertChainVerified: false` or handshake
    failures.
-   The agent fails to reach the destination MCP server when using mTLS.

**Cause:** The client certificate used by the Agent Gateway is expired, not yet
valid, or not trusted by the destination server (CA mismatch).

**Fix:**

1.  Verify the certificate validity dates and CA chain.
2.  If expired or invalid, upload a new certificate to Certificate Manager and
    update the corresponding `ClientTlsPolicy` resource.
3.  Ensure the destination server trusts the CA that signed the gateway's client
    certificate.

--------------------------------------------------------------------------------

## 13. Model Armor Integration Fails with 500, `PERMISSION_DENIED`, or 60-Second Stream Termination (`Stream removed`)

**Symptom:**

-   **Symptom A (`PERMISSION_DENIED`)**: Calling the agent returns `500 Internal
    Server Error`; gateway logs show `grpcStatus: "PERMISSION_DENIED"` on
    `modelarmor.*` and `authzPolicyInfo.result: DENIED`.
-   **Symptom B (`Stream removed` at 60 Seconds)**: Long-running streaming
    responses or outbound HTTP/2 gRPC channels cut off right at **60 seconds**
    with HTTP `500`/`504` or gRPC `UNKNOWN: Stream removed`.

**How to Identify:**

```text
resource.type="networkservices.googleapis.com/Gateway"
jsonPayload.serviceExtensionInfo.backendTargetName : "modelarmor"
jsonPayload.serviceExtensionInfo.backendTargetType="BACKEND_SERVICE"
```

**Cause:**

1.  **Distinct Ingress vs. Egress Service Agents**:
    -   **Agent-to-Anywhere (Egress, max 4 `CONTENT_AUTHZ` policies)** executes
        callouts under the **Service Extensions Service Agent**:
        `service-GATEWAY_PROJECT_NUMBER@gcp-sa-dep.iam.gserviceaccount.com`.
    -   **Client-to-Agent (Ingress, max 1 `CONTENT_AUTHZ` policy, sanitizes ADK
        `streamQuery` only)** executes callouts under the **AI Platform Reasoning
        Engine Service Agent**:
        `service-AGENT_PROJECT_NUMBER@gcp-sa-aiplatform-re.iam.gserviceaccount.com`.
    > **Warning:** Basic `roles/owner` or `roles/editor` grants do **not** satisfy Model Armor data-plane callout checks.
2.  **Non-Configurable 60-Second Stream Deadline**: Envoy enforces a hard
    **60-second total stream lifetime** on `CONTENT_AUTHZ` callouts (independent
    of per-callout `AuthzExtension.timeout` `1s–10s`), and file/PDF sanitization
    is unsupported in gateway integration.

**Fix:**

1.  **For Agent-to-Anywhere (Egress)**: Grant `roles/modelarmor.calloutUser` and
    `roles/serviceusage.serviceUsageConsumer` on the **gateway project**, plus
    `roles/modelarmor.user` on the **Model Armor template project**, to
    `service-GATEWAY_PROJECT_NUMBER@gcp-sa-dep.iam.gserviceaccount.com`:

    ```bash
    gcloud projects add-iam-policy-binding GATEWAY_PROJECT_ID \
        --member="serviceAccount:service-GATEWAY_PROJECT_NUMBER@gcp-sa-dep.iam.gserviceaccount.com" \
        --role="roles/modelarmor.calloutUser"

    gcloud projects add-iam-policy-binding GATEWAY_PROJECT_ID \
        --member="serviceAccount:service-GATEWAY_PROJECT_NUMBER@gcp-sa-dep.iam.gserviceaccount.com" \
        --role="roles/serviceusage.serviceUsageConsumer"

    gcloud projects add-iam-policy-binding TEMPLATE_PROJECT_ID \
        --member="serviceAccount:service-GATEWAY_PROJECT_NUMBER@gcp-sa-dep.iam.gserviceaccount.com" \
        --role="roles/modelarmor.user"
    ```

2.  **For Client-to-Agent (Ingress)**: Grant `roles/modelarmor.calloutUser` on
    the **agent runtime project** and `roles/modelarmor.user` on the **template
    project** to
    `service-AGENT_PROJECT_NUMBER@gcp-sa-aiplatform-re.iam.gserviceaccount.com`.
3.  **Scope `AuthzPolicy.httpRules` to Exclude Long-Lived Streams & gRPC**:
    Restrict `CONTENT_AUTHZ` `httpRules` (e.g., `!request.headers['content-type'].startsWith('application/grpc')`
    and targeted non-streaming tool/model hosts) so `>60s` streams bypass inline
    `CONTENT_AUTHZ` buffering.

--------------------------------------------------------------------------------

## 15. Egress Blocked: Empty Agent Registry IAM Policy (403 Forbidden)

**Symptom:** All egress attempts through the gateway fail with a `403 Permission
Denied` (logged as `Egress request is not authorized`).

**Cause:** The IAM policy on the `agent-registry` resource in the consumer
project is empty or lacks bindings for the agent. The agent's service account
must be explicitly granted the `roles/iap.egressor` role.

**Fix:** Grant the `roles/iap.egressor` role to the agent's service account at
the registry level.

1.  Create a `policy.json` file:

    ```json
    {
      "bindings": [
        {
          "role": "roles/iap.egressor",
          "members": [
            "serviceAccount:YOUR_AGENT_SERVICE_ACCOUNT_EMAIL"
          ]
        }
      ]
    }
    ```

2.  Apply the policy to the Agent Registry:

    ```bash
    gcloud iap web set-iam-policy policy.json \
        --resource-type=agent-registry \
        --project=YOUR_PROJECT_ID
    ```

--------------------------------------------------------------------------------

## 16. Reasoning Engine deployment fails with Code 13 (Internal Error)

**Symptom:**

-   Agent Runtime deployment fails with generic Code 13: `Failed to deploy to
    Agent Platform: Failed to update Agent Runtime: {'code': 13, 'message':
    'Please refer to our troubleshooting pages...'}`.
-   The instance is immediately cleaned up.

### Root Cause A: Conflicting Second Gateway in Shared Tenant Project (`gateway-A` vs. `gateway-B`)

-   **Underlying Cause:** Agent Runtime allocates one shared tenant project per
    customer `(project, region)`. Multiple Reasoning Engines in that `(project,
    region)` **can** share the same `gateway-A`, **but** attempting to bind a
    Reasoning Engine to a *different* gateway (`gateway-B`) while `gateway-A` is
    active fails due to wildcard route conflict (also triggered on pre-April 29,
    2026 engines or projects with SCC Agent Engine Threat Detection enabled — see
    BKI #3).
-   **Fix:** Reuse the existing `gateway-A` across all Reasoning Engines in that
    `(project, region)`, or migrate cleanly:

    1.  Delete any active Reasoning Engines in the region bonded to the old
        gateway.

        ```bash
        curl -X DELETE -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" "https://${LOCATION}-aiplatform.googleapis.com/v1/projects/${PROJECT_ID}/locations/${LOCATION}/reasoningEngines/${REASONING_ENGINE_ID}?force=true"
        ```

    2.  If the old Reasoning Engines are already deleted but routes are stuck,
        delete the old gateway resource to force cleanup:

        ```bash
        gcloud network-services agent-gateways delete OLD_GATEWAY_NAME --location=LOCATION --project=PROJECT_ID
        ```

    3.  Retry deployment bonded to the new gateway.

### Root Cause B: Container Startup Timeout or Initialization Failure

-   **Underlying Cause:** The container fails to complete initialization within
    the startup timeout limit (due to syntax errors, missing dependencies, slow
    network calls, or permission denials).
-   **Fix:**
    1.  Verify the container can start locally.
    2.  Check Cloud Logging at the time of deployment for Python tracebacks.
    3.  De-risk initialization code by lazy loading heavy dependencies.

--------------------------------------------------------------------------------

## 17. Reasoning Engine outbound SSL handshake failure (CERTIFICATE_VERIFY_FAILED) with Egress Agent Gateway

**Symptom:**

-   Log show: `CERTIFICATE_VERIFY_FAILED: self signed certificate in certificate
    chain`
-   Occurs when a Reasoning Engine makes outbound calls while bound to an Egress
    Agent Gateway with `AGENT_IDENTITY` enabled.

**Cause:** When outgoing connections pass through Secure Web Proxy (SWG) on the
Agent Gateway, SWG performs TLS decryption and inspection using a dynamic
certificate signed by its custom root CA. If the Reasoning Engine trust store
does not contain these root certificates, outbound handshakes fail.

For custom container or prebuilt image deployments, the automated trust
certificate injection is skipped, so the gateway's root certificates are not
baked into the container.

**Fix / Workaround:**

-   **For Source/Config-based Deployments (Agent Runtime SDK):** Create the
    Agent Gateway first and wait until provisioning completes. Verify root
    certificates are ready:

    ```bash
    gcloud network-services agent-gateways describe GATEWAY_NAME \
        --location=LOCATION \
        --format="value(agentGatewayCard.rootCertificates)"
    ```

    Once this returns PEM certificates, deploy/update the Reasoning Engine. The
    pipeline will automatically bake them in.

-   **For Custom Container / Prebuilt Image Deployments:** Extract the gateway's
    PEM root certificates using `gcloud network-services agent-gateways describe`
    (note: `gcloud network-services` has **no** `export-cacerts` subcommand) and bake them into your container image:

    ```bash
    gcloud network-services agent-gateways describe GATEWAY_NAME \
        --location=LOCATION \
        --project=PROJECT_ID \
        --format="value[delimiter=\n](agentGatewayCard.rootCertificates)" > agw_root.crt
    ```

    ```dockerfile
    COPY agw_root.crt /usr/local/share/ca-certificates/agw-gateway.crt
    RUN chmod 644 /usr/local/share/ca-certificates/agw-gateway.crt && update-ca-certificates
    ENV GRPC_DEFAULT_SSL_ROOTS_FILE_PATH=/etc/ssl/certs/ca-certificates.crt
    ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
    ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
    ENV AGENT_GATEWAY_ROOT_CERT_302034098528=/etc/ssl/certs/ca-certificates.crt
    ```

--------------------------------------------------------------------------------

## 18. VPC Service Controls (VPC-SC) Perimeter Blocks Agent Gateway Provisioning

> **Note:** **Native VPC-SC Creation Support:** As of September 8, 2026, Agent
> Gateway creation inside a VPC-SC perimeter **works natively out of the box**
> without requiring manual control-plane ingress policies, provided the Agent
> Connectivity Template (ACT) specifies `vpcEgress: ALL_TRAFFIC` and consumer
> DNS resolves `googleapis.com.` to `restricted.googleapis.com` (`199.36.153.4/30`).

**Symptom:**

-   Deployment of Agent Gateway fails or runtime egress is blocked when the
    project is inside a VPC-SC perimeter.
-   Violation logs show `NETWORK_NOT_IN_SAME_SERVICE_PERIMETER` or similar
    VPC-SC blocks for calls between the consumer project and Google-managed
    infrastructure.

**Cause:**

1.  **ACT Egress Mode Misconfiguration (Primary Cause):** The Agent Connectivity
    Template is configured with `vpcEgress: PRIVATE_RANGES_ONLY` or the gateway is
    deployed in Standalone mode (without an ACT). In these modes, traffic bypasses
    the customer's VPC perimeter boundaries, causing VPC-SC to reject the
    deployment or egress calls.
2.  **Legacy or Strict Custom Perimeters (Historical):** Prior to September 8, 2026,
    control plane provisioning workflows required explicit ingress policies for
    Google-managed service agents. In legacy or custom perimeters that block
    Google-managed actuation identities, explicit ingress policies may still be
    required.

**Fix:**

1.  **Verify ACT `ALL_TRAFFIC`, `restricted.googleapis.com` DNS, & Shared VPC Co-Membership:**
    Ensure the ACT uses `vpcEgress: ALL_TRAFFIC` on a consumer PSC-I Network
    Attachment with Cloud NAT, configure a consumer Cloud DNS private zone for
    `googleapis.com.` (`*.googleapis.com` CNAME → `restricted.googleapis.com.` →
    `199.36.153.4/30`) peered via `dnsPeeringConfig`, and ensure any Shared VPC
    host project resides inside the **same** VPC-SC perimeter as the gateway and
    runtime projects.
2.  **Configure Ingress Policies (Legacy / Restrictive Perimeters Fallback):** If
    operating in a strict perimeter where Google-managed actuation identities are
    blocked, configure ingress policies in your VPC-SC perimeter to allow the
    actuation identities. Two ingress rules are required:

### Rule 1: Gateway Control Plane Actuation

Allows the control plane service agent to manage gateway resources.

-   **From**:
    -   Identities:
        `serviceAccount:actuation-a@networkservices-prod.iam.gserviceaccount.com`
    -   Sources: Access Level `*`
-   **To**:
    -   Operations:
        -   Service: `compute.googleapis.com`
            -   Methods:
                -   `FirewallsService.Delete`, `FirewallsService.Get`
                -   `GlobalOperationsService.Get`
                -   `HealthChecksService.Delete`, `HealthChecksService.Get`
                -   `InstanceTemplatesService.Delete`,
                    `InstanceTemplatesService.Get`
                -   `NetworksService.Delete`, `NetworksService.Get`
                -   `RegionAddressesService.Delete`
                -   `RegionBackendServicesService.Delete`,
                    `RegionBackendServicesService.Get`
                -   `RegionForwardingRulesService.Delete`,
                    `RegionForwardingRulesService.Get`
                -   `RegionInstanceGroupManagersService.Delete`,
                    `RegionInstanceGroupManagersService.Get`
                -   `RegionOperationsService.Get`
                -   `RegionRoutersService.Delete`, `RegionRoutersService.Get`
                -   `RoutesService.Delete`, `RoutesService.Get`
                -   `ServiceAttachmentsService.Delete`,
                    `ServiceAttachmentsService.Get`
                -   `SubnetworksService.Delete`, `SubnetworksService.Get`,
                    `SubnetworksService.List`
                -   `ZonesService.List`
        -   Service: `cloudresourcemanager.googleapis.com`
            -   Methods: `Projects.SetIamPolicy`
        -   Service: `networkservices.googleapis.com` (Methods: `*`)
        -   Service: `networksecurity.googleapis.com` (Methods: `*`)
        -   Service: `serviceusage.googleapis.com` (Methods: `*`)
        -   Service: `certificatemanager.googleapis.com` (Methods: `*`)
        -   Service: `privateca.googleapis.com` (Methods: `*`)
    -   Resources: `projects/CUSTOMER_PROJECT_NUMBER`

### Rule 2: Agent Runtime

Allows the Agent Runtime pipeline agent to access security resources.

-   **From**:
    -   Identities:
        `serviceAccount:cloud-aiplatform-pipeline-robot-prod@system.gserviceaccount.com`
    -   Sources: Access Level `*`
-   **To**:
    -   Operations:
        -   Service: `networksecurity.googleapis.com` (Methods: `*`)
    -   Resources: `projects/CUSTOMER_PROJECT_NUMBER`

Replace `CUSTOMER_PROJECT_NUMBER` with your actual project number.

--------------------------------------------------------------------------------

## 19. PSC Subnet Exhaustion Fails Agent Gateway Deployment

**Symptom:**

-   Agent Gateway deployment fails or gets stuck during provisioning.
-   Resource allocation errors related to IP addresses in GCE logs.

**Cause:** The Private Service Connect (PSC) Network Attachment requires free IP
addresses in its allocated subnet to establish connections. If the subnet
(especially if it is small, like `/28`) runs out of free IP addresses, the
gateway cannot allocate the necessary interfaces and deployment fails.

**Fix:** Verify and expand the PSC subnet.

1.  **Find the Agent Gateway Name** (if not provided): List the gateways in the
    project:

    ```bash
    gcloud network-services agent-gateways list --location=$LOCATION --project=$PROJECT_ID
    ```

2.  **Identify the subnetwork used by the gateway's Network Attachment**:
    Describe the gateway:

    ```bash
    gcloud network-services agent-gateways describe AGENT_GATEWAY_NAME --location=$LOCATION --project=$PROJECT_ID
    ```

    Look for `networkConfig.egress.networkAttachment` or
    `networkConfig.ingress.networkAttachment`.

3.  **Describe the Network Attachment to find the subnet name**:

    ```bash
    gcloud compute network-attachments describe <ATTACHMENT_NAME> --region=$LOCATION --project=$PROJECT_ID
    ```

4.  **Describe the subnetwork to check the CIDR range**:

    ```bash
    gcloud compute networks subnets describe <SUBNET_NAME> --region=$LOCATION --project=$PROJECT_ID
    ```

5.  If the subnet is small (e.g. `/28` or `/29`), it may be exhausted. Allocate
    a larger subnet (minimum `/26` recommended) or expand the existing one, and
    recreate the network attachment and gateway if necessary.

--------------------------------------------------------------------------------

## 20. Config Validation Failure: Missing Agent Registry API enablement

**Symptom:** During `gcloud network-services agent-gateways import`, the command
fails with:

```text
ERROR: (gcloud.network-services.agent-gateways.import) {
  "code": 3,
  "details": [
    {
      "@type": "type.googleapis.com/google.rpc.BadRequest",
      "fieldViolations": [
        {
          "description": "most likely missing permissions in project <PROJECT_NUMBER>, location <LOCATION>: agentregistry.agents.list, agentregistry.endpoints.list, and agentregistry.mcpServers.list",
          "field": "resource.registries"
        }
      ]
    }
  ],
  "message": "Config validation failed"
}
```

**Cause:** Primary cause: the Agent Registry API (`agentregistry.googleapis.com`)
is not enabled in the target registry project (even though the error message
suggests missing permissions). Secondary cause (when the API is already enabled):
the caller running `agent-gateways import` lacks `roles/agentregistry.viewer`
(`agentregistry.agents.list`, `agentregistry.endpoints.list`,
`agentregistry.mcpServers.list`) on the registry project.

**Fix:** Enable the Agent Registry API in the project (and ensure the deploying
caller holds `roles/agentregistry.viewer`):

```bash
gcloud services enable agentregistry.googleapis.com --project=YOUR_PROJECT_ID
```

--------------------------------------------------------------------------------

## 21. Agent Identity Egress to Cloud Run / Functions fails with 401/403 (JWT Auth issue)

**Symptom:** The agent is registered in the Agent Registry with an Agent
Gateway. When attempting to call an MCP server or tool hosted on Cloud Run or
Cloud Functions, the request fails with an egress error or HTTP 401 Unauthorized
/ 403 Forbidden.

**Cause:** Direct Agent Identity (using `principalSet`) to Cloud Run OIDC
authentication is not supported natively. Cloud Run requires a standard OIDC ID
token, which the default agent identity cannot obtain directly.

**Fix / Workaround:** The agent must use Service Account impersonation to obtain
an OIDC ID token to authenticate with Cloud Run.

1.  **Configure IAM Permissions:**
    *   The Agent Identity (`principalSet://...`) must have the
        `roles/iam.serviceAccountTokenCreator` role on a target Service Account
        (e.g. `mcp-invoker-sa`).
    *   The target Service Account must have `roles/run.invoker` on the Cloud
        Run service.
2.  **Enable Service Account Token Creator API:** Ensure
    `iamcredentials.googleapis.com` is enabled in the project.
3.  **Impersonate in Code:** Use the Google Auth SDK to impersonate the Service
    Account and generate ID tokens for the Cloud Run audience. Example Python
    (ADK):

    ```python
    from google.auth import impersonated_credentials
    import google.auth

    source_creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    impersonated = impersonated_credentials.Credentials(
        source_credentials=source_creds,
        target_principal="YOUR_TARGET_SA_EMAIL",
        target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    id_token_creds = impersonated_credentials.IDTokenCredentials(
        target_credentials=impersonated,
        target_audience="YOUR_CLOUD_RUN_URL_ORIGIN",
        include_email=True,
    )
    # Use id_token_creds to authenticate requests to Cloud Run.
    ```

4.  **Alternative (Preview — Cloud Run MCP Servers Only):** Deploy the Cloud Run
    MCP server with native IAP (`gcloud beta run deploy SERVICE --allow-unauthenticated
    --iap --functional-type=mcp-server`), grant `roles/run.invoker` to
    `service-PROJECT_NUMBER@gcp-sa-iap.iam.gserviceaccount.com`, and target the
    deterministic `https://SERVICE-PROJECT_NUMBER.REGION.run.app` short URL.

--------------------------------------------------------------------------------

## 22. Cross-Project Agent or MCP Server Not Visible in Central Governance Registry

**Symptom:** You deployed an agent or MCP server in Workload Project A, but
`gcloud agent-registry agents list` or `mcp-servers list` in Central Governance
Project B does not show it.

**Cause:** Automatic registration discovers resources **only within the same
project** where `agentregistry.googleapis.com` is enabled (there is no automatic
cross-project discovery or `gcloud agent-registry boundary` CLI command).

**Fix:** Manually register cross-project agents, MCP servers, and endpoints in
the Central Governance Project's registry using `gcloud agent-registry services
create` in a specific region or `global` (never `us` or `eu`):

```bash
# Example: Register a cross-project A2A agent (omit --interfaces with a2a-agent-card)
gcloud agent-registry services create cross-proj-agent \
  --project=GOVERNANCE_PROJECT_ID \
  --location=REGION \
  --display-name="Cross-Project Agent" \
  --agent-spec-type=a2a-agent-card \
  --agent-spec-content=agent-card.json
```

--------------------------------------------------------------------------------

## 23. Telemetry Egress Blocked by Egress Agent Gateway (Startup Failure)

**Symptom:** Reasoning Engine deployment fails to start up (container crashes
during `set_up()`). Logs show connection reset or handshake errors to
`telemetry.mtls.googleapis.com`.

**Cause:** Your project is using an **Egress Agent Gateway** (default-deny). The
agent runtime connects to Google telemetry services during startup. Because
these endpoints are not registered in the Agent Registry and allowed via policy,
the gateway blocks the connection, causing the startup probe to fail.

**Fix:** Register the required telemetry endpoints in the Agent Registry and
allow access via policy.

1.  **Verify & Register Telemetry and Tracing Endpoints:** You MUST explicitly
    check and verify whether all required monitoring and tracing endpoints
    (`telemetry.mtls.googleapis.com`, `monitoring.googleapis.com`,
    `trace.mtls.googleapis.com`, `cloudtrace.googleapis.com`) are registered as
    Endpoints in the Agent Registry:

    ```bash
    gcloud agent-registry endpoints list --location=us-central1 --project=$PROJECT_ID
    ```

    In Agent Registry, read-only `Endpoint` entries are projected automatically
    from writable `Service` entries (`gcloud agent-registry endpoints` is read-only
    with no `create` subcommand). Register or update your consolidated `googleapis` service
    with `--endpoint-spec-type=no-spec` so all required telemetry/tracing FQDNs
    are projected as Endpoints:

    ```bash
    gcloud agent-registry services create googleapis \
        --location=us-central1 \
        --project=$PROJECT_ID \
        --display-name="Google APIs" \
        --endpoint-spec-type=no-spec \
        --interfaces=url=https://telemetry.mtls.googleapis.com,protocolBinding=JSONRPC \
        --interfaces=url=https://monitoring.googleapis.com,protocolBinding=JSONRPC \
        --interfaces=url=https://trace.mtls.googleapis.com,protocolBinding=JSONRPC \
        --interfaces=url=https://cloudtrace.googleapis.com,protocolBinding=JSONRPC
    ```

2.  **Authorize the Egress:** Ensure your `AuthorizationPolicy` (`AuthzPolicy` +
    IAP `roles/iap.egressor` / UAP policy) is bound to the Gateway and allows
    the agent's principal set to egress to these registered telemetry endpoints.

--------------------------------------------------------------------------------

## 24. UAP Org Policy Blocker (constraints/iam.managed.disableAccessPolicyBinding)

**Symptom:** Creating an IAM Policy Binding (`gcloud iam policy-bindings create`
or Terraform `google_iam_{organizations,folders,projects}_policy_binding`) fails with:

```text
ERROR: (gcloud.iam.policy-bindings.create) CUSTOM_ORG_POLICY_VIOLATION: Operation violates organization policy constraint 'constraints/iam.managed.disableAccessPolicyBinding'.
```

**Cause:** Enterprise Google Cloud organizations often enforce
`constraints/iam.managed.disableAccessPolicyBinding` by default to prevent
unauthorized IAM v3 bindings. (Note: always use the singular constraint name
`disableAccessPolicyBinding`; some documentation pages contain a plural typo
`disableAccessPolicyBindings` that `gcloud org-policies` rejects.)

**Fix:** An Organization or Folder Administrator must apply an Org Policy V2
override setting `enforce: false` at the target resource level:

```bash
gcloud org-policies set-policy --project=${PROJECT_ID} override.yaml
```

Where `override.yaml` defines:

```yaml
name: projects/PROJECT_ID/policies/iam.managed.disableAccessPolicyBinding
spec:
  rules:
    - enforce: false
```

Allow 30–60 seconds for IAM policy control plane propagation before retrying.

--------------------------------------------------------------------------------

## 25. UAP Policy Binding Destruction Race Condition (400 FAILED_PRECONDITION)

**Symptom:** During automated teardown or `terraform destroy`, destroying
`google_iam_{organization,folder,project}_access_policy` (after `google_iam_{organizations,folders,projects}_policy_binding`) fails with:

```text
HTTP 400 FAILED_PRECONDITION: Access policy is referenced by active policy binding(s).
```

**Cause:** Deleting a `PolicyBinding` is subject to a 10–30 second replication
delay in the IAM control plane. If an orchestrator deletes the binding and
immediately issues a deletion for the parent `AccessPolicy`, IAM rejects the
call because the binding is still visible in eventual consistency.

**Fix:** Ensure teardown workflows poll `GET` on the `PolicyBinding` resource
URL until an HTTP 404 is confirmed before deleting the referenced
`AccessPolicy`. In Terraform scripts or destroy provisioners, never exit 0 on
timeout.

--------------------------------------------------------------------------------

## 26. Agent Gateway Multi-Registry & Jurisdiction Validation Errors

**Symptom:** `gcloud network-services agent-gateways import` or Terraform apply
fails with HTTP `400` / `InvalidArgument`:

```text
Invalid argument: maximum of two registries are supported. When it's two registries, one of them must be global, the other one can be either regional or multi-regional.
```

**Cause:** Either (a) more than two registries were specified, (b) two
registries were configured without `global` (e.g., two regional registries like
`us-central1` and `europe-west1`, or two `global` registries), or (c) the
regional/multi-regional registry violates jurisdiction alignment (a regional
gateway in `us-central1` can only attach `us-central1` or `us`, never
`europe-west1` or `eu`).

**Fix:** Configure **at most two registries**, ensuring **exactly one is `global`**
and the second matches the gateway's exact region or data-residency
multi-region:

```yaml
registries:
  - //agentregistry.googleapis.com/projects/PROJECT_NUMBER/locations/global
  - //agentregistry.googleapis.com/projects/PROJECT_NUMBER/locations/us-central1
```

--------------------------------------------------------------------------------

## 27. CEL Null Dereference Crash on Non-Tool MCP Methods

**Symptom:** Gatekeeper returns HTTP 500 or `PERMISSION_DENIED` with internal
evaluation error logs when an agent invokes MCP lifecycle or non-tool methods
(`prompts/list`, `resources/read`).

**Cause:** When invoking non-tool MCP operations, the `tool` message inside
`mcp_server` is `null`. A CEL rule that dereferences
`destination.agent_registry.mcp_server.tool.annotations.*` or `tool.name`
without first checking the method throws an unhandled null-dereference exception
in the CEL evaluator.

**Fix:** Guard all tool attribute dereferences with a method check:

```cel
(destination.agent_registry.mcp_server.method == 'tools') && (destination.agent_registry.mcp_server.tool.annotations.read_only_hint == true)
```

--------------------------------------------------------------------------------

## 28. ACT ALL_TRAFFIC Silent Outbound Hang (Missing Cloud NAT)

**Symptom:** When an Agent Gateway uses an Agent Connectivity Template with
`vpcEgress: ALL_TRAFFIC`, Reasoning Engine calls to public external APIs
(`api.weather.gov`, `api.ipify.org`, SaaS tools) hang and eventually fail with
connection timeouts. Egress to Google APIs continues to function normally.

**Cause:** In `ALL_TRAFFIC` mode, all non-Google outbound packets exit the PSC-I
Network Attachment into the consumer VPC subnet (`agw-psci-subnet`). If that
subnet does not have an active Cloud NAT gateway, public traffic is dropped.
(Google APIs bypass Cloud NAT via Andromeda Private Google Access).

**Fix:** Configure Cloud Router and Cloud NAT on the consumer VPC covering the
PSC-I subnet:

```bash
gcloud compute routers nats create agw-cloud-nat \
    --router=agw-nat-router \
    --region=LOCATION \
    --nat-custom-subnet-ip-ranges=agw-psci-subnet \
    --auto-allocate-nat-external-ips
```

--------------------------------------------------------------------------------

## 29. Agent Gateway Control-Plane Mutation Concurrency Lock (HTTP 409 ABORTED)

**Symptom:** Submitting a PATCH, update, or import command against an Agent
Gateway returns:

```text
HTTP 409 ABORTED: unable to queue the operation
```

**Cause:** The Network Services control plane enforces a strict per-resource
concurrency mutex lock on each Agent Gateway resource. Concurrent mutations are
aborted while an asynchronous update or delete operation is already active.

**Fix:** Wait ~1.5 to 2 minutes for the in-flight Long-Running Operation (LRO)
to reach `done: true` before initiating another mutation.

--------------------------------------------------------------------------------

## 30. ACT Deletion Fails with `400 FAILED_PRECONDITION` (`already being used`)

**Symptom:** Attempting to delete an Agent Connectivity Template fails with:

```text
HTTP 400 FAILED_PRECONDITION: Resource projects/.../agentConnectivityTemplates/... is already being used by resource(s) projects/.../agentGateways/...
```

**Cause:** Either an Agent Gateway deletion Long-Running Operation (LRO) is
still in flight, another Agent Gateway in the project still references the ACT,
or an asynchronous gateway cleanup left a backend cross-reference pending.

**Fix:**

1.  Verify that all referencing `AgentGateway` resources in the region have
    finished deleting (`done: true`):

    ```bash
    gcloud network-services agent-gateways list --location=${REGION} --project=${PROJECT_ID}
    gcloud network-services operations list --location=${REGION} --project=${PROJECT_ID}
    ```

2.  Always delete dependent resources in strict reverse order (`AuthzPolicy` →
    `AuthzExtension` → `AgentGateway` → `AgentConnectivityTemplate`), waiting
    for each LRO to complete before issuing the next delete.
3.  If `agent-gateways list` is empty and all operations show `done: true` for
    more than 10 minutes while the ACT still reports `already being used`,
    create a newly named ACT to unblock deployments immediately and open a
    Google Cloud Support case referencing the stuck ACT URI so support can clear
    the orphaned backend reference.

--------------------------------------------------------------------------------

## 31. Reasoning Engine Deletion Preconditions (Active Sessions Require ?force=true)

**Symptom:** Deleting a Vertex AI Reasoning Engine instance fails with:

```text
HTTP 400 FAILED_PRECONDITION: Cannot delete ReasoningEngine with active sessions.
```

**Cause:** Active agent sessions or conversations remain attached to the engine
runtime.

**Fix:** Append `?force=true` to the delete API call or use the force flag in
the CLI/REST client to cascade session cleanup.

--------------------------------------------------------------------------------

## 32. REST API Path Matching Gotcha (.json Extensions and Query Strings)

**Symptom:** An agent calling an external REST API (e.g. Zendesk) receives HTTP
403 `Egress request is not authorized`, even though a UAP rule allows
`/api/v2/tickets`.

**Cause:** SDK clients typically append `.json` (e.g. `/api/v2/tickets.json`) or
query strings (`?page=1`). Strict equality checks reject these variations, while
naive `.startsWith('/api/v2/tickets')` introduces security escapes to
`/api/v2/tickets_delete_all`.

**Fix:** Construct explicit boundary-aware CEL path conditions:

```cel
((destination.unregistered.path == '/api/v2/tickets') ||
 (destination.unregistered.path == '/api/v2/tickets.json') ||
 (destination.unregistered.path.startsWith('/api/v2/tickets/')) ||
 (destination.unregistered.path.startsWith('/api/v2/tickets?')) ||
 (destination.unregistered.path.startsWith('/api/v2/tickets.json?')))
```


--------------------------------------------------------------------------------

## 33. Secure Web Proxy (SWP) & Policy-Based Routing (PBR) Egress Failures

**Symptom:** When attempting to route egress traffic from an Agent Gateway
Network Attachment through a downstream Secure Web Proxy (SWP) for Layer 7 URL
filtering, packets drop silently, connections time out, or requests fail with
`HTTP 403 Forbidden`, `HTTP 503 Service Unavailable: remote connection failure`,
or `INVALID_ARGUMENT`.

**Causes & Platform Constraints:**

1.  **PSC Endpoints Cannot Be Route Next-Hops**: Google Cloud route tables (both
    static routes and Policy-Based Routes) do **not** allow Private Service
    Connect (PSC) forwarding rules (`--load-balancing-scheme=""`) or service
    attachments as next hops.
2.  **SWP via PSC Service Attachment Lacks Next-Hop Mode**: Publishing Secure
    Web Proxy behind a PSC Service Attachment operates strictly in **Explicit
    Proxy Mode** (`HTTP CONNECT`). Packets emerging from an Agent Gateway
    Network Attachment are Layer 3/Layer 4 transparent IP packets; they cannot
    reach an explicit proxy without client-side proxy configuration (unless the
    container is explicitly configured with `HTTPS_PROXY` on `:443` and a
    `v1beta1` L4 `AuthzPolicy` — see BKI #34).
3.  **Static Route Tag Defect**: Next-hop routing mode with static routes
    requires VM network tags (`--tags`). Network Attachments
    (`compute network-attachments`) are consumer network interfaces, not VM
    instances, and cannot bear network tags. Static routes cannot match or steer
    traffic originating from an Agent Gateway Network Attachment.
4.  **SWP Gateway Resource Definition Syntax Error**: Creating an SWP gateway
    with `type: SECURE_WEB_PROXY` fails validation. The Network Services
    API requires `type: SECURE_WEB_GATEWAY` and
    `routingMode: NEXT_HOP_ROUTING_MODE`.
5.  **Cloud NAT Missing `ENDPOINT_TYPE_SWG`**: SWP Envoy proxy instances reside
    on the private proxy-only subnet and lack external IPs. Outbound internet
    egress requires Cloud NAT configured with
    `--endpoint-types=ENDPOINT_TYPE_VM,ENDPOINT_TYPE_SWG`. If
    `ENDPOINT_TYPE_SWG` is omitted, proxy outbound traffic hangs silently.
6.  **ADK Streaming Session Allowlist Omission**: In `ALL_TRAFFIC` ACT mode,
    Agent Development Kit (ADK) streaming queries initialize sessions via
    `POST https://<region>-aiplatform.mtls.googleapis.com/.../sessions`. Because
    `ALL_TRAFFIC` forces all runtime egress to the Network Attachment, PBR
    steers this session call to SWP. If `<region>-aiplatform.mtls.googleapis.com`
    is omitted from the GatewaySecurityPolicy allowlist, SWP drops it
    (`default_denied`), causing ADK streaming queries to fail with HTTP 503
    (`remote connection failure`), while direct `query()` calls succeed.

**Fix:**

1.  **Deploy Next-Hop SWP directly in the consumer VPC**:
    Create an Envoy proxy-only subnet (`purpose: REGIONAL_MANAGED_PROXY`, `role: ACTIVE`,
    minimum `/26`) and deploy SWP listening on an internal IP on the PSC-I
    subnet (e.g. `10.20.1.250`) with `type: SECURE_WEB_GATEWAY` and
    `routingMode: NEXT_HOP_ROUTING_MODE`.
2.  **Configure Policy-Based Routing (PBR)**:
    Create a PBR matching source CIDR `10.20.1.0/24` (the Network Attachment
    subnet) and destination `0.0.0.0/0` with `--next-hop-ilb-ip=10.20.1.250`
    (priority 200). Add a default fallback PBR with priority 1000:

    ```bash
    gcloud network-connectivity policy-based-routes create agw-psci-to-swp-pbr \
      --network=projects/PROJECT_ID/global/networks/VPC_NAME \
      --source-range=10.20.1.0/24 \
      --destination-range=0.0.0.0/0 \
      --next-hop-ilb-ip=10.20.1.250 \
      --priority=200 \
      --project=PROJECT_ID
    ```

3.  **Configure Cloud NAT with `ENDPOINT_TYPE_SWG`**:
    Create (or recreate) Cloud NAT on the Cloud Router via `gcloud compute routers nats create`
    with `--endpoint-types=ENDPOINT_TYPE_VM,ENDPOINT_TYPE_SWG` (`--endpoint-types` is immutable and not supported on `nats update`).
4.  **Allowlist External Domains and Regional AI Platform in GatewaySecurityPolicy**:
    Ensure the CEL policy rule permits both external target domains and the
    regional AI platform session endpoint:
    `inUrlList(host(), ['api.weather.gov', 'api.ipify.org', '<region>-aiplatform.mtls.googleapis.com'])`.

--------------------------------------------------------------------------------

## 34. Explicit Forward HTTPS Proxy (`HTTP CONNECT`) Fails with `HTTP 404` or `403` Through Agent Gateway

**Symptom:**

-   **Symptom A (`HTTP 404` on `CONNECT`)**: An Agent Runtime container or tool
    configured with `HTTPS_PROXY=https://proxy.corp.internal:443` fails on every
    proxied request with `HTTP 404 Not Found` (`curl: (56) CONNECT tunnel
    failed, response 404`).
-   **Symptom B (`gcloud` Schema / Validation Error)**: Importing an
    `AuthzPolicy` containing `networkRules` fails under GA `gcloud`, or fails
    with `INVALID_ARGUMENT` when `target.loadBalancingScheme` or `ports` is set.
-   **Symptom C (`HTTP 403` from Downstream Proxy or ADC Metadata Hang)**: The
    tunnel reaches Squid / Explicit SWP, which rejects the client with `403
    Access Denied`, or Vertex AI SDK / `google-auth` hangs trying to reach
    `169.254.169.254` or `*.googleapis.com` through the proxy.

**Cause:**

1.  By default, Agent Gateway terminates TLS and routes decrypted streams
    through an L7 HTTP connection manager, which rejects nested `HTTP CONNECT`
    methods with `404`.
2.  `networkRules` (L4 SNI pass-through) is available only in the **`v1beta1`**
    API (`gcloud beta`), prohibits `target.loadBalancingScheme` when targeting
    `agentGateways`, and does not support `ports` in public schemas.
3.  **Two-Plane Source IP Split**: Inside Agent Gateway's Envoy listener,
    Agent Runtime connections arrive from Google's internal managed runtime
    egress CIDR `7.0.0.0/8` (while consumer VPC workloads arrive from their VPC
    CIDR), whereas packets exiting Agent Gateway's PSC-I NIC into your **consumer
    VPC** are sourced from your **consumer PSC-I Network Attachment subnet CIDR**
    (e.g., `10.20.0.0/24` — never `7.0.0.0/8`). In addition, L4 pass-through
    bypasses ACT `tlsConfig.trustConfig` certificate validation and breaks GCE
    metadata / Google API mTLS if `NO_PROXY` is omitted.

**Fix:**

1.  **Import a `v1beta1` L4 `AuthzPolicy` matching the proxy SNI** (omit
    `loadBalancingScheme` and `ports`; max 5 `networkRules`, max 10 `snis`,
    mutually exclusive with `httpRules`; either omit `from` or include **both**
    `7.0.0.0/8` and your PSC-I CIDR in `from.sources[].ipBlocks`):

    ```yaml
    # proxy-l4-authz-policy.yaml
    name: allow-explicit-proxy-l4
    action: ALLOW
    policyProfile: REQUEST_AUTHZ
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

2.  **Configure TLS on `:443` & Allow the Consumer PSC-I Subnet CIDR on the Proxy**:
    Listen on `:443` with TLS (e.g., `HTTPS_PROXY=https://proxy.corp.internal:443`),
    ensure `proxy.corp.internal.` resolves via `dnsPeeringConfig`, and allow
    your **consumer PSC-I Network Attachment subnet CIDR** (e.g., `10.20.0.0/24` /
    `10.0.0.0/8` RFC 1918) in consumer VPC GCE ingress firewall rules and Squid
    `acl localnet src` — do **not** allow `7.0.0.0/8` on consumer VPC firewalls
    or Squid ACLs (`7.0.0.0/8` is used **only** inside `AuthzPolicy`
    `networkRules[].from.sources[].ipBlocks` when `from` is configured).
3.  **Set `NO_PROXY` and Container CA Trust**: Set both `NO_PROXY` and `no_proxy`
    to `"169.254.169.254,metadata.google.internal,localhost,127.0.0.1,.googleapis.com,googleapis.com"`,
    and bundle both `agentGatewayCard.rootCertificates` and your Private CA root
    into `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, and
    `GRPC_DEFAULT_SSL_ROOTS_FILE_PATH`.
4.  **Security Trade-Off**: L4 `networkRules` bypasses L7 Agent Gateway policies
    (IAP/UAP, Model Armor, SGP, and `httpRules`) for traffic inside the
    `proxy.corp.internal` tunnel; enforce domain/URL policies on the downstream
    proxy or use BKI #33 (Next-Hop SWP + PBR) when L7 Agent Gateway inspection
    is required.

--------------------------------------------------------------------------------

## 35. Cloud DNS Transitive Peering Chain Exceeded (>2 Hops) or Authoritative Root Zone (`"."`) Causing `SERVFAIL` / `NXDOMAIN`

**Symptom:**

-   **Symptom A (`INVALID_ARGUMENT` or `HTTP 503` / `SERVFAIL` on Private Host)**:
    ACT or Gateway import fails preflight validation on a multi-hop peered DNS
    zone, or runtime calls to internal FQDNs fail with `HTTP 503` / `NXDOMAIN`
    even though VMs in the Spoke VPC resolve them.
-   **Symptom B (`NXDOMAIN` on All `*.googleapis.com` & Public Domains)**: After
    configuring `dnsPeeringConfig.domains: ["."]`, every Google API and public
    internet request fails DNS resolution.

**Cause:**

1.  **Cloud DNS 2-Hop Transitive Limit**: Agent Gateway supports transitive
    Cloud DNS peering up to **at most 2 hops** (3 VPC networks: `Gateway Tenant
    VPC → Attached Spoke VPC → Target Hub VPC`). Agent Gateway's internal tenant
    peering consumes **Hop 1**, leaving at most **1** customer DNS peering hop.
    If the 2nd-hop VPC chains to another Cloud DNS Peering Zone (a 3rd hop),
    preflight validation or runtime DNS resolution fails.
2.  **Authoritative `"."` Zone Trap**: Peering `domains: ["."]` to an
    **Authoritative** private zone for `"."` makes that zone authoritative for
    the entire DNS root, returning `NXDOMAIN` for all unrecorded domains.
3.  **Schema Split**: `AgentConnectivityTemplate` `dnsPeeringConfig` accepts
    only `domains` (array) and `targetNetwork` (string URI with **Project ID**;
    passing `targetProject` fails schema validation), whereas inline
    `AgentGateway.networkConfig.dnsPeeringConfig` requires `domains`,
    `targetNetwork`, and `targetProject`.

**Fix:**

1.  Keep DNS peering to **at most 1 customer peering hop** (`<= 2` hops total),
    ensuring the 2nd-hop Hub VPC hosts an **Authoritative Private Zone** or uses
    **Cloud DNS Forwarding** (inbound/outbound forwarding IPs) rather than
    another Peering Zone. Where supported in your region, you can point
    `dnsPeeringConfig.targetNetwork` directly at the central DNS Hub VPC
    (granting `roles/dns.peer` and `roles/dns.reader` to
    `service-GATEWAY_PROJECT_NUMBER@gcp-sa-agentgateway.iam.gserviceaccount.com`
    and `roles/dns.reader` + `roles/compute.networkViewer` to the caller on the
    Hub project).
2.  Use `domains: ["."]` **only** with a **Cloud DNS Private Forwarding Zone**,
    never an Authoritative private root zone; prefer specific suffixes with
    trailing dots (e.g., `["corp.internal."]`).

--------------------------------------------------------------------------------

## 36. Consumer VPC Packet Intercept (`HTTP 503`) & Workforce / Workload Identity Federation (`Code 13` / `403`) Limits

**Symptom:**

-   **Symptom A (`HTTP 503` on PSC-I Egress)**: All private or internet egress
    through an ACT Network Attachment fails with `HTTP 503` or TLS connection
    resets despite valid Cloud NAT, firewall rules, and Agent Registry entries.
-   **Symptom B (`Code 13` or `403` with WIF Principals)**: Provisioning Agent
    Gateway / Registry resources from a Workforce Identity Federation session
    returns `Code 13` (`Internal error`), or cross-cloud (AWS / Azure) Workload
    Identity Federation (WIF — Preview) runtime requests fail with `Code 13` or
    `403 Forbidden`.

**Cause:**

1.  **Network Security Packet Intercept Conflict**: Consumer VPCs with Network
    Security Packet Intercept (`InterceptDeploymentGroup`) or inline third-party
    NGFW packet interception matching the PSC-I Network Attachment subnet
    disrupt Agent Gateway's egress flows.
2.  **Preview WIF Caller & Claim Limits**: Workforce Identity Federation human
    principals hit `Code 13` during Preview gateway/registry management
    operations (adding broader IAM roles to the WIF user does **not** bypass
    this Preview limitation), and referencing unsupported custom WIF attribute
    expressions in IAP / UAP policies fails runtime evaluation.

**Fix:**

1.  Exclude the Agent Gateway PSC-I Network Attachment subnet (or use a
    dedicated egress VPC/subnet) from Network Security Packet Intercept rules.
2.  Execute gateway/registry provisioning using a standard Cloud Identity /
    Google Workspace user or Google Cloud Service Account, and bind exact
    supported `principal://iam.googleapis.com/locations/global/workforcePools/...`
    or `workloadIdentityPools/...` identifiers in runtime policies.

--------------------------------------------------------------------------------

## 37. Immediate `HTTP 498` After Binding Agent Runtime to Gateway, or Gemini Enterprise Regional `UpdateEngine` Failures

**Symptom:**

-   **Symptom A (`HTTP 498`)**: Immediately after binding an Agent Runtime
    (Reasoning Engine) to an Agent Gateway, agent invocations fail with HTTP
    status **`498`**.
-   **Symptom B (Gemini Enterprise `404`/`400` or Bypassed Egress)**: Attaching
    an Agent Gateway to a Gemini Enterprise engine in `us` or `eu` via
    `discoveryengine.googleapis.com` fails, or registered connectors/MCP tools
    bypass the gateway.

**Cause:**

1.  Binding an Agent Runtime to an Agent Gateway in enforcing mode *before*
    registering and authorizing essential platform APIs (Vertex AI, Cloud
    Resource Manager, IAM Credentials, Telemetry, Sessions / Memory Bank) blocks
    mandatory runtime platform calls, surfacing as `HTTP 498`.
2.  Gemini Enterprise engines require regional endpoint host prefixes
    (`global-`, `us-`, or `eu-discoveryengine.googleapis.com`) on `UpdateEngine`
    `PATCH` **and** per-connector opt-in (`"use_agent_gateway_egress": true`).

**Fix:**

1.  Deploy the IAP extension in `iamEnforcementMode: "DRY_RUN"` first or
    register the consolidated `googleapis` service entry and grant
    `roles/iap.egressor` / UAP allow rules **before** binding the Agent Runtime
    to the gateway.
2.  For Gemini Enterprise, call
    `PATCH https://{global-|us-|eu-}discoveryengine.googleapis.com/v1/projects/PROJECT_NUMBER/locations/GE_LOCATION/collections/default_collection/engines/ENGINE_ID?updateMask=agentGatewaySetting.defaultEgressAgentGateway.name`
    and set `"use_agent_gateway_egress": true` on each `DataConnector`.

--------------------------------------------------------------------------------

## 38. Semantic Governance Policy (SGP) Failures: Startup gRPC Crash, Streaming Bypass, Missing Agent in Picker, or `metadata` Overwrite

**Symptom:**

-   **Symptom A (Startup gRPC Crash)**: Agent Runtime crashes on startup after
    attaching an SGP `AuthzPolicy`.
-   **Symptom B (Streamed Model Call Returns No Verdict or an Error)**:
    Streamed model calls (`:streamGenerateContent`, `:streamRawPredict`) return
    no verdict or an error, or produce zero evaluation entries in
    `projects/PROJECT_ID/logs/semantic-governance-policy`.
-   **Symptom C (Missing Agent)**: Expected Reasoning Engine is missing from the
    Console SGP agent selector, or CLI fails with
    `SEMANTIC_GOVERNANCE_POLICY_AGENT_NOT_CONFIGURED`.
-   **Symptom D (Unexpected Enforcement After `metadata` Update)**: Updating
    `sgpUserIntentMatching: "ENABLED"` or `"DISABLED"` unexpectedly activates
    blocking enforcement (wiping `sgpEnforcementMode: "DRY_RUN"`), or sessions
    fail with `FAILED_PRECONDITION` when calling `SGP_DNS_HOSTNAME`.

**Cause & Fixes:**

1.  **Mandatory gRPC Exclusion, Non-Streaming Invocation, & `.contains()` `when` Filter**:
    The LLM in the semantic governance policy engine does **not** support
    streamed model responses (`:streamGenerateContent`, `:streamRawPredict`
    return no verdict or an error), and omitting gRPC exclusion intercepts
    internal `application/grpc` startup calls. Invoke models **without
    streaming** and configure `httpRules[].when` on the `CONTENT_AUTHZ`
    `AuthzPolicy` using `.contains()` (because `request.path` includes query
    strings):
    `"!request.headers['content-type'].startsWith('application/grpc') && (request.path.contains(':generateContent') || request.path.contains(':rawPredict') || request.path.contains('/v1/messages') || request.path.contains('/chat/completions'))"`.
2.  **Agent Eligibility (`AGENT_IDENTITY` + `agent_gateway_config`)**: Both
    fields must be set **at Reasoning Engine creation time**
    (`spec.effectiveIdentity` starting with `agents.global.`); redeploy
    ineligible engines.
3.  **VPC Connectivity, Reserved Subnets, & Service Agent IAM**: Ensure consumer
    VPC subnets do **not** overlap SGP's reserved internal ranges
    (`10.0.0.0/24`, `10.0.1.0/24`, `10.0.2.0/24`), configure `dnsPeeringConfig`
    so `SGP_DNS_HOSTNAME` (`dnsRecord`) resolves, and grant
    `roles/compute.networkAdmin`, `roles/dns.admin`, and `roles/cloudtrace.agent`
    to `service-PROJECT_NUMBER@gcp-sa-aiplatform.iam.gserviceaccount.com`.
4.  **Wholesale `updateMask=metadata` Replacement**: Importing or patching
    `AuthzExtension` `metadata` replaces the **entire** `metadata` map. Always
    include **both** keys together (e.g., `sgpEnforcementMode: "DRY_RUN"` and
    `sgpUserIntentMatching: "ENABLED"` or `"DISABLED"`), and verify verdicts in
    `projects/PROJECT_ID/logs/semantic-governance-policy`.
5.  **SGP Control-Plane Error Reference (`gcloud beta ai semantic-governance-policies` / `semantic-governance-policy-engine`)**:
    -   `SEMANTIC_GOVERNANCE_POLICY_ALREADY_EXISTS` / `SEMANTIC_GOVERNANCE_POLICY_ETAG_MISMATCH`: Use `update` with the latest `etag` from `describe`.
    -   `SEMANTIC_GOVERNANCE_POLICY_AGENT_REQUIRED` / `SEMANTIC_GOVERNANCE_POLICY_CONSTRAINT_REQUIRED`: Supply `--agent` and `--natural-language-constraint`.
    -   `SEMANTIC_GOVERNANCE_POLICY_AGENT_INVALID_NAME` / `SEMANTIC_GOVERNANCE_POLICY_MCP_SERVER_INVALID_NAME` / `SEMANTIC_GOVERNANCE_POLICY_AGENT_REGISTRY_INVALID_NAME` / `SEMANTIC_GOVERNANCE_POLICY_AGENT_NOT_FOUND` / `SEMANTIC_GOVERNANCE_POLICY_MCP_SERVER_NOT_FOUND`: Pass full `projects/PROJECT_ID/locations/LOCATION/{agents|mcpServers}/agentregistry-...` resource paths registered in the same location.
    -   `SEMANTIC_GOVERNANCE_POLICY_AGENT_NOT_CONFIGURED`: Redeploy agent with `AGENT_IDENTITY` + `agent_gateway_config` set at creation time.
    -   `SEMANTIC_GOVERNANCE_POLICY_REGISTRY_DENIED`: Enable `agentregistry.googleapis.com` and grant `roles/agentregistry.viewer`.
    -   `SEMANTIC_GOVERNANCE_POLICY_AGENT_UNSUPPORTED_REGION` / `SEMANTIC_GOVERNANCE_POLICY_MCP_SERVER_UNSUPPORTED_REGION` / `SEMANTIC_GOVERNANCE_POLICY_ENGINE_SERVICE_NOT_AVAILABLE_IN_LOCATION` / `SEMANTIC_GOVERNANCE_POLICY_ENGINE_NOT_ENABLED_IN_REGION`: Use a supported SGP region (`us-central1`, `us-east1`, `us-east4`, `us-west1`, `europe-southwest1`, `europe-west1`, `europe-west4`, `europe-west8`), set `api_endpoint_overrides/aiplatform`, and provision the engine via `gcloud beta ai semantic-governance-policy-engine update` until `state: ACTIVE`.

--------------------------------------------------------------------------------

## 39. Native MCP `AuthzPolicy` Blocks Session Handshake (`initialize` / `ping`) Due to Missing `MATCH_BASE_PROTOCOL_METHODS` & `ExtensionBinding` Double-Invocation

**Symptom:**

-   **Symptom A (`403` on MCP Session Startup)**: After attaching a native MCP
    Layer 7 `AuthzPolicy` (`httpRules[].to.operations[].mcp`, `action: ALLOW`)
    paired with `DENY_BY_DEFAULT`, MCP clients and ADK agents fail immediately
    during session startup with `HTTP 403 Forbidden` before calling `tools/list`
    or `tools/call`.
-   **Symptom B (Duplicate Extension Calls / Double Latency)**: Requests routed
    through an Agent Gateway invoke the same `AuthzExtension` or
    `ProducerExtension` twice.

**Cause:**

1.  MCP clients execute JSON-RPC base lifecycle methods (`initialize`, `ping`,
    `notifications/initialized`) before calling tools. In
    `httpRules[].to.operations[].mcp`, `baseProtocolMethodsOption` defaults to
    **`SKIP_BASE_PROTOCOL_METHODS`**, which prevents `initialize` and `ping`
    from matching an `ALLOW` rule when `DENY_BY_DEFAULT` is active.
2.  **`ExtensionBinding` Hierarchy & Coexistence Double-Invocation**: When
    `ExtensionBinding` resources (Preview) attach the **same** extension at
    **both** project scope (`target.scope.parent: "projects/PROJECT_NUMBER"`,
    `resourceTypes: "AGENT_GATEWAY"`) **and** gateway resource scope
    (`target.resources`), both bindings execute on matching requests. Combining
    a project-scope `ExtensionBinding` with a gateway-bound `AuthzPolicy`
    (`action: CUSTOM`) for the same extension likewise invokes it twice (double
    latency and double billing).

**Fix:**

1.  Set `baseProtocolMethodsOption: MATCH_BASE_PROTOCOL_METHODS` on `ALLOW`
    rules (keep `SKIP_BASE_PROTOCOL_METHODS` on `DENY` rules so denying one tool
    does not block the MCP session), omit `target.loadBalancingScheme`, and
    re-import with `gcloud network-security authz-policies import`:

    ```yaml
    name: allow-approved-mcp-tools
    action: ALLOW
    policyProfile: REQUEST_AUTHZ
    target:
      resources:
        - projects/PROJECT_ID/locations/REGION/agentGateways/AGENT_GATEWAY_NAME
    httpRules:
      - to:
          operations:
            - mcp:
                baseProtocolMethodsOption: MATCH_BASE_PROTOCOL_METHODS
                methods:
                  - name: "tools/list"
                  - name: "tools/call"
                    params:
                      - exact: "get_order_status"
    ```

2.  Attach each extension at **either** project scope (`target.scope`) **or**
    gateway resource scope (`target.resources` / `AuthzPolicy`), never both on
    the same traffic path.
