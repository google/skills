# ComputeClass: Prioritization, Logic & Fallbacks

## Traversal & Tie-Breaking

-   **Sequential:** Evaluated top-to-bottom. Unobtainable shapes enter a **5-minute cooldown**. Keep priority lists compact (aim for ≤6–8 rungs).
-   **Tie-break (No Score):** Top entry wins. If multiple shapes match one rule, lowest unit cost wins.
-   **Tie-break (`priorityScore`):** Int 1–1000 (Higher = Preferred). If one
    rule has a score, **all** must. Max **3 rules per score**. Tied rules are
    evaluated together by the autoscaler expander (lowest cost wins, with
    random tie-breaking when costs are equal — no round-robin guarantee). (GKE
    1.35.2-gke.1842000+).
-   **Equal-Score Zonal Rules**: Since GKE reservations are zonal, you can
    define separate priority rules for each zone (e.g., `us-central1-a`, `b`,
    and `c`) and assign them the **exact same `priorityScore`**. GKE evaluates
    these tied rules together via the autoscaler expander (lowest cost, random
    tie-break on equal cost); this is not round-robin and does not guarantee an
    even zonal distribution. `locationPolicy: BALANCED` does not guarantee it
    either: it balances zones within one multi-zone node pool, and with node
    pool auto-creation each single-zone `reservations.specific[]` entry gets
    its own node pool. For an even spread across per-zone reservations, add pod
    `topologySpreadConstraints` on the workload (see "Balanced HA Scale-Up
    Across Zones" in `compute-class-cost-optimization.md`).

## Cooldown & Fallback Mechanics in Practice

-   **5-Minute Fixed Cooldown**: When a scale-up fails due to stockout (`scale.up.error.out.of.resources` / `ZONE_RESOURCE_POOL_EXHAUSTED`), Cluster Autoscaler applies a 5-minute cooldown to that priority rule. Unlike standard node pool MIG backoffs, this cooldown is fixed (not exponential).
-   **Cooldown Prolongation Across Rungs**: When sequential stockouts occur down the priority ladder, each failure resets the 5-minute cooldown timer for all previously failing rungs in that ComputeClass. This pushes Cluster Autoscaler forward toward the first obtainable priority rather than immediately restarting from the top after individual MIG backoffs expire.
-   **Fallback Floor Safety Guarantee**: The final priority rule in `priorities[]` (and implicit `ScaleUpAnyway` rule) is **never backed off** by the ComputeClass cooldown, guaranteeing an active fallback floor.
-   **Zonal vs Regional Cooldown Scope**:
    -   *Legacy GKE Behavior (< 1.36.3-gke.1244000)*: In GKE versions prior to `1.36.3-gke.1244000`, a single-zone stockout on a declarative rule triggers a **regional** ~5-minute cooldown across all zones for that priority tier.
    -   *Modern GKE Behavior (≥ 1.36.3-gke.1244000)*: Starting in GKE `1.36.3-gke.1244000+`, stockout cooldowns are strictly **zonal** (failing zone enters cooldown, while healthy zones continue provisioning the preferred tier). Quota errors (`QUOTA_EXCEEDED`) remain regional across all zones.
-   **Zonal Cooldown Cascades & Mitigations**:
    -   *Root Cause*: Unconstrained pods with `locationPolicy: BALANCED` do not trigger cascades on their own (the autoscaler skews provisioning to healthy zones). Cascades to the bottom tier occur when **zonally constrained workloads** (pods bound to a zonal PersistentVolume or rigid zonal `nodeSelector`/affinity) demand capacity in a stocked-out zone, forcing evaluation of subsequent fallback rungs.
    -   *Mitigation 1 (Intermediate Rungs)*: Insert intermediate machine family rungs (e.g. `c4` -> `c3` -> `n4` -> `n2d`) instead of a steep drop from scarce hardware directly to baseline `e2`/`n2d`.
    -   *Mitigation 2 (Stateful Workload Isolation)*: Isolate stateful and zonally constrained workloads into a dedicated ComputeClass separate from the stateless fleet.
    -   *Mitigation 3 (`dynamic-rwo` StorageClass)*: Back stateful workloads with `dynamic-rwo` (`type: dynamic`, `use-allowed-disk-topology: "true"`), enabling disk-topology-aware scaling.
-   **Manual `nodepools` Priority Traps**:
    -   Rules referencing existing manual node pools via `priorities[].nodepools` do **not** use ComputeClass cooldown prolongation; they rely solely on standard 5-minute GCE MIG backoffs.
    -   With sprawling manual pool lists (e.g. 10+ pools across multiple zones), early MIG backoffs expire before lower tiers are evaluated, causing Cluster Autoscaler to bounce back to the top of the priority list and loop indefinitely without reaching lower tiers.
    -   *Best Practice*: Prefer declarative `machineFamily` rules with `nodePoolAutoCreation.enabled: true`. If manual pools must be used, cap total manual pools at **6–8 node pools**.
-   **`flexStart` Ordering Rule**:
    -   DWS Flex Start priorities use queued capacity provisioning, which takes 3–15+ minutes to return a stockout signal.
    -   If placed high or middle in `priorities[]`, higher-tier backoffs expire during the queue wait, resetting Cluster Autoscaler to the top of the ladder.
    -   *Best Practice*: Place the `flexStart` rule (`flexStart: {enabled:
        true}`) after every other non-preemptible tier; only a Spot last resort
        may follow it (see the Inference and Prod Training rows below).
-   **`min-nodes` Interaction with Scheduler**:
    -   `kube-scheduler` places incoming pods on existing idle capacity (held warm by `min-nodes`) *before* Cluster Autoscaler evaluates ComputeClass priorities.
    -   If lower-priority manual pools have idle capacity due to high `min-nodes`, pods immediately schedule onto those lower-priority nodes, bypassing preferred ComputeClass tiers entirely.
    -   *Best Practice*: Set `min-nodes` to 0 on manual pools and use `CapacityBuffer` (or upcoming `spec.minimumCapacity.targetNodeCount`) for warm headroom.
-   **GKE 1.36+ Synchronous Obtainability**:
    -   Starting in GKE 1.36, Cluster Autoscaler queries an internal capacity obtainability service synchronously in memory before issuing VM creation calls.
    -   It skips currently exhausted machine families in memory without generating GCE API errors or tripping 5-minute cooldowns.
-   **Coarse Heuristics of `advice.capacity`**:
    -   The `gcloud beta compute advice capacity` CLI returns discrete Spot/Flex probability buckets (`0.1`, `0.5`, `0.9`). Google does not expose public real-time on-demand obtainability APIs.
    -   Declare preferred ordering in ComputeClasses; Cluster Autoscaler arbitrates obtainability at runtime.

## Fallback Patterns

Pattern        | Priority Order           | Rationale                                                                                   | Asset
-------------- | ------------------------ | ------------------------------------------------------------------------------------------- | -----
Inference      | Res -> OD -> DWS -> Spot | Accelerator node startup is slow. Avoid Spot preemption risk for latency-sensitive serving. | `genai-inference-g4-compute-class.yaml`
Prod Training  | Res -> DWS -> OD -> Spot | DWS wait acceptable. Spot preemption disruptive. Put DWS before Spot; Flex at bottom of non-preemptible tiers. | `tpu-v5e-training-compute-class.yaml`
Dev Training   | Spot -> OD               | Spot for cost; OD floor unblocks dev.                                                       |
Cost Batch     | Spot -> OD               | Use `priorityScore` to pick cheapest Spot family.                                           | `spot-cost-tiebreak-compute-class.yaml`
Latency Hybrid | Manual -> Auto-creation  | Skip auto-creation delay by hitting warm pools (limit manual pools to ≤6–8).                | `manual-pool-tiebreak-compute-class.yaml`

## Key Rules

-   **No repetition:** Doesn't improve obtainability.
-   **Vary dimensions:** Zone, Family, Capacity (Spot/OD), **machine size (cores)**.
-   **Size obtainability (large shapes are scarce):** Shapes **>32 vCPU** draw from thinner capacity pools and hit `out.of.resources` stockouts far more than ≤32-core shapes. A ComputeClass pinned to large machines **only** has no escape hatch → `Pending`. Add **smaller-core fallback priorities** *if the workload allows it*. **Gate on Pod requests:** node auto-creation sizes nodes to Pod *requests*, so a single pod requesting >32 vCPU **cannot** land on a smaller node — only horizontally-scalable workloads (many small pods that bin-pack) benefit. For a genuinely large single pod, vary **zone/family** instead, not cores.
-   **Always include a floor:** End with high-availability OD (e.g., N4/E2) to prevent `Pending`.
-   **Stateful Gen Isolation:** For PV workloads, do NOT mix hardware generations (e.g., all Gen 4 OR all Gen 2) in `priorities[]`. Mixing causes Hyperdisk vs PD attachment failures. **Exception (GKE 1.35.3-gke.1290000+):** with the built-in `dynamic-rwo` StorageClass (`type: dynamic` + `use-allowed-disk-topology: "true"`) the autoscaler scales up only disk-compatible nodes, so it skips the incompatible-generation priority instead of attach-failing — mixing generations is then safe.
-   **Mixed Architectures:** Mix ARM (`n4a`) and x86 (`n4`) in `priorities[]`. Autoscaler skips incompatible shapes based on Pod constraints. **Must use multi-platform image builds.**
-   **Spot Availability:** For CPU, if OD is out, Spot usually is too. For Accelerators, Spot often has capacity when OD doesn't.

