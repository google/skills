# IAM and Security Standards for GCP

Prevent outages and security breaches by following additive IAM patterns,
dedicated CI/CD service accounts, and Workload Identity.

## Table of Contents

-   [Additive vs. Authoritative IAM](#additive-vs-authoritative-iam) (Lines
    17-37)
-   [CI/CD Pipeline Service Accounts](#cicd-pipeline-service-accounts-cloud-build-developer-connect-artifact-registry-and-binary-authorization)
    (Lines 39-84)
-   [Workload Identity (GKE and Agent Registry SPIFFE Identity)](#workload-identity-gke-and-agent-registry-spiffe-identity)
    (Lines 86-106)
-   [Organization Policy Constraints](#organization-policy-constraints) (Lines
    108-127)

## Additive vs. Authoritative IAM

**NEVER** use authoritative resources (`google_project_iam_policy` or
`google_project_iam_binding`) for core projects unless you are explicitly
managing the *entire* policy and understand the risk of lockouts.

Resource                     | Type                        | Impact                                      | Usage
:--------------------------- | :-------------------------- | :------------------------------------------ | :----
`google_project_iam_member`  | **Additive**                | Adds a single member/role. Safe.            | **Preferred**
`google_project_iam_binding` | **Authoritative (Role)**    | Overwrites all members for a specific role. | Use with caution.
`google_project_iam_policy`  | **Authoritative (Project)** | Overwrites the entire project IAM policy.   | **BANNED** for general use.

### Example: Safe Additive IAM

```terraform
resource "google_project_iam_member" "storage_admin" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.main.email}"
}
```

## CI/CD Pipeline Service Accounts (Cloud Build, Developer Connect, Artifact Registry, and Binary Authorization)

Never use the legacy default Cloud Build service account
(`<PROJECT_NUMBER>@cloudbuild.gserviceaccount.com`) for production triggers.
Provision a dedicated Cloud Build runner service account (`cloudbuild-runner`)
with least-privilege additive IAM roles:

```terraform
resource "google_service_account" "cloudbuild_runner" {
  project      = var.project_id
  account_id   = "cloudbuild-runner"
  display_name = "Dedicated Cloud Build Runner Service Account"
}

locals {
  cloudbuild_runner_roles = [
    "roles/logging.logWriter",                    # Required for CLOUD_LOGGING_ONLY
    "roles/artifactregistry.writer",              # Push images & export SPDX SBOMs
    "roles/developerconnect.readTokenAccessor",   # Fetch read tokens for GitHub/GitLab/Bitbucket
    "roles/run.developer",                        # Deploy Cloud Run revisions
    "roles/container.developer",                  # Deploy to GKE clusters
    "roles/binaryauthorization.attestorsVerifier" # Verify Binary Authorization attestors on prod
  ]
}

resource "google_project_iam_member" "cloudbuild_runner_permissions" {
  for_each = toset(local.cloudbuild_runner_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.cloudbuild_runner.email}"
}

# Scope serviceAccountUser strictly to the target runtime SA (never project-wide)
resource "google_service_account_iam_member" "cloudbuild_runner_act_as_runtime" {
  service_account_id = google_service_account.gsa.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.cloudbuild_runner.email}"
}

# Grant Cloud Build Service Agent least-privilege access to read Developer Connect repository links
resource "google_project_iam_member" "cloudbuild_service_agent_devconnect" {
  project = var.project_id
  role    = "roles/developerconnect.readTokenAccessor"
  member  = "serviceAccount:service-${var.project_number}@gcp-sa-cloudbuild.iam.gserviceaccount.com"
}
```

## Workload Identity (GKE and Agent Registry SPIFFE Identity)

Bind Kubernetes Service Accounts (KSA) to Google Service Accounts (GSA) without
managing JSON keys. For AI Agents and MCP Servers on GKE, pair Workload Identity
with the `iam.gke.io/spiffe-identity-type: "agent-identity"` pod template
annotation for Google Cloud Agent Registry discovery.

```terraform
# 1. The Google Service Account
resource "google_service_account" "gsa" {
  account_id   = "app-workload-sa"
  project      = var.project_id
}

# 2. The IAM Binding for Workload Identity
resource "google_service_account_iam_member" "workload_identity_user" {
  service_account_id = google_service_account.gsa.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${var.k8s_namespace}/${var.k8s_sa_name}]"
}
```

## Organization Policy Constraints

Common constraints to enforce during `terraform validate` or `plan`:

-   `constraints/compute.disableSerialPortAccess`: Prevents unencrypted console
    access.
-   `constraints/compute.vmExternalIpAccess`: Blocks external IPs for VMs.
-   `constraints/iam.allowedPolicyMemberDomains`: Restricts IAM to specific
    Workspace/Cloud Identity domains.

```terraform
resource "google_project_organization_policy" "disable_serial_port" {
  project    = var.project_id
  constraint = "constraints/compute.disableSerialPortAccess"

  boolean_policy {
    enforced = true
  }
}
```
