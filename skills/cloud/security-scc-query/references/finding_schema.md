# SCC Finding Schema Reference

This reference describes the common fields returned in the JSON payload of a
Security Command Center finding.

```json
{
  "name": "organizations/{org_id}/sources/{source_id}/findings/{finding_id}",
  "parent": "organizations/{org_id}",
  "resourceName": "//compute.googleapis.com/projects/{project_id}/zones/{zone}/instances/{instance_name}",
  "findingClass": "TOXIC_COMBINATION",
  "category": "TOXIC_COMBINATION_PUBLIC_VM_WITH_EXCESSIVE_PERMISSIONS",
  "state": "ACTIVE",
  "severity": "CRITICAL",
  "eventTime": "2026-06-16T17:41:31Z",
  "createTime": "2026-06-16T17:41:31Z",
  "attackExposure": {
    "score": 0.85,
    "attackExposureResult": "organizations/{org_id}/simulations/{sim_id}/attackExposureResults/{result_id}"
  },
  "findingDetails": {
    "description": "Publicly accessible instance with exploitable software vulnerability and the ability to assume service accounts"
  }
}
```

## Field Explanations

*   `name`: The unique identifier for the finding.
*   `parent`: The organization, folder, or project under which this finding is
    grouped.
*   `findingClass`: The high-level classification of the finding. Automated
    triaging requires this to be `TOXIC_COMBINATION`.
*   `state`: The current status of the finding. Typically `ACTIVE` or `MUTED`.
*   `attackExposure`: Holds information about the computed exposure risk and
    simulation result identifiers.
