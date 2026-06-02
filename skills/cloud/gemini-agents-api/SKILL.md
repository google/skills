---
name: gemini-agents-api
description: Manages custom Agent resources on Gemini Enterprise Agent Platform. Use when the user wants to programmatically create, configure, list, update, or delete stateful, server-managed Agent resources (including mounting files, skills, and tools) before executing conversations.
---

# Gemini Enterprise Agent Platform - Managed Agents API Skill

This skill provides complete instructions, REST request endpoints, and JSON payload structures to programmatically manage **custom Agent resources** on the Gemini Enterprise Agent Platform (Agent Platform).

The **Managed Agents API** forms the **Control Plane** of the platform. It allows developers to provision, retrieve, update, and delete tailored, stateful agent containers equipped with system instructions, sandboxed files, custom skill registries, and local/remote tools.
---

## 1. Authentication & Setup

All REST requests to the Control Plane must include a Bearer token derived from Application Default Credentials (ADC), and target the production global endpoint.

### 1. Setup Environment Variables

Before running requests, set up the required project variables and access token:

```bash
export PROJECT_ID="your-project-id"
export LOCATION="global"
export ACCESS_TOKEN=$(gcloud auth print-access-token)
```

> [!IMPORTANT]
> **API Location Support**:
> The `LOCATION` environment variable must be set to a regional location where the Gemini Enterprise Agent Platform's **Managed Agents API** is actively supported (e.g., `global`, or other available regional endpoints).


### 2. Endpoint URL

The production Agents Control Plane endpoint is:
```http
https://aiplatform.googleapis.com/v1beta1/projects/{PROJECT_ID}/locations/{LOCATION}/agents
```

---

## 2. Programmatic Agent Management (Control Plane CRUD)

### 1. Create Agent (Long-Running Operation)

To create a new agent resource, issue a `POST` request with the custom configuration. You can mount remote files, folders, or skills directly from **Google Cloud Storage** buckets into the agent container's workspace. Creating an agent is a Long-Running Operation (LRO) that spawns an asynchronous job.

*   **Method**: `POST`
*   **Endpoint**: `https://aiplatform.googleapis.com/v1beta1/projects/${PROJECT_ID}/locations/${LOCATION}/agents`

#### Request Payload

```bash
curl -X POST "https://aiplatform.googleapis.com/v1beta1/projects/${PROJECT_ID}/locations/${LOCATION}/agents" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{
    "id": "my-custom-agent",
    "base_agent": "antigravity-preview-05-2026",
    "description": "A professional agent configured with remote tools and mounted Cloud Storage directories.",
    "system_instruction": "You are a helpful, domain-expert assistant.",
    "tools": [
      {"type": "code_execution"},
      {"type": "filesystem"},
      {"type": "google_search"},
      {"type": "url_context"}
    ],
    "base_environment": {
      "type": "remote",
      "sources": [
        {
          "type": "gcs",
          "source": "gs://your-agent-bucket-name/skills",
          "target": "/.agent/skills"
        }
      ],
      "network": {
        "allowlist": [
          { "domain": "*" }
        ]
      }
    }
  }'
```

#### LRO Operations Response

Since agent provisioning takes a few moments, the endpoint immediately returns an operation tracking object:
```json
{
  "name": "projects/1234567890/locations/global/operations/operation-987654321-abcde",
  "metadata": {
    "@type": "type.googleapis.com/google.cloud.aiplatform.v1beta1.CreateAgentOperationMetadata",
    "genericMetadata": {
      "createTime": "2026-05-14T19:00:00.123456Z",
      "updateTime": "2026-05-14T19:00:01.654321Z"
    }
  }
}
```

#### [Advanced] Mount Skill Registry Resources

To mount skills directly from the Skill Registry service instead of Cloud Storage, replace the Cloud Storage source item in the payload:
```json
"sources": [
  {
    "type": "skill_registry",
    "source": "projects/your-project-id/locations/global/skills/my-math-skill/revisions/123456789012",
    "target": "/.agent/skills"
  }
]
```

#### [Advanced] Configuring Model Context Protocol (MCP) Servers

To configure Third-Party MCP servers for an agent, add the server metadata directly under the `"tools"` parameter array inside the creation request. The platform securely routes tool execution requests to the external MCP server.

```json
"tools": [
  {
    "type": "mcp",
    "name": "my-mcp-server",
    "url": "https://mcp.yourcompany.com/api",
    "headers": {
      "Authorization": "Bearer YOUR_MCP_AUTH_TOKEN"
    }
  }
]
```
*   **name**: A descriptive name for the MCP server.
*   **url**: The endpoint URL of the external MCP server.
*   **headers**: (Optional) Custom key-value pairs containing authentication tokens (e.g. API keys, bearer tokens) required to call the server. The platform guarantees that these headers are only sent to the specified MCP server URL.

> [!TIP]
> **Overriding MCP at Interaction Time (Data Plane)**:
> You can dynamically override or supply MCP tools directly when creating a conversation interaction (Data Plane) by passing `"type": "mcp_server"` inside the `"tools"` payload of `interactions.create`. Refer to the Interactions API documentation for details.

---

### 2. Polling the LRO Status

To track the status of agent creation and obtain the final ready resource, poll the operation URL returned in the `name` field of the creation response.

*   **Method**: `GET`
*   **Endpoint**: `https://aiplatform.googleapis.com/v1beta1/{OPERATION_NAME}`

```bash
curl -X GET "https://aiplatform.googleapis.com/v1beta1/projects/1234567890/locations/global/operations/operation-987654321-abcde" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json"
```

#### In-Progress Response

```json
{
  "name": "projects/1234567890/locations/global/operations/operation-987654321-abcde",
  "metadata": { ... }
}
```

#### Finished Success Response

Once the container is ready, `"done": true` is set, and the completed `Agent` resource description resides inside `"response"`:
```json
{
  "name": "projects/1234567890/locations/global/operations/operation-987654321-abcde",
  "done": true,
  "response": {
    "@type": "type.googleapis.com/google.cloud.aiplatform.v1beta1.Agent",
    "name": "projects/your-project-id/locations/global/agents/my-custom-agent",
    "base_agent": "antigravity-preview-05-2026",
    "description": "A professional agent configured with remote tools and mounted Cloud Storage directories.",
    "system_instruction": "You are a helpful, domain-expert assistant."
  }
}
```

---

### 3. Get Agent

Retrieve the configuration metadata, tools, and environment setup of an existing custom agent.

*   **Method**: `GET`
*   **Endpoint**: `https://aiplatform.googleapis.com/v1beta1/projects/${PROJECT_ID}/locations/${LOCATION}/agents/{AGENT_ID}`

```bash
curl -X GET "https://aiplatform.googleapis.com/v1beta1/projects/${PROJECT_ID}/locations/global/agents/my-custom-agent" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json"
```

#### Response Example
Returns the complete configured state of the custom Agent resource:
```json
{
  "name": "projects/your-project-id/locations/global/agents/my-custom-agent",
  "base_agent": "antigravity-preview-05-2026",
  "description": "A professional agent configured with remote tools and mounted Cloud Storage directories.",
  "system_instruction": "You are a helpful, domain-expert assistant.",
  "tools": [
    {"type": "code_execution"},
    {"type": "filesystem"},
    {"type": "google_search"},
    {"type": "url_context"}
  ],
  "base_environment": {
    "type": "remote",
    "sources": [
      {
        "type": "gcs",
        "source": "gs://your-agent-bucket-name/skills",
        "target": "/.agent/skills"
      }
    ],
    "network": {
      "allowlist": [
        { "domain": "*" }
      ]
    }
  }
}
```

---

### 4. List Agents

Retrieve a list of all configured custom agents located under the target Google Cloud project.

*   **Method**: `GET`
*   **Endpoint**: `https://aiplatform.googleapis.com/v1beta1/projects/${PROJECT_ID}/locations/${LOCATION}/agents`

```bash
curl -X GET "https://aiplatform.googleapis.com/v1beta1/projects/${PROJECT_ID}/locations/global/agents" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json"
```

#### Response Example
Returns a JSON list of all configured custom Agents under the target project:
```json
{
  "agents": [
    {
      "name": "projects/your-project-id/locations/global/agents/my-custom-agent",
      "base_agent": "antigravity-preview-05-2026",
      "description": "A professional agent configured with remote tools and mounted Cloud Storage directories.",
      "system_instruction": "You are a helpful, domain-expert assistant."
    },
    {
      "name": "projects/your-project-id/locations/global/agents/my-telecom-agent",
      "base_agent": "antigravity-preview-05-2026",
      "description": "A highly specialized telecom support agent.",
      "system_instruction": "You are a professional telecom support agent. Follow system policies carefully."
    }
  ]
}
```

---

### 5. Update Agent (Patching Configuration)

Modify configuration fields (such as instructions, descriptions, tools, or mounts) on a custom agent resource in place. You **must** specify the fields being updated using the `update_mask` query parameter.

*   **Method**: `PATCH`
*   **Endpoint**: `https://aiplatform.googleapis.com/v1beta1/projects/${PROJECT_ID}/locations/${LOCATION}/agents/{AGENT_ID}?update_mask=system_instruction`

```bash
curl -X PATCH "https://aiplatform.googleapis.com/v1beta1/projects/${PROJECT_ID}/locations/global/agents/my-custom-agent?update_mask=system_instruction" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-custom-agent",
    "system_instruction": "You are a highly specialized telecom support agent. Follow system policies carefully."
  }'
```

---

### 6. Delete Agent

Delete custom Agent resources when they are no longer needed to free up backend workspace containers.

*   **Method**: `DELETE`
*   **Endpoint**: `https://aiplatform.googleapis.com/v1beta1/projects/${PROJECT_ID}/locations/${LOCATION}/agents/{AGENT_ID}`

```bash
curl -X DELETE "https://aiplatform.googleapis.com/v1beta1/projects/${PROJECT_ID}/locations/global/agents/my-custom-agent" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}"
```

#### Response Example
A successful deletion request returns an empty JSON response body with HTTP Status `200 OK`:
```json
{}
```

---

## 3. Interacting with Custom Agents (Data Plane)

Once you have programmatically created and provisioned your custom stateful agent using the **Control Plane** (this skill), you can execute multi-turn chat, tool execution, and streaming conversations with it using the **Data Plane** (**Interactions API**).

To interact with your custom agent:
1.  Obtain your agent's resource path name (e.g., `projects/{PROJECT_ID}/locations/global/agents/{AGENT_ID}`).
2.  Pass this resource path directly inside your data plane conversation requests under the **`agent`** parameter.

#### Python Example
```python
interaction = client.interactions.create(
    agent="projects/your-project-id/locations/global/agents/my-custom-agent",
    input="Hello! Who are you?"
)
```

#### REST / curl Example
```json
{
  "agent": "projects/your-project-id/locations/global/agents/my-custom-agent",
  "input": [{
    "role": "user",
    "content": [{"type": "text", "text": "Hello! Who are you?"}]
  }]
}
```

Refer to the **`gemini-interactions-api`** skill guide (`../gemini-interactions-api/SKILL.md`) for full instructions, Python and TS/JS code blocks, and streaming setups to run conversations with your provisioned agents.

