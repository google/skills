---
name: google-cloud-solution-architecture
metadata:
  category: MultiProductSolutions
description: >-
  Interactively discovers requirements for a specific cloud workload and
  generates design recommendations and architectural guidance to build a
  multi-product solution in Google Cloud. Use this skill to generate holistic,
  end-to-end design recommendations and architectural guidance for complex,
  multi-product workloads on Google Cloud for specific use cases. Don't use this
  skill when other specialized skills (e.g., product-specific or
  google-cloud-recipe-*) directly address the user's workload or use case.
---

# Google Cloud solution-architecture workflow

## Overview of the workflow

The workflow consists of the following phases:

*   **Phase 1: Requirements discovery**. Gather detailed requirements related to
    the cloud workload or use case that the user needs assistance for.
*   **Phase 2: Solution architecture**. Use the requirements that were gathered
    in Phase 1 to generate a detailed solution architecture for the cloud
    workload or use case.
*   **Phase 3: Solution validation**. Create a plan to validate the generated
    solution, generate validation instructions and scripts, and provide them to
    the user to execute (or perform a dry-run validation with explicit
    permission from the user).
*   **Phase 4: Solution packing and presentation**. Consolidate the generated
    content and present the solution.

**Important notes about the workflow**:

*   **Strict phase separation**: During Phase 1 (Requirements discovery), when
    you ask the user clarifying questions, don't recommend, propose, or outline
    any architectural designs, technical decompositions, cloud services, or
    component mappings. Proposing solutions before functional and non-functional
    requirements are thoroughly assessed causes confirmation bias and risks
    anchoring the solution on specific products, features, or tools prematurely.

*   **Iterative approval & task transitions**: For each deliverable in this
    workflow (technical decompositions, product recommendations, diagrams,
    architectural descriptions, and deployment scripts), explicitly present your
    output to the user for approval. If the user requests modifications,
    iteratively revise the content until approved before progressing to the
    subsequent task or phase.

*   **No autonomous execution of code and scripts**: Don't run any scripts or
    code that you generate without explicit, unambiguous permission from the
    user. Executing scripts autonomously can provision unintended cloud
    resources (incurring unexpected costs), mutate live infrastructure, or pose
    security and safety risks. Always offer the option for the user to execute
    the commands manually.

*   **When you can skip certain phases**: If the user's prompt indicates that a
    specific phase or task in this workflow is already completed or approved
    (e.g., "requirements discovery stage is completed", "product selection is
    approved", or "architecture is confirmed"), don't repeat that phase or task.
    Instead, skip directly to the requested task (such as generating the
    technical decomposition, recommending products, or compiling the solution
    guide).

## Phase 1: Requirements discovery

1.  Gather the following requirements related to the workload or use case for
    which the user needs assistance.

    **CRITICAL**: You MUST NOT generate any architecture designs, product
    recommendations, or technical decompositions until the user provides these
    requirements.

    *   **Functional requirements**: Ask the user to describe the business
        processes, activities, and use cases of their workload.
    *   **Non-functional requirements**: Ask the user to describe requirements
        for security, privacy, compliance, reliability, disaster recovery, cost,
        operations, performance, and sustainability.
        *   **CRITICAL**: If non-functional requirements are missing or
            incomplete, you MUST ask the user to describe the requirements and
            explicitly explain why they are important (e.g., because they
            directly dictate operational SLAs, availability tiers, scaling
            configuration, cost budgets, resource types, and the security
            posture) when asking the user to supply them.
    *   **Current state**: Ask whether the workload currently runs on other
        cloud providers or on-premises (if yes, prompt for the architecture of
        the existing deployment).
    *   **System dependencies**: Ask the user to describe any dependencies
        between their application and other workloads, products, systems, or
        tools.

2.  Review the input that the user has provided so far, and check whether there
    are any ambiguities or contradictions (e.g., conflicting goals like complete
    network isolation with zero internet exposure vs. real-time ingestion from
    public APIs).

    If you identify any ambiguities or contradictions in the user's
    requirements, you must:

    *   Clearly describe the ambiguities and contradictions.
    *   Explain why the contradictory requirements cannot be simultaneously
        satisfied.
    *   Request the user to clarify their trade-off preferences and choices to
        resolve the ambiguities and contradictions.
        *   If the user delegates the choice to you (e.g., the user replies with
            "do what you think is best" or "you decide"), then provide a clear
            suggestion to resolve the ambiguity or contradiction, explain your
            reasoning, and ask the user to approve your suggestion.

    **CRITICAL**: Until all the ambiguities and contradictions that you identify
    are resolved, don't recommend or generate any architecture design, technical
    decomposition, or Google Cloud product recommendations. Ambiguous or
    contradictory requirements lead to invalid architectural assumptions.

3.  Generate a technical decomposition of the components of the workload that
    breaks down the solution into logical components. Present it to the user and
    obtain approval before proceeding to Phase 2.

    **CRITICAL**: Before proceeding to Phase 2, ensure that the user has
    approved the technical decomposition. Misalignment of the technical
    decomposition with the user's requirements will invalidate the outputs of
    the subsequent phases in this workflow.

## Phase 2: Solution architecture

Use the approved requirements from Phase 1 to generate a comprehensive solution
architecture.

### Ground all generated content

For each task in this phase, to ensure that the generated content aligns with
the latest and official Google Cloud guidance, you must ground the generated
content by using the following resources:

*   Google Developer Knowledge MCP server
    *   Server: https://developerknowledge.googleapis.com/mcp
    *   Tools:
    *   `developerknowledge:search_documents`
    *   `developerknowledge:get_documents`
    *   `developerknowledge:answer_query`
*   Relevant skills from https://github.com/google/skills
*   Official Google Cloud documentation, including the following:
    *   Reference architectures and design guides that are relevant to the
        technology category of the workload: `references/architecture-guides.md`
    *   Decision-making guides for the products and topics that are relevant to
        the workload: `references/decision-making-guides.md`
    *   Best-practices guides for the products and topics that are relevant to
        the workload: `references/best-practices-guides.md`

For each item in the generated guidance, you must include citations to the
relevant official Google Cloud documentation pages.

### Task 2.1: Identify Google Cloud products and features required for the workload.

1.  Recommend the products and features that are appropriate for each component
    of the user's workload.

    **CRITICAL**:

    *   Don't recommend any products or features that are deprecated, retired,
        decommissioned, or unsupported. To check the status of a product or
        feature, call `developerknowledge:answer_query` or
        `developerknowledge:search_documents` with query strings like:
        "{product_name} release status".
    *   If multiple products or features can be used for a component of the
        workload, then do the following:
        *   Recommend the most appropriate product or feature. When alternative
            products exist, the relevant product documentation might provide
            guidance on when to choose each product. Follow that guidance.
        *   Mention the available alternative products or features.
        *   Explain the pros and cons of each alternative product or feature.

2.  Present the generated product recommendations to the user and ask whether
    any changes are needed.

    **CRITICAL**: Don't generate anything further (architecture diagrams,
    descriptions, or deployment configurations) in the same turn. Halt execution
    immediately after listing the product choices until the user approves the
    product selections.

3.  After the user approves the product selections, proceed to Task 2.2.

### Task 2.2: Generate an architecture diagram.

1.  Generate an architecture diagram in Mermaid format:
    https://github.com/mermaid-js/mermaid.
2.  Present the generated diagram to the user and obtain approval before
    proceeding to Task 2.3.

### Task 2.3: Generate an architecture description.

1.  Generate a description that explains the purpose of each component, the
    relationships between the components, and the task flow or data flow.
2.  Present the generated architecture description to the user and obtain
    approval before proceeding to Task 2.4.

### Task 2.4: Generate design recommendations.

1.  Generate design recommendations and best practices to optimally configure
    each component in the architecture based on the workload's requirements.
    **Important**:

    *   When generating design recommendations, incorporate the following:
        *   Functional requirements that were gathered in Phase 1.
        *   Non-functional requirements that were gathered in Phase 1.
    *   To generate guidance for non-functional requirements, use the following
        skills, as appropriate:
        -   `google-cloud-waf-security`
        -   `google-cloud-waf-reliability`
        -   `google-cloud-waf-cost-optimization`
        -   `google-cloud-waf-operational-excellence`
        -   `google-cloud-waf-performance-optimization`
        -   `google-cloud-waf-sustainability`

    If any of the specialized `google-cloud-waf-*` skills are not available in
    your current workspace, derive design guidance directly from the
    documentation references in `references/best-practices-guides.md`.

2.  Present the generated recommendations to the user and obtain approval before
    proceeding to Task 2.5.

### Task 2.5: Generate deployment guidance.

1.  Generate deployment guidance, including infrastructure-as-code and
    instructions to enable the user to deploy the solution.
2.  Present the generated deployment guidance to the user and obtain approval
    before proceeding to Phase 3.

## Phase 3: Solution validation

### Task 3.1: Pre-deployment validation

1.  Create a pre-deployment plan to statically validate the generated solution
    and verify that it meets the workload's requirements without provisioning
    live resources:
    *   **Deployment dry-run**: Validate infrastructure syntax and preview the
        resources that will be provisioned using dry-run commands (e.g.,
        `terraform plan` or (where supported) `gcloud ... --dry-run`).
    *   **Architecture & policy analysis**: Perform static verification of
        network routing topologies, firewall rules, and IAM enforcement against
        best practices.
2.  Present the static validation plan to the user and obtain explicit
    permission from the user to execute the dry-run commands. If the user gives
    permission, then run the commands; otherwise, or if the user prefers,
    provide the exact commands that the user can run manually.
3.  Troubleshoot and fix any errors or policy discrepancies identified during
    dry-run checks until validation succeeds.
4.  Proceed to Task 3.2

### Task 3.2: Runtime validation (Post-deployment)

1.  Ask the user whether they choose to deploy the infrastructure now to perform
    live runtime verification, or skip directly to Phase 4.
2.  **If the user chooses to deploy the infrastructure**:
    *   After the user deploys the infrastructure, generate runtime verification
        commands (using tools like `curl`, `ping`, or `gcloud`) and provide them
        to the user to execute, to test live endpoint reachability, networking
        paths, and load balancer routing.
    *   Troubleshoot any deployment or runtime routing issues until checks pass.
3.  Proceed to Phase 4.

## Phase 4: Solution packaging and presentation

Package all the generated text and code artifacts for final presentation.

1.  Consolidate the text artifacts that were generated in Phase 2 and Phase 3
    into a single Markdown file named `solution-architecture-guide.md`, based on
    the template in `assets/output-template.md`.
2.  Request the user's permission to write the code files in the user's
    workspace.
3.  After the user gives permission, write the code files in the user's
    workspace.
