---
name: google-cloud-solution-agentic-analytics-spark-knowledge-catalog
metadata:
  category: MultiProductSolutions
description: >-
  Discovers requirements and generates guidance to design and deploy a governed,
  secure agentic-analytics solution for data that's distributed across Google
  Cloud, other cloud providers, or on-premises. Data that's outside Google Cloud
  (such as data from Databricks, Snowflake, Salesforce, SAP, or Oracle systems)
  is accessed through federation mechanisms such as Apache Iceberg, other
  "zero-copy ETL" methods, or remote query push-down. Use this skill when
  designing an architecture for efficient analytics across large volumes of
  structured and unstructured data that's located in multiple systems and
  environments, including other cloud providers and on-premises.
---

# Agentic analytics across cloud providers and data types

This skill provides a workflow to design and implement a governed, secure
pipeline for agentic analytics solution across structured and unstructured data
that's distributed across Google Cloud, on-premises systems, and other cloud
providers.

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

## Phase 1: Requirements discovery and analysis

1.  Request the user to describe the functional requirements (business
    processes, activities, and use cases) of their workload. Ask the user the
    following questions, one question at a time:
    -   What are your primary inventory data sources? Are they unstructured
        (e.g., PDF flavor recipes, invoices) or structured (e.g., historical
        sales in Iceberg)?
    -   Where are these sources hosted? Are they split across AWS S3, Azure
        Blob, Google Cloud Storage, or databases like AlloyDB?
    -   How do you manage and federate metadata across your data
        sources within Google Cloud and in external locations (such as other
        cloud providers)?
    -   What are your analytical and computational requirements to join, clean,
        and run forecast models over large-scale distributed data?
    -   What types of natural language prompts do your data scientists or
        operational agents expect to execute in their agentic IDE (VS Code or
        Antigravity IDE)?
2.  Request the user to describe the non-functional requirements of their
    workload.

    The following are examples of questions you can ask to gather non-functional
    requirements:
    -   **Security, privacy, and compliance**: What data privacy rules,
        regulatory compliance (e.g., GDPR, HIPAA), or data governance
        requirements must the system adhere to?
    -   **Reliability**: What are your uptime, high-availability,
        fault-tolerance, and disaster recovery objectives (RTO/RPO)?
    -   **Performance**: What target query latencies and SLA expectations does
        your workload require?
    -   **Operations**: What operational monitoring metrics do your data
        scientists and engineers need?
    -   **Cost & Sustainability**: Do you have specific budget constraints and
        data egress/transfer cost requirements?
3.  Ask the user whether the workload currently runs on other cloud providers or
    on-premises.
    *   If the user answers "yes", then ask the user to describe the
        architecture of the current deployment.
    *   If the user answer "no", then proceed to the next step.
4.  Request the user to describe dependencies, if any, on other workloads,
    products, or tools. The following are examples of questions that you can
    ask to get information about the dependencies:
    *   Do you have any upstream or downstream dependencies on external systems
        (e.g., identity providers, data curation platforms, CI/CD pipelines, or
        active data catalogs)?
    *   Are there any requirements for your general data-engineering software
        delivery lifecycle (e.g., version control, testing, data quality
        assurance)? Provide the path to a directory or examples of these
        artifacts.
5.  Review the input that the user has provided so far, and check whether there
    are any ambiguities or contradictions.

    If you identify any ambiguities or contradictions in the requirements that
    the user has provided (e.g., zero-copy vs copying data to a repository), then
    do the following for each ambiguity or contradiction that you identify:
    *   Describe the ambiguity or contradiction (e.g., explain why copying data
        contradicts the zero-copy requirement and also incurs data-transfer
        costs).
    *   Ask the user how they wish to resolve the ambiguity or contradiction.
        *   If the user delegates the choice to you (e.g., the user replies with
            "do what you think is best" or "you decide"), then provide a clear
            suggestion to resolve the ambiguity or contradiction (e.g., suggest
            prioritizing zero-copy remote queries), explain your reasoning
            (e.g., to eliminate multi-cloud fees and data duplication), and ask
            the user to approve your suggestion.

    **Critical**: Until all the ambiguities and contradictions that you identify
    are resolved according to the preceding guidance, you must NOT recommend or
    generate any architecture design, technical decomposition, or Google Cloud
    product recommendations.

6.  **Important**: DON'T start this step if there are unresolved contradictions
    or ambiguities from Step 5.

    Generate a technical decomposition of the components of the workload.
    *   The technical decomposition must break down the solution into logical
        components.
    *   The decomposition MUST address role-based security and credentials
        within the relevant layers.
    *   The decomposition MUST be organized under the following four layers,
        which represent a standard architectural pattern for agentic analytics
        solutions, flowing from user interaction through data context and
        governance to core data processing:
        *   **User-interaction layer (IDE)**: e.g., agentic development
            environment.
        *   **Grounding and trusted data**: e.g., foundation model, MCP servers,
            and data warehouse in the cloud.
        *   **Metadata curation**: e.g., metadata scanning.
        *   **Data processing and analytics**: e.g., analytics workflows, Spark
            data processing, and external data stores.
7.  Request the user to approve the generated technical decomposition.
8.  If the user requests changes, then generate an updated technical
    decomposition.
9.  Repeat steps 5 through 8 until the user approves the generated technical
    decomposition.
10. After the user approves the technical decomposition, proceed to Phase 2.
    **Important**: Don't proceed to the next phase until the user approves the
    generated technical decomposition of the workload.

## Phase 2: Solution architecture

### Ground all generated content

For each task in this phase, to ensure that the generated content aligns with
the latest and official Google Cloud guidance, ground the generated content by
using the following resources:
*   Google Developer Knowledge MCP server
    *   Instructions to connect to the MCP Server:
        https://developers.google.com/knowledge/mcp.md.txt
    *   Server: https://developerknowledge.googleapis.com/mcp
        *   Tools:
            *   `developerknowledge:search_documents`
            *   `developerknowledge:get_documents`
            *   `developerknowledge:answer_query`
*   Relevant skills from https://github.com/google/skills
*   Official Google Cloud documentation, including the following:
    *   Reference architecture for agentic cross-cloud analytics workflows
        across multi-cloud data lakes, structured data warehouses, and
        unstructured data stores:
        https://docs.cloud.google.com/architecture/agentic-ai-cross-cloud-analytics.md.txt
    *   Decision-making guides for the products and topics that are relevant to
        the workload:
        https://github.com/google/skills/blob/main/skills/cloud/google-cloud-solution-architecture/references/decision-making-guides.md
    *   Best-practices guides for the products and topics that are relevant to
        the workload:
        https://github.com/google/skills/blob/main/skills/cloud/google-cloud-solution-architecture/references/best-practices-guides.md

### Task 2.1: Identify Google Cloud products and features required for the workload.

1.  For each component in the confirmed technical decomposition, identify the
    appropriate Google Cloud products and features, based on the guidance in the
    following resources and adjusted suitably based on the approved technical
    decomposition:
    -   `references/product-selection-guidance.md`
    -   `https://github.com/google/skills/blob/main/skills/cloud/google-cloud-solution-architecture/references/decision-making-guides.md`
2.  Present the generated product recommendations and ask the user to approve
    the recommendations.
3.  If the user requests changes, then make the required changes.
4.  Repeat steps 2 and 3 until the user approves the product recommendations.
5.  After the user approves the product recommendations, proceed to Task 2.2.

### Task 2.2: Generate an architecture diagram.

1.  Generate an architecture diagram in Mermaid format:
    https://github.com/mermaid-js/mermaid.
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

    **Important**:
    *   When you generate design recommendations, consider the following:
        *   Functional requirements that were gathered in Phase 1.
        *   Non-functional requirements that were gathered in Phase 1.
    *   Align the generated design recommendations with the recommendations in
        `references/design-recommendations.md`.
    *   To generate design recommendations for Knowledge Catalog, use the
        resources that are listed in
        `references/knowledge-catalog-documentation.md`
    *   To generate guidance for the non-functional requirements, use the
        following skills:
        -   `google-cloud-waf-security`
        -   `google-cloud-waf-reliability`
        -   `google-cloud-waf-cost-optimization`
        -   `google-cloud-waf-operational-excellence`
        -   `google-cloud-waf-performance-optimization`
        -   `google-cloud-waf-sustainability`
2.  Present the generated recommendations to the user and ask whether the user
    needs any changes.
3.  If the user needs changes, then make the required changes.
4.  Repeat steps 2 and 3 until the user confirms that the generated design
    recommendations meet their requirements.
5.  Proceed to Task 2.5.

### Task 2.5: Generate deployment guidance.

1.  Generate deployment guidance, including code and instructions to enable the
    user to deploy the solution.

    **Important**:
    *   The guidance must provide steps for deployment prerequisites, including
        setting up the Google Cloud project, enabling billing, enabling the
        required APIs, and setting up the required roles and permissions.
    *   Use the following resources as the technical foundation for the
        deployment guidance that you generate:
        -   https://github.com/gemini-cli-extensions/data-agent-kit-starter-pack/tree/main/skills:
            A plugin that provides a specialized suite of skills and MCP tools
            to let you use your preferred coding agent to architect complex data
            pipelines, transform data with dbt, write Spark and BigQuery SQL
            notebooks, create and troubleshoot Dataflow pipelines, and
            orchestrate end-to-end workflows across the Google Cloud data
            ecosystem.
        -   https://codelabs.developers.google.com/next26/gen-keynote/raw-data-forecasting#0:
            A codelab that provides instructions to use the Data Agent Kit
            extension to efficiently analyze a cross-cloud data topology from
            within your preferred agentic development environment.
        -   https://codelabs.developers.google.com/governance-context-part1#0: A
            codelab that provides instructions to build a data foundation in
            BigQuery, apply rigid metadata tags (Knowledge Catalog Aspects) to
            differentiate valid data from noise, and use the Gemini CLI to
            locally test if the LLM strictly follows your governance rules.
        -   https://docs.cloud.google.com/dataplex/docs/establish-foundational-data-context.md.txt:
            A tutorial that shows how to establish data context in Knowledge
            Catalog.
        -   https://docs.cloud.google.com/dataplex/docs/ingest-custom-sources.md.txt:
            A guide that explains how to bring information about your unique,
            custom data sources into Knowledge Catalog.
2.  Present the generated deployment guidance to the user and ask whether the
    user needs any changes.
3.  If the user requests changes, then make the required changes.
4.  Repeat steps 2 and 3 until the user confirms that the generated deployment
    guidance meets their requirements.
5.  Proceed to Phase 3.

## Phase 3: Solution validation

1.  Create a plan to validate the generated solution. The plan must outline the
    steps to verify that the generated solution meets the workload's
    requirements.
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

1.  Consolidate the text artifacts that were generated in Phase 2 and Phase 3
    into a single Markdown file named `solution-architecture-guide.md`, based on
    the template in `assets/output-template.md`.
2.  Present the consolidated solution-architecture-guide.md to the user.
3.  Request the user's permission to write the code files in the user's
    workspace.
4.  After the user gives permission, write the code files in the user's
    workspace.

## Supporting resources

*   https://docs.cloud.google.com/data-cloud-extension/antigravity/transform-data.md.txt:
    Guide to how the Data Agent Kit extension lets you use notebooks for data
    transformation and analysis.
*   https://docs.cloud.google.com/dataplex/docs/use-cases.md.txt: Use cases for
    Knowledge Catalog.
*   https://docs.cloud.google.com/managed-spark/docs/guides/lightning-engine.md.txt:
    Guide to accelerating Apache Spark workloads by using Lightning Engine.
*   https://docs.cloud.google.com/bigquery/docs/use-knowledge-catalog.md.txt:
    Guide to use Knowledge Catalog as a governance and agentic layer for
    BigQuery.
