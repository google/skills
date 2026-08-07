# API enable and disable LQL queries

## Example queries

### Google Cloud Service API enablement audit logs

**Variables to replace:** None

```lql
resource.type="audited_resource" AND
protoPayload.methodName="google.api.serviceusage.v1.ServiceUsage.EnableService"
```

### Google Cloud Service API disablement audit logs

**Variables to replace:** None

```lql
resource.type="audited_resource" AND
protoPayload.methodName="google.api.serviceusage.v1.ServiceUsage.DisableService"
```

### Logging API disabled

**Variables to replace:** None

```lql
resource.type="audited_resource"
protoPayload.methodName="google.api.serviceusage.v1.ServiceUsage.DisableService"
protoPayload.authorizationInfo.granted="true"
protoPayload.response.service.state="DISABLED"
protoPayload.authorizationInfo.resource="services/logging.googleapis.com"
```
