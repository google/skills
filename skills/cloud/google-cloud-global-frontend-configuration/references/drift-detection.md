# Google Cloud Global Load Balancer Drift Detection Guidelines

This reference document details how to detect, analyze, and reconcile configuration drift in Google Cloud Global External Application Load Balancer infrastructure using Infrastructure Manager previews.

---

## Core Directives - Behavioral Rules

1. **Safety First:** Never modify production infrastructure directly during drift detection. Always generate a **preview** first to safely inspect differences.
2. **Reconciliation Options:** When drift is detected, always present the user with a clear, two-choice decision path:
    *   **Option A (Reconcile to Code):** Overwrite manual changes by re-applying the Terraform configuration.
    *   **Option B (Backport to Code):** Update the Terraform HCL code to match the manual changes made in the console.

---

## The Drift Detection Flow

### Step 1: Generate Infrastructure Preview
Create a preview using Infrastructure Manager to compare the deployed infrastructure against the local Terraform code.

*   Run the preview command, passing the existing deployment name and the path to the local Terraform directory:
    ```bash
    gcloud infra-manager previews create {preview_name} \
        --location={region} \
        --local-source={path_to_tf_dir} \
        --service-account={service_account_email} \
        --deployment="projects/{project_id}/locations/{region}/deployments/{deployment_name}"
    ```
*   *Wait for the preview creation to complete successfully.*

### Step 2: List Detected Drifts
Query the generated preview to identify specific resources that have drifted.

*   Run the command to list resource drifts:
    ```bash
    gcloud infra-manager resource-drifts list \
        --preview="projects/{project_id}/locations/{region}/previews/{preview_name}"
    ```
*   Present the output list of drifted resources to the user in a clean, readable table format, detailing:
    *   Resource Name & Type
    *   Action (e.g., UPDATE, DELETE)
    *   Drift Status (e.g., DRIFTED)

### Step 3: Present Reconciliation Paths
Analyze the list from Step 2 and present the two reconciliation options:

*   **Option A: Overwrite and Re-align to Code**
    *   Explain that this will revert all manual console changes and re-apply the local Terraform state.
    *   Provide the command to re-apply the deployment (referencing `references/managed-deployment.md`):
        ```bash
        gcloud infra-manager deployments apply projects/{project_id}/locations/{region}/deployments/{deployment_name} \
            --local-source={path_to_tf_dir} \
            --service-account={service_account_email} \
            --import-existing-resources
        ```
*   **Option B: Backport Console Changes to Code**
    *   Explain that this will update their local Terraform files to reflect the manual changes made in the console, preserving them.
    *   Detail the exact HCL changes they need to make to their `main.tf` based on the drift output.
