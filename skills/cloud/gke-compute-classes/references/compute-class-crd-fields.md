# ComputeClass: CRD Fields & Spec Reference

Full CRD: `kubectl describe crd computeclasses.cloud.google.com`.

## Minimal Shape

```yaml
apiVersion: cloud.google.com/v1
kind: ComputeClass
metadata: { name: my-class }
spec:
  nodePoolAutoCreation: { enabled: true }
  priorities:
  - machineFamily: n4
    minCores: 16
```

## Top-Level Spec Fields

| Field                          | Purpose              | Default / Note       |
| ------------------------------ | -------------------- | -------------------- |
| `description`                  | Usage guidelines.    | Optional string.     |
| `nodePoolAutoCreation.enabled` | Enable node pool     | `false`              |
:                                : auto-creation for    :                      :
:                                : this ComputeClass.   :                      :
:                                : **Does NOT require   :                      :
:                                : cluster-level Node   :                      :
:                                : Auto Provisioning.** :                      :
| `nodePoolAutoCreation.shieldedInstanceConfig` | Shielded GKE Nodes   | Optional. Toggles    |
:                                               : settings for auto-   : `enableSecureBoot`   :
:                                               : created pools.       : and `enableIntegrity-:
:                                               :                      : Monitoring` (GKE     :
:                                               :                      : 1.36.3-gke.1244000+).:
| `nodePoolConfig`               | Defaults for node    | See below.           |
:                                : pool auto-creation   :                      :
:                                : pools (image, SA,    :                      :
:                                : labels, taints).     :                      :
| `priorityDefaults`             | Defaults applied to  | e.g. `zones`,        |
:                                : all `priorities[]`   : `sysctls`.           :
:                                : entries.             :                      :
| `priorities[]`                 | Ordered list of      | Tried top-to-bottom. |
:                                : provisioning         :                      :
:                                : attempts.            :                      :
| `autoscalingPolicy`            | Consolidation        | `1` min floor.       |
:                                : thresholds and       :                      :
:                                : delay.               :                      :
| `activeMigration`              | Drift logic to       | Honors PDBs.         |
:                                : higher priorities.   :                      :
| `whenUnsatisfiable`            | Fallback behavior    | `DoNotScaleUp`       |
:                                : when priorities      : (Default).           :
:                                : exhaust.             :                      :

## `nodePoolConfig` (node pool auto-creation Only)

Applied to pools created by the autoscaler.

-   `imageType`: `cos_containerd`, `ubuntu_containerd` (must be **lowercase**).
-   `nodeLabels`: Key-value pairs.
-   `taints`: List of `{ key, value, effect }`. Valid for an intentional
    dedication taint; keys **cannot contain `kubernetes.io`** (GKE Warden
    rejects it). **DO NOT re-add `cloud.google.com/compute-class` on
    auto-created pools — GKE applies and auto-tolerates it. (Manual pools, by
    contrast, REQUIRE it as label + taint to bind.)**
-   `serviceAccount`: Identity for nodes (use custom SA with least privilege,
    not default).
-   `gvnic`: `{ enabled: true }` (`boolean`, default `false`) to enable Google
    Virtual NIC on auto-created node pools.

## `priorities[]` Fields

-   `machineFamily` / `machineType`: Intent vs. strict. Prefer family.
-   `minCores`, `minMemoryGb`: Lower bounds for intent-based matching.
-   `spot`: `true` for Spot, `false` for On-Demand.
-   `location.zones`: List of zones to attempt. **Cannot combine with
    `reservations.affinity: Specific`** (error: *location config with specific
    reservations enabled*) — with Specific reservations, zones come from
    `reservations.specific[].zones` and you keep only a policy-only
    `location.locationPolicy`.
-   `location.locationPolicy`: `ANY` (default; packs for utilization, tends to
    fill one zone) or `BALANCED` (best-effort even **node** spread across zones
    at scale-up — *infrastructure* layer; still scales up if a zone is short).
    Balances nodes, **not** pods — for even *pod* distribution add pod
    `topologySpreadConstraints`/`DoNotSchedule` (*workload* layer).
-   `reservations`: `affinity` is one of `Specific`, `AnyBestEffort`,
    `AnyThenFail` (GKE 1.36.0-gke.3204000+) or `None`.
-   `flexStart`: `{ enabled: true }` for DWS queued provisioning.
-   `gpu` / `tpu`: Accelerator requests (count, type, topology).
-   `nodepools`: (Standard Only) List of manual pool names to target.
-   `nodeSystemConfig` (also valid under `spec.priorityDefaults`):
    -   `linuxNodeConfig`: `sysctls` (e.g., `net.ipv4.tcp_tw_reuse: true`,
        `net.core.somaxconn: 4096`), `transparentHugepageEnabled` (`string`
        enum: `TRANSPARENT_HUGEPAGE_ENABLED_ALWAYS`,
        `TRANSPARENT_HUGEPAGE_ENABLED_MADVISE`,
        `TRANSPARENT_HUGEPAGE_ENABLED_NEVER`, or
        `TRANSPARENT_HUGEPAGE_ENABLED_UNSPECIFIED`). **Never quote integer or
        boolean values.**
    -   `kubeletConfig`: `cpuCfsQuota`, `podPidsLimit`, and (on `spot: true`
        priorities only, GKE `1.36.0-gke.3204000+`)
        `shutdownGracePeriodSeconds` (`0`, `30`, or `120` to extend graceful
        Spot shutdown up to 120s).
-   `secondaryBootDisks`: Attach secondary boot disks (e.g. pre-warmed container image disks) to auto-provisioned nodes for zero-delay container startup.
-   `bootDiskProfile`: Performance profile for boot disks (e.g. `BALANCED`).
-   `ephemeralLocalSsdProfile` / `dedicatedLocalSsdProfile`: Intent-based NVMe scratch space profiles.
-   `storage`: Set `bootDiskType`, `bootDiskSize`, and `localSSDCount`
    specifically for this priority. Overrides cluster/nodePoolConfig defaults.
    **This is the NODE boot disk, NOT the workload's data PV** — for attached
    PVs use a Kubernetes `StorageClass` (recommend the built-in `dynamic-rwo`
    with `use-allowed-disk-topology: "true"` on GKE 1.35.3-gke.1290000+; see
    [provisioning methods](./compute-class-provisioning-methods.md)).

## Important Schema Constraints

-   **Case Sensitivity**: `imageType` must be lowercase (e.g.,
    `cos_containerd`).
-   **Version-Gated Fields**: Check cluster version before emitting newer CRD
    fields: `spec.description` (GKE 1.33+), `spec.nodePoolConfig.gvnic`
    (`{enabled: true}`, GKE 1.34.1-gke.3759000+),
    `nodeSystemConfig.linuxNodeConfig.transparentHugepageEnabled` (GKE
    1.34.1-gke.3084001+), and
    `nodeSystemConfig.kubeletConfig.shutdownGracePeriodSeconds` (`0 | 30 | 120`,
    GKE 1.36.0-gke.3204000+). Do NOT emit them on older clusters.
-   **Field Nesting**: Place `spec.description` at top-level `spec`,
    `gvnic.enabled` under `spec.nodePoolConfig`, and
    `transparentHugepageEnabled` / `shutdownGracePeriodSeconds` (`spot: true`
    only) under `priorities[].nodeSystemConfig` (or `spec.priorityDefaults`).
-   **Spot-Only `shutdownGracePeriodSeconds`**: The CRD rejects
    `shutdownGracePeriodSeconds` on any priority that does not set `spot: true`
    (*shutdownGracePeriodSeconds is only supported for Spot*), and in
    `priorityDefaults.nodeSystemConfig` unless every priority is Spot.
-   **YAML Formatting**: ALWAYS use literal integers for fields like
    `bootDiskSize`, `minCores`, and `somaxconn`. **DO NOT wrap them in quotes.**
    -   **Correct**: `bootDiskSize: 50`
    -   **Incorrect**: `bootDiskSize: "50"`
-   **Storage**: Use `bootDiskSize`, NOT `bootDiskSizeGb`.

## `whenUnsatisfiable`

-   `DoNotScaleUp` (Default): Pods stay `Pending`. Best for specific hardware
    needs.
-   `ScaleUpAnyway`: Provisions **E2** nodes on Standard with node pool
    auto-creation. Avoid for specialized workloads.
