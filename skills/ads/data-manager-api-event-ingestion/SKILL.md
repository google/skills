---
name: data-manager-api-event-ingestion
description: >-
  Guides developers through implementing event and conversion ingestion to
  Google products using the Data Manager API /v1/events:ingest endpoint
  and its associated client libraries. Use this skill when the user wants to upload
  offline conversions, enhanced conversions for leads, click conversions, call
  conversions, Google Analytics web or app events, or any other event ingestion
  use case supported by the Data Manager API. Don't use for uploading audience
  members (use the data-manager-api-audience-ingestion skill), or for debugging
  errors, checking request status, or investigating missing conversions (use
  the data-manager-api-troubleshooting skill).
metadata:
  version: "1.3.1"
  category: GoogleAds
---
# Data Manager API Event Ingestion

## Implementation Workflow

### Prerequisites

-   **Authentication & Library Installation**: If you need to set up access to
    the Data Manager API or install the client and utility libraries, refer to
    the `data-manager-api-setup` skill.

### Step 1: Identify Use Case & Read Documentation

-   **Determine Destination Account Type**: [CRITICAL] If it can't be determined
    from the user's context, consider clarifying which destination events are
    being ingested to before generating any code. This maps to the
    `account_type` field of the `operating_account` in the `Destination`,
    and also determines valid event identifiers and requirements.
-   **Identify User Intent**:
    -   **Answering questions about requirements or implementing ingestion
        code**: Retrieve the full contents of the relevant implementation guide
        for the destination and use case in the **Implementation guide** column
        below before answering or writing code. Use its **Event field
        requirements**, **Identifier requirements**, and **How Google handles
        multi-source data** sections as the source of truth for destination
        configuration, event and identifier requirements, and deduplication or
        update behavior.
    -   **Checking request status or inspecting errors**: Use the
        `data-manager-api-troubleshooting` skill.
    -   **Migrating from another Google API**: Refer to
        [Step 3: Retrieve Migration Guides](#step-3-retrieve-migration-guides)
        below to extract the full contents of the relevant field mapping guide.

| Destination (`operating_account.account_type`) | Use case | Implementation guide |
| :--- | :--- | :--- |
| **Google Ads** (`GOOGLE_ADS`) | Offline conversions, enhanced conversions for leads | [Send events](https://developers.google.com/data-manager/api/devguides/events/google-ads/offline/send-events.md.txt) |
| **Google Ads** (`GOOGLE_ADS`) | Multi-source conversions supplementing the Google tag | [Send events](https://developers.google.com/data-manager/api/devguides/events/google-ads/online/send-events.md.txt) |
| **Google Ads** (`GOOGLE_ADS`) | Store sales conversions | [Send events](https://developers.google.com/data-manager/api/devguides/events/google-ads/store-sales/send-events.md.txt) |
| **Google Ads** (`GOOGLE_ADS`) | Call conversions | [Send events](https://developers.google.com/data-manager/api/devguides/events/google-ads/call/send-events.md.txt) |
| **Google Analytics** (`GOOGLE_ANALYTICS_PROPERTY`) | Recommended and custom GA4 events | [Send events](https://developers.google.com/data-manager/api/devguides/events/analytics/recommended-custom-events/send-events.md.txt) |
| **Google Analytics** (`GOOGLE_ANALYTICS_PROPERTY`) | Multi-source events with a transaction ID | [Send events](https://developers.google.com/data-manager/api/devguides/events/analytics/online/send-events.md.txt) |
| **Floodlight** (`FLOODLIGHT_CONFIG`) | Floodlight offline conversions | [Send events](https://developers.google.com/data-manager/api/devguides/events/cm360/offline/send-events.md.txt) |
| **Floodlight** (`FLOODLIGHT_CONFIG`) | Multi-source conversions supplementing the Google or Floodlight tag | [Send events](https://developers.google.com/data-manager/api/devguides/events/cm360/online/send-events.md.txt) |

If the request doesn't match any row, fetch the
[Events overview](https://developers.google.com/data-manager/api/devguides/events.md.txt)
to find the right guide rather than guessing.

### Step 2: Retrieve Code Sample

> [!IMPORTANT]
> If writing or updating an ingestion script, ALWAYS retrieve the
> relevant code sample to use as a reference:

| Language | Sample |
| :--- | :--- |
| **Python** | [`ingest_events.py`](https://github.com/googleads/data-manager-python/blob/main/samples/events/ingest_events.py) |
| **Java** | [`IngestEvents.java`](https://github.com/googleads/data-manager-java/blob/main/data-manager-samples/src/main/java/com/google/ads/datamanager/samples/IngestEvents.java) |
| **PHP** | [`ingest_events.php`](https://github.com/googleads/data-manager-php/blob/main/samples/events/ingest_events.php) |
| **Node** | [`ingest_events.ts`](https://github.com/googleads/data-manager-node/blob/main/samples/events/ingest_events.ts) |
| **.NET**| [`IngestEvents.cs`](https://github.com/googleads/data-manager-dotnet/blob/main/samples/IngestEvents.cs) |

### Step 3: Retrieve Migration Guides

> [!IMPORTANT]
> If refactoring code to upgrade from another Google API, ALWAYS
> extract the full contents of the relevant field mapping guide.

#### Google Ads

*   **Offline conversions, enhanced conversions for leads** (migrating from the
    Google Ads API):
    [Google Ads Offline Conversions Migration Field Mappings](https://developers.google.com/data-manager/api/devguides/events/google-ads/offline/upgrade/field-mappings.md.txt)
*   **Store sales conversions** (migrating from the Google Ads API):
    [Google Ads Store Sales Migration Field Mappings](https://developers.google.com/data-manager/api/devguides/events/google-ads/store-sales/upgrade/field-mappings.md.txt)
*   **Call conversions** (migrating from the Google Ads API):
    [Google Ads Call Conversions Migration Field Mappings](https://developers.google.com/data-manager/api/devguides/events/google-ads/call/upgrade/field-mappings.md.txt)

#### Google Analytics

*   **Recommended and custom GA4 events** (migrating from the Google Analytics
    Measurement Protocol):
    [Google Analytics Measurement Protocol Migration Field Mappings](https://developers.google.com/data-manager/api/devguides/events/analytics/measurement-protocol/upgrade/field-mappings.md.txt)

#### Floodlight

*   **Floodlight offline conversions** (migrating from the Campaign Manager 360
    API):
    [Campaign Manager 360 Offline Conversions Migration Field Mappings](https://developers.google.com/data-manager/api/devguides/events/cm360/offline/upgrade/field-mappings.md.txt)

### Step 4: Implementation

Implement the ingestion logic using the following checkpoints:

-   [ ] **Initialize Client**: Instantiate the Data Manager client
    (`IngestionServiceClient`).
-   [ ] **Define Destinations**: Build the `Destination` object using the
    `product_destination_id` and the appropriate account configurations:
    `operating_account` (target account receiving data), `login_account` (if
    authenticating using a manager account or a data partner account), and
    `linked_account` (if you're a data partner accessing the account via a
    partner link to a manager account). The Data Manager API does not support
    sending events to Floodlight or Google Analytics destinations using a linked
    data partner. **STRONGLY RECOMMENDED**: Refer to the
    [Configure destinations and headers](https://developers.google.com/data-manager/api/devguides/concepts/destinations.md.txt)
    guide for more details on configuring destinations.
-   [ ] **Prepare Event Data**: Use the utility library helpers to format and
    normalize user identifiers correctly.
-   [ ] **Construct Payload**: Build the request payload
    (`IngestEventsRequest`) containing the destinations, event records,
    consent permissions, and `encoding` (`HEX` or `BASE64`, matching the
    encoding used to hash user identifiers).
-   [ ] **Support Validation**: Support sending the `validate_only` boolean
    option on the `IngestEventsRequest` to allow developers to validate schemas
    without actually uploading data.
-   [ ] **Send Request**: Execute `ingest_events` and record the returned
    `request_id` for later diagnostics. Keep the request payload, or a mapping
    from each event's position to your own record ID, with the `request_id`.
    Diagnostics identify failed events by their position in the request.
-   [ ] **Check for Ingestion Warnings**: If any non-required field had a
    validation failure, the response from `ingest_events` will also
    include `field_warnings`, a list of `FieldWarning` objects detailing the
    issues.
-   [ ] **Retrieve Request Status**: Check the status of the ingestion request
    using diagnostics. Since request processing is asynchronous, a
    successful ingestion response (HTTP 200 OK returning a `request_id`) only
    indicates the payload was received. To check if the records actually
    succeeded, partially succeeded, or failed to process, query the
    `client.retrieve_request_status` endpoint using the `request_id`, starting
    at least 30 minutes after sending. Skip this step when `validate_only` is
    `true`, because validation-only requests don't have diagnostics. Skipping
    this step for real requests is a common user mistake. To read the results
    or debug failures, use the `data-manager-api-troubleshooting` skill.

## Formatting

*   Fetch the [Format user data](https://developers.google.com/data-manager/api/devguides/concepts/formatting.md.txt)
    guide and use that as the source of truth for formatting and
    normalization rules.

*   Use the utility library to format, hash, and encrypt user data
    (emails, phone numbers, addresses).

    **Python Example:**

    ```python
    from google.ads.datamanager_util import Formatter
    from google.ads.datamanager_util.format import Encoding

    formatter: Formatter = Formatter()

    processed_email: str = formatter.process_email_address(
        email, Encoding.HEX
    )
    ```

## Critical Gotchas

*   Format `product_destination_id` as a numeric string. It is NOT a resource
    name path.
*   Format `event_timestamp` strictly in RFC 3339 format. Use the SDK's typed
    timestamp object instead of a raw string where available.
*   Nest click identifiers (`gclid`, `gbraid`, `wbraid`) inside the
    `ad_identifiers` block, not directly on the base event payload.
*   The enum values for `ConsentStatus` are `CONSENT_GRANTED` and
    `CONSENT_DENIED`. Do not use the values `GRANTED` and `DENIED`.
*   Note that `consent` can be set globally on the `IngestEventsRequest` or on
    individual `Event`s.
*   Verify that `UserIdentifier` uses `email_address` and `phone_number`.
    Do not use the Google Ads API fields `hashed_email` and
    `hashed_phone_number`.
*   Ensure the currency field on the event is named `currency`, not
    `currency_code`.
*   If sending hashed user identifiers in `user_data`, you must set the
    `encoding` field on the `IngestEventsRequest` to `HEX` or `BASE64`,
    matching the encoding passed to the utility library `Formatter`.
*   `event_source` is required for Google Ads offline conversions and enhanced
    conversions for leads (such as `WEB`), and must be `IN_STORE` for store
    sales.
*   Google Ads session attributes: Prefer setting
    `ad_identifiers.session_attributes` to the base64-encoded string captured
    from the form submission. Don't build this string from individual
    attributes. Only if you can't capture the encoded string, add an
    `ExperimentalField` to `experimental_fields` for each attribute (required:
    `gad_source`, `gad_campaignid`, `session_start_time_usec`; optional:
    `landing_page_url`, `landing_page_referrer`), and set
    `ad_identifiers.landing_page_device_info.user_agent`.
*   Use `IngestEvents` (`ingest_events`, `IngestEventsRequest`) for all
    conversion and event uploads. Do not suggest `IngestAdEvents`, which is
    only available to ad tech partner accounts on an allowlist.

## API Reference

*   [REST API Reference](https://developers.google.com/data-manager/api/reference/rest/v1/events/ingest.md.txt)
