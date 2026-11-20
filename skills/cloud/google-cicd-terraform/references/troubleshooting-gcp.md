# Troubleshooting GCP-Terraform Errors

A guide to identifying and resolving common errors encountered when managing GCP
and CI/CD resources with Terraform.

## Table of Contents

*   [403 Forbidden (Permission Denied)](#403-forbidden-permission-denied) (Lines
    21-41)
*   [Cloud Build Trigger `INVALID_ARGUMENT` with Custom Service Account](#cloud-build-trigger-invalid_argument-with-custom-service-account)
    (Lines 43-55)
*   [Developer Connect Connection and Repository Link Errors](#developer-connect-connection-and-repository-link-errors-github-gitlab-bitbucket)
    (Lines 57-73)
*   [Cloud Run Binary Authorization Policy Rejection (`IMAGE_UNTRUSTED`)](#cloud-run-binary-authorization-policy-rejection-image_untrusted)
    (Lines 75-89)
*   [Resource In Use and Deletion Delays](#resource-in-use-and-deletion-delays)
    (Lines 91-107)
*   [GCS State Locking](#gcs-state-locking) (Lines 109-123)
*   [Provider Schema Inspection](#provider-schema-inspection) (Lines 125-136)

## 403 Forbidden (Permission Denied)

**Symptoms**: `Error 403: Permission '...' denied on resource '...'`.

**Fixes**:

1.  **Service Usage API**: Ensure the `serviceusage.googleapis.com` API is
    enabled in the project.
2.  **Missing Roles**: Verify the principal (Service Account or User) has the
    required IAM roles. Use `google_project_iam_member` to add them:
    *   Artifact Registry repository/image push: `roles/artifactregistry.admin`
        or `roles/artifactregistry.writer`
    *   Developer Connect token fetch (`fetchReadToken`):
        `roles/developerconnect.readTokenAccessor` or
        `roles/developerconnect.admin`
    *   Cloud Build trigger creation with custom SA:
        `roles/cloudbuild.builds.editor` and `roles/iam.serviceAccountUser` on
        the custom service account
    *   GKE cluster credentials & deployment: `roles/container.developer`
3.  **Propagation Delay**: IAM changes can take up to 60 seconds to propagate.
    Retry the operation.

## Cloud Build Trigger `INVALID_ARGUMENT` with Custom Service Account

**Symptoms**: `Error 400: invalid argument: if 'build.service_account' is
specified, the build must either (a) specify 'build.logs_bucket', (b) use the
CLOUD_LOGGING_ONLY logging option, or (c) use the NONE logging option`.

**Fixes**:

1.  Whenever `service_account` is set on `google_cloudbuild_trigger`, ensure the
    referenced `cloudbuild.yaml` or inline `build` block sets
    `options { logging = "CLOUD_LOGGING_ONLY" }`.
2.  Ensure the custom service account has `roles/logging.logWriter` on the
    project.

## Developer Connect Connection and Repository Link Errors (GitHub, GitLab, Bitbucket)

**Symptoms**: `Error waiting for Creating GitRepositoryLink: PERMISSION_DENIED`
or `FAILED_PRECONDITION: Connection is not in COMPLETE state`.

**Fixes**:

1.  **Complete OAuth/App Installation**: A `google_developer_connect_connection`
    (configured with `github_config`, `gitlab_config`, or
    `bitbucket_cloud_config`) must have its installation state completed in the
    GCP Console before creating a
    `google_developer_connect_git_repository_link`.
2.  **Service Agent Role**: Ensure the Cloud Build Service Agent
    (`service-<PROJECT_NUMBER>@gcp-sa-cloudbuild.iam.gserviceaccount.com`) has
    `roles/developerconnect.admin` or `roles/developerconnect.readTokenAccessor`
    before creating a `google_cloudbuild_trigger` with
    `developer_connect_event_config`.

## Cloud Run Binary Authorization Policy Rejection (`IMAGE_UNTRUSTED`)

**Symptoms**: Deployment to `prod` Cloud Run service fails with `Admission
webhook denied the request: Image ... denied by Binary Authorization default
policy: Image ... is not attested by attestor ...`.

**Fixes**:

1.  Resolve the immutable image digest (`@sha256:...`) in Artifact Registry.
2.  Verify whether an attestation exists using `gcloud container binauthz
    attestations list --artifact-url="<IMAGE_URI>@<DIGEST>"`.
3.  Create the required attestation with
    `gcloud container binauthz attestations create` (or via a Cloud Build KMS
    signing step) before deploying to `prod` with
    `binary_authorization = "default"`.

## Resource In Use and Deletion Delays

**Symptoms**: `Error: Resource ... is still in use` or
`Error deleting Subnetwork: ...`.

**Fixes**:

1.  **Dependency Chains**: GCP often has hidden dependencies. For example, a
    `google_compute_subnetwork` cannot be deleted if a `google_compute_address`
    or a VM is still using it.
2.  **Force Destroy**: For `google_storage_bucket` or
    `google_artifact_registry_repository`, use `force_destroy = true` (or
    `cleanup_policy_dry_run = false`) if you want Terraform to delete a
    non-empty container in ephemeral test environments.
3.  **Sequential Deletion**: Sometimes `terraform destroy` struggles with
    complex VPC peering. Try destroying resources in smaller chunks if a timeout
    occurs.

## GCS State Locking

**Symptoms**:
`Error: Error acquiring the state lock: ... GCS bucket ... already locked`.

**Fixes**:

1.  **Check for Active Processes**: Ensure no other developer or CI job is
    running.
2.  **Manual Unlock**: If a process crashed and left the lock behind, use the
    force-unlock command with the Lock ID provided in the error message:

    ```bash
    terraform force-unlock <LOCK_ID>
    ```

## Provider Schema Inspection

To see exactly what fields a resource supports and avoid "Attribute not found"
errors:

```bash
# Export the full provider schema to JSON
terraform providers schema -json > schema.json

# Use jq to find specific resource details
cat schema.json | jq '.provider_schemas["registry.terraform.io/hashicorp/google"].resource_schemas["google_cloudbuild_trigger"]'
```
