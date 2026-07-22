# IAM & IAP CEL Conditions Reference

Common Expression Language (CEL) conditions allow fine-grained access authorization for Agent Identities (SPIFFE) interacting with Agent Gateways and MCP tool endpoints.

---

## 1. CEL Condition Patterns

### Allow Read-Only MCP Tools Only
```json
{
  "title": "allow_readonly_tools_only",
  "description": "Restricts agent calls to MCP tools tagged as read-only",
  "expression": "resource.labels.access_tier == 'readonly' || request.path.endsWith('/read') || request.path.endsWith('/get')"
}
```

### Restrict Access by Agent Environment
```json
{
  "title": "prod_agent_identity_match",
  "description": "Ensures only production agents access production tool endpoints",
  "expression": "request.auth.principal.labels.environment == 'prod' && resource.labels.environment == 'prod'"
}
```

### Time-Bound & Working Hours Restriction
```json
{
  "title": "business_hours_only",
  "description": "Allows agent operations only during UTC business hours",
  "expression": "request.time.getHours('Etc/UTC') >= 8 && request.time.getHours('Etc/UTC') < 18"
}
```

---

## 2. Setting IAM Policy with Conditions (Tier M)

1. **Export existing policy:**
   ```bash
   gcloud iap web get-iam-policy \
       --resource-type=AgentRegistryResource \
       --project=$PROJECT_ID --format=json > iap-policy.json
   ```

2. **Apply updated policy:**
   ```bash
   gcloud iap web set-iam-policy iap-policy.json \
       --resource-type=AgentRegistryResource \
       --project=$PROJECT_ID
   ```
