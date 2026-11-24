---
name: apigee-agent-gateway-governance
metadata:
  version: "1.0.3"
  category: AiAndMachineLearning
description: >-
  Stands up an Apigee API proxy that a Google Cloud Agent Gateway calls as an
  ext-proc (Service Extension) callout on an agent's LLM traffic, to meter
  token usage per model, extract caller identity, and apply Model Armor prompt
  screening or a semantic cache. Use when wiring Apigee in as an AI gateway
  behind an Agent Gateway, when an agent's model egress needs governing, or
  when a callout proxy returns no verdict and you need to find out why. The
  distinguishing question is whether Apigee forwards the traffic or only
  inspects it: this skill is inspect-only, and builds the proxy itself. Don't
  use it when Apigee is meant to receive a request and route it onward to a
  backend — including hosting an MCP server behind Apigee — which needs a proxy
  with a target instead. Don't use for governing the agent's calls to tools or
  MCP servers. Don't use for choosing or switching which model a request goes
  to. Don't use for creating the Agent Gateway itself, nor for Apigee hybrid.
---

# Apigee as an Agent Gateway Service Extension

Wires an Apigee proxy in as an **ext-proc callout** on a GCP Agent Gateway. The
proxy is a **processor, not an API proxy**: it has no backend, inspects the LLM
request and response the gateway hands it, and returns a verdict.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

You build the proxy; the user does not.

**Two modes, one schema. Decide which before anything else, and say which.**
Input file present → **prod mode**: it is the contract, every value comes from
it, and a missing or malformed field is a refusal, not a default. No input file
and the user is describing an outcome → **dev mode**: apply the documented
defaults, show a plan with durations and get approval, start with identity and
metering only, write `apigee-agent-gateway-governance.yaml` at the end as the
handoff. `assets/apigee-agent-gateway-governance.example.yaml` documents the
schema both modes use.

Modes, defaults, durations, cost disclosure and the interlocks that bind both:
`references/modes.md`. **Read it before you start.**

**Colour the plan's ACTION column** — green `REUSE`, cyan `CREATE`/`RESERVE`,
yellow `APPEND`/`MODIFY`; full palette in `references/modes.md`. Yellow is the
one that earns its place: it is the only signal that a resource the user already
owns is being changed. Rendered plain, the one row that modifies something is
indistinguishable from the dozen that do not — which is exactly the row the
approval exists for.

## Prerequisite: where the agent runs

Check this **before** building anything. It decides whether traffic can reach
the gateway at all, and it is silent when wrong — every step below still
succeeds while nothing arrives.

**Use Agent Runtime**, created with `agent_gateway_config` /
`agent_to_anywhere_config`. It is the supported path and the orchestrator builds
the client-side PSC, routing, DNS and cert trust for you. There is no `gcloud`
surface for this and no console path — it is SDK-only, at agent creation time.
See
[Route traffic through Agent Gateway](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/agent-gateway-runtime-deploy.md.txt)
for the binding, and `references/networking-psc.md` for a worked example.

**Set `GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES: "False"` in the
agent's `env_vars`, or every invocation 401s** on the agent's own
`sessions.create`, before user code runs. Deploy-time invisible. Full symptom
and isolation: `references/gotchas.md`, Agent Gateway.

Where the agent runs is otherwise settled — the premise is a working gateway and
a working agent. Do not explain how to build one or list unsupported compute
unprompted; `references/networking-psc.md` has the constraints if it turns out
to matter.

## Tool versions

Do not assume these are installed or current.

Tool                                         | Minimum     | Why
-------------------------------------------- | ----------- | ---
`gcloud`                                     | **588.0.0** | `apigee apis import --from-template` is on the GA track at this version; older SDKs need `gcloud beta`
`google-cloud-aiplatform[agent_engines,adk]` | `>=2.1,<3`  | Agent Runtime client used to bind the agent to the gateway
`google-adk`                                 | `>=2.9,<3`  | only if you build the test agent with ADK

**On gcloud >= 588.0.0: every feature must keep its `uid`, and the template must
never declare `endpoints` or `targets`.** All six features set `uid` today and
the template declares neither, so the shipped bundle is correct — but both are
load-bearing now, and breaking either one still compiles, still deploys, and
reports nothing. Mechanism and symptoms: `references/gotchas.md`, under
Authoring (AFT).

```bash
gcloud version | head -1          # confirm >= 588.0.0
gcloud components update          # if older
pip install "google-cloud-aiplatform[agent_engines,adk]>=2.1,<3" "google-adk>=2.9,<3"
```

`scripts/compile_check.py` needs PyYAML and names the interpreter if it is
missing. `pip install pyyaml`, or run it with a Python 3 that has it; gcloud's
bundled interpreter does not, and the SDK's vendored `yaml` is Python 2.

```bash
python3 scripts/compile_check.py assets/apigee-proxy-template.yaml
```

## Execution model

Three layers, and the choice between them is not stylistic:

Layer                 | Used for                                               | Why
--------------------- | ------------------------------------------------------ | ---
**AFT YAML template** | the proxy itself                                       | version-controlled, reviewable, diffable
**`gcloud`**          | PSC, DNS, AuthzExtension, AuthzPolicy                  | native commands exist
**REST (`curl`)**     | env properties, envgroups, deployments, debug sessions | no `gcloud` equivalent today

The customer owns **one** input file
(`assets/apigee-agent-gateway-governance.example.yaml`). It is the
version-controlled artifact. Never hand-edit the generated proxy: regenerate it.

**Run the Apigee-side sequence with the script, not by hand.** Steps 1, 3 and 4
below are order-dependent and each fails in a way that reads as a different
problem. `scripts/deploy_proxy.sh` does all three, preserves the properties
map, polls the async operation, and exits non-zero if the deployment does not
come up `EXTENSIBLE`:

```bash
scripts/deploy_proxy.sh --org "$ORG" --env "$ENV" --proxy "$PROXY" \
  --template assets/apigee-proxy-template.yaml [--service-account "$SA"] --yes \
  [--index-endpoint-id ID --index-id ID --sc-project P --sc-region R --embeddings-model M]
```

Run it without `--yes` first: it prints the plan and changes nothing. Show that
plan, then re-run with `--yes` once the user agrees.

**The vector-search flags are the one exception to "edit the default in every
feature that declares it".** Those three ids are substituted at deploy time
and checked for leftovers; hand-editing them into `feature-semantic-cache.yaml`
deploys fine, skips the check, and makes the file single-use.

`scripts/ensure_gateway_connectivity.sh` is the same idea for the gateway leg
(step 0). It is the only part of this skill that modifies a resource the user
already owns, so it applies nothing without `--yes`.

The steps are written out below so you can diagnose a failure, not so you can
retype them.

## Inputs you must resolve first

**Environment prerequisites: `references/setup.md`** — gcloud SDK (588+),
project, billing, `gcloud services enable`, region, credentials, IAM. Nothing
below creates any of it.

Prod: from the input file, then environment, then ask — never invent. Dev: apply
the `references/modes.md` defaults, and ask only for what has none.

-   `project`, `region`
-   `apigee.org`, `apigee.environment`, `apigee.envgroup`, `apigee.hostname`,
    `apigee.proxy`
-   `network.vpc`, `network.subnet`, `network.networkAttachment`
-   `gateway.name`, `gateway.matchPaths` (a **list**, one entry per wire shape),
    `gateway.manageNetworkConfig`

**`matchPaths` drives TWO artifacts; write both from the same list.** The
**AuthzPolicy** `paths[].suffix` gets one suffix per entry, verbatim with
leading punctuation kept — it decides what the gateway routes to Apigee. The
template's **`LLM_URI_MATCH`** gets one `(request.uri Like "*<entry>*")` clause
per entry, OR-ed, leading `:` or `/` **stripped** — it decides what the proxy
acts on once it arrives. The shipped two-entry default gives:

```
((request.uri Like "*generateContent*") or (request.uri Like "*chat/completions*"))
```

The AuthzPolicy is the outer gate and wins: a suffix list narrower than
`matchPaths` means the missing shape never reaches Apigee at all. Derive both
from the input file and never from the default when the file disagrees — the
file is the reviewable contract and a mismatch is invisible once deployed.

**A one-entry list is legitimate** and governs one shape. Dropping an entry
governs one fewer **silently** — deploys clean, zero transactions for the shape
dropped — and narrows `feature-normalize`, Model Armor and the cache together.
`references/gotchas.md`, Runtime.

**`semanticCache` is a KNOWN ISSUE whenever it is on — warn, then build it.**
The key is the prompt embedding alone: no caller, no model, no shape. A hit
therefore crosses callers — similar prompts share an answer — and one model
behind one shape does not make it safe. With more shapes the first model to
answer answers for the other too: empty HTTP 200 across shapes, wrong-model
body within one. Warn whenever the cache is on, not only on multi-shape, then
build. Wording: `references/modes.md`; mechanism: `references/gotchas.md`.

**Each entry is a SUFFIX match.** You write these, not the user — derive them
from which endpoint their agent actually calls, and do not ask them to reason
about suffixes. Vertex's OpenAI-compatible endpoint and `api.openai.com` need
different entries, and getting it wrong governs nothing silently; the forms and
the evidence are in `references/gotchas.md`, Runtime.

**There is no `apiShape` field.** Metering does not depend on the wire shape —
the count is normalised in JS across both — so the field selected nothing and
was removed. Adding a shape is an `||` branch in `extract-model.js` plus an
entry in `matchPaths`.

**Three places carry the callout hostname and all three must match** — the
Apigee envgroup, the AuthzExtension `authority`/`service`, and the private DNS A
record. You set all three from one value: a build invariant to hold, not a
question for the user. It becomes a topic only when a callout never lands, and
then it is the first check. Build order matters alongside it — the
AuthzExtension is inert until the host resolves and the proxy is deployed, so
"the extension exists" is not evidence that leg works. `references/gotchas.md`,
Runtime.

## Workflow

### 0. Gateway: give it a route into the VPC

A gateway with no `networkConfig` has no route into the customer's VPC and
cannot resolve the callout hostname. **This skill builds it** — network
attachment, egress and DNS peering — so its absence is a build step, not a
blocker, and should be reported that way. Do not open with an alarm about a
resource you are about to create.

One thing here does need the user, and it is the reason this is step 0 rather
than a silent prerequisite: attaching egress is **one-way and affects traffic
they already run**. Settle it in the plan, before anything executes — see
"Confirm everything up front" below. Capturing a known-good agent turn first is
worth doing when they are nervous about a production gateway, because it
separates "never worked" from "we broke it"; it is a precaution to offer, not a
step to impose.

```bash
gcloud network-services agent-gateways describe "$GATEWAY" \
  --location="$REGION" --project="$PROJECT" --format='value(networkConfig)'
gcloud network-security authz-policies list \
  --location="$REGION" --project="$PROJECT"
```

**A console-created gateway already has a CUSTOM AuthzPolicy** — an IAP
`REQUEST_AUTHZ` one, which coexists with ours and is not needed for the egress
JWT. You never create the gateway, so assess it rather than assuming.
`references/gotchas.md`, Agent Gateway.

Empty `networkConfig` output means missing, and it is easy to miss: the gateway
still serves ordinary agent traffic perfectly, because that path goes to public
Google endpoints and never enters the VPC. Only the Apigee callout fails.

If it is missing, behaviour depends on `gateway.manageNetworkConfig`:

-   **`true`** — run the script below. It creates the network attachment, then
    read-modify-writes the gateway to add the egress attachment and DNS peering.
    Agreement for this is taken in the plan, not here; `--yes` carries it.
-   **`false`** — the user has said they want to make this change themselves.
    Print the script invocation and let them run it. Do not modify the gateway.

```bash
scripts/ensure_gateway_connectivity.sh \
  --gateway "$GATEWAY" --project "$PROJECT" --region "$REGION" \
  --vpc "$VPC" --subnet "$SUBNET" --attachment "$ATTACHMENT" \
  --domain "$DNS_DOMAIN"            # add --yes only after the user agrees
```

Either way `networkConfig` has to exist before the Apigee work starts — not
because its absence is an error, but because every later step then succeeds and
governs nothing.

Use the script, not the raw commands: `import` is a whole-resource upsert and a
hand-built YAML silently drops the gateway's `registries` and `protocols`. Why,
and the `etag` and `PROTOCOL_UNSPECIFIED` handling: `references/gotchas.md`.

### 1. Apigee: enable the environment

The env must carry `apigee-service-extension-enabled=true`. No `gcloud` flag
exists; PATCH the properties map.

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://apigee.googleapis.com/v1/organizations/$ORG/environments/$ENV"
```

**The PATCH replaces the whole map.** Read it first and re-send every property
you intend to keep, or you will silently drop them.

```bash
curl -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "https://apigee.googleapis.com/v1/organizations/$ORG/environments/$ENV?updateMask=properties" \
  -d '{"properties":{"property":[{"name":"apigee-service-extension-enabled","value":"true"}]}}'
```

This does **not** disable Apigee Analytics — the two coexist; if analytics looks
missing it is the separate per-environment add-on. `references/gotchas.md`.

**Use a dedicated environment**, attached to **exactly one envgroup**. An
environment in two makes the gateway 404 every request with the extension never
invoked. It also leaves the `/` base path free, which is what the proxy ships
with.

`scripts/ensure_apigee_environment.sh` creates the environment, attaches it to
the regional runtime instance, and creates and attaches the envgroup — so step 2
is already done when it succeeds. It creates billable resources and applies
nothing without `--yes`; that agreement is taken in the plan, not here.

```bash
scripts/ensure_apigee_environment.sh \
  --org "$ORG" --env "$ENV" --region "$REGION" \
  --envgroup "$ENVGROUP" --hostname "$HOSTNAME"      # add --yes to apply
```

It is idempotent and resumable, and refuses with exit 2 when the environment is
already in another envgroup or the envgroup exists on a different hostname. It
also handles three things a runbook tends to get wrong — the omitted `type` on
create, the four-minute instance attachment that **locks the environment**, and
polling the operation rather than a `GET` that succeeds too early.

### 2. Apigee: envgroup on the callout hostname

Done already if step 1's script ran. Verify, or do it by hand for an envgroup
that already exists. The hostname must be exactly the callout host, and the
group must be attached to the env.

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://apigee.googleapis.com/v1/organizations/$ORG/envgroups/$ENVGROUP/attachments"
```

**How many envgroups is the environment in?** More than one and the callout
never lands. `deploy_proxy.sh` enforces this before touching anything and exits
2 naming them; `assess_integration.sh` reports it. Read the failure literally if
it fires — the environment is wrong, not the script.

### 3. Build the proxy from the template

```bash
gcloud apigee apis import organizations/$ORG/apis/$PROXY \
  --from-template=assets/apigee-proxy-template.yaml
```

Each `features:` entry resolves **relative to the template file's own
directory**, never the working directory, so a bare filename must sit beside the
template (a subpath like `features/feature-identity.yaml` works too). `assets/`
is flat by convention, not compiler demand — but moving a file without updating
`features:` fails the import with a bare `FileNotFoundError`.

If you get `Permission denied on resource ... (or it may not exist)` on an org
you demonstrably have access to, it is the credential, not the access. With
context-aware access enabled the default gcloud credential is rejected. Pass the
ADC token instead:

```bash
CLOUDSDK_AUTH_ACCESS_TOKEN=$(gcloud auth application-default print-access-token) \
  gcloud apigee apis import ...
```

To change a parameter, **edit the `default` in every FEATURE that declares it**
— not in the template. `gcloud apigee apis import` passes an empty
caller-parameter map, so each feature resolves its own default and the
template's declaration of the same name is never read. Editing the template
changes nothing, silently, and the compile still passes. Measured: setting
`MA_CONTINUE_ON_ERROR` to DRY_RUN in the template shipped ENFORCE on a
fail-closed policy. `LLM_URI_MATCH` is declared in four features and all four
must agree. `scripts/compile_check.py` fails on any disagreement. There is no
`--parameters` flag.

Enable an optional recipe by adding its feature to the template's `features`
list. See `references/recipes.md`.

**`tokenMetering.models` in the input file is NOT generative.** It documents
which buckets exist; it does not create them. A bucket is real only when it has
an `LLMTokenQuota` step in `feature-token-metering.yaml` and a matching
`*_TOKEN_LIMIT` parameter. Three exist: `gemini-pro`, `gemini-flash` and `other`
— the catch-all for any model whose name contains neither `pro`/`argon` nor
`flash`/`hydrogen`. Adding a fourth entry to the list meters nothing, and
**omitting `other`
silently unmeters every non-Gemini model**: the count is extracted and then
discarded, with no `ratelimit` reference anywhere in the transaction. Adding a
model is a feature-file edit, not a config change.

### 4. Deploy

Deploy to the service-extension env, then confirm the deployment reports
`proxyDeploymentType: EXTENSIBLE`.

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  ".../environments/$ENV/deployments"
```

`STANDARD` means it will **not** govern the agent's off-Apigee tool egress.

If any policy calls a Google API — Model Armor, embeddings, Vector Search —
deploy **with a service account** or the deploy is rejected with
`MISSING_SERVICE_ACCOUNT`:

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  ".../apis/$PROXY/revisions/$REV/deployments?override=true&serviceAccount=$DEPLOY_SA"
```

### 5. Networking

This is the **gateway → Apigee** leg only. PSC endpoint to the Apigee instance
service attachment, plus a private DNS A record. See
`references/networking-psc.md`. The Apigee instance `consumerAcceptList` must
include your project or the connection never reaches `ACCEPTED`.

The **agent → gateway** leg is the prerequisite above, and is not built here.

### 6. Bind the gateway

AuthzExtension then AuthzPolicy — in that order, and only once the host resolves
and the proxy is deployed. The extension is inert until then.

**Both document bodies ship as assets. Copy and substitute; do not invent them**
— `assets/authz-extension.example.yaml` and `assets/authz-policy.example.yaml`.
They carry the fields that are load-bearing and have no obvious default:
`wireFormat: EXT_PROC_GRPC`, `failOpen`, the `authority`/`service` pair, the
`metadata` body flags, and the policy's `customProvider` / `httpRules` nesting.

```bash
gcloud service-extensions authz-extensions import $AUTHZ_EXT \
  --source=authz-extension.yaml --location=$REGION --project=$PROJECT
gcloud beta network-security authz-policies import $AUTHZ_POLICY \
  --source=authz-policy.yaml --location=$REGION --project=$PROJECT
```

**The policy's resource paths take the project NUMBER, not the ID** — both
`target.resources` and `customProvider.authzExtension.resources`. Resolve it
yourself; narrating two numbers at the user does not help. The trap, for when a
callout never lands: the number in the gateway's
`serviceExtensionsServiceAccount` is the Google-managed tenant project, not
theirs, and it is the only one on screen, so it is the natural thing to copy. A
wrong number imports cleanly and targets nothing. Copy the slots from
`assets/authz-policy.example.yaml`.

### 7. Verify

You **cannot** test with curl — the host is internal and the proxy expects the
gateway's IAP-egress JWT. Run `scripts/read_debug_session.sh --arm`, drive a
turn, read it back with `--session`. Expect **one** transaction per turn per
governed shape under a suffix list this narrow; zero alone does not mean the
callout is dead — the script prints the probe that settles it.

## Hard rules

**Gate every step — how urgently depends on your AuthzPolicy.** An ungated
`continueOnError="false"` policy faults on any call that carries no prompt, and
that **breaks the agent's turn**. Historically the most common failure here.

A narrow suffix list routes only the model call to Apigee, so the trap mostly
does not fire. Broaden the policy and it fires at once: the ext-proc then sees
every agent egress — session create/read, `appendEvent`, OpenTelemetry exports —
measured at 12 calls for one single-question turn, of which one was the model
call. Gate the steps regardless; a condition is cheap and it is what makes the
policy safe to widen later. Full measurement: `references/gotchas.md`.

-   model call: `(request.uri Like "*generateContent*")`

**Never fail-close on your own metering.** Keep `continueOnError="true"` on the
JavaScript and quota policies so a metering bug cannot break LLM traffic.

**This skill meters by default and can enforce on request.** Enforcement is
`assets/feature-token-enforce.yaml`: request-flow `EnforceOnly` policies sharing
each `SharedName` with the response-flow `CountOnly` half. Add it to the
template's feature list. Verified live on ext-proc traffic — the over-budget
caller gets a **429**, model never called.

Never offer `CountOnly=false` as a substitute: in the response flow it cannot
gate (the answer is already on the wire) and it freezes the counter, losing the
metering too.

State two things whenever you offer it. It is **one request late** — the turn
that crosses the limit completes, because a token cost is not known until the
model answers. And it buckets on the **requested** model, which under an OpenAI
alias can differ from the resolved model the counting side bills. The two traps
that both present as "it never refuses": `references/gotchas.md`.

**Normalize the model to a bucket.** With an OpenAI-compatible endpoint the
model is an alias in the request body and the *resolved* name is in the response
body (`google/gemini-4-argon`). Exact-matching a raw name fails on the response
path.

**`jsonPath` needs its third argument `true`** so it returns a scalar. Without
it the quota policy receives a node it cannot parse.

## References

-   `references/modes.md` — **read first.** How to answer "what can you do", dev
    vs prod, the defaults, durations, cost disclosure, the interlocks, and
    reading an assess report
-   `scripts/assess_integration.sh` — **read-only.** Setup Status Summary then a
    per-check table; `--json` carries both. Lead with the summary and read out
    the **Enforcement** row. Run it before planning: it decides CREATE vs REUSE.
    `TODO` is a build step, not a failure; only `FAIL` exits non-zero
-   `references/networking-psc.md` — both network legs, PSC, DNS, acceptance
-   `references/recipes.md` — Model Armor and semantic cache
-   `references/verify.md` — debug sessions and the checklist script
-   `references/setup.md` — SDK, project, billing, APIs, region, auth, IAM
-   `references/gotchas.md` — 63 failure modes and their symptoms
-   `assets/apigee-agent-gateway-governance.example.yaml` — the input contract
-   `assets/apigee-proxy-template.yaml` — the AFT template. Features merge by
    `priority` and all sit beside it: `feature-identity.yaml` (10),
    `feature-normalize.yaml` (15), `feature-model-armor.yaml` (20),
    `feature-semantic-cache.yaml` (30), `feature-token-metering.yaml` (50).
-   `assets/authz-extension.example.yaml`, `assets/authz-policy.example.yaml` —
    the step-6 bodies. Copy and substitute; paths take the project **number**

    **Anything read out of the request body is normalised once, at priority 15,
    not inside whichever feature needs it first.** `LLM_URI_MATCH` is shared, so
    widening it arms every feature gated on it simultaneously — including Model
    Armor, which fails closed. Model Armor and the cache both read
    `agw.user_prompt`; the quotas read `agw.total_tokens`, set on the response
    path by the metering feature's own JS for the same reason.
-   `scripts/ensure_apigee_environment.sh` — create the environment, attach it
    to the instance, create and attach the envgroup. Idempotent, `--yes` gated
-   `scripts/ensure_gateway_connectivity.sh` — route the gateway into the VPC. Read-modify-write; `--yes` gated
-   `scripts/ensure_vector_search.sh` — only when `semanticCache` is enabled:
    build index and endpoint, deploy one on the other, read back the domain.
    `--yes` gated, ~34 min, bills continuously
-   `scripts/teardown_vector_search.sh` — the only thing that STOPS that charge. Refuses until the revision drops `SCL-lookup`. `--yes` gated
-   `scripts/deploy_proxy.sh` — the Apigee-side sequence, idempotent, `--dry-run`
-   `scripts/read_debug_session.sh` — `--arm` a session (printing when it
    actually closes) and read it back as the `verify.md` checklist, instead of
    parsing the transaction JSON by hand
-   `scripts/compile_check.py` — compile the template offline, no org needed
