---
name: gke-basics
description: >-
  Plans, creates, and configures production-ready GKE clusters using the golden
  path Autopilot configuration. Covers Day-0 checklist, Autopilot vs Standard,
  networking, security, observability, scaling, cost optimization, and AI/ML
  inference. Use when creating GKE clusters, provisioning GKE environments,
  designing GKE networking, securing GKE, optimizing GKE cost, autoscaling, or
  upgrading. Don't use if specialized skills for security, networking, scaling,
  cost, storage, or upgrades are more applicable (use gke-security,
  gke-networking, gke-scaling, gke-cost, gke-storage, or gke-upgrades instead).
---

# Google Kubernetes Engine (GKE) Basics

GKE is a managed Kubernetes platform on Google Cloud for deploying, scaling, and
operating containerized applications. This skill defaults to the **golden path
Autopilot configuration** — see [gke-golden-path](../gke-golden-path/SKILL.md)
for defaults, rules, and guardrails.

## Quick Start

```bash
gcloud services enable container.googleapis.com --quiet
gcloud container clusters create-auto my-cluster --region=us-central1 --quiet
gcloud container clusters get-credentials my-cluster --region=us-central1 --quiet
kubectl create deployment hello-server \
  --image=us-docker.pkg.dev/google-samples/containers/gke/hello-app:1.0
```

## Reference Directory

Load the relevant reference based on trigger keywords. Prefer the most specific
match; if ambiguous, ask the user to clarify. If a referenced sibling skill
(pointing to `..`) is not installed or cannot be accessed, inform the user that
they may need to install that specific skill (e.g., `gke-networking`), and fall
back to your general GKE knowledge.

Scenario               | Trigger Keywords                                                                          | Reference
---------------------- | ----------------------------------------------------------------------------------------- | ---------
Core Concepts          | Autopilot vs Standard, architecture, pricing, what is GKE                                 | [core-concepts.md](./references/core-concepts.md)
Golden Path & Defaults | golden path, Day-0 checklist, production defaults, cluster defaults                       | [gke-golden-path](../gke-golden-path/SKILL.md)
Cluster Creation       | create cluster, new cluster, provision GKE                                                | [gke-cluster-creation](../gke-cluster-creation/SKILL.md)
Networking             | private cluster, VPC, subnet, Gateway API, DNS, ingress, egress, datapath                 | [gke-networking](../gke-networking/SKILL.md)
Security & IAM         | Workload Identity, Secret Manager, RBAC, Binary Auth, hardening, audit, gVisor, IAM roles | [gke-security](../gke-security/SKILL.md)
Scaling                | HPA, VPA, autoscaler, autoscaling, NAP, scale pods, scale nodes                           | [gke-scaling](../gke-scaling/SKILL.md)
Compute Classes        | ComputeClass, machine family, Spot fallback, GPU node pool, node selection                | [gke-compute-classes](../gke-compute-classes/SKILL.md)
Cost                   | cost, savings, Spot VMs, rightsizing, CUD, optimize spend, budget                         | [gke-cost](../gke-cost/SKILL.md)
AI/ML Inference        | inference, model serving, LLM, GPU, TPU, GIQ, vLLM                                        | [gke-inference](../gke-inference/SKILL.md)
Upgrades               | upgrade, maintenance window, release channel, patching, version                           | [gke-upgrades](../gke-upgrades/SKILL.md)
Observability          | monitoring, logging, Prometheus, Grafana, metrics, alerts, dashboards                     | [gke-observability](../gke-observability/SKILL.md)
Multi-tenancy          | multi-tenant, namespace isolation, team access, enterprise, RBAC planning                 | [gke-multitenancy](../gke-multitenancy/SKILL.md)
Batch & HPC            | batch, HPC, job queue, high performance, MPI, parallel                                    | [gke-batch-hpc](../gke-batch-hpc/SKILL.md)
App Onboarding         | containerize, deploy app, Dockerfile, onboard, migrate to GKE                             | [gke-app-onboarding](../gke-app-onboarding/SKILL.md)
Backup & DR            | backup, restore, disaster recovery, CMEK                                                  | [gke-backup-dr](../gke-backup-dr/SKILL.md)
Storage                | storage, PVC, persistent volume, StorageClass, Filestore, GCS FUSE                        | [gke-storage](../gke-storage/SKILL.md)
Reliability            | PDB, health probe, liveness, readiness, topology spread, graceful shutdown                | [gke-reliability](../gke-reliability/SKILL.md)
Client Libraries       | client library, client-go, kubernetes python, kubernetes java, kubernetes SDK             | [client-library-usage.md](./references/client-library-usage.md)
Infrastructure as Code | Terraform, IaC, HCL, infrastructure as code                                               | [iac-usage.md](./references/iac-usage.md)
MCP Server             | MCP tools, MCP server, MCP setup                                                          | [mcp-usage.md](./references/mcp-usage.md)
CLI / Tools            | gcloud, kubectl, commands, how to                                                         | [cli-reference.md](./references/cli-reference.md)
Production Audit       | production readiness, compliance, golden path check                                       | [gke-cluster-creation](../gke-cluster-creation/SKILL.md)

*If you need product information not found in these references, use the Developer Knowledge MCP server `search_documents` tool.*
