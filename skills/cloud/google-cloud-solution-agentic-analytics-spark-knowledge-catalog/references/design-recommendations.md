# Design recommendations

Use the following guidance to generate design recommendations for a governed,
secure pipeline for agentic analytics solution across structured and
unstructured data that's distributed across Google Cloud, on-premises systems,
and other cloud providers.

*   **Security, privacy, and compliance**:
    *   Assign the required roles and permissions.
    *   Configure token federation or Secret Manager credentials to allow Spark
        REST catalogs to authenticate with remote AWS S3 / Azure storage.
    *   Establish the required aspect types and business glossaries to classify
        table sensitivities (e.g., private vs public) and map business metrics.
    *   Use Knowledge Catalog lineage tracking to identify PII data leakage
        paths across database conversions.
*   **Reliability**:
    *   Configure Cross-Cloud Interconnect with redundant links in separate
        domains to prevent network drops during massive queries.
*   **Operational excellence**:
    *   Organize Spark sessions by deploying reusable session templates
        (`template.yaml`) in Managed Service for Apache Spark.
    *   Track data lineage in Knowledge Catalog to perform impact analysis on
        upstream schema breaks.
*   **Cost optimization**:
    *   Run zero-copy Spark REST catalog queries to AWS S3 instead of
        transferring files over public endpoints, eliminating network egress
        fees.
    *   Use Knowledge Catalog lineage cost-optimization tools to find and prune
        orphaned tables.
*   **Performance efficiency**:
    *   Enable Lightning Engine with native runtime
        (`spark.dataproc.lightningEngine.runtime=native`) and set the compute
        tier to premium (`dataproc.tier=premium`) inside the Spark session
        templates.
    *   Configure off-heap memory settings (`spark.memory.offHeap.size=1g`) to
        boost vector operations.
    *   To minimize geographic latency, select Google Cloud regions that let you
        co-locate Google Cloud resources alongside AWS/Azure datacenters where
        S3 buckets reside.
*   **Sustainability**:
    *   Run Managed Service for Apache Spark Serverless with Lightning Engine to
        perform operations in memory, reducing server compute waste.
    *   Use zero-copy architecture (BigQuery Omni/Spark REST catalogs) to
        prevent storing duplicate multi-petabyte datasets.
