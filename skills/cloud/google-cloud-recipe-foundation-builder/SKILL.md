---
name: google-cloud-recipe-foundation-builder
metadata:
  category: GettingStarted
description: >-
  Deploys a baseline landing zone foundation for a Google Cloud Organization, establishing security guardrails using Organization Policies, resource hierarchy folders and projects, billing association, and centralized logging and monitoring. Deploys Google Cloud's recommended security controls and architecture.
  Use when setting up a new Google Cloud Organization or establishing a secure, enterprise-grade landing zone foundation.

  Don't use for individual project onboarding (use google-cloud-recipe-onboarding or product-specific skills instead).
---

# Google Cloud Recipe: Foundation Builder

> [!WARNING] This skill is currently in a preview state. It will deploy a secure
> foundation, but does not have all advanced features. Users who want more
> options should visit
> [Google Cloud Setup](https://docs.cloud.google.com/docs/enterprise/cloud-setup).

This skill guides the setup of a secure, enterprise-grade Google Cloud landing
zone foundation. It establishes baseline security controls, organizes the
initial resource hierarchy, and configures centralized audit logging and
cross-environment monitoring.

## Overview

The recipe provisions the following core components at the organization root:

*   **Security Guardrails**: Enforces 17 baseline Google Cloud Organization
    Policies to secure the environment (13 Boolean, 4 List constraints).
*   **Resource Hierarchy**: Establishes 4 folders (`Common`, `Production`,
    `Non-Production`, `Development`) and provisions corresponding projects
    sequentially with globally unique ID prefixes (`logging-`, `prod-`,
    `non-prod-`, `dev-` followed by a shared suffix).
*   **Billing & API Enablement**: Links all projects to your billing account and
    activates critical logging/monitoring services.
*   **Centralized Logging & Monitoring**: Deploys a global, centralized log
    bucket with 30-day retention, configures an organization-wide audit log
    sink, and sets up a cross-environment metrics scope.

--------------------------------------------------------------------------------

## Clarifying Questions

Before executing this recipe, the agent **must** gather the following details:

1.  **Organization ID**: Run `gcloud organizations list` to retrieve the
    available organizations, present them to the user, and ask them to select
    the target **Organization ID**.
2.  **Billing Account ID**: Run `gcloud billing accounts list
    --filter=open=true` to retrieve only the active (open) billing accounts,
    present them to the user, and ask them to select the active **Billing
    Account ID**.
3.  **Project ID Suffix**: Ask if the user has a preferred prefix or target
    suffix for Project IDs (default uses prefix + a shared random 8-character
    string, e.g., `prod-ab12cd34`).
4.  **Log Bucket Region**: Ask for the target region for resources if they want
    to override the default `global` log bucket location.

--------------------------------------------------------------------------------

## Prerequisites

Ensure the following prerequisites are met before beginning the deployment:

*   **GCP Identity**: You must have a Google Cloud Organization resource set up.
*   **Administrative IAM Roles**: The identity executing these commands must
    hold the required administrative permissions. If any step fails with a
    `Permission Denied` error, the agent will attempt to self-remediate by
    granting the corresponding recommended role as detailed in **Phase 2: Error
    Recovery & Lazy Role Remediation Strategy**.
*   **Tools**: The `gcloud` CLI must be installed, authorized with the above
    identity, and configured for use.

--------------------------------------------------------------------------------

## Steps to Complete the Recipe

### Phase 1: Pre-flight Confirmation

Identify the target organization and obtain explicit user approval before making
changes.

1.  **Identify and Discover Organization**: Verify the target organization. If
    only the display name is known, list organizations to find the ID. Then,
    retrieve the organization metadata to dynamically calculate the **Directory
    Customer ID** and **Domain Name**:

    ```bash
    # List to find ID if needed
    gcloud organizations list

    # Describe the organization to retrieve metadata
    gcloud organizations describe [ORGANIZATION_ID]
    ```

    *Calculate values:*

    *   **Domain Name** (`[ORG_NAME]` / `[YOUR_DOMAIN]`): Use the `displayName`
        value from the output (e.g., `my-business.com`).
    *   **Customer ID** (`[DIRECTORY_CUSTOMER_ID]`): Use the
        `owner.directoryCustomerId` value from the output (e.g., `C01234567`).

2.  **Present Blueprint Summary**: Present the exact details of the blueprint to
    the user and request confirmation to proceed:

    > **Proposed Foundation Deployment Summary for Organization: `[ORG_NAME]`
    > (`[ORGANIZATION_ID]`)**
    >
    > *   **Security:** Enforce 17 baseline Organization Policies (13 Boolean, 4
    >     List).
    > *   **Folders:** Create 4 folders sequentially (`Common`, `Production`,
    >     `Non-Production`, `Development`).
    > *   **Projects:** Create 4 projects sequentially with unique IDs
    >     (`logging-[SUFFIX]`, `prod-[SUFFIX]`, `non-prod-[SUFFIX]`,
    >     `dev-[SUFFIX]`).
    > *   **Billing:** Link all projects to Billing Account
    >     `[BILLING_ACCOUNT_ID]`.
    > *   **APIs:** Enable Logging and Monitoring APIs on the central project.
    > *   **Centralized Logging:** Deploy a `global` log bucket
    >     `[ORG_NAME]-logging` (30-day retention), configure an
    >     organization-level sink
    >     `[ORGANIZATION_ID]-logbucketsink-[RANDOM_HEX]`, and establish
    >     cross-project metrics scopes.
    >
    > Do you wish to proceed with this deployment? (Yes/No)

> [!IMPORTANT] **Pause execution** and wait for explicit user approval before
> moving to Phase 2. If the user declines, abort the operation.

### Phase 2: Error Recovery & Lazy Role Remediation Strategy

To ensure deployment continues smoothly on clean organizations without requiring
complex upfront permission checks (which require a quota project), the agent
**must** adopt a "lazy recovery" approach.

Instead of testing permissions in advance, the agent will attempt to execute
each step in the recipe. If a step fails with a `Permission Denied` error, the
agent will attempt to self-remediate by granting the corresponding recommended
administrative group of roles to the deployment identity and retrying the
operation.

> [!IMPORTANT] When asked about pre-deployment readiness, prerequisites, or
> checks to run, the agent **must** explicitly explain that the landing zone
> deployment adopts a lazy role remediation strategy rather than upfront
> testing, detailing all of the following in its response: 1. Confirm it will
> execute deployment commands directly, catching any Permission Denied
> errors. 2. Confirm it will attempt to self-remediate on failure by running the
> exact commands `gcloud organizations add-iam-policy-binding` or `gcloud
> billing accounts add-iam-policy-binding` to grant the entire administrative
> group of roles to the active identity, and then retry the failed deployment
> command. 3. List the core administrative groups that it will attempt to grant
> (Organization Admin Group, Billing Admin Group, and Security Admin Group)
> mapped to their key roles. 4. Confirm it will halt execution and request
> manual administrator intervention if the self-remediation grant command fails.

#### Remediation Protocol

For any command that fails due to missing permissions:

1.  **Identify Required Admin Group**: Determine which administrative group is
    responsible for the failed action. Refer to the
    [Administrative IAM Reference](references/admin-iam.md#core-administrative-groups--roles)
    for details.
2.  **Attempt Self-Remediation**: Grant **all** roles belonging to that
    administrative group to the active authenticated account sequentially. Refer
    to the
    [Administrative IAM Reference Remediation Guide](references/admin-iam.md#remediation)
    for the copy-pasteable script commands:

    *   **For Organization/Folder level failures (Org Admin Group or Security
        Admin Group)**: Run `gcloud organizations add-iam-policy-binding`
        sequentially for each role in the group.
    *   **For Billing level failures (Billing Admin Group)**: Run `gcloud
        billing accounts add-iam-policy-binding` sequentially for each role in
        the group.

3.  **Halt on Remediation Failure**:

    *   If the grant commands succeed, immediately retry the failed deployment
        command.
    *   If any of the grant commands fail (e.g., due to lack of `setIamPolicy`
        admin rights), **halt execution** and instruct the user to ask their
        Organization/Billing Administrator to manually grant the entire
        administrative group of roles.

#### Phase-Specific Remediation Mapping

*   **Phase 3: Security Guardrails (Org Policies)**:
    *   If `gcloud org-policies set-policy` fails: Attempt to grant the entire
        **Organization Admin Group** (9 roles) at the organization level.
*   **Phase 4: Resource Hierarchy (Folders & Projects)**:
    *   If `gcloud resource-manager folders create` or `gcloud projects create`
        fails: Attempt to grant the entire **Organization Admin Group** (9
        roles) at the organization level.
*   **Phase 4: Billing Link**:
    *   If `gcloud billing projects link` fails: Attempt to grant the entire
        **Billing Admin Group** (3 roles) at the billing account level, and
        ensure the active identity is granted the **Organization Admin Group**
        (which contains `roles/billing.user`) at the organization level.
*   **Phase 5: Centralized Logging & Monitoring**:
    *   If `gcloud logging sinks create` fails at org level: Attempt to grant
        the entire **Logging/Monitoring Admin Group** (2 roles:
        `roles/logging.admin`, `roles/monitoring.admin`) and the **Security
        Admin Group** (9 roles) at the organization level.

### Phase 3: Security Guardrails (Org Policies)

Apply 17 baseline security controls at the organization root.

> [!CAUTION] Applying `iam.allowedPolicyMemberDomains` first can lock out the
> deployment identity if it resides in an unallowed domain. Ensure the
> deployment identity is safe before enforcing this policy.

1.  Generate the YAML configuration files for the 17 policies. Refer to the
    [Organization Policies Reference](references/org-policies.md) for the exact
    YAML templates for both Boolean and List constraints.
2.  Apply each organization policy sequentially using the `gcloud org-policies`
    tool:

    ```bash
    gcloud org-policies set-policy [POLICY_FILE_NAME].yaml
    ```

### Phase 4: Resource Hierarchy

#### 1. Folder Creation

Check if target folders exist to avoid duplication. The agent must check for all
4 folders: for any folder that already exists (e.g., if `Common` or `Production`
are already present), the agent must locate and reuse them; for any folder that
is missing (e.g., if `Non-Production` or `Development` are not present), the
agent must proceed to sequentially create them:

> [!IMPORTANT] When explaining how existing resources (folders and projects) are
> handled to prevent duplication, the agent **must** explicitly name the
> remaining missing folders (`Non-Production` and `Development`) and confirm
> that it will proceed to sequentially create only these missing folders and
> projects.

```bash
# Check and Create "Common" Folder
gcloud resource-manager folders list --organization=[ORGANIZATION_ID] --filter="display_name=Common"
# If not present:
gcloud resource-manager folders create --display-name="Common" --organization=[ORGANIZATION_ID]

# Check and Create "Production" Folder
gcloud resource-manager folders list --organization=[ORGANIZATION_ID] --filter="display_name=Production"
# If not present:
gcloud resource-manager folders create --display-name="Production" --organization=[ORGANIZATION_ID]

# Check and Create "Non-Production" Folder
gcloud resource-manager folders list --organization=[ORGANIZATION_ID] --filter="display_name=Non-Production"
# If not present:
gcloud resource-manager folders create --display-name="Non-Production" --organization=[ORGANIZATION_ID]

# Check and Create "Development" Folder
gcloud resource-manager folders list --organization=[ORGANIZATION_ID] --filter="display_name=Development"
# If not present:
gcloud resource-manager folders create --display-name="Development" --organization=[ORGANIZATION_ID]
```

#### 2. Project Creation and Billing Link

Check if target projects already exist in the folders by matching their display
names. If not present, generate a shared 8-character random suffix (e.g.,
`ab12cd34`) and create the projects sequentially, linking billing and enabling
APIs immediately:

```bash
# Check if "central-logging-monitoring" project exists in Common folder
gcloud projects list --filter="parent.id=[COMMON_FOLDER_ID] AND parent.type=folder AND name=central-logging-monitoring"

# If not present: Create, link billing, and enable APIs
gcloud projects create logging-[SUFFIX] --name="central-logging-monitoring" --folder=[COMMON_FOLDER_ID]
gcloud billing projects link logging-[SUFFIX] --billing-account=[BILLING_ACCOUNT_ID]
gcloud services enable compute.googleapis.com logging.googleapis.com monitoring.googleapis.com --project=logging-[SUFFIX]

# Check if "production" project exists in Production folder
gcloud projects list --filter="parent.id=[PRODUCTION_FOLDER_ID] AND parent.type=folder AND name=production"

# If not present: Create, link billing, and enable APIs
gcloud projects create prod-[SUFFIX] --name="production" --folder=[PRODUCTION_FOLDER_ID]
gcloud billing projects link prod-[SUFFIX] --billing-account=[BILLING_ACCOUNT_ID]
gcloud services enable compute.googleapis.com run.googleapis.com container.googleapis.com artifactregistry.googleapis.com firestore.googleapis.com pubsub.googleapis.com aiplatform.googleapis.com cloudaicompanion.googleapis.com apphub.googleapis.com designcenter.googleapis.com discoveryengine.googleapis.com iam.googleapis.com config.googleapis.com cloudbuild.googleapis.com cloudasset.googleapis.com cloudkms.googleapis.com cloudresourcemanager.googleapis.com --project=prod-[SUFFIX]

# Check if "non-production" project exists in Non-Production folder
gcloud projects list --filter="parent.id=[NON_PRODUCTION_FOLDER_ID] AND parent.type=folder AND name=non-production"

# If not present: Create, link billing, and enable APIs
gcloud projects create non-prod-[SUFFIX] --name="non-production" --folder=[NON_PRODUCTION_FOLDER_ID]
gcloud billing projects link non-prod-[SUFFIX] --billing-account=[BILLING_ACCOUNT_ID]
gcloud services enable compute.googleapis.com run.googleapis.com container.googleapis.com artifactregistry.googleapis.com firestore.googleapis.com pubsub.googleapis.com aiplatform.googleapis.com cloudaicompanion.googleapis.com apphub.googleapis.com designcenter.googleapis.com discoveryengine.googleapis.com iam.googleapis.com config.googleapis.com cloudbuild.googleapis.com cloudasset.googleapis.com cloudkms.googleapis.com cloudresourcemanager.googleapis.com --project=non-prod-[SUFFIX]

# Check if "development" project exists in Development folder
gcloud projects list --filter="parent.id=[DEVELOPMENT_FOLDER_ID] AND parent.type=folder AND name=development"

# If not present: Create, link billing, and enable APIs
gcloud projects create dev-[SUFFIX] --name="development" --folder=[DEVELOPMENT_FOLDER_ID]
gcloud billing projects link dev-[SUFFIX] --billing-account=[BILLING_ACCOUNT_ID]
gcloud services enable compute.googleapis.com run.googleapis.com container.googleapis.com artifactregistry.googleapis.com firestore.googleapis.com pubsub.googleapis.com aiplatform.googleapis.com cloudaicompanion.googleapis.com apphub.googleapis.com designcenter.googleapis.com discoveryengine.googleapis.com iam.googleapis.com config.googleapis.com cloudbuild.googleapis.com cloudasset.googleapis.com cloudkms.googleapis.com cloudresourcemanager.googleapis.com --project=dev-[SUFFIX]
```

> [!NOTE] **Agentic Parallelism Option**: While the manual runbook enforces
> sequential project execution to avoid terminal race conditions, an AI agent
> with multi-agent orchestration capability may optionally spawn subagents to
> provision the 4 projects in parallel once folder IDs are resolved.

### Phase 5: Centralized Logging and Monitoring

Configure centralized audit logging and cross-project monitoring scope in the
`logging-[SUFFIX]` project.

Refer to the
[Centralized Logging and Monitoring Reference](references/logging-monitoring.md)
for the detailed step-by-step commands to:

1.  Create the central log bucket.
2.  Create the organization-wide log sink.
3.  Grant required IAM permissions to the log sink.
4.  Configure the cross-project monitoring metrics scope.

--------------------------------------------------------------------------------

## Validation Logic & Checklist

Evaluate the deployment against the following verification checks:

-   [ ] **Security Policies**: Run `gcloud org-policies list
    --organization=[ORGANIZATION_ID]` and verify all 17 target policies are
    enforced or correctly configured.
-   [ ] **Resource Folders**: Verify folders `Common`, `Production`,
    `Non-Production`, and `Development` exist under the organization root.
-   [ ] **Billing Linkage**: Run `gcloud billing projects list` and assert that
    all 4 newly created projects are linked to your billing account.
-   [ ] **Log Bucket & Retention**: Verify the log bucket `[ORG_NAME]-logging`
    exists in project `logging-[SUFFIX]`, is located in `global`, and has a
    retention period of exactly 30 days.
-   [ ] **Log Sink Routing**: Run `gcloud logging sinks describe` at the
    organization level and confirm the sink routes cloud audit logs to the
    global bucket and holds standard `writerIdentity` credentials.
-   [ ] **Metrics Scope Linkage**: Run `gcloud beta monitoring metrics-scopes
    describe` and assert that the `dev`, `non-prod`, and `prod` projects appear
    in the monitored list of the central `logging` project.

--------------------------------------------------------------------------------

## Links

*   [Google Cloud Resource Hierarchy Documentation](https://cloud.google.com/resource-manager/docs/creating-managing-organization)
*   [Google Cloud Organization Policies Overview](https://cloud.google.com/resource-manager/docs/organization-policy/overview)
*   [Centralized Audit Logging Best Practices](https://cloud.google.com/architecture/security-foundations/logging-monitoring)
*   [Cloud Monitoring Metrics Scopes Configuration](https://cloud.google.com/monitoring/settings/multiple-projects)
*   [Gcloud Logging Sinks CLI Reference](https://cloud.google.com/sdk/gcloud/reference/logging/sinks)
*   [Google Cloud Landing Zones Guide](https://docs.cloud.google.com/architecture/landing-zones)
*   [Google Cloud Security Foundations Blueprint](https://docs.cloud.google.com/architecture/blueprints/security-foundations)
