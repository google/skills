# Cost Tracking & FinOps Standards

Keep your agent infrastructure cost-compliant by maintaining standardized tags across all cloud computing components.

## Labeling Schema

All projects and workloads associated with Agent deployments must maintain these metadata attributes:

| Label Key | Valid Values | Description |
|---|---|---|
| `agent-id` | `[a-z0-9_-]{3,63}` | The identifier of the deploying agent. |
| `business-unit` | `engineering`, `finance`, `pso` | The department paying for resources. |
| `environment` | `dev`, `staging`, `prod` | Deployment lifecycle tier. |

## BigQuery Cost Analysis Query

Use this query in your Google Cloud Billing export dataset to identify your top 5 most expensive agents over the past week:

```sql
SELECT 
  labels.value AS agent_id,
  SUM(cost) AS total_cost,
  currency
FROM `[YOUR_BILLING_DATASET].gcp_billing_export_v1_[BILLING_ID]`
CROSS JOIN UNNEST(labels) AS labels
WHERE labels.key = 'agent-id'
  AND usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY 1, currency
ORDER BY total_cost DESC
LIMIT 5;
```
