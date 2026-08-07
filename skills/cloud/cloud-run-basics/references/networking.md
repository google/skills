# Cloud Run Networking best practices and cost optimization

When configuring networking options for Cloud Run services, apply these best
practices and cost optimization strategies.

## Optimize costs

When configuring networking options for your resources, consider the following:

*   **Co-locate your resources**: Deploy your Cloud Run resources in the same
    region as your backend databases (like Cloud SQL or Firestore) and Cloud
    Storage buckets. Data transfer between Google Cloud resources within the
    same region is free (`$0.00 / GiB`).
*   **Switch to Direct VPC egress**: If you are securely routing traffic to
    internal VPC network resources, switch to Direct VPC egress from Serverless
    VPC Access connectors. Direct VPC egress scales to zero, eliminating the
    baseline compute overhead and idle costs associated with connector
    instances.
*   **Offload static assets**: Use Cloud CDN in front of your Cloud Run
    resources to cache static assets and highly cacheable content. Serving data
    from the edge is significantly cheaper than paying for standard internet
    egress directly from Cloud Run.
*   **Monitor internet egress**: Inbound traffic (ingress) is always free, and 1
    GiB of free outbound internet data transfer is provided per month within
    North America. Focus your monitoring efforts on outbound traffic that
    crosses region boundaries or exceeds the free tier.

## Monitor IP address usage

If you're using Direct VPC egress, make sure that you have enough IP addresses
for your subnet. The number of IP addresses you use depends on the number of
instances that your workloads run, so we recommend monitoring your IP address
usage. Be sure that your IP usage over time stays within the bounds supported by
the subnet.

To estimate your IP address usage:

1.  Look up the number of instances in your project using the metric type
    `run.googleapis.com/container/instance_count`.
2.  Multiply the instance count metric's value by 2 to get an estimate of the
    number of IP addresses in use.

## IP address exhaustion strategies

Having a large number of Cloud Run workloads can cause IP exhaustion challenges
when using the RFC 1918 private IP address space with Direct VPC egress. The
following strategies can help you manage IP address exhaustion by using
alternative IP address ranges.

### Use non-RFC 1918 IPv4 addresses

Aside from the RFC 1918 IPv4 address ranges, Cloud Run also supports RFC 6598
(`100.64.0.0/10`) and Class E/RFC 5735 (`240.0.0.0/4`) ranges. All Google Cloud
services and features work with these non-RFC 1918 ranges, including VPC
networks, Cloud Load Balancing, and Private Service Connect. For best
compatibility, start with the RFC 6598 (`100.64.0.0/10`) range. If already in
use, consider using Class E/RFC 5735 (`240.0.0.0/4`).

### Use Cloud NAT or Private Service Connect

If your Cloud Run workload using a non-RFC 1918 range needs to reach an
on-premises destination that accepts only RFC 1918, use one of the following
solutions:

*   Use Hybrid NAT to perform address translation and egress using a small RFC
    1918 range.
*   Expose the on-premises service as a Private Service Connect hybrid service.

### Use IPv4 and IPv6 (dual-stack) subnets

Although it won't reduce IPv4 exhaustion, moving your apps to IPv6 is a good
first step. Set up dual-stack resources to avoid IPv4 exhaustion problems in the
future.

## Port exhaustion reduction strategies

When sending a large number of requests to a single destination IP address, use
connection pooling to maintain and reuse connections to the destination. High
connection rates to a single IP address can exhaust outbound ports and cause
connection refused errors.

### Use connection pooling and reuse connections

Use application-level connection pools (e.g., HTTP keep-alive or database
connection pooling libraries) and limit maximum pool size per container instance
to reuse active TCP connections rather than opening new sockets for every
request.

## Performance and throughput strategies

This section covers scalable options for improving network performance and
throughput towards the internet and Google services.

### Use the second generation execution environment

For the best networking performance for Cloud Run services, use the second
generation execution environment when routing traffic with Direct VPC egress.
The second generation environment provides faster network performance,
especially in the presence of packet loss.

### Use Direct VPC egress for faster network egress throughput

To achieve faster throughput across network egress connections, use Direct VPC
egress to route traffic through your VPC network. We recommend using this in
conjunction with the second generation execution environment.

#### Example 1: External traffic to the internet

If you're sending external traffic to the public internet, route all traffic
through the VPC network by setting `--vpc-egress=all-traffic`. With this
approach, you must set up Cloud NAT to reach the public internet.

#### Example 2: Internal traffic to a Google API

If you're using Direct VPC egress to send traffic to a Google API, such as Cloud
Storage, choose one of the following options:

*   Specify `private-ranges-only` (default) with Private Google Access:
    1.  Set the flag `--vpc-egress=private-ranges-only`.
    2.  Enable Private Google Access.
    3.  Configure DNS for Private Google Access so your target domain (such as
        `storage.googleapis.com`) maps to `199.36.153.8/30` or
        `199.36.153.4/30`.
*   Specify `all-traffic` with Private Google Access:
    1.  Set the flag `--vpc-egress=all-traffic`.
    2.  Enable Private Google Access.

## Use the default MTU setting for Cloud Run

Don't change the maximum transmission unit (MTU) setting of a VPC network when
using it with Cloud Run. Use the default MTU of 1,460 bytes instead.
