# Errors and resolutions

Use this table when a PSH MCP tool call, REST request, or `gcloud` command
fails. When a failure prevents retrieving PSH **events** for a project, the
verdict for that project is `INCONCLUSIVE` with the failure as the reason;
never fall back to guessing.

| Observed signal | Cause | Resolution |
| :--- | :--- | :--- |
| `Malformed name: 'projects/{project_id}/events'` (or `/impacts`) | `parent` is missing `/locations/global` | Use `projects/{project_id}/locations/global`. |
| `Location {region} is not found or access is unauthorized.` | `parent` or `--location` names a region instead of `global` | PSH events and impacts are served only under `locations/global`. Filter by region client-side using `eventImpacts[].location.locationName` or resource paths in `asset.assetName`. |
| `Permission 'mcp.googleapis.com/tools.call' denied on resource ...` | Caller lacks `roles/mcp.toolUser` on `{project_id}`, or `{project_id}` is wrong | Confirm `{project_id}` from the prompt or alert. If correct, report `INCONCLUSIVE` (permission denied) and name `roles/mcp.toolUser` and `roles/servicehealth.viewer`. |
| `Permission denied on resource project {project_id}.` (on events) | Project does not exist, or caller lacks `roles/servicehealth.viewer` (`servicehealth.events.list`) | Confirm `{project_id}`; if correct, report `INCONCLUSIVE` (permission denied) and name `roles/servicehealth.viewer`. |
| `Permission 'servicehealth.impacts.list' denied`, `503 UNAVAILABLE`, or `404` on `impacts` (while `events` succeeded) | Custom event-only role omits `servicehealth.impacts.*`, or the `impacts` endpoint is unavailable | Never treat a failed `impacts` call as an empty list: keep the event-level verdict (`IMPACTED` or `RELATED` stays `IMPACTED`; never downgrade to `NO_IMPACT_IDENTIFIED` or switch to `INCONCLUSIVE`), report `"Resource-level impacts could not be retrieved: {reason}"` regardless of `relevance` (never claim no resources were listed), and never invent resource names. |
| `Service Health API has not been used in project ... or it is disabled` | `servicehealth.googleapis.com` is not enabled | Report `INCONCLUSIVE` (API disabled) and tell the user to enable `servicehealth.googleapis.com` (noting resource-level impacts require enablement 24h before an event starts). Do not enable it without user approval. |
| `Resource "projects/.../events/{event_id}" was not found` | Wrong `{event_id}` or wrong `{project_id}` | Take `name` verbatim from a `list_project_events` result; event IDs are scoped per project. |
| `(gcloud.service-health) Invalid choice: 'impacts'` | `impacts` is in Preview (`v1beta`) and not in the GA `gcloud` track | Use `gcloud beta service-health impacts` or the `v1beta` REST endpoint. |
| `invalid filter: unsupported filter field: "relevance"` (or `location`) on events | Field is not filterable on `events.list` | Drop it from `filter`; read `relevance` and `eventImpacts` from the results. |
| `invalid filter` on `event_impacts.product.product_name="..."` or `events="..."` | `=` used on a repeated/array field instead of `:` | Use the `:` (`HAS`) operator—for example `event_impacts.product.product_name:"Google Cloud SQL"` (exact, case-sensitive) or `events:"projects/{project_id}/locations/global/events/{event_id}"`. |
| `invalid filter: unsupported filter field` on `impacts` (for example `event`, `asset.assetType`, `updateTime`) | Wrong field name or operator on `impacts.list` | Use snake_case `events:"projects/{project_id}/locations/global/events/{event_id}"` (plural `events` with `:`), `asset.asset_name`, `asset.asset_type`, or `update_time`, or list without `filter` and match `events` client-side. |
| `unable to parse filter "update_time>=2026-..."` | Timestamp not quoted | Write `update_time>="2026-09-01T00:00:00Z"` (escape inner quotes inside JSON). |
| HTTP 429 or deadline exceeded | Rate limit or timeout | Retry once with backoff. If it fails again on events, report `INCONCLUSIVE` (rate limit or timeout). |
| Result too large to read | Many events or impacts | Narrow with `filter` and `pageSize`, or save the output to a temporary file outside the repository and extract only required fields. |
