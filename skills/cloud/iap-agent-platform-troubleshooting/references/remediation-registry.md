# Remediation: IAP allow policies (V1) and Agent Registry

These templates change resources. Print them for the user to run; never run
them.

## Grant roles/iap.egressor

For IAP allow policies (V1). Role: IAP Policy Admin (`roles/iap.admin`).

This adds one binding and keeps the others. A resource gets the registry-wide
grants plus its own, so grant on the destination: the agent gets only the
access that the logs show it needs. A registry-wide grant (no resource flag)
covers every registered resource in `{registry_location}`. Print it only if the
user wants that scope, state the scope in the report, and offer a `--condition`
that narrows it (see
[V1 condition attributes](cel-attributes.md#v1-condition-attributes)).

```bash
gcloud iap web add-iam-policy-binding \
    --resource-type=agent-registry --region={registry_location} \
    {resource_flag} --member={principal} --role=roles/iap.egressor \
    --project={project_id}
```

-   `{resource_flag}`: `--mcp-server={mcp_server_id}`,
    `--endpoint={endpoint_id}`, or `--agent={agent_id}`, with the ID from the
    audit entry's `resource_id`. Leave it out for a registry-wide grant.
-   For a conditional grant, add
    `--condition=expression={cel_expression},title={title}`. If the expression
    contains commas, change the separator:
    `--condition=^:^title={title}:expression={cel_expression}`.

Source:
[Configure IAP allow policies](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/configure-iam-policies.md.txt).

## Register a destination in Agent Registry

Role: Agent Registry API Editor (`roles/agentregistry.editor`).

Register the endpoint in a registry that the gateway uses, in a region or
`global`, not the `us` or `eu` multi-region. `{protocol}` is `http-json`,
`grpc`, or `jsonrpc`.

After registration, `destination.unregistered.*` clauses in allow and deny
rules no longer match that host:

-   Before you print this template, search the bound Access policies for the
    hostname. For each clause that names it, also print the matching change to
    a `destination.agent_registry.*` condition, with "Change Access policy
    rules" in [remediation-access-policies.md](remediation-access-policies.md).
-   With IAP allow policies (V1), if no registry-wide `roles/iap.egressor`
    grant covers the agent, also print the "Grant roles/iap.egressor"
    template, so that the agent can reach the new resource.

```bash
gcloud agent-registry services create {service_id} \
    --location={registry_location} --project={project_id} \
    --display-name="{display_name}" --endpoint-spec-type=no-spec \
    --interfaces=url={url},protocolBinding={protocol}
```

To group several URLs into one endpoint and one IAP policy binding, repeat
`--interfaces`. For MCP servers, follow
[Register MCP servers](https://docs.cloud.google.com/agent-registry/register-mcp-servers.md.txt).
Source:
[Register endpoints](https://docs.cloud.google.com/agent-registry/register-endpoints.md.txt).

## Add a hostname variant to a registered service

Role: Agent Registry API Editor (`roles/agentregistry.editor`).

This adds an interface to the service that the endpoint was registered from,
so existing policies on that endpoint also cover the new URL.

After the update, `destination.unregistered.*` clauses in allow and deny rules
no longer match the new hostname:

-   Before you print this template, search the bound Access policies for the
    hostname. For each clause that names it, also print the matching change to
    a `destination.agent_registry.*` condition, with "Change Access policy
    rules" in [remediation-access-policies.md](remediation-access-policies.md).
-   With IAP allow policies (V1), if no `roles/iap.egressor` grant on the
    endpoint or registry-wide gives the agent access, also print the "Grant
    roles/iap.egressor" template.

```bash
gcloud agent-registry services update {service_id} \
    --location={registry_location} --project={project_id} \
    --add-interfaces=protocolBinding={protocol},url={url}
```

For all flags, see `gcloud agent-registry services update --help`.

## Add a tool to a registered MCP server

Role: Agent Registry API Editor (`roles/agentregistry.editor`).

Use this only for an MCP server registered with
`--mcp-server-spec-type=tool-spec`, because the spec type can't change after
registration. Servers that GKE or Cloud Run registered automatically have a
read-only tool list that comes from the server, so this template doesn't apply
to them.

The update replaces the whole spec, so `toolspec.json` must list every tool that
the server provides, not only the missing one. Build it from the server's own
`tools/list` response, which has the same format.

```bash
gcloud agent-registry services update {service_id} \
    --location={registry_location} --project={project_id} \
    --mcp-server-spec-content=toolspec.json
```

`{service_id}` is the name that the server was registered with (see
`gcloud agent-registry services list`), not the generated MCP server ID. The
spec is limited to 10 KB. Source:
[Register MCP servers](https://docs.cloud.google.com/agent-registry/register-mcp-servers.md.txt).

## Wait times

| Change | Wait |
| :--- | :--- |
| IAP allow policy (V1) binding | Typically 2 minutes, sometimes 7 minutes or longer ([Access change propagation](https://docs.cloud.google.com/iam/docs/access-change-propagation.md.txt)) |
| Agent Registry | No published figure, and a change can take a few minutes to apply. Retest after a few minutes, and look for a new audit entry |
