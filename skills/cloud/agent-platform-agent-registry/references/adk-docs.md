# Google Cloud Agent Registry — Python ADK Integration

## Table of Contents

- [Use Cases](#use-cases): Lines 23-31
- [Prerequisites](#prerequisites): Lines 32-49
- [Installation](#installation): Lines 50-81
- [Use with Agent (`AgentRegistry` Client)](#use-with-agent-agentregistry-client): Lines 82-134
- [Authentication for Google MCP Servers and Remote A2A Agents](#authentication-for-google-mcp-servers-and-remote-a2a-agents): Lines 135-256
- [API Reference](#api-reference): Lines 257-286
- [Configuration Options](#configuration-options): Lines 287-297
- [Additional Resources](#additional-resources): Lines 298-302

---

The Agent Registry client library within the Agent Development Kit (ADK) allows
developers to discover, look up, and connect to AI Agents and MCP Servers
cataloged within the
[Google Cloud Agent Registry](https://docs.cloud.google.com/agent-registry/overview.md.txt).
This enables dynamic composition of agent-based applications using governed
components.

## Use Cases

- **Accelerated Development**: Find and reuse existing agents and tools (MCP
  Servers) from the central catalog instead of rebuilding them.
- **Dynamic Integration**: Discover agent and MCP Server endpoints at runtime,
  making applications resilient to environment changes.
- **Enhanced Governance**: Use governed and verified components from the
  registry within your ADK applications.

## Prerequisites

- A
  [Google Cloud project](https://docs.cloud.google.com/resource-manager/docs/creating-managing-projects.md.txt)
  with an active billing account attached.
- The
  [Agent Registry API](https://docs.cloud.google.com/agent-registry/setup.md.txt)
  enabled in your Google Cloud project (`gcloud services enable
  agentregistry.googleapis.com`).
- Authentication configured for your environment using
  [Application Default Credentials](https://docs.cloud.google.com/docs/authentication/application-default-credentials.md.txt)
  (ask the user to run `gcloud auth application-default login` interactively).
- Environment variables `GOOGLE_CLOUD_PROJECT` set to your project ID and
  `GOOGLE_CLOUD_LOCATION` set to the appropriate region (e.g., `global`,
  `us-central1`).
- `google-adk` library installed (seek explicit user approval before running
  `pip install` on the host).

## Installation

Install `google-adk` with the A2A, Agent Identity, and MCP extras (pinning to
`>=1.0.0,<2.0.0` in `requirements.txt` for reproducible builds):

```bash
pip install "google-adk[a2a,agent-identity,mcp]>=1.0.0,<2.0.0"
```

### Optional Dependencies

You can also install individual extras depending on your use case:

- **For A2A (Agent-to-Agent) Support (`a2a`)**: Required for
  `get_remote_a2a_agent` and `RemoteA2aAgent`:
  ```bash
  pip install "google-adk[a2a]>=1.0.0,<2.0.0"
  ```

- **For MCP Toolsets (`mcp`)**: Required for `get_mcp_toolset` and
  `McpToolset`:
  ```bash
  pip install "google-adk[mcp]>=1.0.0,<2.0.0"
  ```

- **For Agent Identity Auth Manager Bindings (`agent-identity`)**: Required for
  `GcpAuthProviderScheme` when `get_mcp_toolset` or `get_remote_a2a_agent`
  automatically resolves credentials via Agent Registry `Binding` resources:
  ```bash
  pip install "google-adk[agent-identity]>=1.0.0,<2.0.0"
  ```

## Use with Agent (`AgentRegistry` Client)

The primary way to use the Agent Registry integration within an ADK agent is to
dynamically fetch remote agents or toolsets using the `AgentRegistry` client:

```python
import os
from google.adk.agents.llm_agent import LlmAgent
from google.adk.integrations.agent_registry import AgentRegistry

# 1. Initialization
project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")

if not project_id:
    raise ValueError("GOOGLE_CLOUD_PROJECT environment variable not set.")

registry = AgentRegistry(
    project_id=project_id,
    location=location,
)

# 2. Listing Resources
print("\nListing Agents...")
agents_response = registry.list_agents()
for agent in agents_response.get("agents", []):
    print(f"  - {agent.get('name')} ({agent.get('displayName')})")

print("\nListing MCP Servers...")
mcp_servers_response = registry.list_mcp_servers()
for server in mcp_servers_response.get("mcpServers", []):
    print(f"  - {server.get('name')} ({server.get('displayName')})")

# 3. Using a Remote A2A Agent
# Replace with the full resource name of your registered agent
agent_name = f"projects/{project_id}/locations/{location}/agents/YOUR_AGENT_ID"
my_remote_agent = registry.get_remote_a2a_agent(agent_name=agent_name)

# 4. Using an MCP Toolset
# Replace with the full resource name of your registered MCP server
mcp_server_name = f"projects/{project_id}/locations/{location}/mcpServers/YOUR_MCP_SERVER_ID"
my_mcp_toolset = registry.get_mcp_toolset(mcp_server_name=mcp_server_name)

# 5. Example Agent Composition
main_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="demo_agent",
    instruction="You can leverage registered tools and sub-agents.",
    tools=[my_mcp_toolset],
    sub_agents=[my_remote_agent],
)
```

## Authentication for Google MCP Servers and Remote A2A Agents

### Remote A2A Agents

- **Automatic Resolution via Auth Manager `Binding`**: When an Agent Identity
  Auth Manager `Binding` exists for the target agent in Agent Registry,
  `registry.get_remote_a2a_agent(agent_name)` resolves request credentials
  automatically via `GcpAuthProviderScheme` — no custom `httpx_client`
  boilerplate is needed.
- **When No `Binding` Exists**: Pass a custom `httpx.AsyncClient` matching the
  bearer token type expected by the target A2A endpoint:

1. **Google Cloud API A2A Endpoints (`https://*.googleapis.com`)**: Attach an
   OAuth 2.0 access token scoped to
   `https://www.googleapis.com/auth/cloud-platform`, plus `X-Goog-User-Project`
   when Application Default Credentials (ADC) have no default quota project:

   ```python
   import httpx
   import google.auth
   from google.auth.transport.requests import Request


   class GoogleApiAuth(httpx.Auth):
       def __init__(self, quota_project_id: str | None = None):
           self.quota_project_id = quota_project_id
           self.creds, _ = google.auth.default(
               scopes=["https://www.googleapis.com/auth/cloud-platform"]
           )

       def auth_flow(self, request):
           if not self.creds.valid:
               self.creds.refresh(Request())
           request.headers["Authorization"] = f"Bearer {self.creds.token}"
           quota_project = self.quota_project_id or getattr(
               self.creds, "quota_project_id", None
           )
           if quota_project:
               request.headers["X-Goog-User-Project"] = quota_project
           yield request


   httpx_client = httpx.AsyncClient(
       auth=GoogleApiAuth(quota_project_id=project_id),
       timeout=httpx.Timeout(60.0),
   )

   remote_agent = registry.get_remote_a2a_agent(
       f"projects/{project_id}/locations/{location}/agents/YOUR_AGENT_ID",
       httpx_client=httpx_client,
   )
   ```

2. **Cloud Run (`https://*.run.app`) or IAP-Protected A2A Endpoints**: OAuth 2.0
   access tokens fail against Cloud Run and Identity-Aware Proxy (IAP) HTTPS
   agents. Attach an **OIDC ID token**
   (`google.oauth2.id_token.fetch_id_token(Request(), target_audience)`) whose
   `aud` claim matches the target Cloud Run service URL or IAP OAuth 2.0 client
   ID (requires a service account, compute metadata server, or impersonated
   credentials; for local user-credential testing, mint an ID token with
   `gcloud auth print-identity-token --audiences=TARGET_AUDIENCE`):

   ```python
   import httpx
   from google.auth.transport.requests import Request
   from google.oauth2 import id_token


   class OidcIdTokenAuth(httpx.Auth):
       def __init__(self, target_audience: str):
           self.target_audience = target_audience

       def auth_flow(self, request):
           oidc_jwt = id_token.fetch_id_token(Request(), self.target_audience)
           request.headers["Authorization"] = f"Bearer {oidc_jwt}"
           yield request


   httpx_client = httpx.AsyncClient(
       auth=OidcIdTokenAuth("https://my-agent-123456.us-central1.run.app"),
       timeout=httpx.Timeout(60.0),
   )

   remote_agent = registry.get_remote_a2a_agent(
       f"projects/{project_id}/locations/{location}/agents/YOUR_AGENT_ID",
       httpx_client=httpx_client,
   )
   ```

### Google MCP Servers

For Google MCP servers (`https://*.googleapis.com`), authentication headers are
automatically passed in (or resolved via Auth Manager `Binding`). If you need
custom header resolution, provide a `header_provider` callable in the
`AgentRegistry` constructor:

```python
import google.auth
from google.auth.transport.requests import Request
from google.adk.integrations.agent_registry import AgentRegistry


def google_auth_header_provider(context):
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    if not creds.valid:
        creds.refresh(Request())
    headers = {"Authorization": f"Bearer {creds.token}"}
    quota_project = getattr(creds, "quota_project_id", None) or project_id
    if quota_project:
        headers["X-Goog-User-Project"] = quota_project
    return headers


registry = AgentRegistry(
    project_id=project_id,
    location=location,
    header_provider=google_auth_header_provider,
)
```

## API Reference

The `AgentRegistry` class provides the following core methods:

- `list_mcp_servers(self, filter_str=None, page_size=None, page_token=None)`:
  Fetches a list of registered MCP Servers.
- `search_mcp_servers(self, *, search_string=None, search_type=None, ...)`:
  Searches registered MCP Servers (`KEYWORD` or `SEMANTIC`).
- `get_mcp_server(self, name)`: Retrieves detailed metadata of a specific MCP
  Server.
- `get_mcp_toolset(self, mcp_server_name, auth_scheme=None, ...)`: Constructs
  an ADK `McpToolset` from a registered MCP Server (accepts `auth_credential`
  and `continue_uri`, plus `projects/.../locations/.../mcpServers/...` or
  `mcpServers/...`; resolves `auth_scheme` automatically via
  `GcpAuthProviderScheme` when an Auth Manager `Binding` exists).
- `list_agents(self, filter_str=None, page_size=None, page_token=None)`:
  Fetches a list of registered A2A Agents.
- `search_agents(self, *, search_string=None, search_type=None, ...)`: Searches
  registered A2A Agents (`KEYWORD` or `SEMANTIC`).
- `get_agent_info(self, name)`: Retrieves detailed metadata of a specific A2A
  Agent.
- `get_remote_a2a_agent(self, agent_name, *, httpx_client=None, ...)`: Creates
  an ADK `RemoteA2aAgent` (accepts `auth_scheme`, `auth_credential`, and
  `continue_uri`, plus full or relative `agents/...` names; resolves
  `auth_scheme` automatically via `GcpAuthProviderScheme` when an Auth Manager
  `Binding` exists).
- `list_endpoints(self, filter_str=None, page_size=None, page_token=None)`,
  `get_endpoint(self, name)`, and `get_model_name(self, endpoint_name)`: Lists
  or resolves registered Endpoints.

## Configuration Options

The `AgentRegistry` constructor accepts the following arguments:

- `project_id` (`str`, required): The Google Cloud project ID.
- `location` (`str`, required): The Google Cloud location/region, such as
  `"global"`, `"us-central1"`.
- `header_provider` (`Callable`, optional): A callable taking a
  `ReadonlyContext` and returning a dictionary of custom headers to include in
  requests made by `McpToolset` or `RemoteA2aAgent` to target services.

## Additional Resources

- [Build Multi-Agent Systems & Call A2A Agents](https://docs.cloud.google.com/agent-registry/resolve-endpoints-and-build-orchestrators.md.txt)
- [ADK Agent Registry Integration](https://google.github.io/adk-docs/integrations/agent-registry/)
- [Google Auth Library](https://google-auth.readthedocs.io/en/latest/)
