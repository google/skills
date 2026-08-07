# Start ADB Forwarder

To forward ADB connection to the remote device, run the
`scripts/demo_adb_forwarder.py` script.

## Python Environment Setup

Before running the python script, ensure you have set up the virtual
environment:

1.  **Navigate to Scripts Directory**: Ensure your current working directory is
    the skill scripts directory (the directory containing
    `demo_adb_forwarder.py`) before running any of the following commands. If
    you are an agent, ensure you set the working directory (or `Cwd` parameter
    of your execution tool) to this directory. This is required because
    subsequent commands (like `pip install` and running scripts) use relative
    paths.

2.  **Virtual Environment**: Create and activate a dedicated local virtual
    environment:

    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install Dependencies**: Install the required client dependencies:

    ```bash
    pip install -r requirements.txt
    ```

> [!IMPORTANT] Every time you execute the python connection forwarder, you must
> ensure this virtual environment is activated first.

## Running the ADB Forwarder

1.  **Calculate Duration**: Calculate the remaining lifetime of the device
    session in seconds (the difference between `expireTime` and the current
    time) to align the forwarder's lifespan.

2.  **Start Connection Forwarder**: Start `demo_adb_forwarder.py` in the
    background with the calculated remaining duration passed via the `--ttl`
    argument. Run this command in the background using your environment's
    command execution capability.

    Run this command in local virtual environment:

    ```bash
    python3 demo_adb_forwarder.py --device_session {session_name} --ttl {remaining_seconds}
    ```

    Ensure you record the returned **Command ID**.

## Wait for Online and Parse Port

1.  **Monitor Output**: Monitor the background forwarder command output for the
    following log line: `ADB forwarding listening on localhost:{port}`

2.  **Extract Port**: Extract the `{port}` number. If this line does not appear
    within 2 minutes (typically under 1 minute), terminate the forwarder
    background process using your environment's process management capability,
    cancel the session, and report failure.
