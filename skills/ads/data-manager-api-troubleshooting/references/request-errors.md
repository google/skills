# Request errors

Use this reference to fix synchronous errors from ingestion requests.

## Contents

*   [Fix INVALID_ARGUMENT errors](#fix-invalid_argument-errors)
    *   [Fields required by use case](#fields-required-by-use-case)
*   [Permission errors](#permission-errors)

## Fix INVALID_ARGUMENT errors

1.  For each `field_violations` entry, use the `field` path to find where the
    problem is: `destinations[...]` points to destination or account settings,
    and `events.events[N]` or `audience_members.audience_members[N]` points to
    record N. The `reason`, an
    [`ErrorReason`](https://developers.google.com/data-manager/api/reference/rest/v1/ErrorReason),
    says what's wrong.
2.  Match the violation to the
    [client-side validation](https://developers.google.com/data-manager/api/devguides/concepts/best-practices.md.txt#client-side-validation)
    check it breaks:

    | Violation | Check |
    | :--- | :--- |
    | `REQUIRED_FIELD_MISSING` inside a compound object, such as `address` | Include the object only when all its required fields are present (`address` needs `given_name`, `family_name`, `region_code`, and `postal_code`). Otherwise drop the whole object. |
    | `REQUIRED_FIELD_MISSING` on any other field, or `NO_IDENTIFIERS_PROVIDED` | The field or identifier is required for this destination and use case. See [Fields required by use case](#fields-required-by-use-case). |
    | `INVALID_HEX_ENCODING`, `INVALID_BASE64_ENCODING`, `INVALID_SHA256_FORMAT` | Check that the value was hashed, and that the request's `encoding` field (`HEX` or `BASE64`) matches how the hashed values were encoded. |

    For other reasons, see
    [Format user data](https://developers.google.com/data-manager/api/devguides/concepts/formatting.md.txt).
3.  Fix the cause in the code that builds requests so later batches pass, not
    only in the failing records.
4.  A failed response might not list every problem in the request. After
    fixing the reported violations, resend with `validate_only` set to `true`
    until the request passes, then resend it with `validate_only` set to
    `false`.

### Fields required by use case

Fields marked optional in the API reference can be required for a specific
destination and use case, such as `transaction_id` for some event use cases or
`terms_of_service` for Customer Match uploads. Check the implementation guide
for the use case and link the user to it. For example, the guide for Google Ads
offline conversions is
[Send events](https://developers.google.com/data-manager/api/devguides/events/google-ads/offline/send-events.md.txt),
and the guide for Google Ads Customer Match is
[Upload data](https://developers.google.com/data-manager/api/devguides/audiences/google-ads/customer-match/upload-data.md.txt).
Every events **Send events** guide has an **Event field requirements** section
for required fields and an **Identifier requirements** section for the
identifiers each event needs. Check the section that matches the violation.
To find the guide for another use case, use the
`data-manager-api-event-ingestion` or `data-manager-api-audience-ingestion`
skill, or start from the
[Events overview](https://developers.google.com/data-manager/api/devguides/events.md.txt)
or the
[Audiences overview](https://developers.google.com/data-manager/api/devguides/audiences.md.txt).

## Permission errors

`UNAUTHENTICATED`, `SERVICE_DISABLED`, or a token without the
`https://www.googleapis.com/auth/datamanager` scope are setup problems. Use the
`data-manager-api-setup` skill.

`PERMISSION_DENIED` with valid credentials is usually an access path problem:
for ingestion requests, the API checks access using each `Destination`, not
request headers; for resource management requests (such as managing user lists
or partner links), it uses request headers (`login-account` and
`linked-account`). For the fields or headers to set in each access scenario, see
[Configure destinations and headers](https://developers.google.com/data-manager/api/devguides/concepts/destinations.md.txt).
