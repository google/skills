# Cluster Autoscaler: Capacity Buffers (Pre-warm)

## `CapacityBuffer` (CRD)

- **Provisioning Strategy:** `buffer.x-k8s.io/active-capacity` (Placeholder pods).
- **Namespace-scoped:** Targets a specific `ComputeClass` via `nodeSelector` in the `podTemplateRef`.

## Sizing Modes
- **Fixed:** `replicas: 3`. Always keep N units warm.
- **Dynamic:** `percentage: 20` + `scalableRef: <Deployment>`. Headroom scales with workload.

## Why use Buffers?
- **Bursty Serving:** Pod-pending SLOs can't tolerate 60-120s node pool auto-creation delay.
- **HPA outpaces cluster autoscaler:** Workload scales faster than nodes can arrive.
- **Pre-warming:** Warm GPUs/TPUs before known traffic windows.

*Note:* Replaces the "dumb" floor of `--min-nodes` with shape-aware, class-targeted warm capacity.
