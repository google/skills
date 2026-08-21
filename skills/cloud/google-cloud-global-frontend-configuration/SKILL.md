---
name: google-cloud-global-frontend-configuration
metadata:
  category: Networking
description: |
  Guides agents through a 6-step discovery process to design and deploy Google Cloud global external Application Load Balancers with Cloud CDN, Cloud Armor, and Service Extensions, mapping workload requirements to best-practice configurations.
  Use when:
  - Designing, configuring, or deploying a Google Cloud global external Application Load Balancer, Cloud CDN, Cloud Armor WAF, or Service Extensions.
  - Discovering existing Google Cloud resources (Cloud Storage, MIGs, GKE, Cloud Run) to use as backends.
  - Generating production-grade Terraform HCL or gcloud CLI scripts for global external Application Load Balancers.
  - Actuating deployments via Infrastructure Manager or bash scripts, including IAM pre-checks.
  - Detecting, analyzing, or reconciling configuration drift on deployed global external Application Load Balancers.
  Don't use for:
  - Non-Google Cloud load balancing or security configurations.
  - Purely regional or internal load balancing setups (unless part of a hybrid/failover global design).
---

# Google Cloud global external Application Load Balancer Configuration Skill

## Purpose & Agent Guidance

This skill enables the agent to guide users through a structured, 6-step discovery process to design and deploy Google Cloud global external Application Load Balancers (incorporating Cloud CDN, Cloud Armor, and Service Extensions).

**Assumptions & Target Environments:**
- This skill assumes it is called from environments (such as Gemini CLI, Antigravity, etc.) where the Google Cloud CLI (`gcloud`) can be executed.
- If `gcloud` is not available or accessible, the skill cannot perform automated resource discovery or managed deployment actuation. In such environments, the skill will limit its support to guiding the design and generating Terraform HCL configurations.

When executing this skill, the agent must:
- Map user workload requirements to simplified, opinionated best-practice configurations using actual Google Cloud product names.
- Progressively disclose details, hiding advanced complexity unless the user explicitly asks for customization.
- Leverage the reference documents in the `references/` directory to perform resource discovery, code generation, actuation, and drift detection.

## The 6-Step Configuration Flow

### Step 1: Basics
*   **Project Discovery:** Consult `references/resource-discovery.md` to auto-detect the Google Cloud project ID. Present the discovered project ID to the user.
*   Ask the user for the foundational details of their load balancer:
    *   **Name & Description:** What should we call this load balancer?
    *   **Protocol Selection:** Do they need HTTP, HTTPS, or both?
    *   **Certificate Management:** Do they want to use Google-managed certificates or bring their own existing certificates?

### Step 2: Origin Configuration
Help the user define their backend workloads through a strictly sequential, step-by-step loop. Do NOT ask everything at once. All steps are mandatory.

*   **Sub-step A - Origin Setup:** Ask if they have a single origin or need multi-origin support. Wait for response.
*   **Sub-step B - Origin Types:** Ask them to select the backend types from: Cloud Storage Buckets, Compute Engine Managed Instance Groups (MIGs), Google Kubernetes Engine (GKE) Clusters, Cloud Run Services, or External/Internet origins (IP/FQDN). Wait for response.
*   **Sub-step C - Origin Definition Loop:** Execute the following loop sequentially for EACH origin type selected in Sub-step B. Wait for the user to answer for one origin before asking about the next:
    *   **Resource Discovery:** For Google Cloud-native origins (Cloud Storage, MIGs, GKE, Cloud Run), consult `references/resource-discovery.md` to fetch resources. Present the list starting with **1. Create New**, **2. NA**. For External/Internet origins, just ask for the FQDN/IP.
    *   **Workload Type (CRITICAL):** Immediately after they define the resource, ask exactly what type of workload is being served:
        1.  **Static Images / Objects** (Static content, images, videos, styling assets)
        2.  **Cacheable API** (Read-only, public APIs where cached data is acceptable)
        3.  **Uncacheable API / Transactions** (Transactional endpoints, login, checkout, account changes)
        4.  **Dynamic Web (SSR)** (Dynamic pages, server-side rendered apps, custom dynamic sessions)
*   **Sub-step D - Routing Rules:** Once ALL origins have been fully defined one by one, ask how traffic should be routed between them (Path-based, header-based, or query-param-based). Wait for response.
*   **Sub-step E - Logging:** After routing is established, ask if they want to enable Cloud CDN logging, and if so, at what sampling rate (0-100%). Wait for response.

### Step 3: Traffic Management & Extensibility
*   Provide a brief summary of the origins and routing rules defined in Step 2.
*   Ask if they need to enable Advanced Traffic Management settings (such as granular weighted load balancing, traffic mirroring, or **Cloud Load Balancing Service Extensions** for custom WASM plugins / callouts), or if they want to proceed with **Google Cloud Best Practice Configuration**.

### Step 4: Caching (Cloud CDN)
Propose a "Recommended Configuration" based entirely on the Workload Type from Step 2. Do not list the advanced settings (TTL, Cache Keys, Compression) unless they reject the recommendation and want to customize.

*   **If Workload = Static Images / Objects:**
    *   Cache Mode: Cache All Static
    *   TTL: Client (1 day / 86400s), Default (30 days / 2592000s), Max (365 days / 31536000s) — balances long-term cache offload for static assets with periodic re-validation.
    *   Cache Key: Protocol + Host + Path (Ignore Query Strings)
    *   Compression: Enabled (Brotli & Gzip)
    *   Negative Caching: Enabled
    *   Serve while stale: Enabled
*   **If Workload = Cacheable API:**
    *   Cache Mode: Use Origin Headers
    *   TTL: Managed by Origin (Omitted from configuration to prevent errors)
    *   Cache Key: Protocol + Host + Path + Include Query Strings
    *   Compression: Enabled (Gzip)
    *   Negative Caching: Enabled
    *   Serve while stale: Disabled
*   **If Workload = Uncacheable API / Transactions:**
    *   Cache Mode: Disabled (CDN Bypassed)
*   **If Workload = Dynamic Web (SSR):**
    *   Cache Mode: Use Origin Headers
    *   TTL: Managed by Origin (Omitted from configuration to prevent errors)
    *   Cache Key: Protocol + Host + Path
    *   Compression: Enabled (Brotli & Gzip)
    *   Cache Bypass: Bypass cache if session cookies (e.g., SESSID, JWT) are present

### Step 5: Security (Cloud Armor)
Propose a "Recommended Configuration" based entirely on the Workload Type from Step 2. Keep advanced protection (Bot Management, Threat Intel, Geo-blocking) hidden unless requested.

*   **If Workload = Static Images / Objects:**
    *   Rate Limiting: None (Standard Edge behavior; rate limiting is unsupported on Cloud Armor Edge policies for Cloud Storage buckets).
    *   OWASP Protection: Disabled
*   **If Workload = Cacheable API:**
    *   Rate Limiting: 100 requests per minute per client IP (standard baseline to prevent API abuse and DDoS while accommodating normal interactive usage).
    *   OWASP Protection: Enabled (SQLi, XSS, Local File Inclusion)
*   **If Workload = Uncacheable API / Transactions:**
    *   Rate Limiting: Strict 30 requests per minute per client IP (tight threshold to protect sensitive transactional endpoints like login/checkout from credential stuffing and brute-force attacks).
    *   OWASP Protection: Enabled (SQLi, XSS, Remote Command Execution, Session Fixation)
    *   Bot Management & Threat Intel: Enabled (Block malicious bots and known malicious IPs)
*   **If Workload = Dynamic Web (SSR):**
    *   Rate Limiting: 120 requests per minute per client IP (generous threshold to accommodate burst requests for initial page loads and asset hydration in SSR web applications).
    *   OWASP Protection: Enabled (SQLi, XSS, CSRF, Shellshock)
    *   Geo-blocking: Optional (Restrict/allow specific country access)

### Step 6: Review & Deploy
*   **Configuration Summary:** Generate a complete, formatted markdown table showing all finalized settings from Steps 1 through 5, using Google Cloud product names. Follow this exact template structure:

    | Component | Parameter / Setting | Value & Justification |
    | :--- | :--- | :--- |
    | **Load Balancer** | Name & Protocol | `<Name>` (HTTP/HTTPS) |
    | **Origins** | Backends & Workloads | `<Backend 1>` (`<Workload Type>`), `<Backend 2>`... |
    | **Traffic Management** | Routing Rules | `<Path / Header rules or Default>` |
    | **Cloud CDN** | Cache Mode & TTLs | `<Cache Mode>`, Default TTL: `<TTL>` |
    | **Cloud Armor** | Rate Limiting & OWASP | `<RPM Limit>`, OWASP Rules: `<Enabled/Disabled>` |
    | **Service Extensions**| WASM / Callouts | `<Enabled/Disabled or N/A>` |

*   **Next Action:** Ask the user to choose their deployment/generation format (Terraform HCL or gcloud CLI Bash Script) and their next action:
    1.  **Show Code / Script** (Display the HCL code or gcloud bash script. Once displayed, offer options to **Download** or **Deploy/Execute**)
    2.  **Download files** (Save `main.tf` or `deploy.sh` to the local workspace)
    3.  **Deploy Configuration:** Initiate the deployment via Infrastructure Manager or execute the gcloud script. This should be done using the deployment instructions in `references/managed-deployment.md`.

---

## Relevant Documentation & Supportive Links
- [Cloud Load Balancing Overview](https://cloud.google.com/load-balancing/docs/load-balancing-overview)
- [Cloud CDN Documentation](https://cloud.google.com/cdn/docs)
- [Cloud Armor Documentation](https://cloud.google.com/armor/docs)
- [Cloud Load Balancing Service Extensions](https://cloud.google.com/service-extensions/docs/overview)
- [Infrastructure Manager Overview](https://cloud.google.com/infrastructure-manager/docs)
- [Official Terraform LB-HTTP Module](https://registry.terraform.io/modules/GoogleCloudPlatform/lb-http/google/latest)
- [Official Terraform Cloud Armor Module](https://registry.terraform.io/modules/GoogleCloudPlatform/cloud-armor/google/latest)
