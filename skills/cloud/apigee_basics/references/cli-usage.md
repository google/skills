# Apigee CLI Usage

This document details command-line interfaces (CLIs) for managing Apigee X and
Apigee Hybrid.

--------------------------------------------------------------------------------

## 1. gcloud apigee CLI

The Google Cloud SDK (`gcloud`) provides commands to interact with the Apigee
control plane. Ensure the `gcloud` CLI is updated and the correct project is
targeted:

```bash
gcloud components update
gcloud config set project YOUR_GCP_PROJECT_ID
```

### Common Commands

**List Organizations**

Retrieve Apigee organization details linked to the current project.

```bash
gcloud apigee organizations list
```

**Describe Organization**

Inspect configuration parameters, environment groups, and billing details.

```bash
gcloud apigee organizations describe --format=json
```

**List Environments**

List environments associated with the organization.

```bash
gcloud apigee environments list
```

**List API Proxies**

List API proxies deployed or configured in the organization.

```bash
gcloud apigee apis list
```

**Check Long Running Operations**

Many Apigee operations (like creating an organization, instances, or environment
groups) are asynchronous and return an Operation ID. You can check their status
using:

```bash
gcloud apigee operations describe OPERATION_ID
```

**Describe Deployments**

List all active deployments of API proxies across environments:

```bash
gcloud apigee deployments list
```

--------------------------------------------------------------------------------

## 2. Helm (Apigee Hybrid only)

For **Apigee Hybrid**, Helm is the official tool for installing and managing the
runtime components (Synchronizer, Runtime, Cassandra database, Logger) in a
Kubernetes cluster.

> [!NOTE] The legacy command-line utility `apigeectl` is deprecated as of April
> 17, 2024. All deployments should use Helm.

### Setup and Context

Helm interacts with your Kubernetes cluster context (configured via `kubectl`).
Your configuration is defined in a local YAML file (e.g., `overrides.yaml`),
which represents your desired state for the cluster topology.

### Common Helm Commands

Apigee Hybrid is installed as a sequence of Helm charts. The general pattern to
install or upgrade a component is:

```bash
helm upgrade RELEASE_NAME CHART_DIRECTORY/ \
  --install \
  --namespace APIGEE_NAMESPACE \
  --atomic \
  -f overrides.yaml
```

*   `--install`: Installs the chart if it is not already installed.
*   `--atomic`: Rolls back the installation on failure.
*   `-f overrides.yaml`: Specifies your custom configuration overrides.

### Recommended Installation Sequence

Before installing, you must pull the charts from the Google Artifact Registry:

```bash
export CHART_REPO=oci://us-docker.pkg.dev/apigee-release/apigee-hybrid-helm-charts
export CHART_VERSION=1.16.0 # Use the latest supported version

helm pull $CHART_REPO/apigee-operator --version $CHART_VERSION --untar
helm pull $CHART_REPO/apigee-datastore --version $CHART_VERSION --untar
# Pull other charts (apigee-telemetry, apigee-redis, apigee-ingress-manager, apigee-org, apigee-env)
```

Install components in the following order:

1.  **Apigee Operator**: Manages Apigee custom resources.

    ```bash
    helm upgrade operator apigee-operator/ --install --namespace apigee --atomic -f overrides.yaml
    ```

2.  **Datastore**: Deploys the Cassandra database.

    ```bash
    helm upgrade datastore apigee-datastore/ --install --namespace apigee --atomic -f overrides.yaml
    ```

3.  **Telemetry**: Deploys logging and metrics collectors.

    ```bash
    helm upgrade telemetry apigee-telemetry/ --install --namespace apigee --atomic -f overrides.yaml
    ```

4.  **Redis**: Deploys data cache.

    ```bash
    helm upgrade redis apigee-redis/ --install --namespace apigee --atomic -f overrides.yaml
    ```

5.  **Ingress Manager**: Manages ingress controllers.

    ```bash
    helm upgrade ingress-manager apigee-ingress-manager/ --install --namespace apigee --atomic -f overrides.yaml
    ```

6.  **Organization**: Configures organization-level settings.

    ```bash
    helm upgrade organization apigee-organization/ --install --namespace apigee --atomic -f overrides.yaml
    ```

7.  **Environment**: Deploys the runtime services for a specific environment.

    ```bash
    helm upgrade env-prod apigee-env/ --install --namespace apigee --atomic --set env=prod -f overrides.yaml
    ```

### Managing overrides.yaml

The `overrides.yaml` file contains environment-specific settings. Example:

```yaml
gcpProjectID: my-hybrid-project
k8sCluster:
  name: hybrid-gke-cluster
  region: us-central1
org: my-apigee-org
envs:
  - name: prod
    serviceAccountPaths:
      synchronizer: ./keys/my-hybrid-project-apigee-synchronizer.json
      runtime: ./keys/my-hybrid-project-apigee-runtime.json
      udca: ./keys/my-hybrid-project-apigee-udca.json
cassandra:
  replicaCount: 3
```
