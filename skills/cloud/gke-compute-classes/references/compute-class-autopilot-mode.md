# Autopilot Mode on Standard Clusters

Run **Autopilot-mode** workloads (Google-managed nodes, pod-based billing,
Autopilot security defaults) on a **Standard** cluster — per-workload, without
converting the cluster. Selection is by ComputeClass.

## Built-in `autopilot` classes

-   **Classes:** `autopilot` and `autopilot-spot` — **pre-installed** on
    qualifying clusters. Reference by name; do **not** author them.
-   **Requirements:** GKE **1.33.1-gke.1107000+**, **Rapid** channel initially
    (rolling to other channels). **Excluded:** Extended channel and
    routes-based-networking clusters.
-   **Availability lag:** preinstalled classes may take up to ~1h to appear
    after cluster creation (CRD installed by the autoscaler component). See
    debug ref / `gke_ccc_preinstalled_delay`.

## Opting a workload in

-   **Per-Pod:** `nodeSelector: { cloud.google.com/compute-class: autopilot }`
    (or a node-affinity rule on that label).
-   **Namespace default:** `kubectl label ns $NS
    cloud.google.com/default-compute-class=autopilot` — all Pods in the
    namespace run Autopilot mode unless they select another class.
-   **Existing Pods:** Pods already running on Standard nodes switch to
    Autopilot mode **only when recreated** (rollout/restart), not in place.

## Billing — driven by the priority-rule type, NOT pod size

Billing is **not** tied to a vCPU threshold. It's the kind of priority rule GKE
uses:

-   **Built-in `autopilot`/`autopilot-spot` = always pod-based:** pay for Pod
    **requests** only (no system overhead, no empty nodes). Built-in pod size
    **50m–28 vCPU**; can still burst.
-   **Custom class with `spec.autopilot.enabled` — billing follows the rule:**
    -   **`podFamily` rule → pod-based** (GKE 1.35.2-gke.1485000+). Same
        pay-per-request model as the built-in class, but in a class you author.
    -   **Hardware rule (`machineFamily`, `machineType`, `gpu`) → node-based.**
        You pay for the node because you pinned the shape/accelerator.
-   A custom Autopilot class is therefore **not automatically node-based** —
    it's node-based only when its selected priority requests specific hardware.

## Custom ComputeClass in Autopilot mode (`spec.autopilot`)

Add the **`spec.autopilot.enabled: true`** field to any custom ComputeClass;
Pods that select it then run in Autopilot mode on Google-managed nodes. The
**priority-rule type** sets the billing model (see above):

```yaml
spec:
  autopilot:
    enabled: true
  priorities:
  - podFamily: general-purpose   # pod-based billing (GKE 1.35.2-gke.1485000+)
  - machineFamily: n4            # node-based billing (pinned hardware)
    minCores: 64
```

-   **Reach for a custom class when** you need a specific
    `machineFamily`/`machineType`, **GPU/TPU**, or a Pod the built-in
    `autopilot` class won't take (e.g. **>28 vCPU**) — billing then follows the
    rule type (hardware rule → node-based). For the same managed,
    pay-per-request model in your own class, use a **`podFamily`** rule instead.
-   Combine rules in one `priorities[]` to keep Autopilot management while
    controlling machine selection.

## Caveats (cite when relevant)

-   **Privileged restriction:** Autopilot enforces user-space /
    privileged-admission controls — `privileged`, `hostNetwork`, `hostPID/IPC`,
    `hostPath`, and arbitrary host access are **rejected**. A workload needing
    those **cannot** use Autopilot mode; keep it on a standard (node-based)
    ComputeClass. (See CRITICAL POD-PRIVILEGE RULE in SKILL.md.)
-   **Managed nodes:** no node-pool ops, no manual node config — Google manages
    shapes/sizes, upgrades, security (Shielded VM, etc.).
-   **Pod requests required:** billing and bin-packing are driven by Pod
    *requests* (not limits); unset requests get defaults.
