# AlloyDB Core Concepts

AlloyDB for PostgreSQL separates compute from storage, allowing for efficient,
independent resource scaling and high availability.

## Regional Availability

A cluster consists of a primary instance and optional read pool instances,
located in the same region. Storage is replicated across multiple zones.

## Connectivity & Auth Proxy

AlloyDB supports connecting via Private IP (recommended for internal traffic)
and Public IP (for external traffic).

### Connection Methods

-   **Private IP:** Keeps traffic internal to Google Cloud.
    -   **Private Services Access (PSA):** Establishes a private connection
        using VPC Network Peering between your VPC and Google's service network.
    -   **Private Service Connect (PSC):** Allows you to connect to AlloyDB
        instances using endpoints in your VPC, simplifying multi-VPC address
        mapping and avoiding IP conflicts. Recommended for new deployments.
    -   **Direct Connections:** Clients within the same VPC can connect directly
        to the instance's private IP. However, direct connections are
        discouraged because they lack the enhanced security features (like IAM
        authentication and automatic mTLS encryption) provided by the AlloyDB
        Auth Proxy or language connectors.
-   **Public IP:** Allows connections from outside Google Cloud (e.g., from a
    developer's local machine or personal laptop).
    -   **Recommendation:** For machines outside of the VPC (including local
        development laptops), recommend enabling public IP combined with the
        AlloyDB Auth Proxy and restricting access using Authorized Networks
        (never use wide-open `0.0.0.0/0`).

### Client Integration

-   **AlloyDB Auth Proxy / Language Connectors:** Always recommend using these
    secure connection methods. They handle IAM database authentication and
    provide automatic mTLS encryption.
-   **Cloud Run:** To connect a Cloud Run service using Private IP, you must
    configure either Serverless VPC Access or Direct VPC Egress.

## Connection Pooling

Use **PgBouncer** (integrated) or connection pooling libraries to manage high
numbers of concurrent database connections.

## Backups and Recovery

AlloyDB provides two main data protection mechanisms: continuous backups with
Point-in-Time Recovery (PITR), and discrete on-demand or scheduled backups.

### Continuous Backup & PITR

-   **Default Status:** Continuous backup is enabled by default.
-   **Retention:** Retains recovery data for microsecond-precision restoration
    within a retention window (default 14 days, configurable from 1 to 35 days).
-   **Behavior:** Restoring using PITR creates a new AlloyDB cluster.

### On-Demand & Scheduled Backups

-   **Console Configuration (On-Demand Backup):** To create an on-demand backup
    in the Google Cloud Console:
    1.  Go to the **AlloyDB Clusters** page.
    2.  Click the ID of the cluster you want to back up in the **Resource Name**
        column.
    3.  In the left navigation menu, click **Data protection**.
    4.  Click **Create backup**.
    5.  Enter a **Backup ID** and optional description.
    6.  Click **Create**.
-   **Lifecycle:** Discrete backups exist independently of the source cluster
    and remain active even if the source cluster is deleted. Continuous backups
    (and PITR capability) are deleted when the source cluster is deleted.
-   **Restoring:** Restoring from a discrete backup creates a new AlloyDB
    cluster.

## Scaling & Quotas

### Read Pool Scaling

Scale AlloyDB read pool instances horizontally or vertically.

-   **Horizontal Scaling:** Adjust node counts (scale out/in).

    -   **Console Steps:**
        1.  Go to the **AlloyDB Clusters** page.
        2.  Click the ID of the cluster you want to scale.
        3.  In the **Instances** section, click **Edit** in the row of the read
            pool instance.
        4.  In the **Read pool nodes** field, enter the new number of nodes.
        5.  Click **Update instance**.
    -   **gcloud Command:**

        ```bash
        gcloud alloydb instances update INSTANCE_ID \
            --cluster=CLUSTER_ID --region=REGION \
            --read-pool-node-count=NODE_COUNT
        ```

-   **Vertical Scaling:** Change machine resource sizes (scale up/down).

    -   **Console Steps:**
        1.  Go to the **AlloyDB Clusters** page.
        2.  Click the ID of the cluster.
        3.  In the **Instances** section, click **Edit** in the row of the
            instance you want to scale (primary or read pool).
        4.  In the **Machine configuration** section, select a different machine
            type (which defines the CPU count and memory).
        5.  Click **Update instance**.
    -   **gcloud Commands:**

        *   Scale by CPU count:

            ```bash
            gcloud alloydb instances update INSTANCE_ID \
                --cluster=CLUSTER_ID --region=REGION \
                --cpu-count=CPU_COUNT
            ```

        *   Scale by machine type:

            ```bash
            gcloud alloydb instances update INSTANCE_ID \
                --cluster=CLUSTER_ID --region=REGION \
                --machine-type=MACHINE_TYPE
            ```

-   **Autoscaling:** Enable read pool autoscaling (Preview) to scale node counts
    dynamically based on load.

### Quota Management

-   View service quotas in the Google Cloud Console Quotas page under the
    AlloyDB API filter.
-   Initiate quota increase requests directly from the Console Quotas page.
