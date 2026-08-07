# Product Mapping Guidance

For each component in the confirmed technical decomposition and agentic design
pattern, identify the appropriate Google Cloud products and features, based on
the following guidance. Use
https://docs.cloud.google.com/architecture/choose-agentic-ai-architecture-components.md.txt
to ground the product mapping and guidance that you generate.

- **Cloud Run networking**:
  - Recommended primary configuration: Regional External Application Load
    Balancer combined with Cloud Armor for HTTP/HTTPS/WebSocket
    ingress, and Direct VPC egress for Cloud Run private network
    access.
  - Alternative product 1: Global External Application Load Balancer
    - Pros: Single anycast IP, global IPv6 termination, and low-latency
      routes to globally distributed backend services.
    - Cons: Terminates TLS globally at edge locations, which might not
      comply with strict regional data residency regulations.
  - Alternative product 2: Internal Application Load Balancer
    - Pros: Securely exposes Cloud Run services internally within the VPC
      to meet internal ingress criteria, terminates TLS with trusted
      certificates, and supports Cloud Armor backend security policies.
    - Cons: Requires that you configure serverless network endpoint groups
      (NEGs) as backends and manage load balancer resources.
  - Alternative product 3: Private Service Connect interface
    - Pros: Secure private VPC connections for Gemini Enterprise Agent
      Runtime that uses network attachments.
    - Cons: Limited to RFC 1918 routable subnet ranges, requires proxy
      setup for non-routable/internet destinations.
- **Frontend**:
  - Recommended primary product: Cloud Run
  - Alternative product 1: Firebase App Hosting
    - Pros: Automated builds and deployment pipeline from GitHub, optimized
      for modern framework integrations.
    - Cons: Less control over container configurations, limits
      customization of low-level networking.
  - Alternative product 2: Google Kubernetes Engine (GKE)
    - Pros: Maximum control over routing, scaling, and custom container
      runtimes.
    - Cons: Significant infrastructure management complexity and cost
      overhead.
- **Agent development framework**:
  - Recommended primary product: Agent Development Kit (ADK).
- **Agent-to-agent communication**:
  - Recommended primary product: Agent2Agent (A2A) protocol.
- **Runtime for your agent**:
  - Recommended primary product: Cloud Run
  - Alternative product 1: Gemini Enterprise Agent Runtime
    - Pros: Fully managed Python runtime, built-in memory/sessions,
      secure code execution sandbox.
    - Cons: Limited to Python, does not support hosting custom MCP
      servers, less control over container environment.
  - Alternative product 2: Google Kubernetes Engine (GKE)
    - Pros: Maximum infrastructure control, stateful pods, custom
      scaling.
    - Cons: High operational complexity and overhead.
- **Model runtime**:
  - Recommended primary product: Gemini Enterprise Agent Platform
  - Alternative product 1: Cloud Run
    - Pros: Serverless hosting for containerized open/custom models like
      Gemma.
    - Cons: Cannot serve Google Gemini models, manual
      instance scaling overhead.
  - Alternative product 2: Google Kubernetes Engine (GKE)
    - Pros: Maximum control over inference server on GPU/TPU nodes,
      cheap for predictable high volume.
    - Cons: Cannot run Google Gemini models, high cluster management
      overhead.
- **Model selection**:
  - Recommended primary product: Gemini Flash with Gemini Live API
  - Alternative product 1: Gemini Pro
    - Pros: Highest capability for reasoning, complex instructions, context
      tracking, and multi-agent coordination.
    - Cons: Higher request cost and latency, which makes it less suitable
      for real-time conversational requirements.
- **VPC connection to the database**: The architect agent sends queries
  through this connector to securely access resources in the Virtual
  Private Cloud (VPC) network used for storage resources in this
  architecture.
  - Recommended primary product: Serverless VPC Access connector.
  - Alternative product 1: Direct VPC egress
    - Pros: Lower latency, lower resource cost, and avoids throughput
      scaling bottlenecks.
    - Cons: Requires specific routing and subnet configurations.
- **Caching**:
  - Recommended primary product: Memorystore for Redis Cluster
- **Database**:
  - Recommended primary product: [Google Cloud Databases](https://cloud.google.com/products/databases)
    Use the recommendations listed on this page to help the user choose
    the appropriate database option.
  - Alternative product 1: Compute Engine (for self-hosted databases)
    - Pros: Full control over database configurations, OS accessibility, and
      custom database engines or extensions.
    - Cons: High operational overhead to manually manage backups, patching,
      scaling, and high availability.
