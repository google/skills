---
name: gke-basics
metadata:
  category: Containers
description: >-
  Manages core GKE cluster provisioning, credentials, Autopilot vs Standard selection,
  and workload deployment. Use when creating GKE clusters, fetching kubectl credentials,
  configuring Workload Identity, or deciding between Autopilot and Standard modes.
  Don't use for specialized GKE networking (use gke-networking), advanced security hardening
  (use gke-platform-security or gke-workload-security), or cluster upgrades (use gke-upgrades).
---

# GKE Basics & Critical Gotchas

Managed Kubernetes platform on Google Cloud. Defaults to Autopilot mode unless Standard is explicitly required.

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
   * Never mount raw GCP Service Account JSON keys in Pods.
   * Annotate the Kubernetes ServiceAccount (`KSA`) to bind to the Google Service Account (`GSA`):
     ```yaml
     metadata:
       annotations:
         iam.gke.io/gcp-service-account: GSA_NAME@PROJECT_ID.iam.gserviceaccount.com
     ```

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
