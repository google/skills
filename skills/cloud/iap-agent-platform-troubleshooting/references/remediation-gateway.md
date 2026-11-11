# Remediation: gateway authorization chain

These templates change resources. Print them for the user to run; never run
them.

## Point the authorization policy at the gateway

Roles: Network Security Admin (`roles/networksecurity.admin`), plus the
`networkservices.agentGateways.use` permission on the gateway.

`import` replaces the whole authorization policy, so start from the current
policy when one exists. The authorization policy must be in the same project
as the extension.

1.  Save the current policy:

    ```bash
    gcloud network-security authz-policies describe {authz_policy} \
        --location={location} --project={project_id} --format=yaml \
        > authz-policy.yaml
    ```

2.  In `authz-policy.yaml`, add this entry under `target.resources`, and keep
    the existing entries. Delete the `createTime` and `updateTime` lines,
    because `import` rejects output-only fields. Keep every other field.

    ```yaml
      - "projects/{project_id}/locations/{location}/agentGateways/{gateway}"
    ```

    If the policy calls the wrong extension, replace the entry under
    `customProvider.authzExtension.resources` with
    `projects/{project_id}/locations/{location}/authzExtensions/{authz_extension}`
    instead. If the new extension enforces and the old one ran in dry run,
    this turns on enforcement, so give the warning from
    [Turn on enforcement](#turn-on-enforcement).

    If no authorization policy exists yet, write the whole file instead:

    ```yaml
    name: {authz_policy}
    target:
      resources:
      - "projects/{project_id}/locations/{location}/agentGateways/{gateway}"
    policyProfile: REQUEST_AUTHZ
    action: CUSTOM
    customProvider:
      authzExtension:
        resources:
        - "projects/{project_id}/locations/{location}/authzExtensions/{authz_extension}"
    ```

3.  Import it:

    ```bash
    gcloud network-security authz-policies import {authz_policy} \
        --source=authz-policy.yaml --location={location} --project={project_id}
    ```

A gateway accepts at most four custom authorization policies. Source:
[Delegate authorization](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/delegate-authorization.md.txt).

## Turn on enforcement

Role: Service Extensions Admin (`roles/networkservices.serviceExtensionsAdmin`).

Print this only if the user asks to turn on enforcement. It isn't a fix for a
denial.

Before enforcing, ask the user to review the disallowed requests that IAP
logged in dry run. Enforcement blocks every request that the policies don't
allow, including the Google services that the agent calls at startup.

1.  Save the extension:

    ```bash
    gcloud service-extensions authz-extensions describe {authz_extension} \
        --location={location} --project={project_id} --format=yaml \
        > authz-extension.yaml
    ```

2.  In `authz-extension.yaml`, delete the `iamEnforcementMode: "DRY_RUN"` line
    under `metadata`. Also delete the `createTime` and `updateTime` lines,
    because `import` rejects output-only fields. Keep every other field.
3.  Import it:

    ```bash
    gcloud service-extensions authz-extensions import {authz_extension} \
        --source=authz-extension.yaml --location={location} \
        --project={project_id}
    ```

Source:
[Troubleshoot IAM Unified Access Policies](https://docs.cloud.google.com/gemini-enterprise-agent-platform/troubleshooting/troubleshoot-iam-policies-uap.md.txt).

## Wait time

A gateway chain change has no published figure and can take a few minutes to
apply. Retest after a few minutes, and look for a new audit entry.
