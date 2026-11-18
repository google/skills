# Loading & Generating Organization Deployment Configuration (`deployment-config.json`)

This guide defines the standard procedure for retrieving, caching, generating,
and applying organization-wide deployment defaults (`deployment-config.json`)
from a central Git configuration repository hosted on **any source control
provider** (including **GitHub**, **GitLab**, **Bitbucket**, self-managed Git
servers, or other Git hosts) or directly from the active Google Cloud
environment, aligned with the Administrator Runtime Configuration schema.

--------------------------------------------------------------------------------

## Table of Contents

-   [1. Onboarding & Persistence Lifecycle](#1-onboarding-persistence-lifecycle)
    (Lines 24-59)
-   [2. Pulling `deployment-config.json` Across Source Control Providers](#2-pulling-deployment-configjson-across-source-control-providers)
    (Lines 63-169)
-   [3. Generating `deployment-config.json` from Enabled GCP Services or User-Specified Services](#3-generating-deployment-configjson-from-enabled-gcp-services-or-user-specified-services)
    (Lines 173-235)
-   [4. `deployment-config.json` Schema (Aligned with Local Skill Config Prototype)](#4-deployment-configjson-schema-aligned-with-local-skill-config-prototype)
    (Lines 239-319)
-   [5. Agent Execution Rules](#5-agent-execution-rules) (Lines 323-470)

## 1. Onboarding & Persistence Lifecycle

Before asking the developer for Google Cloud parameters (`project_id`, `region`,
runtime target, Artifact Registry repository, GKE cluster, or Developer Connect
/ Cloud Build settings), always resolve configuration in the following order:

1.  **Check Persisted Workspace Configuration First**:
    *   Inspect the workspace for an existing
        `.gcp-deploy/deployment-config.json` (and optional
        `./deployment-config.json`, `.gcp-deploy/config-state.json`, or local
        `gcp-deploy.json`).
    *   **Existing Project**: If `.gcp-deploy/deployment-config.json` is already
        present in the workspace, **read and use it immediately without asking
        the developer to re-configure it and without running `git pull`**
        (avoiding unnecessary network or credential prompt delays).
2.  **Explicit Prompt / Workspace Context Parameters**:
    *   If `.gcp-deploy/deployment-config.json` does not exist locally, but the
        required deployment parameters (`project_id`, `region`, and target
        resource name) are already explicitly provided in the user prompt or
        workspace context (`GEMINI.md`, `CLAUDE.md`, or `AGENTS.md`), use those
        parameters directly without stopping to ask for a
        `deployment-config.json` Git repository URL.
3.  **New Project Onboarding**:
    *   Otherwise, if no configuration state exists in the workspace, ask the
        developer **once**:

        > *"Please provide the Git repository URL (GitHub, GitLab, Bitbucket,
        > or your source control provider) containing your organization's
        > `deployment-config.json` (or let me know if you want to generate one
        > from your GCP project or configure parameters manually)."*
    *   Once fetched or generated, save the file to
        `.gcp-deploy/deployment-config.json` (and `./deployment-config.json`
        when generating a new config), record the repository URL in
        `.gcp-deploy/config-state.json`, and ensure `.gcp-deploy/` is ignored in
        `.gitignore` and `.dockerignore` so future prompts in the project
        automatically reuse it.

--------------------------------------------------------------------------------

## 2. Pulling `deployment-config.json` Across Source Control Providers

Detect the Git provider from the repository URL (HTTPS or SSH) and retrieve
`deployment-config.json` using the methods below.

### Method A: Universal Git Sparse Checkout (Works Across All Source Control Providers — GitHub, GitLab, Bitbucket, and Any Git Host)

This universal method works with **any Git source control provider** (public or
private). Always pass `GIT_TERMINAL_PROMPT=0` so `git` never blocks on an
interactive prompt if local credentials are not configured:

```bash
mkdir -p .gcp-deploy
rm -rf .gcp-deploy/config-repo
GIT_TERMINAL_PROMPT=0 git clone --depth 1 --filter=blob:none --sparse "<GIT_REPO_URL>" .gcp-deploy/config-repo
git -C .gcp-deploy/config-repo sparse-checkout set deployment-config.json
cp .gcp-deploy/config-repo/deployment-config.json .gcp-deploy/deployment-config.json
```

*(If a specific branch or tag `<REF>` is specified, pass `--branch <REF>` to
`git clone`.)*

### Method B: Private Repo Retrieval via Google Cloud Developer Connect Token (GitHub, GitLab, Bitbucket)

If the configuration repository is private and local Git credentials are not
configured in the terminal (`GIT_TERMINAL_PROMPT=0 git clone` fails with an
authentication error), fetch a short-lived read token from Google Cloud
Developer Connect (creating the repository link first if needed) and clone with
`sparse-checkout`:

```bash
PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
REGION=${REGION:-us-central1}
# Find existing connection and repo link (or create the repo link if missing)
CONNECTION_ID=$(gcloud developer-connect connections list --location="$REGION" --project="$PROJECT_ID" --format="value(name.basename())" --limit=1 --quiet)
REPO_LINK_ID=$(gcloud developer-connect connections git-repository-links list --connection="$CONNECTION_ID" --location="$REGION" --project="$PROJECT_ID" --filter="cloneUri:<GIT_REPO_URL>" --format="value(name.basename())" --limit=1 --quiet)
TOKEN=$(gcloud developer-connect connections git-repository-links fetch-read-token "$REPO_LINK_ID" --connection="$CONNECTION_ID" --location="$REGION" --project="$PROJECT_ID" --format="value(token)" --quiet)

# Pass token via in-memory Git HTTP header (x-access-token for GitHub, oauth2 for GitLab, x-token-auth for Bitbucket)
# so the secret is never written to .git/config on disk or exposed on the process command line
if echo "<GIT_REPO_URL>" | grep -qi "gitlab"; then
  GIT_USER="oauth2"
elif echo "<GIT_REPO_URL>" | grep -qi "bitbucket"; then
  GIT_USER="x-token-auth"
else
  GIT_USER="x-access-token"
fi
AUTH_HEADER="Authorization: Basic $(printf '%s:%s' "$GIT_USER" "$TOKEN" | base64 | tr -d '\n')"
rm -rf .gcp-deploy/config-repo
GIT_TERMINAL_PROMPT=0 GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=http.extraHeader GIT_CONFIG_VALUE_0="$AUTH_HEADER" \
  git clone --depth 1 --filter=blob:none --sparse "<GIT_REPO_URL>" .gcp-deploy/config-repo
git -C .gcp-deploy/config-repo sparse-checkout set deployment-config.json
cp .gcp-deploy/config-repo/deployment-config.json .gcp-deploy/deployment-config.json
rm -rf .gcp-deploy/config-repo
```

### Method C: Provider-Specific CLI & Raw HTTP Fallbacks

If direct single-file retrieval is preferred over `git clone`:

#### 1. GitHub (`github.com` or GitHub Enterprise)

*   **Via GitHub CLI (`gh`)** *(handles private repos automatically)*:

    ```bash
    gh api "repos/<OWNER>/<REPO>/contents/deployment-config.json?ref=<BRANCH>" \
      -H "Accept: application/vnd.github.raw" > .gcp-deploy/deployment-config.json
    ```
*   **Via Raw HTTPS**:

    ```bash
    curl -sSfL ${GITHUB_TOKEN:+-H "Authorization: Bearer $GITHUB_TOKEN"} \
      "https://raw.githubusercontent.com/<OWNER>/<REPO>/<BRANCH>/deployment-config.json" \
      -o .gcp-deploy/deployment-config.json
    ```

#### 2. GitLab (`gitlab.com` or Self-Managed GitLab)

*   **Via GitLab CLI (`glab`)** *(handles private repos automatically; replace
    `/` in `<GROUP>/<PROJECT>` with `%2F`)*:

    ```bash
    glab api "projects/<URL_ENCODED_PROJECT_PATH>/repository/files/deployment-config.json/raw?ref=<BRANCH>" \
      > .gcp-deploy/deployment-config.json
    ```
*   **Via GitLab REST API / Raw HTTPS**:

    ```bash
    curl -sSfL ${GITLAB_TOKEN:+-H "PRIVATE-TOKEN: $GITLAB_TOKEN"} \
      "https://<GITLAB_HOST>/<GROUP>/<PROJECT>/-/raw/<BRANCH>/deployment-config.json" \
      -o .gcp-deploy/deployment-config.json
    ```

#### 3. Bitbucket (`bitbucket.org` or Bitbucket Data Center)

*   **Via Bitbucket Cloud API / Raw HTTPS**:

    ```bash
    curl -sSfL ${BITBUCKET_TOKEN:+-H "Authorization: Bearer $BITBUCKET_TOKEN"} \
      "https://api.bitbucket.org/2.0/repositories/<WORKSPACE>/<REPO_SLUG>/src/<BRANCH>/deployment-config.json" \
      -o .gcp-deploy/deployment-config.json
    ```

    *(Or with Bitbucket App Password: `curl -sSfL -u
    "$BITBUCKET_USERNAME:$BITBUCKET_APP_PASSWORD"
    "https://bitbucket.org/<WORKSPACE>/<REPO_SLUG>/raw/<BRANCH>/deployment-config.json"
    -o .gcp-deploy/deployment-config.json`)*

--------------------------------------------------------------------------------

## 3. Generating `deployment-config.json` from Enabled GCP Services or User-Specified Services

When the user asks to **generate a deployment configuration file** based on:

*   The services enabled in their GCP environment (e.g., *"Generate a deployment
    configuration file based on the services enabled in my GCP environment"*),
    OR
*   A specific subset of services (e.g., *"Generate a deployment configuration
    file that utilizes Cloud Run, Artifact Registry, Developer Connect, and
    Cloud Build"*):

### Step 1: Discover Active GCP Services and Existing CI/CD Resources

Run a single batched shell snippet to inspect enabled APIs and discover existing
Artifact Registry repositories, Developer Connect connections, Cloud Run
services, and GKE clusters:

```bash
export CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:google-cicd-release-orchestration)"
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"

# 1. List enabled CI/CD & runtime APIs
ENABLED_APIS=$(gcloud services list --enabled --project="$PROJECT_ID" \
  --filter="config.name:(run.googleapis.com OR container.googleapis.com OR artifactregistry.googleapis.com OR cloudbuild.googleapis.com OR developerconnect.googleapis.com OR binaryauthorization.googleapis.com)" \
  --format="value(config.name)" --quiet 2>/dev/null || true)

# 2. Discover existing Artifact Registry Docker repositories
AR_REPO=$(gcloud artifacts repositories list --project="$PROJECT_ID" --location="$REGION" \
  --filter="format:DOCKER" --format="value(name.basename())" --limit=1 --quiet 2>/dev/null || true)

# 3. Discover existing Developer Connect connection
DEVCONNECT_ID=$(gcloud developer-connect connections list --project="$PROJECT_ID" --location="$REGION" \
  --format="value(name.basename())" --limit=1 --quiet 2>/dev/null || true)

# 4. Discover existing GKE cluster (if container.googleapis.com is enabled)
GKE_CLUSTER=$(gcloud container clusters list --project="$PROJECT_ID" --region="$REGION" \
  --format="value(name)" --limit=1 --quiet 2>/dev/null || true)
```

### Step 2: Populate and Persist `deployment-config.json`

1.  **Include Only Requested / Enabled Runtime & CI/CD Sections**:
    *   Always include `active_runtime`, `default_environment`,
        `fail_on_push_error`, and `common_gcp_settings` (`project_id`,
        `region`).
    *   Include `cloud_run` (`dev` and `prod`) when `run.googleapis.com` is
        enabled or Cloud Run is requested. Set `active_runtime` to `"Cloud Run"`
        if Cloud Run is the primary runtime.
    *   Include `gke` (`dev` and `prod`) when `container.googleapis.com` is
        enabled or GKE is requested (if the user explicitly requests *only*
        Cloud Run, Artifact Registry, Developer Connect, and Cloud Build, you
        may either omit `gke` or leave `active_runtime: "Cloud Run"`).
    *   Include `developer_connect_and_cloud_build` when
        `cloudbuild.googleapis.com` or `developerconnect.googleapis.com` is
        enabled or requested, populating `connection_id` with the discovered
        `$DEVCONNECT_ID` (or `"my-devconnect-connection"` default) and
        `service_account` with
        `projects/${PROJECT_ID}/serviceAccounts/cloudbuild-runner@${PROJECT_ID}.iam.gserviceaccount.com`.
2.  **Save to Both Workspace Locations**:
    *   Write the generated JSON to both `./deployment-config.json` and
        `./.gcp-deploy/deployment-config.json` so subsequent deployment commands
        in the same session or repository immediately pick it up.

--------------------------------------------------------------------------------

## 4. `deployment-config.json` Schema (Aligned with Local Skill Config Prototype)

The `.gcp-deploy/deployment-config.json` file (as well as any root-level
`./deployment-config.json` or local `gcp-deploy.json` workspace alias, which use
this identical JSON schema) maps 1-to-1 to the 4 configuration sections in the
CI/CD integration prototype:

1.  **Runtime Selection & Common Settings** (`active_runtime`,
    `default_environment`, `fail_on_push_error`, `common_gcp_settings`)
2.  **Runtime: Google Cloud Run Configuration** (`cloud_run.dev`,
    `cloud_run.prod`)
3.  **Runtime: Google Kubernetes Engine (GKE) Configuration** (`gke.dev`,
    `gke.prod`)
4.  **Developer Connect & Cloud Build Configuration** (`build_mode`,
    `developer_connect`, `cloud_build_trigger`)

```json
{
  "active_runtime": "Cloud Run",
  "default_environment": "dev",
  "fail_on_push_error": true,
  "common_gcp_settings": {
    "project_id": "my-gcp-project",
    "region": "us-central1"
  },
  "cloud_run": {
    "dev": {
      "project_id": "my-gcp-project",
      "region": "us-central1",
      "artifact_registry": "us-central1-docker.pkg.dev/my-gcp-project/my-app-images-dev",
      "service_name": "<app-name>-dev",
      "public_access": true,
      "container_port": 8080
    },
    "prod": {
      "project_id": "my-gcp-project",
      "region": "us-central1",
      "artifact_registry": "us-central1-docker.pkg.dev/my-gcp-project/my-app-images-prod",
      "service_name": "<app-name>-prod",
      "public_access": false,
      "container_port": 8080,
      "require_confirmation": true,
      "binary_authorization": "default",
      "binary_authorization_policy": "prod-policy"
    }
  },
  "gke": {
    "dev": {
      "project_id": "my-gcp-project",
      "cluster_location": "us-central1",
      "cluster_name": "my-gke-cluster-dev",
      "namespace": "dev",
      "artifact_registry": "us-central1-docker.pkg.dev/my-gcp-project/my-app-images-dev",
      "manifest_path": "./kubernetes-manifests/"
    },
    "prod": {
      "project_id": "my-gcp-project",
      "cluster_location": "us-central1",
      "cluster_name": "my-gke-cluster-prod",
      "namespace": "prod",
      "artifact_registry": "us-central1-docker.pkg.dev/my-gcp-project/my-app-images-prod",
      "manifest_path": "./release/kubernetes-manifests.yaml",
      "require_confirmation": true
    }
  },
  "developer_connect_and_cloud_build": {
    "build_mode": "Developer Connect + Cloud Build",
    "developer_connect": {
      "location": "us-central1",
      "connection_id": "my-devconnect-connection"
    },
    "cloud_build_trigger": {
      "project_id": "my-gcp-project",
      "region": "us-central1",
      "service_account": "projects/my-gcp-project/serviceAccounts/cloudbuild-runner@my-gcp-project.iam.gserviceaccount.com",
      "default_branch": "^main$",
      "auto_run_trigger": true
    }
  }
}
```

--------------------------------------------------------------------------------

## 5. Agent Execution Rules

When `deployment-config.json` is loaded or generated, enforce the following 8
execution rules:

1.  **Runtime Determination**:
    *   If `active_runtime` is set to `"Cloud Run"` or `"GKE"` (and not
        overridden by the user prompt), use that target directly without asking.
    *   If set to `"prompt"`, ask the user: *"Would you like to deploy to Cloud
        Run or GKE?"*
2.  **Environment Determination & Auto-Population**:
    *   Use the environment specified in the user's prompt (`dev` or `prod`). If
        unspecified, use `default_environment` (or if only one environment
        exists in `deployment-config.json`, default to that environment;
        otherwise prompt the user).
    *   Once the runtime (`cloud_run` or `gke`) and environment (`dev` or
        `prod`) are determined, **automatically populate all parameters from
        that section without asking the user** for project ID, region, Artifact
        Registry URI, service/cluster name, namespace, manifest path, or
        container port.
    *   When `require_confirmation` is `true` (always enforced for `prod`),
        always require explicit user confirmation before deploying to `prod`
        unless the user prompt already explicitly confirms `prod` deployment.
3.  **Deployment Target Naming**:
    *   Derive `<app-name>` from the Git repository name
        (`git remote get-url origin`) or current directory name, and apply the
        configured environment pattern (e.g., `<app-name>-dev` or
        `<app-name>-prod`).
4.  **Artifact Registry Push Enforcement**:
    *   When `fail_on_push_error` is `true` (default), pushing the image to the
        configured `artifact_registry` URI is mandatory. If the push fails for
        any reason (authentication, permissions, network, or Cloud Build
        errors), **immediately fail the deployment and report the error to the
        user**. Never bypass Artifact Registry by falling back to external or
        public registries (such as Docker Hub).
5.  **Developer Connect & Cloud Build Enforcement**:

    *   Whenever `build_mode` is `"Developer Connect + Cloud Build"` (or
        `"developer-connect"`) and deploying from the user's own source control
        repository (**GitHub**, **GitLab**, **Bitbucket**, or any supported Git
        provider), **do NOT build locally using Docker CLI** and **do NOT check
        or worry about unpublished local branches**—always use the **default
        branch in the remote source control repository**.
    *   Determine the remote repository's default branch universally across any
        Git provider (even for private repos with no local clone) via Developer
        Connect's read token + `git ls-remote --symref`:

        ```bash
        TOKEN=$(gcloud developer-connect connections git-repository-links fetch-read-token <REPO_LINK_ID> \
          --connection=<CONNECTION_ID> --location=<REGION> --project=<PROJECT_ID> --format="value(token)" --quiet 2>/dev/null || true)
        if [ -n "$TOKEN" ]; then
          AUTH_HEADER="Authorization: Basic $(printf 'x-access-token:%s' "$TOKEN" | base64 | tr -d '\n')"
          DEFAULT_BRANCH=$(GIT_TERMINAL_PROMPT=0 GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=http.extraHeader GIT_CONFIG_VALUE_0="$AUTH_HEADER" \
            git ls-remote --symref "<GIT_REPO_URI>" HEAD 2>/dev/null | awk '/^ref:/ {sub("refs/heads/", "", $2); print $2}')
        else
          DEFAULT_BRANCH=$(GIT_TERMINAL_PROMPT=0 git ls-remote --symref "<GIT_REPO_URI>" HEAD 2>/dev/null | awk '/^ref:/ {sub("refs/heads/", "", $2); print $2}')
        fi
        ```

        *(Only fall back to `default_branch` in `deployment-config.json` with
        `^` and `$` stripped if the remote `HEAD` ref cannot be resolved.)*
    *   Automatically link the repository to Developer Connect using
        `gcloud developer-connect connections git-repository-links create` under
        the configured `developer_connect.connection_id`.
    *   Create or run the Cloud Build trigger using
        `gcloud builds triggers create developer-connect` (or
        `gcloud beta builds triggers create developer-connect`) and
        `gcloud builds triggers run` with the pre-configured dedicated
        `cloud_build_trigger.service_account`:

        *   **Mandatory `CLOUD_LOGGING_ONLY`**: Always include
            `options: { logging: CLOUD_LOGGING_ONLY }` in the Cloud Build
            configuration when using a dedicated `--service-account`.
        *   **Check Remote Branch for `cloudbuild.yaml` & `Dockerfile`**:
            Inspect
            `git ls-tree "origin/${DEFAULT_BRANCH}" cloudbuild.yaml Dockerfile`.
            If `cloudbuild.yaml` or `Dockerfile` is not committed on
            `origin/${DEFAULT_BRANCH}`, use
            `--inline-config=<INLINE_CLOUDBUILD_YAML>` (with
            `options: { logging: CLOUD_LOGGING_ONLY }` and inline `Dockerfile`
            creation if needed) so the trigger succeeds on the first run.
        *   **Use Remote Default Branch & Strip Regex Anchors for
            `triggers run`**: When creating a trigger, pass
            `--branch-pattern="^${DEFAULT_BRANCH}$"`. When calling `gcloud
            builds triggers run <TRIGGER_ID> --branch="${DEFAULT_BRANCH}"`,
            always pass the literal default branch name without `^` or `$` regex
            anchors.
        *   **Batch CLI Execution**: Combine Artifact Registry check/create,
            Developer Connect repo link check/create, and Cloud Build trigger
            check/create/run into a single shell script without calling
            `gcloud help` first.
    *   Use the resulting Artifact Registry image for subsequent Cloud Run or
        GKE deployments.
    *   For 3rd-party public sample repositories (which are outside the user's
        Developer Connect permissions), clone and build directly.
6.  **Secret Leak Interception & Secret Manager Enforcement**:

    *   Before building or packaging any image, scan the workspace for `.env*`,
        `*.pem`, `*.key`, `*credentials*.json`, and hardcoded secrets in
        `Dockerfile` (`ENV`/`ARG`) or Kubernetes manifests.
    *   Ensure secret files are added to `.dockerignore` and `.gcloudignore`,
        remove hardcoded secrets from `Dockerfile`/manifests, and recommend or
        configure **Google Cloud Secret Manager** (`--set-secrets` on Cloud Run
        or Secret Manager CSI driver / secret references on GKE).
7.  **Automatic Agent Registry Registration for AI Agents & MCP Servers**:

    *   Inspect the codebase (`requirements.txt`, `pyproject.toml`,
        `package.json`, `agent.py`, `mcp_server.py`) before deploying.
    *   If the workload is an **AI Agent** (`google-adk`, `langchain`,
        `langgraph`, `crewai`, `autogen`) or **MCP Server** (`mcp`, `fastmcp`,
        `@modelcontextprotocol/sdk`):
        *   Enable `agentregistry.googleapis.com` (`gcloud services enable
            agentregistry.googleapis.com --project=<PROJECT_ID> --quiet`).
        *   On **Cloud Run**, deploy with `gcloud beta run deploy` using
            `--functional-type=agent --identity-type=agent-identity` (for AI
            agents) or `--functional-type=mcp-server` (for MCP servers) and
            verify discovery via `gcloud agent-registry agents list` or
            `gcloud agent-registry mcp-servers list`
            (`--location=<REGION> --project=<PROJECT_ID>`).
        *   On **GKE**, add
            `metadata.labels["registry.gke.io/functional-type"]: "AGENT"` (or
            `"MCP_SERVER"`),
            `metadata.annotations["apphub.cloud.google.com/functional-type"]:
            "AGENT"` (or `"MCP_SERVER"`), and
            `spec.template.metadata.annotations["iam.gke.io/spiffe-identity-type"]:
            "agent-identity"` to the Kubernetes `Deployment`.
8.  **SBOM Generation on Image Build & Binary Authorization Enforcement on Cloud
    Run `prod`**:

    *   After pushing a container image to Artifact Registry, resolve its
        `@sha256:...` digest and export its SPDX SBOM using `gcloud artifacts
        sbom export --uri="<IMAGE_URI>@<DIGEST>" --project=<PROJECT_ID>`.
    *   When deploying to `cloud_run.prod` with
        `"binary_authorization": "default"`:
        *   Pass `--binary-authorization=default` to `gcloud run deploy`.
        *   Before deploying to `prod`, evaluate the Binary Authorization policy
            via `gcloud beta container binauthz policy evaluate
            "${BINARY_AUTHZ_POLICY:-prod-policy}" --platform=cloudRun
            --project=<PROJECT_ID> --image="<IMAGE_URI>@<DIGEST>" --format=yaml`
            and check existing attestations via
            `gcloud container binauthz attestations list
            --artifact-url="https://<IMAGE_URI>@<DIGEST>"
            --project=<PROJECT_ID>`. If `verdict: CONFORMANT` and an attestor
            signature is required, sign the digest via
            `gcloud beta container binauthz attestations sign-and-create
            --artifact-url="https://<IMAGE_URI>@<DIGEST>"`; if
            `verdict: NON_CONFORMANT`, do NOT sign and explain the failing SLSA
            provenance or vulnerability check.
