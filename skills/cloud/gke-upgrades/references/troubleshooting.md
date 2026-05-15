# Troubleshooting GKE Upgrade Issues

## Diagnostic flowchart

When an upgrade is stuck or failing, work through these checks in order. Each section has the diagnosis command, what to look for, and the fix.

## 1. PDB blocking drain (most common)

**Diagnose:**
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0
kubectl describe pdb PDB_NAME -n NAMESPACE
```

**Fix — temporarily relax the PDB:**
```bash
# Option A: Allow all disruptions temporarily
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"100%"}}'

# Option B: Back up and edit
kubectl get pdb PDB_NAME -n NAMESPACE -o yaml > pdb-backup.yaml
# Edit minAvailable/maxUnavailable, then:
kubectl apply -f pdb-backup.yaml
```

Restore original PDB after upgrade completes.

## 2. Resource constraints (no room for pods)

**Diagnose:**
```bash
kubectl get pods -A | grep Pending
kubectl get events -A --field-selector reason=FailedScheduling
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"
```

**Fix — increase surge capacity:**
```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

Or scale down non-critical workloads temporarily.

## 3. Bare pods blocking drain

**Diagnose:**
```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

**Fix:** Delete bare pods (they won't reschedule anyway) or wrap in Deployments.

## 4. Admission webhooks rejecting pod creation

**Diagnose:**
```bash
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations
# Check for webhooks matching broad API groups
kubectl describe validatingwebhookconfigurations WEBHOOK_NAME
```

**Fix — temporarily disable problematic webhook:**
```bash
# Add failure policy annotation or delete temporarily
kubectl delete validatingwebhookconfigurations WEBHOOK_NAME
# Re-create after upgrade
```

## 5. PVC attachment issues

**Diagnose:**
```bash
kubectl get pvc -A | grep -v Bound
kubectl get events -A --field-selector reason=FailedAttachVolume
```

**Fix:** Check if volumes are zone-locked. For regional clusters, PVs may need to be in the same zone as the new node. Consider migrating workloads to already-upgraded nodes.

## 6. Long termination grace periods

**Diagnose:**
```bash
kubectl get pods -A -o json | \
  jq '.items[] | select(.spec.terminationGracePeriodSeconds > 120) | {ns:.metadata.namespace, name:.metadata.name, grace:.spec.terminationGracePeriodSeconds}'
```

**Fix:** Reduce `terminationGracePeriodSeconds` in the workload spec if possible. GKE waits up to 1 hour for pod eviction during surge upgrades.

## 7. Upgrade operation stuck at GKE level

**Diagnose:**
```bash
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES"
```

**Fix:** If the operation shows no progress for >2 hours after resolving pod-level issues, contact GKE support with cluster name, zone, and operation ID.

## Validation after applying a fix

```bash
# Monitor node upgrade progress
watch 'kubectl get nodes -o wide | grep -E "NAME|CURRENT_VERSION|TARGET_VERSION"'

# Check no pods stuck
kubectl get pods -A | grep -E "Terminating|Pending"

# Confirm upgrade resuming
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=1
```
