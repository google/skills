# Networking LQL queries

## Table of contents

- [Base schema and structural patterns](#base-schema-and-structural-patterns) (L29-L79)
- [Core resource types](#core-resource-types) (L34-L41)
- [VPC flow logs schema](#vpc-flow-logs-schema) (L43-L57)
- [Firewall rules schema](#firewall-rules-schema) (L59-L66)
- [Load balancer top-level abstraction](#load-balancer-top-level-abstraction) (L68-L79)
- [Example queries](#example-queries) (L81-L248)
- [Firewall - all logs](#firewall---all-logs) (L83-L90)
- [Firewall logs for a given country](#firewall-logs-for-a-given-country) (L92-L100)
- [Firewall logs from a VM](#firewall-logs-from-a-vm) (L102-L110)
- [Firewall subnet logs](#firewall-subnet-logs) (L112-L120)
- [Compute Engine subnetwork traffic logs to a subnet](#compute-engine-subnetwork-traffic-logs-to-a-subnet) (L122-L129)
- [VPC flow logs](#vpc-flow-logs) (L131-L138)
- [VPC flow logs for specific port and protocol](#vpc-flow-logs-for-specific-port-and-protocol) (L140-L149)
- [VPC flow logs for specific subnet](#vpc-flow-logs-for-specific-subnet) (L151-L159)
- [VPC flow logs for specific subnet prefix](#vpc-flow-logs-for-specific-subnet-prefix) (L161-L169)
- [VPC flow logs for a specific VM](#vpc-flow-logs-for-a-specific-vm) (L171-L179)
- [VPN gateway logs](#vpn-gateway-logs) (L181-L188)
- [HTTP load balancer 5xx errors](#http-load-balancer-5xx-errors) (L190-L197)
- [HTTP load balancer requests to PHPMyAdmin](#http-load-balancer-requests-to-phpmyadmin) (L199-L206)
- [HTTP load balancer spillover events](#http-load-balancer-spillover-events) (L208-L216)
- [VPN gateway peer not responding](#vpn-gateway-peer-not-responding) (L218-L225)
- [VPC flow logs egress (excluding internal traffic)](#vpc-flow-logs-egress-excluding-internal-traffic) (L227-L237)
- [Cloud CDN signed URL 403 errors](#cloud-cdn-signed-url-403-errors) (L239-L248)

## Base schema and structural patterns

Google Cloud networking telemetry utilizes highly specialized, deeply nested log
structures that differ fundamentally from standard application logs.

### Core resource types

*   **Subnetworks (`gce_subnetwork`)**: The anchor resource type for both VPC
    Flow Logs and Firewall Rules Logs.
*   **Load Balancers (`http_load_balancer`, `tcp_load_balancer`)**: Captures
    ingress traffic and backend routing metrics.
*   **Gateways and Routers (`vpn_gateway`, `cloud_router`)**: Captures edge
    transit telemetry.

### VPC flow logs schema

When searching for "network traffic", "port connections", "traffic from a
subnet", or "VM-to-VM traffic", you are querying VPC Flow Logs.

*   **Target:** `resource.type="gce_subnetwork"` AND
    `log_id("compute.googleapis.com/vpc_flows")`.
*   **Nested Architecture:** Flow logs do *not* use a flat payload. They use
    three deep jsonPayload hierarchies:
    *   Connection Details: `jsonPayload.connection.src_port`,
        `jsonPayload.connection.protocol`, `jsonPayload.connection.dest_ip`.
    *   Source Details: `jsonPayload.src_instance.vm_name`.
    *   Destination Details: `jsonPayload.dest_instance.vm_name`.
*   **CIDR Matching:** Always use the `ip_in_net()` function for CIDR range
    matching against IPs, rather than strictly matching substrings.

### Firewall rules schema

When checking "firewall hits", "blocked traffic", or "allowed traffic":

*   **Target:** `resource.type="gce_subnetwork"` AND
    `log_id("compute.googleapis.com/firewall")`.
*   **Rule Attributes:** Found in `jsonPayload.rule_details`.
*   **Location Attributes:** Found in `jsonPayload.remote_location.country`.

### Load balancer top-level abstraction

When debugging a Load Balancer (for example, tracking down 500 errors or
specific URL paths):

*   **Target:** `resource.type="http_load_balancer"`.
*   **The Gotcha:** Cloud Load Balancing natively promotes HTTP properties to
    the top-level `httpRequest` object of the LogEntry.
*   **Do not use `jsonPayload` for HTTP elements.** Query `httpRequest.status`,
    `httpRequest.requestMethod`, and `httpRequest.requestUrl`.
*   *Note:* Internal LB orchestration (like "spilled over" events) will still
    reside in `jsonPayload.statusDetails`.

## Example queries

### Firewall - all logs

**Variables to replace:** None

```lql
resource.type="gce_subnetwork" AND
log_id("compute.googleapis.com/firewall")
```

### Firewall logs for a given country

**Variables to replace:** `<COUNTRY_ISO_ALPHA_3>`

```lql
resource.type="gce_subnetwork" AND
log_id("compute.googleapis.com/firewall") AND
jsonPayload.remote_location.country="<COUNTRY_ISO_ALPHA_3>"
```

### Firewall logs from a VM

**Variables to replace:** `<INSTANCE_NAME>`

```lql
resource.type="gce_subnetwork" AND
log_id("compute.googleapis.com/firewall") AND
jsonPayload.instance.vm_name="<INSTANCE_NAME>"
```

### Firewall subnet logs

**Variables to replace:** `<SUBNET_NAME>`

```lql
resource.type="gce_subnetwork" AND
log_id("compute.googleapis.com/firewall") AND
resource.labels.subnetwork_name="<SUBNET_NAME>"
```

### Compute Engine subnetwork traffic logs to a subnet

**Variables to replace:** `<SUBNET_IP>`

```lql
resource.type="gce_subnetwork" AND
ip_in_net(jsonPayload.connection.dest_ip, "<SUBNET_IP>")
```

### VPC flow logs

**Variables to replace:** None

```lql
resource.type="gce_subnetwork" AND
log_id("compute.googleapis.com/vpc_flows")
```

### VPC flow logs for specific port and protocol

**Variables to replace:** `<PORT_ID>`, `<PROTOCOL>`

```lql
resource.type="gce_subnetwork" AND
log_id("compute.googleapis.com/vpc_flows") AND
jsonPayload.connection.src_port="<PORT_ID>" AND
jsonPayload.connection.protocol="<PROTOCOL>"
```

### VPC flow logs for specific subnet

**Variables to replace:** `<SUBNET_NAME>`

```lql
resource.type="gce_subnetwork" AND
log_id("compute.googleapis.com/vpc_flows") AND
resource.labels.subnetwork_name="<SUBNET_NAME>"
```

### VPC flow logs for specific subnet prefix

**Variables to replace:** `<SUBNET_IP>`

```lql
resource.type="gce_subnetwork" AND
log_id("compute.googleapis.com/vpc_flows") AND
ip_in_net(jsonPayload.connection.dest_ip, "<SUBNET_IP>")
```

### VPC flow logs for a specific VM

**Variables to replace:** `<VM_NAME>`

```lql
resource.type="gce_subnetwork" AND
log_id("compute.googleapis.com/vpc_flows") AND
jsonPayload.src_instance.vm_name="<VM_NAME>"
```

### VPN gateway logs

**Variables to replace:** `<GATEWAY_ID>`

```lql
resource.type="vpn_gateway" AND
resource.labels.gateway_id="<GATEWAY_ID>"
```

### HTTP load balancer 5xx errors

**Variables to replace:** None

```lql
resource.type="http_load_balancer" AND
httpRequest.status>=500
```

### HTTP load balancer requests to PHPMyAdmin

**Variables to replace:** None

```lql
resource.type="http_load_balancer" AND
httpRequest.requestUrl:"phpmyadmin"
```

### HTTP load balancer spillover events

**Variables to replace:** `<BACKEND_SERVICE_NAME>`

```lql
resource.type="http_load_balancer" AND
resource.labels.backend_service_name="<BACKEND_SERVICE_NAME>" AND
jsonPayload.statusDetails=~"(spilled_over|overflow|spillover)"
```

### VPN gateway peer not responding

**Variables to replace:** None

```lql
resource.type="vpn_gateway"
"establishing IKE_SA failed, peer not responding"
```

### VPC flow logs egress (excluding internal traffic)

**Variables to replace:** `<VPC_NAME>`

```lql
resource.type="gce_subnetwork" AND
logName=~"vpc_flows" AND
jsonPayload.reporter="SRC" AND
jsonPayload.src_vpc.vpc_name="<VPC_NAME>" AND
(jsonPayload.dest_vpc.vpc_name!="<VPC_NAME>" OR NOT jsonPayload.dest_vpc:*)
```

### Cloud CDN signed URL 403 errors

**Variables to replace:** `<FORWARDING_RULE_NAME>`, `<REQUEST_URL>`

```lql
resource.type="http_load_balancer" AND
resource.labels.forwarding_rule_name="<FORWARDING_RULE_NAME>" AND
httpRequest.requestUrl="<REQUEST_URL>" AND
jsonPayload.statusDetails="signed_request_key_not_found"
```
