---
name: google-cloud-solution-agentic-ai-borderless-data-lakehouse
metadata:
  category: MultiProductSolutions
description: >-
  Guides agents to discover requirements and design a governed,
  secure borderless open data lakehouse with agentic AI integration. Use when
  designing a multi-product architecture that connects data silos to AI agents,
  joining data across clouds, or running federated queries across Google Cloud
  and external data sources, including on-premises or other cloud providers.
  Don't use for simple single-cloud data warehouses or non-AI workloads.
---

# Borderless open data lakehouse agentic AI system

Follow this workflow to help users design and implement a custom multi-product
solution in the cloud for a given workload, use case, or requirement.

## Product Renaming & Terminology

When generating solution designs, architecture diagrams, and documentation, use
the updated Google Cloud product names. For details on legacy vs. updated
product names and terminology, see
[references/product_renaming.md](references/product_renaming.md).

## Workflow

The solution design and implementation workflow consists of the following
phases:

- **Phase 1: Requirements discovery and analysis**: Analyze the workload's
  requirements, constraints, dependencies, and current state.
- **Phase 2: Solution design**: Build a technology stack, architecture, and
  deployment configuration for the workload based on Google Cloud design best
  practices and recommendations.
- **Phase 3: Implementation plan**: Generate automation
  and instructions to deploy the solution.
- **Phase 4: Solution validation**: Validate that the deployment meets the
  requirements of the workload.

### Phase 1: Requirements discovery and analysis

- [ ] **Step 1: Discover requirements**: Understand the functional and
  non-functional requirements, business goals, and current state (if any) of the
  workload, including its architecture, dependencies, and constraints. Use the
  following questions to guide the requirements discovery process:
   - What are your primary data sources?
   - How do you manage and federate metadata across your data sources?
   - What are your security and credential management requirements?
   - What are the analytical and computational requirements to join and
     transform this borderless data?
   - What types of natural language prompts or user queries do you expect AI
     agents or end-users to execute against this data?

- [ ] **Step 2: Identify components**: Based on the requirements analysis,
  identify the components of the workload and their relationships. Also identify
  any borderless components, hybrid components, or on-prem components that the
  solution needs to integrate with.

- [ ] **Step 3: Generate component decomposition**: Generate a technical
  decomposition of the components of the workload.

- [ ] **Step 4: Ask for confirmation**: Ask the user to confirm whether the
  generated technical decomposition matches their workload requirements.

- [ ] **Step 5: Iterate**: If the user requests changes, then generate an
  updated technical decomposition, and ask the user to confirm the changes.
  Continue iterating until the user confirms the technical decomposition.

### Phase 2: Solution design

- [ ] **Step 1: Retrieve relevant Google Cloud documentation**: Use available
  search or fetch tools to read the content of the following Google Cloud
  documentation to ground the guidance that you generate in the remaining
  steps of this phase before proceeding.
   - [Build hybrid and borderless architectures using Google Cloud](https://docs.cloud.google.com/architecture/hybrid-multicloud-patterns/one-page-view.md.txt)
   - [Build a borderless open data lakehouse](https://docs.cloud.google.com/architecture/agentic-ai-build-multicloud-open-data-lakehouse.md.txt)
   - [Implement agentic analytics workflows for distributed data](https://docs.cloud.google.com/architecture/agentic-ai-cross-cloud-analytics.md.txt)
   - [Analytics Hybrid and Multicloud Pattern](https://docs.cloud.google.com/architecture/hybrid-multicloud-patterns-and-practices/analytics-hybrid-multicloud-pattern.md.txt)
   - [Google Cloud multi-regional deployment archetype](https://docs.cloud.google.com/architecture/deployment-archetypes/multiregional.md.txt)
   - [Network segmentation and connectivity for distributed applications in Cross-Cloud Network](https://docs.cloud.google.com/architecture/ccn-distributed-apps-design/connectivity.md.txt)
   - [Patterns for Connecting Other Cloud Service Providers with Google Cloud](https://docs.cloud.google.com/architecture/patterns-for-connecting-other-csps-with-gcp.md.txt)

  *Important*: Use the content that you retrieve from Google Cloud
   documentation to ground the guidance that you generate in the remaining
   steps of this phase.

- [ ] **Step 2: Map components to Google Cloud products**: For each component in
  the confirmed technical decomposition, identify the appropriate Google Cloud
  products and features, based on the guidelines in
  [references/product_mapping.md](references/product_mapping.md).

- [ ] **Step 3: Create architecture diagram**: Create an architecture diagram
  that shows the components, their relationships, and data/control flows.
   - The diagram must be in the Mermaid format:
     https://github.com/mermaid-js/mermaid.
   - The diagram must show a clear distinction between the products in the
     data ingestion subsystem and the serving subsystem.
   - The diagram must show Managed Service for Apache Spark as a shared
     component, bridging the data ingestion and serving subsystems.

- [ ] **Step 4: Generate design recommendations**: Generate design guidance
  based on the guidelines in
  [references/design_recommendations.md](references/design_recommendations.md).

- [ ] **Step 5: Draft solution architecture**: Compile the requirements,
  technical decomposition, product mapping, architecture diagram, and design
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
   - [Build a Multicloud Open Data Lakehouse with Agentic AI](https://codelabs.developers.google.com/next26/multicloud-lakehouse)
   - [Terraform Registry documentation for biglake_iceberg_catalog](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/biglake_iceberg_catalog)
   - [Create an Apache Iceberg table with metadata in Lakehouse runtime catalog](https://docs.cloud.google.com/managed-spark/docs/guides/spark-workloads-with-bigquery-metastore.md.txt)
   - [Accelerate Spark batch workloads and sessions with Lightning Engine](https://docs.cloud.google.com/managed-spark/docs/guides/lightning-engine-serverless.md.txt)
   - [Create data agents](https://docs.cloud.google.com/bigquery/docs/create-data-agents.md.txt)

   *Important*: Use these resources as the technical foundation for the IaC and
   deployment instructions you generate in the remaining steps of this phase.

- [ ] **Step 2: Identify deployment prerequisites**: Document prerequisites for
  the deployment, including the following:
   - Projects and billing associations
   - Required Google Cloud APIs
   - Required IAM permissions
   - Any other prerequisites

- [ ] **Step 3: Generate Infrastructure as Code (IaC)**: Generate code (e.g.,
  Terraform) and deployment scripts to automate the provisioning of the proposed
  Google Cloud resources.

- [ ] **Step 4: Write deployment instructions**: Draft sequential, step-by-step
  deployment instructions to execute the IaC and initialize the workload
  components.

- [ ] **Step 5: Request review**: Present the generated deployment instructions
  to the user for feedback and confirmation.

- [ ] **Step 6: Iterate**: If the user requests changes, generate an updated
  implementation plan and repeat steps 2-5 until the user approves the
  implementation plan.

### Phase 4: Solution validation

- [ ] **Step 1: Retrieve relevant verification resources (optional)**: If the
  resources from Phase 3 are not already in your context, retrieve the same
  implementation resources as the starting point for the validation checks
  and verification scripts that you generate in this phase.

- [ ] **Step 2: Define validation checks**: Outline validation steps to verify
  that the deployed infrastructure meets the workload requirements:
   - **Deployment dry-run**: Commands like `terraform plan` to preview
     changes.
   - **Connectivity and routing**: Verification of network paths, load
     balancer routing, and service endpoints.
   - **Security policies**: Verification of restricted access, firewall
     rules, and IAM enforcement.

- [ ] **Step 3: Generate verification scripts**: Draft lightweight scripts or
  command-line instructions (e.g. using `curl` or `gcloud`) that the user can
  run to perform these validation checks.

- [ ] **Step 4: Compile validation report**: Document the validation steps,
  verification scripts, and expected outcomes in a single Markdown file.

- [ ] **Step 5: Conduct validation and finalize**: Assist the user in executing
  the validation checks and troubleshooting any deployment issues. After the
  solution is validated successfully, request final approval from the user.

- [ ] **Step 6: Iterate**: If the user requests changes, then generate an
  updated validation plan and repeat steps 2-5 until the user approves the
  validation plan.
