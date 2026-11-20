# GKE ComputeClasses: Debugging

## First Check: GKE Version

If fields are ignored or fail with "not supported," the control plane is likely
too old.

-   **Verify CRD:** `kubectl describe crd computeclasses.cloud.google.com`
-   **Check Versions:** `gcloud container clusters describe <CLUSTER>
    --format="value(currentMasterVersion,currentNodeVersion)"`

## Symptom 1: ComputeClass Config Error

Check `status.conditions` on the ComputeClass object via `kubectl describe
ComputeClass <NAME>`.

-   **Common Error:** `location config with specific reservations enabled`.
-   **Fix:** Remove `location.zones` from the reservation priority — zones come
    from `reservations.specific[].zones` instead. Only `location.zones`
    collides; a policy-only `location.locationPolicy` (e.g. `BALANCED`) may
    remain.

## Symptom 2: Scale-Up Failure (Pods Pending)

Check **Autoscaler Visibility logs**
([docs](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cluster-autoscaler-visibility)).

-   **Log Filter:**
    `log_id("container.googleapis.com/cluster-autoscaler-visibility")`
-   **Asset:** `assets/log-autoscaler-events.sh <cluster-name>` (Live tail).

| `messageId`                         | Meaning           | Fix                |
| ----------------------------------- | ----------------- | ------------------ |
| `scale.up.error.out.of.resources`   | GCE stockout      | Add zone/family    |
:                                     :                   : fallbacks.         :
| `scale.up.error.quota.exceeded`     | Project quota cap | Raise quota in     |
:                                     :                   : target region.     :
| `scale.up.error.ip.space.exhausted` | Subnet full       | Expand subnet      |
:                                     :                   : ranges.            :
| `scale.up.no.scale.up`              | No priority       | Check Pod requests |
:                                     : matched           : vs shapes.         :

## Symptom 3: Trapped in Pending (GPU Tolerations Missing)

-   **Symptom:** Pod requesting a GPU ComputeClass is stuck in `Pending` with
    `noScaleUp` logs.
-   **Cause:** GKE auto-taints GPU nodes (`nvidia.com/gpu:NoSchedule`).
    Scheduler refuses placement without a toleration.
-   **Fix:** Add toleration to pod spec:

    ```yaml
    tolerations:
    - key: "nvidia.com/gpu"
      operator: "Exists"
      effect: "NoSchedule"
    ```

## Symptom 4: Wrong Nodes Provisioned (E2 Fallback Trap)

-   **Symptom:** Requested specific nodes (e.g., `C3` or `N4`), but GKE
    provisions default `E2` nodes.
-   **Cause:** `whenUnsatisfiable: ScaleUpAnyway` provisions generic E2 nodes to
    start the pod if preferred hardware fails.
-   **Fix:** Set `whenUnsatisfiable: DoNotScaleUp` to strictly enforce hardware
    list.

## Symptom 5: Active Migration Blocked

-   **Symptom:** Spot capacity returned, but pods stuck on On-Demand nodes.
-   **Cause:** Pod Disruption Budgets (PDBs) block eviction. Active migration
    strictly honors PDBs.
-   **Fix:** Ensure PDBs allow at least 1 disruption. `maxUnavailable: 0` blocks
    migration.
-   **Common GKE blocker — system-managed pods:** Non-DaemonSet pods in system
    namespaces (`kube-system`, `gke-managed-*`, `gmp-system`) often carry tight
    PDBs + low replicas, so the source node cannot drain (also blocks ordinary
    scale-down). Check `kubectl get pdb -A` and the autoscaler `noScaleDown`
    reason; raise replicas to add PDB headroom or isolate them onto a separate
    ComputeClass.
-   **Note:** PDBs / `safe-to-evict` only gate *voluntary* disruption; Spot
    preemption is involuntary and ignores both.

## Symptom 6: ImageType Fragmentation Bug (Pre-1.33.5)

-   **Symptom:** Autoscaler creates hundreds of tiny, fragmented node pools.
-   **Cause:** Explicitly defining `imageType` (`ubuntu_containerd` or
    `cos_containerd`) on
    versions older than 1.33.5-gke.1862000 (and 1.34.1-gke.2541000).
-   **Fix:** Upgrade cluster or temporarily remove `imageType`.

## Symptom 7: Pods Ignoring ComputeClass

-   **Fixes:** Ensure pod has `nodeSelector: cloud.google.com/compute-class:
    <NAME>`. **Translate non-GKE node selectors** — a generic/AWS-style
    `machine-family: c4` won't match; use GKE-native
    `cloud.google.com/machine-family: c4` (family) or
    `node.kubernetes.io/instance-type` (shape), or better, move the constraint
    into the ComputeClass `priorities[]`. Verify manual pools have correct
    label/taint. Check if Pod requests exceed priority bounds.

## Symptom 8: "ANY" Reservation Bypasses Fallbacks

-   **Cause:** `reservations.affinity: AnyBestEffort` consumes On-Demand capacity at
    the GCE layer before evaluating your remaining ComputeClass priorities, preventing your intended fallback.
-   **Fix:** Use `affinity: AnyThenFail` (GKE 1.36.0-gke.3204000+) or `affinity: Specific` with named reservations.

## Symptom 9: Disk/PV Attachment Fail

-   **Cause:** Mixing Gen 4 VMs (Hyperdisk) and Gen 2 (PD) in the same priority
    list.
-   **Fix:** Do not mix generations for workloads with attached PVs. **Or (GKE
    1.35.3-gke.1290000+):** back the data PVs with the built-in `dynamic-rwo`
    StorageClass (`type: dynamic` + `use-allowed-disk-topology: "true"`) — the
    autoscaler becomes disk-topology-aware and scales up only compatible nodes,
    so a mixed-generation `priorities[]` no longer attach-fails.

## Symptom 10: Zonal PV Deadlock (Pending Pods)

-   **Symptom:** StatefulSet pod is Pending because disk is in zone B but node
    is in zone A.
-   **Fix:** Do **not** hardcode `location` in priorities. Use a `StorageClass`
    with `volumeBindingMode: WaitForFirstConsumer` so the disk provisions in the
    chosen node's zone — the built-in `dynamic-rwo` (GKE 1.35.3-gke.1290000+)
    already sets this plus `use-allowed-disk-topology: "true"`.

## Symptom 11: List Loops / Backoff

-   **Cause:** A long priority list (more than about 10 rules; keep ladders
    to 6–8). Unobtainable shapes enter a 5-minute cooldown.
    Long lists expire upper-tier cooldowns before reaching the bottom, causing
    an infinite loop.
-   **Fix:** Trim list; remove redundant rules.

## Symptom 12: Pods on Low-Priority Nodes

-   **Symptom:** Pods land on existing low-priority nodes (e.g., On-Demand)
    instead of triggering scale-up for available high-priority nodes (e.g.,
    Spot).
-   **Cause:** ComputeClass controls *node provisioning*, not *pod scheduling*.
    K8s schedules pods on any existing node with capacity before scaling up.
-   **Fix:**
    1.  **ActiveMigration:** Set `optimizeRulePriority: true` to eventually move
        workloads to higher-priority nodes.
    2.  **PriorityClass:** Use native K8s PriorityClass for pod-level
        preemption.
    3.  **Kueue:** Use Kueue for complex batch/AI/ML fair-sharing and queueing.

## Useful Commands

```bash
kubectl get nodes -L cloud.google.com/compute-class
kubectl get pods -A -o json | jq -r '.items[] | select(.spec.nodeSelector["cloud.google.com/compute-class"]=="<name>") | .metadata.name'
gcloud logging read 'log_id("container.googleapis.com/cluster-autoscaler-visibility")' --freshness=1h --limit=50
```
