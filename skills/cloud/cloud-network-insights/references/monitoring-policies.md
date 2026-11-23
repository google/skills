# Monitoring Policy Configuration Reference (AppNeta API)

This guide covers creating and deleting Network and Web Monitoring Policies
(`/api/v4/monitoringPolicy`), and deleting Monitoring Point records
(`/api/v4/monitoringPoint`), with the Broadcom AppNeta REST API v4.

## Contents

-   [1. Set Up AppNeta API Access](#1-set-up-appneta-api-access): Lines 18-95
-   [2. Network Monitoring Policies](#2-network-monitoring-policies): Lines 99-164
-   [3. Web Monitoring Policies](#3-web-monitoring-policies): Lines 168-222
-   [4. Delete Policies and Monitoring Point Records](#4-delete-policies-and-monitoring-point-records): Lines 226-261
-   [5. Policy Script](#5-policy-script): Lines 265-438
    -   [AppNeta Web UI](#appneta-web-ui): Lines 372-385
    -   [Proxy VM](#proxy-vm): Lines 387-438
-   [6. Troubleshooting](#6-troubleshooting): Lines 442-461

## 1. Set Up AppNeta API Access

Run these steps in order. `WORK_DIR` is a private directory created with
`mktemp -d`, and `PROVIDER_ID` is `external` when Cloud Network Insights was
enabled in the Google Cloud console.

1.  **AppNeta host** (`APPNETA_HOST`, such as `google.na1.cni.appneta.com`). It
    isn't a secret, so reuse the literal value in later commands:

    ```bash
    gcloud network-management network-monitoring-providers describe PROVIDER_ID \
      --location=global --project=PROJECT_ID --format="value(providerUri)"
    ```

2.  **Reachability probe**, once and without a token:

    ```bash
    curl -sS -o /dev/null -w '%{http_code}\n' --connect-timeout 10 --max-time 15 \
      "https://APPNETA_HOST/api/v4/organization"
    ```

    -   Any HTTP code, including `401`, means AppNeta is reachable: run the
        [policy script](#5-policy-script) yourself
        (or the steps below one at a time).
    -   `000` with curl exit code 6, 7, or 28 (DNS failure, connection refused,
        or timeout) means your environment can't reach AppNeta. Stop the
        AppNeta work here and don't retry. Give the user three choices in one
        message: the [AppNeta web UI](#appneta-web-ui) steps, the filled-in
        [policy script](#5-policy-script) to run themselves, or a
        [proxy VM](#proxy-vm) that you create and run the script from. Then
        continue with the rest of the task.

3.  **Provider access token** in a private curl config file. The token wraps
    your Google Cloud access token and expires with it (about one hour; see
    [Exchange tokens](https://docs.cloud.google.com/network-intelligence-center/docs/cloud-network-insights/access-appneta-api.md.txt#exchange-tokens));
    without a signed-in `gcloud` account, the command falls back to
    Application Default Credentials. This form keeps the token out of command
    lines and output; never run the token commands without the redirect, and
    never print the file:

    ```bash
    gcloud network-management network-monitoring-providers generate-provider-access-token \
      PROVIDER_ID --location=global --project=PROJECT_ID \
      --gcp-access-token="$(gcloud auth print-access-token 2>/dev/null || gcloud auth application-default print-access-token)" \
      --format="value(providerAccessToken)" \
      | sed 's/.*/header = "Authorization: Bearer &"/' > WORK_DIR/appneta-auth
    test -s WORK_DIR/appneta-auth || echo "No provider access token; see the gcloud error above."
    ```

4.  **Organization ID** (`ORG_ID`). The response is an array of every
    organization the token can access (one per Cloud Network Insights project),
    so select this project's organization by `name` (or match
    `externalAccountId` to the project number) instead of taking the first
    `id`:

    ```bash
    curl -sS --connect-timeout 10 --max-time 30 -K WORK_DIR/appneta-auth \
      "https://APPNETA_HOST/api/v4/organization" \
      | jq '.[] | select(.name == "PROJECT_ID") | {id, name, externalAccountId}'
    ```

    If `jq` fails with an error such as `Cannot index number`, the response is
    an error object: rerun the call without `jq` to read it (for `401`, see
    [Troubleshooting](#6-troubleshooting)).

Every later call starts with the same
`curl -sS --connect-timeout 10 --max-time 30 -K WORK_DIR/appneta-auth` options;
add `-H "Content-Type: application/json"` when you send a body. Never add `-v`,
`--verbose`, or `--trace`: they print the `Authorization` header. Without `jq`,
filter the JSON with any JSON tool, such as `python3 -c`, the same way.

-   **Reference Documentation**:
    -   [Broadcom AppNeta REST API v4 Documentation](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/api/api-v4.html):
        Authentication headers, organization/policy/Monitoring Point ID lookup,
        and valid `APPNETA_MP_TYPE` values.
    -   **OpenAPI 3.0 Spec**:
        `https://APPNETA_HOST/api/openapi.json?version=v4` (or Swagger UI at
        `https://APPNETA_HOST/api/swagger/index.html#/`).

--------------------------------------------------------------------------------

## 2. Network Monitoring Policies

1.  **Check Existing Policies**: Query `GET /api/v4/monitoringPolicy` first to
    verify whether a policy with the target `name` already exists. The list
    includes policies from every organization the token can access, so look
    only at your `ORG_ID`, and pipe the response straight into the filter
    rather than pasting it into a script, where quoting errors can silently
    skip the check:

    ```bash
    curl -sS --connect-timeout 10 --max-time 30 -K WORK_DIR/appneta-auth \
      "https://APPNETA_HOST/api/v4/monitoringPolicy" \
      | jq --argjson org ORG_ID '[.[] | select(.orgId == $org) | {id, name, target}]'
    ```

2.  **Create Network Monitoring Policy**: If the name isn't listed, save the
    payload below as `WORK_DIR/POLICY_NAME.json` and send it:

    ```bash
    curl -sS --connect-timeout 10 --max-time 30 -K WORK_DIR/appneta-auth \
      -X POST -H "Content-Type: application/json" --data @WORK_DIR/POLICY_NAME.json \
      "https://APPNETA_HOST/api/v4/monitoringPolicy"
    ```

```json
{
  "orgId": ORG_ID,
  "name": "POLICY_NAME",
  "description": "DESCRIPTION",
  "monitoringEnabled": true,
  "target": "TARGET_IP",
  "networkMonitoring": {
    "dualEnded": false,
    "networkProtocol": "TCP",
    "networkPathGroupName": "Default"
  },
  "webHttpMonitoring": null,
  "monitoringPointRules": [
    {
      "filterRule": {
        "type": {
          "values": ["APPNETA_MP_TYPE"],
          "exclude": false
        }
      }
    }
  ]
}
```

-   `target`: An IP address or hostname without a scheme (for example,
    `8.8.8.8`).
-   `dualEnded`: `false` (single-ended against a target IP) or `true`
    (dual-ended between two AppNeta Monitoring Points).
-   `networkProtocol`: `"TCP"` (default) or `"UDP"`.
-   `APPNETA_MP_TYPE`: Must match the AppNeta Monitoring Point type string
    (such as `"c50 Container"`, `"Google CE"`, or `"v35 Virtual"`; the `type`
    field in `monitoring-points list` shows it — see
    [Monitoring Point Types](https://techdocs.broadcom.com/us/en/ca-enterprise-software/it-operations-management/appneta-for-google-cloud-network-insights/GA/api/api-v4.html#title-appneta-api_monitoring-point-types)).
-   `monitoringPointRules`: A `type` filter applies the policy to every
    Monitoring Point of that type in the organization. To scope the policy to
    specific Monitoring Points, such as the one the user named, filter by
    Monitoring Point name instead:
    `"filterRule": {"name": {"values": ["MP_NAME"], "exclude": false}}`, where
    `MP_NAME` is the `displayName` of the Monitoring Point in `monitoring-points
    list`.

--------------------------------------------------------------------------------

## 3. Web Monitoring Policies

After checking `GET /api/v4/monitoringPolicy` (Section 2, step 1), create an
HTTP/HTTPS synthetic web policy with the Section 2 `POST` command and the
following JSON payload:

```json
{
  "orgId": ORG_ID,
  "name": "POLICY_NAME",
  "description": "DESCRIPTION",
  "monitoringEnabled": true,
  "target": "TARGET_URL",
  "networkMonitoring": {
    "dualEnded": false,
    "networkProtocol": "TCP",
    "networkPathGroupName": "Default"
  },
  "webHttpMonitoring": {
    "method": "GET",
    "intervalMinutes": 5,
    "timeoutSeconds": 60,
    "ignoreSslValidation": false,
    "followRedirects": true,
    "assertions": [
      {
        "type": "statuscode",
        "value": "200"
      }
    ]
  },
  "monitoringPointRules": [
    {
      "filterRule": {
        "type": {
          "values": ["APPNETA_MP_TYPE"],
          "exclude": false
        }
      }
    }
  ]
}
```

-   `target`: The full URL including the scheme (for example,
    `https://1.1.1.1`); the companion `NetworkPath` probes its host. Before
    relying on a `200` assertion, confirm the URL returns it (for example,
    `curl -sL --connect-timeout 10 --max-time 15 -o /dev/null
    -w '%{http_code}' -- "TARGET_URL"` from a host with internet access).
-   `networkMonitoring`: Required on Web Monitoring Policies (`null` returns
    `HTTP 400: Network Monitoring must be specified.`). The policy creates a
    `WebPath` plus a companion `NetworkPath` to the target host
    (`relatedNetworkPathId`) unless one already exists.
-   `monitoringPointRules`: To limit the policy to specific Monitoring Points,
    use the `name` filter from Section 2.

--------------------------------------------------------------------------------

## 4. Delete Policies and Monitoring Point Records

Deletions are permanent: deleting a policy removes its paths, and deleting a
Monitoring Point record also deletes the paths it sources and their history.
Look up the IDs, show the user exactly what you'll delete, and send the
`DELETE` calls only after an explicit yes (`SKILL.md` Rule 4), one call per
ID. Never reuse IDs from memory or from another organization: the token also
sees other projects' organizations, whose policies and records can share
names.

1.  **Policies**: list this organization's policies and their IDs (Section 2,
    step 1).
2.  **Monitoring Point records**: list this organization's records with their
    IDs and status (each `id` is also the last segment of the Monitoring
    Point's `name` in `monitoring-points list`):

    ```bash
    curl -sS --connect-timeout 10 --max-time 30 -K WORK_DIR/appneta-auth \
      "https://APPNETA_HOST/api/v4/monitoringPoint?orgId=ORG_ID&limit=1000" \
      | jq --argjson org ORG_ID '[.[] | select(.orgId == $org) | {id, name, connectionStatus}]'
    ```

3.  **Delete** each confirmed policy or record by its ID, and a record only
    after its host is gone and it shows `OFFLINE`:

    ```bash
    curl -sS --connect-timeout 10 --max-time 30 -K WORK_DIR/appneta-auth -X DELETE \
      -o /dev/null -w '%{http_code}\n' "https://APPNETA_HOST/api/v4/monitoringPolicy/POLICY_ID"
    curl -sS --connect-timeout 10 --max-time 30 -K WORK_DIR/appneta-auth -X DELETE \
      -o /dev/null -w '%{http_code}\n' "https://APPNETA_HOST/api/v4/monitoringPoint/MP_ID"
    ```

    A `2xx` code means deleted, and `404` means already gone. On `401`, repeat
    Section 1, step 3 once and retry.
4.  **Verify** with a fresh list, and with `network-paths list`, `web-paths
    list`, or `monitoring-points list`.

--------------------------------------------------------------------------------

## 5. Policy Script

This script creates policies, or lists them, by name in this project's
organization; it never deletes anything (deletions follow Section 4). It checks
for existing policies before creating, mints its own token (or reads it from
standard input with `--auth-stdin`), keeps the token in memory, and never
prints it or writes it to a file. Use it in one of three ways:

-   **AppNeta reachable**: save it as `WORK_DIR/cni-policies.sh` and run
    `bash WORK_DIR/cni-policies.sh` yourself.
-   **AppNeta unreachable, the user runs it**: paste the complete filled-in
    script into your reply as a code block, for the user to run from a machine
    that has a signed-in `gcloud`, `curl`, `jq`, and HTTPS access to
    `APPNETA_HOST`. A path to a file in your environment doesn't help: the user
    runs it elsewhere. The script contains no tokens or keys.
-   **AppNeta unreachable, the user picks a proxy VM**: see
    [Proxy VM](#proxy-vm).

Replace `PROJECT_ID`, `PROVIDER_ID`, and `APPNETA_HOST` at the top, then edit
only the last lines: one `create_policy NAME TARGET MP_NAME network|web` line
per policy (network targets are bare IPs or hostnames, web targets are full
URLs, and `MP_NAME` is the Monitoring Point's `displayName`), or
`list_policies` to show this organization's policies.

```bash
#!/bin/bash
# Creates Cloud Network Insights monitoring policies in AppNeta, or lists this
# project's policies. It never deletes anything.
# Usage: bash cni-policies.sh [--auth-stdin]
set -euo pipefail
PROJECT_ID="PROJECT_ID"
PROVIDER_ID="PROVIDER_ID"
API="https://APPNETA_HOST/api/v4"

# Provider access token, kept in memory and never printed. With --auth-stdin
# (on a proxy VM), it's read from standard input instead of minted here.
TOKEN=""
if [ "${1:-}" = "--auth-stdin" ]; then
  IFS= read -r TOKEN || true
else
  GCP_TOKEN=$(gcloud auth print-access-token 2>/dev/null \
    || gcloud auth application-default print-access-token)
  TOKEN=$(gcloud network-management network-monitoring-providers \
    generate-provider-access-token "$PROVIDER_ID" --location=global \
    --project="$PROJECT_ID" --gcp-access-token="$GCP_TOKEN" \
    --format="value(providerAccessToken)")
fi
[ -n "$TOKEN" ] || { echo "No provider access token." >&2; exit 1; }
auth() { printf 'header = "Authorization: Bearer %s"\n' "$TOKEN"; }

api() {  # api [CURL_OPTIONS...] URL: prints the response body; fails on HTTP errors
  local out code
  out=$(curl -sS --connect-timeout 10 --max-time 30 -K <(auth) \
    -H "Content-Type: application/json" -w '\n%{http_code}' "$@") || true
  code=${out##*$'\n'}
  out=${out%$'\n'*}
  case "$code" in
    2??) printf '%s\n' "$out" ;;
    *) echo "HTTP ${code:-error}: $out" >&2; return 1 ;;
  esac
}

# This project's organization; the token can see one organization per project.
ORG_ID=$(api "$API/organization" \
  | jq -e --arg p "$PROJECT_ID" 'first(.[] | select(.name == $p) | .id)') \
  || { echo "Could not find the AppNeta organization for $PROJECT_ID." >&2; exit 1; }
echo "AppNeta organization for $PROJECT_ID: $ORG_ID"

list_policies() {  # list_policies: this organization's policies (id, name, target)
  api "$API/monitoringPolicy" \
    | jq -c --argjson org "$ORG_ID" '.[] | select(.orgId == $org) | {id, name, target}'
}

policy_ids() {  # policy_ids NAME: IDs of the policies with that name in this organization
  api "$API/monitoringPolicy" \
    | jq -r --argjson org "$ORG_ID" --arg n "$1" \
        '.[] | select(.orgId == $org and .name == $n) | .id'
}

create_policy() {  # create_policy NAME TARGET MP_NAME network|web
  case "${4:-}" in
    network|web) ;;
    *) echo "Usage: create_policy NAME TARGET MP_NAME network|web" >&2; return 1 ;;
  esac
  local existing
  existing=$(policy_ids "$1")  # set -e stops here on API errors
  if [ -n "$existing" ]; then echo "exists: $1"; return 0; fi
  jq -n --argjson org "$ORG_ID" --arg name "$1" --arg target "$2" \
      --arg mp "$3" --arg kind "$4" '{
    orgId: $org, name: $name, description: "Cloud Network Insights policy",
    monitoringEnabled: true, target: $target,
    networkMonitoring: {dualEnded: false, networkProtocol: "TCP",
                        networkPathGroupName: "Default"},
    webHttpMonitoring: (if $kind == "web" then {method: "GET",
      intervalMinutes: 5, timeoutSeconds: 60, ignoreSslValidation: false,
      followRedirects: true, assertions: [{type: "statuscode", value: "200"}]}
      else null end),
    monitoringPointRules: [{filterRule: {name: {values: [$mp], exclude: false}}}]
  }' | api -X POST --data @- "$API/monitoringPolicy" | jq -c '{id, name, target}'
  echo "created: $1"
}

# Edit below: one line per policy.
create_policy "POLICY_NAME" "TARGET" "MP_NAME" network
# list_policies
```

### AppNeta Web UI

Give these steps, filled in, when the user creates or deletes policies in the
AppNeta web UI (get `PROJECT_NUMBER` with `gcloud projects describe PROJECT_ID
--format="value(projectNumber)"`):

1.  Open the monitoring policies page that the Google Cloud console links to:
    `https://APPNETA_HOST/pvc/monitoringPolicies.html?project=PROJECT_NUMBER`.
2.  Add one policy per request: a **Network** policy with the target IP or
    host (such as `8.8.8.8`), or a **Web** policy with the full URL (such as
    `https://1.1.1.1`) and a `200` status check. Name it `POLICY_NAME` and
    choose only the Monitoring Point `MP_NAME` as its source. To delete a
    policy, delete it on the same page.
3.  Check the result with `network-paths list` and `web-paths list`.

### Proxy VM

Use this only after the user picks it (`SKILL.md` Rule 6). Their choice
approves a small billable VM and a firewall rule that allows SSH only from
Identity-Aware Proxy. The token is minted in your environment and reaches the
VM only on standard input, so never put it in a command argument, file,
startup script, metadata, or the serial console.

1.  Create the VM with outbound internet access, no service account, and `jq`,
    plus the IAP-only SSH rule:

    ```bash
    gcloud compute instances create cni-proxy --project=PROJECT_ID --zone=ZONE \
      --machine-type=e2-small --image-family=debian-12 \
      --image-project=debian-cloud --network=NETWORK --subnet=SUBNET \
      --tags=cni-proxy --no-service-account --no-scopes \
      --metadata=startup-script='export DEBIAN_FRONTEND=noninteractive; apt-get update && apt-get -o DPkg::Lock::Timeout=300 install -y jq'
    gcloud compute firewall-rules create cni-proxy-iap-ssh --project=PROJECT_ID \
      --network=NETWORK --direction=INGRESS --allow=tcp:22 \
      --source-ranges=35.235.240.0/20 --target-tags=cni-proxy
    ```

2.  Copy the filled-in script (it holds no tokens), wait up to 3 minutes for
    the startup script to install `jq` (if it's still missing, read the VM's
    serial port output and tell the user), then run the script with the token
    on standard input:

    ```bash
    gcloud compute scp WORK_DIR/cni-policies.sh cni-proxy:~ --zone=ZONE \
      --project=PROJECT_ID --tunnel-through-iap --quiet
    gcloud compute ssh cni-proxy --zone=ZONE --project=PROJECT_ID \
      --tunnel-through-iap --quiet \
      --command='for i in $(seq 1 36); do command -v jq && break; sleep 5; done; command -v jq'
    gcloud network-management network-monitoring-providers \
      generate-provider-access-token PROVIDER_ID --location=global \
      --project=PROJECT_ID \
      --gcp-access-token="$(gcloud auth print-access-token 2>/dev/null || gcloud auth application-default print-access-token)" \
      --format="value(providerAccessToken)" \
      | gcloud compute ssh cni-proxy --zone=ZONE --project=PROJECT_ID \
          --tunnel-through-iap --quiet --command='bash cni-policies.sh --auth-stdin'
    ```

3.  In your final summary, ask whether to delete the VM and its firewall rule
    or keep them for later policy changes, and delete them only after the user
    answers:

    ```bash
    gcloud compute instances delete cni-proxy --zone=ZONE --project=PROJECT_ID \
      --quiet
    gcloud compute firewall-rules delete cni-proxy-iap-ssh --project=PROJECT_ID \
      --quiet
    ```

--------------------------------------------------------------------------------

## 6. Troubleshooting

-   **`401 Unauthorized`**: The provider token expired, or it was minted from a
    stale Google Cloud token. Repeat Section 1, step 3 (or rerun the script)
    once, then retry. If AppNeta still returns `401`, stop and tell the user
    their options: mint the Google Cloud token with
    `gcloud auth application-default print-access-token` instead (on hosts with
    certificate-based access, `gcloud auth print-access-token` returns a
    certificate-bound token, which exchanges into an AppNeta token that gets
    `401`), sign in again with `gcloud auth login`, or mint the Google Cloud
    token as a service account that has
    `roles/networkmanagement.CloudNetworkInsightsEditor` on the project (which
    requires `roles/iam.serviceAccountTokenCreator` on that service account).
    Never create service accounts, grant roles, or impersonate an account
    yourself.
-   **`400 Network Monitoring must be specified.`**: A Web policy needs a
    non-null `networkMonitoring` block (Section 3).
-   **Timeouts (curl exit code 28), DNS errors (6), or refused connections
    (7)**: Your environment can't reach AppNeta. Don't retry; give the user
    the three choices in Section 1, step 2.
