# Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command with
this skill, follow these usage attribution instructions. Tag every command you
execute directly in the terminal so usage can be attributed. The tag identifies
only the skill and its version; it carries no user data.

-   **`gcloud` CLI Commands**: Prefix every `gcloud` invocation, whatever the
    subcommand, with the metrics environment variable. Set it inline on each
    command because shell state may not persist between commands:

    ```bash
    CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:cloud-operator; version:1.0.3)" \
    gcloud <command> [flags]
    ```

    Do not use `gcloud config set` for this: it would persist beyond the current
    task and mislabel unrelated usage.

-   **Direct HTTP, REST, and MCP Requests**: On direct HTTP calls to Google
    Cloud APIs (for example with `curl`) or HTTP requests to a remote MCP
    server, include `agent-skills/1.0 (skill:cloud-operator; version:1.0.3)` in
    the `User-Agent` header. If a `User-Agent` header is already specified,
    append this string to the end of it rather than overwriting existing
    `User-Agent` data — the collection pipeline parses the
    `agent-skills/<version>` and `skill:<name>` tokens, so any rewording breaks
    attribution:

    ```
    User-Agent: <existing_user_agent> agent-skills/1.0 (skill:cloud-operator; version:1.0.3)
    ```

-   **Constraint for Generated Code**: The tracking prefix is strictly for
    commands you execute directly in the terminal. Do NOT include this tracking
    prefix in generated scripts, Terraform templates, or code provided to the
    user for their own repositories.

-   **User Opt-Out**: If the user asks to disable or remove tracking or
    attribution tags, omit the `CLOUDSDK_METRICS_REQUEST_ATTRIBUTION` variable
    and custom `User-Agent` suffix from all commands.
