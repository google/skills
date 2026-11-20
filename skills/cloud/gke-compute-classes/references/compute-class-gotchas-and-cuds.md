<!-- disableFinding(LINK_RELATIVE_G3DOC) -->

# ComputeClass: Gotchas, CUDs & Constraints

## Common Traps

-   **`AnyBestEffort` Reservation:** Consumes On-Demand capacity at the GCE level before evaluating your remaining ComputeClass priorities. Avoid if you want to fall back to Spot or cheaper families; use `AnyThenFail` (GKE 1.36.0-gke.3204000+) or `Specific` affinity.
-   **Reservations are Zonal:** Pin zones via `reservations.specific[].zones`.
    `location.zones` (per-priority or `priorityDefaults.location`) collides with
    `Specific` — omit it; a policy-only `location.locationPolicy: BALANCED` is
    fine.
-   **Disk Generation:**
    -   **Gen 4** (`n4`, `c4`): Requires **Hyperdisk**.
    -   **Gen 2** (`n2`, `c2`): Requires **Persistent Disk**.
    -   *Rule:* For stateful PV workloads, do NOT mix Gen 2 and Gen 4 priorities
        (fallback attach fails -> `ContainerCreating` trap).
    -   *Exception (GKE 1.35.3-gke.1290000+):* back data PVs with the built-in
        `dynamic-rwo` StorageClass (`type: dynamic` +
        `use-allowed-disk-topology: "true"`). The autoscaler reads disk
        requirements and scales up only compatible nodes, so mixing generations
        in `priorities[]` becomes safe. See
        [Asset: dynamic-rwo-storageclass.yaml](../assets/dynamic-rwo-storageclass.yaml).
    -   *Caveat:* `dynamic-rwo` only governs **newly provisioned** PVs. An
        **existing** PV already created as a fixed PD or Hyperdisk does **not**
        retroactively become flexible — migrate its data onto a
        `dynamic-rwo`-backed volume (snapshot/restore or app/DB-level copy;
        PD↔Hyperdisk is not an in-place conversion).
    -   *Reference:*
        [Asset: postgres-primary-compute-class.yaml](../assets/postgres-primary-compute-class.yaml)

## Provisioning Nuance

-   **DWS FlexStart:** Queued (~3 min). If `capacityCheckWaitTimeSeconds` is
    unset, GKE falls back once the initial provisioning attempt fails; set it
    (GKE 1.33.1-gke.1788000+) to keep retrying before falling back.
    `maxRunDurationSeconds` doesn't help obtainability.
-   **ComputeClass ≠ Full Node API:** node pool auto-creation doesn't support
    every `gcloud node-pools create` flag. If missing, use a **Manual Pool**
    bound to the ComputeClass.

## CUDs vs. Reservations

-   **Committed Use Discounts (CUDs):**
    -   **Automatic Consumption:** GKE cluster autoscaler automatically consumes
        CUDs based on the machine family of the node provisioned. If you have an
        `n4` CUD, provisioning an `n4` VM automatically consumes the discount up
        to exhaustion.
    -   **No Configuration Required:** A ComputeClass does **not** need to be
        specifically configured to consume CUDs. Consumption is implicit.
    -   **Flexible CUDs (FlexCUDs):** Portable across most families (C3, N2,
        N4). The discount follows whichever family the ComputeClass provisions
        for the On-Demand floor.
-   **Reservations:**
    -   **Explicit Configuration Required:** Unlike CUDs, capacity reservations
        are **not** automatically consumed. They must be explicitly configured
        and targeted via the Node Pool API (for manual pools) or within the
        ComputeClass `reservations` block (for node pool auto-creation).

## System Configuration Allowlist

GKE allows only specific `sysctls` and `kubeletConfig` fields.

-   **Check CRD:** `kubectl describe crd computeclasses.cloud.google.com` for
    the authoritative allowlist.
-   **Symptoms:** Unsupported keys show up in `status.conditions`.
-   **Version Gating:** Many fields (e.g. `singleProcessOOMKill`) require 1.33+
    or 1.34+.

## Service Mesh / Networking Nuances

-   Nodes provisioned by ComputeClasses (especially via node pool auto-creation)
    must be compatible with existing network policies or service mesh (e.g.,
    Anthos/Istio) sidecar requirements.
-   Ensure any required taints or labels for mesh injection or network traffic
    routing are included in the `nodePoolConfig`. An intentional **dedication**
    taint is valid here; the only redundant one is
    `cloud.google.com/compute-class` — node pool auto-creation applies and
    auto-tolerates it, so don't re-add it. **Manual pools, by contrast, DO
    require it as label + taint to bind to the ComputeClass.** Note: a
    `nodePoolConfig.taints` key cannot contain the reserved `kubernetes.io`
    substring (GKE Warden rejects it).
