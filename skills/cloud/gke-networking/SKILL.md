---
name: gke-networking
description: >-
  Plans, configures, and manages core GKE cluster networking. Covers private
  clusters, VPC-native configurations, DNS, node egress, Dataplane V2, and
  IP planning. Use when designing GKE networking layouts, configuring private
  clusters, setting up Dataplane V2, planning GKE IP ranges, or managing VPC-
  native cluster modes. Don't use for application ingress, load balancing, or
  service networking (use gke-service-networking instead).
metadata:
  category: Networking
---

# GKE Networking

This reference covers networking configuration for GKE clusters. The golden path
enforces private, VPC-native clusters with Dataplane V2.

> **MCP Tools:** `get_cluster`, `update_cluster`, `apply_k8s_manifest`,
> `get_k8s_resource`

## Golden Path Networking Defaults

Setting                                                              | Golden Path Value                  | Day-0/1 | Notes
-------------------------------------------------------------------- | ---------------------------------- | ------- | -----
`privateClusterConfig.enablePrivateNodes`                            | `true`                             | Day-0   | Nodes have no public IPs
`masterAuthorizedNetworksConfig.privateEndpointEnforcementEnabled`   | `true`                             | Day-0   | Control plane only reachable via private endpoint or DNS
`controlPlaneEndpointsConfig.dnsEndpointConfig.allowExternalTraffic` | `true`                             | Day-0   | Allows DNS-based access from outside VPC
`networkConfig.datapathProvider`                                     | `ADVANCED_DATAPATH` (Dataplane V2) | Day-0   | eBPF-based, built-in Network Policy
`networkConfig.dnsConfig.clusterDns`                                 | `CLOUD_DNS`                        | Day-0   | Managed DNS, more reliable than kube-dns
`networkConfig.enableIntraNodeVisibility`                            | `true`                             | Day-1   | VPC Flow Logs for intra-node traffic
`ipAllocationPolicy.autoIpamConfig.enabled`                          | `true`                             | Day-0   | Automatic IP range management
`ipAllocationPolicy.createSubnetwork`                                | `true`                             | Day-0   | Auto-create dedicated subnet
`defaultMaxPodsConstraint.maxPodsPerNode`                            | `48`                               | Day-0   | Conservative default; 110 for high density

## Private Cluster Access Patterns

The golden path creates a private cluster. Users access it via:

1.  **DNS endpoint (default)**: `allowExternalTraffic: true` enables access via
    the cluster's DNS endpoint from outside the VPC. No VPN required.
2.  **Private endpoint**: Direct access from within the VPC or via Cloud
    VPN/Interconnect.
3.  **Authorized networks**: Add specific CIDRs to
    `masterAuthorizedNetworksConfig` for IP-based access control.

```bash
# Access private cluster via DNS endpoint (golden path default)
gcloud container clusters get-credentials {cluster_name} \
  --region {region} --dns-endpoint \
  --quiet

# Access via private endpoint (from within VPC)
gcloud container clusters get-credentials {cluster_name} \
  --region {region} --internal-ip \
  --quiet
```

## Bring-Your-Own VPC/Subnet

If the customer has existing network infrastructure:

```bash
gcloud container clusters create-auto {cluster_name} \
  --region {region} \
  --network {vpc_name} \
  --subnetwork {subnet_name} \
  --cluster-secondary-range-name {pod_range} \
  --services-secondary-range-name {svc_range} \
  --enable-private-nodes \
  --enable-master-authorized-networks \
  --quiet
```

> **Day-0 Warning**: VPC, subnet, and IP ranges cannot be changed after cluster
> creation.

## VPC-Native Mode Benefits

VPC-native clusters route traffic natively using GCP Alias IP ranges. Key
benefits to cover:

1.  **Scalability**: Traffic routes natively inside the VPC, bypassing the need
    for custom routes and avoiding custom route limit bottlenecks.
2.  **Direct VPC Integration**: Direct resource integration across GCP networks
    without complex bridging or routing tunnels.
3.  **Avoiding IP Exhaustion**: Supports discontiguous IP ranges and optimizes
    allocation, reducing the risk of exhausting subnet IP ranges.

## IP Planning

| Resource      | Golden Path  | Notes                                      |
| ------------- | ------------ | ------------------------------------------ |
| Pod CIDR      | `/17` (auto) | ~32K pod IPs; size based on maxPodsPerNode |
| Service CIDR  | `/20` (auto) | ~4K service IPs                            |
| Node subnet   | auto-created | /20 recommended for growth                 |
| Max pods/node | 48           | Each node gets a /25 pod range; set to 110 |
:               :              : for /24 per node                           :

**Pod CIDR sizing rule of thumb:**

-   `maxPodsPerNode=48` -> each node uses a `/25` (128 IPs) from pod CIDR
-   `maxPodsPerNode=110` -> each node uses a `/24` (256 IPs) from pod CIDR
-   Larger maxPodsPerNode = fewer nodes fit in a given CIDR

## Egress

-   Default: nodes use Cloud NAT for outbound internet access (private nodes
    have no public IPs) to allow private nodes to reach the internet without
    public IP exposure.
-   For static egress IPs: configure Cloud NAT with manual IP allocation to
    maintain a consistent source IP for external allowlists or partner
    firewalls.
-   For restricted egress: route through a firewall appliance via custom routes
    to inspect and filter outbound traffic according to organization security
    policies.

## Network Policy

Dataplane V2 (golden path) provides built-in Network Policy enforcement — no
additional addon needed. Apply default-deny per namespace, then allow specific
flows.

> See the `gke-workload-security` skill for default-deny policy and the
> `gke-multitenancy` skill for per-team allow policies.
