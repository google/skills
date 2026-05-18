# Runbook Command Templates

Standard command sequences for GKE upgrades. Replace placeholders: `CLUSTER_NAME`, `ZONE`, `TARGET_VERSION`, `NODE_POOL_NAME`.

## Pre-flight

```bash
# Current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Available versions for channel
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels)"

# Deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
```

## Control plane upgrade

```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Verify (wait ~10-15 min)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

kubectl get pods -n kube-system
```

## Node pool upgrade (Standard only)

```bash
# Configure surge settings
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade MAX_SURGE \
  --max-unavailable-upgrade MAX_UNAVAILABLE

# Upgrade
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Verify
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE
kubectl get pods -A | grep -v Running | grep -v Completed
```

## Maintenance window configuration

```bash
# Set recurring maintenance window
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start YYYY-MM-DDTHH:MM:SSZ \
  --maintenance-window-end YYYY-MM-DDTHH:MM:SSZ \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Add maintenance exclusion (up to 30 days)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "EXCLUSION_NAME" \
  --add-maintenance-exclusion-start-time START_TIME \
  --add-maintenance-exclusion-end-time END_TIME
```

## Rollback guidance

Control plane downgrade is rare and not recommended without GKE support involvement. Node pool downgrades require creating a new pool at the old version and migrating workloads.

```bash
# Cancel in-progress node pool upgrade (if needed)
# GKE will finish the current node and stop
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE

# Create replacement node pool at previous version (if rollback needed)
gcloud container node-pools create NODE_POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version PREVIOUS_VERSION \
  --num-nodes NUM_NODES \
  --machine-type MACHINE_TYPE

# Cordon old pool and migrate workloads
kubectl cordon -l cloud.google.com/gke-nodepool=NODE_POOL_NAME
```
