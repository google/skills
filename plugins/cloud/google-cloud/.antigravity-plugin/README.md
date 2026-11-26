# Google Cloud plugin

The `google-cloud` plugin equips Antigravity with foundational skills,
safety guardrails, and live documentation grounding for building on Google
Cloud.

This plugin bundles curated Agent Skills, routing rules, and configuration for
two MCP servers, **Developer Knowledge** and **Autocloud** (the Cloud Operator
Agent), into a single portable package.

## Setup

Both MCP servers sign in with your Google credentials (Application Default
Credentials, ADC). No gcloud or Google Cloud project yet? Ask Antigravity to get
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

1.  Restart Antigravity, then ask it to **set up Cloud Operator**: it finds the
    organization of a project you work in (`gcloud projects get-ancestors`),
    finds your operator agent there or helps you create it, and checks the
    connection with one call. To create the agent yourself, open
    `https://console.cloud.google.com/autocloud/agent/create?organizationId=<YOUR_ORGANIZATION_ID>`,
    signed in with the same account, and click **Get started**, then **Create
    agent**. If the servers don't appear, turn the plugin on in `/plugin` (a
    new install can start disabled).

If `gcloud auth application-default login` says "This app is blocked", your
organization blocks Application Default Credentials and the servers can't sign
in; ask your admin.

## Troubleshooting

-   **The servers don't appear:** restart Antigravity, and turn the plugin on
    in `/plugin` (a new install can start disabled).
-   **Developer Knowledge fails with "Forbidden" or "requires a quota
    project":** your Application Default Credentials have no quota project.
    Set one, then restart your agent:
    `gcloud auth application-default set-quota-project <YOUR_PROJECT_ID>`.
-   **Cloud Operator answers "This method is not available in this project."
    (`RUN_NOT_ALLOWED`):** this check can fail intermittently, especially just
    after the agent is created, so your agent tries up to 3 times, about 30
    seconds apart. If all 3 fail, Cloud Operator isn't on for your organization
    yet; your agent notes that in its local memory and stops calling it there
    until you ask it to try again.
-   **Other errors:** Antigravity explains them and the fix when a call fails.

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
-   **[cloud-operator-admin-setup](./skills/cloud-operator-admin-setup)**:
    Helps an organization administrator turn Cloud Operator on or off and set
    its organization-wide controls, with gcloud or in the Google Cloud console.
-   **[cloud-operator-share-context](./skills/cloud-operator-share-context)**:
    Finds Google Cloud operating context you already have (environments,
    product preferences, runbooks) in instruction files, memory and docs, and
    copies what you approve into the operator agent's memory.

### MCP Servers

-   **[Developer Knowledge MCP server](https://developers.google.com/knowledge/mcp)**:
    Provides AI agents with up-to-date grounding in official Google developer
    documentation over streamable HTTP.
-   **Autocloud MCP server** (`autocloud`): Gives AI agents the
    `ask_cloud_operator`, `search_operator_sessions` and
    `fetch_operator_session` tools, which hand Google Cloud work to your
    operator agent in the project's organization. It sees your live
    resources, logs, metrics, billing and policies, and calls can run for up
    to 20 minutes.

Both servers sign in with your Google credentials (Application Default
Credentials), declared in the plugin's `com.google.antigravity/mcp_config.json`
and `mcp_config.json`.

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

If you run Antigravity with terminal sandboxing or behind a corporate
firewall/proxy, configure your environment to allow the following outbound URLs
and terminal commands.

> [!NOTE] The core bundled skills (`gcloud`, `google-cloud-recipe-auth`,
> `google-cloud-recipe-onboarding`) and the `developer-knowledge` MCP server
> only require `gcloud` and HTTPS access to `*.googleapis.com`,
> `docs.cloud.google.com`, and `developers.google.com`. Access to GitHub domains
> (`raw.githubusercontent.com`, `api.github.com`) is only required at runtime
> for dynamic skill discovery (`finding-google-skills`). `curl` is required for
> that, the REST API fallback in `retrieving-developer-knowledge`, and the REST
> calls in `cloud-operator-setup` and `cloud-operator-admin-setup`. Dynamically
> fetched skills may require additional product-specific CLI tools or API
> endpoints.

### 1. Required Outbound URL Allowlist

| Domain / Endpoint | Used By | Purpose |
| :--- | :--- | :--- |
| `https://raw.githubusercontent.com` (`githubusercontent.com`) | `finding-google-skills` | Fetches the `index.json` catalog and on-demand `SKILL.md` / reference files from `google/skills`. |
| `https://github.com`, `https://api.github.com` | Installer, `finding-google-skills`, `google-cloud-discovery` | Installs the plugin and queries the GitHub Trees API fallback (`/repos/google/skills/git/trees/main`). |
| `https://developerknowledge.googleapis.com` | `developer-knowledge` MCP, `retrieving-developer-knowledge` | Connects to the remote MCP server (`/mcp`) and REST API v1 fallback (`/v1/documents:*`, `/v1:answerQuery`). |
| `https://geminicloudassist.googleapis.com` | `autocloud` MCP, `cloud-operator`, `cloud-operator-setup`, `cloud-operator-admin-setup`, `cloud-operator-share-context` | Connects to the Autocloud MCP server (`/mcp/autocloud`), and the REST calls `:getOrgEnablement` (setup) and `agentAdminSettings` (admin setup). |
| `https://oauth2.googleapis.com` | Both MCP servers | Refreshes your Google credentials. |
| `https://*.googleapis.com` | `gcloud`, `google-cloud-recipe-auth`, `google-cloud-recipe-onboarding`, `cloud-operator-admin-setup` | Authenticates and executes `gcloud` CLI commands against Google Cloud APIs. |
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
-   **Cloud Operator** (`cloud-operator`, `cloud-operator-setup`,
    `cloud-operator-admin-setup`, `cloud-operator-share-context`):
    `curl` for read-only REST calls (`:getOrgEnablement`,
    `agentAdminSettings` reads, `:testIamPermissions`);
    `gcloud organizations describe` and `gcloud config get-value account`, to
    tell whether the organization is your own;
    `gcloud projects get-ancestors`, to find the organization of the project a
    request is about;
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
    `gcloud services enable`, and for `cloud-operator-admin-setup`,
    `gcloud organizations add-iam-policy-binding` and the `curl -X PATCH` that
    changes `agentAdminSettings`. Do not auto-allow these commands; keep them
    gated behind confirmation (**Ask**) or run them manually beforehand.
