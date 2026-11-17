---
name: gemini-live-api
metadata:
  version: "1.1.0"
  category: AiAndMachineLearning
description: >-
  Builds, integrates, and troubleshoots Gemini Enterprise Agent Platform Live
  API (BidiGenerateContent) WebSocket clients and sessions. Use when scaffolding
  a LiveAPI client or demo UI/backend (GA v1 WebSockets, isolated Python venv,
  ADC bearer token refresh, transparent session resumption, ClientMessage and
  ServerMessage JSON protos, tool responses, context_update, interrupt and
  transcription handling) or debugging Live API issues such as silent or empty
  turns, audio amplitude collapse, tonal humming, voice gender or accent drift,
  premature turn completion, barge-in failures, output_transcription leaks,
  malformed or looping tool calls, WebSocket 1008/1011/goAway drops, or latency
  spikes. Don't use for non-live, non-bidirectional Gemini API calls such as
  unary generateContent, embeddings, image/video generation, or fine-tuning —
  use the gemini-api skill for those.
---

> [!IMPORTANT]
> Gemini Enterprise Agent Platform was previously named "Vertex AI"; the API
> service endpoint remains `aiplatform.googleapis.com`.

# LiveAPI Service Skill

This skill provides instructions for generating a **LiveAPI client service
class** that connects to the Gemini Enterprise Agent Platform Live API over
WebSockets (`LlmBidiService/BidiGenerateContent`), as well as diagnosing and
resolving Live API runtime issues. The generated client handles bidirectional
JSON frame streaming, bearer-token authentication via Application Default
Credentials (ADC), transparent session resumption, tool call responses,
mid-session context updates, and `ClientMessage` / `ServerMessage` proto
exchange.

The skill also produces a demo frontend + backend service so the user can
interactively validate the generated client (text, audio, video, transcription,
and interrupt handling).

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Prerequisites

Before running the generation flow, verify or guide the user through the
following prerequisites (always ask for user approval before modifying host
configurations or installing system tools):

-   **Google Cloud Project & Billing**: An active Google Cloud project with a
    linked billing account (review [Gemini Enterprise Agent Platform pricing](https://cloud.google.com/products/gemini-enterprise-agent-platform/pricing)):

    ```bash
    gcloud config set project {project_id}
    ```

-   **API Enablement & IAM**: The `aiplatform.googleapis.com` API enabled on the
    project, and the caller principal granted at least Vertex AI User
    (`roles/aiplatform.user`):

    ```bash
    gcloud services enable aiplatform.googleapis.com
    ```

-   **Application Default Credentials (ADC)**: Configured on the host running
    the generated client (see [Google Cloud authentication](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/start/gcp-auth.md.txt)):

    ```bash
    gcloud auth application-default login
    ```

-   **Regional Location**: Default to `us-central1` unless the user specifies
    another supported US or EU region (e.g., `europe-west4`; see [supported locations](https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/locations.md.txt)).
    Live API models do **not** support the `global` endpoint.
-   **Isolated Output Directory**: A destination folder supplied by the user
    (e.g., `/tmp/liveapi_out`) where generated code, virtual environments, and
    the demo service will be written. **Never** mutate the host's system Python
    environment.
-   **Implementation Language**: Python is the default and reference language
    when the user does not specify another language.

## Supported Live API Models

-   **`gemini-3.8-live` (GA — Recommended default)**: Native audio I/O, VAD,
    affective dialog and proactive audio **always enabled by default**,
    `NON_BLOCKING` and `BLOCKING` function calling, mid-session
    `context_update`, and custom transcription vocabulary.
-   **`gemini-live-2.5-flash-native-audio` (GA)**: Native audio I/O,
    transcriptions, VAD, optional `generation_config.enable_affective_dialog`
    and `proactivity.proactive_audio`, and function calling.
-   **`gemini-3.5-transcribe-live-preview` (Preview)**: Dedicated low-latency
    speech-to-text streaming (`input_transcription` and
    `interim_input_transcription`) with `VERBATIM` and `SMART` modes and custom
    vocabulary.

## Reference Files

Load these files from `references/` on demand (do **not** treat them as
standalone skills):

-   [client_server_messages.md](references/client_server_messages.md): Wire
    protocol reference for `ClientMessage` / `ServerMessage`, model-specific
    `gemini-3.8-live` rules, and JSON examples.
-   [client_server_messages.proto](references/client_server_messages.proto):
    Proto3 schema derived from the public Live API documentation for generating
    typed `ClientMessage` and `ServerMessage` classes.
-   [session_manager.md](references/session_manager.md): Specification for
    connection lifecycle, 1-based message buffering, `go_away` handling, and
    transparent session resumption.
-   [Audio, Voice, Accent, and Quality Troubleshooting](references/troubleshooting_audio_voice.md):
    Prebuilt voice gender table, accent/locale fixes, amplitude collapse, tonal
    humming, and jitter buffering.
-   [Turns, VAD, Barge-In, and Transcriptions Troubleshooting](references/troubleshooting_turns_vad.md):
    `generationComplete` vs. `turnComplete`, `contextWindowCompression` readback
    settings, client stall nudges, backchannel gating, telephony VAD padding,
    and transcription/instruction leakage guards.
-   [Tool Calling, Safety Filters, Lifecycle, Latency, and Cost Troubleshooting](references/troubleshooting_tools_lifecycle.md):
    Typed schemas, `NON_BLOCKING` scheduling, state-machine polarity, pre-tool
    filler handling, safety filters, WebSocket `1008`/`1011` and `goAway`
    recovery, `TTFT` triage, and cost optimization.

## Steps

### Step 1: Copy the reference files

Copy `client_server_messages.md`, `client_server_messages.proto`, and
`session_manager.md` from this skill's `references/` folder into the user's
destination output folder. These files become the local source of truth for the
generated client.

### Step 2: Reconcile and compile the proto definitions

Check the public documentation linked in
[client_server_messages.md](references/client_server_messages.md). If any new
server fields are needed for the user's task, update the copied
`client_server_messages.md` and `client_server_messages.proto` in the
destination folder, and compile `client_server_messages.proto` (e.g., via
`grpc_tools.protoc` or `protoc`) into the destination folder.

### Step 3: Implement the client class and `SessionManager`

Implement a client service class in the user's chosen language that:

-   Imports the local compiled `client_server_messages.proto` types
    (`ClientMessage`, `ServerMessage`).
-   Connects over WebSockets to:
    `wss://{location}-aiplatform.googleapis.com/ws/google.cloud.aiplatform.{api_version}.LlmBidiService/BidiGenerateContent`
    where `api_version` defaults to `"v1"` (allow overriding to `"v1beta1"` for
    preview-only features such as Vertex RAG Engine).
-   Formats `setup.model` as
    `projects/{project_id}/locations/{location}/publishers/google/models/{model_id}`.
-   Serializes outgoing `ClientMessage` instances as **UTF-8 JSON text frames**
    (e.g., `google.protobuf.json_format.MessageToJson`) and parses incoming JSON
    text frames into `ServerMessage` with unknown fields ignored
    (`ignore_unknown_fields=True`). **Never** send binary protobuf bytes.
-   Implements transparent session resumption per
    [session_manager.md](references/session_manager.md) (including
    `context_window_compression.sliding_window` when sessions may exceed 15
    minutes).

For languages that require an isolated runtime (e.g., Python), create an
isolated environment (e.g., `venv`) **inside the destination folder** along with
a `requirements.txt` pinning exact compatible versions within tested bounds
(`websockets>=13.0,<16.0`, `protobuf>=5.29.0,<7.0.0`,
`google-auth>=2.35.0,<3.0.0`, `requests>=2.32.0,<3.0.0`,
`grpcio-tools>=1.68.0,<2.0.0`) and a runnable `setup.sh` script that creates the
`venv`, runs `pip install -r requirements.txt` (explicitly referencing
`requirements.txt`), and compiles `client_server_messages.proto`. **Never**
install into the system interpreter or user-global site-packages, and never
instruct the user to run `sudo pip install`.

#### Initialization parameters

Accept at construction time:

-   `project_id`: Google Cloud project ID.
-   `location`: Regional location (e.g., `"us-central1"`; reject `"global"`).
-   `model_id`: Live API model ID (e.g., `"gemini-3.8-live"`).
-   `config`: A `ClientMessage` with the `setup` field populated.
-   `api_version` (optional): Defaults to `"v1"` (supports `"v1beta1"`).

#### Authentication

Obtain an access token via Application Default Credentials with scope
`https://www.googleapis.com/auth/cloud-platform`, attach it to the WebSocket
handshake header as `Authorization: Bearer <token>`, refresh it before or upon
expiry, and attach the valid/refreshed token on every reconnection (including
`go_away` and close codes `1000`, `1006`, or `1011`). **Do not** hard-code a
long-lived API key as the only auth mechanism.

#### Public async API

Expose the following async methods, all gated on receipt of a `setup_complete`
`ServerMessage` before sending:

-   `send_realtime_data(data: ClientMessage)`: Send continuous low-latency
    media/text. `data` MUST be typed as `ClientMessage` carrying
    `realtime_input`.
-   `send_client_content(data: ClientMessage)`: Send discrete, history-bearing
    turns. `data` MUST be typed as `ClientMessage` carrying `client_content`.
    (On `gemini-3.8-live`, set
    `setup.history_config.initial_history_in_client_content = true` when seeding
    prior history, and never use `role="system"` in `client_content`.)
-   `send_tool_response(data: ClientMessage)`: Reply to a server `tool_call`.
    `data` MUST be typed as `ClientMessage` carrying `tool_response`. (On
    `gemini-3.8-live`, return informative status objects such as
    `{"status": "ok"|"not_found", "retryable": false, ...}` instead of empty
    `{}` to prevent retry sweeps.)
-   `send_context_update(data: ClientMessage)`: Update `system_instruction`
    and/or `tools` mid-session (`gemini-3.8-live`). `data` MUST be typed as
    `ClientMessage` carrying `context_update`.
-   `receive() -> AsyncIterator[ServerMessage]`: Async generator yielding
    `ServerMessage` instances parsed from the WebSocket stream.

Do not expose synchronous blocking variants as the primary API surface.

### Step 4: Write a test file

Generate a test file in the destination folder that initializes the client and
exercises `text`, `audio` (16 kHz PCM), `video` (sampled JPEG/PNG frames),
`send_tool_response`, and `send_context_update`, verifying `ServerMessage`
responses. Ask the user for any runtime inputs needed (`project_id`, model, or
sample media).

### Step 5: Generate `how_to_run.md`

Write `how_to_run.md` in the destination folder documenting the generated client
class, setup scripts, and complete examples building `ClientMessage` payloads
for realtime audio/video/text, `client_content` turns (including seeded
history), `tool_response` (async `scheduling` and structured responses), and
`context_update`.

### Step 6: Generate a demo frontend + backend service

Create a frontend UI and backend service in the destination folder that reuse
the local `ClientMessage` / `ServerMessage` protos from Step 1. Through the UI
the user must be able to:

-   Open and close a Live API session.
-   Select the model (defaulting to `gemini-3.8-live`).
-   Stream microphone audio (16 kHz mono PCM) and camera or screen frames (~1
    fps JPEG) to the model.
-   Send typed text messages.
-   Play back 24 kHz model audio and view interleaved user and model
    transcriptions.

Follow [Live API best practices](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api/best-practices.md.txt)
for audio capture, echo cancellation, and playback buffering.

#### Handling the `interrupt` signal

When `server_content` arrives with `interrupted: true`, the UI MUST:

-   Keep played audio and rendered transcription time-aligned.
-   Immediately stop currently playing model audio and stop appending to the
    in-progress model transcription bubble.
-   Clear unplayed audio buffers and queued unrendered transcription text so
    stale content never bleeds into the next turn.
-   Start fresh chat bubbles for subsequent user and model turns.

#### Handling the transcription `finished` signal

For streamed `input_transcription` and `output_transcription` chunks (and
optional `interim_input_transcription` previews), append text to the active
bubble while `finished` is unset/`false`, and close that bubble to start a fresh
one when `finished: true` arrives. Route `input_transcription` to user-role
bubbles and `output_transcription` to model-role bubbles.

### Step 7: Generate `how_to_test_with_ui.md`

Write `how_to_test_with_ui.md` in the destination folder with:

-   Exact shell command(s) to start the backend service.
-   Exact shell command(s) to start the frontend UI.
-   Browser URL (`http://localhost:PORT`).
-   Walkthrough for starting a session, selecting a model, streaming mic/camera/
    screen inputs, sending text, and verifying audio + transcription + barge-in.

## Validation Checklist

Verify every item before completing generation:

-   [ ] `client_server_messages.md`, `client_server_messages.proto`, and
    `session_manager.md` were copied into the destination folder.
-   [ ] The generated client compiles and imports the local `ClientMessage` and
    `ServerMessage` proto types, and exchanges UTF-8 JSON text frames
    (`MessageToJson` / `Parse` with unknown fields ignored).
-   [ ] The client connects to
    `wss://{location}-aiplatform.googleapis.com/ws/google.cloud.aiplatform.{api_version}.LlmBidiService/BidiGenerateContent`
    defaulting `api_version` to `"v1"` on a regional endpoint (never `global`),
    and formats `setup.model` as
    `projects/{project_id}/locations/{location}/publishers/google/models/{model_id}`.
-   [ ] Authentication uses ADC bearer tokens (`Authorization: Bearer <token>`),
    refreshes before expiry, and reattaches the valid token on every reconnect.
-   [ ] Public async methods `send_realtime_data`, `send_client_content`,
    `send_tool_response`, `send_context_update`, and `receive` are present,
    typed with `ClientMessage` / `ServerMessage`, and gated on `setup_complete`.
-   [ ] Transparent session resumption sets `session_resumption.transparent =
    true`, tracks `new_handle`, indexes buffered messages starting at `1`,
    prunes via `last_consumed_client_message_index`, and replays from index `1`
    on reconnect (`go_away` and WebSocket codes `1000` / `1006` / `1011`).
-   [ ] For Python, an isolated `venv`, `setup.sh`, and `requirements.txt` live
    inside the destination folder with zero changes to system/global Python.
-   [ ] `how_to_run.md` and `how_to_test_with_ui.md` exist, and the demo UI
    implements `interrupted: true` and `Transcription.finished` handling.
-   [ ] The client does **not** target `generativelanguage.googleapis.com` and
    does **not** pass API keys in URL query strings.

--------------------------------------------------------------------------------

## Troubleshooting Live API Issues

When debugging an existing Live API integration or runtime failure (rather than
scaffolding a new client from scratch), follow this diagnostic workflow before
making prompt tweaks.

### Diagnostic Workflow

1.  **Verify environment and model currency:** Confirm a regional endpoint
    (for example, `us-central1`; `global` is not supported for Live API
    WebSockets) and active billing ([Google Cloud Pricing](https://cloud.google.com/pricing)).
    Legacy `gemini-2.0-*` models and `gemini-live-2.5-flash` (half-cascade) are
    deprecated or shut down; test whether the symptom resolves on
    `gemini-3.8-live` or `gemini-live-2.5-flash-native-audio`.
2.  **Capture the full serialized wire payload:** Log the exact
    `BidiGenerateContentSetup` JSON, `clientContent`, `realtimeInput`,
    `toolResponse`, and `contextUpdate` frames actually sent over the WebSocket.
    Frameworks often inject extra session state or tool declarations absent from
    source prompt files.
3.  **Audit against Pre-Flight Configuration Rules:** Fix primary structural
    defects (gender mismatch, missing regional `languageCode`, low `temperature`
    + `generationConfig.enableAffectiveDialog`, bloated `tools` or
    `systemInstruction`) first.
4.  **Isolate optional flags and tools:** On
    `gemini-live-2.5-flash-native-audio`, temporarily disable
    `setup.proactivity.proactiveAudio` and
    `setup.generationConfig.enableAffectiveDialog` (both are built-in by default
    on `gemini-3.8-live` and should be omitted there), and stub out `tools` when
    testing minimal prompt behavior.
5.  **Reproduce and verify A/B:** Replay the failing turn sequence before and
    after 1-2 targeted changes, checking audio duration, PCM amplitude,
    `output_transcription`, and `turnComplete` signals.

### Quick Symptom Triage Matrix

| Symptom | Primary Suspect | Immediate Fix | Reference |
| --- | --- | --- | --- |
| Voice flips gender (Turn 1 or mid-call) | Prebuilt voice gender mismatches SI persona name/pronouns | Match `voiceName` gender to SI persona | [Audio & Voice](references/troubleshooting_audio_voice.md#voice-gender-swaps) |
| Accent reverts to `en-US`, pitch jumps, or code-mix fails | Omitted `speechConfig.languageCode` or long single-script SI | Set supported BCP-47 `languageCode` (e.g., `en-IN`) and concise SI | [Audio & Voice](references/troubleshooting_audio_voice.md#accent-reversion-pitch-jumps-and-code-mixed-switching) |
| Output mimics user's voice timbre | Native audio role leakage from user audio in context | Upgrade to `gemini-3.8-live`; clarify role boundaries; reconnect | [Audio & Voice](references/troubleshooting_audio_voice.md#output-voice-mimics-user-timbre) |
| Gradual voice/tone drift over long calls | Audio-token conditioning drift as history grows | Enable `contextWindowCompression` and rotate long sessions | [Audio & Voice](references/troubleshooting_audio_voice.md#multi-turn-voice-and-tone-drift) |
| Fast speech (240+ WPM) or raw `/IPA/` leaks | Long single-breath clauses, `2.5` affective dialog, or TTS markup in SI | Shorten clauses, strip TTS headers/IPA, or use `gemini-3.8-live` | [Audio & Voice](references/troubleshooting_audio_voice.md#fast-speech-rate-and-tts-markup-or-ipa-leaks) |
| Near-zero audio volume (`-34 dBFS`), intact text | Tool schemas `>40k` tokens or rolling text logs in SI | Prune `tools` to active turn/step, drop rolling text logs, keep SI `<2,000` tokens | [Audio & Voice](references/troubleshooting_audio_voice.md#near-zero-audio-amplitude-collapse) |
| `150-700 Hz` tonal hum or endless greeting | `temperature <= 0.3` with `2.5` `generationConfig.enableAffectiveDialog` | Set `temperature >= 0.7`, disable `2.5` affective dialog, open fresh session | [Audio & Voice](references/troubleshooting_audio_voice.md#tonal-humming-buzz-150-700-hz-and-non-terminating-greetings) |
| Choppy playback with `0.1-0.5s` gaps | Small variable WebSocket audio chunks played raw | Add a `~200 ms` client-side jitter buffer | [Audio & Voice](references/troubleshooting_audio_voice.md#choppy-playback-and-audio-jitter) |
| Premature `generationComplete` (`~0.75s`) or missing `turnComplete` | Advancing on `generationComplete`, `<verbatim>` tags, or history bloat | Wait for `turnComplete`, strip `<verbatim>` tags, add `contextWindowCompression` | [Turns & Transcripts](references/troubleshooting_turns_vad.md#premature-generationcomplete-and-missing-turncomplete) |
| `0` audio chunks after `toolResponse` (`>14k` tokens) | XML/JSON bloat diluting voice conditioning | Use prose SI, clean JSON tools, and `contextWindowCompression` | [Turns & Transcripts](references/troubleshooting_turns_vad.md#post-toolresponse-zero-audio-turns-in-deep-contexts) |
| Empty turns (`output_audio=0`) and `12-30s` wedges | `2.5` `proactivity.proactiveAudio` or client `3s` stall nudges | Disable `proactivity.proactiveAudio` on `2.5`; remove `3s` `clientContent` nudges | [Turns & Transcripts](references/troubleshooting_turns_vad.md#empty-turns-from-proactiveaudio-and-client-stall-nudges) |
| Turn-1 `output_transcription` dropped or silence placeholder leak | `realtimeInput.text` kickoff under `TURN_INCLUDES_ALL_INPUT` | Use `TURN_INCLUDES_ONLY_ACTIVITY` and `clientContent(turnComplete=True)` | [Turns & Transcripts](references/troubleshooting_turns_vad.md#turn-1-transcript-drops-and-prompt-template-newlines) |
| Unspoken Markdown or code in `output_transcription` | Post-speech text flush into UI / persisted transcripts | Set `languageCode`, ban Markdown in SI, strip trailing code blocks in UI | [Turns & Transcripts](references/troubleshooting_turns_vad.md#unspoken-markdown-or-code-tail-bursts-in-output_transcription) |
| Audible instruction leak pre-tool without transcript | Spoken pre-tool filler in `>70k`-token context | Call tools silently, strip `"speak..."` wrappers, compress context | [Turns & Transcripts](references/troubleshooting_turns_vad.md#pre-tool-filler-audible-leakage-without-transcripts) |
| Model speaks `<no speech>`, `{pause}`, or raw JSON | `NON_BLOCKING` missing `scheduling="SILENT"`, echo, or routing trap | Set `scheduling="SILENT"`, enable AEC, cap unclear turns | [Turns & Transcripts](references/troubleshooting_turns_vad.md#spoken-placeholder-tokens-and-raw-json-leaks) |
| Short `"Mm-hmm"` cuts off speech; double interrupt stalls | Acoustic barge-in firing on brief backchannels | Filter `<500 ms` backchannels client-side before streaming | [Turns & Transcripts](references/troubleshooting_turns_vad.md#short-backchannel-cutoffs-and-double-interruption-silence) |
| Final digits clipped (`"98058"` -> `"98050"`) | Manual VAD closing too fast on 8 kHz PSTN audio | Add `400-500 ms` hangover padding; confirm critical digits | [Turns & Transcripts](references/troubleshooting_turns_vad.md#manual-vad-tail-clipping-and-8-khz-telephony-distortion) |
| New turn plays over old turn after barge-in | Server finished fast without emitting `interrupted: true` | Flush client playback buffer on new turn start and on `interrupted` | [Turns & Transcripts](references/troubleshooting_turns_vad.md#barge-in-playback-overlap-and-background-noise-triggers) |
| `MALFORMED_FUNCTION_CALL` on complex args | Single `STRING` parameter used as mini-DSL | Use typed `OBJECT`, `ARRAY`, `ENUM`, `BOOLEAN` properties | [Tools & Lifecycle](references/troubleshooting_tools_lifecycle.md#malformed_function_call-on-complex-tool-arguments) |
| Tool loops or duplicate reply on `NON_BLOCKING` tool | State machine in SI or missing `scheduling="SILENT"` | Move state machine to app layer; set `scheduling="SILENT"` | [Tools & Lifecycle](references/troubleshooting_tools_lifecycle.md#redundant-tool-loops-and-duplicate-non_blocking-speech) |
| Unreliable pre-tool filler on fast vs. slow tools | Per-latency-tier natural-language filler rules in SI | Call tools silently and play a client-side UI/audio cue while waiting | [Tools & Lifecycle](references/troubleshooting_tools_lifecycle.md#pre-tool-early-acknowledgement-filler-misfires) |
| Minimal test prompt ignored or agent invents data | Production `tools` left attached or framework context leak | Stub `tools` in tests; audit full serialized wire JSON | [Tools & Lifecycle](references/troubleshooting_tools_lifecycle.md#test-prompt-ignored-or-model-invents-unseen-data) |
| Stall on search grounding or ignored SI update | Undeclared `googleSearch` (incompatible with custom functions) or `clientContent` SI update | Use `googleSearch` alone or custom search tool; use `contextUpdate` on `3.8-live` | [Tools & Lifecycle](references/troubleshooting_tools_lifecycle.md#undeclared-google-search-deadlock-and-mid-session-si-updates) |
| Safety refusal on `custom_vocabulary` | Synthetic concatenated single-token compounds distorting ASR | Keep multi-word phrases space-delimited in `custom_vocabulary` | [Tools & Lifecycle](references/troubleshooting_tools_lifecycle.md#safety-refusals-on-custom_vocabulary) |
| WebSocket `1008` / `1011` / `goAway` or `429` | Unsupported `generationConfig`, timeout, or burst traffic | Audit setup fields, enable `sessionResumption`, backoff on `429` | [Tools & Lifecycle](references/troubleshooting_tools_lifecycle.md#websocket-1008-1011-goaway-drops-and-429-throttling) |
| `6-12s` `TTFT` spike or high multi-turn audio cost | Client 3P tool delay, regional queue, or 1:1 audio token retention | Log per-stage timestamps; compress/rotate sessions; check pricing | [Tools & Lifecycle](references/troubleshooting_tools_lifecycle.md#latency-ttft-triage) |

### Pre-Flight Configuration Rules

1.  **Align voice gender with persona gender:** Match prebuilt `voiceName`
    gender with `systemInstruction` persona gender so acoustic and text
    conditioning do not compete.
2.  **Set `speechConfig.languageCode` when pinning a regional accent or default
    language:** While optional for dynamic multilingual auto-detection, omitting
    it defaults the initial voice reference to `en-US` and overrides text accent
    instructions. Use a supported BCP-47 code (such as `en-IN` or `es-US`).
3.  **Keep `temperature >= 0.7` (default `1.0`):** Values `<= 0.3` (especially
    when paired with `generationConfig.enableAffectiveDialog` on `2.5` models)
    trap native-audio sampling in tonal humming loops.
4.  **Keep `systemInstruction` `< 2,000` tokens and prune `tools` per turn:**
    Rolling text transcripts in SI and `>40,000`-token tool declarations dilute
    voice conditioning, causing `-34 dBFS` amplitude collapse and `0`-audio
    turns.
5.  **Write plain-spoken prose without markup:** Strip `#` Markdown headers,
    `<verbatim>` / `<taskflow>` XML, Gemini-TTS `# Director's Notes`, raw IPA
    `/slashes/`, and `"""` code delimiters so unspoken code or markup does not
    leak into `output_transcription`.
6.  **Separate prompt template blocks with `\n`:** Avoid concatenating adjacent
    template sections onto a single run-on line without newline separators.
7.  **Declare typed tool schemas:** Use `OBJECT`, `ARRAY`, `ENUM`, and `BOOLEAN`
    instead of packing mini-DSLs into a single `STRING` argument.
8.  **Set `scheduling="SILENT"` on transactional `NON_BLOCKING` responses:**
    Prevents duplicate speech or `<no speech>` leaks after async tool results
    (note: `gemini-3.8-live-extended-thinking-preview` does not support explicit
    `FunctionResponse.scheduling`).
9.  **Wait for `turnComplete`, not `generationComplete`:** Prevents sequential
    `clientContent` turns from self-interrupting active playback pacing.
10. **Enable `contextWindowCompression` and `sessionResumption`:** Prevents
    long-session audio drop/drift, bounds multi-turn audio token retention cost,
    and recovers cleanly across `goAway`, `1000`, `1006`, and `1011`
    disconnects.
