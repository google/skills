# Cloud SQL CLI Usage

The `gcloud sql` command group is used to manage Cloud SQL instances and
related resources.

## Basic Syntax

```bash
gcloud sql [GROUP] [COMMAND] [FLAGS]
```

## Essential Commands

### Instance Management

- **Create a primary instance:**

  ```bash
  gcloud sql instances create my-instance \
      --database-version=POSTGRES_18 \
      --edition=ENTERPRISE \
      --tier=db-custom-2-7680 \
      --region=us-central1 \
      --ssl-mode=ENCRYPTED_ONLY \
      --enable-point-in-time-recovery \
      --database-flags=cloudsql.iam_authentication=on \
      --quiet
  ```

- **Create a read pool (Enterprise Plus):**

  Creates a multi-node load-balanced read pool connected to a primary instance.

  ```bash
  gcloud sql instances create my-read-pool \
      --master-instance-name=my-instance \
      --instance-type=READ_POOL_INSTANCE \
      --edition=ENTERPRISE_PLUS \
      --tier=db-perf-optimized-N-2 \
      --node-count=2 \
      --no-assign-ip \
      --quiet
  ```

- **Create a read replica:**

  Creates an individual single-node read replica.

  ```bash
  gcloud sql instances create my-replica \
      --master-instance-name=my-instance \
      --quiet
  ```

- **List instances:**

  ```bash
  gcloud sql instances list --quiet
  ```

- **Describe an instance or read pool:**

  ```bash
  gcloud sql instances describe my-instance --quiet
  ```

- **Restart an instance:**

  ```bash
  gcloud sql instances restart my-instance --quiet
  ```

### Database and User Management

- **Create a database:**

  ```bash
  gcloud sql databases create my-db --instance=my-instance --quiet
  ```

- **Create an IAM database user (Recommended):**

  ```bash
  gcloud sql users create user-email@example.com \
      --instance=my-instance \
      --type=CLOUD_IAM_USER \
      --quiet
  ```

- **Create a user with a static password:**

  ```bash
  gcloud sql users create my-user --instance=my-instance \
      --password=my-password \
      --quiet
  ```

### Operations and Backups

- **List operations:**

  ```bash
  gcloud sql operations list --instance=my-instance --quiet
  ```

- **Create a backup:**

  ```bash
  gcloud sql backups create --instance=my-instance --quiet
  ```

- **Restore from a backup:**

  - *To the same instance that took the backup:*
    ```bash
    gcloud sql backups restore backup_id --restore-instance=my-instance --quiet
    ```

  - *To a different target instance:*
    *(Requires `--backup-instance` to specify the source instance of the backup ID)*
    ```bash
    gcloud sql backups restore backup_id \
        --restore-instance=target-instance \
        --backup-instance=source-instance \
        --quiet
    ```

## Common Flags

- `--project`: Specifies the Google Cloud project ID.

- `--region`: The region where the instance is located.

- `--edition`: Database edition (`ENTERPRISE` or `ENTERPRISE_PLUS`).

- `--tier`: Machine tier (e.g., `db-custom-2-7680`, `db-perf-optimized-N-2`).

- `--ssl-mode`: SSL enforcement mode (`ALLOW_UNENCRYPTED_AND_ENCRYPTED`, `ENCRYPTED_ONLY`, `TRUSTED_CLIENT_CERTIFICATE_REQUIRED`).

- `--database-flags`: Specifies database parameters (e.g., `cloudsql.iam_authentication=on`).

- `--tags`: Attaches Resource Manager tags (e.g., `tagKeys/123456789012=tagValues/987654321098`).

- `--format`: Changes output format (e.g., `json`, `yaml`).
