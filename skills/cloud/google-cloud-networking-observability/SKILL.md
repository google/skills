---
name: google-cloud-networking-observability
metadata:
  version: "1.0.8"
  category: Compute
description: >-
  Investigates Google Cloud networking issues by analyzing GCP logs, metrics, and diagnostics. Use when investigating dropped network traffic, packet drops, drop reasons, VPC Flow Logs (including Private Service Connect / PSC, serverless / App Engine Direct VPC, and cost estimation), Cloud NAT, firewall or threat logs, VPN metrics/tunnels, or Connectivity Tests for path diagnostics. Don't use for generic VM management or non-observability tasks.
---

# Google Cloud Networking Observability Expert

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## 🛑 Core Directive: Results First

1. **Single-Guide Loading**: Identify the matching guide in **Section 2** and
   read only that file before acting (plus
   [references/mcp-usage.md](references/mcp-usage.md) when MCP tools are
   available in your environment).
2. **Data & Metric Lookups**: Execute targeted queries to retrieve the requested
   data. Once obtained (including `0`, `null`, or `"No traffic"`), present it
   and stop immediately. Never query a second source (e.g., comparing BigQuery
   and Monitoring) to double-check a conclusive answer.
3. **Troubleshooting & Root-Cause Analysis**: Follow the matching guide's
   workflow to inspect control-plane configurations, logs, and metrics before
   forming conclusions. Recommend fixes with exact resource names and
   commands—**never** mutate project resources or workload state during
   investigation (except ephemeral Connectivity Tests when path verification is
   needed).

## Procedures

### 1. Environment & Source Rules

- **Prerequisites**: Target projects require an active billing account,
  authenticated SDK access (`gcloud auth login` or
  `GOOGLE_APPLICATION_CREDENTIALS`, `gcloud config set project {project_id}`,
  default region e.g. `us-central1` via
  `gcloud config set compute/region {region}`; see
  [Google Cloud CLI installation](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt)
  and [locations](https://docs.cloud.google.com/about/locations) — never install
  tools without explicit user approval), enabled APIs (`compute.googleapis.com`,
  `logging.googleapis.com`, `monitoring.googleapis.com`,
  `bigquery.googleapis.com`, `networkmanagement.googleapis.com`), and read roles
  (`roles/compute.networkViewer`, `roles/logging.viewer`,
  `roles/monitoring.viewer`, `roles/bigquery.jobUser`,
  `roles/bigquery.dataViewer`, or `roles/networkmanagement.admin` for
  Connectivity Tests).
- **BigQuery First for Volume/Top-N**: Always prefer BigQuery linked datasets
  (`_AllLogs`) over Cloud Logging for volume trends, top talkers, or
  aggregations. Never manually aggregate time-series points via the Monitoring
  API for Top-N tasks.
- **Schema & Sample Check**: Inspect a sample log record (`LIMIT 1` /
  `--limit=1 --format=json`) or fetch the guide's official `.md.txt`
  documentation URL before writing complex filters or aggregations to verify
  exact payload field paths; if `bq query` fails with schema errors, run
  `bq show --schema --format=json {project}:{dataset}.{table}` and
  `bq query --use_legacy_sql=false --dry_run`.
- **Metadata Fallback**: Subnets with `EXCLUDE_ALL_METADATA` have `NULL` VM
  names in VPC Flow Logs; filter or group by internal IP
  (`jsonPayload.connection.src_ip`) instead.
- **Tool Priority**: Prefer MCP servers
  ([references/mcp-usage.md](references/mcp-usage.md)) when declared in your
  tools; otherwise use `gcloud`/`bq`. Never use `gcloud monitoring`; use REST
  `curl` templates in [references/metrics-analysis.md](references/metrics-analysis.md).

### 2. Analysis Guides (Read Only the Single Matching Guide)

| Symptom or Task | Reference Guide |
| :--- | :--- |
| **VPC Flow Logs**: traffic volume, top talkers, latency, packet drops and loss rates, Private Service Connect (PSC / PSC-I), serverless workloads | [references/vpc-flow-analysis.md](references/vpc-flow-analysis.md) |
| **VPC Flow Logs Cost Estimation** | [references/vpc-flow-logs-cost-estimation.md](references/vpc-flow-logs-cost-estimation.md) |
| **Firewall Rules & Logs**: DENY/ALLOW hits, attributing firewall deny drops to specific rules, blocked IPs, rule shadowing | [references/firewall-analysis.md](references/firewall-analysis.md) |
| **Cloud NAT**: gateway discovery, NAT IP/port mapping audit, port exhaustion drops, allocated connection counts | [references/cloud-nat-analysis.md](references/cloud-nat-analysis.md) |
| **Threat Logs**: Cloud IDS / Firewall Plus high-severity alerts and top attackers | [references/threat-analysis.md](references/threat-analysis.md) |
| **Metrics & VPN**: internal/external RTT, VM throughput, packet loss, or Cloud VPN (`vpn_gateway` health, traffic, drops) | [references/metrics-analysis.md](references/metrics-analysis.md) |
| **Connectivity Tests**: reachability path `create`, `describe`, `delete` | [references/connectivity-tests.md](references/connectivity-tests.md) |

## Boundaries (CRITICAL)

- **Print SQL**: Always print generated SQL in the response.
- **Flow Analyzer Link**: For VPC Flow Log tasks, include
  [Google Cloud Console Flow Analyzer](https://console.cloud.google.com/net-intelligence/flow-analyzer).
- **First-Turn Time Math**: Compute relative time ranges (e.g., "12 hours ago")
  in the first turn.
