# Custom domains, load balancers, TLS, and unreachable gateways

-   [The request never reaches the gateway](#the-request-never-reaches-the-gateway): Lines 8-22
-   [Custom domains and load balancers](#custom-domains-and-load-balancers): Lines 24-47
-   [TLS versions and scanner findings](#tls-versions-and-scanner-findings): Lines 49-68
-   [Network restrictions](#network-restrictions): Lines 70-85

## The request never reaches the gateway

If the caller gets an error but the gateway has no matching log entry, and the
service account and required APIs check out (see
[triage-and-logs.md](triage-and-logs.md#when-the-logs-are-empty)), and log
exclusions and a wrong scope are ruled out, the request probably stopped
before the gateway. Check, with read-only commands on the caller's machine:

1.  **Host.** The URL's host matches a gateway's `defaultHostname`, or a custom
    domain that routes to the gateway.
2.  **DNS.** The host resolves (`nslookup {host}`). For a custom domain, it
    resolves to the load balancer's IP address.
3.  **TLS.** `curl -v https://{host}/{path}` completes the handshake. Use a
    `GET` on a path that's safe to call, and note the TLS version the client
    negotiates.

## Custom domains and load balancers

A custom domain for a gateway goes through a global external (or classic)
Application Load Balancer with a serverless NEG
([Use a custom domain](https://docs.cloud.google.com/api-gateway/docs/using-custom-domains.md.txt),
[Get started with load balancing for API Gateway](https://docs.cloud.google.com/api-gateway/docs/gateway-serverless-neg.md.txt)).
Check these documented constraints
([Load balancing for API Gateway](https://docs.cloud.google.com/api-gateway/docs/gateway-load-balancing.md.txt)):

-   The domain's DNS A or AAAA record must point to the load balancer's IP
    address. DNS changes can take from seconds to hours to propagate.
-   A serverless NEG can point only to gateways in the NEG's own region, and
    only to gateways in the same project as the load balancer. One NEG can
    target several gateways through a URL mask.
-   Gateways with streaming enabled can't sit behind a load balancer or
    serverless NEG, so they can't use custom domains during Public Preview.
-   API Gateway doesn't support ingress control settings, so the gateway's own
    hostname stays reachable even when a load balancer is in front of it.
    Callers can reach that hostname directly and bypass the load balancer's
    controls, such as Cloud Armor, so keep API key or JWT authentication on
    the gateway.

For building or changing the load balancer itself, hand off to the
`google-cloud-global-frontend-configuration` skill.

## TLS versions and scanner findings

API Gateway enforces TLS 1.2 or later. Clients that connect with TLS 1.1 or
earlier complete the handshake and then get
`400 Bad Request - The request was malformed`. External SSL-checking sites may
see the successful handshake and wrongly report that TLS 1.1 and earlier are
supported
([Release notes, July 23, 2025](https://docs.cloud.google.com/api-gateway/docs/release-notes.md.txt)).

-   For a scanner finding, repeat the test with a client pinned to TLS 1.1, and
    show the `400` response as evidence that the request is refused.
-   For control over minimum TLS versions and cipher suites, put a global
    external Application Load Balancer with an SSL policy in front of the
    gateway
    ([Use SSL policies](https://docs.cloud.google.com/load-balancing/docs/use-ssl-policies.md.txt)).
    The SSL policy applies only to the load balancer's frontend; the gateway's
    own hostname keeps API Gateway's TLS settings, so a scanner pointed at it
    gives the same result. This doesn't apply to streaming gateways.
-   The release note says that an opt-out from TLS 1.2+ enforcement is
    available through Cloud Customer Care.

## Network restrictions

-   **Callers by IP address.** The gateway's hostname can't be closed to the
    internet. To filter callers, use authentication on the gateway and, if
    needed, Cloud Armor on a load balancer in front of it.
-   **Backends that only accept private or allowlisted traffic.** The public
    API Gateway docs describe serverless backends reached at an `https`
    address and secured with IAM. They don't document fixed outbound IP
    addresses or private network connectivity for gateways. Recommend
    IAM-based backend authentication (see [auth-errors.md](auth-errors.md)),
    and escalate if the design depends on private connectivity.
-   **VPC Service Controls.** Check the
    [supported products page](https://docs.cloud.google.com/vpc-service-controls/docs/supported-products.md.txt)
    before you assume a perimeter covers API Gateway. Model routing gateways
    don't support VPC Service Controls
    ([Model routing overview](https://docs.cloud.google.com/api-gateway/docs/model-routing-overview.md.txt)).
