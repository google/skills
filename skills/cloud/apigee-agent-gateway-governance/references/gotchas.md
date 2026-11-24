# Failure modes, by symptom

Four groups. **Runtime** gotchas come from a working ext-proc setup and were
observed live. **Authoring** gotchas were found compiling this template through
the gcloud AFT compiler and apply to anyone writing AFT features. **Tooling**
and **Agent Gateway** gotchas were hit standing this up against a live org.

## Contents

-   [Runtime](#runtime): lines 15-566
-   [Authoring (AFT)](#authoring-aft): lines 567-635
-   [Tooling and environment](#tooling-and-environment): lines 636-720
-   [Agent Gateway](#agent-gateway): lines 721-836

## Runtime

**Every agent request returns 404 the moment you attach the AuthzPolicy, and the
extension is never invoked.** The environment hosting the ext-proc proxy is
attached to more than one envgroup. It must be in exactly one.

A debug session captures nothing and Cloud Monitoring records no requests, so it
looks like a networking or callout problem — but the callout target is fine.

**The one curl below is a reachability probe and nothing more.** From *inside
the VPC*, `curl -k -H "Host: <hostname>" https://<psc-ip>/` returns HTTP 200,
which proves only that the PSC endpoint and DNS resolve. It carries no
IAP-egress JWT and no agent body, so it exercises neither the callout nor a
single policy. **Never offer it as a way to test whether the integration
works** — that is a debug session against live agent traffic, and there is no
substitute. Count the environment's envgroups before suspecting anything else:

```bash
for g in $(curl -s -H "Authorization: Bearer $TOKEN" \
    ".../organizations/$ORG/envgroups" | python3 -c \
    "import json,sys; print(' '.join(g['name'] for g in json.load(sys.stdin)['environmentGroups']))"); do
  echo -n "$g -> "; curl -s -H "Authorization: Bearer $TOKEN" \
    ".../organizations/$ORG/envgroups/${g}/attachments" | python3 -c \
    "import json,sys; print([a.get('environment') for a in json.load(sys.stdin).get('environmentGroupAttachments',[])])"
done
```

Isolated by changing one variable at a time against a working setup. These are
**not** causes, each individually disproved: a second CUSTOM AuthzPolicy on the
gateway, gateway `registries`, the extension's `wireFormat` / `failOpen`, a
`.local` callout domain, and a leading colon in the AuthzPolicy path suffix.

Two of those are worth stating positively, because both look plausible enough to
cost someone an afternoon. A `.local` callout domain resolves fine — the gateway
reaches it over DNS peering, where multicast DNS never enters the picture. And
the shipped `:generateContent` suffix, colon included, was re-confirmed against
live traffic on a dedicated environment: the transaction was captured, the
client ID and model were extracted, and the quota counted.

**Attaching a just-created environment fails with `FAILED_PRECONDITION: the
resource is locked by another operation that is 1 percent completed`.** The
environment is *readable* long before it is *ready*. `GET /environments/{env}`
returns 200 while the create operation is still at 1%, so a "wait until I can
fetch it" loop exits immediately and the instance attach is then rejected for
holding a lock.

Poll the create operation instead — the POST returns it, and the error message
names it too:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://apigee.googleapis.com/v1/organizations/$ORG/operations/$OP_ID"
# done:true, metadata.state:FINISHED, and `error` set if it failed
```

The same lock covers the instance attachment, which takes about four minutes —
a property PATCH issued in that window fails in a way that reads like a
permissions problem. `scripts/ensure_apigee_environment.sh` waits on both
operations.

**The gateway import is rejected: domain "x." does not exist as a private
zone.** `dnsPeeringConfig.domains` is validated against private zones that
already exist in the target VPC, so the zone has to be created *before* the
gateway is patched — earlier than the step order suggests. The zone may be
empty; only its existence is checked, and the A record cannot be written until
the PSC endpoint has an IP anyway. `scripts/ensure_gateway_connectivity.sh`
creates it.

**Deploy fails with `CONFLICTING_DEPLOYMENT`.** Apigee allows one proxy per base
path per environment, and this proxy sits at `/`. On the dedicated environment
the skill now requires, `/` is free and this cannot happen — so hitting it means
the environment is shared, and the 404 above is coming for you next. Fix the
environment, not the base path. The failure surfaces only at deploy time, after
the import has already left an undeployed revision behind, so
`deploy_proxy.sh` enumerates base paths first and names the occupant.

**A non-root base path does work, if you need one.** Verified live: the same
proxy rebuilt with `basePath: "/v1beta1"` was invoked normally and the whole
policy chain ran — the Vertex path the gateway forwards is
`/v1beta1/projects/…/models/gemini-4-hydrogen:generateContent`, so `/v1beta1`
matches it. Proof it really metered rather than merely returning 200: the flash
counter moved 235 → 302, exactly the turn's own 67 tokens.

Two limits before reaching for it. It does **not** let you share an environment
— the 404 is caused by the envgroup count, which base paths have nothing to do
with. And it narrows the proxy permanently: the template also matches
`*/v1/chat/completions*`, and a `/v1beta1` base path can never see those. Use it
only to run a second processor alongside this one in the same dedicated
environment.

**The callout never lands — check the gateway first.** Before suspecting
anything you built, confirm the gateway can reach the VPC at all:

```bash
gcloud network-services agent-gateways describe "$GATEWAY" \
  --location="$REGION" --project="$PROJECT" --format='value(networkConfig)'
```

Empty output means the gateway has no egress `networkAttachment` and no
`dnsPeeringConfig`, so it has no route to the Apigee PSC endpoint and cannot
resolve the callout host. Everything downstream still builds and deploys
cleanly. The trap is that the gateway keeps serving ordinary agent traffic
perfectly — that path goes to public Google endpoints and never enters the VPC —
so the agent looks healthy while the callout is dead.
`scripts/ensure_gateway_connectivity.sh` fixes it.

**The callout never lands, and the gateway is fine.** Then it is the hostnames.
The Apigee envgroup hostname, the AuthzExtension `authority`/`service`, and the
private DNS A record must be the same string. Any divergence and nothing arrives
— with no error anywhere.

Check the build order at the same time: **the AuthzExtension is inert until the
callout host resolves and the proxy is deployed.** Creating the extension and
policy before those exist succeeds and reports nothing wrong, and the callout
stays dead until the two catch up. An extension created too early is not
self-healing in any visible way — re-check it once the host and deployment are
in place.

**Policies run but extract nothing.** The AuthzExtension `metadata` needs
`apigee-request-body: 'true'` and `apigee-response-body: 'true'`. Without them
`request.content` and `response.content` are empty and body extraction yields
nothing.

**No error is raised anywhere** — not in the trace, not in the policy, not on
the gateway. The extraction simply resolves empty and everything downstream
carries on, so there is nothing to search for and no failure to diagnose. Do not
go looking for an error message; check the two metadata flags first. This is the
single most common cause of "the policy runs but extracts nothing".

**The agent's turn breaks the moment you add a policy.** Most AI policies
default to `continueOnError="false"`, so on a call carrying no prompt the
extraction resolves empty, the policy raises, and the turn fails.

Whether this bites depends on how broadly the AuthzPolicy matches. With a
suffix list holding only model-call paths, only model calls reach Apigee —
with `:generateContent` alone, unfiltered debug sessions capture exactly one
transaction per turn — so every call the proxy sees carries a prompt. Broaden
the match and the ext-proc sees
*every* agent egress instead: session create and read, `appendEvent`, and the
OpenTelemetry `/v1/metrics`, `/v1/logs` and `/v1/traces` posts. Measured by
widening the policy to `prefix: /` for one single-question turn: **12
transactions, exactly one of them the model call.** The other 11 are promptless,
and each one is a chance for an ungated policy to fault. Gate every step anyway;
it costs a condition and it is what lets the policy be widened safely.

**Token counts never match the per-model counter.** Normalize the model to a
bucket. On an OpenAI-compatible endpoint the request body carries an alias
(`gemini-flash`) and the response body carries the resolved name
(`google/gemini-4-argon`); an exact-match condition on the raw string fails on
the response path.

**The quota policy errors on the token source.** `jsonPath` needs its third
argument `true` to return a scalar. Without it the policy receives a node or
array it cannot parse.

**`total_tokens` exceeds prompt + completion.** Observed: 1135 against 223 for a
thinking model. Metering `usage.total_tokens` bills the full amount, which is
usually intended. The payload does not label the excess, so don't report a
breakdown it doesn't contain.

**A response-path deny does not reach the caller at all.** This is the one to
read twice, because the intuitive failure — an ugly error — is not what happens.
The caller gets a **complete, successful answer** while Apigee believes it
denied the request.

The token quota runs in `PostFlow/Response`, because the token count does not
exist until the model has answered. By then the response is already on the wire.
Verified live, paired by token count against client output:

| quota `continueOnError` | extension `failOpen` | Apigee | what the client got |
| --- | --- | --- | --- |
| `true` (as shipped) | `true` | CONTINUE, 200 | full answer |
| `false` | `true` | ABORT, 429 | full answer |
| `false` | `false` | ABORT, 429→500 | full answer |

**The 500 in the trace is a decoy.** It appears only after `RESP_SENT`, in
Mint/Analytics bookkeeping, carrying the 429's reason phrase
(`status=500, reason="Too Many Requests"`). It is never transmitted. It is also
the first thing an operator sees, which is how this was mis-documented for so
long.

**Switching the quota to blocking also destroys the metering.** A blocking quota
refuses to count the request that violated it, so `used.count` freezes at the
limit for the remainder of the window — observed stalling at 149/200. Count-only
gives accurate metering and no gating; blocking gives neither.

**Request-path faults do propagate, so enforcement belongs there — and the
policy has a first-class way to do it.** Use the documented `SharedName` split
rather than hand-rolling an observer:

```xml
<!-- request flow: checks the counter, never increments it.
     LLMModelSource is REQUIRED here even though this half never counts --
     omitting it is a live outage, see "LLMModelSource is REQUIRED" below. -->
<LLMTokenQuota name="LTQ-enforce-pro" type="rollingwindow">
  <SharedName>llm-tokens-pro</SharedName>
  <EnforceOnly>true</EnforceOnly>
  <Allow count="40000"/>
  <Interval>1</Interval><TimeUnit>hour</TimeUnit>
  <Distributed>true</Distributed>
  <LLMModelSource>{agw.req_model_bucket}</LLMModelSource>
</LLMTokenQuota>

<!-- response flow: increments it, never refuses -->
<LLMTokenQuota name="LTQ-count-pro" type="rollingwindow">
  <SharedName>llm-tokens-pro</SharedName>
  <CountOnly>true</CountOnly>
  <Allow count="40000"/>
  <Interval>1</Interval><TimeUnit>hour</TimeUnit>
  <Distributed>true</Distributed>
  <LLMTokenUsageSource>{agw.total_tokens}</LLMTokenUsageSource>
  <LLMModelSource>{agw.model_name}</LLMModelSource>
</LLMTokenQuota>
```

Exactly one of `CountOnly` and `EnforceOnly` may be set on a policy. The
enforce half carries no `LLMTokenUsageSource` — it only reads the counter the
other half writes — but it **does** still require `LLMModelSource`, which is
not optional and not implied by the absence of counting. Apigee's own sample
for this pattern is a
`<RouteRule name="noroute"/>` proxy, which is our shape, so a processor with no
target is not a blocker.

An **earlier version of this file said enforcement "cannot work" here.** That
was wrong and the inference was bad: it generalised a real observation about one
`CountOnly=false` policy in the *response* flow into a claim about the policy
type. Do not repeat it to a user.

**Shipped as `assets/feature-token-enforce.yaml`** — three enforce policies,
one per `SharedName`, gated on the requested-model bucket, off by default.

**Verified live in the shape that matters**: a no-route proxy
invoked as `EXT_PROC_GRPC` by an Agent Gateway, on real Agent Runtime traffic,
where request and response arrive as separate gRPC messages. The over-budget
turn was refused with `429 Too Many Requests` and *"Rate limit LLM Token quota
violation"*, before the model was called. From that trace, flash budget 500:

```
ratelimit.enforce-LTQ-flash.used.count      = 1086   <- written by CountOnly
ratelimit.enforce-LTQ-flash.allowed.count   = 500
ratelimit.enforce-LTQ-flash.exceed.count    = 586
error.state                                 = PROXY_REQ_FLOW
```

The request-path policy read exactly what the response-path policy had
accumulated under the same `SharedName`, so **the linkage does join the two
halves in a no-route ext-proc proxy.** `<Identifier>` also scopes per caller
on the enforce half — `ratelimit.*.identifier` resolved to the calling agent's
principal, not a shared bucket.

An earlier report of "0 refusals at any budget" was a test harness pointed at
a different project, so that traffic never reached the proxy under test. Not a
platform defect — but worth keeping as a reminder to confirm traffic arrives
before concluding a policy does not fire.

**Two traps that both present identically as "it never refuses".**

*The nasty one: bucketing on a raw URI substring.* The enforce half buckets on
the requested model, and testing the whole URI for a model name is unsafe:

```
/v1beta1/projects/.../models/gemini-4-hydrogen:generateContent
                ^^^ contains "pro" inside *pro*jects
```

A `request.uri Like "*pro*"` condition therefore matches a **flash** request,
sends it to the pro bucket, finds headroom and allows — while the count half
correctly bills flash. Indistinguishable from a broken platform, and entirely
a config error. The shipped JS anchors the match after `models/` and buckets
on the extracted name for exactly this reason; do not simplify it into a
substring test on `request.uri`.

*The loud one:* omitting `LLMModelSource`, below.

**`LLMModelSource` is REQUIRED on the enforce half.** It is tempting to infer
that a policy which never counts needs no source elements at all; that
inference caused an outage. The restriction is on `LLMTokenUsageSource`
only — the enforce half must not *count*. It must still know *which bucket* to
check. Omit `LLMModelSource` and the policy substitutes a default of
`jsonPath('$.model', request.content, true)`, which does not resolve on a
Gemini-native `:generateContent` call because the model is in the URI, not the
body. It then raises `FailedToResolveModelName`, and at
`continueOnError="false"` that refuses **every** governed turn, not just
over-budget ones. Measured: 100% of traffic down for 8 minutes.

One limitation by construction: the enforce half buckets on the **requested**
model, because the resolved name only exists in the response. On an
OpenAI-compatible endpoint an alias may resolve to a different model, so a call
can be enforced against one bucket and counted against another. Everything is
still counted and still checked; it is only unsafe if someone assumes a
per-model limit is exact under aliasing.

Two further properties to accept — one a design constraint, one a `RaiseFault`
defect.

**Enforcement is one turn late.** The check reads the counter as it stood before
the current turn, because that turn's cost is unknown until the model answers.
Callers can overshoot by one turn. Unavoidable when enforcing in this position.

**`RaiseFault` discards `FaultResponse.Set` entirely — and this is NOT a general
property of request-path faults.** Easy to get backwards, and Model Armor is a
live counter-example in this same proxy:

| fault source | client status | client payload |
| --- | --- | --- |
| a policy's own error carrying an HTTP mapping — `SanitizeUserPrompt` raising `steps.sanitize.user.prompt.FilterMatched` | **400**, preserved | preserved in full, naming the matched filter |
| `RaiseFault`, whatever `StatusCode` is configured | **always 500** | always `Raising fault. Fault name : <policy>` |

Confirmed by single-variable test: a `RaiseFault`'s `StatusCode` changed `429` →
`400` with `ReasonPhrase` to match, verified in the deployed bundle, changed
nothing at the client. Status, reason phrase and body are all dropped, and no
configuration recovers them.

Two consequences. Do not promise an opaque 500 from a policy that raises its own
mapped error — Model Armor returns a clean 400 with detail. And because the
policy name is provably the only field a `RaiseFault` transmits, **naming one is
load-bearing, not cosmetic**: it is the entire diagnostic the caller gets.

**A tool policy "doesn't fire".** Check `proxyDeploymentType`. A proxy carrying
only generic policies deploys `STANDARD` and does not see the agent's calls to
off-Apigee tools or MCP servers. It must be `EXTENSIBLE`.

**Analytics went dark.** Not caused by the Service Extension. Setting
`apigee-service-extension-enabled=true` does **not** disable Apigee Analytics —
they coexist. On a Pay-as-you-go org, Apigee API Analytics is a paid
per-environment add-on that is simply off at environment creation; enable it
with `addonsConfig:setAddonEnablement {"analyticsEnabled":true}`. On a
Subscription org it is on already. Check `billingType` on the org before
concluding anything. Cloud Monitoring (`apigee.googleapis.com/proxyv2/*`) works
either way.

**A property you did not touch disappeared.** The environment PATCH replaces the
entire properties map. Read it first, re-send everything you want to keep.

**Deploy is rejected with `MISSING_SERVICE_ACCOUNT`.** Any policy calling a
Google API needs `?serviceAccount=` on deploy, plus the matching role —
`roles/modelarmor.user`, `roles/aiplatform.user`.

**Token metering bills for cache hits.** The two features are individually
correct and wrong together, and nothing surfaces it. Measured: the flash
counter moved 683 → 780 across a cache hit — exactly the 97 tokens of the
replayed answer — with Gemini never called.

Nothing in the metering steps is conditional on anything the cache sets.
`JS-extract-model` reads `request.uri`, which on a hit still ends
`:generateContent`, so `agw.model_name` is set as usual; the quota then reads
`usageMetadata` out of the replayed response and counts it. Populate is the
only step in the proxy that knows about `cache_hit`.

It inverts the point of the feature. The cache avoids model spend, but the
caller is metered as though every hit were an inference, so a high-hit-rate
workload exhausts its quota while costing almost nothing to serve.

Fixed in `feature-token-metering.yaml` by adding populate's cache-hit clause to
both quota steps, keeping the model-name gate. `AM-quota-headers` stays ungated
so a hit still returns headers, and `JS-extract-model` stays ungated because it
sets the model name those headers report. This is the one cross-feature
reference in the template, and it degrades safely: with the cache disabled the
variable never resolves and `!= true` is true.

**Placeholder substitution corrupts `DEPLOYED_INDEX_ID` silently.**
`DEPLOYED_INDEX_ID` *contains* `INDEX_ID`, so an ordered `sed` over the feature
file rewrites the parameter's own name:

```
sed 's|INDEX_ID|3873425533026959360|g'
  - name: DEPLOYED_INDEX_ID               ->  - name: DEPLOYED_3873425533026959360
    DeployedIndexID: "{DEPLOYED_INDEX_ID}" ->  "{DEPLOYED_3873425533026959360}"
```

What makes it dangerous is that it survives: declaration and reference are
renamed consistently, so the bundle compiles and runs. It only surfaces later,
when the template supplies a `DEPLOYED_INDEX_ID` that no longer exists. Use
word boundaries (`\bINDEX_ID\b`) or replace longest-first, and assert that no
placeholder survives. `INDEX_ENDPOINT_ID` and `INDEX_ENDPOINT_DOMAIN` share a
prefix the same way. `deploy_proxy.sh` does both and refuses to import a
half-substituted bundle.

**The findNeighbors host cannot be derived, so it is not an input.** The index
endpoint's domain has a leading label assigned at creation time that matches
neither the index id, the endpoint id, nor the project number. It can only be
read back, which is why `apigee-agent-gateway-governance.example.yaml` has no
field for it and
`deploy_proxy.sh --index-endpoint-id` substitutes it at deploy time.

**Semantic cache re-populates on a hit.** On a no-route proxy the response flow
runs on a cache hit too, because there is no target flow for populate to live
in. Ungated, it re-embeds and re-upserts the answer it just served. Gate
populate on the lookup's cache-hit flag.

**The cache-hit condition never matches.** Runtime emits
`SemanticCacheLookup.<policy>.cache_hit`. The policy reference documents
`semanticcache.lookup.<policy>.cache_hit`, which does not resolve — and because
an unresolved variable makes `!= true` true, it fails *open*. Read real variable
names out of a trace before conditioning on them.

**`<DeployedIndexId>` fails bundle validation.** It is `<DeployedIndexID>`,
all-caps ID.

**The transaction you wanted isn't in the debug session.** First check how many
there are, because the answer differs completely.

**One per governed shape, and each is a model call** — that is correct, not
truncation. A suffix list of model-call paths routes only those, so one
transaction per turn per shape is the healthy result. With `:generateContent`
alone that is exactly one.

**Zero** — the callout is not landing at all. Work the entries above: gateway
`networkConfig`, then the three hostnames, then the envgroup count.

**Many, and yours got pushed out** — only happens with a broadly-matching
AuthzPolicy. Measured at `prefix: /`: 12 transactions for one single-question
turn against a `count` cap of 15. Arm the session with a `filter` rather than
firing more traffic, which only makes it worse.

**Something that worked an hour ago returns nothing.** In sandbox orgs an IAM
reaper may strip non-baseline bindings on the deployment SA roughly every 30
minutes. The symptom is not a clean 403 — it is an empty agent turn. Re-grant
immediately before a test run.

**`ServiceCallout` runs despite being unsupported.** It is on the Extension
Processor unsupported-policy list, yet imports, deploys `EXTENSIBLE` and
executes from both request and response flows. Docs and platform disagree; don't
build on it until that is resolved.

**An OpenAI-shape agent is governed by nothing and reports nothing, because its
`matchPaths` entry has a `/v1` in it — or because there is no entry for it at
all.** The AuthzPolicy binds on path **suffix**, and
Vertex's OpenAI-compatible endpoint ends `openapi/chat/completions` — so
`/v1/chat/completions` is not a suffix of it and never matches. Measured: a
debug session open across two successful agent turns captured **0
transactions**; adding `/chat/completions` captured 1. Same signature as the
envgroup 404 — everything deploys clean and governs nothing. `/v1/...` is
correct only for literal `api.openai.com`.

The "no entry at all" case is the one to watch once a second shape has been
added. `matchPaths` compiles
to `LLM_URI_MATCH`, a one-entry list is a legal way to say "govern one shape",
and nothing distinguishes a deliberate single entry from a forgotten second
one. If a shape is reporting zero transactions, check the list length before
anything else.

**With the cache on and two models behind one proxy, an agent returns an
EMPTY answer and no error.** Recognise this symptom, because it sends you into
the agent code and the cause is in the proxy. `SemanticCacheLookup` keys on
the embedding of the prompt **and nothing else** — no model, no wire shape, no
tenant — so whichever model answers a given prompt first answers it for every
model. Reproduced across three consecutive runs, a Gemini agent and an
OpenAI-shape agent against one proxy:

```
cache_hit           : true
agw.requested_model : openai/gpt-oss-120b-maas      <- on a GEMINI request
response            : {"choices":[{"message":{"content":"Mars."}}], ...}
```

The Gemini client looks for `candidates[].content.parts[]`, finds `choices[]`,
matches nothing, and returns `{'parts': [], 'role': 'model'}`. No exception,
no fault, a 200 — an empty success.

Three consequences, worst first: **cross-shape corruption**, which degrades to
empty rather than erroring; **wrong-model answers**, since any model's answer
satisfies any model's question; and **metering misattribution**, because
`extract-model.js` reads the model out of `response.content`, which on a hit
is the *cached* response, so the request is billed to the wrong bucket.

The priority-15 normalisation is what makes this reachable — giving Model Armor
and the cache a shape-agnostic `agw.user_prompt` is exactly what lets a Gemini
prompt and an OpenAI prompt produce the same key. Both changes are still
right; this is the seam between them.

The policy exposes no key composition, so there is no clean fix. Pick a
trade-off:

| mitigation | cost |
| --- | --- |
| disable the cache when >1 model is behind the proxy | loses the feature; the right default |
| one index per model bucket, keyed on `agw.model_name` | multiplies the most expensive resource in the design |
| prefix `agw.user_prompt` with `agw.model_name` in `extract-prompt.js` | one line and it works, but perturbs the semantic space so near-miss prompts stop matching |

**Vector Search `restricts` cannot be used for this, and it is the first idea
everyone has.** The API does support namespace/allow-list filtering on
`upsertDatapoints` and `findNeighbors`, so writing the resolved bucket as a
restrict on populate and filtering on it at lookup would scope hits to one
model without touching the embedding or the index geometry. The obstacle is
not Vector Search, it is the policy surface: `SemanticCacheLookup` exposes
only `UserPromptSource`, `Embeddings.VertexAI.URL` and
`SimilaritySearch.VertexAI.{URL, DeployedIndexID, Threshold}`, and
`SemanticCachePopulate` only `SimilaritySearch.VertexAI.URL` and
`TTLInSeconds`. Both build their request bodies internally and neither takes a
restricts element, so there is nowhere to put one. This is not a
prototype-and-see — there is no seam.

A fix is open with the Apigee team: make the cache key a configurable composite
identifier, so it can carry something beyond the prompt embedding. Model and
wire shape are the same missing dimension as tenant, so the evidence above was
attached to that request rather than raised separately. That request is the
restricts idea asked at the layer that can grant it.

**A non-Gemini model consumes no quota at all, silently.** `agw.model_name`
buckets on the substrings `pro`/`argon` and `flash`/`hydrogen`, and only those
two buckets had a quota bound to them. Measured with `gpt-oss-120b-maas`: the
token count was
extracted correctly (`agw.total_tokens = 223`) and then discarded — **zero**
`ratelimit` references in the whole transaction. This is worse than a
resolution failure, which at least raises `FailedToResolveTokenUsageCount`
into the trace. The shipped fix is a catch-all `LTQ-count-other` on
`OTHER_TOKEN_LIMIT`. The real fix is generating one quota per entry in the
`models:` list, which today reads as authoritative and generates nothing.

**Widening `LLM_URI_MATCH` to a second wire shape makes Model Armor return 500
on every request of that shape.** The condition is shared by every feature
gated on it, so widening it arms them all at once — and Model Armor is
`continueOnError: false` by design. Its `UserPromptSource` JSONPath is written
for one body layout, does not resolve against the other, and the policy fails
**closed**. The result is not a skipped scan, it is a hard failure per
request, with the trace showing `modelarmor-SUP-sanitize` faulting and the
cache policies never reached.

The fix is structural, not a typo fix: anything derived from the request body
is normalised **once**, in `feature-normalize.yaml` at priority 15, which runs
after identity (10) and before Model Armor (20) and the cache (30). Putting
the normalisation inside the cache feature at priority 30 compiles, deploys,
and does nothing — it runs after its consumer. Check the compiled order, which
makes it obvious:

```
identity-VJ, identity-AM, normalize-JS-extract-prompt, modelarmor-SUP-sanitize, semanticcache-SCL-lookup
```

Note the failure direction was lucky. A fail-open policy would have degraded
quietly; Model Armor failing closed is what made this findable in one request.

**The semantic cache stores upstream errors and replays them as HTTP 200.**
`SemanticCachePopulate` is status-blind — gated only on `cache_hit`, it will
cache any response the flow produces. Observed: a transient 429 from a
throttled model was written to the cache, then served to every identical
prompt for the whole TTL, **with a 200 status**. A momentary blip became a
persistent wrong answer that defeats status checking, and metering saw
nothing (`token_source = none`, `used.count = 0` throughout). Client-side the
symptom was a crash — Vertex wraps error envelopes in a JSON array while
success bodies are bare objects.

Gate populate on `response.status.code = 200`. Verified across ten
transactions: populate executed on the one successful response and skipped
all nine 429s. Raised with the Apigee team — the policy should not cache
non-2xx by default, or should expose an eligibility control. Two caveats went
with it: this was seen on a
**no-route** proxy, where the response flow runs for every outcome, and the
200 on replay may come from the ext-proc short-circuit rather than the cache
policy — the composite behaviour is what was measured.

## Authoring (AFT)

Found while compiling this template. Reproduce with `scripts/compile_check.py`.

**gcloud 588.0.0 changed two AFT compiler behaviours, and both fail silently.**
Tracked upstream as a compiler regression. Neither breaks the shipped bundle —
all six features set `uid` and the template declares no `endpoints`/`targets` —
but both become load-bearing from 588.0.0 on, and the guard is invisible.

1.  **Policy names are namespaced only for features that declare a `uid`.**
    Before 588.0.0 the feature name was always prefixed. Now, with `uid:
    semanticcache` set, `SCL-lookup` still compiles to
    `semanticcache-SCL-lookup`. Remove the `uid` and the prefix disappears,
    while every condition naming the policy in full keeps the old name —
    including `SemanticCacheLookup.semanticcache-SCL-lookup.cache_hit`, which
    gates all three quota steps. The bundle compiles, deploys, and the
    cache-hit guard silently stops matching.
2.  **Template-level `endpoints`/`targets` are dropped whenever the template
    supplies features.** A feature's `defaultEndpoint` is only a fragment
    merged into endpoints that already exist, so a template that declares its
    endpoint *and* features ends up with zero endpoints and every flow
    discarded. This template keeps its endpoint inside
    `feature-identity.yaml` (priority 10) for that reason. Do not move it back.
    The import fails with `The proxy must contain a ProxyEndpoint`, which names
    the wrong cause.

Evidence note: read off the compiler's own behaviour change plus the feature
files, not a live 588.0.0 import. Worth one real import to confirm.

**A macro in the template's own body is never substituted.** The compiler runs
parameter replacement over *feature* content only; the template's `endpoints`
are copied verbatim. A `{BASE_PATH}` written in the template's `basePath`
reaches Apigee as the literal string `{BASE_PATH}`. Template-level parameters
exist to supply override *values* to features that declare a parameter of the
same name — they are not usable inside the template itself. Write literals
there.

**Two Flow entries named `PreFlow` emit two `<PreFlow>` elements.**
`models.Flow` carries a single `mode`, so a PreFlow with both a Request and a
Response phase cannot be expressed as one entry; the converter emits one element
per entry, producing invalid ProxyEndpoint XML. Put response-phase steps in
`PostFlow`/`Response`, which is what AFT's own fixtures do. Note this is a
deviation from a playbook that specifies PreFlow Response — verify on a live
org.

**Cross-policy variable references are not namespaced.** Every policy is renamed
`<feature>-<policy>`, and `<Step><Name>` references and `jsc://` resource URLs
are rewritten to match. Policy-derived *flow variables* are not:
`jwt.<policy>.decoded.claim.*`, `SemanticCacheLookup.<policy>.cache_hit`,
`parsepayload.<policy>.operation`, and the `stepName` attribute on
`UseQuotaConfigInAPIProduct` all keep whatever you wrote. Write them
pre-namespaced (`jwt.identity-VJ-iap-egress-jwt.decoded.claim.email`) and they
will break if the feature is renamed or given a `uid`.

**A feature file is not found.** Each `features:` entry is joined onto the
template file's own directory, never the working directory. Moving a feature
into `assets/features/` without changing its `features:` entry to
`features/<name>.yaml` breaks the import with a bare `FileNotFoundError`. The
subdirectory itself is fine — verified by compiling a template whose entries
carry the subpath — so it is the mismatch that breaks it, not the nesting.

**An empty `targets:` list still emits `<TargetEndpoints></TargetEndpoints>`.**
Harmless in the bundles compiled here, but confirm against bundle validation on
first deploy.

**Apigee message templates and AFT macros share `{}`.** `{agw.model_name}` is
left alone only because no declared parameter is named that. Never name an AFT
parameter after a runtime variable.

## Tooling and environment

**"Extensible proxy can not be deployed to a base environment" — on an
environment the scripts created minutes earlier, where every prior step
passed.** The environment type is `BASE`, and `BASE` cannot host an extensible
proxy. The remedy is a PATCH, not a rebuild:

```bash
curl -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  ".../organizations/$ORG/environments/$ENV?updateMask=type" \
  -d '{"type":"COMPREHENSIVE"}'
```

It is `BASE` on purpose. The create deliberately omits `type`, because sending
it is rejected outright on a `SUBSCRIPTION_2021` org with a message about
pricing plans — so the org default applies, and that default is `BASE`.

**What makes this one disorienting is where it lands.** The create, the
instance attach and the `apigee-service-extension-enabled` property PATCH all
succeed against a `BASE` environment. Nothing warns. The failure surfaces only
at proxy deploy, several steps and roughly four minutes of attachment later,
which points suspicion at the proxy or the template rather than at an
environment that was reported healthy. Patching to `COMPREHENSIVE` *before* the
instance attach turns a four-minute round trip into a few seconds, and is
idempotent — patching an already-`COMPREHENSIVE` environment is a no-op, and
the service-extension property survives it.

Reading the type back has its own trap: a healthy environment commonly returns
**no `type` key at all**. Absent is not `BASE`. Only an explicit `BASE` blocks
the deploy — see `scripts/ensure_apigee_environment.sh` and the matching check
in `scripts/assess_integration.sh`.

**`apigee-service-extension-enabled=true` does not disable Apigee Analytics.**
The two coexist; a claim to the contrary circulated in an earlier playbook and
is wrong. Apigee API Analytics is a per-environment add-on orthogonal to the
property: on by default on a **Subscription** org, and on **Pay-as-you-go** a
paid add-on that is off at environment creation and must be enabled explicitly.
So analytics missing on a service-extension environment is almost always the
add-on, not the property. Enable it with:

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  ".../organizations/$ORG/environments/$ENV/addonsConfig:setAddonEnablement" \
  -d '{"analyticsEnabled":true}'
```

It bills from the moment enablement begins, so check `billingType` on the org
before telling a customer either way.

Hit while running this against a live org.

**`--from-template` used to be beta-only. It is on GA as of gcloud 588.0.0.**
Verified by a real import: plain `gcloud apigee apis import --from-template`
succeeds. On an older SDK the GA command rejects the flag, which is easy to
misdiagnose as "the command does not exist in this SDK version" -- the fix
there is `gcloud beta apigee apis import`, or upgrading.

**"Permission denied on resource ... (or it may not exist)" can be a credential
path, not access.** With context-aware access enabled, gcloud's default account
credential was rejected on an org the same user could reach fine over REST with
an ADC token. The error names the resource, which points you at IAM rather than
at the credential. Workaround:

```bash
CLOUDSDK_AUTH_ACCESS_TOKEN=$(gcloud auth application-default print-access-token) \
  gcloud apigee apis import ...
```

**`compile_check.py` dies on `ModuleNotFoundError: No module named 'yaml'`.**
The interpreter you ran it with does not carry PyYAML. The script now says so
by name rather than raising a bare traceback. `pip install pyyaml`, or re-run
with a Python 3 that already has it. Note the gcloud SDK's bundled interpreter
does not, and the SDK's vendored `yaml` is Python 2 -- neither is the answer.
The script needs PyYAML and the in-repo gcloud AFT modules, nothing else.

**An environment is locked while an instance attachment runs.** Setting the
`apigee-service-extension-enabled` property returns `400 FAILED_PRECONDITION ...
resource is locked by another operation` until the attachment LRO finishes.
Attach first, then set properties.

**The environment property PATCH is asynchronous.** It returns a long-running
operation, not the updated Environment, and a readback immediately afterwards
shows empty properties. Poll the operation before concluding the property did
not stick.

## Agent Gateway

**Two `CONTENT_AUTHZ` policies on one gateway: the execution order is
undefined. Do not invent one.**

This is the single most tempting place in the whole integration to fabricate an
answer, because every instinct says a deterministic system must have a
documented tie-break. There is none. Specifically, none of these is the rule,
and stating any of them to a customer is worse than saying "unknown":

- **not** alphabetical by resource name
- **not** creation order, or last-writer-wins
- **not** any `priority` field — `AuthzPolicy` has none for this
- **not** the order they appear in a `list` response

The honest answer is that precedence between two `CONTENT_AUTHZ` policies on
the same gateway is not defined or documented, so the safe assumption is that
either may run first and neither may depend on the other's effect. If ordering
actually matters for a design, that design needs changing.

Coexistence itself is normal and expected: a gateway acquires a policy
automatically when agents are registered, and other governance products add
their own. A
`REQUEST_AUTHZ` policy alongside a `CONTENT_AUTHZ` one is a different phase
entirely and chains cleanly — that case is not ambiguous and should not be
described as if it were.

**They also cannot be merged.** An `AuthzPolicy` carries a single custom
provider, so each product needs its own and the pair has to coexist. A gateway
allows 4 CUSTOM policies, so there is room. Expect "then can we combine them"
as the immediate follow-up to the precedence answer, and answer it unprompted.

**Every invocation of a gateway-attached agent returns 401, and the agent's own
code never runs.** The container fails on its own outbound `sessions.create`
with `401 UNAUTHENTICATED`, which reaches the client wrapped as a `400
INVALID_ARGUMENT  Reasoning Engine Execution failed`.

Fix, in the agent's deploy config:

```python
"env_vars": {
    "GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES": "False",
},
```

Two conditions are both required: the agent is attached to an Agent Gateway,
**and** it was built after 2026-09-30. Neither alone reproduces -- the same
agent without the gateway serves fine, and an engine built before that date
with byte-identical config still serves.

Three things make it expensive to diagnose. It is **invisible at deploy time**:
the deploy succeeds and the engine reports healthy. The failing spec and a
working one differ in nothing readable -- the operative setting is *absent*
from both and resolves to a runtime default that `GetReasoningEngine` does not
report, so a field-by-field diff shows only name and timestamps. And the
traceback points at ADK session code, which reads like an agent bug rather
than a platform one.

Tracked upstream with the full isolation table; it is an instance of the
cert-bound-token family where an Agent Identity token reaches a non-mTLS
endpoint. The gateway is what enforces the cert binding, which is why removing
it appears to "fix" the agent.

The gateway itself is out of scope for this skill, but these cost hours if you
are standing one up to test against. Background:
[Agent Gateway overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/agent-gateway-overview.md.txt)
and
[Set up an Agent Gateway](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/set-up-agent-gateway.md.txt).

**Everything is built, and no traffic arrives.** Check where the agent runs
before anything else. A GCE VM can never reach the gateway — the supported
compute is GKE or Cloud Run, and Cloud Run must be in ambient networking mode.
Use Agent Runtime with `agent_gateway_config`. See
`references/networking-psc.md`.

**A consumer PSC endpoint to the gateway stays `PENDING`.** Expected, and not
fixable with gcloud: acceptance needs an internal `References.CreateReference`
call. It presents as TCP 443 closed, which looks like a firewall rule you are
missing.

**Agent Runtime creation fails with "Permission denied to get Agent Gateway".**
The Vertex AI service agent
(`service-<project-number>@gcp-sa-aiplatform.iam.gserviceaccount.com`) resolves
the gateway on your behalf and needs `networkservices.agentGateways.get` on the
gateway project. Grant `roles/networkservices.viewer` — it is the narrowest
predefined role that carries the permission, and neither
`roles/networkservices.agentGatewayUser` nor `…agentGatewayViewer` does, despite
the names. The error suggests waiting for API-enablement propagation, which will
send you off waiting for something that never arrives if the binding is simply
absent.

**There is no `gcloud` surface for Agent Runtime.** No `agent-engines` or
`reasoning-engines` group on GA, beta or alpha. Attaching an agent to a gateway
is SDK-only, which is easy to misread as the feature being unavailable.

**`AgentGateway` has no `create` verb.** Only import, export, describe, list and
delete. It is declarative YAML or nothing.

**`dnsPeeringConfig.targetNetwork` rejects a bare network name.** It wants
`projects/{project}/global/networks/{network}`, despite the field name.

**The two `dnsPeeringConfig` fields are different schemas.**
`AgentGatewayNetworkConfig` takes `{targetProject, targetNetwork, domains[]}`;
`EgressNetworkConfig` takes `{targetNetwork, domain}`, singular. Copying one
into the other fails validation.

**`agentConnectivityTemplate` wants the project *number*.** Not the ID. It is
also **mutually exclusive with `networkConfig`** — set both and the import is
rejected. Attaching one to an existing gateway returned `code 13, an internal
error has occurred` after ten minutes; treat the template path as unproven.

**Budget ten minutes per import.** `AgentGateway` and `AuthzPolicy` imports both
take roughly that. They have not stopped responding.

**A fresh VPC may have no firewall rules at all**, so SSH to a test instance
times out before you get far enough to debug anything else.
