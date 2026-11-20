# Google Health Developer

Equip your coding agent with direct access to official
[Google Health API](https://developers.google.com/health) documentation through
the remote Google Health Developer Model Context Protocol (MCP) server
(`https://healthdevelopers.googleapis.com/mcp`).

For full setup and usage instructions, see the official
[Google Health Developer MCP guide](https://developers.google.com/health/mcp).

## Overview

-   **Google Health REST and gRPC APIs** (`developers.google.com/health`)
-   **OAuth 2.0 scopes, permissions, and user consent flows**
-   **Data types, schemas, and REST / gRPC endpoints** (activity, sleep, heart
    rate, and wellness metrics)
-   **Fitbit Web API migration documentation**
    (`developers.google.com/health/migration`)

## Authentication and Setup

This plugin requires no API key or Google Cloud credentials. Installing and
enabling this plugin connects your agent directly to
`https://healthdevelopers.googleapis.com/mcp` over Streamable HTTP for read-only
documentation lookup (`search_health_docs` and `get_health_docs`).

## Supported Clients

This package includes manifests and configs for:

-   **Agent Plugins v1.0.0 / Universal:** `plugin.json` and `mcp.json`
-   **Claude Code:** `.claude-plugin/plugin.json` and `.mcp.json`
-   **OpenAI Codex:** `.codex-plugin/plugin.json` and `.mcp.json`
-   **Gemini CLI:** `gemini-extension.json`
-   **VS Code / GitHub Copilot & Cursor:** `.mcp.json` (`https://healthdevelopers.googleapis.com/mcp`) and `rules/AGENTS.md`
-   **Kimi, Qwen, OpenCode & Agent Skills:** Install bundled skills via `npx skills add google/skills` and connect to `https://healthdevelopers.googleapis.com/mcp`
-   **Antigravity:** `mcp_config.json` and `rules/AGENTS.md`
