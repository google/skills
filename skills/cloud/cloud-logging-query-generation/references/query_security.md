# Security (audit logging) LQL queries

## Example queries

### Audit logs—all

**Variables to replace:** None

```lql
logName:"cloudaudit.googleapis.com"
```

### Audit logs—Access Transparency (AXT)

**Variables to replace:** None

```lql
log_id("cloudaudit.googleapis.com/access_transparency")
```

### Audit logs—Admin Activity

**Variables to replace:** None

```lql
log_id("cloudaudit.googleapis.com/activity")
```

### Audit logs—Data Access

**Variables to replace:** None

```lql
log_id("cloudaudit.googleapis.com/data_access")
```

### Audit logs—System Event

**Variables to replace:** None

```lql
log_id("cloudaudit.googleapis.com/system_event")
```

### VPC Service Controls access level attached

**Variables to replace:** `<ACCESS_LEVEL>`

```lql
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.serviceName="accesscontextmanager.googleapis.com" AND
protoPayload.methodName="google.identity.accesscontextmanager.v1.AccessContextManager.UpdateServicePerimeter" AND
-protoPayload.metadata.previousState:"<ACCESS_LEVEL>" AND
protoPayload.request.servicePerimeter.spec.accessLevels:"<ACCESS_LEVEL>"
```

### VPC Service Controls policy updated or deleted

**Variables to replace:** None

```lql
resource.type="audited_resource" AND
(protoPayload.methodName="AccessContextManager.UpdateServicePerimeter" OR
protoPayload.methodName="AccessContextManager.DeleteServicePerimeter")
```
