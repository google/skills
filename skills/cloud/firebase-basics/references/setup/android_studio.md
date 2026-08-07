# Android Studio Setup

This guide explains how to set up Firebase agent skills for Gemini in Android
Studio.

## Skills Installation

Gemini in Android Studio expects skills to be located at `~/.agents/skills`.

To install all Firebase skills, run the following command in your terminal:

```bash
npx -y skills add firebase/agent-skills --skill "*" --yes
```

Ensure that the skills are installed or linked to the `~/.agents/skills`
directory.

## MCP Setup

MCP setup is currently skipped for Android Studio as it only supports SSE
transport, while the Firebase CLI MCP server uses stdio. Direct integration is
not supported without an SSE-to-stdio proxy.
