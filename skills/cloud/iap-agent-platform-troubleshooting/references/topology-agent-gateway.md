# Topology: Agent Runtime with Agent Gateway

This skill supports one topology: an Agent Runtime (Reasoning Engine) agent that
runs with agent identity and sends outbound requests through Agent Gateway,
where IAP for agents makes the authorization decision through an authorization
extension.

## Contents

- [Request path](#request-path): Lines 23-35
- [Agent principal](#agent-principal): Lines 37-68
- [Agent log query](#agent-log-query): Lines 70-102
- [403 errors during startup](#403-errors-during-startup): Lines 104-128
- [Resource names](#resource-names): Lines 130-142
- [Unsupported topologies](#unsupported-topologies): Lines 144-151

Sources:
[Troubleshoot Agent Gateway](https://docs.cloud.google.com/gemini-enterprise-agent-platform/troubleshooting/troubleshoot-agent-gateway.md.txt),
[Use Agent Identity with Agent Runtime](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-identity.md.txt),
[Configure IAM Unified Access Policies](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/policies/configure-iam-policies-uap.md.txt),
[IAP roles and permissions](https://docs.cloud.google.com/iam/docs/roles-permissions/iap.md.txt).

## Request path

Agent Runtime agent -> Agent Gateway -> authorization policy -> authorization
extension (`iap.googleapis.com`) -> IAP evaluates Access policies (V2) or IAP
allow policies (V1) -> destination.

Egress is default-deny. A request succeeds only if every layer allows it: the
agent identity has the IAP `egressViaIAP` permission on the destination
(directly or through a principal set), an authorization policy targets the
gateway, and every other authorization engine on the gateway allows the
request. Access policies (V2) check `iap.resources.egressViaIAP`. IAP allow
policies (V1) check `iap.webServiceVersions.egressViaIAP`, which
`roles/iap.egressor` grants.

## Agent principal

```text
principal://agents.global.org-{org_id}.system.id.goog/resources/aiplatform/projects/{project_number}/locations/{location}/reasoningEngines/{engine_id}
```

-   A project without an organization uses the trust domain
    `agents.global.proj-{project_number}.system.id.goog`.
-   The path contains the project number, not the project ID.
-   Copy the value from `protoPayload.authenticationInfo.principalSubject` in
    the IAP audit entry instead of building it by hand. The field can also
    hold the agent's SPIFFE ID. IAM policies take the `principal://`
    identifier instead, so in that case fill in the format above with values
    from command output.
-   Identifiers in URN format (`urn:agent:...`) are used only for inventory and
    catalog lookup. IAM policies never use them.
-   An agent deployed without agent identity runs as a service account. That
    case is outside this skill's topology; say so.

Principal sets for groups of Agent Runtime agents:

| Scope | Principal set |
| :--- | :--- |
| All agents in a project (organization) | `principalSet://agents.global.org-{org_id}.system.id.goog/attribute.platformContainer/aiplatform/projects/{project_number}` |
| All agents in a project (no organization) | `principalSet://agents.global.proj-{project_number}.system.id.goog/attribute.platformContainer/aiplatform/projects/{project_number}` |
| All Agent Runtime agents in the organization | `principalSet://agents.global.org-{org_id}.system.id.goog/attribute.platform/aiplatform` |

A rule that uses a principal set can still miss the agent. A newly added
identity can take a few minutes to be recognized as a member, and an identity
that lacks the attributes that the set requires can be silently excluded. To
test, the user grants the agent's exact `principal://` identifier directly. If
that works, the cause is the principal set.

## Agent log query

Confirm the error text in the agent's own logs:

```bash
gcloud logging read '
  resource.type="aiplatform.googleapis.com/ReasoningEngine"
  resource.labels.location="{location}"
  resource.labels.reasoning_engine_id="{engine_id}"
  textPayload:"403"' \
  --project={project_id} --freshness=1d --limit=20
```

-   `Egress request is not authorized` in `textPayload` means Agent Gateway
    rejected the egress request. The full message looks like this:

    ```text
    {"code": 403, "message": "403 Forbidden. {'message': 'Egress request is not authorized.', 'status': 'Forbidden'}"}
    ```

    A `streamQuery` call returns the same denial as a stream event. When the
    agent's model call is denied, this event arrives before any tool runs:

    ```text
    {"errorCode": "PERMISSION_DENIED", "errorMessage": "Egress request is not authorized. If Identity-Aware Proxy (IAP) or Agent Gateway egress security is enabled, verify your IAM bindings ..."}
    ```

-   A 403 with any other text might mean that the destination rejected the
    call directly, rather than Agent Gateway. Check the gateway 403 query in
    [gateway-setup.md](gateway-setup.md) before you call it out of scope.

-   Set `--freshness` to cover the time of the failure, for example
    `--freshness=7d` for an older incident.

## 403 errors during startup

When IAP enforces, it also blocks calls that the agent makes to Google services
at startup, unless those hostnames are registered and the agent has the IAP
`egressViaIAP` permission on them. Find the blocked hostnames with the
gateway 403 query in [gateway-setup.md](gateway-setup.md), without the
location, gateway name, and CONNECT lines. Hostnames that commonly need
registration:

-   `https://{location}-aiplatform.mtls.googleapis.com` (Agent Runtime and
    Sessions)
-   `https://cloudresourcemanager.mtls.googleapis.com` and
    `https://cloudresourcemanager.mtls.googleapis.com/`
-   `https://telemetry.mtls.googleapis.com/` (if Google Cloud Observability is
    on)
-   `https://logging.googleapis.com/` (if Cloud Logging is on)
-   `https://monitoring.googleapis.com/` and `https://monitoring.mtls.googleapis.com/`
-   `https://cloudtrace.googleapis.com/` and `https://cloudtrace.mtls.googleapis.com/`
-   `https://secretmanager.googleapis.com/` and
    `https://secretmanager.mtls.googleapis.com/`

Startup errors such as `Failed to convert project number to project ID` in the
`aiplatform.googleapis.com/reasoning_engine_stderr` log aren't IAP denials. They
mean the agent identity lacks basic roles. Route them to
`agent-platform-troubleshooting`.

## Resource names

| Resource | Name format |
| :--- | :--- |
| Agent Gateway | `projects/{project_id}/locations/{location}/agentGateways/{gateway}` |
| Authorization extension | `projects/{project_id}/locations/{location}/authzExtensions/{authz_extension}` |
| Agent Registry instance | `//agentregistry.googleapis.com/projects/{project_id}/locations/{registry_location}` |
| Policy binding target (project) | `//cloudresourcemanager.googleapis.com/projects/{project_number}` |
| Policy binding target (gateway) | `//networkservices.googleapis.com/projects/{project_id}/locations/{location}/agentGateways/{gateway}` |

Agent Runtime agents are regional and are usually registered in a regional
registry in their deployment region. An agent in another project must be
registered in the registry of the project where Agent Gateway runs.

## Unsupported topologies

Gemini Enterprise agents, Cloud Run agents, agents that use Workload Identity
Federation principals, and agents that don't send traffic through Agent Gateway
aren't covered yet. Say that the topology isn't supported, and for general Agent
Platform troubleshooting name `agent-platform-troubleshooting`. Don't adapt this
skill's log filters or principal formats to them, because they differ by
platform.
