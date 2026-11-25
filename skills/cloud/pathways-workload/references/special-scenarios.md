# Special Scenarios

Known Pathways on Cloud failure signatures, with their cause and fix. Step 4
of SKILL.md lists them by error and symptom. Run the commands from the skill
directory, as in SKILL.md.

## Contents

-   [1. Elastic training and checkpoint restore](#1-elastic-training-and-checkpoint-restore): lines 27-62
-   [2. Host OOM kills and memory-pressure evictions](#2-host-oom-kills-and-memory-pressure-evictions): lines 63-117
-   [3. Backend proxy is not in the list of known backends](#3-backend-proxy-is-not-in-the-list-of-known-backends): lines 118-126
-   [4. SIGTERM received by PID 1](#4-sigterm-received-by-pid-1): lines 127-187
-   [5. Newly added instance does not match the expected instances](#5-newly-added-instance-does-not-match-the-expected-instances): lines 188-202
-   [6. Connection to the IFRT proxy server was terminated](#6-connection-to-the-ifrt-proxy-server-was-terminated): lines 203-213
-   [7. Persistent compilation cache errors](#7-persistent-compilation-cache-errors): lines 214-248
-   [8. Lost connection to peer](#8-lost-connection-to-peer): lines 249-265
-   [9. ALTS handshake error from a client outside Google Cloud](#9-alts-handshake-error-from-a-client-outside-google-cloud): lines 266-281
-   [10. Cloud Storage lifecycle prefix limit](#10-cloud-storage-lifecycle-prefix-limit): lines 282-293
-   [11. JAX and Pathways version mismatch](#11-jax-and-pathways-version-mismatch): lines 294-311
-   [12. Pods stuck in ImagePullBackOff or ErrImagePull](#12-pods-stuck-in-imagepullbackoff-or-errimagepull): lines 312-328
-   [13. Port collisions with hostNetwork](#13-port-collisions-with-hostnetwork): lines 329-337
-   [14. The job hangs without failing](#14-the-job-hangs-without-failing): lines 338-351
-   [15. Proxy-to-worker transfers stall](#15-proxy-to-worker-transfers-stall): lines 352-370

--------------------------------------------------------------------------------

## 1. Elastic training and checkpoint restore

During scale transitions, JAX raises `JaxRuntimeError` with `DATA_LOSS`, and the
elastic training loop recovers from an in-memory snapshot or a persistent
checkpoint. To debug a failed recovery, rebuild its timeline from the JAX client
and pathways-rm:

```bash
python3 scripts/debug_workload.py ... --action=elastic --limit=500 --execute
```

Line up these events:

-   Slice loss and return: `Slices Now Ready`, `placed -> unplaced`,
    `Unassigning` (pathways-rm).
-   Recovery start: `Elastic attempt`, `New slices found`.
-   Snapshot path: `Restoring the in-memory snapshot`, or snapshots skipped
    because a checkpoint save was in progress.
-   Checkpoint path: `Falling back to persistent checkpoint`, `Restoring ...`
    with the step.
-   Outcome: `Resuming at step ...` or the next error. The `elastic` action also
    matches the crash and fatal-error list, so the exception that ended a
    recovery attempt shows up in the same timeline.

Then answer, in order:

1.  Which slice was lost, and when?
2.  Did a usable snapshot exist?
3.  Which restore path ran, and from which step?
4.  Was that step committed (`commit_success` / `_CHECKPOINT_METADATA` in the
    checkpoint directory)?
5.  Did the JobSet restart or tear down the job before the elastic wait
    finished? Compare JobSet and pod events (`--action=summary`,
    `--action=pod-events`) with the wait timeout.
6.  Was the proxy started in elastic mode?

## 2. Host OOM kills and memory-pressure evictions

OOMs on the head pod (python, proxy, or RM containers) and on TPU hosts (worker,
colocated Python sidecar) often **do not** appear in container logs or as an
`OOMKilled` pod event, but in the underlying node's kernel logs. A container
restart or exit code 137 without an `OOMKilled` reason also points here. Query
the node logs for OOM kills and memory-pressure evictions:

```bash
python3 scripts/debug_workload.py \
  --project="{project}" \
  --cluster_name="{cluster_name}" \
  --location="{location}" \
  --jobset_name="{jobset_name}" \
  --start_time="{start_time}" --duration=1h \
  --action=node-ooms \
  --execute
```

The node can also run out of memory without a kernel OOM kill: the kubelet
then evicts pods to free memory. Signs: an `Evicted` pod event with `The node
was low on resource: memory. Container <name> was using <N>Ki, request is
<M>...`, and `EvictionThresholdMet` or `NodeHasInsufficientMemory` node
events. An eviction for memory is host memory exhaustion, just like a kernel
OOM kill. So **no kernel OOM kill does not rule out a memory problem**: rule it
out only after the `node-ooms` action (which matches both) and
`--action=pod-events` show neither.

The pod-evictions part of `node-ooms` matches evictions for any resource, so
read the message: `low on resource: memory` is host memory exhaustion, while
`ephemeral-storage` or disk evictions that follow crashes (e.g. core dumps
filling the node disk) are usually side effects, not the root cause.

With `--execute`, `node-ooms` runs its parts one by one (node events, pod
evictions, kernel log lines, serial console), each limited by
`--query_timeout`. The kernel log search is free text and can time out on large
or old windows; if a part prints `[timeout]`, report that part as not checked
and narrow the window or pass `--node_names` to retry it.

When you find a host OOM kill (`Memory cgroup out of memory: Killed process`,
`oom-kill` or `OOMKilling`) or a memory-pressure eviction:

-   Say in the report that it is host (CPU) RAM, not TPU HBM. An HBM OOM shows
    up as `RESOURCE_EXHAUSTED` in the worker or user-workload logs instead, and
    needs different fixes (sharding, batch size), not more container memory.
-   Name the container that used the memory (the eviction message and the
    kernel OOM line both name it) and compare its usage with its memory request
    and limit. A container without a limit, or using far more than its
    request, can starve the other containers on the node, e.g. a colocated
    Python sidecar or data-loading process that grows while loading data or
    weights.
-   Line up the time of the kill or eviction with the first errors of the
    other containers: the errors that follow (lost connections, worker or
    proxy restarts) are side effects, not separate causes.

## 3. Backend proxy is not in the list of known backends

```
RuntimeError: Unable to initialize backend 'proxy': Backend 'proxy' is not in the list of known backends: ['cpu', 'tpu', 'cuda']. (set JAX_PLATFORMS='' to automatically choose an available backend)
```

The proxy backend is missing. Solution: Add pathwaysutils.initialize() at the
beginning of your program.

## 4. SIGTERM received by PID 1

This means that the GKE scheduler has sent a SIGTERM to the corresponding
pathways container and the container has exited in response to that. This can
happen due to a variety of events: GKE preempting your nodes due to lower level
defrag/maintenance events or higher level preemption events. Application errors
typically seen on proxy or RM happen before the first SIGTERM was received. K8s
decided to terminate all the pods in the jobset since the controller exiting
needs a jobset restart If no concrete error is found in the logs, check the
Kubernetes events and infrastructure interruptions with `--action=pod-events`,
`--action=summary` and `--action=interruptions` (see Step 2.3 in SKILL.md).
Check Resource Allocation: Insufficient CPU or memory allocated to the JAX,
proxy, or resource
manager (RM) containers is a leading cause of crashes without clear error
messages. To check if a container has OOMed, you should look at the GCE instance
logs which is hosting the corresponding container by searching for the string
`oom-killer`. It would describe the specific process (if any) that OOMed on the
pathways head node. The query filter to get that information is covered by
`--action=node-ooms`, which checks node-problem-detector
`OOMKilling`/`SystemOOM` events, kubelet memory-pressure evictions, kernel
`Memory cgroup out of memory` lines on the cluster's nodes, and serial-console
logs of the JobSet's nodes (discovered
automatically from the pods' `Scheduled` events, or pass
`--node_names=gke-...,gke-...`). To look at a single node manually:

```
resource.type="gce_instance"
labels."compute.googleapis.com/resource_name"="<Pathways head node>"
log_id("serialconsole.googleapis.com/serial_port_1_output")
SEARCH("oom-kill")
```

As a starting point, consider the following allocations:

Container             | Recommended Memory&nbsp;&nbsp; | Recommended CPU
:-------------------- | :----------------------------- | :--------------
JAX Client            | 100 GiB                        | 16
Pathways Proxy        | 100 GiB                        | 16
Resource Manager (RM) | 32 GiB                         | 16

**Preemption or maintenance cascade.** A node preemption or maintenance event
often produces a chain of errors across components, and the last one in the
chain is usually the most visible. A typical order:

1.  The preemption or maintenance notice (`--action=interruptions`), sometimes
    also forwarded in the pathways-rm logs.
2.  The RM or workers try to suspend or drain the slice; this can fail.
3.  The worker on the lost host is marked dead, and the others report
    `DATA_LOSS` or lost connections ([8](#8-lost-connection-to-peer)).
4.  The proxy restarts or drops its clients
    ([6](#6-connection-to-the-ifrt-proxy-server-was-terminated)).
5.  The JAX client fails, or crashes (e.g. a segmentation fault) while
    disconnecting.

Report the interruption as the root cause and steps 2-5 as its effects, with
their timestamps; do not report the client crash as a separate bug unless it
also happens without an interruption. After the restart, replacement pods may
stay `Pending` (e.g. no capacity); report that as a separate issue that delays
recovery. Side effects of the crashes, such as core dumps filling the node disk
(`DiskPressure`, ephemeral-storage evictions), are not the root cause either.

## 5. Newly added instance does not match the expected instances

```
FAILED_PRECONDITION: The newly added instance does not match with the expected instances
```

This typically occurs when there is a discrepancy between the expected TPU slice
topology by the RM and the actual instances provisioned by GKE for the worker.
[This](https://github.com/google/pathways-job/blob/c0cc7594c9d03a1d96a89110008a0f2d3c9ef189/internal/controller/pathwaysjob_controller.go#L71)
is the mapping supported by Pathways for various TPU chip generations and their
configurations. You can compare the expected and actual topologies by looking at
the proto in the RM logs for the topology that RM was expecting (indicated as
“expected topology”) and the topology that it got from the worker (indicated as
“Newly added slice topology”)

## 6. Connection to the IFRT proxy server was terminated

```
UNAVAILABLE:Connection to IFRT proxy server was terminated: FAILED_PRECONDITION: GrpcClientSession: writes no longer allowed
```

The Pathways cluster and specifically the pathways proxy container that your JAX
client was connected to has terminated or restarted since the original
connection was established. Try restarting your workload to see if the issue
goes away.

## 7. Persistent compilation cache errors

Errors about the compilation cache in Cloud Storage (often the
`--gcs_scratch_location` bucket) are common, but most of them are not fatal.
Before you report one as the root cause, check whether the job kept running
after it and whether the time of the error lines up with the failure.

**Cached executable metadata was edited during the operation:**

```
XlaRuntimeError: ABORTED: Permanent error, with a last message “” of The metadata for object was edited during the operation. Please try again
```

Possible race condition between writing and reading the cached executable object
in GCS. We
[recommend](https://docs.jax.dev/en/latest/persistent_compilation_cache.html#google-cloud)
using GCSFuse to mount your GCS bucket as a local directory. It translates the
GCS preconditions to the filesystem level to do parallel writes atomically and
prevent metadata conflicts you are seeing.

**Permission denied on the cache bucket** (`PERMISSION_DENIED`, e.g. on
`storage.buckets.update` or `storage.objects.*`, while initializing the
persistent cache): the service account cannot set up or use the cache. Pathways
usually falls back to an in-memory cache and keeps running, so this is not the
cause of a crash, but every restart recompiles from scratch, which makes
startup and recovery slower. Fix: grant the service account the missing role on
the bucket, or point the cache at a bucket it administers. Report it as a
contributing issue, and keep looking for the actual failure.

**`FAILED_PRECONDITION` on cache object updates** (e.g. updating an object's
metadata or custom time): possibly several writers updating the same cache
object at once. Like the race above, it is usually retried or skipped. If it
repeats on every startup, try the GCSFuse mount above or a separate cache
prefix per job, and compare startup time with and without the cache.

## 8. Lost connection to peer

One of these errors:

```
XlaRuntimeError: DEADLINE_EXCEEDED: lost connection to peer
DATA_LOSS: Pipe from scheduler to aggregator
```

A TPU worker likely exited either due to a hardware failure or a software fatal
error like OOMs. The GKE instance ID is generally part of the error message and
should be used to navigate to the instance logs to find more pointers for
determining the root cause. Check `--action=interruptions` and
`--action=node-ooms` for that host around the time of the error: a preemption
or host OOM there is the root cause (see the cascade in
[4](#4-sigterm-received-by-pid-1) and [2](#2-host-oom-kills-and-memory-pressure-evictions)).

## 9. ALTS handshake error from a client outside Google Cloud

```
Status 11 from handshaker service: Input frame length is out of range
```

This indicates an auth mismatch between the IFRT proxy client and the server.
IFRT Proxy uses ALTS for authentication by default. ALTS handshaker is running
on GCP VMs by default, so if your JAX client is running on a non GCP VM, this
error is expected. To fix, disable authentication on both the proxy client and
server by adding this environment variable to the JAX process and IFRT proxy
container: IFRT\_PROXY\_USE\_INSECURE\_GRPC\_CREDENTIALS="true".
This turns off authentication and encryption of the proxy traffic, so use it
only on a trusted network. To keep ALTS, run the JAX client on Google Cloud
instead, for example in the same GKE pod as the proxy.

## 10. Cloud Storage lifecycle prefix limit

```
INVALID_ARGUMENT : Permanent error, with a last message of Lifecycle matches_prefix cannot specify more than 50 prefixes per config.; Error while initializing persistent cache storage Cloud Storage
```

This error occurs if the Cloud Storage bucket passed in to the
\--gcs\_scratch\_location flag has reached the maximum lifecycle policy limit.
If this occurs, clean up Cloud Storage lifecycle policies that are no longer
being used. To avoid hitting this issue repeatedly, consider using a common
prefix across all your workloads.

## 11. JAX and Pathways version mismatch

One of these errors:

```
IFRT Proxy client and server failed to agree on the protocol version; supported versions: client = [1, 1], server = [3, 14]
ValueError: Failed to deserialize the Mosaic module: INTERNAL: Unsupported version: expected <= 7 but got 8
```

This indicates that your pathways images are incompatible with the JAX version
you are using. Please ensure that you are using a pathways image tag jax-0.x.y
matching your JAX version.

Check the versions first: compare the client's JAX, jaxlib and pathwaysutils
versions (`pip show jax jaxlib pathwaysutils`) with the Pathways server and
proxy image tags and the `Build label` they log at startup, and report both in
the answer.

## 12. Pods stuck in ImagePullBackOff or ErrImagePull

Go through these steps in order, and include each one in the report:

1.  Read the exact pull error in the pod events (`--action=pod-events` or
    `kubectl describe pod`): a missing tag or manifest (`manifest unknown`,
    `not found`), a permission error, or a network timeout.
2.  For a missing tag or manifest, list the tags that exist in the registry
    (`gcloud artifacts docker tags list <repository>/<image>` or
    `gcloud artifacts docker images list <repository>`).
3.  Switch to a published tag that matches the workload's JAX version. For a
    permission error, check that the node service account can pull from that
    repository instead.

The Pathways containers never started, so their logs are empty: do not look
for the root cause there.

## 13. Port collisions with hostNetwork

Pathways pods usually run with `hostNetwork: true`, so the Pathways ports (RM,
proxy, worker, Megascale) and any extra ports (e.g. metrics exporters enabled
with debugging flags) are shared by every container in the pod and every pod on
the node. Look for `Address already in use` or other bind errors, `Init:Error`,
or `FailedScheduling ... didn't have free ports`. Use `--action=neighbors` to
see what else ran on the node.

## 14. The job hangs without failing

When nothing reports an error, go through these steps in order:

1.  Find the last progress line of every container: user steps
    (`completed step`), RM slice state (`Slices Now Ready`, placed or unplaced
    slices), worker program launches, and proxy requests. Use
    `--order=desc --first_per_pod=1` with `--min_severity=DEFAULT` on each
    container action to get each pod's latest line.
2.  The component that stopped first is the lead.
3.  Check for pods that are Pending, missing or restarted
    (`--action=pod-events`).
4.  Check the Megascale stall detectors (`HANG_DETECTED`, `--action=workers`).

## 15. Proxy-to-worker transfers stall

The proxy repeats `Still waiting to acquire semaphore for destination ... to
send Chunk`, the workers log `Recv completion error`, and the gRPC transport
may later fail with `GOAWAY` (`ping_timeout` or `settings_timeout`). The client
usually just stops making progress, often while restoring a checkpoint or doing
another large host-to-device transfer through the proxy. This means
host-to-device transfers from the IFRT proxy to the workers stalled: it is a
Pathways runtime issue, not Orbax, Cloud Storage or user code. The `proxy` and
`workers` actions match these lines.

-   Check for an image regression: compare the server and proxy image tags and
    `Build label`s of the failing run with the last run of the same workload
    that passed. If they differ, run on the last-good images and report the
    change to Google Cloud support with the logs.
-   Workaround: avoid sending the checkpoint data through the proxy. Call
    `pathwaysutils.initialize()` before creating the Orbax checkpoint manager,
    so restores use the Pathways checkpoint handler
    (`CloudPathwaysArrayHandler`) and the workers read Cloud Storage directly.
