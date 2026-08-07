# GKE TPU Dynamic Slices Status & Failure Signatures

This document provides examples of slice resource statuses and failure
conditions for GKE TPU Dynamic Slices.

## 1. Slice Condition: `FAILED`

When a slice fails to form (e.g. due to node provisioning timeouts or physical
hardware failures), `kubectl describe slice` shows the following condition:

```yaml
Status:
  Conditions:
    Last Transition Time: 2026-06-25T12:00:00Z
    Message: "Slice formation timed out. Insufficient physical nodes provisioned."
    Reason: FAILED
    Status: False
    Type: Ready
```

## 2. Slice Condition: `SliceCreationFailed`

If the requested configuration is invalid (e.g., the topology dimensions do not
match the partition counts provided), the GKE Slice Controller will fail
validation:

```yaml
Status:
  Conditions:
    Last Transition Time: 2026-06-25T12:05:00Z
    Message: "Prerequisites validation failed: partition count does not match topology dimensions."
    Reason: SliceCreationFailed
    Status: False
    Type: Ready
```

## 3. Stuck Deletion (`DEACTIVATING` / Finalizers)

When a slice is deleted, the controller attempts to dismantle the slice. If the
underlying VM/node deletion hangs, the slice remains in `DEACTIVATING` state:

```yaml
Metadata:
  Finalizers: accelerator.gke.io/slice-finalizer
Status:
  Conditions:
    Last Transition Time: 2026-06-25T12:10:00Z
    Message: "Dismantling slice resources..."
    Reason: DEACTIVATING
    Status: False
    Type: Ready
```

If it is stuck for more than 10-15 minutes, Resolution 1 (removing finalizers)
is typically applied to force clean up the resource.
