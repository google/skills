# Model Context Protocol (MCP) in Apigee

Apigee allows you to expose your existing REST APIs as **Model Context Protocol
(MCP) tools** to agentic AI applications. Instead of hand-authoring local MCP
servers or complex integrations, Apigee X provides a managed, cloud-native L7
bridge that handles JSON-RPC translation, security, and discovery automatically.

--------------------------------------------------------------------------------

## 1. Core Concepts

When you enable MCP in Apigee: * An Apigee proxy acts as the **HTTP MCP Server**
endpoint for compliant MCP hosts/clients. * The proxy translates standard MCP
JSON-RPC methods (like `tools/list` and `tools/call`) into backend REST calls,
maps OpenAPI operations to individual MCP tools, and transcodes the responses. *
A tenant-level managed endpoint (`{ORG_NAME}.mcp.apigee.internal`) is deployed
to execute routing.

--------------------------------------------------------------------------------

## 2. Exposing APIs as MCP Tools: Step-by-Step

Exposing REST APIs as MCP tools involves creating an OpenAPI spec, provisioning
an **MCP Discovery Proxy**, securing it, and deploying it.

### Step 1: Create an OpenAPI 3.0.x Specification

You must define the REST operations you want to expose as MCP tools. * Supported
OpenAPI versions: 3.0.0, 3.0.1, 3.0.2, 3.0.3. * **CRITICAL Hostname Matching
Requirement**: The hostname in the `servers.url` field of the OpenAPI spec
**MUST** exactly match the virtual host **hostname** of the environment group
where you deploy the proxy.

```yaml
# oas/quickstart-openapi.yaml
---
openapi: 3.0.3
info:
  title: Cymbal Products API
  description: Official API for managing products, mapped to MCP tools.
  version: 1.0.0
servers:
  - url: https://api.cymbal.com  # MUST match environment group hostname
paths:
  /products:
    get:
      description: Returns a list of available products
      operationId: listProducts
      responses:
        "200":
          description: Success
```

### Step 2: Create the MCP Discovery Proxy

1.  Open the **Apigee Console**.
2.  Navigate to **API proxies** and click **+ Create**.
3.  In the **Proxy template** box, select **MCP Discovery Proxy**.
4.  Enter a Proxy Name, and upload the `quickstart-openapi.yaml` file.
5.  Click **Create**. (This provisions the target endpoint mapping to
    `{ORG_NAME}.mcp.apigee.internal`).

### Step 3: Add a Security Policy

We strongly recommend securing the MCP endpoint. Add an access token
verification policy at the beginning of the **ProxyEndpoint PreFlow**: 1. In the
proxy editor, click **Develop** -> **Proxy endpoints** -> **default** ->
**PreFlow**. 2. Add a new **OAuth v2.0** policy named `VerifyAccessToken`. 3.
Ensure it executes the `<Operation>VerifyAccessToken</Operation>` task.

### Step 4: Deploy to a Comprehensive Environment

1.  Click **Deploy** in the proxy editor.
2.  Select your environment (Note: the environment must be a **Comprehensive**
    type, not Lite).
3.  Provide a deployment Service Account with `roles/apigee.admin` or
    `roles/apigee.deployer` permissions.
4.  Click **Deploy**. The status will change from *Provisioning* to *Deployed*.

### Step 5: Discovery in API Hub

Deploys are automatically ingested into **API Hub**: 1. Go to the **API Hub**
page in the console. 2. Filter the list by **Style: MCP**. Your proxy appears
here, with API operations automatically mapped to discoverable MCP tools.

--------------------------------------------------------------------------------

## 3. Interacting with the MCP Endpoint

Compliance clients can interact with your endpoint at
`https://{ENVIRONMENT_GROUP_HOSTNAME}/mcp` using standard HTTP POST JSON-RPC
payloads.

### A. Initialize the Server

Clients negotiate the protocol version using the `initialize` method:

**Request**

```bash
curl -X POST "https://api.cymbal.com/mcp" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_OAUTH_TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2025-11-25"
    }
  }'
```

**Response**

```json
{
  "id": 1,
  "jsonrpc": "2.0",
  "result": {
    "capabilities": {
      "tools": {
        "listChanged": false
      }
    },
    "protocolVersion": "2025-11-25",
    "serverInfo": {
      "name": "api.cymbal.com",
      "version": "1.0.0"
    }
  }
}
```

### B. List Tools

Retrieve the list of available tools matching the API operations:

**Request**

```bash
curl -X POST "https://api.cymbal.com/mcp" \
  -H "Content-Type: application/json" \
  -H "MCP-Protocol-Version: 2025-11-25" \
  -H "Authorization: Bearer YOUR_OAUTH_TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list",
    "params": {}
  }'
```

**Response**

```json
{
  "id": 2,
  "jsonrpc": "2.0",
  "result": {
    "tools": [
      {
        "name": "listProducts",
        "description": "Returns a list of available products",
        "inputSchema": {
          "type": "object",
          "properties": {}
        }
      }
    ]
  }
}
```
