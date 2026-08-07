---
name: gke-cluster-creation
description: >-
  Plans and executes GKE cluster creation, provisioning, and production
  readiness audits using pre-defined templates (Autopilot, Standard Regional,
  GPU/AI Inference, AI Hypercompute). Use when creating GKE clusters,
  provisioning GKE environments, selecting cluster modes, or auditing GKE
  clusters. Don't use for application onboarding or deployment configuration
  (use gke-app-onboarding instead).
metadata:
  category: Containers
---

# GKE Cluster Creation

This reference guides creating Google Kubernetes Engine (GKE) clusters by
providing a set of best-practice templates and guiding through mode selection
and customization. The **golden path Autopilot** configuration is the default
for all new clusters.

> **MCP Tools:** `list_clusters`, `create_cluster`, `get_cluster`,
> `list_operations`, `get_operation`

## Workflow

1.  **Discover context**: Use `list_clusters` to see existing clusters. Use
    `gcloud config get-value project` if project unknown.
2.  **Gather inputs**: `project_id`, `location` (region or zone),
    `cluster_name`, environment type. If missing essential details, ask the user
    before taking action.
3.  **Select mode & explain trade-offs**: If the user hasn't specified a
    template or mode, present the available templates (e.g., Autopilot, Standard
    Regional, GPU Inference, AI Hypercompute) and explain key trade-offs (Cost
    vs. Availability, Autopilot vs. Standard node management).
4.  **Configure networking**: auto-create subnet (default) or bring-your-own.
5.  **Review golden path settings**: present the default configuration block
    (`gcloud` command or `create_cluster` JSON payload) and confirm with the
    user before creation.
6.  **Create**: Use MCP `create_cluster` tool or `gcloud` CLI.
7.  **Track**: Use `get_operation` to monitor creation progress.
8.  **Verify**: Use `get_cluster` with `readMask="*"` to confirm golden path
    settings applied.

## Mode Selection

| Criteria           | Autopilot (Golden Path)   | Standard                  |
| ------------------ | ------------------------- | ------------------------- |
| Node management    | Google-managed            | Self-managed              |
| Pricing            | Pay per pod resource      | Pay per node (VM)         |
:                    : request                   :                           :
| Node customization | Via ComputeClasses        | Full control              |
| DaemonSets         | Allowed (with             | Full control              |
:                    : restrictions)             :                           :
| GPU/TPU            | Supported via             | Supported via node pools  |
:                    : ComputeClasses            :                           :
| Best for           | Most production workloads | Kernel tuning, custom OS, |
:                    :                           : privileged workloads      :

> **Rule**: Default to Autopilot unless the customer has a specific requirement
> that Autopilot cannot satisfy.

## Best Practices

When guiding the user or generating configurations, adhere to these GKE best
practices:

### Security & Networking

1.  **Private Clusters**: Default to private clusters (`enablePrivateNodes:
    true`) with a private control plane and restricted public endpoints
    (`enable-master-authorized-networks`) to minimize attack surface.
2.  **VPC-Native Networking**: Use VPC-native clusters (`useIpAliases: true` /
    `--enable-ip-alias`) to enable alias IP ranges and pod-level firewall rules.
3.  **Workload Identity**: Prefer Workload Identity (`workloadPool:
    <PROJECT_ID>.svc.id.goog`) for securely granting GKE workloads access to
    Google Cloud services instead of static service account keys.
4.  **Shielded GKE Nodes**: Enable Shielded GKE Nodes
    (`--enable-shielded-nodes`, `--enable-secure-boot`) against rootkits and
    bootkits.
5.  **Least Privilege (RBAC)**: Institute strict Role-Based Access Control
    limits (`scoped-rbs-bindings`).

### Cost Optimization

1.  **Autoscaling**: Enable Cluster Autoscaler and Horizontal/Vertical Pod
    Autoscaler (`--enable-autoscaling`, `--enable-vertical-pod-autoscaling`) to
    adjust resources based on demand.
2.  **Right-Sizing & Spot VMs**: Choose appropriate machine types and node
    counts. Consider Spot VMs (`--spot`) for fault-tolerant, non-critical batch
    or inference workloads.

### High Availability & Reliability

1.  **Regional Clusters**: Use Regional Clusters for production environments to
    ensure control plane replication across multiple zones (`--region` instead
    of `--zone`). *Note: Standard regional creates nodes across 3 zones by
    default.*
2.  **Pod Disruption Budgets**: Recommend setting Pod Disruption Budgets for
    application stability during node maintenance.
3.  **Release Channels**: Subscribe to a release channel (`REGULAR` or `STABLE`)
    for automated, safer cluster upgrades.

## Templates

### 1. Golden Path Autopilot (Production)

This is the default. All settings match
`../gke-golden-path/assets/golden-path-autopilot.yaml`.

**Via gcloud:**

```bash
gcloud container clusters create-auto <CLUSTER_NAME> \
  --region <REGION> \
  --project <PROJECT_ID> \
  --release-channel regular \
  --enable-private-nodes \
  --enable-master-authorized-networks \
  --enable-dns-access \
  --enable-secret-manager \
  --secret-manager-rotation-interval=120s \
  --scoped-rbs-bindings \
  --monitoring=SYSTEM,API_SERVER,SCHEDULER,CONTROLLER_MANAGER,STORAGE,POD,DEPLOYMENT,STATEFULSET,DAEMONSET,HPA,CADVISOR,KUBELET,DCGM \
  --quiet
```

**Via MCP (`create_cluster`):**

```json
{
  "parent": "projects/<PROJECT_ID>/locations/<REGION>",
  "cluster": {
    "name": "<CLUSTER_NAME>",
    "autopilot": { "enabled": true },
    "privateClusterConfig": { "enablePrivateNodes": true },
    "masterAuthorizedNetworksConfig": {
      "privateEndpointEnforcementEnabled": true
    },
    "releaseChannel": { "channel": "REGULAR" },
    "secretManagerConfig": {
      "enabled": true,
      "rotationConfig": { "enabled": true, "rotationInterval": "120s" }
    },
    "rbacBindingConfig": {
      "enableInsecureBindingSystemAuthenticated": false,
      "enableInsecureBindingSystemUnauthenticated": false
    }
  }
}
```

### 2. Autopilot Dev/Test

Relaxes some golden path defaults for cost savings and easier access in
non-production.

**Via gcloud:**

```bash
gcloud container clusters create-auto <CLUSTER_NAME> \
  --region <REGION> \
  --project <PROJECT_ID> \
  --release-channel rapid \
  --quiet
```

**Via MCP (`create_cluster`):**

```json
{
  "parent": "projects/<PROJECT_ID>/locations/<REGION>",
  "cluster": {
    "name": "<CLUSTER_NAME>",
    "autopilot": { "enabled": true },
    "releaseChannel": { "channel": "RAPID" }
  }
}
```

> **Warning**: This does not apply golden path security hardening. Suitable for
> dev/test only.

### 3. Standard Regional (High Availability / Custom Requirements)

Best when Autopilot cannot be used (e.g., custom kernel tuning, specific node OS
requirements). Creates 3 nodes across zones by default.

**Via gcloud:**

```bash
gcloud container clusters create <CLUSTER_NAME> \
  --region <REGION> \
  --project <PROJECT_ID> \
  --num-nodes 3 \
  --machine-type e2-standard-4 \
  --disk-type pd-balanced \
  --enable-autoscaling --min-nodes 1 --max-nodes 10 \
  --enable-shielded-nodes --enable-secure-boot \
  --workload-pool=<PROJECT_ID>.svc.id.goog \
  --enable-private-nodes \
  --enable-master-authorized-networks \
  --enable-vertical-pod-autoscaling \
  --enable-dataplane-v2 \
  --release-channel regular \
  --quiet
```

**Via MCP (`create_cluster`):**

```json
{
  "parent": "projects/<PROJECT_ID>/locations/<REGION>",
  "cluster": {
    "name": "<CLUSTER_NAME>",
    "initialNodeCount": 3,
    "nodeConfig": {
      "machineType": "e2-standard-4",
      "diskType": "pd-balanced",
      "diskSizeGb": 100,
      "oauthScopes": ["https://www.googleapis.com/auth/cloud-platform"],
      "shieldedInstanceConfig": {
        "enableSecureBoot": true,
        "enableIntegrityMonitoring": true
      },
      "workloadMetadataConfig": {
        "mode": "GKE_METADATA"
      }
    },
    "privateClusterConfig": { "enablePrivateNodes": true },
    "releaseChannel": { "channel": "REGULAR" },
    "workloadIdentityConfig": {
      "workloadPool": "<PROJECT_ID>.svc.id.goog"
    }
  }
}
```

### 4. GPU Inference & AI Workloads (L4 / ComputeClass)

Best for: AI/ML Inference, small model serving. Can be provisioned via
Autopilot + ComputeClass or via Standard node pool with `g2-standard-4`
(`nvidia-l4`). *Note: Requires `g2-standard-4` quota.*

**Autopilot ComputeClass / GIQ approach:**

```bash
# 1. Create golden path cluster (same as template 1)
gcloud container clusters create-auto <CLUSTER_NAME> \
  --region <REGION> --project <PROJECT_ID> \
  --enable-private-nodes --enable-master-authorized-networks \
  --enable-dns-access --enable-secret-manager --scoped-rbs-bindings \
  --quiet

# 2. Apply GPU ComputeClass (see gke-compute-classes.md)
kubectl apply -f gpu-compute-class.yaml

# 3. Or use GIQ for inference (see gke-inference.md)
gcloud container ai profiles manifests create \
  --model=gemma-2-9b-it --model-server=vllm --accelerator-type=nvidia-l4 --quiet > inference.yaml
kubectl apply -f inference.yaml
```

**Standard Node Pool approach via MCP (`create_cluster`):**

```json
{
  "parent": "projects/<PROJECT_ID>/locations/<REGION>",
  "cluster": {
    "name": "<CLUSTER_NAME>",
    "initialNodeCount": 1,
    "nodeConfig": {
      "machineType": "g2-standard-4",
      "accelerators": [
        {
          "acceleratorCount": "1",
          "acceleratorType": "nvidia-l4"
        }
      ],
      "diskSizeGb": 100,
      "oauthScopes": ["https://www.googleapis.com/auth/cloud-platform"]
    }
  }
}
```

### 5. AI Hypercompute (A3 HighGPU / Large Model Serving)

Best for: Large-scale LLM / AI model training and hypercompute inference. *Note:
High hourly cost and strict quota requirements (`a3-highgpu-8g` /
`nvidia-h100-80gb-hbm3`).*

**Via gcloud:**

```bash
gcloud container clusters create <CLUSTER_NAME> \
  --region <REGION> \
  --project <PROJECT_ID> \
  --num-nodes 1 \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb-hbm3,count=8 \
  --disk-size 200 \
  --scopes https://www.googleapis.com/auth/cloud-platform \
  --workload-pool=<PROJECT_ID>.svc.id.goog \
  --release-channel regular \
  --quiet
```

**Via MCP (`create_cluster`):**

```json
{
  "parent": "projects/<PROJECT_ID>/locations/<REGION>",
  "cluster": {
    "name": "<CLUSTER_NAME>",
    "initialNodeCount": 1,
    "nodeConfig": {
      "machineType": "a3-highgpu-8g",
      "accelerators": [
        {
          "acceleratorCount": "8",
          "acceleratorType": "nvidia-h100-80gb-hbm3"
        }
      ],
      "diskSizeGb": 200,
      "oauthScopes": ["https://www.googleapis.com/auth/cloud-platform"]
    }
  }
}
```

## Instructions

-   **ALWAYS** ask for `project_id` if not in context.
-   **ALWAYS** ask for `region` (or location).
-   **ALWAYS** ask for a unique `cluster_name`.
-   **DEFAULT** to golden path Autopilot unless customer specifies otherwise or
    has custom node/kernel/hypercompute requirements.
-   **ALWAYS WARN** when deviating to GKE Standard, highlighting that it
    deviates from the golden path and explaining the added
    operational/management overhead (manually managing node pools, upgrades, and
    autoscaling).
-   **EXPLAIN TRADE-OFFS** when presenting templates or mode choices to the user
    if they haven't specified one (e.g., Autopilot vs Standard, Cost vs
    Availability).
-   **PRESENT THE CONFIGURATION** block (`gcloud` command or JSON payload) and
    ask for confirmation before calling any creation tool.
-   **WARN** about Day-0 decisions (networking, private nodes) that are hard to
    change later.
-   **WARN** explicitly about cost and quota requirements when the user selects
    GPU (`g2-standard-4`, `a3-highgpu-8g`), TPU, or multi-region/regional
    clusters (`--region` defaults to 3 zones).
-   When using MCP `create_cluster`, the `cluster.name` parameter should be the
    **short name** (e.g., `my-cluster`), not the full resource path
    (`projects/<PROJECT_ID>/locations/<REGION>/clusters/<CLUSTER_NAME>`). The
    `parent` parameter defines the scope
    (`projects/<PROJECT_ID>/locations/<REGION>`).
