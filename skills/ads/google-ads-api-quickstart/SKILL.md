---
name: google-ads-api-quickstart
description: |
  Guides developers through Google Ads API quickstart: credential setup, choosing from 6 client libraries/REST, configuring environments, and running a "retrieve campaigns" script. Troubleshoots common setup errors: USER_PERMISSION_DENIED, login_customer_id issues, and DEVELOPER_TOKEN_NOT_APPROVED.

  Use this skill when:
  - The user asks how to get started with the Google Ads API.
  - The user needs to set up Google Ads credentials or developer tokens.
  - The user wants to write a quickstart/example script for Google Ads.
  - The user encounters errors like USER_PERMISSION_DENIED or DEVELOPER_TOKEN_NOT_APPROVED.
compatibility: "Outbound HTTPS connectivity required to access the Google Ads API and documentation. Note: If network access is restricted, the agent will fall back to using the last-known stable versions cached within the skill resources."
metadata:
  author: google-ads-api-team
  version: "1.0"
  category: GoogleAds
---
# Google Ads API Quickstart
This skill guides you from absolute zero to running your first successful request to retrieve campaigns.

## Supported Tracks
You can choose to use this skill with:

1. **Official Client Libraries:** Python, Java, .NET, PHP, Ruby, or Perl.
2. **Direct REST:** Raw HTTP REST requests.

---

## Crucial Requirement: Dynamic Version Resolution & Runtime Resolution

> [!IMPORTANT]
> To ensure the integration is secure, stable, and up-to-date, you must resolve all API and runtime versions dynamically. Do not rely on hardcoded defaults.

### Strict Constraints:

*   **DO NOT Hardcode:** Never use hardcoded Google Ads API versions (e.g., `v24`) or language runtime versions (e.g., `Python 3.8+`, `Java 11+`) in generated code or environment setup instructions, unless the user explicitly requests a specific version.
*   **MANDATORY Dynamic Resolution:** You must dynamically resolve the latest stable versions *at the start of execution* before generating any code or configuration, using the procedures detailed below.

### A. Dynamic API Version Resolution
To ensure the integration is secure, stable, and up-to-date, you **MUST** resolve the absolute newest stable major version of the Google Ads API dynamically.

#### Execution Steps:

1.  **Pre-Flight Version Resolution:** Use your web search or URL-reading tools to inspect the latest entry in the [Google Ads API Release Notes](https://developers.google.com/google-ads/api/docs/release-notes.md.txt) or the highest versioned directory in the [Googleapis Github Repository](https://github.com/googleapis/googleapis/tree/master/google/ads/googleads) to resolve `RESOLVED_API_VERSION` (e.g., `v24`). If using Java, you **MUST** also resolve the latest stable release version of the Google Ads Java Client Library (referred to as `RESOLVED_LIBRARY_VERSION`, e.g., `34.0.0`).

2.  **Mandatory Response Anchor:** You **MUST** output the following confirmation block as the **very first line** of your response to the user. Do not output any greeting, pleasantries, or introductory text before this block.
    
    ```text
    [SYSTEM: Using Google Ads API version: RESOLVED_API_VERSION (Resolved from release notes)]
    ```

3.  **Strict Placeholder Mapping Table:** You **MUST** perform on-the-fly search-and-replace on all code templates and reference files using the mapping table below. Do not leave raw placeholders in the final output.

    | Target Language / Tech | Placeholder in Template | Replacement Pattern | Example (Assuming API `v24`) |
    | :--- | :--- | :--- | :--- |
    | **Java** (Maven/Gradle) | `LATEST_LIBRARY_VERSION` | Search & substitute the latest Maven release version of the library. | `34.0.0` |
    | **Java** (Imports) | `vXX` | Replace with **lower-case** API version. | `com.google.ads.googleads.v24` |
    | **.NET / C#** (Namespaces) | `VXX` | Replace with **title-case** API version. | `Google.Ads.GoogleAds.V24` |
    | **PHP** (Namespaces) | `VXX` | Replace with **title-case** API version. | `Google\Ads\GoogleAds\V24` |
    | **REST** (Endpoint URL) | `vXX` | Replace with **lower-case** API version. | `https://googleads.googleapis.com/v24/...` |

> [!TIP]
> **Offline Fallback:** If the URLs are unreachable or the scrape fails, do not halt execution. Fall back to these last-known stable versions:
> *   **Google Ads API Major Version (`RESOLVED_API_VERSION`):** `v24`
> *   **Java Client Library Version (`RESOLVED_LIBRARY_VERSION`):** `34.0.0`

### B. Dynamic Language Runtime Version Resolution
To prevent the generated setup guides from becoming obsolete due to language deprecation cycles, you **MUST** resolve language requirements dynamically.

#### Execution Steps:

1.  **Fetch Live Requirements:** Use your URL-reading tools to inspect the official [Google Ads Client Libraries - Supported Versions](https://developers.google.com/google-ads/api/docs/client-libs.md.txt#supported_api_versions) page.

2.  **Extract Minimums:** Identify the minimum supported runtime version for the user's chosen language by scanning the Overview page or compatibility tables (e.g., looking for explicit requirements like Python 3.8+, Java 11+, .NET 6.0+, PHP 8.1+, Ruby 3.0+).

3.  **Apply On-The-Fly:** Substitute all runtime placeholders (e.g., `<PYTHON_MIN_VERSION>`) in your generated setup guides with these resolved versions.

> [!TIP]
> **Offline Fallback:** If the URL is unreachable or the scrape fails, do not halt execution. Fall back to these last-known safe minimum versions:
> *   **Python:** `3.9+`
> *   **Java:** `11+`
> *   **.NET:** `6.0+`
> *   **PHP:** `8.1+`
> *   **Ruby:** `3.0+`
> *   **Perl:** `5.28.1+`

---

## Step 1: Obtain Google Ads API Credentials

Before installing libraries or making API calls, you must obtain the five required authentication parameters.

### 1. Developer Token

*   **Purpose:** Identifies your developer access and API quota.
*   **How to Obtain:**
    1. Navigate directly to the **API Center** in your Google Ads Manager Account: https://ads.google.com/aw/apicenter *(Note: You must sign in with a Manager account, not a standard serving account)*.
    2. Copy your Developer Token.

> [!WARNING]
> **Pending Token Restriction:** If your Developer Token status is "Pending" (unapproved), you **MUST ONLY** target **Google Ads Test Accounts**. Attempting to call a production account with a pending token will fail with the error: `DEVELOPER_TOKEN_NOT_APPROVED`.

### 2. OAuth2 Client ID & Client Secret

*   **Purpose:** Identifies your application to Google's OAuth 2.0 server and allows you to request user authorization.
*   **How to Obtain:**
    1. Open the [Google Cloud Console](https://console.cloud.google.com/).
    2. Create a new project (or select an existing one).
    3. Search for the **Google Ads API** in the API Library and click **Enable**.
    4. Configure the **OAuth Consent Screen**:
       *   Select **External** user type.
       *   Set the Publishing Status to **Testing**.
       *   > [!IMPORTANT]
       *   > **Add Test Users:** You **MUST** add the email address of the Google account you use to log into Google Ads as a **Test User** in this step. Otherwise, you will be blocked during authorization.
    5. Create the OAuth Client:
       *   Go to **APIs & Services 🡒 Credentials**.
       *   Click **Create Credentials 🡒 OAuth client ID**.
       *   Select **Desktop App** as the Application Type.
       *   Name the client and click **Create**.
    6. **Download Secrets:** Click the download icon (JSON) next to your newly created Client ID. Save this file locally as `client_secrets.json`.

### 3. OAuth2 Refresh Token

*   **Purpose:** Allows your application to obtain new access tokens automatically without requiring manual user login every hour.
*   **How to Obtain:**
    You must run the Google Cloud (`gcloud`) CLI to generate your refresh token.

    #### 1. Install and Verify gcloud CLI:
    Ensure the [gcloud CLI](https://cloud.google.com/sdk/docs/install) is installed and available in your terminal.

    #### 2. Execute the Login Flow:
    Run the following command in your terminal, passing the path to the `client_secrets.json` file downloaded in the previous step:
    
    ```bash
    gcloud auth application-default login \
      --scopes=https://www.googleapis.com/auth/adwords,https://www.googleapis.com/auth/cloud-platform \
      --client-id-file=client_secrets.json
    ```

    #### 3. Authorize in Browser:
    1. The command will open a Google Account login window in your browser.
    2. Sign in using the **Test User** email registered in your OAuth Consent Screen setup.
    3. If your app is unverified, click **Advanced** and continue to the project. Click **Continue** to grant permissions.

    #### 4. Retrieve Your Refresh Token:
    Once successful, `gcloud` will output a message indicating where the credentials were saved (typically `~/.config/gcloud/application_default_credentials.json`). Open that file to copy your `refresh_token`.

### 4. Client Customer ID

*   **Purpose:** The 10-digit ID of the specific Google Ads account you want to query or make changes to.
*   **Format:** Must be 10 digits with **no hyphens** (e.g., `1234567890`, NOT `123-456-7890`).
*   **How to Find It:** Log in to the Google Ads UI; the ID is displayed in the top-right corner next to your user icon.

> [!IMPORTANT]
> **Test Account Requirement:** If your Developer Token is pending (unapproved), this **MUST** be the Customer ID of a **Test Account**. Test accounts have a red "Test account" banner in the top right of the UI.

---

### 5. Login Customer ID

*   **What it is:** The 10-digit Customer ID of the Google Ads Manager Account that owns or manages the target client account.
*   **Format:** Must be 10 digits with **no hyphens** (e.g., `9876543210`).
*   **When to Use:** This is **mandatory** if your OAuth credentials (and developer token) belong to a Manager Account, but you are querying a child/client account (Client Customer ID).

> [!CAUTION]
> **Preventing `USER_PERMISSION_DENIED`:**
> If you are accessing a client account through a Manager Account hierarchy, you **MUST** set this parameter.
> *   `login_customer_id` = The **Manager** Account ID.
> *   `client_customer_id` = The **Child/Client** Account ID.
> Leaving `login_customer_id` blank in a manager-client hierarchy is the #1 cause of permission errors.

---

## Step 2: Choose Your Integration Strategy

Developers can connect to the Google Ads API using either the official high-level client libraries or direct HTTPS REST requests.

### Path A: Official Client Libraries (Recommended)

> [!IMPORTANT]
> **Mandatory Agent Directive:** Once the user selects their language, you **MUST**:
> 1. Use the `view_file` tool to lazy-load the corresponding reference file listed below.
> 2. Apply the **Dynamic Version Resolution** (Section B) to dynamically replace all `vXX`/`VXX` placeholders and library versions *before* generating code.

#### Python
If you need to set up the Google Ads API environment for Python, do not guess the configuration.
Instead, read the detailed setup guide:

*   [Google Ads API Python Setup Reference](references/python.md)
*(Package: `google-ads`)*

#### Java
If you need to set up the Google Ads API environment for Java, do not guess the configuration.
Instead, read the detailed setup guide:

*   [Google Ads API Java Setup Reference](references/java.md)
*(Artifact: `com.google.api-ads:google-ads`)*

#### .NET / C#
If you need to set up the Google Ads API environment for .NET/C#, do not guess the configuration.
Instead, read the detailed setup guide:

*   [Google Ads API .NET Setup Reference](references/dotnet.md)
*(Package: `Google.Ads.GoogleAds`)*

#### PHP
If you need to set up the Google Ads API environment for PHP, do not guess the configuration.
Instead, read the detailed setup guide:

*   [Google Ads API PHP Setup Reference](references/php.md)
*(Package: `googleads/google-ads-php`)*

#### Ruby
If you need to set up the Google Ads API environment for Ruby, do not guess the configuration.
Instead, read the detailed setup guide:

*   [Google Ads API Ruby Setup Reference](references/ruby.md)
*(Gem: `google-ads-ruby`)*

#### Perl
If you need to set up the Google Ads API environment for Perl, do not guess the configuration.
Instead, read the detailed setup guide:

*   [Google Ads API Perl Setup Reference](references/perl.md)
*(Package: `Google::Ads::GoogleAds::Client`)*

### Path B: Direct HTTP REST (No Library Overhead)

Use this path if the user's environment does not support the official client libraries (e.g., lightweight serverless functions, custom language stacks, or restricted runtimes).

> [!IMPORTANT]
> **Mandatory Agent Directive:** If the user chooses the REST path, you **MUST**:
> 1. Use the `view_file` tool to lazy-load the REST reference file below.
> 2. Apply **Dynamic Version Resolution** (Section B) to replace all `vXX` placeholders in the endpoint URLs (e.g., resolving `vXX` to `v24` in `https://googleads.googleapis.com/v24/...`).

#### REST (HTTP)
If you need to set up the Google Ads API environment for REST (HTTP), do not guess the configuration.
Instead, read the detailed setup guide:

*   [Google Ads API REST Setup Reference](references/rest.md)
*(Protocol: Raw HTTP POST JSON)*

---

## Cross-Referencing: AI-Assistant & MCP Connection

> [!TIP]
> **AI Assistant / MCP Integration Handoff:**
> If the goal is to connect an **AI Assistant** (such as Gemini, Cursor, or Claude Code) to query Google Ads via natural language:
> 1. **DO NOT** write custom scripts or client library code.
> 2. **STOP** executing this skill.
> 3. **Transition Immediately** to the **`google-ads-api-mcp-setup`** skill to install and configure the official Google Ads Model Context Protocol (MCP) Server.

---

## Step 4: Troubleshooting Common Errors

> [!IMPORTANT]
> **Static Diagnostics Constraint:** When troubleshooting, you **MUST NOT** execute bash commands, run local test scripts, or attempt to reproduce the error in the workspace. Rely entirely on static code analysis, configuration review, and the diagnostic guides below to prevent endless, failing execution loops.

### 1. Error: `USER_PERMISSION_DENIED`

*   **Symptom:** You receive a `USER_PERMISSION_DENIED` error when executing API requests (e.g., retrieving campaigns).
*   **Likely Cause:** The authenticating OAuth2 user has access to the target client account *indirectly* through a **Manager Account**, but the request header is missing the Manager Account's ID.

#### Required Agent Response Checklist:
When helping a user with this error, your response **MUST** include:

1.  [ ] **Explain the Hierarchy:** Explain that the authenticating user likely belongs to a Manager Account that sits above the target client account.
2.  [ ] **Provide the Fix:** Instruct the user to add their 10-digit Manager Account ID as the `login_customer_id` in their configuration file.
3.  [ ] **Explain the Routing Logic:** Explain that `login_customer_id` tells the API to route the OAuth credentials through the manager account to validate access to the child account.
4.  [ ] **Provide the Configuration Template:** Show the exact YAML configuration block below.

> [!CAUTION]
> **Security Guardrail:** Under no circumstances should you suggest exposing raw passwords, creating new unapproved developer tokens, or widening OAuth scopes beyond the standard `adwords` scope to bypass this error.

#### Configuration Fix Example (`google-ads.yaml`):

```yaml
developer_token: INSERT_DEVELOPER_TOKEN_HERE
client_id: INSERT_OAUTH2_CLIENT_ID_HERE
client_secret: INSERT_OAUTH2_CLIENT_SECRET_HERE
refresh_token: INSERT_OAUTH2_REFRESH_TOKEN_HERE

# Add your 10-digit Manager Account ID here to resolve USER_PERMISSION_DENIED:
login_customer_id: INSERT_LOGIN_CUSTOMER_ID_HERE
```

### 2. Error: `DEVELOPER_TOKEN_NOT_APPROVED`

*   **Symptom:** The script fails with a `DEVELOPER_TOKEN_NOT_APPROVED` error message.
*   **Likely Cause:** Your Developer Token is currently in the "Pending" (unapproved) state, and you are attempting to target a live production Google Ads account.

#### Required Agent Response Checklist:
When helping a user with this error, your response **MUST** include:

1.  [ ] **Explain the "Pending" Restriction:** Explain that an unapproved (Pending) developer token is fully functional but **restricted to Google Ads Test Accounts only**.
2.  [ ] **Define Production Access Levels:** You **MUST** explicitly list all three access levels by name: state that targeting live production accounts requires the token to be approved for **Explorer Access**, **Basic Access**, or **Standard Access** by the Google Ads API compliance team. Do not condense or paraphrase this to "at least Basic Access".
3.  [ ] **Provide Sandbox Setup Steps:** Guide the user on how to set up a sandbox environment:
    *   Create a **Test Manager Account** (which does not require an approved token).
    *   Create **Test Client Accounts** under that Test Manager.
    *   Use the Test Client Customer ID in their configuration.
4.  [ ] **Provide a Link to the Guide:** Point the user to the official [Google Ads API Test Accounts Guide](https://developers.google.com/google-ads/api/docs/best-practices/test-accounts.md.txt).

> [!CAUTION]
> **Security & Integrity Guardrail:** You **MUST NOT** advise the developer to modify the client library source code, bypass token validation checks, or use third-party "cracked" wrappers to bypass this error. The restriction is enforced server-side by Google, and client-side modifications will not work.

