# GKE TPU Metrics Signatures

This document describes key metric signatures and what they indicate for GKE TPU workloads.

## 1. Node Unready Signature

- **Metric**: `kubernetes.io/node/status_condition`
- **Signature**: `condition="Ready"`, `status="False"` (or `status="Unknown"`)
- **Meaning**: The GKE node hosting the TPU is not healthy. Workloads on this node will be disrupted.

## 2. Node Pool Error Signature

- **Metric**: `kubernetes.io/node_pool/status`
- **Signature**: `status="Error"`
- **Meaning**: The multi-host TPU node pool has encountered an error (e.g., provisioning failure).

## 3. Node Preemption Signature

- **Metric**: `kubernetes.io/node/interruption_count`
- **Signature**: `interruption_type="PreemptionEvent"`
- **Meaning**: The node was preempted (common for Spot VMs). Workload needs to be rescheduled.

## 4. Host Error Signature

- **Metric**: `kubernetes.io/node/interruption_count`
- **Signature**: `interruption_type="TerminationEvent"`, `interruption_reason="HostError"`
- **Meaning**: The underlying physical host encountered a hardware error. GKE should trigger AutoRepair.

## 5. Low TPU Utilization Signature

- **Metric**: `kubernetes.io/container/accelerator/duty_cycle` or `kubernetes.io/container/accelerator/tensorcore_utilization`
- **Signature**: Value `< 0.2` (20%) during active training.
- **Meaning**: The TPU is heavily underutilized, likely due to data bottleneck or small batch size.
