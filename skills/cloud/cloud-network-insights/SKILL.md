---
name: cloud-network-insights
metadata:
  category: Networking
  version: "1.0.1"
description: >-
  Guides and automates setup, onboarding, and synthetic monitoring operations
  for Cloud Network Insights in Google Cloud and Broadcom AppNeta. Use when
  enabling Cloud Network Insights, deploying or troubleshooting Monitoring
  Points across cloud and on-premises environments, configuring Network or Web
  monitoring policies and AppNeta alarm rules, configuring alert policies,
  querying path alarms and performance metrics, or verifying synthetic path
  reachability. Don't use for generic network observability, VPC Flow Logs,
  Cloud NAT, or VPC firewall debugging.
---

# Cloud Network Insights

## Attribution

For all `gcloud` CLI, REST API, and MCP attribution requirements when executing
commands with this skill, follow the instructions in
[Usage Attribution](references/attribution.md).

## 🛑 Core Directive: Results First

1.  **Identify the Requested Task**: Determine if the user is attempting service
    enablement, checking activation status, downloading/installing or
    troubleshooting Monitoring Points (MPs), configuring AppNeta monitoring
    policies or alarm rules, verifying provisioned resources and paths,
    configuring alert policies, or querying Cloud Logging alarms and Cloud
    Monitoring metrics.
2.  **Execute and Present**: Perform the minimum required commands or API calls
    to accomplish the task or provide exact guidance.
3.  **Definitive Answers**: For status and verification queries, report the
    definitive state (for example, `ACTIVE`, `ACTIVATING`, or path listings)
    immediately.

## Overview

Cloud Network Insights provides comprehensive synthetic monitoring for
Cross-Cloud Network observability in partnership with Broadcom AppNeta. It
monitors network and web paths using Monitoring Points (MPs) installed across
Google Cloud, on-premises data centers, other public clouds (like AWS or Azure),
and the public internet.

This skill automates onboarding, service enablement, Monitoring Point
deployment, policy creation, and path verification.

## Procedures and CUJs

### 1. Service Enablement and Status

-   **Enable API**:

    ```bash
    gcloud services enable networkmanagement.googleapis.com --project=PROJECT_ID
    ```
-   **Create Provider** (use `external` to match the Google Cloud console
    default, or a custom `PROVIDER_ID`):

    ```bash
    gcloud network-management network-monitoring-providers create PROVIDER_ID \
      --provider-type=EXTERNAL \
      --location=global \
      --project=PROJECT_ID
    ```

    > ⚠️ If this command fails due to unaccepted Terms of Service, direct the
    > user to the Google Cloud console onboarding page:
    > `https://console.cloud.google.com/net-intelligence/cloud-network-insights/onboarding?project=PROJECT_ID`
-   **Verify State**:

    ```bash
    gcloud network-management network-monitoring-providers \
      describe PROVIDER_ID \
      --location=global \
      --project=PROJECT_ID \
      --format=json
    ```

    Check that `.state` is `ACTIVE`. (`ACTIVATING` indicates the backend is
    provisioning AppNeta resources.)
-   **Delete Provider (Cleanup)**:

    ```bash
    gcloud network-management network-monitoring-providers delete PROVIDER_ID \
      --location=global \
      --project=PROJECT_ID
    ```

### 2. Monitoring Point Deployment and Verification

Cloud Network Insights supports 7 distinct Monitoring Point deployment types:
`container`, `helm`, `gce-vm`, `aws-ec2`, `azure-vm`, `vmware`, and `kvm`.

-   **Platform Selection**: Never assume a default deployment type. Identify or
    prompt the user for their target environment before proceeding.
-   **Procedures and Commands**: For all required parameters, download commands,
    deployment manifests, and status verification commands (`monitoring-points
    list`), see
    [Monitoring Point Deployment Reference](references/monitoring-point-deployment.md).

### 3. Monitoring Policy and Alarm Rule Configuration (AppNeta)

Monitoring policies configure active synthetic network and web tests executed by
Monitoring Points, and alarm rules define the thresholds and evaluation windows
that raise path alarms.

-   **Policy Types (`/api/v4/monitoringPolicy`)**:
    -   **Network Monitoring Policies**: Monitor packet loss, latency, and
        jitter to target IPs (or dual-ended between Monitoring Points) over TCP
        or UDP.
    -   **Web Monitoring Policies**: Synthetic HTTP/HTTPS application checks
        (such as GET requests with status code 200 assertions).
-   **Check Before Creating**: Always query `GET /api/v4/monitoringPolicy` first
    to verify whether a policy with your target name already exists before
    creating a new one, avoiding duplicate resource creation and API conflicts.
-   **Alarm Rules (AppNeta Web UI Only)**: Alarm rules are configured in the
    AppNeta Web UI (in **Alarms** > **Alarm Rules**; see
    [Broadcom Alarm Rules](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/alarms-set-up/alarms-rules.html))
    and are not supported via the REST API v4.
-   **Procedures and Payloads**: For authentication token generation,
    organization discovery, and REST JSON payloads, see
    [Monitoring Policy Configuration Reference](references/monitoring-policies.md).

### 4. Verifying Provisioned Paths in Google Cloud

Once policies are configured and MPs are online, verify provisioned paths:

-   **List Network Paths**:

    ```bash
    gcloud network-management network-monitoring-providers network-paths list \
      --network-monitoring-provider=PROVIDER_ID \
      --location=global \
      --project=PROJECT_ID \
      --format=json
    ```
-   **List Web Paths**:

    ```bash
    gcloud network-management network-monitoring-providers web-paths list \
      --network-monitoring-provider=PROVIDER_ID \
      --location=global \
      --project=PROJECT_ID \
      --format=json
    ```
-   **Filter by Monitoring Point**: Add
    `--filter="sourceMonitoringPointId=MONITORING_POINT_ID"` to list only paths
    sourced from a specific Monitoring Point, where `MONITORING_POINT_ID` is the
    last segment of the Monitoring Point's `name` in `monitoring-points list`.
-   **Expected Extra Paths**: Each Web policy also creates a companion
    `NetworkPath` to the target host (unless one already exists), and a newly
    deployed Monitoring Point inherits paths from existing policies whose
    `monitoringPointRules` match it.

### 5. Querying Cloud Network Insights Resources and State

1.  **Discover the Provider Name**: Run `gcloud network-management
    network-monitoring-providers list --location=global --project=PROJECT_ID`
    to retrieve the provider ID (`PROVIDER_ID`). The provider ID is `external`
    when enabled via the Google Cloud console, or a custom name if created
    manually.
2.  **Query Child Resources**: Pass
    `--network-monitoring-provider=PROVIDER_ID` and `--location=global` to
    child resource commands (such as `list` and `describe`):
    -   Monitoring Points: `gcloud network-management
        network-monitoring-providers monitoring-points [list|describe]`
    -   Network Paths: `gcloud network-management network-monitoring-providers
        network-paths [list|describe]`
    -   Web Paths: `gcloud network-management network-monitoring-providers
        web-paths [list|describe]`

### 6. Alert Policies, Cloud Logging, and Cloud Monitoring Metrics

-   **Alert Policies (`gcloud monitoring policies`)**: Create log-matched alert
    policies (`conditionMatchedLog.filter`, including
    `alertStrategy.notificationRateLimit` in `POLICY_FILE`) for path alarms and
    operational events (see
    [Set up alerts and notifications](https://cloud.google.com/network-intelligence-center/docs/cloud-network-insights/set-up-alerts)).
    For `insights_alarm` policies, include `AND NOT
    jsonPayload.noise_conditions:*` by default to filter out frequent/burst
    noise unless the user asks to include noisy alarms. Always set
    `"userLabels": {"cloud-network-insights": "true"}` in `POLICY_FILE` so the
    policy appears in the Cloud Network Insights alert policies view in the
    Google Cloud console:

    ```bash
    # Create an alert policy from a JSON or YAML file
    gcloud monitoring policies create --project=PROJECT_ID \
      --policy-from-file=POLICY_FILE

    # Delete an alert policy (for cleanup)
    gcloud monitoring policies delete POLICY_ID \
      --project=PROJECT_ID \
      --quiet
    ```

    Example `conditionMatchedLog.filter` values for Google Cloud console alert
    templates:

    -   *Network Path Outage / Extended Loss / DNS Errors*:

        ```text
        resource.type = "networkmanagement.googleapis.com/NetworkPath" AND logName =~ "insights_alarm" AND (jsonPayload.alarm_severity = "MAJOR" OR jsonPayload.alarm_severity = "CRITICAL") AND jsonPayload.state = "RAISED" AND jsonPayload.alarm_type =~ "QUALITY_OF_SERVICE" AND jsonPayload.rule =~ "Outage" AND NOT jsonPayload.noise_conditions:*
        ```

        *(Substitute `jsonPayload.rule =~ "Extended loss"` or `"Multiple DNS
        errors"` with `alarm_severity = "MINOR"` as needed.)*
    -   *Web Path Multiple Web Errors*:

        ```text
        resource.type = "networkmanagement.googleapis.com/WebPath" AND logName =~ "insights_alarm" AND jsonPayload.alarm_severity = "MAJOR" AND jsonPayload.state = "RAISED" AND jsonPayload.alarm_type =~ "QUALITY_OF_SERVICE" AND jsonPayload.rule =~ "Multiple Web errors" AND NOT jsonPayload.noise_conditions:*
        ```
    -   *Monitoring Point Offline and Network Path MTU Change Events*:

        ```text
        resource.type = "networkmanagement.googleapis.com/MonitoringPoint" AND logName =~ "insights_event" AND jsonPayload.event_type = "MONITORING_POINT_OFFLINE"
        ```

        ```text
        resource.type = "networkmanagement.googleapis.com/NetworkPath" AND logName =~ "insights_event" AND jsonPayload.event_type = "MTU_CHANGE"
        ```
-   **Cloud Logging (`gcloud logging read`)**: Query path alarms (`logName =~
    "insights_alarm"`) and operational lifecycle events (`logName =~
    "insights_event"`) exported to Cloud Logging (see
    [Set up logging](https://cloud.google.com/network-intelligence-center/docs/cloud-network-insights/set-up-logging)
    for `jsonPayload` field schemas and event types). Because alarm state
    transitions (`RAISED`, `UPDATED`, `CLEARED`) are logged as separate entries
    sharing the same `jsonPayload.alarm_id`, determine currently active alarms
    by checking that the latest entry for an `alarm_id` has not transitioned to
    `CLEARED`.
-   **Cloud Monitoring (REST API `projects.timeSeries.list`)**: Query path
    performance metrics (`NetworkPath` and `WebPath`, filtered by
    `resource.labels.path_id`) via `GET
    "https://monitoring.googleapis.com/v3/projects/PROJECT_ID/timeSeries"` with
    `Authorization: Bearer $(gcloud auth application-default
    print-access-token)` in Cloud Monitoring (see
    [Monitoring metrics](https://cloud.google.com/network-intelligence-center/docs/cloud-network-insights/monitoring-metrics)
    and
    [View dashboards](https://cloud.google.com/network-intelligence-center/docs/cloud-network-insights/view-dashboards)).

### 7. Deployment Diagnostics and Troubleshooting

To diagnose a Monitoring Point deployment across any platform:

1.  **Google Cloud Registration**: Check that `connectionStatus` is `ONLINE` in
    `monitoring-points list` (or `describe`) to verify the Monitoring Point is
    registered and connected to Cloud Network Insights.
2.  **Model-Specific Workload, Host, and Appliance Health**: Inspect the
    Monitoring Point runtime, container/Kubernetes workload, or v35 Web Admin
    status on the target platform using the model-specific troubleshooting
    guides in
    [Monitoring Point Deployment Reference](references/monitoring-point-deployment.md),
    [Broadcom Troubleshooting Monitoring Points](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/troubleshooting-section/troubleshooting.html),
    and
    [Troubleshooting Cloud Network Insights](https://cloud.google.com/network-intelligence-center/docs/cloud-network-insights/troubleshooting).
3.  **Network, Proxy, and Firewall Rules**: Verify the target environment's
    firewall, Web Proxy, custom CA certificate, and gRPC/SSL inspection bypass
    settings (`data.na1.cni.appneta.com`, `content.na1.cni.appneta.com`,
    `comms.na1.cni.appneta.com`, or `.p.` endpoints for Private Service Connect)
    against
    [Broadcom Firewall Configuration](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-firewall.html)
    and
    [Add Monitoring Points](https://cloud.google.com/network-intelligence-center/docs/cloud-network-insights/add-monitoring-points).

## Reference Documentation

For detailed guides, complete payloads, and templates:

-   [Monitoring Point Deployment Reference](references/monitoring-point-deployment.md):
    Deployment guides and command references across all 7 platforms (container,
    Helm, GCE VM Terraform, AWS, Azure, VMware, KVM).
-   [Monitoring Policy Configuration Reference](references/monitoring-policies.md):
    Network and Web monitoring policy JSON payloads and AppNeta API workflows.
-   [Google Cloud Network Insights Documentation](https://cloud.google.com/network-intelligence-center/docs/cloud-network-insights):
    Official Google Cloud documentation for Cloud Network Insights setup,
    concepts, and operations.
-   [Broadcom AppNeta for Cloud Network Insights Documentation](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA.html):
    Broadcom AppNeta monitoring points, path performance, and API guides.
