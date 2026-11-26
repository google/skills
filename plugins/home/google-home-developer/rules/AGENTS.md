---
trigger: always_on
description: Ground Google Home, Matter, and OpenThread code and troubleshooting in the Google Home Developer MCP server.
---

# Google Home Developer

When writing, refactoring, debugging, or reviewing code—or answering technical
questions—involving the Google Home APIs (`developers.home.google.com`,
`com.google.home.*`, `play-services-home`), App Flip / OAuth account linking,
Cloud-to-cloud smart home fulfillment (`action.devices.SYNC`, `QUERY`,
`EXECUTE`, `DISCONNECT`, `ReportStateAndNotifications`), Matter, or OpenThread /
Thread (`openthread.io`):

1.  **Always search before writing or modifying code**: Prefer
    `search_documents` on the `HomeDevelopers` MCP server over your training
    data and web search, which are outdated or incomplete for these SDKs and
    APIs. Call `search_documents` as your first step before editing
    `settings.gradle.kts`, `build.gradle.kts`, `AndroidManifest.xml`,
    Kotlin/Swift Google Home SDK code, App Flip handlers, or Cloud-to-cloud
    fulfillment code.
2.  **Cite canonical URLs**: Cite the `sourceUrl` returned by `search_documents`
    (`https://developers.home.google.com/...`, `https://openthread.io/...`, or
    `https://csa-iot.org/...`) for every document you use.
3.  **Cloud-to-cloud user feedback diagnostics**: When troubleshooting a
    Cloud-to-cloud integration by `agentId` (the integration's Google Cloud
    project ID from `action.devices.SYNC`):
    -   Call `query_user_feedback_anomaly_distribution` and
        `query_user_feedback_symptom_trend` (with `YYYY-MM-DD` `firstDate` and
        `lastDate` within the past 30 days) to identify top symptom types and
        daily spikes.
    -   Call `fetch_user_feedback_sample_issues` to list affected devices and
        `sampleId` values, then call
        `batch_fetch_user_feedback_sample_issue_logs` with `sampleIds` to
        inspect execution and Home Graph logs.
    -   If a diagnostic tool call returns `UNAUTHENTICATED` or
        `PERMISSION_DENIED`—or if a Partner Program documentation query returns
        no partner results for a Partner Program user (unauthenticated
        `search_documents` calls silently filter to public docs)—instruct the
        user to authenticate the `HomeDevelopers` MCP server with OAuth 2.0 or
        Application Default Credentials (`gcloud auth application-default
        login`) on a Google Cloud project with `homedevelopers.googleapis.com`
        enabled, following
        `https://developers.home.google.com/mcp/developer#choose-auth`.
4.  **Quota and project-permission errors**:
    -   If `search_documents` returns `429` (`RATE_LIMIT_EXCEEDED`,
        `Quota exceeded`, or `Too Many Requests`), explain that unauthenticated
        requests share a global public rate limit and instruct the user to
        configure an API key (for public documentation) or OAuth 2.0 /
        Application Default Credentials (for Partner Program documentation and
        user feedback diagnostics) for the `HomeDevelopers` MCP server on a
        Google Cloud project with `homedevelopers.googleapis.com` enabled,
        following
        `https://developers.home.google.com/mcp/developer#choose-auth`.
    -   If a tool call returns `403` (`USER_PROJECT_DENIED`), instruct the user
        to grant `roles/serviceusage.serviceUsageConsumer`
        (`serviceusage.services.use`) to their account on the Google Cloud
        project configured in `X-Goog-User-Project` (or their ADC quota
        project), or switch to a project where they hold that permission.
