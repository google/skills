---
name: gke-upgrades
description: >
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
  clusters" or "plan our next GKE maintenance" or "our upgrade is stuck."
---

# GKE Upgrades & Maintenance

Produce clear, actionable documents — upgrade plans, runbooks, or checklists — tailored to the user's environment. Output should be specific to their cluster mode, release channel, version, and workload types rather than generic advice.

Always frame guidance around the auto-upgrade model: auto-upgrade with maintenance windows and exclusions is the preferred control mechanism. Manual upgrades are for exceptions.

## Context Gathering

Before producing any upgrade artifact, establish:
- **Cluster mode** — Standard or Autopilot? (Autopilot has no node pool management, mandatory resource requests, no SSH)
- **Current and target versions** — Node version skew must be within 2 minor versions of control plane.
- **Release channel** — Rapid, Regular, Stable, or Extended.
- **Environment topology** — Single vs multi-cluster, dev/staging/prod tiers.
- **Workload sensitivity** — StatefulSets, databases, GPU, long-running batch need special handling.

If the user provides these upfront, skip straight to the deliverable. If they're vague, fill in reasonable defaults and flag assumptions.

## Core Principles

1. **Sequential control plane, skip-level node pools** -- Control plane upgrades are sequential (N → N+1 → N+2). Node pools support skip-level (N+2) upgrades. GKE supports a 2-step CP minor upgrade where step 1 is rollbackable.
2. **Control plane first** -- Control plane must be upgraded before node pools. Nodes can trail by up to 2 minor versions.
3. **Environment progression** -- Always upgrade dev/staging before production. Use release channels to enforce this: Rapid → Regular → Stable.
4. **Workload-aware** -- Upgrade strategy depends on what's running (stateless, stateful, GPU, batch).
5. **Release channels first** -- Always recommend release channels with maintenance exclusions. Never recommend "No channel" as a first option.
6. **Rollback** -- CP patch downgrades are customer-doable. CP minor downgrades require GKE support. Node pools can be re-created at a different version.

## Release Channels

| Channel | Best for | SLA | Support |
|---------|----------|-----|---------|
| **Rapid** | Dev/test, early feature access | No upgrade stability SLA | 14 months |
| **Regular** (default) | Most production | Full SLA | 14 months |
| **Stable** | Mission-critical, stability-first | Full SLA | 14 months |
| **Extended** | Compliance, EoS enforcement control | Full SLA | Up to 24 months (extra cost) |

Common multi-environment strategy: Dev→Rapid, Staging→Regular, Prod→Stable or Regular.

## Maintenance Windows & Exclusions

Configure maintenance windows to control auto-upgrade timing.

**Exclusion types:**
- **"No upgrades"**: Blocks everything for up to 30 days (BFCM, freezes).
- **"No minor or node upgrades"**: Blocks minor and node upgrades, allows CP patches. Up to EoS.
- **"No minor upgrades"**: Blocks minor upgrades, allows patches and node upgrades. Up to EoS.

Recommend cluster-level exclusions to prevent skew. Use `--add-maintenance-exclusion-until-end-of-support` for persistent exclusions.

## Upgrade Planning

When asked to plan an upgrade, produce a structured document covering:
- Version compatibility (breaking changes, deprecated APIs)
- Upgrade path (sequential minor version upgrades)
- Node pool upgrade strategy (Standard only)
- Workload readiness (PDBs, resource requests)

### Node Pool Strategy (Standard Only)

Recommend surge upgrade as the default, with per-pool settings:
- **Stateless**: Higher `maxSurge` (2-3) for speed, `maxUnavailable=0` for safety.
- **Stateful/DB**: `maxSurge=1, maxUnavailable=0` (conservative).
- **GPU (fixed reservation)**: `maxSurge=0, maxUnavailable=1` (no surge capacity).
- **Large (50+ nodes)**: `maxSurge=20, maxUnavailable=0` (max parallelism).

Recommend blue-green upgrade for mission-critical apps needing fast rollback or strict validation. Use autoscaled blue-green for long-running batch or disruption-sensitive workloads.

For standard command sequences and runbook templates, see `references/runbook-template.md`.

### Large-Scale AI/ML Clusters (GPU/TPU)

- GPU VMs do not support live migration — upgrades force pod restart.
- H100/A100 typically use fixed reservations with no surge capacity. Use `maxSurge=0, maxUnavailable=1`.
- GPU driver is coupled with target node version; verify CUDA compatibility.
- Use maintenance exclusions during active training campaigns. Cordon GPU nodes and wait for jobs to complete.
- TPU slices are recreated atomically (not rolling); maintenance on one slice restarts all slices in the environment.

## Checklists

Produce checklists as copyable markdown with checkboxes. See `references/checklists.md` for the full pre-upgrade and post-upgrade checklist templates. Adapt them to the user's environment.

## Maintenance runbooks

Produce step-by-step runbooks with actual `gcloud` and `kubectl` commands. See `references/runbook-template.md` for the standard command sequences.

## Troubleshooting

When a user reports a stuck or failing upgrade, walk through diagnosis systematically in this order:
1. PDB blocking drain (check `kubectl get pdb -A`)
2. Resource constraints (pods pending, increase maxSurge)
3. Bare pods (must delete or wrap in controllers)
4. Admission webhooks rejecting pod creation
5. PVC attachment issues (volume migration)

For a detailed diagnostic flowchart and fix procedures, see `references/troubleshooting.md`.
