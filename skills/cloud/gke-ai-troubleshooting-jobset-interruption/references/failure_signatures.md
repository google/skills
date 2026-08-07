# JobSet Interruption Failure Signatures

This document provides authentic, anonymized logs, metrics, and signal patterns
associated with GKE JobSet interruptions, Spot VM preemptions, physical host
hardware failures, and worker application hangs.

--------------------------------------------------------------------------------

## 1. Nodepool Preemption Event (Spot VMs)

When Spot VMs are preempted by GCE, the nodepool logs record a preemption
interruption event.

**Example Cloud Logging (LQL) Match:**

```sql
resource.type="gke_nodepool"
severity=INFO

"PreemptionEvent: Node 'gke-tpu-pool-12345-abcde' in node pool 'tpu-pool' was preempted."
```

--------------------------------------------------------------------------------

## 2. Node / Host Hardware Failure (TerminationEvent)

A physical host error or hardware failure will trigger a TerminationEvent, often
accompanied by a "Host Error" or "kernel panic" payload.

**Example Logs:**

```text
May 20 08:12:15 gke-tpu-pool-12345-abcde kernel: [ 9876.543210] BUG: unable to handle kernel paging request at 0000000000002008
May 20 08:12:16 gke-tpu-pool-12345-abcde systemd[1]: node-problem-detector.service: Main process exited, code=exited, status=1/FAILURE
```

**Cloud Logging Filter Match:**

```sql
resource.type="k8s_node"
severity=ERROR

"TerminationEvent: Node 'gke-tpu-pool-12345-abcde' was terminated due to: Host Error"
```

--------------------------------------------------------------------------------

## 3. Worker NCCL / Collective Communication Timeouts (MegaScale Hang)

When a training run hangs due to network packet drop or worker failure, the
remaining workers will eventually timeout waiting for collective communication.

**Example Log Patterns:**

```text
[rank0]:[2026-05-20 08:14:30,123] torch.distributed.elastic.multiprocessing.api: [ERROR] Child process 12345 died with exit code 1
[rank0]:[2026-05-20 08:14:35,456] NCCL WARN : [Proxy Service] Failed to send, connection reset by peer
[rank0]:[2026-05-20 08:14:40,000] NCCL WARN: Collective collectiveName/1234567890abcde timeout after 1800 seconds
```

--------------------------------------------------------------------------------

## 4. Pod Unschedulable Due to Resource Quota / Placement Constraints

If the GKE autoscaler cannot find sufficient capacity or compact placement
groups for rescheduled JobSet workers, pods will remain `Pending` with
`Unschedulable` status.

**Example Log / PromQL Signal:**

```sql
resource.type="k8s_pod"
severity=WARNING

"0/8 nodes are available: 8 Insufficient tpu, 8 node(s) did not match Topology Spread Constraints."
```
