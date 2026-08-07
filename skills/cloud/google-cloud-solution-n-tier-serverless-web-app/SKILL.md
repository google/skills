---
name: google-cloud-solution-n-tier-serverless-web-app
metadata:
  category: MultiProductSolutions
description: >-
  Guides agents to interactively discover customer requirements for a Secure n-tier serverless web application and generate a tailored cloud multi-product solution that incorporates opinionated best practices and architecture guidance. Use when users need agentic assistance with designing and creating a multi-product solution in the cloud for Secure n-tier serverless web application. Don't use when designing VM or GKE-based architectures or when not using Google Cloud.
---

<!-- disableFinding(all) -->
<!-- mdlint off -->

# Secure n-tier serverless web application with strict private application tiers

This skill guides agents through the workflow of designing and implementing a
secure serverless web application with as many architectural design layers as
specified by the user. It uses Cloud Run for the serverless layers and Cloud SQL
for PostgreSQL as the data layer. A three-tier web application might be
represented in three architectural layers: a Cloud Run presentation layer, a
Cloud Run application layer, and a Cloud SQL for PostgreSQL database layer.

The architecture enforces strict physical and network isolation across all tiers (T1 to TN):

*   **Tier 1 presentation tier (frontend / reverse proxy)**: Public-facing UI rendering/gateway service (Cloud Run). Exposes the entry point via Cloud Load Balancing and routes requests downstream to internal tiers privately via Direct VPC Egress.
*   **Tier 2..N application tier (internal microservices / business logic)**: Private application services (Cloud Run). 100% isolated from the internet (Ingress: VPC-internal, `INGRESS_TRAFFIC_INTERNAL_ONLY`), reachable exclusively via upstream VPC routing (`egress = "ALL_TRAFFIC"` with Private Google Access on the subnet for `*.run.app` URLs, or `egress = "PRIVATE_RANGES_ONLY"` via an internal Application Load Balancer).
*   **Data tier**: Private Cloud SQL for persistent data and Memorystore for
    Redis for caching, reachable exclusively from authorized application tiers.

## Workflow

> [!TIP]
> **Optional MCP Server Integration**: If your AI coding client supports the **Model Context Protocol (`MCP`)**, you can connect the [Google Developer Knowledge MCP Server](https://developers.google.com/knowledge/mcp) (`npx -y @google/mcp-developer-knowledge-server`) to dynamically query real-time Google Cloud documentation (`cloud.google.com/docs`) alongside this skill's offline knowledge base (`references/related-guidance.md`).

The solution design and implementation workflow is divided into the following
phases:

*   **Phase 1: Requirements discovery and analysis**: Analyze the workload's
    requirements, constraints, dependencies, and current state.
*   **Phase 2: Solution design & IaC drafting**: Build a technology stack, architecture, and deployment configuration for the workload. **IMPORTANT: You should strongly recommend and offer to generate the complete Terraform code (based on `assets/main.tf` and adhering to all Phase 3 specifications) alongside the solution architecture during this phase.** This allows the user to immediately review and iteratively modify the code as the conversation continues. However, if the user explicitly states they do not want code, confirm their preference before proceeding.
*   **Phase 3: Implementation plan & iterative refinement**: Modify and refine the generated Terraform code and deployment instructions as the conversation and user feedback evolve.
*   **Phase 4: Solution validation**: Validate that the deployment meets the
    requirements of the workload.

--------------------------------------------------------------------------------

### Phase 1: Requirements discovery and analysis

To prevent multi-turn interview fatigue and maintain trajectory determinism across evaluations, adopt an **opinionated 80% default golden path** unless the user explicitly requests deviations:

1.  **Default Golden Path Configuration (`80% Baseline`)**:
    *   **Architecture**: Secure 3-tier serverless pipeline (`frontend` Cloud Run -> `backend application` Cloud Run -> `Cloud SQL PostgreSQL`).
    *   **Region**: `us-central1`.
    *   **Database**: Cloud SQL for PostgreSQL (`POSTGRES_18`) Enterprise Edition via Private Service Connect (`psc_enabled = true`).
    *   **Edge Protection**: Global external Application Load Balancer with Cloud Armor WAF (`sqli-v33-stable`) and Cloud CDN (`enable_cdn = true`).
    *   **Networking & Security**: Direct VPC Egress (`ALL_TRAFFIC`), `run.app.` Cloud DNS private zone, least-privilege egress firewalls (`TCP 5432, 443`), and Cloud SQL Auth Proxy sidecar (`DB_SOCKET_PATH` with IAM Auth).

2.  **Disambiguation Protocol (`Maximum 2 Optional Questions`)**:
    If the user's initial prompt leaves requirements open-ended (and is not fast-forwarding with exact specs), do **not** present a multi-topic questionnaire. Only ask up to **2 optional disambiguation questions** concisely before confirmation:
    1.  **Load Balancer & Residency Topology**: Do you require a **Global Application Load Balancer with Cloud CDN** (default for worldwide users), or a **Regional Application Load Balancer without CDN** (for strict EU/regional data residency compliance)?
    2.  **In-Memory Caching Tier**: Should we provision an optional **Memorystore for Redis** caching tier (`Private Services Access`) alongside Cloud SQL to accelerate read queries?

3.  **Verify & Confirm**: Present the confirmed 3-tier golden path decomposition to the user and request confirmation before proceeding to Phase 2 (or fast-forward automatically when instructed).

### Phase 2: Solution design

1.  **Retrieve the 9 architectural security boundaries and report audit checklist from `references/non-negotiable-architectural-rules.md` and product mapping from `references/related-guidance.md`**. *Important*: Use the retrieved content to ground your design and verify the report audit checklist before TF generation (`assets/main.tf` is the Single Source of Truth for exact HCL). If the [Google Developer Knowledge MCP Server](https://developers.google.com/knowledge/mcp) is connected, query docs dynamically in real time.

2.  **Map components to Google Cloud products**: Map your confirmed decomposition directly to Google Cloud products based on Section 11 ("Comprehensive product mapping specifications") inside `references/related-guidance.md`:
    *   **Public Ingress & WAF**: global or regional external Application Load Balancer (`INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER`), Cloud Armor (`sqli-v33-stable`), Cloud CDN (if global Application Load Balancer). Note: When deploying a regional external Application Load Balancer, an explicit proxy-only subnet (`purpose = "REGIONAL_MANAGED_PROXY"`) is required in the VPC and `network` must be specified on the regional forwarding rule.
    *   **Internal compute tiers (T1 to TN)**: Cloud Run microservices (`INGRESS_TRAFFIC_INTERNAL_ONLY`), Direct VPC Egress configured with `egress = "ALL_TRAFFIC"`, Private Google Access enabled on the subnet, and a Cloud DNS Managed Private Zone (`google_dns_managed_zone`) for `run.app.` bound to `vpc_network` mapping `*.run.app` directly to Private Google Access VIPs (`199.36.153.4/30 / 199.36.153.8/30`) when calling internal `*.run.app` URLs (to prevent queries from resolving via public Google DNS to `216.58.x.x` and hitting `deny_all_egress` or failing VPC-internal ingress checks), or `egress = "PRIVATE_RANGES_ONLY"` when routing via an internal Application Load Balancer, deployed from specified/placeholder container image.
    *   **Private data tier**: Cloud SQL PostgreSQL via Private Service Connect + IAM DB Auth. If database caching was selected, add Memorystore Redis via Private Services Access. Depending on reliability requirements, specify either "Cloud SQL for PostgreSQL Enterprise edition instance" or a "Cloud SQL for PostgreSQL Enterprise Plus edition instance".
    *   **Secrets, Registry, & Security**: Secret Manager, Artifact Registry, least-privilege egress firewalls (explicitly permitting outbound TCP port 5432 to Cloud SQL PSC IP and TCP port 443 to Private Google Access VIPs `199.36.153.4/30, 199.36.153.8/30` on `allow_backend_db_egress` so the Cloud SQL Auth Proxy sidecar can query `sqladmin.googleapis.com` and exchange tokens for ephemeral IAM certs on startup without crashing), and optional VPC Service Controls.

3.  **Create architecture diagram**: Create a clean Mermaid format architecture diagram (`assets/output-template.md`) illustrating the multi-tier request and data flow across entry point, public reverse proxy, private microservice compute tiers, and private database/caching endpoints.

4.  **Draft solution architecture and generate Terraform & `gcloud` CLI code**:
    Compile the requirements, technical decomposition, product mapping,
    architecture diagram, design recommendations, AND the complete
    Infrastructure as Code (`Terraform based on assets/main.tf alongside a
    self-contained sequence of gcloud CLI deployment commands adhering to all
    Phase 3 mandatory specifications`) into a single Markdown file structured
    strictly per the standardized Google Cloud Solution Architecture output
    template at `assets/output-template.md` and present them to the user.
    When saving or outputting the report artifact, append an ISO 8601 UTC timestamp and ensure the filename strictly ends with the `.md` extension (`e.g., workload_name_architecture_report-20260701T212820Z.md`). Verify that all 9 security boundaries from `assets/main.tf` are documented cleanly in your report. 

5.  **Request review and iterate**: Present the solution architecture (and Terraform code, `gcloud` script, or validation script if generated) to the user and request feedback. Modify and refine both the architecture and code iteratively as the conversation continues.

--------------------------------------------------------------------------------

### Phase 3: Implementation plan

1.  **Retrieve relevant building block templates from the `assets/` directory**.
    *Important*: Use the code in `assets/main.tf` as the
    foundation for your Terraform implementation plan (`assets/output-template.md` for architecture structure).

2.  **Identify deployment prerequisites**:

    *   Required Google Cloud APIs (`run.googleapis.com`,
        `sqladmin.googleapis.com`, `redis.googleapis.com`,
        `servicenetworking.googleapis.com`, `secretmanager.googleapis.com`,
        `monitoring.googleapis.com`, `dns.googleapis.com`).
    *   Required IAM permissions (Project Editor, Security Admin, etc.).

3.  **Generate Infrastructure as Code (IaC) (`Architectural Specifications`)**: 
    Retrieve relevant architectural and hierarchy guidance from
    `references/non-negotiable-architectural-rules.md`. Base code strictly on the building blocks in
    `assets/main.tf` (`Section 5.1` for Tier 1, `Section 5.2` for Tiers 2..N), ensuring `database_version = "POSTGRES_18"` is preserved exactly. Do NOT generate from memory/v1 legacy resources or revert to older database versions like `POSTGRES_15`.

4.  **Write deployment instructions & README.md**: Draft comprehensive step-by-step deployment instructions (or a complete `README.md` artifact), ensuring you include:
    *   Instructions to initialize and apply Terraform (`terraform init`, `terraform apply`). **Zero-Install Environment Recommendation**: Explicitly recommend running `terraform` commands and your generated automated validation script inside **Google Cloud Shell** (`https://shell.cloud.google.com`), where `python3`, `gcloud`, and `terraform` are 100% pre-installed and authenticated out of the box so developers without local SDKs can deploy and validate immediately.
    *   **Step-by-Step `gcloud` CLI Deployment Commands (`Bottom-Up Wiring`)**: In Section 6.3 ("Step-by-step gcloud CLI deployment commands") inside `assets/output-template.md`, provide a complete, self-contained sequence of `gcloud` CLI commands required to deploy this exact architecture without Terraform. These commands must enforce reverse/bottom-up order (`VPC/subnets -> data tiers -> internal microservices -> public gateway -> load balancer`), specify `--database-version=POSTGRES_18` when provisioning Cloud SQL, and extract downstream container URLs (`gcloud run services describe... --format='value(status.url)'`) into shell variables to dynamically pass them via `--update-env-vars` into upstream services.
    *   Explanation of all Terraform variables, **explicitly including and documenting the `enable_vpc_sc` variable**.
    *   **Dedicated VPC Service Controls Guidance Section**: Provide specific instructions and gcloud commands for implementing an Org-level VPC-SC service perimeter around Cloud Run (`run.googleapis.com`), Cloud SQL (`sqladmin.googleapis.com`), and Secret Manager (`secretmanager.googleapis.com`) when `enable_vpc_sc = true`.
    *   Container image deployment strategies (specifying pre-existing image URLs or placeholder bootstrapping followed by CI/CD).
    *   Cloud DNS Managed Private Zone (`google_dns_managed_zone`) configuration for `run.app.` bound to `vpc_network`, mapping `*.run.app` directly to Private Google Access VIPs (`199.36.153.4/30 / 199.36.153.8/30`), alongside external DNS records and database schema initialization.

5.  **Request review**: Present the implementation plan to the user for
    approval. Iterate as needed.

--------------------------------------------------------------------------------

### Phase 4: Solution validation

1.  **Define solution verification steps & requirements**: During validation planning, mandate these 5 verification steps across any deployed environment:
    *   **SSL Provisioning**: Verify that the Google-managed SSL certificate (`google_compute_managed_ssl_certificate`) becomes `ACTIVE` (checking `--global` status or regional equivalents).
    *   **Frontend Ingress Block**: Verify that direct internet access targeting the Tier 1 Frontend's default `*.run.app` URL is blocked (`HTTP 403 Forbidden` from edge screening).
    *   **Backend Ingress Block**: Verify that direct internet access targeting internal compute tiers' `*.run.app` URLs (`INGRESS_TRAFFIC_INTERNAL_ONLY`) is blocked across all internal microservice tiers (`HTTP 404 Not Found` or `HTTP 403 Forbidden`).
    *   **Frontend Public Access via Application Load Balancer**: Verify that accessing the custom domain routes successfully to the presentation tier via the Application Load Balancer (`HTTP 200` to `399`).
    *   **Edge WAF Protection**: Verify that a simulated SQL injection request (`/?id=1%20OR%201=1` on the custom domain) is intercepted and blocked (`HTTP 403 Forbidden` from Cloud Armor).
    *   **Private Server-to-Server Connectivity**: Verify via Cloud Run application logs (`Logs Explorer`) and database connection pooling telemetry (`Cloud SQL Query Insights`) that tier 1 -> tier 2 -> data tier queries succeed over private VPC fiber (`Direct VPC Egress` + `Private Service Connect` / `Private Services Access`).

2.  **Generate tailored automated validation script**: Rather than relying on a static pre-packaged script, **generate a custom automated validation script** (e.g., self-contained Python validation script using standard built-in `urllib` / `subprocess` libraries, or a cross-platform bash/PowerShell script) customized precisely to the user's deployed domain, SSL certificate name, and exact multi-tier `*.run.app` URIs.

3.  **Provide cross-platform execution guidance**: Explain how the user can execute the generated script across their target OS (`macOS`, `Linux`, `Windows PowerShell`, or zero-install **Google Cloud Shell** (`https://shell.cloud.google.com`)).

4.  **Compile validation report**: Document the validation checks, the generated verification script code, execution commands, and expected outcomes in Section 6.4 ("Solution verification guide and custom automated validation script") inside `assets/output-template.md`.

5.  **Conduct validation and finalize**: Assist the user in running the generated verification script, inspecting logs, and troubleshooting any DNS or WAF propagation issues. Request final approval.
