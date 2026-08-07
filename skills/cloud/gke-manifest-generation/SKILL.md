---
name: gke-manifest-generation
metadata:
  category: Containers
description: >-
  Generates and updates secure, production-ready Kubernetes YAML manifests optimized for GKE Autopilot and GKE Standard clusters. Use when creating or modifying GKE deployment manifests, configuring container security contexts, setting CPU/memory resource limits, defining readiness/liveness/startup probes, mounting secrets and volumes, configuring GKE Gateway API routes, targeting Spot VMs, or deploying AI model inference workloads (vLLM, TGI, Gemma). Don't use for live cluster operations, pod troubleshooting (use gke-workload-troubleshooting), or cluster infrastructure provisioning (use gke-cluster-creation).
---

# GKE Manifest Generation Skill

This skill provides guidelines, tooling integration, and templates to translate
natural language descriptions or application code changes into secure,
compliant, and cost-effective Kubernetes YAML manifests optimized for both GKE
Autopilot and GKE Standard clusters.

## Core Rules & Verification

When generating or updating YAML manifests, you **must** strictly adhere to the
following rules:

### 1. Namespace & Resource Isolation

-   **Explicit Namespace**: Always declare `namespace: {namespace}` explicitly
    in the metadata of every resource (Deployments, Services, ConfigMaps,
    Secrets, PVCs, Roles, bindings). Map it to the namespace configured in your
    active `SETTINGS.md`. Never omit the namespace.
-   **Dedicated ServiceAccount**: Avoid using the namespace's `default`
    ServiceAccount. Always create and reference a dedicated `ServiceAccount`
    (e.g., `devteam-agent-sa`) for each microservice.

### 2. GKE Resource Tuning (Autopilot & Standard)

-   **Resources Requests & Limits**: Always specify CPU and Memory requests and
    limits for all containers.
    -   *GKE Autopilot*: Requests determine pod billing directly; requests and
        limits must be equal. If they differ, Autopilot will automatically scale
        requests up to match limits, which can significantly increase costs.
    -   *GKE Standard*: Requests ensure stable scheduling and bin-packing;
        limits prevent resource starvation/noisy-neighbor issues.
-   **Density Defaults**: For stateless apps or sidecars on GKE Standard,
    default to conservative requests (e.g., `requests.cpu: "100m"` or `"200m"`,
    `requests.memory: "256Mi"` or `"512Mi"`) with burstable limits. Use a
    reasonable overcommit ratio for limits (e.g., 2x to 4x requests, like
    `limits.cpu: "400m"` to `"800m"`, and `limits.memory: "512Mi"` to `"1Gi"`).
    Avoid excessive overcommit limits (like `limits.cpu: "4"` for a `100m`
    request) to prevent severe CPU throttling and latency degradation under
    heavy scheduling load, particularly in environments without guaranteed node
    shares.
-   **Spot VMs for Staging/Dev**: For non-production workloads (e.g., namespaces
    containing `-test`, `-dev`, or `-staging`), or if the user requests cost
    optimization, automatically target GKE Spot VMs. This requires injecting
    both the `nodeSelector` targeting Spot VMs AND the corresponding toleration
    to tolerate the Spot VM taint:

    ```yaml
    nodeSelector:
      cloud.google.com/gke-spot: "true"
    tolerations:
      - key: "cloud.google.com/gke-spot"
        operator: "Equal"
        value: "true"
        effect: "NoSchedule"
    ```

    (On GKE Standard, this assumes a Spot node pool is configured).

### 3. Container Security Hardening (Pod Security Standards)

-   **Non-Root Execution**: Always configure `securityContext` at the Pod level
    (and container level if overriding) to run as a non-root user (e.g.,
    `runAsNonRoot: true`, `runAsUser: 10000`, `runAsGroup: 10000`, `fsGroup:
    10000`). This is strictly enforced on GKE Autopilot and is a critical
    security baseline for GKE Standard.
-   **Minimal Privileges**: Always set `allowPrivilegeEscalation: false` and
    `seccompProfile: {type: RuntimeDefault}`.
-   **Read-Only Root Filesystem**: Set `readOnlyRootFilesystem: true` to prevent
    modifications to the container image filesystem.
    -   *Writable Directory Fallback*: If `readOnlyRootFilesystem` is enabled,
        mount a local `emptyDir` volume to `/tmp` or `/var/run/` to allow
        applications (like Java/Nginx) to write temp files without crashing.
-   **Secret Volume Mounting**: Prefer mounting Secrets as read-only files
    (configured in the `volumes` spec with `defaultMode: 0400`) instead of
    mapping them as environment variables, unless the application framework
    exclusively supports env-var based configuration. This prevents secrets
    leaking into application logs.

### 4. Health Checking (Mandatory Probes)

-   **Liveness & Readiness Probes**: Every Deployment container must define both
    `livenessProbe` and `readinessProbe`.
    -   **Web/API**: Use `httpGet` probes.
    -   **TCP Services**: Use `tcpSocket` probes.
    -   **Databases/Caches**: Use command-based `exec` probes (e.g.,
        `exec.command: ["redis-cli", "ping"]`).
-   **Startup Probes for Slow-Starting Apps**: For applications with slow boot
    times (e.g., Java spring boot, complex Python scripts, LLM model servers),
    you **must** also define a `startupProbe`. When a `startupProbe` is defined,
    the liveness and readiness probes are disabled until it succeeds, preventing
    Kubernetes from prematurely killing the pod during startup:

    ```yaml
    startupProbe:
      httpGet:
        path: /healthz
        port: 8080
      failureThreshold: 30
      periodSeconds: 10
    ```

-   **Sensible Defaults**: Set `initialDelaySeconds: 5` to `15` depending on
    startup time (e.g., Java requires a longer delay than Go/Nginx).

### 5. Services & Ingress Routing

-   **Internal ClusterIP**: Default all internal microservices to `type:
    ClusterIP`. Never use `type: LoadBalancer` or `NodePort` unless the workload
    is explicitly intended to be publicly accessible from the internet.
-   **Port Naming**: Always assign clear, standard names to service and
    container ports (e.g., `name: http-web` or `name: grpc-api`) to enable
    automatic protocol discovery, tracing, and Web App routing.
-   **Prefer Gateway API**: When exposing APIs externally, prioritize using GKE
    Gateway API (`Gateway` and `HTTPRoute` resources) over legacy `Ingress`
    objects to enable advanced L7 routing and security features (e.g., Cloud
    Armor).

### 6. Volume Mounts, StorageClasses & subPath Safety

-   **Avoid Directory Overwrites**: When mounting a `ConfigMap` or `Secret` to
    an application directory containing other files (like Nginx public
    directories), always use `subPath` to overlay only the specific file.
    *Caveat*: Note that containers using `subPath` volume mounts do not receive
    automatic configuration updates if the underlying ConfigMap or Secret is
    modified; pods must be restarted manually to pick up changes.
-   **StorageClass Selection**: Use the correct GKE storage class in
    PersistentVolumeClaims:
    -   *CSI Driver Clusters (Autopilot & Modern Standard)*: Use `standard-rwo`
        (default balanced PD) or `premium-rwo` (SSD PD).
    -   *Legacy Standard Clusters*: Use `standard` (default PD) or `premium`
        (SSD PD) if `standard-rwo`/`premium-rwo` are not configured.
    -   *Database rule*: Use SSD storage classes (`premium-rwo` or `premium`)
        only when the prompt explicitly requests high IOPS, low latency, or
        database storage.

### 7. High Availability on GKE

-   **Topology Spread**: For deployments with >1 replica, use `podAntiAffinity`
    or `topologySpreadConstraints` with `topologyKey: "kubernetes.io/hostname"`
    to distribute pods across GKE nodes and availability zones.
-   **PodDisruptionBudget**: For deployments with >1 replica, declare a
    `PodDisruptionBudget` to guarantee minimum replica availability during
    voluntary GKE node upgrades and maintenance cycles.

### 8. Updates & Server-Side Apply Reconciliations

-   **Stable List Keys**: Under Kubernetes Server-Side Apply (SSA), elements in
    associative lists (like volumes, volume mounts, ports, and container
    definitions) are matched and merged by their unique identifier keys
    (typically `name`). You **must** keep the `name` key stable when modifying
    properties of an existing list item. Renaming the `name` key will cause SSA
    to create a brand new entry and leave the old entry intact (orphaned) rather
    than modifying it.
-   **Minimal Diff**: Make only the changes requested. Adhere closely to
    existing labels, annotations, and conventions.

--------------------------------------------------------------------------------

## Specialty Workloads: GKE AI/Inference Serving (vLLM, TGI, etc.)

For model serving workloads, prioritize using optimized tooling like GKE
Inference Quickstart if available. If generating manually:

1.  **GPU Request & Allocation**:
    -   Always request `nvidia.com/gpu` in both `requests` and `limits`.
    -   Add a `nodeSelector` or node affinity targeting the desired GKE
        accelerator tag (e.g., `cloud.google.com/gke-accelerator: nvidia-l4`).
2.  **Shared Memory Boost**:
    -   Model servers require high shared memory (`/dev/shm`) for inter-process
        communications. Always declare and mount an `emptyDir` volume with
        `medium: Memory` to `/dev/shm`.
3.  **Weight Loading Optimization**:
    -   Mount model weight directories (like GCS buckets) using the GKE GCS Fuse
        CSI driver (`csi.storage.gke.io`) as `readOnly: true` for efficient
        cold-starts.

--------------------------------------------------------------------------------

## Tooling & Grounding Guidelines

When generating manifests, you should leverage the following tooling to reduce
hallucinations and optimize configurations:

1.  **Inference Workloads (GKE Inference Quickstart CLI)**:

    -   Make sure you have the
        [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed.
    -   For all AI/LLM inference workloads (e.g. model serving), you **must**
        prioritize using the `gcloud` CLI GKE Inference Quickstart command to
        generate the optimized manifests instead of writing them manually:

        ```bash
        gcloud container ai profiles manifests create \
          --model={model_name} \
          --model-server={server_name} \
          --accelerator-type={accelerator_type} \
          --output=manifest \
          --output-path={output_file_path}
        ```

    -   *Constraint*: You must include all resources returned by this command
        (Deployments, Services, PodMonitoring, etc.) without filtering.

2.  **Grounding in Official Documentation (Developer Knowledge API)**:

    -   For GKE-specific features, API defaults, manifest examples, or security
        contexts, you **must** query Google's developer knowledge base to
        retrieve official GKE documentation:
        -   **`answer_query`**: Use this to ask direct questions (e.g., *"How to
            configure GCS Fuse CSI driver in GKE"*). This is the preferred tool
            for general queries.
        -   **`search_documents`**: Use this to search for relevant GKE guides
            or examples when you don't have a specific question.
        -   **`get_document`**: Use this to fetch full document contents when
            you have a specific document ID.

--------------------------------------------------------------------------------

## Reference Examples

For detailed, production-ready manifest templates, consult the following
reference guides:

-   **[Basic Hardened Nginx Workload](references/basic-workload.md)**:
    Production-ready deployment with dedicated service account, security
    contexts, probes, anti-affinity, and PodDisruptionBudget.
-   **[Network Policy](references/network-policy.md)**: Default-deny ingress
    network policy and selective ingress allowance for specific apps.
-   **[AI/LLM Inference Workload](references/ai-inference.md)**: GPU resource
    allocation, Workload Identity, GCS FUSE CSI driver mounting, `/dev/shm`
    shared memory boost, and startup probes.
-   **[GKE Gateway API Routing](references/gateway-api.md)**: Exposing workloads
    using GKE L7 Gateway API (`Gateway` and `HTTPRoute` resources).
