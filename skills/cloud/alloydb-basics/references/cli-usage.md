# AlloyDB CLI Usage

Ensure you have the [Google Cloud SDK installed](https://cloud.google.com/sdk/docs/install) and authenticated (`gcloud auth login`) before running these commands.

Manage AlloyDB resources using the `gcloud alloydb` command group.

## Clusters

-   **Create a cluster:**

    ```bash
    gcloud alloydb clusters create CLUSTER_ID --region=REGION \
        --password=PASSWORD --network=VPC_NAME
    ```

-   **List clusters:**

    ```bash
    gcloud alloydb clusters list --region=REGION
    ```

-   **Get cluster information:**

    ```bash
    gcloud alloydb clusters describe CLUSTER_ID --region=REGION
    ```

-   **Delete a cluster:**

    ```bash
    gcloud alloydb clusters delete CLUSTER_ID --region=REGION

    ```

    ## Instances

-   **Create a primary instance:**

    ```bash
    gcloud alloydb instances create INSTANCE_ID --cluster=CLUSTER_ID \
        --region=REGION --instance-type=PRIMARY --cpu-count=8
    ```

-   **Create a read pool instance:**

    ```bash
    gcloud alloydb instances create INSTANCE_ID --cluster=CLUSTER_ID \
        --region=REGION --instance-type=READ_POOL \
        --read-pool-node-count=2 --cpu-count=2
    ```

-   **List instances:**

    ```bash
    gcloud alloydb instances list --cluster=CLUSTER_ID --region=REGION
    ```

-   **Restart an instance:**

    ```bash
    gcloud alloydb instances restart INSTANCE_ID --cluster=CLUSTER_ID \
        --region=REGION
    ```

-   **Scale read pool horizontally (node count):**

    ```bash
    gcloud alloydb instances update INSTANCE_ID --cluster=CLUSTER_ID \
        --region=REGION --read-pool-node-count=NODE_COUNT
    ```

-   **Scale instance vertically (CPU count):**

    ```bash
    gcloud alloydb instances update INSTANCE_ID --cluster=CLUSTER_ID \
        --region=REGION --cpu-count=CPU_COUNT
    ```

-   **Scale instance vertically (machine type):**

    ```bash
    gcloud alloydb instances update INSTANCE_ID --cluster=CLUSTER_ID \
        --region=REGION --machine-type=MACHINE_TYPE
    ```

## Backups & Restore

-   **Create an on-demand backup:**

    ```bash
    gcloud alloydb backups create BACKUP_ID --cluster=CLUSTER_ID \
        --region=REGION
    ```

-   **List backups:**

    ```bash
    gcloud alloydb backups list --region=REGION
    ```

-   **Configure continuous backup recovery window:**

    ```bash
    gcloud alloydb clusters update CLUSTER_ID --region=REGION \
        --continuous-backup-recovery-window-days=DAYS
    ```

-   **Enable and configure automated scheduled backups:**

    ```bash
    gcloud alloydb clusters update CLUSTER_ID --region=REGION \
        --automated-backup-days-of-week=DAYS_OF_WEEK \
        --automated-backup-start-times=START_TIMES \
        --automated-backup-retention-period=RETENTION_PERIOD
    ```

    *Example:* `--automated-backup-days-of-week=MONDAY,WEDNESDAY,FRIDAY --automated-backup-start-times=01:00 --automated-backup-retention-period=30d`

-   **Disable automated backups:**

    ```bash
    gcloud alloydb clusters update CLUSTER_ID --region=REGION \
        --disable-automated-backup
    ```

-   **Restore from a discrete backup:**

    ```bash
    gcloud alloydb clusters restore DEST_CLUSTER_ID --region=REGION \
        --backup=BACKUP_ID
    ```

-   **Restore to a point in time (PITR):**

    ```bash
    gcloud alloydb clusters restore DEST_CLUSTER_ID --region=REGION \
        --source-cluster=SOURCE_CLUSTER_ID \
        --point-in-time=TIMESTAMP
    ```

    *Note: TIMESTAMP must be in RFC 3339 format, e.g. `2026-07-30T15:00:00.00Z`.*
