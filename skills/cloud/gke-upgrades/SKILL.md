---
name: gke-upgrades
metadata:
  category: Containers
description: >-
  Plans, executes, and validates Google Kubernetes Engine (GKE) cluster upgrades
  and maintenance operations for both Standard and Autopilot clusters. Produces
  upgrade plans, pre/post-upgrade checklists, maintenance runbooks with gcloud
  commands, release channel strategy, and troubleshooting guides. Handles node
  pool upgrade strategies (surge, blue-green), version compatibility, PDB
  management, and workload-specific concerns (stateful, GPU, operators). Use this
  skill whenever the user mentions GKE upgrades, Kubernetes version bumps, node
  pool maintenance, GKE patching, cluster version management, release channel
  selection, maintenance windows, surge upgrades, stuck upgrades, or any GKE
  lifecycle management task — even casual mentions like "we need to upgrade our
  clusters" or "plan our next GKE maintenance" or "our upgrade is stuck." Don't
  use for GKE cluster creation, application onboarding, general networking/routing
  setup, or security policy configurations (use gke-basics or relevant GKE skills
  instead).
---

# GKE Upgrades & Maintenance

Produce clear, actionable documents — upgrade plans, runbooks, or checklists — tailored to the user's environment. Output should be specific to their cluster mode, release channel, version, and workload types rather than generic advice.

Always frame guidance around the auto-upgrade model: auto-upgrade with maintenance windows and exclusions is the preferred control mechanism.

## Context Gathering

Before producing any upgrade artifact, establish:

- **Cluster mode** — Standard or Autopilot? (Autopilot has no node pool management, mandatory resource requests, no SSH)
- **Current and target versions** — Node version skew must be within 2 minor versions of control plane.
- **Release channel** — Rapid, Regular, Stable, or Extended.
- **Environment topology & Rollout Sequencing** — Single vs multi-cluster, dev/staging/prod tiers, and whether Rollout Sequencing is used.
- **Workload sensitivity** — StatefulSets, databases, GPU, long-running batch need special handling.

If the user provides these upfront, skip straight to the deliverable. If they're vague, fill in reasonable defaults and flag assumptions.

## Core Principles

GKE versions follow Kubernetes version terminology: **Major.Minor.Patch** (e.g., 1.30.1-gke.1187000). A **Minor** version bump (e.g., 1.29 → 1.30) introduces new features and APIs. A **Patch** version bump (e.g., 1.30.1 → 1.30.2) introduces security and bug fixes. Ensure the user understands this distinction.

1. **Sequential control plane, skip-level node pools** -- Control plane upgrades are sequential (N → N+1 → N+2). Node pools support skip-level (N+2) upgrades.
2. **Control plane first** -- Control plane must be upgraded before node pools. Nodes can trail by up to 2 minor versions.
3. **Environment progression** -- Always upgrade dev/staging before production. Use **Rollout Sequencing** (preferred) to automate and enforce this progression across environments (e.g., dev → staging → prod), or manually coordinate version progression if Rollout Sequencing is not used.
4. **Workload-aware** -- Upgrade strategy depends on what's running (stateless, stateful, GPU, batch).
5. **Release channels first** -- Always recommend release channels. Note that "No channel" (static versioning) is deprecated and clusters should be migrated to release channels.
6. **Rollback/Downgrade** -- Control Plane patches and Node Pools (minor and patches) can be rolled back (downgraded to a target version). GKE supports a 2-step Control Plane minor upgrade where step 1 is rollbackable. Other Control Plane minor version rollbacks are NOT customer-doable and require GKE Support.
7. **Node pool upgrade ordering** -- When upgrading multiple node pools, always recommend sequential ordering: upgrade non-critical/stateless pools first (acting as a canary) to verify cluster health before upgrading critical stateful (database) or GPU pools.

## Release Channels

| Channel | Best for | SLA |
|---------|----------|-----|
| **Rapid** | Dev/test, early feature access | No upgrade stability SLA |
| **Regular** (default) | Most production | Full SLA |
| **Stable** | Mission-critical, stability-first | Full SLA |
| **Extended** | Compliance, EoS enforcement control | Full SLA |

### Support Lifecycle
Standard GKE versions are supported for 14 months after they become available in the **Regular** channel. This means:

- **Rapid** channel versions may be supported for longer than 14 months (since they enter Rapid before Regular).
- **Stable** channel versions may be supported for less than 14 months (since they enter Stable after Regular).
- **Extended** support extends this period up to 24 months. Note that extra cost applies only during the extended support period (months 15-24).

## Maintenance Windows & Exclusions

Configure maintenance windows to control auto-upgrade timing. GKE also supports node pool level maintenance exclusions (in addition to cluster level) to block upgrades for specific workloads.

**Exclusion types & Limits:**

- **"No upgrades" (Scope: `no_upgrades`)**: Blocks all upgrades (minor, patch, node).
  - **Limit**: Max **90 days** of total exclusion duration in any **rolling 365-day window**.
  - **Chaining constraint**: Because of the rolling 365-day limit, you cannot chain multiple exclusions to cover a continuous period longer than 90 days (e.g., you cannot cover a 100-day freeze using `no_upgrades`).
- **"No minor or node upgrades" (Scope: `no_minor_or_node_upgrades`)**: Blocks minor and node upgrades, but allows control plane patch upgrades (low risk).
  - **Limit**: Up to **180 days per exclusion**. Can be extended (by adding new exclusions) up to the minor version's **End of Support (EoS)**.
- **"No minor upgrades" (Scope: `no_minor_upgrades`)**: Blocks minor upgrades, but allows control plane patches and node upgrades.
  - **Limit**: Up to **180 days per exclusion**. Can be extended up to EoS.

**Important Exclusion Rules (MUST follow when recommending exclusions and MUST include in the final text response):**

1. **Auto-upgrades only**: Maintenance exclusions **only block automatic upgrades**. Manual upgrades initiated by the user will bypass exclusions. You MUST explain this to the user.
2. **Warn against "No channel"**: You MUST explicitly warn that disabling release channels ("No channel" / static versioning) is deprecated and must not be used as a replacement for exclusions.
3. **Compare Scopes**: You MUST explain the difference between 'No upgrades' (limitations, blocks patches) and 'No minor or node upgrades' (allows patches, longer duration). Recommend 'No minor or node upgrades' when the user wants to allow security patches/fixes while blocking minor version jumps.
4. **Handle periods > 90 days**: If the user needs to block upgrades for more than 90 days, you MUST explain that 'No upgrades' is limited to 90 days in a rolling 365-day window (preventing chaining for longer continuous periods) and advise using 'No minor or node upgrades' (which can last up to 180 days per exclusion, extendable until EoS) or persistent exclusions for minor upgrades until End of Support.
5. **Version skew**: Be mindful of version skew (between control plane and node pools) when using exclusions. Ensure skew does not exceed the supported 2 minor versions. Use `--add-maintenance-exclusion-until-end-of-support` for persistent exclusions.
6. **Correct gcloud syntax**: When providing `gcloud` commands for exclusions, you MUST use the separate flag syntax: `--add-maintenance-exclusion-name`, `--add-maintenance-exclusion-start`, `--add-maintenance-exclusion-end` (or `--add-maintenance-exclusion-until-end-of-support`), and `--add-maintenance-exclusion-scope` (do NOT use a single comma-separated `--add-maintenance-exclusion` flag).

## Mandatory Upgrade Overrides

GKE reserves the right to override user-defined maintenance windows and exclusions for mandatory operations. These overrides cannot be disabled or blocked.

**Common Override Scenarios:**

- **Critical Security Patches**: Urgent vulnerability fixes that must be applied immediately to protect infrastructure.
- **End of Support (EoS) / End of Life (EOL) Enforcement**: If a cluster is running an unsupported version, GKE will force upgrade it to a supported version.
- **Expiring Certificates**: If control plane certificates (CAs) are expiring (within 30 days) and rotation is required to prevent cluster unrecoverability.
- **Maintenance Starvation**: GKE requires at least 48 hours of maintenance availability in any rolling 32-day window. If exclusions block too much, GKE may force an upgrade.

**Guidance (MUST follow when overrides are discussed):**

1. **Correlate with Bulletins**: If GKE performs an unexpected upgrade, you MUST explicitly suggest checking GKE Release Notes or Security Bulletins to correlate the event with emergency patches (do not just suggest checking Cloud Audit Logs).
2. **Design for Resilience**: Workloads must be designed to survive unexpected control plane or node rotation. You MUST recommend:
   - Regional clusters (multi-master) to ensure API availability during control plane upgrades.
   - Multi-zone workload deployments.
   - Replicas > 1 for critical deployments.
   - Properly configured Pod Disruption Budgets (PDBs) that are not overly restrictive.

## Upgrade Planning

When asked to plan an upgrade, produce a structured document covering:

- Version compatibility (breaking changes, deprecated APIs) (minor version upgrades only)
- Upgrade path (sequential minor version upgrades) (minor version upgrades only)
- Node pool upgrade strategy (Standard only)
- Workload readiness (PDBs, resource requests)
- Rollback/Contingency procedure (how to revert node pools or coordinate with GKE Support for master rollback)

**Compatibility Search Rule:**

- If compatibility information (e.g., third-party operator compatibility, GPU driver/CUDA compatibility matrix) is not immediately available in the workspace or via a quick web search, **do NOT loop or make multiple search attempts**. Instead, list the compatibility verification as a **critical pre-upgrade action item** for the user in the checklist.

### Node Pool Strategy (Standard Only)

Recommend **Surge upgrade** as the default and most common strategy, with per-pool settings:

- **Stateless**: Higher `maxSurge` (2-3) for speed, `maxUnavailable=0` for safety.
- **Stateful/DB**: `maxSurge=1, maxUnavailable=0` (conservative).
- **GPU (fixed reservation)**: `maxSurge=0, maxUnavailable=1` (no surge capacity).
- **Large (50+ nodes)**: `maxSurge=20, maxUnavailable=0` (max parallelism).

For mission-critical workloads requiring fast rollback or strict validation, recommend **Standard Blue-Green** upgrades. Acknowledge **Autoscaled Blue-Green** as an option for disruption-sensitive workloads, but note it is currently in preview and may have capacity requirements.

**Upgrade Ordering (User-initiated only):** When planning manual upgrades, specify the sequence of node pool upgrades. Recommend upgrading stateless pools first, verifying cluster stability, and then upgrading stateful/GPU pools. For auto-upgrades, GKE automatically manages sequential node pool upgrades.

For standard command sequences and runbook templates, see [`references/runbook-template.md`](references/runbook-template.md).

### Large-Scale AI/ML Clusters (GPU/TPU)

- **No Live Migration**: GPU VMs do not support live migration; GKE upgrades will force pod restarts. You MUST explain this.
- **Fixed Reservations & Quota**: H100/A100 typically use fixed reservations with no spare quota.
  - Recommend **rolling upgrade with zero surge**: `maxSurge=0, maxUnavailable=1`. This releases the reservation of the node being upgraded before provisioning its replacement.
  - You MUST explain that **Blue-Green upgrades are not feasible** because they require double (2x) the GPU resources (both quota and reservations) during the transition.
- **Driver Coupling**: The GPU driver is tightly coupled with the target node OS image version.
  - You MUST explain that node upgrades update the underlying OS image, introducing new Linux Kernels and hardware drivers (NVIDIA).
  - You MUST warn that driver updates can break CUDA compatibility.
  - You MUST recommend comparing OS image, kernel version (`uname -r`), and driver versions between old (working) and new (non-working) nodes to diagnose driver issues.
  - You MUST recommend deploying a test pod (e.g., vector addition) to verify GPU access.
  - You MUST recommend rolling back the node pool to the previous version as a quick mitigation if production is blocked.
  - You MUST advise updating workload dependencies (CUDA version in container images) to match the new driver before attempting the upgrade again.
  - You MUST advise **upgrading and testing CUDA compatibility in a staging environment/cluster** before applying the upgrade to the production GPU node pools.
- **Operational Safety**:
  - You MUST recommend using GKE **maintenance exclusions** to block auto-upgrades during active training campaigns.
  - Prior to manual upgrades, cordon GPU nodes and wait for active training jobs to checkpoint/complete.
- **TPU Considerations**: TPU slices are recreated atomically (not rolling); maintenance on one slice restarts all slices in the environment.

## Checklists

Produce checklists as copyable markdown with checkboxes. See [`references/checklists.md`](references/checklists.md) for the full pre-upgrade and post-upgrade checklist templates. Adapt them to the user's environment.

**Stateful Workloads:** When stateful workloads (databases) are present, always include checks for PV backup completion and verification of PV reclaim policies (e.g., Retain vs Delete) in the pre-upgrade checklist.

**Autopilot Checklists:** For Autopilot clusters, ensure the checklists include:

- Verification of `resources.requests` on all containers (Autopilot requirement).
- You MUST include specific `kubectl` commands for API deprecation checks, specifically: `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated` to check if any active workloads are using deprecated APIs.
- Verifying PDBs to ensure they don't block node drain (even though GKE manages nodes, PDBs are still respected).
- Identifying and deleting "bare pods" (pods not managed by a ReplicaSet/Deployment/StatefulSet) as they won't be rescheduled during node recreation.
- Verification of `terminationGracePeriodSeconds` to ensure pods have enough time to shut down gracefully during node recreation.

## Maintenance runbooks

Produce step-by-step runbooks with actual `gcloud` and `kubectl` commands. See `references/runbook-template.md` for the standard command sequences.

## Maintenance Window Pauses

When diagnosing a \"stuck\" upgrade, consider if it was paused by a maintenance window:

- **Silent Pause Behavior:** If a maintenance window closes before an upgrade (auto or manual) completes, GKE intentionally pauses the rollout to prevent disruption outside allowed times.
- **Mixed-Version State:** The cluster is left in a stable mixed-version state (some nodes upgraded, some not). You MUST explicitly state that this is a supported and safe intended outcome.
- **Resumption:** The upgrade will automatically resume when the next maintenance window opens.
- **Mitigation for immediate completion:** If the user wants to complete the upgrade immediately, you MUST suggest **temporarily widening the maintenance window** to include the current time (e.g., using `gcloud container clusters update ... --maintenance-window-start ... --maintenance-window-duration ...`). Do not suggest re-triggering the manual upgrade or bypassing the window.

## Troubleshooting

When a user reports a stuck or failing upgrade, you MUST systematically analyze and address ALL 5 potential causes in your final response. Do not omit checks even if you suspect one is the primary cause:

1. **PDB blocking drain:** Identify if any PDB has `ALLOWED DISRUPTIONS = 0` using `kubectl get pdb -A`.
2. **Resource constraints:** Check if pods are stuck in `Pending` due to capacity limits.
3. **Bare pods:** Identify pods without owner references that are blocking the drain (recommend deleting them).
4. **Admission webhooks:** Check if Validating/Mutating webhooks are rejecting pod creation on new nodes.
5. **PVC attachment issues:** Check for volume attachment failures (especially zone constraints).

**Stockout / Quota Exhaustion Rule:**

- If the upgrade is stuck due to `ZONE_RESOURCE_POOL_EXHAUSTED` (stockout) or `QUOTA_EXCEEDED` for Compute Engine resources:
  1. Recommend modifying the upgrade strategy to `maxSurge=0` (rolling in-place) to bypass quota limits.
  2. For `QUOTA_EXCEEDED`, suggest requesting a quota increase from Google Cloud.
  3. You MUST suggest **migrating workloads or creating new node pools in a different zone or region** where capacity/quota is available as a mitigation.

Refer to [`references/troubleshooting.md`](references/troubleshooting.md) for the exact diagnostic commands and fix procedures for each step.

## References

- [GKE Release Notes](https://cloud.google.com/kubernetes-engine/docs/release-notes)
- [Upgrading GKE Clusters](https://cloud.google.com/kubernetes-engine/docs/how-to/upgrading-a-cluster)
- [Maintenance Windows & Exclusions](https://cloud.google.com/kubernetes-engine/docs/concepts/maintenance-windows-and-exclusions)
- [Rollout Sequencing Concepts](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/rollout-sequencing/about-rollout-sequencing)
- [Configure Rollout Sequencing](https://cloud.google.com/kubernetes-engine/docs/how-to/rollout-sequencing)
