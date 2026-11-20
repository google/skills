# ComputeClass: Cost Optimization & FlexCUDs

## Aligning with Committed Use Discounts (CUDs)

Before selecting machine families for your `priorities[]` list, you **must**
identify your existing Committed Use Discounts (CUDs) and Reservations.

**Key Strategy:** The On-Demand "floor" of your ComputeClass should heavily bias
toward machine families covered by your CUDs (Resource-based or Flexible).

### FlexCUD Coverage

-   **Eligible:** Most general-purpose and compute-optimized families (e.g.,
    `N2`, `N4`, `C3`, `C4`, `E2`, `N2D`).
-   **Ineligible / Excluded:**
    -   GPUs
    -   TPUs
    -   Local SSDs
    -   Memory-optimized families (`M` series) (typically require resource-based
        CUDs)
    -   Preemptible / Spot VMs
    -   Sole-tenant nodes

### Priority List Design

When designing the `priorities[]` array for workloads that don't strictly
require specialized hardware:

1.  **Spot Tier (Highest Priority):** Attempt to provision Spot VMs first. Spot
    is cheaper than FlexCUD On-Demand but is not covered by CUDs. Use
    `priorityScore` to tie-break across multiple Spot families based on unit
    cost. (Note: You can assign the same score to a maximum of 3 rules).
2.  **FlexCUD Tier (Middle Priority / Floor):** If Spot is unavailable, fall
    back to On-Demand families that are explicitly covered by your active
    FlexCUDs.
3.  **General On-Demand Tier (Lowest Priority - Optional):** If FlexCUD families
    are exhausted, fall back to other general-purpose On-Demand families (e.g.,
    `E2`) to ensure obtainability.

### Example: Balancing Spot and FlexCUDs

```yaml
  priorities:
  # 1. Try Spot first across modern families
  - machineFamily: n4
    spot: true
    priorityScore: 100
  - machineFamily: c4
    spot: true
    priorityScore: 90
  # 2. Fallback to On-Demand covered by FlexCUD
  - machineFamily: n4
    spot: false
    priorityScore: 50  # if any rule sets priorityScore, every rule must
    # Assume N4 is covered by our regional FlexCUD commit
```

## Active Migration for Cost

Enable `activeMigration` to allow GKE to continuously move workloads to more
cost-effective nodes as capacity becomes available.

```yaml
  activeMigration:
    optimizeRulePriority: true
```

-   If a workload falls back to an On-Demand node (because Spot was
    unavailable), active migration will automatically evict the pod and move it
    to a Spot node when Spot capacity returns.
-   **Throttling Vol. Disruptions:** Active migration honors Pod Disruption
    Budgets (PDBs). Use PDBs to throttle eviction rates. To stop active
    migration for specific pods, add the
    `cluster-autoscaler.kubernetes.io/safe-to-evict: "false"` annotation
    (adding it to a Deployment's pod template triggers a rolling restart; a
    PDB applies without one — see `compute-class-lifecycle.md`).
-   **WARNING:** PDBs and `safe-to-evict` only block *voluntary* scaler actions.
    They **cannot** block *involuntary* Spot VM preemptions.

## Balanced HA Scale-Up Across Zones

"Balanced" spans **two independent layers** — clarify which the user wants:

-   **Infrastructure (nodes):** `locationPolicy: BALANCED` spreads node scale-up
    roughly evenly across zones (best-effort; **still scales up** if a zone is
    short; `ANY` packs one zone).
-   **Workload (pods):** BALANCED does **not** balance pods. Add pod
    `topologySpreadConstraints` (`maxSkew:1`, `topologyKey:
    topology.kubernetes.io/zone`, `whenUnsatisfiable: DoNotSchedule` — default
    `ScheduleAnyway` won't enforce it) on the **workload** (see
    `gke-cluster-autoscaler`).

**Trap:** one priority *per zone* does NOT balance — priorities are sequential,
so zone-a drains fully before zone-b is tried.

**Method A — `locationPolicy: BALANCED` (no `priorityScore`, works
pre-1.35.2):**

-   Use **ONE** `priorities[]` entry per machine size (not one priority *per
    zone*). Inside it, set `reservations.affinity: Specific`; the
    `reservations.specific[]` list holds **one entry per zone** (3 zones → 3
    named `specific[]` entries with their own `name` + `zones`). Don't make a
    separate priority per reservation, and don't collapse all zones into a
    single entry.
-   Set `location.locationPolicy: BALANCED`. **Schema:** do **not** put
    `location.zones` on a `Specific`-reservation priority (error: *location
    config with specific reservations enabled*) — zones come from the
    reservations; the `location` block keeps `locationPolicy` only.
-   Asset: `balanced-reserved-zonal-compute-class.yaml`.

**Method B — equal `priorityScore` (GKE 1.35.2-gke.1842000+; not balanced):**

-   Define separate per-zone priority rules and assign them an **equal
    `priorityScore`** (max 3 rules/score).
-   GKE evaluates them together via the autoscaler expander (lowest cost wins,
    with random tie-breaking when costs are equal). This is not round-robin and
    does not guarantee an even zonal spread; add pod `topologySpreadConstraints`
    when an even spread matters.
