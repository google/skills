---
name: gke-cost-analysis
metadata:
  category: CloudObservabilityAndMonitoring
description: >-
  Answer natural language questions and perform analysis on GKE cluster and
  workload costs using BigQuery billing exports, cost allocation data, and live
  cluster monitoring metrics. Use when querying GKE costs across projects,
  namespaces, or workloads, analyzing billing reports in BigQuery (`bq`), checking
  cluster cost budgets (`gcloud billing`), or diagnosing cost drivers like pod
  requests vs. actual utilization (`kubectl top`). Don't use for applying cost
  optimization changes, creating rightsizing manifests (VPA/MPA), or selecting
  ComputeClasses (use gke-cost-optimization instead).
---

# GKE Cost Analysis

This skill provides guidance on answering natural language questions about
GKE-related costs, billing reports, and utilization analysis.

## Overview

When users ask about GKE costs (e.g., "What are my costs across projects?",
"What's my most expensive namespace?", "Why is my cluster cost spiking?"), use
this skill to provide a structured and expert response using BigQuery billing
exports, cost allocation metadata, and live cluster metrics.

## Instructions

When handling a cost-related question:

1.  **Provide a Direct Answer**: Address the specific cost question or
    analytical request clearly and concisely.
2.  **Explain BigQuery Integration**: Explain how to query BigQuery for
    historical cost breakdown. Note that GKE costs originate from the GCP
    Billing Detailed BigQuery Export (`gcp_billing_export_resource_v1_*`).
3.  **Check & Verify Cost Allocation**: Explain that GKE Cost Allocation must be
    enabled on the cluster (`--enable-cost-allocation`) for namespace, label,
    and workload-level billing granularity. If queries return empty labels,
    provide the `gcloud` command to enable it.
4.  **Analyze Pricing Drivers & Utilization**: When diagnosing cost drivers,
    explain whether the cluster is in Autopilot (billed by requested pod
    CPU/memory) or Standard mode (billed by underlying VM node size + control
    plane fees), and compare live utilization (`kubectl top`) against
    provisioned requests.
5.  **Provide Actionable Commands/Queries**: Provide concrete BigQuery CLI (`bq
    query`) commands or read-only `gcloud`/`kubectl` inspection commands. Prefer
    `bq` over BigQuery Studio when available.

## Key Points & Pricing Drivers

-   **Data Source**: GKE costs come from GCP Billing Detailed BigQuery Export.
    The user must provide the full path to their BigQuery table (dataset name
    and table name containing the Billing Account ID).
-   **Granularity Requirement**: GKE Cost Allocation
    (`--enable-cost-allocation`) must be enabled on the cluster to populate
    `goog-k8s-cluster-name`, `k8s-namespace`, `k8s-workload-name`, and
    `k8s-workload-type` labels in BigQuery.
-   **Autopilot vs. Standard Cost Drivers**:
    -   **Autopilot Pricing**: Billed directly on pod resource requests
        (`requests.cpu`, `requests.memory`, ephemeral storage). Over-requested
        pods drive up billing regardless of whether the pod actively uses those
        CPU cycles or memory.
    -   **Standard Pricing**: Billed on provisioned node pool VMs (`e2`, `n4`,
        `c3`, etc.) plus a cluster management fee ($0.10/hour). Idle nodes or
        multiple low-utilization dev clusters drive excess infrastructure costs.
-   **Credits & Discounts Impact**: When analyzing `cost` versus
    `cost_before_credits`, note that Committed Use Discounts (CUDs) and Spot VMs
    appear as credits or reduced rate charges in the billing export.
-   **Tools & Syntax**: BigQuery CLI (`bq`) is preferred. When writing Standard
    SQL queries, use a dot (`.`) instead of a colon (`:`) to separate the
    project ID and dataset name (`{project_id}.{dataset_name}.{table_name}`).
-   **Defaults**: Assume last 30 days, row limit 10, ordering by cost descending
    (`ORDER BY cost DESC`), unless specified otherwise.

## Live Cluster & Cost Monitoring

Use read-only CLI commands to inspect current cluster budgets, node utilization,
and pod resource consumption vs. requests:

```bash
# View billing budgets for an account (requires Cost Management API)
gcloud billing budgets list --billing-account={billing_account} --quiet

# Verify/Enable GKE cost allocation on a cluster for namespace-level billing tracking
gcloud container clusters update {cluster_name} \
    --enable-cost-allocation \
    --region {region}

# View live node resource utilization across the cluster
kubectl top nodes

# View pod resource usage across namespaces (compare against requested limits to diagnose waste)
kubectl top pods --all-namespaces --containers
```

## Applying Cost Optimizations

To apply rightsizing changes based on analysis (such as setting up `VPA`
recommendation mode, adjusting CPU/memory to `P95 * 1.2`, configuring Spot VMs
via `nodeSelector` or `ComputeClass`, enforcing `ResourceQuotas`, or selecting
machine types and CUDs), use the **`gke-cost-optimization`** skill.

## Example BigQuery Queries

Use these queries as templates to answer questions. All parameters (dataset,
table, project, cluster, etc.) must be replaced with user values.

### Cost of a Single Workload in a Single Cluster

```sql
bq query --nouse_legacy_sql '
SELECT
  SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS cost,
  SUM(cost) AS cost_before_credits
FROM {billing_export_table} AS bqe
WHERE _PARTITIONTIME >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
  AND project.id = "{project_id}"
  AND EXISTS(SELECT * FROM bqe.labels AS l WHERE l.key = "goog-k8s-cluster-location" AND l.value = "{region}")
  AND EXISTS(SELECT * FROM bqe.labels AS l WHERE l.key = "goog-k8s-cluster-name" AND l.value = "{cluster_name}")
  AND EXISTS(SELECT * FROM bqe.labels AS l WHERE l.key = "k8s-namespace" AND l.value = "{namespace}")
  AND EXISTS(SELECT * FROM bqe.labels AS l WHERE l.key = "k8s-workload-type" AND l.value = "{workload_type}")
  AND EXISTS(SELECT * FROM bqe.labels AS l WHERE l.key = "k8s-workload-name" AND l.value = "{workload_name}")
;
'
```

### Cost of Each Workload in Each Cluster

```sql
bq query --nouse_legacy_sql '
SELECT
  project.id AS project_id,
  (SELECT l.value FROM bqe.labels AS l WHERE l.key = "goog-k8s-cluster-location" LIMIT 1) AS cluster_location,
  (SELECT l.value FROM bqe.labels AS l WHERE l.key = "goog-k8s-cluster-name" LIMIT 1) AS cluster_name,
  (SELECT l.value FROM bqe.labels AS l WHERE l.key = "k8s-namespace" LIMIT 1) AS k8s_namespace,
  (SELECT l.value FROM bqe.labels AS l WHERE l.key = "k8s-workload-type" LIMIT 1) AS k8s_workload_type,
  (SELECT l.value FROM bqe.labels AS l WHERE l.key = "k8s-workload-name" LIMIT 1) AS k8s_workload_name,
  SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS cost,
  SUM(cost) AS cost_before_credits
FROM {billing_export_table} AS bqe
WHERE _PARTITIONTIME >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
  AND EXISTS(SELECT * FROM bqe.labels AS l WHERE l.key = "goog-k8s-cluster-name")
GROUP BY 1, 2, 3, 4, 5, 6
ORDER BY 7 DESC
LIMIT 10
;
'
```

### Cost Breakdown by Namespace in a Cluster

```sql
bq query --nouse_legacy_sql '
SELECT
  (SELECT l.value FROM bqe.labels AS l WHERE l.key = "k8s-namespace" LIMIT 1) AS k8s_namespace,
  SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS net_cost,
  SUM(cost) AS gross_cost
FROM {billing_export_table} AS bqe
WHERE _PARTITIONTIME >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
  AND project.id = "{project_id}"
  AND EXISTS(SELECT * FROM bqe.labels AS l WHERE l.key = "goog-k8s-cluster-name" AND l.value = "{cluster_name}")
GROUP BY 1
ORDER BY 2 DESC
LIMIT 10
;
'
```

Note: Checking that the `goog-k8s-cluster-name` label exists scopes the total
billing data specifically to GKE costs.
