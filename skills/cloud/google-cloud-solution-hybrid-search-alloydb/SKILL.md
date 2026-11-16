---
name: google-cloud-solution-hybrid-search-alloydb
metadata:
  version: "1.0.2"
  category: MultiProductSolutions
description: >-
  Discovers requirements and generates architectural, design, and deployment
  guidance for dynamic hybrid search systems by combining semantic search and
  keyword search. Optimized for AlloyDB hybrid search use cases in Google Cloud.
  Use when users need vector search combined with structured SQL
  filtering, faceted attributes, semantic reranking, in-database AI validation,
  or serverless hosting across transactional relational databases, analytical
  data warehouses, or managed database engines. DON'T use this skill for simple
  keyword-only search, or when a standalone non-relational vector database is
  required.
---

# Dynamic Hybrid Search using AlloyDB

This skill provides a workflow to design and implement secure, low-latency, and
high-accuracy hybrid search solutions combining structured dataset filtering,
vector search indexing, faceted metadata filtering, semantic reranking, recall
evaluation, in-database AI validation, database abstraction layers, and
serverless application hosting.

## Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Overview of the workflow

The workflow consists of the following phases:

1. **Requirements discovery**. Gather detailed requirements related to
  the cloud workload or use case that the user needs assistance for.
2. **Solution architecture**. Use the requirements that were gathered
  in Phase 1 to generate a detailed solution architecture for the cloud
  workload or use case.
3. **Solution validation**. Create a plan to validate the generated
  solution, generate validation instructions and scripts, and run the
  validation.
4. **Solution packaging and presentation**. Consolidate the generated
  content and present the solution.

**Important notes about the workflow**:

- **Strict phase separation**: During Phase 1 (Requirements discovery), when you
  ask the user clarifying questions, DON'T recommend, propose, or outline any
  architectural designs, cloud services, or component mappings. This prevents
  premature architecture commitments or hallucinations before the full scope is
  understood.
- **Halting for approval**: For any step where you are instructed
  to "obtain approval before proceeding", you MUST stop executing, present the
  completed tasks to the user, and wait for their explicit approval. You MUST
  NOT proceed to execute any subsequent tasks or generate any further guidance
  in that response.
- **Ground all generated content**: For all tasks across all phases, you MUST
  first look in the following resources:
  - [Product Mapping](references/product-mapping.md),
  - [Design Recommendations](references/design-recommendations.md) for the
  required guidance. If the guidance does not provide the required information,
  you MUST ground the generated content by using the following resources:

  - Google Developer Knowledge MCP server:
    https://developers.google.com/knowledge/mcp.md.txt
    - Server: https://developerknowledge.googleapis.com/mcp
      - Tools:
        - `developerknowledge:search_documents`
        - `developerknowledge:get_documents`
        - `developerknowledge:answer_query`
  - Relevant skills from https://github.com/google/skills
  - Official Google Cloud documentation in
    [Related Guidance](references/related-guidance.md)

## Product Renaming & Terminology

When generating solution designs, architecture diagrams, and documentation,
check the latest Google Cloud documentation for the most up-to-date product
names. The table below provides examples of name mappings to be aware of. Note
that underlying APIs, Terraform resources, and IAM roles may retain their legacy
identifiers.

<table>
  <thead>
    <tr>
      <th>Legacy Name</th>
      <th>Updated Name</th>
      <th>Notes</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Vertex AI</td>
      <td>Gemini Enterprise Agent Platform</td>
      <td>Gemini Enterprise Agent Platform can be shortened to Agent Platform after first instance</td>
    </tr>
    <tr>
      <td>Vertex AI Embedding</td>
      <td>Text embedding on Gemini Enterprise Agent Platform</td>
      <td>This refers to the text embedding models available on Gemini Enterprise Agent Platform</td>
    </tr>
    <tr>
      <td>Vertex AI Matching Engine</td>
      <td>Vector Search</td>
      <td></td>
    </tr>
  </tbody>
</table>

## Phase 1: Requirements discovery

In this phase, you must gather detailed requirements related to the hybrid
search workload that the user wants to design and deploy in Google Cloud.

**Acknowledge provided requirements**: If the
user's prompt already contains some requirements (functional or non-functional,
such as catalog size, search modalities, faceted attributes, or latency
targets), you MUST explicitly acknowledge and restate all of these requirements
in your response. Do NOT ask the user to describe or re-describe any
requirements that they have already provided in the prompt.

Complete the following steps strictly in the specified order:

- [ ] **Step 1**: Ask the user to describe the functional requirements of the
  workload, including catalog dataset details (e.g., e-commerce apparel, retail
  products, patent database), search modalities (natural language text, visual
  search, attribute filters), metadata attributes for faceted filtering (e.g.,
  `category`, `sub_category`, `color`, `gender`, `price`), and quality checks
  (reranking, LLM validation).
- [ ] **Step 2**: You MUST explicitly ask the user to describe ALL of the
  following six categories of non-functional requirements. You need this
  information because each category represents a critical architectural pillar,
  and neglecting any of them can result in a solution that is insecure,
  unreliable, or inefficient (do NOT omit any of them):
  - **Security, privacy, and compliance**: E.g., private VPC endpoints, Private
    Service Connect, Direct VPC Egress, and access control.
  - **Reliability**: E.g., high availability, failover, disaster recovery goals
    (RTO/RPO), regional vs multi-region AlloyDB topology.
  - **Cost**: E.g., budget constraints for compute, database instances, and
    Gemini Enterprise Agent Platform API calls.
  - **Operational excellence**: E.g., monitoring, logging, dashboards, and
    automated deployment.
  - **Performance**: E.g., target P95 query latency (e.g., < 100ms), vector
    search recall target (e.g., > 95%), catalog item scale, and QPS
    expectations.
  - **Sustainability**: E.g., carbon footprint, low-carbon region selection.
- [ ] **Step 3**: Ask the user whether the workload currently runs on other
  cloud providers or on-premises.
  - If the user's answer is "yes", then ask the user to describe the
    architecture of the current deployment.
  - If the user's answer is "no", then proceed to the next step.
- [ ] **Step 4**: Ask the user to describe dependencies, if any, on other
  workloads, products, or tools (e.g., existing inventory databases, ERP
  systems, application runtime languages like Java or Python).

- [ ] **Step 5**: Review the input that the user has provided so far, and check
  whether there are any ambiguities, conflicts, or contradictions in the
  functional requirements, non-functional requirements, and dependencies. You
  MUST compare all requirements against each other to identify any conflicts.

  If you identify any ambiguities, conflicts, or contradictions in the
  requirements that the user has provided, you MUST do the following for each
  ambiguity, conflict, or contradiction:
  - [ ] Identify exactly where each contradiction lies and explain to the
    user why the requirements are incompatible and cannot be simultaneously
    satisfied. Do NOT treat fundamental contradictions as design choice
    questions (e.g., asking how to implement or configure a conflicting
    requirement).
  - [ ] Ask the user to clarify their trade-off preferences to resolve the
    contradiction.
  - [ ] If the user delegates the choice to you (e.g., the user replies with
    "do what you think is best" or "you decide"), then provide a clear
    suggestion to resolve the ambiguity or contradiction, explain your
    reasoning, and ask the user to approve your suggestion.

  **Critical**: Until all the ambiguities and contradictions that you identify
  are resolved according to the preceding guidance, you must NOT recommend or
  generate any architecture design or Google Cloud product recommendations.

- [ ] **Step 6**: Summarize the functional and non-functional requirements
  provided by the user into a consolidated requirements summary.

- [ ] **Step 7**: Present the generated requirements summary to the user and
  obtain approval (the user MUST explicitly say "yes" or "I approve") before
  proceeding to Phase 2.

**Important**: **STOP**, DON'T proceed to generate architecture diagram,
architecture description or product recommendations until you have confirmed the
generated requirements summary and resolved all ambiguities and contradictions
in this phase.

## Phase 2: Solution architecture

### Task 2.1: Identify Google Cloud products and features required for the workload.

- [ ] **Step 1**: Recommend products and features that are appropriate for each
  component of the user's workload, prioritizing Google Cloud products.

  **Important**: The Google Cloud products and features that you recommend
  MUST be consistent with the guidance in
  [Product Mapping](references/product-mapping.md).

- [ ] **Step 4**: Present the generated product recommendations to the user and
  obtain approval (the user MUST explicitly say "yes" or "I approve") before
  proceeding to Task 2.2.

  **Important**: **STOP**, DON'T proceed to generate architecture diagram until
  you have confirmed the generated product recommendations with the user.

### Task 2.2: Generate an architecture diagram and description

- [ ] **Step 1**: Generate an architecture diagram in the Mermaid format:
      https://github.com/mermaid-js/mermaid.

  The diagram must show the data flows and request flows across the components
  of the architecture, based on the gathered requirements and product
  recommendations. The diagram MUST explicitly show both the ingestion pipeline
  and serving pipeline.

  The following is an **example** of the data flows and request flows that the
  architecture diagram should show:
  - **Ingestion pipeline**: Catalog Data -> AlloyDB Table
    (`apparels`) -> B-Tree Indexes on Facets -> Text embedding
    (`text-embedding-005`) -> ScaNN Vector Index.
  - **Serving pipeline**: User Browser -> Cloud Run Web App -> MCP
    Toolbox for Databases -> AlloyDB Single-Query Hybrid Search (ScaNN Vector
    Search + SQL WHERE Filters) -> `ai.rank` Reranker -> Gemini Pro
    `ai.generate` Quality Validation -> Validated Results -> User Browser.

- [ ] **Step 2**: Generate a description that explains the purpose of each
  component, the relationships between the components, and the task flow or data
  flow.
- [ ] **Step 3**: Present the generated architecture diagram and description
  to the user and obtain approval (the user MUST explicitly say "yes" or "I
  approve") before proceeding to Task 2.3.

  **Important**: **STOP**, DON'T proceed to generate design recommendations
  until you have confirmed the generated architecture description with the user.

### Task 2.3: Generate design recommendations.

- [ ] **Step 1**: Generate design recommendations and best practices to
  optimally configure each component in the architecture based on the workload
  requirements.

  **Important**:
    - When you generate design recommendations, consider the following:
      - Functional requirements that were gathered in Phase 1.
      - Non-functional requirements that were gathered in Phase 1.
    - Align the generated design recommendations with the recommendations in
      [Design Recommendations](references/design-recommendations.md).
    - To generate guidance for the non-functional requirements, use the
      following skills:
      - `google-cloud-waf-security`
      - `google-cloud-waf-reliability`
      - `google-cloud-waf-cost-optimization`
      - `google-cloud-waf-operational-excellence`
      - `google-cloud-waf-performance-optimization`
      - `google-cloud-waf-sustainability`
- [ ] **Step 2**: Present the generated recommendations to the user and obtain
  approval (the user MUST explicitly say "yes" or "I approve") before
  proceeding to Task 2.4.

  **Important**: **STOP**, DON'T proceed to generate deployment guidance until
  you have confirmed the design recommendations with the user.

### Task 2.4: Generate deployment guidance.

- [ ] **Step 1**: Generate guidance to deploy the solution, including the
  following:
  - AlloyDB DDL & SQL setup scripts for extensions (`google_ml_integration`,
    `alloydb_scann`), tables, B-Tree indexes, ScaNN vector indexes, hybrid
    search SQL, and Gemini validation CTEs.
  - MCP Toolbox deployment configuration on Cloud Run.
  - Python Cloud Run Function shim deployment command.
  - Application deployment command (`gcloud run deploy {app_name}`).
  - Terraform code or `gcloud` CLI commands to create required infrastructure.

  **Important**: The deployment guidance that you generate MUST be consistent
  with the guidance in the following resources:
  - [Related Guidance](references/related-guidance.md)
  - Relevant skills in
    https://github.com/google/skills/tree/main/skills/cloud

- [ ] **Step 2**: Present the generated deployment guidance to the user and
  obtain approval (the user MUST explicitly say "yes" or "I approve") before
  proceeding to Phase 3.

  **Important**: **STOP**, DON'T proceed to generate solution validation until
  you have confirmed the deployment guidance with the user.

## Phase 3: Solution validation

### Task 3.1: Pre-deployment validation

- [ ] **Step 1**: Create a pre-deployment plan to statically validate the
  generated solution and verify that it meets the workload requirements
  without provisioning live resources:
  - **Deployment dry-run**: Validate infrastructure syntax and preview the
    resources that will be provisioned using dry-run commands (e.g.,
    `terraform plan` or (where supported) `gcloud ... --dry-run`).
  - **Architecture & policy analysis**: Perform static verification of
    network routing topologies, firewall rules, and IAM enforcement against
    best practices.
- [ ] **Step 2**: Present the static validation plan to the user, obtain
  approval (the user MUST explicitly say "yes" or "I approve"), and execute the
  dry-run commands.
- [ ] **Step 3**: Troubleshoot and fix any errors or policy discrepancies
  identified during dry-run checks until validation succeeds.
- [ ] **Step 4**: Proceed to Task 3.2

### Task 3.2: Runtime validation (Post-deployment)

- [ ] **Step 1**: Ask the user whether they choose to deploy the infrastructure
  now to perform live runtime verification, or skip directly to Phase 4.
- [ ] **Step 2**: **If the user chooses to deploy the infrastructure**:
  - After the user deploys the infrastructure, generate runtime
    verification commands (using tools like `curl`, `ping`, or `gcloud`)
    and provide them to the user to execute, to test live endpoint
    reachability, networking paths, and load balancer routing.
  - Troubleshoot any deployment or runtime routing issues until checks pass.
- [ ] **Step 3**: Proceed to Phase 4.

## Phase 4: Solution packaging and presentation

- [ ] **Step 1**: Consolidate the final text artifacts that were generated in
  Phase 2 into a single Markdown file named `solution-architecture-guide.md`,
  based on the template in [Output Template](assets/output-template.md).
- [ ] **Step 2**: Request the user's permission to write the code files in the
  user's workspace.
- [ ] **Step 3**: After the user gives permission, write the final code files in
  the user's workspace.
