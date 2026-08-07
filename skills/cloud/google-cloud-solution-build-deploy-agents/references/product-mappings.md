# Product mappings

Use the following list to identify the appropriate Google Cloud products and
features for each component in the confirmed technical decomposition:

## Table of Contents

| Component / Feature | Line hints |
| :--- | :--- |
| [Cloud Run networking](#cloud-run-networking) | Lines 24-45 |
| [Frontend](#frontend) | Lines 46-59 |
| [Agent development framework](#agent-development-framework) | Lines 60-63 |
| [Agent-to-agent communication](#agent-to-agent-communication) | Lines 64-71 |
| [Agent runtime](#agent-runtime) | Lines 72-91 |
| [Agent registry](#agent-registry) | Lines 92-97 |
| [Model runtime](#model-runtime) | Lines 98-110 |
| [Model selection](#model-selection) | Lines 111-121 |
| [Model input and output inspection](#model-input-and-output-inspection) | Lines 122-125 |
| [VPC connection to databases](#vpc-connection-to-databases) | Lines 126-137 |
| [Agent memory](#agent-memory) | Lines 138-175 |
| [Database (for search and retrieval)](#database-for-search-and-retrieval) | Lines 176-187 |
| [Agent tools](#agent-tools) | Lines 188-213 |

## <a id="cloud-run-networking"></a>Cloud Run networking

*   Recommended primary configuration: Regional External Application Load
    Balancer combined with Cloud Armor for HTTP/HTTPS/WebSocket ingress, and
    Direct VPC egress for Cloud Run private network access.
*   Alternative product 1: Global External Application Load Balancer
    *   Pros: Single anycast IP, global IPv6 termination, and low-latency
        routes to globally distributed backend services.
    *   Cons: Terminates TLS globally at edge locations, which might not
        comply with strict regional data residency regulations.
*   Alternative product 2: Internal Application Load Balancer
    *   Pros: Securely exposes Cloud Run services internally within the VPC
        to meet internal ingress criteria, terminates TLS with trusted
        certificates, and supports Cloud Armor backend security policies.
    *   Cons: Requires that you configure serverless network endpoint groups
        (NEGs) as backends and manage load balancer resources.
*   Alternative product 3: Private Service Connect interface
    *   Pros: Secure private VPC connections for Gemini Enterprise Agent
        Runtime that uses network attachments.
    *   Cons: Limited to RFC 1918 routable subnet ranges, requires proxy
        setup for non-routable/internet destinations.

## <a id="frontend"></a>Frontend

*   Recommended primary product: Cloud Run
*   Alternative product 1: Firebase App Hosting
    *   Pros: Automated builds and deployment pipeline from GitHub,
        optimized for modern framework integrations.
    *   Cons: Less control over container configurations, limits
        customization of low-level networking.
*   Alternative product 2: Google Kubernetes Engine (GKE)
    *   Pros: Maximum control over routing, scaling, and custom container
        runtimes.
    *   Cons: Significant infrastructure management complexity and cost
        overhead.

## <a id="agent-development-framework"></a>Agent development framework

*   Recommended primary product: Agent Development Kit (ADK).

## <a id="agent-to-agent-communication"></a>Agent-to-agent communication

*   Recommended primary product: Agent Gateway for governed Agent2Agent
    (A2A) connectivity.
    *   Pros: Provides client-to-agent ingress, agent-to-anywhere egress,
        and natively integrates IAM, Model Armor, Agent Registry, and Agent
        Identity.

## <a id="agent-runtime"></a>Agent runtime

*   Recommended primary product: Gemini Enterprise Agent Runtime
    *   Pros: Fully managed runtime that supports built-in memory/sessions
        (Agent Platform Sessions), secure code execution sandbox, and native
        connection to remote MCP servers (like those hosted on Cloud Run).
    *   Cons: Limited to the supported languages (see the supported
        [Language](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/Shared.Types/Language)
        list) and doesn't host custom Model Context Protocol (MCP) servers
        directly (they must be hosted externally on Cloud Run or GKE).
*   Alternative product 1: Cloud Run
    *   Pros: Serves custom container instances scaling to zero; highly
        performant when hosting custom language engines, local API layers,
        or custom MCP servers.
    *   Cons: Requires managing container builds and continuous delivery
        configurations, can't host or serve Gemini models.
*   Alternative product 2: Google Kubernetes Engine (GKE)
    *   Pros: Maximum infrastructure control, stateful pods, custom scaling.
    *   Cons: High operational complexity and overhead.

## <a id="agent-registry"></a>Agent registry

*   Recommended primary product: Agent Registry
    *   Pros: Provides a unified catalog for agents, tools, and MCP servers.
        Optimizes routing in multi-agent (A2A) paths.

## <a id="model-runtime"></a>Model runtime

*   Recommended primary product: Gemini Enterprise Agent Platform
*   Alternative product 1: Cloud Run
    *   Pros: Serverless hosting for containerized open/custom models like
        Gemma. Can be configured to autoscale.
    *   Cons: Cannot serve Google Gemini models.
*   Alternative product 2: Google Kubernetes Engine (GKE)
    *   Pros: Maximum control over inference server on GPU/TPU nodes, cheap
        for predictable high volume.
    *   Cons: Cannot run Google Gemini models, high cluster management
        overhead.

## <a id="model-selection"></a>Model selection

*   Recommended primary product (Text): Gemini Flash
*   Recommended primary product (Audio/Video): Gemini Flash with Gemini Live
    API
*   Alternative product 1: Gemini Pro
    *   Pros: Highest capability for reasoning, complex instructions,
        context tracking, and multi-agent coordination.
    *   Cons: Higher request cost and latency, which makes it less suitable
        for real-time conversational requirements.

## <a id="model-input-and-output-inspection"></a>Model input and output inspection

For security, always include model input and output inspection.

*   Recommended primary product: Model Armor

## <a id="vpc-connection-to-databases"></a>VPC connection to databases

An agent sends queries through this connector to securely access resources in
the Virtual Private Cloud (VPC) network used for storage resources in this
architecture.

*   Recommended primary product: Serverless VPC Access connector
*   Alternative product 1: Direct VPC egress
    *   Pros: Lower latency, lower resource cost, and avoids throughput
        scaling bottlenecks.
    *   Cons: Requires specific routing and subnet configurations.

## <a id="agent-memory"></a>Agent memory

### Short-term memory

*   Recommended primary product: Agent Platform Sessions
    *   Pros: Native, built-in managed memory for Gemini Enterprise Agent
        Runtime, low-ops, the default choice for most cases since it
        eliminates the need to provision and manage external databases.
    *   Cons: Requires an Agent Runtime instance and is limited to the
        managed Agent Platform Sessions service (regional availability
        applies), although the agent itself can still run on Cloud Run or GKE.
*   Alternative product 1: Memorystore for Redis Cluster
    *   Pros: High performance, sub-millisecond read/write latency.
        Ideal escalation path when you require microsecond response times and
        high throughput.
    *   Cons: Requires managing Redis nodes, VPC routing/peering
        configuration, and has a higher base cost.
*   Alternative product 2: Firestore
    *   Pros: Fully managed NoSQL database with serverless scaling,
        excellent for persistent state storage.
    *   Cons: Higher latency compared to in-memory stores, which might
        affect real-time interactive applications.
*   Alternative product 3: Cloud SQL (with ADK `DatabaseSessionService`)
    *   Pros: Strong relational guarantees and ACID compliance for complex
        querying over session state.
    *   Cons: Higher connection overhead and latency, and requires managing
        database instances.

### Long-term memory

*   Recommended primary product: Memory Bank
*   Alternative product 1: Firestore
    *   Pros: Serverless, highly scalable document database that is ideal
        for storing large volumes of persistent knowledge.
    *   Cons: Requires custom implementation for semantic search,
        embedding, and retrieval logic compared to purpose-built memory
        solutions.

## <a id="database-for-search-and-retrieval"></a>Database (for search and retrieval)

*   Recommended primary product:
    [Google Cloud Databases](https://cloud.google.com/products/databases)
    Use the recommendations listed on this page to help the user choose the
    appropriate database option (e.g., Cloud SQL, AlloyDB).
*   Alternative product 1: Compute Engine (for self-hosted databases)
    *   Pros: Full control over database configurations, OS accessibility,
        and custom database engines or extensions.
    *   Cons: High operational overhead to manually manage backups,
        patching, scaling, and high availability.

## <a id="agent-tools"></a>Agent tools

*   API Management Platform (Enterprise Scale):
    *   Recommended product: Apigee API hub.
    *   Use case: Best for managing, securing, and monitoring a large number
        of API-based tools at an enterprise scale. It allows agents to
        connect to data instantly through prebuilt connectors or custom APIs.
*   Model Context Protocol (MCP):
    *   Recommended primary products:
        *   Google Cloud MCP servers (fully managed by Google for connecting
            to Google Cloud services).
        *   Cloud Run or GKE (for deploying custom, self-hosted MCP servers
            as containerized applications).
        *   Use case: Best for building modular or multi-agent systems that
            require interoperable and reusable tools, decoupling the agent's
            logic from specific tool implementations.
*   Built-in Tools:
    *   Recommended primary framework: Agent Development Kit (ADK).
    *   Use case: Best for common tasks (e.g., web search, code execution
        in a secure environment) to accelerate initial development without
        configuring external communication protocols.
*   Custom Function Tools:
    *   Use case: Best for integrating with specific internal or third-party
        APIs that do not have an MCP server, or for exposing an
        "agent-as-a-tool" function in multi-agent orchestration.
