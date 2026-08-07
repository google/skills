---
name: data-manager-api-setup
description: >-
  Guides developers through client library installation and authentication setup
  steps for the Data Manager API. Use this skill when a user is getting started
  with the Data Manager API and needs to setup their local environment, install
  the client library, or setup access to the API. Don't use for implementing
  audience or event ingestion logic (use the data-manager-api-audience-ingestion
  or data-manager-api-event-ingestion skills instead).
metadata:
  version: 1.0
  category: GoogleAds
---
# Data Manager API Setup

## Setup Authentication

Refer to [Set up API access](https://developers.google.com/data-manager/api/devguides/quickstart/set-up-access.md.txt)
for more details.

1.  **Enable API (Prerequisite)**: Check that the user has enabled the Data
    Manager API in their Google Cloud project.
2.  **Generate ADC**: Authenticate the local workspace using Application
    Default Credentials (ADC) via `gcloud auth application-default login`.
    *   **Required Scopes**: Include scopes
        `https://www.googleapis.com/auth/datamanager` and
        `https://www.googleapis.com/auth/cloud-platform`.
    *   **Multi-API Scopes**: If using the same credentials for other APIs,
        append their scopes (e.g.,
        `https://www.googleapis.com/auth/adwords`).
    *   **Service Accounts**: Ensure the Service Account has the
        `Service Usage Consumer` IAM role, and the user executing `gcloud`
        has the Token Creator role
        (`roles/iam.serviceAccountTokenCreator`) on that Service Account
        for impersonation.

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
*   [Java Setup Reference](references/java.md) (packages: `com.google.api-ads:data-manager` and `data-manager-util`)
*   [Node Setup Reference](references/node.md) (packages: `@google-ads/datamanager` and `@google-ads/data-manager-util`)
*   [PHP Setup Reference](references/php.md) (packages: `googleads/data-manager` and `googleads/data-manager-util`)
*   [.NET Setup Reference](references/dotnet.md) (packages: `Google.Ads.DataManager.V1` and `Google.Ads.DataManager.Util.csproj`)
