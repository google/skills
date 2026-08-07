# Cloud Storage (GCS) LQL queries

## Base schema and structural patterns

Google Cloud Storage (GCS) telemetry is entirely driven by Cloud Audit Logs. GCS
utilizes Audit Logs to track everything from bucket provisioning
(administrative) to file downloads (data access).

### Core resource type

*   **Buckets (`gcs_bucket`)**: All GCS logs are bound to the bucket resource
    type. Filter explicitly using `resource.labels.bucket_name="<BUCKET_NAME>"`
    to scope queries to a specific bucket.

### Audit log routing

GCS logs split cleanly along the standard Cloud Audit Log paradigm:

*   **Admin Activity**: Use `log_id("cloudaudit.googleapis.com/activity")` to
    query control-plane mutations. This captures administrative operations like
    `storage.buckets.create`, `storage.buckets.delete`, and IAM policy
    modifications.
*   **Data Access**: Use `log_id("cloudaudit.googleapis.com/data_access")` to
    query object-level file interactions, like file uploads
    (`storage.objects.create`) or file reads (`storage.objects.get`).

### Operation targeting

*   Combine resource isolation with `protoPayload.methodName` (for example:
    `protoPayload.methodName="storage.objects.delete"`) to locate precise user
    or system actions.

## Example queries

### All audit logs for GCS buckets

**Variables to replace:** None

```lql
resource.type="gcs_bucket" AND
logName:"cloudaudit.googleapis.com"
```

### GCS bucket deletion logs

**Variables to replace:** None

```lql
resource.type="gcs_bucket" AND
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.methodName="storage.buckets.delete"
```

### GCS bucket logs

**Variables to replace:** `<BUCKET_NAME>`

```lql
resource.type="gcs_bucket" AND
resource.labels.bucket_name="<BUCKET_NAME>"
```

### GCS bucket creation logs

**Variables to replace:** None

```lql
resource.type="gcs_bucket" AND
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.methodName="storage.buckets.create"
```

