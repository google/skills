---
name: data-manager-api-setup
description: >-
  Guides developers through client library installation and authentication setup
  steps for the Data Manager API. Use this skill when a user is getting started
  with the Data Manager API and needs to setup their local environment, install
  the client library, or setup access to the API. Don't use for implementing
  audience or event ingestion logic (use the data-manager-api-audience-ingestion
  or data-manager-api-event-ingestion skills instead), or for debugging
  UNAUTHENTICATED, PERMISSION_DENIED, or other errors from requests after setup
  (use the data-manager-api-troubleshooting skill).
metadata:
  version: "1.1.1"
  category: GoogleAds
---
# Data Manager API Setup

## Setup Authentication

Refer to [Set up API access](https://developers.google.com/data-manager/api/devguides/quickstart/set-up-access.md.txt)
for more details.

### 1. Enable the API

**Prerequisites**: A Google Cloud project, the Google Cloud CLI (`gcloud`), and
a Google Account with a project role that can enable APIs, such as **Owner**,
**Editor**, or **Service Usage Admin**. Always tell the user about the required
role. If `gcloud` isn't installed, prompt the user to install it first.

```shell
gcloud services enable datamanager.googleapis.com --project={project_id}
gcloud services list --enabled --project={project_id} --filter="datamanager.googleapis.com"
```

### 2. Generate Application Default Credentials (ADC)

Choose the method that matches the user's scenario:

*   **User account** (API calls are made as the user's own Google Account): The
    Data Manager API scopes are sensitive, so the user must first configure
    their project's Google Auth Platform:
    1.  **Data Access** page: Add the Data Manager API scopes.
    2.  **Audience** page: Set **Publishing status** to **Testing**. Use the
        **Internal** user type for a Google Workspace organization, or
        **External** with the user's account added as a **Test user**.
    3.  Create (or reuse) a **Desktop app** OAuth client and download its JSON
        configuration file.
    4.  The user runs the following command, which opens a browser login:

        ```shell
        gcloud auth application-default login \
          --scopes="https://www.googleapis.com/auth/datamanager,https://www.googleapis.com/auth/cloud-platform" \
          --client-id-file="{client_id_file_path}"
        ```

    **Unverified app screen**: This warning appears because the Data Manager API
    scopes are sensitive. During **Testing**, External test users still see it
    and can continue past it. Before other users can sign in, the app must
    complete
    [OAuth app verification](https://developers.google.com/data-manager/api/devguides/concepts/oauth-verification.md.txt).
    Service accounts don't need verification.
*   **Service account** (API calls are made as an app identity instead of a
    person): For local development, use service account impersonation rather
    than a service account key, since keys are a security risk if not managed
    carefully.
    *   Grant the Service Account the `Service Usage Consumer` IAM role
        (`roles/serviceusage.serviceUsageConsumer`) on the project.
    *   Grant the user executing `gcloud` the Token Creator role
        (`roles/iam.serviceAccountTokenCreator`) on that Service Account.
    *   Run:

        ```shell
        gcloud auth application-default login \
          --impersonate-service-account={service_account_email} \
          --scopes="https://www.googleapis.com/auth/datamanager,https://www.googleapis.com/auth/cloud-platform"
        ```
*   **Data partner creating partner links** in advertiser accounts: Read
    [Partner Links](references/partner-links.md).

**Multiple APIs**: To use the same credentials for other APIs, append their
scopes to the `--scopes` list in the commands above (e.g.,
`https://www.googleapis.com/auth/adwords` for the Google Ads API or
`https://www.googleapis.com/auth/display-video` for the Display & Video 360
API).

**Verify**: `gcloud auth application-default print-access-token` prints an
access token when credentials are set up correctly.

**Troubleshooting `PERMISSION_DENIED` with a valid token**: Add the user or
service account to the destination account (for example, the Google Ads account
or its manager account). For service accounts, also confirm the
`Service Usage Consumer` role on the Cloud project.

**Production**: For production authentication (workloads in or outside Google
Cloud, apps that act on behalf of other users, or partner links), see
[Deploy to production](https://developers.google.com/data-manager/api/devguides/concepts/deploy.md.txt).

## Install Client & Utility Libraries

Refer to [Install a client library](https://developers.google.com/data-manager/api/devguides/quickstart/install-library.md.txt)
for more details.

The companion utility libraries provide pre-built helper classes
and functions to correctly format, hash, and encrypt user identifiers (such as
emails, phone numbers, and physical addresses) prior to API ingestion. Use of
these libraries is highly recommended to ensure that user identifier formatting
matches the API's specifications.

Select the language-specific installation guide below:

*   [Python Setup Reference](references/python.md) (packages: `google-ads-datamanager` and `google-ads-datamanager-util`)
*   [Java Setup Reference](references/java.md) (packages: `com.google.api-ads:data-manager` and `com.google.api-ads:data-manager-util`)
*   [Node Setup Reference](references/node.md) (packages: `@google-ads/datamanager` and `@google-ads/datamanager-util`)
*   [PHP Setup Reference](references/php.md) (packages: `googleads/data-manager` and `googleads/data-manager-util`)
*   [.NET Setup Reference](references/dotnet.md) (packages: `Google.Ads.DataManager.V1` and `Google.Ads.DataManager.Util`)
