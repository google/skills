# Prerequisites

Set up the environment before you run any check.

## Google Cloud CLI

1.  Install the Google Cloud CLI by following the
    [installation guide](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt).
2.  Update the installed components, so that the `agent-registry`,
    `iam access-policies`, and `iap web` command groups are current:

    ```bash
    gcloud components update
    ```

    The commands in this skill were checked against Google Cloud CLI 588.0.0.

3.  Authenticate and select the project that contains the agent:

    ```bash
    gcloud auth login
    gcloud config set project {project_id}
    ```

Every command in this skill also passes `--project` explicitly, so a different
active configuration can't send a read to the wrong project. If Agent Gateway
runs in a different project from the agent, use the gateway's project ID for
gateway, authorization, Access policy, and IAP audit log reads.

## APIs

A project that already runs Agent Gateway normally has these APIs enabled. The
diagnosis never enables an API. If a read fails because an API is disabled,
print the "Enable an API" template from
[remediation-setup.md](remediation-setup.md) for the user.

| API | Used for |
| :--- | :--- |
| `iap.googleapis.com` | IAP for agents decisions and V1 IAP allow policies |
| `iam.googleapis.com` | Access policies and policy bindings |
| `networkservices.googleapis.com` | Agent Gateway and its authorization extension |
| `networksecurity.googleapis.com` | Authorization policies |
| `agentregistry.googleapis.com` | Agent Registry resources |
| `aiplatform.googleapis.com` | Agent Runtime |
| `logging.googleapis.com` | IAP audit entries, gateway logs, and agent logs |

## Read-only roles

Ask the user to confirm that the account running the checks has one of these
role sets on the project. Use the default unless the organization requires
narrower grants.

| Option | Roles | Notes |
| :--- | :--- | :--- |
| Default | `roles/iam.securityAuditor`, `roles/iam.accessPolicyViewer`, `roles/agentregistry.viewer` | Security Auditor covers the gateway, authorization policy and extension, V1 IAP allow policies, Data Access audit logs, and the principal access boundary list. The other two cover Access policies and Agent Registry |
| Granular | `roles/logging.privateLogViewer`, `roles/compute.networkViewer`, `roles/iam.securityReviewer`, `roles/iam.accessPolicyViewer`, `roles/agentregistry.viewer`, `roles/orgpolicy.policyViewer` | Same coverage with narrower grants |

Neither option grants `resourcemanager.projects.searchPolicyBindings`, which
the policy binding search on the project needs (see
[policy-model.md](policy-model.md)). Also ask for a custom role with only that
permission on the project, instead of a broad basic role such as Viewer.

The optional principal access boundary check lists policies at the organization
level. It needs `roles/iam.securityAuditor` or
`roles/iam.principalAccessBoundaryViewer` granted on the organization.

If a read returns `PERMISSION_DENIED`, stop and report which role from this
table is missing. Don't try other commands to work around it, because partial
evidence leads to a wrong root cause.

Fixes need admin roles. Each remediation template names the role that the user
running it needs.

## Billing

The project must have an active billing account attached. The diagnosis itself
creates no resources. Enabling Data Access audit logs adds log volume that might
be charged; see
[Google Cloud Observability pricing](https://cloud.google.com/products/observability/pricing).

## Region

Use the location where the agent, Agent Gateway, and Agent Registry run. If the
user doesn't know it, start with `us-central1`, the region in the public
examples, and confirm it against the agent's resource name. Access policies and
policy bindings always use `--location=global`. An Agent Registry instance can
be regional, multi-regional, or `global`. For availability, see
[Google Cloud locations](https://cloud.google.com/about/locations).

## Cleanup

The diagnosis creates nothing, so there's nothing to delete. If the user turns
on Data Access audit logs only for this investigation, they can remove the
`iap.googleapis.com` entry from `auditConfigs` afterward with the same
read-modify-write steps that added it.
