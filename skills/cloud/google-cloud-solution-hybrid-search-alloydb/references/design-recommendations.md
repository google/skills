# Design recommendations

Important: The recommendations below apply to the primary recommended products
  in `references/product-mapping.md`. If an alternative product is selected,
  use the resources listed under that product's section in
  `references/product-mapping.md` to generate appropriate design
  recommendations.

Use the following guidance to generate design recommendations for a secure,
scalable, and high-performance hybrid search solution combining structured
relational queries, full-text search, and vector similarity search on Google
Cloud.

*   **Security, privacy, and compliance**:
    *   Encrypt AlloyDB database data at rest using Customer-Managed Encryption
        Keys (CMEK) and restrict network access by creating a service perimeter
        with VPC Service Controls (VPC-SC).
    *   Combine IAM least-privilege roles (`roles/alloydb.client`,
        `roles/alloydb.viewer`) with PostgreSQL database-native granular roles
        (`CREATE ROLE`) to prevent destructive commands (such as `DROP TABLE` or
        `TRUNCATE`) even if an agent identity is compromised.
    *   Use AlloyDB Auth Proxy or Language Connectors for IAM-based connection
        authorization and TLS 1.3 encrypted data transit.
    *   Prevent PostgreSQL search path hijacking by setting `ALTER ROLE
        user_name SET search_path = pg_catalog, pg_temp;` for privileged
        database roles to bypass untrusted public schemas.
    *   Disable default `run.app` ingress URLs for Cloud Run services, routing
        public traffic exclusively through a regional external Application Load
        Balancer protected by Cloud Armor WAF rules (`sqli-v33-stable` and XSS
        protection).
    *   Mitigate multi-tenant prompt injection data leaks by deploying specific
        custom tools (e.g., `lookup_active_order` via MCP Toolbox) where tenant
        identity filters are enforced in backend code outside LLM prompt
        control, avoiding generic open-ended `execute_sql` access.
    *   Enforce action-selection patterns (hardcoded Action-Selector or Dual-LLM
        guardrail pre-screening) and strict tool allowlists to prevent
        unauthorized tool chaining and control-flow manipulation.
    *   Enable Model Armor on AI endpoints (`gcloud ai endpoints update
        --enable-model-armor`) to sanitize MCP tool inputs and outputs, and
        configure Sensitive Data Protection (DLP) de-identification templates
        (`model_armor_config.json`) to redact PII automatically.
    *   Enable Data Access audit logging in Cloud Logging for MCP tools and
        AlloyDB services, logging raw LLM SQL commands, tool parameters, user
        IDs, and session IDs to detect exfiltration attempts via log-based
        alerts.

*   **Reliability**:
    *   Provision AlloyDB primary instances with automatic multi-zone high
        availability (HA) failover and configure microsecond Point-In-Time
        Recovery (PITR) continuous backups to recover from accidental or
        malicious data corruption by autonomous agents.
    *   Deploy Cloud Run web services and shims across multiple availability
        zones within a region to ensure automatic load-balancing and zone outage
        resilience.
    *   Use regional or dual-region Cloud Storage buckets combined with Pub/Sub
        message flow control and retry policies to handle ingestion spikes
        reliably.

*   **Operational excellence**:
    *   To minimize recall degradation and reduce manual interventions,
        configure ScaNN vector indexes with automatic maintenance enabled.
    *   Use AlloyDB Query Insights and System Insights dashboards to monitor
        query latency, replication lag, and peak database connection counts.
    *   Route application logs to Cloud Logging in structured JSON format and
        trace complete end-to-end execution paths across services using Cloud
        Trace.

*   **Cost optimization**:
    *   Utilize Committed Use Discounts (CUDs) for predictable AlloyDB instance
        compute workloads, or basic instances for non-production development
        environments.
    *   Configure Cloud Run services to scale to zero instances when idle to
        eliminate compute costs during off-peak hours.
    *   Apply Object Lifecycle Management policies to Cloud Storage buckets to
        automatically archive or delete temporary ingestion data.
    *   Configure Cloud Logging exclusion filters to drop non-critical debug
        logs and reduce log storage costs.

*   **Performance efficiency**:
    *   Configure ScaNN index parameters based on dataset size and tree depth:
        *   *Two-Level Tree*: Set `num_leaves = sqrt(rows)` for balanced build
            speed, or `rows/100` for optimal quality.
        *   *Three-Level Tree*: Set `max_num_levels = 2` and
            `num_leaves =power(rows, 2/3)` (balanced) or `rows/100` (quality).
        *   *Four-Level Tree*: Set `scann.max_allowed_num_levels = 3`,
            `max_num_levels = 3`, and `num_leaves = power(rows, 3/4)`.
    *   Improve search recall on highly selective filters by setting
        `scann.satisfy_limit = 'relaxed_order'` (streaming) and capping
        partition search using `scann.max_num_leaves_to_search_pct = 15`.
    *   For high-dimensional embeddings (>= 500 dimensions), tune
        `scann.pre_reordering_num_neighbors` (default `50 * K`) to refine
        re-ranking precision.
    *   Attach Direct VPC Egress to Cloud Run services to establish low-latency,
        private IP network paths to the AlloyDB instance without internet hops.

*   **Sustainability**:
    *   Utilize serverless compute platforms (Cloud Run and Cloud Run functions)
        to automatically scale compute down when idle, minimizing energy
        consumption.
    *   Execute vector distance calculations, full-text ranking, and embedding
        generation directly inside AlloyDB to avoid unnecessary cross-service
        network egress and duplicate compute cycles.
