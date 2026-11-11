# Agent Registry lookups

IAP for agents matches each egress request against the Agent Registry
instances that Agent Gateway uses. A destination counts as registered only when
its hostname matches a registered interface URL exactly. Policies that name a
registry resource must use the name that Agent Registry assigned.

Sources:
[Troubleshoot Agent Gateway](https://docs.cloud.google.com/gemini-enterprise-agent-platform/troubleshooting/troubleshoot-agent-gateway.md.txt),
[Set up Agent Gateway](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/set-up-agent-gateway.md.txt),
[Register endpoints](https://docs.cloud.google.com/agent-registry/register-endpoints.md.txt),
[Register MCP servers](https://docs.cloud.google.com/agent-registry/register-mcp-servers.md.txt),
[Agent Registry locations](https://docs.cloud.google.com/agent-registry/locations.md.txt),
[IAP allow policies overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/iam-overview.md.txt).

## Which registry to search

-   Search the registries listed in the gateway's `registries` field (see
    [gateway-setup.md](gateway-setup.md)). Use the project ID and location
    from each registry path as `{project_id}` and `{registry_location}`.
-   If the gateway uses a global and a regional or multi-regional registry,
    the regional or multi-regional entry takes precedence over a global entry
    with the same interface URL.
-   An agent in another project must be registered in the registry of the
    project where Agent Gateway runs.
-   Agents, MCP servers, and endpoints can't be registered manually in the `us`
    and `eu` multi-regions. Use a region or `global`.

## Resolve a destination by URL

```bash
gcloud agent-registry endpoints list \
    --location={registry_location} --project={project_id} \
    --format="json(name,interfaces)"
gcloud agent-registry mcp-servers list \
    --location={registry_location} --project={project_id} \
    --format="json(name,interfaces)"
gcloud agent-registry agents list \
    --location={registry_location} --project={project_id}
```

`{host}` is the hostname of the URL that the agent called. A resource matches
only if the hostname of one of its `interfaces[].url` values equals `{host}`
exactly. Compare the hostnames yourself instead of with `--filter`, because a
filter's `:` operator isn't an exact match. Use the full `name` in CEL.

To read one resource in full:

```bash
gcloud agent-registry mcp-servers describe {mcp_server_id} \
    --location={registry_location} --project={project_id}
gcloud agent-registry endpoints describe {endpoint_id} \
    --location={registry_location} --project={project_id}
gcloud agent-registry agents describe {agent_id} \
    --location={registry_location} --project={project_id}
```

-   Resource names have the form
    `projects/{project_id}/locations/{registry_location}/mcpServers/{mcp_server_id}`
    (or `endpoints/` or `agents/`). There's no `registries/` segment and no
    `--registry` flag. Policy conditions use this full `name`, not its
    basename.
-   If no resource matches in any registry that the gateway uses, the
    destination isn't registered. The IAP audit entry agrees: it has
    `metadata.destination.unregistered`, or its
    `labels."iap.googleapis.com/audited_resource_name"` is
    `unregisteredResource` or ends in `unregisteredEndpoint`.
-   Exception for MCP servers registered with a tool spec: a `tools/call` for a
    tool that isn't in the spec is also logged as unregistered, even though the
    hostname matches the server's interface URL. Compare the tool that the agent
    called with `tools[].name` in `mcp-servers describe` output before you call
    the host unregistered.

## Common causes

| Cause | Evidence | Fix |
| :--- | :--- | :--- |
| Hostname variant not registered | The URL in the gateway log, for example a regional or `mtls` hostname, matches no interface URL | Add the variant as an interface of the existing service (read the registration warning below). With Access policies (V2) only, you can instead allow it with a `destination.unregistered.host` condition |
| Destination not registered | No resource matches the URL | Register it (read the registration warning below). IAP allow policies (V1) can't allow an unregistered destination, so with V1, register it and then grant `roles/iap.egressor`. With Access policies (V2) only, you can instead allow it with `destination.unregistered.*` conditions ([cel-attributes.md](cel-attributes.md)) |
| Tool missing from the MCP server's tool spec | The audit entry is unregistered, but the host matches an MCP server's interface URL, and the called tool isn't in its `tools[].name` | Add the tool to the tool spec ("Add a tool to a registered MCP server" in [remediation-registry.md](remediation-registry.md)). Don't allow it with `destination.unregistered.*` clauses, which stop matching once the tool is added |
| Wrong resource ID in a rule | The name in the policy differs from `name` in the list output for that URL, for example a display name in place of the generated ID, or the project number in place of the project ID | Replace the name in the rule with the full `name` from the list output, not its basename |
| Wrong registry | The resource exists, but in a registry that the gateway doesn't use | Register it in a registry that the gateway uses |

**Registration warning:** after a hostname is registered,
`destination.unregistered.*` clauses in allow and deny rules no longer match
it. Before you print a registration or interface template, search the bound
Access policies for the hostname, and also print the matching change to a
`destination.agent_registry.*` condition. With IAP allow policies (V1), also
print the `roles/iap.egressor` grant for a newly registered resource.

-   Registering an endpoint creates a `Service` resource. Agent Registry then
    generates a read-only `Endpoint` resource. In policy conditions, use the
    endpoint's full `name` from `endpoints list`, not its basename.
-   A service with several `--interfaces` values is one endpoint, so a single
    IAP policy binding covers every interface URL.
-   The registration and interface templates are in
    [remediation-registry.md](remediation-registry.md).
