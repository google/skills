# Google Cloud Developer plugin

The `google-cloud-developer` plugin equips AI coding agents with foundational
skills, safety guardrails, and live documentation grounding for building on
Google Cloud.

Built on the open [Agent Plugins specification](https://agent-plugins.org/),
this plugin bundles curated Agent Skills, routing rules, and configuration for
the **Developer Knowledge MCP server** into a single portable package.

--------------------------------------------------------------------------------

## Installation

### Antigravity

Install the plugin from the Antigravity Marketplace:

1. In Antigravity 2.0, go to Customizations > Marketplace and search for "Google Cloud Developer".
2. Click the **Add** button.

Alternatively, install the plugin using the Antigravity CLI:

```bash
agy plugin install google-cloud-developer
```

### Claude Code

1.  Add the Google plugins marketplace, then install the plugin:

    ```bash
    claude plugin marketplace add google/skills
    claude plugin install google-cloud-developer@google-plugins
    ```

1.  Enable the Developer Knowledge API in your Google Cloud project by using the
    gcloud CLI:

    ```bash
    gcloud services enable developerknowledge.googleapis.com --project=<YOUR_PROJECT_ID>
    ```

1.  Create an API key for the Developer Knowledge API by following the
    instructions
    [Create and secure the API key](https://developers.google.com/knowledge/quickstart#create-secure-key).
    Save the key you create in a secure location.

1.  Export the API key to your environment before starting Claude Code:

    ```bash
    export DEVELOPERKNOWLEDGE_API_KEY=<YOUR_API_KEY>
    ```

    > [!NOTE] The `DEVELOPERKNOWLEDGE_API_KEY` environment variable needs to be
    > set in the environment before you start Claude Code. You may consider
    > adding this export to your shell's startup script (e.g. `.bashrc`,
    > `.zshrc`) for convenience.

### Codex CLI

1.  Add the Google plugins marketplace, then install the plugin:

    ```bash
    codex plugin marketplace add google/skills
    codex plugin add google-cloud-developer@google-plugins
    ```

1.  Enable the Developer Knowledge API in your Google Cloud project by using the
    gcloud CLI:

    ```bash
    gcloud services enable developerknowledge.googleapis.com --project=<YOUR_PROJECT_ID>
    ```

1.  Create an API key for the Developer Knowledge API by following the
    instructions
    [Create and secure the API key](https://developers.google.com/knowledge/quickstart#create-secure-key).
    Save the key you create in a secure location.

1.  Enable authenticated access to the Developer Knowledge MCP server by
    updating `~/.codex/config.toml` (or your project's `.codex/config.toml`) to
    include the following lines:

    ```toml
    [mcp_servers.developer-knowledge]
      url = "https://developerknowledge.googleapis.com/mcp"
      env_http_headers = { "X-Goog-Api-Key" = "DEVELOPERKNOWLEDGE_API_KEY" }
    ```

1.  Export the API key to your environment before starting Codex:

    ```bash
    export DEVELOPERKNOWLEDGE_API_KEY=<YOUR_API_KEY>
    ```

    > [!NOTE] The `DEVELOPERKNOWLEDGE_API_KEY` environment variable needs to be
    > set in the environment before you start Codex. You may consider adding
    > this export to your shell's startup script (e.g. `.bashrc`, `.zshrc`) for
    > convenience.

    > [!NOTE] Note: After you change the configuration, the server may show a
    > *not logged in* status. This is expected and won't affect your access.

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

### MCP Server

-   **[Developer Knowledge MCP server](https://developers.google.com/knowledge/mcp)**:
    Provides AI agents with up-to-date grounding in official Google developer
    documentation over streamable HTTP.

### Routing Rules

-   **[google-cloud-discovery.md](./rules/google-cloud-discovery.md)**:
    Always-on routing map that guides the agent to discover and suggest deeper
    product-specific skills (such as `gke-*`, `agent-platform-*`,
    `google-cloud-waf-*`, and `<product>-basics`) when a task requires
    specialized domain knowledge beyond the foundational bundle.

--------------------------------------------------------------------------------

## Plugin in Action

To see how this plugin works, consider a situation where you're bootstrapping a
new project as part of working on a script. With the `google-cloud-developer`
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
-   **Interactive or state-changing `gcloud` commands**
    (`google-cloud-recipe-onboarding`, `google-cloud-recipe-auth`):
    `gcloud auth login`, `gcloud auth application-default login`,
    `gcloud config set`, `gcloud projects create`,
    `gcloud billing projects link`, `gcloud services enable`. Do not auto-allow
    these commands; keep them gated behind confirmation (**Ask**) or run them
    manually beforehand.
