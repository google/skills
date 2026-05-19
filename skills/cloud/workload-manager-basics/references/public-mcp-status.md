# Workload Manager Public MCP Status

No public Workload Manager MCP server is currently documented. Do not write
examples that imply Workload Manager has a public MCP integration.

Use the public SDK or REST API for production workflows.

## Current Recommendation

```mermaid
flowchart LR
    Request["User request"] --> Check["Need Workload Manager resource?"]
    Check --> SDK["Use Python or Go SDK for evaluations"]
    Check --> REST["Use REST for uncovered resources"]
    SDK --> Verify["Verify operation and findings"]
    REST --> Verify
```

## Safety Rules

- Require a project, location, evaluation ID, and explicit resource scope for
  mutating operations.
- Default list operations to read-only roles.
- Require confirmation before deleting evaluations or executions.
- Surface BigQuery export destinations and CMEK key names before creating or
  updating evaluations.
