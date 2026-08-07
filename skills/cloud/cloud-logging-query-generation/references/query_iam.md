# IAM and service accounts LQL queries

## Table of contents

- [Base schema and structural patterns](#base-schema-and-structural-patterns) (L20-L66)
- [Log types](#log-types) (L25-L30)
- [Resource types](#resource-types) (L32-L41)
- [PolicyDelta (Role Bindings)](#policydelta-role-bindings) (L43-L56)
- [Service account credentials](#service-account-credentials) (L58-L66)
- [Example queries](#example-queries) (L68-L159)
- [Service account creation logs](#service-account-creation-logs) (L70-L79)
- [Service account creation key logs](#service-account-creation-key-logs) (L81-L89)
- [Set access control policy logs](#set-access-control-policy-logs) (L91-L99)
- [External principal granted access to organization](#external-principal-granted-access-to-organization) (L101-L112)
- [Resource creation, modification, or deletion](#resource-creation-modification-or-deletion) (L114-L121)
- [Role granted to principal](#role-granted-to-principal) (L123-L134)
- [Role removed from principal](#role-removed-from-principal) (L136-L147)
- [Permission updated in a custom role](#permission-updated-in-a-custom-role) (L149-L159)

## Base schema and structural patterns

IAM operations span multiple resource types. Always constrain your query to the
correct target resource before writing payload logic.

### Log types

*   Use `log_id("cloudaudit.googleapis.com/activity")` for mutating operations
    (for example, granting roles, creating service accounts).
*   Use `log_id("cloudaudit.googleapis.com/data_access")` for read operations
    (for example, `GetRole`, `GetIamPolicy`, `ListServiceAccounts`).

### Resource types

*   **`project`**, **`folder`**, or **`organization`**: Use when the intent is
    to audit IAM role bindings or permissions assigned at the hierarchy level
    (for example, "Who granted the editor role on my project?").
*   **`service_account`**: Use when the intent is the creation, deletion, or
    modification of the Service Account identity itself, or the generation of
    its authentication keys.
*   **`iam_role`**: Use when auditing modifications made to Custom IAM Roles
    directly (for example, adding a new permission to an existing custom role).

### PolicyDelta (Role Bindings)

When auditing who was granted or revoked a role, do NOT look in the raw request.
Google Cloud translates all access control changes into a unified `policyDelta`
object.

*   `protoPayload.methodName`: Usually `"SetIamPolicy"`.
*   `protoPayload.serviceData.policyDelta.bindingDeltas.action`: The action
    taken, either `"ADD"` or `"REMOVE"`.
*   `protoPayload.serviceData.policyDelta.bindingDeltas.member`: The principal
    being modified (for example, `"user:alice@example.com"` or
    `"serviceAccount:my-sa@example.com"`).
*   `protoPayload.serviceData.policyDelta.bindingDeltas.role`: The precise IAM
    role being modified (for example, `"roles/editor"`).

### Service account credentials

When a user asks about Service Account Keys (which present a high security risk
if leaked), target the admin API methods directly:

*   `protoPayload.methodName`: Use
    `"google.iam.admin.v1.CreateServiceAccountKey"` for key generation events,
    and `"google.iam.admin.v1.CreateServiceAccount"` for the initial account
    creation.

## Example queries

### Service account creation logs

**Variables to replace:** `<EMAIL_ID>`

```lql
resource.type="service_account" AND
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.methodName="google.iam.admin.v1.CreateServiceAccount" AND
protoPayload.response.email="<EMAIL_ID>"
```

### Service account creation key logs

**Variables to replace:** None

```lql
resource.type="service_account" AND
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.methodName="google.iam.admin.v1.CreateServiceAccountKey"
```

### Set access control policy logs

**Variables to replace:** None

```lql
resource.type="project" AND
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.methodName="SetIamPolicy"
```

### External principal granted access to organization

**Variables to replace:** `<DOMAIN_NAME>`

```lql
resource.type="project" AND
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.@type="type.googleapis.com/google.cloud.audit.AuditLog" AND
protoPayload.request.@type:"IamPolicy" AND
protoPayload.serviceData.policyDelta.bindingDeltas.member:* AND
NOT protoPayload.serviceData.policyDelta.bindingDeltas.member:"@<DOMAIN_NAME>.com"
```

### Resource creation, modification, or deletion

**Variables to replace:** None

```lql
log_id("cloudaudit.googleapis.com/activity") AND
(SEARCH(protoPayload.methodName, "create") OR SEARCH(protoPayload.methodName, "delete") OR SEARCH(protoPayload.methodName, "update"))
```

### Role granted to principal

**Variables to replace:** `<EMAIL_ID>`

```lql
log_id("cloudaudit.googleapis.com/activity") AND
resource.type="project" AND
protoPayload.serviceName="cloudresourcemanager.googleapis.com" AND
protoPayload.methodName="SetIamPolicy" AND
protoPayload.serviceData.policyDelta.bindingDeltas.action="ADD" AND
protoPayload.serviceData.policyDelta.bindingDeltas.member:"<EMAIL_ID>"
```

### Role removed from principal

**Variables to replace:** `<EMAIL_ID>`

```lql
log_id("cloudaudit.googleapis.com/activity") AND
resource.type="project" AND
protoPayload.serviceName="cloudresourcemanager.googleapis.com" AND
protoPayload.methodName="SetIamPolicy" AND
protoPayload.serviceData.policyDelta.bindingDeltas.action="Remove" AND
protoPayload.serviceData.policyDelta.bindingDeltas.member:"<EMAIL_ID>"
```

### Permission updated in a custom role

**Variables to replace:** `<ROLE_ID>`

```lql
log_id("cloudaudit.googleapis.com/activity") AND
resource.type="iam_role" AND
protoPayload.serviceName="iam.googleapis.com" AND
SEARCH(protoPayload.methodName, "UpdateRole") AND
resource.labels.role_name:"<ROLE_ID>"
```
