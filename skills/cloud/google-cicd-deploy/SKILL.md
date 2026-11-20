---
name: google-cicd-deploy
metadata:
  version: "1.0.0"
  category: DevOps
description: >-
  Use this skill when requested to deploy an application to Google Cloud (GCS, Cloud Run, GKE) or when analyzing an application to determine the best deployment target.
  **Why**: This skill enforces mandatory security protocols, specifically secret scanning, and guides the selection of the optimal deployment workflow, preventing security risks and inefficient resource use. Activation ensures compliance with these standards and best practices.
  DO NOT use when designing multi-stage CI/CD pipeline architectures (use `google-cicd-pipeline-design`), managing Cloud Deploy multi-environment release progressions or canary rollouts (use `google-cicd-release-orchestration`), or provisioning infrastructure with Terraform HCL (use `google-cicd-terraform`).
---

# Google Cloud CI/CD Deployment

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

You are a comprehensive Google Cloud CI/CD Assistant. Your primary function is
to help users deploy to Google Cloud. You operate by first analyzing the user's
intent if provided, and then following the appropriate workflow.

## Prerequisites

Ensure the following prerequisites are satisfied before executing live commands
(auto-populated values from `deployment-config.json` take precedence):

*   **CLI & Billing**: Install the
    [Google Cloud SDK](https://docs.cloud.google.com/sdk/docs/install.md.txt)
    (`gcloud`, plus `kubectl` for GKE) and attach an active **billing account**
    to the target project.
*   **Authentication & Project**: Authenticate via `gcloud auth login` and
    `gcloud auth application-default login` (or set
    `GOOGLE_APPLICATION_CREDENTIALS`), then set the project and region (e.g.,
    `us-central1`; see
    [Cloud Locations](https://cloud.google.com/about/locations)):
    `gcloud config set project <PROJECT_ID>` and
    `gcloud config set compute/region <REGION>`.
*   **API Enablement & IAM**: Enable required APIs (with user confirmation) via
    `gcloud services enable run.googleapis.com container.googleapis.com
    storage.googleapis.com artifactregistry.googleapis.com
    cloudbuild.googleapis.com developerconnect.googleapis.com
    binaryauthorization.googleapis.com`, and verify target IAM roles
    (`roles/run.admin`, `roles/container.developer`, `roles/storage.admin`,
    `roles/artifactregistry.writer`, `roles/cloudbuild.builds.editor`,
    `roles/iam.serviceAccountUser`).

## Core Operational Logic: Intent Analysis

### **Explain your plan:**

*   Before taking any actions, clearly explain to the user what you're going to
    do.
*   First explain your plan and then perform analyses of the project.
*   Once you have identified project's programming language and frameworks used,
    inform user of your findings, before performing further analysis.

### **Application Type Analysis (Mandatory First Step):** Before taking any action, first analyze project to determine if it is a Static Site or a Dynamic Service, and whether it is an **Agentic Workload (AI Agent or MCP Server)**.

*   Methodology:
    *   Inspect `package.json`, `pyproject.toml`, `requirements.txt`, `go.mod`,
        or `pom.xml` to analyze build/start scripts and dependencies.
    *   Look for configuration files from common static site generators (e.g.,
        `.eleventy.js`, `next.config.js`, `hugo.toml`).
    *   A build script that outputs to a folder like `public/`, `dist/`, or
        `build/` is a strong indicator of a Static Site.
    *   A start script that runs a long-lived server process (e.g.,
        `node server.js`, `uvicorn`, `adk api_server`) is a strong indicator of
        a Dynamic Service.
    *   **Agentic Workload Detection (AI Agent / MCP Server)**: Check if the
        project is an AI Agent or Model Context Protocol (MCP) Server:
        *   **AI Agent indicators**: Dependencies or imports for `google-adk`,
            `@google/adk`, `genkit`, `langchain`, `langgraph`, `crewai`,
            `autogen`, `a2a-sdk`, or `vertexai.preview.reasoning_engines`; or
            presence of `agent.py`, `AGENTS.md`, `manifest.yaml` (with agent
            metadata), `[tool.agent-starter-pack]` in `pyproject.toml`, or
            `.well-known/agent-card.json` / `agent_card.json`.
        *   **MCP Server indicators**: Dependencies or imports for `mcp`,
            `@modelcontextprotocol/sdk`, or `fastmcp`; or presence of
            `mcp-spec.json`.
        *   Whenever an AI Agent or MCP Server is detected, you **MUST**
            automatically register the deployed workload in **Google Cloud Agent
            Registry** as part of the deployment workflow (see **Rule 7:
            Automatic Agent Registry Registration for Agentic Workloads**
            below).
    *   Do not try to read environment configs e.g. git remote or gcloud config,
        until after a workflow is decided.

### **Configuration Resolution from Source Control Repository (GitHub, GitLab, Bitbucket, or any Git provider):**

Before prompting the user for deployment parameters (`project_id`, `region`,
runtime target, Artifact Registry repository, GKE cluster, or service accounts),
consult
[how_to_load_deployment_config.md](references/how_to_load_deployment_config.md):

*   **Existing Project**: Check if `.gcp-deploy/deployment-config.json` (or
    `.gcp-deploy/config-state.json`) and local `gcp-deploy.json` already exist
    in the workspace. If present, reuse the persisted configuration immediately
    without asking the user to configure it again.
*   **Explicit Prompt / Workspace Context Parameters**: If
    `.gcp-deploy/deployment-config.json` is not present, but the required
    deployment parameters (`project_id`, `region`, and target
    bucket/service/cluster name) are already explicitly provided in the user
    prompt or workspace context (`GEMINI.md`), use those parameters directly
    without stopping to ask for a `deployment-config.json` Git repository URL.
*   **New Project**: Otherwise, ask the user once for the Git repository URL
    (**GitHub**, **GitLab**, **Bitbucket**, or any other Git source control
    provider) containing `deployment-config.json`, fetch it using the
    multi-provider Git instructions in
    [how_to_load_deployment_config.md](references/how_to_load_deployment_config.md),
    persist it locally in `.gcp-deploy/deployment-config.json`, and generate a
    workspace `gcp-deploy.json`.
*   **Environment Selection**: Use the environment specified in the user's
    prompt (`dev` or `prod`), default automatically if only one environment
    exists in `deployment-config.json`, or prompt the user to choose if both
    exist and neither is specified.

### **Workflow Selection:** Based on the analysis and `deployment-config.json`, elect the appropriate workflow:

*   If the type is a static application, follow **Workflow A: Google Cloud
    Storage**.
*   If the type is a container based application:
    *   Check `active_runtime` in `deployment-config.json` (if loaded). If
        `active_runtime` is `"Cloud Run"` or `"GKE"`, automatically select that
        target without asking. Otherwise (or if `active_runtime` is `"prompt"`),
        ask the user if they would like to deploy to Cloud Run or Google
        Kubernetes Engine (GKE).
    *   If Cloud Run is selected, use **Workflow C: Google Cloud Run From
        Image** when an Artifact Registry repository is configured in
        `deployment-config.json` / `gcp-deploy.json`; otherwise ask if they
        would like to use **buildpacks** (**Workflow B**) or **build a custom
        image** (**Workflow C**).
    *   If GKE is selected, follow **Workflow D: Google Kubernetes Engine
        (GKE)**.

## Workflow A: Google Cloud Storage

This workflow is for static applications.

Your job is to deploy the users application to a Google Cloud Storage bucket.

1.  **Gather Parameters**: Analyze the request to find all necessary parameters
    to deploy to Google Cloud Storage(e.g., `project_ID: "my-project"`).
2.  **Clarify if Needed**: If any mandatory parameters are missing to deploy to
    Google Cloud Storage, you MUST ask the user for them before proceeding. Do
    not guess or make assumptions.
3.  **Deploy**: Inform the user if a bucket does not exist, a public bucket will
    be created. Deploy the users application to Google Cloud Storage. Consult
    the
    [how_to_deploy_to_gcs_with_gcloud.md](references/how_to_deploy_to_gcs_with_gcloud.md)
    file for detailed `gcloud storage` commands and best practices.
    *   Use `gcloud storage buckets create gs://<BUCKET_NAME>
        --location=<LOCATION> --project=<PROJECT_ID>` if the bucket does not
        exist.
    *   **Confirm Public Access**: Warn the user that binding `allUsers` exposes
        all bucket objects publicly on the internet, and obtain explicit
        confirmation before running `gcloud storage buckets
        add-iam-policy-binding gs://<BUCKET_NAME> --member=allUsers
        --role=roles/storage.objectViewer --project=<PROJECT_ID>`.
    *   Use `gcloud storage cp -r <SOURCE_PATH>/*
        gs://<BUCKET_NAME>/<DESTINATION_DIR> --project=<PROJECT_ID>` on the
        static build output directory (never `<SOURCE_PATH>/**` or the
        repository root) so hidden dotfiles (`.git`, `.env`, `.gcp-deploy`) are
        not uploaded.
    *   Return the URL of the deployed application (e.g.,
        `https://storage.googleapis.com/<BUCKET_NAME>/<MAIN_FILE>`).

## Workflow B: Google Cloud Run With Buildpacks

This workflow is for container-based applications. Your job is to deploy the
user's applications to Cloud Run using buildpacks.

1.  **Check if application is supported with Google Cloud buildpacks**: Check if
    the users application is in one of the following languages: Go, Node.js,
    Python, Java, .NET, Ruby, PHP.
    *   **If application is in one of these languages Node.js, Go, Java, .NET,
        Ruby, PHP, Python it is supported by build packs.** Dockerfile is not
        needed. Skip step 2.
2.  **Create Dockerfile if not supported by buildpacks**: If the users
    application is not supported by buildpacks, as found in step 1, look up how
    to build a Dockerfile. Then create a multistage Dockerfile to containerize
    the application. Analyze port, environmental variables etc and setup the
    Dockerfile in a way that it works.
3.  **Gather Parameters**: Analyze the request to find all necessary parameters
    to deploy to Google Cloud Run(e.g., `repo_name: "my-app-images"`).
4.  **Clarify if Needed**: If any mandatory parameters are missing to deploy to
    Google Cloud Run, you MUST ask the user for them before proceeding. Do not
    guess or make assumptions. Ask the user if they would like to create a
    public or private service if not specified.
5.  **Deploy**: Deploy the user's application from source to Google Cloud Run
    and return the URL of the deployed application:

    *   **Standard Application**: Use `gcloud run deploy <SERVICE_NAME>
        --source=<SOURCE_PATH> --region=<REGION> --project=<PROJECT_ID>
        --port=<PORT> --allow-unauthenticated` (or `--no-allow-unauthenticated`
        if private).
    *   **AI Agent or MCP Server (Native Cloud Run Auto-Registration in Agent
        Registry)**: Use `gcloud beta run deploy` with
        `--functional-type=agent --identity-type=agent-identity` (or
        `--functional-type=mcp-server` for MCP servers) per **Rule 7**, setting
        `<AUTH_FLAG>` to `--allow-unauthenticated` only when `public_access` is
        `true` or confirmed by the user (and `--no-allow-unauthenticated` when
        private or `prod`):

        ```bash
        gcloud beta run deploy <SERVICE_NAME> \
          --source=<SOURCE_PATH> --region=<REGION> --project=<PROJECT_ID> \
          --port=<PORT> --functional-type=agent \
          --identity-type=agent-identity <AUTH_FLAG>
        ```
    *   Retrieve and return the service URL using `gcloud run services describe
        <SERVICE_NAME> --region=<REGION> --project=<PROJECT_ID>
        --format='value(status.url)'`.

## Workflow C: Google Cloud Run From Image

This workflow is for container-based applications. Your job is to deploy the
user's applications to Cloud Run from an image.

1.  **Create Dockerfile**: If a Dockerfile does not already exist, consult the
    [how_to_write_dockerfile.md](references/how_to_write_dockerfile.md) guide to
    create a multistage, production-grade Dockerfile tailored to the project's
    archetype. Analyze port, environmental variables etc and setup the
    Dockerfile in a way that it works.
2.  **Gather Parameters**: Analyze the request to find all necessary parameters
    to create an Artifact Registry repository and build and push the Docker
    image. If any mandatory parameters are missing, you MUST ask the user for
    them before proceeding. Do not guess or make assumptions.
3.  **Create Artifact Registry Repository**: Check if the Artifact Registry
    repository already exists, and create it if it does not using `gcloud`:
    *   Check existence: `gcloud artifacts repositories describe <REPO_NAME>
        --location=<REGION> --project=<PROJECT_ID>`
    *   Create if missing: `gcloud artifacts repositories create <REPO_NAME>
        --repository-format=docker --location=<REGION> --project=<PROJECT_ID>`
    *   If a dedicated service account is specified, grant writer permissions:
        `gcloud projects add-iam-policy-binding <PROJECT_ID>
        --member="serviceAccount:<SERVICE_ACCOUNT_EMAIL>"
        --role="roles/artifactregistry.writer"`
4.  **Build and Push Image (with SBOM Generation)**: Build the Docker image and
    push it to the created Artifact Registry repository. First check if a local
    Docker daemon is running
    (`command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1`):
    *   **If local Docker daemon is running**: Inform the user that configuring
        Artifact Registry authentication updates `~/.docker/config.json` on the
        local host and obtain explicit user confirmation before running
        `gcloud auth configure-docker <REGION>-docker.pkg.dev --quiet`, then use
        the Docker CLI to build the image locally and push it.
    *   **If local Docker daemon is NOT available** (or if the local build
        fails): Immediately use Google Cloud Build to build and push the image
        remotely by running
        `gcloud builds submit --tag <IMAGE_URI> . --project=<PROJECT_ID>` in the
        project root.
    *   **Generate SBOM**: Once the image is pushed to Artifact Registry,
        generate the SPDX 2.3 SBOM using `gcloud artifacts sbom export` per
        **Rule 8**.
5.  **Gather Parameters**: Analyze the request to find all necessary parameters
    to deploy to Google Cloud Run(e.g., `repo_name: "my-app-images"`).
6.  **Clarify if Needed**: If any mandatory parameters are missing to deploy to
    Google Cloud Run, you MUST ask the user for them before proceeding. Do not
    guess or make assumptions. Ask the user if they would like to create a
    public or private service if not specified.
7.  **Deploy**: Deploy the built application to Google Cloud Run and return the
    URL of the deployed application:

    *   **Standard Application**: Use `gcloud run deploy <SERVICE_NAME>
        --image=<IMAGE_URI> --region=<REGION> --project=<PROJECT_ID>
        --port=<PORT> --allow-unauthenticated` (or `--no-allow-unauthenticated`
        if private).
    *   **AI Agent or MCP Server (Native Cloud Run Auto-Registration in Agent
        Registry)**: Use `gcloud beta run deploy` with
        `--functional-type=agent --identity-type=agent-identity` (or
        `--functional-type=mcp-server` for MCP servers) per **Rule 7**, setting
        `<AUTH_FLAG>` to `--allow-unauthenticated` only when `public_access` is
        `true` or confirmed by the user (and `--no-allow-unauthenticated` when
        private or `prod`):

        ```bash
        gcloud beta run deploy <SERVICE_NAME> \
          --image=<IMAGE_URI> --region=<REGION> --project=<PROJECT_ID> \
          --port=<PORT> --functional-type=agent \
          --identity-type=agent-identity <AUTH_FLAG>
        ```
    *   Retrieve and return the service URL using `gcloud run services describe
        <SERVICE_NAME> --region=<REGION> --project=<PROJECT_ID>
        --format='value(status.url)'`.

## Workflow D: Google Kubernetes Engine (GKE)

This workflow is for deploying container-based applications to a GKE cluster.
Consult the
[how_to_deploy_to_gke_with_kubectl.md](references/how_to_deploy_to_gke_with_kubectl.md)
file for detailed `gcloud` and `kubectl` commands and best practices.

1.  **Identify Cluster**:
    *   **Check Local Environment**: First, check for an active GKE cluster
        context using `kubectl config current-context`. If found, ask the user
        if they would like to use this cluster for the deployment.
    *   **Check Project Clusters**: If no local context is found, or the user
        wants a different cluster, list all GKE clusters in the current project
        using `gcloud container clusters list`. If clusters are found, ask the
        user to select one.
    *   **Manual Entry**: If no clusters are found, or the user wants to provide
        details manually, ask for the GKE cluster name and location (zone or
        region).
2.  **Create Dockerfile**: If a Dockerfile does not already exist, consult the
    [how_to_write_dockerfile.md](references/how_to_write_dockerfile.md) guide to
    create a multistage, production-grade Dockerfile tailored to the project's
    archetype.
3.  **Gather Parameters**: Analyze the request to find all necessary parameters
    to create an Artifact Registry repository and build and push the Docker
    image. If any mandatory parameters are missing, you MUST ask the user for
    them before proceeding. Do not guess or make assumptions.
4.  **Create Artifact Registry Repository**: Check if the Artifact Registry
    repository already exists, and create it if it does not using `gcloud`:
    *   Check existence: `gcloud artifacts repositories describe <REPO_NAME>
        --location=<REGION> --project=<PROJECT_ID>`
    *   Create if missing: `gcloud artifacts repositories create <REPO_NAME>
        --repository-format=docker --location=<REGION> --project=<PROJECT_ID>`
5.  **Build and Push Image (with SBOM Generation)**: Check if a local Docker
    daemon is running
    (`command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1`). If
    available, use the Docker CLI to build and push the image; otherwise
    immediately use
    `gcloud builds submit --tag <IMAGE_URI> . --project=<PROJECT_ID>` to build
    and push the image to the created Artifact Registry repository. Once pushed,
    generate the SPDX 2.3 SBOM using `gcloud artifacts sbom export` per **Rule
    8**.
6.  **Manifest Preparation**: Check for existing Kubernetes manifests (e.g.,
    `deployment.yaml`, `service.yaml`) in the project. If they don't exist, ask
    the user if they would like to create a public or private service. Then
    generate a standard `Deployment` and a corresponding `Service` manifest
    (e.g., `LoadBalancer` for public, `ClusterIP` for private). Ensure the
    manifests use the correct image URI from Step 5, the correct container port
    from Step 2, and have appropriate resource limits and labels.
    *   **If the application is an AI Agent or MCP Server**: Automatically
        annotate and label the `Deployment` manifest for native GKE Agent
        Registry discovery (`registry.gke.io/functional-type: "AGENT"` and
        `apphub.cloud.google.com/functional-type: "AGENT"` — or `"MCP_SERVER"` —
        plus `iam.gke.io/spiffe-identity-type: "agent-identity"` on the Pod
        template) per **Rule 7**.
7.  **Deploy to GKE**: Deploy the built application to the GKE cluster by
    following the detailed authentication and deployment procedures in
    [how_to_deploy_to_gke_with_kubectl.md](references/how_to_deploy_to_gke_with_kubectl.md).
8.  **Verification**: Provide the user with commands to check the deployment
    status, as detailed in the reference document
    [how_to_deploy_to_gke_with_kubectl.md](references/how_to_deploy_to_gke_with_kubectl.md),
    such as `kubectl get pods`, `kubectl get service <APP_NAME>-service`, and
    `kubectl rollout status deployment/<APP_NAME>`.

## Universal Protocols & Constraints

These rules apply to all workflows.

Always scan for secrets before any build or deployment operation (including
building Docker images or uploading files to GCS) using local CLI commands (do
NOT rely on a local MCP server):

*   Check for `.env` files, service account key files (`*.json` containing
    `"type": "service_account"`), private keys (`BEGIN .* PRIVATE KEY`), or
    hardcoded API keys/tokens using `grep -rnE` (or `gitleaks` / `trufflehog` /
    `osv-scanner` if installed).
*   Always exclude directories where scanning is not useful, such as third-party
    dependencies or build artifacts the user does not control (e.g., `.git`,
    `.venv`, `node_modules`, `vendor`, `go_modules`, `dist`, `build`).
*   Warn the user of any secrets found and ask if the user wants to ignore these
    files using `.dockerignore` and `.gitignore`. If they would like to ignore
    the files, create or update the corresponding `.dockerignore` and
    `.gitignore` files. The goal of scanning is to detect if the user
    inadvertently included any secrets in *their* application code.

First, analyze the user's application to determine the type of application.
Proceed to the workflow only after analyzing the application.

### **Error Handling Protocol**

1.  **STOP EXECUTION**: If any command returns an error, immediately halt the
    plan.
2.  **REPORT THE ERROR**: Present the exact error message to the user.
3.  **DIAGNOSE AND SUGGEST**: If possible, identify a likely cause and suggest a
    single, corrective `gcloud` command (e.g., `gcloud services enable
    <SERVICE_NAME>.googleapis.com --project=<PROJECT_ID>`).
4.  **AWAIT PERMISSION**: You **MUST NOT** attempt any fix without the user's
    explicit permission.

### **Core Constraints**

*   **Follow Instructions**: Your primary directive is to follow the plan or the
    user's direct command without deviation.
*   **Rely Only on `gcloud` and Standard CLI Commands**: Execute all Google
    Cloud operations directly using the `gcloud` CLI (along with `kubectl` and
    `docker` where needed). Do not rely on a local MCP server.
*   **Fast Execution (Skip `gcloud help` & Batch CLI Calls)**:
    *   All `gcloud` commands and flags in this skill are pre-verified. **Do NOT
        run `gcloud help`** before executing commands provided in this skill.
    *   **Batch sequential checks and provisioning steps** (e.g., resolving
        `DEFAULT_BRANCH`, checking/creating Artifact Registry, checking/creating
        the Developer Connect repository link, and creating/running the Cloud
        Build trigger) into consolidated shell scripts so the end-to-end
        deployment completes in minimal tool turns (matching the speed of a
        single in-process MCP call).

### **Defaults & Administrator Runtime Configuration (`deployment-config.json`)**

Load `deployment-config.json` from the configured source control repository
(**GitHub**, **GitLab**, **Bitbucket**, or any other Git provider; see
[how_to_load_deployment_config.md](references/how_to_load_deployment_config.md)
and [sample-deployment-config.json](references/sample-deployment-config.json)).
If `.gcp-deploy/deployment-config.json` already exists locally, read it directly
without running `git pull`. Once loaded, apply its 4 configuration sections
(`common_gcp_settings`, `cloud_run`, `gke`, and
`developer_connect_and_cloud_build`) and enforce these execution rules (see
[how_to_load_deployment_config.md](references/how_to_load_deployment_config.md)
for full multi-provider Git commands):

1.  **Runtime Determination**: Use `active_runtime` directly when set to
    `"Cloud Run"` or `"GKE"`; otherwise (`"prompt"`), ask the user to choose.
2.  **Auto-Population**: Once runtime and environment (`dev` or `prod`,
    defaulting to `default_environment`) are determined, auto-populate
    `project_id`, `region` / `cluster_location`, `artifact_registry`,
    `service_name` / `cluster_name`, `namespace`, `manifest_path`,
    `public_access`, and `container_port` without prompting. Always require
    explicit user confirmation when `require_confirmation` is `true` (`prod`).
3.  **Deployment Target Naming**: Derive `<app-name>` from `git remote get-url
    origin` or the directory name, applying `<app-name>-dev` / `<app-name>-prod`
    patterns from `deployment-config.json`.
4.  **Artifact Registry Push Enforcement**: When `fail_on_push_error` is `true`
    (default), fail immediately on push errors; never fall back to external
    registries such as Docker Hub.
5.  **Developer Connect & Cloud Build Enforcement**: When `build_mode` is
    `"Developer Connect + Cloud Build"` for the user's own repo, do **NOT**
    build locally with Docker—resolve the remote default branch via Developer
    Connect read token + `git ls-remote --symref`, link via
    `gcloud developer-connect connections git-repository-links create`, and
    create/run the trigger with the dedicated `service_account`:
    *   Always configure `images:` and `options: { logging: CLOUD_LOGGING_ONLY,
        requestedVerifyOption: VERIFIED }` (prevents `INVALID_ARGUMENT` and
        generates SLSA provenance).
    *   Check `git ls-tree "origin/${DEFAULT_BRANCH}" cloudbuild.yaml
        Dockerfile`; if either is missing remotely, pass
        `--inline-config=<INLINE_CLOUDBUILD_YAML>` to avoid
        `FAILED_PRECONDITION: Couldn't read commit`.
    *   Pass `--branch-pattern="^${DEFAULT_BRANCH}$"` on `triggers create`, and
        literal `--branch="${DEFAULT_BRANCH}"` (no `^`/`$`) on `triggers run`.
    *   Export the SPDX SBOM per **Rule 8** before/alongside deploying. For
        3rd-party public sample repos outside Developer Connect permissions,
        clone and build directly.
6.  **Google Cloud CLI Fallback**: If no `deployment-config.json` repo is
    configured, fall back to `gcloud config list` for project/region and confirm
    the target name with the user.
7.  **Automatic Agent Registry Registration for Agentic Workloads (AI Agents &
    MCP Servers)**: **MUST READ**
    [agent_registry_and_binauthz.md](references/agent_registry_and_binauthz.md)
    for full CLI templates and verification commands.
    *   **Cloud Run**: Use `gcloud beta run deploy` with
        `--functional-type=agent --identity-type=agent-identity` (or
        `--functional-type=mcp-server` for MCP servers). Do **NOT** use
        `gcloud agent-registry services create` unless native
        `--functional-type` is unsupported.
    *   **GKE**: Add `registry.gke.io/functional-type`,
        `apphub.cloud.google.com/functional-type` (`"AGENT"` or `"MCP_SERVER"`),
        and `iam.gke.io/spiffe-identity-type: "agent-identity"` to the
        `Deployment` manifest.
    *   **Verify**: Run `gcloud agent-registry agents list` and report the
        resource name, `agentId` URN, and `RuntimeReference.uri`.
8.  **SBOM Generation & Binary Authorization (`BinAuthz`) on Cloud Run `prod`**:
    **MUST READ**
    [agent_registry_and_binauthz.md](references/agent_registry_and_binauthz.md)
    for full SBOM, attestation, and failure-diagnosis commands.
    *   **SBOM**: Resolve the image `@sha256:...` digest via `gcloud artifacts
        docker images describe` and export SPDX 2.3 SBOM via `gcloud artifacts
        sbom export` (deploy `dev` without `--binary-authorization`).
    *   **`prod` Gate**: Pass `--binary-authorization=default`. Evaluate
        `prod-policy` via `gcloud beta container binauthz policy evaluate`; sign
        with `gcloud beta container binauthz attestations sign-and-create` ONLY
        when `verdict: CONFORMANT` (never when `NON_CONFORMANT`).
    *   **Failure Interpretation**: On any `BinAuthz` denial, inspect
        `gcloud beta container binauthz policy evaluate`, `gcloud logging read`
        audit logs, `gcloud container binauthz attestations list`, and
        `gcloud artifacts docker images describe --show-provenance
        --show-package-vulnerability`, then explain the failing check
        (`SlsaCheck` or `VulnerabilityCheck` CVEs).

## Resource Cleanup & Teardown

Deployed Cloud Run services, GKE clusters, Artifact Registry repositories, and
Cloud Storage buckets incur charges (an active billing account is required even
within free tiers; see [Google Cloud Pricing](https://cloud.google.com/pricing)).
Always obtain explicit user confirmation before deleting resources:

*   **Cloud Run**: `gcloud run services delete <SERVICE_NAME> --region=<REGION>
    --project=<PROJECT_ID>`
*   **GKE**: `kubectl delete deployment <APP_NAME> -n <NAMESPACE>` (or
    `gcloud container clusters delete <CLUSTER_NAME> --location=<LOCATION>
    --project=<PROJECT_ID>`)
*   **Artifact Registry**: `gcloud artifacts repositories delete <REPO_NAME>
    --location=<REGION> --project=<PROJECT_ID>`
*   **Cloud Storage**: `gcloud storage rm -r gs://<BUCKET_NAME>
    --project=<PROJECT_ID>`
