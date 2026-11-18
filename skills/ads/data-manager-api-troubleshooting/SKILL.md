---
name: data-manager-api-troubleshooting
description: >-
  Diagnoses and fixes errors, warnings, and missing data for Data Manager API
  event and audience ingestion requests. Use when an IngestEvents,
  IngestAudienceMembers, RemoveAudienceMembers, RemoveAllAudienceMembers, or
  RetrieveRequestStatus call fails (INVALID_ARGUMENT, REQUIRED_FIELD_MISSING,
  INVALID_HEX_ENCODING, PERMISSION_DENIED, UNAUTHENTICATED,
  RESOURCE_EXHAUSTED, INVALID_REQUEST_ID), when
  a response has fieldWarnings, when checking request status or diagnostics,
  when request status shows FAILED or PARTIAL_SUCCESS or processing errors,
  when finding which records failed, or when a request returned 200 but
  conversions or audience members are missing. Don't
  use for writing new ingestion code (use the data-manager-api-event-ingestion
  or data-manager-api-audience-ingestion skills) or first-time credential
  setup (use the data-manager-api-setup skill).
metadata:
  version: "1.0.0"
  category: GoogleAds
---

# Data Manager API Troubleshooting

The Data Manager API reports problems in three places, at three different times.

## Step 1: Classify the problem

Ask for the exact error payload, response, or diagnostics output if the user
hasn't shared it.

| Symptom | When | What it means | Go to |
| :--- | :--- | :--- | :--- |
| Request throws an exception or returns 4xx/5xx | Immediately | The **entire** request was rejected. No records were ingested. | [Step 2](#step-2-fix-request-errors) |
| Request succeeds with `field_warnings` | Immediately | The request was accepted, but the flagged field had an issue (for example, an invalid or missing optional value). Don't resend. Fix the source data for future requests. | None |
| Request succeeded, but data is missing or lower than expected | Check `retrieve_request_status` 30 minutes to 24 hours later | Records can still fail during asynchronous processing. Diagnostics show per-destination results, including which records failed. | [Step 3](#step-3-check-request-status-and-diagnostics) |

## Step 2: Fix request errors

The API uses a fast-fail model: if any record fails synchronous validation, the
whole request fails and no records are processed. Fix the problem and resend the
**entire** request. To confirm a fix first, send the ingestion request with
`validate_only` set to `true`.

### Read the full error

For `INVALID_ARGUMENT`, the top-level `message` is always generic ("There was a
problem with the request."). Read **every** entry in the `google.rpc.BadRequest`
detail's `field_violations`, including `field` (a path with list indexes, such
as `events.events[1].user_data.user_identifiers[2]`), `reason` (an
`ErrorReason`), and `description`. For any error, also log `request_id` from
`google.rpc.RequestInfo` and include it in support requests.

In Python (`google.api_core.exceptions.GoogleAPICallError`), read `err.details`:

```python
from google.api_core import exceptions
from google.rpc import error_details_pb2

try:
  ...
except exceptions.GoogleAPICallError as err:
  for detail in err.details:
    if isinstance(detail, error_details_pb2.BadRequest):
      for v in detail.field_violations:
        print(v.field, v.reason, v.description)
    elif isinstance(detail, error_details_pb2.RequestInfo):
      print("request_id:", detail.request_id)
```

### Fix by error code

| Error code | What to do |
| :--- | :--- |
| `INVALID_ARGUMENT` (400) | Follow [Fix INVALID_ARGUMENT errors](references/request-errors.md#fix-invalid_argument-errors). |
| `UNAUTHENTICATED` (401), `PERMISSION_DENIED` (403) | Read `ErrorInfo.reason`, then follow [Permission errors](references/request-errors.md#permission-errors). |
| `RESOURCE_EXHAUSTED` (429) | Check `ErrorInfo.metadata.quota_limit`. For a per-minute limit, resend with exponential backoff and jitter. For a daily limit, don't resend until the quota resets at midnight Pacific Time. In both cases, reduce the request count by batching more records per request (up to 2,000 events or 10,000 audience members) and sending at most 10 requests concurrently. |
| `RetrieveRequestStatus` fails with `INVALID_REQUEST_ID` or `REQUEST_TOO_OLD` | Status exists only for recent requests that succeeded and didn't set `validate_only`. For `INVALID_REQUEST_ID`, check that the ID is the `request_id` from a successful, non-validation ingestion response (if the original request failed, fix it using its own error). For `REQUEST_TOO_OLD`, diagnostics are no longer available. |

For other error codes, check whether the error can be retried before resending.
See
[Best practices for error handling](https://developers.google.com/data-manager/api/devguides/concepts/understand-errors.md.txt#best-practices-for-error-handling).

## Step 3: Check request status and diagnostics

Each destination in the response has an overall `request_status`, error and
warning counts, and a request-type status with record and identifier counts.
Some audience data also has a match rate. Field names differ by request type
and data type. Use the fields in
[Request status and diagnostics](references/request-status.md).

### Requirements and timing

*   Diagnostics exist only for requests that succeeded and didn't set
    `validate_only`.
*   Wait at least 30 minutes after ingestion, then poll with exponential backoff
    until every destination reaches `SUCCESS`, `PARTIAL_SUCCESS`, or `FAILED`.
    Processing can take up to 24 hours. When writing code that reads request
    status, handle destinations still in `PROCESSING` by polling again later
    instead of reporting their results.

### Map records to their errors and warnings

`record_indices` are 0-based positions in the original request's `events` or
`audience_members` list. When a user asks which records failed or wants to fix
them, invert `error_info.error_counts` and `warning_info.warning_counts` for
each destination into a per-record list of errors and warnings. Resend only the
corrected records that had errors, and only to the destinations where they
failed. For warning-only records, fix the issue for future uploads.

To find what a processing reason means and how to fix it, see
[Processing reasons](references/request-status.md#processing-reasons).

## References

*   [Request errors](references/request-errors.md)
*   [Request status and diagnostics](references/request-status.md)
*   [Understand API errors](https://developers.google.com/data-manager/api/devguides/concepts/understand-errors.md.txt)
*   [Diagnostics](https://developers.google.com/data-manager/api/devguides/diagnostics.md.txt)
*   [Configure destinations and headers](https://developers.google.com/data-manager/api/devguides/concepts/destinations.md.txt)
*   [Best practices](https://developers.google.com/data-manager/api/devguides/concepts/best-practices.md.txt)
*   [Limits and quotas](https://developers.google.com/data-manager/api/devguides/limits.md.txt)
