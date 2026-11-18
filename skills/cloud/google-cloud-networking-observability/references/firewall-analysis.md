# Firewall Rule Logging Analysis Reference

Use Firewall Rules Logging (`compute.googleapis.com/firewall`) to rank active
firewall rules, attribute firewall deny drops to specific rules, and identify
blocked source/destination IPs.

## 1. Key Fields

-   **Monitored Resource**: `resource.type="gce_subnetwork"` (or
    `gce_network`/`gce_firewall_policy` for hierarchical/network policies).
-   **JSON Payload Fields** (`jsonPayload` in Cloud Logging / `json_payload` in
    BigQuery `_AllLogs`):
    -   `disposition`: `"ALLOWED"` or `"DENIED"`.
    -   `rule_details.reference`: Firewall rule identifier (e.g.,
        `network:{vpc}/firewall:{rule_name}`).
    -   `rule_details.action`: `"ALLOW"` or `"DENY"`.
    -   `rule_details.direction`: `"INGRESS"` or `"EGRESS"`.
    -   `rule_details.priority`: Rule priority integer.
    -   `connection`: `src_ip`, `src_port`, `dest_ip`, `dest_port`, `protocol`.
    -   `instance`: `vm_name`, `project_id`, `region`, `zone`.

## 2. Aggregate Rule Activity & Denied Traffic (BigQuery)

Prefer BigQuery (`execute_sql_readonly` MCP or `bq query`) for hit counts, top
active rules, and firewall deny attribution:

```bash
bq query --use_legacy_sql=false --format=json --project_id={project_id} '
SELECT
  JSON_VALUE(json_payload.rule_details.reference) AS rule_reference,
  JSON_VALUE(json_payload.rule_details.action) AS action,
  COUNT(*) AS hit_count,
  COUNTIF(
    JSON_VALUE(json_payload.rule_details.action) = "DENY"
    OR JSON_VALUE(json_payload.disposition) = "DENIED"
  ) AS deny_count,
  ARRAY_AGG(
    DISTINCT IF(
      JSON_VALUE(json_payload.rule_details.action) = "DENY"
      OR JSON_VALUE(json_payload.disposition) = "DENIED",
      JSON_VALUE(json_payload.connection.src_ip),
      NULL
    ) IGNORE NULLS LIMIT 10
  ) AS blocked_src_ips
FROM `{project_id}.{dataset_id}._AllLogs`
WHERE
  log_name LIKE "%/logs/compute.googleapis.com%2Ffirewall"
  AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
GROUP BY 1, 2
ORDER BY hit_count DESC
LIMIT 10
'
```

*(Add `AND (JSON_VALUE(json_payload.rule_details.action) = "DENY"`
`OR JSON_VALUE(json_payload.disposition) = "DENIED")` to `WHERE` when querying
exclusively for blocking rules.)*

## 3. Exploratory Log Lookup (Cloud Logging)

Use `list_log_entries` MCP or `gcloud logging read` for recent samples or when
BigQuery log sinks are not linked:

```text
logName="projects/{project_id}/logs/compute.googleapis.com%2Ffirewall"
jsonPayload.rule_details.action="DENY"
```

```bash
gcloud logging read 'logName="projects/{project_id}/logs/compute.googleapis.com%2Ffirewall" AND jsonPayload.rule_details.action="DENY" AND timestamp>="{start_time}"' \
  --project={project_id} --limit=20 --format=json --quiet
```

## Reference Documentation

-   [VPC Firewall Rules Logging overview](https://docs.cloud.google.com/firewall/docs/vpc-firewall-rules-logging-overview.md.txt)
-   [Use VPC Firewall Rules Logging](https://docs.cloud.google.com/firewall/docs/manage-vpc-firewall-rules-logging.md.txt)
