# Related documentation

## Table of contents

-   [Architecture guides](#architecture-guides): Lines 12 to 44
-   [Deployment guides](#deployment-guides): Lines 45 to 55
-   [Product-specific best practices guides](#product-specific-best-practices-guides):
    Lines 56 to 80
-   [Product-specific decision-making guides](#product-specific-decision-making-guides):
    Lines 81 to 109

## <a name="architecture-guides"></a>Architecture guides

Use the following reference architectures and design guides to design
infrastructure for a RAG workload on Google Cloud:

-   [RAG infrastructure for generative AI using GKE and Cloud SQL](https://docs.cloud.google.com/architecture/rag-capable-gen-ai-app-using-gke.md.txt):
    A flexible, container-based architecture that provides maximum control to
    build custom applications with open source tools such as Ray, Hugging Face,
    and LangChain.
-   [RAG infrastructure for generative AI using Gemini Enterprise and Agent Platform](https://docs.cloud.google.com/architecture/rag-genai-gemini-enterprise-vertexai.md.txt):
    An agent-driven architecture that uses Gemini Enterprise as a unified
    platform to orchestrate an end-to-end RAG dataflow for enterprise
    applications that require real-time data availability and enriched
    contextual search.
-   [RAG infrastructure for generative AI using Agent Platform and Vector Search](https://docs.cloud.google.com/architecture/gen-ai-rag-vertex-ai-vector-search.md.txt):
    A fully managed, serverless architecture that provides optimized,
    high-performance vector search for large-scale applications.
-   [RAG infrastructure for generative AI using Agent Platform and AlloyDB for PostgreSQL](https://docs.cloud.google.com/architecture/rag-capable-gen-ai-app-using-vertex-ai.md.txt):
    An architecture that stores vector embeddings alongside your operational
    data in a fully managed database like AlloyDB for PostgreSQL.
-   [Harness CI/CD pipeline for RAG applications](https://docs.cloud.google.com/architecture/partners/harness-cicd-pipeline-for-rag-app.md.txt):
    An architecture for a continuous integration (CI) and continuous deployment
    (CD) pipeline for a RAG application in Google Cloud.
-   [Private connectivity for RAG-capable generative AI applications](https://docs.cloud.google.com/architecture/private-connectivity-rag-capable-gen-ai.md.txt):
    Guidance to configure private endpoints and private service connections for
    secure RAG data ingestion and processing.
-   [Networking for AI inference model serving on GKE](https://docs.cloud.google.com/architecture/networking-for-ai-inference-gke.md.txt):
    Guidance to structure load balancers and private VPC subnets to serve AI
    models on GKE securely.
-   [RAG infrastructure for generative AI using Gemini Enterprise and Vector Search](https://docs.cloud.google.com/architecture/gen-ai-rag-vertex-ai-vector-search.md.txt):
    Design considerations and guidelines for leveraging the Gemini Enterprise
    Agent Platform with Vector Search.

## <a name="deployment-guides"></a>Deployment guides

Use the following resources to generate the deployment guidance:

-   Example blueprints and Notebooks for RAG on GKE:
    https://gke-ai-labs.dev/docs/blueprints/rag-on-gke/
-   Reference architecture for running inference workloads on GKE:
    https://github.com/GoogleCloudPlatform/accelerated-platforms/blob/main/docs/platforms/gke/base/use-cases/inference-ref-arch/README.md
-   Build a RAG chatbot with GKE and Cloud Storage:
    https://docs.cloud.google.com/kubernetes-engine/docs/tutorials/build-rag-chatbot.md.txt

## <a name="product-specific-best-practices-guides"></a>Product-specific best practices guides

The following guides provide optimization guidelines and operational best
practices for the products used in this RAG architecture.

-   [Optimize GKE for machine learning inference](https://docs.cloud.google.com/kubernetes-engine/docs/best-practices/machine-learning/inference.md.txt):
    Best practices for optimizing ML inference workloads, reducing cold-start
    latency, and sizing compute profiles.
-   [Best practices for running cost-effective applications on GKE](https://docs.cloud.google.com/architecture/best-practices-for-running-cost-effective-kubernetes-applications-on-gke.md.txt):
    Best practices for running cost-effective, containerized Kubernetes
    applications.
-   [Cloud SQL for PostgreSQL: Example of an embedding workflow](https://docs.cloud.google.com/sql/docs/postgres/understand-example-embedding-workflow.md.txt)
    Guide with example of embedding workflow using an AI embedding model as a
    service.
-   [Generate and manage auto vector embeddings for large tables in AlloyDB](https://docs.cloud.google.com/alloydb/docs/ai/generate-manage-auto-embeddings-for-tables.md.txt):
    Guide about embedding generation in AlloyDB.
-   [Build generative AI applications using AlloyDB AI](https://docs.cloud.google.com/alloydb/docs/ai.md.txt):
    AI tools and options to build a RAG workflow using AlloyDB.
-   [Parallel composite uploads strategy](https://docs.cloud.google.com/storage/docs/parallel-composite-uploads.md.txt):
    Guide to designing high-throughput object upload pipelines using parallel
    composite uploads.
-   [GKE Autopilot security measures](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/autopilot-security.md.txt):
    Security best practices and posture configurations for GKE Autopilot
    clusters.

## <a name="product-specific-decision-making-guides"></a>Product-specific decision-making guides

Use the following comparison guides to evaluate design trade-offs and options in
the GKE and AlloyDB RAG stack.

-   [Choose GKE cluster mode](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/choose-cluster-mode.md.txt):
    GKE Autopilot versus GKE Standard modes of operation.
-   [GKE Autopilot compute classes](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/autopilot-compute-classes.md.txt):
    Predefined ComputeClasses for GKE Autopilot Pods (Balanced, Scale-Out, GPU
    options like L4).
-   [Agent Platform RAG Engine: vector database choices](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/rag-engine/vector-db-choices.md.txt):
-   [Choose a connectivity option for AlloyDB](https://docs.cloud.google.com/alloydb/docs/choose-alloydb-connectivity.md.txt):
    Compares AlloyDB connectivity methods, including AlloyDB Auth Proxy, Private
    Service Connect (PSC), and direct VPC peering, to help you select the
    appropriate method.
-   [Choose an AlloyDB machine type](https://docs.cloud.google.com/alloydb/docs/choose-machine-type.md.txt):
    Explains how to select the appropriate machine type for your AlloyDB primary
    and read instances based on vCPUs, memory, and performance.
-   [Choose a vector index in AlloyDB AI](https://docs.cloud.google.com/alloydb/docs/ai/choose-index-strategy.md.txt):
    Compares indexing strategies to help you choose the appropriate model for
    vector search. When to use Cloud SQL `pgvector` vs. Agent Platform Vector
    Search.
-   [PostgreSQL pgvector indexing strategy](https://github.com/pgvector/pgvector#indexing):
    Comparing HNSW and IVFFlat indices in `pgvector` for approximate nearest
    neighbor (ANN) search.
-   [Cloud SQL for PostgreSQL configuration choices](https://docs.cloud.google.com/sql/docs/postgres/instance-settings.md.txt):
    Selecting machine series, storage type, and other configuration options for
    Cloud SQL for PostgreSQL instances.
