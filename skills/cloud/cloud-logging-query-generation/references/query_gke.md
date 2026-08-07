# Kubernetes Engine (GKE) LQL queries

## Table of contents

- [Base schema and structural patterns](#base-schema-and-structural-patterns) (L72-L141)
- [Resource types](#resource-types) (L78-L91)
- [Application logs (stdout / stderr) pattern](#application-logs-stdout--stderr-pattern) (L93-L102)
- [Kubernetes events pattern](#kubernetes-events-pattern) (L104-L111)
- [System and control plane logs pattern](#system-and-control-plane-logs-pattern) (L113-L121)
- [Google Cloud vs Kubernetes Audit Logs](#google-cloud-vs-kubernetes-audit-logs) (L123-L132)
- [User-defined Kubernetes labels gotcha](#user-defined-kubernetes-labels-gotcha) (L134-L141)
- [Example queries](#example-queries) (L143-L771)
- [Cluster logs in a specific Google Cloud location](#cluster-logs-in-a-specific-google-cloud-location) (L145-L152)
- [Pod eviction events](#pod-eviction-events) (L154-L162)
- [Container errors from a specific pod](#container-errors-from-a-specific-pod) (L164-L172)
- [Google Kubernetes Engine cluster operations](#google-kubernetes-engine-cluster-operations) (L174-L181)
- [Google Kubernetes Engine cluster creation](#google-kubernetes-engine-cluster-creation) (L183-L191)
- [Kubernetes cluster deployment](#kubernetes-cluster-deployment) (L193-L201)
- [Kubernetes cluster authentication failure](#kubernetes-cluster-authentication-failure) (L203-L211)
- [Kubernetes cluster operations and events in us-central1-b](#kubernetes-cluster-operations-and-events-in-us-central1-b) (L213-L220)
- [Kubernetes pod requests from users](#kubernetes-pod-requests-from-users) (L222-L231)
- [Kubernetes events](#kubernetes-events) (L233-L240)
- [Kubernetes endpoints update](#kubernetes-endpoints-update) (L242-L250)
- [Kubernetes control plane logs](#kubernetes-control-plane-logs) (L252-L260)
- [Kubernetes Engine control plane logs](#kubernetes-engine-control-plane-logs) (L262-L270)
- [Pod deletion](#pod-deletion) (L272-L280)
- [Kubernetes pod audit logs from control plane](#kubernetes-pod-audit-logs-from-control-plane) (L282-L292)
- [Kubernetes pod evictions](#kubernetes-pod-evictions) (L294-L304)
- [Kubernetes node audit logs from the control plane](#kubernetes-node-audit-logs-from-the-control-plane) (L306-L316)
- [Kubernetes cluster control plane for Addon Manager Activity](#kubernetes-cluster-control-plane-for-addon-manager-activity) (L318-L328)
- [Kubernetes control plane errors (excluding Conflict , which is normal)](#kubernetes-control-plane-errors-excluding-conflict--which-is-normal) (L330-L341)
- [Ingress Controller events](#ingress-controller-events) (L343-L353)
- [Service Controller events (kube-controller-manager)](#service-controller-events-kube-controller-manager) (L355-L365)
- [Cluster Autoscaler events](#cluster-autoscaler-events) (L367-L377)
- [Cluster Autoscaler scale up failures (visibility logs)](#cluster-autoscaler-scale-up-failures-visibility-logs) (L379-L389)
- [Query pod during creation](#query-pod-during-creation) (L391-L399)
- [Scheduler events](#scheduler-events) (L401-L411)
- [Scheduler events (preemptions)](#scheduler-events-preemptions) (L413-L424)
- [Node events](#node-events) (L426-L433)
- [Out of memory (OOM) events](#out-of-memory-oom-events) (L435-L444)
- [Looking at Kube-proxy logs](#looking-at-kube-proxy-logs) (L446-L453)
- [Looking at dockerd logs](#looking-at-dockerd-logs) (L455-L462)
- [Looking at kubelet errors or failures](#looking-at-kubelet-errors-or-failures) (L464-L472)
- [Looking at node logs for GKE system logs](#looking-at-node-logs-for-gke-system-logs) (L474-L490)
- [Container and pod logs for GKE system logs](#container-and-pod-logs-for-gke-system-logs) (L492-L508)
- [Stdout container logs across all pods and containers in a cluster](#stdout-container-logs-across-all-pods-and-containers-in-a-cluster) (L510-L517)
- [Container error logs across all pods and containers in a cluster](#container-error-logs-across-all-pods-and-containers-in-a-cluster) (L519-L527)
- [Container error logs for a pod with a specific name](#container-error-logs-for-a-pod-with-a-specific-name) (L529-L537)
- [Container error logs for a specific container in a specific pod](#container-error-logs-for-a-specific-container-in-a-specific-pod) (L539-L548)
- [Container error logs for a specific namespace and container](#container-error-logs-for-a-specific-namespace-and-container) (L550-L559)
- [Container logs for a pod with a specific label](#container-logs-for-a-pod-with-a-specific-label) (L561-L569)
- [Container error logs for pods running on a specific node](#container-error-logs-for-pods-running-on-a-specific-node) (L571-L579)
- [Container logs for a pod with a label generated using skaffold](#container-logs-for-a-pod-with-a-label-generated-using-skaffold) (L581-L590)
- [Container error logs for a specific pod containing a POST in the textPayload](#container-error-logs-for-a-specific-pod-containing-a-post-in-the-textpayload) (L592-L601)
- [Container error logs for a specific pod containing a GET in the structured JSON](#container-error-logs-for-a-specific-pod-containing-a-get-in-the-structured-json) (L603-L612)
- [Container errors logs in the kube-system namespace](#container-errors-logs-in-the-kube-system-namespace) (L614-L622)
- [Container error in the container insights log](#container-error-in-the-container-insights-log) (L624-L631)
- [Kubernetes container logs](#kubernetes-container-logs) (L633-L640)
- [Kubernetes API server logs](#kubernetes-api-server-logs) (L642-L651)
- [Kubernetes Scheduler logs](#kubernetes-scheduler-logs) (L653-L662)
- [Kubernetes Controller Manager logs](#kubernetes-controller-manager-logs) (L664-L673)
- [Stdout container logs across all TPU nodes with the same prefix](#stdout-container-logs-across-all-tpu-nodes-with-the-same-prefix) (L675-L683)
- [Container error logs across all TPU nodes with the same prefix](#container-error-logs-across-all-tpu-nodes-with-the-same-prefix) (L685-L694)
- [Stdout container logs from the same GKE Job](#stdout-container-logs-from-the-same-gke-job) (L696-L704)
- [Container error logs from the same GKE Job](#container-error-logs-from-the-same-gke-job) (L706-L715)
- [Stdout container logs from the same GKE JobSet](#stdout-container-logs-from-the-same-gke-jobset) (L717-L725)
- [Container error logs from the same GKE JobSet](#container-error-logs-from-the-same-gke-jobset) (L727-L736)
- [Node auto-repair events](#node-auto-repair-events) (L738-L747)
- [Cluster deletion events](#cluster-deletion-events) (L749-L757)
- [Pod IP assignment and release](#pod-ip-assignment-and-release) (L759-L771)

## Base schema and structural patterns

GKE logs are split across multiple `resource.type` values depending on what
generated the log. Always constrain your query to the correct resource type
first before searching payloads.

### Resource types

*   **Containers (`k8s_container`)**: Use for application logs, standard out
    (`textPayload`), and structured JSON logs (`jsonPayload`) emitted by your
    workloads. This is the most common resource type for debugging applications.
*   **Pods (`k8s_pod`)**: Use for Kubernetes pod lifecycle events (for example,
    evictions, scheduling gaps, readiness probes).
*   **Nodes (`k8s_node`)**: Use for infrastructure-level node events (for
    example, kubelet errors, container runtime logs, node auto-repair).
*   **Cluster/Control Plane (`k8s_cluster` or `gke_cluster`)**: Use for control
    plane logs (API server, scheduler, controller-manager) and cluster-level
    operations. Kubernetes-native components log to `k8s_cluster`, while GCP
    infrastructure operations (like deleting the GKE cluster) log to
    `gke_cluster`.

### Application logs (stdout / stderr) pattern

When a user asks to search for "errors in my application", "logs from the
foo-pod", or "stdout from a container":

*   Target `resource.type="k8s_container"`.
*   Filter by `resource.labels.pod_name`, `resource.labels.container_name`, or
    `resource.labels.namespace_name`.
*   The raw log string is found in `textPayload` (unstructured) or `jsonPayload`
    (structured log records).

### Kubernetes events pattern

When a user asks about Kubernetes *events* like Pod evictions, Node scaling, or
BackOffs:

*   Filter by `log_id("events")`.
*   Search within `jsonPayload.reason` (for example, `"Evicted"`,
    `"FailedScheduling"`, `"BackOff"`) and `jsonPayload.message`.

### System and control plane logs pattern

When debugging GKE internal infrastructure (for example, ingress controllers,
kube-dns):

*   Target the `kube-system` namespace
    (`resource.labels.namespace_name="kube-system"`).
*   Control plane components generally log under the `k8s_cluster` resource
    type.

### Google Cloud vs Kubernetes Audit Logs

When auditing *infrastructure* (for example, who created the GKE cluster
itself), this falls under general Google Cloud API audit logs. However, when
auditing *inside* the cluster (for example, who deleted a Namespace or Pod):

*   Target `resource.type="k8s_cluster"`.
*   Filter by `log_id("cloudaudit.googleapis.com/activity")` (or `data_access`).
*   Search within `protoPayload.methodName` using native Kubernetes API strings
    (for example, `"io.k8s.core.v1.namespaces.create"`).

### User-defined Kubernetes labels gotcha

When filtering by custom Kubernetes pod labels (like `app: my-app` or `tier:
backend`), do NOT look in `resource.labels` or `labels.app` (or similar
unwrapped keys). Cloud Logging stores custom Kubernetes metadata in the global
`labels` object, automatically prefixed with `"k8s-pod/"`.

*   **Example:** `labels."k8s-pod/app"="my-app"`

## Example queries

### Cluster logs in a specific Google Cloud location

**Variables to replace:** `<LOCATION>`

```lql
resource.type="k8s_cluster" AND
resource.labels.location="<LOCATION>"
```

### Pod eviction events

**Variables to replace:** None

```lql
resource.type="k8s_pod" AND
log_id("events") AND
jsonPayload.reason="Evicted"
```

### Container errors from a specific pod

**Variables to replace:** `<POD_NAME>`

```lql
resource.type="k8s_container" AND
resource.labels.pod_name="<POD_NAME>" AND
severity=ERROR
```

### Google Kubernetes Engine cluster operations

**Variables to replace:** None

```lql
resource.type="gke_cluster" AND
log_id("cloudaudit.googleapis.com/activity")
```

### Google Kubernetes Engine cluster creation

**Variables to replace:** None

```lql
resource.type="gke_cluster" AND
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.methodName="google.container.v1.ClusterManager.CreateCluster"
```

### Kubernetes cluster deployment

**Variables to replace:** None

```lql
resource.type="k8s_cluster" AND
log_id("cloudaudit.googleapis.com/activity") AND
SEARCH(protoPayload.methodName, "deployments")
```

### Kubernetes cluster authentication failure

**Variables to replace:** None

```lql
resource.type="k8s_cluster" AND
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.authenticationInfo.principalEmail="system:anonymous"
```

### Kubernetes cluster operations and events in us-central1-b

**Variables to replace:** None

```lql
resource.type="k8s_cluster" AND
resource.labels.location="us-central1-b"
```

### Kubernetes pod requests from users

**Variables to replace:** `<USER_EMAIL>`

```lql
resource.type="k8s_cluster" AND
log_id("cloudaudit.googleapis.com/activity") AND
SEARCH(protoPayload.methodName, "io.k8s.core.v1.pods") AND
protoPayload.authenticationInfo.principalEmail="<USER_EMAIL>"
```

### Kubernetes events

**Variables to replace:** None

```lql
resource.type="k8s_cluster" AND
log_id("events")
```

### Kubernetes endpoints update

**Variables to replace:** None

```lql
resource.type="k8s_cluster" AND
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.request.kind="Endpoints"
```

### Kubernetes control plane logs

**Variables to replace:** None

```lql
resource.type="k8s_cluster" AND
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.serviceName="k8s.io"
```

### Kubernetes Engine control plane logs

**Variables to replace:** None

```lql
resource.type="k8s_cluster" AND
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.serviceName="container.googleapis.com"
```

### Pod deletion

**Variables to replace:** None

```lql
resource.type="k8s_cluster" AND
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.methodName=~"io\.k8s\.core\.v1\.pods\.(create|delete)"
```

### Kubernetes pod audit logs from control plane

**Variables to replace:** `<CLUSTER_LOCATION>`, `<CLUSTER_NAME>`, `<POD_NAME>`, `<POD_NAMESPACE>`

```lql
resource.type="k8s_cluster" AND
resource.labels.location="<CLUSTER_LOCATION>" AND
resource.labels.cluster_name="<CLUSTER_NAME>" AND
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.resourceName="core/v1/namespaces/<POD_NAMESPACE>/pods/<POD_NAME>"
```

### Kubernetes pod evictions

**Variables to replace:** `<CLUSTER_LOCATION>`, `<CLUSTER_NAME>`

```lql
resource.type="k8s_cluster" AND
resource.labels.location="<CLUSTER_LOCATION>" AND
resource.labels.cluster_name="<CLUSTER_NAME>" AND
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.methodName="io.k8s.core.v1.pods.eviction.create"
```

### Kubernetes node audit logs from the control plane

**Variables to replace:** `<CLUSTER_LOCATION>`, `<CLUSTER_NAME>`

```lql
resource.type="k8s_cluster" AND
resource.labels.location="<CLUSTER_LOCATION>" AND
resource.labels.cluster_name="<CLUSTER_NAME>" AND
log_id("cloudaudit.googleapis.com/activity") AND
SEARCH(protoPayload.methodName, "io.k8s.core.v1.nodes")
```

### Kubernetes cluster control plane for Addon Manager Activity

**Variables to replace:** `<CLUSTER_LOCATION>`, `<CLUSTER_NAME>`

```lql
resource.type="k8s_cluster" AND
resource.labels.location="<CLUSTER_LOCATION>" AND
resource.labels.cluster_name="<CLUSTER_NAME>" AND
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.authenticationInfo.principalEmail="system:addon-manager"
```

### Kubernetes control plane errors (excluding Conflict , which is normal)

**Variables to replace:** `<CLUSTER_LOCATION>`, `<CLUSTER_NAME>`

```lql
resource.type="k8s_cluster" AND
resource.labels.location="<CLUSTER_LOCATION>" AND
resource.labels.cluster_name="<CLUSTER_NAME>" AND
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.status.message!="Conflict" AND
protoPayload.status.code!=0
```

### Ingress Controller events

**Variables to replace:** `<CLUSTER_LOCATION>`, `<CLUSTER_NAME>`

```lql
resource.type="k8s_cluster" AND
resource.labels.location="<CLUSTER_LOCATION>" AND
resource.labels.cluster_name="<CLUSTER_NAME>" AND
log_id("events") AND
jsonPayload.source.component="loadbalancer-controller"
```

### Service Controller events (kube-controller-manager)

**Variables to replace:** `<CLUSTER_LOCATION>`, `<CLUSTER_NAME>`

```lql
resource.type="k8s_cluster" AND
resource.labels.location="<CLUSTER_LOCATION>" AND
resource.labels.cluster_name="<CLUSTER_NAME>" AND
log_id("events") AND
jsonPayload.source.component="service-controller"
```

### Cluster Autoscaler events

**Variables to replace:** `<CLUSTER_LOCATION>`, `<CLUSTER_NAME>`

```lql
resource.type="k8s_cluster" AND
resource.labels.location="<CLUSTER_LOCATION>" AND
resource.labels.cluster_name="<CLUSTER_NAME>" AND
log_id("events") AND
jsonPayload.source.component="cluster-autoscaler"
```

### Cluster Autoscaler scale up failures (visibility logs)

**Variables to replace:** `<CLUSTER_LOCATION>`, `<CLUSTER_NAME>`

```lql
resource.type="k8s_cluster" AND
resource.labels.location="<CLUSTER_LOCATION>" AND
resource.labels.cluster_name="<CLUSTER_NAME>" AND
log_id("container.googleapis.com/cluster-autoscaler-visibility") AND
jsonPayload.resultInfo.results.errorMsg.messageId:"scale.up"
```

### Query pod during creation

**Variables to replace:** `<POD_NAME>`

```lql
resource.type="k8s_pod" AND
resource.labels.pod_name="<POD_NAME>" AND
log_id("events")
```

### Scheduler events

**Variables to replace:** `<CLUSTER_LOCATION>`, `<CLUSTER_NAME>`

```lql
resource.type="k8s_pod" AND
resource.labels.location="<CLUSTER_LOCATION>" AND
resource.labels.cluster_name="<CLUSTER_NAME>" AND
log_id("events") AND
jsonPayload.source.component="default-scheduler"
```

### Scheduler events (preemptions)

**Variables to replace:** `<CLUSTER_LOCATION>`, `<CLUSTER_NAME>`

```lql
resource.type="k8s_pod" AND
resource.labels.location="<CLUSTER_LOCATION>" AND
resource.labels.cluster_name="<CLUSTER_NAME>" AND
log_id("events") AND
jsonPayload.source.component="default-scheduler" AND
jsonPayload.reason="Preempted"
```

### Node events

**Variables to replace:** None

```lql
resource.type="k8s_node" AND
log_id("events")
```

### Out of memory (OOM) events

**Variables to replace:** None

```lql
resource.type="k8s_node"
log_id("events")
(jsonPayload.reason:("OOMKilling" OR "SystemOOM")
  OR jsonPayload.message:("OOM encountered" OR "out of memory"))
```

### Looking at Kube-proxy logs

**Variables to replace:** None

```lql
resource.type="k8s_node" AND
log_id("kube-proxy")
```

### Looking at dockerd logs

**Variables to replace:** None

```lql
resource.type="k8s_node" AND
log_id("container-runtime")
```

### Looking at kubelet errors or failures

**Variables to replace:** None

```lql
resource.type="k8s_node" AND
log_id("kubelet") AND
jsonPayload.MESSAGE:("error" OR "fail")
```

### Looking at node logs for GKE system logs

**Variables to replace:** None

```lql
resource.type = "k8s_node" AND
logName:( "logs/container-runtime" OR
"logs/docker" OR
"logs/kube-container-runtime-monitor" OR
"logs/kube-logrotate" OR
"logs/kube-node-configuration" OR
"logs/kube-node-installation" OR
"logs/kubelet" OR
"logs/kubelet-monitor" OR
"logs/node-journal" OR
"logs/node-problem-detector")
```

### Container and pod logs for GKE system logs

**Variables to replace:** None

```lql
resource.type = ("k8s_container" OR "k8s_pod") AND
resource.labels.namespace_name = (
"cnrm-system" OR
"config-management-system" OR
"gatekeeper-system" OR
"gke-connect" OR
"gke-system" OR
"istio-system" OR
"knative-serving" OR
"monitoring-system" OR
"kube-system")
```

### Stdout container logs across all pods and containers in a cluster

**Variables to replace:** None

```lql
resource.type="k8s_container" AND
log_id("stdout")
```

### Container error logs across all pods and containers in a cluster

**Variables to replace:** None

```lql
resource.type="k8s_container" AND
log_id("stderr") AND
severity=ERROR
```

### Container error logs for a pod with a specific name

**Variables to replace:** `<POD_NAME>`

```lql
resource.type="k8s_container" AND
resource.labels.pod_name="<POD_NAME>" AND
severity=ERROR
```

### Container error logs for a specific container in a specific pod

**Variables to replace:** `<POD_NAME>`

```lql
resource.type="k8s_container" AND
resource.labels.pod_name="<POD_NAME>" AND
resource.labels.container_name="server" AND
severity=ERROR
```

### Container error logs for a specific namespace and container

**Variables to replace:** None

```lql
resource.type="k8s_container" AND
resource.labels.namespace_name="istio-system" AND
resource.labels.container_name="egressgateway" AND
severity=ERROR
```

### Container logs for a pod with a specific label

**Variables to replace:** None

```lql
resource.type="k8s_container" AND
labels."k8s-pod/app"="loadgenerator" AND
severity=ERROR
```

### Container error logs for pods running on a specific node

**Variables to replace:** `<NODE_NAME>`

```lql
resource.type="k8s_container" AND
labels."compute.googleapis.com/resource_name"="<NODE_NAME>" AND
severity=ERROR
```

### Container logs for a pod with a label generated using skaffold

**Variables to replace:** `<SKAFFOLD_RUN_ID>`

```lql
resource.type="k8s_container" AND
labels."k8s-pod/app"="loadgenerator" AND
labels."k8s-pod/skaffold_dev/run-id"="<SKAFFOLD_RUN_ID>" AND
severity=ERROR
```

### Container error logs for a specific pod containing a POST in the textPayload

**Variables to replace:** `<POD_NAME>`

```lql
resource.type="k8s_container" AND
resource.labels.pod_name="<POD_NAME>" AND
textPayload:"POST" AND
severity=ERROR
```

### Container error logs for a specific pod containing a GET in the structured JSON

**Variables to replace:** `<POD_NAME>`

```lql
resource.type="k8s_container" AND
resource.labels.pod_name="<POD_NAME>" AND
jsonPayload."http.req.method"="GET" AND
severity=ERROR
```

### Container errors logs in the kube-system namespace

**Variables to replace:** None

```lql
resource.type="k8s_container" AND
resource.labels.namespace_name="kube-system" AND
severity=ERROR
```

### Container error in the container insights log

**Variables to replace:** None

```lql
resource.type="k8s_container" AND
log_id("clouderrorreporting.googleapis.com/insights")
```

### Kubernetes container logs

**Variables to replace:** `<CONTAINER_NAME>`

```lql
resource.type="k8s_container" AND
resource.labels.container_name="<CONTAINER_NAME>"
```

### Kubernetes API server logs

**Variables to replace:** `<CLUSTER_LOCATION>`, `<CLUSTER_NAME>`

```lql
resource.type="k8s_control_plane_component" AND
resource.labels.component_name="apiserver" AND
resource.labels.location="<CLUSTER_LOCATION>" AND
resource.labels.cluster_name="<CLUSTER_NAME>"
```

### Kubernetes Scheduler logs

**Variables to replace:** `<CLUSTER_LOCATION>`, `<CLUSTER_NAME>`

```lql
resource.type="k8s_control_plane_component" AND
resource.labels.component_name="scheduler" AND
resource.labels.location="<CLUSTER_LOCATION>" AND
resource.labels.cluster_name="<CLUSTER_NAME>"
```

### Kubernetes Controller Manager logs

**Variables to replace:** `<CLUSTER_LOCATION>`, `<CLUSTER_NAME>`

```lql
resource.type="k8s_control_plane_component" AND
resource.labels.component_name="controller-manager" AND
resource.labels.location="<CLUSTER_LOCATION>" AND
resource.labels.cluster_name="<CLUSTER_NAME>"
```

### Stdout container logs across all TPU nodes with the same prefix

**Variables to replace:** `<TPU_NODE_PREFIX>`

```lql
resource.type="k8s_container" AND
labels."compute.googleapis.com/resource_name"=~"<TPU_NODE_PREFIX>.*" AND
log_id("stdout")
```

### Container error logs across all TPU nodes with the same prefix

**Variables to replace:** `<TPU_NODE_PREFIX>`

```lql
resource.type="k8s_container" AND
labels."compute.googleapis.com/resource_name"=~"<TPU_NODE_PREFIX>.*" AND
log_id("stderr") AND
severity=ERROR
```

### Stdout container logs from the same GKE Job

**Variables to replace:** `<JOB_NAME>`

```lql
resource.type="k8s_container" AND
labels."k8s-pod/batch.kubernetes.io/job-name" = "<JOB_NAME>" AND
log_id("stdout")
```

### Container error logs from the same GKE Job

**Variables to replace:** `<JOB_NAME>`

```lql
resource.type="k8s_container" AND
labels."k8s-pod/batch.kubernetes.io/job-name"="<JOB_NAME>" AND
log_id("stderr") AND
severity=ERROR
```

### Stdout container logs from the same GKE JobSet

**Variables to replace:** `<JOBSET_NAME>`

```lql
resource.type="k8s_container" AND
labels."k8s-pod/jobset_sigs_k8s_io/jobset-name"="<JOBSET_NAME>" AND
log_id("stdout")
```

### Container error logs from the same GKE JobSet

**Variables to replace:** `<JOBSET_NAME>`

```lql
resource.type="k8s_container" AND
labels."k8s-pod/jobset_sigs_k8s_io/jobset-name"="<JOBSET_NAME>" AND
log_id("stderr") AND
severity=ERROR
```

### Node auto-repair events

**Variables to replace:** `<CLUSTER_NAME>`

```lql
resource.type="gke_nodepool" AND
resource.labels.cluster_name="<CLUSTER_NAME>" AND
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.methodName="google.container.v1.ClusterManager.RepairNodePool"
```

### Cluster deletion events

**Variables to replace:** `<CLUSTER_NAME>`

```lql
resource.type="gke_cluster" AND
resource.labels.cluster_name="<CLUSTER_NAME>" AND
SEARCH(protoPayload.methodName, "DeleteCluster")
```

### Pod IP assignment and release

**Variables to replace:** `<CLUSTER_NAME>`, `<POD_NAME>`

```lql
resource.type="k8s_cluster" AND
resource.labels.cluster_name="<CLUSTER_NAME>" AND
protoPayload.resourceName:"<POD_NAME>" AND
((protoPayload.methodName="io.k8s.core.v1.pods.status.patch" AND
  protoPayload.request.status.podIP:*) OR
 (protoPayload.methodName="io.k8s.core.v1.pods.delete" AND
  protoPayload.response.status.podIP:*))
```
