# Design Recommendations Guidance

Generate design guidance based on the products used in the solution
architecture. Use the latest guidelines from
https://docs.cloud.google.com/architecture/multiagent-ai-system#design_considerations
and Google Cloud best practices to ground the guidance that you generate.

- **Security, privacy, and compliance**:
  - To limit access to the app, disable the default run.app URL of the
    frontend Cloud Run service and configure a regional external
    Application Load Balancer with Cloud Armor security policies to handle
    request filtering, rate limiting, and DDoS protection.
  - Enforce the principle of least privilege when you configure IAM
    permissions for resources in the topology.
  - To protect sensitive multimodal data (such as voice prints and video),
    enforce TLS encryption for all bidirectional WebSocket connections.
  - Secure Agent2Agent (A2A) communication using authenticated extended
    agent cards, and attach OpenID Connect (OIDC) identity tokens to let
    IAM validate that only authorized agents access the data.
  - Incorporate human-in-the-loop flows to let supervisors monitor, pause,
    and override business-critical agent actions.
  - For more information about security considerations, see
    https://docs.cloud.google.com/architecture/framework/perspectives/ai-ml/security.md.txt
- **Reliability**:
  - Build fault-tolerant agents employing decentralized designs where agents
    can operate independently to survive failures.
  - Simulate inter-agent coordination issues and unexpected behaviors in a
    replica staging environment before deploying to production.
  - Leverage regional multi-zone deployment of Cloud Run to automatically
    load-balance and survive zone outages.
  - Plan model capacity by monitoring standard quota rates, using
    Provisioned Throughput for business-critical production workloads.
  - For more information about reliability considerations, see
    https://docs.cloud.google.com/architecture/framework/perspectives/ai-ml/reliability.md.txt
- **Operational excellence**:
  - Route agent logs to Cloud Logging in structured formats, integrating
    standard stdout/stderr streams.
  - Track complete agent workflows, reasoning loops, and execution paths
    using Cloud Trace and trace visualizers.
  - Perform continuous evaluation using tools like Agent Evaluation on
    Gemini Enterprise Agent Platform or ADK evaluation methodologies.
  - Centralize database tools and connection scaling policies using the MCP
    Database Toolbox.
  - For more information about operational excellence considerations, see
    https://docs.cloud.google.com/architecture/framework/perspectives/ai-ml/operational-excellence.md.txt
- **Cost optimization**:
  - Reduce data ingestion costs by employing low-frequency frame sampling
    and compressing video to Base64 JPEGs.
  - Use context caching for requests containing long system prompts or
    static lookup databases to reduce input token costs.
  - Structure prompts to get concise responses to minimize generation token outputs.
  - Start with the smaller and most cost-efficient models. Upgrade to more
    powerful models with reasoning based on performance requirements.
  - For more information about cost optimization considerations, see
    https://docs.cloud.google.com/architecture/framework/perspectives/ai-ml/cost-optimization.md.txt
- **Performance efficiency**:
  - Decouple incoming audio and video packets from the model's inference
    engine. Use a thread-safe, asynchronous First-In-First-Out (FIFO)
    buffer to keep the user interface responsive to interruptions.
  - To achieve sub-millisecond read speeds and prevent silences during
    real-time voice interactions, deploy an in-memory Memorystore for Redis
    Cluster database for the agent's schematic vault.
  - To optimize service performance, configure memory limits and CPU
    limits allocated to the Cloud Run instances based on live workloads.
  - For more information about performance considerations, see
    https://docs.cloud.google.com/architecture/framework/perspectives/ai-ml/performance-optimization.md.txt
- **Sustainability**:
  - Route simpler tasks to small language models (SLMs) and optimize model
    routing to minimize total model inference footprint.
  - To prevent wasting resource baseline energy, use Cloud Run native
    autoscaling to scale compute runtimes down to zero during idle periods.
  - For more information about sustainability considerations, see
    https://docs.cloud.google.com/architecture/framework/sustainability/printable.md.txt
