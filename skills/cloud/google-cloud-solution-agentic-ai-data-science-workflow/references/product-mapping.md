# Product Mapping Guidance

For each component in the confirmed technical decomposition and agentic design
pattern, identify the appropriate Google Cloud products and features, based on
the following guidance. Use
https://docs.cloud.google.com/architecture/choose-agentic-ai-architecture-components.md.txt
to ground the product mapping and guidance that you generate.

- **Frontend interface**:
  - Recommended primary product: Cloud Run
  - Alternative product 1: Google Kubernetes Engine (GKE)
    - Pros: Full control over container runtimes, custom ingress/routing, and
      built-in VPC integration for strict private internal network access and
      governance.
    - Cons: High operational management complexity, manual cluster lifecycle
      overhead, and higher base infrastructure costs.
- **Runtime for your agent**:
  - Recommended primary product: Cloud Run
  - Alternative product 1: Gemini Enterprise Agent Runtime
    - Pros: Fully managed Python runtime, built-in memory storage, and secure
      code execution sandbox.
    - Cons: Limited to Python, doesn't support hosting custom MCP servers,
      and less control over container environment.
  - Alternative product 2: Google Kubernetes Engine (GKE)
    - Pros: Maximum infrastructure control, stateful pods, and custom
      scaling.
    - Cons: High operational complexity and overhead.
- **Database & Data Warehouse**:
  - Recommended primary product: [Google Cloud Databases](https://cloud.google.com/products/databases).
    Use the recommendations listed to help the user choose the
    appropriate database option.
- **Database connectivity**:
  - Recommended primary product: MCP Toolbox for Databases or Google Cloud
    MCP servers.
  - Alternative product 1: Custom MCP servers
    - Pros: Full control over tool schemas, custom data transformations, and
      custom authentication logic.
    - Cons: Requires that you build, host, and maintain custom container
      infrastructure and connection pooling.
  - Alternative product 2: ADK built-in tools
    - Pros: Direct framework integration with zero additional infrastructure
      or MCP protocol overhead.
    - Cons: Limited to supported built-in tool types and lacks centralized
      MCP connection pooling across agent runtimes.
- **Model runtime**:
  - Recommended primary product: Gemini Enterprise Agent Platform
  - Alternative product 1: Cloud Run
    - Pros: Serverless hosting for containerized open/custom models.
    - Cons: Can't serve Google Gemini models and requires manual instance
      scaling overhead.
  - Alternative product 2: Google Kubernetes Engine (GKE)
    - Pros: Maximum control over inference server on compute nodes and is
      cheap for predictable high volume.
    - Cons: Can't run Google Gemini models and has high cluster management
      overhead.
- **Model selection**:
  - Recommended primary product: Gemini Flash
  - Alternative product 1: Gemini Pro
    - Pros: Highest capability for reasoning, complex instructions, context
      tracking, and multi-agent coordination.
    - Cons: Higher request cost and latency, which makes it less suitable
      for real-time conversational requirements.