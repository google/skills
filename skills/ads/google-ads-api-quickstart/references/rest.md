# Google Ads API REST Setup Reference

This guide outlines how to authenticate, configure, and execute direct HTTP REST requests to retrieve campaigns from the Google Ads API without using a client library.

---

## Step 1: Obtain a Short-Lived Access Token

> [!IMPORTANT]
> **Mandatory Agent Directive (OAuth Authorization Routes):**
> When guiding a user through the REST quickstart, your response **MUST** explicitly explain both OAuth2 authorization routes:
> 1. **Option A: Service Account Flow (Recommended):** Explain creating a service account, granting direct Ads account access, generating a JWT claim set, and exchanging it for an access token.
> 2. **Option B: User Authentication Flow (Alternative):** Explain exchanging a `refresh_token`, `client_id`, and `client_secret` for an access token via cURL.
> 
> Do not omit either flow in your final output.

Since client libraries automatically refresh OAuth2 tokens, you must manually request an access token when using the direct REST interface.

### Option A: Service Account Flow (Recommended)
For server-to-server REST applications, using a Service Account is the recommended best practice:
1. **Set up your Cloud Project:** Create a Service Account in the Google Cloud Console and download the private key in JSON format. Record the service account email and key.
2. **Grant Account Access:** Grant the service account email direct access to your Google Ads account in the Google Ads UI (Targeting account access level: Explorer, Basic, or Standard).
3. **Generate JWT Claim Set:** Follow the [OAuth 2.0 Server to Server Applications](https://developers.google.com/identity/protocols/oauth2/service-account#authorizingrequests) guide (selecting the HTTP/REST tab) to create and sign a JWT claim set.
   * **Scope:** Use `https://www.googleapis.com/auth/adwords`.
   * **Impersonation (`sub`):** You can skip the `sub` parameter when constructing the JWT claim set, as the service account has direct access to the Google Ads account.
4. **Exchange JWT for Access Token:** Exchange the signed JWT for a short-lived `access_token` via the Google OAuth2 token endpoint (`https://oauth2.googleapis.com/token`).

### Option B: User Authentication Flow (Alternative)
If you are authenticating as an individual user, exchange your `refresh_token`, `client_id`, and `client_secret` for a short-lived `access_token` (typically valid for 1 hour):

```bash
curl \
  --data "grant_type=refresh_token" \
  --data "client_id=INSERT_OAUTH2_CLIENT_ID_HERE" \
  --data "client_secret=INSERT_OAUTH2_CLIENT_SECRET_HERE" \
  --data "refresh_token=INSERT_OAUTH2_REFRESH_TOKEN_HERE" \
  https://www.googleapis.com/oauth2/v3/token
```

### Expected JSON Response:
```json
{
  "access_token": "ya29.a0AfH6S...",
  "expires_in": 3599,
  "scope": "https://www.googleapis.com/auth/adwords",
  "token_type": "Bearer"
}
```

Copy the value of `"access_token"` to authenticate your subsequent API requests.

---

## Step 2: Make the HTTP POST Request to Retrieve Campaigns

The Google Ads API REST interface provides a unified mechanism for retrieving resources using the **Google Ads Query Language (GAQL)**. To fetch campaigns, send a `POST` request to the `searchStream` endpoint.

*   **Endpoint URL:** `https://googleads.googleapis.com/vXX/customers/{customer_id}/googleAds:searchStream`
*   **Method:** `POST`
*   **Headers:**
    *   `Content-Type: application/json`
    *   `developer-token: <INSERT_DEVELOPER_TOKEN_HERE>`
    *   `Authorization: Bearer <INSERT_OAUTH2_ACCESS_TOKEN_HERE>`
    *   `login-customer-id: <INSERT_LOGIN_CUSTOMER_ID_HERE>` *(Required only if authenticating through a manager account)*

> [!TIP]
> **Capture Request ID:** When using cURL, add the `--include` (or `-i`) flag to view response HTTP headers. The `request-id` header uniquely identifies your API request and is highly valuable for debugging or contacting Google developer support.

### Execute via cURL:
```bash
# Set your target Client Customer ID (10-digit number only, no hyphens)
CUSTOMER_ID="1234567890"

curl --include --request POST "https://googleads.googleapis.com/vXX/customers/${CUSTOMER_ID}/googleAds:searchStream" \
  --header "Content-Type: application/json" \
  --header "developer-token: INSERT_DEVELOPER_TOKEN_HERE" \
  --header "Authorization: Bearer INSERT_OAUTH2_ACCESS_TOKEN_HERE" \
  --header "login-customer-id: INSERT_LOGIN_CUSTOMER_ID_HERE" \
  --data '{
    "query": "SELECT campaign.id, campaign.name, campaign.status FROM campaign ORDER BY campaign.id"
  }'
```

---

## Step 3: Parse the JSON Response

Unlike typical REST endpoints that return a single JSON object, the `searchStream` method streams chunks of results wrapped in a JSON array. Each chunk contains a list of campaign resources:

```json
[
  {
    "results": [
      {
        "campaign": {
          "resourceName": "customers/1234567890/campaigns/987654321",
          "id": "987654321",
          "name": "Interstate Search Promo",
          "status": "ENABLED"
        }
      },
      {
        "campaign": {
          "resourceName": "customers/1234567890/campaigns/555444333",
          "id": "555444333",
          "name": "Local Brand Awareness",
          "status": "PAUSED"
        }
      }
    ],
    "fieldMask": "campaign.id,campaign.name,campaign.status"
  }
]
```
