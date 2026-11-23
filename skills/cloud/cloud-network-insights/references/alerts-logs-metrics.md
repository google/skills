# Alert Policies, Cloud Logging, and Cloud Monitoring Metrics

Use this reference for Cloud Network Insights alert policies, alarm and event
logs, and path performance metrics. Follow the rules in
[Usage Attribution](attribution.md) for every command.

## Contents

-   [1. Alarm and Event Logs](#1-alarm-and-event-logs): Lines 14-41
-   [2. Alert Policy File](#2-alert-policy-file): Lines 43-96
-   [3. Scope to One Path or Target](#3-scope-to-one-path-or-target): Lines 98-120
-   [4. Path Metrics in Cloud Monitoring](#4-path-metrics-in-cloud-monitoring): Lines 122-176

## 1. Alarm and Event Logs

Path and Monitoring Point alarms and events reach Cloud Logging as two logs on
`resource.type` `networkmanagement.googleapis.com/NetworkPath`, `.../WebPath`,
or `.../MonitoringPoint` (fields:
[Set up logging](https://docs.cloud.google.com/network-intelligence-center/docs/cloud-network-insights/set-up-logging.md.txt)).

-   **`insights_alarm`**: `jsonPayload` has `alarm_id`, `state` (`RAISED`,
    `UPDATED`, `CLEARED`), `alarm_severity` (`CRITICAL`, `MAJOR`, `MINOR`,
    `WARNING`), `alarm_type` (`QUALITY_OF_SERVICE`), `rule` (alarm rule name),
    and `noise_conditions`. Filter on `jsonPayload.alarm_severity`, not the
    LogEntry `severity` (mapped to `CRITICAL`, `ERROR`, `WARNING`, `NOTICE`).
-   **`insights_event`**: `jsonPayload.event_type` is
    `MONITORING_POINT_OFFLINE`, `MONITORING_POINT_ONLINE`, `ROUTE_CHANGE`,
    `MTU_CHANGE`, `QOS_CHANGE`, or `FORWARDING_LOSS_CLEAR`.
-   **Active alarms**: each state change is a separate entry with the same
    `jsonPayload.alarm_id`; an alarm is active only if its latest entry isn't
    `CLEARED`. `gcloud logging read` lists newest entries first and looks back
    1 day unless you set `--freshness`; an alarm raised before that window can
    still be active, so widen it and print only the fields you need. Without a
    `path_id` filter, also cap the output (for example, `--limit=500`); if it
    returns that many entries, raise the limit or filter by path:

    ```bash
    gcloud logging read 'logName =~ "insights_alarm" AND resource.labels.path_id = "PATH_ID"' \
      --project=PROJECT_ID --freshness=7d \
      --format="table(timestamp,resource.labels.path_id,jsonPayload.alarm_id,jsonPayload.state,jsonPayload.alarm_severity,jsonPayload.rule)"
    ```

## 2. Alert Policy File

Save this log-match policy as `POLICY_FILE`, fill in the placeholders (for
`FILTER`, a console template filter below, scoped as in section 3 if needed),
and run `gcloud monitoring policies create --project=PROJECT_ID
--policy-from-file=POLICY_FILE` (to delete it, follow `SKILL.md` Rule 4 and run
`gcloud monitoring policies delete POLICY_ID --project=PROJECT_ID --quiet`). It
opens an incident when a new entry matches the filter (see
[Set up alerts and notifications](https://docs.cloud.google.com/network-intelligence-center/docs/cloud-network-insights/set-up-alerts.md.txt)):

```json
{
  "displayName": "DISPLAY_NAME",
  "documentation": {"content": "NOTES_FOR_RESPONDERS", "mimeType": "text/markdown"},
  "userLabels": {"cloud-network-insights": "true"},
  "conditions": [{
    "displayName": "Log match condition",
    "conditionMatchedLog": {"filter": "FILTER"}
  }],
  "combiner": "OR",
  "alertStrategy": {"notificationRateLimit": {"period": "300s"}, "autoClose": "1800s"},
  "notificationChannels": []
}
```

-   **`userLabels`**: `"cloud-network-insights": "true"` lists the policy in
    the Cloud Network Insights alert policies view; set it on every policy.
-   **Noise**: `AND NOT jsonPayload.noise_conditions:*` skips alarms flagged
    `frequent-detection` (default: 5 alarms on the same item in 24 hours) or
    `burst-detection` (default: more than 1 per 60 minutes). Keep it unless
    the user wants noisy alarms too; event logs don't have this field.
-   **Fixed rules**: one condition, `combiner` `"OR"`, and `autoClose` of at
    least `1800s`; `notificationRateLimit.period` is the minimum time between
    notifications. Escape each `"` in `filter` as `\"`, and list channels as
    `projects/PROJECT_ID/notificationChannels/CHANNEL_ID`.
-   **Roles**: creating the policy needs
    `roles/networkmanagement.CloudNetworkInsightsViewer`,
    `roles/logging.configWriter`, `roles/monitoring.alertPolicyEditor`, and
    `roles/monitoring.notificationChannelViewer`; adding a notification channel
    also needs `roles/monitoring.notificationChannelEditor`.

Console alert template filters, starting with network path outage:

```text
resource.type = "networkmanagement.googleapis.com/NetworkPath" AND logName =~ "insights_alarm" AND (jsonPayload.alarm_severity = "MAJOR" OR jsonPayload.alarm_severity = "CRITICAL") AND jsonPayload.state = "RAISED" AND jsonPayload.alarm_type =~ "QUALITY_OF_SERVICE" AND jsonPayload.rule =~ "Outage" AND NOT jsonPayload.noise_conditions:*
```

| Template | Change to the outage filter |
| :--- | :--- |
| Network path extended loss | `jsonPayload.alarm_severity = "MAJOR"` and `jsonPayload.rule =~ "Extended loss"` |
| Network path DNS errors | `jsonPayload.alarm_severity = "MINOR"` and `jsonPayload.rule =~ "Multiple DNS errors"` |
| Web path web errors | `resource.type = "networkmanagement.googleapis.com/WebPath"`, `jsonPayload.alarm_severity = "MAJOR"`, and `jsonPayload.rule =~ "Multiple Web errors"` |
| Monitoring Point offline | Whole filter: `resource.type = "networkmanagement.googleapis.com/MonitoringPoint" AND logName =~ "insights_event" AND jsonPayload.event_type = "MONITORING_POINT_OFFLINE"` |
| Network path MTU change | Whole filter: `resource.type = "networkmanagement.googleapis.com/NetworkPath" AND logName =~ "insights_event" AND jsonPayload.event_type = "MTU_CHANGE"` |

## 3. Scope to One Path or Target

Path alarms, path events, and path metrics carry the resource label `path_id`;
add `AND resource.labels.path_id = "PATH_ID"` to scope a log query, alert
filter, or metric query to one network or web path.

1.  `PATH_ID` is the last segment of the path's `name`. List the paths to a
    target (`destination`: IP address, hostname, or URL) with this command or
    `web-paths list`; add `AND sourceMonitoringPointId=MONITORING_POINT_ID` to
    the filter to keep one source Monitoring Point:

    ```bash
    gcloud network-management network-monitoring-providers network-paths list \
      --network-monitoring-provider=PROVIDER_ID --location=global --project=PROJECT_ID \
      --filter='destination="TARGET"' --format="table(name.basename(),displayName,sourceMonitoringPointId,dualEnded)"
    ```

2.  A target can have several paths (one per source Monitoring Point, plus the
    companion `NetworkPath` of each Web policy). OR their IDs to cover all:
    `(resource.labels.path_id = "ID_1" OR resource.labels.path_id = "ID_2")`.
    Paths created later aren't covered until you add their IDs.
3.  For a Monitoring Point event, use `resource.labels.monitoring_point_id`
    with the last segment of the Monitoring Point's `name`.

## 4. Path Metrics in Cloud Monitoring

All metric types start with `networkmanagement.googleapis.com/insights/`,
followed by `network/` for network paths (resource type
`networkmanagement.googleapis.com/NetworkPath`) or `web/` for web paths
(`networkmanagement.googleapis.com/WebPath`). Both resource types have the
labels `resource_container`, `location`, `network_monitoring_provider_id`, and
`path_id`. Single-ended paths report `total/` metrics; dual-ended paths
(`dualEnded: true`) report `in/` and `out/` metrics instead.

| Suffix | Kind, unit | Meaning |
| :--- | :--- | :--- |
| `network/rtt_avg`, `network/rtt_min`, `network/rtt_max` | GAUGE, ms | Round-trip time of data and voice probes |
| `network/total/loss_percent` (or `in/`, `out/`) | GAUGE, % | Packet loss |
| `network/total/jitter` (or `in/`, `out/`) | GAUGE, ms | Packet delay variation |
| `network/test_error` | GAUGE, 0 or 1 | 1 if errors stopped the test (100% loss is a `Connect` error); labels `error_type`, `error_detail` |
| `network/data/total/packets_sent_count`, `network/data/total/packets_received_count` | DELTA, count | Data probes sent and received |
| `network/voice/total/mos` (or `in/`, `out/`) | GAUGE, score | Estimated call quality from voice probes |
| `web/http/response_time/total` (or `dns_lookup`, `tcp_connect`, `ssl_connect`, `request_wait`, `request_receive`, `redirect`) | GAUGE, ms | Total or per-phase time of the first request |
| `web/http/test_error`, `web/browser/test_error` | GAUGE, 0 or 1 | 1 if the HTTP or browser test failed; labels `error_type`, `error_detail`, `response_code` |
| `web/total_transaction_time` | GAUGE, ms | Time to run the whole workflow |

Metric labels include `destination`, `source_monitoring_point_display_name`,
and `monitoring_policy_display_name`; `metric.labels.destination = "TARGET"`
selects every path to a target without ID lookups. Full lists and charts:
[Monitoring metrics](https://docs.cloud.google.com/network-intelligence-center/docs/cloud-network-insights/monitoring-metrics.md.txt),
[networkmanagement metrics](https://docs.cloud.google.com/monitoring/api/metrics_gcp_i_o.md.txt#networkmanagement),
[View dashboards](https://docs.cloud.google.com/network-intelligence-center/docs/cloud-network-insights/view-dashboards.md.txt).

Query one metric type per `projects.timeSeries.list` call (GNU `date`; `-K`
keeps the access token out of the process list, and the token falls back to
`gcloud auth print-access-token` if Application Default Credentials aren't set
up):

```bash
GCP_TOKEN=$(gcloud auth application-default print-access-token 2>/dev/null || gcloud auth print-access-token) &&
curl -sS -G --connect-timeout 10 --max-time 30 \
  "https://monitoring.googleapis.com/v3/projects/PROJECT_ID/timeSeries" \
  -K <(printf 'header = "Authorization: Bearer %s"\n' "$GCP_TOKEN") \
  --data-urlencode 'filter=metric.type = "networkmanagement.googleapis.com/insights/network/total/loss_percent" AND resource.labels.path_id = "PATH_ID"' \
  --data-urlencode "interval.startTime=$(date -u -Iseconds -d '-6 hours')" \
  --data-urlencode "interval.endTime=$(date -u -Iseconds)" \
  --data-urlencode "aggregation.alignmentPeriod=300s" \
  --data-urlencode "aggregation.perSeriesAligner=ALIGN_MEAN" \
  --data-urlencode "view=FULL"
```

The interval is `(startTime, endTime]` in RFC 3339. `ALIGN_MEAN` suits the
GAUGE metrics; the DELTA counts (`packets_sent_count`,
`packets_received_count`) need `ALIGN_SUM` or `ALIGN_RATE`. For one value over
the whole window, set `aggregation.alignmentPeriod` to the window (`3600s` for
the past hour). Drop the `aggregation.*` lines for raw points, or add
`aggregation.crossSeriesReducer=REDUCE_MEAN` to merge paths. Each
`timeSeries[]` item has `points[]`, newest first, with `value.doubleValue` (or
`value.int64Value`, a string, for INT64 metrics).
