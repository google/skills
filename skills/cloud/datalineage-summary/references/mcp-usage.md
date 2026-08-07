# Google Cloud Data Lineage MCP Usage

The Data Lineage service is supported by a remote Model Context Protocol (MCP)
server that provides structured tools for discovering relationships between data
assets.

## MCP Tools for Data Lineage

-   **search_lineage**: Performs a breadth-first search (upstream or downstream)
    to retrieve lineage links for an asset identified by its Fully Qualified
    Name (FQN). Supports Column-Level Lineage (CLL).

### Tool Preference Hierarchy

*   Default: Data Lineage MCP tool (`DataLineageServer:search_lineage`) > `bq`
    CLI > `gcloud` CLI.
*   Note: `gcloud` does NOT support lineage links searches in standard/beta
    tracks. Always prefer the MCP tool.

## Setup Instructions

To connect to the Data Lineage MCP server, see
[Use the Data Lineage MCP server](https://docs.cloud.google.com/dataplex/docs/use-lineage-mcp.md.txt).

For client configuration, add the following block to your agent's MCP
configuration file (e.g., `mcp_config.json`):

```json
{
  "mcpServers": {
    "DataLineageServer": {
      "serverUrl": "https://datalineage.googleapis.com/mcp",
      "authProviderType": "google_credentials",
      "headers": {
        "x-goog-user-project": "<GCP_PROJECT_ID>"
      }
    }
  }
}
```
