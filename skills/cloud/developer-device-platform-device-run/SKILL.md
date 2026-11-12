---
name: developer-device-platform-device-run
description: >-
  Runs automated, non-interactive jobs on remote Android devices with Developer
  Device Platform (DDP) Device Run using `gcloud beta device-run sessions`:
  native Android executables or shell scripts (for example CLI tools, custom
  runners, test harnesses or benchmarks) and
  Android instrumentation tests, on one or many devices, then waits for
  completion and collects per-device outputs and logs. Use when running a
  binary or test suite on remote devices without an interactive connection.
  Don't use it for interactive device reservations, adb tunnels or screen
  streaming (use developer-device-platform-basics), or for local devices.
metadata:
  version: "1.0.0"
  category: CloudInfrastructureAndServices
---

# Developer Device Platform: Device Run

Device Run executes a job on remote DDP devices and returns its artifacts (logs,
pulled files) to a Cloud Storage bucket. One session fans out to one job per
requested device.

> [!WARNING]
> Developer Device Platform (DDP) is currently in Preview. The
> `gcloud beta device-run` commands might change without notice.

## When to use this skill

The user wants to...                                       | Use
:--------------------------------------------------------- | :--
Run a native binary or shell script on remote devices      | This skill (`android-executable`)
Run an Android instrumentation test APK on remote devices  | This skill (`instrumentation`)
Reserve a device, connect with adb, stream the screen      | `developer-device-platform-basics`
Extend or cancel an interactive device lease               | `developer-device-platform-basics`
Work with a device connected over USB                      | Neither (not DDP)

The setup below is complete; this skill doesn't depend on another skill for
authentication, project selection or API enablement.

### Requests this skill does not handle

For interactive use (reserve a device, adb, screen streaming, leases):

*   **If `developer-device-platform-basics` is installed:** do not submit a
    Device Run session; switch to `developer-device-platform-basics`, and note
    that interactive reservations are also billed to the active project.
*   **If `developer-device-platform-basics` is not installed:** reply in a
    single message **without calling any tools** (no commands, searches, file
    reads or scheduling), then stop:
    1.  Say that Device Run is for non-interactive batch jobs, so you will not
        submit a Device Run session.
    2.  Point the user to an interactive Device Streaming reservation with the
        `developer-device-platform-basics` skill (or
        https://docs.cloud.google.com/device-streaming/docs/overview.md.txt),
        and suggest installing the skill.
    3.  Warn that an interactive reservation is also billed to the active
        Google Cloud project.

### Keep answers fast

Prefer this skill and `gcloud beta device-run ... --help` over broad web
searches for Device Run syntax. If `gcloud` or the `beta` component is not
installed, fall back to the official documentation at
https://docs.cloud.google.com/developer-device-platform/device-run.md.txt and
https://docs.cloud.google.com/sdk/gcloud/reference/beta/device-run. For dry
runs, show the commands instead of running them.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Setup

Run these checks once per environment. Do not assume tools are installed, and
do not install or update software without the user's approval.

1.  **gcloud CLI**: Check that gcloud is installed and has Device Run commands:

    ```bash
    gcloud --version
    gcloud beta device-run sessions submit android-executable --help >/dev/null
    ```

    If gcloud is missing, point the user to
    https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt. If the `beta`
    component or the Device Run commands are missing, **ask the user** before
    running `gcloud components install beta` or `gcloud components update`.

2.  **Authentication**: Check the active account. On a Compute Engine or other
    remote VM, the active account may be the VM's default service account
    (`...@...iam.gserviceaccount.com`), which often lacks the scopes Device Run
    and billing calls need (`No service account scopes specified`). If there is
    no active account, or only such a service account, ask the user to sign in.
    `--update-adc` also updates Application Default Credentials in the same
    flow; add `--no-launch-browser` in SSH or remote terminals:

    ```bash
    gcloud auth list --filter=status:ACTIVE --format="value(account)"
    gcloud auth login --update-adc
    ```

3.  **Project**: Use the user's active project, or the one they name. Never
    hardcode a project, and don't change the active project without asking.

    ```bash
    export PROJECT_ID=$(gcloud config get project)
    # Only if the user asks to switch:
    gcloud config set project PROJECT_ID
    ```

4.  **Billing**: Device Run is billed to the project. Check that billing is
    enabled; if it isn't, stop and tell the user.

    ```bash
    gcloud billing projects describe "${PROJECT_ID}" \
      --format="value(billingEnabled)"
    ```

5.  **Enable the Device Run API** (if not already enabled; ask first):

    ```bash
    gcloud services enable devicerun.googleapis.com --project="${PROJECT_ID}"
    ```

6.  **IAM roles**: The user needs `roles/devicerun.admin`,
    `roles/serviceusage.serviceUsageConsumer` and `roles/viewer` on the
    project. To read inputs from a bucket in another project, grant the DDP
    service agent `roles/storage.objectViewer` on that bucket (see
    https://docs.cloud.google.com/developer-device-platform/device-run/share-storage.md.txt).

7.  **Bucket**: Sessions store inputs and outputs in Cloud Storage. Without
    `--bucket-name`, gcloud uses or creates `gs://${PROJECT_ID}-devicerun`.
    For project IDs that contain `:`, `.` or `google`, gcloud replaces them
    (with `-`, `-` and `elgoog`) before adding `-devicerun`; read the actual
    bucket from the `Result files` URI printed by `submit` or `describe`. A
    bucket named explicitly with `--bucket-name` MUST already exist. Pass the
    bucket name only (no `gs://`, no path). Inputs and outputs under
    `gs://<bucket>/automation/` are kept until you delete them or a Cloud
    Storage lifecycle rule expires them, and storage is billed meanwhile.

## Core workflow

1.  **Pick devices.** Users usually name devices the way they are sold ("Pixel
    10", "Galaxy S22"), while `--device` needs a catalog ID such as
    `frankel-36` (codename + Android API level). Resolve names to IDs from the
    live catalog with
    [device_selection.md](references/device_selection.md); never guess an ID
    from memory. If a device is offered on several Android versions and the
    user didn't name one, list the versions, recommend one, and let the user
    pick one, several (one job each) or all; never pick silently. Before
    submitting, show the user the resolved ID, the device name and the Android
    version, and call out any other choice you made for them (physical vs
    virtual, variant).

2.  **Stage inputs.** `--executable`, `--test`, `--target-app` and the source
    side of `--other-files-to-push` accept `gs://` paths or local paths. Local
    files are uploaded automatically into a fresh
    `automation/inputs/<timestamp>/` folder, so prefer local paths for files
    that change between runs (scripts, freshly built binaries). Upload large,
    reused files (models, datasets) to the bucket once and reference them by
    `gs://` path.

3.  **Confirm cost.** **Explicit user confirmation required.** Device Run
    sessions are billed to the active Google Cloud project. Before submitting,
    tell the user the project (`${PROJECT_ID}`), the devices, the number of
    jobs, and the timeout, warn that this incurs charges, and STOP until they
    approve. Include this billing warning in **every** answer that shows a
    submit command, even when you only explain the steps or the user will run
    the command themselves.

4.  **Submit.** Pick the submit type:

    *   Native executable or shell script: see
        [android_executable.md](references/android_executable.md).
    *   Instrumentation test APK: see
        [instrumentation.md](references/instrumentation.md).
    *   Same binary with several configurations (different flags, inputs or
        environment variables) per device: see
        [multi_config_runs.md](references/multi_config_runs.md).

5.  **Wait.** For runs longer than a few minutes, submit with `--async` and
    follow [session_lifecycle.md](references/session_lifecycle.md).

6.  **Collect results.** Download and map artifacts to devices with
    [results.md](references/results.md).

7.  **Report** one row per device: device ID, job folder (`job-NNN`), result,
    key outputs, and the `gs://` path of the session folder. Call out failed,
    timed-out or cancelled jobs explicitly instead of dropping them.

## Rules

*   **Always set the timeout.** `--executable-timeout` (or
    `--instrumentation-timeout`) defaults to `5m`; the valid range is `1m` to
    `3h`. Estimate the run time and set it explicitly.
*   **Arguments are comma-separated.** Each element of `--executable-args`
    becomes one argument. Rewrite space-separated command lines. If a value
    contains a comma, use the `^SEP^` prefix (see
    [android_executable.md](references/android_executable.md)).
*   **No shell in the direct call.** With a binary as `--executable` there is no
    shell: set environment variables with `--executable-env-vars`, not `export`.
*   **Do not overwrite shared inputs.** DDP fetches inputs when a job starts.
    Never overwrite a `gs://` script or binary that a pending session uses; use
    local paths (auto-uploaded) or a unique `gs://` path per run.
*   **Label sessions** with `--labels` (for example `purpose=smoke,build=1234`)
    so they are easy to find later.
*   **Poll politely.** Never poll in a tight loop; poll every 30 to 60 seconds
    and report progress (see
    [session_lifecycle.md](references/session_lifecycle.md)).
*   **Cancel on request.** If the user wants to stop, cancel the session (see
    [session_lifecycle.md](references/session_lifecycle.md)) and tell the
    user it was cancelled.
*   **Do not use the Device Streaming API** (`devicestreaming.googleapis.com`,
    `deviceSessions`) to run batch jobs; that is for interactive leases.

## Reference index

*   [device_selection.md](references/device_selection.md): map device names
    such as "Pixel 10" to catalog IDs, OS versions, physical vs virtual.
*   [android_executable.md](references/android_executable.md): flags, direct
    call, shared libraries, script as executable.
*   [instrumentation.md](references/instrumentation.md): APK tests, sharding,
    test targets.
*   [session_lifecycle.md](references/session_lifecycle.md): sync vs async,
    wait, describe, cancel, status and result types.
*   [results.md](references/results.md): bucket layout, job-to-device mapping,
    logs.
*   [multi_config_runs.md](references/multi_config_runs.md): run
    the same binary with several configurations per device.
*   [troubleshooting.md](references/troubleshooting.md): common failures.
