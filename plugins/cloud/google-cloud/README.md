# Google Cloud plugin

Skills, safety guardrails and live documentation that help AI coding agents
build on Google Cloud. Built on the open
[Agent Plugins specification](https://agent-plugins.org/), it bundles:

-   **Skills** for `gcloud`, authentication, onboarding and Cloud Operator.
-   **Developer Knowledge** (MCP server): answers from Google's developer
    documentation.
-   **Autocloud** (MCP server): the Cloud Operator Agent, which designs,
    reviews, operates and troubleshoots infrastructure in your projects.

--------------------------------------------------------------------------------

## Installation

### Antigravity

-   **Marketplace:** in Antigravity 2.0, open **Customizations > Marketplace**,
    search for "Google Cloud" and click **Add**.
-   **CLI:**

    ```bash
    agy plugin install google-cloud
    ```

**Next:** [Setup](#setup): sign in to Google Cloud and connect Cloud Operator.

### Claude Code

1.  Install the plugin:

    ```bash
    claude plugin marketplace add google/skills
    claude plugin install google-cloud@google-plugins
    ```

Works on native Windows too; no WSL needed.

**Next:** [Setup](#setup): sign in to Google Cloud and connect Cloud Operator.

### Codex CLI

1.  Install the plugin:

    ```bash
    codex plugin marketplace add google/skills
    codex plugin add google-cloud@google-plugins
    ```

    No `codex` command on macOS? The ChatGPT app includes one:
    `/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex`.

1.  Connect the plugin's two servers. Codex doesn't run the plugin's sign-in
    helper on its own, so this adds the servers to `~/.codex/config.toml`.

    -   macOS, Linux, WSL or Git Bash:

        ```bash
        bash "${CODEX_HOME:-$HOME/.codex}"/plugins/cache/*/google-cloud/*/com.google.codex-config/setup
        ```

    -   Windows PowerShell:

        ```powershell
        & (Get-ChildItem "$(if ($env:CODEX_HOME) { $env:CODEX_HOME } else { "$env:USERPROFILE\.codex" })\plugins\cache\*\google-cloud\*\com.google.codex-config\setup.cmd" | Select-Object -Last 1).FullName
        ```

    It prints `Codex config updated`. If it fails, it says why and prints the
    settings to add to `config.toml` yourself.

    -   Run it again after each plugin update.
    -   What it changes: [How the servers sign in](#how-the-servers-sign-in).
    -   It uses Codex's folder: `CODEX_HOME` if you set it, otherwise
        `~/.codex` (`%USERPROFILE%\.codex` on Windows).
    -   Git Bash with a `$HOME` other than `%USERPROFILE%`: run this first,
        then the command above:

        ```bash
        export CODEX_HOME="$(cygpath -u "$USERPROFILE")/.codex"
        ```

**Next:** [Setup](#setup): sign in to Google Cloud and connect Cloud Operator.

--------------------------------------------------------------------------------

## Setup

New to Google Cloud? Ask your agent to get you started: the
`google-cloud-recipe-onboarding` skill sets up `gcloud`, an account and a
project with you.

1.  Install the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install)
    (`gcloud`).

1.  Sign in, and turn on Developer Knowledge in a project you use:

    ```bash
    gcloud auth login
    gcloud auth application-default login
    gcloud auth application-default set-quota-project <YOUR_PROJECT_ID>
    gcloud services enable developerknowledge.googleapis.com --project=<YOUR_PROJECT_ID>
    ```

    -   `gcloud auth login`: for the `gcloud` commands the skills run.
    -   `gcloud auth application-default login`: for the two MCP servers.
    -   The last two: Developer Knowledge bills its calls to that project. You
        need `serviceusage.services.use` there (Owners and Editors have it).
    -   Cloud Operator needs neither. You get a personal operator agent in each
        organization you work in, if its admins turned Cloud Operator on.

1.  Restart your agent and ask it to **set up Cloud Operator**. It finds your
    project's organization, finds or helps you create your operator agent, and
    tests the connection.

    To create the agent yourself, open this page with the same account, then
    click **Get started** and **Create agent**:
    `https://console.cloud.google.com/autocloud/agent/create?organizationId=<YOUR_ORGANIZATION_ID>`

1.  Ask as you normally would. For example:

    -   "Which Compute Engine VMs are running in project <YOUR_PROJECT_ID>?"
    -   "Why did my Cloud Run deploy fail?"
    -   "Review this Terraform before I apply it."

    Questions about your live resources go to your operator agent;
    documentation questions go to Developer Knowledge.

--------------------------------------------------------------------------------

## Plugin in Action

Say you're new to Google Cloud and ask your agent:

> *I'm brand new to this platform, and I need to get an account and a first
> project with billing set up. Then, I need my local machine authenticated so a
> script that I'm writing can call the APIs as a service identity instead of as
> me.*

1.  **Checks your environment:** whether `gcloud` is installed, and which
    projects and organizations you already have.
2.  **Reviews the risks:** IAM best practices, such as avoiding leaked keys or
    keys committed to git.
3.  **Plans with you:** outlines the steps and asks before changing any
    resources.

--------------------------------------------------------------------------------

## What's Included

### Bundled Skills

-   **[gcloud](./skills/gcloud)**: validation, best practices and guardrails
    for `gcloud` commands.
-   **[google-cloud-recipe-auth](./skills/google-cloud-recipe-auth)**:
    authentication, credential choice and service identities.
-   **[google-cloud-recipe-onboarding](./skills/google-cloud-recipe-onboarding)**:
    your first project: account, billing and `gcloud`.
-   **[finding-google-skills](./skills/finding-google-skills)**: finds and
    installs more specialized skills from the Google Agent Skills repo.
-   **[retrieving-developer-knowledge](./skills/retrieving-developer-knowledge)**:
    answers grounded in official Google documentation.
-   **[cloud-operator](./skills/cloud-operator)**: sends requests about your
    projects (questions, architecture, Terraform and Kubernetes review,
    rollouts, incidents, cost) to the Cloud Operator Agent.
-   **[cloud-operator-setup](./skills/cloud-operator-setup)**: finds your
    project's organization, checks or creates your operator agent there, then
    offers to share your Google Cloud context with it.
-   **[cloud-operator-share-context](./skills/cloud-operator-share-context)**:
    copies Google Cloud context you already have (environments, preferences,
    runbooks) into your operator agent's memory, with your approval.

### MCP Servers

| Server | Name | What it does | Endpoint |
| :--- | :--- | :--- | :--- |
| [Developer Knowledge](https://developers.google.com/knowledge/mcp) | `developer-knowledge` | Up-to-date grounding in official Google developer documentation | `https://developerknowledge.googleapis.com/mcp` |
| Autocloud | `autocloud` | The `ask_cloud_operator`, `search_operator_sessions` and `fetch_operator_session` tools: hand Google Cloud work to your operator agent in the project's organization, which sees your live resources, logs, metrics, billing and policies. Calls can run for up to 20 minutes | `https://geminicloudassist.googleapis.com/mcp/autocloud` |

Each agent reads the servers from its own file: `mcp.json` (Agent Plugins
clients), `.mcp.json` (Claude Code), `mcp_config.json` (Antigravity) and
`gemini-extension.json` (Gemini CLI).

#### How the servers sign in

Both servers use your Google credentials (Application Default Credentials).
The plugin's `scripts/adc-headers` (`scripts/adc-headers.cmd` on Windows) gets
a fresh token on each connection.

-   **Claude Code** runs it for you.
-   **Codex** needs [Codex CLI step 2](#codex-cli), which adds to
    `~/.codex/config.toml` the settings in
    [com.google.codex-config/config.json](./com.google.codex-config/config.json):
    -   each server's URL and sign-in helper;
    -   Cloud Operator's `X-Goog-Api-Client` header and a 20-minute timeout;
    -   `mcp_optional_startup_grace_ms = 0`, so Codex waits for the servers to
        start.

    Your other settings stay as they are. Codex runs the helper without
    `CLOUDSDK_CONFIG` or `GOOGLE_APPLICATION_CREDENTIALS`, so it uses gcloud's
    default credentials. If you set Codex up by hand before, you can delete
    `~/.codex/bin/adc-headers` (`%USERPROFILE%\.codex\bin\adc-headers.cmd` on
    Windows).

### Routing Rules

-   **[google-cloud-discovery.md](./rules/google-cloud-discovery.md)**:
    always-on map that points the agent to deeper product skills (such as
    `gke-*`, `agent-platform-*`, `google-cloud-waf-*` and `<product>-basics`)
    when a task needs them.

--------------------------------------------------------------------------------

## Network, Sandbox, and Permission Requirements

In a sandbox or behind a firewall or proxy, allow these URLs and commands.

> [!NOTE]
>
> -   The core skills (`gcloud`, `google-cloud-recipe-auth`,
>     `google-cloud-recipe-onboarding`) and Developer Knowledge need only
>     `gcloud` and HTTPS to `*.googleapis.com`, `docs.cloud.google.com` and
>     `developers.google.com`.
> -   GitHub (`raw.githubusercontent.com`, `api.github.com`) and `curl` are
>     needed only for skill discovery (`finding-google-skills`) and the REST
>     fallback in `retrieving-developer-knowledge`.
> -   Skills found that way may need more CLI tools or endpoints.

### 1. Required Outbound URL Allowlist

| Domain / Endpoint | Used By | Purpose |
| :--- | :--- | :--- |
| `https://developerknowledge.googleapis.com` | `developer-knowledge` MCP, `retrieving-developer-knowledge` | The MCP server (`/mcp`) and its REST fallback (`/v1/documents:*`, `/v1:answerQuery`). |
| `https://geminicloudassist.googleapis.com` | `autocloud` MCP, `cloud-operator`, `cloud-operator-setup`, `cloud-operator-share-context` | The Autocloud MCP server (`/mcp/autocloud`). |
| `https://oauth2.googleapis.com` | Both MCP servers, `gcloud` | Refreshes your Google credentials. |
| `https://*.googleapis.com` | `gcloud`, `google-cloud-recipe-auth`, `google-cloud-recipe-onboarding`, `cloud-operator` | `gcloud` commands against Google Cloud APIs. |
| `https://docs.cloud.google.com`, `https://developers.google.com` | `gcloud`, `google-cloud-recipe-auth`, `google-cloud-recipe-onboarding`, `cloud-operator` | Official documentation (`*.md.txt`). |
| `https://raw.githubusercontent.com` | `finding-google-skills` | The `index.json` skill catalog and on-demand `SKILL.md` and reference files from `google/skills`. |
| `https://github.com`, `https://api.github.com` | Installation, `finding-google-skills`, `google-cloud-discovery` | Installs the plugin, and lists `google/skills` when the catalog isn't available (`/repos/google/skills/git/trees/main`). |

### 2. Required Terminal Command Permissions

-   **Skill discovery and REST fallback** (`finding-google-skills`,
    `retrieving-developer-knowledge`): `curl` (`curl -sSL`, `curl -s -X POST`,
    `curl -s -G`; `curl.exe` or `Invoke-WebRequest` on Windows), and
    optionally `jq` or `grep` to filter the skill catalog.
-   **Read-only `gcloud` checks** (`gcloud`, `google-cloud-recipe-onboarding`):
    `which gcloud`, `gcloud help`, `gcloud topic`, `gcloud cheat-sheet`,
    `gcloud auth list`, `gcloud config get-value`, `gcloud config list`,
    `gcloud organizations list`, `gcloud projects list`,
    `gcloud projects describe`, `gcloud billing projects describe`,
    `gcloud billing accounts list`, `gcloud compute regions list`,
    `gcloud compute zones list`.
-   **MCP server sign-in** (Claude Code and Codex): `scripts/adc-headers`
    (`scripts/adc-headers.cmd` on Windows) runs
    `gcloud auth application-default print-access-token` and
    `gcloud config get-value` on each connection.
-   **Codex setup** ([Codex CLI step 2](#codex-cli)):
    `com.google.codex-config/setup` (`setup.cmd` on Windows) runs
    `codex app-server`.
-   **Cloud Operator** (`cloud-operator`, `cloud-operator-setup`,
    `cloud-operator-share-context`):
    -   `gcloud projects get-ancestors`: finds the organization of the project
        a request is about.
    -   `gcloud organizations list`: when that fails.
    -   `gcloud config get-value project`: only to suggest a project.
    -   `gcloud auth application-default print-access-token`: checks your
        credentials when a call fails to sign in.
-   **Developer Knowledge REST fallback** (`retrieving-developer-knowledge`):
    `gcloud auth print-access-token`, or
    `gcloud auth application-default print-access-token`, and
    `gcloud config get-value project`.
-   **Interactive or state-changing `gcloud` commands**
    (`google-cloud-recipe-onboarding`, `google-cloud-recipe-auth`,
    `cloud-operator`, `cloud-operator-setup`): `gcloud auth login`,
    `gcloud auth application-default login`,
    `gcloud auth application-default set-quota-project`, `gcloud config set`,
    `gcloud projects create`, `gcloud billing projects link`,
    `gcloud services enable`. Don't auto-allow these: keep them behind
    confirmation (**Ask**), or run them yourself first.

--------------------------------------------------------------------------------

## Troubleshooting

Problems while setting up the plugin or making your first calls. For anything
else, your agent explains the error and the fix.

### Signing in

-   **`gcloud auth application-default login` says "This app is blocked":**
    your organization blocks Application Default Credentials, so the servers
    can't sign in. Ask your admin.
-   **A server says it couldn't get a token, or "gcloud isn't installed":**
    install the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install),
    run `gcloud auth application-default login`, then restart your agent.
-   **"agent_id must be explicitly specified when authenticating as a service
    account", or "can only be created with an end-user credential":** your
    Application Default Credentials are a service account's. Run
    `gcloud auth application-default login` with your own account. If
    `GOOGLE_APPLICATION_CREDENTIALS` points to a key file, unset it: it
    overrides that sign-in.
-   **Setup can't find your project's organization:** `gcloud` isn't signed in
    as you (for example, it uses a VM's service account). Run
    `gcloud auth login`, check `gcloud config get-value account`, then ask
    again.

### Connecting the servers

-   **A server, or `ask_cloud_operator`, is missing:** restart your agent.
    -   Antigravity: turn the plugin on in `/plugin`; a new install can start
        off.
    -   Claude Code: run `claude mcp get autocloud`. If it shows an `autocloud`
        entry of your own (for example, from the standalone Cloud Operator
        plugin), remove it: `claude mcp remove autocloud -s <scope>`.
-   **Codex shows "Not logged in", or no tools:** run
    [Codex CLI step 2](#codex-cli) again, then restart Codex.
-   **Codex setup prints "Codex config update failed":** run it again. If it
    fails again, add the lines it prints to `config.toml` yourself, as it
    says.
-   **Windows: the servers don't connect:** in Command Prompt, go to the
    installed plugin's folder and run `scripts\adc-headers.cmd`. It prints the
    sign-in error and its fix.
    -   Claude Code's folder:
        `%USERPROFILE%\.claude\plugins\cache\google-plugins\google-cloud\<version>`
    -   Codex's: the same, with `.codex` in place of `.claude`.
    -   Still failing? Run your agent in
        [WSL](https://learn.microsoft.com/windows/wsl/install).

### Developer Knowledge

-   **"... requires a quota project, which is not set by default":** run
    `gcloud auth application-default set-quota-project <YOUR_PROJECT_ID>`, then
    restart your agent.
-   **"Developer Knowledge API has not been used in project ... or it is
    disabled":** turn the API on in your quota project:

    ```bash
    gcloud services enable developerknowledge.googleapis.com --project=<YOUR_PROJECT_ID>
    ```

### Cloud Operator

-   **Your agent answers Google Cloud questions itself:** uninstall the
    standalone Cloud Operator plugin; its skill competes with this one.
-   **"personal operator agent ... has not been initialized yet":** you don't
    have an operator agent in that organization yet. Ask your agent to **set
    up Cloud Operator**; it helps you create one.
-   **"agent ... is not ready to serve yet":** the agent was just created. Wait
    about a minute and ask again.
-   **"This method is not available in this project." (`RUN_NOT_ALLOWED`):**
    this can fail for a while after you create the agent, so your agent tries
    3 times, about 30 seconds apart. If all fail, Cloud Operator isn't on for
    your organization yet; your agent stops calling it there until you ask it
    to try again.
-   **"AutoCloud is disabled for organization ..." (`ORG_DISABLED`), or "The
    caller does not have permission":** an administrator of your organization
    controls access to Cloud Operator. Ask them.
-   **You sign in with a personal Google Account (for example, @gmail.com):**
    Cloud Operator doesn't support personal accounts yet. Developer Knowledge
    and the other skills still work.
-   **Your project isn't in an organization:** Cloud Operator works only with
    projects in an organization.

--------------------------------------------------------------------------------

## Uninstall

-   **Claude Code:**

    ```bash
    claude plugin uninstall google-cloud@google-plugins
    ```

-   **Codex:** remove the plugin and the two servers setup added:

    ```bash
    codex plugin remove google-cloud@google-plugins
    codex mcp remove autocloud
    codex mcp remove developer-knowledge
    ```

    You can also delete the `mcp_optional_startup_grace_ms` line at the top of
    `~/.codex/config.toml`.

-   **Antigravity:**

    ```bash
    agy plugin uninstall google-cloud
    ```

-   **The marketplace too:** after removing the plugin, run
    `claude plugin marketplace remove google-plugins` or
    `codex plugin marketplace remove google-plugins`. This also uninstalls the
    other plugins you installed from it. In Codex, remove each with
    `codex plugin remove` first, or their entries stay in `config.toml`.
