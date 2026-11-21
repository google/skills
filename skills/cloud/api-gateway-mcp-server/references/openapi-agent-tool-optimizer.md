# OpenAPI Agent Tool Optimizer Reference

- [High-Accuracy Tool Descriptions](#high-accuracy-tool-descriptions): Lines 7-24
- [Schema Rendering and OpenAPI 3.x MCP Limits](#schema-rendering-and-openapi-3x-mcp-limits): Lines 26-39
- [Chatty CRUD and Destructive Endpoint Rules](#chatty-crud-and-destructive-endpoint-rules): Lines 41-45

## High-Accuracy Tool Descriptions

Every exposed MCP operation MUST resolve to a non-empty description (taken from `x-google-mcp-tool.description`, the operation `description`, or `summary`); operations without a resolvable description are rejected by API Gateway when creating the API config. The tool description is the primary signal an LLM uses for tool selection. Standard OpenAPI summaries ("Gets an order", "Creates an RMA") describe *what* an endpoint returns, but omit *when* and *why* an agent should call it.

Use `x-google-mcp-tool.description` on each exposed operation to set the LLM-facing description. The operation's own `description` stays unchanged for REST documentation:

1. **State the trigger condition ("Use this tool when..."):** Specify the exact user intent or prerequisite state that requires calling this tool.
2. **Specify ordering dependencies:** If a write tool (`create_return_rma`) requires an identifier (`itemSku`) returned by a read tool (`get_order_status`), instruct the agent in `x-google-mcp-tool.description` to call the read tool first whenever that identifier is unknown.
3. **Document parameter formats inline:** Add concrete format examples (`ORD-XXXXX`, ISO-8601 dates, allowed `enum` values) to each parameter's `description` field so the model formats arguments accurately on the first attempt.

```yaml
      x-google-mcp-tool:
        name: create_return_rma
        description: >-
          Create a Return Merchandise Authorization (RMA) and generate a prepaid return label for a delivered order.
          Use this tool when a customer asks to return or replace an item.
          Call get_order_status first if you do not yet know the itemSku or if you have not verified that the order status is DELIVERED.
```

## Schema Rendering and OpenAPI 3.x MCP Limits

API Gateway enforces specific schema and payload rules when generating MCP tool declarations from an OpenAPI 3.x specification:

| Constraint | API Gateway MCP Behavior | Required OpenAPI Refactoring |
| --- | --- | --- |
| Nested object schemas | API Gateway rejects complex nested schemas when you create the API config. A simple nested object body works. | Prefer shallow request schemas for new tools. If `gcloud api-gateway api-configs create` fails with a schema error, simplify that schema. Add a `description` with the expected format to each property, and check the tool's `inputSchema` in `tools/list` after you deploy. |
| Request parameter types | API Gateway supports only primitive types in request parameters. | Use primitive types (`string`, `integer`, `number`, `boolean`) for path, query, and header parameters of a tool. Otherwise, set `x-google-mcp-tool: false` on the operation. |
| Empty response bodies (`HTTP 204`) | Operations that return empty response bodies (such as `204 No Content`) are NOT supported as MCP tools. | Update the backend and OpenAPI `responses` block to return `200 OK` with a JSON confirmation object (for example, `{"deleted": true, "id": "..."}`), or set `x-google-mcp-tool: false` on `204` endpoints. |
| External `$ref` references and file limits | External `$ref` URLs are rejected. An OpenAPI document can have at most `200` YAML alias nodes. Uploaded OpenAPI 3.x files are limited to `10 MB` total and `50` files. | Inline external `$ref` definitions into local `#/components/schemas/`, and use at most `200` YAML alias nodes. |
| Tool count limit | Maximum of `1,000` MCP tools per gateway. | Expose only curated, task-oriented operations rather than every raw database table route. |
| Supported HTTP methods | Only `GET`, `POST`, `PUT`, `PATCH`, and `DELETE` can be exposed as MCP tools. `HEAD`, `OPTIONS`, and `TRACE` are not supported. | Global MCP enablement does not expose `HEAD`, `OPTIONS`, or `TRACE` operations. Do not set `x-google-mcp-tool` to `true` or an object on them: the validator reports an error. |

Reference: [OpenAPI 3.x feature limitations - MCP limitations](https://docs.cloud.google.com/api-gateway/docs/openapi-v3-limitations.md.txt)

## Chatty CRUD and Destructive Endpoint Rules

1. **Opt out internal and administrative routes:** When `x-google-api-management.mcp` is set to `true` (or configured as an object for `tools-list`), every eligible `GET`, `POST`, `PUT`, `PATCH`, and `DELETE` operation in the specification becomes an MCP tool by default. Explicitly set `x-google-mcp-tool: false` on health checks (`/healthz`), metrics endpoints, bulk-delete operations, and internal admin routes.
2. **Keep REST security on opted-out routes:** NEVER rely on `x-google-mcp-tool: false` to secure an administrative operation. **Rationale:** Setting `x-google-mcp-tool: false` only omits the operation from MCP `tools/list` and blocks `tools/call`, while the underlying REST path remains live on the gateway hostname unless protected by a strict `security` requirement or removed from the OpenAPI specification.
3. **Warn on destructive tools:** Because API Gateway does not emit `destructiveHint` or `readOnlyHint` annotations in Public Preview, include an explicit warning in `x-google-mcp-tool.description` on any `DELETE` or `PUT` operation that remains exposed (for example, *"Permanently deletes the resource. Call only after explicit user confirmation."*).
