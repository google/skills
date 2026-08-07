# Exploring Commands

The Firebase CLI documents itself. Use help commands to discover functionality.

-   **Global Help**: List all available commands and categories.

    ```bash
    npx -y firebase-tools@latest --help
    ```

-   **Command Help**: Get detailed usage for a specific command.

    ```bash
    npx -y firebase-tools@latest [command] --help
    # Example:
    npx -y firebase-tools@latest deploy --help
    npx -y firebase-tools@latest firestore:indexes --help
    ```
