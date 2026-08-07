# Refresh Android Studio Local Environment

Follow these steps to refresh Gemini in Android Studio's local environment,
ensuring that agent skills are fully up-to-date.

Gemini in Android Studio expects skills to be located at `~/.agents/skills`.

1.  **List Available Skills:** Identify all Firebase skills available in the
    repository:

    ```bash
    npx -y skills add firebase/agent-skills --list
    ```

1.  **Check Currently Installed Skills:** Check the contents of the skills
    directory to see what is currently installed:

    ```bash
    ls -la ~/.agents/skills
    ```

1.  **Add Missing Skills:** Use the `skills` CLI to add skills. If the CLI
    supports an `android_studio` agent identifier, you can run:

    ```bash
    npx -y skills add firebase/agent-skills --agent android_studio --skill "*" --yes
    ```

    If the `skills` CLI does not support Android Studio directly, you can
    manually copy or symlink the desired skills from your local clone of
    `firebase/agent-skills` to `~/.agents/skills`.

1.  **Update Existing Skills:** To update skills, you can try:

    ```bash
    npx -y skills update --agent android_studio --yes
    ```

    If manual installation was used, pull the latest changes from the
    `firebase/agent-skills` repository and copy the updated files to
    `~/.agents/skills`.
