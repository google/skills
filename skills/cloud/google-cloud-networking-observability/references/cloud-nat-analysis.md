# Cloud NAT Analysis Reference

Use Cloud Router control-plane inspection, Cloud NAT logs
(`compute.googleapis.com/nat_flows`), and Cloud Monitoring metrics to discover
NAT gateways, audit internal-to-external IP/port mappings, count allocated
connections, or troubleshoot port exhaustion.

## 1. Gateway Discovery & Live Control-Plane Mappings

Because Cloud NAT configurations (`nats[]`) live on the Compute `Router`
resource, discover all NAT gateways, routers, regions, and logging settings
across the project in **one command**:

```bash
gcloud compute routers list --project={project_id} --filter="nats:*" \
  --format="json(name,region.basename(),network.basename(),nats)"
```

Inspect runtime NAT status or currently allocated VM IP:port ranges directly
from the router control plane (works even when Cloud NAT logging is disabled):

```bash
gcloud compute routers get-status {router_name} --region={region} --project={project_id} --format=json
gcloud compute routers get-nat-mapping-info {router_name} --region={region} --project={project_id} --format=json
```

*Note*: `get-nat-mapping-info` shows active VM-level port-range allocations;
historical per-connection 7-tuples (`dest_ip`, exact `nat_port`, and
`allocation_status`) require `compute.googleapis.com/nat_flows` logs. (Egress
VPC Flow Logs only record `nat_gateway_details.{gateway_name,router_name,type}`,
not the external `nat_ip`/`nat_port`.)

## 2. Cloud NAT Logs (`compute.googleapis.com/nat_flows`)

-   **Resource**: `resource.type="nat_gateway"`,
    `resource.labels.{gateway_name, router_id, region, project_id}`.
-   **JSON Fields** (`jsonPayload` in Cloud Logging / `json_payload` in BigQuery
    `_AllLogs`):
    -   `connection`: `src_ip`, `src_port` (internal VM IP/port), `nat_ip`,
        `nat_port` (allocated external NAT IP/port), `dest_ip`, `dest_port`,
        `protocol`.
    -   `allocation_status`: `"OK"` (allocated) or `"DROPPED"` (port exhaustion).
    -   `endpoint`: `vm_name`, `project_id`, `region`, `zone`.
    -   `gateway_identifiers`: `gateway_name`, `router_name`, `region`.

**Cloud Logging (`list_log_entries` MCP or `gcloud logging read`)** — latest
mapping entry (append `AND jsonPayload.allocation_status="DROPPED"` for drops):

```bash
gcloud logging read 'resource.type="nat_gateway" AND logName="projects/{project_id}/logs/compute.googleapis.com%2Fnat_flows" AND timestamp>="{start_time}"' \
  --project={project_id} --limit=1 --order=desc --format=json --quiet
```

**BigQuery (`execute_sql_readonly` MCP or `bq query`)** — connection counts:

```bash
bq query --use_legacy_sql=false --format=json --project_id={project_id} '
SELECT
  JSON_VALUE(json_payload.endpoint.vm_name) AS vm_name,
  JSON_VALUE(json_payload.connection.src_ip) AS internal_ip,
  JSON_VALUE(json_payload.connection.nat_ip) AS external_nat_ip,
  JSON_VALUE(json_payload.allocation_status) AS allocation_status,
  COUNT(*) AS connection_count
FROM `{project_id}.{dataset_id}._AllLogs`
WHERE
  log_name LIKE "%/logs/compute.googleapis.com%2Fnat_flows"
  AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
GROUP BY 1, 2, 3, 4
ORDER BY connection_count DESC
LIMIT 20
'
```

## 3. Cloud NAT Monitoring Metrics (`list_timeseries` MCP or REST `curl`)

-   **Allocated New Connections**:
    `compute.googleapis.com/nat/new_connections_count` (`gce_instance`, `DELTA`
    INT64; labels: `nat_gateway_name`, `router_id`) or
    `router.googleapis.com/nat/new_connections_count` (`nat_gateway`, `DELTA`
    INT64). Sum over window with `ALIGN_SUM` + `REDUCE_SUM`.
-   **Dropped Packets & Allocation Failures**:
    `router.googleapis.com/nat/dropped_sent_packets_count` (`nat_gateway`,
    `DELTA` INT64, `metric.labels.reason`: `OUT_OF_RESOURCES`,
    `ENDPOINT_INDEPENDENCE_CONFLICT`),
    `compute.googleapis.com/nat/dropped_sent_packets_count` (`gce_instance`), and
    `router.googleapis.com/nat/nat_allocation_failed` (`nat_gateway`, `GAUGE`
    BOOL).
-   **Active Connections & Port Usage**:
    `compute.googleapis.com/nat/open_connections` and
    `compute.googleapis.com/nat/port_usage` (`gce_instance`, `GAUGE` INT64).

## Reference Documentation

-   [Cloud NAT logs and metrics](https://docs.cloud.google.com/nat/docs/monitoring.md.txt)
