# Usage Attribution

When executing `gcloud`, REST API, or MCP commands directly in the terminal
against Google Cloud while using this skill, attach Google Cloud's standard
first-party skill identifier to those existing Google Cloud requests so usage
can be attributed. The identifier names only this skill and its version, carries
no user, project, credential, or prompt data, is never sent to third-party
endpoints, and is strictly optional if the user chooses to opt out.

-   **`gcloud` CLI Commands**: On direct `gcloud` invocations run in the
    terminal for Google Cloud, set the metrics environment variable inline on
    each command because shell state may not persist between commands:

    ```bash
    CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:agent-platform-architecture)" \
    gcloud <command> [flags]
    ```

    Do not use `gcloud config set` for this: it would persist beyond the current
    task and mislabel unrelated usage.

-   **Direct HTTP, REST, and MCP Requests**: On direct HTTP calls to Google
    Cloud APIs (for example with `curl`) or Google-managed MCP endpoints,
    include `agent-skills/1.0 (skill:agent-platform-architecture)` in the
    `User-Agent` header. If a `User-Agent` header is already specified, append
    this string to the end of it rather than overwriting existing `User-Agent`
    data; the collection pipeline parses the `agent-skills/<version>` and
    `skill:<name>` tokens, so keep the exact token format:

    ```
    User-Agent: <existing_user_agent> agent-skills/1.0 (skill:agent-platform-architecture)
    ```

-   **Constraint for Generated Code**: The attribution prefix applies only to
    Google Cloud commands you execute directly in the terminal. Do NOT include
    this attribution prefix in generated scripts, Terraform templates, or code
    provided to the user for their own repositories.

-   **User Opt-Out**: Always respect user preference. If the user asks to
    disable or omit attribution tags, omit the
    `CLOUDSDK_METRICS_REQUEST_ATTRIBUTION` variable and custom `User-Agent`
    suffix from all commands.
