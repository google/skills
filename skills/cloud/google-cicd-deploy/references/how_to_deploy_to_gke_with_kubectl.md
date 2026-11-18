# How to Deploy to Google Kubernetes Engine (GKE) with `kubectl`

This document outlines the standard procedure for deploying containerized
applications, AI Agents, and MCP Servers to a Google Kubernetes Engine (GKE)
cluster using standard CLI tools (`gcloud`, `kubectl`).

--------------------------------------------------------------------------------

## Table of Contents

-   [Step 1: Gather Deployment Parameters](#step-1-gather-deployment-parameters)
    (Lines 23-40)
-   [Step 2: Authenticate with the GKE Cluster & Ensure Namespace Exists](#step-2-authenticate-with-the-gke-cluster-ensure-namespace-exists)
    (Lines 44-59)
-   [Step 3: Prepare Kubernetes Manifests](#step-3-prepare-kubernetes-manifests)
    (Lines 63-167)
-   [Step 4: Deploy Build Artifacts](#step-4-deploy-build-artifacts) (Lines
    171-177)
-   [Step 5: Verification](#step-5-verification) (Lines 181-198)
-   [Step 6: Troubleshooting GKE Authentication & Permission Errors](#step-6-troubleshooting-gke-authentication-permission-errors)
    (Lines 202-241)

## Step 1: Gather Deployment Parameters

Before executing any commands, identify the following parameters (from
`.gcp-deploy/deployment-config.json` `gke.<env>` if available, or from the user
prompt/workspace context):

*   **`PROJECT_ID`**: The Google Cloud project where the GKE cluster and
    Artifact Registry are hosted.
*   **`CLUSTER_NAME`**: The name of the GKE cluster (e.g., `my-gke-cluster-dev`
    or `my-gke-cluster-prod`).
*   **`LOCATION`**: The geographic location (zone or region) of the cluster
    (e.g., `us-central1` or `us-central1-a`).
*   **`NAMESPACE`**: The target Kubernetes namespace (e.g., `dev`, `prod`, or
    `default`).
*   **`IMAGE_URI`**: The full URI of the container image in Artifact Registry
    (e.g., `us-central1-docker.pkg.dev/my-project/my-repo/my-image:latest`).
*   **`MANIFEST_PATH`**: The path to the Kubernetes manifest files (e.g.,
    `./kubernetes-manifests/` or `./k8s/`).

--------------------------------------------------------------------------------

## Step 2: Authenticate with the GKE Cluster & Ensure Namespace Exists

Use the `gcloud` CLI to retrieve credentials for the cluster
(`USE_GKE_GCLOUD_AUTH_PLUGIN=True`) and ensure the target namespace exists
before applying manifests:

```bash
export USE_GKE_GCLOUD_AUTH_PLUGIN=True

CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:google-cicd-deploy)" \
gcloud container clusters get-credentials "<CLUSTER_NAME>" \
    --location="<LOCATION>" \
    --project="<PROJECT_ID>"

kubectl create namespace "<NAMESPACE>" --dry-run=client -o yaml | kubectl apply -f -
```

--------------------------------------------------------------------------------

## Step 3: Prepare Kubernetes Manifests

Ensure that the Kubernetes manifests (typically `deployment.yaml` and
`service.yaml`) are correctly configured.

### 1. Update the Image URI

The `image:` field in the `Deployment` manifest MUST be updated to point to the
`IMAGE_URI` pushed to Artifact Registry during the build step.

### 2. Standard Manifest Example (if none exist)

If the project does not already have manifests, generate a basic set under
`<MANIFEST_PATH>`:

**`deployment.yaml`**:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: <APP_NAME>
  namespace: <NAMESPACE>
  labels:
    app: <APP_NAME>
spec:
  replicas: 1
  selector:
    matchLabels:
      app: <APP_NAME>
  template:
    metadata:
      labels:
        app: <APP_NAME>
    spec:
      containers:
      - name: <APP_NAME>
        image: <IMAGE_URI>
        ports:
        - containerPort: <CONTAINER_PORT>
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

**`service.yaml`**:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: <APP_NAME>-service
  namespace: <NAMESPACE>
spec:
  selector:
    app: <APP_NAME>
  ports:
    - protocol: TCP
      port: 80
      targetPort: <CONTAINER_PORT>
  type: LoadBalancer
```

### 3. Agentic Workload Labels & Annotations (AI Agents & MCP Servers)

If the workload being deployed to GKE is an **AI Agent** (`google-adk`,
`langchain`, `langgraph`, `crewai`, `autogen`) or **MCP Server** (`mcp`,
`fastmcp`, `@modelcontextprotocol/sdk`), enable `agentregistry.googleapis.com`
and automatically add the Google Cloud Agent Registry discovery labels and
SPIFFE identity annotations to the `Deployment` manifest (`"AGENT"` for AI
agents or `"MCP_SERVER"` for MCP servers):

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: <APP_NAME>
  namespace: <NAMESPACE>
  labels:
    app: <APP_NAME>
    registry.gke.io/functional-type: "AGENT" # Or "MCP_SERVER"
  annotations:
    apphub.cloud.google.com/functional-type: "AGENT" # Or "MCP_SERVER"
spec:
  replicas: 1
  selector:
    matchLabels:
      app: <APP_NAME>
  template:
    metadata:
      labels:
        app: <APP_NAME>
      annotations:
        iam.gke.io/spiffe-identity-type: "agent-identity"
    spec:
      containers:
      - name: <APP_NAME>
        image: <IMAGE_URI>
        ports:
        - containerPort: <CONTAINER_PORT>
```

--------------------------------------------------------------------------------

## Step 4: Deploy Build Artifacts

Apply the manifests to the target namespace in the GKE cluster:

```bash
kubectl apply -f "<MANIFEST_PATH>" -n "<NAMESPACE>"
```

--------------------------------------------------------------------------------

## Step 5: Verification

After the deployment is applied, verify the rollout status, external IP, and (if
applicable) Agent Registry discovery:

1.  **Check Rollout Status**:
    `kubectl rollout status deployment/<APP_NAME> -n <NAMESPACE> --timeout=180s`
2.  **Check Pod Status**: `kubectl get pods -n <NAMESPACE>`
3.  **Check Service IP**:
    `kubectl get service <APP_NAME>-service -n <NAMESPACE>`
4.  **Verify Agent Registry Discovery (for AI Agents / MCP Servers)**:

    ```bash
    # For AI Agents:
    gcloud agent-registry agents list --location="<LOCATION>" --project="<PROJECT_ID>"
    # For MCP Servers:
    gcloud agent-registry mcp-servers list --location="<LOCATION>" --project="<PROJECT_ID>"
    ```

--------------------------------------------------------------------------------

## Step 6: Troubleshooting GKE Authentication & Permission Errors

If cluster credential retrieval or manifest deployment fails, diagnose and
report the exact root cause without switching to another runtime or fabricating
cluster endpoints:

*   **`PERMISSION_DENIED` on `gcloud container clusters get-credentials`
    (`container.clusters.get` denied)**:

    *   The active identity lacks the `roles/container.clusterViewer` or
        `roles/container.developer` IAM role on `<PROJECT_ID>`.
    *   **Remediation**:

        ```bash
        gcloud projects add-iam-policy-binding <PROJECT_ID> \
          --member="user:<USER_OR_SA_EMAIL>" \
          --role="roles/container.developer"
        ```
*   **Kubernetes RBAC `Error from server (Forbidden): deployments.apps is
    forbidden: User "..." cannot create resource "deployments" in API group
    "apps" in the namespace "<NAMESPACE>"`**:

    *   The principal can authenticate to the cluster endpoint, but lacks
        Kubernetes RBAC or GKE IAM permissions to create workloads in
        `<NAMESPACE>`.
    *   **Remediation**: Grant `roles/container.developer` at the GCP project
        level or bind a Kubernetes `RoleBinding` / `ClusterRoleBinding` (`edit`
        or `admin`) in `<NAMESPACE>`:

        ```bash
        kubectl create rolebinding <APP_NAME>-deployer-binding \
          --clusterrole=edit \
          --user="<USER_OR_SA_EMAIL>" \
          --namespace="<NAMESPACE>"
        ```
*   **`executable gke-gcloud-auth-plugin not found`**:

    *   Install `google-cloud-cli-gke-gcloud-auth-plugin` (or
        `gcloud components install gke-gcloud-auth-plugin`) and ensure
        `USE_GKE_GCLOUD_AUTH_PLUGIN=True` is exported.
