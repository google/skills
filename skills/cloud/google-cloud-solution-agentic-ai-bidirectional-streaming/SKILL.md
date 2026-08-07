---
name: google-cloud-solution-agentic-ai-bidirectional-streaming
metadata:
  category: MultiProductSolutions
description: >-
  Guides agents to interactively discover customer requirements
  for live, bidirectional multi-agent AI systems that process continuous streams
  of multimodal data for real-time technical guidance and safety monitoring.
  Generates a custom Google Cloud solution that uses opinionated best practices
  and architecture guidance. Use when users need agentic assistance to design
  and create a multi-product solution in the cloud for live bidirectional
  multimodal streaming workloads. Don't use for simple text-based chat
  applications or workloads without real-time streaming requirements.
---

# Live bidirectional multimodal streaming agentic AI solution

This skill guides agents through the workflow to design and implement a
tailored multi-product solution in the cloud for a live, bidirectional
multimodal streaming workload, use case, or requirement.

## Workflow

The solution design and implementation workflow consists of the following
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

### Phase 1: Requirements discovery and analysis

- [ ] **Step 1: Discover requirements**: Understand the functional and
  non-functional requirements, business goals, and current state (if any) of the
  workload, including its architecture, dependencies, and constraints. Use the
  following questions to guide the requirements discovery process:
   - What are the primary input modalities (audio, video, or text) and
     what is the target latency for real-time, narrated feedback?
   - Do you require real-time safety monitoring, hazard detection, or visual
     inspection? If so, then what specific safety hazards, operational risks,
     or incorrect steps need to be monitored and detected in the video
     stream?
   - What existing systems, knowledge bases, product documentation, or
     schematic repositories must the AI agents access for grounded guidance?
   - What are the client-side device constraints and network limitations?

- [ ] **Step 2: Identify components**: Based on the requirements analysis,
  identify the components of the workload and their relationships. Also identify
  any cross-cloud components, hybrid components, or on-prem components that the
  solution needs to integrate with.

- [ ] **Step 3: Generate component decomposition**: Generate a technical
  decomposition of the components of the workload. The technical decomposition
  must break down the solution into logical components.

- [ ] **Step 4: Ask for confirmation**: Ask the user to confirm whether the
  generated technical decomposition matches their workload requirements.

- [ ] **Step 5: Iterate**: If the user requests changes, then generate an
  updated technical decomposition, and ask the user to confirm the changes.
  Continue iterating until the user confirms the technical decomposition.

### Phase 2: Solution design

- [ ] **Step 1: Retrieve relevant Google Cloud documentation**:
   - [Enable live bidirectional multimodal streaming](https://docs.cloud.google.com/architecture/agentic-ai-bidirectional-multimodal-streaming.md.txt)
   - [Multi-agent AI system in Google Cloud](https://docs.cloud.google.com/architecture/multiagent-ai-system.md.txt)
   - [Choose your agentic AI architecture components](https://docs.cloud.google.com/architecture/choose-agentic-ai-architecture-components.md.txt)
   - [Multi-agent private networking patterns in Google Cloud](https://docs.cloud.google.com/architecture/multi-agent-private-networking-patterns.md.txt)

   *Important*: Use the content that you retrieve from Google Cloud
   documentation to ground the guidance that you generate in the remaining
   steps of this phase.

- [ ] **Step 2: Map components to Google Cloud products**: For each component in
  the confirmed technical decomposition and agentic design pattern, identify the
  appropriate Google Cloud products and features, based on the guidelines in
  [references/product-mapping.md](references/product-mapping.md).

- [ ] **Step 3: Create architecture diagram**: Generate an architecture diagram
  in Mermaid format: https://github.com/mermaid-js/mermaid.

- [ ] **Step 4: Generate design recommendations**: Generate design guidance
  based on the guidelines in [references/design-recommendations.md](references/design-recommendations.md).

- [ ] **Step 5: Draft solution architecture**: Compile the requirements, technical
  decomposition, product mapping, architecture diagram, and design
  recommendations into a single Markdown file named
  `solution-architecture-guide.md`, based on the template in
  [assets/output-template.md](assets/output-template.md).

- [ ] **Step 6: Request review**: Present the generated solution architecture to
  the user and request their feedback or approval.

- [ ] **Step 7: Iterate**: If the user requests changes, generate an updated
  solution architecture and repeat steps 2-6 until the user approves the
  solution architecture.

### Phase 3: Implementation plan

- [ ] **Step 1: Retrieve relevant implementation resources**:
   - [Host AI agents on Cloud Run](https://docs.cloud.google.com/run/docs/ai-agents.md.txt)
   - [Triggering Cloud Run with WebSockets](https://docs.cloud.google.com/run/docs/triggering/websockets.md.txt)
   - [Start and Manage a Gemini Live API Session](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api/start-manage-session.md.txt)
   - [ADK Streaming Tools](https://adk.dev/streaming/streaming-tools/)
   - [ADK Streaming Configuration](https://adk.dev/streaming/configuration/)
   - [Codelab: Way Back Home Level 4 instructions](https://codelabs.developers.google.com/way-back-home-level-4/instructions#0)
     (and
     [solution code](https://github.com/gca-americas/way-back-home/tree/main/level_4))

   *Important*: Use these resources as the technical foundation for the IaC and
   deployment instructions you generate in the remaining steps of this phase.

- [ ] **Step 2: Identify deployment prerequisites**: Document prerequisites for
  the deployment, including the following:
   - Projects and billing associations
   - Required Google Cloud APIs
   - Required IAM permissions
   - Any other prerequisites

- [ ] **Step 3: Generate Infrastructure as Code (IaC)**: Generate code, like
  Terraform, and deployment scripts to automate the provisioning of the proposed
  Google Cloud resources.

- [ ] **Step 4: Write deployment instructions**: Draft sequential, step-by-step
  deployment instructions to execute the IaC and initialize the workload
  components. Update deployment instructions in
  `solution-architecture-guide.md`, based on the template in
  [assets/output-template.md](assets/output-template.md).

- [ ] **Step 5: Request review**: Present the generated deployment instructions
  to the user for feedback and confirmation.

- [ ] **Step 6: Iterate**: If the user requests changes, then generate an
  updated implementation plan and repeat steps 2-5 until the user approves the
  implementation plan.

### Phase 4: Solution validation

- [ ] **Step 1: Retrieve relevant verification resources (optional)**: If the
  resources from Phase 3 are not already in your context, retrieve the same
  implementation resources as the starting point for the
  validation checks and verification scripts that you generate in this phase.

- [ ] **Step 2: Define validation checks**: Outline validation steps to verify
  that the deployed infrastructure meets the workload requirements:
   - **Deployment dry-run**: Commands like `terraform plan` to preview
     changes.
   - **Connectivity and routing**: Verification of network paths, load
     balancer routing, and service endpoints.
   - **Security policies**: Verification of restricted access, firewall
     rules, and IAM enforcement.

- [ ] **Step 3: Generate verification scripts**: Draft lightweight scripts or
  command-line instructions, such as using `curl` or `gcloud`, that the user can
  run to perform these validation checks.

- [ ] **Step 4: Compile validation report**: Document the validation steps,
  verification scripts, and expected outcomes in
  `solution-architecture-guide.md`, based on the template in
  [assets/output-template.md](assets/output-template.md).

- [ ] **Step 5: Conduct validation and finalize**: Assist the user in executing
  the validation checks and troubleshooting any deployment issues. After the
  solution is validated successfully, request final approval from the user.

- [ ] **Step 6: Iterate**: If the user requests changes, then generate an
  updated validation plan and repeat steps 2-5 until the user approves the
  validation plan.
