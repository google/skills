---
name: google-cicd-release-orchestration
metadata:
  version: "1.0.0"
  category: DevOps
description: >-
  Use this skill when you need to design Cloud Deploy delivery pipelines or manage releases for applications deploying to Cloud Run or Google Kubernetes Engine (GKE). This skill encodes best practices for multi-environment deployment, deployment strategies (like canary), and release management (including rollbacks and automations). Always activate this skill for these tasks to ensure robust and consistent configuration.
  DO NOT use for single-step direct deployments to Cloud Storage, Cloud Run, or GKE without Cloud Deploy (use `google-cicd-deploy`), end-to-end CI/CD source-to-build trigger architecture design (use `google-cicd-pipeline-design`), or Terraform HCL infrastructure provisioning (use `google-cicd-terraform`).
---

# Cloud Deploy Pipelines

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Overview

This skill encompasses the entire lifecycle of Cloud Deploy for a user, from
designing and creating delivery pipelines to managing releases and debugging
release failures.

**All** Workflows require the `clouddeploy.googleapis.com` API to be enabled.

## Prerequisites

Ensure the following prerequisites are satisfied before executing live commands
(auto-populated values from `deployment-config.json` take precedence):

*   **CLI & Billing**: Install the
    [Google Cloud SDK](https://docs.cloud.google.com/sdk/docs/install.md.txt)
    (`gcloud`, `skaffold`, plus `kubectl` for GKE) and attach an active
    **billing account** to the target project.
*   **Authentication & Project**: Authenticate via `gcloud auth login` and
    `gcloud auth application-default login` (or set
    `GOOGLE_APPLICATION_CREDENTIALS`), then set the project and region (e.g.,
    `us-central1`; see
    [Cloud Locations](https://cloud.google.com/about/locations)):
    `gcloud config set project <PROJECT_ID>` and
    `gcloud config set compute/region <REGION>`.
*   **API Enablement & IAM**: Enable required APIs (with user confirmation) via
    `gcloud services enable clouddeploy.googleapis.com cloudbuild.googleapis.com
    artifactregistry.googleapis.com run.googleapis.com container.googleapis.com
    monitoring.googleapis.com`, and verify target IAM roles per
    [iam-permissions.md](references/iam-permissions.md).

## Workflow: Designing a Pipeline

This workflow provides steps for designing a Cloud Deploy `DeliveryPipeline`.

### Constraints & Rules

1.  **NO PLACEHOLDERS**: Never generate YAML with placeholders like
    `<PROJECT_ID>`. Ask the user for values first.
2.  **Context First**: Always check existing files and conversation context
    before asking.
3.  **Step-by-Step**: Perform the steps one at a time. The goal is to guide the
    user through designing a delivery pipeline.

### Step 0: Prerequisites

**Required Context**: Before generating ANY configuration for this workflow,
first check `.gcp-deploy/deployment-config.json` (pulled from the organization's
source control config repository—**GitHub**, **GitLab**, **Bitbucket**, or any
Git provider—per
[how_to_load_deployment_config.md](references/how_to_load_deployment_config.md)
and [sample-deployment-config.json](references/sample-deployment-config.json))
and local `gcp-deploy.json` to automatically populate the values below. Ask the
user strictly for any information still missing:

-   **Project ID**: The Google Cloud project ID for the Cloud Deploy resources.
-   **Region**: The region for the Cloud Deploy resources (e.g., `us-central1`).
-   **Application Name**: The name of the application that will be deployed. Use
    the application name to generate the names of the Cloud Deploy resources,
    such as `DeliveryPipeline` and `Target` resources.
-   **Runtime**: Either Cloud Run or Google Kubernetes Engine (GKE).
    -   **If Cloud Run**: The Cloud Run project and location.
    -   **If GKE**: The GKE cluster name.

### Step 1: Define the target environments

1.  Identify the number of deployment environments (e.g., dev, staging,
    production).
2.  Identify if promotions should require user approval.
3.  Define each of the deployment environments as Cloud Deploy `Target`
    resources in a `clouddeploy.yaml` file.
    -   Use [configure-targets.md](references/configure-targets.md) as a
        reference when generating the resource YAML.
    -   Always prefix target IDs with the application name provided by the user
        (e.g., `[app-name]-[env]`) to prevent resource name collisions when
        multiple applications are deployed to different environments. For
        example, if the user wants to deploy an application named "hello-world"
        to test and prod environments, then use "hello-world-test" and
        "hello-world-prod" as the `Target` IDs.

### Step 2: Define the delivery pipeline

1.  Identify whether the user wants to use a canary deployment strategy for any
    of the target environments.
2.  Define the Cloud Deploy `DeliveryPipeline` in the `clouddeploy.yaml` file.
    -   Use [configure-pipelines.md](references/configure-pipelines.md) as a
        reference when generating the resource YAML.
    -   Use application name as the `DeliveryPipeline` ID.

### Step 3: Define automations

1.  Identify whether the user wants to automatically rollback if any failures
    occur during the rollout.
2.  **If the user specified multiple deployment environments in the previous
    step**
    -   Identify if they want automatic promotions between deployment
        environments.
3.  **If the user specified a canary deployment strategy in the previous step**
    -   Identify if they want to automatically advance the rollout through the
        phases after a wait period.
4.  Define the Cloud Deploy `Automation` resources in the `clouddeploy.yaml`
    file.
    -   Use [configure-automations.md](references/configure-automations.md) as a
        reference when generating the resource YAML.

### Step 4: Validate the clouddeploy.yaml file

Ensure that the `clouddeploy.yaml` file is valid. See
https://docs.cloud.google.com/deploy/docs/config-files.md.txt for the schema.

### Step 5: Create the delivery pipeline

Run the following command to create the Cloud Deploy `DeliveryPipeline` and
associated resources, using the values collected in Step 0:

```bash
gcloud deploy apply --file=clouddeploy.yaml --region=<REGION> --project=<PROJECT_ID>
```

### Step 6: Create a skaffold.yaml file and runtime manifests

**Required Context**: Before generating a `skaffold.yaml` file, you **MUST**
know if the user has manifests for the runtime they are deploying to.

1.  **If the user does not have runtime manifests**: Generate some basic ones
    based on the runtime.
    -   **If Cloud Run**: Generate a Cloud Run manifest. Use
        [basic-cloudrun-manifests.md](references/basic-cloudrun-manifests.md) as
        a reference.
    -   **If GKE**: Generate a Kubernetes `Deployment` and `Service` manifest.
        Use [basic-k8s-manifests.md](references/basic-k8s-manifests.md) as a
        reference.
2.  Create a `skaffold.yaml` file required to create a Cloud Deploy `Release`
    for the `DeliveryPipeline`.
    -   Use [configure-skaffold.md](references/configure-skaffold.md) as a
        reference when generating the `skaffold.yaml` file.
    -   **For multi-environment pipelines**: You must define a Skaffold profile
        for each Cloud Deploy target environment, named to match the target ID
        exactly. Do NOT use generic names like 'staging' or 'prod' for profile
        names unless they match the target IDs.

### Step 7: Setup IAM permissions

Use [iam-permissions.md](references/iam-permissions.md) as a reference to set up
the necessary IAM permissions based on the `DeliveryPipeline` defined.

## Workflow: Add Google Observability Alert Policy Analysis to a Pipeline

Cloud Deploy integrates with Google Cloud Observability to provide metrics
analysis when deploying an application. When the application is deployed, Cloud
Deploy will monitor alert policies defined in Google Cloud Observability for any
incidents that were triggered after the application was deployed.

This feature can be used alongside automation to enable automatic rollbacks if
the application deployment triggers alert policies.

This section covers how to update the user's `DeliveryPipeline` to leverage this
feature.

### Constraints & Rules

A `DeliveryPipeline` MUST already be defined or being designed in the current
context.

### Step 0: Prerequisites

Cloud Deploy **requires** the Google Cloud Observability alerting policies to be
defined before they can be referenced in the `DeliveryPipeline`.

1.  Prompt the user whether they have existing alerting policies defined for the
    application. **DO NOT** assume that existing alerting policies are
    applicable to the application being deployed.
2.  If the user does not have alerting policies defined for the application,
    help the user generate them.
    -   **If Cloud Run**: Use
        [basic-cloudrun-alerts.md](references/basic-cloudrun-alerts.md) as a
        reference.

### Step 1: Update the pipeline definition

1.  Identify the duration for which the metrics analysis should run after the
    application is deployed (e.g., 30 minutes).
2.  Identify which alerting policies Cloud Deploy should monitor for incidents.
3.  Update the `DeliveryPipeline` definition in the `clouddeploy.yaml` file to
    include analysis configuration.
    -   Use [configure-pipelines.md](references/configure-pipelines.md) as a
        reference when updating the `DeliveryPipeline` definition.

### Step 2: Validate the clouddeploy.yaml file

Ensure that the `clouddeploy.yaml` file is valid. See
https://docs.cloud.google.com/deploy/docs/config-files.md.txt for the schema.

### Step 3: Apply the pipeline changes

Run the following command to update the Cloud Deploy `DeliveryPipeline`:

```bash
gcloud deploy apply --file=clouddeploy.yaml --region=<REGION> --project=<PROJECT_ID>
```

### Step 4: Setup IAM permissions

Use [iam-permissions.md](references/iam-permissions.md) as a reference to set up
the necessary IAM permissions for analysis.

## Release Management

This section covers the various aspects of managing Cloud Deploy `Release`
resources.

### Constraints & Rules

In order to manage releases, a `DeliveryPipeline` MUST already be defined and
configured in Cloud Deploy. Determine whether a delivery pipeline is defined by
checking for a `clouddeploy.yaml` file and checking if the resources exist in
Cloud Deploy or ask the user directly.

**Required Context**:

-   **Project ID**: The Google Cloud project ID of the `DeliveryPipeline`.
-   **Region**: The region of the `DeliveryPipeline` (e.g., `us-central1`).
-   **Delivery Pipeline ID**: The `DeliveryPipeline` ID.

### Create a release

**Use case**: The user wants to deploy a new version of their application.

**Required Context**: Before creating a `Release`, you **MUST** know whether the
users runtime manifests are using a placeholder for the container image and the
value of the placeholder. This is **CRITICAL** for build artifact substitution
in Cloud Deploy. Check the users runtime manifests or ask the user directly. See
examples in
[basic-cloudrun-manifests.md](references/basic-cloudrun-manifests.md) and
[basic-k8s-manifests.md](references/basic-k8s-manifests.md).

Run the following command to create a `Release` for the `DeliveryPipeline`:

```bash
gcloud deploy releases create release-$DATE-$TIME --delivery-pipeline=<DELIVERY_PIPELINE_ID> --region=<REGION> --project=<PROJECT_ID>
```

If the user is leveraging build artifact substitution with a placeholder in the
image field of the runtime manifests then use the `--images` flag:

```bash
gcloud deploy releases create release-$DATE-$TIME --delivery-pipeline=<DELIVERY_PIPELINE_ID> --region=<REGION> --project=<PROJECT_ID> --images <IMAGE_PLACEHOLDER>=<IMAGE_URI>
```

**CRITICAL**: If the `skaffold.yaml` is not in the current directory, use the
`--source` flag to specify the directory where the `skaffold.yaml` file is
located.

Reference documentation for `gcloud deploy releases create`:
https://docs.cloud.google.com/sdk/gcloud/reference/deploy/releases/create.md.txt.

### Promote a release

**Use case**: The user wants to promote the application to the next target
environment in the `DeliveryPipeline` progression sequence.

Run the following command to promote a `Release` to the next target in the
`DeliveryPipeline` progression sequence:

```bash
gcloud deploy promote --release=<RELEASE_ID> --delivery-pipeline=<DELIVERY_PIPELINE_ID> --region=<REGION> --project=<PROJECT_ID>
```

**TIP**: Use a short <RELEASE_ID> since the command will auto-generate a
`Rollout` ID (with a 63 character limit) in the format:
`<RELEASE_ID>-to-<TARGET_ID>`.

Reference documentation for `gcloud deploy releases promote`:
https://docs.cloud.google.com/sdk/gcloud/reference/deploy/releases/promote.md.txt.

### Monitor a release

**Use case**: Monitor the status of a release across a `DeliveryPipeline`.

Monitoring a release across a `DeliveryPipeline` consists of checking the status
of both the `Release` resource and its child `Rollout` resource(s). Always
ensure that the `Release` has completed successfully before checking the status
of the `Rollout`.

### Troubleshoot

#### Release failed

Get the release to determine which of the target renders failed and inspect the
failure message and failure cause. Additionally the target renders contain a
Cloud Build reference where the target render was executed. Retrieve the build
logs to determine the root cause of the failure.

#### Rollout failed

Get the rollout to determine which of the jobs failed and inspect the failure
message and failure cause. Additionally the `Rollout` contains a Cloud Build
reference where the failed job was executed. Retrieve the build logs to
determine the root cause of the failure.

*   **Binary Authorization (`BinAuthz`) Failure Interpretation on Promotion to
    Production**: If a rollout or promotion to `prod` fails because Binary
    Authorization blocked the image (e.g., Cloud Run
    `BinaryAuthorizationCheckFailed` or GKE
    `imagepolicywebhook.image-policy.k8s.io` admission denial), automatically
    inspect and interpret the Binary Authorization evaluation results for the
    user:

    1.  Check Cloud Audit Logs for the exact BinAuthz denial reason:

        ```bash
        gcloud logging read 'logName:"cloudaudit.googleapis.com%2Fpolicy" OR protoPayload.serviceName="binaryauthorization.googleapis.com" OR protoPayload.status.message:"Binary Authorization"' \
          --project=<PROJECT_ID> --limit=10 --format=json --quiet
        ```
    2.  Inspect the active Binary Authorization policy and platform policies
        (`gcloud container binauthz policy export --project=<PROJECT_ID>` and
        `gcloud beta container binauthz policy list --platform=<cloudRun|gke>
        --project=<PROJECT_ID>`), and if a platform policy is used, evaluate it
        against the image digest (`gcloud beta container binauthz policy
        evaluate <POLICY_ID> --platform=<cloudRun|gke> --project=<PROJECT_ID>
        --image=<DIGEST_URI>`).
    3.  Cross-check existing attestations (`gcloud container binauthz
        attestations list --artifact-url="https://<DIGEST_URI>"
        --project=<PROJECT_ID>`) and Artifact Analysis provenance/vulnerability
        findings (`gcloud artifacts docker images describe <DIGEST_URI>
        --show-provenance --show-package-vulnerability --project=<PROJECT_ID>`).
    4.  Clearly explain which policy rule, missing attestation
        (`<ATTESTOR_NAME>`), provenance check, or CVE severity threshold blocked
        the promotion and provide actionable remediation steps.

## Resource Cleanup & Teardown

Cloud Deploy pipelines, staging Cloud Storage buckets, Cloud Build executions,
and target Cloud Run / GKE runtimes incur charges (an active billing account is
required even within free tiers; see
[Google Cloud Pricing](https://cloud.google.com/pricing)). Always obtain
explicit user confirmation before deleting resources:

*   **Delivery Pipeline & Targets**: `gcloud deploy delete
    --file=clouddeploy.yaml --force --region=<REGION> --project=<PROJECT_ID>`
    (or `gcloud deploy delivery-pipelines delete <DELIVERY_PIPELINE_ID> --force
    --region=<REGION> --project=<PROJECT_ID>`)
*   **Alerting Policies**: `gcloud alpha monitoring policies delete <POLICY_ID>
    --project=<PROJECT_ID>`
