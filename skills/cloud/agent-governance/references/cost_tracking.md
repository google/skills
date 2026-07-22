# Agent Usage Cost Tracking & FinOps Guide

This reference document outlines the complete workflow for tracking, attributing, and querying AI agent usage costs on Google Cloud using standardized resource labeling and BigQuery billing exports.

---

## 1. Cost Components for AI Agents

Costs incurred by autonomous AI agents and workflows typically span multiple Google Cloud services:

| Component | Cost Driver | Example Services |
| :--- | :--- | :--- |
| **Agent Engine / Runtime** | Serverless / container compute | Cloud Run, GKE, Vertex AI Reasoning Engine |
| **Model Inference** | Input/Output tokens, model tier | Gemini 1.5 Pro/Flash, Vertex AI Model Garden |
| **RAG & Embeddings** | Vector index hosting, query operations | Vertex AI Vector Search, Vertex AI Search |
| **Storage & Memory** | Session state, agent artifacts, logs | Cloud Storage, Firestore, Cloud SQL |
| **Tooling & Gateways** | API extensions, proxy egress, MCP servers | Cloud Run, Cloud Functions, API Gateway |

---

## 2. Standardized FinOps Labeling Scheme

Consistent labeling across all agent infrastructure is required for accurate cost allocation.

### Standard Label Keys

* `agent-id`: Unique identifier for the agent instance (e.g., `orders-agent-prod`). **[MANDATORY]**
* `business-unit`: Owning division or cost center (e.g., `logistics`, `finance`). **[MANDATORY]**
* `environment`: Deployment stage (`dev`, `staging`, `prod`). **[MANDATORY]**
* `agent-owner`: Owning team contact or email (e.g., `ai-ops-team`).
* `agent-name`: Human-readable name (e.g., `order-resolution-agent`).

### Example Configuration (`agent_labels.yaml`)

```yaml
agent-id: "orders-agent-prod"
business-unit: "logistics"
environment: "prod"
agent-owner: "ai-ops-team"
agent-name: "order-resolution-agent"
```

---

## 3. Applying Governance Labels (Tier M)

> ⚠️ **Tier M Safety Restriction:** Applying or updating labels mutates resource metadata. Always confirm target resource names and project parameters before applying.

### Cloud Run Agent Runtime
```bash
gcloud run services update $SERVICE_NAME \
    --update-labels=agent-id=$AGENT_ID,business-unit=$BU,environment=$ENV \
    --region=$LOCATION_ID \
    --project=$PROJECT_ID
```

### Vertex AI Endpoints
```bash
gcloud ai endpoints update $ENDPOINT_ID \
    --update-labels=agent-id=$AGENT_ID,business-unit=$BU,environment=$ENV \
    --region=$LOCATION_ID \
    --project=$PROJECT_ID
```

### Cloud Storage Buckets (Memory / Artifacts)
```bash
gcloud storage buckets update gs://$BUCKET_NAME \
    --update-labels=agent-id=$AGENT_ID,business-unit=$BU,environment=$ENV \
    --project=$PROJECT_ID
```

---

## 4. Analytical BigQuery Cost Queries (Tier R)

Enable [Cloud Billing Export to BigQuery](https://cloud.google.com/billing/docs/how-to/export-data-bigquery) to query granular agent expenditures.

### Query 1: Top 5 Most Expensive Agents (Last 7 Days)

```sql
SELECT
  labels.value AS agent_id,
  ROUND(SUM(cost), 2) AS total_cost_usd,
  ANY_VALUE(invoice.month) AS invoice_month,
  ARRAY_AGG(DISTINCT service.description) AS services_used
FROM
  `$PROJECT_ID.$BILLING_DATASET.gcp_billing_export_v1_$BILLING_ACCOUNT_ID`
CROSS JOIN
  UNNEST(labels) AS labels
WHERE
  labels.key = 'agent-id'
  AND usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY
  agent_id
ORDER BY
  total_cost_usd DESC
LIMIT 5;
```

### Query 2: Cost Breakdown by Service & Environment

```sql
SELECT
  (SELECT value FROM UNNEST(labels) WHERE key = 'agent-id') AS agent_id,
  (SELECT value FROM UNNEST(labels) WHERE key = 'environment') AS environment,
  service.description AS service_name,
  ROUND(SUM(cost), 2) AS service_cost_usd
FROM
  `$PROJECT_ID.$BILLING_DATASET.gcp_billing_export_v1_$BILLING_ACCOUNT_ID`
WHERE
  EXISTS(SELECT 1 FROM UNNEST(labels) WHERE key = 'agent-id')
  AND usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY
  agent_id, environment, service_name
ORDER BY
  agent_id, service_cost_usd DESC;
```

---

## 5. Visualizations, Budgets & Anomaly Alerts

1. **Google Cloud Console Billing Reports:** Navigate to **Billing > Reports** and filter by Group By `Label: agent-id`.
2. **Budgets & Alerts:** Set up programmatic budget alerts in **Billing > Budgets & Alerts** with label filters to trigger notifications or Cloud Functions when spending crosses 80%, 100%, or 120% thresholds.
