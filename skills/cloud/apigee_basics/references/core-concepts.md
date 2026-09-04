# Apigee Core Concepts

This document introduces the core architectural and lifecycle concepts of the
Apigee platform.

## 1. Apigee X vs. Apigee Hybrid

Apigee is designed with a disaggregated plane architecture, separating the
control operations (creation, analytics, deployment) from the runtime proxy
traffic.

*   **Apigee X**: A fully-managed Cloud SaaS platform. Google manages both the
    **Control Plane** (UI, APIs, Analytics in a Google-managed GCP project) and
    the **Runtime Plane** (the L7 Envoy-based gateway executing policies, hosted
    in a tenant project peered with your VPC).
*   **Apigee Hybrid**: A hybrid deployment topology. Google manages the
    **Control Plane** in the cloud, but the customer hosts and manages the
    **Runtime Plane** locally or in their cloud VPC within a Kubernetes cluster
    (using GKE, EKS, AKS, or Anthos).
    *   Communication between planes occurs asynchronously via the Apigee
        Synchronizer (ingress configuration sync) and Fluentd/Martini (analytics
        data ingestion).

### Determining Runtime Type (X vs. Hybrid)

You can identify if an Apigee organization is managed (Apigee X) or hybrid using
the following methods:

1.  **Google Cloud Console**:
    *   Navigate to **Apigee > Management > Instances** in the Cloud Console.
    *   Apigee Hybrid instances are marked as **Read-only** in the console UI
        (configuration changes must be made via Kubernetes/Helm).
2.  **API or CLI**:
    *   Query the organization details (e.g., using `gcloud apigee organizations
        describe`).
    *   Check the `runtimeType` field in the response:
        *   `CLOUD` indicates a fully managed **Apigee X** organization.
        *   `HYBRID` indicates an **Apigee Hybrid** deployment.

## 2. Environments & Environment Groups

API proxy deployments are scoped to environments, which in turn are routed
through virtual hosts defined in environment groups.

*   **Environments**: A logical partition where API proxies are deployed and
    execute. Examples: `dev`, `staging`, `prod`. Policies, Key Value Maps
    (KVMs), and Target Servers are scoped to environments.
*   **Environment Groups**: A collection of environments grouped under one or
    more hostnames. External client traffic is routed to the correct environment
    using the hostnames associated with the group and base path configurations.
    *   *Example*: Hostname `api.cymbal.com` in Environment Group `prod-group`
        maps to the `prod` environment.
    *   *Note*: Virtual hosts in Apigee X utilize a GCP HTTPS Load Balancer
        configured in the customer's project, which routes traffic through
        Private Service Connect (PSC) or VPC Peering to the Apigee runtime.

## 3. API Proxies

An API Proxy is a set of configuration files and policies that act as a facade
for a backend service. It consists of two primary endpoints:

*   **ProxyEndpoint**: Defines the public-facing interface of the proxy,
    including:
    *   `BasePath`: The URI fragment clients target (e.g., `/v1/weather`).
    *   `Flows`: Pipelines (Preflow, Conditional Flows, Postflow) executing
        policies on requests and responses.
    *   `RouteRule`: Routing logic deciding which TargetEndpoint to invoke based
        on headers or query parameters.
*   **TargetEndpoint**: Defines how Apigee communicates with the backend service
    (target URL, TLS settings, load balancing, target preflow/postflow
    execution).

```
 Client  ==[HTTP]==>  ProxyEndpoint (Preflow/Postflow)  ==[RouteRule]==>  TargetEndpoint  ==[HTTP]==>  Backend Target
```

*   **Revisions**: Proxies are version-controlled via **Revisions** (e.g.,
    Revision 1, Revision 2). Revisions are immutable once deployed. Modifying a
    proxy creates a new revision, allowing safe blue-green deployments and
    rollbacks.

## 4. API Products

An API Product is a logical bundle of API resources (proxies and paths) combined
with access rules.

*   API Products are the primary unit of monetization and access control. They
    specify:
    *   Which API proxies and paths are accessible (e.g., Proxy `weather`, Path
        `/forecast` only).
    *   **Quota**: Rate limits enforced on the app (e.g., 1000 calls per month).
    *   **Key Approval**: Automatic approval or manual review when a developer
        requests access.
    *   **Scopes**: OAuth scopes permitted by this product (e.g.,
        `read:weather`).

## 5. Developers & Developer Apps

To consume an API Product, clients must register and obtain credentials.

*   **Developers**: A profile representing the API consumer (name, email,
    company).
*   **Developer Apps**: A logical application registered by a Developer that is
    associated with one or more API Products.
    *   When a Developer App is created, Apigee automatically generates a
        **Consumer Key** (API Key) and a **Consumer Secret**.
    *   The Consumer Key must be provided by client requests (via query
        parameter, header, or OAuth flow) to identify the application and verify
        it is authorized for the associated API Product.
