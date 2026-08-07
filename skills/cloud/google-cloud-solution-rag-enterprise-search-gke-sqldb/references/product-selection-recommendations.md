# Product-selection recommendations

This file provides Google Cloud product recommendations for specific components
of a RAG workload that uses a vector-enabled SQL database as the store and index
for the embedding vectors, an open model and open-source inferencing framework,
and Kubernetes containers to host all the application components.

**Important**:

*   Don't recommend any products that are deprecated, retired, decommissioned,
    or unsupported. Verify the status of the products by using the resources
    that are listed in the "Ground all generated content" section in
    `../SKILL.md`.
*   Don't recommend any features that are deprecated, retired, decommissioned,
    or unsupported. Verify the status of the features by using the resources
    that are listed in the "Ground all generated content" section in
    `../SKILL.md`.
*   If multiple products or features can be used for a component of the
    workload, then do the following:
    *   Recommend the most appropriate product or feature. When alternative
        products exist, the relevant product documentation might provide
        guidance on when to recommend each product. Follow that guidance.
    *   Mention the available alternative products or features.
    *   Explain the pros and cons of each alternative product or feature.

## Component-specific product recommendations

*   **Storage**: Recommend Cloud Storage for raw document storage. Recommend
    using the Cloud Storage FUSE CSI driver to mount buckets directly to GKE
    processing Pods for seamless access.
*   **Orchestration and compute**: Recommend GKE Autopilot as the default to
    automate node management and right-size resource allocation. Use Ray (Ray
    Data and Ray Core) on GKE to orchestrate multi-worker chunking and
    preprocessing jobs.
*   **Embedding vectors store and index**: Recommend AlloyDB for PostgreSQL.
    Explain that this choice provides the following advantages:
    *   Enables standard relational enterprise metadata to exist alongside
        embedding vectors, avoiding database silos.
    *   Provides full PostgreSQL compatibility and advanced embedding and
        vector-indexing capabilities.
*   **Generation of embedding vectors and responses**: Recommend an open model
    like GemmaEmbedding to generate embedding vectors and Gemma to generate
    responses. Recommend an open-source inferencing framework (e.g., vLLM)
    that's hosted on GKE.
*   **Alternatives**: Mention the following alternatives:
    *   For the embedding vectors index, suggest Cloud SQL for PostgreSQL (with
        the `pgvector` extension) and Vector Search on Gemini Enterprise Agent
        Platform as alternatives.
    *   For generating embedding vectors, suggest the Embeddings API of Gemini
        Enterprise Agent Platform Embeddings API as an alternative.
    *   For inferencing, suggest Gemini Enterprise Agent Platform as an
        alternative. Enumerate the relative pros and cons of each alternative.
