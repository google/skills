# Google Ads API Python Setup Reference

This guide outlines how to configure, install, and write your first Google Ads API call using Python.

## Prerequisites

> [!IMPORTANT]
> **Action Required: Dynamic Python Version Resolution**
> Before presenting these prerequisites to the user, you **must** dynamically resolve the minimum required Python version to ensure compliance with current support cycles:
> 1. Access the [Supported Client Library Versions](https://developers.google.com/google-ads/api/docs/client-libs.md.txt#supported_api_versions) documentation page.
> 2. Scan the page/table for the **Python** client library to identify the minimum supported Python runtime version (e.g., Python 3.8+).
> 3. Replace the `MINIMUM_PYTHON_VERSION` placeholder below with the dynamically retrieved version in your final output to the user.

*   **Python:** Version `MINIMUM_PYTHON_VERSION` or higher.
*   **Package Manager:** `pip`

---

## Step 1: Environment & Installation

> [!TIP]
> **Best Practice:** Always install the client library within a virtual environment (`venv`) to prevent dependency conflicts with other system packages. This is especially important for automated agents operating in shared workspaces.

### 1. Create and Activate a Virtual Environment
Run the following commands in your project root:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install the Library
Install the official Google Ads Python Client Library:
```bash
python -m pip install google-ads
```

---

## Step 2: Configuration (`google-ads.yaml` & Alternate Methods)

Create a file named `google-ads.yaml`.

The Python client library supports multiple methods for initializing the `GoogleAdsClient`:
1. **YAML File (`load_from_storage`):** Resolves in order: (1) Explicit path passed to `load_from_storage('/path/to/google-ads.yaml')`, (2) `GOOGLE_ADS_CONFIGURATION_FILE_PATH` environment variable, or (3) `$HOME/google-ads.yaml` by default.
2. **Environment Variables (`load_from_env`):** Reads uppercase `GOOGLE_ADS_` prefixed variables (e.g., `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_CLIENT_ID`). *(Note: If `GOOGLE_ADS_CONFIGURATION_FILE_PATH` is set, `load_from_env` will load from that YAML file instead).*
3. **Dictionary (`load_from_dict`):** Accepts a Python dictionary of credentials directly.
4. **YAML String (`load_from_string`):** Accepts a raw YAML string in memory.

> [!IMPORTANT]
> **Hermetic Workspace Rule:** For self-contained project environments, it is best practice to keep `google-ads.yaml` in your project root directory and load it explicitly.

Populate the file with your credentials:
```yaml
# google-ads.yaml
developer_token: INSERT_DEVELOPER_TOKEN_HERE
client_id: INSERT_OAUTH2_CLIENT_ID_HERE
client_secret: INSERT_OAUTH2_CLIENT_SECRET_HERE
refresh_token: INSERT_OAUTH2_REFRESH_TOKEN_HERE
# Optional: Un-comment if you are accessing a client account through a manager account
# login_customer_id: INSERT_LOGIN_CUSTOMER_ID_HERE
use_proto_plus: true
```

---

## Step 3: Write the Quickstart Script

Create a file named `get_campaigns.py`. 

> [!IMPORTANT]
> **Rule 1: Normalize Customer IDs**
> Before passing the Client Customer ID to the API, you **must** normalize it by stripping all hyphens (e.g., converting `123-456-7890` to `1234567890`). The script below handles this automatically in the entry point.
>
> **Rule 2: Configuration Pathing**
> The script below is configured to look for `google-ads.yaml` in the **current working directory** first, falling back to environment variables or default search paths.

```python
import argparse
import os
import sys
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

def main(client, customer_id):
    # Initialize the Google Ads Service
    googleads_service = client.get_service("GoogleAdsService")
    
    # Define the GAQL query
    query = "SELECT campaign.id, campaign.name, campaign.status FROM campaign ORDER BY campaign.id"
    
    print("Querying Google Ads API...")
    try:
        # Execute the search stream request
        stream = googleads_service.search_stream(customer_id=customer_id, query=query)
        for response in stream:
            for row in response.results:
                print(f"Campaign found: ID = {row.campaign.id}, Name = '{row.campaign.name}', Status = {row.campaign.status.name}")
                
    except GoogleAdsException as ex:
        print(f"Request ID '{ex.request_id}' failed with status '{ex.error.code().name}':")
        for error in ex.failure.errors:
            print(f"\tError: {error.message}")
        sys.exit(1)

if __name__ == '__main__':
    # Determine configuration file path (prefer local workspace config)
    local_config = os.path.join(os.getcwd(), "google-ads.yaml")
    
    if os.path.exists(local_config):
        # Load explicitly from local workspace
        googleads_client = GoogleAdsClient.load_from_storage(local_config)
    elif "GOOGLE_ADS_DEVELOPER_TOKEN" in os.environ:
        # Load from environment variables
        googleads_client = GoogleAdsClient.load_from_env()
    else:
        # Fallback to default search paths (GOOGLE_ADS_CONFIGURATION_FILE_PATH or $HOME/google-ads.yaml)
        googleads_client = GoogleAdsClient.load_from_storage()

    parser = argparse.ArgumentParser(description="Lists campaigns for a specified customer ID.")
    parser.add_argument("-c", "--customer_id", required=True, help="10-digit customer ID.")
    
    args = parser.parse_args()
    
    # Normalize customer ID by removing hyphens before passing to main
    normalized_customer_id = args.customer_id.replace("-", "")
    
    main(googleads_client, normalized_customer_id)
```

---

## Step 4: Run the Script

Execute the script from your terminal, passing the customer ID as an argument.

> [!NOTE]
> Ensure your virtual environment is active (`source .venv/bin/activate`) before running.

```bash
python get_campaigns.py -c XXXXXXXXXX
```
*(Replace `XXXXXXXXXX` with your 10-digit customer ID, with or without hyphens).*

---

## Step 5: Verification & Troubleshooting

### Expected Success Output
Upon successful execution, you should see output similar to the following:
```text
Querying Google Ads API...
Campaign found: ID = 123456789, Name = 'Search - Brand - US', Status = ENABLED
Campaign found: ID = 987654321, Name = 'Display - Remarketing', Status = PAUSED
```

### Common Errors

| Error Symptom / Code | Root Cause | Solution |
| :--- | :--- | :--- |
| `FileNotFoundException` / `File not found` | The library cannot find `google-ads.yaml`. | Ensure the file is named exactly `google-ads.yaml` and is placed in the directory from which you are running the script, or in your `$HOME` directory. |
| `DEVELOPER_TOKEN_NOT_APPROVED` | You are using an unapproved ("Pending") developer token against a production account (production calls require Explorer, Basic, or Standard Access). | Use a **Test Account** (which allows pending tokens) or wait for token approval. |
| `NOT_ADS_USER` | The OAuth2 user credentials used to generate the refresh token do not have access to the specified `-c/--customer_id`. | Re-authenticate the OAuth2 flow using a Google account that has access to the target Ads account. |
| `ModuleNotFoundError: No module named 'google'` | Python cannot find the installed library. | You likely installed the library in a virtual environment but are running the script using the global python interpreter. Ensure you run `source .venv/bin/activate` first. |
