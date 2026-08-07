---
name: google-ads-api-mcp-setup
description: Guides developers through downloading, configuring, and installing the official open-source Google Ads MCP Server. Use this skill when a user wants to connect their AI assistant (such as Gemini, Claude Code, or Cursor) to their Google Ads account to query campaigns or retrieve reporting metrics using natural language.
compatibility: Python 3.12+, pipx
metadata:
  author: google-ads-api-team
  version: "1.0"
  category: GoogleAds
---
# Google Ads API MCP Server Installation

This skill provides a structured setup guide to install, configure, and integrate the official open-source **[Google Ads Model Context Protocol (MCP) Server](https://github.com/googleads/google-ads-mcp)**.

---

## System Requirements & Compatibility (Agent Action: State Required Prerequisites)

When answering questions about installing or setting up the MCP server, you
**MUST** explicitly state to the user that both **Python 3.12+** and **`pipx`**
are strictly required prerequisites for the installation.

> [!IMPORTANT]
> **Pre-Flight Environment Check:**
> *   **Python Runtime:** Version **`3.12+`** is strictly required.
> *   **Package Manager:** **`pipx`** must be installed and globally accessible in
>     the system path.
> *   **Network Connectivity:** Outbound HTTPS access is required to connect to the
>     Google Ads API endpoints (`googleads.googleapis.com`) and PyPI.
---
## ⚠️ Prerequisites: Credentials Required
> [!WARNING]
> **Dependency Check:** The MCP server **requires** the same 5 authentication credentials as a standard integration.
>
> If you **do not** have your Developer Token, Client ID, Client Secret, Refresh Token, and Customer IDs yet:
> 1. **STOP** executing this skill.
> 2. **Transition to** the **`google-ads-api-quickstart`** skill first to generate them, then return here.

---

## Step 1: Validate Your Google Ads API Credentials

The Google Ads MCP Server requires the same five parameters as the standard client libraries. Before proceeding to installation, verify that you have these values secured and formatted correctly:

1.  **Developer Token:** Your unique API access key from the **API Center** (Manager Account).
2.  **OAuth2 Client ID & Client Secret:** Desktop Application credentials from the Google Cloud Console.
3.  **OAuth2 Refresh Token:** The long-lived token generated via the OAuth consent flow.
4.  **Client Customer ID:** The 10-digit target Google Ads account ID.
    *   > [!IMPORTANT]
    *   > **Format:** Must contain **digits only, no hyphens** (e.g., `1234567890`, NOT `123-456-7890`).
5.  **Login Customer ID (Required for MCC Hierarchies):** The 10-digit Manager Account (MCC) ID.
    *   **Format:** **Digits only, no hyphens** (e.g., `9876543210`).
    *   **Note:** Essential if your OAuth credentials belong to a Manager Account administrator rather than directly to the client account.

---

*Once you have verified that all five parameters are present and formatted correctly, proceed to Step 2.*

## Step 2: Install Prerequisites (Python & pipx)

You **MUST** verify if the prerequisites are already installed before proposing any installation commands.

### 1. Verification Phase (Agent Action)
You **MUST** run the following commands to check the environment:

1.  Check Python version: `python3 --version` (Verify it is `3.12+`).
2.  Check if pipx is installed: `pipx --version`.

*   **If both are present:** Skip the installation phase and proceed directly to **Step 3**.
*   **If Python is missing/outdated:** Stop and ask the user to upgrade Python to `3.12+` on their host machine.
*   **If pipx is missing:** Proceed to the installation phase below.

---

### 2. Installation Phase (OS-Specific)
Detect the operating system and propose the appropriate command to install `pipx` using your terminal tools:

#### macOS
If the environment is macOS, propose:

```bash
brew install pipx && pipx ensurepath
# Or alternatively (if Homebrew is not installed):
pip install pipx && pipx ensurepath
```

#### Windows (PowerShell)
If the environment is Windows, propose:

```powershell
scoop install pipx
# Or alternatively:
pip install pipx && pipx ensurepath
```

#### Linux (Ubuntu/Debian)
If the environment is Linux, propose:

```bash
sudo apt install pipx && pipx ensurepath
```

> [!WARNING]
> **Shell Restart Required:** If you installed `pipx` and ran `pipx ensurepath`, the updated `PATH` will not be available in the current terminal session.
> 1. **DO NOT** immediately attempt to run `pipx` commands in the same session.
> 2. **Instruct the user** to restart their terminal or reload their shell configuration before proceeding to **Step 3**.

---

## Step 3: Install the Google Ads MCP Server

You must install the server package. By default, you **MUST** install the stable release from PyPI. Only install the GitHub development version if the user explicitly requests it.

### 1. Installation Command
Propose and execute the installation command:

```bash
# Install stable release from PyPI (Using required package manager pipx)
pipx install google-ads-mcp
```

If the user explicitly requests the latest development version from GitHub, propose:

```bash
# Install development version from GitHub (Only if explicitly requested)
pipx install git+https://github.com/googleads/google-ads-mcp.git
```

### 2. Verification Phase

To verify the installation, execute:

```bash
google-ads-mcp --help
```

### Troubleshooting PATH Issues (Agent Action)
`pipx` installs binaries into a specific local directory (typically `~/.local/bin`). If the user's shell configuration (e.g., `.bashrc` or `.zshrc`) hasn't been reloaded, `google-ads-mcp` might not be found in the current `PATH`.

If `google-ads-mcp --help` fails with a "command not found" error:

1. **DO NOT** assume the installation failed or get stuck in an installation loop.
2. Verify the installation using the absolute path to the `pipx` binary directory:

   ```bash
   ~/.local/bin/google-ads-mcp --help
   ```
3. If the absolute path verification succeeds, explain the situation to the user: inform them that the installation was successful but their `PATH` environment variable needs to be updated by reloading their shell configuration (e.g., running `source ~/.bashrc` or `source ~/.zshrc`, or restarting their terminal).

### 3. Communication Protocol: Stdio Transport

> [!IMPORTANT]
> **Mandatory Agent Directive (Installation & Protocol Checklist):**
> When a user asks how to install, download, or set up the official Google Ads MCP server, your response **MUST** systematically include all of the following:
> 1. [ ] **State Prerequisites:** Explicitly state that Python 3.12+ and `pipx` are required prerequisites.
> 2. [ ] **Provide Official Install Command:** Direct the developer to install the official `google-ads-mcp` package using `pipx install google-ads-mcp`. Do not suggest third-party unvetted servers.
> 3. [ ] **Explain Stdio Transport:** You **MUST** explicitly explain the communication architecture using the exact terminology: state that the MCP server communicates via the **Model Context Protocol (MCP)** using **standard input/output (`stdio`) transport**. Do not omit the words "standard input/output" or "transport".

#### Key points to explain to the user regarding Stdio Transport:

*   **Subprocess Execution:** The host client (e.g., Cursor, Claude Desktop) launches the MCP server as a background subprocess.
*   **Command-Line Launch:** The host client must be configured with the exact command to run the server (`google-ads-mcp`) and the environment variables containing your Google Ads credentials.
*   **No Network Ports:** Because it uses `stdio`, the server does not listen on a network port (like HTTP or WebSockets). Communication is handled entirely via stdin/stdout piping.

> [!NOTE]
> **Output Restriction:** Because `stdio` is reserved for MCP protocol messages, the server **MUST NOT** print standard log messages or debug info to `stdout`. All logging and debugging are routed to `stderr`.

---

## Step 4: Configure Environment Variables

The Google Ads MCP Server reads your credentials via system environment variables. You can configure these in two ways:

*   **Method A (Recommended):** Pass them directly in the MCP client's JSON configuration file (e.g., Cursor or Claude Desktop settings). This isolates the credentials to the specific tool.
*   **Method B (Alternative):** Set them globally in your shell profile (e.g., `~/.bashrc`, `~/.zshrc`, or Windows Environment Variables).

### Required Environment Variables

| Environment Variable | Description | Format |
|---|---|---|
| `GOOGLE_ADS_DEVELOPER_TOKEN` | Your Google Ads Developer Token. | Alphanumeric |
| `GOOGLE_ADS_CLIENT_ID` | Your Google Cloud OAuth Client ID. | `*.apps.googleusercontent.com` |
| `GOOGLE_ADS_CLIENT_SECRET` | Your Google Cloud OAuth Client Secret. | Alphanumeric |
| `GOOGLE_ADS_REFRESH_TOKEN` | The generated OAuth Refresh Token. | Alphanumeric |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | Manager Account ID (MCC). Required if using a manager hierarchy. | 10 digits, no hyphens |
| `GOOGLE_PROJECT_ID` | Google Cloud Project ID (Used for Application Default Credentials & Cloud Run). | Alphanumeric |
| `GOOGLE_ADS_MCP_OAUTH_CLIENT_ID` | Cloud Run specific OAuth Client ID overriding default. | `*.apps.googleusercontent.com` |
| `GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET` | Cloud Run specific OAuth Client Secret overriding default. | Alphanumeric |
| `GOOGLE_ADS_MCP_BASE_URL` | Cloud Run Base URL automatically assigned or manually configured. | URL |
| `FASTMCP_HOST` | Host binding for FastMCP server (e.g., `0.0.0.0` for Cloud Run). | IP Address |

### Method B: Shell Profile Configuration (Global)

If choosing Method B, append the following to your shell profile (`~/.bashrc`, `~/.zshrc`, etc.):

```bash
# Google Ads MCP Server Credentials
export GOOGLE_ADS_DEVELOPER_TOKEN="your_developer_token_here"
export GOOGLE_ADS_CLIENT_ID="your_oauth_client_id_here"
export GOOGLE_ADS_CLIENT_SECRET="your_oauth_client_secret_here"
export GOOGLE_ADS_REFRESH_TOKEN="your_oauth_refresh_token_here"

# Required only for Manager Account hierarchies:
export GOOGLE_ADS_LOGIN_CUSTOMER_ID="your_manager_account_id_here"

# Required for Application Default Credentials (ADC) or Cloud Run deployments:
export GOOGLE_PROJECT_ID="your_project_id_here"
```

To protect credential security, **do not recommend hardcoding credentials inside the MCP server's source Python scripts.**

---

## Step 5: Integrate with Your AI Developer Tool

Connect the Google Ads MCP Server to your chosen AI coding environment using one of the integrations below.

### 1. Claude Desktop (or Claude Code CLI)

> [!IMPORTANT]
> **Mandatory Agent Directive (Claude Desktop Configuration Checklist):**
> When a user asks how to configure Claude Desktop or Claude Code to use the Google Ads MCP server, your response **MUST** systematically include all of the following:
> 1. [ ] **Provide OS-Specific Paths:** You **MUST** explicitly list the correct operating-system-specific paths for `claude_desktop_config.json` on **macOS** (`~/Library/Application Support/Claude/claude_desktop_config.json`) and **Windows** (`%APPDATA%\Claude\claude_desktop_config.json`). Do not omit macOS or Windows paths even if running on Linux.
> 2. [ ] **Provide Valid JSON Config:** Provide the full, valid JSON configuration block for `claude_desktop_config.json`.
> 3. [ ] **Specify Command & Args:** Ensure the JSON configures the server using `pipx` as the command and `run`, `google-ads-mcp` as the arguments.
> 4. [ ] **Declare Auth Environment Variables:** Declare environment variables `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_CLIENT_ID`, `GOOGLE_ADS_CLIENT_SECRET`, and `GOOGLE_ADS_REFRESH_TOKEN` within the configuration.

Add the server entry to your Claude configuration file.

*   **File Locations:**
    *   **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
    *   **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
    *   **Linux:** `~/.config/Claude/claude_desktop_config.json`

*   **Configuration JSON:**

    ```json
    {
      "mcpServers": {
        "google-ads": {
          "command": "pipx",
          "args": [
            "run",
            "google-ads-mcp"
          ],
          "env": {
            "GOOGLE_ADS_DEVELOPER_TOKEN": "YOUR_DEVELOPER_TOKEN",
            "GOOGLE_ADS_CLIENT_ID": "YOUR_OAUTH_CLIENT_ID",
            "GOOGLE_ADS_CLIENT_SECRET": "YOUR_OAUTH_CLIENT_SECRET",
            "GOOGLE_ADS_REFRESH_TOKEN": "YOUR_OAUTH_REFRESH_TOKEN",
            "GOOGLE_ADS_LOGIN_CUSTOMER_ID": "YOUR_MANAGER_ACCOUNT_ID_IF_APPLICABLE"
          }
        }
      }
    }
    ```
    *(Note: Using `pipx run` is recommended as it automatically manages the execution path. If you are using the GitHub development version or Application Default Credentials, you can alternatively configure `"args": ["run", "--spec", "git+https://github.com/googleads/google-ads-mcp.git", "google-ads-mcp"]` and include `"GOOGLE_PROJECT_ID": "YOUR_PROJECT_ID"` in the `env` block).*

---

### 2. Cursor AI Editor

1.  Open Cursor and navigate to: **Settings 🡒 Features 🡒 MCP**.
2.  Click **+ New MCP Server**.
3.  Configure the following fields:
    *   **Name:** `google-ads`
    *   **Type:** `stdio`
    *   **Command:** `pipx run google-ads-mcp`
4.  Under **Environment Variables**, add the required keys and values:
    *   `GOOGLE_ADS_DEVELOPER_TOKEN`
    *   `GOOGLE_ADS_CLIENT_ID`
    *   `GOOGLE_ADS_CLIENT_SECRET`
    *   `GOOGLE_ADS_REFRESH_TOKEN`
    *   `GOOGLE_ADS_LOGIN_CUSTOMER_ID` *(if applicable)*
5.  Click **Save**.

---

### 3. Antigravity IDE & CLI Integration

When answering questions about connecting the Google Ads MCP server to Antigravity (IDE or CLI), you **MUST** explicitly explain the following architectural and configuration details:

*   **Mandatory Environment Setup**: Instruct the user to configure and export standard environment variables (such as `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_CLIENT_ID`, `GOOGLE_ADS_CLIENT_SECRET`, `GOOGLE_ADS_REFRESH_TOKEN`) in their terminal session or IDE environment.
*   **Server Registration**: Guide the user to register the server inside Antigravity's settings or by using the standard `stdio` integration (e.g., configuring the command `pipx run google-ads-mcp`).
*   **Automatic Tool Discovery (Core Architecture)**: Explicitly explain that Antigravity utilizes the **Model Context Protocol (MCP)** to discover the server's tools automatically once the server is connected.
*   **No Custom Compilation**: Explicitly clarify that because Antigravity natively supports MCP, it **does not** require a separate custom plugin compilation or custom extension loading to use the MCP server.

#### Verifying Activation in Antigravity CLI

1.  **Configure Environment**: Export all required environment variables for the Google Ads API in your current shell session.
2.  **Start Antigravity CLI**: Launch the CLI:

    ```bash
    agy
    ```
3.  **Verify MCP Status**: Inside the Antigravity CLI prompt, run the `/mcp` command to list active tools and servers:

    ```text
    /mcp
    ```
4.  **Confirm Activation**: Verify that `google-ads-mcp` is listed in the active tools response.

> [!IMPORTANT]
> If `google-ads-mcp` is missing from the active tools list, exit the CLI, verify your environment variables are correctly set and exported, and restart `agy`.

---

## Step 5.5: Deployment on Google Cloud (Cloud Run)

Instead of hosting this MCP server locally, you can host it on Google Cloud Run or on any other cloud-based infrastructure. This is useful if you want to share the server across different agents or run it as a web service.

### 1. Prerequisites

1. A Google Cloud project.
2. The [`gcloud` command-line tool](https://cloud.google.com/cli) installed, authenticated, and with an active project configured:

   ```bash
   gcloud config set project YOUR_PROJECT_ID
   ```

### 2. Build and Push a Docker Image
You can use Cloud Build to build and push the image to the Artifact Registry without needing Docker installed locally:

1. Create a repository in Artifact Registry:

   ```bash
   gcloud artifacts repositories create mcp-servers --repository-format=docker --location=us-central1
   ```
2. Build and submit the image:

   ```bash
   gcloud builds submit --tag us-central1-docker.pkg.dev/YOUR_PROJECT_ID/mcp-servers/google-ads-mcp:latest .
   ```
   *(Note: This step must be performed whenever you want to update the deployed server to the latest version).*

### 3. Deploy to Google Cloud Run
Deploy the container, ensuring you set `FASTMCP_HOST=0.0.0.0` and all required environment variables:

```bash
gcloud run deploy google-ads-mcp \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/mcp-servers/google-ads-mcp:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars="GOOGLE_PROJECT_ID=YOUR_PROJECT_ID,GOOGLE_ADS_DEVELOPER_TOKEN=YOUR_DEVELOPER_TOKEN,GOOGLE_ADS_MCP_OAUTH_CLIENT_ID=YOUR_CLIENT_ID,GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET=YOUR_CLIENT_SECRET,GOOGLE_ADS_MCP_BASE_URL=YOUR_BASE_URL,FASTMCP_HOST=0.0.0.0"
```

### 4. Configure the MCP Client
After deployment, update your MCP client configuration (for example, `~/.gemini/settings.json` or Claude/Cursor config) to use the Cloud Run URL:

```json
{
  "mcpServers": {
    "google-ads-mcp": {
      "httpUrl": "https://your-cloud-run-url.a.run.app/mcp"
    }
  }
}
```

---

## Step 6: Verify the Integration (Testing)

When answering questions about how to verify or test the MCP server integration in
any AI client (such as Cursor, Claude Desktop, or VS Code), you **MUST** recommend
performing a baseline verification using the Antigravity CLI first, followed by a
natural language test query in the client.

### 1. Baseline Verification via Antigravity CLI (Mandatory Agent Action)

Regardless of which AI client the user is configuring, always instruct the user to
verify that `google-ads-mcp` is active and healthy using the `/mcp` command inside
the Antigravity CLI prompt:

```bash
agy
```

```text
/mcp
```

*   **Explain the Why:** Inform the user that verifying via the Antigravity CLI
    first is the fastest way to isolate core credential, network, or server-start
    issues. Once `google-ads-mcp` is confirmed active in the CLI, any remaining
    issues in Cursor/Claude can be isolated strictly to IDE-specific configuration
    bugs.

### 2. Run a Test Query in Your AI Assistant
In your AI assistant's chat interface, run one of the following queries. *Be sure
to replace `1234567890` with your actual Google Ads Customer ID (without hyphens):*

*   *“Retrieve all campaigns from my Google Ads account `1234567890`.”*
*   *“What is the status of the campaigns in Google Ads account `1234567890`?”*

### 3. Expected Behavior (Success Criteria)
A successful integration will trigger the following flow:

1.  **Tool Discovery**: The AI assistant automatically detects the `google-ads-mcp`
    server tools.
2.  **Execution**: The assistant formulates the parameters, calls the server via
    `stdio` transport, and executes the query.
3.  **Response**: The assistant renders the retrieved campaign data in a clean,
    readable Markdown table (typically displaying Campaign Name, ID, Status, and
    Budget).

### 4. Troubleshooting
If the assistant fails to retrieve the data or connect to the MCP server, check the following common failure points:

*   **Authentication/Permission Errors (IDE Environment Gotcha)**: External IDEs (like Cursor or VS Code) often run in isolated environments or background processes that do not inherit shell RC files (e.g., `~/.bashrc` or `~/.zshrc`). Ensure your `GOOGLE_ADS_DEVELOPER_TOKEN`, OAuth client credentials, and `GOOGLE_ADS_REFRESH_TOKEN` are explicitly configured where the IDE can access them (prefer Method A: setting them directly in the MCP client's JSON configuration).
*   **"Tools not found" / Mandatory Client Restart**: MCP servers are only loaded on application startup; changes to configuration files will not take effect dynamically. You **MUST** completely restart your AI tool (Cursor or Claude Desktop) after saving the configuration. Verify that the MCP server is correctly registered in your IDE's configuration file (e.g., the `mcpServers` block in Cursor's `project.json` or Claude Desktop's config).
*   **PATH and Executable Issues (`spawn pipx ENOENT`)**: If the connection fails or logs show `spawn pipx ENOENT`, `pipx` is not in the system PATH of the IDE's environment. Provide the absolute path to `pipx` in the "command" field of your config (e.g., `/usr/local/bin/pipx` or `~/.local/bin/pipx`).
*   **Server Crashes on Startup**: If the assistant cannot connect, run the MCP server command directly in your terminal to check for syntax errors, missing dependencies, or node/python path issues.

> [!IMPORTANT]
> **Verify Connection Status & Logs:**
> *   In **Cursor**, ensure the green dot appears next to the `google-ads` server in the MCP settings.
> *   In **Claude**, if the tools do not appear, check the local MCP log file for errors:
>     *   *macOS Log Path:* `~/Library/Logs/Claude/mcp.log`
>     *   *Windows Log Path:* `%APPDATA%\Claude\Logs\mcp.log`

---

## Step 7: Available MCP Tools & Usage Guide

Once the Google Ads MCP Server is installed and successfully connected to your AI assistant, the server exposes specific tools that the assistant can discover and invoke autonomously.

> [!IMPORTANT]
> **Mandatory Agent Directive (Tool Explanation Checklist):**
> When a user asks what tools the Google Ads MCP server provides or how to use them, your response **MUST** systematically include all of the following:
> 1. [ ] **List All 3 Tools:** Explicitly name `list_accessible_customers`, `get_resource_metadata`, and `search`.
> 2. [ ] **Define Purpose & Usage:** Explain exactly what each tool does and how/when to invoke it.
> 3. [ ] **Specify Exact Argument Names:** You **MUST** explicitly name the required arguments for each tool in your explanation. E.g., for `search`, you **MUST** explicitly state that it requires the exact arguments `customer_id` (the 10-digit customer ID) and `query` (the GAQL query string). Do not paraphrase `customer_id` to "account".
> 4. [ ] **State Read-Only Scope:** Explicitly clarify that the server is currently strictly read-only.

When assisting a user or formulating queries, refer to the following tool definitions and best practices:

### 1. `list_accessible_customers`

*   **Purpose:** Returns the list of Google Ads customer IDs and account names that are accessible to the authenticated user.
*   **How to Use:** Call this tool first when starting a new session or when the target customer ID is unknown. It requires no arguments.
*   **Example Intent:** *"What Google Ads accounts do I have access to?"*

### 2. `get_resource_metadata`

*   **Purpose:** Retrieves detailed structural metadata about a specific Google Ads API resource type (e.g., `campaign`, `ad_group`, `customer`).
*   **How to Use:** Call this tool to inspect the schema, available fields, metrics, and segments for a resource before constructing a GAQL query.
*   **Arguments:**
    *   `resource` (string, required): The name of the resource to inspect (e.g., `campaign`).
*   **Example Intent:** *"What fields and metrics can I query for an ad group?"*

### 3. `search`

*   **Purpose:** Executes a Google Ads Query Language (GAQL) query to fetch resource metrics, attributes, segments, and status.
*   **How to Use:** Construct a valid GAQL query string based on the resource metadata and execute the search against a specific customer account.
*   **Arguments:**
    *   `customer_id` (string, required): The 10-digit target Google Ads customer ID (digits only, no hyphens).
    *   `query` (string, required): A valid GAQL query string (e.g., `SELECT campaign.id, campaign.name, campaign.status, metrics.impressions FROM campaign WHERE campaign.status = 'ENABLED'`).
*   **Example Intent:** *"Get the impressions and status of all enabled campaigns for account 1234567890."*

> [!NOTE]
> **Read-Only Scope:** The Google Ads MCP Server is currently strictly read-only. It cannot modify bids, pause campaigns, or create new advertising assets.
