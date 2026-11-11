# CEL attributes for policy conditions

Access policy (V2) rules hold their CEL expression in
`conditions."iap.googleapis.com".expression`. The rule's effect applies only
when the whole expression is true. IAP allow policies (V1) use other attribute
names; see [V1 condition attributes](#v1-condition-attributes).

## Contents

- [Registered destinations](#registered-destinations): Lines 23-33
- [MCP servers](#mcp-servers): Lines 35-46
- [Unregistered destinations](#unregistered-destinations): Lines 48-54
- [Matching rules](#matching-rules): Lines 56-83
- [Fix patterns](#fix-patterns): Lines 85-126
- [V1 condition attributes](#v1-condition-attributes): Lines 128-142

Sources:
[CEL attributes for IAM Unified Access Policies](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/cel-attributes-uap.md.txt),
[Configure IAM Unified Access Policies](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/configure-iam-policies-uap.md.txt),
[IAP allow policies overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/iam-overview.md.txt),
[Configure IAP allow policies](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/configure-iam-policies.md.txt).

## Registered destinations

| Attribute | Values | Operators |
| :--- | :--- | :--- |
| `destination.is_registered` | `true`, `false` | `==`, `!=` |
| `destination.agent_registry.resource_type` | `'AGENT'`, `'ENDPOINT'`, `'MCP_SERVER'`, `'SKILL'` | `==`, `!=`, `in` |
| `destination.agent_registry.location` | Location ID, such as `'global'` or `'us-central1'` | `==`, `!=`, `in` |
| `destination.agent_registry.project_id` | Project ID | `==`, `!=`, `in` |
| `destination.agent_registry.agent.name` | `projects/{project_id}/locations/{location}/agents/{agent_name}` | `==`, `!=`, `in` |
| `destination.agent_registry.endpoint.name` | `projects/{project_id}/locations/{location}/endpoints/{endpoint_name}` | `==`, `!=`, `in` |
| `destination.agent_registry.mcp_server.name` | `projects/{project_id}/locations/{location}/mcpServers/{mcp_server_name}` | `==`, `!=`, `in` |

## MCP servers

| Attribute | Values | Operators |
| :--- | :--- | :--- |
| `destination.agent_registry.mcp_server.method` | JSON-RPC method of the request, such as `'initialize'`, `'tools/list'`, `'tools/call'`, `'prompts/get'`, or `'resources/read'` | `==`, `!=`, `in` |
| `destination.agent_registry.mcp_server.tool.name` | Tool name | `==`, `!=`, `in` |
| `destination.agent_registry.mcp_server.tool.annotations.read_only_hint` | `true`, `false` | `==`, `!=` |
| `destination.agent_registry.mcp_server.tool.annotations.destructive_hint` | `true`, `false` | `==`, `!=` |
| `destination.agent_registry.mcp_server.tool.annotations.idempotent_hint` | `true`, `false` | `==`, `!=` |
| `destination.agent_registry.mcp_server.tool.annotations.open_world_hint` | `true`, `false` | `==`, `!=` |
| `destination.agent_registry.mcp_server.prompt.name` | Prompt name | `==`, `!=`, `in` |
| `destination.agent_registry.mcp_server.resource.name` | Resource name | `==`, `!=`, `in` |

## Unregistered destinations

| Attribute | Values | Operators |
| :--- | :--- | :--- |
| `destination.unregistered.host` | Hostname, such as `'example.com'` | `==`, `!=`, `in`, `startsWith()`, `endsWith()`, `contains()` |
| `destination.unregistered.path` | Request path, such as `'/api/v1'` | `==`, `!=`, `in`, `startsWith()`, `endsWith()`, `contains()` |
| `destination.unregistered.method` | `'GET'`, `'POST'`, `'PUT'`, `'DELETE'` | `==`, `!=`, `in` |

## Matching rules

-   `startsWith()`, `endsWith()`, and `contains()` work only on
    `destination.unregistered.host` and `destination.unregistered.path`.
-   IAP compares the method exactly as the request sent it, normally
    uppercase, such as `'POST'`. The gateway log's `httpRequest.requestMethod`
    shows it (see [gateway-setup.md](gateway-setup.md)). Some documentation
    examples use lowercase, so copy the case from the gateway log. A rule with
    `'post'` never matches a POST request. Never tell the user to change the
    case of a rule that already matches.
-   `mcp_server.method` holds the MCP JSON-RPC method, such as `'tools/call'` or
    `'initialize'`. The public attribute table shows `'tools'` and `'prompts'`,
    but a condition such as `method == 'tools'` never matches.
-   `tool.name` and `tool.annotations.*` are set only on `tools/call` requests,
    from the registered tool spec. On `initialize`, `tools/list`, and other
    methods, the name is empty and every annotation is `false`. An allow rule
    that requires a tool attribute therefore doesn't allow the MCP handshake,
    and the client fails before it calls any tool.
-   Hostnames match exactly. `us-central1-aiplatform.googleapis.com` and
    `us-central1-aiplatform.mtls.googleapis.com` are different hosts, so the
    condition must cover every variant that the agent calls.
-   Resource names have no `registries/` segment. Copy the exact value from the
    audit entry's `metadata.destination.agent_registry.resource_id`, from the
    `name` in Agent Registry list output, or from a clause in the same policy
    that already matches, instead of building it by hand. Resource names use
    the project ID. A project number in its place never matches.
-   Compare the principal separately. The condition can't fix a principal that
    doesn't match the audit entry's `principalSubject`.

## Fix patterns

Keep the clauses that already work, and widen only the part that failed.

Add a missing hostname variant:

```text
destination.unregistered.host in ['us-central1-aiplatform.googleapis.com',
    'us-central1-aiplatform.mtls.googleapis.com']
```

Allow a path prefix and methods on an unregistered host:

```text
destination.unregistered.host == '{host}' &&
destination.unregistered.path.startsWith('{path_prefix}') &&
destination.unregistered.method in ['GET', 'POST']
```

Allow one registered MCP server:

```text
destination.agent_registry.mcp_server.name == '{mcp_server_name}'
```

Allow only read-only tools on that MCP server, and keep the handshake and tool
discovery working:

```text
destination.agent_registry.mcp_server.name == '{mcp_server_name}' &&
(destination.agent_registry.mcp_server.method != 'tools/call' ||
destination.agent_registry.mcp_server.tool.annotations.read_only_hint == true)
```

Allow every registered destination in one registry location. Use this pattern
only if the user explicitly asks for it, because it's broader than the smallest
fix:

```text
destination.is_registered == true &&
destination.agent_registry.location == '{registry_location}'
```

## V1 condition attributes

IAP allow policy conditions read attributes with `api.getAttribute()`, which
takes the attribute name and a default value:

| Attribute | Example |
| :--- | :--- |
| `iap.googleapis.com/mcp.toolName` | `api.getAttribute('iap.googleapis.com/mcp.toolName', '') == '{tool_name}'` |
| `iap.googleapis.com/mcp.resourceName` | `api.getAttribute('iap.googleapis.com/mcp.resourceName', '') == '{resource_name}'` |
| `iap.googleapis.com/mcp.promptName` | `api.getAttribute('iap.googleapis.com/mcp.promptName', '') == '{prompt_name}'` |
| `iap.googleapis.com/mcp.tool.isReadOnly` | `api.getAttribute('iap.googleapis.com/mcp.tool.isReadOnly', false) == true` |
| `iap.googleapis.com/mcp.tool.isDestructive`, `.isIdempotent`, `.isOpenWorld` | Same form as `isReadOnly` |
| `iap.googleapis.com/request.auth.type` | `api.getAttribute('iap.googleapis.com/request.auth.type', '') == 'MCP'` |

Don't mix V1 and V2 attribute names in one condition.
