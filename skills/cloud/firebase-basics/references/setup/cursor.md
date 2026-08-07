# Cursor Setup

To get the most out of Firebase in Cursor, follow these steps to install the
agent skills and the MCP server.

### 1. Install and Verify Firebase Skills

Check if the skills are already installed before proceeding:

1.  **Check Local skills**: Run `npx skills list --agent cursor`. If the output
    includes `firebase-basics`, the skills are already installed locally.
1.  **Check Global skills**: If not found locally, check the global installation
    by running:

    ```bash
    npx skills list --global --agent cursor
    ```

    If the output includes `firebase-basics`, the skills are already installed
    globally.

1.  **Install Skills**: If both checks fail, run the following command to
    install the Firebase agent skills:

    ```bash
    npx skills add firebase/agent-skills --agent cursor --skill "*"
    ```

    *Note: Omit `--yes` and `--global` to choose the installation location
    manually. If prompted interactively in the terminal, ensure you send the
    appropriate user choices via standard input to complete the installation.*

1.  **Verify Installation**: Re-run the checks in steps 1 or 2 to confirm that
    `firebase-basics` is now available.

### 2. Configure and Verify Firebase MCP Server

The MCP server allows Cursor to interact directly with Firebase projects.

1.  **Locate `mcp.json`**: Find the configuration file for your operating
    system:

    -   Global: `~/.cursor/mcp.json`
    -   Project: `.cursor/mcp.json`

    *Note: If the directory or `mcp.json` file does not exist, create them and
    initialize the file with `{ "mcpServers": {} }` before proceeding.*

1.  **Check Existing Configuration**: Open `mcp.json` and check the `mcpServers`
    section for a `firebase` entry.

    -   It is already configured if the `command` is `"firebase"` OR if the
        `command` is `"npx"` with `"firebase-tools"` and `"mcp"` in the `args`.
    -   **Important**: If a valid `firebase` entry is found, the MCP server is
        already configured. **Skip step 3** and proceed directly to step 4.

    **Example valid configurations**:

    ```json
    "firebase": {
      "command": "npx",
      "args": ["-y", "firebase-tools@latest", "mcp"]
    }
    ```

    OR

    ```json
    "firebase": {
      "command": "firebase",
      "args": ["mcp"]
    }
    ```

1.  **Add or Update Configuration**: If the `firebase` block is missing or
    incorrect, add it to the `mcpServers` object:

    ```json
    "firebase": {
      "command": "npx",
      "args": [
        "-y",
        "firebase-tools@latest",
        "mcp"
      ]
    }
    ```

    *CRITICAL: Merge this configuration into the existing `mcp.json` file. You
    MUST preserve any other existing servers inside the `mcpServers` object.*

1.  **Verify Configuration**: Save the file and confirm the `firebase` block is
    present and properly formatted JSON.

### 3. Restart and Verify Connection

1.  **Restart Cursor**: Instruct the user to restart the Cursor application.
    **Stop and wait** for their confirmation before proceeding.
1.  **Confirm Connection**: Check the MCP server list in the Cursor UI to
    confirm that the Firebase MCP server is connected.
