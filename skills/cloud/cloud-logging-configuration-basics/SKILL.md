---
name: cloud-logging-configuration-basics
description: >-
  Configure single-project Google Cloud Logging: regional log buckets, log sinks, log views, restricting or hiding sensitive logs in the default view (_Default) filter,
  IAM permissions for views (Logs View Accessor, IAM conditions), logs-based metrics, log exclusions, and sampling.
  Don't use for cross-project logging or multi-project setups.
metadata:
  category: CloudObservabilityAndMonitoring
---

# Configuring Cloud Logging

Use this skill to configure Cloud Logging resources such as log buckets, log
views, or log sinks.

> [!IMPORTANT] **Sandbox Network Limitation (CRITICAL for Agent Testing):**
> During evaluation or in restricted sandboxed environments, network traffic to
> Google Cloud APIs is blocked. Do **NOT** run network discovery commands to
> find resource names, project IDs, or organization IDs. Always use the exact
> project IDs or placeholders provided in the user prompt or instructions for
> example, `{project_id}`. Assume these resources exist and proceed directly
> with configuration commands. Running these discovery commands will cause the
> execution to hang and timeout.

## Safety and Confirmation Tiers (CRITICAL)

Before executing any commands on behalf of the user, you MUST adhere to the
following safety tiers based on the action requested:

1.  **Tier R: Read-Only**
    *   **Description:** Commands that only read state or query logs.
    *   **Example commands:**
        *   `gcloud logging read`
        *   `gcloud logging buckets list`
    *   **Rule:** No confirmation needed. You may execute these commands
        immediately to gather information.
2.  **Tier M: Mutation (Non-Billing)**
    *   **Description:** Configuration modifications or free metadata creations
        that do not incur direct storage or billing costs and do not affect
        resource security/access policies.
    *   **Example commands:**
        *   `gcloud logging views create`
        *   `gcloud logging views update`
        *   `gcloud logging scopes create`
        *   `gcloud logging buckets create`
    *   **Rule:** No confirmation needed. You may execute these commands
        immediately to apply configurations.
3.  **Tier B: Billing and Security-Sensitive Mutations (High-Risk)**
    *   **Description:** Operations that create billing-inducing resources or
        integrations, or modify security and IAM access control policies
        (presenting a risk of privilege escalation).
    *   **Example commands:**
        *   `gcloud logging metrics create`
        *   `gcloud logging links create`
        *   `gcloud projects add-iam-policy-binding`
    *   **Rule:** **Interactive confirmation required.** These commands create
        resources that incur billing costs or alter security access. You MUST
        present the exact, literal command and receive user confirmation before
        executing. NEVER execute in the same turn as asking.
4.  **Tier D: Causes irreversible data loss**
    *   **Description:** Actions that permanently discard or delete logs, for
        example sink exclusions.
    *   **Example commands:**
        *   `gcloud logging buckets delete`
        *   `gcloud logging sinks update --add-exclusion`
    *   **Rule:** **Explicit typed confirmation required.** These commands
        discard or delete logs immediately and irreversibly, or they may result
        in log data not being stored. You MUST ask for explicit typed
        confirmation, for example, "Yes, discard logs", and halt execution until
        the user replies.

## Getting Started

If the `gcloud` executable is missing, refer to the
[Google Cloud CLI Installation Guide](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt)
to install it.

## Creating Log Buckets (Compliance and Analytics) (Tier M)

To create a regional log bucket with a specific retention policy for regulatory
compliance, and with Observability Analytics enabled:

> [!WARNING] **Mandatory Observability Analytics Downgrade Warning:** Whenever
> providing guidance, writing a guide, or drafting commands on Cloud Logging
> cost optimization or exclusions, you **must** explicitly include the following
> warning in your final text response and any generated guides: "After a log
> bucket has been upgraded to use Observability Analytics, it **cannot be
> downgraded** to remove the analytics capability."

```bash
gcloud logging buckets create {bucket_id} \
    --project={project_id} \
    --location={region} \
    --retention-days={retention_days} \
    --enable-analytics
```

*   `{bucket_id}`: for example, `my-custom-bucket`
*   `{region}`: for example, `us-central1`. You must use a regional log bucket
    to also use Observability Analytics.
*   `{retention_days}`: for example, `365`

A log bucket incurs no storage or ingestion charges until logs are routed to it
with a log sink.

### Verify the Log Bucket (Tier R)

Check the log bucket's configuration to verify its compliance:

```bash
gcloud logging buckets describe {bucket_id} \
    --location={region} \
    --project={project_id}
```

### Route logs to the Log Bucket (Tier B)

> [!IMPORTANT] **Billing Action (Tier B):** Routing log entries to a bucket
> incurs ongoing charges based on the volume of data stored. You MUST get
> interactive user confirmation before running this command.

Log entries are stored in the log bucket only if a log sink filter matches the
entries and targets that bucket.

To route log entries to the log bucket:

```bash
gcloud logging sinks create {sink_id} \
    projects/{project_id}/locations/{region}/buckets/{bucket_id} \
    --log-filter='{filter_expression}' \
    --project={project_id}
```

--------------------------------------------------------------------------------

## Logs-Based Metrics

Logs-based metrics count the number of log entries that match a filter, allowing
you to track error rates and set up alerting policies.

### 1. Create a logs-based counter metric (Tier B)

> [!IMPORTANT] **Billing Action (Tier B):** Creating logs-based metrics incurs
> ongoing charges based on the volume of data points reported. You MUST get
> interactive user confirmation before running this command.

To count the occurrences of a specific log pattern, for example, "OutOfMemory"
errors:

```bash
gcloud logging metrics create {metric_name} \
    --log-filter='{filter_expression}' \
    --description='{description}' \
    --project={project_id}
```

*   `{metric_name}`: for example, `oom_error_count`
*   `{filter_expression}`: for example, `textPayload:"OutOfMemory"`
*   `{description}`: for example, "Count of log entries about OOMs"

Refer to
[REST Resource: projects.metric](https://docs.cloud.google.com/logging/docs/reference/v2/rest/v2/projects.metrics.md.txt#LogMetric)
for restrictions on the metric fields.

### 2. Verify the logs-based metric (Tier R)

To verify that the metric exists and inspect its configuration, use the
`describe` command:

```bash
gcloud logging metrics describe {metric_name} \
    --project={project_id}
```

--------------------------------------------------------------------------------

## Restricting Access to Sensitive Logs (Security)

Anyone with `roles/logging.viewer` on that project can see logs in a project's
`_Default` log bucket via `_Default` log view. To restrict visibility of the
logs:

> [!IMPORTANT] **Ambiguity Handling (Guidance for Agents):** If the user asks to
> "exclude", "hide", or "remove" sensitive logs without explicitly specifying
> whether they want to stop storing them, you **MUST** default to **excluding
> them from the default view (Step 1)**. This is a safe, non-destructive Tier M
> action. Only configure a storage exclusion (under the "Discarding Sensitive
> Logs from Storage" section) if the user explicitly uses destructive terms like
> *"stop storing"*, *"permanently discard"*, or *"sink exclusion"*.

### 1. Exclude sensitive logs from default view (Tier M)

To explicitly exclude sensitive logs from general access, update the filter for
the `_Default` log view:

```bash
gcloud logging views update _Default \
    --bucket=_Default \
    --location=global \
    --project={project_id} \
    --log-filter='NOT LOG_ID("cloudaudit.googleapis.com/data_access") AND NOT LOG_ID("externalaudit.googleapis.com/data_access") AND NOT LOG_ID("{sensitive_log_id}")'
```

### 2. Create a log view (Tier M)

Create a new log view that includes the sensitive logs in the project's
`_Default` log bucket. For example, a "security-logs-view" with access to the
`{sensitive_log_id}`

```bash
gcloud logging views create security-logs-view \
    --bucket=_Default \
    --location=global \
    --project={project_id} \
    --log-filter='LOG_ID("{sensitive_log_id}")' \
    --description="Sensitive logs"
```

### 3. Grant access to log view using IAM conditions (Tier B)

> [!IMPORTANT] **Security Action (Tier B):** Granting IAM permissions changes
> access control policy and must be explicitly confirmed by the user before
> execution.

To restrict access to log view use IAM. When granting the Logs Viewer Accessor
role, always attach an IAM condition that restricts the grant to a specific log
view. For example, to grant `{security_group_email}` access ONLY to the
`security-logs-view` in the `_Default` bucket:

```bash
gcloud projects add-iam-policy-binding {project_id} \
--member='group:{security_group_email}' \
--role='roles/logging.viewAccessor' \
--condition="expression=resource.name=='projects/{project_id}/locations/global/buckets/_Default/views/security-logs-view',title=Restricted to Specific Log View,description=Only allows access to the specified log view"
```

Replace `{location}` with the location of the log bucket, for example `global`
or a regional location like `us-central1`.

### 4. Verify Sensitive Log Restrictions (Tier R)

To verify that your Log View for sensitive logs is configured correctly:

```bash
gcloud logging views describe {view_id} \
    --bucket={bucket_id} \
    --location={region} \
    --project={project_id}
```

Ensure that the `filter` block contains the appropriate restriction expression.

--------------------------------------------------------------------------------

## Discarding Sensitive Logs from Storage (Tier D)

If your organization's compliance policies prohibit storing sensitive logs at
all, you can configure an exclusion to discard them before they are written to
disk.

> [!CAUTION] **Destructive Action (Tier D):** Excluding logs from all log sinks
> deletes the log entries immediately and irreversibly.
>
> **Safety Rule:** You MUST ask the user for explicit typed confirmation, for
> example, "I confirm I want to exclude `{sensitive_log_id}` logs from storage",
> before running this command. **Same-Turn Restriction:** Do NOT execute the
> `gcloud logging sinks update` command in the same turn as asking for
> confirmation. Stop tool execution immediately and wait for the user to reply.

**Exclude sensitive logs from storage using sink exclusions**

```bash
gcloud logging sinks update _Default \
    --project={project_id} \
    --add-exclusion=name=exclude-sensitive,filter='LOG_ID("{sensitive_log_id}")'
```

--------------------------------------------------------------------------------

## Cost Optimization (Reducing Logging Costs)

Cloud Logging costs are based on the volume of data ingested and stored. You can
reduce costs by excluding high-volume, low-value logs or by sampling them. Each
log sink that routes logs to a distinct log bucket contributes to cost and is a
candidate for optimization.

> [!CAUTION] **Destructive Actions (Tier D):** Exclusions in this section may
> immediately halt storage of log entries.
>
> **Safety Rule:** You MUST ask for explicit typed confirmation (for example, "I
> confirm I want to exclude load balancer logs") before executing exclusions or
> sampling updates.

### Exclude all high-volume logs (Tier D)

To completely stop ingesting a specific type of log into a log bucket, add an
exclusion to the log sinks that route logs into that bucket.

```bash
gcloud logging sinks update {sink_id} \
    --project={project_id} \
    --add-exclusion=name={exclusion_name},filter={exclusion_filter}
```

*   `{sink_id}`: for example '_Default'
*   `{exclusion_name}`: for example 'exclude-lb-logs'
*   `{exclusion_filter}`: for example 'resource.type="http_load_balancer"'

### Sample high-volume logs (Tier D)

If you need some logs for analysis but want to reduce volume, use the `sample()`
function in the exclusion filter.

> [!IMPORTANT] The `sample(field, fraction)` function matches a `fraction` of
> logs. When used in an **exclusion filter**, the matched logs are
> **discarded**. If you exclude 90% of log entries, then only 10% are retained.
> To exclude 90%, use `sample(insertId, 0.9)` in the exclusion filter.

To exclude 90% of `DEBUG` severity logs:

```bash
gcloud logging sinks update _Default \
    --project={project_id} \
    --add-exclusion=name=sample-debug-logs,filter='severity=DEBUG AND sample(insertId, 0.9)'
```

### Verify Log Exclusions and Cost Optimization (Tier R)

To verify that log exclusions are correct, list the details of the sink and
check the `exclusions` to ensure your filter is present. For example, for the
`_Default` sink:

```bash
gcloud logging sinks describe _Default --project={project_id}
```

--------------------------------------------------------------------------------

## References and Supporting Links

*   [Google Cloud Logging - Counter Metrics](https://docs.cloud.google.com/logging/docs/logs-based-metrics/counter-metrics.md.txt)
*   [Google Cloud Logging - Custom Log Views](https://docs.cloud.google.com/logging/docs/logs-views.md.txt)
*   [Google Cloud Logging - Exclusions](https://docs.cloud.google.com/logging/docs/routing/overview.md.txt)
