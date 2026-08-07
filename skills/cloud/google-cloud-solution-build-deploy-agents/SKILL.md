---
name: google-cloud-solution-build-deploy-agents
metadata:
  category: MultiProductSolutions
description: >-
  Designs, builds, and deploys AI agents or multi-agent systems on Google Cloud.
  Provides an interactive workflow to gather requirements, recommend a tailored
  architecture, and generate deployment instructions. Use when designing or
  implementing agentic systems on Google Cloud. Don't use for general Google
  Cloud solution architecture (use google-cloud-solution-architecture instead)
  or for narrow tasks targeting a single product without agent context.
---

# Build and deploy AI agents on Google Cloud

This skill guides agents through the workflow of designing and implementing a
tailored multi-product solution in the cloud for a given workload, use case, or
requirement.

## Workflow

The solution design and implementation workflow is divided into the following
phases:

*   **Phase 1: Requirements discovery and analysis**: Analyze the workload's
    requirements, constraints, dependencies, and current state.
*   **Phase 2: Solution design**: Build a technology stack, architecture, and
    deployment configuration for the workload based on Google Cloud design best
    practices and recommendations.
*   **Phase 3: Implementation plan**: Generate automation and instructions to
    deploy the solution.
*   **Phase 4: Solution validation**: Validate that the deployment meets the
    requirements of the workload.

Copy this checklist into your active task/plan artifact to track progress across
the four phases:

-   [ ] Phase 1: Requirements discovery and analysis completed & confirmed.
-   [ ] Phase 2: Solution architecture generated & approved.
-   [ ] Phase 3: Implementation plan generated & approved.
-   [ ] Phase 4: Solution validation generated & approved.

### Phase 1: Requirements discovery and analysis

1.  **Discover requirements**: Gather and understand the functional and
    non-functional requirements, business goals, and current state (if any) of
    the workload, including its architecture, dependencies, and constraints.

    *Important*: First, check whether the user's initial prompt has already
    answered the following questions or whether the prompt explicitly asks you
    to propose a solution architecture/diagram from a given set of parameters.

    -   If the user's prompt provides sufficient requirements and it explicitly
        requests an architecture proposal or diagram, then skip asking the
        questions below, and instead proceed to the step **Recommend agent
        design pattern**.
    -   If the user's prompt doesn't provide sufficient requirements, then
        complete these steps to gather missing information:

        1.  Ask the user to describe the functional requirements of their
            workload: business processes, activities, and use cases.

        2.  Ask the user to describe the non-functional requirements (security,
            privacy, compliance, reliability, disaster recovery, cost,
            operations, performance, and sustainability) of their workloads.

        3.  Ask the user what existing systems, knowledge bases, product
            documentation, or other documentation the AI agents need to access
            for grounded guidance.

        4.  Ask the user to describe dependencies, if any, on other workloads,
            products, or tools.

        5.  Review the input that the user has provided so far, and check
            whether there are any ambiguities or contradictions in the input.

            If you identify any ambiguities or contradictions in the
            requirements that the user has provided, then do the following for
            each ambiguity or contradiction that you identify:

            *   Describe the ambiguity or contradiction.
            *   Ask the user how they wish to resolve the ambiguity or
                contradiction.
                *   If the user delegates the choice to you (e.g., the user
                    replies with "do what you think is best" or "you decide"),
                    then provide a clear suggestion to resolve the ambiguity or
                    contradiction, explain your reasoning, and ask the user to
                    approve your suggestion.

            **Critical**: Until all the ambiguities and contradictions that you
            identify are resolved according to the preceding guidance, you must
            NOT recommend or generate any architecture design, technical
            decomposition, or Google Cloud product recommendations.

2.  **Recommend agent design pattern**: Evaluate the complexity, workflow,
    latency, and cost requirements of the workload to recommend an agent design
    pattern:

    -   **Single-agent system**: Recommend for simpler tasks, acting as an
        effective starting point to refine core logic and tools.
    -   **Multi-agent system**: Recommend for complex problems requiring
        multiple specialized agents to collaborate on a workflow.

3.  **Identify components**: Based on the requirements analysis, generate a
    technical decomposition of the workload. The technical decomposition must
    identify the logical components of the workloads and their relationships.
    Also identify any cross-cloud components, hybrid components, or on-premises
    components that the solution needs to integrate with.

4.  **Ask for confirmation**: Ask the user to confirm whether the recommended
    design pattern and technical decomposition match their workload
    requirements.

5.  **Iterate**: If the user requests changes, generate an updated technical
    decomposition, and ask the user to confirm the changes. Continue iterating
    until the user confirms the technical decomposition. Proceed to the next
    phase only after the user provides confirmation of the technical
    decomposition.

### Phase 2: Solution design

1.  **Retrieve relevant Google Cloud guidance from
    `references/related-guidance.md`**.

    *Important*: Use the content that you retrieved from
    `references/related-guidance.md` to ground the guidance that you generate in
    the remaining steps of this phase.

2.  **Map components to Google Cloud products**: For each component in the
    confirmed technical decomposition, identify the appropriate Google Cloud
    products and features by consulting
    [product-mappings.md](references/product-mappings.md) for detailed
    recommendations, trade-offs, and alternatives across networking, frontends,
    agent/model runtimes, memory stores, and tools.

3.  **Create architecture diagram**: Create an architecture diagram in Mermaid
    format: https://github.com/mermaid-js/mermaid. The diagram should show the
    components, their relationships, and data/control flows.

4.  **Generate design recommendations**: Generate design guidance based on the
    following Google Cloud best practices and recommendations. Use the
    information in `references/related-guidance.md`, with an emphasis on the
    guidance in `references/design-principles.md`.

5.  **Draft solution architecture**: Compile the requirements, technical
    decomposition, product mapping, architecture diagram, and design
    recommendations into a single Markdown file adhering to the format in
    [solution-template.md](assets/solution-template.md). Save this document in
    the workspace as `solution-architecture.md`.

6.  **Request review**: Present the generated solution architecture (including
    the complete fenced `mermaid` code block for the diagram) directly to the
    user in your response, and explicitly request their feedback or approval.
    When you present the architecture, ask the user to provide approval for you
    to proceed with an implementation plan.

7.  **Iterate**: If the user requests changes, generate an updated solution
    architecture and repeat the steps from "Map components to Google Cloud
    products" through "Request review" until the user approves the solution
    architecture.

### Phase 3: Implementation plan

1.  **Retrieve relevant implementation resources**:

    *Important*: Use the resources in references/related-guidance.md as the
    technical foundation for the Infrastructure as Code (IaC) and the deployment
    instructions that you generate in the remaining steps of this phase.

2.  **Identify deployment prerequisites**: Document prerequisites for the
    deployment, including the following:

    -   Projects and billing associations
    -   Required Google Cloud APIs
    -   Required IAM permissions
    -   Any other prerequisites

3.  **Generate Infrastructure as Code (IaC)**: Generate code (e.g., Terraform)
    and deployment scripts to automate the provisioning of the proposed Google
    Cloud resources.

    -   Where appropriate, alongside or instead of raw infrastructure scripts,
        instruct the user to use Agents CLI commands (`agents-cli scaffold
        create` or `agents-cli scaffold enhance`) to set up or enhance the
        project structure, deployment configuration, and CI/CD pipelines.

4.  **Write deployment instructions**: Draft sequential, step-by-step deployment
    instructions to execute the IaC and initialize the workload components.
    Compile the deployment prerequisites, IaC, and deployment instructions into
    a single Markdown file adhering to the format in
    [implementation-template.md](assets/implementation-template.md). Save this
    document in the workspace as `implementation-instructions.md`.

    -   The instructions MUST provide the exact ADK code to define a stateful
        agent node that takes a prompt, calls a model, and returns a tool
        execution request.
    -   The instructions MUST demonstrate how to register tools like database
        readers by using Model Context Protocol (MCP) standards.
    -   If deploying the agent to Cloud Run, the instructions MUST show how to
        configure Cloud Run to scale to zero when the agent is idle, reducing
        runtime costs.
    -   The instructions MUST recommend using encrypted environment variables to
        store model parameters or private API credentials. Encryption helps to
        prevent the exposure of sensitive credentials in plain-text container
        log streams.
    -   Where appropriate, the instructions MUST specify using the Agents CLI
        `agents-cli deploy` command (alongside or instead of raw
        infrastructure/deployment scripts) to run the deployment.

5.  **Request review**: Present the generated deployment instructions to the
    user and explicitly request their feedback and confirmation.

6.  **Iterate**: If the user requests changes, generate an updated
    implementation plan and repeat the steps from "Generate Infrastructure as
    Code (IaC)" through "Request review" until the user approves the
    implementation plan.

### Phase 4: Solution validation

1.  **Retrieve relevant verification resources**:

    *Important*: Use the resources in references/related-guidance.md and their
    verification patterns as the starting point for the validation checks and
    verification scripts that you generate in the remaining steps of this phase.

2.  **Define validation checks**: Outline validation steps to verify that the
    deployed infrastructure meets the workload's requirements:

    -   **Deployment dry-run**: Commands like `terraform plan` to preview
        changes. Include instructions to run agent deployment in dry-run mode
        (e.g., using `agents-cli deploy --dry-run` or `-n`) to preview steps and
        Terraform executions before pushing to production.
    -   **Local testing and quality verification**: Recommend using the Agents
        CLI to run and test agent logic locally (`agents-cli run`) and conduct
        systematic evaluations (`agents-cli eval run`) to verify agent quality
        and performance before deploying.
    -   **Connectivity and routing**: Verification of network paths, load
        balancer routing, and service endpoints.
    -   **Security policies**: Verification of restricted access, firewall
        rules, and IAM enforcement.

3.  **Generate verification scripts**: Draft lightweight scripts or command-line
    instructions (e.g. using `curl`, `gcloud`, or `agents-cli`) that the user
    can run to perform these validation checks.

    -   The validation plan MUST include instructions using the Agents CLI for
        local runs, evaluations, and post-deployment validation checks (e.g.,
        `agents-cli run --url <service-url>` to test the deployed service
        endpoint).

4.  **Compile validation plan**: Document the validation steps, verification
    scripts, and expected outcomes in a single Markdown file adhering to the
    format in [validation-template.md](assets/validation-template.md). Save this
    document in the workspace as `validation-plan.md`.

5.  **Request review**: Present the validation plan to the user and explicitly
    request their feedback or approval on the validation plan.

6.  **Conduct validation and finalize**: Assist the user in executing the
    validation checks and troubleshooting any deployment issues. After the
    solution is validated successfully, request final approval from the user.

7.  **Iterate**: If the user requests changes, generate an updated validation
    plan and repeat the steps from "Define validation checks" through "Request
    review" until the user approves the validation plan.

--------------------------------------------------------------------------------

## References & Supporting Links

*   For the complete list of Google Cloud architectural documentation, product
    manuals, development kits, and checklists used by this skill, see
    [related-guidance.md](references/related-guidance.md).
