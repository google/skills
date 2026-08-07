---
name: google-cloud-solution-rag-enterprise-search-gke-sqldb
metadata:
  category: MultiProductSolutions
description: >-
  Discovers requirements, and generates architectural, design, and deployment
  guidance for a retrieval-augmented generation (RAG)-capable enterprise search
  system in Google Cloud. Use when users need a vector-enabled SQL database as
  the store and index for the embedding vectors, an open model and open-source
  inferencing framework, and Kubernetes containers to host all the application
  components. DON'T use this skill for fully-managed RAG, or SaaS search
  services, or when a non-SQL vector database is required.
---

# RAG for enterprise search using GKE and AlloyDB

This skill provides a workflow to design and implement a secure, low-latency,
and high-accuracy RAG-enabled conversational search solution for private
enterprise content by using an AlloyDB database, Cloud Storage, and a Google
Kubernetes Engine (GKE) cluster to host all the application components,
including an open model and an open-source inference framework.

## Overview of the workflow

The workflow consists of the following phases:
*   **Phase 1: Requirements discovery**. Gather detailed requirements related to
    the cloud workload or use case that the user needs assistance for.
*   **Phase 2: Solution architecture**. Use the requirements that were gathered
    in Phase 1 to generate a detailed solution architecture for the cloud
    workload or use case.
*   **Phase 3: Solution validation**. Create a plan to validate the generated
    solution, generate validation instructions and scripts, and run the
    validation.
*   **Phase 4: Solution packing and presentation**. Consolidate the generated
    content and present the solution.

**Important notes about the workflow**:

*   **Strict phase separation**: During Phase 1 (Requirements discovery), when
    you ask the user clarifying questions, DON'T recommend, propose, or outline
    any architectural designs, technical decompositions, cloud services, or
    component mappings.

*   **When you can skip certain phases**: If the user's prompt indicates that a
    specific phase or task in this workflow is already completed or approved
    (e.g., "requirements discovery stage is completed", "product selection is
    approved", or "architecture is confirmed"), DON'T repeat that phase or task.
    Instead, skip directly to the requested task (such as generating the
    technical decomposition, recommending products, or compiling the solution
    guide).

## Phase 1: Requirements discovery

In this phase, you must gather detailed requirements related to the RAG workload
that the user wants to design and deploy in Google Cloud.

Complete the following steps strictly in the specified order:
1.  Ask the user to describe the functional requirements of the workload,
    including data types (structured, unstructured), ingestion frequency, and
    conversational features (e.g., multi-turn chat, citation requirements).
2.  Ask the user to describe the following non-functional requirements:
    *   **Security, privacy, and compliance**: E.g., network isolation, private
        endpoints, data residency, and requirements for compliance.
    *   **Reliability**: E.g., scaling, high availability, resilience against
        zone or regional outages, disaster recovery goals for RTO and RPO.
    *   **Cost**: E.g., cost of compute, storage, and database resources.
    *   **Operational excellence**: E.g., monitoring, alerts, and logging.
    *   **Performance**: E.g., data upload speed, performance expectations for
        generating embedding vectors, and latency requirements for model
        responses and data retrieval queries (including vector and hybrid
        search).
    *   **Sustainability**: E.g., carbon footprint, low-carbon regions.
3.  Ask the user whether the workload currently runs on other cloud providers or
    on-premises.
    *   If the user's answer is "yes", then ask the user to describe the
        architecture of the current deployment.
    *   If the user's answer is "no", then proceed to the next step.
4.  Ask the user to describe dependencies, if any, on other workloads, products,
    or tools (e.g., identity providers, external sources, CRM/ERP database
    integrations).

5.  Review the input that the user has provided so far, and check whether there
    are any ambiguities or contradictions.

    If you identify any ambiguities or contradictions in the requirements that
    the user has provided, then
    do the following for each ambiguity or contradiction that you identify:
    *   Describe the ambiguity or contradiction.
    *   Ask the user how they wish to resolve the ambiguity or contradiction.
        *   If the user delegates the choice to you (e.g., the user replies with
            "do what you think is best" or "you decide"), then provide a clear
            suggestion to resolve the ambiguity or contradiction, explain your
            reasoning, and ask the user to approve your suggestion.

    **Critical**: Until all the ambiguities and contradictions that you identify
    are resolved according to the preceding guidance, you must NOT recommend or
    generate any architecture design, technical decomposition, or Google Cloud
    product recommendations.

6.  **Important**: DON'T start this step if there are unresolved contradictions
    or ambiguities from Step 5.

    Generate a technical decomposition of the components of the workload. The
    technical decomposition must break down the solution into logical
    components, as follows:
    *   **Data ingestion**: Blob storage for raw corporate documents.
    *   **Data processing and chunking**: Containerized pipeline to extract
        data, clean it, and chunk it.
    *   **Embedding vectors generation**: Containerized service to convert data
        chunks to embedding vectors.
    *   **Storing and indexing the embedding vectors**: Vector-enabled SQL
        database for storing embedding vectors.
    *   **Handling non-vector data**: Preparing non-vector data, like tables,
        views, and aggregations for data retrieval. Analyzing whether any
        indexing, partitioning, or other performance techniques can be applied
        on the original data schema.
    *   **Query and retrieval**: Accepting client queries, identifying intent,
        and routing to a retrieval workflow, which might include conversion of
        the request to an embedding for semantic search, extracting and applying
        filters for filtered search or supplying all to the hybrid search.
    *   **Prompt augmentation**: Augmenting the prompts with the retrieved
        context.
    *   **Response generation**: Requesting and generating responses from the
        model.
    *   **Response sanity checks**: Evaluating responses using an AI model and
        performing procedural checks according to defined criteria.
7.  Ask the user to approve the generated technical decomposition.

    **Critical**: You MUST stop execution immediately, call no more tools (such
    as file editors, searches, or code tools), and wait for the user to respond
    with their feedback or approval in the chat. Do NOT compile the
    architecture, recommend products, construct maps, or write any files/drafts
    for Phase 2 until the user's explicit approval is received.
8.  If the user requests changes, then generate an updated technical
    decomposition.
9.  Repeat steps 5 through 8 until the user approves the generated technical
    decomposition.
10. Only after the user has explicitly approved the technical decomposition,
    proceed to Phase 2.

    **Important**: You are strictly prohibited from recommending product
    choices, generating the architecture diagram, or drafting design
    recommendations until the technical decomposition is approved.

## Phase 2: Solution architecture

### Ground all generated content

For each task in this phase, to ensure that the generated content aligns with
the latest and official Google Cloud guidance, you must ground the generated
content by using the following resources:
*   Google Developer Knowledge MCP server:
    https://developers.google.com/knowledge/mcp.md.txt
    *   Server: https://developerknowledge.googleapis.com/mcp
        *   Tools:
            *   `developerknowledge:search_documents`
            *   `developerknowledge:get_documents`
            *   `developerknowledge:answer_query`
*   Relevant skills from https://github.com/google/skills
*   Official Google Cloud documentation, including the following:
    *   **Primary architecture reference**:
        https://docs.cloud.google.com/architecture/rag-capable-gen-ai-app-using-gke.md.txt
    *   **Architecture guidance and decision-making guides**:
        -   `references/product-selection-recommendations.md`
        -   `references/design-recommendations.md`
        -   `references/related-documentation.md`

For each item in the generated guidance, you must include citations to the
relevant official Google Cloud documentation pages.

### Task 2.1: Identify Google Cloud products and features required for the workload.

1.  Recommend the products and features that are appropriate for each component
    of the user's workload.

    **Important**: The Google Cloud products and features that you recommend
    MUST be consistent with the guidance in
    `references/product-selection-recommendations.md`.
2.  Present the generated product recommendations and ask the user to approve
    the recommendations.
3.  If the user requests changes, then make the required changes.
4.  Repeat steps 2 and 3 until the user approves the product recommendations.
5.  After the user approves the product recommendations, proceed to Task 2.2.

### Task 2.2: Generate an architecture diagram.

1.  Generate an architecture diagram in the Mermaid format:
    https://github.com/mermaid-js/mermaid.

    The diagram must show the data flows and request flows across the components
    of the architecture, based on the technical composition that you generated.

    The following is an **example** of the data flows and request flows that the
    architecture diagram should show:
    *   **Embedding pipeline (batch/streaming)**: Data source -> Cloud Storage
        -> Cloud Storage FUSE -> GKE Ray Worker (Chunking) --> Embedding
        generation using GemmaEmbedding -> AlloyDB.
    *   **Serving pipeline (real-time)**: User client -> GKE Frontend (LangChain
        Orchestration) -> Database Query (semantic or hybrid search on the
        vector store) -> Retrieve matching data -> Augment prompt -> Gemma vLLM
        endpoint API -> Output (Responsible AI filtering) -> User client.
2.  Present the generated diagram to the user and ask the user to approve the
    architecture diagram.
3.  If the user requests changes, then make the required changes.
4.  Repeat steps 2 and 3 until the user approves the architecture diagram.
5.  After the user approves the architecture diagram, proceed to Task 2.3.

### Task 2.3: Generate an architecture description.

1.  Generate a description that explains the purpose of each component, the
    relationships between the components, and the task flow or data flow.
2.  Present the generated architecture description to the user and ask the user
    to approve the description.
3.  If the user requests any changes, then make the required changes.
4.  Repeat steps 2 and 3 until the user approves the architecture description.
5.  After the user approves the architecture description, proceed to Task 2.4.

### Task 2.4: Generate design recommendations.

1.  Generate design recommendations and best practices to optimally configure
    each component in the architecture based on the workload's requirements.

    **Important**: The design recommendations and best practices that you
    generate MUST be consistent with the guidance in the resources that are
    listed in the following files:
    -   `references/related-documentation.md`
    -   `references/design-recommendations.md`
2.  Present the generated recommendations to the user and ask whether the user
    needs any changes.
3.  If the user needs changes, then make the required changes.
4.  Repeat steps 2 and 3 until the user confirms that the generated design
    recommendations meet their requirements.
5.  Proceed to Task 2.5.

### Task 2.5: Generate deployment guidance.

1.  Generate guidance to deploy the solution, including the following:
    *   Terraform code to create the required infrastructure resources.
    *   Steps or scripts to deploy workloads, such as Ray-on-GKE (KubeRay
        coordinator and worker nodes) and the LangChain frontend deployment.

    **Important**: The deployment guidance that you generate MUST be consistent
    with the guidance in the resources that are listed in the following
    resources:
    -   `references/related-documentation.md`
    -   `references/design-recommendations.md`
    -   Relevant skills in
        https://github.com/google/skills/tree/main/skills/cloud
2.  Present the generated deployment guidance to the user and ask whether the
    user needs any changes.
3.  If the user requests changes, then make the required changes.
4.  Repeat steps 2 and 3 until the user confirms that the generated deployment
    guidance meets their requirements.
5.  Proceed to Phase 3.

## Phase 3: Solution validation

1.  Create a plan to validate the generated solution. The plan must outline the
    steps that are necessary to verify that the generated solution meets the
    workload's requirements. The following are examples of validation steps:
    *   **Deployment dry-run**: Run commands like `terraform plan` to preview
        the infrastructure resources that will be provisioned.
    *   **Connectivity and routing**: Verify network paths, load balancer
        routing, and service endpoints.
    *   **Vector index**: Verify that vector indexes are correctly created and
        populated in the AlloyDB database. This can involve querying the
        database to check index status and content.
    *   **Embedding pipeline**: Test the end-to-end embedding pipeline from data
        ingestion to vector storage, ensuring documents are chunked, embedded,
        and stored correctly.
    *   **Retrieval latency**: Measure the latency of vector and hybrid search
        queries against the AlloyDB vector store to ensure performance meets
        requirements.
    *   **Retrieval accuracy**: Perform sample queries and evaluate the
        relevance of retrieved documents or chunks.
    *   **Security policies**: Verify restricted access, firewall rules, and IAM
        enforcement.
2.  Present the validation plan to the user and request feedback or approval.
3.  If the user requests changes, update the plan as required.
4.  Repeat steps 2 and 3 until the user approves the validation plan.
5.  Generate scripts or commands using tools like `curl` or `gcloud` to perform
    the steps in the approved validation plan.
6.  Request permission from the user to perform the validation checks.
7.  If the user gives permission, run the validation checks and troubleshoot any
    deployment issues.
8.  When all the validation checks pass, proceed to Phase 4.

## Phase 4: Solution packaging and presentation

1.  Consolidate the final text artifacts that were generated in Phase 2 into a
    single Markdown file named `solution-architecture-guide.md`, based on the
    template in `assets/output-template.md`.
2.  Request the user's permission to write the code files in the user's
    workspace.
3.  After the user gives permission, write the final code files in the user's
    workspace.

## Supporting references

-   `references/product-selection-recommendations.md`
-   `references/design-recommendations.md`
-   `references/related-documentation.md`
