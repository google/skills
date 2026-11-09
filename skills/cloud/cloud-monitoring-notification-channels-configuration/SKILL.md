---
name: cloud-monitoring-notification-channels-configuration
metadata:
  version: "1.0.2"
  category: CloudObservabilityAndMonitoring
description: >-
  Generates Terraform HCL configurations for Cloud Monitoring notification
  channels (`google_monitoring_notification_channel`) and adds notification
  channels to alerting policies (`google_monitoring_alert_policy`) in Google
  Cloud projects. Use when creating or configuring email, SMS, Slack, PagerDuty,
  Pub/Sub, or webhook notification channels, verifying Pub/Sub topic
  compatibility (including cross-project topics, message storage policies, and
  in-transit enforcement) and publishing permissions for the Cloud Monitoring
  Service Agent, or adding notification channels to existing alert policies.
  Don't use for authoring or editing alerting policy conditions, selecting
  metric descriptors, or writing PromQL or Monitoring Filter queries.
---

# Cloud Monitoring Notification Channels Configuration

## Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read [Usage Attribution](references/attribution.md). For commands executed
directly in the terminal (never in generated scripts, Terraform, or user code),
prefix `gcloud` with
`CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:cloud-monitoring-notification-channels-configuration)"`
and append `agent-skills/1.0 (skill:cloud-monitoring-notification-channels-configuration)` to `User-Agent` headers.

## Context Provided

*   **Terraform Only**: Write the generated observability configuration ONLY as
    Terraform (`.tf`) files (e.g., `notification_channels.tf`).
    -   Install Terraform **ONLY** if you are asked to deploy the channels AND
        there is no valid Terraform installation.
    -   If you are **NOT** asked to deploy the channels, **DO NOT** install
        Terraform.
*   **Working Directory Inference**: Determine the target path for `.tf` files
    using the following order:
    1.  If the user provides a path, use that exact path for the `.tf` file.
    2.  If a path is not provided, search the workspace for existing `.tf` files
        (preferring files that already define
        `google_monitoring_notification_channel` or
        `google_monitoring_alert_policy` resources, or existing directories in
        the strict preference order: `monitoring/`, then `ops/`, then `sre/`).
        If found, write `notification_channels.tf` in that directory (or update
        the existing `.tf` file when modifying an existing resource).
    3.  If a path is not provided and no `.tf` files or target directories exist
        in the workspace, create and write to
        `monitoring/notification_channels.tf`.
*   **Google Cloud Prerequisites**: When running `gcloud` CLI discovery commands
    or deploying configurations with the `terraform` CLI against a Google Cloud
    project, ensure the following prerequisites are met in order (do not execute
    these commands if the user only asks to generate or print Terraform HCL):
    1.  **Target Project ID & Project Number**:
        *   Identify the target Google Cloud `{project_id}` from the user's
            request or via `gcloud config get-value project`. If neither is
            available, prompt the user to provide `{project_id}` before
            continuing.
        *   When the Google Cloud project number (`{project_number}`) is needed
            (such as constructing the Cloud Monitoring Service Agent identity
            for Pub/Sub channels):
            *   **Method A (Standard)**: Run `gcloud projects describe
                {project_id} --format='value(projectNumber)'`.
            *   **Method B (Ask User)**: If the command fails or you cannot
                retrieve the project number, ask the user to provide it.
    2.  **Authentication**: Authenticate the `gcloud` CLI via `gcloud auth
        login` and configure Application Default Credentials (ADC) for Terraform
        via `gcloud auth application-default login`.
    3.  **Project Configuration & Billing**: Configure the target Google Cloud
        project via `gcloud config set project {project_id}` (and ensure the
        project has an active billing account attached).
        *   **Recovery Actions**: If `gcloud config set project {project_id}` or
            `gcloud projects describe {project_id}` fails, verify active
            credentials with `gcloud auth list`, list accessible projects with
            `gcloud projects list`, or prompt the user to confirm the project ID
            and access permissions. If deployment fails due to a missing or
            inactive billing account, stop deployment and instruct the user to
            link an active billing account (via `gcloud billing projects link
            {project_id} --billing-account={account_id}` or in the Google Cloud
            console) before retrying.
    4.  **IAM Permissions**: Ensure the principal has permission to manage
        notification channels—either via the predefined Monitoring
        NotificationChannel Editor role
        (`roles/monitoring.notificationChannelEditor`, plus
        `roles/monitoring.alertPolicyEditor` when adding a channel to an
        existing alert policy) **or via a custom IAM role** containing the
        equivalent permissions (`monitoring.notificationChannels.get`,
        `monitoring.notificationChannels.list`,
        `monitoring.notificationChannels.create`,
        `monitoring.notificationChannels.update`,
        `monitoring.notificationChannels.delete`, and
        `monitoring.alertPolicies.get` / `monitoring.alertPolicies.update` when
        updating an alert policy).
        *   **Recovery Actions**: Users with a custom role granting these
            permissions do not need the predefined role name. If a `gcloud` or
            `terraform` command fails with `PERMISSION_DENIED` (HTTP 403), stop
            execution, identify the missing `monitoring.notificationChannels.*`
            or `monitoring.alertPolicies.*` permission, and instruct the user to
            ask a project administrator to grant
            `roles/monitoring.notificationChannelEditor` (or a custom role with
            the required permissions) to their principal.
*   **Discovery Tips**:
    *   **Listing Notification Channels**: You MUST use `gcloud beta monitoring
        channels list --project={project_id}` to list notification channels. Do
        **NOT** use any other `gcloud` commands to list notification channels.
    *   **Verifying Pub/Sub Topics**: When configuring a Pub/Sub notification
        channel, run
        [`scripts/verify_pubsub_topic.sh`](scripts/verify_pubsub_topic.sh)
        `{monitoring_project_id} {topic_name_or_path}` to verify that:
        1.  The Pub/Sub API (`pubsub.googleapis.com`) is enabled in the topic's
            project (supporting both same-project topics and cross-project
            topics specified as
            `projects/{topic_project_id}/topics/{topic_name}`).
        2.  The topic exists and the monitoring project's Cloud Monitoring
            Service Agent
            (`service-{monitoring_project_number}@gcp-sa-monitoring-notification.iam.gserviceaccount.com`)
            holds `roles/pubsub.publisher` on the topic or topic project.
        3.  The topic does **not** define a message storage policy
            (`messageStoragePolicy` / `message_storage_policy`) and does **not**
            have in-transit enforcement (`enforceInTransit` /
            `enforce_in_transit`) enabled. **DO NOT** use a Pub/Sub topic that
            defines a message storage policy or enforces in-transit restrictions
            as a notification channel, because Cloud Monitoring cannot deliver
            messages to such topics.
*   **Attribution**: You MUST tag EVERY applicable command and Terraform
    resource below that you create, modify, or suggest to the user.

    *   **Terraform HCL (`user_labels`)**:
        *   Every `google_monitoring_notification_channel` resource that you
            create MUST include the `created-with-google-skill` label in its
            `user_labels` block:

            ```terraform
            user_labels = {
              created-with-google-skill = "cloud-monitoring-notification-channels-configuration"
            }
            ```

        *   When modifying an existing `google_monitoring_alert_policy` resource
            solely to add a notification channel, do **not** use
            `created-with-google-skill` (since this skill did not create the
            alerting policy). Instead, include the
            `added-channel-with-google-skill` label in its `user_labels` block
            (preserving any existing `user_labels` on the policy):

            ```terraform
            user_labels = {
              added-channel-with-google-skill = "cloud-monitoring-notification-channels-configuration"
            }
            ```

    *   Follow the instructions below based on the CLI tool being used:

        *   **gcloud:** Prefix every `gcloud` invocation with the metrics
            environment variables. Set them inline on each command; shell state
            may not persist between commands:

            ```bash
            CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:cloud-monitoring-notification-channels-configuration)" \
                gcloud <command> [flags]
            ```

        *   **Direct HTTP calls:** For direct HTTP calls (e.g. `curl`), you MUST
            pass the explicit `-H "User-Agent: ..."` header in the shell command
            syntax exactly like this:

            ```bash
            curl -H "User-Agent: agent-skills/1.0 (skill:cloud-monitoring-notification-channels-configuration)" ...
            ```

        *   **Terraform:** Prefix every Terraform `plan` and `apply` invocation
            with the metrics environment variables. Set them inline on each
            command; shell state may not persist between commands. For example:

            ```bash
            GOOGLE_TERRAFORM_USERAGENT_EXTENSION="agent-skills/1.0 (skill:cloud-monitoring-notification-channels-configuration)" \
                terraform plan [flags]
            ```

    *   If the skill instructions provide an additional skill script name,
        include that script name in the attribution label. Using a `gcloud`
        command inside
        [`scripts/verify_pubsub_topic.sh`](scripts/verify_pubsub_topic.sh) as an
        example:

        ```bash
        CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:cloud-monitoring-notification-channels-configuration; script:verify_pubsub_topic)" \
            gcloud <command> [flags]
        ```

*   **Execution Note (State Refresh Timeout Recovery)**: When running `terraform
    plan` or `terraform apply`, set a command timeout of **120 seconds**. If the
    command does not complete within 120 seconds (indicating Terraform is
    stalling on a full state refresh across a large state file rather than
    normal execution), cancel the command and retry **at most once** by running
    `terraform plan` and `terraform apply` with `-target` scoped to the specific
    resources being created or updated (for example,
    `-target=google_monitoring_notification_channel.<resource_name>` and, if
    updating an alert policy,
    `-target=google_monitoring_alert_policy.<policy_name>`). If the targeted
    retry also times out after 120 seconds or fails, **DO NOT** retry again;
    stop execution and report the timeout or error to the user.

## Generation

### Input Assumptions (checklist)

*   **Notification Channel Type**: When creating a new notification channel, the
    user MUST provide the notification channel type to configure.
    -   If no type is provided (and the user is not attaching an existing
        notification channel to an alert policy), you MUST prompt the user to
        ask for a type before continuing.
*   **Sensitive Credentials File**: Some notification channels require the use
    of sensitive credentials in their configuration. You MUST verify that the
    user has a `secret.tfvars` file in the working directory. If the file does
    not exist, create one using the template provided in
    [`assets/secret.tfvars`](assets/secret.tfvars) and notify the user that
    credentials should be stored there.

### Execution Steps

1.  Open the reference file corresponding to the notification channel the user
    wants to configure:

    Notification Channel Type | Reference File
    :------------------------ | :----------------------------------------
    **email**                 | [email.md](references/email.md)
    **sms**                   | [sms.md](references/sms.md)
    **slack**                 | [slack.md](references/slack.md)
    **pubsub**                | [pubsub.md](references/pubsub.md)
    **pagerduty**             | [pagerduty.md](references/pagerduty.md)
    **webhook**               | [webhook.md](references/webhook.md)

2.  Follow the guidelines in the `Prerequisites` section (if any) to complete
    all requirements for the channel configuration.

3.  If the reference file contains a `Required Credentials` section under
    `Specification`, you MUST confirm that the listed required credentials are
    configured in the `secret.tfvars` file.

    -   If any of the credentials are set to empty or not found in the file, you
        MUST prompt the user to provide them before proceeding.

4.  Use the template provided in the `Terraform HCL` section under
    `Specification` inside the reference file replacing the specified variables
    as needed to write the new configuration into the output file. If the user
    explicitly specifies a `display_name` for the notification channel, set
    `display_name` to that exact string instead of the default
    `"<Type> Notification Channel (...)"` template string.

5.  **Adding a Channel to an Existing Alert Policy**: When modifying an existing
    `google_monitoring_alert_policy` resource to use an existing
    `google_monitoring_notification_channel` resource (without creating a new
    channel), set `notification_channels` on the
    `google_monitoring_alert_policy` block and set the
    `added-channel-with-google-skill` label to
    `"cloud-monitoring-notification-channels-configuration"` in its
    `user_labels` block (preserving any existing `user_labels`):

    ```terraform
    notification_channels = [
      google_monitoring_notification_channel.<channel_resource_name>.name,
    ]
    user_labels = {
      added-channel-with-google-skill = "cloud-monitoring-notification-channels-configuration"
    }
    ```

### Outputs & Formats

Write all channel configurations into a `notification_channels.tf` file under
the directory chosen in the #context-provided section (or update the target
`.tf` file when adding notification channels to an existing
`google_monitoring_alert_policy`). Ensure every generated
`google_monitoring_notification_channel` resource sets
`created-with-google-skill` to
`"cloud-monitoring-notification-channels-configuration"` in `user_labels`, and
every modified `google_monitoring_alert_policy` resource sets
`added-channel-with-google-skill` to
`"cloud-monitoring-notification-channels-configuration"` in `user_labels`.

--------------------------------------------------------------------------------

## Supporting Links

*   [Create and manage notification channels](https://docs.cloud.google.com/monitoring/support/notification-options.md.txt)
