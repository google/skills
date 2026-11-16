---
name: gke-statefulset-without-probes
metadata:
  version: "1.0.0"
  category: Containers
description: >-
  Audits, detects, and proposes fixes for GKE StatefulSets that are protected
  by a PodDisruptionBudget (PDB) but lack container readiness probes (GKE
  insight subtype PDB_STATEFULSET_WITHOUT_PROBES), causing replacement Pods to
  be counted as healthy before they are ready during voluntary disruptions. Use
  when asked to check, audit, or propose fixes for the
  PDB_STATEFULSET_WITHOUT_PROBES condition, missing readinessProbe
  configurations on PDB-protected GKE StatefulSets, or premature eviction of
  StatefulSet replicas during node pool upgrades or drains despite having a
  PDB. Don't use for StatefulSets missing a PDB (PDB_UNPROTECTED_STATEFULSET),
  PDBs that allow zero disruptions (PDB_UNPERMISSIVE), general probe and PDB
  setup unrelated to this condition (use gke-reliability), Pods stuck in
  Pending (use gke-workload-troubleshooting), ComputeClass configuration (use
  gke-compute-classes), manifest generation (use gke-manifest-generation), or
  cluster upgrade planning (use gke-upgrades).
---

# GKE StatefulSet without readiness probes

Use this skill to find, verify, and propose fixes for `StatefulSet` workloads in
GKE clusters that are configured with a `PodDisruptionBudget` (PDB) but without
container readiness probes (`readinessProbe`), corresponding to the
`PDB_STATEFULSET_WITHOUT_PROBES` insight subtype.

As explained in the section
[When GKE identifies workloads with vulnerability to disruption](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt),
PDBs respect readiness probes when they look at which Pods can be counted as
healthy. Therefore, if a Pod covered by a PDB does not have a readiness probe
configured, the PDB has limited visibility into whether the Pod is healthy or is
just up and running. A Pod is considered healthy by a PDB when its `Ready`
condition is `True` (see the section
[Healthiness of a Pod](https://kubernetes.io/docs/tasks/run-application/configure-pdb/)),
and a container without a readiness probe defaults to a `Success` readiness
state once started (see the section
[Probe results](https://kubernetes.io/docs/concepts/workloads/pods/probes/)).

> **Read-only rule**: Run read-only diagnostic commands only. Never drain,
> delete, or re-create nodes, never dismiss a recommendation, and never run any
> other command that changes the cluster. Give the user any fix to apply
> themselves.

When guiding the user or recommending a check or fix, always include the exact
linked section names and URLs from this skill in your response (do not search
local repository files to copy commands).

## Usage attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you MUST
read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Prerequisites

-   **Google Cloud SDK and tools**:
    -   To install and initialize `gcloud` (project selection and
        authentication) and enable the Kubernetes Engine API
        (`container.googleapis.com`), follow the instructions in the section
        [Before you begin](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/optimize-with-recommenders.md.txt).
        Also ensure that the Recommender API (`recommender.googleapis.com`) is
        enabled to view insights and recommendations.
    -   To install `kubectl` and configure cluster credentials, follow the
        "Install kubectl", "Install required plugins", and "Store cluster
        information for kubectl" sections of
        [Install kubectl and configure cluster access](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cluster-access-for-kubectl.md.txt).
-   **Billing**: Verify that the Google Cloud project has an active Cloud
    Billing account attached.
-   **IAM roles**:
    -   `roles/container.viewer` to read cluster details, StatefulSets, PDBs,
        and GKE diagnosis insights and recommendations.
    -   `roles/container.developer` only if the user later applies the fix.
-   **Documentation**:
    -   [Ensure workloads are disruption-ready](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt)
        (Sections: "Identify workloads with vulnerability to disruption", "When
        GKE identifies workloads with vulnerability to disruption", "Implement
        the guidance to improve disruption readiness")
    -   [Optimize your usage of GKE with insights and recommendations](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/optimize-with-recommenders.md.txt)
        (Sections: "Before you begin", "View insights and recommendations")
    -   [Deploying a stateful application](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/stateful-apps.md.txt)
        (Sections: "Inspecting a StatefulSet", "Updating a StatefulSet",
        "Inspecting update rollout", "Update strategies")
    -   [Install kubectl and configure cluster access](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cluster-access-for-kubectl.md.txt)
        (Sections: "Install kubectl", "Install required plugins", "Store cluster
        information for kubectl")
    -   [Manage clusters](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/managing-clusters.md.txt)
        (Sections: "View your clusters")
    -   [Deploy a Redis cluster on GKE](https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/upgrading-stateful-workload.md.txt)
        (Sections: "Create a Redis Cluster on GKE")
    -   [Node upgrade strategies](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/node-pool-upgrade-strategies.md.txt)
        (Sections: "maxSurge: GKE creates a new surge node before removing an
        existing one", "maxUnavailable: GKE makes an existing node unavailable
        to recreate it", "Phase 3: Drain blue pool")
    -   [Autopilot cluster upgrades](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/cluster-upgrades-autopilot.md.txt)
        (Sections: "Automatic node upgrades")
    -   [Troubleshoot cluster upgrades](https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/upgrades.md.txt)
        (Sections: "Troubleshoot node pool upgrades taking longer than usual")
    -   [Environment architecture](https://docs.cloud.google.com/composer/docs/composer-2/environment-architecture.md.txt)
        (Sections: "Environment's cluster")
    -   [Get support](https://docs.cloud.google.com/kubernetes-engine/docs/getting-support.md.txt)
        (Sections: "Before you contact support", "Recommendations for efficient
        support")
    -   [Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
        (Sections: "Define readiness probes", "Define a liveness command")
    -   [Liveness, Readiness, and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/)
        (Sections: "Liveness probe", "Startup probe", "Check mechanisms", "Probe
        results")
    -   [Specifying a Disruption Budget for your Application](https://kubernetes.io/docs/tasks/run-application/configure-pdb/)
        (Sections: "Specifying a PodDisruptionBudget", "Healthiness of a Pod",
        "Check the status of the PDB", "Unhealthy Pod Eviction Policy")

This skill only reads cluster and recommender state and creates no billable
resources, so no teardown is required.

--------------------------------------------------------------------------------

## Diagnostic workflow

> **Scope check**: If the user says that the cluster belongs to a Managed
> Service for Apache Airflow (formerly Cloud Composer) environment, don't
> propose changes to its workloads, because clusters for Managed Airflow and
> workloads deployed into them are managed by Google, and introducing changes in
> the environment's cluster might break the environment (see the section
> [Environment's cluster](https://docs.cloud.google.com/composer/docs/composer-2/environment-architecture.md.txt)).
> If you aren't sure whether the cluster belongs to a Managed Airflow
> environment, ask the user. If the problem is a StatefulSet that has no
> matching PDB at all (`PDB_UNPROTECTED_STATEFULSET`), or an existing PDB is
> impossible to adhere to for maintenance because its `minAvailable` setting is
> not less than the total Pod count or its `maxUnavailable` setting is zero
> (`PDB_UNPERMISSIVE`, or node pool upgrades stall with
> `"Cannot evict pod as it would violate the pod's disruption budget."` as
> described in the section
> [Troubleshoot node pool upgrades taking longer than usual](https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/upgrades.md.txt)),
> stop using this skill and point the user to the `PDB_UNPROTECTED_STATEFULSET`
> or `PDB_UNPERMISSIVE` action in the section
> [When GKE identifies workloads with vulnerability to disruption](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt).
> Note that `disruptionsAllowed: 0` on a PDB can also occur temporarily while a
> replacement Pod is not `Ready` yet (see the "Check the status of the PDB" and
> "Healthiness of a Pod" sections of
> [Specifying a Disruption Budget for your Application](https://kubernetes.io/docs/tasks/run-application/configure-pdb/)).
> If Pods are stuck in `Pending`, use `gke-workload-troubleshooting` instead,
> because PDBs and readiness probes do not control initial Pod scheduling.

> **Inline telemetry**: If the user already provides the `StatefulSet` and
> `PodDisruptionBudget` specifications in the prompt (and the cluster does not
> belong to a Managed Airflow environment), skip Steps 1–2 and evaluate all
> provided workloads directly in Step 3 without running terminal commands or
> searching the workspace.

### Step 1: Identify the cluster

Obtain `{project_id}`, `{cluster_name}`, and `{location}` from the user prompt.
If the cluster is unknown, ask the user, or follow the instructions in the
section
[View your clusters](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/managing-clusters.md.txt)
to list clusters in `{project_id}`. If you aren't sure whether `{cluster_name}`
belongs to a Managed Airflow environment, ask the user (see the Scope check
above and the section
[Environment's cluster](https://docs.cloud.google.com/composer/docs/composer-2/environment-architecture.md.txt)).

### Step 2: Get the insight and inspect live resources

1.  **Get the insight and recommendation**: As documented in the section
    [Identify workloads with vulnerability to disruption](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt),
    disruption readiness insights are viewed using the Google Cloud CLI or the
    Recommender API and are not available in the Google Cloud console. To find
    StatefulSets with this insight in `{project_id}` and `{location}`, follow
    the `gcloud` or API instructions in the section
    [View insights and recommendations](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/optimize-with-recommenders.md.txt),
    filter for the `PDB_STATEFULSET_WITHOUT_PROBES` subtype, and read the
    associated recommendation.
    -   **No insight**: If the insight list is empty, tell the user that no
        StatefulSet has the `PDB_STATEFULSET_WITHOUT_PROBES` insight, and note
        that recommendations are assessed once daily (see the section
        [Implement the guidance to improve disruption readiness](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt)).
        If the user named or pasted a StatefulSet, still check its live state in
        items 2–3 below because a recent change might not have an insight yet.
        If no insight was found and the user reported early replica evictions
        during an upgrade or drain, follow the section "StatefulSet has
        readiness probe" under Remediation.
    -   **Cannot get the insight**: If you cannot retrieve the insight (for
        example, because the Recommender API `recommender.googleapis.com` is not
        enabled or permissions are missing), point the user to the section
        [View insights and recommendations](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/optimize-with-recommenders.md.txt)
        and the Recommender API prerequisite in Prerequisites, and if the user
        named a StatefulSet, continue to items 2–3 below.
2.  **Configure `kubectl` access and check PDBs**: For each StatefulSet that the
    insight flags, and for any StatefulSet that the user names, configure
    `kubectl` to communicate with `{cluster_name}` in `{location}` by following
    the section
    [Store cluster information for kubectl](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cluster-access-for-kubectl.md.txt).
    Then list and inspect the `PodDisruptionBudget` objects in the namespace by
    following the section
    [Check the status of the PDB](https://kubernetes.io/docs/tasks/run-application/configure-pdb/),
    and check their selectors (see the section
    [Specifying a PodDisruptionBudget](https://kubernetes.io/docs/tasks/run-application/configure-pdb/)).
3.  **Inspect `StatefulSet` configurations and probes**: Check the live state of
    each StatefulSet that the insight flags, and of any StatefulSet that the
    user names, by following the section
    [Inspecting a StatefulSet](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/stateful-apps.md.txt).
    Check its Pod selector (`spec.selector.matchLabels`) and whether any
    container in `spec.template.spec.containers` defines `readinessProbe` (and
    whether `livenessProbe` is configured).
4.  **When you cannot run `gcloud` or `kubectl`**: If you can't run `gcloud` or
    `kubectl`, or the user wants to run the checks, don't write custom scripts.
    Point the user to the sections linked in this step, and continue with Step 3
    when the user pastes the output back.

### Step 3: Evaluate PDB coverage and container readiness probes

Evaluate every StatefulSet in scope:

1.  **Check namespace-scoped PDB coverage**:
    -   Check whether a `PodDisruptionBudget` in the same namespace
        (`{namespace}`) selects the StatefulSet's Pods
        (`spec.selector.matchLabels`) by following the selector rules in the
        section
        [Specifying a PodDisruptionBudget](https://kubernetes.io/docs/tasks/run-application/configure-pdb/).
    -   **StatefulSets without a matching PDB**: If no PDB in `{namespace}`
        matches the StatefulSet's Pod selector labels, classify it as
        **`StatefulSet Not Protected by PDB`**. Per the
        `PDB_UNPROTECTED_STATEFULSET` entry in the section
        [When GKE identifies workloads with vulnerability to disruption](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt),
        all Pods in the StatefulSet can be taken down during an event such as a
        node upgrade. List each such StatefulSet in one line and point the user
        to the `PDB_UNPROTECTED_STATEFULSET` action in that section.
2.  **Check container readiness probes**: For each PDB-protected StatefulSet,
    check `spec.template.spec.containers`:
    -   **Missing readiness probe (`0` containers define `readinessProbe`)**: If
        none of the containers in `spec.template.spec.containers` define a
        `readinessProbe`, classify the workload as
        **`StatefulSet Protected by PDB Without Readiness Probe`**. A
        `livenessProbe` or `startupProbe` alone does not satisfy this check,
        which the section
        [When GKE identifies workloads with vulnerability to disruption](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt)
        defines as "without readiness probes": liveness probes determine when to
        restart a container (see the section
        [Liveness probe](https://kubernetes.io/docs/concepts/workloads/pods/probes/)),
        and startup probes are only executed at startup (see the section
        [Startup probe](https://kubernetes.io/docs/concepts/workloads/pods/probes/)).
        By contrast, PDBs count Ready Pods (see the section
        [Healthiness of a Pod](https://kubernetes.io/docs/tasks/run-application/configure-pdb/)),
        and a container with no readiness probe defaults to a `Success`
        readiness state once started (see the section
        [Probe results](https://kubernetes.io/docs/concepts/workloads/pods/probes/)).
    -   **Has readiness probe (`>= 1` container defines `readinessProbe`)**: If
        at least one container in `spec.template.spec.containers` defines a
        `readinessProbe`, classify the workload as
        **`StatefulSet Has Readiness Probe`** and follow the section
        "StatefulSet has readiness probe" under Remediation. If no StatefulSet
        is missing a `readinessProbe` (or no insight was found) and the user
        reported early replica evictions during an upgrade or drain, also follow
        the section "StatefulSet has readiness probe" under Remediation.

### Step 4: Classify each evaluated StatefulSet

Classify evaluated workloads using these categories:

| Classification | Next step |
| :--- | :--- |
| `StatefulSet Protected by PDB Without Readiness Probe` | Add readiness probe |
| `StatefulSet Has Readiness Probe` | Check liveness / drain |
| `StatefulSet Not Protected by PDB` | Point to action |

--------------------------------------------------------------------------------

## Remediation

Propose these changes for the user to review and apply.

### StatefulSet protected by PDB without readiness probe

1.  **Add readiness and liveness probes**: Follow the action in the section
    [When GKE identifies workloads with vulnerability to disruption](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt):
    add readiness probes to Pods in StatefulSets for the covering PDB, and also
    recommend adding liveness probes. Point the user to the "Define readiness
    probes" and "Define a liveness command" sections of
    [Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).
    As an example of a StatefulSet with readiness and liveness probes on GKE,
    point the user to the section
    [Create a Redis Cluster on GKE](https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/upgrading-stateful-workload.md.txt).
2.  **Ask the user which check shows application readiness**: Ask the user which
    check (`httpGet`, `exec`, `grpc`, or `tcpSocket`) indicates that their
    application is ready to serve traffic, rather than picking a probe for them.
    Explain that per the section
    [Check mechanisms](https://kubernetes.io/docs/concepts/workloads/pods/probes/),
    a `tcpSocket` check is considered successful if the port is open, so it can
    succeed before the application finishes initializing.
3.  **Apply and verify the update (user action only)**: Point the user to the
    "Updating a StatefulSet" (to apply the change), "Update strategies", and
    "Inspecting update rollout" (to check the rollout) sections of
    [Deploying a stateful application](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/stateful-apps.md.txt).
    Note that changing the Pod template in a StatefulSet can trigger a rolling
    update of its replicas, depending on the StatefulSet's `updateStrategy`, and
    do not run the commands in those sections yourself because they modify the
    StatefulSet (`kubectl apply`, `kubectl edit`, and `kubectl rollout undo`).
4.  **Resolution delay and dismissing the recommendation**: Tell the user that
    recommendations are assessed once daily, so it may take up to 24 hours for
    the recommendation to resolve after a change is implemented, and that they
    can dismiss the recommendation if they decide not to add a probe (see the
    section
    [Implement the guidance to improve disruption readiness](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt)).
    Never dismiss a recommendation yourself.

### StatefulSet has readiness probe

1.  **Explain the 24-hour resolution delay if the insight is still present**: If
    the StatefulSet already defines a `readinessProbe` (for example, because the
    user recently added one) and the `PDB_STATEFULSET_WITHOUT_PROBES` insight or
    recommendation is still visible, tell the user that recommendations are
    assessed once daily, so it may take up to 24 hours for the recommendation to
    resolve after a change is implemented (see the section
    [Implement the guidance to improve disruption readiness](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt)).
    Never dismiss a recommendation yourself.
2.  **Check liveness probe configuration**: If the StatefulSet already defines a
    `readinessProbe` but has no `livenessProbe`, mention the recommendation in
    the section
    [When GKE identifies workloads with vulnerability to disruption](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt)
    to also add liveness probes (see the section
    [Define a liveness command](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)).
3.  **When replicas were still evicted before replacement Pods were ready**: If
    a `readinessProbe` exists on the StatefulSet (or no missing-probe
    StatefulSet was found) but replicas were still evicted early during an
    upgrade or drain, point the user to these documented causes:
    -   **Surge or blue-green upgrade drain limits**: During surge upgrades on
        Standard node pools, GKE respects PDBs for up to one hour, and after one
        hour any remaining Pods are forcefully evicted so that the upgrade can
        proceed (see the "maxSurge: GKE creates a new surge node before removing
        an existing one" and "maxUnavailable: GKE makes an existing node
        unavailable to recreate it" sections of
        [Node upgrade strategies](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/node-pool-upgrade-strategies.md.txt));
        on Autopilot clusters, `PodDisruptionBudget` is also respected for 1
        hour during node upgrades (see the section
        [Automatic node upgrades](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/cluster-upgrades-autopilot.md.txt)).
        In blue-green upgrades, Pods with PDB violations are deleted when the
        blue pool is deleted (see the section
        [Phase 3: Drain blue pool](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/node-pool-upgrade-strategies.md.txt)).
    -   **PDB `unhealthyPodEvictionPolicy: AlwaysAllow`**: With
        `unhealthyPodEvictionPolicy: AlwaysAllow` on the PDB, running Pods that
        are not healthy yet can be evicted regardless of whether the criteria in
        a PDB are met (see the section
        [Unhealthy Pod Eviction Policy](https://kubernetes.io/docs/tasks/run-application/configure-pdb/)).
    -   **Readiness probe succeeds before the application is ready**: A
        readiness probe that succeeds before initialization completes—such as a
        `tcpSocket` check, which is considered successful as soon as the port is
        open—marks the Pod `Ready` prematurely (see the section
        [Check mechanisms](https://kubernetes.io/docs/concepts/workloads/pods/probes/)).
    -   **Escalate if unexplained**: If none of these sections explains the
        early eviction, direct the user to Cloud Customer Care by following the
        "Before you contact support" and "Recommendations for efficient support"
        sections of
        [Get support](https://docs.cloud.google.com/kubernetes-engine/docs/getting-support.md.txt).

--------------------------------------------------------------------------------

## Output format

Report the audit in this structure. Include all workloads classified as
`StatefulSet Protected by PDB Without Readiness Probe` in the summary table and
per-workload remediation sections. If any evaluated StatefulSet has no matching
PDB (`StatefulSet Not Protected by PDB`), list it in one line and point the user
to the `PDB_UNPROTECTED_STATEFULSET` action in the section
[When GKE identifies workloads with vulnerability to disruption](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt).
Do not include healthy (`StatefulSet Has Readiness Probe`) StatefulSets in the
summary table unless zero unhealthy StatefulSets exist or the user asked about a
specific workload by name.

```markdown
### Executive summary

Found {actionable_count} PDB-protected StatefulSet(s) lacking a container
`readinessProbe` on cluster `{cluster_name}` (`{location}`, Project:
`{project_id}`):

| StatefulSet | Namespace | Covering PDB | Readiness probe |
| :--- | :--- | :--- | :--- |
| `{name}` | `{namespace}` | `{pdb_name}` | Missing (`liveness`: `{status}`) |

### StatefulSet: `{name}` (`{namespace}`)

> **Diagnosis:** StatefulSet Protected by PDB Without Readiness Probe

**Root cause analysis:**

*   **Missing readiness probe on PDB-protected StatefulSet:** StatefulSet
    `{name}` ({replicas} replicas) is covered by PodDisruptionBudget
    `{pdb_name}`, but container `{container_name}` has no `readinessProbe`
    configured. A `livenessProbe` or `startupProbe` alone does not satisfy this
    check: liveness probes determine when to restart a container (see the
    section
    [Liveness probe](https://kubernetes.io/docs/concepts/workloads/pods/probes/)),
    and startup probes are only executed at startup (see the section
    [Startup probe](https://kubernetes.io/docs/concepts/workloads/pods/probes/)).
*   **Limited PDB visibility during disruptions:** PDBs respect readiness
    probes when they look at which Pods can be counted as healthy (`Ready`
    condition `True`; see the section
    [Healthiness of a Pod](https://kubernetes.io/docs/tasks/run-application/configure-pdb/)).
    Because `{name}` has no `readinessProbe`, `{pdb_name}` has limited
    visibility into whether a Pod is healthy or is just up and running (see the
    section
    [When GKE identifies workloads with vulnerability to disruption](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt)).

**Actionable remediation:**

*   Ask which check shows that `{container_name}` in `{name}` is ready to serve
    traffic (noting from the section
    [Check mechanisms](https://kubernetes.io/docs/concepts/workloads/pods/probes/)
    that a `tcpSocket` check succeeds as soon as the port is open), and add a
    `readinessProbe` (and a `livenessProbe` if missing) by following the
    "Define readiness probes" and "Define a liveness command" sections of
    [Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
    (see the section
    [Create a Redis Cluster on GKE](https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/upgrading-stateful-workload.md.txt)
    for an example).
*   To apply the Pod template change (which can trigger a rolling update of the
    StatefulSet's replicas, depending on the StatefulSet's `updateStrategy`),
    follow the "Updating a StatefulSet" and "Update strategies" sections of
    [Deploying a stateful application](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/stateful-apps.md.txt).

### Verification

*   To monitor and verify the StatefulSet rollout after applying the change,
    follow the section
    [Inspecting update rollout](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/stateful-apps.md.txt).
*   Recommendations are assessed once daily, so it may take up to 24 hours for
    the recommendation to resolve after a change is implemented (or you can
    dismiss the recommendation if you decide not to add a probe; see the section
    [Implement the guidance to improve disruption readiness](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt)).

Learn more:
[Ensure workloads are disruption-ready](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness.md.txt)
(Sections: "When GKE identifies workloads with vulnerability to disruption",
"Implement the guidance to improve disruption readiness") and
[Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
(Section: "Define readiness probes").
```
