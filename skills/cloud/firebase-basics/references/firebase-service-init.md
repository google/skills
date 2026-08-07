# Initialization

Before initializing, check if you are already in a Firebase project directory by
looking for `firebase.json`.

1.  **Project Directory:** Navigate to the root directory of the codebase.
    *(Only if starting a completely new project from scratch without an existing
    codebase, create a directory first: `mkdir my-project && cd my-project`)*

1.  **Initialize Services:** Run the initialization command:

    ```bash
    npx -y firebase-tools@latest init
    ```

The CLI will guide you through:

-   Selecting features (Firestore, Functions, Hosting, etc.).
-   Associating with an existing project or creating a new one.
-   Configuring files (e.g. `firebase.json`, `.firebaserc`).
