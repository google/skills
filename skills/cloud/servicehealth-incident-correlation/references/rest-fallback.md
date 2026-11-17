# REST API and gcloud fallback

Use the Service Health REST API (`curl`) or `gcloud` when no MCP client is
connected.

*   Prefer `curl` over `gcloud ... list` on projects with large event histories:
    REST evaluates `?filter=` server-side, whereas `gcloud` evaluates `--filter`
    client-side after auto-paginating the unfiltered collection (always pass
    both `--filter=...` and `--page-size=100` on `gcloud`).
*   Follow the attribution headers and environment variables in
    `references/attribution.md`. Always pass `{project_id}` explicitly (never
    the host's default `gcloud` project).

## Contents

*   [Authentication](#authentication): Lines 21–28
*   [List events](#list-events): Lines 30–67
*   [Get one event](#get-one-event): Lines 69–80
*   [List and get resource-level impacts (`v1beta` Preview)](#list-and-get-resource-level-impacts-v1beta-preview): Lines 82–113

## Authentication

```bash
TOKEN="$(CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:servicehealth-incident-correlation)" gcloud auth print-access-token)"
```

With user credentials (ADC), pass `-H "x-goog-user-project: {project_id}"` on
REST if needed for quota.

## List events

Always pass a bounded `?filter=...` URL-encoded on REST (or `--filter=...` with
`--page-size=100` on `gcloud`) unless the user explicitly asks for the full
event history, so listings do not return the full historical archive.

```bash
# Active incidents (live/ongoing check without a calendar date):
curl -s \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "User-Agent: curl agent-skills/1.0 (skill:servicehealth-incident-correlation)" \
  "https://servicehealth.googleapis.com/v1/projects/{project_id}/locations/global/events?filter=state%3DACTIVE&pageSize=100"

CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:servicehealth-incident-correlation)" \
gcloud service-health events list --project={project_id} \
  --location=global --page-size=100 --filter="state=ACTIVE" --format=json
```

When correlating a calendar timestamp, use
`state=ACTIVE OR update_time>="{reference_time_minus_24h}"`:

```bash
curl -s \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "User-Agent: curl agent-skills/1.0 (skill:servicehealth-incident-correlation)" \
  "https://servicehealth.googleapis.com/v1/projects/{project_id}/locations/global/events?filter=state%3DACTIVE%20OR%20update_time%3E%3D%222026-10-15T09%3A40%3A00Z%22&pageSize=100"

CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:servicehealth-incident-correlation)" \
gcloud service-health events list --project={project_id} \
  --location=global --page-size=100 --format=json \
  --filter='state=ACTIVE OR update_time>="2026-10-15T09:40:00Z"'
```

*   **REST pagination & views:** follow `nextPageToken` with
    `pageToken={page_token}` and the same `filter`. Omit `view=EVENT_VIEW_FULL`
    unless full update history is needed for every listed event.
*   **`gcloud beta`:** `gcloud beta service-health events list` queries `v1beta`
    (full view: `--view=event-view-full`).

## Get one event

```bash
curl -s \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "User-Agent: curl agent-skills/1.0 (skill:servicehealth-incident-correlation)" \
  "https://servicehealth.googleapis.com/v1/projects/{project_id}/locations/global/events/{event_id}"

CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:servicehealth-incident-correlation)" \
gcloud service-health events describe {event_id} --project={project_id} \
  --location=global --format=json
```

## List and get resource-level impacts (`v1beta` Preview)

`impacts` is served on **`v1beta`** REST and **`gcloud beta`** only (not in GA
`gcloud service-health`):

```bash
curl -s \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "User-Agent: curl agent-skills/1.0 (skill:servicehealth-incident-correlation)" \
  "https://servicehealth.googleapis.com/v1beta/projects/{project_id}/locations/global/impacts?filter=events%3A%22projects%2F{project_id}%2Flocations%2Fglobal%2Fevents%2F{event_id}%22&pageSize=100"

curl -s \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "User-Agent: curl agent-skills/1.0 (skill:servicehealth-incident-correlation)" \
  "https://servicehealth.googleapis.com/v1beta/projects/{project_id}/locations/global/impacts/{impact_id}"
```

```bash
CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:servicehealth-incident-correlation)" \
gcloud beta service-health impacts list --project={project_id} \
  --location=global --page-size=100 \
  --filter='events:"projects/{project_id}/locations/global/events/{event_id}"' \
  --format=json

CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:servicehealth-incident-correlation)" \
gcloud beta service-health impacts describe {impact_id} --project={project_id} \
  --location=global --format=json
```

See the REST references for
[events (`v1`)](https://docs.cloud.google.com/service-health/docs/reference/rest/v1/projects.locations.events.md.txt)
and [impacts (`v1beta`)](https://docs.cloud.google.com/service-health/docs/reference/rest/v1beta/projects.locations.impacts.md.txt).
