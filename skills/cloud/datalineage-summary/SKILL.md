---
name: datalineage-summary
metadata:
  category: BigDataAndAnalytics
description: >-
  Summarizes Google Cloud Data Lineage graphs to help users debug data quality issues and understand data provenance for BQ/GCS.
  Use when summarizing upstream and downstream data flows, and presenting complex lineage data as an intuitive Markdown report.
  Don't use for generic BigQuery queries, editing lineage relationships, or downstream deprecation.
  Don't use for downstream blast-radius impact analysis (use datalineage-bigquery-asset-impact-analysis skill instead).
---

# Data Lineage Summary

This skill guides the agent in investigating and summarizing the Data Lineage
graph for a specific focal asset (Table-Level Lineage) or specific fields
(Column-Level Lineage). It provides an intuitive left-to-right walkthrough of
how data enters and leaves the asset, abstracting away complex node and link
details into plain English.

## Prerequisites

This skill relies on the **Google Cloud Data Lineage (Knowledge Catalog) MCP
Server** for graph traversal. Ensure you can run `search_lineage` queries in
both upstream and downstream directions. For detailed connection configurations
and tool schemas, refer to [MCP Usage](references/mcp-usage.md).

## Workflow Logic

### 1. Get Lineage

Fetch the lineage graph in both directions from the focal point (both upstream
and downstream) by making *two separate calls* to the MCP tool: one with
`"direction": "UPSTREAM"` and another with `"direction": "DOWNSTREAM"`.

*   **Location Strategy**: You **MUST** use the `read_url` tool to fetch the
    comprehensive list of locations dynamically from the provided
    [Knowledge Catalog Locations](https://docs.cloud.google.com/dataplex/docs/locations.md.txt)
    link. To ensure cross-regional lineage is not missed, always verify the
    current list of GCP regions using this link before populating the
    `locations` array. You **MUST** populate the `locations` array with all
    supported physical regions fetched from this link. You may optionally
    additionally determine the asset's specific active region (using `bq show`
    or `gcloud storage ls`).
*   **Search Parameters**: Use `maxDepth = 10`, `maxResults = 5000` and
    `maxProcessPerLink = 10` as robust defaults when calling `search_lineage`.
    For example, a DOWNSTREAM call should be formatted like this (expanding the
    `locations` array as needed):

    ```json
    {
      "parent": "projects/project_id/locations/us",
      "locations": [
        "us",
        "us-central1",
        "us-east1",
        "us-west1",
        "europe-west1",
        "asia-northeast1"
      ],
      "rootCriteria": {
        "entities": {
          "entities": [
            {
              "fullyQualifiedName": "bigquery:project.dataset.table"
            }
          ]
        }
      },
      "direction": "DOWNSTREAM",
      "limits": {
        "maxDepth": 10,
        "maxResults": 5000,
        "maxProcessPerLink": 10
      }
    }
    ```

    Ensure you make a similar call with `"direction": "UPSTREAM"` to fetch the
    upstream lineage.

*   **Column-Level Lineage (CLL)**: The `search_lineage` tool can find all
    Column-Level Lineage (CLL) by configuring the `field` array. If Table-Level
    Lineage (TLL) is requested, configure the call to get CLL links along with
    the TLL links by exploiting the `"*"` wildcard. For example:

    ```json
    "rootCriteria": {
      "entities": {
        "entities": [
          {
            "fullyQualifiedName": "bigquery:project.dataset.table",
            "field": [
              "*"
            ]
          }
        ]
      }
    }
    ```

    If evaluating a specific column, replace `"*"` with the specific column name
    (e.g., `"efficiency_score"`).

### 2. Summarize

Generate the summary using the prompt guidelines below.

*   **Persona**: Act as an expert Data Lineage Analyst generating a concise,
    easy-to-understand left-to-right walkthrough of the data flow.
*   **Structure & Flow**: Start immediately with the summary text, structured as
    follows:
    *   **Overall Flow Type**: State the inferred workflow type and data domain
        (e.g., "This appears to be a Feature Engineering workflow...").
    *   **Systems Overview**: List the primary systems involved up front. If the
        request is for Column-Level Lineage, you MUST explicitly declare that
        the scope of the analysis is limited to the specified field up front.
    *   **Upstream Lineage**: Use the exact bold header `**Upstream Lineage:**`.
        Narrative must detail how data arrives at the focal asset, mentioning
        key source systems, projects, and processing tasks (e.g., Spark on
        Dataproc).
    *   **Downstream Lineage**: Use the exact bold header `**Downstream
        Lineage:**`. Detail where data goes from the focal asset to final
        consumer systems.
    *   **Analysis Metadata**: Display the parameters used for the API call to
        provide transparency on the boundaries of the summary. The output must
        contain:
        *   **Locations Searched**: `{list_of_locations_queried}`
        *   **Parent Location**: `{parent_path}`
        *   **Depth Limit**: `{maxDepth}`
        *   **Process per Link Limit**: `{maxProcessPerLink}`
        *   **Tip for User**: A prompt suggesting they can ask to rerun with
            expanded locations (if not all were used) or depth.
*   **Granularity Constraints**:
    *   Prioritize flows between Systems, Projects, and Datasets over individual
        files/tables.
    *   You MUST explicitly list specific asset names (e.g., source tables,
        intermediate views, consumer tables) if there are fewer than 5. Do not
        just summarize counts if there are fewer than 5; name them explicitly.
        Otherwise, if 5 or more, aggregate them by count (e.g., "5 GCS
        buckets").
    *   Only mention counts for *ultimate sources*, *final consumers*, and
        *total assets*.
    *   Do not repeat project names redundantly for every dataset if only one
        project is involved.
*   **Tone**: Avoid jargon and generic phrases like "There are distinct factual
    points." Be direct and clear. The final output is Markdown.

### 3. Return the Summary

Return the final summarized output back to the user.

## External Documentation

-   [Google Cloud Knowledge Catalog Data Lineage Documentation](https://docs.cloud.google.com/dataplex/docs/about-data-lineage.md.txt)
-   [Use the Data Lineage MCP server](https://docs.cloud.google.com/dataplex/docs/use-lineage-mcp.md.txt)
-   [Knowledge Catalog Data Lineage API Reference](https://docs.cloud.google.com/dataplex/docs/reference/data-lineage/rest.md.txt)
