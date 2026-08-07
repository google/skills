# Cloud Observability and Monitoring LQL queries

## Example queries

### Log sink activities

**Variables to replace:** None

```lql
resource.type="logging_sink" AND
log_id("cloudaudit.googleapis.com/activity")
```

### Log-based metric create or update activities

**Variables to replace:** None

```lql
resource.type="metric" AND
log_id("cloudaudit.googleapis.com/activity") AND
(SEARCH(protoPayload.methodName, "UpdateLogMetric") OR SEARCH(protoPayload.methodName, "CreateLogMetric"))
```

### Notification channel errors

**Variables to replace:** None

```lql
resource.type="stackdriver_notification_channel" AND
severity >= ERROR
```

### Notification channel errors due to throttling

**Variables to replace:** None

```lql
resource.type="stackdriver_notification_channel" AND
severity>=ERROR AND
jsonPayload.summary="Notification delivery throttled."
```

### Uptime checks - all logs

**Variables to replace:** None

```lql
resource.type="uptime_url"
```

### Uptime checks for a specific host

**Variables to replace:** `<URL>`

```lql
resource.type="uptime_url" AND
resource.labels.host="<URL>"
```

### Audit logs configuration removed or disabled

**Variables to replace:** None

```lql
log_id("cloudaudit.googleapis.com/activity") AND
resource.type=("organization" OR "project" OR "folder") AND
protoPayload.serviceData.policyDelta.auditConfigDeltas.action="REMOVE"
```
