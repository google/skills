# Google Cloud Global Load Balancer gcloud Script Generation Guidelines

This reference document details how to generate robust, ordered, production-grade bash scripts containing `gcloud` CLI commands to deploy Google Cloud Global External Application Load Balancer architectures (incorporating Cloud CDN and Cloud Armor WAF) based on a design spec.

---

## Core Directives - Behavioral Rules

1.  **Deterministic Command Ordering:** You must strictly follow the **Dependency Execution Order** below. Google Cloud resource creation has strict dependency trees; executing commands out of order will result in immediate deployment failures.
2.  **Resource Prefixing:** You must prefix every created resource name with the environment variable `$ARCHITECTURE_NAME` to ensure global uniqueness and prevent 409 conflicts.
3.  **Destruction Pairing (Mandatory):** For every script you generate, you MUST generate an accompanying destruction script (`destroy.sh`) that tears down the exact same resources in exact reverse dependency order.
4.  **Error Handling (Strict Requirement):** You must include `set -e` (exit immediately on error) at the top of all generated scripts to prevent cascading failures if an intermediate command fails.

---

## Dependency Execution Order (The Creation Sequence)

All `gcloud` commands must be ordered in this exact sequence in your output script:

1.  **Variables & Setup:** Define environment variables (`ARCHITECTURE_NAME`, `PROJECT_ID`, `REGION`, etc.) and set the active project via `gcloud config set project`.
2.  **Network Endpoint Groups (NEGs):** Create region/global NEGs if using Serverless or External origins.
3.  **Cloud Armor Security Policies:** Create policies and rules.
4.  **Backend Services & Buckets:** Create backends, configure CDN settings, and attach security policies.
5.  **URL Maps:** Create the root URL map and attach backend services.
6.  **Path & Host Rules:** Apply path matchers and routing rules to the URL map.
7.  **Target Proxies:** Create HTTP/HTTPS target proxies, linking the URL map and certificates.
8.  **Global Forwarding Rules:** Create the frontend forwarding rules, binding target proxies to public IPs.

---

## Workload Profile CLI Map (The Source of Truth)

| Workload Type | CDN Flags | WAF Policy & Rules |
| :--- | :--- | :--- |
| **Static Images / Objects** | `--enable-cdn`<br>`--cache-mode=CACHE_ALL_STATIC`<br>`--default-ttl=2592000`<br>`--client-ttl=86400`<br>`--max-ttl=31536000` | None (Rate Limiting unsupported on CLOUD_ARMOR_EDGE) |
| **Cacheable API**| `--enable-cdn`<br>`--cache-mode=USE_ORIGIN_HEADERS` | Rate limit (100 RPM) + OWASP rules (SQLi, XSS, LFI)<br>`--action=deny-403`<br>`--expression="evaluatePreconfiguredExpr('sqli-v33-stable') \|\| evaluatePreconfiguredExpr('xss-v33-stable')"` |
| **Uncacheable API / Transactions**| `--no-enable-cdn` | Strict Rate limit (30 RPM) + OWASP rules + Bot Management/Threat Intel |
| **Dynamic Web (SSR)** | `--enable-cdn`<br>`--cache-mode=USE_ORIGIN_HEADERS` | Rate limit (120 RPM) + OWASP rules (SQLi, XSS, CSRF) |

---

## Backend Reference Directory (Commands)

### 1. Cloud Storage Buckets (GCS)
```bash
gcloud compute backend-buckets create "${ARCHITECTURE_NAME}-bucket-backend" \
    --bucket-name="{bucket_name}" \
    --enable-cdn \
    --cache-mode="{cache_mode}" \
    --default-ttl="{default_ttl}" \
    --client-ttl="{client_ttl}" \
    --max-ttl="{max_ttl}"
```

### 2. Cloud Run Services
```bash
# Create Serverless NEG
gcloud compute network-endpoint-groups create "${ARCHITECTURE_NAME}-neg" \
    --reference-neg-template \
    --network-endpoint-type=serverless \
    --region="{region}" \
    --cloud-run-service="{service_name}"

# Create Backend Service
gcloud compute backend-services create "${ARCHITECTURE_NAME}-backend" \
    --global \
    --protocol=HTTP \
    --security-policy="{security_policy_name}"

# Add NEG to Backend
gcloud compute backend-services add-backend "${ARCHITECTURE_NAME}-backend" \
    --global \
    --network-endpoint-group="${ARCHITECTURE_NAME}-neg" \
    --network-endpoint-group-region="{region}"
```

### 3. Compute Engine MIGs
```bash
# Create Backend Service
gcloud compute backend-services create "${ARCHITECTURE_NAME}-backend" \
    --global \
    --protocol=HTTP \
    --security-policy="{security_policy_name}"

# Add MIG to Backend
gcloud compute backend-services add-backend "${ARCHITECTURE_NAME}-backend" \
    --global \
    --instance-group="{mig_name}" \
    --instance-group-zone="{zone}"
```

### 4. GKE Clusters
```bash
# Create Backend Service
gcloud compute backend-services create "${ARCHITECTURE_NAME}-backend" \
    --global \
    --protocol=HTTP \
    --security-policy="{security_policy_name}"

# Add GKE NEG to Backend
gcloud compute backend-services add-backend "${ARCHITECTURE_NAME}-backend" \
    --global \
    --network-endpoint-group="{gke_neg_name}" \
    --network-endpoint-group-zone="{zone}"
```

### 5. External / Internet Origins (IP/FQDN)
```bash
# Create Global NEG for External Origin
gcloud compute network-endpoint-groups create "${ARCHITECTURE_NAME}-neg" \
    --global \
    --network-endpoint-type=internet-fqdn-port

# Add Endpoint
gcloud compute network-endpoints add "${ARCHITECTURE_NAME}-neg" \
    --global \
    --fqdn="{domain_name}" \
    --port=443

# Create Backend Service
gcloud compute backend-services create "${ARCHITECTURE_NAME}-backend" \
    --global \
    --protocol=HTTPS \
    --security-policy="{security_policy_name}"

# Add NEG to Backend
gcloud compute backend-services add-backend "${ARCHITECTURE_NAME}-backend" \
    --global \
    --network-endpoint-group="${ARCHITECTURE_NAME}-neg"
```

---

## Script Assembly Workflow

1.  **Define Header:** Set `set -e` and export the variables (`ARCHITECTURE_NAME`, `PROJECT_ID`, etc.).
2.  **Generate Creation Block:** Assemble the commands sequentially following the **Dependency Execution Order** and utilizing the **Workload Profile CLI Map** and **Backend Reference Directory**.
3.  **Generate Destruction Block:** Append or output a separate `destroy.sh` script that tears down the exact same resources in exact reverse dependency order.
4.  **Output and Hand-off:** Present the scripts to the user. State the next action (Download Files or Deploy Configuration) and transition to `references/managed-deployment.md` (specifically Phase 2 Option B) to guide them through deployment execution.
