# Live API Session Manager

This document guides the implementation of a `SessionManager` class for the
Gemini Enterprise Agent Platform Live API over WebSockets. It ensures robust
handling of connection rotation, unexpected disconnections, and lossless
transparent session resumption.

## Table of Contents

- [Core Responsibilities](#core-responsibilities): Lines 15-24
- [Protocol and Limits](#protocol-and-limits): Lines 26-40
- [Session Resumption Logic](#session-resumption-logic): Lines 42-115
- [Gotchas](#gotchas): Lines 117-126

## Core Responsibilities

1. **Connection Management**: Maintain a continuous WebSocket connection to the
   regional Live API endpoint until explicitly stopped.
2. **Bidirectional Communication**: Handle sending and receiving JSON text
   frames concurrently (using separate async tasks, coroutines, or threads)
   gated on `setup_complete`.
3. **Transparent Session Resumption**: Automatically reconnect, refresh ADC
   bearer tokens if needed, and replay unconsumed messages without losing
   in-flight audio, video, tool responses, or context updates.

## Protocol and Limits

- **Proto File**: `client_server_messages.proto`
- **Client Envelope**: `ClientMessage` (`BidiGenerateContentClientMessage`)
- **Server Envelope**: `ServerMessage` (`BidiGenerateContentServerMessage`)
- **Wire Serialization**: UTF-8 JSON text frames via Protobuf JSON mapping
  (e.g., `MessageToJson` and `Parse(..., ignore_unknown_fields=True)`).
- **Duration Limits**:
  - **WebSocket connection lifetime (~10 minutes)**: The server sends a
    `go_away` frame (`time_left` typically ~60s) before closing the socket.
  - **Session context limit (~15 minutes uncompressed)**: For long-running
    sessions (>15 minutes), also configure
    `setup.context_window_compression.sliding_window` alongside
    `setup.session_resumption` so session context does not hit the token/time
    ceiling across reconnects.

## Session Resumption Logic

### 1. Enable Transparent Session Resumption

In the initial `ClientMessage.setup` (`BidiGenerateContentSetup`), always set
`session_resumption.transparent = true` (`SessionResumptionConfig`). This
instructs the server to emit `last_consumed_client_message_index` inside
`SessionResumptionUpdate` frames so the client knows which buffered frames have
been committed to session state.

### 2. Track Session Handle Updates

Listen for `session_resumption_update` frames from the server:

- Whenever `resumable` is `true` and `new_handle` is non-empty, store
  `new_handle` as the latest resumption token.
- Note that during active generation or tool execution, the server may emit
  `resumable: false` with an empty `new_handle`; retain the most recent valid
  `new_handle` rather than overwriting it with an empty string.

### 3. Message Buffering and 1-Based Indexing

Maintain an ordered client-side buffer of post-setup `ClientMessage` frames
(`realtime_input`, `client_content`, `tool_response`, `context_update`) so
unacknowledged frames can be replayed on reconnect:

- **Indexing**: User-managed message indices MUST start at **1**. Index **0** is
  reserved by the server for the initial `setup` frame.
- Increment the index by 1 for each post-setup `ClientMessage` sent on the
  current connection.
- **Pruning**: When a `session_resumption_update` arrives with
  `last_consumed_client_message_index > 0`, remove all buffered messages with
  `index <= last_consumed_client_message_index`.
- **Reset on Resumption**: Upon reconnecting, re-index the remaining buffered
  messages starting from **1** for the first replayed message on the new
  WebSocket connection.

### 4. Handling Disconnections and `go_away`

- **Proactive Reconnection**: When `go_away` arrives, proactively initiate
  reconnection using the stored `new_handle` before `time_left` expires.
- **Transient Socket Closes**: Catch WebSocket close codes **1000** (normal
  closure), **1006** (abnormal closure), and **1011** (transient internal server
  error) in **both** the receive loop **and** every `send_*` / internal `_send`
  path, triggering reconnection from whichever path observes the close first.
- **Unexpected Errors**: For non-recoverable protocol/auth errors (e.g., `1007`
  invalid frame, `1008` invalid setup/policy violation, or permission denied),
  stop the session manager and surface the error immediately; subsequent
  `send_*` / `receive` calls should raise an exception describing the stop
  reason.
- **Reconnect Backoff**: Retry transient reconnection failures with bounded
  exponential backoff and fresh/valid ADC bearer tokens.

### 5. Reconnection with Message Replay

When reconnecting:

1. Clear the "ready for user sends" gate before opening the new socket so new
   `send_*` calls wait until **both** `setup_complete` and full buffer replay
   have completed.
2. Open a new WebSocket connection with a valid (refreshed if needed) ADC
   `Authorization: Bearer <token>` header, send `setup` with
   `session_resumption.handle = <latest_new_handle>` and
   `session_resumption.transparent = true`, and wait for `setup_complete`.
3. Replay all messages remaining in the buffer **before** unblocking new user
   sends. Do **not** clear, pop, or mutate the buffered message list in-place
   during replay — keep all unacknowledged messages intact until a fresh
   `session_resumption_update` arrives on the new connection, in case the
   reconnection attempt itself drops mid-replay.
4. Map the replayed messages to sequential per-connection indices starting at
   **1** (`1`, `2`, ..., `len(buffer)`) on the new connection without mutating
   the underlying list prior to server acknowledgment, then set the
   ready-to-send gate so new user messages continue at index `len(buffer) + 1`,
   `len(buffer) + 2`, and so on.

## Gotchas

- **Never use index 0** for post-setup messages; index `0` is always the `setup`
  frame.
- **Idle-loop detection**: Ensure the receive loop triggers reconnection when
  the send loop is idle, and the send loop triggers reconnection when the
  receive loop is idle.
- **Expired handles**: Resumption handles expire after a period of inactivity;
  if resuming with an expired handle is rejected during `setup`, fall back
  cleanly to starting a fresh session if configured to do so.
