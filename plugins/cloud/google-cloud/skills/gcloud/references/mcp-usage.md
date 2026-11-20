# Cloud CLI Remote MCP Server Usage

Google Cloud resources can be managed via the Model Context Protocol (MCP),
allowing AI agents to interact with Google Cloud using structured tool calls
rather than directly executing local shell commands.

MCP operations for `gcloud` are executed through the **Cloud CLI remote MCP
server** (backed by the Cloud CLI Execution API, `cloudcli.googleapis.com`).

## Server Endpoint & Tool Overview

-   **Server Endpoint:** `https://cloudcli.googleapis.com/mcp`
-   **Transport:** HTTP (JSON-RPC 2.0)
-   **API Name:** Cloud CLI Execution API (`cloudcli.googleapis.com`)
-   **Available Tool:** `run_gcloud_command`

The `run_gcloud_command` tool executes a single `gcloud` command securely in a
managed remote environment on behalf of the user.

## Client Configuration (`mcp_config.json`)

To connect an MCP client (such as Antigravity) to the remote Cloud CLI MCP
server,
configure the server entry in `mcp_config.json` with `authProviderType` set to
`"google_credentials"`:

```json
{
  "mcpServers": {
    "gcloud-remote": {
      "serverUrl": "https://cloudcli.googleapis.com/mcp",
      "authProviderType": "google_credentials"
    }
  }
}
```

> [!IMPORTANT] Specifying `"authProviderType": "google_credentials"` is
> mandatory. It instructs the MCP client to attach Application Default
> Credentials (ADC) with the `https://www.googleapis.com/auth/cloud-platform`
> OAuth scope. Omitting this field will cause the client to send unauthenticated
> requests, resulting in `401 Unauthorized` errors.

## Prerequisites & IAM Requirements

Before using the Cloud CLI remote MCP server, the target project and calling
identity must satisfy two mandatory prerequisites:

### 1. API Enablement

The Cloud CLI Execution API (`cloudcli.googleapis.com`) must be enabled on the
target project.

-   **Via Google Cloud Console (No CLI required):**

    1.  Open the [Google Cloud Console](https://console.cloud.google.com/).
    2.  Navigate to **APIs & Services** --> **Library**.
    3.  Search for **Cloud CLI Execution API** (or open the
        [Cloud CLI Execution API Library Page](https://console.cloud.google.com/apis/library/cloudcli.googleapis.com)).
    4.  Select the target project from the project dropdown.
    5.  Click **Enable**.

-   **Via `gcloud` CLI:**

    ```bash
    gcloud services enable cloudcli.googleapis.com --project={project_id}
    ```

### 2. IAM Roles & Permissions

-   **MCP Access Role:** The caller identity must hold the **MCP Tool User**
    role (`roles/mcp.toolUser`, which grants the `mcp.tools.call` permission) on
    the target project.
-   **Downstream Resource Roles:** The caller identity must also hold standard
    IAM permissions on the underlying resources being queried or modified (e.g.,
    `roles/compute.viewer`, `roles/run.developer`).

> [!CAUTION] If either the Cloud CLI Execution API is not enabled or the caller
> lacks the `roles/mcp.toolUser` role, the endpoint returns **`403 Forbidden`**
> during both tool discovery (`tools/list`) and tool invocation (`tools/call`).

## Tool Parameters

Calls to `run_gcloud_command` accept the following parameters:

-   **`command`** (string, required): The full `gcloud` command line string to
    execute (e.g., `"gcloud compute instances list --project={resource_project}
    --format=json"`).
-   **`project`** (string, required): The resource name of the Google Cloud
    project hosting the Cloud CLI Execution API in the format
    `"projects/{api_project}"` (e.g., `"projects/my-api-project"`).
-   **`input_files`** (list of objects, optional): Files to provision in the
    remote execution environment before running the command. Each item contains
    a relative `path` and string `contents`.

> [!IMPORTANT] **API Host Project vs. Resource Project Context:**
>
> -   The top-level **`project`** parameter (`"projects/{api_project}"`) is used
>     **strictly for quota, billing, and API enablement** of the
>     `cloudcli.googleapis.com` API itself. It does NOT set the project context
>     for the command being executed.
> -   For **project-scoped commands**, you MUST explicitly include
>     `--project={resource_project}` within the `command` string. The target
>     `{resource_project}` does NOT have to be the project hosting the Cloud CLI
>     Execution API.
> -   For **non-project-scoped commands** (such as billing, folder, or
>     organization queries), you MUST include
>     `--billing-project={billing_project}` in the `command` string if the
>     underlying API requires a quota project.

### Example Invocations

#### 1. Basic Command Execution

```json
{
  "command": "gcloud compute instances list --project=my-resource-project --format=json",
  "project": "projects/my-cloudcli-api-project"
}
```

#### 2. Command with Input Files

```json
{
  "command": "gcloud run services replace service-config.yaml --region=us-central1 --project=my-resource-project",
  "project": "projects/my-cloudcli-api-project",
  "input_files": [
    {
      "path": "service-config.yaml",
      "contents": "apiVersion: serving.knative.dev/v1\nkind: Service\nmetadata:\n  name: my-service\n..."
    }
  ]
}
```

## Response Structure

The tool returns an execution response containing:

-   `exit_code`: Numeric exit status of the command execution. **This is the
    primary and authoritative indicator of command success or failure.**
-   `stdout`: Standard output stream from the command.
-   `stderr`: Standard error stream from the command.
-   `output_files`: Any files generated by the command.

> [!NOTE] - **Exit Code Authority:** A command is successful if and only if
> `exit_code == 0`. A non-zero `exit_code` indicates failure.
>
> -   **Informational `stderr` Output:** In `gcloud`, `stderr` frequently
>     contains standard status messages, progress updates, and asynchronous
>     tracking IDs (such as `--async` operation IDs) even when the command
>     executes successfully (`exit_code == 0`). Agents MUST NOT assume a command
>     failed merely because `stderr` is non-empty.
> -   **Error Diagnosis:** If `exit_code != 0`, diagnostic error messages may
>     appear in either `stderr` or `stdout`. Inspect both streams to understand
>     the failure and formulate a correction.

## Prohibited & Unsupported Commands

The Cloud CLI remote MCP server operates in a sandboxed, non-interactive
environment. The following list shows a few example `gcloud` commands that
aren't supported (such as command groups that manage local machine
configuration, credentials, interactive shells, or metadata). This list is
non-exhaustive and subject to the addition or removal of commands without
notice:

-   `gcloud auth` (Local authentication & credential management)
-   `gcloud config` (Local CLI configuration profiles and properties)
-   `gcloud iam service-accounts` (Service account management)
-   `gcloud init` (Interactive setup wizard)
-   `gcloud survey` (User feedback & surveys)
-   `gcloud compute ssh` / `gcloud app instances ssh` (Interactive SSH shells)

## Safety & Execution Guidelines

-   **Mandatory User Consent for Mutations:** Destructive or state-changing
    commands (such as `create`, `delete`, `update`, or `patch`) modify or
    destroy GCP resources. These commands must NOT be invoked autonomously
    unless the user has explicitly authorized the action.
-   **Asynchronous Operations (`--async`):** For long-running operations (such
    as creating VM instances, GKE clusters, or database instances), always
    append the `--async` flag in the `command` string to avoid execution
    timeouts.
-   **Data Reduction & Formatting:** Use `--format=json`, `--filter`, and
    `--limit` in the `command` string to constrain output volume and prevent
    context window bloat.
-   **Non-Interactive Execution (`--quiet`):** Include `--quiet` (or `-q`) on
    commands that might otherwise prompt for interactive user confirmation.
