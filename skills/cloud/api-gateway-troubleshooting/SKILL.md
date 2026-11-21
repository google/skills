---
name: api-gateway-troubleshooting
metadata:
  version: "1.0.0"
  category: Serverless
description: >-
  Diagnoses failing requests and deployment errors on Google Cloud API Gateway.
  Use when calls through a gateway return 4xx or 5xx errors, including 429 and
  other quota errors, time out, or fail a CORS preflight; when
  `api-configs create` fails with a service account, concurrency, or limit
  error, or `gateways create` or `gateways update` fails; when a custom domain,
  load balancer, or TLS finding involves a gateway; or when the user asks if
  Google is at fault. Don't use for Apigee, Cloud Endpoints, or GKE Gateway API.
  For OpenAPI errors from `api-configs create`, use
  api-gateway-openapi-spec-authoring; for setting up or changing API keys,
  JWTs, or quotas, use api-gateway-backend-security-and-rate-limiting; for MCP
  `/mcp` errors, use api-gateway-mcp-server.
---

# API Gateway Troubleshooting

Use this skill to find out why requests to a deployed Google Cloud API Gateway
fail and how to fix them. Work only from three sources of evidence:

1.  Public Google Cloud documentation, linked from this skill.
2.  The user's own project, read with the user's own credentials.
3.  Files and output that the user provides, such as an OpenAPI document, an
    error response, or a pasted log entry.

## Scope

This skill covers only Google Cloud API Gateway. If the question is about
Apigee, Cloud Endpoints, or GKE Gateway API, reply that this skill covers only
Google Cloud API Gateway, and don't run its steps or commands.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Ground rules

| Rule | Why |
| :--- | :--- |
| Stay read-only until the user approves a change. While you diagnose, run only `list`, `describe`, `get-iam-policy`, and `logging read` commands, plus `nslookup` and `curl` `GET` requests to a path that's safe to call. | Gateways serve production traffic, and the quota metrics and limits of the most recently created API config apply to every gateway of the API. |
| Before any change, show the exact command, what it changes, and how to undo it, then wait for an explicit yes. Changes include IAM grants, `api-configs create`, `gateways update`, Cloud Run ingress changes, and `gcloud services enable`. | The user owns the project and the change. |
| Never fix a `401` or `403` by making a backend public (`--allow-unauthenticated`, `--no-invoker-iam-check`, `allUsers`) or by granting a basic role such as Editor. | Grant the gateway's service account the invoker role on the one backend instead, which keeps least privilege. |
| Keep every log read bounded: filter on the gateway, set `--freshness` or a timestamp window, and set `--limit`. | Unbounded reads are slow and pull in caller data that the diagnosis doesn't need. |
| Redact API keys, bearer tokens, and JWTs before you show log entries, commands, or files. | Request logs and pasted output can contain credentials. |
| Base every limit, default, and error meaning on a linked public doc or on output from the user's project. If neither explains the problem, say so and escalate. | Guessing about undocumented behavior leads to wrong fixes. |
| Use the user's existing `gcloud` login. Never ask for passwords, API key values, or service account key files. | Credentials don't belong in a chat transcript. |
| For Preview features (streaming, MCP, model routing), check the [release notes](https://docs.cloud.google.com/api-gateway/docs/release-notes.md.txt) before answering. | Preview behavior changes between releases. |

## Prerequisites

1.  **Google Cloud CLI.** Use a recent `gcloud` (the commands here were
    checked with version 591.0.0); see
    [Install the gcloud CLI](https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt).
    Don't install or update software without the user's approval. If
    `gcloud` isn't available or the user says not to run commands, work in
    *evidence mode*: give the user the read-only commands to run, and diagnose
    from the output, response bodies, and log entries they paste.
2.  **Authentication.** Use the user's existing `gcloud auth login` session;
    this skill doesn't need application-default credentials.
3.  **Project.** Ask which project hosts the gateway and pass
    `--project={project_id}` on every command. Don't run `gcloud config set`,
    because it changes the user's environment. This skill troubleshoots
    existing gateways and never creates projects.
4.  **Billing.** The project needs an active billing account even when usage
    stays in the free tier; see
    [API Gateway pricing](https://cloud.google.com/api-gateway/pricing).
5.  **APIs.** API Gateway requires `apigateway.googleapis.com`,
    `servicemanagement.googleapis.com`, and `servicecontrol.googleapis.com`. A
    gateway can keep responding while one of them is missing, and its logs then
    stay empty, so check with
    `gcloud services list --enabled --project={project_id}`. Enabling a missing
    API is a change that needs approval.
6.  **IAM roles for diagnosis (read-only):** `roles/apigateway.viewer`,
    `roles/logging.viewer`, `roles/serviceusage.serviceUsageViewer`, and
    `roles/iam.serviceAccountViewer` (to check the gateway's service account).
    For Cloud Run backends, add `roles/run.viewer`; to trace a custom domain
    through its load balancer, add `roles/compute.viewer`; to check an API key's
    project, `roles/serviceusage.serviceUsageViewer` is also needed there.
7.  **IAM roles for fixes (only after approval):** `roles/apigateway.admin`;
    `roles/iam.serviceAccountUser` on the gateway's service account, because
    creating or updating an API config or a gateway requires
    `iam.serviceAccounts.actAs`;
    `roles/run.admin` to change a Cloud Run service's IAM policy or ingress;
    `roles/serviceusage.serviceUsageAdmin` to enable an API or a managed
    service, plus `roles/servicemanagement.serviceConsumer` on the API's
    managed service to enable it in another project; and
    `roles/iam.serviceAccountAdmin` to re-enable a disabled service account.
8.  **Region.** Gateways are regional. Use the region that
    `gateways list` reports. When a fix needs a new gateway, create it in the
    original gateway's region, or in `us-central1` if the user has no
    preference; see
    [API Gateway deployment model](https://docs.cloud.google.com/api-gateway/docs/deployment-model.md.txt)
    and [Cloud locations](https://cloud.google.com/about/locations).

## Workflow

Copy this checklist into your notes and tick it off as you go:

```
- [ ] 1. Context collected
- [ ] 2. Gateway identified by defaultHostname
- [ ] 3. Expected or transient states ruled out
- [ ] 4. Gateway log entry read (bounded query)
- [ ] 5. One branch chosen from the classification table
- [ ] 6. Root cause stated with redacted evidence and a doc link
- [ ] 7. Fix proposed, approved, and applied (or handed to the user)
- [ ] 8. Fix verified
- [ ] 9. Escalated, if the evidence points to Google Cloud
```

### 1. Collect context

Extract these from the conversation first, and ask only for what's missing:

| Needed | Why |
| :--- | :--- |
| `{project_id}` of the gateway | Every command is scoped to it. |
| Failing URL (host and path) or `{gateway_id}` and `{region}` | Identifies the gateway. |
| HTTP method, status code, and response body | Separates gateway errors from backend errors. |
| Approximate time of the failure, in UTC | Bounds the log query. |
| What changed recently (new API config, IAM, backend deploy, DNS) | Recent changes are the first place to look. |
| Authentication used by the caller (API key, JWT, none) | Selects the auth branch. |

If the project or the host is unknown, stop and ask before you run any
`gcloud` command. Don't guess project IDs, and don't use the active `gcloud`
project instead.

### 2. Identify the gateway

List the project's gateways:

```bash
gcloud api-gateway gateways list --project={project_id} \
  --format="table(name.basename():label=GATEWAY,name.segment(3):label=REGION,defaultHostname,state,apiConfig)"
```

Match the request host against `defaultHostname`. Don't decide from the URL
suffix: a gateway's hostname can use either of two `gateway.dev` formats or,
for older streaming and model-routing gateways, a `run.app` format. Don't
guess the owning project from numbers in the hostname either; list the
gateways in the project the user names. A custom domain points at a load
balancer whose serverless NEG targets the gateway. See
[references/triage-and-logs.md](references/triage-and-logs.md) for the
hostname formats and how to trace a custom domain.

If no gateway in the project matches, confirm the product before going on
(see [Scope](#scope)).

Then read the gateway's details, including its API config and streaming mode:

```bash
gcloud api-gateway gateways describe {gateway_id} \
  --location={region} --project={project_id}
```

### 3. Rule out expected and transient states

-   **Gateway `state` isn't `ACTIVE`:** `CREATING` or `UPDATING` means an
    operation is still running, so wait and check again. `FAILED` means
    creation failed; read the error of the failed operation. `DELETING` means
    the gateway is being removed.
-   **API config just created:** creating a complex API config can take up to
    ten minutes, and only one config can be created for an API at a time.
-   **First requests after an idle period:** API Gateway has cold-start
    latency.
-   **Google Cloud incident:** check the
    [Service Health dashboard](https://docs.cloud.google.com/service-health/docs/overview.md.txt).

### 4. Read the gateway log entry

Use a bounded query that prints only the fields you need. Replace
`{status_code}` with the status the caller saw:

```bash
gcloud logging read 'resource.type="apigateway.googleapis.com/Gateway" AND resource.labels.gateway_id="{gateway_id}" AND resource.labels.location="{region}" AND httpRequest.status={status_code}' \
  --project={project_id} --freshness=1h --limit=20 \
  --format="json(timestamp,httpRequest.status,httpRequest.latency,httpRequest.requestUrl,jsonPayload.responseDetails,jsonPayload.apiConfig,jsonPayload.apiMethod)"
```

If you know the failure time, replace `--freshness` with a
`timestamp>="{start_utc}" AND timestamp<="{end_utc}"` filter that spans about
30 minutes around it. Read `httpRequest.status`, `httpRequest.requestUrl`,
`jsonPayload.responseDetails`, `jsonPayload.apiConfig`, and
`jsonPayload.apiMethod`. Keep the `--format` field list, because a full entry
can contain the caller's credentials, and redact credentials before you quote
any field, including a `key` query parameter in `httpRequest.requestUrl`.

To compare API configs, compare only the `apis/{api_id}/configs/{config_id}`
part: the same config can appear as a full resource name
(`//apigateway.googleapis.com/projects/...`) and with either the project
number or the project ID.

`jsonPayload.responseDetails` decides the branch: `via_upstream` means the
backend produced the response; any other value means the gateway produced it.
The troubleshooting page explains `via_upstream` and
`service_control_quota_error`, and the model routing page explains the
`model_router_*` values that model-routing gateways log. Quote any other value
as-is, and don't explain how the gateway works internally.

### 5. Classify and follow one branch

Pick the first row that matches, and load only the reference file it names.

| What you see | Likely cause | Reference |
| :--- | :--- | :--- |
| `401` or `403` with `via_upstream` | The backend rejected the gateway: invoker role, audience, or deleted service account | [auth-errors.md](references/auth-errors.md) |
| A `4xx` produced by the gateway whose body names a credential problem (for example `UNAUTHENTICATED`) | The API key or JWT was rejected; quote the body | [auth-errors.md](references/auth-errors.md) |
| `500` with **no** gateway log entry, after log exclusions and a wrong scope are ruled out | The gateway's service account may be deleted or disabled | [auth-errors.md](references/auth-errors.md) |
| `500` with `service_control_quota_error` | Quota metric missing from the newest API config | [config-deployment-errors.md](references/config-deployment-errors.md) |
| `429` with `service_control_quota_error` | The caller exceeded the API's quota | [limits-and-escalation.md](references/limits-and-escalation.md) |
| `404`, `502`, `503`, or `504`, an oversized request, or a timeout | Routing, backend errors, size limits, or the deadline. The docs don't name the status codes for size or deadline failures, so confirm with `responseDetails` and the body. | [backend-routing-and-timeouts.md](references/backend-routing-and-timeouts.md) |
| CORS preflight fails or latency is high | CORS pass-through or slow backend | [backend-routing-and-timeouts.md](references/backend-routing-and-timeouts.md) |
| `api-configs create` fails with an error about the OpenAPI document, such as an unsupported extension or an invalid path, parameter, server, or security requirement | A spec problem | Hand off to `api-gateway-openapi-spec-authoring`; if it isn't installed, see [OpenAPI pre-flight check](#openapi-pre-flight-check) |
| `api-configs create` fails with a service account, concurrency, or limit error, or `gateways create` or `gateways update` fails | Service account, concurrent creates, limits, or the backend deadline | [config-deployment-errors.md](references/config-deployment-errors.md) |
| `400` "The request was malformed" from an old TLS client, TLS scan findings, custom domain, or no log entry at all | TLS enforcement, DNS, load balancer, or wrong host | [networking-domains-tls.md](references/networking-domains-tls.md) |
| Errors on several gateways, or on an unchanged config, with healthy backends | Possible Google Cloud issue | [limits-and-escalation.md](references/limits-and-escalation.md) |

If the request also needs log queries or backend inspection commands, use
[triage-and-logs.md](references/triage-and-logs.md).

### 6. State the root cause

Give the cause, the evidence (redacted, quoted verbatim from logs or command
output), and the public doc section that explains it. If the evidence fits
more than one cause, list at most three, say what would tell them apart, and
collect that evidence before proposing a fix.

### 7. Propose the fix

Show the exact command, the resource it changes, its effect on live traffic,
and how to undo it. Wait for approval, then run it, or hand it to the user if
they prefer. Keep these rules in mind:

-   To change the OpenAPI document, create a new API config and deploy it with
    `gcloud api-gateway gateways update`. Before you create the config, check
    quota metrics with the `api-gateway-backend-security-and-rate-limiting`
    skill, because the newest API config's quota metrics apply to every
    gateway of the API.
-   Before you create a new API config, check the OpenAPI document with the
    linter (see [OpenAPI pre-flight check](#openapi-pre-flight-check)).

### 8. Verify

Read the logs again for new entries after the change, or repeat the failing
request. Repeat a request yourself only if it's safe to repeat, such as a
`GET`; otherwise ask the user to repeat it, because a repeated `POST` can
change data in their backend. After `gateways update`, wait until the
gateway's `state` is `ACTIVE` before you test.

### 9. Escalate when the evidence points to Google Cloud

Escalate to [Cloud Customer Care](https://cloud.google.com/support) when the
service account is active, the required APIs are enabled, and no log exclusion
or wrong scope explains it, but requests get `500` errors with no gateway log
entry; when several gateways fail at once without a config change; when errors
are intermittent on an unchanged config while the backend logs stay clean;
when control-plane operations keep failing with internal errors; or when
Service Health reports an incident. Draft the case text with the evidence
bundle in [limits-and-escalation.md](references/limits-and-escalation.md). The
user files the case.

## OpenAPI pre-flight check

Run the linter on every OpenAPI file before creating an API config. Run it;
don't read its source. If you don't have the file, give the user the command
to run:

```bash
python3 scripts/lint_openapi_for_gateway.py {spec_path} [{spec_path} ...]
```

It reads the files only, makes no network calls, and prints JSON findings that
each link to the public doc for the limitation. Exit code `0` means no errors,
`1` means at least one `ERROR` finding, and `2` means a usage, parse, or
dependency error. The linter needs Python 3.8 or later. YAML input needs
PyYAML; ask the user before you install it with
`pip install "PyYAML>=6.0,<7.0"`. JSON input doesn't. Fix the `ERROR`
findings, and then create the API config. If `api-configs create` still fails
on the OpenAPI document, hand off to `api-gateway-openapi-spec-authoring`, or
use the error message if that skill isn't installed. Show `WARNING` findings
to the user and explain them.

## Output format

Report findings in this form:

```
**Problem:** <one sentence in the user's terms>
**Failed hop:** <gateway or backend, and the evidence for it>
**Evidence:** <redacted log fields or command output, verbatim>
**Root cause:** <one or two sentences> (<public doc link>)
**Fix:** <exact command or spec change; approval needed: yes/no>
**Verify:** <how to confirm the fix>
**Open questions:** <anything you couldn't confirm>
```

## Related skills

| Need | Skill |
| :--- | :--- |
| Write or change API key, JWT, backend authentication, or quota configuration | `api-gateway-backend-security-and-rate-limiting` |
| Write, migrate, or fix an OpenAPI spec, including OpenAPI errors from `api-configs create` | `api-gateway-openapi-spec-authoring` |
| MCP `/mcp` JSON-RPC errors on an MCP-enabled gateway | `api-gateway-mcp-server` |
| Deep IAM analysis, such as deny policies or role discovery | `iam-helper-for-troubleshooting` |
| Build a load balancer, Cloud Armor policy, or custom domain front end | `google-cloud-global-frontend-configuration` |
| Deploy or reconfigure a Cloud Run backend | `cloud-run-basics` |

## Reference files

-   [references/attribution.md](references/attribution.md): usage attribution
    rules for every command you run.
-   [references/triage-and-logs.md](references/triage-and-logs.md): hostname
    formats, log queries, log fields, metrics, and backend inspection
    commands.
-   [references/auth-errors.md](references/auth-errors.md): `401` and `403` on
    either hop, API keys, JWTs, and the gateway service account.
-   [references/backend-routing-and-timeouts.md](references/backend-routing-and-timeouts.md):
    `404`, size limits, backend `5xx`, `504` and deadlines, CORS, and streaming.
-   [references/config-deployment-errors.md](references/config-deployment-errors.md):
    API config and gateway create, update, and delete failures other than
    OpenAPI errors, and quota metric conflicts.
-   [references/networking-domains-tls.md](references/networking-domains-tls.md):
    custom domains, load balancers, TLS, and requests that never reach the
    gateway.
-   [references/limits-and-escalation.md](references/limits-and-escalation.md):
    product limits, quota increases, unsupported features, and the Cloud
    Customer Care evidence bundle.
-   [scripts/lint_openapi_for_gateway.py](scripts/lint_openapi_for_gateway.py):
    offline linter for documented OpenAPI limitations.
