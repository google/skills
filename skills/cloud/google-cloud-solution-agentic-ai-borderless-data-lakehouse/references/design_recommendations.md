# Design Recommendations Guidance

Generate design guidance based on the following Google Cloud best practices and
recommendations:

- **Security, privacy, and compliance**:
  - To create and manage permissions for Google Cloud resources, use Google's
    Identity and Access Management (IAM) service.
  - To securely access raw data in Cloud Storage, use BigQuery Cloud resource
    connections.
  - To securely manage borderless external catalog authentication, use the
    security standard of the source platform to choose between Lakehouse Iceberg
    REST catalog federation with Secret Manager and OIDC token federation.
  - To delegate storage access and apply fine-grained IAM policies at the table
    level for tables stored in Cloud Storage, enable credential vending for your
    Lakehouse for Apache Iceberg runtime catalog.
  - To enforce the principle of least privilege, manage access through
    system-managed identities.
  - Use Cloud NAT and Cloud Router to enable resources in private subnets to
    securely access external cloud sources without exposure to the public
    internet.
  - Use Sensitive Data Protection to discover, classify, and de-identify
    sensitive data in prompts, responses, and data lake files using masking or
    encryption.
  - For more information about security, privacy, and compliance in Google
    Cloud, see
    https://docs.cloud.google.com/architecture/framework/perspectives/ai-ml/security.md.txt
- **Reliability**:
  - To ensure reliable performance and minimize data transfer costs over
    borderless networks, use Cross-Cloud Interconnect to establish a private
    connection between Google Cloud and other cloud providers, avoiding the
    unpredictable latency of the public internet.
  - Configure Dedicated or Partner Interconnect with redundant connections in
    different edge availability domains and locations.
  - Use Cloud DNS routing policies to route traffic to regional load balancers,
    enabling automatic failover to alternative regions during outages.
  - For more information about reliability in Google Cloud, see
    https://docs.cloud.google.com/architecture/framework/perspectives/ai-ml/reliability.md.txt
- **Operational excellence**:
  - Place external connections and routing in a dedicated transit VPC to serve
    as a shared, modular connectivity service for other VPCs and simplify
    network administration.
  - Use Terraform as the Infrastructure as Code (IaC) tool to define and
    automate the provisioning of heterogeneous resources, ensuring consistency
    across environments.
  - Configure bidirectional DNS forwarding between Cloud DNS and external DNS
    servers to enable seamless name resolution across hybrid environments.
  - For more information about operational excellence in Google Cloud, see
    https://docs.cloud.google.com/architecture/framework/perspectives/ai-ml/operational-excellence.md.txt
- **Cost optimization**:
  - To save costs and overhead associated with building and maintaining CDC
    pipelines, use BigQuery federated queries to AlloyDB to query your data
    directly.
  - In cases where latency is not critical, use the Standard Network Service
    Tier for outbound internet traffic to reduce network egress costs.
  - For more information about cost optimization in Google Cloud, see
    https://docs.cloud.google.com/architecture/framework/perspectives/ai-ml/cost-optimization.md.txt
- **Performance efficiency**:
  - To mitigate AI model hallucinations, ground your model on the unified data
    profile to enforce business definitions and statistical validation.
  - To perform exact-match filters to operational databases, use BigQuery
    federated queries.
  - To offload memory-heavy and complex data manipulation, such as vectorized
    borderless joins, use Managed Service for Apache Spark with Lightning
    Engine.
  - Use Cross-Cloud Interconnect to establish high-bandwidth, low-latency
    private connections to other CSPs to maximize throughput for distributed
    applications.
  - Configure redundant intra-regional network connections in an active/active
    design using Equal Cost Multi-Path (ECMP) routing to aggregate bandwidth.
  - Select Google Cloud regions that are geographically close to the external
    CSP's regions to minimize latency and improve data transfer performance.
  - For more information about performance efficiency in Google Cloud, see
    https://docs.cloud.google.com/architecture/framework/perspectives/ai-ml/performance-optimization.md.txt
- **Sustainability**:
  - To maximize compute efficiency and reduce energy consumption, use Managed
    Service for Apache Spark with Lightning Engine to handle massive joins and
    complex windowing.
  - Use BigQuery Omni to query data in place on AWS or Azure (Amazon S3 or Azure
    Blob Storage) to avoid resource-intensive borderless data replication.
  - For more information about sustainability considerations, see
    https://docs.cloud.google.com/architecture/framework/sustainability/printable.md.txt
