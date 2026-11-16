---
name: cb-create-trigger
description: Creates a Cloud Build trigger to automate builds in response to repository events (pushes, tags, pull requests), Pub/Sub messages, Webhook events, or manual invocations. This skill covers all trigger types, repository services (GitHub, Cloud Source Repositories, Bitbucket, GitLab), and build configurations including YAML/JSON files, Dockerfiles, Buildpacks, and inline YAML.
---

## Table of Contents
- [Preconditions](#preconditions) (Lines 21-55)
- [Inputs](#inputs) (Lines 57-87)
- [Execution Steps](#execution-steps) (Lines 89-197)
  - [Step 1: Authentication and Project Initialization](#step-1-authentication-and-project-initialization) (Lines 91-99)
  - [Step 2: Enable Required APIs](#step-2-enable-required-apis) (Lines 101-107)
  - [Step 3: Create the Trigger](#step-3-create-the-trigger) (Lines 109-182)
  - [Step 4: Verification](#step-4-verification) (Lines 184-197)
- [Outputs](#outputs) (Lines 199-209)
- [Related Skills](#related-skills) (Lines 211-220)

## Preconditions

-   **Authentication**: Run the following commands to ensure your CLI is
    authenticated with the correct credentials:

    ```bash
    gcloud auth login
    gcloud auth application-default login
    ```

-   **Project ID**: Ensure you have the `projectId`. If it is not already known,
    prompt the user to provide the project ID where the trigger will be created.

-   **Enable APIs**: Ensure the following APIs are enabled in your project:

    -   `cloudbuild.googleapis.com` (Cloud Build API)
    -   `secretmanager.googleapis.com` (Secret Manager API - required for
        Webhook triggers)
    -   `pubsub.googleapis.com` (Cloud Pub/Sub API - required for Pub/Sub
        triggers)

-   **IAM Roles**: Ensure the user or service account has the following roles:

    -   `roles/cloudbuild.builds.editor` (Cloud Build Editor)
    -   `roles/iam.serviceAccountUser` (to use service accounts with the
        trigger)
    -   `roles/pubsub.subscriber` (for the Cloud Build Service Agent if using
        Pub/Sub triggers)
    -   `roles/secretmanager.admin` (if creating secrets for Webhook triggers)

-   **Organization Policy**: Be aware that organization policies (e.g.,
    `constraints/cloudbuild.allowedServiceAccounts` or
    `constraints/gcp.resourceLocations`) may restrict service account selection
    or regional availability.

## Inputs

Name                     | Type    | Description                                                                                                   | Required/Optional                    | Default
:----------------------- | :------ | :------------------------------------------------------------------------------------------------------------ | :----------------------------------- | :------
`name`                   | String  | A unique name for the trigger within the project's region. Must be alphanumeric and hyphens only.             | Required                             | -
`region`                 | String  | The region where the trigger will be stored. **Warning: Immutable after creation.**                           | Required                             | `global`
`description`            | String  | A concise explanation of the trigger's purpose.                                                               | Optional                             | -
`tags`                   | List    | Arbitrary strings used to organize and filter triggers.                                                       | Optional                             | -
`event_type`             | Enum    | The event that invokes the trigger: `push_branch`, `push_tag`, `pull_request`, `manual`, `pubsub`, `webhook`. | Required                             | `push_branch`
`repo_service`           | Enum    | The repository service: `github`, `cloud_source_repositories`, `bitbucket`, `gitlab`, `developer_connect`.    | Required                             | `github`
`repo_generation`        | Enum    | `1st_gen` or `2nd_gen`. Note: 2nd-gen is not available in the `global` region.                                | Required                             | `1st_gen`
`repository`             | String  | Name or resource path of the connected repository.                                                            | Required                             | -
`branch_pattern`         | String  | Regular expression to match branches (e.g., `^main$`).                                                        | Required for branch events           | -
`tag_pattern`            | String  | Regular expression to match tags (e.g., `^v.*`).                                                              | Required for tag events              | -
`pull_request_pattern`   | String  | Regular expression to match the base branch for pull requests.                                                | Required for PR events               | -
`config_type`            | Enum    | `yaml_json` (Standard), `dockerfile`, `buildpacks`.                                                           | Required                             | `yaml_json`
`config_source`          | Enum    | `repository` (File in repo) or `inline` (YAML provided directly).                                             | Required                             | `repository`
`config_file_path`       | String  | Path to the configuration file in the repository (e.g., `cloudbuild.yaml`).                                   | Required for repo config             | `cloudbuild.yaml`
`inline_config_path`     | String  | Local path to a YAML/JSON file containing the build configuration to be embedded.                             | Required for inline config           | -
`dockerfile`             | String  | Path to the Dockerfile in the repository.                                                                     | Required for Docker builds           | `Dockerfile`
`dockerfile_dir`         | String  | Directory context for the Docker build.                                                                       | Optional                             | `/`
`dockerfile_image`       | String  | Destination container image tag.                                                                              | Optional                             | -
`service_account`        | String  | The service account used for build execution. Strongly recommended for security.                              | Optional (may be required by policy) | -
`substitution_variables` | Map     | Key-value pairs for build parameterization (e.g., `_DEPLOY_ENV=prod`).                                        | Optional                             | -
`require_approval`       | Boolean | Whether builds require manual approval before execution.                                                      | Optional                             | `false`
`pubsub_topic`           | String  | The Pub/Sub topic to subscribe to.                                                                            | Required for Pub/Sub events          | -
`webhook_secret`         | String  | Secret Manager secret version path (e.g., `projects/.../secrets/.../versions/...`).                           | Required for Webhook events          | -
`ignored_files`          | List    | Glob patterns for files that should not trigger builds.                                                       | Optional                             | -
`included_files`         | List    | Glob patterns for files that MUST be changed to trigger builds.                                               | Optional                             | -
`cel_filter`             | String  | Common Expression Language (CEL) filter for Pub/Sub or Webhook events.                                        | Optional                             | -

## Execution steps

### Step 1: Authentication and Project Initialization

Ensure the environment is configured correctly.

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project <PROJECT_ID>
```

### Step 2: Enable Required APIs

Enable services based on the chosen trigger type.

```bash
gcloud services enable cloudbuild.googleapis.com secretmanager.googleapis.com pubsub.googleapis.com
```

### Step 3: Create the Trigger

Choose the subcommand based on the `repo_service` and `event_type`.

**Option A: Create a GitHub Trigger (1st gen)** Use this for standard continuous
deployment from a GitHub repository.

```bash
gcloud builds triggers create github \
    --name=<NAME> \
    --region=<REGION> \
    --repo-owner=<REPO_OWNER> \
    --repo-name=<REPO_NAME> \
    --branch-pattern="<BRANCH_REGEX>" \
    --build-config="<CONFIG_FILE_PATH>" \
    --service-account="projects/<PROJECT_ID>/serviceAccounts/<SERVICE_ACCOUNT_EMAIL>" \
    --substitutions="_KEY=VALUE" \
    --ignored-files="docs/**,README.md"
```

**Option B: Create a Manual Trigger** Use this for triggers that are only
invoked on-demand or on a schedule.

```bash
gcloud builds triggers create manual \
    --name=<NAME> \
    --region=<REGION> \
    --repo="https://github.com/<OWNER>/<REPO>" \
    --repo-type=GITHUB \
    --branch="<BRANCH>" \
    --build-config="<CONFIG_FILE_PATH>"
```

**Option C: Create a Webhook Trigger** Use this to trigger builds via external
HTTP POST requests. Requires a secret in Secret Manager.

```bash
gcloud builds triggers create webhook \
    --name=<NAME> \
    --region=<REGION> \
    --secret="projects/<PROJECT_ID>/secrets/<SECRET_NAME>/versions/<VERSION>" \
    --branch="<BRANCH>" \
    --repo="https://github.com/<OWNER>/<REPO>" \
    --repo-type=GITHUB \
    --build-config="<CONFIG_FILE_PATH>"
```

**Option D: Create a Pub/Sub Trigger** Use this to trigger builds in response to
messages published to a topic.

```bash
gcloud builds triggers create pubsub \
    --name=<NAME> \
    --region=<REGION> \
    --topic="projects/<PROJECT_ID>/topics/<TOPIC_NAME>" \
    --branch="<BRANCH>" \
    --repo="https://github.com/<OWNER>/<REPO>" \
    --repo-type=GITHUB \
    --build-config="<CONFIG_FILE_PATH>"
```

**Option E: Create a Trigger with Inline Configuration** Use this to embed the
build steps directly within the trigger instead of a file in the repository.

```bash
gcloud builds triggers create github \
    --name=<NAME> \
    --region=<REGION> \
    --repo-owner=<REPO_OWNER> \
    --repo-name=<REPO_NAME> \
    --branch-pattern="<BRANCH_REGEX>" \
    --inline-config="<LOCAL_PATH_TO_YAML>"
```

### Step 4: Verification

Confirm the trigger has been created and is enabled.

```bash
gcloud builds triggers describe <NAME> --region=<REGION>
```

To list all triggers in a region:

```bash
gcloud builds triggers list --region=<REGION>
```

## Outputs

| Name           | Description                                                |
| :------------- | :--------------------------------------------------------- |
| `trigger_name` | The unique name of the created trigger.                    |
| `trigger_id`   | The system-generated UUID for the trigger.                 |
| `webhook_url`  | The URL used to invoke a Webhook trigger (includes the key |
:                : and secret placeholders).                                  :
| `topic_name`   | The Pub/Sub topic associated with the trigger (if          |
:                : applicable).                                               :
| `region`       | The location where the trigger resource resides.           |

## Related skills

-   [`cb-run-trigger`](./cb-run-trigger.md): Manually invoke an existing trigger with revision
    overrides.
-   `secret-manager-create-secret`: Create and manage secrets for Webhook
    authentication.
-   `pubsub-create-topic`: Create topics for Pub/Sub triggers or build
    notifications.
-   `cloud-build-create-worker-pool`: Create private worker pools for regional
    builds.