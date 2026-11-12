# Google Cloud global external Application Load Balancer Managed Actuation Guidelines

This reference document details how to deploy finalized global external Application Load Balancer configurations (Terraform via Infrastructure Manager or gcloud scripts), including performing mandatory IAM pre-checks to ensure deployment success.

---

## The 2-Phase Actuation Workflow

### Phase 1: IAM Pre-checks (Mandatory)
Before executing any deployment, you MUST verify that your acting identity has the necessary permissions. Failing to do so will result in half-provisioned infrastructure and orphaned resources.

1.  **Identity Identification:** Find the active identity using `gcloud config get-value account`.
2.  **Permission & Role Validation:** Check for the following permissions and
    roles on the target project:
    *   `resourcemanager.projects.get` (Read project metadata)
    *   `roles/compute.admin` (Full access to Cloud Load Balancing, Cloud CDN,
        and Cloud Armor WAF)
    *   *If using Terraform (via Infrastructure Manager):*
        *   `roles/config.admin` (Infrastructure Manager Administrator)
        *   `iam.serviceAccounts.actAs` (Permission to act as the deployment
            service account, e.g., `roles/iam.serviceAccountUser`)
3.  **Service Account Pre-check:** Infrastructure Manager runs deployments using
    a user-managed service account. You must verify that:
    *   A user-managed service account exists in the project (create one if none
        is provided; do not pass the Google-managed service agent
        `service-{project_number}@gcp-sa-config.iam.gserviceaccount.com` to
        `--service-account`).
    *   The service account has `roles/config.agent` (Infra Manager Agent) plus
        resource-provisioning roles (`roles/editor` or `roles/owner`, or
        granular admin roles such as `roles/compute.admin` and
        `roles/storage.admin`).

---

### Phase 2: Actuation (Choose based on format)

#### Option A: If using Terraform (via Infrastructure Manager)
Infrastructure Manager is Google's managed service for deploying Terraform configurations. It guarantees remote state management and lock enforcement.

1.  **Cleanup Local State:** Ensure any local `.terraform` directory is deleted before deploying, as Infrastructure Manager will fail otherwise:
    ```bash
    rm -rf {local_source_dir}/.terraform
    ```
2.  **Execution:** Run the `gcloud infra-manager deployments apply` command. You MUST specify the `--service-account` to avoid validation errors, and you must have `iam.serviceAccounts.actAs` permission on it. Always include the `--import-existing-resources` flag:
    ```bash
    gcloud infra-manager deployments apply projects/{project_id}/locations/us-central1/deployments/{deployment_id} \
        --local-source="{local_source_dir}" \
        --service-account="{service_account_email}" \
        --import-existing-resources
    ```
3.  **Status Monitoring:** Poll the deployment status until it reaches `ACTIVE`. Run:
    ```bash
    gcloud infra-manager deployments describe projects/{project_id}/locations/us-central1/deployments/{deployment_id}
    ```
4.  **Teardown Instructions:** Always provide the user with the exact command to tear down the infrastructure if they want to clean up:
    ```bash
    gcloud infra-manager deployments delete projects/{project_id}/locations/us-central1/deployments/{deployment_id}
    ```

#### Option B: If using gcloud CLI Script
If the user chose the gcloud script format:

1.  **Permissions Check:** Ensure the active identity has `roles/compute.admin`
    and `roles/storage.admin` (if using Google Cloud Storage bucket).
2.  **Execution:** Instruct the user to save the generated script as `deploy.sh` and execute it:
    ```bash
    chmod +x deploy.sh
    ./deploy.sh
    ```
3.  **Teardown Instructions:** Provide the accompanying `destroy.sh` script to tear down the resources in exact reverse dependency order.
