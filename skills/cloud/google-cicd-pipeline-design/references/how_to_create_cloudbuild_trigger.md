# End-to-End Guide: Creating a Cloud Build Trigger

This document outlines the standard, idempotent procedure for creating a Google
Cloud Build trigger. Creating the trigger is the **final** action in a sequence
of prerequisite checks and resource provisioning steps. The agent must ensure
all dependencies are met before attempting to create the trigger itself.

--------------------------------------------------------------------------------

## Table of Contents

-   [Core Principle: Idempotency](#core-principle-idempotency) (Lines 19-23)
-   [Prerequisite Checklist](#prerequisite-checklist) (Lines 27-224)
-   [Final Step: Creating the Trigger via `gcloud`](#final-step-creating-the-trigger-via-gcloud)
    (Lines 228-289)
-   [Troubleshooting Authentication, Permission & Trigger Errors](#troubleshooting-authentication-permission-trigger-errors)
    (Lines 293-327)

## Core Principle: Idempotency

Every step in this process must be **idempotent**. This means the agent must
**always check if a resource already exists** before attempting to create it.
This prevents errors and ensures the process can be run multiple times safely.

--------------------------------------------------------------------------------

## Prerequisite Checklist

The following dependencies must be satisfied in order before creating the
trigger.

### 1. Ensure `cloudbuild.yaml` Exists (or Prepare `--inline-config`)

The trigger needs a build configuration to execute, and **whenever a dedicated
`--service-account` is used, Cloud Build requires
`options: { logging: CLOUD_LOGGING_ONLY }`**:

```yaml
options:
  logging: CLOUD_LOGGING_ONLY
```

*   **Action**: Check if `cloudbuild.yaml` and `Dockerfile` exist on the remote
    default branch
    (`git ls-tree "origin/${DEFAULT_BRANCH}" cloudbuild.yaml Dockerfile`).
*   **If present on the remote default branch**: Use
    `--build-config="cloudbuild.yaml"`.
*   **If `cloudbuild.yaml` or `Dockerfile` only exists locally (not committed to
    `origin/${DEFAULT_BRANCH}`)**: Pass
    `--inline-config=<PATH_TO_INLINE_CLOUDBUILD_YAML>` to
    `gcloud beta builds triggers create developer-connect` (writing the
    `Dockerfile` in a build step if `Dockerfile` is missing from the remote
    branch, and including `options: { logging: CLOUD_LOGGING_ONLY }`) so the
    remote build succeeds on the first try without
    `FAILED_PRECONDITION: Couldn't read commit`.

### 2. Ensure Artifact Registry Repository Exists

The `cloudbuild.yaml` file will reference an Artifact Registry repository to
push container images. This repository must exist before a build can succeed.

*   **Action**: Parse the `cloudbuild.yaml` file to identify the Artifact
    Registry image path (e.g.,
    `us-central1-docker.pkg.dev/my-project/my-app-repo/my-image`).
*   **Extract** the repository portion
    (`us-central1-docker.pkg.dev/my-project/my-app-repo`).
*   **Check** if this repository already exists in the target GCP project using
    `gcloud`:

    ```bash
    gcloud artifacts repositories describe <REPO_NAME> --location=<REGION> --project=<PROJECT_ID>
    ```
*   **If it does not exist**: Create it using `gcloud`:

    ```bash
    gcloud artifacts repositories create <REPO_NAME> \
      --repository-format=docker \
      --location=<REGION> \
      --project=<PROJECT_ID>
    ```

### 3. Ensure Developer Connect and Repository Link Exist (GitHub, GitLab, Bitbucket)

Cloud Build triggers connect to source code via Developer Connect across
**GitHub**, **GitLab**, and **Bitbucket**. The entire connection and repository
link must be in place.

1.  **Check for Connection**: First, check if a Developer Connect connection
    already exists for the relevant Git provider (**GitHub**, **GitLab**, or
    **Bitbucket**) in the target project and region:

    ```bash
    gcloud developer-connect connections list --location=<REGION> --project=<PROJECT_ID>
    ```
2.  **Create Connection (if needed)**: If no suitable connection exists, create
    one using `gcloud developer-connect connections create` based on the Git
    provider (and prompt the user to complete the authorization flow via the
    `installationState.actionUri` in the GCP Console if `STAGE != COMPLETE`):

    *   **GitHub**:

        ```bash
        gcloud developer-connect connections create <CONNECTION_ID> \
          --location=<REGION> \
          --project=<PROJECT_ID> \
          --github-config-app=developer-connect
        ```
    *   **GitLab (`gitlab.com` or GitLab Enterprise)**:

        ```bash
        gcloud developer-connect connections create <CONNECTION_ID> \
          --location=<REGION> \
          --project=<PROJECT_ID> \
          --gitlab-config-webhook-secret-version=<WEBHOOK_SECRET_VERSION> \
          --gitlab-config-authorizer-credential-user-token-secret-version=<AUTHORIZER_TOKEN_SECRET_VERSION> \
          --gitlab-config-read-authorizer-credential-user-token-secret-version=<READ_TOKEN_SECRET_VERSION>
        ```
    *   **Bitbucket (`bitbucket.org` or Bitbucket Data Center)**:

        ```bash
        gcloud developer-connect connections create <CONNECTION_ID> \
          --location=<REGION> \
          --project=<PROJECT_ID> \
          --bitbucket-cloud-config-workspace=<WORKSPACE> \
          --bitbucket-cloud-config-webhook-secret-version=<WEBHOOK_SECRET_VERSION> \
          --bitbucket-cloud-config-authorizer-credential-user-token-secret-version=<AUTHORIZER_TOKEN_SECRET_VERSION> \
          --bitbucket-cloud-config-read-authorizer-credential-user-token-secret-version=<READ_TOKEN_SECRET_VERSION>
        ```
3.  **Obtain Source URI**: The agent must know the exact URI of the source code
    repository (e.g., `https://github.com/<ORG>/<APP>.git`,
    `https://gitlab.com/<GROUP>/<APP>.git`, or
    `https://bitbucket.org/<WORKSPACE>/<APP>.git`). This should be obtained from
    the user-approved plan, `git remote get-url origin`, or by asking the user
    directly.
4.  **Check for Repository Link**: Check if a repository link for that specific
    URI already exists within the Developer Connect connection:

    ```bash
    gcloud developer-connect connections git-repository-links list \
      --connection=<CONNECTION_ID> \
      --location=<REGION> \
      --project=<PROJECT_ID>
    ```
5.  **Create Repository Link (if needed)**: If the link does not exist, create
    it using `gcloud`:

    ```bash
    gcloud developer-connect connections git-repository-links create <REPO_LINK_ID> \
      --connection=<CONNECTION_ID> \
      --clone-uri=<GIT_REPO_URI> \
      --location=<REGION> \
      --project=<PROJECT_ID>
    ```

    This link
    (`projects/<PROJECT_ID>/locations/<REGION>/connections/<CONNECTION_ID>/gitRepositoryLinks/<REPO_LINK_ID>`)
    is the resource that the Cloud Build trigger will formally point to.

### 4. Ensure Dedicated Service Account and Required IAM Roles Exist

Cloud Build triggers should **always** use a dedicated, user-managed service
account instead of the default Compute Engine service account to follow the
principle of least privilege. **CRITICAL: NEVER use the default Compute Engine
service account (typically formatted as
`[PROJECT_NUMBER]-compute@developer.gserviceaccount.com`), even if you observe
existing triggers in the project using it.**

1.  **Check or Create Service Account**:

    ```bash
    gcloud iam service-accounts describe <SA_NAME>@<PROJECT_ID>.iam.gserviceaccount.com --project=<PROJECT_ID> || \
    gcloud iam service-accounts create <SA_NAME> \
      --display-name="Cloud Build Trigger Service Account" \
      --project=<PROJECT_ID>
    ```
2.  **Grant Required Least-Privilege Roles to the Dedicated Service Account**:
    Grant the necessary roles (`roles/artifactregistry.writer`,
    `roles/developerconnect.readTokenAccessor`, `roles/logging.logWriter`,
    `roles/run.developer`, `roles/serviceusage.serviceUsageConsumer`) to
    `serviceAccount:<SA_NAME>@<PROJECT_ID>.iam.gserviceaccount.com` (if a build
    cache/artifact GCS bucket is needed beyond `CLOUD_LOGGING_ONLY`, grant
    `roles/storage.objectUser` scoped strictly to that bucket):

    ```bash
    for ROLE in \
      roles/artifactregistry.writer \
      roles/developerconnect.readTokenAccessor \
      roles/logging.logWriter \
      roles/run.developer \
      roles/serviceusage.serviceUsageConsumer; do
      gcloud projects add-iam-policy-binding <PROJECT_ID> \
        --member="serviceAccount:<SA_NAME>@<PROJECT_ID>.iam.gserviceaccount.com" \
        --role="$ROLE" \
        --condition=None
    done
    ```
3.  **Grant Service Agent Roles (Developer Connect & Cloud Build P4SAs)**:
    Retrieve the project number (`PROJECT_NUMBER=$(gcloud projects describe
    <PROJECT_ID> --format='value(projectNumber)')`) and ensure the Developer
    Connect and Cloud Build service agents have required permissions:

    ```bash
    PROJECT_NUMBER=$(gcloud projects describe <PROJECT_ID> --format='value(projectNumber)')

    # Developer Connect Service Agent
    gcloud projects add-iam-policy-binding <PROJECT_ID> \
      --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-devconnect.iam.gserviceaccount.com" \
      --role="roles/secretmanager.admin" \
      --condition=None

    # Cloud Build Service Agent
    for ROLE in roles/cloudbuild.serviceAgent roles/developerconnect.readTokenAccessor; do
      gcloud projects add-iam-policy-binding <PROJECT_ID> \
        --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-cloudbuild.iam.gserviceaccount.com" \
        --role="$ROLE" \
        --condition=None
    done

    # Allow Cloud Build Service Agent to act as the dedicated build SA and Cloud Run runtime SA
    gcloud iam service-accounts add-iam-policy-binding <SA_NAME>@<PROJECT_ID>.iam.gserviceaccount.com \
      --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-cloudbuild.iam.gserviceaccount.com" \
      --role="roles/iam.serviceAccountUser" \
      --project=<PROJECT_ID>
    ```

--------------------------------------------------------------------------------

## Final Step: Creating the Trigger via `gcloud`

Once all prerequisites are met, resolve the repository's **default branch in
remote source control** (do not worry about unpublished local branches) using
the Developer Connect repository link's read token + `git ls-remote --symref` so
it works across any Git provider (**GitHub**, **GitLab**, **Bitbucket**, etc.)
even when there is no local clone:

```bash
TOKEN=$(gcloud developer-connect connections git-repository-links fetch-read-token <REPO_LINK_ID> \
  --connection=<CONNECTION_ID> --location=<REGION> --project=<PROJECT_ID> --format="value(token)" --quiet 2>/dev/null || true)
if [ -n "$TOKEN" ]; then
  if echo "<GIT_REPO_URI>" | grep -qi "gitlab"; then
    GIT_USER="oauth2"
  elif echo "<GIT_REPO_URI>" | grep -qi "bitbucket"; then
    GIT_USER="x-token-auth"
  else
    GIT_USER="x-access-token"
  fi
  AUTH_HEADER="Authorization: Basic $(printf '%s:%s' "$GIT_USER" "$TOKEN" | base64 | tr -d '\n')"
  DEFAULT_BRANCH=$(GIT_TERMINAL_PROMPT=0 GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=http.extraHeader GIT_CONFIG_VALUE_0="$AUTH_HEADER" \
    git ls-remote --symref "<GIT_REPO_URI>" HEAD 2>/dev/null | awk '/^ref:/ {sub("refs/heads/", "", $2); print $2}')
else
  DEFAULT_BRANCH=$(GIT_TERMINAL_PROMPT=0 git ls-remote --symref "<GIT_REPO_URI>" HEAD 2>/dev/null | awk '/^ref:/ {sub("refs/heads/", "", $2); print $2}')
fi
```

Then check if the trigger already exists and create it using
`gcloud builds triggers create developer-connect`. **You MUST provide the full
resource name of the dedicated service account created in Step 4 to the
`--service-account` flag.**

```bash
gcloud builds triggers describe <TRIGGER_ID> --region=<REGION> --project=<PROJECT_ID> || \
gcloud builds triggers create developer-connect \
  --name=<TRIGGER_ID> \
  --region=<REGION> \
  --project=<PROJECT_ID> \
  --repository="projects/<PROJECT_ID>/locations/<REGION>/connections/<CONNECTION_ID>/gitRepositoryLinks/<REPO_LINK_ID>" \
  --branch-pattern="^${DEFAULT_BRANCH}$" \
  --build-config="cloudbuild.yaml" \
  --service-account="projects/<PROJECT_ID>/serviceAccounts/<SA_NAME>@<PROJECT_ID>.iam.gserviceaccount.com"
```

*(Note: If the trigger should run on tags instead of branches, replace
`--branch-pattern="^${DEFAULT_BRANCH}$"` with `--tag-pattern="<TAG_REGEX>"`.)*

### Running the Trigger Manually via `gcloud`

When invoking the trigger with `gcloud builds triggers run`, always target the
**default branch in remote source control** (`${DEFAULT_BRANCH}`, resolved from
`refs/remotes/origin/HEAD` or `git ls-remote --symref origin HEAD`; do not check
for or worry about unpublished local branches) and **strip any `^` or `$` regex
characters** (pass `--branch="${DEFAULT_BRANCH}"`, NOT
`--branch="^${DEFAULT_BRANCH}$"`):

```bash
gcloud builds triggers run <TRIGGER_ID> \
  --region=<REGION> \
  --project=<PROJECT_ID> \
  --branch="${DEFAULT_BRANCH}"
```

--------------------------------------------------------------------------------

## Troubleshooting Authentication, Permission & Trigger Errors

When creating or running a Developer Connect + Cloud Build trigger fails,
diagnose the exact root cause and never bypass the error by switching to local
Docker builds or the default Compute Engine service account:

1.  **`INVALID_ARGUMENT: if 'build.service_account' is specified, the build must
    either (a) specify 'build.logs_bucket', (b) use the CLOUD_LOGGING_ONLY
    logging option, or (c) use the NONE logging option`**:
    *   **Cause**: A custom `--service-account` is configured on the trigger,
        but the `cloudbuild.yaml` (or `--inline-config`) omits
        `options: { logging: CLOUD_LOGGING_ONLY }`.
    *   **Fix**: Add `options: { logging: CLOUD_LOGGING_ONLY }` to
        `cloudbuild.yaml` (or `--inline-config`) and ensure the custom service
        account has `roles/logging.logWriter`.
2.  **`PERMISSION_DENIED` when linking a repository or fetching a read token
    (`developerconnect.gitRepositoryLinks.fetchReadToken` /
    `developerconnect.gitRepositoryLinks.create`)**:
    *   **Cause**: Either the caller lacks
        `roles/developerconnect.readTokenAccessor` /
        `roles/developerconnect.admin`, or the GitHub/GitLab/Bitbucket App
        installation in Developer Connect does not have access to the target
        repository.
    *   **Fix**: Grant `roles/developerconnect.readTokenAccessor` (or
        `roles/developerconnect.admin`) to the caller and verify the repository
        is authorized in the Developer Connect connection settings.
3.  **`PERMISSION_DENIED: Caller does not have required permission to use
    service account ...` (`iam.serviceAccounts.actAs`)**:
    *   **Cause**: The caller or Cloud Build Service Agent lacks
        `roles/iam.serviceAccountUser` on the dedicated Cloud Build service
        account (`<SA_NAME>@<PROJECT_ID>.iam.gserviceaccount.com`).
    *   **Fix**: Run `gcloud iam service-accounts add-iam-policy-binding
        <SA_NAME>@<PROJECT_ID>.iam.gserviceaccount.com
        --member="<CALLER_OR_P4SA>" --role="roles/iam.serviceAccountUser"
        --project=<PROJECT_ID>`.
