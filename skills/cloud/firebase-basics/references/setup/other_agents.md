# Other Agents Setup

If you use another agent (like Windsurf, Cline, or Claude Desktop), follow these
steps to install the agent skills and the MCP server.

## Recommended: Global Setup

The agent skills and MCP server should be installed globally for consistent
access across projects.

### 1. Install and Verify Firebase Skills

Check if the skills are already installed before proceeding:

1.  **Check Local skills**: Run `npx skills list --agent <agent-name>`. If the
    output includes `firebase-basics`, the skills are already installed locally.
    Replace `<agent-name>` with the actual agent name, which can be found
    [here](https://github.com/vercel-labs/skills/blob/main/README.md).
1.  **Check Global skills**: If not found locally, check the global installation
    by running:

    ```bash
    npx skills list --global --agent <agent-name>
    ```

    If the output includes `firebase-basics`, the skills are already installed
    globally.

1.  **Install Skills**: If both checks fail, run the following command to
    install the Firebase agent skills:

    ```bash
    npx skills add firebase/agent-skills --agent <agent-name> --skill "*"
    ```

    *Note: Omit `--yes` and `--global` to choose the installation location
    manually. If prompted interactively in the terminal, ensure you send the
    appropriate user choices via standard input to complete the installation.*

1.  **Verify Installation**: Re-run the checks in steps 1 or 2 to confirm that
    `firebase-basics` is now available.

### 2. Configure and Verify Firebase MCP Server

The MCP server allows the agent to interact directly with Firebase projects.

1.  **Locate MCP Configuration**: Find the configuration file for your agent
    (e.g., `~/.codeium/windsurf/mcp_config.json`, `cline_mcp_settings.json`, or
    `claude_desktop_config.json`).

    *Note: If the document or its containing directory does not exist, create
    them and initialize the file with `{ "mcpServers": {} }` before proceeding.*

1.  **Check Existing Configuration**: Open the configuration file and check the
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

    *CRITICAL: Merge this configuration into the existing file. You MUST
    preserve any other existing servers inside the `mcpServers` object.*

1.  **Verify Configuration**: Save the file and confirm the `firebase` block is
    present and properly formatted JSON.

### 3. Restart and Verify Connection

1.  **Restart Agent**: Instruct the user to restart the agent application.
    **Stop and wait** for their confirmation before proceeding.
1.  **Confirm Connection**: Check the MCP server list in the agent's UI to
    confirm that the Firebase MCP server is connected.
