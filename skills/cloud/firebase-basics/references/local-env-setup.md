# Firebase Local Environment Setup

This skill documents the bare minimum setup required for a full Firebase
experience for the agent. Before starting to use any Firebase features, you MUST
verify that each of the following steps has been completed.

## 1. Verify Node.js

-   **Action**: Run `node --version`.

-   **Handling**: Ensure Node.js is installed and the version is `>= 20`. If
    Node.js is missing or `< v20`, install it based on the operating system:

    **Recommended: Use a Node Version Manager** This avoids permission issues
    when installing global packages.

    **For macOS or Linux:**

    1.  Guide the user to the
        [official nvm repository](https://github.com/nvm-sh/nvm#installing-and-updating).
    1.  Request the user to manually install `nvm` and reply when finished.
        **Stop and wait** for the user's confirmation.
    1.  Make `nvm` available in the current terminal session by sourcing the
        appropriate profile:

        ```bash
        # For Bash
        source ~/.bash_profile
        source ~/.bashrc

        # For Zsh
        source ~/.zprofile
        source ~/.zshrc
        ```

    1.  Install Node.js:

        ```bash
        nvm install 24
        nvm use 24
        ```

    **For Windows:**

    1.  Guide the user to download and install
        [nvm-windows](https://github.com/coreybutler/nvm-windows/releases).
    1.  Request the user to manually install `nvm-windows` and Node.js, and
        reply when finished. **Stop and wait** for the user's confirmation.
    1.  After the user confirms, verify Node.js is available:

        ```bash
        node --version
        ```

    **Alternative: Official Installer**

    1.  Guide the user to download and install the LTS version from
        [nodejs.org](https://nodejs.org/en/download).
    1.  Request the user to manually install Node.js and reply when finished.
        **Stop and wait** for the user's confirmation.

## 2. Verify Firebase CLI

-   **Command**: `npx -y firebase-tools@latest --version`
-   **Expected**: Successfully outputs a version string.

## 3. Verify Firebase Authentication

You must be authenticated to manage Firebase projects.

-   **Action**: Run `npx -y firebase-tools@latest login`.
-   **Handling**: If the environment is remote or restricted (no browser
    access), run `npx -y firebase-tools@latest login --no-localhost` instead.

## 4. Install Agent Skills and MCP Server

To fully manage Firebase, the agent needs specific skills and the Firebase MCP
server installed. Refer to the main `SKILL.md` for direct links to the
installation instructions specific to your agent environment.

________________________________________________________________________________

**CRITICAL AGENT RULE:** Do NOT proceed with any other Firebase tasks until
EVERY step above has been successfully verified and completed.
