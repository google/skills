# Gemini CLI Setup

To get the most out of Firebase in the Gemini CLI, follow these steps to install
the agent extension and the MCP server.

## Recommended: Installing Extensions

The best way to get both the agent skills and the MCP server is via the Gemini
extension.

### 1. Install and Verify Firebase Extension

Check if the extension is already installed before proceeding:

1.  **Check Existing Extensions**: Run `gemini extensions list`. If the output
    includes `firebase`, the extension is already installed.
1.  **Install Extension**: If not found, run the following command to install
    the Firebase agent skills and MCP server:

    ```bash
    gemini extensions install https://github.com/firebase/agent-skills
    ```

1.  **Verify Installation**: Run the following checks to confirm installation:

    -   `gemini mcp list` -> Output should include `firebase-tools`.
    -   `gemini skills list` -> Output should include `firebase-basic`.

### 2. Restart and Verify Connection

1.  **Restart Gemini CLI**: Instruct the user to restart the Gemini CLI if any
    new installation occurred. **Stop and wait** for their confirmation before
    proceeding.

________________________________________________________________________________

## Alternative: Manual MCP Configuration (Project Scope)

If the user only wants to use the MCP server for the current project:

### 1. Configure and Verify Firebase MCP Server

1.  **Check Existing Configuration**: Run `gemini mcp list`. If the output
    includes `firebase-tools`, the MCP server is already configured.
1.  **Add the MCP Server**: If not found, run the following command to configure
    the Firebase MCP Server:

    ```bash
    gemini mcp add -e IS_GEMINI_CLI_EXTENSION=true firebase npx -y firebase-tools@latest mcp
    ```

1.  **Verify Configuration**: Re-run `gemini mcp list` to confirm
    `firebase-tools` is connected.

### 2. Restart and Verify Connection

1.  **Restart Gemini CLI**: Instruct the user to restart the Gemini CLI. **Stop
    and wait** for their confirmation before proceeding.
