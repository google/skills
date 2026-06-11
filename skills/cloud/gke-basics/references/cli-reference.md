# CLI & Tool Reference for GKE

## Tool Preference

Default preference order:

```
1. GKE MCP Tools  (preferred — structured, auditable, no shell required)
2. gcloud CLI     (fallback — when MCP doesn't expose the operation)
3. kubectl        (fallback — purely in-cluster ops not covered by MCP)
```

### When to use each

| Interface         | When to Use                | Examples                    |
| ----------------- | -------------------------- | --------------------------- |
| **GKE MCP Tools** | Default for all cluster    | `create_cluster`,           |
:                   : and K8s operations when    : `get_cluster`,              :
:                   : MCP server is available.   : `get_k8s_resource`,         :
:                   : Structured I/O, supports   : `apply_k8s_manifest`,       :
:                   : dry-run, no                : `get_k8s_logs`              :
:                   : shell/kubeconfig needed.   :                             :
| **`gcloud` CLI**  | No MCP equivalent, or user | `gcloud container ai        |
:                   : explicitly requested CLI.  : profiles`, `gcloud          :
:                   : Required for\: GIQ model   : container                   :
:                   : discovery, available K8s   : get-server-config`, `gcloud :
:                   : versions, maintenance      : iam service-accounts`       :
:                   : windows, monitoring        :                             :
:                   : components, IAM/SA setup,  :                             :
:                   : Cloud Logging queries.     :                             :
| **`kubectl`**     | Neither MCP nor `gcloud`   | `kubectl top pods`,         |
:                   : covers the operation, or   : `kubectl scale deployment`, :
:                   : user explicitly prefers    : `helm install`              :
:                   : kubectl. Required for\:    :                             :
:                   : `kubectl top`, `kubectl    :                             :
:                   : scale`, `kubectl exec`,    :                             :
:                   : `kubectl port-forward`,    :                             :
:                   : Helm, custom CRDs not in   :                             :
:                   : MCP.                       :                             :

### User preference override

If the user states a preference, respect it for the session:

-   **"Use gcloud" / "Use CLI"** → `gcloud` for cluster ops, `kubectl` for K8s
    resource ops. Skip MCP.
-   **"Use kubectl"** → `kubectl` for all K8s resource ops, `gcloud` for
    cluster-level ops. Skip MCP.
-   **"Use MCP"** / no preference → Default. Use MCP for everything it supports.

Even with an override, fall back through the chain for unsupported operations
(e.g., cluster creation always requires `gcloud` or MCP).

--------------------------------------------------------------------------------

> All MCP tools use hierarchical resource paths — see
> [`parent` format](#parent--name-format-quick-reference) at the bottom.

## Cluster Operations

| Operation           | MCP Tool         | CLI Fallback       | Mode        |
| ------------------- | ---------------- | ------------------ | ----------- |
| List clusters       | `list_clusters`  | `gcloud container  | READ        |
:                     :                  : clusters list`     :             :
| Get cluster details | `get_cluster`    | `gcloud container  | READ        |
:                     :                  : clusters describe` :             :
| Create cluster      | `create_cluster` | `gcloud container  | MUTATE      |
:                     :                  : clusters           :             :
:                     :                  : create-auto`       :             :
| Update cluster      | `update_cluster` | `gcloud container  | DESTRUCTIVE |
:                     :                  : clusters update`   :             :
| Get K8s versions    | —                | `gcloud container  | READ        |
:                     :                  : get-server-config` :             :
| Get credentials     | —                | `gcloud container  | READ        |
:                     :                  : clusters           :             :
:                     :                  : get-credentials`   :             :
| Delete cluster      | —                | `gcloud container  | DESTRUCTIVE |
:                     :                  : clusters delete`   :             :

```
# List clusters in a project (all regions)
list_clusters(parent="projects/<PROJECT_ID>/locations/-")

# Get cluster details (all fields)
get_cluster(name="projects/<PROJECT_ID>/locations/<REGION>/clusters/<CLUSTER_NAME>", readMask="*")

# Create golden path Autopilot cluster
create_cluster(
  parent="projects/<PROJECT_ID>/locations/<REGION>",
  cluster='{"name":"<CLUSTER_NAME>","autopilot":{"enabled":true},"privateClusterConfig":{"enablePrivateNodes":true},...}'
)
```

```bash
# Get available Kubernetes versions (CLI-only)
gcloud container get-server-config --region <REGION> --format="yaml(channels)" --quiet

# Create golden path Autopilot cluster (see gke-cluster-creation.md for full templates)
gcloud container clusters create-auto <CLUSTER_NAME> \
  --region <REGION> --project <PROJECT_ID> \
  --enable-private-nodes --enable-master-authorized-networks \
  --enable-dns-access --release-channel regular \
  --enable-secret-manager --scoped-rbs-bindings \
  --quiet

# Get credentials (CLI-only)
gcloud container clusters get-credentials <CLUSTER_NAME> --region <REGION> --project <PROJECT_ID> --quiet
```

## Node Pool Operations

| Operation        | MCP Tool           | CLI Fallback         | Mode        |
| ---------------- | ------------------ | -------------------- | ----------- |
| List node pools  | `list_node_pools`  | `gcloud container    | READ        |
:                  :                    : node-pools list`     :             :
| Get node pool    | `get_node_pool`    | `gcloud container    | READ        |
:                  :                    : node-pools describe` :             :
| Create node pool | `create_node_pool` | `gcloud container    | MUTATE      |
:                  :                    : node-pools create`   :             :
| Update node pool | `update_node_pool` | `gcloud container    | DESTRUCTIVE |
:                  :                    : node-pools update`   :             :

```
list_node_pools(parent="projects/<PROJECT_ID>/locations/<REGION>/clusters/<CLUSTER_NAME>")

create_node_pool(
  parent="projects/<PROJECT_ID>/locations/<REGION>/clusters/<CLUSTER_NAME>",
  nodePool='{"name":"<POOL_NAME>","config":{"machineType":"e2-standard-4"},"initialNodeCount":3,...}'
)
```

## Cluster Updates

| Operation         | MCP Tool         | CLI Fallback            | Mode        |
| ----------------- | ---------------- | ----------------------- | ----------- |
| Update cluster    | `update_cluster` | `gcloud container       | DESTRUCTIVE |
: settings          :                  : clusters update`        :             :
| Update monitoring | —                | `gcloud container       | DESTRUCTIVE |
:                   :                  : clusters update         :             :
:                   :                  : --monitoring=...`       :             :
| Set maintenance   | —                | `gcloud container       | DESTRUCTIVE |
: window            :                  : clusters update         :             :
:                   :                  : --maintenance-window-*` :             :

```
# Enable VPA via MCP
update_cluster(
  name="projects/<PROJECT_ID>/locations/<REGION>/clusters/<CLUSTER_NAME>",
  update='{"desiredVerticalPodAutoscaling":{"enabled":true}}'
)
```

```bash
# Update monitoring components (CLI-only)
gcloud container clusters update <CLUSTER_NAME> --region <REGION> \
  --monitoring=SYSTEM,API_SERVER,SCHEDULER,CONTROLLER_MANAGER,STORAGE,POD,DEPLOYMENT,STATEFULSET,DAEMONSET,HPA \
  --quiet
```

## Kubernetes Resource Operations

| Operation       | MCP Tool                 | CLI Fallback     | Mode        |
| --------------- | ------------------------ | ---------------- | ----------- |
| Get/list        | `get_k8s_resource`       | `kubectl get`    | READ        |
: resources       :                          :                  :             :
| Describe        | `describe_k8s_resource`  | `kubectl         | READ        |
: resource        :                          : describe`        :             :
| Apply manifest  | `apply_k8s_manifest`     | `kubectl apply`  | DESTRUCTIVE |
| Patch resource  | `patch_k8s_resource`     | `kubectl patch`  | DESTRUCTIVE |
| Delete resource | `delete_k8s_resource`    | `kubectl delete` | DESTRUCTIVE |
| List API        | `list_k8s_api_resources` | `kubectl         | READ        |
: resources       :                          : api-resources`   :             :
| Check auth      | `check_k8s_auth`         | `kubectl auth    | READ        |
:                 :                          : can-i`           :             :

```
# List all deployments in a namespace
get_k8s_resource(
  parent="projects/<PROJECT_ID>/locations/<REGION>/clusters/<CLUSTER_NAME>",
  resourceType="deployment", namespace="<NAMESPACE>"
)

# Apply a manifest (with dry-run)
apply_k8s_manifest(parent="...", yamlManifest="...", dryRun=true)

# Patch deployment resources for rightsizing
patch_k8s_resource(
  parent="projects/<PROJECT_ID>/locations/<REGION>/clusters/<CLUSTER_NAME>",
  resourceType="deployment", name="<DEPLOYMENT>", namespace="<NAMESPACE>",
  patch='{"spec":{"template":{"spec":{"containers":[{"name":"app","resources":{"requests":{"cpu":"200m","memory":"256Mi"}}}]}}}}'
)

# Check RBAC permissions
check_k8s_auth(parent="...", verb="create", resourceType="deployments", namespace="<NAMESPACE>")
```

## Diagnostics & Observability

Operation           | MCP Tool                 | CLI Fallback             | Mode
------------------- | ------------------------ | ------------------------ | ----
List events         | `list_k8s_events`        | `kubectl events`         | READ
Get container logs  | `get_k8s_logs`           | `kubectl logs`           | READ
Cluster info        | `get_k8s_cluster_info`   | `kubectl cluster-info`   | READ
K8s version         | `get_k8s_version`        | `kubectl version`        | READ
Rollout status      | `get_k8s_rollout_status` | `kubectl rollout status` | READ
Query Cloud Logging | —                        | `gcloud logging read`    | READ

```
# Get recent events across all namespaces
list_k8s_events(parent="...", allNamespaces=true, limit="50")

# Get logs (last 100 lines, or previous crash)
get_k8s_logs(parent="...", name="<POD>", namespace="<NS>", tail="100")
get_k8s_logs(parent="...", name="<POD>", namespace="<NS>", previous=true)

# Check rollout status
get_k8s_rollout_status(parent="...", resourceType="deployment", name="<DEPLOY>", namespace="<NS>")
```

## Operations Tracking

| Operation        | MCP Tool           | CLI Fallback         | Mode        |
| ---------------- | ------------------ | -------------------- | ----------- |
| List operations  | `list_operations`  | `gcloud container    | READ        |
:                  :                    : operations list`     :             :
| Get operation    | `get_operation`    | `gcloud container    | READ        |
:                  :                    : operations describe` :             :
| Cancel operation | `cancel_operation` | `gcloud container    | DESTRUCTIVE |
:                  :                    : operations cancel`   :             :

```
list_operations(parent="projects/<PROJECT_ID>/locations/<REGION>")
get_operation(name="projects/<PROJECT_ID>/locations/<REGION>/operations/<OP_ID>")
```

## AI/ML Inference (GIQ) — CLI-Only

```bash
gcloud container ai profiles models list --quiet
gcloud container ai profiles list --model=<MODEL_NAME> --quiet
gcloud container ai profiles manifests create \
  --model=<MODEL_NAME> --model-server=<SERVER> \
  --accelerator-type=<ACCELERATOR> \
  --target-ntpot-milliseconds=<NTPOT> --quiet > inference.yaml

# Deploy generated manifest via MCP
apply_k8s_manifest(parent="...", yamlManifest="<contents of inference.yaml>")
```

## kubectl-Only Operations

No MCP or `gcloud` equivalent:

```bash
kubectl top pods --all-namespaces --sort-by=cpu
kubectl top nodes
kubectl scale deployment <DEPLOYMENT> --replicas=<N> -n <NAMESPACE>
kubectl exec -it <POD_NAME> -n <NAMESPACE> -- /bin/sh
kubectl port-forward svc/<SERVICE> <LOCAL_PORT>:<REMOTE_PORT> -n <NAMESPACE>
kubectl cp <NAMESPACE>/<POD>:<PATH> <LOCAL_PATH>
kubectl run debug --rm -it --image=busybox -- /bin/sh
kubectl drain <NODE_NAME> --ignore-daemonsets --delete-emptydir-data
helm install <RELEASE> <CHART> -n <NAMESPACE>
helm upgrade <RELEASE> <CHART> -n <NAMESPACE>
```

## `parent` / `name` Format Quick Reference

```
Project+Region:  projects/{PROJECT}/locations/{REGION}
Cluster:         projects/{PROJECT}/locations/{REGION}/clusters/{CLUSTER}
Node Pool:       projects/{PROJECT}/locations/{REGION}/clusters/{CLUSTER}/nodePools/{POOL}
Operation:       projects/{PROJECT}/locations/{REGION}/operations/{OP_ID}
```

Use `locations/-` to match all regions/zones when listing.

## Error Handling

Error / Symptom                       | Likely Cause                                 | Remediation
------------------------------------- | -------------------------------------------- | -----------
`PERMISSION_DENIED` on cluster create | Missing `container.clusters.create` IAM role | Grant `roles/container.admin` or `roles/container.clusterAdmin`
Quota exceeded                        | Regional vCPU, GPU, or IP address limits     | Request quota increase or select a different region
IP exhaustion / CIDR conflict         | Pod subnet too small or overlapping ranges   | Re-plan IP ranges; may require cluster recreation (Day-0)
Workload Identity not working         | Missing OIDC issuer or federated credential  | Verify `workloadIdentityConfig.workloadPool`; configure federated identity binding
Private cluster unreachable           | No authorized networks or DNS endpoint       | Enable `dnsEndpointConfig.allowExternalTraffic` or add authorized networks
Secret Manager rotation failing       | SA missing `secretmanager.versions.access`   | Grant Secret Manager accessor role to workload's GSA
Control-plane metrics missing         | Monitoring components not configured         | Enable APISERVER, SCHEDULER, CONTROLLER_MANAGER in `monitoringConfig`
