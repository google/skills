---
name: gemini-live-api
metadata:
  category: AiAndMachineLearning
description: >-
  Generates a Gemini LiveAPI client service class in the user's chosen programming
  language. Use when the user wants to build, scaffold, or integrate a client
  that connects to the Gemini Enterprise LiveAPI websocket endpoint, handles
  session setup/resumption, bearer token refresh, and sending/receiving
  `ClientMessage`/`ServerMessage` protos. Don't use for general (non-live,
  non-bidirectional) Gemini API usage such as one-shot `generateContent`,
  embeddings, image/video generation, or fine-tuning — use the `gemini-api`
  skill for those.
---

# LiveAPI Service Skill

This skill provides instructions for generating a **LiveAPI client service
class** that connects to the Gemini Enterprise Live API over WebSockets. The
generated client handles bidirectional streaming, bearer-token authentication
via Application Default Credentials (ADC), transparent session resumption, and
`ClientMessage` / `ServerMessage` proto exchange.

The skill also produces a demo frontend + backend service so the user can
interactively validate the generated client (text, audio, video, transcription,
and interrupt handling).

## Prerequisites

Before running the generation flow, ensure the following are available on the
host:

-   A Google Cloud project with the Vertex AI / Gemini Enterprise Agent Platform
    APIs enabled.
-   Application Default Credentials configured on the host running the generated
    client:

    ```bash
    gcloud auth application-default login
    ```

-   A destination output folder supplied by the user (e.g. `/tmp/liveapi_out`)
    where the generated code, environment, and demo will be written. **Never**
    mutate the host's system Python environment.

-   The user's chosen implementation language (Python is the default and
    reference language for this skill).

## Reference Files

Provided files in `references/` (do **not** treat these as standalone skills —
they are loaded on demand):

-   `client_server_messages.md`: Public reference for the `ClientMessage` /
    `ServerMessage` schemas used by the Live API.
-   `client_server_messages.proto`: The proto definition generated from
    `client_server_messages.md`.
-   `session_manager.md`: Describes how to correctly handle sessions, buffering,
    and resumption on disconnection.

## Steps

### Step 1: Copy the reference files

Copy `client_server_messages.md`, `client_server_messages.proto`, and
`session_manager.md` from this skill's `references/` folder into the user's
destination output folder. These files become the source of truth for the
generated client.

### Step 2: Reconcile with the public documentation

Examine the public documents linked from `client_server_messages.md`. If there
are any discrepancies between the public documents and the copied
`client_server_messages.md` / `client_server_messages.proto`, update the copies
in the destination folder so the generated client compiles and runs against the
current server contract.

### Step 3: Implement the client class

Implement a class in the user's chosen language that:

-   Imports the local `client_server_messages.proto` types (`ClientMessage`,
    `ServerMessage`).
-   Opens a WebSocket connection to the Live API endpoint.
-   Exposes async methods so the user can send and receive data to/from the
    model.

For languages that require an isolated runtime (e.g. Python), create an isolated
environment (e.g. `venv`) **inside the destination folder** and generate a bash
script (e.g. `setup.sh`) that recreates the environment and installs
dependencies. **Never** install into the system interpreter or the user's global
site-packages, and never instruct the user to run `sudo pip install`.

#### Initialization parameters

The user provides the following at construction time:

-   `project_id`
-   `location`
-   `model_id`
-   `config`: a `ClientMessage` with the `setup` field populated.

#### Authentication

Obtain a bearer token via Application Default Credentials, attach it to the
WebSocket connect request as `Authorization: Bearer <token>`, refresh the token
before or upon expiry, and reuse the refreshed token on every reconnection
(including `go_away` and unexpected disconnects). **Do not** hard-code a
long-lived API key as the only auth mechanism.

#### Public async API

The class MUST expose the following async methods, gated on receipt of a
`setup_complete` `ServerMessage` before sending:

-   `send_realtime_data(data)`: send realtime input. `data` is a `ClientMessage`
    carrying a `realtime_input` field.
-   `send_client_content(data)`: send non-realtime, turn-based content that
    contributes to history. `data` is a `ClientMessage` carrying a
    `client_content` field.
-   `receive()`: yield `ServerMessage` instances parsed from the WebSocket
    stream.

Do not expose synchronous blocking variants as the primary API surface.

### Step 4: Write a test file

Once the client is implemented, generate a test file that initializes the
connection and exercises sending `text`, `audio`, and `video` data and receiving
the responses. Ask the user for any information required to run the test
(project, model, media samples).

### Step 5: Generate `how_to_run.md`

Provide a `how_to_run.md` in the destination folder that documents the generated
class. Include full examples showing how to build `ClientMessage` payloads for
every supported modality, how to send them, and how to receive data from the
model.

### Step 6: Generate a demo frontend + backend service

Create scripts that deploy the implementation as a service with both a frontend
UI and a backend service (any language). The service MUST reuse the
`ClientMessage` / `ServerMessage` protos from Step 1 for wire traffic. Through
the UI the user should be able to:

-   Start a new connection / close the current connection.
-   Select the model to use.
-   Select input sources (audio and/or video from camera or screenshot) and
    stream them to the model.
-   Send a text message to the model.
-   Hear model audio and see the interleaved model and user transcription /
    conversation history.

While implementing audio and transcription playback, follow the guidance in
[Live API best practices](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api/best-practices).

#### Handling the `interrupt` signal

When a `ServerMessage`'s `server_content` arrives with `interrupted: true`, the
UI MUST:

-   Ensure played audio and its corresponding transcription remain time-aligned.
-   Immediately stop the currently playing model audio and stop appending to the
    in-progress transcription bubble.
-   Clear the unplayed audio buffer and any pending unrendered transcription so
    stale content does not bleed into the next turn.
-   Start new chat bubbles for the next user and model turns.

#### Handling the transcription `finished` signal

For streamed `input_transcription` / `output_transcription` chunks, append to
the currently active bubble while `finished` is unset, and close that bubble and
start a fresh one when `finished` is observed. Route `input_transcription` text
to user-role bubbles and `output_transcription` text to model-role bubbles.

### Step 7: Generate `how_to_test_with_ui.md`

Write `how_to_test_with_ui.md` describing how to launch and use the demo
service. It MUST include:

-   The exact shell command(s) or script invocation(s) to start the backend
    service.
-   The exact shell command(s) or script invocation(s) to start the frontend UI.
-   The host and port (e.g. `http://localhost:PORT`) the user should open in
    their browser.
-   How to start a session, select a model, choose input sources (mic, camera,
    screen), send a text message, and observe model audio and transcription in
    the UI.

## Validation Checklist

Before considering the generation complete, verify each item:

-   [ ] `client_server_messages.md`, `client_server_messages.proto`, and
    `session_manager.md` were copied into the destination folder.
-   [ ] The generated client imports the local proto-generated `ClientMessage`
    and `ServerMessage` types.
-   [ ] The client connects to the Live API WebSocket at
    `wss://{location}-aiplatform.googleapis.com/ws/google.cloud.aiplatform.v1beta1.LlmBidiService/BidiGenerateContent`
    (or the `wss://aiplatform.googleapis.com/...` global variant), and formats
    the setup `model` field as
    `projects/{project_id}/locations/{location}/publishers/google/models/{model_id}`.
-   [ ] Authentication uses ADC-provided bearer tokens sent as `Authorization:
    Bearer <token>`, is refreshed before expiry, and reattached on every
    reconnect.
-   [ ] Public async methods `send_realtime_data`, `send_client_content`, and
    `receive` are present, correctly typed, and gated on `setup_complete`.
-   [ ] Transparent session resumption is enabled
    (`session_resumption.transparent = true`), the latest `new_handle` is
    tracked, sent-message indexing starts at 1, the buffer is pruned via
    `last_consumed_client_message_index`, and buffered messages are replayed on
    reconnect (including on `go_away` and WebSocket close codes 1000 / 1006).
-   [ ] If using python, an isolated environment (e.g. `venv`) plus a `setup.sh`
    and `requirements.txt` (or equivalent) exist inside the destination folder;
    no changes were made to system or user-global Python.
-   [ ] `how_to_run.md` and `how_to_test_with_ui.md` are present, and the demo
    UI reuses the same `ClientMessage` / `ServerMessage` protos.
-   [ ] Interrupt handling and transcription `finished` handling behave as
    described above.
-   [ ] The client does **not** target `generativelanguage.googleapis.com` and
    does **not** authenticate via API key in a query string.
