# Agent Gateway IAM Conditions & CEL References

Use these Common Expression Language (CEL) templates when writing `iap-policy.json` conditions for Agent Gateway to control what tools an agent can call.

### 1. Restrict to Read-Only Tools
Blocks an Agent from calling any tool marked as write-capable in the Agent Registry.

```json
{
  "condition": {
    "title": "Read-only access",
    "description": "Allows Agent access to any tool as long as the attribute is read-only",
    "expression": "api.getAttribute('iap.googleapis.com/mcp.tool.isReadOnly', false) == true"
  }
}
```

### 2. Restrict to Specific Tool Name
Limits access exclusively to a trusted target tool.

```json
{
  "condition": {
    "title": "Restricted to Calendar",
    "expression": "api.getAttribute('iap.googleapis.com/mcp.toolName', '') == 'MyCalendarTool'"
  }
}
```
