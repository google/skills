---
name: gke-basics
metadata:
  version: "1.1.3"
  category: Containers
description: >-
  Manages core GKE cluster provisioning, credentials, Autopilot vs Standard selection,
  and workload deployment. Use when creating GKE clusters, fetching kubectl credentials,
  or deciding between Autopilot and Standard modes. Don't use for Workload Identity
  (use gke-workload-identity), GKE networking (use gke-networking), security hardening
  (use gke-platform-security or gke-workload-security), or cluster upgrades (use gke-upgrades).
---

# GKE Basics & Critical Gotchas

> **Routing Note:** For Workload Identity KSA/GSA setup, use the
> `gke-workload-identity` skill. For cluster security flags
> (`--database-encryption-key`, `--security-posture`, RBAC, Shielded Nodes,
> Binary Authorization), use the `gke-platform-security` skill. For cluster
> upgrades or maintenance windows, use the `gke-upgrades` skill. For generating
> Kubernetes YAML manifests (`Deployment`, `StatefulSet`, `Service`,
> `HTTPRoute`, `PodDisruptionBudget`), use the `gke-manifest-generation` skill.

Managed Kubernetes platform on Google Cloud. Defaults to Autopilot mode unless Standard is explicitly required.

## Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read [Usage Attribution](references/attribution.md). For commands executed
directly in the terminal (never in generated scripts, Terraform, or user code),
prefix `gcloud` with
`CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:gke-basics)"`
and append `agent-skills/1.0 (skill:gke-basics)` to `User-Agent` headers.

## Key Selection Rules: Autopilot vs. Standard

* **Default to Autopilot** for almost all workloads.
* **Use Standard ONLY if:**
  * Custom node OS kernel parameters (`sysctl`) are required.
  * Custom node taints or specific hardware node pools are required.
  * DaemonSets require raw `hostPath` mounts to the host OS filesystem.
* When explaining why Standard is required over Autopilot, explicitly cite all matching restrictions (e.g., custom sysctls and custom node taints).
* *For advanced cluster architecture or complex node pool creation planning, refer to `gke-cluster-creation`.*

## Critical Gotchas & Best Practices

1. **Private Autopilot Clusters:**
   * Use `--enable-private-nodes` for private node IP addresses.
   * Use `--enable-private-endpoint` to disable public IP access to the control plane.
   * Restrict control plane access with `--enable-master-authorized-networks` and `--master-authorized-networks=CIDR_BLOCK`:
     ```bash
     gcloud container clusters create-auto CLUSTER_NAME --region=REGION \
       --enable-private-nodes \
       --enable-private-endpoint \
       --enable-master-authorized-networks \
       --master-authorized-networks=CIDR_BLOCK
     ```

2. **Workload Identity (IAM Binding):**
   * Never mount raw GCP Service Account JSON keys in Pods; use the
     `gke-workload-identity` skill for KSA/GSA setup.

3. **Autopilot Resource Requests:**
   * In Autopilot, CPU requests must be specified in increments of 250m (0.25 vCPU). If an unaligned CPU request (e.g., 300m) is requested, round up to the nearest 250m increment (500m / 0.5 vCPU).
   * Resource requests equal limits automatically. Omit `limits` to allow Autopilot to set defaults matching `requests`.

4. **Cluster Credentials:**
   * Always explicitly specify `--region` (for regional clusters) or `--zone` (for zonal clusters) when fetching credentials:
     ```bash
     gcloud container clusters get-credentials CLUSTER_NAME --region=REGION --quiet
     ```

## Reference Directory

-   [Core Concepts](references/core-concepts.md): Architecture, cluster modes (Autopilot vs Standard), networking, scaling, and security model.

-   [CLI Usage & Tool Reference](references/cli-reference.md): Tool preference hierarchy (MCP vs gcloud vs kubectl), `gcloud container` commands, and user preference overrides.

-   [Client Libraries](references/client-library-usage.md): Official Kubernetes and Google Cloud Container client libraries in Python, Go, Node.js, and Java.

-   [MCP Usage](references/mcp-usage.md): Connecting to and using the 23 structured GKE MCP tools for cluster management, K8s resources, and diagnostics.

-   [Infrastructure as Code](references/iac-usage.md): Terraform examples for `google_container_cluster` (Autopilot), Kubernetes provider resources, and YAML samples.
