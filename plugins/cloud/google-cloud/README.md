# Google Cloud plugin

The `google-cloud` plugin equips AI coding agents with foundational
skills, safety guardrails, and live documentation grounding for building on
Google Cloud.

Built on the open [Agent Plugins specification](https://agent-plugins.org/),
this plugin bundles curated Agent Skills, routing rules, and configuration for
two MCP servers into a single portable package:

-   **Developer Knowledge**: grounded, up-to-date answers from Google's
    developer documentation.
-   **Autocloud**: the Cloud Operator Agent, which designs, reviews, operates
    and troubleshoots infrastructure in your projects.

--------------------------------------------------------------------------------

## Installation

### Antigravity

Install the plugin from the Antigravity Marketplace:

1. In Antigravity 2.0, go to Customizations > Marketplace and search for "Google Cloud".
2. Click the **Add** button.

Alternatively, install the plugin using the Antigravity CLI:

```bash
agy plugin install google-cloud
```

### Claude Code

1.  Add the Google plugins marketplace, then install the plugin:

    ```bash
    claude plugin marketplace add google/skills
    claude plugin install google-cloud@google-plugins
    ```

    > [!NOTE] On native Windows, the plugin signs in with your Google
    > credentials through `scripts/adc-headers.cmd`, so it doesn't need WSL.
    > If the servers still don't connect, see [Troubleshooting](#troubleshooting).

### Codex CLI

1.  Add the Google plugins marketplace, then install the plugin:

    ```bash
    codex plugin marketplace add google/skills
    codex plugin add google-cloud@google-plugins
    ```

    > [!NOTE] If `codex` isn't found and you use the ChatGPT desktop app on
    > macOS, the Codex CLI ships inside the app: run
    > `/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex`
    > instead, or add its folder to your `PATH`.

1.  Add the servers to Codex's `config.toml` ([Setup](#setup)).

--------------------------------------------------------------------------------

## Setup

Both MCP servers sign in with your Google credentials (Application Default
Credentials, ADC). No gcloud or Google Cloud project yet? Ask your agent to get
you started on Google Cloud: the plugin's `google-cloud-recipe-onboarding`
skill walks you through it.

1.  Install the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install)
    (`gcloud`).

1.  Sign in, set the project that calls are billed to (usually a project you
    work in), and enable both APIs there:

    ```bash
    gcloud auth login
    gcloud auth application-default login
    gcloud auth application-default set-quota-project <YOUR_PROJECT_ID>
    gcloud services enable developerknowledge.googleapis.com geminicloudassist.googleapis.com --project=<YOUR_PROJECT_ID>
    ```

    Your account needs `serviceusage.services.use` on that project (Owners and
    Editors have it). Cloud Operator gives you a personal operator agent in each
    Google Cloud organization you work in, for projects in that organization.
    You don't need a role to create or use your own agent; your organization's
    administrators decide whether Cloud Operator is turned on.

1.  In Codex only, add the servers to `config.toml` (below).

1.  Restart your agent, then ask it to **set up Cloud Operator**: it finds the
    organization of a project you work in (`gcloud projects get-ancestors`),
    finds your operator agent there or helps you create it, and checks the
    connection with one call. To create the agent yourself, open
    `https://console.cloud.google.com/autocloud/agent/create?organizationId=<YOUR_ORGANIZATION_ID>`,
    signed in with the same account, and click **Get started**, then **Create
    agent**.

If `gcloud auth application-default login` says "This app is blocked", your
organization blocks Application Default Credentials and the servers can't sign
in; ask your admin.

### Codex: add the servers to config.toml

Codex can't use the plugin's own server entries to sign in, so you add both
servers to its configuration yourself.

1.  Copy the plugin's sign-in helper to a fixed path, because the installed
    plugin folder changes with each version. The commands copy it from the
    most recently installed version, so run them after you install the
    plugin in Codex, and again after an update.

    macOS and Linux:

    ```bash
    mkdir -p ~/.codex/bin
    cp "$(ls -dt ~/.codex/plugins/cache/*/google-cloud/*/ | head -n 1)scripts/adc-headers" ~/.codex/bin/
    chmod +x ~/.codex/bin/adc-headers
    ```

    Windows (PowerShell):

    ```powershell
    mkdir "$env:USERPROFILE\.codex\bin" -Force | Out-Null
    $dir = (Get-ChildItem "$env:USERPROFILE\.codex\plugins\cache\*\google-cloud\*" -Directory | Sort-Object LastWriteTime)[-1].FullName
    Copy-Item "$dir\scripts\adc-headers.cmd" "$env:USERPROFILE\.codex\bin\" -Force
    ```

1.  Add both servers to `~/.codex/config.toml` (or your project's
    `.codex/config.toml`), using the full path to the helper. The helper sends
    a fresh token from your Google credentials on each connection, and
    `tool_timeout_sec` lets Cloud Operator calls run for up to 20 minutes.

    -   **macOS:** copy the block below as it is, with your user name in place
        of `<YOU>`.
    -   **Linux:** copy the same block, with `/home/<YOU>` in place of
        `/Users/<YOU>` in **both** `http_headers_helper` lines.
    -   **Windows:** copy the same block, then change the `http_headers_helper`
        line in **both** entries to:

        ```toml
        http_headers_helper = '"C:/Users/<YOU>/.codex/bin/adc-headers.cmd"'
        ```

    ```toml
    # Wait for the servers to start: getting a token takes a few seconds.
    mcp_optional_startup_grace_ms = 0

    [mcp_servers.developer-knowledge]
    url = "https://developerknowledge.googleapis.com/mcp"
    http_headers_helper = '"/Users/<YOU>/.codex/bin/adc-headers"'

    [mcp_servers.autocloud]
    url = "https://geminicloudassist.googleapis.com/mcp/autocloud"
    http_headers = { "X-Goog-Api-Client" = "google-cloud/2.0.0 agent-skills/1.0 (skill:cloud-operator; version:1.2.0; plugin:google-cloud)" }
    http_headers_helper = '"/Users/<YOU>/.codex/bin/adc-headers"'
    tool_timeout_sec = 1200
    ```

    Put `mcp_optional_startup_grace_ms` at the top of the file, before any
    `[section]`. These entries replace the plugin's own entries of the same
    name. Keep the double quotes inside the single quotes: Codex runs the
    helper through a shell, and the quotes keep a path with spaces in one
    piece. The helper reads your credentials from gcloud's default location;
    Codex doesn't pass `CLOUDSDK_CONFIG` or `GOOGLE_APPLICATION_CREDENTIALS` to
    it.

After the restart (step 4 above), `/mcp` in the Codex CLI lists both servers'
tools.

--------------------------------------------------------------------------------

## Troubleshooting

-   **A server isn't listed, or `ask_cloud_operator` isn't available:** restart
    your agent. In Antigravity, turn the plugin on in `/plugin` (a new install
    can start disabled). In Claude Code, `claude mcp get autocloud` shows
    whether an `autocloud` entry of your own, for example from the standalone
    Cloud Operator plugin, replaces the plugin's; remove it with
    `claude mcp remove autocloud -s <scope>`.
-   **Your agent answers Google Cloud questions itself:** uninstall the
    standalone Cloud Operator plugin, whose skill competes with this one.
-   **Developer Knowledge fails with "Forbidden" or "requires a quota
    project":** your Application Default Credentials have no quota project.
    Set one, then restart your agent:
    `gcloud auth application-default set-quota-project <YOUR_PROJECT_ID>`.
-   **On Windows, the servers don't connect:** run `scripts\adc-headers.cmd`
    from the installed plugin folder in Command Prompt
    (`%USERPROFILE%\.claude\plugins\cache\google-plugins\google-cloud\<version>`
    for Claude Code, or the same path under `.codex` for Codex). It prints the
    headers, or the
    sign-in error and its fix (for example, `gcloud` isn't on `PATH`, or you
    haven't run `gcloud auth application-default login`). If it works but the
    servers still don't connect, run your agent in
    [WSL](https://learn.microsoft.com/windows/wsl/install).
-   **Cloud Operator answers "This method is not available in this project."
    (`RUN_NOT_ALLOWED`):** this check can fail intermittently, especially just
    after the agent is created, so your agent tries up to 3 times, about 30
    seconds apart. If all 3 fail, Cloud Operator isn't on for your organization
    yet; your agent notes that in its local memory and stops calling it there
    until you ask it to try again.
-   **Codex doesn't see the servers' tools:** check that
    `mcp_optional_startup_grace_ms = 0` is at the top of `~/.codex/config.toml`,
    and that `codex mcp list` shows both servers.
-   **Other errors:** your agent explains them and the fix when a call fails.

--------------------------------------------------------------------------------

## What's Included

### Bundled Skills

-   **[gcloud](./skills/gcloud)**: Safety-critical validation, best practices,
    and execution guardrails for `gcloud` CLI commands.
-   **[google-cloud-recipe-auth](./skills/google-cloud-recipe-auth)**:
    Authentication workflows, credential selection, and service identity best
    practices.
-   **[google-cloud-recipe-onboarding](./skills/google-cloud-recipe-onboarding)**:
    First-project onboarding, account setup, and billing configuration.
-   **[finding-google-skills](./skills/finding-google-skills)**: Discovery and
    on-demand installation of specialized skills from the Google Agent Skills
    repo.
-   **[retrieving-developer-knowledge](./skills/retrieving-developer-knowledge)**:
    Grounded retrieval of official Google documentation.
-   **[cloud-operator](./skills/cloud-operator)**:
    Routes Google Cloud requests about your projects (questions, architecture,
    Terraform and Kubernetes review, rollouts, incidents, cost) to the Cloud
    Operator Agent. If you haven't set up an operator agent yet, it hands you to
    `cloud-operator-setup`.
-   **[cloud-operator-setup](./skills/cloud-operator-setup)**: Finds the
    organization of a project you choose, checks your operator agent there or
    walks you through creating it, then offers to share your existing Google
    Cloud context with it.
-   **[cloud-operator-share-context](./skills/cloud-operator-share-context)**:
    Finds Google Cloud operating context you already have (environments,
    product preferences, runbooks) in instruction files, memory and docs, and
    copies what you approve into the operator agent's memory.

### MCP Servers

The plugin declares both servers for each agent (`mcp.json` for Agent Plugins
clients, `.mcp.json` for Claude Code, `mcp_config.json` for Antigravity,
`gemini-extension.json` for Gemini CLI):

| Server | Name | What it does | Endpoint |
| :--- | :--- | :--- | :--- |
| [Developer Knowledge](https://developers.google.com/knowledge/mcp) | `developer-knowledge` | Up-to-date grounding in official Google developer documentation | `https://developerknowledge.googleapis.com/mcp` |
| Autocloud | `autocloud` | The `ask_cloud_operator`, `search_operator_sessions` and `fetch_operator_session` tools: hand Google Cloud work to your operator agent in the project's organization, which sees your live resources, logs, metrics, billing and policies. Calls can run for up to 20 minutes | `https://geminicloudassist.googleapis.com/mcp/autocloud` |

In Claude Code, the plugin runs its `scripts/adc-headers` (on Windows,
`scripts/adc-headers.cmd`) each time it connects to a server, to send a fresh
token from your Google credentials; you don't run it yourself. In Codex, you
point `~/.codex/config.toml` at the same helper (Setup, above).

### Routing Rules

-   **[google-cloud-discovery.md](./rules/google-cloud-discovery.md)**:
    Always-on routing map that guides the agent to discover and suggest deeper
    product-specific skills (such as `gke-*`, `agent-platform-*`,
    `google-cloud-waf-*`, and `<product>-basics`) when a task requires
    specialized domain knowledge beyond the foundational bundle.

--------------------------------------------------------------------------------

## Plugin in Action

To see how this plugin works, consider a situation where you're bootstrapping a
new project as part of working on a script. With the `google-cloud`
plugin installed, you can prompt your agent:

> *I'm brand new to this platform, and I need to get an account and a first
> project with billing set up. Then, I need my local machine authenticated so a
> script that I'm writing can call the APIs as a service identity instead of as
> me.*

1.  **Environment awareness**: The agent silently runs background checks against
    your live environment for prerequisites like CLI availability and potential
    existing projects or organizations.

2.  **Review**: The agent considers IAM best practices to avoid risks that might
    be assumed as part of the prompt, like accidental key leaks or git commits.

3.  **Interaction with guardrails**: The agent outlines a workflow roadmap and
    offers to act on those steps before modifying any resources.

--------------------------------------------------------------------------------

## Network, Sandbox, and Permission Requirements

If you run your agent in a local sandbox or behind a corporate firewall/proxy,
configure your environment to allow the following outbound URLs and terminal
commands.

> [!NOTE] The core bundled skills (`gcloud`, `google-cloud-recipe-auth`,
> `google-cloud-recipe-onboarding`) and the `developer-knowledge` MCP server
> only require `gcloud` and HTTPS access to `*.googleapis.com`,
> `docs.cloud.google.com`, and `developers.google.com`. Access to GitHub domains
> (`raw.githubusercontent.com`, `api.github.com`) and `curl` is only required at
> runtime for dynamic skill discovery (`finding-google-skills`) and the REST API
> fallback in `retrieving-developer-knowledge`. Dynamically fetched skills may
> require additional product-specific CLI tools or API endpoints.

### 1. Required Outbound URL Allowlist

| Domain / Endpoint | Used By | Purpose |
| :--- | :--- | :--- |
| `https://raw.githubusercontent.com` (`githubusercontent.com`) | `finding-google-skills` | Fetches the `index.json` catalog and on-demand `SKILL.md` / reference files from `google/skills`. |
| `https://github.com`, `https://api.github.com` | Installer, `finding-google-skills`, `google-cloud-discovery` | Installs the plugin and queries the GitHub Trees API fallback (`/repos/google/skills/git/trees/main`). |
| `https://developerknowledge.googleapis.com` | `developer-knowledge` MCP, `retrieving-developer-knowledge` | Connects to the remote MCP server (`/mcp`) and REST API v1 fallback (`/v1/documents:*`, `/v1:answerQuery`). |
| `https://geminicloudassist.googleapis.com` | `autocloud` MCP, `cloud-operator`, `cloud-operator-setup`, `cloud-operator-share-context` | Connects to the Autocloud MCP server (`/mcp/autocloud`). |
| `https://oauth2.googleapis.com` | Both MCP servers | Refreshes your Google credentials. |
| `https://*.googleapis.com` | `gcloud`, `google-cloud-recipe-auth`, `google-cloud-recipe-onboarding` | Authenticates and executes `gcloud` CLI commands against Google Cloud APIs. |
| `https://docs.cloud.google.com`, `https://developers.google.com` | `gcloud`, `google-cloud-recipe-auth`, `google-cloud-recipe-onboarding` | Reads official Google Cloud documentation (`*.md.txt`). |

### 2. Required Terminal Command Permissions

-   **Skill discovery & REST fallback** (`finding-google-skills`,
    `retrieving-developer-knowledge`): `curl` (`curl -sSL`, `curl -s -X POST`,
    `curl -s -G`), `jq`, `grep`, and optionally `npx skills` (only if installing
    discovered skills locally).
-   **Read-only `gcloud` checks** (`gcloud`, `google-cloud-recipe-onboarding`):
    `which gcloud`, `gcloud help`, `gcloud topic`, `gcloud cheat-sheet`,
    `gcloud auth list`, `gcloud config get-value`, `gcloud config list`,
    `gcloud organizations list`, `gcloud projects list`,
    `gcloud projects describe`, `gcloud billing projects describe`,
    `gcloud billing accounts list`, `gcloud compute regions list`,
    `gcloud compute zones list`.
-   **MCP server sign-in** (Claude Code and Codex): the plugin's
    `scripts/adc-headers` (`scripts/adc-headers.cmd` on Windows) runs
    `gcloud auth application-default print-access-token` and
    `gcloud config get-value` each time the agent connects to a server.
-   **Cloud Operator** (`cloud-operator`, `cloud-operator-setup`,
    `cloud-operator-share-context`): `gcloud projects get-ancestors`, to
    find the organization of the project a request is about;
    `gcloud organizations list`, when that fails;
    `gcloud config get-value project`, offered only as a suggestion; and
    `gcloud auth application-default print-access-token`, to check your
    credentials when a call fails to sign in.
-   **Interactive or state-changing `gcloud` commands**
    (`google-cloud-recipe-onboarding`, `google-cloud-recipe-auth`,
    `cloud-operator`, `cloud-operator-setup`): `gcloud auth login`,
    `gcloud auth application-default login`,
    `gcloud auth application-default set-quota-project`, `gcloud config set`,
    `gcloud projects create`, `gcloud billing projects link`,
    `gcloud services enable`. Do not auto-allow these commands; keep them gated
    behind confirmation (**Ask**) or run them manually beforehand.
