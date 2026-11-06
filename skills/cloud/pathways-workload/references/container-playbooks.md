# Container Playbooks

Per-container debugging steps for Pathways on Cloud workloads, in the order
of Step 3 of SKILL.md: user workload, IFRT proxy, resource manager,
workers, then the colocated Python sidecar. Always chase the earliest
error. Run the commands from the skill directory, as in SKILL.md.

## Contents

-   [A. User workload container](#a-user-workload-container): lines 20-91
-   [B. IFRT proxy server](#b-ifrt-proxy-server): lines 92-117
-   [C. Resource manager (pathways-rm)](#c-resource-manager-pathways-rm): lines 118-139
-   [D. Pathways workers (pathways-worker)](#d-pathways-workers-pathways-worker): lines 140-186
-   [E. Colocated Python sidecar](#e-colocated-python-sidecar): lines 187-253
-   [F. All logs of a container](#f-all-logs-of-a-container): lines 254-259
-   [G. When the error is still not clear](#g-when-the-error-is-still-not-clear): lines 260-290

--------------------------------------------------------------------------------

## A. User workload container

Start with the user workload logs (container `user-workload`, `main` or
`jax-tpu`). This container runs the primary Python code.

1.  **Find the Timestamp**: Find the exact timestamp of the last completed step
    or progress trace (e.g., `"completed step"`, `"Final goodput"`).

2.  **Identify Node/Worker Faults**: Look for exceptions or node references that
    stopped responding or failed.

3.  **Common Errors**:

    -   `jax.errors.JaxRuntimeError` (with `DATA_LOSS`): elasticity failure
        (see scenario 1 in Step 4 of SKILL.md).
    -   `Dict key mismatch` or `Error opening "zarr" driver`: Orbax/checkpoint
        issues.
    -   `Fatal Python error:` or
        `CRITICAL - Timeout from watchdog 'step-timebomb'`: process hangs.

4.  **Query Logs**:

```bash
python3 scripts/debug_workload.py \
  --project="{project}" \
  --cluster_name="{cluster_name}" \
  --location="{location}" \
  --jobset_name="{jobset_name}" \
  --start_time="{start_time}" --duration=1h \
  --action=user-workload \
  --execute
```

The built-in progress strings are partly framework specific (e.g.
`"completed step"` is logged by MaxText). If the user's workload logs progress
or errors differently, add its strings with `--extra_terms` (repeatable, plain
text); they are OR-ed with the built-in list. This works for the `errors`,
`user-workload`, `proxy`, `pathways-rm` and `workers` actions:

```bash
python3 scripts/debug_workload.py ... --action=user-workload \
  --extra_terms="train_step" --extra_terms="loss is nan" --execute
```

The real error may be logged at INFO. If the RM and workers look healthy, scan
the user container at all severities, starting just before the first exception
(e.g. a narrow `--start_time` with `--duration=5m`):

```bash
python3 scripts/debug_workload.py ... --action=user-workload \
  --min_severity=DEFAULT --execute
```

If the user workload logs are inconclusive, pin the timestamp of the earliest
suspicious error in the logs and widen the filter to the proxy server, followed
by the Pathways RM, followed by the Pathways worker. Some workloads may also
have a colocated python sidecar. Always chase the earliest error. See the next
sections for more details.

Example failures:

1.  `SLICE_FAILURE_CHIP_DRIVER_ERROR`: Not a root cause; indicates something
    earlier failed.
2.  `Unable to initialize backend 'proxy': UNAVAILABLE: Unable to establish
    connection`: This is a general error saying that your JAX program was not
    able to connect to the IFRT Proxy server running on GKE. To determine the
    root cause, check for the proxy server logs to verify if the proxy started
    successfully. If it did, this could happen due to networking issues e.g.
    firewall restrictions. If your JAX container is running outside of GKE, you
    can workaround that issue by colocating your JAX client with proxy server on
    the same k8s pod.

## B. IFRT proxy server

You can use the debug_workload script to quickly query the logs:

```bash
python3 scripts/debug_workload.py \
  --project="{project}" \
  --cluster_name="{cluster_name}" \
  --location="{location}" \
  --jobset_name="{jobset_name}" \
  --start_time="{start_time}" --duration=1h \
  --action=proxy \
  --execute
```

If the proxy logs repeat `Connection refused` to the resource manager port
(`:29001`) or `not yet heard from ... :29001`, the resource manager is down or
crash-looping. The JAX client then hangs at
`Sending InitRequest and waiting for response` until the test times out. Go to
the RM section and check whether `Build label` repeats (one per RM restart).

If you see `"IFRT proxy server was terminated: UNAVAILABLE: Socket closed"`: -
This is downstream. The proxy server died because a deeper Pathways worker or
Resource Manager container crashed. Skip proxy server logs and go directly to
Worker/RM logs.

## C. Resource manager (pathways-rm)

Examines slice allocation and overall Pathways clustering.

1.  Look for slice count synchronization and ready transitions (e.g.,
    `"N/M Pathways Slices Now Ready"` or `"slice ready"`).

2.  Track assignment, placement, and unassignment events of slices.

3.  **Query Logs**:

```bash
python3 scripts/debug_workload.py \
  --project="{project}" \
  --cluster_name="{cluster_name}" \
  --location="{location}" \
  --jobset_name="{jobset_name}" \
  --start_time="{start_time}" --duration=1h \
  --action=pathways-rm \
  --execute
```

## D. Pathways workers (pathways-worker)

There are many workers; each replicated Job is a slice, and each index is a
worker.

-   **Root Cause Isolation**: When one worker fails, all other workers in the
    slice cascade-fail shortly after. The true error is only on the *first*
    failing worker's logs at the very beginning of the incident.

-   **Leader Triage**: Filter logs specifically to the **leader workers**
    (`completion-index = 0` for each slice index) to significantly reduce query
    volume and identify which sub-worker failed.

-   **Multiline Logging Gotcha**: Be aware that multiline proto or serialized
    logs often get split. Non-first lines may incorrectly show as high severity
    errors in Cloud Logging.

-   **Sanitized Images**: Note that sanitized images will not have readable
    Python stack traces.

-   **Workers that stop responding**: Pathways workers log
    `Megascale hang detected` / `Megascale detects a hang`; Megascale itself
    logs `HANG_DETECTED`. The `workers` action matches all three. For a
    multi-slice job that stops responding, follow the public
    [gke-ai-troubleshooting-tpu-mxla-hang](https://raw.githubusercontent.com/google/skills/d542604d73544bcb4bcc61322f3b25522ceba7ed/skills/cloud/gke-ai-troubleshooting-tpu-mxla-hang/SKILL.md)
    skill.

-   **Query Logs**:

```bash
python3 scripts/debug_workload.py \
  --project="{project}" \
  --cluster_name="{cluster_name}" \
  --location="{location}" \
  --jobset_name="{jobset_name}" \
  --start_time="{start_time}" --duration=1h \
  --action=workers \
  --execute
```

The built-in lists of the `pathways-rm` and `workers` actions only cover known
failures. If they return nothing useful, re-run them with
`--min_severity=WARNING` (or `ERROR`) to also get every warning/error line, and
add any other failure strings you know of with `--extra_terms`. Keep the time
window tight: with `--min_severity` the result can be noisy (see the multiline
logging gotcha above).

## E. Colocated Python sidecar

Container `colocated-python-sidecar`, or the custom name found in Step 1 of
SKILL.md. Used in some workloads for colocated dataloading or checkpointing.
Look for workers that stopped responding indefinitely waiting for colocated
Python sidecars (often because one sidecar process died quietly).

The sidecar container is usually named `colocated-python-sidecar`, but customer
workloads may use a different name. The sidecar always runs **in the TPU worker
pods, next to the `pathways-worker` container** (usually as a native sidecar,
i.e. an `initContainer` with `restartPolicy: Always`). Containers of the head
pod (`pathways-rm`, `pathways-proxy`, the user's JAX container) are never the
sidecar. Before querying, find the actual name unless you got it from Step 1:

-   From the JobSet YAML (see Retrieving Active YAML Configuration in Step 1
    of SKILL.md):
    in the pod template that has the `pathways-worker` container, the sidecar is
    the other container (in `containers` or `initContainers`). It typically sets
    `GRPC_SERVER_ADDRESS` (port `50051`) and
    `CLOUD_PATHWAYS_SIDECAR_SHM_DIRECTORY`, and shares a memory volume with
    `pathways-worker`.
-   If the JobSet is still running, list the containers of each pod and pick the
    non-`pathways-worker` container of the pods that have `pathways-worker`:

    ```bash
    kubectl get pods -n {namespace} \
      -l jobset.sigs.k8s.io/jobset-name={jobset_name} \
      -o jsonpath='{range .items[*]}{.metadata.name}: {.spec.initContainers[*].name} {.spec.containers[*].name}{"\n"}{end}'
    ```

-   For past incidents, list which containers logged from which pods in the time
    window, and pick the non-`pathways-worker` container of the pods that also
    log `pathways-worker`:

    ```bash
    gcloud logging read 'resource.type="k8s_container"
      resource.labels.cluster_name="{cluster_name}"
      resource.labels.namespace_name="{namespace}"
      labels."k8s-pod/jobset_sigs_k8s_io/jobset-name"="{jobset_name}"
      timestamp>="{start_time}" timestamp<="{end_time}"' \
      --project="{project}" --limit=10000 \
      --format='value(resource.labels.pod_name,resource.labels.container_name)' \
      | sort -u
    ```

    The sidecar usually logs `Registering remote Python CPU backend` or
    `Installed shared memory allocator for remote Python` at startup, which you
    can use to confirm the pick. If no container other than `pathways-worker`
    logs from the worker pods, the workload most likely does not use a colocated
    Python sidecar.

If it is not the default, pass `--sidecar_container="{sidecar_container}"` to
every debug_workload command (it also excludes the sidecar from
`--action=user-workload`):

```bash
python3 scripts/debug_workload.py \
  --project="{project}" \
  --cluster_name="{cluster_name}" \
  --location="{location}" \
  --jobset_name="{jobset_name}" \
  --start_time="{start_time}" --duration=1h \
  --sidecar_container="{sidecar_container}" \
  --action=colocated-python-sidecar \
  --execute
```

## F. All logs of a container

If the above actions didn't help, you can try to look at all the logs.
Drop the filters in the log queries to see all logs for the containers, in the
same order as above.

## G. When the error is still not clear

### Increase verbosity of proxy logs

If you suspect more proxy logs are needed, you can ask the user to increase the
verbosity of the proxy server and the JAX client as follows:

a) IFRT Proxy Client Detailed Logs: Setting the below env variable in your JAX
container would log all IFRT calls originating from JAX.

```
TF_CPP_VMODULE=grpc_host_buffer=3,rpc_helper=3,host_buffer=3,ifrt_backend=3,grpc_service_impl=3
```

b) IFRT Proxy Server Detailed Logs: Setting the below flag in the IFRT Proxy
server command line args would log all incoming IFRT calls originating from the
IFRT Proxy client.

```
spec:
  customComponents:
  - componentType: proxy_server
    customFlags:
    - --vmodule=grpc_host_buffer=3,rpc_helper=3,host_buffer=3,ifrt_backend=3,grpc_service_impl=3
```

### Getting XProfs

If you need to view the profile of the user job, proxy, RM, and workers to
understand why certain operations are taking long, ask the user to provide XProf
snapshots.
