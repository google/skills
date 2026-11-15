# Networking Metrics Reference

Use Cloud Monitoring (`list_timeseries` MCP or the v3 REST API via `curl`) to
analyze network latency (RTT), VM throughput, packet drops, and Cloud VPN
gateway health.

## 1. Standard Networking & Cloud VPN Metrics

Use these monitored resource types, metric kinds, labels, and aligners directly
without querying `metricDescriptors` first:

-   **Internal & External VM Latency (`resource.type="gce_instance"`)**:
    -   `networking.googleapis.com/vm_flow/rtt` (VM-to-VM within Google Cloud)
        and `networking.googleapis.com/vm_flow/external_rtt` (internet traffic)
        — `DELTA` `DISTRIBUTION`.
    -   **Region Scoping & Peer Labels**: Local VM zone is
        `resource.labels.zone` (filter a region with
        `resource.labels.zone = starts_with("{region}-")`); peer location is
        `metric.labels.remote_region` and `metric.labels.remote_zone`.
    -   **Alignment**: Always align `DISTRIBUTION` RTT metrics with
        `perSeriesAligner=ALIGN_PERCENTILE_50` (and optional
        `crossSeriesReducer=REDUCE_MEAN` or `REDUCE_PERCENTILE_50` when
        aggregating across VMs in a region) to obtain a scalar numeric latency.
-   **Active Probing Network SLO**:
    -   `networking.googleapis.com/cloud_netslo/active_probing/rtt`
        (`DISTRIBUTION`, `ALIGN_PERCENTILE_50`) and
        `networking.googleapis.com/cloud_netslo/active_probing/probe_count`.
-   **VM Throughput & Packets (`resource.type="gce_instance"`)**:
    -   `compute.googleapis.com/instance/network/sent_bytes_count`,
        `received_bytes_count`, `sent_packets_count`, `received_packets_count`
        — `DELTA` `INT64` (`ALIGN_SUM` or `ALIGN_RATE`).
-   **Cloud VPN Gateways & Tunnels (`resource.type="vpn_gateway"`)**:
    -   **Gateway Discovery**:
        ```bash
        gcloud compute vpn-gateways list --project={project_id}
        gcloud compute target-vpn-gateways list --project={project_id}
        gcloud compute vpn-tunnels list --project={project_id}
        ```
    -   **Labels**: `resource.labels.{gateway_id, region, project_id}`,
        `metric.labels.{gateway_name, tunnel_name}`.
    -   **Tunnel Health**: `vpn.googleapis.com/tunnel_established` (`GAUGE`
        `DOUBLE`, `ALIGN_MEAN`; values `> 0` indicate an established tunnel).
    -   **Traffic Volume**: `vpn.googleapis.com/network/sent_bytes_count` and
        `vpn.googleapis.com/network/received_bytes_count` (`DELTA` `INT64`,
        `ALIGN_SUM` + `REDUCE_SUM` grouped by `metric.labels.gateway_name` or
        `metric.labels.tunnel_name`).
    -   **Packet Drops**:
        `vpn.googleapis.com/network/dropped_sent_packets_count` and
        `vpn.googleapis.com/network/dropped_received_packets_count` (`DELTA`
        `INT64`, `ALIGN_SUM` + `REDUCE_SUM`).

## 2. REST API Query Pattern (`curl`)

When Cloud Monitoring MCP (`list_timeseries`) is unavailable, query the v3 REST
API directly (never use `gcloud monitoring`):

```bash
curl -s -G \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://monitoring.googleapis.com/v3/projects/{project_id}/timeSeries" \
  --data-urlencode 'filter=metric.type="{metric_type}" AND resource.type="{resource_type}"' \
  --data-urlencode "interval.startTime={start_time}" \
  --data-urlencode "interval.endTime={end_time}" \
  --data-urlencode "aggregation.alignmentPeriod=3600s" \
  --data-urlencode "aggregation.perSeriesAligner=ALIGN_PERCENTILE_50"
```

## 3. Dynamic Metric Discovery (Unlisted Metrics Only)

Only query `metricDescriptors` (`list_metric_descriptors` MCP or REST `curl`)
when investigating a metric not listed above:

```bash
curl -s -G \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://monitoring.googleapis.com/v3/projects/{project_id}/metricDescriptors" \
  --data-urlencode 'filter=metric.type=starts_with("{prefix}")' \
  | jq -r '.metricDescriptors[] | "\(.type) (\(.metricKind)/\(.valueType)): \(.description)"'
```

## Reference Documentation

-   [Cloud VPN logs and metrics](https://docs.cloud.google.com/network-connectivity/docs/vpn/how-to/viewing-logs-metrics.md.txt)
