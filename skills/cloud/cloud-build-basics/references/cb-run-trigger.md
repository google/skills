---
name: cb-run-trigger
description: Manually executes a predefined Cloud Build trigger to start a build. Supports specifying a Git branch, tag, or commit SHA for source-based triggers, and overriding substitution variables for all trigger types.
---

## Table of Contents
- [Preconditions](#preconditions) (Lines 19-38)
- [Inputs](#inputs) (Lines 40-62)
- [Execution Steps](#execution-steps) (Lines 64-132)
  - [Step 1: Set Project Context](#step-1-set-the-project-context) (Lines 66-72)
  - [Step 2: Run the Cloud Build Trigger](#step-2-run-the-cloud-build-trigger) (Lines 74-114)
  - [Step 3: Verify Build Initiation and Monitor Status](#step-3-verify-build-initiation-and-monitor-status) (Lines 116-132)
- [Outputs](#outputs) (Lines 134-143)
- [Related Skills](#related-skills) (Lines 145-151)

## Preconditions

*   The Cloud Build API (`cloudbuild.googleapis.com`) must be enabled in the
    project.
*   The user must have the `roles/cloudbuild.builds.editor` IAM role to initiate
    builds.
*   If the trigger is configured with a user-managed service account, the user
    must also have the `roles/iam.serviceAccountUser` permission on that service
    account (`iam.serviceAccounts.actAs`).
*   Authenticate the `gcloud` CLI:

    ```bash
    gcloud auth login
    gcloud auth application-default login
    ```

*   Identify the target Google Cloud Project ID. If not known, prompt the user
    for it.

## Inputs

Name            | Type   | Description                                                                                                   | Required/Optional | Default
:-------------- | :----- | :------------------------------------------------------------------------------------------------------------ | :---------------- | :------
`projectId`     | String | The ID of the Google Cloud project where the trigger resides.                                                 | Required          | -
`triggerId`     | String | The unique name or UUID of the trigger to execute.                                                            | Required          | -
`region`        | String | The region where the trigger is defined (e.g., `global`, `us-central1`).                                      | Required          | `global`
`revisionType`  | String | The type of source revision to build: `branch`, `tag`, or `sha`. Not applicable for repoless/inline triggers. | Optional          | `branch`
`revisionValue` | String | The actual value for the revision (e.g., branch name `main`, tag `v1.2.0`, or commit hash `7a1b3c4`).         | Optional          | -
`substitutions` | Map    | Key-value pairs for substitution variable overrides (e.g., `_ENVIRONMENT=prod,_TAG=latest`).                  | Optional          | -

> [!IMPORTANT] **Pricing**: Trigger invocation is free ($0.00). However, the
> resulting build consumes compute resources. Cloud Build provides 120 free
> build-minutes per day on default machine types. Beyond this, standard
> per-minute rates apply based on the machine type and region.

> [!WARNING] **Substitution Immutability**: You can only override values for
> substitution variables that are ALREADY defined in the trigger configuration.
> You cannot add new keys at runtime. 

> [!NOTE] **Jurisdictional Constraints**: In Jurisdictional Consoles (DRZ),
> triggers using legacy 1st-gen repositories are disabled for manual runs. Only
> 2nd-gen repositories are supported.

## Execution steps

### Step 1: Set the project context

Ensure the `gcloud` CLI is pointing to the correct project.

```bash
gcloud config set project <PROJECT_ID>
```

### Step 2: Run the Cloud Build trigger

Choose the appropriate variation based on the trigger configuration and desired
revision.

**Variation A: Run using a branch** Use this for triggers targeting a specific
Git branch.

```bash
gcloud builds triggers run <TRIGGER_ID> --region=<REGION> --branch=<BRANCH_NAME>
```

**Variation B: Run using a tag** Use this for triggers targeting a specific Git
tag.

```bash
gcloud builds triggers run <TRIGGER_ID> --region=<REGION> --tag=<TAG_NAME>
```

**Variation C: Run using a commit SHA** Use this to build a specific commit hash
(short or full 40-character hex SHA).

```bash
gcloud builds triggers run <TRIGGER_ID> --region=<REGION> --sha=<COMMIT_SHA>
```

**Variation D: Run with substitution overrides** Append the `--substitutions`
flag to any run command to override variables.

```bash
gcloud builds triggers run <TRIGGER_ID> --region=<REGION> --branch=<BRANCH_NAME> --substitutions="_VARIABLE_NAME=<VALUE>"
```

**Variation E: Run a repoless or inline trigger** For Manual, Pub/Sub, or
Webhook triggers that use an inline `cloudbuild.yaml` and no repository.

```bash
gcloud builds triggers run <TRIGGER_ID> --region=<REGION>
```

### Step 3: Verify build initiation and monitor status

The `run` command will output a build ID. Use this ID to check the status or
view the execution logs.

**Check build status:**

```bash
gcloud builds describe <BUILD_ID> --region=<REGION>
```

**Stream build logs:**

```bash
gcloud builds log <BUILD_ID> --region=<REGION>
```

## Outputs

| Name          | Description                                                |
| :------------ | :--------------------------------------------------------- |
| `buildId`     | The unique identifier for the initiated build (e.g.,       |
:               : `a1b2c3d4-e5f6-...`).                                      :
| `buildStatus` | The current state of the build (e.g., `QUEUED`, `WORKING`, |
:               : `SUCCESS`, `FAILURE`, `CANCELLED`).                        :
| `logUrl`      | A link to view the live logs in the Google Cloud Console   |
:               : (derived from the build ID).                               :

## Related skills

*   [`cb-create-trigger`](./cb-create-trigger.md): Create a new build trigger from a repository or inline
    source.
*   `cb-list-triggers`: List and filter all triggers in a project and region.
*   `cb-approve-build`: Approve a pending build for triggers requiring manual
    approval.