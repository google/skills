---
name: google-cloud-solution-agentic-ai-data-science-workflow
metadata:
  category: MultiProductSolutions
description: >-
  Designs a tailored multi-product agentic data science
  architecture on Google Cloud that incorporates opinionated best practices. Use
  when architecting multi-product solutions for agent-based data analytics or ML
  workloads. Don't use for simple queries, non-agentic pipelines, general cloud
  reviews, or writing agent code.
---

# Data science workflow with AI agents solution

This skill guides agents through the workflow to design and implement a
tailored multi-product solution in the cloud for a given workload, use case, or
requirement.

## Workflow

The solution design and implementation workflow consists of the following
phases:

- **Phase 1: Requirements discovery and analysis**: Analyze the workload's
  requirements, constraints, dependencies, and current state.
- **Phase 2: Solution design**: Build a technology stack, architecture, and
  deployment configuration for the workload based on Google Cloud design best
  practices and recommendations.
- **Phase 3: Implementation plan**: Generate automation and instructions to
  deploy the solution.
- **Phase 4: Solution validation**: Validate that the deployment meets the
  requirements of the workload.

## Product Renaming & Terminology

When generating solution designs, architecture diagrams, and documentation,
check the latest Google Cloud documentation for the most up-to-date product
names. The table below provides examples of name mappings to be aware of. Note
that underlying APIs, Terraform resources, and IAM roles may retain their legacy
identifiers.

| Legacy Name | Updated Name |
| :--- | :--- |
| Vertex AI | Gemini Enterprise Agent Platform |
| Vertex AI Agent Engine | Gemini Enterprise Agent Runtime |

### Phase 1: Requirements discovery and analysis

- [ ] **Step 1: Discover requirements**: Understand the functional and
  non-functional requirements, business goals, and current state (if any) of the
  workload by asking clarifying questions. You must halt and wait for the user
  to answer these questions before proceeding to the **Identify components**
  step. Use the following questions to guide this requirements discovery
  process:
   - What data sources and data types do you need to access and analyze?
   - Who are the target end users, and what network access model do you require?
   - What types of user queries or analytical requests do you expect end users
     to submit to the system?
   - What performance, security, or governance constraints apply?

- [ ] **Step 2: Identify components**: Only after the user has responded to the
  clarifying questions in the **Discover requirements** step, analyze their
  responses to identify the components of the workload and their relationships.
  Also identify any cross-cloud, hybrid, or on-premises components that the
  solution needs to integrate with.

- [ ] **Step 3: Generate component decomposition**: Generate a technical
  decomposition outlining the technical components of the workload and their
  relationships.

- [ ] **Step 4: Ask for confirmation**: Present the technical decomposition and
  ask the user to confirm if it matches their workload requirements. Do not
  proceed to Phase 2 until this is confirmed.

- [ ] **Step 5: Iterate**: If the user requests changes, generate an updated
   technical decomposition and ask for confirmation again. Continue iterating
   until the user explicitly confirms the decomposition.

### Phase 2: Solution design

- [ ] **Step 1: Retrieve relevant Google Cloud documentation**: Use available
  search or fetch tools to read the content of the following Google Cloud
  documentation to ground the guidance that you generate in the remaining steps
  of this phase before proceeding.
   - [Data science workflow with AI agents](https://docs.cloud.google.com/architecture/agentic-ai-data-science.md.txt)
   - [Multi-agent AI system in Google Cloud](https://docs.cloud.google.com/architecture/multiagent-ai-system.md.txt)
   - [Choose your agentic AI architecture components](https://docs.cloud.google.com/architecture/choose-agentic-ai-architecture-components.md.txt)
   - [Choose a design pattern for your agentic AI system](https://docs.cloud.google.com/architecture/choose-design-pattern-agentic-ai-system.md.txt)

- [ ] **Step 2: Define agentic AI design pattern**: Select the appropriate agent
  design pattern and agent breakdown based on the workload requirements:
   - **Recommended primary pattern**: Coordinator pattern.
   - **Alternative patterns**:
     - *Single-agent pattern*: For simpler workloads scoped to a single data
       source and direct tool use without multi-agent orchestration overhead.
     - *Sequential or parallel pattern*: For deterministic data processing
       pipelines with predefined, non-adaptive execution steps or concurrent
       data gathering.
     - *Review and critique pattern*: For complex or high-stakes data science
       tasks that require dedicated critic loops.

- [ ] **Step 3: Map components to Google Cloud products**: For each component in
  the confirmed technical decomposition and agentic design pattern, identify the
  appropriate Google Cloud products and features, based on the guidelines in
  /references/product-mapping.md.

- [ ] **Step 4: Create architecture diagram**: Create an architecture diagram
  that shows the components, their relationships, and data/control flows.
   - The diagram must be in the Mermaid format:
     https://github.com/mermaid-js/mermaid.
   - The diagram must use component labels and groupings consistent with the
     official Google Cloud architecture icons.

- [ ] **Step 5: Generate design recommendations**: Generate design guidance
  based on the guidelines in /references/design-recommendations.md.

- [ ] **Step 6: Draft solution architecture**: Compile the requirements,
  technical decomposition, product mapping, architecture diagram, and design
   recommendations into a single Markdown file named
   `solution-architecture-guide.md`, based on the template in
   `/assets/output-template.md`.

- [ ] **Step 7: Request review**: Present the generated solution architecture to
  the user and request their feedback or approval. You must halt and wait for
  the user's explicit approval before proceeding to Phase 3.

- [ ] **Step 8: Iterate**: If the user requests changes, then generate an
  updated solution architecture and repeat steps 2-7 in this phase until the
  user explicitly approves the solution architecture.

### Phase 3: Implementation plan

- [ ] **Step 1: Retrieve relevant implementation resources**:
   - [ADK Data Science Sample Code](https://github.com/google/adk-samples/tree/main/python/agents/data-science)
   - [Stateful Data Science Agent on Agent Engine](https://codelabs.developers.google.com/next26/adk-deploy-scale)
   - [Build and deploy an AI agent to Cloud Run using ADK](https://docs.cloud.google.com/run/docs/ai/build-and-deploy-ai-agents/deploy-adk-agent.md.txt)
   - [Use AlloyDB with agents](https://docs.cloud.google.com/alloydb/docs/connect-ide-using-mcp-toolbox.md.txt)
   - [MCP Toolbox for Databases Configuration](https://mcp-toolbox.dev/documentation/configuration/)

   _Important_: Use these resources as the technical foundation for the IaC and
   deployment instructions you generate in the remaining steps of this phase.

- [ ] **Step 2: Identify deployment prerequisites**: Document prerequisites for
  the deployment, including the following:
   - Projects and billing associations
   - Required Google Cloud APIs
   - Required IAM permissions
   - Any other prerequisites

- [ ] **Step 3: Generate Infrastructure as Code (IaC)**: Generate code, such as
  Terraform, and deployment scripts to automate the provisioning of the proposed
  Google Cloud resources.

- [ ] **Step 4: Write deployment instructions**: Draft sequential, step-by-step
  deployment instructions to execute the IaC and initialize the workload
  components. Update deployment instructions in
  `solution-architecture-guide.md`, based on the template in
  `assets/output-template.md`.

- [ ] **Step 5: Request review**: Present the generated deployment instructions
  to the user for feedback and confirmation. You must halt and wait for the
  user's explicit approval before proceeding to Phase 4.

- [ ] **Step 6: Iterate**: If the user requests changes, then repeat steps 2-5
  to generate an updated implementation plan that the user requested.

- [ ] **Step 7: Proceed to the next phase**: After the user approves the
  implementation plan, proceed to Phase 4.

### Phase 4: Solution validation

- [ ] **Step 1: Retrieve relevant verification resources (optional)**: If the
  resources from Phase 3 are not already in your context, retrieve the same
  implementation resources as the starting point for the
  validation checks and verification scripts that you generate in this phase.

- [ ] **Step 2: Define validation checks**: Outline validation steps to verify
  that the deployed infrastructure meets the workload's requirements:
   - **Deployment dry-run**: Commands like `terraform plan` to preview changes.
   - **Connectivity and routing**: Verification of network paths, load balancer
     routing, and service endpoints.
   - **Security policies**: Verification of restricted access, firewall rules,
     and IAM enforcement.

- [ ] **Step 3: Generate verification scripts**: Draft lightweight scripts or
  command-line instructions (e.g. using `curl` or `gcloud`) that the user can
  run to perform these validation checks.

- [ ] **Step 4: Compile validation report**: Document the validation steps,
  verification scripts, and expected outcomes in a single Markdown file.

- [ ] **Step 5: Conduct validation and finalize**: Assist the user in executing
  the validation checks and troubleshooting any deployment issues. After you
  validate the solution successfully, request final approval from the user.

- [ ] **Step 6: Iterate**: If the user requests changes, then generate an
  updated validation plan and repeat the validation drafting and script
  generation steps in this phase until the user approves the validation plan.
