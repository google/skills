---
name: google-analytics-data-api-basics
metadata:
  category: GoogleAnalytics
description: >-
  Manages Google Analytics reporting data, enables the Analytics Data API via the Cloud CLI, and creates reports using the Google Analytics Data API (v1beta). Use when you need to interact with Google Analytics properties, run customized analytics reports, query metrics (like activeUsers, screenPageViews) and dimensions (like city, date), check metrics and dimensions compatibility, or verify API enablement. Don't use for Google Analytics Admin API operations (e.g., creating properties, managing users) or for front-end tracking installation.
---

# Getting Started with Google Analytics Data API

The Google Analytics Data API v1beta provides programmatic access to Google
Analytics report data. It allows you to build customized dashboards,
automate reporting workflows, and integrate Google Analytics data into your enterprise
applications.

## Enabling the API via Cloud CLI

Before making API calls, ensure the Google Analytics Data API is enabled in your
Google Cloud project.

If `gcloud` is not found, prompt the user to install the Google Cloud CLI before
running these commands.

1.  **Enable the API:** Use the Cloud CLI (`gcloud`) to enable
    `analyticsdata.googleapis.com`.

    ```bash
    gcloud services enable analyticsdata.googleapis.com --quiet
    ```

    *Why: Enabling the API ensures your Cloud project has the necessary quota
    and permissions allocated for running Google Analytics reports.*

2.  **Verify API Enablement:**

    ```bash
    gcloud services list --enabled --filter="analyticsdata.googleapis.com"
    ```

## Authentication

To authenticate your API requests, you must generate Application Default
Credentials (ADC) and give your account the necessary scopes. Run the following
command in your terminal:

```bash
gcloud auth application-default login --scopes="https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/analytics.readonly"
```

*Why: This configures ADC in your local environment with the required Cloud
Platform and Google Analytics read-only scopes, allowing the client library to
automatically authenticate your requests.*

## Creating a Data API Report (v1beta)

To create a report, use the official Google Analytics Data client library.
Always prefer the `v1beta` version of the API for stability and access to
current Google Analytics reporting capabilities.

> [!IMPORTANT] **Mandatory Agent Directive:** When the user selects or requires
> a specific programming language, read the corresponding client library setup
> reference guide in `references/` listed below.

### Supported Client Libraries

#### Python

If you need to install or set up the Google Analytics Data API client library
for Python, read the setup guide:

*   [Python Installation Reference](references/python.md) *(Package:
    `google-analytics-data`)*

#### Java

If you need to install or set up the Google Analytics Data API client library
for Java, read the setup guide:

*   [Java Installation Reference](references/java.md) *(Artifact:
    `com.google.cloud:google-cloud-analytics-data`)*

#### PHP

If you need to install or set up the Google Analytics Data API client library
for PHP, read the setup guide:

*   [PHP Installation Reference](references/php.md) *(Package:
    `google/analytics-data`)*

#### Node.js

If you need to install or set up the Google Analytics Data API client library
for Node.js, read the setup guide:

*   [Node.js Installation Reference](references/nodejs.md) *(Package:
    `@google-analytics/data`)*

#### Go

If you need to install or set up the Google Analytics Data API client library
for Go, read the setup guide:

*   [Go Installation Reference](references/go.md) *(Package:
    `cloud.google.com/go/analytics/data/apiv1beta`)*

#### .NET

If you need to install or set up the Google Analytics Data API client library
for .NET / C#, read the setup guide:

*   [.NET Installation Reference](references/dotnet.md) *(Package:
    `Google.Analytics.Data.V1Beta`)*

#### Ruby

If you need to install or set up the Google Analytics Data API client library
for Ruby, read the setup guide:

*   [Ruby Installation Reference](references/ruby.md) *(Gem:
    `google-analytics-data-v1beta`)*

> [!NOTE] **Additional Resources**: For further examples of calling the Data API
> with Java, PHP, Node.js, .NET, Python and REST, as well as hints on
> authentication with a service account, refer to the official
> [Data API Quickstart](https://developers.google.com/analytics/devguides/reporting/data/v1/quickstart).

### Python Quick Start

1.  **Install the Client Library:**

    ```bash
    pip install google-analytics-data
    ```

    If `pip` is not available, prompt the user to install `pip` before
    installing the client library.

2.  **Run a Report Request:** Below is a complete example demonstrating how to
    query a Google Analytics property for active users and sessions grouped by city and date.
    Replace `YOUR-PROPERTY-ID` with your actual Google Analytics property ID (e.g.,
    `1234567`).

    ```python
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest

    def sample_run_report(property_id: str):
        # Initialize the client.
        # Assumes Application Default Credentials (ADC) are configured in your environment.
        client = BetaAnalyticsDataClient()

        request = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=[
                Dimension(name="city"),
                Dimension(name="date")
            ],
            metrics=[
                Metric(name="activeUsers"),
                Metric(name="sessions")
            ],
            date_ranges=[
                DateRange(start_date="2026-05-01", end_date="today")
            ],
        )

        response = client.run_report(request)

        print(f"Report result for property {property_id}:")
        for row in response.rows:
            print(
                f"City: {row.dimension_values[0].value}, "
                f"Date: {row.dimension_values[1].value}, "
                f"Active Users: {row.metric_values[0].value}, "
                f"Sessions: {row.metric_values[1].value}"
            )

    if __name__ == "__main__":
        sample_run_report("YOUR-PROPERTY-ID")
    ```

    *Why: Using `BetaAnalyticsDataClient` and `RunReportRequest` ensures
    compatibility with the v1beta endpoint and strongly typed request
    validation.*

## Metrics and Dimensions Schema

When constructing your `RunReportRequest`, you must use valid API names for
dimensions and metrics. Refer to the official
[Data API Schema documentation](https://developers.google.com/analytics/devguides/reporting/data/v1/api-schema)
for the complete, authoritative list of available fields.

### Commonly Used Dimensions

Dimensions represent categorical attributes of your data.

*   `city`: The town or city of the user.
*   `country`: The country of the user.
*   `date`: The date of the event, formatted as YYYYMMDD.
*   `deviceCategory`: The category of mobile device (e.g., desktop, mobile,
    tablet).
*   `eventName`: The name of the triggered event.
*   `pageTitle`: The title of the web page.

### Commonly Used Metrics

Metrics represent quantitative measurements.

*   `activeUsers`: The number of active users.
*   `eventCount`: The total count of events.
*   `sessions`: The total number of sessions.
*   `screenPageViews`: The number of app screens or web pages viewed.
*   `totalRevenue`: The total revenue from purchases, subscriptions, and
    advertising.

### Metrics and Dimensions Compatibility Check

Some dimensions and metrics cannot be queried together in the same report
request. If you encounter an `INVALID_ARGUMENT` error regarding incompatible
fields, verify your field combinations For programmatic access to the Data API
schema, use `getMetadata()`. To programmatically check the compatibility of
specific dimension and metric combinations before running a report, use the
`checkCompatibility()` method.

```python
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import CheckCompatibilityRequest, Compatibility, Dimension, Metric

def sample_check_compatibility(property_id: str):
    client = BetaAnalyticsDataClient()

    # Define the dimensions and metrics you want to query together.
    # For example, checking if 'itemName' (an e-commerce dimension)
    # is compatible with 'activeUsers' and 'totalRevenue'.
    request = CheckCompatibilityRequest(
        property=f"properties/{property_id}",
        dimensions=[
            Dimension(name="itemName"),
            Dimension(name="date")
        ],
        metrics=[
            Metric(name="activeUsers"),
            Metric(name="totalRevenue")
        ],
    )
    response = client.check_compatibility(request)

    print(f"Compatibility check for property {property_id}:")
    for dim in response.dimension_compatibilities:
        is_compatible = dim.compatibility == Compatibility.COMPATIBLE
        print(f"Dimension '{dim.dimension_metadata.api_name}' is compatible: {is_compatible}")

    for metric in response.metric_compatibilities:
        is_compatible = metric.compatibility == Compatibility.COMPATIBLE
        print(f"Metric '{metric.metric_metadata.api_name}' is compatible: {is_compatible}")

if __name__ == "__main__":
    sample_check_compatibility("YOUR-PROPERTY-ID")
```
