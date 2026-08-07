<!-- Use this template to compile the content that you generate based on the
instructions in `SKILL.md`. -->

# Google Cloud solution architecture: RAG for enterprise search using GKE and AlloyDB

## 1. Executive summary and workload overview

[A brief description of the conversational search workload, the business goals
of the enterprise search system, and the proposed high-level RAG solution
architecture combining GKE orchestration with AlloyDB vector search]

## 2. Requirements and current state

### 2.1. Functional requirements

*   **Business processes**: [Details of the enterprise documents and
    conversational search processes that the workload supports]
*   **Activities and use cases**: [Details of user interactions and task/data
    flows: e.g., query rates, chunking/embedding batch ingestion schedules, and
    retrieval needs]

### 2.2. Non-functional requirements

*   **Security**: [Details of security requirements: e.g., identity and access
    control, network isolation, private endpoints, data residency, and any
    compliance requirements.]
*   **Reliability**: [Details of reliability requirements: e.g., resource
    scaling, HA, multi-zone vs. regional, SLA]
*   **Cost**: [Details of cost constraints]
*   **Operations**: [Details of operational requirements: e.g., logging,
    monitoring]
*   **Performance**: [Details of performance requirements: e.g., search
    latencies, content generation speed]
*   **Sustainability**: [Details of resource utilization and carbon footprints]

### 2.3. Current state

[If applicable, describe the current on-premises or other-cloud solution.]

*   **Current solution**: [Details of existing indexes or databases]
*   **Pain points and drivers for migration/redesign**: [Details about why the
    existing solution is not optimal]

### 2.4. Dependencies

*   **Internal dependencies**: [Details of internal dependencies: e.g., ERP,
    CRM, or identity directories]
*   **External dependencies**: [Details of external connections: e.g., public
    datasets, SaaS platforms]

## 3. Technical decomposition of the workload

[Technical decomposition of the workload components, breaking down the
application into logical layers: data ingestion, data preprocessing & chunking,
embedding generation, creating/updating the vector index, context retrieval,
prompt augmentation, and response generation.]

## 4. Proposed solution architecture

### 4.1. Google Cloud products and features mapping

[List the Google Cloud products and features mapped to the technical components
of the workload. For each component, justify the selection, note alternatives
considered, and describe the pros and cons of the recommended product/feature.]

### 4.2. Architecture diagram

[Architecture diagram in the Mermaid format showing the relationships and data
flows between the components.]

### 4.3. Architecture description

[Detailed description of the architecture. Describe the task flow and data flow
between the components.]

*   **Embedding flow**: [E.g., document ingestion, FUSE mounting, chunking logic
    in Ray, vectorization, and SQL inserting.]
*   **Serving flow**: [E.g., prompt submission, database lookup, prompt
    augmentation, calling Gemma vLLM endpoint API, and safety filtering.]

## 5. Design and configuration recommendations

### 5.1. Security, privacy, and compliance

*   **Access control**: [E.g., IAM-based authentication]
*   **Data protection**: [E.g., Cloud KMS CMEK, Sensitive Data Protection
    scanning of ingestion documents]
*   **Network security**: [E.g., Private IP only for AlloyDB and GKE, Private
    Service Connect (PSC), VPC Service Controls perimeters]

### 5.2. Reliability

*   **Redundant deployment**: [E.g., Regional GKE cluster across three zones,
    AlloyDB HA instance]
*   **Backup and disaster recovery**: [E.g., AlloyDB backup and recovery, GKE
    image streaming to avoid cold starts]

### 5.3. Operational excellence

*   **Monitoring and logging**: [E.g., Cloud Logging, Cloud Monitoring, System
    Insights, Query Insights]
*   **Infrastructure as Code (IaC)**: [E.g., Terraform for infra provisioning]

### 5.4. Cost optimization

*   **Sizing and scaling**: [E.g., GKE Autopilot scaling, Spot VMs for Ray
    workers, Object Lifecycle Management on Storage]
*   **Pricing models**: [E.g., Committed Use Discounts (CUD) for AlloyDB and GKE
    compute]

### 5.5. Performance efficiency

*   **Caching and database indexing**: [E.g., HNSW index strategy for fast ANN
    searches, performance tracking using Query Insights]
*   **Data updates**: [E.g., Parallel composite uploads to Cloud Storage]

### 5.6. Sustainability

*   [E.g., Serverless API offloading, GKE right-sizing node utilization]

## 6. Deployment guidance

[Instructions and code for deploying the RAG architecture.]

### 6.1. Deployment prerequisites

*   [E.g., Enabled APIs: container.googleapis.com, sqladmin.googleapis.com,
    secretmanager.googleapis.com, aiplatform.googleapis.com]
*   [E.g., Tools: Google Cloud CLI, Terraform, kubectl, helm]

### 6.2. Step-by-step deployment instructions

1.  [E.g., Terraform init and apply for infra setup]
2.  [E.g., Install KubeRay operator on GKE and submit chunking job]
3.  [E.g., Connect to Postgres, verify pgvector extension, test query flow]

## 7. Validation plan

[Details of the steps to verify that the generated solution meets the workload's
requirements. Also include references to any validation scripts that were
generated.]

## 8. References

[Links to useful and authoritative resources, such as relevant Google Cloud
documentation pages.]
