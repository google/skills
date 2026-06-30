# Cluster Autoscaler: Optimization Profiles & Location Policies

## Autoscaling Profiles (Cluster-wide)
| Profile | Behavior | When to use |
|---------|----------|-------------|
| `balanced` (default) | Keeps spare capacity; conservative scale-down. | Latency-sensitive serving. |
| `optimize-utilization` | Aggressive packing; faster removal. | Cost-driven; Batch; **Golden Path**. |

- **Command:** `gcloud container clusters update <C> --autoscaling-profile=optimize-utilization`.

## Spot Best Practices
- **Mandatory Fallback:** Any time you recommend or debug the use of Spot instances (whether via manual pools or node pool auto-creation), suggest including other Spot or On-Demand fallback priorities via ComputeClasses. Spot capacity is highly variable, and without a fallback, workloads will become stuck during GCE stockouts (`scale.up.error.out.of.resources`).

## Location Policies (`--location-policy`)

- **`BALANCED`**: Best-effort even **node** spread across zones *at scale-up* (infrastructure layer; still scales up if a zone is short). Does **not** balance **pods** — that's a separate workload layer needing pod `topologySpreadConstraints` (`DoNotSchedule`, see PTS below). The two are independent. Use for **HA workloads**.
- **`ANY`**: Grabs capacity from any zone. **Best for Spot VMs** and scarce SKUs (maximizes obtainability).

## ComputeClass `locationPolicy`

```yaml
priorities:
- machineFamily: n4
  spot: true
  location:
    locationPolicy: ANY # Spot preference
```

## Pod Topology Spread Constraints (PTS)
Cluster Autoscaler supports PTS for zonal spreading during scale-up.

To enforce spreading via autoscaler, you **MUST** use `whenUnsatisfiable: DoNotSchedule`.

Example Configuration:
```yaml
spec:
  topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: "topology.kubernetes.io/zone"
    whenUnsatisfiable: DoNotSchedule  # Required for cluster autoscaler compatibility
    labelSelector:
      matchLabels:
        app: my-app
```

## Resource CUDs vs. Reservations

- **Committed Use Discounts (CUDs):** Automatically consumed by the Cluster Autoscaler. When the autoscaler provisions a node of a specific machine family (e.g., `n4`), it automatically consumes any available CUD for that family up to exhaustion. No explicit autoscaler, Node Auto Provisioning, or ComputeClass configuration is needed.
- **Reservations:** Unlike CUDs, capacity reservations are **not** automatically consumed. They must be explicitly targeted. You must configure consumption via the Node Pool API (for standard/manual pools) or via a ComputeClass `reservations` block (for node pool auto-creation).
- **Freshly-created reservations (cache lag):** The autoscaler caches reservation data and does **not** see a new reservation immediately. Driving scale-up against a brand-new reservation while Cluster Autoscaler's cache is stale makes Cluster Autoscaler fail to find the capacity and **back off that reservation** — which delays retries and compounds the stall. **Fix:** wait **at least 30 minutes** after creating a reservation before relying on it for autoscaler-driven scale-up. (Applies to the reservation itself; growing an existing, already-cached reservation is fine.)
