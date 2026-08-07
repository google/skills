# Claude Code Setup

To get the most out of Firebase in Claude Code, follow these steps to install
the agent skills and the MCP server.

## Recommended Method: Using Plugins

The recommended method is using the plugin marketplace to install both the agent
skills and the MCP functionality.

### 1. Install and Verify Plugins

Check if the plugins are already installed before proceeding:

1.  **Check Existing Skills**: Run `npx skills list --agent claude-code` to
    check for local skills. Run `npx skills list --global --agent claude-code`
    to check for global skills. Note whether the output includes
    `firebase-basics`.
1.  **Check Existing MCP Configuration**: Run `claude mcp list -s user` and
    `claude mcp list -s project`. Note whether the output of either command
    includes `firebase`.
1.  **Determine Installation Path**:
    -   If **both** skills and MCP configuration are found, the plugin is fully
        installed. **Stop here and skip all remaining setup steps in this
        document.**
    -   If **neither** are found, proceed to step 4.
    -   If **only one** is found (e.g., skills are installed but MCP is missing,
        or vice versa), **stop and prompt the user**. Explain the mixed state
        and ask if they want to proceed with installing the Firebase plugin
        before continuing to step 4.
1.  **Add Marketplace**: Run the following command to add the marketplace (this
    uses the default User scope):

    ```bash
    claude plugin marketplace add firebase/agent-skills
    ```

1.  **Install Plugins**: Run the following command to install the plugin:

    ```bash
    claude plugin install firebase@firebase
    ```

1.  **Verify Installation**: Re-run the checks in steps 1 and 2 to confirm the
    skills and the MCP server are now available.

### 2. Restart and Verify Connection

1.  **Restart Claude Code**: Instruct the user to restart Claude Code. **Stop
    and wait** for their confirmation before proceeding.
