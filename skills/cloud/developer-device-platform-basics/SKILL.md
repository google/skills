---
name: developer-device-platform-basics
description: >-
  Provides guidance and instructions on managing remote devices on Developer Device Platform (DDP).
  Use when reserving remote Android devices, establishing connection tunnels, checking session status, or extending/cancelling leases.
  Don't use for iOS or local device/hardware inquiries.
metadata:
  category: CloudInfrastructureAndServices
---

# Developer Device Platform

Developer Device Platform (DDP) is a Google fully managed, global infrastructure
providing access to a wide variety of physical and virtual devices.

> [!WARNING] Developer Device Platform (DDP) is currently at Preview.

> [!IMPORTANT] For all devicerun and devicestreaming API operations (reserving,
> status checking, stopping/canceling, updating, or listing a session), always
> verify and use the exact instructions and curl commands provided in the linked
> reference `.md` files.

## Authentication & Setup

**CRITICAL**: Before running any requests, you MUST ensure the environment is
correctly initialized by following these steps:

Before running any requests, verify if the `gcloud` executable is present. If
missing, refer to the official
[Google Cloud CLI Installation Guide](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt)
to install it on the current platform (Linux, macOS, Windows, etc.).

1.  **Google Cloud Authentication**: Authenticate with your Google Cloud
    credentials and configure active Application Default Credentials (ADC) for
    the Developer Device Platform:

    ```bash
    gcloud auth login --no-browser
    gcloud auth application-default login --no-browser
    ```

2.  **Enable APIs** (if not already enabled):

    ```bash
    gcloud services enable devicerun.googleapis.com devicestreaming.googleapis.com testing.googleapis.com --quiet
    ```

> [!NOTE] Cloud Testing API is needed for Device Streaming API during Preview.

3.  **Enable gcloud beta component**:

    ```bash
    gcloud components install beta
    ```

4.  **Setup Environment Variables**: Set up the required project variable and
    access token:

    ```bash
    export PROJECT_ID=$(gcloud config get project)
    export ACCESS_TOKEN=$(gcloud auth application-default print-access-token 2>/dev/null)
    ```

5.  **Python Environment**: For instructions on setting up the python virtual
    environment, see [start_adb_forwarder.md].

## Listing Available Devices

To find the correct `modelCode` and `osVersion` to use when starting a session,
you can list the available devices:

1.  **List Models**: Run the following command to list available Android device
    models:

    ```bash
    gcloud beta device-run devices list
    ```

    Use the `ID` column to find the value for the `CATALOG_ID` parameter to
    describe a specific device (e.g., `shiba-36`).

2.  **Describe a Model**: Run the API request to get more details about a
    specific model (e.g., supportedProducts, resolution). Always rely on the
    exact curl command and instructions provided in [describe_device.md].

## Starting a Device Session

When the user asks to reserve or connect to a device:

1.  **Check Device Availability**:

    Look up `CATALOG_ID` of the device using `Listing Available Devices`
    instructions. Check the device availability of the `CATALOG_ID` by using the
    exact curl command and instructions provided in [describe_device.md]. The
    device MUST contain "deviceStreaming" in "supportedProducts" to be reserved.

    If no specific device is specified, use `CATALOG_ID=shiba-34` (Pixel 8 on
    SDK 34).

    If `OS_VERSION` was not specified by the user, ask the user to select a
    version from the device list (preferring the version with the highest
    availability {"available": "AVAILABILITY_HIGH" }).

    If `OS_VERSION` is unavailable for `deviceStreaming`, do not reserve one.
    Prompt the user for an alternative `OS_VERSION`.

2.  **Extract Parameters**:

    *   `model_id`: `modelCode` from device details. Required.
    *   `version_id`: `osVersion` from device details. Required.

3.  **Reserve Device**:

    **Rule**: **Explicit User Confirmation Required**. Reserving a device incurs
    billing charges and creates cloud resources. The agent MUST ALWAYS warn the
    user explicitly about the billing costs that will be incurred on the active
    Google Cloud project (e.g., `${PROJECT_ID}`). You MUST STOP and ask for
    explicit approval before proceeding with any session creation commands.

    Then, run the API request with `model_id` and `version_id` to reserve the
    device. Always rely on the exact curl command and instructions provided in
    [reserve_device.md].

    Parse the response to get `session_name` (the session name, e.g.,
    `projects/${PROJECT_ID}/deviceSessions/session-xxxxxx`). If reservation
    fails, report the error.

4.  **Wait for Session to be Active**:

    While waiting for the device session to be provisioned, poll the session
    status until `"state"` is `"ACTIVE"`. See [session_status.md] for the exact
    curl command.

    Repeat this check every 5 seconds to prevent hitting API rate limit. If it
    does not become active within 2 minutes (typically under 1 minute), report
    failure and cancel the session. Once active, extract `expireTime` from the
    session JSON response and convert it to the user's local time in a
    human-readable format (e.g., "June 9, 2026 at 2:44 PM PDT").

5.  **Start Connection Forwarder**: Start the ADB forwarder script to forward
    connection to the remote device. Always rely on the exact command and
    instructions provided in [start_adb_forwarder.md]. Ensure you record the
    **Command ID**.

6.  **Wait for Online and Parse Port**: Wait for the forwarder to be online and
    extract the listening port. Always rely on the exact logic and instructions
    provided in [start_adb_forwarder.md].

7.  **Provide Instructions to User**:

    Once online, run `adb -s localhost:{port} shell getprop ro.product.model` to
    retrieve the device model name. Then, print a message directly to the user
    in the chat (do NOT create any artifact file) with the following
    instructions:

    ### Device is ready!

    ```
    Device Model: {device_model}
    OS Version: {version_id}
    ADB Address: localhost:{port}
    Session Expiration: {expire_time_human_readable_local}
    ```

8.  **Save Session State**: Save the `{session_name}` and `{command_id}` in your
    conversation memory/context so you can clean it up later.

## Viewing the Device Screen of a Reserved Device

The coding agent can directly interact with the remote device using `adb`. Users
may use a utility to display the screen and manually control the reserved device
in DDP. See [view_device.md] for an example utility.

## Stopping a Device Session

When the user asks to stop, cleanup, or release the device:

1.  **Identify Session**: Retrieve the active `{session_name}` and
    `{command_id}` from your context. If you don't have them, list active
    sessions first (see helper command below) to find the session name.

2.  **Cancel Session via API**: Cancel the session via the API. Always rely on
    the exact curl command and instructions provided in [cancel_session.md].

3.  **Terminate Connection Forwarder**: Terminate the background process
    matching `{command_id}` using your environment's process management
    capability.

4.  **Confirm**: Confirm to the user that the session has been cancelled and
    resources released.

## Change Device Session Expiration Time

When the user asks to change the expiration time of an active device session:

**Rule**: **Explicit User Confirmation Required**. Extending a device session
incurs additional billing charges and creates cloud resources. The agent MUST
ALWAYS warn the user explicitly about the extra billing costs that will be
incurred on the active Google Cloud project (e.g., `${PROJECT_ID}`). You MUST
STOP and ask for explicit approval before proceeding with any session extension
commands.

1.  **Extract Parameters**:

    *   `session_name`: The active session name.
    *   `ttl`: The new remaining duration (e.g., `3600s`). Derive the `ttl` if
        it's provided in another format.

2.  **Change Session via API**: Change the session via the API using
    `updateMask=ttl`. Always rely on the exact curl commands and instructions
    provided in [update_session_expiration.md].

3.  **Restart Connection Forwarder**:

    *   Run `adb disconnect localhost:{port}` to ensure the old forwarder
        connection is closed.
    *   Stop the old connection forwarder corresponding to `{command_id}`.
    *   Start a new connection forwarder by following Step 5 in "Starting a
        Device Session" (calculating the new `--ttl` duration in seconds and
        storing the newly returned Command ID).

4.  **Confirm**: Confirm to the user that the session duration has been updated
    and the connection forwarder has been restarted with the new TTL.

## Helper: List Active Sessions

To find active sessions if you lost context, always rely on the curl command and
instructions provided in [list_sessions.md].

## References

*   [gcloud device-run CLI]
*   [Device Streaming API]
*   [describe_device.md]
*   [reserve_device.md]
*   [session_status.md]
*   [start_adb_forwarder.md]
*   [view_device.md]
*   [cancel_session.md]
*   [update_session_expiration.md]
*   [list_sessions.md]

[gcloud device-run CLI]: https://docs.cloud.google.com/sdk/gcloud/reference/beta/device-run
[Device Streaming API]: https://docs.cloud.google.com/device-streaming/docs/reference/rest.md.txt
[describe_device.md]: references/describe_device.md
[reserve_device.md]: references/reserve_device.md
[session_status.md]: references/session_status.md
[start_adb_forwarder.md]: references/start_adb_forwarder.md
[view_device.md]: references/view_device.md
[cancel_session.md]: references/cancel_session.md
[update_session_expiration.md]: references/update_session_expiration.md
[list_sessions.md]: references/list_sessions.md
