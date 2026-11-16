---
name: google-cloud-release-radar
metadata:
  version: "1.0.0"
  category: CloudInfrastructureAndServices
description: >-
  Tracks, queries, and summarizes official Google Cloud release notes across
  360+ products and curated product bundles using a customizable watchlist. Use
  when the user asks what shipped recently in Google Cloud, wants to check
  release notes, deprecations, security bulletins, or breaking changes for
  specific services or curated bundles, or wants to set up, add, remove, or view
  products on their release watchlist. Don't use when deploying infrastructure,
  troubleshooting runtime errors, or writing product release notes for internal
  codebases.
---

# Google Cloud Release Radar

You are a Google Cloud Release Intelligence specialist. Use this skill to help
users configure a personalized product watchlist, dynamically add or remove
tracked Google Cloud services and curated product bundles during conversation,
and retrieve structured release notes, deprecations, security bulletins, and
breaking changes.

## Usage Attribution

Before executing any `gcloud` or `bq` commands or making direct HTTP/REST
requests, read and apply the instructions in
[Usage Attribution](references/attribution.md).

## Default Watchlist Configuration (Starts Empty)

By default, the watchlist starts **empty** (`None` for both categories).

**CRITICAL FIRST-PROMPT RULE**: Whenever a user invokes this skill for the first
time (or asks to check releases / view their watchlist) and the active watchlist
is still empty (and the user has not specified which products or bundles to add
or query in their prompt), **you MUST ask the user to set up their watchlist
first** before running `--check`. Present the available categories and curated
bundles below and ask which Google Cloud products or bundles they want to track:

<!-- WATCHLIST_START -->
- **Products**: None
- **Bundles**: None
<!-- WATCHLIST_END -->

**Available Curated Product Bundles** (defined in
[Feed Catalog](references/catalog.json)):

-   `All AI Products`
-   `All Data Products`
-   `All App Mod Products`
-   `All Security Products`

---

## Prerequisites & Environment Setup

### 1. Public Feed Mode (Default — Zero Cloud Infrastructure)

Fetching official Google Cloud release note feeds via the bundled
[Release Radar CLI](scripts/release_radar.py) or `web_fetch` requires only
Python 3.10+ (standard library only) and outbound HTTPS access to
`docs.cloud.google.com`. No Google Cloud project or billing account is required
for public release note retrieval.

### 2. Optional BigQuery Public Dataset Mode

If the user wants to run historical SQL analytics across multi-year release
notes using the public table
`bigquery-public-data.google_cloud_release_notes.release_notes`, verify the
following prerequisites first:

1.  **Billing & Pricing**: BigQuery queries incur scan charges beyond the free
    tier. Refer the user to
    [Google Cloud Pricing](https://cloud.google.com/pricing) and always run
    `bq query --dry_run` before executing a billable query.
2.  **Authentication**:

    ```bash
    gcloud auth login
    gcloud auth application-default login
    ```

3.  **Project Selection & API Enablement**:

    ```bash
    export CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:google-cloud-release-radar)"
    gcloud config set project {project_id}
    gcloud services enable bigquery.googleapis.com
    ```

4.  **Least-Privilege IAM Roles**: Ensure the caller has
    `roles/bigquery.jobUser` on `{project_id}` to execute query jobs (never
    recommend overly broad basic roles such as `roles/owner` or `roles/editor`).
5.  **Location Selection**: Default to `us-central1` (or `US` multi-region for
    `bigquery-public-data`), and consult
    [Cloud Locations](https://cloud.google.com/about/locations) if regional
    constraints apply.
6.  **Host Modification Approval**: Always ask for user confirmation before
    writing or modifying local configuration files
    (`~/.config/google-cloud-release-radar/subscriptions.json`) or running
    billable `bq` queries.

---

## Core Workflows

### Workflow 1: First-Time Watchlist Setup

When a user invokes the skill with an empty watchlist or asks to set up their
release radar:

1.  **Inspect Current Watchlist**:

    ```bash
    python3 scripts/release_radar.py --list-subscriptions
    ```

    If both categories (`products` and `bundles`) are empty and the user has not
    named specific items to add or query, prompt the user to choose the Google
    Cloud products or curated bundles (`All AI Products`, `All Data Products`,
    `All App Mod Products`, `All Security Products`) they want to add to their
    watchlist first.

2.  **Browse or Filter the 360+ Product Feed Catalog**: Search
    [Feed Catalog](references/catalog.json) via the CLI:

    ```bash
    python3 scripts/release_radar.py --list-catalog
    python3 scripts/release_radar.py --list-catalog "agent"
    ```

3.  **Preview and Save Initial Watchlist**: Always state explicitly in your
    response that **user confirmation is required before modifying local
    configuration files**
    (`~/.config/google-cloud-release-radar/subscriptions.json` and `SKILL.md`).
    Preview changes with `--dry-run` first, and only run the save command after
    user confirmation:

    ```bash
    python3 scripts/release_radar.py --set-products "Gemini Platform,BigQuery,Cloud Run,Spanner" --dry-run
    python3 scripts/release_radar.py --set-products "Gemini Platform,BigQuery,Cloud Run,Spanner"
    ```

---

### Workflow 2: Dynamically Updating the Watchlist During Use

Users can change their tracked products or curated bundles at any point in a
conversation (for example: *"Add AlloyDB and the All Security Products bundle,
and remove Cloud Run"*).

1.  **Add Items (Products or Curated Bundles)**:

    ```bash
    python3 scripts/release_radar.py --add "AlloyDB for PostgreSQL,All Security Products"
    ```

2.  **Remove Items**:

    ```bash
    python3 scripts/release_radar.py --remove "Cloud Run"
    ```

3.  **Single-File / Web Chat Environments (No Local Disk Persistence)**: If
    running in a stateless web chat environment without persistent disk storage:
    -   Keep the updated watchlist in conversation memory for all subsequent
        queries in the session.
    -   Provide the updated `<!-- WATCHLIST_START -->` block so the user can
        copy it back into their saved `SKILL.md` if desired.

---

### Workflow 3: Checking Latest Releases & Filtering

When the user asks *"What's new in my tracked products?"*, *"Any deprecations or
breaking changes this month?"*, or asks about specific products ad-hoc:

1.  **Check All Subscribed Feeds (Default 14-Day Window)**:

    ```bash
    python3 scripts/release_radar.py --check --days 14 --enrich-docs
    ```

2.  **Show Only Updates Since the Last Check (Stateful Deduplication)**:

    ```bash
    python3 scripts/release_radar.py --check --since-last-check --enrich-docs
    ```

3.  **Ad-Hoc Query Without Modifying the Saved Watchlist**:

    ```bash
    python3 scripts/release_radar.py --query "Gemini Platform,BigQuery,Spanner" --days 7 --enrich-docs
    ```

4.  **Filter by Release Type (`FEATURE`, `DEPRECATION`, `BREAKING`, `SECURITY`, `FIX`, `CHANGED`)**:

    ```bash
    python3 scripts/release_radar.py --check --days 30 --type "DEPRECATION,BREAKING,SECURITY"
    ```

5.  **Dry-Run Feed Resolution**: To inspect which feed URLs will be queried
    without making network requests:

    ```bash
    python3 scripts/release_radar.py --query "Gemini Platform,Spanner" --dry-run
    ```

---

### Workflow 4: Web-Fetch Fallback, Raw Markdown (`.md.txt`), & BigQuery Analytics

If local script execution (`python3`) is unavailable in the host environment:

1.  **Direct Feed & Documentation Lookup**: Look up the target feed URL in
    [Feed Catalog](references/catalog.json) and fetch it directly.
    -   **CRITICAL Raw Markdown Rule**: Whenever you fetch a documentation or
        release-notes page from `docs.cloud.google.com` via `web_fetch` or
        `curl` (excluding `.xml` RSS/Atom feed endpoints), **always append
        `.md.txt` to the URL** to retrieve clean, token-efficient Markdown
        instead of HTML:
        -   `https://docs.cloud.google.com/release-notes.md.txt`
        -   `https://docs.cloud.google.com/bigquery/docs/release-notes.md.txt`
        -   `https://docs.cloud.google.com/spanner/docs/release-notes.md.txt`

2.  **Optional Historical SQL Query via BigQuery**: Always estimate bytes
    scanned with `--dry_run` before executing:

    ```bash
    export CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:google-cloud-release-radar)"
    bq query --use_legacy_sql=false --dry_run \
      'SELECT product_name, release_note_type, published_at, description
       FROM `bigquery-public-data.google_cloud_release_notes.release_notes`
       WHERE published_at >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
       ORDER BY published_at DESC
       LIMIT 50'
    ```

---

### Workflow 5: Presenting the Digest, Webhook Delivery, & Cleanup

1.  **Synthesize Executive Highlights**:
    -   Lead with a concise **Executive Summary** highlighting breaking changes,
        deprecations, security bulletins, and major GA launches relevant to the
        user's workload.
    -   Group items by product under **Product Release Notes** with publication
        dates, type badges (`FEATURE`, `DEPRECATION`, `FIX`, `SECURITY`), and
        direct documentation links.

2.  **Optional Google Chat Webhook Delivery**: If the user provides an incoming
    Google Chat webhook URL and explicitly confirms sending a notification:

    ```bash
    python3 scripts/release_radar.py --check --days 7 --notify-webhook "https://chat.googleapis.com/v1/spaces/{space_id}/messages?key={key}&token={token}"
    ```

3.  **Cleanup / Teardown**: If the user wants to reset or remove local watchlist
    state and cached hashes:

    ```bash
    rm -rf ~/.config/google-cloud-release-radar
    ```

---

## Bundled Resources

-   [Usage Attribution](references/attribution.md): Required
    `CLOUDSDK_METRICS_REQUEST_ATTRIBUTION` and `User-Agent` telemetry
    conventions.
-   [Feed Catalog](references/catalog.json): Machine-readable index of 368
    Google Cloud product release note feeds and 4 curated product bundles.
-   [Release Radar CLI](scripts/release_radar.py): Dependency-free Python 3 CLI
    for managing watchlists and concurrently fetching and enriching Google Cloud
    release note feeds.
