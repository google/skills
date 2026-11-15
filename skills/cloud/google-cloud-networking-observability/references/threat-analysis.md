# Threat Log Analysis Reference

Use Firewall Threat Logs and Cloud IDS logs to identify, analyze, and
troubleshoot security incidents in your VPC network.

## Table of Contents

-   [1. View Threat Alerts (Cloud Logging)](#1-view-threat-alerts-cloud-logging):
    Lines 16-38
-   [2. Aggregate Threat Trends (BigQuery)](#2-aggregate-threat-trends-bigquery):
    Lines 40-89
-   [3. CLI Fallback (gcloud and bq)](#3-cli-fallback-gcloud-and-bq): Lines
    91-122
-   [4. Key Fields](#4-key-fields): Lines 124-134

## 1. View Threat Alerts (Cloud Logging)

Use `list_log_entries` (when Cloud Logging MCP is declared) or `gcloud logging
read` for quick identification of recent alerts. Search **both** Cloud Firewall
Plus and Cloud IDS threat log sources:

```text
logName:(
"projects/{project_id}/logs/networksecurity.googleapis.com%2Ffirewall_threat" OR
"projects/{project_id}/logs/ids.googleapis.com%2Fthreat")
```

To filter for high-severity threats (`HIGH` or `CRITICAL`):

```text
logName:(
"projects/{project_id}/logs/networksecurity.googleapis.com%2Ffirewall_threat" OR
"projects/{project_id}/logs/ids.googleapis.com%2Fthreat")
jsonPayload.threatDetails.severity=("HIGH" OR "CRITICAL")
```

*(Append `jsonPayload.action="DENY"` when filtering specifically for blocked
threats.)*

## 2. Aggregate Threat Trends (BigQuery)

Use `execute_sql_readonly` (when BigQuery MCP is declared) or `bq query` for
multi-day audits and top attacker analysis.

**Note**: In BigQuery `_AllLogs`, the top-level column is `json_payload`
(`snake_case`), while nested threat log JSON keys retain `camelCase` (e.g.,
`threatDetails`, `clientIp`, `serverIp`, `serverPort`).

```sql
SELECT
  timestamp,
  JSON_VALUE(json_payload.threatDetails.threat) AS threat_name,
  JSON_VALUE(json_payload.threatDetails.severity) AS severity,
  JSON_VALUE(json_payload.threatDetails.category) AS category,
  JSON_VALUE(json_payload.action) AS action,
  JSON_VALUE(json_payload.connection.clientIp) AS src_ip,
  JSON_VALUE(json_payload.connection.serverIp) AS dest_ip,
  JSON_VALUE(json_payload.connection.serverPort) AS dest_port,
  JSON_VALUE(json_payload.threatDetails.description) AS description
FROM `{project_id}.{dataset_id}._AllLogs`
WHERE
  log_id IN (
    'networksecurity.googleapis.com/firewall_threat',
    'ids.googleapis.com/threat'
  )
  AND JSON_VALUE(json_payload.threatDetails.severity) IN ('HIGH', 'CRITICAL')
  AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
ORDER BY timestamp DESC
LIMIT 20
```

To rank top attacker IPs:

```sql
SELECT
  JSON_VALUE(json_payload.connection.clientIp) AS attacker_ip,
  COUNT(*) AS attack_count,
  ARRAY_AGG(DISTINCT JSON_VALUE(json_payload.threatDetails.threat) LIMIT 5) AS sample_threats
FROM `{project_id}.{dataset_id}._AllLogs`
WHERE
  log_id IN (
    'networksecurity.googleapis.com/firewall_threat',
    'ids.googleapis.com/threat'
  )
  AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY 1
ORDER BY attack_count DESC
LIMIT 10
```

## 3. CLI Fallback (gcloud and bq)

**View High-Severity Threat Alerts (`gcloud`)**:

```bash
gcloud logging read 'logName:("projects/{project_id}/logs/networksecurity.googleapis.com%2Ffirewall_threat" OR "projects/{project_id}/logs/ids.googleapis.com%2Fthreat") AND jsonPayload.threatDetails.severity=("HIGH" OR "CRITICAL") AND timestamp>="{start_time}"' \
  --project={project_id} --limit=20 --format=json --quiet
```

**Aggregate High-Severity Threat Trends (`bq`)**:

```bash
bq query --use_legacy_sql=false --format=json --project_id={project_id} '
SELECT
  timestamp,
  JSON_VALUE(json_payload.threatDetails.threat) AS threat_name,
  JSON_VALUE(json_payload.threatDetails.severity) AS severity,
  JSON_VALUE(json_payload.threatDetails.category) AS category,
  JSON_VALUE(json_payload.action) AS action,
  JSON_VALUE(json_payload.connection.clientIp) AS src_ip,
  JSON_VALUE(json_payload.connection.serverIp) AS dest_ip,
  JSON_VALUE(json_payload.connection.serverPort) AS dest_port
FROM `{project_id}.{dataset_id}._AllLogs`
WHERE
  log_id IN ("networksecurity.googleapis.com/firewall_threat",
             "ids.googleapis.com/threat")
  AND JSON_VALUE(json_payload.threatDetails.severity) IN ("HIGH", "CRITICAL")
  AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
ORDER BY timestamp DESC
LIMIT 20
'
```

## 4. Key Fields

-   `jsonPayload.threatDetails.threat`: Human-readable threat name.
-   `jsonPayload.threatDetails.severity`: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`,
    `INFORMATIONAL`.
-   `jsonPayload.threatDetails.category`: Threat category.
-   `jsonPayload.action`: `"ALLOW"`, `"DENY"`, or `"ALERT"`.
-   `jsonPayload.connection.clientIp`: Source IP.
-   `jsonPayload.connection.serverIp` / `serverPort`: Destination IP and port.
-   `jsonPayload.threatDetails.cves`: Associated CVE IDs.
-   `jsonPayload.threatDetails.description`: Attack payload details.
