# Cloud Storage MCP Usage

The Cloud Storage Model Context Protocol (MCP) server lets an agent perform
storage operations through structured tool calls instead of shelling out to the
CLI or building HTTP requests. It comes in two forms:

-   **Remote server (managed):** A Google-hosted HTTP endpoint. No installation;
    authenticates with OAuth 2.0 and IAM. Best for inspecting buckets and
    objects, small text reads and writes, and remote management.

-   **Local server (MCP Toolbox):** The open-source
    [MCP Toolbox](https://github.com/googleapis/mcp-toolbox) running its
    prebuilt `cloud-storage` tools on your machine over stdio. Best when you
    need local filesystem integration (upload, download), copy/move operations,
    or larger payloads.

## Choosing a Server

| Your need                                               | Use               |
| :------------------------------------------------------ | :---------------- |
| Zero setup: inspect buckets, read small text/PDF/image  | Remote server     |
: objects                                                 :                   :
| Small text writes from a managed endpoint               | Remote server     |
| Enterprise guardrails: Model Armor screening of tool    | Remote server     |
: calls, IAM deny policies (e.g. enforce read-only)       :                   :
| Upload/download local files, binary content, or objects | Local MCP Toolbox |
: over 8 MiB                                              :                   :
| Copy, move, or rename objects; bucket metadata/IAM      | Local MCP Toolbox |
: inspection                                              :                   :

When requirements conflict, the hard limits win: the remote server cannot write
binary content, exceed 8 MiB per read or write, or touch the local filesystem —
those workloads need the Toolbox (or the [CLI](cli-api-usage.md)). Model Armor
and IAM deny policies protect only the Google-hosted remote server, so
security-sensitive deployments that fit within its limits should prefer remote.

## Remote Server (Managed)

The remote server runs on Google's infrastructure at a single global endpoint:

-   **Endpoint:** `https://storage.googleapis.com/storage/mcp`
-   **Transport:** HTTP
-   **Auth:** OAuth 2.0 with IAM. API keys are not accepted; every request
    requires IAM authorization. Callers need `roles/mcp.toolUser` plus the
    relevant `roles/storage.*` roles (for example, `roles/storage.objectViewer`
    to read, `roles/storage.objectCreator` to write).

Add it to your MCP client as an HTTP server. Because Google Cloud's remote MCP
servers require IAM authentication, you must configure client-side credentials
or headers (such as an OAuth 2.0 access token). Follow the
[Configure MCP in an AI application](https://docs.cloud.google.com/mcp/configure-mcp-ai-application)
guide for client-specific setup instructions (such as Claude Desktop, Claude
Code, or Gemini CLI).

For example, to manually configure Claude Code using a temporary access token,
place this in your client configuration (e.g. `.mcp.json` or
`~/.claude/mcp_servers.json`):

```json
{
  "mcpServers": {
    "cloud-storage": {
      "type": "http",
      "url": "https://storage.googleapis.com/storage/mcp",
      "headers": {
        "Authorization": "Bearer ACCESS_TOKEN",
        "User-Agent": "gcs-skills/1.0 (skill:google-cloud-storage-basics)"
      }
    }
  }
}
```

Tool calls follow standard JSON-RPC, for example:

```
POST /storage/mcp HTTP/1.1
Host: storage.googleapis.com
Content-Type: application/json
Authorization: Bearer OAUTH2_TOKEN

{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "id": "1",
  "params": {
    "name": "list_buckets",
    "arguments": {"projectId": "my-project"}
  }
}
```

**Limits:** Read and write operations are capped at 8 MiB. Reads are restricted
to text, PDF, and image content; writes are restricted to text. For larger
objects or binary writes, use the local MCP Toolbox, the
[CLI](cli-api-usage.md), or a [client library](client-library-usage.md).

### Defend Against Prompt Injection with Model Armor

Because the remote server is Google-hosted, you can protect it with
[Model Armor](https://docs.cloud.google.com/model-armor/model-armor-mcp-google-cloud-integration),
a service that screens MCP tool calls and responses to mitigate prompt
injection, malicious URLs, and sensitive-data disclosure. This server-side
protection applies only to the remote server, not the local Toolbox. Enable it
once per project with a Model Armor floor setting:

```bash
gcloud model-armor floorsettings update \
  --full-uri='projects/PROJECT_ID/locations/global/floorSetting' \
  --enable-floor-setting-enforcement=TRUE \
  --add-integrated-services=GOOGLE_MCP_SERVER \
  --google-mcp-server-enforcement-type=INSPECT_AND_BLOCK \
  --malicious-uri-filter-settings-enforcement=ENABLED
```

Floor settings apply project-wide and also affect other integrated services
(such as Vertex AI), not just MCP. Enable the prompt injection and jailbreak
filter only if your MCP traffic carries natural-language data.

### Restrict Tool Access with IAM Deny Policies

You can further lock down the remote server with
[IAM deny policies](https://docs.cloud.google.com/mcp/control-mcp-use-iam) that
block unwanted tool calls at the organization, folder, or project level. Deny
rules can match on the principal, the OAuth client ID, or tool properties — for
example, denying any tool that is not read-only (`tool.isReadOnly`) to prevent
an agent from creating, modifying, or deleting data.

## Local Server (MCP Toolbox)

MCP Toolbox is Google's open-source MCP server (formerly Gen AI Toolbox for
Databases). It ships a prebuilt `cloud-storage` tool source that exposes the
full set of bucket and object operations.

1.  **Download the binary.** The Toolbox ships as a standalone binary (or
    container image) — it is not published as an npm or pip package, so never
    configure it via `npx` or `pip`. Replace `VERSION` with the
    [latest release](https://github.com/googleapis/mcp-toolbox/releases) and
    pick your OS/architecture path:

    ```bash
    curl -L -o toolbox \
      https://storage.googleapis.com/mcp-toolbox-for-databases/VERSION/linux/amd64/toolbox
    chmod +x toolbox
    ```

2.  **Configure credentials.** The Toolbox uses Application Default Credentials
    (ADC) in every environment: locally via the command below, on GCP compute
    via the attached service account, and elsewhere (CI, on-prem) via workload
    identity federation. **Never download a service-account key file or set
    `GOOGLE_APPLICATION_CREDENTIALS` to one** — key files are a security
    liability and are never needed for the Toolbox.

    ```bash
    gcloud auth application-default login
    ```

3.  **Add it to your MCP client.** For example, in a Claude Code `.mcp.json`
    (the same `command`/`args` work for other clients such as Gemini CLI):

    ```json
    {
      "mcpServers": {
        "cloud-storage": {
          "command": "./PATH/TO/toolbox",
          "args": ["--prebuilt", "cloud-storage", "--stdio"],
          "env": {"CLOUD_STORAGE_PROJECT": "PROJECT_ID"}
        }
      }
    }
    ```

The identity behind ADC needs the `roles/storage.*` roles for the operations you
intend to call (for example, `roles/storage.objectAdmin` for copy, move, and
delete; `roles/storage.admin` to create or delete buckets).

## Available Tools

The two servers expose **different** tool sets. Tool names do not always match
across them: the remote server has `write_text` (which the Toolbox does not),
and the Toolbox has `write_object`, `download_object`, `upload_object`, and the
copy/move tools (which the remote server does not). Call only the tools that
exist on the server you are connected to.

**Remote server (8 tools):**

| Tool                  | Description                                        |
| :-------------------- | :------------------------------------------------- |
| `list_buckets`        | List buckets in a project.                         |
| `list_objects`        | List objects in a bucket.                          |
| `get_object_metadata` | Get an object's metadata.                          |
| `read_object`         | Read object content, including images and PDFs (up |
:                       : to 8 MiB).                                         :
| `create_bucket`       | Create a bucket.                                   |
| `delete_bucket`       | Delete a bucket.                                   |
| `write_text`          | Write text to an object (overwrites existing       |
:                       : content).                                          :
| `delete_object`       | Delete an object.                                  |

**Local MCP Toolbox (14 tools):**

| Tool                    | Description                                      |
| :---------------------- | :----------------------------------------------- |
| `list_buckets`          | List buckets in a project.                       |
| `list_objects`          | List objects in a bucket.                        |
| `get_bucket_metadata`   | Get a bucket's metadata.                         |
| `get_bucket_iam_policy` | Get a bucket's IAM policy.                       |
| `get_object_metadata`   | Get an object's metadata.                        |
| `read_object`           | Read UTF-8 text content (up to 8 MiB); binary is |
:                         : rejected — use `download_object`.                :
| `download_object`       | Download an object (including binary) to a local |
:                         : file.                                            :
| `create_bucket`         | Create a bucket.                                 |
| `delete_bucket`         | Delete a bucket.                                 |
| `write_object`          | Write text content to an object (overwrites).    |
| `upload_object`         | Upload a local file (including binary) to an     |
:                         : object.                                          :
| `copy_object`           | Copy an object.                                  |
| `move_object`           | Move (rename) an object; deletes the source.     |
| `delete_object`         | Delete an object.                                |

On the Toolbox, `read_object`/`write_object` handle UTF-8 text only and are
capped at 8 MiB; use `download_object`/`upload_object` for binary or large
files.

> [!CAUTION]
>
> **CRITICAL: You MUST stop and ask the user for explicit permission before
> calling any tool that deletes a bucket or object (`delete_bucket`,
> `delete_object`, `move_object` — which deletes the source) or overwrites
> existing content (`write_text`, `write_object`, `upload_object`).**

## Documentation

-   [Use the Cloud Storage MCP server](https://docs.cloud.google.com/storage/docs/use-cloud-storage-mcp)
-   [Cloud Storage MCP reference (tools)](https://docs.cloud.google.com/storage/docs/reference/mcp)
-   [Connect LLMs to Cloud Storage with MCP Toolbox](https://docs.cloud.google.com/storage/docs/pre-built-tools-with-mcp-toolbox)
-   [Google Cloud MCP servers overview](https://docs.cloud.google.com/mcp/overview)
-   [Configure MCP in an AI application](https://docs.cloud.google.com/mcp/configure-mcp-ai-application)
-   [Protect MCP servers with Model Armor](https://docs.cloud.google.com/model-armor/model-armor-mcp-google-cloud-integration)
-   [Control MCP use with IAM deny policies](https://docs.cloud.google.com/mcp/control-mcp-use-iam)
