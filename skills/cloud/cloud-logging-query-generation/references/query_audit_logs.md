# Audit logs reference

## Table of contents

- [Log types (log_id)](#log-types-log_id) (L19-L35)
- [Base schema (protoPayload)](#base-schema-protopayload) (L37-L75)
- [Common structural patterns](#common-structural-patterns) (L77-L112)
- [The policy and IAM mutation pattern](#the-policy-and-iam-mutation-pattern) (L82-L89)
- [The client configuration pattern](#the-client-configuration-pattern) (L91-L112)
- [Example queries](#example-queries) (L114-L199)
- [IAM role added or removed for a principal (Admin Activity)](#iam-role-added-or-removed-for-a-principal-admin-activity) (L116-L129)
- [GCE Firewall rule logging disabled (Admin Activity)](#gce-firewall-rule-logging-disabled-admin-activity) (L131-L140)
- [VPC SC access level attached to a perimeter (Admin Activity)](#vpc-sc-access-level-attached-to-a-perimeter-admin-activity) (L142-L152)
- [API service disabled (Admin Activity)](#api-service-disabled-admin-activity) (L154-L165)
- [BigQuery job execution (Data Access)](#bigquery-job-execution-data-access) (L167-L176)
- [GCE node preempted (System Event)](#gce-node-preempted-system-event) (L178-L187)
- [VPC Service Controls access blocked (Policy Denied)](#vpc-service-controls-access-blocked-policy-denied) (L189-L199)

## Log types (log_id)

GCP Audit logs are strictly categorized into 4 types. Depending on the intent,
filter your queries using the corresponding `log_id()`:

*   **Admin Activity** (`log_id("cloudaudit.googleapis.com/activity")`):
    User-driven API calls that **modify** configuration or metadata (for
    example, creating VMs, changing IAM roles).
*   **Data Access** (`log_id("cloudaudit.googleapis.com/data_access")`): API
    calls that **read** configuration/metadata, or user-driven calls that
    create, modify, or read user-provided *data*.
*   **System Event** (`log_id("cloudaudit.googleapis.com/system_event")`):
    **Google Cloud systems** modifying resources automatically (not driven by
    direct user action, like autoscalers).
*   **Policy Denied** (`log_id("cloudaudit.googleapis.com/policy")`): A Google
    Cloud service denies access because of a security policy violation (for
    example, VPC Service Controls blocking access).

## Base schema (protoPayload)

**Actor details (Who did it?)**

*   `protoPayload.authenticationInfo.principalEmail`: The email of the
    authenticated user or service account. (Example: `="alice@example.com"`)

**Action details (What was done?)**

*   `protoPayload.methodName`: The API method called.
    *   *Gotcha:* Prefer the exact match operator (`=`) when you know the exact
        API string. Use the scoped `SEARCH()` function (e.g.,
        `SEARCH(protoPayload.methodName, "compute.instances.insert")`) as a
        fallback if you do not reliably know the full method name prefix. Do NOT
        use the colon operator (`:`) as it may cause false positives by matching
        a substring.
*   `protoPayload.resourceName`: The exact resource being acted upon.

**Network and Context (From where/how?)**

*   `protoPayload.requestMetadata.callerIp`: The IP address of the caller.
    (Example: `="192.168.1.1"`)
*   `protoPayload.requestMetadata.requestAttributes.*`: Context used for IAM
    condition evaluations (for example, `.time` or `.reason`).

**Authorization and Permissions (Why was it allowed/denied?)**

*   `protoPayload.authorizationInfo.permission`: The IAM permission checked.
    (Example: `="compute.instances.delete"`)
*   `protoPayload.authorizationInfo.granted`: Whether the permission check
    succeeded (`true` or `false`).
*   `protoPayload.authorizationInfo.resource`: The specific resource the
    permission was checked against.

**Outcomes (Did it succeed?)**

*   `protoPayload.status.code`: The RPC status code (0 means success). To find
    failures, use `protoPayload.status.code!=0`.
*   `protoPayload.status.message`: The developer-facing error message.

## Common structural patterns

Audit log custom payloads structure information differently depending on the
intent. Use these patterns to synthesize queries.

### The policy and IAM mutation pattern

When a user asks about changes to permissions, roles, or access rules across
*any* service (IAM, Storage, and others), GCP almost always puts this in
`policyDelta` rather than the raw request.

**Rule:** For role or permission changes, look under
`protoPayload.serviceData.policyDelta` (or `metadata.policyDelta`).

### The client configuration pattern

When a user wants to know if a specific configuration setting was applied (for
example, "was logging disabled?", "what IP was assigned?"), that data lives in
the `request` payload.

**Rule:** For user-provided configuration values, look under
`protoPayload.request`.

**Warning:** The structure of `protoPayload.request` maps exactly to the
underlying REST/gRPC API schema of each individual service and varies
drastically between them. Do not assume its structure, but you may cautiously
inspect `protoPayload.request` (for example, `protoPayload.request.account_id`)
or `protoPayload.response` if it logically maps to the user's intent. Do not
fall back to `protoPayload.resourceName` for identifying newly created target
resources, as `resourceName` often reflects the parent scope (e.g., the
Project).

**Note:** For state diffs and update verifications (to ensure something was
*newly* added rather than just present in a broader update), you must also use
the `protoPayload.metadata.previousState` object (for example, negating it to
ensure it wasn't there before).

## Example queries

### IAM role added or removed for a principal (Admin Activity)

**Variables to replace:** `<USER_EMAIL>` *(Note: Change resource.type to
"folder" or "organization" for higher-level changes)*

```lql
log_id("cloudaudit.googleapis.com/activity") AND
resource.type="project" AND
protoPayload.methodName="SetIamPolicy" AND
protoPayload.serviceName="cloudresourcemanager.googleapis.com" AND
(protoPayload.serviceData.policyDelta.bindingDeltas.action="ADD" OR
protoPayload.serviceData.policyDelta.bindingDeltas.action="REMOVE") AND
protoPayload.serviceData.policyDelta.bindingDeltas.member="user:<USER_EMAIL>"
```

### GCE Firewall rule logging disabled (Admin Activity)

**Variables to replace:** None

```lql
log_id("cloudaudit.googleapis.com/activity") AND
resource.type="gce_firewall_rule" AND
protoPayload.methodName="v1.compute.firewalls.patch" AND
protoPayload.request.logConfig.enable="false"
```

### VPC SC access level attached to a perimeter (Admin Activity)

**Variables to replace:** `<ACCESS_LEVEL_NAME>`

```lql
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.serviceName="accesscontextmanager.googleapis.com" AND
SEARCH(protoPayload.methodName, "UpdateServicePerimeter") AND
protoPayload.request.servicePerimeter.spec.accessLevels:"<ACCESS_LEVEL_NAME>" AND
-protoPayload.metadata.previousState:"<ACCESS_LEVEL_NAME>"
```

### API service disabled (Admin Activity)

**Variables to replace:** `<API_NAME>` *(Note: To find when a generic API was
disabled, use `audited_resource`, which differs from normal service endpoints.)*

```lql
log_id("cloudaudit.googleapis.com/activity") AND
resource.type="audited_resource" AND
protoPayload.methodName="google.api.serviceusage.v1.ServiceUsage.DisableService" AND
protoPayload.authorizationInfo.granted="true" AND
protoPayload.authorizationInfo.resource:"services/<API_NAME>.googleapis.com"
```

### BigQuery job execution (Data Access)

**Variables to replace:** `<USER_EMAIL>`

```lql
log_id("cloudaudit.googleapis.com/data_access") AND
resource.type="bigquery_project" AND
protoPayload.methodName=("google.cloud.bigquery.v2.JobService.InsertJob" OR "google.cloud.bigquery.v2.JobService.Query") AND
protoPayload.authenticationInfo.principalEmail="<USER_EMAIL>"
```

### GCE node preempted (System Event)

**Variables to replace:** `<INSTANCE_ID>`

```lql
log_id("cloudaudit.googleapis.com/system_event") AND
resource.type="gce_instance" AND
protoPayload.methodName="compute.instances.preempted" AND
resource.labels.instance_id="<INSTANCE_ID>"
```

### VPC Service Controls access blocked (Policy Denied)

**Variables to replace:** `<UNIQUE_ID>`

```lql
log_id("cloudaudit.googleapis.com/policy") AND
severity=ERROR AND
resource.type="audited_resource" AND
protoPayload.metadata.@type="type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata" AND
protoPayload.metadata.vpcServiceControlsUniqueId="<UNIQUE_ID>"
```
