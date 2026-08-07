---
name: datalineage-bigquery-asset-impact-analysis
metadata:
  category: BigDataAndAnalytics
description: >-
  Analyzes the downstream impact (blast radius) when a BigQuery table or view is broken, stale, or modified.
  Identifies all downstream tables, dashboards, and processes that will be affected.
  Use when:
  - Performing a blast radius or impact analysis for a BigQuery table or view.
  - Assessing the consequences of modifying, deleting, or pausing updates to a BigQuery asset.
  - Identifying downstream dependencies (tables, dashboards, processes) of a BigQuery asset.
  Don't use for:
  - General BigQuery querying or data analysis (use BigQuery-related tools instead).
  - Non-BigQuery assets (e.g., Cloud Storage files) unless they are part of the BigQuery lineage.
  - Creating or modifying lineage links directly.
---

# BigQuery Asset Impact Analysis

This skill guides the agent in performing a downstream impact analysis (blast
radius assessment) when a BigQuery table or view is reported as broken, stale,
missing, or when a user is planning maintenance and wants to know the
consequences of modifying or pausing updates to an asset.

It relies primarily on the **Google Cloud Data Lineage (Knowledge Catalog) MCP Server**
to discover relationships between assets.

## Prerequisites

This skill requires access to the Google Cloud Data Lineage API and an active
client connection to the Data Lineage MCP Server. For detailed connection
configurations and tool schemas, refer to [MCP Usage](references/mcp-usage.md).

## Analysis Workflow

### 1. Resolve the Asset's Fully Qualified Name (FQN)

*   Ensure you have the correct FQN format for the BigQuery asset:
    *   *Format:* `bigquery:{project_id}.{dataset_id}.{table_or_view_id}`
    *   *Example:* `bigquery:my-prod-project.analytics.orders`


### 2. Determine Locations and Parent Path

Identify the locations to search and construct the Data Lineage API request:

*   **Discover Asset Location**: Run the command `bq show --format=json
    {project_id}:{dataset_id}` and extract the `location` field (e.g.,
    `us-central1` or `us`). If location discovery fails due to permissions or
    missing tools, prompt the user for the dataset's location.
*   **Set Parent Path**: Set the `parent` path using the project ID and the
    MCP server's location. Consult the `DataLineageServer` tool definition
    to find the configured region or location (e.g., `us`). The format is:
    `projects/{project_id}/locations/{mcp_server_location}`.
*   **Configure Search Scope**: Include the discovered asset location in the
    `locations` array of the payload (e.g., `["us-central1"]` or `["us",
    "us-central1"]`).

### 3. Retrieve the Downstream Lineage Graph

Call the `DataLineageServer:search_lineage` tool to fetch downstream
relationships.

*   **Direction**: Set to `DOWNSTREAM`.
*   **Search Parameters**: Use `max_depth = 10` and `max_process_per_link = 5`
    as robust defaults.

### 4. Identify the Blast Radius

Traverse the returned lineage links to build the impact graph:

*   **Affected Assets**: The `target` of each link represents a downstream asset
    that depends on your source asset.
*   **Transform Processes**: Inspect the `processes` field on each link. This
    identifies the ETL pipelines, BigQuery Views, or Scheduled Queries that
    propagate the data.
*   **Direct vs. Indirect Impact**:
    *   **Direct Impact (Depth 1)**: Assets directly consuming the source asset.
        If a link has `dependency_type: EXACT_COPY`, mark the target as
        "Directly Stale / Identical Copy".
    *   **Indirect Impact (Depth > 1)**: Assets further down the stream that
        will experience cascading stale data or failures.

### 5. Summarize and Format the Output

Present your findings clearly to the user using the following structure:

1.  **Executive Summary**: State the total number of downstream assets affected
    and the maximum depth of the impact.
2.  **Critical Path**: Highlight high-priority downstream assets (e.g., assets
    containing "prod", "dashboard", "reporting", or "master" in their names).
3.  **Blast Radius Table**: A clean Markdown table listing the dependencies. You
    MUST include all columns:

    | Downstream Asset                 | Transform Process                     | Depth | Impact Type |
    | :------------------------------- | :------------------------------------ | :---- | :---------- |
    | `bigquery:project.dataset.table` | `projects/p/locations/l/processes/proc` | 1     | Direct      |
    | `bigquery:project.dataset.view`  | `projects/p/locations/l/processes/view` | 2     | Indirect    |
4.  **Analysis Metadata**: Provide transparency on the parameters and boundaries
    of your search so the user can choose to expand them:
    *   **Locations Searched**: `{list_of_locations_queried}`
    *   **Parent Location**: `{parent_path}`
    *   **Depth Limit**: `{max_depth}`
    *   **Process per Link Limit**: `{max_process_per_link}`
    *   *Tip for User*: Let the user know they can request to rerun the analysis
        with expanded locations or larger depth limits.

## Crucial Constraints & Guardrails

1.  **Interpret Empty Responses Correctly**:
    *   If the lineage response is empty, immediately assume that no
        dependencies exist in the queried locations and report this to the
        user.
2.  **Strictly Banned Bypasses**:
    *   Exclusively retrieve downstream relationships using the
        `DataLineageServer:search_lineage` tool.
3.  **Verify Asset Existence First**:
    *   If `bq show` indicates the source table does not exist, stop and report
        this directly to the user. Do not attempt to guess alternative table
        names unless the user explicitly instructs you to do so.
4.  **No Output Shortcutting or Hallucinated Artifacts**:
    *   Present the complete downstream blast radius table directly in your
        final response. Avoid telling the user you have created a separate
        Markdown file or artifact containing the details unless you have
        explicitly executed file-writing tools to create it.

## Reference Directory

-   [MCP Usage](references/mcp-usage.md): Using the Google Cloud Data Lineage
    remote MCP server and tool preferences.

## External Documentation

-   [Google Cloud Knowledge Catalog Data Lineage Documentation](https://cloud.google.com/dataplex/docs/about-data-lineage)
-   [Use the Data Lineage MCP server](https://docs.cloud.google.com/dataplex/docs/use-lineage-mcp)
-   [Knowledge Catalog Data Lineage API Reference](https://cloud.google.com/dataplex/docs/reference/data-lineage/rest)
