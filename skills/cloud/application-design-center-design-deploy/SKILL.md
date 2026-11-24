---
name: application-design-center-design-deploy
description: >-
  Processes GCP infrastructure design and deployment workflows within Application Design Center (ADC).
  Use when:
  - Designing GCP infrastructure with Terraform.
  - Validating local HCL.
  - Performing best-practice plan scans.
  - Importing templates to Application Design Center (ADC).
  - Deploying templates.
  - Troubleshooting deployment failures.
  Boundaries:
  - Only use for GCP-specific cloud infrastructure.
  - Only use for Terraform coding within the ADC context.
license: Apache-2.0
metadata:
  version: "1.0.2"
  publisher: google
  category: CloudInfrastructure
---

# Designing and Deploying GCP Infrastructure with Application Design Center

## Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read [Usage Attribution](references/attribution.md). For commands executed
directly in the terminal (never in generated scripts, Terraform, or user code),
prefix `gcloud` with
`CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:application-design-center-design-deploy)"`
and append `agent-skills/1.0 (skill:application-design-center-design-deploy)` to `User-Agent` headers.

## Overview

This skill provides a prescriptive, production-grade workflow for the entire
infrastructure lifecycle on Google Cloud Platform (GCP). It replaces the
automated, opaque-box GAD `design_infra` tool with an **agent-controlled design
and validation loop** utilizing modular Terraform and local CLI validation,
followed by a **shifted-left best practices plan scan** prior to synchronization
with the Application Design Center (ADC) registry for deployment and lifecycle
management.

Always maintain the persona of a Principal Cloud Architect. Keep the local
Terraform configuration as the source of truth, and ensure the design is fully
compliant with best practices before importing it into the cloud registry.

--------------------------------------------------------------------------------

## Index

1.  [Pre-requisites: Setup & Confirmation](#pre-requisites-setup-confirmation)
2.  [Phase 1: Local Infrastructure Design & Validation](#phase-1-local-infrastructure-design-validation)
3.  [Phase 2: Shifted-Left Best Practices Assessment & Iterative Remediation](#phase-2-shifted-left-best-practices-assessment-iterative-remediation)
4.  [Phase 3: Import IaC to Application Design Center](#phase-3-import-iac-to-application-design-center)
5.  [Phase 4: Application Deployment & Monitoring](#phase-4-application-deployment-monitoring)
6.  [Phase 5: Troubleshoot Deployment Failures](#phase-5-troubleshoot-deployment-failures)
7.  [Phase 6: Verification & E2E Testing](#phase-6-verification-e2e-testing)

--------------------------------------------------------------------------------

## Pre-requisites: Setup & Confirmation

Before executing Phase 1, you **must** perform the following setup steps:

1.  **Confirm Target Project & Location**:

    *   Explicitly ask the user to confirm the target GCP **project ID** and
        **location** (region).
    *   If the user does not specify a location, use **`us-central1`** as the
        default.
    *   Verify that your local environment has the active project set:

        ```bash
        gcloud config set project <project_id>
        ```

--------------------------------------------------------------------------------

## Phase 1: Local Infrastructure Design & Validation

**Goal**: Transform user requirements and codebase characteristics into a 100%
validated, secure, and compile-ready Terraform configuration locally.

1.  **Invoke the `design` Skill**: Call and execute the `design` skill (defined
    in [design](references/design_guide.md))
    for the user's prompt.
    *   The `design` skill will autonomously perform the Codebase Analysis,
        query the catalog registry, planning, HCL generation, and local CLI
        validation loop (`terraform init`, `validate`, `plan`) in a dedicated
        scratch directory.
2.  **Locate Validated HCL**: Identify the scratch directory where the `design`
    skill saved the validated, compile-ready Terraform files (e.g.,
    `scratch/tf_validate_<session_id>/`).
3.  **Verify Handover (MANDATORY)**: Ensure that the local validation loop in
    the `design` skill completed successfully with a clean plan before
    proceeding. Meticulously inspect the HCL to verify:
    *   **Secret-Safe Policy**: Confirm that no plaintext credentials,
        passwords, or hardcoded secrets are written in `terraform.tfvars` or HCL
        resource blocks. All sensitive inputs must be wired through GCP Secret
        Manager.
    *   **State Isolation Policy**: Confirm that there is no remote backend
        block (e.g., `backend "gcs" {}`) in the HCL files. State must remain
        local in the scratch folder during validation, allowing ADC to handle
        the remote state registry upon import.
    *   *Remediation*: If any violations are found, correct them in the HCL,
        re-run local validation, and verify again. Do not proceed with
        unvalidated or insecure code.
4.  **Export Terraform Plan to JSON (MANDATORY)**: In the scratch directory, run
    the following commands to generate a binary plan and convert it into a clean
    JSON representation:

    ```bash
    terraform plan -out=tfplan && terraform show -json tfplan > tfplan.json
    ```

    Verify that the `tfplan.json` file is successfully written in your scratch
    directory.

--------------------------------------------------------------------------------

## Phase 2: Shifted-Left Best Practices Assessment & Iterative Remediation

**Goal**: Validate the local plan's alignment with security, cost, and
reliability benchmarks BEFORE importing it into the cloud registry, using the
native ADC plan assessment API.

1.  **Discover Space ID (MANDATORY)**: Before running the assessment or creating
    templates, you **must** dynamically discover the active ADC Space ID in your
    target location:

    *   **List Spaces**: Run the command:

        ```bash
        gcloud design-center spaces list --project=<project_id> --location=<location>
        ```

    *   **Select Space**: Parse the output to identify the active space (e.g.,
        `test-deploy` or `googlespace`). If multiple spaces exist, ask the user
        to confirm. If no space exists, ask the user or create one:

        ```bash
        gcloud design-center spaces create <space_id> --project=<project_id> --location=<location>
        ```

2.  **Execute Plan Assessment via gcloud**: Run the plan-based assessment using
    the discovered Space ID and your exported `tfplan.json` file. Execute the
    command directly in your terminal:

    ```bash
    gcloud alpha design-center spaces generate-terraform-assessment-report <space_id> \
        --location=<location> \
        --project=<project_id> \
        --terraform-plan="<scratch_directory_path>/tfplan.json" \
        --format=json
    ```

3.  **Analyze Findings**: Present all findings to the user in a clean tabular
    format, detailing specific violations, resource scopes, and associated
    severity levels.

4.  **Local Remediation Loop**:

    *   **Do not** attempt to import or commit insecure code.
    *   Edit your **local HCL files** in the scratch directory to fix the
        reported violations (e.g., adding encryption keys, enabling OS Login, or
        restricting IAM scopes).
    *   Re-run Phase 1 local validation and plan export:

        ```bash
        terraform validate && terraform plan -out=tfplan && terraform show -json tfplan > tfplan.json
        ```

    *   Re-run the plan assessment command shown in step 2.

5.  **Exit Criteria**:

    *   All high/critical findings resolved, or acceptable trade-offs
        documented.
    *   Maximum of three (3) iterative attempts reached. Once clean or
        acceptable, proceed to Phase 3.

--------------------------------------------------------------------------------

## Phase 3: Import IaC to Application Design Center

**Goal**: Synchronize the fully validated and best-practice-compliant local HCL
configuration with the ADC cloud registry to establish the deployable template
resource.

1.  **Verify or Create the Application Template (MANDATORY)**: Before importing
    the HCL, you **must** ensure the parent Application Template resource exists
    in the discovered ADC space.

    *   **Check Existence**: Run `gcloud design-center spaces
        application-templates describe <template_id> --space=<space_id>
        --project=<project_id> --location=<location>` to check if the template
        exists.
    *   **Create if Missing**: If the describe command returns a `NOT_FOUND`
        error, create the template resource first by running:

        ```bash
        gcloud design-center spaces application-templates create <template_id> --space=<space_id> --project=<project_id> --location=<location> --display-name="<Name>" --description="<Description>"
        ```

2.  **Strict HCL Parser Constraints (CRITICAL):** Before calling the import
    operation, ensure your local HCL complies with the ADC registry's strict
    ingestion rules:

    *   **Pure Module Policy (No Resource Blocks):** The ADC parser strictly
        **prohibits any `resource` blocks** inside the imported HCL. Only
        `module`, `variable`, `output`, and `provider` blocks are allowed. If a
        resource is required (e.g. Private Service Access peering) but no
        standalone module is registered for it in the catalog, you MUST check if
        it is supported as a built-in configuration option inside an existing
        registered module (e.g. setting `private_service_access_config` inside
        `module "vpc"`).
    *   **Strict String Typing:** The ADC parser does not perform implicit type
        coercion from boolean to string. For example, subnet private access must
        be declared as a literal string: `subnet_private_access = "true"`, NOT
        as a boolean `true`.
    *   **No Terraform Block:** The parser strictly prohibits the `terraform {}`
        version constraint block. Omit it entirely from `providers.tf` or
        `main.tf`.

3.  **Import to ADC Template**: Once the template resource is confirmed to exist
    and the HCL is validated against the above constraints, invoke the hosted
    `application_design_center:manage_application_template` MCP tool with the
    `APPLICATION_TEMPLATE_OPERATION_IMPORT_IAC` operation:

    *   **Arguments**:

        *   `project`: The target project ID.
        *   `location`: The GCP deployment region (e.g., `us-central1`).
        *   `spaceId`: The discovered ADC space ID.
        *   `applicationTemplateId`: A unique name for your application
            template.
        *   `operation`: `APPLICATION_TEMPLATE_OPERATION_IMPORT_IAC`
        *   `iacModule`: A structured object containing the files list:

            ```json
            {
              "files": [
                { "name": "main.tf", "content": "<content of main.tf>" },
                { "name": "variables.tf", "content": "<content of variables.tf>" },
                { "name": "terraform.tfvars", "content": "<content of terraform.tfvars>" }
              ]
            }
            ```

    *   **Resilience & Retries (MANDATORY)**:

        *   If the `IMPORT_IAC` call fails due to a transient error (e.g., `502
            Bad Gateway`, `504 Gateway Timeout`, or `429 Rate Limit`), **do not
            immediately retry**.
        *   Use **exponential backoff with jitter** (e.g., waiting 2s, 4s, 8s
            plus a random fraction of a second).
        *   **Verify Revision before Retry**: If a timeout occurred, first call
            `gcloud alpha design-center spaces application-templates describe`
            to check if the import actually succeeded in the background. Only
            retry if the template was not updated.

4.  **Capture Template URI**: Upon success, this establishes the template
    resource in your space. Construct the `applicationTemplateUri` using the
    pattern:
    `projects/{project}/locations/{location}/spaces/{spaceId}/applicationTemplates/{applicationTemplateId}`

--------------------------------------------------------------------------------

## Phase 4: Application Deployment & Monitoring

**Goal**: Deploy the validated, best-practice-compliant application template to
the GCP environment.

1.  **Deploy Application**: Invoke the hosted
    `application_design_center:manage_application` MCP tool with the
    `APPLICATION_OPERATION_DEPLOY` operation:
    *   **Arguments**:
        *   `project`: Target project ID.
        *   `location`: Target deployment location.
        *   `spaceId`: Target space ID.
        *   `applicationId`: A unique ID for the deployed application instance.
        *   `applicationTemplateUri`: The URI established in Phase 3.
        *   `serviceAccount`: The deployment service account.
    *   **Resilience & Retries (MANDATORY)**:
        *   If the `DEPLOY` operation fails with transient network or gateway
            errors (e.g., `502`, `504`), apply **exponential backoff with
            jitter** before retrying.
        *   If the deployment LRO times out or fails with a state conflict,
            verify the application status using `gcloud design-center spaces
            applications describe` to confirm its status before retrying the
            deploy call, avoiding concurrent conflicting deployments.
2.  **Active LRO Monitoring**:
    *   The tool returns a Long-Running Operation (LRO). Inform the user that
        the deployment has started.
    *   **Do not sleep** during deployment status polling. Poll the LRO actively
        every 30–60 seconds until `done: true` using the command `gcloud
        design-center operations describe <operation_name>`.
3.  **Handle Results**:
    *   **Success**: If `done` is `true` and there is no `error` field, proceed
        to Phase 6.
    *   **Failure**: If an `error` field is present, analyze the error type and
        proceed to Phase 5.

--------------------------------------------------------------------------------

## Phase 5: Troubleshoot Deployment Failures

**Goal**: Diagnose and remediate deployment failures iteratively using the
specialized troubleshooting skill and established cloud resolution patterns.

1.  **Iterative Cloud Resolution Patterns (CRITICAL):** If the deployment fails
    with a `REVISION_FAILED` or `TERRAFORM` error, check for these common
    resource conflicts:

    *   **Service Account 409 Conflict (`alreadyExists`):** If the deployment
        fails because a service account generated by the module (e.g.
        `frontend-service-us-central-sa`) already exists in the project,
        remediate the local HCL by disabling service account creation and
        referencing the existing one:

        ```hcl
        create_service_account = false
        service_account        = "<existing_service_account_email>"
        ```

    *   **Container Image 404 NotFound:** If the deployment fails because a
        container image is not found, confirm that the image exists in your
        registry. For testing or hello-world deployments, leverage the official
        public Google hello-world image:
        `us-docker.pkg.dev/cloudrun/container/hello`

2.  **Delegate to the Troubleshooting Skill**: If a deployment failure occurs
    and does not match the above patterns, invoke and execute the specialized
    `infra-deployment-debugging` guide (located in
    [infra-deployment-debugging](references/troubleshooting_guide.md)).

3.  **Select the Troubleshooting Context**:

    *   **For Local Validation Errors (Phase 1/2)**: Follow **Case B: Raw
        Terraform Deployment** instructions in the troubleshooting skill to
        isolate syntax, compilation, and plan-time validation errors.
    *   **For Cloud Deployment Failures (Phase 4)**: Follow **Case A: ADC
        Application Deployment** instructions in the troubleshooting skill to
        analyze LRO errors, retrieve service logs, and diagnose cloud
        environment issues.

4.  **Apply Local-First Remediation**:

    *   Follow the troubleshooting skill's remediation guides to formulate a
        fix.
    *   **MANDATORY**: Apply the fix directly to your **local HCL files** in the
        scratch directory, re-run local validation, re-import the HCL, and
        trigger a new deployment.
    *   Re-run Phase 1 local validation and plan export:

        ```bash
        terraform validate && terraform plan -out=tfplan && terraform show -json tfplan > tfplan.json
        ```

    *   Re-run the plan assessment (Phase 2) to ensure no new violations are
        introduced.

    *   Re-import the corrected HCL to ADC using
        `APPLICATION_TEMPLATE_OPERATION_IMPORT_IAC`.

    *   Trigger a new deployment using `APPLICATION_OPERATION_DEPLOY`.

5.  **Iteration Threshold**: Repeat the troubleshooting, validation, import, and
    redeployment cycle up to five (5) times. If it still fails, report the full
    history and diagnostics to the user.

--------------------------------------------------------------------------------

## Phase 6: Verification & E2E Testing

**Goal**: Confirm that the deployed services are healthy and fully functional.

1.  **Retrieve Deployed Resources**: Invoke the hosted
    `application_design_center:manage_application` MCP tool with the
    `APPLICATION_OPERATION_GET` operation to retrieve the resource details,
    public endpoints, and output parameters.
2.  **Health Check**: Verify that all services are using the correct container
    image URLs and that their runtime status is healthy.
3.  **E2E Validation**: Conduct a simple demo test (e.g., checking public HTTP
    endpoints or triggering a dry-run transaction) to ensure E2E functionality.
    Present the results and public URLs to the user to conclude the task.

## Reporting Issues

Report bugs or improvements for this skill at [Google Skills Issues](https://github.com/google/skills/issues).
