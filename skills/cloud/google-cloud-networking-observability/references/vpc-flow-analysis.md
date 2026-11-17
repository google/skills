# VPC Flow Analysis Reference

Use VPC Flow Logs to analyze traffic volume, top talkers, latency, and packet
drops for various Cloud products such as PSC, serverless workloads, and others.

## Table of Contents

-   [1. Querying VPC Flow Logs (BigQuery and Cloud Logging)](#1-querying-vpc-flow-logs-bigquery-and-cloud-logging):
    Lines 20-65
-   [2. Core, Instance, Subnet, Latency and Drop Fields](#2-core-instance-subnet-latency-and-drop-fields):
    Lines 67-88
-   [3. Packet Drops Analysis](#3-packet-drops-analysis): Lines 90-98
-   [4. Private Service Connect (PSC) Analysis](#4-private-service-connect-psc-analysis):
    Lines 100-110
-   [5. Serverless Workloads (Direct VPC Egress)](#5-serverless-workloads-direct-vpc-egress):
    Lines 112-121
-   [6. Flow Analyzer and Reference Documentation](#6-flow-analyzer-and-reference-documentation):
    Lines 123-132

## 1. Querying VPC Flow Logs (BigQuery and Cloud Logging)

Always include **both** legacy subnet (`compute.googleapis.com/vpc_flows`) and
Network Management (`networkmanagement.googleapis.com/vpc_flows`) log names.
Prefer BigQuery (`_AllLogs`) for volume/Top-N aggregations and Cloud Logging for
small exploratory lookups.

-   **Column Naming**: In BigQuery `_AllLogs`, the top-level JSON column is
    `json_payload` (`snake_case`); in Cloud Logging filters, it is `jsonPayload`
    (`camelCase`). Nested VPC Flow Log fields are `snake_case` in both.

### BigQuery (`execute_sql_readonly` MCP or `bq query`)

```bash
bq query --use_legacy_sql=false --format=json --project_id={project_id} '
SELECT
  JSON_VALUE(json_payload.src_instance.vm_name) AS src_vm,
  JSON_VALUE(json_payload.connection.src_ip) AS src_ip,
  JSON_VALUE(json_payload.connection.dest_ip) AS dest_ip,
  SUM(CAST(JSON_VALUE(json_payload.bytes_sent) AS INT64)) AS total_bytes_sent
FROM `{project_id}.{dataset_id}._AllLogs`
WHERE
  log_name IN (
    "projects/{project_id}/logs/compute.googleapis.com%2Fvpc_flows",
    "projects/{project_id}/logs/networkmanagement.googleapis.com%2Fvpc_flows"
  )
  AND JSON_VALUE(json_payload.reporter) = "SRC"
  AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
GROUP BY 1, 2, 3
ORDER BY total_bytes_sent DESC
LIMIT 10
'
```

### Cloud Logging (`list_log_entries` MCP or `gcloud logging read`)

```text
(logName="projects/{project_id}/logs/compute.googleapis.com%2Fvpc_flows" OR
 logName="projects/{project_id}/logs/networkmanagement.googleapis.com%2Fvpc_flows")
resource.type="gce_subnetwork"
```

```bash
gcloud logging read '(logName="projects/{project_id}/logs/compute.googleapis.com%2Fvpc_flows" OR logName="projects/{project_id}/logs/networkmanagement.googleapis.com%2Fvpc_flows") AND resource.type="gce_subnetwork" AND timestamp>="{start_time}"' \
  --project={project_id} --limit=10 --format=json --quiet
```

## 2. Core, Instance, Subnet, Latency and Drop Fields

-   **5-Tuple (`connection`)**: `src_ip`, `src_port`, `dest_ip`, `dest_port`,
    `protocol` (`6` = TCP, `17` = UDP, `1` = ICMP).
-   **Volume & Direction**: `bytes_sent`, `packets_sent` (string-encoded `INT64`
    in JSON; `CAST(JSON_VALUE(...) AS INT64)`), `reporter` (`"SRC"` or `"DEST"`
    — filter to one side when summing traffic between internal VMs to avoid
    double-counting).
-   **VM Instance Metadata (`src_instance` / `dest_instance`)**: `vm_name`,
    `project_id`, `region`, `zone`. (`NULL` when subnet metadata is
    `EXCLUDE_ALL_METADATA`; fall back to `connection.src_ip` / `dest_ip`.)
-   **VPC & Subnetwork Metadata**: `src_vpc` / `dest_vpc` (`vpc_name`,
    `subnetwork_name`, `subnetwork_region`, `project_id`), plus
    `resource.labels.{subnetwork_name, subnetwork_id, location}` on
    `resource.type="gce_subnetwork"`.
-   **Latency (RTT)**: Prefer `round_trip_time.median_msec` (`DOUBLE`,
    sub-millisecond precision across TCP and Falcon); `rtt_msec` (`INT64`, whole
    ms) is TCP-only.
-   **Packet Drops**: `disposition` (`"DROPPED"`), `drop_reason`,
    `packets_dropped`, `bytes_dropped`, `throughput_inclusion` (`"INCLUDED"`
    when `packets_sent` / `bytes_sent` already include dropped traffic;
    `"EXCLUDED"` when dropped traffic is counted separately).

## 3. Packet Drops Analysis

VPC Flow Logs record dropped packet volume, drop reasons, dropped packet/byte
counters, and `throughput_inclusion` (check whether dropped traffic is already
included in `packets_sent` / `bytes_sent` before combining counters).

-   **Firewall Deny Attribution**: VPC Flow Logs report firewall drops without
    naming the specific rule. To attribute denies to specific firewall rules,
    query **Firewall Rules Logging** (`compute.googleapis.com/firewall`).

## 4. Private Service Connect (PSC) Analysis

VPC Flow Logs annotate Private Service Connect (PSC) traffic across endpoints,
service attachments, and PSC interfaces (PSC-I), recording the reporting side
(consumer or producer), endpoint/attachment metadata, connection IDs, network
attachments, and producer project or service class metadata.

-   **Cross-Project Correlation**: Producer-side flow logs include the
    consumer's pre-NAT 5-tuple annotation alongside the local connection,
    supporting correlation across consumer and producer logs via the shared
    connection ID or consumer connection annotation.

## 5. Serverless Workloads (Direct VPC Egress)

VPC Flow Logs annotate serverless workloads using Direct VPC egress (such as
Cloud Run and App Engine), capturing workload-specific metadata on source or
destination.

-   **Dynamic IP Allocation**: Serverless instances dynamically allocate IP
    addresses from the VPC subnet pool. Rather than filtering by static IP
    addresses, identify serverless traffic using the serverless workload
    metadata annotations.

## 6. Flow Analyzer and Reference Documentation

-   **Visual Analysis**: Include
    [Google Cloud Console Flow Analyzer](https://console.cloud.google.com/net-intelligence/flow-analyzer)
    in VPC Flow Log responses for interactive flow visualization.
-   **Record Schema Discovery**: For exact nested field paths (such as packet
    drops, PSC endpoints/interfaces, or serverless metadata), inspect a sample
    log record (`LIMIT 1` / `--limit=1`) or search/fetch the official public
    documentation (e.g., via `curl -sL`):
    [VPC Flow Logs record format](https://docs.cloud.google.com/vpc/docs/about-flow-logs-records.md.txt)
