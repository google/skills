# Policy models

The authorization extension's `metadata.iapPolicyVersion` names the model that
IAP evaluates: `V2` for IAM Unified Access Policies (Access policies), `V1` for
IAP allow policies. Read the extension first
([gateway-setup.md](gateway-setup.md)), then use the sections for that version,
plus the section that applies to both versions.

## Contents

- [V2: How Access policies are evaluated](#v2-how-access-policies-are-evaluated): Lines 29-45
- [V2: Read policies and bindings](#v2-read-policies-and-bindings): Lines 47-88
- [V2: Organization policy constraint](#v2-organization-policy-constraint): Lines 90-101
- [V2: Errors from Access policy commands](#v2-errors-from-access-policy-commands): Lines 103-113
- [Both versions: principal access boundary (optional)](#both-versions-principal-access-boundary-optional): Lines 115-131
- [V1: IAP allow policies](#v1-iap-allow-policies): Lines 133-145
- [V1: Scopes](#v1-scopes): Lines 147-165

Sources:
[IAM Unified Access Policies overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/iam-overview-uap.md.txt),
[Configure IAM Unified Access Policies](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/configure-iam-policies-uap.md.txt),
[Manage IAM Unified Access Policies](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/manage-iam-policies-uap.md.txt),
[Troubleshoot IAM Unified Access Policies](https://docs.cloud.google.com/gemini-enterprise-agent-platform/troubleshooting/troubleshoot-iam-policies-uap.md.txt),
[Troubleshoot Agent Gateway](https://docs.cloud.google.com/gemini-enterprise-agent-platform/troubleshooting/troubleshoot-agent-gateway.md.txt),
[IAP allow policies overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/iam-overview.md.txt),
[Configure IAP allow policies](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/configure-iam-policies.md.txt),
[Policy bindings REST reference](https://docs.cloud.google.com/iam/docs/reference/rest/v3/projects.locations.policyBindings.md.txt).

## V2: How Access policies are evaluated

-   Access policies take effect when they're bound to the project that
    contains Agent Gateway, or to the gateway itself. Every gateway in that
    project enforces every policy bound to the project.
-   Each rule has an `effect` (`ALLOW` or `DENY`), `principals`, an
    `operation` with the permission `iap.googleapis.com/resources.egressViaIAP`,
    and `conditions` keyed by `iap.googleapis.com` that hold a CEL
    `expression`. The effect applies only when the whole expression is true.
-   `excludedPrincipals` removes principals from a rule even if `principals`
    lists them.
-   Deny rules are evaluated first. If a deny rule's condition is true, the
    request is blocked even when an allow rule also matches.
-   A broader allow rule, for example one bound for the whole project without
    conditions, can grant access that a narrower rule was meant to limit.
-   Policies created in the Google Cloud console are bound to the project
    automatically.

## V2: Read policies and bindings

```bash
gcloud iam access-policies list --location=global --project={project_id}
gcloud iam access-policies describe {policy} \
    --location=global --project={project_id}
gcloud iam policy-bindings search-target-policy-bindings \
    --target=//cloudresourcemanager.googleapis.com/projects/{project_number} \
    --location=global --project={project_id}
```

The target search doesn't return bindings on the gateway. A binding belongs to
the closest Resource Manager resource to its target, so a binding on the
gateway belongs to the gateway's project. List every binding in that project:

```bash
gcloud iam policy-bindings list \
    --location=global --project={project_id} \
    --format="json(name,policy,policyKind,target)"
```

Keep the entries whose `policyKind` is `ACCESS` and whose `target.resource`
exactly equals the project
(`//cloudresourcemanager.googleapis.com/projects/{project_number}`, or the same
with `{project_id}`) or the gateway
(`//networkservices.googleapis.com/projects/{project_id}/locations/{location}/agentGateways/{gateway}`).
Compare the strings yourself instead of with `--filter`. Then read every bound
policy.

-   Read every policy bound to the project or the gateway, not only the one
    that the user names. A deny rule in any bound policy wins.
-   A policy without a binding to the gateway's project or to the gateway isn't
    enforced. Print the "Bind an Access policy to the project" template from
    [remediation-access-policies.md](remediation-access-policies.md).
-   For each rule, check `principals` and `excludedPrincipals` against the
    agent: a `principal://` entry must equal the agent's identifier from the
    audit entry, and a `principalSet://` entry must contain it (see the
    principal set table in
    [topology-agent-gateway.md](topology-agent-gateway.md)). Then compare the
    condition with the request, using [cel-attributes.md](cel-attributes.md).
-   If no rule allows the agent, print the "Change Access policy rules"
    template, or "Create an Access policy" if the project has no policy.

## V2: Organization policy constraint

```bash
gcloud org-policies describe iam.managed.disableAccessPolicyBinding \
    --project={project_id} --effective
```

-   While this managed constraint is enforced, Access policies can't be bound
    to the project. It's enforced by default in new organizations.
-   If it's enforced and the binding is missing, the fix has two steps: the
    user overrides the constraint for the project, then creates the binding.
    Print both templates in that order.

## V2: Errors from Access policy commands

| Error | Meaning | Fix |
| :--- | :--- | :--- |
| `POLICY_NOT_FOUND` or 404 | The policy name is wrong | List the policies and copy the name |
| `TOO_MANY_ACCESS_POLICY_BINDINGS_PER_TARGET` | The project has too many bindings | Consolidate rules into fewer policies, and delete unused bindings |
| `TOO_MANY_ACCESS_POLICY_BINDINGS_TO_POLICY` | One policy has too many bindings | Bind it at a broader scope and narrow it with CEL conditions |
| `TOO_MANY_CONDITIONS` | A rule has too many conditions | Combine them with `&&`, `\|\|`, or `in`, or split the rule |
| 412 or `ABORTED` | The etag is out of date | Read the policy again and use the new etag |
| The last rule can't be deleted | A policy needs at least one rule | Delete the policy instead |
| A policy can't be deleted | It still has bindings | Delete its bindings first |

## Both versions: principal access boundary (optional)

Check this when an Access policy (V2) or an IAP allow policy (V1) allows the
agent but IAP still denies the request. Agent Gateway can use IAP to enforce
principal access boundary policies with either model. Principal access boundary
policies take precedence over IAM allow policies: the request fails if an
active boundary policy leaves the destination out of the agent's scope.

```bash
gcloud iam principal-access-boundary-policies list \
    --organization={org_id} --location=global
```

For each policy, check whether `details.rules[].resources[]` puts the
destination in the agent's scope. If a policy leaves it out, report the policy
as a likely cause, and ask the user to confirm that it's bound to the agent's
principal set.

## V1: IAP allow policies

-   IAP allow policies grant `roles/iap.egressor` (IAP-secured Egressor) on
    Agent Registry resources. Members are `principal://` or `principalSet://`
    identifiers.
-   Never grant `roles/iap.tunnelResourceAccessor` (IAP-secured Tunnel User).
    It grants access to IAP TCP forwarding tunnels, not egress.
-   IAP allow policies apply only to registered resources. Binding a policy to
    an unregistered resource fails with `NOT_FOUND`. The public troubleshooting
    guide covers unregistered endpoints with Access policies.
-   Target resources by the IDs that Agent Registry assigns (see
    [agent-registry.md](agent-registry.md)), never by URN identifiers.
-   A policy on a regional registry applies only to resources in that region.

## V1: Scopes

| Scope | Read command |
| :--- | :--- |
| Registry-wide | `gcloud iap web get-iam-policy --resource-type=agent-registry --region={registry_location} --project={project_id}` |
| One MCP server | Add `--mcp-server={mcp_server_id}` |
| One endpoint | Add `--endpoint={endpoint_id}` |
| One agent | Add `--agent={agent_id}` |

-   IAP allow policies follow the IAM resource hierarchy: a resource inherits
    the registry-wide policy, and its own policy adds grants to it. A grant at
    either level gives the agent access, so read both.
-   A response with an `etag` but no `bindings` means that no policy exists at
    that scope.
-   A binding with a `condition` grants access only when the expression is
    true. V1 conditions use `api.getAttribute()`; see
    [cel-attributes.md](cel-attributes.md).
-   To fix a missing grant, print the "Grant roles/iap.egressor" template from
    [remediation-registry.md](remediation-registry.md).
