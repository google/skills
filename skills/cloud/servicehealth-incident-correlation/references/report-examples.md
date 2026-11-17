# Report examples

These examples show the expected shape of a report. Event IDs, projects,
project numbers (`987654321098`), and text are synthetic placeholders; real
reports must quote retrieved PSH data.

## Contents

*   [Interactive: RELATED incident on a product without resource-level impacts](#interactive-related-incident-on-a-product-without-resource-level-impacts): Lines 15–43
*   [Interactive: RELATED incident on a supported product, no resource-level impacts listed](#interactive-related-incident-on-a-supported-product-no-resource-level-impacts-listed): Lines 45–71
*   [Interactive: product not covered by PSH](#interactive-product-not-covered-by-psh): Lines 73–85
*   [Headless: impacted resources listed by PSH](#headless-impacted-resources-listed-by-psh): Lines 87–112
*   [Headless: events call failed](#headless-events-call-failed): Lines 114–126

## Interactive: RELATED incident on a product without resource-level impacts

```text
Status: IMPACTED -- Project orders-frontend-prod is affected by incident EVT1001 (PSH relevance RELATED).

Project ID source: named in your message.

Incident EVT1001: "Compute Engine: elevated packet loss in us-east1". Active
since 2026-10-16T13:52Z (detailed state: CONFIRMED). Your VM packet loss
started at 14:05Z, inside the incident window, for the same product and region.
PSH marks this incident RELATED: it affects a product in a location your project
uses.

| Product               | Location | Status   | Start  | End     |
| :-------------------- | :------- | :------- | :----- | :------ |
| Google Compute Engine | us-east1 | AFFECTED | 13:52Z | ongoing |

Resource-level impacts: Resource-level impacts are not supported for Google
Compute Engine yet.

Latest symptom (PSH update 2026-10-16T14:30Z): "Compute Engine VM instances in
us-east1 may experience intermittent packet loss and elevated network latency."
Workaround: "Shift latency-sensitive traffic to backends in another region
until mitigation completes."

Links:
- Incident: https://console.cloud.google.com/servicehealth/incidentDetails/projects%2Forders-frontend-prod%2Flocations%2Fglobal%2Fevents%2FEVT1001?project=orders-frontend-prod
- PSH dashboard: https://console.cloud.google.com/servicehealth/incidents?project=orders-frontend-prod
```

## Interactive: RELATED incident on a supported product, no resource-level impacts listed

```text
Status: IMPACTED -- Project billing-db-prod is affected by incident EVT1002 (PSH relevance RELATED).

Project ID source: named in your message.

Incident EVT1002: "Cloud SQL: elevated connection errors in us-central1". Active
since 2026-10-16T15:10Z (detailed state: CONFIRMED). Your connection errors
started at 15:30Z, inside the incident window, for the same product and region.
PSH marks this incident RELATED.

| Product          | Location    | Status   | Start  | End     |
| :--------------- | :---------- | :------- | :----- | :------ |
| Google Cloud SQL | us-central1 | AFFECTED | 15:10Z | ongoing |
| Google Cloud SQL | us-east1    | RESOLVED | 15:10Z | 15:45Z  |

Resource-level impacts: PSH has not listed any resource-level impacts for this
incident. Resource-level impacts are not available for every Google Cloud SQL
incident yet, so this project can still be impacted.

Symptoms and workaround: No workaround published.

Links:
- Incident: https://console.cloud.google.com/servicehealth/incidentDetails/projects%2Fbilling-db-prod%2Flocations%2Fglobal%2Fevents%2FEVT1002?project=billing-db-prod
- PSH dashboard: https://console.cloud.google.com/servicehealth/incidents?project=billing-db-prod
```

## Interactive: product not covered by PSH

```text
Status: INCONCLUSIVE -- Impact on project marketing-site-prod could not be determined: Firebase Hosting is not supported by Personalized Service Health.

Project ID source: named in your message.

PSH returned no incidents for this project, and Personalized Service Health
does not cover Firebase Hosting, so PSH can neither confirm nor rule out a
Google-side problem for this service.

PSH dashboard: https://console.cloud.google.com/servicehealth/incidents?project=marketing-site-prod
```

## Headless: impacted resources listed by PSH

```text
Status: IMPACTED -- Project catalog-gke-prod is affected by incident EVT1003 (PSH relevance IMPACTED).

Project ID source: alert payload (incident.resource.labels.project_id).

Incident EVT1003: "GKE: elevated control plane API latency in us-central1".
Active since 2026-10-16T14:00Z (detailed state: CONFIRMED). The alert started
at 14:05Z, inside the incident window, for the same product and region.

| Product                  | Location    | Status   | Start  | End     |
| :----------------------- | :---------- | :------- | :----- | :------ |
| Google Kubernetes Engine | us-central1 | AFFECTED | 14:00Z | ongoing |

Resource-level impacts (listed by PSH):
- //container.googleapis.com/projects/987654321098/locations/us-central1/clusters/catalog-api
  (container.googleapis.com/Cluster) -- "Cluster control plane experienced
  elevated API latency in us-central1." (recorded 2026-10-16T14:12:00Z)

Symptoms and workaround: No workaround published.

Links:
- Incident: https://console.cloud.google.com/servicehealth/incidentDetails/projects%2Fcatalog-gke-prod%2Flocations%2Fglobal%2Fevents%2FEVT1003?project=catalog-gke-prod
- PSH dashboard: https://console.cloud.google.com/servicehealth/incidents?project=catalog-gke-prod
```

## Headless: events call failed

```text
Status: INCONCLUSIVE -- Impact on project payroll-prod could not be determined: permission denied on the Personalized Service Health API.

Project ID source: named in the request.

The caller lacks roles/servicehealth.viewer on project payroll-prod, so PSH
events could not be retrieved and PSH can neither confirm nor rule out a
Google-side problem.

PSH dashboard: https://console.cloud.google.com/servicehealth/incidents?project=payroll-prod
```
