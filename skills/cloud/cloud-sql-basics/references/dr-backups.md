# Cloud SQL Disaster Recovery & Backups

Cloud SQL provides multiple mechanisms for data protection, continuous replication, high availability, and disaster recovery (DR).

## Backup Types and Recovery

- **Automated Backups:** Daily instance snapshots taken during a user-configurable 4-hour window. Enterprise edition retains up to 7 backups by default; Enterprise Plus edition supports retention up to 35 days.

- **On-Demand Backups:** Manually created backups that remain stored until explicitly deleted. Useful before performing high-risk schema migrations or administrative changes.

- **Enhanced Backups:** Managed data protection integrated with Google Cloud **Backup and DR Service** for enterprise governance, centralized management, and compliance across projects.
  - **Air-Gapped & Immutable Vaults:** Backups are stored in separate, logically isolated projects to protect against ransomware and accidental deletion.
  - **Extended Retention & Flexible Schedules:** Supports up to **10 years** of retention (compared to 1 year for standard backups) with flexible schedules (hourly, daily, weekly, monthly, or yearly).
  - **Retention Lock:** Enforces non-deletable, non-modifiable backup rules until the specified retention duration expires.
  - **Cross-Project Recovery:** Facilitates recovery of database workloads into different target projects for disaster recovery operations.

- **Point-in-Time Recovery (PITR):** Uses continuous transaction logging (binary logging for MySQL, write-ahead logging for PostgreSQL, transaction logging for SQL Server) to restore an instance to a specific second in time.
  - **Retention Limits:** Up to 7 days (Enterprise edition) or up to 35 days (Enterprise Plus edition).
  - **Storage:** Stored on disk or Cloud Storage depending on configuration.

- **Final Backups:** Automated final state snapshots taken before instance deletion or post-failover rebuilds to protect data against accidental loss.

- **Backup Locations:** Stored by default in the closest multi-region location to the instance, or in custom regional/multi-region storage buckets. Can be restored to the same instance or to a new target instance.

### Standard vs. Enhanced Backups

| Feature | Standard Backups | Enhanced Backups |
| :--- | :--- | :--- |
| **Management** | Instance-level Cloud SQL backups | Centralized Backup and DR Service |
| **Storage Vault** | Same project / multi-region storage bucket | Separate air-gapped immutable backup project |
| **Max Retention** | Up to 1 year | Up to 10 years |
| **Scheduling** | Daily (4-hour configurable window) | Hourly, Daily, Weekly, Monthly, Yearly |
| **Retention Lock** | Not supported | Supported (Enforced retention policy) |
| **Cross-Project Recovery** | Standard instance restore to project targets | Centralized cross-project recovery workflows |
| **Billing Model** | Cloud SQL backup storage pricing | Backup and DR Service pricing model |

## Replication Types and High Availability (HA)

- **High Availability (HA) Standby Replicas:** Provides regional redundancy with a standby VM situated in a secondary zone within the same region. Employs automatic synchronous replication and instant failover in the event of primary hardware or zonal failure.

- **Standalone Read Replicas:** Asynchronous read-only instances (zonal or cross-region) used to scale query traffic and provide local read access.
  - **Node Limits:** Up to 20 total for MySQL/PostgreSQL; up to 7 for SQL Server.

- **Cascading Replicas:** Read replicas that replicate from another read replica rather than directly from the primary instance, reducing replication load on the primary instance.

## Advanced Disaster Recovery (DR)

Exclusive to **Cloud SQL Enterprise Plus Edition**, Advanced DR simplifies regional disaster recovery and drill testing:

- **Designated DR Replica:** A cross-region read replica designated as the target for regional recovery operations.

- **Replica Failover:** Rapid cross-region failover triggered during primary region outages. Promotes the designated DR replica to primary while retaining the old primary in the replication topology for eventual restoration.

- **Switchover:** Zero-data-loss, zero-downtime operation used for planned cross-region failover or routine DR drills. Gracefully reverses roles between the primary instance and the DR replica.

- **DNS Write Endpoints:** Provides a global DNS endpoint that automatically shifts write traffic to the newly promoted primary instance following a switchover or replica failover.

## Read Pools vs. Read Replicas in Architecture

| Feature | Standalone Read Replica | Read Pool Node |
| :--- | :--- | :--- |
| **Primary Purpose** | Read scaling & cross-region DR failover target | High-concurrency, load-balanced regional read traffic |
| **Topology** | Direct or cascading from primary instance | Direct replication only (no cascading) |
| **Connection Endpoint** | Individual dedicated IP / Connection name | Single load-balanced IP / Connection name pool |
| **DR & Promotion** | Can be promoted to an independent primary | Cannot be promoted directly to a primary instance |
| **Scaling Mechanism** | Individual instance creation/deletion | Manual scaling or automatic scaling (1-20 nodes) |

## Disaster Recovery & Backup CLI Management

### Backup Management & Operations

- **Enable automated backups and Point-in-Time Recovery (PITR):**
  ```bash
  gcloud sql instances patch my-instance \
      --backup-start-time=03:00 \
      --enable-point-in-time-recovery \
      --quiet
  ```

- **Create an on-demand backup:**
  ```bash
  gcloud sql backups create --instance=my-instance \
      --description="Pre-migration snapshot" \
      --quiet
  ```

- **List available backups:**
  ```bash
  gcloud sql backups list --instance=my-instance --quiet
  ```

- **Restore from a backup:**
  - *To the original instance (overwrites current data):*
    ```bash
    gcloud sql backups restore backup_id --restore-instance=restore-instance --quiet
    ```
  - *To a different target instance:*
    ```bash
    gcloud sql backups restore backup_id \
        --restore-instance=restore-instance \
        --backup-instance=source-instance \
        --quiet
    ```

- **Perform Point-in-Time Recovery (PITR Clone):**
  Clones an instance to a new instance state at a specific RFC 3339 timestamp.
  ```bash
  gcloud sql instances clone source-instance restored-instance \
      --point-in-time="2026-07-16T12:00:00Z" \
      --quiet
  ```

### High Availability & Disaster Recovery Operations

- **Simulate/trigger High Availability (HA) failover:**
  Fail over to the standby instance in the secondary zone for testing.
  ```bash
  gcloud sql instances failover my-ha-instance --quiet
  ```

- **Perform planned DR switchover (Enterprise Plus Edition):**
  Executes a zero-data-loss switchover to a designated cross-region DR replica.
  ```bash
  gcloud sql instances switchover my-dr-replica --quiet
  ```

- **Promote a read replica to an independent primary:**
  ```bash
  gcloud sql instances promote-replica my-replica --quiet
  ```

For more information, see:

- [About Backups in Cloud SQL](https://docs.cloud.google.com/sql/docs/mysql/backup-recovery/manage-standard-backups.md.txt)
- [About High Availability (HA)](https://docs.cloud.google.com/sql/docs/mysql/high-availability.md.txt)
- [About Disaster Recovery in Cloud SQL](https://docs.cloud.google.com/sql/docs/mysql/intro-to-cloud-sql-disaster-recovery.md.txt)
