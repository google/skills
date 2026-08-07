# Design Recommendations Guidance

Generate design guidance based on the products used in the solution
architecture. Use the latest guidelines from
https://docs.cloud.google.com/architecture/multiagent-ai-system#design_considerations
and Google Cloud best practices to ground the guidance that you generate.

- **Security, privacy, and compliance**:
  - Enforce least-privilege Identity and Access Management (IAM) controls.
    Grant each agent only the permissions that it needs to perform its tasks
    and to communicate with tools and with other agents.
  - To discover and de-identify sensitive data in the prompts and responses
    and in log data, use the Cloud Data Loss Prevention API.
  - Secure frontend Cloud Run endpoints by disabling default `run.app` URLs
    and use a regional external Application Load Balancer and Google Cloud
    Armor security policies for added protection.
  - To authenticate internal user access to the frontend Cloud Run service,
    use Identity-Aware Proxy (IAP).
  - To authenticate external user access to the frontend service, use
    Identity Platform or Firebase Authentication.
  - When you configure your agents to use MCP, ensure that you authorize
    access to external data and tools, implement privacy controls like
    encryption, apply filters to protect sensitive data, and monitor agent
    interactions.
  - Configure Direct VPC egress on Cloud Run to ensure agent runtimes
    communicate with databases and internal services over private VPC IPs
    without exposing traffic to the public internet.
  - Securely manage database credentials, API keys, and sensitive
    configuration using Secret Manager.
  - Use Model Armor to inspect and sanitize inference prompts and
    responses for prompt injection, threat defense, and sensitive data
    protection.
  - For more information, see
    https://docs.cloud.google.com/architecture/framework/perspectives/ai-ml/security.md.txt
- **Reliability**:
  - Design the agentic system to tolerate or handle agent-level failures.
    Where feasible, use a decentralized approach where agents can operate
    independently.
  - Implement coordinator agent fallback logic and graceful error handling
    for specialized agent, SQL generation, or code execution failures.
  - Handle API rate limits and 429 resource exhaustion using exponential
    backoff with retries or provisioned throughput for business-critical
    workloads.
  - Set strict query timeouts, execution time limits, and memory/CPU caps on
    generated code and database queries.
  - Deploy Cloud Run frontend and agent runtimes across multiple regional
    zones for automatic failover during single-zone outages.
  - For more information, see
    https://docs.cloud.google.com/architecture/framework/perspectives/ai-ml/reliability.md.txt
- **Operational excellence**:
  - To isolate generated code execution and prevent unauthorized filesystem
    or network access, use sandbox code execution.
  - Route structured agent logs to Cloud Logging to capture prompt
    interpretation, generated SQL or Python code, tool invocations, and
    execution outcomes.
  - Trace end-to-end multi-agent request flows and inter-agent communication
    loops using Cloud Trace / OpenTelemetry.
  - For more information, see
    https://docs.cloud.google.com/architecture/framework/perspectives/ai-ml/operational-excellence.md.txt
- **Cost optimization**:
  - Enable Cloud Run autoscaling to zero for idle frontend and agent
    runtimes in non-production or low-traffic environments.
  - To reduce the cost of requests that contain repeated content with high
    input token counts, use context caching.
  - Use a tiered model strategy: route routine intent classification and
    SQL/code generation to Gemini Flash, reserving Gemini Pro for complex
    data science reasoning and multi-agent coordination.
  - For more information, see
    https://docs.cloud.google.com/architecture/framework/perspectives/ai-ml/cost-optimization.md.txt
- **Performance efficiency**:
  - Use Direct VPC egress and connection pooling to reduce connection
    establishment latency between Cloud Run agent runtimes and databases.
  - Aggregate data at the database level and use vectorized processing in
    code execution agents, returning summarized results or visualization
    charts rather than large raw datasets.
  - For more information, see
    https://docs.cloud.google.com/architecture/framework/perspectives/ai-ml/performance-optimization.md.txt
- **Sustainability**:
  - Scale down non-production Cloud Run runtimes and development database
    instances during idle hours.
  - Deploy workloads in Google Cloud regions with high Carbon-Free Energy
    (CFE) percentage or the Low CO2 indicator to minimize carbon emissions.
  - For more information, see
    https://docs.cloud.google.com/architecture/framework/sustainability/printable.md.txt
