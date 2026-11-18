# Request status and diagnostics

Use this reference to read `RetrieveRequestStatusResponse` diagnostics for
event and audience requests.

## Status fields by request type

`RetrieveRequestStatusResponse.request_status_per_destination[]` has one entry
per destination:

```
destination
request_status                 # SUCCESS, PROCESSING, FAILED, PARTIAL_SUCCESS
error_info.error_counts[]      # reason, record_count, record_indices[]
warning_info.warning_counts[]  # same fields as error_counts
# Exactly one of, set by the original request type:
events_ingestion_status             # IngestEvents: record_count
audience_members_ingestion_status   # IngestAudienceMembers: see table below
audience_members_removal_status     # RemoveAudienceMembers: see table below
remove_all_audience_members_status  # RemoveAllAudienceMembers: no fields
```

`audience_members_ingestion_status` and `audience_members_removal_status` each
contain exactly one status field, set by the type of audience data in the
request. Every status field has `record_count`, plus:

| Ingestion status field | Removal status field | Other fields |
| :--- | :--- | :--- |
| `user_data_ingestion_status` | `user_data_removal_status` | `user_identifier_count`. Ingestion also has `upload_match_rate_range`. |
| `mobile_data_ingestion_status` | `mobile_data_removal_status` | `mobile_id_count` |
| `pair_data_ingestion_status` | `pair_data_removal_status` | `pair_id_count` |
| `user_id_data_ingestion_status` | `user_id_data_removal_status` | `user_id_count` |
| `ppid_data_ingestion_status` | `ppid_data_removal_status` | `ppid_count` |
| `composite_data_ingestion_status` | `composite_data_removal_status` | `data_type_counts[]` (`type`, `count`). Ingestion also has `upload_match_rate_range`. |
| `google_user_id_data_ingestion_status` | `google_user_id_data_removal_status` | `google_user_id_count` |
| `partner_provided_id_data_ingestion_status` | `partner_provided_id_data_removal_status` | `partner_provided_id_count` |

```python
from google.ads.datamanager_v1 import IngestionServiceClient, RetrieveRequestStatusRequest

client = IngestionServiceClient()
response = client.retrieve_request_status(
    RetrieveRequestStatusRequest(request_id=request_id)
)
for status in response.request_status_per_destination:
    # If status.request_status is PROCESSING, wait and poll again.
    # Otherwise, read the fields listed above.
    ...
```

If a field is missing from this list, see
[`RequestStatusPerDestination`](https://developers.google.com/data-manager/api/reference/rpc/google.ads.datamanager.v1#requeststatusperdestination)
or
[Check event or audience status per destination](https://developers.google.com/data-manager/api/devguides/diagnostics.md.txt#event_or_audience_status)
instead of searching the client library or other skills.

## Processing reasons

`ErrorCount.reason` is a
[`ProcessingErrorReason`](https://developers.google.com/data-manager/api/reference/rpc/google.ads.datamanager.v1#processingerrorreason),
and `WarningCount.reason` is a
[`ProcessingWarningReason`](https://developers.google.com/data-manager/api/reference/rpc/google.ads.datamanager.v1#processingwarningreason).
Look up a reason's meaning in the reference.

A warning means the record was processed, but part of it wasn't used. For
example, `PROCESSING_WARNING_REASON_USER_IDENTIFIER_DECRYPTION_ERROR` means the
encrypted user identifiers couldn't be decrypted, so the event was processed
using only its ad identifiers. Don't resend warning-only records. Fix the source
data for future uploads.
