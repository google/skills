# Refresh Other Local Environment

Follow these steps to refresh the local environment of other agents, ensuring
that their agent skills and plugins are fully up-to-date.

Other agents rely on `npx skills`. Updates should prioritize the global level;
if skills are installed at the project level, omit the `--global` flag.

Replace `<AGENT_NAME>` with the actual agent name, which can be found in the
[skills repository README](https://github.com/vercel-labs/skills/blob/main/README.md).

1.  **List Available Skills:** Identify all Firebase skills available in the
    repository:

    ```bash
    npx -y skills add firebase/agent-skills --list
    ```

1.  **Check Currently Installed Skills:** Determine which skills are already
    installed and linked for the agent at both project and global levels:

    ```bash
    # Check project-level skills
    npx -y skills list --agent <AGENT_NAME>

    # Check global-level skills
    npx -y skills list --agent <AGENT_NAME> --global
    ```

    *Note: If a skill shows `Agents: not linked` in the output, it is installed
    but not currently available to the agent.*

1.  **Add Missing or Unlinked Skills:** Compare the results from Step 1 and Step
    2\. For each missing or unlinked skill, follow the appropriate conditional
    instruction below:

    -   **IF any Firebase skills were found at the PROJECT level in Step 2:**
        Add the missing skill to the project level:

        ```bash
        npx -y skills add firebase/agent-skills --agent <AGENT_NAME> --skill "<SKILL_NAME>" --yes
        ```

    -   **IF any Firebase skills were found at the GLOBAL level in Step 2:** Add
        the missing skill to the global level:

        ```bash
        npx -y skills add firebase/agent-skills --agent <AGENT_NAME> --skill "<SKILL_NAME>" --global --yes
        ```

    -   **IF NO Firebase skills were found in Step 2:** Add each missing skill
        to the global level:

        ```bash
        npx -y skills add firebase/agent-skills --agent <AGENT_NAME> --skill "<SKILL_NAME>" --global --yes
        ```

1.  **Update Existing Skills:** Update all currently installed skills to their
    latest versions:

    ```bash
    # Update project-level skills
    npx -y skills update --agent <AGENT_NAME> --yes

    # Update global-level skills
    npx -y skills update --agent <AGENT_NAME> --global --yes
    ```
