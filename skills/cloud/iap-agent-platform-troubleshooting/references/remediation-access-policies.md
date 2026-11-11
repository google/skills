# Remediation: Access policies (V2)

These templates change resources. Print them for the user to run; never run
them.

## Contents

- [If a DENY rule causes the denial](#if-a-deny-rule-causes-the-denial): Lines 15-22
- [Override the organization policy constraint](#override-the-organization-policy-constraint): Lines 24-49
- [Bind an Access policy to the project](#bind-an-access-policy-to-the-project): Lines 51-68
- [Create an Access policy](#create-an-access-policy): Lines 70-108
- [Change Access policy rules](#change-access-policy-rules): Lines 110-145
- [Wait times](#wait-times): Lines 147-153

## If a DENY rule causes the denial

Treat the block as possibly deliberate, because deny rules are how
administrators put guardrails on every agent. Name the policy and the rule,
quote its `description`, and say that keeping the block is a valid outcome.
Print a change only as an option for the rule's owner to approve. The narrowest
one adds the agent's exact principal to the rule's `excludedPrincipals`;
changing the condition affects every agent.

## Override the organization policy constraint

Role: Organization Policy Administrator (`roles/orgpolicy.policyAdmin`).

This turns off an organization guardrail for the project, so tell the user to
get approval from the organization policy owner before running it. Print it
only when the constraint blocks the binding that the fix needs.

Write `policy.yaml`:

```yaml
name: projects/{project_id}/policies/iam.managed.disableAccessPolicyBinding
spec:
  rules:
  - enforce: false
```

```bash
gcloud org-policies set-policy policy.yaml
gcloud org-policies describe iam.managed.disableAccessPolicyBinding \
    --project={project_id} --effective
```

The second command confirms the override. Then print the binding template.
Source:
[Create and manage organization policies](https://docs.cloud.google.com/organization-policy/create-organization-policies.md.txt).

## Bind an Access policy to the project

Roles: Access Policy Admin (`roles/iam.accessPolicyAdmin`) and Project IAM
Admin (`roles/resourcemanager.projectIamAdmin`).

`{policy_name}` is the policy's full `name` from
`gcloud iam access-policies describe`.

```bash
gcloud iam policy-bindings create {binding_id} \
    --policy={policy_name} \
    --target-resource=//cloudresourcemanager.googleapis.com/projects/{project_number} \
    --policy-kind=access --location=global --project={project_id}
```

If it fails because of the organization policy constraint, print the override
template first. Source:
[Configure IAM Unified Access Policies](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/configure-iam-policies-uap.md.txt).

## Create an Access policy

Role: Access Policy Admin (`roles/iam.accessPolicyAdmin`).

Write `rules.json`. Copy `{principal}` from the audit entry's
`principalSubject`, and build `{cel_expression}` from
[cel-attributes.md](cel-attributes.md).

```json
[
  {
    "description": "{rule_description}",
    "effect": "ALLOW",
    "principals": ["{principal}"],
    "operation": {
      "permissions": ["iap.googleapis.com/resources.egressViaIAP"]
    },
    "conditions": {
      "iap.googleapis.com": {
        "expression": "{cel_expression}"
      }
    }
  }
]
```

```bash
gcloud iam access-policies create {policy} --details-rules=rules.json \
    --location=global --project={project_id} --validate-only
gcloud iam access-policies create {policy} --details-rules=rules.json \
    --location=global --project={project_id}
```

The first command only validates and creates nothing. When the rules are
valid, gcloud prints `done` for the operation and then reports `NOT_FOUND` for
the policy, because it reads back a policy that validation didn't create. Tell
the user to expect this. A failed operation with `INVALID_ARGUMENT` means the
rules need fixing. Then print the binding template. Source:
[Configure IAM Unified Access Policies](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/configure-iam-policies-uap.md.txt).

## Change Access policy rules

Role: Access Policy Admin (`roles/iam.accessPolicyAdmin`).

`--details-rules` replaces the policy's whole rule list, so the file must
contain every rule.

1.  Save the policy, and note its `etag`:

    ```bash
    gcloud iam access-policies describe {policy} \
        --location=global --project={project_id} --format=json > policy.json
    ```

2.  Extract the rules and the etag, then change only the rule that failed in
    `rules.json`, for example by adding a hostname variant or a principal.
    Keep the other rules unchanged:

    ```bash
    jq '.details.rules' policy.json > rules.json
    jq -r '.etag' policy.json
    ```

    Without `jq`, copy the `details.rules` array into `rules.json` by hand.
3.  Validate, then apply:

    ```bash
    gcloud iam access-policies update {policy} --details-rules=rules.json \
        --etag={etag} --location=global --project={project_id} --validate-only
    gcloud iam access-policies update {policy} --details-rules=rules.json \
        --etag={etag} --location=global --project={project_id}
    ```

A 412 or `ABORTED` error means the etag is out of date. Start again from step
1. Source:
[Manage IAM Unified Access Policies](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/manage-iam-policies-uap.md.txt).

## Wait times

| Change | Wait |
| :--- | :--- |
| Organization policy | Up to 15 minutes ([Apply organization policies](https://docs.cloud.google.com/organization-policy/apply-policies.md.txt)) |
| Principal set membership | A few minutes ([Troubleshoot Agent Gateway](https://docs.cloud.google.com/gemini-enterprise-agent-platform/troubleshooting/troubleshoot-agent-gateway.md.txt)) |
| Access policies and bindings | No published figure, and a change can take a few minutes to apply. Retest after a few minutes, and look for a new audit entry |
