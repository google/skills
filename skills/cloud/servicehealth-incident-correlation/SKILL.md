---
name: servicehealth-incident-correlation
metadata:
  version: "1.0.0"
  category: CloudObservabilityAndMonitoring
description: >-
  Checks Personalized Service Health (PSH) events and resource-level impacts to
  determine whether a Google Cloud incident affects a project or its resources,
  returning an impact verdict with affected resources, published symptoms, and
  workarounds. Use when asked whether Google Cloud is having an outage or
  affecting a project or its resources, when looking up a PSH event, or when
  triaging live Google Cloud workload issues or alerts whose symptoms suggest a
  possible Google Cloud service disruption—even if the user does not suspect an
  outage. Don't use for local code or build errors, routine alerts or
  automations that neither ask for a service health check nor suggest a platform
  disruption, configuring PSH alerts, or checking non-project-specific public
  status.
---

# Personalized Service Health incident correlation

Correlates
[Personalized Service Health (PSH)](https://docs.cloud.google.com/service-health/docs/overview.md.txt)
events (`v1`) and resource-level impacts (`v1beta`, Preview) with observed
workload symptoms (product, location, resource, time) to return a per-project
impact verdict. Read-only: relay published PSH symptoms and workarounds without
modifying resources or inventing incident data.

> [!IMPORTANT]
> **The costliest mistake is a false all-clear.** Telling a responder "not
> Google" during an active Google Cloud incident misdirects incident response.
> When a PSH events call fails or the customer's product is not covered by PSH,
> the verdict is `INCONCLUSIVE`, never `NO_IMPACT_IDENTIFIED`.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Prerequisites

*   **Target project:** Pass `{project_id}` explicitly on every call; never run
    `gcloud config set project`.
*   **Billing:** The project must have an active billing account attached.
*   **API enablement:** Requires `servicehealth.googleapis.com` on
    `{project_id}` (`gcloud services enable servicehealth.googleapis.com
    --project={project_id}`; ask before enabling). Resource-level impacts
    (Preview) require enablement at least **24 hours before** an incident
    starts.
*   **Authentication & IAM:** Authenticate via `gcloud auth login`,
    `gcloud auth application-default login`, or
    `GOOGLE_APPLICATION_CREDENTIALS` (install the
    [Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt)
    if `gcloud` is missing). Requires `roles/servicehealth.viewer` on
    `{project_id}` (`servicehealth.events.*` and `servicehealth.impacts.*`;
    custom roles may omit `impacts`), plus `roles/mcp.toolUser` for remote MCP.
*   **Transports:** Use the
    [PSH remote MCP server](https://docs.cloud.google.com/service-health/docs/use-service-health-mcp.md.txt)
    (`https://servicehealth.googleapis.com/mcp`, scope
    `https://www.googleapis.com/auth/servicehealth.readonly`). Read
    [REST API and gcloud fallback](references/rest-fallback.md) only if the MCP
    server is unavailable.

## Workflow

### Step 1: Determine scope

1.  **Project ID.** Query only a project named in the prompt/conversation, an
    alert payload (`incident.resource.labels.project_id`, else
    `incident.scoping_project_id`), a resource path `projects/{project_id}/...`,
    or caller context. **Never fall back to the host's default `gcloud` project
    or `GOOGLE_CLOUD_PROJECT`**: querying the agent's own host project produces
    false signals for unrelated stacks.
2.  **Observed context.** Extract any product, location, named resource, and
    reference time (alert `incident.started_at` in Unix seconds, a user-given
    time with relative times such as "20 minutes ago" converted to UTC, or
    now).
3.  **Missing scope.**
    *   *Interactive:* Ask only when an essential identifier is missing (an
        unnamed workload project ID, or a question about a specific event
        without its event ID). When no workload project was named, ask solely
        for the Google Cloud project ID without issuing an impact verdict
        (`Status: ...`) or listing events from any environment, host, or quota
        project. Broad checks ("Are there any outages?") for a named project
        need no narrowing by service or region.
    *   *Headless (alert, notification, or automated caller):* Never wait for
        human input; when no workload project ID is present, return
        `INCONCLUSIVE` right away, naming the missing project ID, without
        substituting any environment or quota project.
4.  **PSH coverage.** Whenever web access is available, fetch the live
    [Supported products and locations](https://docs.cloud.google.com/service-health/docs/supported-products-locations.md.txt)
    page first; otherwise use the [PSH coverage](references/coverage.md)
    snapshot. Both list onboarded products and mark emerging incident (`*`),
    `IMPACTED` relevance (`†`), and resource-level impact (`‡`, Preview)
    support.

### Step 2: Retrieve incidents (bounded)

All PSH resources use `parent` `projects/{project_id}/locations/global`. Pass
`pageSize: 100` and follow all `nextPageToken` pages (`list_project_events`
defaults to `pageSize=10` and orders results alphabetically by `event_id`, not
newest-first). Take event resource names verbatim from retrieved events or the
prompt.

MCP tools:

*   `list_project_events` (`parent`, `filter`, `pageSize`, `pageToken`): lists
    events without `updates`. Each `eventImpacts` entry carries the granular
    status of one product/location pair: `state` (`AFFECTED` or `RESOLVED`),
    `startTime`, and `endTime`. Filterable fields (space-joined AND):
    `category`, `state`, `update_time`, and
    `event_impacts.product.product_name` (repeated field: requires `:` for
    exact, case-sensitive element match; `=` fails with `invalid filter`).
    **`relevance`, location, `startTime`, and `endTime` are not filterable.**
*   `get_project_event` (`name`): fetches one event with `updates` (symptoms and
    workarounds).
*   `list_project_impacts` (`parent`, `filter`, `pageSize`, `pageToken`): lists
    resource-level impacts (Preview `Impact` resources); scope it per event as
    in Step 3.
*   `get_project_impact` (`name`): fetches one resource-level impact by ID.

**Always pass a bounded `filter` on `list_project_events`** (and `?filter=` or
`--filter=` on REST/`gcloud`) unless the user explicitly asks for the full
event history, since an unfiltered call returns the full historical archive:

| Situation | Event `filter` |
| :--- | :--- |
| Live/ongoing check with no symptom start time ("Is anything down right now?") | `state=ACTIVE` |
| Correlating a symptom or alert start time (`YYYY-MM-DD...`, Unix `started_at`, or a relative time such as "20 minutes ago" converted to UTC) | `state=ACTIVE OR update_time>="{reference_time_minus_24h}"` |
| Product known (exact, case-sensitive name from `coverage.md`; combine variants with `OR`, or omit only the product clause while keeping `state` or `update_time` and match `productName` client-side) | add `event_impacts.product.product_name:"{product_name}"` |
| Recently resolved check (only when asked) | `update_time>="{now_minus_n_hours}"` |

For example, correlating symptoms that started at 2026-10-16T14:05:00Z on
Compute Engine (attribution prefix from Usage Attribution omitted):

```bash
# MCP
list_project_events {"parent": "projects/{project_id}/locations/global",
  "filter": "state=ACTIVE OR update_time>=\"2026-10-15T14:05:00Z\"",
  "pageSize": 100}

# gcloud fallback: --filter is required here too
gcloud service-health events list --project={project_id} --location=global \
  --page-size=100 --format=json \
  --filter='state=ACTIVE OR update_time>="2026-10-15T14:05:00Z"'
```

Quote RFC 3339 timestamps (`update_time>="2026-09-01T00:00:00Z"`). Save large
responses to a temp file outside the repository rather than reading raw JSON
into context, and summarize large multi-event listings by product and location.

### Step 3: Correlate with what was observed

1.  **Product and location.** Keep incidents matching the observed product and
    location (or all active incidents on a general project check). Regions,
    zones, multi-regions (such as `us`, `europe`, `asia`), and `global` are
    distinct PSH locations, and any hierarchy between them is product-specific:
    *   Exact location named (e.g., `europe-west1` or `us-west1-a`): stay within
        that exact location for the impact verdict. If no incident matches that
        exact location, still mention active or recently closed incidents in
        proximate locations (e.g., other zones in `us-west1`, its containing
        region, or a `europe` multi-region incident) as helpful context without
        marking the project `IMPACTED`.
    *   Vague location named (e.g., "Europe" or "US"): match broadly across
        every location that fits the description.

    If an `eventImpacts` entry omits `location` (e.g., emerging or informational
    events), check `title` and `description` before ruling out a location match.
2.  **Event state.** Before checking the timeline:
    *   `detailedState` `MERGED`: consolidated into `parentEvent`, not resolved.
        Because closed (`MERGED`) events receive no further updates, follow
        `parentEvent` via `get_project_event` until reaching a root event that
        is not `MERGED`, and replace the merged events with it. Treat the root
        event as the **single source of truth** for active/closed state,
        `relevance`, impact verdict, linked `impacts`, and published
        symptoms/workarounds (never carry forward superseded child symptoms, and
        assess the root event even when its `eventImpacts` names an underlying
        service).
    *   `detailedState` `EMERGING` (Google is still investigating): an active
        incident, reported with the emerging-incident wording in Step 5.
    *   `detailedState` `FALSE_POSITIVE` or `AUTO_CLOSED`: does **not** match.
3.  **Timeline.** Pick the window, then compare the reference time with it.
    *   *Window:* when a location was named, use the `eventImpacts` entries
        matching the observed product and location. The window opens at their
        earliest `startTime`, stays open while any of them is `AFFECTED`, and
        closes at their latest `endTime` once all are `RESOLVED`, even if the
        event stays `ACTIVE` elsewhere. Otherwise, or when the matching entries
        carry no granular status, use the event's `startTime` to `endTime` (open
        while the event is `ACTIVE`).
    *   *Comparison* (`startTime` often lags symptom onset):
        *   Reference time inside the window: **matches**.
        *   Up to **4 hours before** the window opens: **matches** (note that
            symptoms preceded `startTime`).
        *   More than 4 hours before the window opens: does **not** match
            (mention only as a possible aggravating factor since `startTime`).
        *   Window closed within **1 hour before** the reference time: **recent
            close** (`INCONCLUSIVE`); state how long before the reference time
            it closed.
        *   Window closed more than 1 hour before the reference time: does
            **not** match.
4.  **Event details.** Call `get_project_event` for surviving matches and read
    the latest update's symptom and workaround (unless full history was
    requested).
5.  **Resource-level impacts (informational only).** Query
    `list_project_impacts` (or its REST/`gcloud beta` equivalent) with
    `filter` `events:"{event.name}"` for every
    surviving incident (the root event, never a `MERGED` one) and report what
    it returns, but never derive the verdict from it. Even for products with
    resource-level impact coverage, product teams can detect resource-level
    impact only for some incidents and PSH does not say which, so an empty list
    never means "not impacted".
    *   `asset.assetName` uses numeric `{project_number}`, not `{project_id}`—
        match customer-named resources by `assetType`, location, and resource
        name. If a named resource is absent while other project resources
        appear, report both facts.
6.  **Fresh state.** Re-fetch incident data from earlier turns or alert payloads
    before issuing a verdict.

### Step 4: Issue the verdict

PSH `Event.relevance` and the skill verdict are distinct, and the verdict comes
from events only: resource-level impact results (listed impacts, an empty list,
or a failed call) never change it.

1.  **`IMPACTED`** if any matching incident's `Event.relevance` is `IMPACTED`
    or `RELATED`. The verdict makes no distinction between the two; Step 5
    reports each event's `relevance`. **Never treat `RELATED` as "not impacted"
    or skip it when asked for "only impacting" incidents**: it is PSH's
    strongest signal for products without project-level or resource-level
    impact support.
2.  **`INCONCLUSIVE`** if the `events` call failed, the observed product is not
    onboarded to PSH, the project ID is missing in a headless flow, or a
    matching incident's window (Step 3) closed within 1 hour before the
    reference time. State why. A failed `impacts` call alone never makes the
    verdict `INCONCLUSIVE`.
3.  **`NO_IMPACT_IDENTIFIED`** when `events` succeeded for a PSH-covered product
    and:
    *   No incident matches, **or**
    *   Every match has a `relevance` other than `IMPACTED` or `RELATED`
        (`NOT_IMPACTED`, `PARTIALLY_RELATED`, or `UNKNOWN`).

    **Never present this as an all-clear**: incident declaration can lag
    symptoms. State this caveat and suggest checking the workload or re-checking
    PSH if symptoms persist.

### Step 5: Report

Report in concise prose for interactive and headless callers alike, with the
granular status table below (see
[Report examples](references/report-examples.md)). For multi-project checks,
give each project its own verdict and describe shared incidents once. Include in
order:

1.  **Impact verdict** (one per project; use these exact tokens, the second
    `IMPACTED` form for `EMERGING` incidents, and list every matching event ID):
    *   `Status: IMPACTED -- Project {project_id} is affected by incident {event_id} (PSH relevance {relevance}).`
    *   `Status: IMPACTED -- Project {project_id} matches emerging incident {event_id}, which Google is still investigating (PSH relevance {relevance}).`
    *   `Status: NO_IMPACT_IDENTIFIED -- No PSH incident impacting project {project_id} was identified at this time.`
    *   `Status: INCONCLUSIVE -- Impact on project {project_id} could not be determined: {reason}.`
2.  **Project ID source** (prompt, alert payload, resource name, request
    context).
3.  **Event summary** (one per matching event; every active event on a general
    project check): title, event ID, `relevance`, state, window, and how it
    correlates with observed symptoms. List incidents in proximate locations
    separately as context.
4.  **Granular status** (per event, right after its summary): a table with one
    row per `eventImpacts` entry, so the status of each product and location
    stands out (omit it when no entry carries granular status):

    | Product | Location | Status | Start | End |
    | :--- | :--- | :--- | :--- | :--- |
    | {productName} | {locationName} | {AFFECTED or RESOLVED} | {startTime} | {endTime, or "ongoing"} |
5.  **Resource-level impacts** (per event): each returned impact's
    `assetName`, `assetType`, and `description`/timestamps, or when none were
    returned:
    *   Empty `impacts` on a product with resource-level impact coverage: `"PSH
        has not listed any resource-level impacts for this incident.
        Resource-level impacts are not available for every {product} incident
        yet, so this project can still be impacted."`
    *   Empty `impacts` on a product/resource type without coverage:
        `"Resource-level impacts are not supported for
        {product_or_resource_type} yet."`
    *   Failed `impacts` call: `"Resource-level impacts could not be retrieved:
        {reason}"`, with the same failure detail as for a failed `events` call
        (never claim none were listed, and never invent resource names)
6.  **Symptoms and workarounds** (per event): quote the latest update ("No
    workaround published" if empty).
7.  **PSH links**: per event,
    `https://console.cloud.google.com/servicehealth/incidentDetails/{event_name}?project={project_id}`
    (`/` in `event.name` encoded as `%2F`); and in every report whose project ID
    is known, whatever the verdict, the events dashboard
    `https://console.cloud.google.com/servicehealth/incidents?project={project_id}`.

## References

Read each reference only when its condition applies, to keep context small:

*   [Usage Attribution](references/attribution.md): before the first command.
*   [PSH coverage: supported products and resource-level impacts](references/coverage.md):
    only when the live Supported products and locations page cannot be fetched.
*   [Errors and resolutions](references/errors.md): only after a call fails.
*   [REST API and gcloud fallback](references/rest-fallback.md): only when MCP
    is unavailable.
*   [Report examples](references/report-examples.md): when writing the report.
*   [PSH concepts](https://docs.cloud.google.com/service-health/docs/concepts.md.txt)
    and [PSH MCP reference](https://docs.cloud.google.com/service-health/docs/reference/mcp.md.txt)
