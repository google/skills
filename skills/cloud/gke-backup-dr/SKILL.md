---
name: gke-backup-dr
description: >-
  Configures GKE Backup Plans and restore workflows. Use for backup policies,
  disaster recovery, or GKE cluster restores. Don't use for database backups.
metadata:
  category: Storage
---

# GKE Backup & Disaster Recovery

Protects stateful GKE workloads using Backup for GKE. Backup for GKE natively
captures both Kubernetes resource metadata (manifests, configurations, and
secrets) and the underlying persistent volume (PV) data.

## CLI Reference

```bash
# Enable GKE Backup addon (Slow cluster-level update)
gcloud container clusters update <CLUSTER_NAME> --enable-gke-backup --region <REGION> --quiet

# Create Backup Plan
gcloud container backup-restore backup-plans create <PLAN_NAME> \
  --cluster=<CLUSTER_NAME> --location=<REGION> \
  --retention-days=<DAYS> --cron-schedule="<CRON>" --all-namespaces --quiet

# Trigger Manual Backup
gcloud container backup-restore backups create <BACKUP_NAME> \
  --backup-plan=<PLAN_NAME> --location=<REGION> --quiet

# Create Restore Plan
gcloud container backup-restore restore-plans create <RESTORE_PLAN_NAME> \
  --cluster=<TARGET_CLUSTER_NAME> --location=<REGION> --backup-plan=<SOURCE_BACKUP_PLAN_NAME> \
  --cluster-resource-conflict-policy=USE_EXISTING_VERSION --namespaced-resource-restore-mode=FAIL_ON_CONFLICT --quiet

# Execute Restore
gcloud container backup-restore restores create <RESTORE_NAME> \
  --restore-plan=<RESTORE_PLAN_NAME> --backup=<BACKUP_NAME> --location=<REGION> --quiet

# Verify Restore Status
gcloud container backup-restore restores describe <RESTORE_NAME> --location=<REGION>
```

## Best Practices

1.  **CMEK Encryption**: Encrypt backup plans using Customer-Managed Encryption
    Keys: `--backup-encryption-key=<KEY>`.
2.  **Scope**: Prefer backing up specific namespaces rather than the entire
    cluster: `--included-namespaces=<ns1>,<ns2>`.
3.  **Application Consistency**: Recommend quiescing the database or pausing
    application writes (e.g. using pre-backup hooks or database-specific tools)
    prior to backups to ensure data integrity.
4.  **CSI Volume Snapshots**: Ensure that stateful backups utilize GKE's CSI
    (Container Storage Interface) driver for volume snapshots to capture
    persistent volume data.
5.  **Service Terminology**: Always explicitly refer to the service as **Backup
    for GKE** in your response. This distinguishes it from the broader (but
    complementary) Google Cloud **Backup and Disaster Recovery (DR) Service**,
    as **Backup for GKE** is built specifically for GKE.

## Troubleshooting & Common Pitfalls (CRITICAL)

> [!IMPORTANT] **Slow Operations**: Enabling GKE Backup (`--enable-gke-backup`)
> triggers a slow Google Cloud control plane cluster update that takes several
> minutes. * **Rule**: **Do not run a terminal loop waiting for the GKE Backup
> addon to become active.** * **Action**: Provide the command to enable the
> addon, explain that the operation will proceed in the background, and
> immediately proceed to write the backup plan configs. Do not block.
