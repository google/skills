---
name: google-cicd-terraform
metadata:
  version: "1.0.0"
  category: DevOps
description: >-
  Architect, provision, and troubleshoot infrastructure on Google Cloud using Terraform. This skill ensures best practices like GCS backend usage and least-privilege IAM are followed. Enforces Google's Cloud Foundation Fabric patterns and rigorous validation protocols to ensure secure, idempotent, and scalable deployments across environments. Activate when the user requests infrastructure changes, pipeline design involving Terraform, or debugging Terraform issues.
  DO NOT use when deploying application code or container images directly via `gcloud` or `kubectl` without Terraform (use `google-cicd-deploy`), designing high-level CI/CD architecture before choosing an IaC tool (use `google-cicd-pipeline-design`), or managing Cloud Deploy releases and rollouts via `clouddeploy.yaml` (use `google-cicd-release-orchestration`).
---

# Terraform GCP Skill

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

This skill provides expert-level guidance for architecting, deploying, and
managing GCP infrastructure using Terraform.

## Prerequisites

Ensure the following prerequisites are satisfied before executing live commands:

*   **CLI & Billing**: Install Terraform (`>= 1.6.0`), `tflint`, and the
    [Google Cloud SDK](https://docs.cloud.google.com/sdk/docs/install.md.txt)
    (`gcloud`), and attach an active **billing account** to the target project.
*   **Authentication & Project**: Authenticate via `gcloud auth login` and
    `gcloud auth application-default login` (or set
    `GOOGLE_APPLICATION_CREDENTIALS` for CI service accounts), then set the
    project and region (e.g., `us-central1`; see
    [Cloud Locations](https://cloud.google.com/about/locations)):
    `gcloud config set project <PROJECT_ID>` and
    `gcloud config set compute/region <REGION>`.
*   **API Enablement & IAM**: Enable required APIs (with user confirmation) via
    `gcloud services enable cloudresourcemanager.googleapis.com
    serviceusage.googleapis.com iam.googleapis.com storage.googleapis.com
    cloudbuild.googleapis.com developerconnect.googleapis.com
    artifactregistry.googleapis.com run.googleapis.com
    container.googleapis.com`, and follow least-privilege IAM roles per
    [iam-and-security.md](references/iam-and-security.md).

## 🎯 When to Use This Skill

-   Designing GCP Landing Zones (Projects, Folders, Shared VPCs).
-   Provisioning Google Cloud resources (GKE, Cloud Run, Cloud SQL, Spanner).
-   Setting up remote state management via **GCS Backend**.
-   Implementing IAM least-privilege via Terraform.
-   Troubleshooting `terraform plan` discrepancies in GCP (see
    [troubleshooting-gcp.md](references/troubleshooting-gcp.md)).

## 🏗️ Core Architecture: GCS Backend & State

**Always** use a GCS backend for state. Local state is strictly for local
prototyping and must never be committed. If local state directory is used, add
it to .gitignore.

### Standard Backend Configuration

```terraform
terraform {
  backend "gcs" {
    # Variables (var.*) are not allowed in backend blocks; set literal values
    # or pass via: terraform init -backend-config="bucket=tf-state-<PROJECT_ID>"
    bucket = "tf-state-<PROJECT_ID>"
    prefix = "terraform/state/<ENVIRONMENT>"
  }
}
```

Note: The GCS bucket must have Object Versioning enabled to allow recovery from
accidental state corruption or overlapping writes.

### Required Provider Version

Use the Google Cloud Terraform provider version 7.20.0 or higher. This skill
utilizes features (e.g., Developer Connect) introduced in Google Provider
v7.20.0.

```terraform
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 7.20.0"
    }
  }
}
```

To retrieve the latest version of the Google provider, use the following
command:

```bash
curl -s https://registry.terraform.io/v1/providers/hashicorp/google | jq -r .version
```

## 🛠️ Execution Protocol (Safety First)

The Agent must follow this lifecycle for every infrastructure change to ensure
idempotency and prevent production outages:

1.  Initialize (`terraform init`):

    -   Verify backend connectivity.

    -   Ensure provider plugins are downloaded and versions are locked in
        `.terraform.lock.hcl`.

2.  Validate (`terraform validate` & `tflint`):

    -   Check for internal HCL consistency.

    -   Run `tflint` with the Google plugin to catch cloud-specific deprecated
        fields or non-optimal configurations.

3.  Plan (`terraform plan -out=tfplan`):

    -   Generate a speculative execution plan.

    -   Mandatory Step: The Agent must summarize the plan for the user,
        specifically highlighting any Destroy actions.

4.  Apply (`terraform apply tfplan`):

    -   Strict Constraint: Only execute the application after the user provides
        explicit manual confirmation.

## 🔍 Live Provider Documentation Lookup

To prevent hallucinations regarding new fields or deprecated attributes, the
Agent must verify the grounded truth of the provider schema.

### Schema Inspection via CLI

The primary command for retrieving the machine-readable schema of the currently
initialized providers is:

```bash
$ terraform providers schema -json
```

## 🛡️ GCP-Specific Standards

1.  **Resource Naming & "Main" Pattern**: To maintain a clean module interface,
    use the main identifier for singleton resources (the primary resource the
    module is named after). Use underscores for identifiers and hyphens for
    names (see [naming-conventions.md](references/naming-conventions.md)).

    ```terraform
    resource "google_compute_network" "main" {
      name                    = "${var.prefix}-vpc"
      auto_create_subnetworks = false
    }
    ```

2.  **IAM Management** (see
    [iam-and-security.md](references/iam-and-security.md) and
    [gcp-networking-patterns.md](references/gcp-networking-patterns.md)):

    -   Never use `google_project_iam_policy`: This resource is authoritative
        and replaces the entire IAM policy for the project. It is the #1 cause
        of accidental lockouts.

    -   Prefer `google_project_iam_member` or `google_project_iam_binding`:

        -   `google_project_iam_member` is additive and safely grants a role to
            a single member.
        -   `google_project_iam_binding` is authoritative for a single role.
            It's useful for managing all members of a role, but be aware it
            overwrites existing members for that role.

    -   Shared VPC: Always distinguish between Host projects (where the network
        lives) and Service projects (where resources consume the network).

    -   Private Google Access: Subnets should always have
        private_ip_google_access = true.

    -   Workload Identity: Prefer GKE Workload Identity over static Service
        Account JSON keys.

3.  **Cloud Build Triggers with Developer Connect**: When using Developer
    Connect git repository links, use `developer_connect_event_config` — NOT
    `repository_event_config`. The `repository_event_config` block is for Cloud
    Build v2 repository connections and will not work with Developer Connect
    resources. An example block to create a Cloud Build trigger with Developer
    Connect git repository link is as follows:

    ```terraform
    resource "google_cloudbuild_trigger" "main" {
      developer_connect_event_config {
        git_repository_link = google_developer_connect_git_repository_link.main.id
        push {
          branch = var.trigger_branch
        }
      }
    }
    ```

4.  **Developer Connect Connection (GitHub, GitLab, Bitbucket)**: When
    configuring `google_developer_connect_connection`, configure the block
    matching the user's source control provider (`github_config`,
    `github_enterprise_config`, `gitlab_config`, `gitlab_enterprise_config`,
    `bitbucket_cloud_config`, or `bitbucket_data_center_config`). If using
    `github_config`, always set `github_app` to `"DEVELOPER_CONNECT"` (using
    `"FIREBASE"` is incorrect and will cause triggers to fail).

    ```terraform
    resource "google_developer_connect_connection" "main" {
      location      = var.region
      connection_id = var.connection_id
      project       = var.project_id

      # Example for GitHub (use gitlab_config / bitbucket_cloud_config for GitLab / Bitbucket):
      github_config {
        github_app = "DEVELOPER_CONNECT" # CORRECT
        authorizer_credential {
          oauth_token_secret_version = "" # Populated after manual authorization
        }
      }

      depends_on = [google_project_service.main["developerconnect.googleapis.com"]]

      lifecycle {
        ignore_changes = [github_config[0].authorizer_credential]
      }
    }
    ```

5.  **Developer Connect Git Repository Link**: When configuring
    `google_developer_connect_git_repository_link`, use `parent_connection` and
    `git_repository_link_id` as required arguments.

    ```terraform
    resource "google_developer_connect_git_repository_link" "main" {
      location                = var.region
      parent_connection       = google_developer_connect_connection.main.connection_id
      git_repository_link_id  = "my-repo-link"
      clone_uri               = var.git_repo_uri
    }
    ```

## 📂 Directory Structure

Follow this standard (see
[style-and-structure.md](references/style-and-structure.md)) to ensure
compatibility with Antigravity (AGY) discovery and Google best practices:

```
.
└── terraform/
    ├── main.tf              # Entry point / Resource definitions
    ├── variables.tf         # Typed variables with units and descriptions
    ├── outputs.tf           # Resource ID outputs (no direct input pass-through)
    ├── versions.tf          # Provider version pinning
    ├── network.tf           # (Optional) Grouped networking resources
    ├── examples/            # Example usage for modules
    ├── files/               # Static files (startup scripts, etc.)
    ├── templates/           # .tftpl templates
    ├── scripts/             # Scripts called by Terraform
    └── helpers/             # Scripts NOT called by Terraform
```

## ⚠️ Anti-Patterns (Do NOT do these)

-   ❌ Legacy GitHub Triggers: Do not use the legacy `github` block in
    `google_cloudbuild_trigger`. Always use `developer_connect_event_config`.

-   ❌ Hardcoded IDs: Never hardcode Project IDs. Use variables or a
    `data "google_project"` source.

-   ❌ Service Account Keys: Never generate or store .json keys. Use Workload
    Identity Federation or the default metadata server.

-   ❌ Broad Scopes: Avoid cloud-platform scopes for GKE nodes; use fine-grained
    IAM roles instead.

-   ❌ Uppercase Types: Terraform variable types must be lowercase (e.g.,
    `type = string` not `type = STRING`).

## 🧪 Testing Strategy

-   Consult [testing-and-mocking.md](references/testing-and-mocking.md) for
    mocked plan validation and `terraform test` patterns.
-   Static Analysis: Use checkov, trivy, or terrascan to catch insecure GCP
    configurations (e.g., public GCS buckets).
-   Integration Testing: Use terraform test (v1.6+) to assert that GCP labels
    and network tags are correctly applied to resources before full deployment.

## 📚 Reference Guides

-   [naming-conventions.md](references/naming-conventions.md): Resource
    identifier and GCP naming rules.
-   [style-and-structure.md](references/style-and-structure.md): Module layout,
    formatting, and variable typing standards.
-   [iam-and-security.md](references/iam-and-security.md): Least-privilege IAM,
    Workload Identity, and Secret Manager integration.
-   [gcp-networking-patterns.md](references/gcp-networking-patterns.md): Custom
    VPCs, Shared VPC, and Private Service Connect patterns.
-   [testing-and-mocking.md](references/testing-and-mocking.md): Terraform
    unit/integration testing (`*.tftest.hcl`) and static analysis.
-   [troubleshooting-gcp.md](references/troubleshooting-gcp.md): Common GCP
    Terraform errors and remediation steps.

## Resource Cleanup & Teardown

Provisioned GKE clusters, Cloud Run services, Cloud SQL instances, Artifact
Registry repositories, and GCS state buckets incur charges (an active billing
account is required even within free tiers; see
[Google Cloud Pricing](https://cloud.google.com/pricing)). Always generate and
summarize a speculative destroy plan (`terraform plan -destroy -out=tfdestroy`)
and obtain explicit manual confirmation from the user before running
`terraform apply tfdestroy` (or `gcloud projects delete <PROJECT_ID>` for
ephemeral sandbox projects).
