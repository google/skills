---
name: gke-unprotected-statefulset
metadata:
  version: "1.0.0"
  category: Containers
description: >-
  Audits, detects, and proposes fixes for GKE StatefulSets that lack a matching
  PodDisruptionBudget (PDB) to prevent simultaneous Pod evictions during
  voluntary node drains (GKE insight subtype PDB_UNPROTECTED_STATEFULSET). Use
  when investigating the PDB_UNPROTECTED_STATEFULSET insight, checking whether
  GKE StatefulSets have a matching PDB, or proposing fixes for selector
  mismatches where an existing PDB does not match the StatefulSet's
  .spec.selector. Don't use for existing PDBs that allow zero disruptions or
  block node drains (PDB_UNPERMISSIVE), general probe and PDB setup unrelated
  to this insight (use gke-reliability), upgrade planning (use gke-upgrades),
  Pods stuck in Pending (use gke-workload-troubleshooting), node autoscaling or
  capacity stockouts (use gke-cluster-autoscaler), ComputeClass configuration
  (use gke-compute-classes), or general Kubernetes manifest generation (use
  gke-manifest-generation).
---

# GKE unprotected StatefulSet skill

Use this skill to find, verify, and propose fixes for GKE `StatefulSet`
workloads lacking a matching `PodDisruptionBudget` (PDB), subtype
`PDB_UNPROTECTED_STATEFULSET`. Without a matching PDB, voluntary node drains can
take down all Pods at once or drop a stateful app below quorum; a zero-budget
PDB triggers `PDB_UNPERMISSIVE`, which GKE violates after one hour (see
[When GKE identifies workloads with vulnerability to disruption](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt)
and "Dealing with disruptions" and "Pod disruption budgets" in
[Disruptions](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/)).

> **Read-only rule**: Run read-only diagnostic commands only. Never drain,
> delete, or re-create nodes, create or modify Kubernetes resources, dismiss or
> change insight or recommendation state, or run any other command that changes
> the cluster or project. Give the user any fix to apply themselves.

## Usage attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, read and
follow [Usage Attribution](references/attribution.md).

## Prerequisites

1.  **Google Cloud CLI, APIs, and billing**: If `gcloud` is missing or
    uninitialized or `container.googleapis.com` is disabled, point the user to
    [Before you begin](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/optimize-with-recommenders.md.txt)
    (never enable APIs or install software yourself). If
    `recommender.googleapis.com` is disabled, point the user to "gcloud" in
    [Enable the API](https://docs.cloud.google.com/recommender/docs/enable-api.md.txt).
    The project needs an active Cloud Billing account.
2.  **`kubectl` and cluster credentials**: If `kubectl` or required auth plugins
    are missing, point the user to "Install kubectl" and "Install required
    plugins" in
    [Install kubectl and configure cluster access](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cluster-access-for-kubectl.md.txt),
    and use "Store cluster information for kubectl" on that page to configure
    cluster credentials for `kubectl`.
3.  **IAM roles**: Under
    [Google Kubernetes Engine roles](https://docs.cloud.google.com/iam/docs/roles-permissions/container.md.txt)
    and
    [Required roles](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/optimize-with-recommenders.md.txt):
    *   Kubernetes Engine Viewer (`roles/container.viewer`) to configure
        credentials and read clusters, StatefulSets, PDBs, insights, and
        recommendations.
    *   Kubernetes Engine Developer (`roles/container.developer`) only for the
        user to create/update PDBs, update/scale StatefulSets, or dismiss
        recommendations.
    *   Kubernetes Engine Cluster Admin (`roles/container.clusterAdmin`) only
        for the user to configure cluster maintenance windows/exclusions or
        Standard node-pool maintenance exclusions.
4.  **Documentation**:
    *   [Ensure workloads are disruption-ready](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt)
        (Sections: "Identify workloads with vulnerability to disruption", "When
        GKE identifies workloads with vulnerability to disruption", "Implement
        the guidance to improve disruption readiness")
    *   [Optimize your usage of GKE with insights and recommendations](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/optimize-with-recommenders.md.txt)
        (Sections: "Before you begin", "Required roles", "View insights and
        recommendations", "Dismiss or restore recommendations", "Dismiss
        recommendations using the Google Cloud CLI")
    *   [Enable the API](https://docs.cloud.google.com/recommender/docs/enable-api.md.txt)
        (Sections: "gcloud")
    *   [Insights](https://docs.cloud.google.com/recommender/docs/insights/using-insights.md.txt)
        (Sections: "Description", "Content", "Target Resources", "State Info",
        "Severity", "Last Refresh Time")
    *   [Google Kubernetes Engine roles and permissions](https://docs.cloud.google.com/iam/docs/roles-permissions/container.md.txt)
        (Sections: "Google Kubernetes Engine roles")
    *   [Install kubectl and configure cluster access](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cluster-access-for-kubectl.md.txt)
        (Sections: "Install kubectl", "Install required plugins", "Store cluster
        information for kubectl")
    *   [Manage clusters](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/managing-clusters.md.txt)
        (Sections: "View your clusters")
    *   [Deploying a stateful application](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/stateful-apps.md.txt)
        (Sections: "Creating a StatefulSet", "Inspecting a StatefulSet",
        "Updating a StatefulSet", "Scaling a StatefulSet")
    *   [Node upgrade strategies](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/node-pool-upgrade-strategies.md.txt)
        (Sections: "maxSurge: GKE creates a new surge node before removing an
        existing one", "maxUnavailable: GKE makes an existing node unavailable
        to recreate it", "Phase 3: Drain blue pool", "Phase 5: Delete blue
        pool")
    *   [Autopilot cluster upgrades](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/cluster-upgrades-autopilot.md.txt)
        (Sections: "Automatic node upgrades")
    *   [Troubleshoot cluster upgrades](https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/upgrades.md.txt)
        (Sections: "Troubleshoot node pool upgrades taking longer than usual")
    *   [Maintenance windows and exclusions](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/maintenance-windows-and-exclusions.md.txt)
        (Sections: "Automatic maintenance that doesn't respect GKE maintenance
        policies", "Maintenance windows", "Maintenance exclusions", "Node pool
        maintenance exclusions", "Limitations on configuring maintenance
        exclusions", "Example: Company's legacy database not resilient to node
        pool upgrades")
    *   [Configure maintenance windows and exclusions](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/maintenance-windows-and-exclusions.md.txt)
        (Sections: "Configure a maintenance window", "Configure a maintenance
        exclusion")
    *   [Environment architecture](https://docs.cloud.google.com/composer/docs/composer-2/environment-architecture.md.txt)
        (Sections: "Environment's cluster")
    *   [Get support](https://docs.cloud.google.com/kubernetes-engine/docs/getting-support.md.txt)
        (Sections: "Before you contact support", "Recommendations for efficient
        support")
    *   [Disruptions](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/)
        (Sections: "Voluntary and involuntary disruptions", "Dealing with
        disruptions", "Pod disruption budgets")
    *   [Specifying a Disruption Budget for your Application](https://kubernetes.io/docs/tasks/run-application/configure-pdb/)
        (Sections: "Identify an Application to Protect", "Think about how your
        application reacts to disruptions", "Rounding logic when specifying
        percentages", "Specifying a PodDisruptionBudget", "Create the PDB
        object", "Check the status of the PDB", "Healthiness of a Pod",
        "Unhealthy Pod Eviction Policy", "Arbitrary workloads and arbitrary
        selectors")
    *   [Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
        (Sections: "Define readiness probes")

This skill creates no billable resources, so no teardown is required.

## Diagnostic workflow

> **Scope and Managed Airflow check**:
> *   **Managed Service for Apache Airflow (formerly Cloud Composer)**: Under
>     [Environment's cluster](https://docs.cloud.google.com/composer/docs/composer-2/environment-architecture.md.txt),
>     clusters for Managed Airflow and workloads deployed into them are managed
>     by Google: do not introduce changes in the environment's cluster (doing so
>     might break the environment). When the user says the cluster belongs to a
>     Managed Airflow (or Cloud Composer) environment, do not propose workload
>     or PDB changes; ask when that isn't clear.
> *   **Unpermissive PDBs (`PDB_UNPERMISSIVE`)**: For requests solely about
>     `PDB_UNPERMISSIVE` or drains blocked by
>     `"Cannot evict pod as it would violate the pod's disruption budget."` on a
>     matching PDB, stop and point the user to
>     [When GKE identifies workloads with vulnerability to disruption](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt)
>     and
>     [Troubleshoot node pool upgrades taking longer than usual](https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/upgrades.md.txt)
>     to adjust `minAvailable` or `maxUnavailable` themselves. In an audit,
>     handle matching unpermissive PDBs via "When a matching PDB already
>     exists".
> *   **Other GKE topics**: Hand off general probe/PDB setup to
>     `gke-reliability`, upgrade planning to `gke-upgrades`, `Pending` Pods to
>     `gke-workload-troubleshooting`, autoscaling/stockouts to
>     `gke-cluster-autoscaler`, ComputeClasses to `gke-compute-classes`, and
>     general manifest generation to `gke-manifest-generation`.
> *   **Provided manifests, insights, or `kubectl` output**: After the Managed
>     Airflow check, if insight/recommendation details, manifests, or `kubectl`
>     output are provided, capture any `{project_id}`, `{cluster_name}`, and
>     `{location}`, skip Steps 1–2 (honoring dismissed recommendations per Step
>     2), and evaluate every workload in Step 3 without discovery commands.

### Step 1: Identify the target cluster

Obtain `{project_id}`, `{cluster_name}`, and `{location}` (control plane region
or zone) from the prompt. If `{project_id}` is unknown, ask the user; if
`{cluster_name}` or `{location}` is unknown, ask the user or follow
[View your clusters](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/managing-clusters.md.txt)
for `{project_id}`. Ask when it isn't clear whether `{cluster_name}` belongs to
a Managed Airflow environment.

### Step 2: Check for `PDB_UNPROTECTED_STATEFULSET` insights and recommendations

1.  **Query insights**: Under
    [Identify workloads with vulnerability to disruption](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt),
    disruption-readiness insights are available only via `gcloud` or the
    Recommender API (not the Google Cloud console). Follow `gcloud` or API
    instructions in
    [View insights and recommendations](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/optimize-with-recommenders.md.txt)
    for `{project_id}` and `{location}`, filtering for
    `PDB_UNPROTECTED_STATEFULSET`.
2.  **Filter active insights and check recommendation state**: Keep `ACTIVE`
    insights matching `{cluster_name}` via "State Info" and "Target Resources",
    record "Severity" and "Last Refresh Time", and read `{statefulset_name}`
    (`{namespace}` if shown), suggested selector labels ("Description" and
    "Content"), and `associatedRecommendations.recommendation` via
    [Insights](https://docs.cloud.google.com/recommender/docs/insights/using-insights.md.txt),
    "View insights and recommendations" and "Dismiss recommendations using the
    Google Cloud CLI" in
    [Optimize your usage of GKE with insights and recommendations](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/optimize-with-recommenders.md.txt),
    and "When GKE identifies workloads with vulnerability to disruption" and
    "Implement the guidance to improve disruption readiness" in
    [Ensure workloads are disruption-ready](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt).
    Check the recommendation's state using only the read-only list (`ACTIVE`
    filter hides dismissed recommendations) or describe step in "Dismiss
    recommendations using the Google Cloud CLI"—never run `mark-dismissed`. If
    `{namespace}` or `{statefulset_name}` is unknown, ask or point to
    [Inspecting a StatefulSet](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/stateful-apps.md.txt).
3.  **Branch on results** (include the `.md.txt` links from items 1–2 when
    pointing the user to those sections):
    *   **Active insights**: For each active insight, if its associated
        recommendation was dismissed, report that the user dismissed it instead
        of recommending a PDB again (dismissing only hides it in the console
        while it remains discoverable via `gcloud` and the Recommender API; see
        [Dismiss or restore recommendations](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/optimize-with-recommenders.md.txt)).
        Otherwise continue to Step 3 for `{statefulset_name}` in `{namespace}`.
    *   **No active insight for `{cluster_name}`**: Recommendations are assessed
        once daily ("Implement the guidance to improve disruption readiness" in
        item 2), so recent changes may not appear yet. Proceed to Step 3 if
        `{statefulset_name}` and `{namespace}` were given; otherwise report none
        was found and ask for them (or point to "Inspecting a StatefulSet" in
        item 2).
    *   **API disabled or unreachable**: If `recommender.googleapis.com` is
        disabled, point to "gcloud" in
        [Enable the API](https://docs.cloud.google.com/recommender/docs/enable-api.md.txt)
        (and continue to Step 3 if `{statefulset_name}` and `{namespace}` are
        known). If unreachable, point to "View insights and recommendations"
        (item 1), "Inspecting a StatefulSet" (item 2), and
        [Check the status of the PDB](https://kubernetes.io/docs/tasks/run-application/configure-pdb/),
        continuing with Step 3 once output is shared.

### Step 3: Inspect the StatefulSet selector and existing PDBs

Configure `kubectl` credentials for `{cluster_name}` in `{location}` via
[Store cluster information for kubectl](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cluster-access-for-kubectl.md.txt),
and evaluate every StatefulSet in scope (never stop after the first):

1.  **Inspect the StatefulSet**: Follow "Inspecting a StatefulSet" (and see
    "Creating a StatefulSet" for `spec.template.metadata.labels`) in
    [Deploying a stateful application](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/stateful-apps.md.txt)
    for `{statefulset_name}` in `{namespace}` to read `{replicas}`
    (`spec.replicas`), `{statefulset_selector}` (`.spec.selector`), and
    `spec.template.metadata.labels`, plus container `readinessProbe` (see
    [Define readiness probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)).
    Per
    [Identify an Application to Protect](https://kubernetes.io/docs/tasks/run-application/configure-pdb/),
    `.spec.selector` goes into a matching PDB's `.spec.selector`. If
    `{statefulset_name}` is not found, ask whether it was deleted:
    *   If the user confirms it was deleted, tell them no PDB is needed and the
        recommendation can take up to 24 hours to resolve (see
        [Implement the guidance to improve disruption readiness](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt)).
    *   Otherwise, re-check `{namespace}` and any Step 2 insight's
        [Target Resources](https://docs.cloud.google.com/recommender/docs/insights/using-insights.md.txt)
        (it might target another cluster); if still not found, direct the user
        to Cloud Customer Care ("Before you contact support" and
        "Recommendations for efficient support" in
        [Get support](https://docs.cloud.google.com/kubernetes-engine/docs/getting-support.md.txt)).
2.  **Inspect PDBs and selector overlap in `{namespace}`**: Follow "Check the
    status of the PDB", "Specifying a PodDisruptionBudget", "Identify an
    Application to Protect", and "Arbitrary workloads and arbitrary selectors"
    in
    [Specifying a Disruption Budget for your Application](https://kubernetes.io/docs/tasks/run-application/configure-pdb/)
    to read each PDB's `.spec.selector` (`{}` matches every Pod in
    `{namespace}`), `minAvailable`, `maxUnavailable`, `status.expectedPods`, and
    `status.disruptionsAllowed`. `PDB_UNPROTECTED_STATEFULSET` alerts when no
    existing PDB labels match `{statefulset_selector}` (see
    [When GKE identifies workloads with vulnerability to disruption](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt)).
    Count only a PDB whose `.spec.selector` equals `{statefulset_selector}` as a
    match; record any matching `{existing_pdb_name}`, and record any
    `{existing_pdb_name}` selecting the Pods without matching (`{}`, subset
    labels, extra `spec.template.metadata.labels`, or a Pod subset), noting
    whether it also selects other workloads' Pods.

### Step 4: Classify each evaluated StatefulSet from live state

Classify each workload into one category from Step 3, reporting any Step 2
[Severity](https://docs.cloud.google.com/recommender/docs/insights/using-insights.md.txt):

1.  **`StatefulSet Protected`**: `{existing_pdb_name}` in `{namespace}` equals
    `{statefulset_selector}` (any `{replicas}`). Record
    `{other_statefulset_name}` and `{other_statefulset_summary}` via "When a
    matching PDB already exists".
2.  **`Single-Replica or Scaled-to-Zero StatefulSet`**: `{replicas} <= 1` and no
    PDB in `{namespace}` equals `{statefulset_selector}`. Record
    `{other_statefulset_name}` and `{other_statefulset_summary}` via
    "Single-replica and scaled-to-zero StatefulSets".
3.  **`Unprotected StatefulSet`**: `{replicas} > 1` and no PDB in `{namespace}`
    equals `{statefulset_selector}`. Record missing-PDB or `{existing_pdb_name}`
    mismatch details in `{classification_summary}`; follow "Unprotected
    StatefulSet (add or update a PDB)".

Count the `Unprotected StatefulSet` workloads as `{count}`.

## Remediation

Give the user fixes to apply themselves (never modify resources or state).

### Unprotected StatefulSet (add or update a PDB)

1.  **Specify `.spec.selector` and disruption budget**: Point to "When GKE
    identifies workloads with vulnerability to disruption" and "Implement the
    guidance to improve disruption readiness" in
    [Ensure workloads are disruption-ready](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt),
    [Pod disruption budgets](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/),
    and "Identify an Application to Protect", "Think about how your application
    reacts to disruptions", "Rounding logic when specifying percentages", and
    "Specifying a PodDisruptionBudget" in
    [Specifying a Disruption Budget for your Application](https://kubernetes.io/docs/tasks/run-application/configure-pdb/):
    *   **Selector**: Copy `{statefulset_selector}` (`.spec.selector`, matching
        Step 2's recommendation when current) into the PDB's `.spec.selector`,
        without adding Pod-template-only `spec.template.metadata.labels` (see
        [Creating a StatefulSet](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/stateful-apps.md.txt)).
    *   **Budget**: Set only one of `maxUnavailable` (`1` adapts to scale;
        requires one shared controller) or `minAvailable` (quorum, such as `2`
        of `3` or `3` of `5`). Never set `maxUnavailable` to `0`/`0%` or
        `minAvailable` to `100%` or an integer/rounded-up percentage not less
        than `{replicas}` (`PDB_UNPERMISSIVE`, causing 1-hour drain waits).
2.  **Create vs. update overlapping `{existing_pdb_name}`**: Under "Identify an
    Application to Protect", "Specifying a PodDisruptionBudget", "Create the PDB
    object", and "Arbitrary workloads and arbitrary selectors" in
    [Specifying a Disruption Budget for your Application](https://kubernetes.io/docs/tasks/run-application/configure-pdb/)
    (eviction is disallowed for any Pod covered by multiple PDBs):
    *   **No PDB selects the Pods**: Point to "Create the PDB object" to add it.
    *   **`{existing_pdb_name}` selects only this StatefulSet's Pods** (empty
        `{}`, subset labels, extra `spec.template.metadata.labels`, or a Pod
        subset): Advise **not** creating a second PDB; point to "Create the PDB
        object" to update `{existing_pdb_name}` in place to
        `{statefulset_selector}`.
    *   **`{existing_pdb_name}` also selects other workloads' Pods** (empty
        `{}`, shared subset labels, or a shared Pod-template label): Warn that
        `maxUnavailable` requires all selected Pods to share one controller
        (bare or unsupported-controller Pods allow only integer `minAvailable`),
        the budget is shared across all selected Pods rather than per-workload
        quorum, and adding a second PDB blocks eviction while narrowing
        `{existing_pdb_name}` alone drops coverage from the other workloads;
        point to those sections to give each controller a non-overlapping PDB
        matching `.spec.selector`.
3.  **Readiness probes (`PDB_STATEFULSET_WITHOUT_PROBES`)**: PDBs respect
    readiness probes when they look at which Pods can be counted as healthy, and
    a Pod counts as healthy when it has a `.status.conditions` item with
    `type="Ready"` and `status="True"`. If missing, point to
    [Healthiness of a Pod](https://kubernetes.io/docs/tasks/run-application/configure-pdb/),
    [When GKE identifies workloads with vulnerability to disruption](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt),
    [Define readiness probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/),
    and
    [Updating a StatefulSet](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/stateful-apps.md.txt).
4.  **Resolution window and dismissal**: Recommendations are assessed once daily
    and take up to 24 hours to resolve after changes (see
    [Implement the guidance to improve disruption readiness](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt)).
    Only if the user decides not to add a PDB, point to "Dismiss or restore
    recommendations" and "Dismiss recommendations using the Google Cloud CLI" in
    [Optimize your usage of GKE with insights and recommendations](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/optimize-with-recommenders.md.txt):
    dismissing only hides a recommendation for all users in the console (where
    it doesn't appear again even if GKE detects the same behavior), while it
    remains discoverable via the Google Cloud CLI and Recommender API.

### Single-replica and scaled-to-zero StatefulSets

1.  **If `{replicas} == 0`**: Ask whether it stays at `0` or scales up (under
    [Check the status of the PDB](https://kubernetes.io/docs/tasks/run-application/configure-pdb/),
    zero matching Pods shows `ALLOWED DISRUPTIONS: 0`). If kept at `0`, no Pods
    run to disrupt (for dismissal, see item 4 of "Unprotected StatefulSet (add
    or update a PDB)" above); if scaling to `1`, follow items 2–3; if scaling
    above `1` (see
    [Scaling a StatefulSet](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/stateful-apps.md.txt)),
    follow "Unprotected StatefulSet (add or update a PDB)" for that target.
2.  **Explain 1-replica PDB trade-offs**: PDBs target replicated apps ("Dealing
    with disruptions" and "Pod disruption budgets" in
    [Disruptions](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/)).
    Under "Think about how your application reacts to disruptions" and
    "Specifying a PodDisruptionBudget" (`Example 4`) in
    [Specifying a Disruption Budget for your Application](https://kubernetes.io/docs/tasks/run-application/configure-pdb/),
    `maxUnavailable: 1` or a positive percentage still allows evicting the lone
    Pod (`100%` unavailability), while `maxUnavailable` of `0`/`0%` or
    `minAvailable` of `1`/`100%` triggers `PDB_UNPERMISSIVE` and a 1-hour drain
    wait on Standard surge and Autopilot upgrades (see item 3 of "When a
    matching PDB already exists" below). If a non-matching `{existing_pdb_name}`
    selects the Pod, handle overlap per item 2 of "Unprotected StatefulSet (add
    or update a PDB)".
3.  **Documented single-instance options**: Point the user to:
    *   Omit a PDB and tolerate brief drain downtime (see
        [Think about how your application reacts to disruptions](https://kubernetes.io/docs/tasks/run-application/configure-pdb/)).
        If an active recommendation exists and the user decides against a PDB,
        share item 4 of "Unprotected StatefulSet (add or update a PDB)" above.
    *   Scale above `1` replica before adding a PDB via
        [Scaling a StatefulSet](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/stateful-apps.md.txt).
    *   Control maintenance timing via a cluster maintenance window/exclusion or
        (Standard only) a node-pool maintenance exclusion—noting maintenance
        policies don't block all automatic maintenance and on Autopilot GKE
        honors the configuration if possible; see "Automatic maintenance that
        doesn't respect GKE maintenance policies", "Maintenance windows",
        "Maintenance exclusions", "Node pool maintenance exclusions",
        "Limitations on configuring maintenance exclusions", and "Example:
        Company's legacy database not resilient to node pool upgrades" in
        [Maintenance windows and exclusions](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/maintenance-windows-and-exclusions.md.txt),
        [Automatic node upgrades](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/cluster-upgrades-autopilot.md.txt),
        and "Configure a maintenance window" and "Configure a maintenance
        exclusion" in
        [Configure maintenance windows and exclusions](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/maintenance-windows-and-exclusions.md.txt).

### When a matching PDB already exists

*   **Stale active insight**: If an active `PDB_UNPROTECTED_STATEFULSET` insight
    still appears for `{other_statefulset_name}`, ask when `{existing_pdb_name}`
    was created or updated and check "Target Resources" and "Last Refresh Time"
    in
    [Insights](https://docs.cloud.google.com/recommender/docs/insights/using-insights.md.txt).
    If "Last Refresh Time" is earlier than the PDB change, explain the daily
    24-hour assessment window (see
    [Implement the guidance to improve disruption readiness](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt))
    and advise **not** dismissing just to clear normal lag: under
    [Dismiss or restore recommendations](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/optimize-with-recommenders.md.txt),
    dismissing only hides a recommendation for all users in the console (where
    it doesn't appear again even if GKE detects the same behavior), while it
    remains discoverable via `gcloud` and the Recommender API. If "Last Refresh
    Time" is later than the PDB change and the insight is still active, direct
    the user to Cloud Customer Care via "Before you contact support" and
    "Recommendations for efficient support" in
    [Get support](https://docs.cloud.google.com/kubernetes-engine/docs/getting-support.md.txt).
*   **Single or zero replicas**: If `{replicas} <= 1`, on `1` replica even a
    permissive PDB allows `100%` unavailability (`0` matches zero Pods); follow
    "Single-replica and scaled-to-zero StatefulSets".

Check—or point the user to check:

1.  **Permissiveness (`PDB_UNPERMISSIVE`)**: Verify via "Check the status of the
    PDB", "Rounding logic when specifying percentages", and "Specifying a
    PodDisruptionBudget" in
    [Specifying a Disruption Budget for your Application](https://kubernetes.io/docs/tasks/run-application/configure-pdb/)
    that when `{replicas} > 0` and Pods are healthy, `ALLOWED DISRUPTIONS`
    (`status.disruptionsAllowed`) is non-zero (`minAvailable`, rounded up for
    percentages, is less than `{replicas}`, or `maxUnavailable > 0`); otherwise
    point to
    [When GKE identifies workloads with vulnerability to disruption](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt)
    and
    [Troubleshoot node pool upgrades taking longer than usual](https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/upgrades.md.txt).
2.  **Readiness probes (`PDB_STATEFULSET_WITHOUT_PROBES`)**: Check container
    `readinessProbe`; if missing, point to item 3 of "Unprotected StatefulSet
    (add or update a PDB)" above.
3.  **Disruption despite both**: Point the user to:
    *   **One-hour surge PDB timeout** ("maxSurge: GKE creates a new surge node
        before removing an existing one" and "maxUnavailable: GKE makes an
        existing node unavailable to recreate it") and **Standard blue-green
        pool deletion** bypassing PDBs ("Phase 3: Drain blue pool" and "Phase 5:
        Delete blue pool") in
        [Node upgrade strategies](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/node-pool-upgrade-strategies.md.txt),
        plus the 1-hour PDB limit in
        [Automatic node upgrades](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/cluster-upgrades-autopilot.md.txt)
        and
        [When GKE identifies workloads with vulnerability to disruption](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt).
    *   **`unhealthyPodEvictionPolicy: AlwaysAllow`** evicting running non-Ready
        Pods regardless of budget (see
        [Unhealthy Pod Eviction Policy](https://kubernetes.io/docs/tasks/run-application/configure-pdb/)).
    *   **Involuntary disruptions or direct deletions** bypassing PDBs
        ("Voluntary and involuntary disruptions" and "Pod disruption budgets" in
        [Disruptions](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/)).
    *   **Escalation**: Direct the user to Cloud Customer Care via "Before you
        contact support" and "Recommendations for efficient support" in
        [Get support](https://docs.cloud.google.com/kubernetes-engine/docs/getting-support.md.txt).

## Output format

Cite relied-on doc sections by exact title and link. Omit unprovided
`{cluster_name}`, `{location}`, or `{project_id}`; omit `Unprotected
StatefulSets detected` and `Recommended remediation` when `{count}` is `0`; omit
`Other evaluated StatefulSets` when none apply (`{other_statefulset_summary}`
covers single-replica/scaled-to-zero options or `{existing_pdb_name}`
permissiveness, readiness-probe, and 24-hour lag notes); and report Step 2's
[Severity](https://docs.cloud.google.com/recommender/docs/insights/using-insights.md.txt)
when retrieved.

```markdown
### Unprotected StatefulSets detected

Found {count} `StatefulSet` workload(s) without a matching
`PodDisruptionBudget` on cluster `{cluster_name}` (`{location}`, Project:
`{project_id}`):

| StatefulSet | Namespace | Replicas | Classification & details |
| :--- | :--- | :---: | :--- |
| `{statefulset_name}` | `{namespace}` | {replicas} | {classification_summary} |

### Other evaluated StatefulSets

*   `{other_statefulset_name}` (`{namespace}`, `replicas: {replicas}`):
    {other_statefulset_summary}

### Recommended remediation

*   For `{statefulset_name}` (`{namespace}`): follow "Identify an Application
    to Protect", "Specifying a PodDisruptionBudget", "Create the PDB object",
    and "Arbitrary workloads and arbitrary selectors" in
    [Specifying a Disruption Budget for your Application](https://kubernetes.io/docs/tasks/run-application/configure-pdb/)
    to create a `PodDisruptionBudget` copying `{statefulset_selector}` with an
    appropriate budget, or update `{existing_pdb_name}` without overlapping
    PDBs.

### Verification

*   Follow
    [Check the status of the PDB](https://kubernetes.io/docs/tasks/run-application/configure-pdb/)
    to verify `ALLOWED DISRUPTIONS` (`status.disruptionsAllowed`) is non-zero
    and `status.expectedPods` matches `{replicas}`.
*   Recommendations are assessed once daily and take up to 24 hours to resolve
    (see
    [Implement the guidance to improve disruption readiness](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt)).
```
