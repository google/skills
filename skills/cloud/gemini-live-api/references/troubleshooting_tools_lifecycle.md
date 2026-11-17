# Tool Calling, Safety Filters, Lifecycle, Latency, and Cost

Root causes and fixes for malformed or looping tool calls, duplicate
`NON_BLOCKING` speech, early-acknowledgement ("filler") misfires, prompt/context
contamination, input safety false positives, WebSocket `1008`/`1011`/`goAway`
drops, `429` throttling, latency (`TTFT`) triage, and multi-turn audio token
cost optimization.

## Table of Contents

- [MALFORMED_FUNCTION_CALL on Complex Tool Arguments](#malformed_function_call-on-complex-tool-arguments): Lines 24-58
- [Redundant Tool Loops and Duplicate NON_BLOCKING Speech](#redundant-tool-loops-and-duplicate-non_blocking-speech): Lines 60-121
- [State-Machine Polarity Traps and Unbounded Routing Loops](#state-machine-polarity-traps-and-unbounded-routing-loops): Lines 123-149
- [Pre-Tool Early Acknowledgement (Filler) Misfires](#pre-tool-early-acknowledgement-filler-misfires): Lines 151-172
- [Test Prompt Ignored or Model Invents Unseen Data](#test-prompt-ignored-or-model-invents-unseen-data): Lines 174-201
- [Undeclared Google Search Deadlock and Mid-Session SI Updates](#undeclared-google-search-deadlock-and-mid-session-si-updates): Lines 203-239
- [Safety Refusals on custom_vocabulary](#safety-refusals-on-custom_vocabulary): Lines 241-258
- [WebSocket 1008, 1011, goAway Drops, and 429 Throttling](#websocket-1008-1011-goaway-drops-and-429-throttling): Lines 260-290
- [Latency (TTFT) Triage](#latency-ttft-triage): Lines 292-315
- [Multi-Turn Audio Token Cost Optimization](#multi-turn-audio-token-cost-optimization): Lines 317-336

--------------------------------------------------------------------------------

## MALFORMED_FUNCTION_CALL on Complex Tool Arguments

**Symptom:** Tool calls fail with `MALFORMED_FUNCTION_CALL` or dropped quotes /
closing brackets, sometimes accompanied by stray reasoning text.

**Root Cause:** Declaring a tool with a single `STRING` parameter (for example,
`query_dsl: STRING` or `payload: STRING`) and instructing the model inside
`system_instruction` to format a quote-heavy JSON or key-value mini-DSL string
causes the model to drop closing quotes or delimiters during real-time speech
generation.

### Fix

Always declare explicit typed schema properties (`OBJECT`, `ARRAY`, `ENUM`,
`BOOLEAN`, `INTEGER`) in `functionDeclarations[].parameters` (or
`parametersJsonSchema`) instead of encoding a mini-DSL inside a `STRING`.

```json
{
  "name": "search_flights",
  "description": "Search available flights for a route and cabin.",
  "parameters": {
    "type": "OBJECT",
    "properties": {
      "origin": { "type": "STRING" },
      "destination": { "type": "STRING" },
      "cabin": { "type": "STRING", "enum": ["ECONOMY", "BUSINESS", "FIRST"] },
      "nonstop_only": { "type": "BOOLEAN" }
    },
    "required": ["origin", "destination"]
  }
}
```

--------------------------------------------------------------------------------

## Redundant Tool Loops and Duplicate NON_BLOCKING Speech

**Symptom:**

-   The model invokes the same tool repeatedly with identical arguments in a
    loop.
-   With `NON_BLOCKING` tools, the assistant speaks a response while the tool
    runs and then speaks a second, duplicate answer when `toolResponse` arrives.

**Root Cause:**

1.  **State-machine bloat & contradictory directives:** Multi-hop deterministic
    state machines inside large `system_instruction` prompts combined with
    conflicting rules (*"ALWAYS call tools"* vs. *"Only one tool call per
    turn"*) push real-time native-audio models into repetitive tool loops.
2.  **Default `FunctionResponse` scheduling:** Returning a `NON_BLOCKING`
    `FunctionResponse` without `scheduling="SILENT"` instructs the server to
    trigger a new model generation turn when the response arrives, causing a
    duplicate spoken reply.

### Fix

1.  Move deterministic state transitions and retry counters into application
    code, and expose only the tools valid for the current conversation step.
2.  Set `scheduling="SILENT"` on transactional or background `FunctionResponse`
    payloads when the model has already acknowledged the action and only needs
    the result stored in context. (Note:
    `gemini-3.8-live-extended-thinking-preview` does not support explicit
    `FunctionResponse.scheduling`.)

```json
{
  "toolResponse": {
    "functionResponses": [{
      "id": "call_1",
      "name": "save_preference",
      "scheduling": "SILENT",
      "response": { "status": "saved", "retryable": false }
    }]
  }
}
```

```python
# Equivalent Python google-genai SDK call
await session.send_tool_response(
    function_responses=[
        types.FunctionResponse(
            id=call.id,
            name=call.name,
            response={"status": "saved", "retryable": false},
            scheduling=types.FunctionResponseScheduling.SILENT,
        )
    ]
)
```

3.  For small reference lists (`<= 50` items), include a compact lookup table in
    `system_instruction` or resolve entities via client-side retrieval before
    injecting results.

--------------------------------------------------------------------------------

## State-Machine Polarity Traps and Unbounded Routing Loops

**Symptom:** In branching voice workflows (such as triage or confirmation
flows), the assistant misroutes when the user says `"No"`, loops indefinitely
on ambiguous questions or unintelligible fragments, or leaks raw JSON routing
blocks.

**Root Cause:**

1.  **Question polarity inversion:** Asking `"Do you want to cancel your
    order?"` (`"No"` = keep order) followed immediately by `"To confirm, you
    want to keep your order, correct?"` (`"No"` = cancel order) without
    explicitly mapping `"No"` on the confirmation step causes the model to
    carry over the initial `"No"` intent.
2.  **Unbounded Q&A / forbidden same-state routing:** Prohibiting a routing tool
    from targeting the current state without a turn cap causes infinite loops or
    raw JSON fallback dumps when callers stay off-topic.

### Fix

1.  Keep confirmation question polarity consistent across turns, or explicitly
    specify both affirmative and negative branch targets in the tool response
    instructions.
2.  Enforce a bounded retry limit (for example, re-prompt once on unclear input,
    then escalate or transfer on the second consecutive unclear turn).

--------------------------------------------------------------------------------

## Pre-Tool Early Acknowledgement (Filler) Misfires

**Symptom:** Attempting to use natural-language `system_instruction` rules to
make the model speak a filler phrase (*"Let me look that up"*) before slow
tools (`3-5s`) while remaining silent before fast utility tools (`< 1s`) causes
frequent false-positive fillers on fast tools, silent execution on slow tools,
or double spoken sentences (empathy + filler) before a single tool call.

**Root Cause:** Natural-language filler rules inside large `system_instruction`
prompts cannot reliably discriminate tool latency tiers at decode time.

### Fix

1.  **Silent tools + client UI cue (recommended):** Instruct the model to
    invoke tools immediately without spoken filler, and play a lightweight
    client-side chime or visual indicator while awaiting `toolResponse`.
2.  **Uniform single-sentence acknowledgement:** If spoken acknowledgement is
    required before slow operations, keep it uniform rather than writing
    per-tool latency rules in `system_instruction`, and combine any empathy and
    waiting phrase into a single short sentence.

--------------------------------------------------------------------------------

## Test Prompt Ignored or Model Invents Unseen Data

**Symptom:**

-   Replacing `system_instruction` with a 1-line echo test prompt still causes
    the assistant to run the production workflow.
-   The assistant states user details (account tiers, dates, names) that are not
    in the prompt template and were never spoken by the user.

**Root Cause:**

1.  **Latent tool schemas:** Leaving production `tools` attached in
    `BidiGenerateContentSetup` acts as latent workflow instructions that
    outweigh a minimal 1-line `system_instruction`.
2.  **Client framework context contamination:** Agent frameworks or middleware
    often serialize extra session-state attributes (templates, script buffers,
    user profile objects) into the assembled setup or `clientContent` payload
    without appearing in the raw prompt file.

### Fix

1.  Remove or stub out `tools` when testing minimal or echo prompts in
    isolation.
2.  Log and inspect the **complete serialized wire JSON** (`setup`,
    `clientContent`, `toolResponse`) actually sent over the WebSocket rather
    than auditing only source prompt templates.

--------------------------------------------------------------------------------

## Undeclared Google Search Deadlock and Mid-Session SI Updates

**Symptom:**

-   Sessions stall for `8-10s` until idle timeout when the prompt demands
    search grounding.
-   Mid-session `clientContent` attempts to update instructions fail, trigger an
    unsolicited model reply, or erase earlier rules.

**Root Cause:**

1.  Instructing *"Ground answers to Google Search ONLY"* in `system_instruction`
    without declaring `{"googleSearch": {}}` in `setup.tools` causes the model
    to attempt an undeclared search call and stall waiting for a response. Note
    that on Live API, `googleSearch` **cannot** be combined with
    `functionDeclarations` in the same `setup.tools` configuration.
2.  `gemini-3.8-live` rejects `role="system"` in `clientContent` (mid-session
    instruction and tool updates must use `contextUpdate`, which replaces
    `setup.systemInstruction` in full). On `2.5` models, sending
    `turnComplete: true` on a context update immediately triggers an unsolicited
    spoken turn rather than quietly updating instructions for the next user
    utterance.

### Fix

1.  Either declare `{"googleSearch": {}}` alone in `setup.tools` (when no
    `functionDeclarations` are used), remove the Google Search mandate from
    `system_instruction`, or expose search behind a custom server-executed
    function declaration when combining search with other custom tools.
2.  On `gemini-3.8-live`, send a `contextUpdate`
    (`BidiGenerateContentContextUpdate`) frame carrying the **complete**
    replacement `systemInstruction` (and/or updated `tools`). On `2.5` models,
    reconnect or resume a session with the updated `setup.systemInstruction` at
    a turn boundary rather than sending `role="system"` or `turnComplete: true`
    in `clientContent`.

--------------------------------------------------------------------------------

## Safety Refusals on custom_vocabulary

**Symptom:** Spoken queries containing domain terms registered in
`inputAudioTranscription.customVocabulary` trigger an unexpected canned safety
refusal (*"I'm just a language model and can't help with that."*), while the
exact same audio passes when `customVocabulary` is omitted.

**Root Cause:** Concatenating multi-word domain phrases into synthetic
single-token compounds in `customVocabulary` can distort speech-recognition
subword tokenization and trigger false-positive input safety blocks.

### Fix

Keep multi-word phrases in `inputAudioTranscription.customVocabulary`
space-delimited as natural words rather than concatenating synthetic
single-token compounds.

--------------------------------------------------------------------------------

## WebSocket 1008, 1011, goAway Drops, and 429 Throttling

**Symptom:** Sessions terminate mid-call with WebSocket close codes `1008`
(Policy Violation), `1011` (Internal Error), `goAway`, or fail to connect during
traffic spikes with HTTP `429 RESOURCE_EXHAUSTED`.

**Root Cause:**

1.  **`1008` on setup:** Caused by unsupported `generationConfig` fields in Live
    API (`responseSchema`, `responseMimeType`, `responseLogprobs`, `logprobs`,
    `stopSequence`, `routingConfig`, `audioTimestamp`), an unknown or
    case-mismatched `voiceName`, or invalid `toolResponse` payloads.
2.  **`1008` / `goAway` mid-call:** Hitting the per-connection Live session
    duration limit (~10-15 minutes) without session resumption enabled.
3.  **`1011` / `429`:** Transient upstream disconnects without resumption, or
    unsmoothed outbound dialing / connection bursts exceeding regional QPM/RPM.

### Fix

1.  Audit `setup.generationConfig` against supported Live API fields, and verify
    case-sensitive `voiceName` spelling.
2.  Enable transparent session resumption (`sessionResumption: { transparent:
    true }`), track `sessionResumptionUpdate.newHandle` and
    `lastConsumedClientMessageIndex`, and reconnect automatically on `goAway`
    and close codes `1000`, `1006`, or `1011`. Follow the Session Manager
    reference (`references/session_manager.md`) linked from `SKILL.md` for the
    full buffering and replay state machine.
3.  Smooth connection bursts with jittered exponential backoff on `429`, and
    evaluate Provisioned Throughput for predictable high-concurrency workloads.

--------------------------------------------------------------------------------

## Latency (TTFT) Triage

**Symptom:** Time-to-first-audio-byte (`TTFT`) spikes from `< 1.5s` to `6-12s`,
causing idle timeouts.

**Root Cause:** Multi-second delays fall into three distinct buckets:
1.  **Client 3P tool latency:** Gap between receiving `toolCall` and sending
    `toolResponse`.
2.  **User barge-in overlap:** Caller resumes speaking before the server turn
    finishes.
3.  **Regional backend / prefix-cache latency:** Delay between `activityEnd` /
    `turnComplete` (or `toolResponse`) and the first `serverContent` chunk with
    no pending client tool calls.

### Fix

Log monotonic timestamps at `activityEnd` (or `clientContent`), `toolCall`,
`toolResponse`, and first `serverContent` audio chunk. Optimize slow client 3P
APIs (or mark non-critical calls `NON_BLOCKING` with `scheduling="SILENT"`). If
server latency spikes at flat QPS with no client tool delay, test an alternate
supported region and share session IDs + UTC timestamps with Google Cloud
Support.

--------------------------------------------------------------------------------

## Multi-Turn Audio Token Cost Optimization

**Symptom:** Multi-turn Live API call costs grow superlinearly as session
duration increases.

**Root Cause:** Live API retains prior model audio output tokens 1-for-1 as
audio input context across subsequent turns in the same session, and streams
continuous background audio when `TURN_INCLUDES_ALL_INPUT` is active.

### Fix

1.  Configure `contextWindowCompression` sliding windows to cap retained audio
    history.
2.  Rotate/reset long sessions at natural conversation boundaries.
3.  Set `realtimeInputConfig.turnCoverage = "TURN_INCLUDES_ONLY_ACTIVITY"` so
    long silent intervals are not retained in turn context.
4.  Offload pure text/data post-processing (summarization, classification) to
    non-audio `generateContent` calls.
5.  Review current rates and calculators on the
    [Google Cloud Pricing](https://cloud.google.com/pricing) page.
