---
name: pathways-workload
description: >-
  Debugs failed, crashing or hung Pathways on Cloud workloads (JAX training or
  inference on Cloud TPU in GKE, run as a JobSet, PathwaysJob or
  LeaderWorkerSet). Reads Cloud Logging for every Pathways container (user
  workload, IFRT proxy, pathways-rm, pathways-worker, colocated Python
  sidecar), node kernel logs and GKE events, then reports the earliest real
  error, the root cause and a fix. Use when a Pathways workload fails to start,
  crashes, restarts or stops making progress, or shows errors such as IFRT
  proxy connection failures, DEADLINE_EXCEEDED lost connection to peer, host
  OOM kills, ImagePullBackOff, or JAX and Pathways version mismatches. Don't
  use for GKE workloads that don't use Pathways, or for creating clusters or
  deploying new Pathways workloads.
metadata:
  version: "1.0.0"
  category: AiAndMachineLearning
---

# Pathways on Cloud Workload Debugging Skill

This skill provides comprehensive instructions, debugging playbooks, and helper
utilities to troubleshoot Pathways on Cloud GKE workloads.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

--------------------------------------------------------------------------------

## Overview

Pathways:
[Pathways on Cloud Introduction](https://docs.cloud.google.com/ai-hypercomputer/docs/workloads/pathways-on-cloud/pathways-intro)

### Understanding Initial Setup for JAX+Pathways on Cloud

A GKE cluster is required to use Pathways. We have instructions to create one
which utilize either 1\) a one click setup like XPK or 2\) a series of gcloud
commands here:
[https\://docs.cloud.google.com/ai-hypercomputer/docs/workloads/pathways-on-cloud/create-gke-cluster](https://docs.cloud.google.com/ai-hypercomputer/docs/workloads/pathways-on-cloud/create-gke-cluster)

Advanced customers have built custom infrastructure which rolls Pathways based
JobSets and cluster creation commands. To debug their infra issues, we may want
to ask them to share their jobset YAMLs with us (redacting their main container
definition is fine).

### Parsing Important Logs

How to determine if various Pathways components have started successfully

**IFRT Proxy Server (a.k.a Pathways Client) Ready**

```
IFRT proxy server started with status OK

Pathways worker Ready: Pathways Server serving on [::]:29001
```

**RM (Resource Manager) Ready and eventually all TPU slices are ready**

```
Pathways Server serving on [::]:29001
...
...
***<num slices>/<num slices> Pathways Slices Now Ready ***
```

**Individual Pathways worker (on a TPU host) Ready**

```
Pathways Server serving on [::]:29001
```

--------------------------------------------------------------------------------

## Step 1: Metadata & Configuration Gathering

Before initiating debugging, gather critical parameters to construct accurate
queries: 1. `project` 2. `cluster_name` 3. `location` 4. the workload name and
kind (see [Identifying the Workload](#identifying-the-workload)) 5. `namespace`
(default: `default`) 6. `issue_time` (UTC, when the failure was first noticed)

Always bound log queries in time. Use the window
`[issue_time - 30m, issue_time + 30m]`, i.e. pass
`--start_time="{start_time}" --duration=1h` to the debug_workload script, where
`{start_time}` is `issue_time - 30m` in RFC 3339 (e.g. `2026-10-22T11:10:00Z`).
Unbounded queries are slow and get truncated by `--limit`. Widen the window only
if the first error is not in it.

-   If the window contains more than one failure, report each with timestamps
    and say which one matches the user's symptom.
-   Report the root cause and the workaround separately. The root cause is the
    component that logged the earliest stall or error (for example the proxy,
    the RM or a worker). A configuration change that avoids that code path
    (a different checkpoint handler, flag or topology) is a workaround or a
    contributing factor: list it under the fix, not as the root cause.
-   When you compare with other runs (an earlier attempt, a sibling test that
    passed, or the same test on other days), use the comparison to narrow down
    which code path is affected, not as proof of the cause. A setting that
    differs in a passing run does not explain the failure if a Pathways
    component logged the stall or error.
-   End the report with the checks you ran and their result, so the user can
    repeat them: preflight, the actions or `gcloud logging read` queries you
    used (with their time window), pod events, and node OOMs. Include checks
    that failed or could not run (e.g. no log access) and say what to run
    instead.

> [!TIP]
>
> Always check the recent chat context or shared log queries from the user.
> Often, all five fields can be directly scraped from their console links or
> queries!

### Identifying the Workload

The debug_workload script finds the workload's logs by the object that created
its pods. Use the matching flag (the examples in this skill use
`--jobset_name`):

Workload kind                                 | Flag                     | Find it with
:-------------------------------------------- | :----------------------- | :-----------
JobSet (most training workloads, XPK)         | `--jobset_name=<name>`   | `kubectl get jobsets -n {namespace}`
LeaderWorkerSet (e.g. Pathways inference)     | `--lws_name=<name>`      | `kubectl get leaderworkersets -n {namespace}`
Plain Job (not created by a JobSet)           | `--job_name=<name>`      | `kubectl get jobs -n {namespace} -l '!jobset.sigs.k8s.io/jobset-name'`
Anything else (bare pods, custom controllers) | `--pod_prefix=<prefix>`  | `kubectl get pods -n {namespace}`

For past incidents, list the pods that logged in the window and their owner
labels instead:

```bash
gcloud logging read 'resource.type="k8s_container"
  resource.labels.cluster_name="{cluster_name}"
  resource.labels.namespace_name="{namespace}"
  timestamp>="{start_time}" timestamp<="{end_time}"' \
  --project="{project}" --limit=10000 \
  --format='value(resource.labels.pod_name,labels."k8s-pod/jobset_sigs_k8s_io/jobset-name",labels."k8s-pod/leaderworkerset_sigs_k8s_io/name",labels."k8s-pod/batch_kubernetes_io/job-name")' \
  | sort -u
```

If parts of the workload run in different objects, query them together by
repeating `--workload=<kind>:<name>` (kinds: `jobset`, `lws`, `job`, `pod`).
For example, if the JAX client or the proxy runs in its own Job next to the
Pathways JobSet, debug both: `--workload=jobset:{jobset_name}
--workload=job:{client_job_name}`.

To see what else ran on the same nodes, run `scripts/debug_workload.py` with
`--action=neighbors --execute`. It lists every namespace/pod/container that
logged on the workload's nodes and marks the ones that are not part of the
workload. Use it to spot another workload sharing the hosts (e.g. a second
resource manager or proxy on the same host and port when host exclusivity is not
set) and to find the real container names of the workload's pods (e.g. a
custom-named colocated Python sidecar).

### Retrieving Active YAML Configuration

If the workload is still active/alive, run the following command to inspect how
it is structured and identify misconfigurations (use `leaderworkerset` or `job`
instead of `jobset` for those kinds):

```bash
kubectl get jobset {jobset_name} -n {namespace} -o yaml
```

If the workload has been deleted but you suspect misconfiguration, request the
user to paste or share the workload YAML in the chat.

### Recording Versions

Before reading errors, record each component's image tag (from the YAML or the
pod spec) and `Build label` (logged at startup by pathways-rm, pathways-proxy
and pathways-worker), plus the client's JAX, jaxlib and pathwaysutils versions.
Check that they are from matching releases and that the flags passed to each
component exist in its image.

--------------------------------------------------------------------------------

## Step 1.5: Quick Triage - Preflight, Then Crash Sweep

First run the preflight check. It verifies that you can read the project's logs
and that the workload logged in the time window. An empty result from any
other action is not a clean result until preflight passes. If you cannot run
commands yourself (for example no log access) and give the user a plan or a
list of commands instead, start that plan with the preflight command:

```bash
python3 scripts/debug_workload.py \
  --project="{project}" \
  --cluster_name="{cluster_name}" \
  --location="{location}" \
  --jobset_name="{jobset_name}" \
  --start_time="{start_time}" --duration=1h \
  --action=preflight
```

Then, before reading containers one by one, run the crash and fatal-error sweep
across all containers of the workload. It looks for segfaults, `Check failed`,
Python tracebacks, OOM kills, unknown flags, permission errors, etc., and
returns the earliest hits first:

```bash
python3 scripts/debug_workload.py \
  --project="{project}" \
  --cluster_name="{cluster_name}" \
  --location="{location}" \
  --jobset_name="{jobset_name}" \
  --start_time="{start_time}" --duration=1h \
  --action=errors \
  --execute
```

The container of the earliest hit is usually where the root cause is; then use
the container-specific playbook in Step 3 for that container. If the sweep is
empty, also run `--action=node-ooms` (OOM kills often do not appear in container
logs) and `--action=pod-events`.

If a cascade fills the output (hundreds of pods logging the same error), you
may add `--first_per_pod=N` to keep only the first N matching log lines of each
pod/container plus its last matching line, e.g. `--first_per_pod=1` to see
which pod failed first and how the failure spread, or `--first_per_pod=3` to
also see each pod's next few lines. Use it at your discretion: it fetches up to
`--fetch_limit` lines (default 1000) before grouping, so it is slower than a
plain query and can be slow or time out when the workload has many pods. Narrow
the time window first, and prefer a plain query when only a few pods are
involved. Never conclude "no crash" from a `--first_per_pod` sweep alone: it
skips lines in the middle of each pod's log, and the fetch limit can cut off
later pods. Confirm with a plain query on the suspect container.

--------------------------------------------------------------------------------

## Step 2: GKE JobSet Lifecycle Verification

If the workload has not started or failed immediately at scheduling time:

### 1. Verify Webhook & Scheduling Status

Identify if scheduling blocks are occurring due to insufficient cluster
resources or webhook failures.

Check for webhook mutating errors, `OOMKilled` controller managers, or
Unschedulable conditions:

```bash
# Check controller manager pods in the JobSet system namespace
kubectl get pods -n jobset-system
```

### 2. Symptom: Forever Suspended JobSet

If a JobSet is created but remains in a permanently `Suspended` state and never
spawns child pods:

-   **Potential Root Causes**:
    -   The JobSet name is too long. Because JobSet appends replicated job names
        and index numbers to child resources, long prefixes fail standard
        Kubernetes resource name validation (max 63/253 chars).
    -   The JobSet YAML is malformed (e.g. invalid or missing fields, wrong
        resource requests or node selectors), so the workload is never admitted
        to the queue and stays suspended. Ask the user for the YAML (see
        [Retrieving Active YAML Configuration](#retrieving-active-yaml-configuration))
        and check it for errors.
-   **Diagnosis**: Check the JobSet controller manager logs in `jobset-system`
    namespace to find truncation, length limit, name-generation, or validation
    errors. You can use the debug_workload script to quickly query the logs:

```bash
python3 scripts/debug_workload.py \
  --project="{project}" \
  --cluster_name="{cluster_name}" \
  --location="{location}" \
  --jobset_name="{jobset_name}" \
  --start_time="{start_time}" --duration=1h \
  --action=summary \
  --execute
```

### 3. SIGTERM and Pre-emption Diagnosis

-   SIGTERMs are the most common mechanism for GKE to stop/restart workloads. A
    SIGTERM is a symptom; find out who sent it.
-   Common senders: Spot VM preemption, Compute Engine host maintenance, host
    errors, node auto-repair, or a JobSet restart triggered by another failed
    container. Check infrastructure interruptions and pod events for the time
    window:

    ```bash
    python3 scripts/debug_workload.py \
      --project="{project}" \
      --cluster_name="{cluster_name}" \
      --location="{location}" \
      --jobset_name="{jobset_name}" \
      --start_time="{start_time}" --duration=1h \
      --action=interruptions \
      --execute
    # then the same command with --action=pod-events
    ```

-   If no infrastructure event explains the SIGTERM, trace the failure back from
    the user workload to the TPU that failed first:

    1.  In the user workload logs (`--action=user-workload`), find the time of
        the first error or the last completed step.
    2.  In the RM logs (`--action=pathways-rm`) around that time, find when the
        first failure occurred or the first TPU slice/worker stopped responding
        (e.g. a slice leaving the ready state or `Job cancelled due to ...`),
        and which slice/worker it was.
    3.  Inspect that worker's logs (`--action=workers`, adding
        `--min_severity=WARNING` if needed) and its node's events
        (`--action=pod-events`, `--action=node-ooms`, `--action=interruptions`)
        to find out what happened there.
    4.  The cause can be a user code error (unlikely) or another fault, such as
        a hardware failure, an OOM, a crash in the worker, or a node
        interruption.

-   `kubectl get events -n {namespace} --field-selector
    involvedObject.name={jobset_name}` only works for live incidents: Kubernetes
    keeps events for a certain time only. For past incidents use
    `--action=pod-events` / `--action=summary`, which read the events from Cloud
    Logging.

-   For deeper analysis of restarts and interruptions, follow the public
    [gke-ai-troubleshooting-jobset-interruption](https://raw.githubusercontent.com/google/skills/d542604d73544bcb4bcc61322f3b25522ceba7ed/skills/cloud/gke-ai-troubleshooting-jobset-interruption/SKILL.md)
    skill; for host maintenance, follow
    [gke-ai-troubleshooting-handle-disruption-gpu-tpu](https://raw.githubusercontent.com/google/skills/d542604d73544bcb4bcc61322f3b25522ceba7ed/skills/cloud/gke-ai-troubleshooting-handle-disruption-gpu-tpu/SKILL.md).

--------------------------------------------------------------------------------

## Step 3: Container-Specific Debugging Playbook

Because Pathways is distributed, inspect logs container-by-container in logical
order to avoid cascade noise, and always chase the earliest error. Before you
query a container, read its section in
[Container Playbooks](references/container-playbooks.md): it has the log
signals, the `debug_workload.py` command and the gotchas for that container.

Order | Container | Action | Look for | Playbook
:---- | :-------- | :----- | :------- | :-------
1 | User workload (`user-workload`, `main`, `jax-tpu`) | `--action=user-workload` | The last completed step, then the first exception | [A](references/container-playbooks.md#a-user-workload-container)
2 | IFRT proxy | `--action=proxy` | `Connection refused` to the RM port (`:29001`), `Socket closed` | [B](references/container-playbooks.md#b-ifrt-proxy-server)
3 | Resource manager (`pathways-rm`) | `--action=pathways-rm` | Slice ready transitions, placement, a repeated `Build label` (restarts) | [C](references/container-playbooks.md#c-resource-manager-pathways-rm)
4 | Pathways workers (`pathways-worker`) | `--action=workers` | The first worker that failed, Megascale stall detectors (`HANG_DETECTED`) | [D](references/container-playbooks.md#d-pathways-workers-pathways-worker)
5 | Colocated Python sidecar | `--action=colocated-python-sidecar` | Workers waiting for a sidecar that died | [E](references/container-playbooks.md#e-colocated-python-sidecar)

Rules that apply to every container:

-   A client-side `Unable to initialize backend 'proxy': UNAVAILABLE: Unable to
    establish connection` is a symptom. Check whether the proxy, RM and workers
    started (see [Parsing Important Logs](#parsing-important-logs)) and find
    their earliest error before you suspect the user's code.
-   `IFRT proxy server was terminated: UNAVAILABLE: Socket closed` and
    `SLICE_FAILURE_CHIP_DRIVER_ERROR` are downstream errors: go to the RM and
    worker logs.
-   When one worker fails, the other workers of the slice fail shortly after.
    The root cause is in the logs of the first worker that failed.
-   The built-in search terms only cover known failures. If an action returns
    nothing useful, re-run it with `--min_severity=WARNING` (`DEFAULT` for the
    user workload) and add the workload's own strings with `--extra_terms`.
-   If the logs still don't explain the failure, read all logs of the
    container ([F](references/container-playbooks.md#f-all-logs-of-a-container)),
    then ask for more verbose proxy logs or XProfs
    ([G](references/container-playbooks.md#g-when-the-error-is-still-not-clear)).

--------------------------------------------------------------------------------

## Step 4: Special Scenarios

These known failures have a specific cause and fix. When an error or
symptom matches a row, read that scenario in
[Special Scenarios](references/special-scenarios.md) before you conclude:

Error or symptom | Scenario
:--------------- | :-------
`JaxRuntimeError` with `DATA_LOSS` during scale changes; elastic recovery or checkpoint restore fails | [1. Elastic training and checkpoint restore](references/special-scenarios.md#1-elastic-training-and-checkpoint-restore)
Container restarts or exit code 137 without `OOMKilled`; `Memory cgroup out of memory`, `oom-kill`, `OOMKilling` | [2. Host OOM kills on the head pod or TPU hosts](references/special-scenarios.md#2-host-oom-kills-on-the-head-pod-or-tpu-hosts)
`Unable to initialize backend 'proxy': Backend 'proxy' is not in the list of known backends` | [3. Backend proxy is not in the list of known backends](references/special-scenarios.md#3-backend-proxy-is-not-in-the-list-of-known-backends)
`SIGTERM received by PID 1`; containers stop without a clear error | [4. SIGTERM received by PID 1](references/special-scenarios.md#4-sigterm-received-by-pid-1)
`FAILED_PRECONDITION: The newly added instance does not match with the expected instances` | [5. Newly added instance does not match the expected instances](references/special-scenarios.md#5-newly-added-instance-does-not-match-the-expected-instances)
`Connection to IFRT proxy server was terminated: FAILED_PRECONDITION: GrpcClientSession: writes no longer allowed` | [6. Connection to the IFRT proxy server was terminated](references/special-scenarios.md#6-connection-to-the-ifrt-proxy-server-was-terminated)
`XlaRuntimeError: ABORTED: ... The metadata for object was edited during the operation` | [7. Cached executable metadata was edited during the operation](references/special-scenarios.md#7-cached-executable-metadata-was-edited-during-the-operation)
`DEADLINE_EXCEEDED: lost connection to peer` or `DATA_LOSS: Pipe from scheduler to aggregator` | [8. Lost connection to peer](references/special-scenarios.md#8-lost-connection-to-peer)
`Status 11 from handshaker service: Input frame length is out of range` | [9. ALTS handshake error from a client outside Google Cloud](references/special-scenarios.md#9-alts-handshake-error-from-a-client-outside-google-cloud)
`Lifecycle matches_prefix cannot specify more than 50 prefixes per config` | [10. Cloud Storage lifecycle prefix limit](references/special-scenarios.md#10-cloud-storage-lifecycle-prefix-limit)
`IFRT Proxy client and server failed to agree on the protocol version`, or `Failed to deserialize the Mosaic module: ... Unsupported version` | [11. JAX and Pathways version mismatch](references/special-scenarios.md#11-jax-and-pathways-version-mismatch): compare the client's JAX, jaxlib and pathwaysutils versions with the Pathways image tags and `Build label`s
Pods in `ImagePullBackOff` or `ErrImagePull` | [12. Pods stuck in ImagePullBackOff or ErrImagePull](references/special-scenarios.md#12-pods-stuck-in-imagepullbackoff-or-errimagepull): read the pull error in the pod events, then list the registry's tags (`gcloud artifacts docker tags list`)
`Address already in use`, `Init:Error`, or `didn't have free ports` | [13. Port collisions with hostNetwork](references/special-scenarios.md#13-port-collisions-with-hostnetwork)
No error anywhere, but the job stops making progress | [14. The job hangs without failing](references/special-scenarios.md#14-the-job-hangs-without-failing)
`Still waiting to acquire semaphore`, `Recv completion error`, `GOAWAY` | [15. Proxy-to-worker transfers stall](references/special-scenarios.md#15-proxy-to-worker-transfers-stall)

--------------------------------------------------------------------------------

## Related Public Skills and Writing Your Own Queries

These public skills from
[github.com/google/skills](https://github.com/google/skills) complement this
skill. If they are installed, use them by name; otherwise read them from the
links.

Symptom                                                         | Public skill
:-------------------------------------------------------------- | :-----------
Writing a custom Cloud Logging query                            | [cloud-logging-query-generation](https://raw.githubusercontent.com/google/skills/d542604d73544bcb4bcc61322f3b25522ceba7ed/skills/cloud/cloud-logging-query-generation/SKILL.md) (GKE examples: [query_gke.md](https://raw.githubusercontent.com/google/skills/d542604d73544bcb4bcc61322f3b25522ceba7ed/skills/cloud/cloud-logging-query-generation/references/query_gke.md))
JobSet restarts, Spot preemption, maintenance, host termination | [gke-ai-troubleshooting-jobset-interruption](https://raw.githubusercontent.com/google/skills/d542604d73544bcb4bcc61322f3b25522ceba7ed/skills/cloud/gke-ai-troubleshooting-jobset-interruption/SKILL.md)
Compute Engine host maintenance on TPU/GPU nodes                | [gke-ai-troubleshooting-handle-disruption-gpu-tpu](https://raw.githubusercontent.com/google/skills/d542604d73544bcb4bcc61322f3b25522ceba7ed/skills/cloud/gke-ai-troubleshooting-handle-disruption-gpu-tpu/SKILL.md)
Multi-slice job stops responding (`HANG_DETECTED`)              | [gke-ai-troubleshooting-tpu-mxla-hang](https://raw.githubusercontent.com/google/skills/d542604d73544bcb4bcc61322f3b25522ceba7ed/skills/cloud/gke-ai-troubleshooting-tpu-mxla-hang/SKILL.md)
Node NotReady, unresponsive node, auto-repair                   | [gke-ai-troubleshooting-node-unresponsive-timeout](https://raw.githubusercontent.com/google/skills/d542604d73544bcb4bcc61322f3b25522ceba7ed/skills/cloud/gke-ai-troubleshooting-node-unresponsive-timeout/SKILL.md)

When you write your own queries:

-   Always use double quotes for strings, uppercase `AND`/`OR`/`NOT`, and
    parentheses to group terms.
-   Restrict `resource.type` (`k8s_container`, `k8s_pod`, `k8s_node`,
    `gke_nodepool`, `gce_instance`) and use `log_id("events")`,
    `log_id("stdout")` or `log_id("stderr")` where possible.
-   Always add a time window (`timestamp>="..."` and `timestamp<="..."`).
-   Pathways components log glog lines into `jsonPayload.message` (some
    containers) or `textPayload` (others); bare quoted terms or `SEARCH()` match
    both.
-   Pod label keys are stored with `.` replaced by `_`, e.g.
    `labels."k8s-pod/batch_kubernetes_io/job-completion-index"` and
    `labels."k8s-pod/jobset_sigs_k8s_io/jobset-name"`. Some public examples
    spell the Job label with dots (`batch.kubernetes.io/job-name`); that form
    does not match Pathways logs.
