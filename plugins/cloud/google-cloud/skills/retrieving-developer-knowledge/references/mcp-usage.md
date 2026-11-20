# MCP Tool Usage & API Details

The Developer Knowledge skill integrates with the Developer Knowledge Remote MCP
server (`https://developerknowledge.googleapis.com/mcp`).

## Available Tools

1.  **`search_documents`**:

    -   Accepts a search query string.
    -   Returns relevant document text chunks containing matching syntax, code
        blocks, or flags.
    -   Each returned item includes a `content` field and a `parent` URI field.

2.  **`answer_query`**:

    -   Accepts a natural language question.
    -   Performs server-side RAG and returns a synthesized response with source
        citations.
    -   This tool has limited quota. If you get a 429 out of quota error, use
        `search_documents` instead.

3.  **`get_documents`**:

    -   Fetches full document contents.
    -   Takes a `names` array parameter: `names:
        ["documents/{uri_without_scheme}"]`.
    -   Example: For parent URI `https://cloud.google.com/run/docs/deploying`,
        pass `names: ["documents/cloud.google.com/run/docs/deploying"]`.
