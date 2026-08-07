# Product Mapping Guidance

Explain to the user that the solution consists of two subsystems:

- The **data ingestion subsystem** ingests data from external sources and uses a
  central lakehouse to unify and process fragmented databases into a unified
  data profile in Google Cloud.
- The **serving subsystem** lets users query an AI assistant and a data analysis
  agent to analyze the consolidated data.

For each component in the confirmed technical decomposition, identify the
appropriate Google Cloud products and features, based on the following guidance:

- **Data ingestion subsystem components**:
  - **Central metadata and governance**:
    - **Recommended primary product**: Lakehouse for Apache Iceberg
    - **Alternative product 1**: Dataproc Metastore
      - **Pros**: Better for legacy open-source heavy pipelines.
      - **Cons**: Can have lower performance for borderless federation and
        Apache Iceberg.
  - **Processing engine**:
    - **Recommended primary product**: Managed Service for Apache Spark with
      Lightning Engine
    - **Alternative product 1**: BigQuery
      - **Pros**: Allows querying data in place on external clouds using
        standard SQL, reducing data movement.
      - **Cons**: Less flexible than Spark for highly complex, programmatic
        transformations or custom code.
    - **Alternative product 2**: Dataflow
      - **Pros**: Powerful for complex, unified batch or stream ETL.
      - **Cons**: Requires learning the Apache Beam programming model and
        managing a Cloud Storage bucket for job error logs.
  - **Internal data storage**:
    - **Recommended primary product**: Cloud Storage using Apache Iceberg format
      or Apache Parquet format.
    - **Alternative product 1**: BigQuery storage
      - **Pros**: Provides high performance for native BigQuery queries.
      - **Cons**: Less portable for other open-source processing engines
        compared to open formats on Cloud Storage.
    - **Alternative product 2**: Cloud Storage
      - **Pros**: Eliminates borderless egress fees and latency if you choose to
        consolidate your workload to a single cloud.
  - **Security**:
    - **Recommended primary product**: Use Secret Manager to securely hold
      authentication credentials for federated REST catalogs. Manage direct
      storage object access using BigQuery Cloud Resource connections and
      runtime credential vending.
    - **Alternative product 1**: Cloud Key Management Service (KMS)
      - **Pros**: Provides hardware-backed key management for encryption.
      - **Cons**: Not designed to store plain-text secrets like API tokens.
  - **Borderless networking**:
    - **Recommended primary product**: Cross-Cloud Interconnect
    - **Alternative product 1**: Cloud VPN (HA VPN)
      - **Pros**: Offers lower costs during low-traffic periods.
      - **Cons**: Can have higher latency and lower bandwidth compared to
        dedicated Cross-Cloud Interconnect.
- **Serving subsystem components**:
  - **AI serving and agentic workflows**:
    - **Recommended primary product**: BigQuery data agent with Antigravity CLI
    - **Alternative product 1**: Gemini Enterprise Agent Platform
      - **Pros**: Provides built-in orchestration, native enterprise grounding,
        and managed chat UIs.
      - **Cons**: Offers less granular control over the prompt loop, and can be
        more expensive than a lightweight MCP server.
    - **Alternative product 2**: Google Cloud Data Agent Kit
      - **Pros**: Optimized for data practitioners, data engineers, and data
        scientists to manage the data lifecycle and perform interactive analysis
        directly within their IDE.
      - **Cons**: Designed for developer-centric workflows rather than serving
        production end-to-end business applications.
