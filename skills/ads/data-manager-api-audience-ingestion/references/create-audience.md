# Create an Audience (User List)

If the user needs to create a new audience before ingesting data, follow these
steps.

## Reference

[CRITICAL] Follow the relevant guide for sample requests and more information on
how to create an audience using the Data Manager API:

*   **Google Ads Customer Match**: [Create a Customer Match audience](https://developers.google.com/data-manager/api/devguides/audiences/google-ads/customer-match/create-audience.md.txt)
*   **Display & Video 360 Customer Match**: [Create a Customer Match audience](https://developers.google.com/data-manager/api/devguides/audiences/display-video/customer-match/create-audience.md.txt)

## Common Mistakes & Gotchas

The below examples are in Python, but the concepts apply to all client libraries.

1.  The correct client is `UserListServiceClient`, not `UserListsClient`.

```python
from google.ads import datamanager_v1

user_list_client = datamanager_v1.UserListServiceClient()
```

2.  Do not pass Google Ads specific headers like `login-customer-id` or
    `developer-token`. If required, set `login-account` or `linked-account`
    headers formatted as resource names (e.g.,
    `accountTypes/{account_type}/accounts/{id}`) for resource management
    requests.

    *   Set `login-account` if authenticating using a manager account or a data
        partner account.
    *   Set `linked-account` if you're a data partner accessing the account via
        a partner link to a manager account.
    *   Consult the [Configure destinations and
        headers](https://developers.google.com/data-manager/api/devguides/concepts/destinations.md.txt)
        documentation for example headers in different resource management
        request access scenarios.

```python
headers = []
account_type = "GOOGLE_ADS"
login_account_id = "1234567890"

if login_account_id:
    headers.append(
        (
            "login-account",
            f"accountTypes/{account_type}/accounts/{login_account_id}",
        )
    )

response = user_list_client.create_user_list(
    parent=parent_account, user_list=user_list_data, metadata=headers
)
```