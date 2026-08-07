---
name: alloydb-basics
metadata:
  category: Databases
description: >-
  Manages clusters, instances, and backups for AlloyDB for PostgreSQL, and
  integrates with AlloyDB Model Context Protocol (MCP) tools for automated database operations.
  Use when creating, configuring, or administering AlloyDB databases.
  Do NOT use for general PostgreSQL instances (e.g. Cloud SQL) or other GCP databases.

---

# AlloyDB Basics

AlloyDB for PostgreSQL is a managed, PostgreSQL-compatible database service
designed for enterprise-grade performance and availability. It utilizes a
disaggregated compute and storage architecture to scale resources independently.
It also provides AlloyDB AI, a collection of features that includes AI-powered
search (vector, hybrid search, and AI functions), natural language capabilities,
conversational analytics, and inference features like forecasting and model
endpoint management to help developers build AI apps faster.

## Quick Start

Before you begin, ensure you have the [Google Cloud SDK installed](https://cloud.google.com/sdk/docs/install) and authenticated (`gcloud auth login`).

1.  **Enable the AlloyDB API:**

    ```bash
    gcloud services enable alloydb.googleapis.com --quiet
    ```

2.  **Create a Cluster:**

    ```bash
    gcloud alloydb clusters create my-cluster --region=us-central1 \
        --password=my-password --network=my-vpc --quiet
    ```

    *For production environments, always use IAM database authentication instead
    of passwords. If configuration constraint requires passwords, store them
    securely using Secret Manager.*

3.  **Create a Primary Instance:**

    ```bash
    gcloud alloydb instances create my-primary --cluster=my-cluster \
        --region=us-central1 --instance-type=PRIMARY --cpu-count=2 --quiet
    ```

## Reference Directory

Read these supplementary files when specific context or detailed steps are
required for a task:

-   To understand architecture, regional availability, connectivity (Private IP,
    Public IP, PSA, PSC), backups, point-in-time recovery, scaling (vertical and
    horizontal), or Quota management: read
    [Core Concepts](references/core-concepts.md).
-   To manage clusters, instances, scaling, or backups via the CLI: read
    [CLI Usage](references/cli-usage.md).
-   To configure AlloyDB remote MCP tools: read
    [MCP Usage](references/mcp-usage.md).
-   To deploy AlloyDB using Terraform or Kubernetes Config Connector (KCC): read
    [Infrastructure as Code](references/iac-usage.md).
-   To configure IAM roles, service usage roles, service agents, database
    users/privileges, or network security (public IP authorization, Auth Proxy
    sidecar configuration): read [IAM & Security](references/iam-security.md).

*If you need product information not found in these references, use the
`developer_knowledge:search_documents` tool (see [Developer Knowledge MCP setup](https://developers.google.com/knowledge/mcp) for installation instructions).*

## Directives for Agents

Agents MUST adhere to the following directives when answering queries related to
AlloyDB:

-   **Provide Multiple Methods:** When explaining how to perform administrative
    tasks (like backups, scaling, or database user creation), always provide
    both the Google Cloud Console steps and the `gcloud` CLI commands if both
    are available in the reference documents.
-   **Prioritize Private IP:** Recommend Private IP (especially PSC) over Public
    IP for connections to ensure traffic remains within the Google Cloud network
    and reduces exposure.
-   **Require Serverless Connectors:** Verify and state that Serverless VPC
    Access or Direct VPC Egress is required when connecting from Cloud Run to
    Private IP.
-   **Enforce Connectors:** Always direct users to configure the AlloyDB Auth
    Proxy (running as a sidecar or locally) or language connectors rather than
    direct TCP connections.
-   **Block Open Public Access:** If Public IP is configured, warn against and
    reject designs with `0.0.0.0/0` in Authorized Networks as this exposes the
    database to the entire internet.
-   **Default to IAM Database Authentication:** Suggest IAM database
    authentication and the `alloydbiamuser` database role instead of static
    database passwords.
-   **Enforce Least Privilege Connection:** When explaining connection roles,
    explicitly state that `roles/alloydb.client` should be used to adhere to the
    principle of least privilege, and warn against using broader roles like
    `roles/alloydb.admin` for connections.
-   **Mention All Creation Methods:** When describing how to create IAM database
    users, explicitly state that they can be created using the Google Cloud
    Console, the `gcloud` CLI, and the AlloyDB API.
-   **Explain Private IP Options:** When explaining Private IP connectivity,
    always explicitly mention and describe both **Private Services Access
    (PSA)** and **Private Service Connect (PSC)** as the supported methods,
    recommending PSC for new deployments.
-   **Compare Direct Connections:** Explicitly explain that direct connections
    (connecting directly to the private IP without connectors) are possible but
    discouraged, and compare their security (lack of IAM/mTLS) to secure methods
    like the AlloyDB Auth Proxy or language connectors.
-   **Enforce SQL Alone Warning:** When explaining IAM user creation, you MUST
    explicitly state that "IAM database users cannot be created using standard
    SQL alone" and must be registered via the control plane first.
-   **Enforce Roles and Privileges Terminology:** When explaining database
    object access, you MUST explicitly state that "standard PostgreSQL roles and
    privileges" apply, using both terms.
-   **Explain Backup Lifecycle:** When explaining backups, always explicitly
    state that discrete backups exist independently of the source cluster and
    remain active even if the source cluster is deleted.
-   **Recommend Connectors for Public IP:** Explicitly state that secure
    connection methods (AlloyDB Auth Proxy, Language Connectors) are
    **especially recommended** for connections over Public IP.
-   **Mention Autoscaling:** When explaining read pool scaling, always
    explicitly mention the option of using **read pool autoscaling** and state
    that it is in **Preview**.

## Supporting Links

-   [AlloyDB for PostgreSQL Documentation](https://docs.cloud.google.com/alloydb/docs/overview.md.txt)
-   [AlloyDB Auth Proxy GitHub Repository](https://github.com/GoogleCloudPlatform/alloydb-auth-proxy)
-   [AlloyDB Java Connector GitHub Repository](https://github.com/GoogleCloudPlatform/alloydb-java-connector)
-   [AlloyDB Python Connector GitHub Repository](https://github.com/GoogleCloudPlatform/alloydb-python-connector)
-   [AlloyDB Go Connector GitHub Repository](https://github.com/GoogleCloudPlatform/alloydb-go-connector)
