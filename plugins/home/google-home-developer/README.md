# Google Home Developer

Connects your coding agent to the remote Google Home Developer MCP server
(`https://homedevelopers.googleapis.com/mcp`) for official Google Home, Matter,
and OpenThread documentation search and Cloud-to-cloud integration diagnostics.

For available tools, authentication setup, and usage examples, see the
[Google Home Developer MCP documentation][mcp-guide].

## Authentication and Setup

-   **Public documentation (no credentials required):** Works out of the box
    over Streamable HTTP (`https://homedevelopers.googleapis.com/mcp`) for
    public Google Home APIs, Cloud-to-cloud, Matter, and OpenThread
    documentation search. Configure an optional API key if you need dedicated
    per-project quota.
-   **Cloud-to-cloud diagnostics and Partner Program docs:** Require OAuth 2.0
    or Application Default Credentials (`gcloud auth application-default login`)
    on a Google Cloud project with `homedevelopers.googleapis.com` enabled. See
    [Choose an authentication method][choose-auth].

## Installation

### Antigravity

Install from the Antigravity Marketplace (`Customizations > Marketplace` →
search **Google Home Developer** → **Add**), or via CLI:

```bash
agy plugin install google-home-developer
```

### Claude Code

```bash
claude plugin marketplace add google/skills
claude plugin install google-home-developer@google-plugins
```

### Codex CLI

```bash
codex plugin marketplace add google/skills
codex plugin add google-home-developer@google-plugins
```

### Gemini CLI

Install this package as a Gemini CLI extension (`gemini-extension.json`), or add
the remote MCP server directly:

```bash
gemini mcp add --transport http HomeDevelopers https://homedevelopers.googleapis.com/mcp
```

### VS Code / GitHub Copilot & Cursor

Connect to `https://homedevelopers.googleapis.com/mcp` using `.mcp.json` (or the
one-click buttons on the [Google Home Developer MCP guide][mcp-guide]) and
include `rules/AGENTS.md` for agent routing rules.

[mcp-guide]: https://developers.home.google.com/mcp/developer
[choose-auth]: https://developers.home.google.com/mcp/developer#choose-auth
