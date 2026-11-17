# Live API `ClientMessage` and `ServerMessage` Reference

This document describes the **wire-level WebSocket JSON protocol** for the
Gemini Enterprise Agent Platform Live API
(`LlmBidiService/BidiGenerateContent`).

Canonical reference docs:

- [Live API reference](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/models/live-api.md.txt)
- [RPC reference (`google.cloud.aiplatform.v1`)](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rpc/google.cloud.aiplatform.v1)
- [Start and manage live sessions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api/start-manage-session.md.txt)
- [Migrate from Gemini 2.5 to Gemini 3.8 Live](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api/migrate-from-gemini-2-5-to-gemini-3-8-live.md.txt)
- [Asynchronous function calling](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api/asynchronous-function-calling.md.txt)
- [Configure language and voice](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api/configure-language-voice.md.txt)
- [Live API best practices](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api/best-practices.md.txt)

## Table of Contents

1. [Connection, Endpoints, and Models](#1-connection-endpoints-and-models): Lines 35-69
2. [Top-Level Envelopes (`ClientMessage` and `ServerMessage`)](#2-top-level-envelopes-clientmessage-and-servermessage): Lines 71-101
3. [Session Lifecycle](#3-session-lifecycle): Lines 103-134
4. [`BidiGenerateContentSetup` (`setup`)](#4-bidigeneratecontentsetup-setup): Lines 136-206
5. [`BidiGenerateContentClientContent` (`clientContent`)](#5-bidigeneratecontentclientcontent-clientcontent): Lines 208-224
6. [`BidiGenerateContentRealtimeInput` (`realtimeInput`)](#6-bidigeneratecontentrealtimeinput-realtimeinput): Lines 226-243
7. [`BidiGenerateContentToolResponse` (`toolResponse`) and Function Calling](#7-bidigeneratecontenttoolresponse-toolresponse-and-function-calling): Lines 245-264
8. [`BidiGenerateContentContextUpdate` (`contextUpdate`)](#8-bidigeneratecontentcontextupdate-contextupdate): Lines 266-279
9. [Server Messages (`setupComplete`, `serverContent`, `toolCall`, `voiceActivity`)](#9-server-messages-setupcomplete-servercontent-toolcall-voiceactivity): Lines 281-315
10. [Lifecycle and Accounting (`GoAway`, `SessionResumptionUpdate`, `UsageMetadata`)](#10-lifecycle-and-accounting-goaway-sessionresumptionupdate-usagemetadata): Lines 317-334
11. [End-to-End JSON Wire Examples](#11-end-to-end-json-wire-examples): Lines 336-420
12. [Realtime vs. Add-Context Input Cookbook](#12-realtime-vs-add-context-input-cookbook): Lines 422-484
13. [Common Pitfalls](#13-common-pitfalls): Lines 486-504

---

## 1. Connection, Endpoints, and Models

### Endpoints

| Channel | WebSocket URI | When to use |
| --- | --- | --- |
| **GA (`v1`, default)** | `wss://{LOCATION}-aiplatform.googleapis.com/ws/google.cloud.aiplatform.v1.LlmBidiService/BidiGenerateContent` | Default for all standard Live API sessions (`gemini-3.8-live`, `gemini-live-2.5-flash-native-audio`, etc.). |
| **Preview (`v1beta1`)** | `wss://{LOCATION}-aiplatform.googleapis.com/ws/google.cloud.aiplatform.v1beta1.LlmBidiService/BidiGenerateContent` | Use when configuring `v1beta1`-only tools such as Vertex RAG Engine (`retrieval.vertexRagStore`). |

> **Regional endpoints required:** Live API models only support regional
> endpoints in US and EU multi-regions (recommended default: `us-central1`; for
> example, `europe-west4` in EU). Live API models do **not** support the
> `global` endpoint (`wss://aiplatform.googleapis.com/...`).

### Authentication & Wire Framing

- **Header**: `Authorization: Bearer <ADC access token>` on the WebSocket HTTP
  upgrade request (refresh before expiry and re-attach on every reconnect).
- **Wire format**: Every frame is a **JSON-serialized protobuf text message**
  (UTF-8 WebSocket text frame) matching `ClientMessage` (client -> server) or
  `ServerMessage` (server -> client) from `client_server_messages.proto`. Never
  send binary-encoded protobuf bytes (`SerializeToString()`). When parsing
  server JSON frames into `ServerMessage`, ignore unknown fields
  (`ignore_unknown_fields=True` in Python `google.protobuf.json_format.Parse`)
  for forward compatibility.

### Supported Models

| Model ID | Status | Key Capabilities & Behavioral Notes |
| --- | --- | --- |
| `gemini-3.8-live` | **GA (Recommended)** | Native audio I/O, VAD, affective dialog & proactive audio **always enabled by default**, `contextUpdate` (mid-session instructions/tools), `NON_BLOCKING` & `BLOCKING` function calling, custom vocabulary. |
| `gemini-live-2.5-flash-native-audio` | **GA** | Native audio I/O, transcriptions, VAD, opt-in `enableAffectiveDialog` & `proactivity.proactiveAudio`, function calling. |
| `gemini-3.5-transcribe-live-preview` | **Preview** | Dedicated low-latency speech-to-text streaming (`inputTranscription` / `interimInputTranscription`), `VERBATIM` & `SMART` modes, custom vocabulary. |

---

## 2. Top-Level Envelopes (`ClientMessage` and `ServerMessage`)

### `ClientMessage` (client -> server)

Each client frame sets **exactly one** `message_type` oneof field:

| JSON Field | Proto Type | When to use |
| --- | --- | --- |
| `setup` | `BidiGenerateContentSetup` | First frame only. Configures model, voice, tools, VAD, resumption, and transcriptions. |
| `clientContent` | `BidiGenerateContentClientContent` | Turn-based, history-bearing input (typed turns, uploaded clips/images, seeded history). Interrupts active model output. |
| `realtimeInput` | `BidiGenerateContentRealtimeInput` | Continuous, low-latency audio/video/text stream + manual VAD markers. |
| `toolResponse` | `BidiGenerateContentToolResponse` | Replies to server-issued `toolCall` requests. |
| `contextUpdate` | `BidiGenerateContentContextUpdate` | Updates `systemInstruction` and/or `tools` mid-session (`gemini-3.8-live`). |

### `ServerMessage` (server -> client)

Each server frame carries one `message_type` event (and may carry top-level
`usageMetadata`):

| JSON Field | Proto Type | Meaning |
| --- | --- | --- |
| `setupComplete` | `BidiGenerateContentSetupComplete` | Sent once after `setup` succeeds. Gate all subsequent sends on this. |
| `serverContent` | `BidiGenerateContentServerContent` | Streamed model output (`modelTurn`), `inputTranscription` / `outputTranscription` / `interimInputTranscription`, `interrupted`, `generationComplete`, `turnComplete`. |
| `toolCall` | `BidiGenerateContentToolCall` | Requests client execution of one or more `FunctionCall`s. |
| `toolCallCancellation` | `BidiGenerateContentToolCallCancellation` | Cancels previously issued `FunctionCall.id`s (typically on user barge-in). |
| `goAway` | `GoAway` | Connection will close soon (`timeLeft`, typically ~60s before the 10-minute WebSocket limit). |
| `sessionResumptionUpdate` | `SessionResumptionUpdate` | Checkpoint `newHandle` and `lastConsumedClientMessageIndex` for transparent reconnects. |
| `voiceActivity` | `VoiceActivity` | Server VAD `ACTIVITY_START` / `ACTIVITY_END` signal (when `setup.explicitVadSignal = true`). |
| `usageMetadata` | `UsageMetadata` | Token counts across prompt, candidate, thought, cached, and tool-use modalities. |

---

## 3. Session Lifecycle

```text
Client                                                Server
  |-- ClientMessage { setup } -----------------------> |
  | <------------------ ServerMessage { setupComplete }|
  |-- contextUpdate / clientContent / realtimeInput -> |
  | <-------- serverContent (modelTurn, transcripts) --|
  | <-------- serverContent { generationComplete } ----|
  | <-------- serverContent { turnComplete } ----------|
  | <-------- toolCall { functionCalls[] } ------------|
  |-- toolResponse { functionResponses[] } ----------> |
  | <-------- sessionResumptionUpdate { newHandle } ---|
  | <-------- goAway { timeLeft: "60s" } --------------|
  |   (reconnect with setup.sessionResumption.handle)  |
```

**Core protocol rules:**
1. **First frame**: Must be `setup`. Wait for `setupComplete` before sending any
   `realtimeInput`, `clientContent`, `toolResponse`, or `contextUpdate`.
2. **Connection vs. session limits**: A single WebSocket connection lasts up to
   **10 minutes** (`goAway` arrives ~60 seconds before termination). Without
   context compression, session context is capped at **15 minutes**; enable
   `contextWindowCompression.slidingWindow` + `sessionResumption` to extend
   sessions indefinitely across reconnects.
3. **Mid-session instruction updates**: In `gemini-3.8-live`, `role: "system"`
   in `clientContent` is **not supported**; always use `contextUpdate`.
4. **Initial history seeding**: In `gemini-3.8-live`, set
   `setup.historyConfig.initialHistoryInClientContent = true` if you will send
   prior conversation turns via `clientContent` after `setupComplete`.

---

## 4. `BidiGenerateContentSetup` (`setup`)

| JSON Field | Type | Notes |
| --- | --- | --- |
| `model` | `string` (required) | `projects/{project}/locations/{location}/publishers/google/models/{model_id}`. |
| `generationConfig` | `GenerationConfig` | Response modality, sampling, `speechConfig`, `mediaResolution`, `enableAffectiveDialog`. |
| `systemInstruction` | `Content` | Developer instructions (`parts[].text` only). |
| `tools[]` | repeated `Tool` | `functionDeclarations`, `googleSearch`, `codeExecution`, `urlContext`, `retrieval`, etc. Cannot mix `googleSearch` with `functionDeclarations`. |
| `sessionResumption` | `SessionResumptionConfig` | `{ handle?: string, transparent?: bool }`. Set `transparent: true` for lossless buffer replay. |
| `contextWindowCompression` | `ContextWindowCompressionConfig` | `{ triggerTokens?: int64, slidingWindow?: { targetTokens?: int64 } }`. Required for sessions >15 min. |
| `realtimeInputConfig` | `RealtimeInputConfig` | VAD sensitivity, barge-in (`activityHandling`), and `turnCoverage`. |
| `inputAudioTranscription` | `AudioTranscriptionConfig` | Enables `serverContent.inputTranscription` (and `interimInputTranscription`). Supports `languageCodes`, `customVocabulary`, `mode`. |
| `outputAudioTranscription` | `AudioTranscriptionConfig` | Enables `serverContent.outputTranscription`. |
| `explicitVadSignal` | `bool` | If `true`, server emits top-level `voiceActivity` messages on speech start/end. |
| `proactivity` | `ProactivityConfig` | `{ proactiveAudio?: bool }`. Always on in `gemini-3.8-live`; configurable on `gemini-live-2.5-flash-native-audio`. |
| `historyConfig` | `HistoryConfig` | `{ initialHistoryInClientContent?: bool }`. Set `true` when seeding history in `gemini-3.8-live`. |
| `safetySettings[]` | repeated `SafetySetting` | `{ category, threshold, method? }`. |
| `labels` | `map<string, string>` | Billing/reporting resource labels. |

### `GenerationConfig` (Live API subset)

| JSON Field | Type | Notes |
| --- | --- | --- |
| `responseModalities[]` | repeated enum | `AUDIO` (default) or `TEXT`. Pick one primary output mode per session. |
| `temperature`, `topP`, `topK`, `maxOutputTokens`, `seed` | numeric | Standard sampling controls (`temperature` 0.0–2.0). |
| `speechConfig` | `SpeechConfig` | Voice and language settings when outputting audio. |
| `mediaResolution` | enum | `MEDIA_RESOLUTION_LOW` (64 tokens), `MEDIA_RESOLUTION_MEDIUM` (256 tokens), `MEDIA_RESOLUTION_HIGH` (256 tokens + zoomed reframing). |
| `enableAffectiveDialog` | `bool` | Emotion-aware responses. Always enabled by default on `gemini-3.8-live`; opt-in on `2.5` native-audio. |

> **Unsupported in Live `setup.generationConfig`:** `responseLogprobs`,
> `responseMimeType`, `logprobs`, `responseSchema`, `stopSequences`,
> `routingConfig`, `audioTimestamp`.

### `SpeechConfig` & `VoiceConfig`

| JSON Field | Type | Notes |
| --- | --- | --- |
| `voiceConfig.prebuiltVoiceConfig.voiceName` | `string` | Case-sensitive name from the 30 prebuilt voices below (e.g., `"Aoede"`, `"Puck"`, `"Charon"`). |
| `languageCode` | `string` | Optional BCP-47 output language/accent code (e.g., `"en-US"`, `"en-IN"`, `"ja-JP"`). Native-audio models auto-detect and switch languages dynamically when omitted; set explicitly to pin a specific regional accent or default session language so setup does not fall back to `"en-US"`. |

**30 Prebuilt Voices** (case-sensitive; see [Configure language and voice](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api/configure-language-voice.md.txt)):
`Zephyr`, `Puck`, `Charon`, `Kore`, `Fenrir`, `Leda`, `Orus`, `Aoede`,
`Callirrhoe`, `Autonoe`, `Enceladus`, `Iapetus`, `Umbriel`, `Algieba`,
`Despina`, `Erinome`, `Algenib`, `Rasalgethi`, `Laomedeia`, `Achernar`,
`Alnilam`, `Schedar`, `Gacrux`, `Pulcherrima`, `Achird`, `Zubenelgenubi`,
`Vindemiatrix`, `Sadachbia`, `Sadaltager`, `Sulafat`.

### `AudioTranscriptionConfig`

Pass `{}` to enable default verbatim transcription, or customize:

- `languageCodes[]`: BCP-47 hints (e.g., `["en-US", "es-US"]`); omit for
  auto-detection.
- `customVocabulary[]`: Up to 1,000 domain-specific terms, product names, or
  acronyms to bias speech recognition (`gemini-3.8-live` and
  `gemini-3.5-transcribe-live-preview`).
- `mode`: `VERBATIM` (default) or `SMART` (disfluency removal and formatting).

### `RealtimeInputConfig` and `AutomaticActivityDetection`

- `automaticActivityDetection`: Configures `disabled`,
  `startOfSpeechSensitivity` (`START_SENSITIVITY_HIGH` or `LOW`),
  `endOfSpeechSensitivity` (`END_SENSITIVITY_HIGH` or `LOW`),
  `prefixPaddingMs`, and `silenceDurationMs`. Server-side VAD is enabled when
  `disabled` is unset or `false`.
- `activityHandling`: `START_OF_ACTIVITY_INTERRUPTS` (default barge-in) or
  `NO_INTERRUPTION`.
- `turnCoverage`: `TURN_INCLUDES_ALL_INPUT` (default) or
  `TURN_INCLUDES_ONLY_ACTIVITY`.

---

## 5. `BidiGenerateContentClientContent` (`clientContent`)

Appends discrete `Content` turns (`role: "user"` or `"model"`) to session
history.

| JSON Field | Type | Notes |
| --- | --- | --- |
| `turns[]` | repeated `Content` | Ordered oldest -> newest. In `gemini-3.8-live`, `role: "system"` is rejected (use `contextUpdate`). |
| `turnComplete` | `bool` | `true` starts generation immediately; `false` buffers context without generating yet. |

> **Seeding initial history (`gemini-3.8-live`):** Set
> `setup.historyConfig.initialHistoryInClientContent = true` in `setup`, wait
> for `setupComplete`, and send prior turns in `clientContent` (`turnComplete:
> false` if seeding silently before starting live audio, or `true` to prompt an
> immediate reply).

---

## 6. `BidiGenerateContentRealtimeInput` (`realtimeInput`)

Continuous, low-latency streaming input. Set **one** payload field per frame:

| JSON Field | Type | Notes |
| --- | --- | --- |
| `audio` | `Blob` | `mimeType: "audio/pcm;rate=16000"` (16-bit signed, 16 kHz, mono, little-endian PCM, ~20–100 ms chunks). |
| `video` | `Blob` | Sampled image frames (`image/jpeg`, `image/png`, `image/webp`) at ~1 fps. Do not send MP4/WebM containers. |
| `text` | `string` | Low-latency text input streamed into the active session. |
| `audioStreamEnd` | `bool` | Flushes cached audio when the mic is muted/stopped (auto-VAD enabled only). |
| `activityStart` / `activityEnd` | `{}` | Manual utterance boundaries (only valid when `automaticActivityDetection.disabled: true`). |
| `mediaChunks[]` | repeated `Blob` | **Deprecated.** Use `audio` or `video` instead. |

**Audio I/O formats:** Input is **16 kHz** 16-bit signed mono PCM
(`audio/pcm;rate=16000`); model audio output in `serverContent.modelTurn` is
**24 kHz** 16-bit signed mono PCM (`audio/pcm;rate=24000`).

---

## 7. `BidiGenerateContentToolResponse` (`toolResponse`) and Function Calling

Declare functions in `setup.tools[].functionDeclarations[]` (or update via
`contextUpdate`). When the server sends `toolCall`, reply via `toolResponse`
(never `clientContent`):

| Message / Field | Values & Behavior |
| --- | --- |
| `FunctionDeclaration.behavior` | `NON_BLOCKING` (Live API default: model keeps speaking/listening while tool executes asynchronously) \| `BLOCKING` (`gemini-3.8-live`: pauses conversation until `toolResponse` arrives; canceled via `toolCallCancellation` if user barges in). |
| `FunctionResponse.id` | Must match the originating `FunctionCall.id`. |
| `FunctionResponse.scheduling` | Controls `NON_BLOCKING` delivery: `WHEN_IDLE` (default — waits until model finishes speaking), `INTERRUPT` (interrupts model output; if user is currently speaking in `gemini-3.8-live`, waits for user to finish), or `SILENT` (adds to context without generating). Note: `gemini-3.8-live-extended-thinking-preview` does not support explicit `FunctionResponse.scheduling`. |
| `FunctionResponse.parts[]` | Optional multimodal blobs/URIs (`inlineData` / `fileData`) alongside `response` JSON. |

> **Critical `gemini-3.8-live` anti-retry rule:** `gemini-3.8-live` actively
> retries or sweeps parameters 2–5x when a tool returns an empty or ambiguous
> payload like `{}` or `{"results": []}`. Always return structured status fields
> (`status`, `retryable: false`, and an explanatory `message` on empty/error
> results, or `status: "ok"` on success) and cap retries in `systemInstruction`.

---

## 8. `BidiGenerateContentContextUpdate` (`contextUpdate`)

Updates session preamble mid-stream in order with other inputs
(`gemini-3.8-live`):

| JSON Field | Type | Behavior |
| --- | --- | --- |
| `systemInstruction` | `Content` | Replaces `setup.systemInstruction`. Omit to keep existing instructions. |
| `tools` | `{ tools?: Tool[] }` | Wrapper message: omit `tools` to keep existing tools; set `"tools": {"tools": [...]}` to replace tools; set `"tools": {}` (or `{"tools": []}`) to clear all tools. |

> Updating `systemInstruction` or `tools` invalidates the server prefix cache;
> send `contextUpdate` only when instructions or tools actually change.

---

## 9. Server Messages (`setupComplete`, `serverContent`, `toolCall`, `voiceActivity`)

### `BidiGenerateContentSetupComplete` (`setupComplete`)

- `{ "sessionId": "..." }` — confirms session initialization; gate all client
  sends on receiving this message.

### `BidiGenerateContentServerContent` (`serverContent`)

| JSON Field | Type | Notes |
| --- | --- | --- |
| `modelTurn` | `Content` | Streamed model parts (`inlineData` 24 kHz PCM audio, `text`, or `thought: true` reasoning parts). |
| `generationComplete` | `bool` | Model finished generating tokens/audio for this turn (client playback buffer may still be draining). |
| `turnComplete` | `bool` | Logical end of the turn. |
| `turnCompleteReason` | enum | Reason turn ended (e.g., `NEED_MORE_INPUT`, `MALFORMED_FUNCTION_CALL`, `RESPONSE_REJECTED`, or safety enums). |
| `interrupted` | `bool` | User barged in — immediately stop audio playback, clear queued audio/unrendered transcript buffers, and close the active bubble. |
| `inputTranscription` | `Transcription` | `{ text, finished }`. Finalized/chunked user speech transcript. |
| `interimInputTranscription` | `Transcription` | `{ text, finished }`. Low-latency interim hypothesis updated while the user is still speaking. |
| `outputTranscription` | `Transcription` | `{ text, finished }`. Streamed transcript of model speech. |
| `speechState` | enum | `SPEECH` \| `NON_SPEECH` transitions on `realtimeInput.audio`. |
| `interactionStatus` | enum | Sent alongside `turnComplete`: `IN_PROGRESS` (background tool/reasoning still active) \| `IDLE` (all processing done). |
| `groundingMetadata` | object | Search / grounding citations when grounding tools are active. |

### `BidiGenerateContentToolCall` (`toolCall`) and `BidiGenerateContentToolCallCancellation` (`toolCallCancellation`)

- `toolCall.functionCalls[]`: `{ id, name, args }`.
- `toolCallCancellation.ids[]`: Stop in-flight work for these `id`s and do
  **not** send `toolResponse` for them.

### `VoiceActivity` (`voiceActivity`)

- `{ "type": "ACTIVITY_START" | "ACTIVITY_END", "audioOffset": "3.240s" }` —
  emitted when `setup.explicitVadSignal = true`.

---

## 10. Lifecycle and Accounting (`GoAway`, `SessionResumptionUpdate`, `UsageMetadata`)

- **`GoAway`**: `{ "timeLeft": "60s" }`. Proactively open a new WebSocket and
  resume using the latest `SessionResumptionUpdate.newHandle`.
- **`SessionResumptionUpdate`**: Carries `newHandle`, `resumable`, and
  `lastConsumedClientMessageIndex`. When `setup.sessionResumption.transparent =
  true`, prune buffered client messages up to `lastConsumedClientMessageIndex`.
- **`UsageMetadata`**:
  - Token counters: `promptTokenCount`, `candidatesTokenCount`,
    `totalTokenCount`, `toolUsePromptTokenCount`, `thoughtsTokenCount`,
    `cachedContentTokenCount`.
  - Per-modality breakdowns (`ModalityTokenCount[]` with `modality` and
    `tokenCount`): `promptTokensDetails`, `cacheTokensDetails`,
    `candidatesTokensDetails`, `toolUsePromptTokensDetails`.
  - `trafficType`: `ON_DEMAND`, `PROVISIONED_THROUGHPUT`,
    `ON_DEMAND_PRIORITY`, etc.

---

## 11. End-to-End JSON Wire Examples

### Session `setup` (`gemini-3.8-live` with transparent resumption, custom vocabulary & async tool)

```json
{
  "setup": {
    "model": "projects/my-proj/locations/us-central1/publishers/google/models/gemini-3.8-live",
    "generationConfig": {
      "responseModalities": ["AUDIO"],
      "speechConfig": {
        "voiceConfig": { "prebuiltVoiceConfig": { "voiceName": "Aoede" } }
      }
    },
    "systemInstruction": {
      "parts": [{ "text": "You are a concise voice assistant. Retry failed tools at most once." }]
    },
    "tools": [{
      "functionDeclarations": [{
        "name": "lookup_order",
        "description": "Looks up order status by ID.",
        "behavior": "NON_BLOCKING",
        "parametersJsonSchema": {
          "type": "object",
          "properties": { "order_id": { "type": "string" } },
          "required": ["order_id"]
        }
      }]
    }],
    "sessionResumption": { "transparent": true },
    "contextWindowCompression": {
      "triggerTokens": "100000",
      "slidingWindow": { "targetTokens": "50000" }
    },
    "inputAudioTranscription": {
      "customVocabulary": ["Cloud Run", "GKE", "AlloyDB"]
    },
    "outputAudioTranscription": {},
    "historyConfig": { "initialHistoryInClientContent": true }
  }
}
```

### Mid-session `contextUpdate`

```json
{
  "contextUpdate": {
    "systemInstruction": {
      "parts": [{ "text": "Switch to Spanish and keep answers under two sentences." }]
    }
  }
}
```

### Async `toolCall` & structured `toolResponse`

```json
// Server -> client
{
  "toolCall": {
    "functionCalls": [
      { "id": "call_1", "name": "lookup_order", "args": { "order_id": "ORD-99" } }
    ]
  }
}

// Client -> server
{
  "toolResponse": {
    "functionResponses": [{
      "id": "call_1",
      "name": "lookup_order",
      "scheduling": "WHEN_IDLE",
      "response": {
        "status": "ok",
        "retryable": false,
        "order": { "id": "ORD-99", "eta": "2026-11-08" }
      }
    }]
  }
}
```

---

## 12. Realtime vs. Add-Context Input Cookbook

Choose the input envelope based on whether you are streaming live media or
appending discrete turns:

| Aspect | `realtimeInput` | `clientContent` |
| --- | --- | --- |
| **Use case** | Live mic, camera/screen frames (~1 fps), push-to-talk | Typed chat turns, seeding history, discrete audio/image uploads |
| **Turn boundary** | Server VAD (default) or `activityStart` / `activityEnd` | Explicit `turnComplete: true` |
| **Barge-in effect** | Controlled by `realtimeInputConfig.activityHandling` | Immediately interrupts active model output |

### A. `realtimeInput` payloads

```json
// 1. Continuous mic chunk (16 kHz, 16-bit mono PCM)
{ "realtimeInput": { "audio": { "mimeType": "audio/pcm;rate=16000", "data": "<base64-pcm>" } } }

// 2. Mic muted / stream paused (auto-VAD enabled)
{ "realtimeInput": { "audioStreamEnd": true } }

// 3. Manual VAD utterance (requires automaticActivityDetection.disabled = true in setup)
{ "realtimeInput": { "activityStart": {} } }
{ "realtimeInput": { "audio": { "mimeType": "audio/pcm;rate=16000", "data": "<base64-pcm>" } } }
{ "realtimeInput": { "activityEnd": {} } }

// 4. Camera / screen frame (~1 fps JPEG/PNG/WebP)
{ "realtimeInput": { "video": { "mimeType": "image/jpeg", "data": "<base64-jpeg>" } } }

// 5. Realtime text
{ "realtimeInput": { "text": "Focus on the top-right chart." } }
```

### B. `clientContent` payloads

```json
// 1. Seeded multi-turn history (requires historyConfig.initialHistoryInClientContent = true on 3.8-live)
{
  "clientContent": {
    "turns": [
      { "role": "user", "parts": [{ "text": "Hi, my name is Sam." }] },
      { "role": "model", "parts": [{ "text": "Hello Sam! How can I help?" }] }
    ],
    "turnComplete": false
  }
}

// 2. Discrete user text + inline image + Cloud Storage URI
{
  "clientContent": {
    "turns": [{
      "role": "user",
      "parts": [
        { "text": "Compare this screenshot with the reference diagram:" },
        { "inlineData": { "mimeType": "image/jpeg", "data": "<base64-jpeg>" } },
        { "fileData": { "mimeType": "application/pdf", "fileUri": "gs://my-bucket/spec.pdf" } }
      ]
    }],
    "turnComplete": true
  }
}
```

---

## 13. Common Pitfalls

- **Sending binary protobuf frames** — the WebSocket accepts UTF-8 JSON text
  frames only (`MessageToJson` / `Parse`).
- **Using the `global` endpoint** — Live API models require a regional endpoint
  such as `us-central1`.
- **Sending frames before `setupComplete`** — causes immediate connection close.
- **Using `role: "system"` in `clientContent` on `gemini-3.8-live`** — rejected;
  use `contextUpdate` instead.
- **Seeding history without `historyConfig.initialHistoryInClientContent: true`**
  — required on `gemini-3.8-live`.
- **Returning `{}` in `FunctionResponse.response`** — causes `gemini-3.8-live`
  to retry/sweep tool arguments; always return `status`, `retryable`, and
  `message`.
- **Combining `googleSearch` and `functionDeclarations`** — unsupported in the
  same `setup.tools` list.
- **Ignoring `interrupted: true` or `Transcription.finished`** — flush queued
  24 kHz playback audio immediately on `interrupted: true`, and close/rotate UI
  transcript bubbles when `finished: true` arrives.
