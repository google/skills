---
name: cloud-build-basics
metadata:
  version: "1.0.3"
  category: DevOps
description: >-
  Teaches the fundamentals of Cloud Build on Google Cloud. Covers core concepts,
  API enablement, console navigation to the Build History page, and the end-to-end
  workflow for creating and manually running a basic build trigger. Do not use for
  managing private pools or complex pipeline architectures.
---

# Cloud Build Basics

## Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read [Usage Attribution](references/attribution.md). For commands executed
directly in the terminal (never in generated scripts, Terraform, or user code),
prefix `gcloud` with
`CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:cloud-build-basics)"`
and append `agent-skills/1.0 (skill:cloud-build-basics)` to `User-Agent` headers.

## Prerequisites

Before starting, ensure the following prerequisites are met:

1.  **Google Cloud SDK**: Ensure the [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) is installed and configured.
2.  **Authentication**: Authenticate the gcloud CLI:
    ```bash
    gcloud auth login
    gcloud auth application-default login
    ```
3.  **Project ID**: Know the target Google Cloud Project ID. Set the context:
    ```bash
    gcloud config set project <PROJECT_ID>
    ```
4.  **Enable Cloud Build API**: The Cloud Build API must be enabled for the project.
    ```bash
    gcloud services enable cloudbuild.googleapis.com
    ```
5.  **Permissions**: Ensure the user or service account has the necessary permissions, such as `roles/cloudbuild.builds.editor` and `roles/serviceusage.serviceUsageAdmin` (to enable the API).

## Core Concepts

Cloud Build (GCB) is a serverless platform that executes your builds on Google Cloud. It translates your source code into deployable artifacts, such as Docker containers or Java archives.

| Concept | Description |
| :--- | :--- |
| **`cloudbuild.yaml`** | The required configuration file that defines the build steps. It is written in YAML or JSON. |
| **Build Steps** | A sequence of actions (steps) GCB performs. Each step runs a command inside a specific Docker container (the builder). Common builders include `gcr.io/cloud-builders/gcloud`, `gcr.io/cloud-builders/docker`, and custom containers. |
| **Artifacts** | The output of the build, typically a container image pushed to Google Container Registry (GCR) or Artifact Registry (AR), or other deployable files. |
| **Triggers** | Automation rules that invoke a build in response to an event, such as a push to a Git repository, a Pub/Sub message, or a manual request. |

## Navigation: Viewing Build History

The Cloud Build Build History page is the central place to monitor the status of past and ongoing builds.

1.  **Open the Cloud Console**: Navigate to the Google Cloud Console.
2.  **Go to Cloud Build**: Use the search bar or the navigation menu to find **Cloud Build**.
3.  **Select Build History**: In the left navigation pane, select **History** (or use the direct URL: `https://console.cloud.google.com/cloud-build/builds`).
4.  **Review Builds**:
    *   **Status**: Check the status column (`SUCCESS`, `FAILURE`, `WORKING`, `QUEUED`).
    *   **Region**: Use the region filter at the top to view builds that ran in a specific region (important for regional worker pools).
    *   **Logs**: Click on a specific Build ID to view the detailed logs, execution steps, and build summary. This is crucial for debugging failed builds.

> [!NOTE]
> If this is your first time visiting the page, you might see the "zero-state" experience, which offers options to run a sample build or create your first trigger (as noted in the [`cb-list-build-zero-state`](references/cb-list-build-zero-state.md) skill). Note that region settings for triggers and builds are immutable after creation and must be chosen deliberately.

## Creating a Basic Automated Trigger

This process defines an automation rule to run a build whenever code is pushed to a specified Git branch.

### Step 1: Start Trigger Creation

1.  Navigate to the **Cloud Build Triggers** page (`https://console.cloud.google.com/cloud-build/triggers`).
2.  Click **Create trigger**.

### Step 2: Configure Trigger Settings

1.  **Name**: Provide a unique, descriptive name (e.g., `github-main-branch-build`).
2.  **Region**: Select the region where the trigger configuration will be stored (e.g., `global` or a specific regional endpoint). **Note: Trigger and build region settings are immutable after creation and must be chosen deliberately.**
3.  **Event**: Select the event type. For automated CI/CD, select **Push to a branch**.
4.  **Source**: Select the repository source:
    *   **Repository**: Connect your source repository (GitHub, Bitbucket, Cloud Source Repositories, etc.). If needed, authorize the connection.
    *   **Repository Name**: Select the specific repository you want to link.
5.  **Branch**: Enter the branch pattern (e.g., `^main$` or `^develop`).

### Step 3: Configure Build Settings

1.  **Configuration**: Select **Cloud Build configuration file (yaml or json)**.
2.  **Location**: Keep the default **Repository** and specify the path to your build configuration file (e.g., `cloudbuild.yaml`).
    *   *Alternative*: For very simple builds, you can choose **Inline** to paste the YAML configuration directly into the trigger.
3.  **(Optional) Service Account**: For production environments, select a dedicated service account with limited permissions to enforce the principle of least privilege.

### Step 4: Save and Test

1.  Click **Create**. The trigger is now active and will run automatically on the next matching Git push.

> [!TIP]
> The `cb-create-trigger` skill provides detailed `gcloud` commands for creating triggers across all types (GitHub, Pub/Sub, Webhook) and configurations (inline, Dockerfile, YAML). Use that skill for CLI automation.

## Running an Existing Trigger Manually

Sometimes you need to run a trigger on demand, outside of its normal automation flow (e.g., to rebuild an old commit or test a new substitution).

> [!IMPORTANT]
> **Substitution Immutability**: You can only override values for substitution variables that are **already defined in the trigger configuration**. You cannot introduce new substitution variable keys at runtime.

### Option A: Via the Cloud Console

1.  Navigate to the **Cloud Build Triggers** page (`https://console.cloud.google.com/cloud-build/triggers`).
2.  Locate the trigger you wish to run.
3.  Click the vertical ellipsis (⋮) next to the trigger and select **Run**.
4.  A dialog will appear, allowing you to specify:
    *   **Source branch/tag**: Choose the specific Git reference to build from.
    *   **Substitution Variables**: Override any existing substitution variables (e.g., set `_VERSION` to a new value).
5.  Click **Run trigger**. The build will start immediately, and you can monitor its status on the **History** page.

### Option B: Via the gcloud CLI

Use the `gcloud builds triggers run` command to invoke the trigger and optionally override parameters.

```bash
# Run the trigger against the 'main' branch
gcloud builds triggers run <TRIGGER_NAME> \
    --region=<REGION> \
    --branch=main

# Run the trigger and override a substitution variable
gcloud builds triggers run <TRIGGER_NAME> \
    --region=<REGION> \
    --branch=main \
    --substitutions=_IMAGE_TAG="20231027-manual"

# Monitor the initiated build
# Note: The run command outputs the build ID. Use it to check status:
# gcloud builds log <BUILD_ID> --region=<REGION>
```

> [!NOTE]
> The `cb-run-trigger` skill provides more complex invocation examples, including running against a specific commit SHA or using tags.

## Related Skills

*   [`cb-create-trigger`](references/cb-create-trigger.md): Detailed CLI-focused instructions for creating all trigger types.
*   [`cb-list-build-zero-state`](references/cb-list-build-zero-state.md): Advanced management of the Cloud Build dashboard and onboarding zero state.
*   [`cb-run-trigger`](references/cb-run-trigger.md): Comprehensive guide to manually running triggers using various `gcloud` options.

## External Resources & Documentation

*   [Cloud Build Documentation](https://cloud.google.com/build/docs)
*   [Cloud Build Configuration File Schema](https://cloud.google.com/build/docs/build-config-file-schema)
*   [Automating Builds with Triggers](https://cloud.google.com/build/docs/automating-builds/create-manage-triggers)
*   [gcloud CLI builds Reference](https://cloud.google.com/sdk/gcloud/reference/builds)
