# Cloud Audit Logs for IAP egress decisions

IAP for agents writes each egress authorization decision to Cloud Audit Logs as
a Data Access audit log entry. Data Access audit logs are off by default for
most services, so check the configuration before you trust an empty result.

## Contents

- [Check whether Data Access audit logs are on](#check-whether-data-access-audit-logs-are-on): Lines 21-39
- [Find IAP egress decisions](#find-iap-egress-decisions): Lines 41-72
- [Fields to record](#fields-to-record): Lines 74-98
- [What the signals mean](#what-the-signals-mean): Lines 100-124

Sources:
[Configure Data Access audit logs](https://docs.cloud.google.com/logging/docs/audit/configure-data-access.md.txt),
[Troubleshoot Agent Gateway](https://docs.cloud.google.com/gemini-enterprise-agent-platform/troubleshooting/troubleshoot-agent-gateway.md.txt),
[Monitor Agent Gateway](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/monitor-agent-gateway.md.txt),
[IAP roles and permissions](https://docs.cloud.google.com/iam/docs/roles-permissions/iap.md.txt),
[Logging query language](https://docs.cloud.google.com/logging/docs/view/logging-query-language.md.txt).

## Check whether Data Access audit logs are on

```bash
gcloud projects get-iam-policy {project_id} --format="json(auditConfigs)"
```

1.  The logs are on for IAP egress if the `iap.googleapis.com` and
    `allServices` entries in `auditConfigs` turn on all three Data Access log
    types between them: `ADMIN_READ`, `DATA_READ`, and `DATA_WRITE`. A type
    that either entry turns on counts.
2.  If any type is missing, check for an inherited setting before you conclude
    that the logs are off. A folder or organization can also turn the logs on,
    and this command shows only the project's own policy. Run the IAP decision
    query in the next section with `--freshness=30d`. If any IAP egress entry
    exists, the logs are on.
3.  Otherwise, the logs are off. Stop, explain that past requests weren't
    recorded, print the "Enable Data Access audit logs for IAP" template from
    [remediation-setup.md](remediation-setup.md), and ask the user to
    reproduce the failure after they apply it.

## Find IAP egress decisions

Read the logs of the project that contains Agent Gateway:

```bash
gcloud logging read '
  protoPayload.serviceName="iap.googleapis.com"
  protoPayload.authorizationInfo.permission:"egressViaIAP"' \
  --project={project_id} --freshness=1d --limit=20
```

The logged permission name varies by release:
`iap.googleapis.com/resources.egressViaIAP` or `iap.resources.egressViaIAP`
for Access policies (V2), and `iap.webServiceVersions.egressViaIAP` for IAP
allow policies (V1). Keep the `:` substring match, because an exact `=` match
on one name can return nothing.

Add one of these lines inside the filter to narrow the result. Field names
differ between releases and entry layouts, so the dry-run and version filters
test every known name:

| Filter line | Returns |
| :--- | :--- |
| `protoPayload.status.code!=0` | Denied decisions, enforced or dry run |
| `(protoPayload.metadata.dryRun=true OR protoPayload.request.dryRun=true OR protoPayload.metadata.iamEnforcementMode="DRY_RUN")` | Decisions logged in dry run, which IAP didn't enforce |
| `(protoPayload.metadata.policy_version="POLICY_VERSION_V2" OR protoPayload.metadata.iapPolicyVersion="v2")` | Decisions evaluated against Access policies |
| `protoPayload.request.httpRequest.url:"{host}"` | Decisions for one destination host |
| `protoPayload.metadata.mcp_attributes.base_protocol_method="true"` | MCP base-protocol requests only |

A narrow `--freshness` window can return zero rows even when entries exist.
Before you conclude that no entry exists, widen `--freshness` to cover the time
of the failure.

## Fields to record

Entries use different field layouts. Check each name in the order listed.

| Field | Meaning |
| :--- | :--- |
| `protoPayload.authorizationInfo[].granted` | `true` if IAP allowed the request, `false` if it denied it |
| `protoPayload.authenticationInfo.principalSubject` | The caller's SPIFFE ID or `principal://` identity. Copy a `principal://` value exactly. For a SPIFFE ID, see [topology-agent-gateway.md](topology-agent-gateway.md#agent-principal) |
| `protoPayload.metadata.destination.agent_registry.resource_id` | The registered destination that the request resolved to, such as `projects/{project_id}/locations/{location}/endpoints/{endpoint_id}`. It uses the project ID. Older entries put the destination in `protoPayload.authorizationInfo[].resource` instead |
| `protoPayload.metadata.destination.unregistered` | Present, with `host`, `path`, and `method`, when the hostname isn't registered in Agent Registry. Older entries show `unregisteredResource` in `labels."iap.googleapis.com/audited_resource_name"` instead, and some IAP allow policy (V1) entries show a name that ends in `unregisteredEndpoint` there, with no `metadata.destination` |
| `protoPayload.request.httpRequest.url`, `protoPayload.requestMetadata.requestAttributes.host` and `.path` | The URL that the agent called |
| `protoPayload.metadata.dryRun`, `protoPayload.request.dryRun`, or `protoPayload.metadata.iamEnforcementMode` | `true` or `DRY_RUN` means IAP logged the decision but didn't block the request. A dry-run entry can show `granted: true` for a request that the policies don't allow |
| `protoPayload.metadata.policy_version`, `protoPayload.request.policy_version`, or `protoPayload.metadata.iapPolicyVersion` | The policy model that IAP evaluated. `POLICY_VERSION_V2` or `v2` means Access policies |
| `protoPayload.status.code` | Non-zero for a denied request |

-   `authorizationInfo[].resource` and `audited_resource_name` can name the
    Agent Gateway rather than the destination. Read the destination from
    `metadata.destination` when it's present.
-   `metadata.unsatisfied_access_levels` also appears on granted entries.
    Don't report it as a cause of an egress denial.

Some Access policy (V2) entries include CEL evaluation details. Use them to
find the part of the condition that didn't match. Most entries have none, so
compare `resource_id` or the `unregistered` values with each literal in the
condition yourself.

## What the signals mean

-   **Entry with `granted: false`, not dry run:** IAP denied the request.
    Check the policy model and rules.
-   **Entry with `dryRun: true` or `iamEnforcementMode: DRY_RUN`:** IAP didn't
    block the request. A 403 in dry run likely comes from the gateway's egress
    proxy or from the destination. The entry's `granted` value doesn't show
    whether a policy allows the request, so compare the policies with the
    request (SKILL.md Steps 3-4) to find whether IAP would deny it once
    enforced. If requests pass that should be blocked, check which extension
    the gateway's authorization policy calls (see
    [gateway-setup.md](gateway-setup.md)).
-   **Entry with `granted: true`, not dry run:** IAP allowed the request. Look
    at the gateway decision and the destination.
-   **Many destinations denied at once, including the agent's own model call**
    (`{location}-aiplatform.mtls.googleapis.com` `generateContent`), often with
    `iamcredentials` and `telemetry` hosts: the rule doesn't match for any
    request. Check the principal and every registry name literal in the
    condition (SKILL.md Step 4) before you look at single hosts. The agent
    fails before it runs any tool, so the URL that the user reported might not
    appear in the logs.
-   **No entry for the request, logs on:** the gateway might have denied the
    request before IAP evaluated it, for example because the authorization
    chain is incomplete or another `REQUEST_AUTHZ` policy denied it first.
    Check the chain in [gateway-setup.md](gateway-setup.md).
