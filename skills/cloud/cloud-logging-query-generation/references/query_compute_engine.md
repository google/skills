# Compute Engine (GCE) LQL queries

## Table of contents

- [Base schema and structural patterns](#base-schema-and-structural-patterns) (L44-L101)
- [Core resource types](#core-resource-types) (L50-L60)
- [Guest OS and application logs (Ops Agent)](#guest-os-and-application-logs-ops-agent) (L62-L72)
- [Boot and kernel logs (serial console)](#boot-and-kernel-logs-serial-console) (L74-L81)
- [Google infrastructure system events](#google-infrastructure-system-events) (L83-L91)
- [User activity audit logs](#user-activity-audit-logs) (L93-L101)
- [Example queries](#example-queries) (L103-L467)
- [Activity audit logs for Compute Engine instances](#activity-audit-logs-for-compute-engine-instances) (L105-L112)
- [System logs (syslog) emitted by Compute Engine instances](#system-logs-syslog-emitted-by-compute-engine-instances) (L114-L121)
- [Compute Engine firewall rule deletion](#compute-engine-firewall-rule-deletion) (L123-L131)
- [Compute Engine VM authlogs](#compute-engine-vm-authlogs) (L133-L140)
- [Compute Engine host error](#compute-engine-host-error) (L142-L155)
- [Compute Engine host memory alert](#compute-engine-host-memory-alert) (L157-L170)
- [Compute Engine host migrated](#compute-engine-host-migrated) (L172-L186)
- [Compute Engine VM terminated/preempted](#compute-engine-vm-terminatedpreempted) (L188-L197)
- [Compute Engine VM terminated due to scratch disk creation failure](#compute-engine-vm-terminated-due-to-scratch-disk-creation-failure) (L199-L213)
- [Compute Engine zone resource pool exhaustion (stockout)](#compute-engine-zone-resource-pool-exhaustion-stockout) (L215-L226)
- [Compute Engine VM instance created](#compute-engine-vm-instance-created) (L228-L237)
- [Compute Engine VM instance deleted with name](#compute-engine-vm-instance-deleted-with-name) (L239-L248)
- [Compute Engine VM instance deleted with ID](#compute-engine-vm-instance-deleted-with-id) (L250-L259)
- [Compute Engine VM instance restarted](#compute-engine-vm-instance-restarted) (L261-L271)
- [Compute Engine Shielded VM boot integrity failure](#compute-engine-shielded-vm-boot-integrity-failure) (L273-L282)
- [Compute Engine VM instance stopped by Guest OS](#compute-engine-vm-instance-stopped-by-guest-os) (L284-L296)
- [Compute Engine Shielded VM boot file was blocked](#compute-engine-shielded-vm-boot-file-was-blocked) (L298-L307)
- [Persistent disk created](#persistent-disk-created) (L309-L318)
- [Nodes added in sole-tenant node](#nodes-added-in-sole-tenant-node) (L320-L331)
- [Autoscale events in sole-tenant node](#autoscale-events-in-sole-tenant-node) (L333-L343)
- [Manual snapshot taken](#manual-snapshot-taken) (L345-L354)
- [Scheduled snapshot taken](#scheduled-snapshot-taken) (L356-L366)
- [Snapshot schedule created](#snapshot-schedule-created) (L368-L377)
- [Snapshot schedule attached](#snapshot-schedule-attached) (L379-L389)
- [Quota exceeded](#quota-exceeded) (L391-L400)
- [Query unhealthy instances in instance group](#query-unhealthy-instances-in-instance-group) (L402-L410)
- [Query instance group members within a time frame in UTC time format](#query-instance-group-members-within-a-time-frame-in-utc-time-format) (L412-L423)
- [Instances added to instance group](#instances-added-to-instance-group) (L425-L434)
- [Instances removed from instance group](#instances-removed-from-instance-group) (L436-L445)
- [Instance template set or updated](#instance-template-set-or-updated) (L447-L457)
- [Firewall logs](#firewall-logs) (L459-L467)

## Base schema and structural patterns

Compute Engine logs are highly segmented depending on whether you are analyzing
the VM's internal operating system, Google's infrastructure events, or
user-driven API audit logs.

### Core resource types

*   **VM Instances (`gce_instance`)**: The most common resource type. Use this
    when analyzing a running VM (Guest OS), its boot console, or its lifecycle
    events.
*   **Storage (`gce_disk`, `gce_snapshot`)**: Use for operations on persistent
    disks and snapshots.
*   **Networking (`gce_firewall_rule`, `gce_route`, `gce_network`)**: Use for
    infrastructure-level network changes, NOT for traffic flow logs.
*   **Groups (`gce_instance_group`, `gce_instance_template`)**: Use for Managed
    Instance Group (MIG) scaling, creation, and health checks.

### Guest OS and application logs (Ops Agent)

When a user asks to search for "errors inside my VM", "syslog", "auth requests",
or "app logs":

*   Target `resource.type="gce_instance"`.
*   These are usually ingested via the Ops Agent.
*   Filter by `log_id("syslog")`, `log_id("winevt.raw")`, or the custom file
    `log_id`.
*   The raw log string is found in `textPayload` (unstructured) or `jsonPayload`
    (structured).

### Boot and kernel logs (serial console)

When a VM is unbootable, crashing on startup, or experiencing kernel panics:

*   Target `resource.type="gce_instance"`.
*   Filter by `log_id("serialconsole.googleapis.com/serial_port_1_output")`.
*   Search within `textPayload` (for example, `"kernel panic"`, `"Out of
    memory"`).

### Google infrastructure system events

When a VM is preempted, terminated by Google, or migrated during a host error:

*   Target `resource.type="gce_instance"`.
*   Filter by `log_id("cloudaudit.googleapis.com/system_event")`.
*   System events are NOT driven by users, so they are logged as system events.
    Use `protoPayload.methodName` (for example, `"compute.instances.hostError"`,
    `"compute.instances.preempted"`).

### User activity audit logs

When a user asks "who deleted my VM", "who stopped the instance", or "when was
this disk attached":

*   Target the relevant resource type (`gce_instance`, `gce_disk`, etc.).
*   Filter by `log_id("cloudaudit.googleapis.com/activity")`.
*   Use `protoPayload.methodName` (for example, `"v1.compute.instances.delete"`,
    `"v1.compute.disks.attach"`).

## Example queries

### Activity audit logs for Compute Engine instances

**Variables to replace:** None

```lql
resource.type="gce_instance" AND
log_id("cloudaudit.googleapis.com/activity")
```

### System logs (syslog) emitted by Compute Engine instances

**Variables to replace:** None

```lql
resource.type="gce_instance" AND
log_id("syslog")
```

### Compute Engine firewall rule deletion

**Variables to replace:** None

```lql
resource.type="gce_firewall_rule" AND
log_id("cloudaudit.googleapis.com/activity") AND
SEARCH(protoPayload.methodName, "firewalls.delete")
```

### Compute Engine VM authlogs

**Variables to replace:** None

```lql
resource.type="gce_instance" AND
log_id("authlog")
```

### Compute Engine host error

**Variables to replace:** `<INSTANCE_ID>`

```lql
resource.type="gce_instance" AND
protoPayload.serviceName="compute.googleapis.com" AND
(SEARCH(protoPayload.methodName, "compute.instances.hostError")
OR
operation.producer:"compute.instances.hostError") AND
log_id("cloudaudit.googleapis.com/system_event") AND
resource.labels.instance_id="<INSTANCE_ID>" AND
severity=INFO
```

### Compute Engine host memory alert

**Variables to replace:** `<INSTANCE_ID>`

```lql
resource.type="gce_instance" AND
protoPayload.serviceName="compute.googleapis.com" AND
(jsonPayload.methodName:"compute.instances.host_event_notify"
OR
operation.producer:"compute.instances.host_event_notify") AND
log_id("cloudaudit.googleapis.com/host_event_notify") AND
resource.labels.instance_id="<INSTANCE_ID>" AND
severity=CRITICAL
```

### Compute Engine host migrated

**Variables to replace:** `<INSTANCE_ID>`

```lql
resource.type="gce_instance" AND
protoPayload.serviceName="compute.googleapis.com" AND
(SEARCH(protoPayload.methodName, "compute.instances.migrateOnHostMaintenance")
OR
operation.producer:
"compute.instances.migrateOnHostMaintenance") AND
log_id("cloudaudit.googleapis.com/system_event") AND
resource.labels.instance_id="<INSTANCE_ID>" AND
severity=INFO
```

### Compute Engine VM terminated/preempted

**Variables to replace:** `<INSTANCE_ID>`

```lql
resource.type="gce_instance" AND
protoPayload.methodName=~"compute\.instances\.(guestTerminate|preempted)" AND
log_id("cloudaudit.googleapis.com/system_event") AND
resource.labels.instance_id="<INSTANCE_ID>"
```

### Compute Engine VM terminated due to scratch disk creation failure

**Variables to replace:** `<INSTANCE_ID>`

```lql
resource.type="gce_instance" AND
protoPayload.serviceName="compute.googleapis.com" AND
(protoPayload.methodName="compute.instances.scratchDiskCreationFailed"
OR
operation.producer:
"compute.instances.scratchDiskCreationFailed") AND
log_id("cloudaudit.googleapis.com/system_event") AND
resource.labels.instance_id="<INSTANCE_ID>" AND
severity=INFO
```

### Compute Engine zone resource pool exhaustion (stockout)

**Variables to replace:** None

```lql
resource.type="gce_instance" AND
log_id("cloudaudit.googleapis.com/activity") AND
(protoPayload.methodName="v1.compute.instances.start" OR
protoPayload.methodName="v1.compute.instances.insert") AND
protoPayload.status.message=~"(ZONE_RESOURCE_POOL_EXHAUSTED|does not have enough resources|resource pool exhausted)" AND
severity>=WARNING
```

### Compute Engine VM instance created

**Variables to replace:** `<INSTANCE_NAME>`

```lql
resource.type="gce_instance" AND
SEARCH(protoPayload.methodName, "compute.instances.insert") AND
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.request.name="<INSTANCE_NAME>"
```

### Compute Engine VM instance deleted with name

**Variables to replace:** `<INSTANCE_NAME>`

```lql
resource.type="gce_instance" AND
SEARCH(protoPayload.methodName, "compute.instances.delete") AND
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.resourceName:"<INSTANCE_NAME>"
```

### Compute Engine VM instance deleted with ID

**Variables to replace:** `<INSTANCE_ID>`

```lql
resource.type="gce_instance" AND
SEARCH(protoPayload.methodName, "compute.instances.delete") AND
log_id("cloudaudit.googleapis.com/activity") AND
resource.labels.instance_id="<INSTANCE_ID>"
```

### Compute Engine VM instance restarted

**Variables to replace:** `<INSTANCE_ID>`

```lql
resource.type="gce_instance" AND
protoPayload.methodName=~"compute\.instances\.(start|stop|reset|automaticRestart|guestTerminate|instanceManagerHaltForRestart)" AND
(log_id("cloudaudit.googleapis.com/activity")
OR log_id("cloudaudit.googleapis.com/system_event")) AND
resource.labels.instance_id="<INSTANCE_ID>"
```

### Compute Engine Shielded VM boot integrity failure

**Variables to replace:** `<INSTANCE_ID>`

```lql
resource.type="gce_instance" AND
log_id("compute.googleapis.com/shielded_vm_integrity") AND
jsonPayload.earlyBootReportEvent.policyEvaluationPassed="false" AND
resource.labels.instance_id="<INSTANCE_ID>"
```

### Compute Engine VM instance stopped by Guest OS

**Variables to replace:** `<INSTANCE_ID>`

```lql
resource.type="gce_instance" AND
protoPayload.serviceName="compute.googleapis.com" AND
(SEARCH(protoPayload.methodName, "compute.instances.guestTerminate") OR
operation.producer:"compute.instances.guestTerminate") AND
log_id("cloudaudit.googleapis.com/system_event") AND
resource.labels.instance_id="<INSTANCE_ID>" AND
severity=INFO
```

### Compute Engine Shielded VM boot file was blocked

**Variables to replace:** `<INSTANCE_ID>`

```lql
resource.type="gce_instance" AND
log_id("serialconsole.googleapis.com/serial_port_1_output") AND
textPayload:"Security Violation" AND
resource.labels.instance_id="<INSTANCE_ID>"
```

### Persistent disk created

**Variables to replace:** `<PERSISTENT_DISK_NAME>`

```lql
resource.type="gce_disk" AND
SEARCH(protoPayload.methodName, "compute.disks.insert") AND
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.resourceName: "<PERSISTENT_DISK_NAME>"
```

### Nodes added in sole-tenant node

**Variables to replace:** `<NODE_GROUP_ID>`

```lql
resource.type="gce_node_group" AND
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.methodName=~("compute.nodeGroups.addNodes"
OR "compute.nodeGroups.insert") AND
resource.labels.node_group_id="<NODE_GROUP_ID>" AND
severity=INFO
```

### Autoscale events in sole-tenant node

**Variables to replace:** `<NODE_GROUP_ID>`

```lql
resource.type="gce_node_group" AND
log_id("cloudaudit.googleapis.com/system_event") AND
protoPayload.methodName=~("compute.nodeGroups.deleteNodes"
OR "compute.nodeGroups.addNodes") AND
resource.labels.node_group_id="<NODE_GROUP_ID>"
```

### Manual snapshot taken

**Variables to replace:** `<SNAPSHOT_NAME>`

```lql
resource.type="gce_snapshot" AND
log_id("cloudaudit.googleapis.com/activity") AND
SEARCH(protoPayload.methodName, "compute.snapshots.insert") AND
protoPayload.resourceName:"<SNAPSHOT_NAME>"
```

### Scheduled snapshot taken

**Variables to replace:** `<PERSISTENT_DISK_NAME>`

```lql
resource.type="gce_disk" AND
log_id("cloudaudit.googleapis.com/system_event") AND
protoPayload.methodName="ScheduledSnapshots" AND
protoPayload.response.operationType="createSnapshot" AND
protoPayload.response.targetLink="<PERSISTENT_DISK_NAME>"
```

### Snapshot schedule created

**Variables to replace:** `<SCHEDULE_NAME>`

```lql
resource.type="gce_resource_policy" AND
log_id("cloudaudit.googleapis.com/activity") AND
SEARCH(protoPayload.methodName, "compute.resourcePolicies.insert") AND
protoPayload.request.name="<SCHEDULE_NAME>"
```

### Snapshot schedule attached

**Variables to replace:** `<PERSISTENT_DISK_NAME>`, `<SCHEDULE_NAME>`

```lql
resource.type="gce_disk" AND
log_id("cloudaudit.googleapis.com/activity") AND
SEARCH(protoPayload.methodName, "compute.disks.addResourcePolicies") AND
protoPayload.request.resourcePolicys:"<SCHEDULE_NAME>" AND
protoPayload.resourceName:"<PERSISTENT_DISK_NAME>"
```

### Quota exceeded

**Variables to replace:** None

```lql
resource.type="gce_instance" AND
SEARCH(protoPayload.methodName, "compute.instances.insert") AND
protoPayload.status.message:"QUOTA_EXCEEDED" AND
severity=ERROR
```

### Query unhealthy instances in instance group

**Variables to replace:** `<INSTANCE_GROUP_NAME>`

```lql
resource.type="gce_instance_group" AND
resource.labels.instance_group_name="<INSTANCE_GROUP_NAME>" AND
jsonPayload.healthCheckProbeResult.healthState="UNHEALTHY"
```

### Query instance group members within a time frame in UTC time format

**Variables to replace:** `<END_TIME>`, `<INSTANCE_GROUP_NAME>`, `<START_TIME>`

```lql
resource.type="gce_instance_group_manager" AND
resource.labels.instance_group_manager_name="<INSTANCE_GROUP_NAME>" AND
jsonPayload.@type=
"type.googleapis.com/compute.InstanceGroupManagerEvent" AND
jsonPayload.instanceHealthStateChange.detailedHealthState="HEALTHY" AND
timestamp >= "<START_TIME>" AND timestamp <= "<END_TIME>"
```

### Instances added to instance group

**Variables to replace:** `<INSTANCE_GROUP_NAME>`

```lql
resource.type="gce_instance_group" AND
SEARCH(protoPayload.methodName, "compute.instanceGroups.addInstances") AND
log_id("cloudaudit.googleapis.com/activity") AND
resource.labels.instance_group_name="<INSTANCE_GROUP_NAME>"
```

### Instances removed from instance group

**Variables to replace:** `<INSTANCE_GROUP_NAME>`

```lql
resource.type="gce_instance_group" AND
SEARCH(protoPayload.methodName, "compute.instanceGroups.removeInstances") AND
log_id("cloudaudit.googleapis.com/activity") AND
resource.labels.instance_group_name="<INSTANCE_GROUP_NAME>"
```

### Instance template set or updated

**Variables to replace:** `<INSTANCE_GROUP_MANAGER>`

```lql
resource.type="gce_instance_group_manager" AND
log_id("cloudaudit.googleapis.com/activity") AND
protoPayload.methodName=
"v1.compute.instanceGroupManagers.setInstanceTemplate" AND
resource.labels.instance_group_manager_name="<INSTANCE_GROUP_MANAGER>"
```

### Firewall logs

**Variables to replace:** `<INSTANCE_NAME>`

```lql
resource.type="gce_subnetwork" AND
log_id("compute.googleapis.com/firewall") AND
jsonPayload.instance.vm_name="<INSTANCE_NAME>"
```
