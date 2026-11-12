# Session lifecycle

## Synchronous vs asynchronous

*   **Default (synchronous):** `sessions submit ...` blocks until the session
    finishes. Fine for short runs.
*   **`--async`:** returns right after submission. Use it for anything longer
    than a few minutes, and for agents that should keep the user informed.

The submit output contains the session ID in the form `Creating session
[SESSION_ID]`. Capture it; every later command needs it.

## Waiting

Option A, block until done (streams a progress tracker to stderr and prints the
result table on completion):

```bash
gcloud beta device-run sessions wait SESSION_ID \
  --project="${PROJECT_ID}" --location=global
```

Option B, poll and report progress (preferred for agents):

```bash
gcloud beta device-run sessions describe SESSION_ID \
  --project="${PROJECT_ID}" --location=global
```

*   Poll every 30 to 60 seconds. Never poll in a tight loop.
*   While `PENDING` or `RUNNING`, `describe` writes only the status summary
    (and latest progress message) to stderr. Once `DONE`, it writes the
    summary to stderr and the per-job result table to stdout; capture both.
*   Add `--full` (optionally `--format=json`) for full session details,
    including per-job status while a session is still running.
*   If your environment has a native scheduling or background-task mechanism,
    you may use it instead of sleeping in the foreground.

## Status and result

A session and each of its jobs report a **status** and, once done, a **result**:

Status      | Meaning
:---------- | :---------------------------------------------
`PENDING`   | Waiting for a device.
`RUNNING`   | Executing.
`DONE`      | Finished; read the result.
`SUSPENDED` | Paused, typically due to quota. Tell the user.

Result      | Meaning
:---------- | :-----------------------------------------------------
`PASSED`    | Completed successfully.
`FAILED`    | The executable or tests failed.
`ERROR`     | Infrastructure or setup error; investigate the cause with `sessions describe SESSION_ID --full`.
`TIMED_OUT` | Exceeded the timeout; consider a longer timeout.
`CANCELLED` | Cancelled by the user or system.

The session is finished when its status is `DONE`. Do not wait for states such
as `ACTIVE` or `SUCCEEDED`; those are not Device Run states (`ACTIVE` belongs to
interactive Device Streaming leases).

## Cancel

```bash
gcloud beta device-run sessions cancel SESSION_ID \
  --project="${PROJECT_ID}" --location=global
```
