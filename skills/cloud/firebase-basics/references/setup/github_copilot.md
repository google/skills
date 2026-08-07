# GitHub Copilot Setup

To get the most out of Firebase with GitHub Copilot in VS Code, follow these
steps to install the agent skills and the MCP server.

## Recommended: Global Setup

The agent skills and MCP server should be installed globally for consistent
access across projects.

### 1. Install and Verify Firebase Skills

Check if the skills are already installed before proceeding:

1.  **Check Local skills**: Run `npx skills list --agent github-copilot`. If the
    output includes `firebase-basics`, the skills are already installed locally.
1.  **Check Global skills**: If not found locally, check the global installation
    by running:

    ```bash
    npx skills list --global --agent github-copilot
    ```

    If the output includes `firebase-basics`, the skills are already installed
    globally.

1.  **Install Skills**: If both checks fail, run the following command to
    install the Firebase agent skills:

    ```bash
    npx skills add firebase/agent-skills --agent github-copilot --skill "*"
    ```

    *Note: Omit `--yes` and `--global` to choose the installation location
    manually. If prompted interactively in the terminal, ensure you send the
    appropriate user choices via standard input to complete the installation.*

1.  **Verify Installation**: Re-run the checks in steps 1 or 2 to confirm that
    `firebase-basics` is now available.

### 2. Configure and Verify Firebase MCP Server

The MCP server allows GitHub Copilot to interact directly with Firebase
projects.

1.  **Locate `mcp.json`**: Find the configuration file for your environment:

    -   Workspace: `.vscode/mcp.json`
    -   Global: User Settings `mcp.json` file.

    *Note: If the `.vscode/` directory or `mcp.json` file does not exist, create
    them and initialize the file with `{ "mcp": { "servers": {} } }` before
    proceeding.*

1.  **Check Existing Configuration**: Open the `mcp.json` file and check the
    `mcp.servers` object for a `firebase` entry.

    -   It is already configured if the `command` is `"firebase"` OR if the
        `command` is `"npx"` with `"firebase-tools"` and `"mcp"` in the `args`.
    -   **Important**: If a valid `firebase` entry is found, the MCP server is
        already configured. **Skip step 3** and proceed directly to step 4.

    **Example valid configurations**:

    ```json
    "firebase": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "firebase-tools@latest", "mcp"]
    }
    ```

    OR

    ```json
    "firebase": {
      "type": "stdio",
      "command": "firebase",
      "args": ["mcp"]
    }
    ```

1.  **Add or Update Configuration**: If the `firebase` block is missing or
    incorrect, add it to the `mcp.servers` object:

    ```json
    "firebase": {
      "type": "stdio",
      "command": "npx",
      "args": [
        "-y",
        "firebase-tools@latest",
        "mcp"
      ]
    }
    ```

    *CRITICAL: Merge this configuration into the existing `mcp.json` file under
    the `mcp.servers` object. You MUST preserve any other existing servers
    inside `mcp.servers`.*

1.  **Verify Configuration**: Save the file and confirm the `firebase` block is
    present and properly formatted JSON.

### 3. Restart and Verify Connection

1.  **Restart VS Code**: Instruct the user to restart VS Code. **Stop and wait**
    for their confirmation before proceeding.
1.  **Confirm Connection**: Check the MCP server list in the VS Code Copilot UI
    to confirm that the Firebase MCP server is connected.
