# Agent Gateway authorization chain

Agent Gateway sends an egress request to IAP for agents only when this chain is
complete:

1.  An authorization policy targets the gateway.
2.  That policy delegates the decision to an authorization extension.
3.  The extension calls `iap.googleapis.com`.

If a link is missing, the extension isn't executed and Cloud Audit Logs has no
IAP entry for the request. Read every link in the project that contains Agent
Gateway.

## Contents

- [Gateway](#gateway): Lines 30-41
- [Authorization policies](#authorization-policies): Lines 43-79
- [Authorization extension](#authorization-extension): Lines 81-103
- [Enforcement mode](#enforcement-mode): Lines 105-117
- [Gateway decision logs](#gateway-decision-logs): Lines 119-145

Sources:
[Set up Agent Gateway](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/set-up-agent-gateway.md.txt),
[Delegate authorization](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/delegate-authorization.md.txt),
[Troubleshoot Agent Gateway](https://docs.cloud.google.com/gemini-enterprise-agent-platform/troubleshooting/troubleshoot-agent-gateway.md.txt),
[Troubleshoot IAM Unified Access Policies](https://docs.cloud.google.com/gemini-enterprise-agent-platform/troubleshooting/troubleshoot-iam-policies-uap.md.txt),
[Monitor Agent Gateway](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/monitor-agent-gateway.md.txt),
[Authorization extensions REST reference](https://docs.cloud.google.com/service-extensions/docs/reference/rest/v1/projects.locations.authzExtensions.md.txt).

## Gateway

```bash
gcloud network-services agent-gateways describe {gateway} \
    --location={location} --project={project_id}
```

-   Record the full `name`. Authorization policies must list it exactly.
-   `registries` lists the Agent Registry instances that the gateway uses: at
    most two, and if there are two, one is `global` and the other is regional
    or multi-regional. Look up destinations in them with
    [agent-registry.md](agent-registry.md).

## Authorization policies

```bash
gcloud network-security authz-policies list \
    --location={location} --project={project_id}
gcloud network-security authz-policies describe {authz_policy} \
    --location={location} --project={project_id}
```

The policy that delegates to IAP has these values:

| Field | Expected value |
| :--- | :--- |
| `target.resources` | Contains the gateway's full name |
| `policyProfile` | `REQUEST_AUTHZ` |
| `action` | `CUSTOM` |
| `customProvider.authzExtension.resources` | Contains the authorization extension's full name |

-   If no policy targets the gateway, the extension isn't executed. That's the
    root cause. Print the "Point the authorization policy at the gateway"
    template from [remediation-gateway.md](remediation-gateway.md).
-   If the policy names a different extension than you expect, read that
    extension. A leftover extension can still call IAP, but with another
    `iapPolicyVersion`, so that IAP evaluates the other policy model and can
    deny requests that the intended policies allow, or in `DRY_RUN`, so that
    IAP blocks nothing.
-   The authorization policy is in the same project as the extension.
-   A gateway accepts at most four authorization policies, whatever their
    profile (`REQUEST_AUTHZ` or `CONTENT_AUTHZ`). Custom policies with the
    same profile run in no guaranteed order.
-   Policies with `action: ALLOW` or `action: DENY` are the gateway's own MCP
    rules, and they can deny a request without IAP. They're evaluated after
    the `REQUEST_AUTHZ` policy that delegates to IAP, so IAP has already
    allowed any request that they deny. If `ALLOW` policies target the
    gateway, a request that matches none of them is denied. Without
    `baseProtocolMethodsOption: MATCH_BASE_PROTOCOL_METHODS`, the agent can't
    establish an MCP session.

## Authorization extension

```bash
gcloud service-extensions authz-extensions describe {authz_extension} \
    --location={location} --project={project_id}
```

| Field | Value | Meaning |
| :--- | :--- | :--- |
| `service` | `iap.googleapis.com` | The extension sends decisions to IAP for agents |
| `metadata.iapPolicyVersion` | `V2` | IAP evaluates IAM Unified Access Policies (Access policies) |
| `metadata.iapPolicyVersion` | `V1` | IAP evaluates IAP allow policies |
| `metadata.iamEnforcementMode` | `DRY_RUN` | IAP logs decisions but doesn't block requests |
| `metadata.iamEnforcementMode` | Absent or `ENFORCE` | IAP blocks the requests that it denies |
| `failOpen` | Absent or `false` | If the call to IAP fails or times out, the request fails |
| `failOpen` | `true` | If the call to IAP fails or times out, the request continues without an IAP decision |

-   `iapPolicyVersion` is required. Record it, and read only the matching
    section of [policy-model.md](policy-model.md).
-   If `service` isn't `iap.googleapis.com`, the chain doesn't reach IAP for
    agents. Report that, and stop.
-   The Agent Platform setup guides set `failOpen: false`. If it's `true`,
    report it as a risk, even when it isn't the root cause.

## Enforcement mode

-   **`DRY_RUN`:** IAP writes disallowed requests to Cloud Audit Logs but
    doesn't block them. A 403 in dry run likely comes from the gateway's
    egress proxy, such as its other authorization policies, or from the
    destination. Check the gateway logs in the next section.
-   **Requests pass that should be blocked:** the extension is in dry run, or
    no policy binding covers the gateway's project or the gateway (see
    [policy-model.md](policy-model.md)). To enforce, the user removes
    `iamEnforcementMode: "DRY_RUN"` from the extension and imports it again.
    Print the "Turn on enforcement" template from
    [remediation-gateway.md](remediation-gateway.md) only if the user asks to
    turn on enforcement. It isn't a fix for a denial.

## Gateway decision logs

Agent Gateway writes these logs in dry run too.

```bash
gcloud logging read '
  resource.type="networkservices.googleapis.com/Gateway"
  resource.labels.gateway_type="SECURE_WEB_GATEWAY"
  resource.labels.location="{location}"
  resource.labels.gateway_name="{gateway}"
  httpRequest.status=403
  -httpRequest.requestMethod="CONNECT"' \
  --project={project_id} --freshness=1d --limit=20
```

| Field | Meaning |
| :--- | :--- |
| `httpRequest.requestUrl` | The URL that the agent called. Its hostname must match a registered interface exactly |
| `jsonPayload.authzPolicyInfo.policies.result` | The overall authorization result, `ALLOWED` or `DENIED` |

-   Entries can also include `serviceExtensionsInfo`, which names the
    authorization extension that handled the request.
-   To find hostnames blocked while the agent starts, remove the
    `resource.labels.location`, `resource.labels.gateway_name`, and
    `-httpRequest.requestMethod="CONNECT"` lines.
-   Widen `--freshness` to cover the time of the failure before you conclude
    that no entry exists.
