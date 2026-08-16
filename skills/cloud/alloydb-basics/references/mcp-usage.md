# AlloyDB MCP Usage

Configure the remote Model Context Protocol (MCP) server to allow AI
applications to query and administer AlloyDB databases.

## Endpoint

Use the region-specific API endpoint format:
`https://alloydb.REGION.rep.googleapis.com/mcp`

Replace `REGION` with the target Google Cloud region ID (e.g., `us-central1`).

## Setup and Authentication

1.  Enable the AlloyDB API (`alloydb.googleapis.com`) in the project.
2.  Grant the `roles/mcp.toolUser` role to the principal executing the tool
    calls.
3.  Point your MCP host to the regional endpoint. For detailed instructions, see
    the
    [Use the AlloyDB remote MCP server](https://docs.cloud.google.com/alloydb/docs/ai/use-alloydb-mcp.md.txt)
    guide.

## Resources

-   [AlloyDB API Documentation](https://cloud.google.com/alloydb/docs/reference/rest)
-   [MCP Toolbox](https://mcp-toolbox.dev/): Use this open-source tool as a
    local alternative to run the remote MCP server in development environments.
    -   [MCP Toolbox AlloyDB Integration](https://mcp-toolbox.dev/integrations/alloydb/source/)
    -   [Configure your MCP client](https://docs.cloud.google.com/alloydb/docs/connect-ide-using-mcp-toolbox.md.txt)
