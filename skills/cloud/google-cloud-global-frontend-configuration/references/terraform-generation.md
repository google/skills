# Google Cloud Global Load Balancer Terraform Code Generation Guidelines

This reference document details how to generate syntactically perfect, production-grade Terraform HCL code for Google Cloud Global External Application Load Balancer architectures (incorporating Cloud CDN and Cloud Armor WAF) based on a design spec.

---

## Core Directives - Behavioral Rules

1.  **Deterministic Output:** You must strictly follow the **Workload Profile Map** below. If a user selects a workload type, you MUST apply the corresponding HCL properties. Do not deviate or get "creative" with the code.
2.  **Schema Enforcement:** You expect a "Design Spec" containing: Architecture Name, Project, Region, Protocols, Origins (with associated Workload Types), and Routing Rules.
3.  **Cross-Resource Linking:** Ensure all Terraform resources are correctly linked using reference syntax (e.g., `service = google_compute_backend_service.example.id`) rather than hardcoding names.
4.  **Directory Isolation:** Always generate HCL code inside a dedicated, isolated subdirectory named after the architecture (e.g., `/gfe/deployments/{architecture_name}/`) to avoid stale state or resource name pollution.
5.  **Resource Prefixing:** Ensure all Google Cloud resource names in the generated HCL are dynamically prefixed with the Architecture Name (either via input variables or string interpolation) to guarantee global uniqueness and prevent 409 resource conflicts.
6.  **Lowercase Naming Only:** Infrastructure Manager and Google Cloud APIs are strict on resource naming. The architecture name, deployment IDs, and all generated resource names MUST be strictly lowercase and match `^[a-z](?:[-a-z0-9]{0,61}[a-z0-9])?$`. If the user provides a name with uppercase characters, convert it to lowercase automatically before using it in the configuration.

---

## Terraform Syntax & Google Cloud API Constraints

To prevent validation and deployment errors, always adhere to the following Google Cloud provider constraints:

1.  **Cloud Armor (`google_compute_security_policy`)**:
    *   **Default Action**: Do NOT use `default_rule_action = "..."` at the top level. You must explicitly define the default action as a `rule` block with priority `2147483647` and action `allow` (or `deny`).
    *   **Rate Limiting Action**: Use `action = "throttle"` instead of `rate-based-ban` for rate limit rules. This ensures compatibility across different API/provider versions.
    *   **Cloud Armor Edge Constraints**: `type = "CLOUD_ARMOR_EDGE"` policies (required for Backend Buckets) DO NOT support `rate_limit_options`. Only use standard `allow` or `deny` rules. Do not generate rate limiting configurations for backend buckets.
2.  **Backend Buckets (`google_compute_backend_bucket`)**:
    *   **Cache Key Policy**: Do NOT include a `cache_key_policy` block (e.g., trying to set `include_query_string = false`). Backend buckets do not support these arguments; query strings are automatically ignored by default when using `CACHE_ALL_STATIC`.
    *   **Default TTL Limits**: The `cdn_policy.default_ttl` cannot be greater than the `max_ttl`. If you set `default_ttl` to a value larger than the default `86400` (e.g., the recommended `2592000` / 30 days for static objects), you MUST explicitly set `max_ttl` to a value equal to or larger than `default_ttl` (e.g., `31536000` / 365 days).
3.  **Backend Services (`google_compute_backend_service`)**:
    *   **Origin Header TTLs**: If using `cache_mode = "USE_ORIGIN_HEADERS"`, you MUST omit `default_ttl` and `client_ttl` from the `cdn_policy` block. Specifying them will cause validation errors.
    *   **Request Coalescing**: Avoid using `request_coalescing = true` inside the `cdn_policy` of backend services unless verified to be supported by the active provider version.
4.  **Provider Version**:
    *   Always configure the `required_providers` block to use the Google provider version `~> 5.0` (or newer) to ensure rate-limiting features are correctly supported.

---

## Workload Profile Map (The Source of Truth)

| Workload Type | `enable_cdn` | `cdn_policy.cache_mode` | `default_ttl` | `max_ttl` | Cache Key Policy | WAF Protection (Cloud Armor) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Static Images / Objects** | `true` | `CACHE_ALL_STATIC` | `2592000` (30d) | `31536000` (365d) | Host + Protocol + Path (Ignore Query Strings) | None (Rate Limiting unsupported on CLOUD_ARMOR_EDGE) |
| **Cacheable API**| `true` | `USE_ORIGIN_HEADERS` | Omitted (Managed by Origin) | Omitted | **Include Query Strings** | OWASP (SQLi/XSS/LFI) + Rate Limit (100 RPM) |
| **Uncacheable API / Transactions**| `false`| N/A | N/A | N/A | N/A | OWASP (SQLi/XSS/RCE/Session Fixation) + Strict Rate Limit (30 RPM) + Bot Management |
| **Dynamic Web (SSR)** | `true` | `USE_ORIGIN_HEADERS` | Omitted (Managed by Origin) | Omitted | Host + Protocol + Path (Bypass on session cookie) | OWASP (SQLi/XSS/CSRF/Shellshock) + Rate Limit (120 RPM) |

---

## The Generation Workflow

1.  **Consume Spec:** Read the provided Design Spec carefully.
2.  **Prepare Directory Structure:** Create the dedicated subdirectory `/gfe/deployments/{architecture_name}/`.
3.  **Assemble HCL:**
    *   Generate a `variables.tf` and `terraform.tfvars` defining the input variables (`architecture_name`, `project_id`, `region`, etc.) to dynamically parameterize the blueprint.
    *   Generate the `terraform` and `provider` blocks in `main.tf`.
    *   For each origin, create the appropriate backend resource (`backend_bucket`, `backend_service`, or `region_network_endpoint_group`), dynamically prefixing the `name` field using the architecture name prefix, and injecting properties from the **Workload Profile Map**.
    *   Create the `google_compute_security_policy` resources for each backend using the WAF rules defined in the map, with dynamic prefixing.
    *   Create the `google_compute_url_map` using the provided path and header-based routing rules.
    *   Create the frontend resources (`target_http_proxy` / `target_https_proxy` with `ssl_certificates`, and `global_forwarding_rule`), with dynamic prefixing.
4.  **Output Code:** Provide the complete, finalized `main.tf`, `variables.tf`, and `terraform.tfvars` files to the user. Do not include conversational filler; focus on the technical integrity of the code.
5.  **Hand-off:** Once the code is output, state the next action (Download Files or Deploy Configuration) and transition to `references/managed-deployment.md` (specifically Phase 2 Option A) to guide the user through deployment pre-checks and execution.
