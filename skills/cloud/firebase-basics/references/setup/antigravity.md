# Antigravity Setup

To get the most out of Firebase in Antigravity, follow these steps to install
the agent skills and the MCP server.

### 1. Install and Verify Firebase Skills

Check if the skills are already installed before proceeding:

1.  **Check Local skills**: Run `ls -d .agent/skills/firebase-basics` or `ls -d
    .agents/skills/firebase-basics`. If the directory exists, the skills are
    already installed locally.
1.  **Check Global skills**: If not found locally, check the global installation
    by running:

    ```bash
    npx skills list --global --agent antigravity
    ```

    If the output includes `firebase-basics`, the skills are already installed
    globally.

1.  **Install Skills**: If both checks fail, run the following command to
    install the Firebase agent skills:

    ```bash
    npx skills add firebase/agent-skills --agent antigravity --skill "*"
    ```

    *Note: Omit `--yes` and `--global` to choose the installation location
    manually. If prompted interactively in the terminal, ensure you send the
    appropriate user choices via standard input to complete the installation.*

1.  **Verify Installation**: Re-run the checks in steps 1 or 2 to confirm that
    `firebase-basics` is now available.

### 2. Configure and Verify Firebase MCP Server

The MCP server allows Antigravity to interact directly with Firebase projects.
This is considered the **mandatory extension configuration** required for full
functionality.

1.  **Locate `mcp_config.json`**: Find the configuration file for your operating
    system:

    -   macOS / Linux: `~/.gemini/antigravity/mcp_config.json`
    -   Windows: `%USERPROFILE%\\.gemini\\antigravity\\mcp_config.json`

    *Note: If the `.gemini/antigravity/` directory or `mcp_config.json` file
    does not exist, create them and initialize the file with `{ "mcpServers": {}
    }` before proceeding.*

1.  **Check Existing Configuration**: Open `mcp_config.json` and check the
    `mcpServers` section for a `firebase` entry.

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

    *CRITICAL: Merge this configuration into the existing `mcp_config.json`
    file. You MUST preserve any other existing servers inside the `mcpServers`
    object.*

1.  **Verify Configuration**: Save the file and confirm the `firebase` block is
    present and properly formatted JSON.

### 3. Restart and Verify Connection

1.  **Restart Antigravity**: Instruct the user to restart the Antigravity
    application. **Stop and wait** for their confirmation before proceeding.
1.  **Confirm Connection**: Check the MCP server list in the Antigravity UI to
    confirm that the Firebase MCP server is connected.
