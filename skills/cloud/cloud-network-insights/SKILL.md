---
name: cloud-network-insights
metadata:
  category: Networking
  version: "2.0.0"
description: >-
  Guides and automates setup, onboarding, synthetic monitoring operations, and
  cleanup for Cloud Network Insights in Google Cloud and Broadcom AppNeta. Use
  when enabling Cloud Network Insights, deploying or troubleshooting Monitoring
  Points across cloud and on-premises environments, configuring Network or Web
  monitoring policies and AppNeta alarm rules, configuring alert policies,
  querying path alarms and performance metrics, verifying synthetic path
  reachability, removing specific or all Monitoring Points, monitoring
  policies, and their hosts, or turning Cloud Network Insights off (only after
  warning the user and getting an explicit yes). Don't use for generic network
  observability, VPC Flow Logs, Cloud NAT, or VPC firewall debugging.
---

# Cloud Network Insights

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Task Router

Cloud Network Insights runs synthetic network and web tests from Monitoring
Points (MPs) that report to Broadcom AppNeta. Find the user's task, run its
check-first command, and follow only the linked steps.

| Task | Check first | Steps |
| :--- | :--- | :--- |
| Enable Cloud Network Insights or check its status | `providers list` | [1. Enable](#1-enable-cloud-network-insights) |
| Deploy a container (c50) MP or the Compute Engine appliance | `monitoring-points list` | [2. Deploy](#2-deploy-monitoring-points) |
| Deploy an MP on Kubernetes, AWS, Azure, VMware, or KVM | `monitoring-points list` | [Platform Summary](references/monitoring-point-deployment.md#2-platform-summary) |
| Create Network or Web monitoring policies | AppNeta reachability probe | [3. Policies](#3-monitoring-policies-and-alarm-rules) |
| Verify Monitoring Points and paths | `monitoring-points list` | [4. Verify](#4-verify-monitoring-points-and-paths) |
| Remove specific policies or Monitoring Points, or everything you set up | `monitoring-points list`; list and confirm first (Rule 4) | [5. Clean Up](#5-clean-up) |
| Turn Cloud Network Insights off | `providers list`; warn and ask first (Rule 4) | [Turning Off](#turning-cloud-network-insights-off) |
| Alert policies, alarm logs, and path metrics | `gcloud monitoring policies list` | [6. Alerts](#6-alert-policies-cloud-logging-and-cloud-monitoring-metrics) |
| Troubleshoot a Monitoring Point | `monitoring-points describe` | [7. Troubleshoot](#7-troubleshoot-monitoring-points) |

Check-first commands (`PROVIDER_ID` is `external` when Cloud Network Insights
was enabled in the Google Cloud console):

```bash
gcloud network-management network-monitoring-providers list --location=global --project=PROJECT_ID
gcloud network-management network-monitoring-providers monitoring-points list \
  --network-monitoring-provider=PROVIDER_ID --location=global --project=PROJECT_ID
```

## Rules

1.  **Confirm the project** and pass `--project=PROJECT_ID` to every command.
    Without a user preference, use region `us-central1` and zone
    `us-central1-a` (others:
    [Google Cloud locations](https://cloud.google.com/about/locations)).
2.  **Automate first.** Run `gcloud`, `curl`, and `ssh` yourself whenever your
    environment and the user allow them, and prefer them to console pages.
    Hand a step to the user only when it needs a browser you don't have (the
    Broadcom terms in the Google Cloud console, the AppNeta web UI) or an
    endpoint is unreachable from your environment; give the exact URL, clicks
    or commands, and success signal. Start independent long-running work
    (such as VM creation) first, and put every question and console step you
    need (names, approvals, terms) in one message.
3.  **Accept third-party terms only with the user's consent.** The first time
    Cloud Network Insights is turned on in a project, someone must accept the
    Broadcom End User Agreement in the Google Cloud console. Deploying the
    Compute Engine appliance with `gcloud` (the default) or Terraform has no
    terms step; only the Google Cloud Marketplace page shows its listing's
    terms, so use it only when the user asks for Marketplace. Unless the
    user's message explicitly pre-approved accepting all Terms of Service
    (general task instructions and CLI auto-approve flags don't count), stop
    before accepting any terms and ask: without a browser tool, give the
    console URL and clicks for the user to accept; with one, summarize the
    main points of the terms shown in the console, say that the full text
    there is what applies, and accept only after an explicit yes. Why:
    accepting terms binds the user to a legal agreement.
4.  **Delete only after an explicit yes.** Before deleting VMs, deployments,
    firewall rules, policies, or Monitoring Point records, list exactly what
    you'll delete (each name with its ID, zone, or AppNeta organization), say
    it's permanent, and wait for a yes. Skip the question only if the user
    already confirmed that list or explicitly said to delete those items
    without asking (a general "work end to end" doesn't count). Then delete
    exactly those items, each by name or ID, never by looping over search
    results. Turning Cloud Network Insights off is irreversible: it deletes
    the project's AppNeta organization and every Monitoring Point record,
    policy, path, alert policy, and their history, but not the Monitoring
    Point VMs or containers; give these warnings and the console steps first
    ([Turning Off](#turning-cloud-network-insights-off)). Never disable
    `networkmanagement.googleapis.com`: Connectivity Tests and other Network
    Intelligence Center features use it. Why: `--quiet` skips gcloud's own
    delete prompt, and an AppNeta deletion also erases its paths' history.
5.  **Keep secrets private.** Run `mktemp -d` once and use the printed path as
    `WORK_DIR` for install bundles, `mp-config` files, and tokens. Never print,
    echo, or paste tokens, device keys, bundles, or `mp-config` contents, not
    even a few lines with `head`. Monitoring Point VMs hold their device key or
    bundle in instance metadata, so describe them only with a `--format` that
    leaves out `metadata`, such as `--format="value(name,status)"`. Never use
    `curl -v`, `--verbose`, or `--trace` on AppNeta calls (they print the
    token), and run `gcloud auth print-access-token` (or its
    `application-default` form) and `generate-provider-access-token` only
    inside `$(...)`, piped, or redirected to a file, as this skill shows.
6.  **Call AppNeta directly first.** Run AppNeta API calls from your own
    environment. Only if AppNeta is unreachable from there, give the user
    their choices in one message: the AppNeta web UI steps, the filled-in
    policy script to run themselves, or a small proxy VM that you create in
    the project to run the calls from. Create the proxy VM only if the user
    picks it, send the token to it only on standard input, and ask in your
    final summary whether to delete the VM or keep it. Why: the token acts as
    the user, and anyone who can read a VM can read its metadata and disk.
7.  **Ask before** creating billable VMs or clusters, changing packages on an
    existing host, or opening inbound firewall rules (single-ended tests need
    none; never `0.0.0.0/0` or TCP 22 without explicit approval). Never create
    service accounts, impersonate accounts, change IAM, or run `gcloud auth
    login` yourself; if a permission is missing, name the role the user needs.
8.  **Report only what you verified.** Every state you report (`ACTIVE`,
    `ONLINE`, `OFFLINE`, created, deleted) must come from a command you ran in
    this session.

## Prerequisites

-   **gcloud CLI**: If `gcloud` is missing, point the user to
    [Install the gcloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt)
    instead of installing it yourself, and give console steps until it's
    installed. The AppNeta API scripts also need `curl` and `jq`.
-   **Authentication and Billing**: On authentication errors, ask the user to
    run `gcloud auth login`, or `gcloud auth application-default login` where
    a command falls back to Application Default Credentials. The project needs
    an active billing account; see
    [Network Intelligence Center pricing](https://cloud.google.com/products/network-intelligence-center/pricing).
-   **IAM Roles**: First enablement (accepting the Broadcom terms) needs
    `roles/networkmanagement.CloudNetworkInsightsAdmin` plus
    `roles/serviceusage.serviceUsageAdmin`; managing providers, bundles, and
    policies needs `roles/networkmanagement.CloudNetworkInsightsEditor`;
    read-only queries need `roles/networkmanagement.CloudNetworkInsightsViewer`.
    Monitoring Point VMs also need Compute Engine roles:
    `roles/compute.instanceAdmin.v1` for the default `gcloud` path (others:
    [Compute Engine Appliance](references/monitoring-point-deployment.md#4-compute-engine-appliance)),
    and a proxy VM's firewall rule needs `roles/compute.securityAdmin`.

## 1. Enable Cloud Network Insights

1.  Enable the API. It's idempotent, so run it even if it may be enabled:

    ```bash
    gcloud services enable networkmanagement.googleapis.com --project=PROJECT_ID
    ```

    If it fails because the Google Cloud Terms of Service aren't accepted, ask
    the user to sign in to the Google Cloud console once and accept them.
2.  Run the `providers list` check-first command. If a provider is listed,
    note its ID as `PROVIDER_ID` and go to step 5.
3.  If none is listed, try to create it. This works only if the Broadcom
    terms were accepted in this project before (for example, before someone
    turned Cloud Network Insights off), and then `PROVIDER_ID` is `external`:

    ```bash
    gcloud network-management network-monitoring-providers create external \
      --provider-type=EXTERNAL --location=global --project=PROJECT_ID
    ```

    If it fails with `Terms of Service not accepted` (code 9), go to step 4.
4.  The Broadcom End User Agreement must be accepted in the console, which
    `gcloud` can't do (Rule 3). Without a browser tool, ask the user to open
    `https://console.cloud.google.com/net-intelligence/cloud-network-insights/onboarding?project=PROJECT_ID`,
    click **Enable**, check the Broadcom agreement, click **Accept**, and
    reply when the page says it's enabled, even if they told you to accept
    all terms. With a browser tool, open that page, summarize the agreement's
    main points, say that the console's full text is what applies, and click
    **Accept** only after an explicit yes (or at once if the user told you in
    advance to accept all terms). Accepting creates the provider `external`,
    so don't run `create` afterwards; say that you'll then confirm it in
    `providers list` and wait for `ACTIVE` (step 5).
5.  Poll every 15 seconds until the state is `ACTIVE`, usually 30-60 seconds
    after the terms are accepted (`ACTIVATING` means AppNeta is provisioning).
    `providerUri` is the AppNeta host (`APPNETA_HOST`):

    ```bash
    gcloud network-management network-monitoring-providers describe PROVIDER_ID \
      --location=global --project=PROJECT_ID --format="value(state,providerUri)"
    ```

## 2. Deploy Monitoring Points

There are 7 deployment types: `container` (c50), `helm`, `gce-vm` (Compute
Engine appliance), `aws-ec2`, `azure-vm`, `vmware`, and `kvm`. Never assume a
type: each one installs differently and measures from a different place, so
ask which environment the user wants to measure from. The VM or host name
becomes the Monitoring Point name (`HOSTNAME`).

1.  Create `WORK_DIR` if needed and run the `monitoring-points list`
    check-first command. If `HOSTNAME` is already listed, even as `OFFLINE`,
    pick an unused name (ask first if the user chose it).
2.  Follow the matching path in the
    [Monitoring Point Deployment Reference](references/monitoring-point-deployment.md):

    | Situation | Path |
    | :--- | :--- |
    | Container MP on a new Compute Engine VM (default on Google Cloud; no SSH needed) | [Path B: startup script](references/monitoring-point-deployment.md#path-b-new-compute-engine-vm-no-ssh) |
    | Container MP on an existing Linux host that you can log in to | [Path A: existing host](references/monitoring-point-deployment.md#path-a-existing-host) |
    | Compute Engine appliance | [Step 1: `gcloud`](references/monitoring-point-deployment.md#step-1-gcloud); Terraform or Google Cloud Marketplace only if the user asks |
    | Kubernetes, AWS, Azure, VMware, or KVM | [Platform Summary](references/monitoring-point-deployment.md#2-platform-summary) |

    Deploy the Compute Engine appliance yourself with `gcloud`. Don't ask the
    user to open Google Cloud Marketplace or to accept its terms: this path
    has no terms step. Use the Marketplace page only when the user asks for it
    ([Step 3](references/monitoring-point-deployment.md#step-3-google-cloud-marketplace)).
3.  Wait for `connectionStatus: ONLINE` with the polling loop below:

    | After | Poll every | Usually `ONLINE` |
    | :--- | :--- | :--- |
    | Container `setup.sh install` on a host | 10 seconds | Within 30 seconds |
    | Container VM created with the startup script | 30 seconds | About 2-3 minutes |
    | Appliance VM created | 30 seconds | About 3 minutes |

### Wait for a Monitoring Point State

Run each wait as this one blocking command. It prints the list every 30
seconds and stops when `HOSTNAME` shows `STATE` (`ONLINE` after a deployment,
`OFFLINE` after a host deletion), for at most 10 minutes. For several
Monitoring Points, chain one `echo "$s" | grep -q ...` test per `HOSTNAME` with
`&&` before `break`. Don't run separate `sleep` commands or check a background
task's status while it runs; if your tool backgrounds it, wait for its
completion message.

```bash
for i in $(seq 1 20); do
  s=$(gcloud network-management network-monitoring-providers monitoring-points list \
    --network-monitoring-provider=PROVIDER_ID --location=global --project=PROJECT_ID \
    --format="value(displayName,connectionStatus)")
  echo "$s"
  echo "$s" | grep -q "^HOSTNAME[[:space:]]*STATE$" && break
  sleep 30
done
```

## 3. Monitoring Policies and Alarm Rules

Monitoring policies (`/api/v4/monitoringPolicy`, AppNeta REST API v4) define
the tests: **Network** policies measure loss, latency, and jitter to an IP or
host over TCP or UDP; **Web** policies run HTTP/HTTPS checks such as a `GET`
with a `200` assertion. Alarm rules exist only in the AppNeta web UI
(**Alarms** > **Alarm Rules**; see
[Broadcom Alarm Rules](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/alarms-set-up/alarms-rules.html)),
not the REST API v4.

1.  Probe the AppNeta API once from your environment, with a short timeout
    (`APPNETA_HOST` is the `providerUri` from [1. Enable](#1-enable-cloud-network-insights),
    step 5):

    ```bash
    curl -sS -o /dev/null -w '%{http_code}\n' --connect-timeout 10 --max-time 15 \
      "https://APPNETA_HOST/api/v4/organization"
    ```

    -   **Any HTTP code** (`401` is normal here): AppNeta is reachable. Run the
        [policy script](references/monitoring-policies.md#5-policy-script)
        yourself.
    -   **`000`, curl exit code 6, 7, or 28**: AppNeta is unreachable from your
        environment. Don't retry. Fill in the script (step 2) and give the
        user three choices in one message (Rule 6): (a) create the policies in
        the AppNeta web UI with the
        [UI steps](references/monitoring-policies.md#appneta-web-ui), filled
        in; (b) run the complete filled-in script, pasted as a Markdown code
        block (it holds no tokens or keys; never just a path to a file in your
        environment), from a machine with `gcloud`, `curl`, `jq`, and HTTPS
        access to `APPNETA_HOST`; or (c) let you create a small proxy VM in the
        project and run the script from it
        ([Proxy VM](references/monitoring-policies.md#proxy-vm)). Then
        continue with the rest of the task.
2.  Fill in the script with one `create_policy NAME TARGET MP_NAME network|web`
    line per policy. It picks this project's organization by name, skips names
    that already exist there, and scopes each policy to one Monitoring Point.
    For custom payloads, use the
    [step-by-step calls](references/monitoring-policies.md#1-set-up-appneta-api-access).
3.  On `HTTP 401`, rerun the script once; it mints a fresh token (tokens last
    about one hour). If `401` persists, stop and give the user the options:
    `gcloud auth application-default print-access-token` as the Google Cloud
    token (certificate-bound user tokens exchange into AppNeta tokens that get
    `401`), signing in again with `gcloud auth login`, or a token from a
    service account that has
    `roles/networkmanagement.CloudNetworkInsightsEditor`. Never create service
    accounts, impersonate, or change IAM yourself.
4.  Confirm the new paths with `network-paths list` and `web-paths list`
    ([4. Verify](#4-verify-monitoring-points-and-paths)).

## 4. Verify Monitoring Points and Paths

1.  **Monitoring Points**: `connectionStatus` must be `ONLINE`.
2.  **Network and Web Paths**:

    ```bash
    gcloud network-management network-monitoring-providers network-paths list \
      --network-monitoring-provider=PROVIDER_ID --location=global --project=PROJECT_ID --format=json
    gcloud network-management network-monitoring-providers web-paths list \
      --network-monitoring-provider=PROVIDER_ID --location=global --project=PROJECT_ID --format=json
    ```

3.  **Filter by Monitoring Point**: Add
    `--filter="sourceMonitoringPointId=MONITORING_POINT_ID"` (the last segment
    of the Monitoring Point's `name` in `monitoring-points list`).
4.  **Expected Extra Paths**: Each Web policy also creates a companion
    `NetworkPath` to the target host (unless one already exists), and a newly
    deployed Monitoring Point inherits paths from existing policies whose
    `monitoringPointRules` match it.

## 5. Clean Up

Match the scope to the request, and touch nothing that this setup didn't
create:

| Request | Do |
| :--- | :--- |
| Delete specific policies or Monitoring Points | [Targeted Cleanup](#targeted-cleanup) only |
| Remove everything you set up, keep Cloud Network Insights on | [Full Cleanup](#full-cleanup) |
| Turn Cloud Network Insights off | [Turning Off](#turning-cloud-network-insights-off), with no per-resource cleanup first |

### Targeted Cleanup

Inventory only the named items (Full Cleanup, step 1), confirm them (step 2),
and then:

-   **A monitoring policy**: delete it by ID (step 3), then confirm that its
    paths are gone with `network-paths list` and `web-paths list`.
-   **A Monitoring Point**: delete only its host (step 4), wait until it's
    `OFFLINE` (step 5), and delete its record (step 6). Its paths go with the
    record; policies stay unless the user asks you to delete them.

### Full Cleanup

Cloud Network Insights stays enabled. Follow this order; each step depends on
the previous one.

1.  **Inventory** before deleting anything: run `monitoring-points list`,
    `network-paths list`, `web-paths list`, `gcloud compute instances list`,
    `gcloud compute firewall-rules list`, and, if anything came from Google
    Cloud Marketplace, `gcloud infra-manager deployments list
    --location=REGION` (all with `--project=PROJECT_ID`). Then run the AppNeta
    probe ([3. Policies](#3-monitoring-policies-and-alarm-rules), step 1); if
    AppNeta is reachable, look up the IDs of this organization's policies and
    Monitoring Point records
    ([Delete by ID](references/monitoring-policies.md#4-delete-policies-and-monitoring-point-records)).
2.  **Confirm** (Rule 4): reply with what you'll delete: the policies (name
    and ID), hosts (VMs with their zone, deployments, firewall rules), and
    Monitoring Point records (name and ID), and wait for a yes. Leave out
    anything this setup didn't create, or ask about it.
3.  **Delete the monitoring policies** you listed, one `DELETE` call per ID
    ([Delete by ID](references/monitoring-policies.md#4-delete-policies-and-monitoring-point-records));
    `404` means already deleted. If AppNeta is unreachable, give the user the
    AppNeta web UI steps in the reply template below instead.
4.  **Delete the Monitoring Point hosts** you listed. Delete a Marketplace
    deployment with `gcloud infra-manager deployments delete DEPLOYMENT
    --location=REGION --project=PROJECT_ID --quiet` (it also removes its VM
    and firewall rules), and other VMs as shown below; for Terraform, Helm,
    and hosts that stay, see
    [Host Cleanup](references/monitoring-point-deployment.md#6-host-cleanup):

    ```bash
    gcloud compute instances delete HOSTNAME_1 HOSTNAME_2 --zone=ZONE --project=PROJECT_ID --quiet
    ```

5.  **Wait for `OFFLINE`**: Monitoring Points turn `OFFLINE` about 4-5 minutes
    after their host is deleted. Poll every 30 seconds with
    [the polling loop](#wait-for-a-monitoring-point-state) (`STATE` =
    `OFFLINE`). If one is still `ONLINE` after 8 minutes, tell the user it will
    turn `OFFLINE` shortly, and continue.
6.  **Delete the Monitoring Point records** you listed, one `DELETE` call per
    ID, with the AppNeta API (`gcloud` and the Google Cloud console can't
    delete them), each only once it's `OFFLINE`; keep one that isn't
    `OFFLINE` yet and delete it later. `404` means already deleted. On `401`,
    mint a new token once; on `403`, name the role the user needs (Rule 7).
    If AppNeta is unreachable, give the user the AppNeta web UI steps in the
    reply template below instead (get `PROJECT_NUMBER` with `gcloud projects
    describe PROJECT_ID --format="value(projectNumber)"`).
7.  **Verify and report**: Re-run `monitoring-points list` and `instances
    list`, then reply with this template, filled in, in this order:

```markdown
1. Monitoring policies: deleted NAME (ID), ... in AppNeta organization ORG_ID.
   [If AppNeta was unreachable instead: open
   https://APPNETA_HOST/pvc/monitoringPolicies.html?project=PROJECT_NUMBER and
   delete NAME_1 and NAME_2 there.]
2. Hosts: deleted VM_NAMES / DEPLOYMENT / FIREWALL_RULES.
3. Monitoring Point records: deleted HOSTNAME_1 (ID), ... with the AppNeta API
   [; kept HOSTNAME (not OFFLINE yet)].
   [If AppNeta was unreachable instead: open
   https://APPNETA_HOST/pvc/monitoringPoints.html?project=PROJECT_NUMBER, open
   the menu next to each OFFLINE Monitoring Point (HOSTNAME_1, HOSTNAME_2),
   click Delete, and confirm.] Check that they're gone with:
   gcloud network-management network-monitoring-providers monitoring-points list --network-monitoring-provider=PROVIDER_ID --location=global --project=PROJECT_ID
4. Cloud Network Insights is still enabled. Turning it off is irreversible (it
   deletes the AppNeta organization and every Monitoring Point record, policy,
   path, alert policy, and their history). I can do it after you confirm, or
   you can: in the Google Cloud console, open Network Intelligence Center >
   Cloud Network Insights > Settings, click Disable product, type disable, and
   click Confirm.
```

### Turning Cloud Network Insights Off

Turning it off deletes every policy, path, and Monitoring Point record by
itself, so don't delete policies, wait for `OFFLINE`, or delete records first.

1.  Unless the user's request already acknowledged these points, reply with
    them and wait for an explicit yes (Rule 4):
    -   It's irreversible. It deprovisions the project's AppNeta organization
        and deletes every Monitoring Point record, network path, web path,
        monitoring policy, Cloud Network Insights alert policy, and their
        history. Turning it back on needs new Monitoring Points and policies.
    -   It doesn't delete Monitoring Point VMs or containers; that's a
        separate next step, and they're billed until deleted.
    -   To do it yourself: in the Google Cloud console, open
        **Network Intelligence Center** > **Cloud Network Insights** >
        **Settings**, click **Disable product**, type `disable`, and click
        **Confirm**. If the project has a Cloud Network Insights subscription,
        this doesn't cancel it.

    Ask whether you should turn it off now and then delete the Monitoring
    Point hosts you created, naming them.
2.  After an explicit yes, run this (the console does the same; `--force` also
    deletes the Monitoring Point records and paths), then confirm that
    `providers list` is empty:

    ```bash
    gcloud network-management network-monitoring-providers delete PROVIDER_ID \
      --location=global --project=PROJECT_ID --force --quiet
    ```

3.  Then delete the Monitoring Point hosts and firewall rules you named (Full
    Cleanup, step 4) if the user agreed; otherwise list them as still billed.

## 6. Alert Policies, Cloud Logging, and Cloud Monitoring Metrics

Follow [Alerts, Logs, and Metrics](references/alerts-logs-metrics.md) for the
alert policy file, path scoping, log queries, and metric queries. Always:

-   Set `"userLabels": {"cloud-network-insights": "true"}` in alert policies so
    they appear in the Cloud Network Insights alert policies view.
-   Add `AND NOT jsonPayload.noise_conditions:*` to `insights_alarm` alert
    policy filters unless the user asks to include noisy alarms.
-   Treat an alarm as active only if the latest entry for its
    `jsonPayload.alarm_id` isn't `CLEARED`.

## 7. Troubleshoot Monitoring Points

1.  **Google Cloud Registration**: Check that `connectionStatus` is `ONLINE` in
    `monitoring-points list` (or `describe`).
2.  **Workload, Host, and Appliance Health**: Inspect the Monitoring Point
    runtime, container or Kubernetes workload, startup-script log (serial port
    output), or v35 Web Admin status (log in to its Web Admin UI) with the
    model-specific guides in
    [Monitoring Point Deployment Reference](references/monitoring-point-deployment.md),
    [Broadcom Troubleshooting Monitoring Points](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/troubleshooting-section/troubleshooting.html), and
    [Troubleshooting Cloud Network Insights](https://docs.cloud.google.com/network-intelligence-center/docs/cloud-network-insights/troubleshooting.md.txt).
3.  **Network, Proxy, and Firewall Rules**: Verify the target environment's
    firewall, Web Proxy, custom CA certificate, and gRPC/SSL inspection bypass
    settings (`data.na1.cni.appneta.com`, `content.na1.cni.appneta.com`,
    `comms.na1.cni.appneta.com`, or `.p.` endpoints for Private Service Connect)
    against [Broadcom Firewall Configuration](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/appliance-firewall.html) and
    [Add Monitoring Points](https://docs.cloud.google.com/network-intelligence-center/docs/cloud-network-insights/add-monitoring-points.md.txt).

## 8. Before Reporting

1.  Send one summary, after the last step. Re-run `monitoring-points list`
    (and `providers describe` or `instances list`), and report only its states.
2.  List what you created or deleted (VMs, firewall rules, policies, and
    Monitoring Point records, with names, IDs, and `ORG_ID`; a `404` confirmed
    absent) and what the user still has to do, each with its exact script,
    commands, or click path.
3.  Note that Monitoring Point VMs, disks, and external IPs are billed by
    Compute Engine until deleted, and delete `WORK_DIR` when you're done.
4.  If you created a proxy VM for AppNeta calls, ask whether to delete it (and
    its firewall rule) or keep it for later policy changes.

## Reference Documentation

-   [Google Cloud Network Insights Documentation](https://docs.cloud.google.com/network-intelligence-center/docs/cloud-network-insights/overview.md.txt)
-   [Broadcom AppNeta for Cloud Network Insights Documentation](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA.html)
