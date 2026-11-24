# Verifying the callout

**You cannot test this with curl.** The endpoint is internal — only the gateway
reaches the PSC host — and the proxy expects the gateway's IAP-egress JWT.
Driving traffic also needs the gateway's client-facing ingress and mTLS.

The method is: arm an Apigee debug session, send real traffic through the
gateway, read the transactions back.

**Use the script.** Everything in this file below "What to confirm" is
implemented by `scripts/read_debug_session.sh`, which fetches the
transactions and prints the checklist as a table. The raw `curl` calls are
kept because you need them to diagnose the script itself, not because you
should be running them by hand:

```bash
scripts/read_debug_session.sh --org "$ORG" --env "$ENV" --proxy "$PROXY" \
  --rev "$REV" --arm                     # prints the session id and when it closes
# ... drive one agent turn ...
scripts/read_debug_session.sh --org "$ORG" --env "$ENV" --proxy "$PROXY" \
  --rev "$REV" --session "$SESSION" [--steps] [--json]
```

`--arm` reports the **absolute** expiry computed from the `validity` the
server returned, and says so when it was clamped — see the clamp note below.
The transaction shape is not guessable, and a parser that returns nothing
against a healthy trace is the normal first result; that is what the script
exists to stop.

## Contents

-   [Arm a session](#arm-a-session): lines 40-88
-   [Read it back](#read-it-back): lines 89-128
-   [What to confirm, in order](#what-to-confirm-in-order): lines 129-209
-   [Verifying enforcement](#verifying-enforcement): lines 210-246
-   [Measure proxy-side, not from the caller](#measure-proxy-side-not-from-the-caller): lines 247-257
-   [Checking deployment type](#checking-deployment-type): lines 258-267
-   [Offline check](#offline-check): lines 268-277

## Arm a session

How much filtering you need depends on **how broadly your AuthzPolicy matches**,
and the shipped default matches narrowly.

With a suffix list of model-call paths, only those are routed to Apigee. With
`:generateContent` alone an unfiltered session captures exactly **one**
transaction per agent turn — one per governed shape if the list is longer —
verified across several unfiltered sessions, each of which returned a single
transaction. Filtering is optional there, and one transaction is the healthy
result rather than a truncated one. Zero transactions means the callout is not
landing.

Broaden the policy — drop the suffix, or match on a prefix — and the ext-proc
begins seeing every agent egress instead. Measured by widening the policy to
`prefix: /` and running one single-question turn: **12 transactions**, of which
exactly one was the model call. The rest were a session create, a session read,
two `/v1/metrics`, two `/v1/logs`, one `/v1/traces`, and four posts whose path
the trace did not record.

`count` maxes at 15, so that one turn used 12 of the 15 slots — it did not
truncate, but a turn with tool calls would. **Filter whenever the policy matches
broadly**, or the call you care about gets pushed out.

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  ".../environments/$ENV/apis/$PROXY/revisions/$REV/debugsessions?timeout=600" \
  -d '{"count":15,"tracesize":5120,"filter":"(request.uri Like \"*generateContent*\")"}'
```

Bounds: `count` min 1 / max 15 / default 10, `tracesize` max 5120, `timeout`
min 60 / max 600 **seconds**. Passing 900 is rejected outright (*"debug session
timeout (900) should be >= minimum (60) seconds and <= maximum (600)
seconds"*). The `filter` is a flow-`Condition` expression evaluated against the
request.

**600 is what the API validates against, NOT necessarily what you get. Read
`validity` back off the create response and plan from that.** Observed on a
PAYG org (`subscriptionType: PAID`): `?timeout=600` was accepted with no error
and came back `"timeout": "300", "validity": 300` — silently halved. Whether
the 300 ceiling is tier-dependent or a platform change is not established.

This matters more than it sounds. The scenario it breaks is the common one —
arming a session, then going to drive an agent turn by hand. You believe you
have ten minutes, you have five, and the session expires into the *zero
transactions* state that this file teaches you to read as "the callout is not
landing". The wrong conclusion is right there and the clamp is invisible unless
you diff the response against the request.

## Read it back

```bash
curl -s -H "Authorization: Bearer $TOKEN" ".../debugsessions/$SESSION/data"
curl -s -H "Authorization: Bearer $TOKEN" ".../debugsessions/$SESSION/data/$TXN_ID"
```

**`/data` returns a BARE JSON LIST of transaction ids, not an object** -- `[]`
when nothing was captured. An empty list is a *meaningful result* here, not an
error.

**But `[]` does NOT prove the callout is dead. Corroborate before concluding
that, always.** Observed on a working proxy: every debug session on three
consecutive revisions returned `[]` while traffic flowed and was demonstrably
governed -- four sessions, one armed 75 seconds before traffic and polled for
over three minutes. The callout was landing; the tracing was not recording it.
Cause unknown, and not propagation delay.

This is the dangerous shape, because the AuthzExtension is `failOpen: true`:
a genuinely dead callout also looks like healthy traffic, so `[]` plus
"turns succeed" is exactly what both states look like. An operator trusting
`[]` alone will chase a networking fault that does not exist.

**The cheap corroboration is a refusal probe.** Send a prompt the governance
layer must refuse -- an injection, if Model Armor is on -- and look at the
error:

- A refusal carrying an Apigee fault (`400`, `errorcode:
  steps.sanitize.user.prompt.FilterMatched`) proves the proxy is in the path.
  Only Apigee produces that. The callout lands; your tracing is broken.
- No refusal, or a generic gateway error, is consistent with a dead callout.

Only after the probe fails should `[]` be read as "the callout is not
landing".
A helper written as `d.get("responses") or d.get("data")` raises
`AttributeError: 'list' object has no attribute 'get'` on precisely that case,
sending you to debug your own parser instead of the callout. Handle both
shapes. The ids come from `/data`; the flow variables below come from
`/data/$TXN_ID`, one fetch per transaction.

## What to confirm, in order

0.  **A known-good baseline turn, captured BEFORE any of the build runs.**
    Drive one agent turn and record that it succeeded. This checklist otherwise
    assumes the only question is *does the new thing work*, when the question
    that actually arises is *did the new thing break something that used to
    work* -- and with no pre-build invocation in the logs there is nothing to
    compare against. It matters here more than usual because
    `ensure_gateway_connectivity.sh` makes a **one-way** change to a gateway
    that is already carrying live agent traffic.

    When you do reach for log archaeology, **match on the status NAME**
    (`UNAUTHENTICATED`, `PERMISSION_DENIED`), never the numeric code. Cloud
    Logging's `:` is a substring match and agent-engine streams carry Docker
    digests, so `textPayload:"401"` matches the hex in a layer id like
    `1940178d9f4c`. That produced three convincing hits timestamped before any
    change and a confident, wrong "pre-existing failure" conclusion; searching
    `UNAUTHENTICATED` moved the first real occurrence to *after* the change.
1.  **The gateway has `networkConfig`.** Check this before reading any trace —
    if it is absent there will be no transactions to read, because the gateway
    has no route into the VPC. `describe ... --format='value(networkConfig)'`
    printing nothing is the symptom; `scripts/ensure_gateway_connectivity.sh` is
    the fix.
2.  **The PreFlow steps ran at all.** If not, the callout isn't landing — check
    the three hostnames and that the proxy is deployed. Also check the order
    they were created in: **the AuthzExtension is inert until the host resolves
    and the proxy is deployed**, so one created before those existed reports no
    error and simply never fires. Its existence is not evidence it works.
3.  **`request.content` and `response.content` are populated.** Empty means the
    `apigee-request-body` / `apigee-response-body` metadata is missing from the
    AuthzExtension.
4.  **`agw.model_name` is the bucket you expect.** `other` is now a real,
    metered bucket rather than a hole — but it still means the name matched
    neither `pro`/`argon` nor `flash`/`hydrogen`, so check it is deliberate. On
    a Gemini turn `other` means the normalization didn't find the model where it
    looked.
5.  **`agw.token_source` names the branch that matched** — `gemini`, `openai`,
    `sum`, or `none`. `none` is the diagnostic: the count was not found in any
    known shape, `agw.total_tokens` is deliberately left unset, and the quota
    will raise `FailedToResolveTokenUsageCount` rather than meter a silent
    zero. Check this before suspecting the quota itself.
6.  **`agw.total_tokens` is numeric and the matching counter incremented.**
    Pair it with `agw.token_source`: a count with no counter movement means
    the bucket has no quota bound to it.
7.  **`agw.user_prompt` is set on any request Model Armor or the cache will
    see.** It comes from `feature-normalize` at priority 15. Unset means
    either the body shape is unrecognised or that feature is missing from the
    template — and with Model Armor enabled the second case is a 500 per
    request, not a skipped scan.
8.  **Gated steps are skipped on non-model calls.** Only observable if the
    AuthzPolicy matches broadly — under a model-call-only suffix list those
    calls never reach Apigee, so there is nothing to see. Where they do arrive, a step
    skipped on `appendEvent` or `/v1/traces` is the gate working, not a failure.
9.  **With the cache ON and more than one shape configured: on a
    `cache_hit = true`, `agw.requested_model` matches the shape of the request
    that produced it.** Today it will not — the cache key is the prompt
    embedding alone, so the first model to answer a prompt answers it for all
    of them. A mismatch here is the proxy-side signature of the empty-answer
    symptom in `gotchas.md`; the caller sees a 200 with no content and nothing
    in the agent is wrong. Check this before believing a dual-shape cache
    demo.
10. **On any refusal path, read the body the CALLER receives — not just the
    variables going in.** Checks 1-9 are all inbound: did the policies run,
    did the bodies arrive, is the bucket right. Not one asks what comes back
    out, and every refusal path in this skill *composes a response*: Model
    Armor's 400, the quota's 429. Those are the only parts of the proxy an end
    user ever sees.

    This gap shipped a real defect. Enforcement was verified clean — 429,
    counters correct, model never called — while the fault body handed the
    caller the full `principal://...` assertion with org number, project
    number and the agent's resource id. `agw.client_id` was visible in three
    separate traces and nobody connected it to the fault body, because nothing
    asked them to look at the fault body.

    Concretely: take the terminal response `content` of a refused transaction
    and grep it for `principal://`, your project number and your org number.
    For the quota path that is now a regression test. For Model Armor it is
    worth running once — what its faultstring exposes has not been checked.
    `scripts/read_debug_session.sh` prints this body for any non-2xx
    transaction so it is in front of you rather than one fetch away.

## Verifying enforcement

Enforcement is opt-in, and the only feature here that fails **closed**. Two
things mislead people who turn it on, both avoidable:

**It is one request LATE by construction.** The turn that crosses the budget
completes normally and returns 200; the *next* request from that caller is
refused. Sending one over-budget turn, seeing a 200 and concluding enforcement
is broken is the common mistake. A token budget cannot be enforced before the
tokens are known.

**Read the `enforce-*` counters, not the `metering-*` ones.** The metering
policies are `CountOnly`, and a CountOnly quota reports
`allowed.count = 9223372036854775807` — max int64. That is correct for
counting without a ceiling, and it looks exactly like "no limit is applied".
The ceiling lives on the request-flow `EnforceOnly` policy.

The procedure:

1. Arm a session: `scripts/read_debug_session.sh ... --arm`.
2. Drive turns against one caller until the budget is crossed. Watch
   `ratelimit.enforce-LTQ-<bucket>.used.count` climb past `allowed.count`.
3. Expect the refusal on the **following** turn: `429`, errorcode
   `policies.llmtokenquota.LLMTokenQuotaViolation`, and no model call in the
   trace.
4. Confirm the executed steps stop at the quota — nothing after
   `enforce-LTQ-<bucket>` runs, because those policies are
   `continueOnError: false`.
5. Apply check 10 to the 429 body.

A worked example, flash budget 500/hour: `used.count 1086`,
`allowed.count 500`, `exceed.count 586`, `failed true`,
`error.state PROXY_REQ_FLOW`. The request-path `EnforceOnly` policy read the
count the response-path `CountOnly` policy accumulated under the same
`SharedName`, which is also the proof that `SharedName` joins the two halves
in a no-route proxy.

## Measure proxy-side, not from the caller

Timing the agent does not show you what the proxy did. On one semantic-cache
miss/hit pair the client saw 15445 ms versus 13114 ms — a 15% difference
indistinguishable from noise — while the proxy-side spans for the same two
calls were 1396 ms and 382 ms, a 3.7x gap. Agent session setup dominates the
round trip and hides everything the proxy changed.

Take the elapsed figure from the debug session's transaction, not from the
client, for any latency claim about the cache or a policy.

## Checking deployment type

```bash
curl -s -H "Authorization: Bearer $TOKEN" ".../environments/$ENV/deployments"
```

`proxyDeploymentType: EXTENSIBLE` is required. `STANDARD` will not govern the
agent's off-Apigee tool egress, and a tool policy that "doesn't fire" is usually
this.

## Offline check

Before any of the above, validate the template compiles and holds its invariants
— no org needed:

```bash
# Needs PyYAML -- the script names the interpreter if it is missing.
# pip install pyyaml, or use a python3 that has it. See gotchas.md.
python3 scripts/compile_check.py assets/apigee-proxy-template.yaml
```
