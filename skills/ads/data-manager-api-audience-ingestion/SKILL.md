---
name: data-manager-api-audience-ingestion
description: >-
  Guides developers through managing (adding, removing, and clearing) audience members for Google products using
  the Data Manager API and its associated client libraries. Use this skill when the user wants to upload audience
  members, remove specific users, or clear/replace an entire audience for Customer Match, mobile device ID audiences, or any
  other audience use case supported by the Data Manager API. Don't use for uploading events or
  conversions (use the data-manager-api-event-ingestion skill).
metadata:
  version: 1.1
  category: GoogleAds
---

# Data Manager API Audience Ingestion

## Implementation Workflow

### Prerequisites

-   **Authentication & Library Installation**: If you need to set up access to
    the Data Manager API or install the client and utility libraries, refer to
    the `data-manager-api-setup` skill.
-   **Audience Creation (if needed)**: If the user does not have an existing
    audience or needs to create a new one, use the
    [Create an Audience](references/create-audience.md) reference. This step
    provides the `product_destination_id` needed for the ingestion or removal
    requests.

### Step 1: Identify Use Case & Read Documentation

-   **Determine Destination Account Type**: [CRITICAL] If it's not clear where
    the data is being sent (e.g., Google Ads, Display & Video 360, etc.), STOP
    and CLARIFY with the user BEFORE generating any code. Do not assume Google
    Ads by default. This maps to the `account_type` field of the
    `operating_account` in the `Destination`.
-   **Read the implementation guide**: Read the relevant guide for your
    destination and use case. Do this before answering questions or writing code
    because each destination has unique payload structures, consent rules, and
    required fields.

| Destination | Audience Type | Accepted Data Types | Upload Guide | Remove All/Replace All Guide |
| :--- | :--- | :--- | :--- | :--- |
| **Google Ads** | Customer Match | `composite_data.user_data` (contact info), `mobile_data` (device IDs), `user_id_data` (user IDs) | [Upload Data](https://developers.google.com/data-manager/api/devguides/audiences/google-ads/customer-match/upload-data.md.txt) | [Remove All/Replace All](https://developers.google.com/data-manager/api/devguides/audiences/google-ads/customer-match/remove-all-members.md.txt) |
| **Display & Video 360** (DV360) | Customer Match | `composite_data.user_data` (contact info), `mobile_data` (device IDs) | [Upload Data](https://developers.google.com/data-manager/api/devguides/audiences/display-video/customer-match/upload-data.md.txt) | [Remove All/Replace All](https://developers.google.com/data-manager/api/devguides/audiences/display-video/customer-match/remove-all-members.md.txt) |

### Step 2: Retrieve Code Sample

> [!IMPORTANT] If writing or updating an ingestion script, ALWAYS retrieve the
> relevant code sample to use as a reference:

| Language | Sample |
| :--- | :--- |
| **Python** | [`ingest_audience_members.py`](https://github.com/googleads/data-manager-python/blob/main/samples/audiences/ingest_audience_members.py) |
| **Java** | [`IngestAudienceMembers.java`](https://github.com/googleads/data-manager-java/blob/main/data-manager-samples/src/main/java/com/google/ads/datamanager/samples/IngestAudienceMembers.java) |
| **PHP** | [`ingest_audience_members.php`](https://github.com/googleads/data-manager-php/blob/main/samples/audiences/ingest_audience_members.php) |
| **Node** | [`ingest_audience_members.ts`](https://github.com/googleads/data-manager-node/blob/main/samples/audiences/ingest_audience_members.ts) |
| **.NET**| [`IngestAudienceMembers.cs`](https://github.com/googleads/data-manager-dotnet/blob/main/samples/IngestAudienceMembers.cs) |

### Step 3: Retrieve Migration Guides

> [!IMPORTANT] If refactoring code to upgrade from another Google API, ALWAYS
> extract the full contents of the relevant field mapping guide.

#### Google Ads

*   **Google Ads API Customer Match**: [Google Ads API to Customer Match
    Migration Field
    Mappings](https://developers.google.com/data-manager/api/devguides/audiences/google-ads/customer-match/upgrade/field-mappings.md.txt)

#### Display & Video 360

*   **Display & Video 360 API Customer Match**: [Display & Video 360 API to
    Customer Match Migration Field
    Mappings](https://developers.google.com/data-manager/api/devguides/audiences/display-video/customer-match/upgrade/field-mappings.md.txt)

### Step 4: Implementation

Implement the ingestion logic using the following checkpoints:

-   [ ] **Initialize Client**: Instantiate the Data Manager client
    (`IngestionServiceClient`).
-   [ ] **Define Destinations**: Build the `Destination` object using the
    `product_destination_id` and the appropriate account configurations:
    `operating_account` (target account receiving data), `login_account` (if
    authenticating using a manager account or a data partner account), and
    `linked_account` (if you're a data partner accessing the account via a
    partner link to a manager account). **STRONGLY RECOMMENDED**: Refer to the
    [Configure destinations and headers](https://developers.google.com/data-manager/api/devguides/concepts/destinations.md.txt)
    guide for more details on configuring destinations.
-   [ ] **Format User Data**: If sending an `IngestAudienceMembersRequest` or
    `RemoveAudienceMembersRequest`, refer to **[Formatting User
    Data](references/formatting.md)** to properly normalize and hash user identifiers using
    the utility library.
-   [ ] **Construct Payload**: Build the appropriate request payload based on
    the operation:
    *   **Add**: `IngestAudienceMembersRequest`
    *   **Remove**: `RemoveAudienceMembersRequest`
    *   **Remove All**: `RemoveAllAudienceMembersRequest`
-   [ ] **Support Validation**: Support sending the `validate_only` boolean
    option on the payload to allow developers to validate schemas without
    actually applying changes.
-   [ ] **Send Request**: Execute the appropriate method and record the returned
    `request_id` for later diagnostics:
    *   **Add**: `ingest_audience_members`
    *   **Remove**: `remove_audience_members`
    *   **Remove All**: `remove_all_audience_members`
-   [ ] **Check for Ingestion Warnings**: If any non-required field had a
    validation failure, the response from `ingest_audience_members` will also
    include `field_warnings`, a list of `FieldWarning` objects detailing the
    issues.
-   [ ] **Retrieve Request Status**: Check the status of the ingestion request
    using diagnostics. Since request processing is asynchronous, a successful
    response (HTTP 200 OK returning a `request_id`) only indicates the payload
    was received. To check if the records actually succeeded, partially
    succeeded, or failed to process, query `client.retrieve_request_status`
    using the `request_id`. Skipping this step is a common user mistake.

## Critical Gotchas

*   If sending hashed user identifiers in `user_data` for
    `ingest_audience_members` or `remove_audience_members`, you must set the
    `encoding` field on the `IngestAudienceMembersRequest` to `HEX` or `BASE64`.
*   If *uploading* to a Customer Match audience, the `terms_of_service` field is
    required on the `IngestAudienceMembersRequest` to indicate the user has
    accepted the policies.
*   Only set the `address` field on `UserIdentifier` if all required fields
    (`postal_code`, `family_name`, `given_name`, `region_code`) are present;
    incomplete `address` fields will cause the API request to fail.
*   `product_destination_id` must be a numeric string. It is NOT a resource
    name.
*   The enum values for `ConsentStatus` are `CONSENT_GRANTED` and
    `CONSENT_DENIED`. Do not use the values `GRANTED` and `DENIED`.
*   Field names on `UserIdentifier` are `email_address` and `phone_number`. Do
    not use the Google Ads API field names `hashed_email` and
    `hashed_phone_number`.
*   Do not call the diagnostics endpoint (`retrieve_request_status`) if
    `validate_only` is set to `true`.

## Error Handling & Troubleshooting

### Inspecting Error Payloads & Ingestion Warnings

> [!IMPORTANT]
> Refer to [Understand API Errors](https://developers.google.com/data-manager/api/devguides/concepts/understand-errors.md.txt)
> for a detailed guide on how to understand the structure of errors and warnings
> returned by the API.

### Retrieving Request Status (Diagnostics)

Periodically poll for status using exponential backoff, starting at least 30
minutes after sending the request.

1.  Call `client.retrieve_request_status` using
    `RetrieveRequestStatusRequest(request_id=...)`.
2.  Loop through `request_status_per_destination` in the response to inspect
    each target's `request_status`.
3.  If processing is complete and `request_status` is `SUCCESS`,
    `PARTIAL_SUCCESS`, or `FAILED`, inspect diagnostic values:
    *   **Audience Status**: Check the status specific to your request:
        *   **Ingest**: Check the data-type-specific status nested under
            `audience_members_ingestion_status` (e.g.,
            `composite_data_ingestion_status`).
        *   **Remove Individual Members**: Check the data-type-specific status
            nested under `audience_members_removal_status` (e.g.,
            `composite_data_removal_status`).
        *   **Remove All Members**: There are no nested status fields or record
            counts available to check for this request type.
        *   **Record Count**: If applicable (ingest or remove individual
            members), check `record_count` (nested inside the data-type-specific
            status object) which includes both success and failure.
        *   **Identifier Counts**: If applicable (ingest or remove individual
            members), check the data-type-specific count field nested inside the
            status object (e.g., `data_type_counts` if uploading or removing
            composite data, or `mobile_id_count` if uploading or removing
            mobile IDs). Refer to the [Diagnostics
            Guide](https://developers.google.com/data-manager/api/devguides/diagnostics.md.txt)
            for other count fields.
        *   **Match Rate Range**: For uploads of `user_data` and
            `composite_data`, check `upload_match_rate_range` nested inside the
            status object.
    *   **Error Details**: If status is `FAILED` or `PARTIAL_SUCCESS`, inspect
        each error's `reason` and `record_count` under
        `error_info.error_counts`.
    *   **Warning Details**: Inspect each warning's `reason` and `record_count`
        under `warning_info.warning_counts` (even if the destination status is
        `SUCCESS`).

## API Reference

*   [Send audience members guide](https://developers.google.com/data-manager/api/devguides/audiences/send-audience-members.md.txt)
*   [REST API Reference: Ingest](https://developers.google.com/data-manager/api/reference/rest/v1/audienceMembers/ingest.md.txt)
*   [REST API Reference: Remove](https://developers.google.com/data-manager/api/reference/rest/v1/audienceMembers/remove.md.txt)
*   [REST API Reference: Remove All](https://developers.google.com/data-manager/api/reference/rest/v1/audienceMembers/removeAll.md.txt)
