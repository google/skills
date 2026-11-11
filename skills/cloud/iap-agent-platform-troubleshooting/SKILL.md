---
name: iap-agent-platform-troubleshooting
metadata:
  version: "1.0.0"
  category: Security
description: >-
  Diagnoses Identity-Aware Proxy (IAP) denials of outbound requests
  from Gemini Enterprise Agent Platform agents that run on Agent Runtime and
  send traffic through Agent Gateway. Use when an agent request fails
  with "Egress request is not authorized", when Cloud Audit Logs show an IAP
  egressViaIAP decision with granted false, when IAP audit entries are missing
  while debugging agent egress, or when Access policies, IAP allow policies,
  policy bindings, or Agent Registry entries might block agent egress. Don't
  use for Gemini model IAM permission errors (such as
  aiplatform.endpoints.predict), Agent Platform API errors, or Agent Runtime
  deployment or 500 errors (use agent-platform-troubleshooting instead). Don't
  use for setting up, creating, or connecting an Agent Gateway, or for IAP web
  apps, IAP TCP forwarding, or SSH.
---

# IAP troubleshooting for Gemini Enterprise Agent Platform

Find out why Identity-Aware Proxy (IAP) denies a request from a Gemini
Enterprise Agent Platform agent, and print the smallest fix for the
user to run.
This skill supports Agent Runtime (Reasoning Engine) agents that use agent
identity and send traffic through Agent Gateway.

## Operating contract

-   **Read only.** Run only the read commands in this skill and its
    references (`describe`, `list`, `get-iam-policy`,
    `search-target-policy-bindings`, and `logging read`), or the matching
    read-only MCP tools (see [Tool selection](#tool-selection)). The setup
    commands in [prerequisites.md](references/prerequisites.md) change only
    local CLI settings.
-   **Print fixes, never run them.** Don't run a command that creates,
    imports, updates, binds, enables, or deletes anything, even if the user
    asks you to. Print the remediation template for the root cause (see
    [Report](#report)), and let the user run it. Access policies and IAP allow
    policies apply to every agent whose traffic goes through Agent Gateway in
    that project, so a wrong change can block or expose other agents.
-   **Evidence first.** Copy principals, resource names, and hostnames from
    command output. Don't build them from memory.
-   **Stop on missing access.** If a read fails with `PERMISSION_DENIED`,
    report the missing role instead of working around it.

## Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read [Usage Attribution](references/attribution.md). For commands executed
directly in the terminal (never in generated scripts, Terraform, or user code),
prefix `gcloud` with
`CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:iap-agent-platform-troubleshooting)"`
and append `agent-skills/1.0 (skill:iap-agent-platform-troubleshooting)` to
`User-Agent` headers.

## Tool selection

Prefer the read tools of a connected Google Cloud remote MCP server over the
matching `gcloud` read, because remote MCP servers apply IAM, authentication,
and audit logging to every call. Use `gcloud` for any read that no connected
MCP server covers.

-   **Cloud Logging:** run the log queries with `list_log_entries`. The
    queries in the references use `gcloud` syntax, so adapt each one: set
    `resourceNames` to `projects/{project_id}`, keep the filter, replace
    `--freshness` with a `timestamp>=` clause in the filter, and set
    `orderBy` to `timestamp desc` and `pageSize` to the `--limit` value.
    Don't pass `gcloud` flags such as `--freshness` to the tool.
-   **Agent Registry:** resolve destinations with its read tools, such as
    `list_endpoints`, `get_endpoint`, `list_mcp_servers`, and
    `get_mcp_server`.
-   **Cloud CLI:** run the `gcloud` reads in this skill through
    `run_gcloud_command`.
-   **IAP, Agent Gateway, and authorization policies:** no remote MCP server
    covers these, so read them with `gcloud`, directly or through the Cloud
    CLI MCP server.

The read-only contract covers MCP tools too: never call a tool that creates,
updates, or deletes anything, such as `create_binding` or `delete_service`.

## Prerequisites

The Google Cloud CLI must be
[installed](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt) and
authenticated for `{project_id}`. Load
[prerequisites.md](references/prerequisites.md) if it isn't, or when a read
fails with `PERMISSION_DENIED` or a disabled API. It covers
`gcloud auth login`, the APIs, the read-only roles, billing, and the default
region (`us-central1`). The diagnosis creates no resources, so there's nothing
to clean up.

## Required context

Collect these values. Ask the user for any that are missing.

| Value | Source |
| :--- | :--- |
| `{project_id}`, `{project_number}` | The agent's project, and the gateway's project if it's different |
| `{location}` | Region of the agent and Agent Gateway |
| `{engine_id}` | ID of the Agent Runtime agent |
| `{gateway}` | The Agent Gateway that carries the agent's traffic |
| Destination URL | The exact URL that the agent called |
| Error text and time | The agent's logs or the user's report |
| `{org_id}` | Needed only for the optional principal access boundary check |

If the agent and Agent Gateway are in different projects, use the agent's
project number in principals. Use the gateway's project for the gateway, its
authorization policies and extension, Access policies, and policy bindings. Run
the IAP audit query in the gateway's project, and in the agent's project if it
returns nothing.

Load [topology-agent-gateway.md](references/topology-agent-gateway.md) to
confirm the topology, the principal format, the agent log query, and 403
errors during startup. If the agent doesn't run on Agent Runtime behind Agent
Gateway, say that the topology isn't supported yet, and stop.

## Step 0: Classify the failure

Load [audit-logs.md](references/audit-logs.md). Run the IAP decision query for
the time of the failure, and match the entry to the request by principal,
destination, and time. Use the first row that matches. An IAP entry outranks
the error text, because the entry records the decision itself.

| Signal | Meaning | Next |
| :--- | :--- | :--- |
| IAP entry with `granted: false`, not dry run | IAP denied the request | Step 1, then Steps 2-4 |
| IAP entry with `dryRun: true` or `iamEnforcementMode: DRY_RUN` | IAP logged the decision but didn't block the request. A 403 comes from the gateway or the destination | Step 1, then Steps 2-4: find the source of any 403, and whether IAP would deny the request once enforced |
| IAP entry with `granted: true` | IAP allowed the request | Step 2, then the destination |
| No IAP entry, and the error is an IAM permission error on a model or Agent Platform API call, such as `aiplatform.endpoints.predict` denied | Not an IAP egress denial | Stop, and name `agent-platform-troubleshooting` |
| No IAP entry for the request | Data Access audit logs are off, or the gateway denied the request before IAP | Step 1 (logs check), then Step 2 |

## Step 1: Check telemetry

1.  Run the Data Access check in [audit-logs.md](references/audit-logs.md). If
    the logs are off, explain that past requests weren't recorded, print the
    "Enable Data Access audit logs for IAP" template, and stop until the user
    reproduces the failure.
2.  From the matching entry, record `principalSubject`, the destination, the
    policy version, and the CEL evaluation details if the entry has them. Read
    each from the field names in the fields table of
    [audit-logs.md](references/audit-logs.md), because entries use different
    layouts. The destination is `metadata.destination` when it's present, not
    `authorizationInfo[].resource`, which can name the gateway.
3.  If the entry has `metadata.destination.unregistered`, or
    `audited_resource_name` is `unregisteredResource` or ends in
    `unregisteredEndpoint`, the destination counts as unregistered: the hostname
    isn't registered, or, for an MCP server, the called tool isn't in its tool
    spec (see [agent-registry.md](references/agent-registry.md)). Keep that for
    Step 4.

## Step 2: Check the gateway chain

Load [gateway-setup.md](references/gateway-setup.md). Read the gateway, its
authorization policies, and its authorization extension.

-   If no authorization policy with `policyProfile: REQUEST_AUTHZ` lists the
    gateway in `target.resources`, the extension isn't executed and no IAP
    entry exists. That's the root cause.
-   Read the extension that the policy names, not the one you expect. Its
    `service` must be `iap.googleapis.com`. Record `metadata.iapPolicyVersion`,
    `metadata.iamEnforcementMode`, and `failOpen`, because they decide which
    policies IAP evaluates, whether it blocks, and whether a request passes
    when the call to IAP fails or times out.

## Step 3: Check policies and bindings

Load [policy-model.md](references/policy-model.md), and use the section for the
version from Step 2.

-   **V2 (Access policies):** read every policy bound to the project or the
    gateway, because a deny rule in any of them wins and a policy without a
    binding isn't enforced.
-   **V1 (IAP allow policies):** look for `roles/iap.egressor` granted to the
    agent's principal, or to a principal set that contains it, in the
    registry-wide policy and in the destination's own policy. A resource
    inherits the registry-wide grants, so a grant at either level applies.
-   **Allowed but still denied:** check principal access boundary policies
    (needs `{org_id}`) and principal set membership (see
    [topology-agent-gateway.md](references/topology-agent-gateway.md)).

## Step 4: Check the rule match

Load [cel-attributes.md](references/cel-attributes.md) and
[agent-registry.md](references/agent-registry.md).

1.  **Principal:** the rule lists the agent's exact `principal://` identifier,
    or a `principalSet://` that contains the agent: same trust domain, and the
    agent's project number or platform attribute, as listed in the principal set
    table of [topology-agent-gateway.md](references/topology-agent-gateway.md).
    If `principalSubject` holds a SPIFFE ID, build the identifier as described
    there. A project ID in place of the project number, in either form, or a URN
    identifier, never matches.
2.  **Destination:** resolve the URL in Agent Registry.
    -   Registered: the condition names the registry resource with `==` or
        `in`, exactly as the audit entry's `resource_id` or the Agent Registry
        list output shows it.
    -   Unregistered, Access policies (V2) only: the condition matches the
        host, the path, and the method (see
        [cel-attributes.md](references/cel-attributes.md)). IAP allow policies
        (V1) can't allow an unregistered destination: register it, and grant
        `roles/iap.egressor` only if no registry-wide grant covers the agent.
3.  **Condition:** for V2, use the CEL evaluation details from the audit entry
    to find the clause that failed. If the entry has no evaluation details,
    compare the entry's `resource_id` or `unregistered` values with each
    literal in the condition yourself.

## Report

Load only the remediation reference for the root cause:

| Root cause | Load |
| :--- | :--- |
| Data Access audit logs are off, or an API is disabled | [remediation-setup.md](references/remediation-setup.md) |
| The authorization policy doesn't target the gateway, or calls the wrong extension | [remediation-gateway.md](references/remediation-gateway.md) |
| An Access policy (V2) rule doesn't match or a DENY rule matches, a binding is missing, or the organization policy constraint blocks the binding | [remediation-access-policies.md](references/remediation-access-policies.md) |
| An IAP allow policy (V1) grant is missing, the destination or a hostname variant isn't registered, or an MCP tool is missing from the server's tool spec | [remediation-registry.md](references/remediation-registry.md) |

Use this template:

```markdown
## Root cause
{root_cause_quoting_the_mismatched_value}

## Fix (you run this)
{why_smallest_change}
{filled_in_template}
Required role: {role}

## Wait time
{wait_time}

## Verify
- [ ] Reproduce the request.
- [ ] A new IAP audit entry shows granted: true for {principal} and {destination_url}.
- [ ] {read_command_that_confirms_the_change}
```

In dry run, IAP blocks nothing yet. Say so in the root cause, and say that its
logged denials are the requests that enforcement would block, because users
run dry run to find these requests before they enforce. If the user needs the
request to succeed and the policies wouldn't allow it once enforced, print
that fix under "Before you turn on enforcement". Verify it with a read
command, because a dry-run entry's `granted` value doesn't show whether a
policy allows the request.

If the evidence doesn't prove one root cause, list what you checked, what's
still unknown, and the next read command. Don't print a fix.

## Validation loop

Before you send the report, check every item. If one fails, fix the report
and check again.

-   [ ] No command or MCP tool call that you made changed a resource. Every
    fix is printed for the user.
-   [ ] The fix is additive. It keeps existing bindings, rules, and clauses.
-   [ ] If a DENY rule causes the denial, the report says that the block might
    be deliberate and offers any change to that rule only as an option for
    the rule's owner to approve.
-   [ ] The principal is the agent's exact `principal://` identifier, in the
    Agent Runtime format.
-   [ ] Registry resource names in conditions use the project ID, copied from
    the audit entry's `resource_id` or from Agent Registry list output.
-   [ ] A binding fix targets the project that contains Agent Gateway.
-   [ ] Hostnames match exactly, every variant is covered, and methods are in
    the request's case, such as `'GET'`.
-   [ ] The fix allows only the hosts, paths, and methods that the logs show
    the agent calling, and keeps restrictions that the rule already has, such
    as a method limit, because they're often deliberate. If the user asks to
    loosen a rule, say whether the logs show that it's needed. Never print a
    rule that's looser than the logs require.
-   [ ] V1 fixes use `roles/iap.egressor`, never
    `roles/iap.tunnelResourceAccessor`, which grants IAP TCP forwarding, not
    egress.
-   [ ] No fix turns off IAP or switches enforcement to dry run, because that
    removes egress protection for every agent behind the gateway.
-   [ ] Every placeholder is filled in from command output.
-   [ ] Commands printed for the user don't include
    `CLOUDSDK_METRICS_REQUEST_ATTRIBUTION` or the attribution `User-Agent`
    string, because the tag is only for commands you run yourself (see
    [attribution.md](references/attribution.md)).
