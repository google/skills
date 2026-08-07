# Live API Session Manager

This document guides the implementation of a `SessionManager` class for the Gemini Live API over WebSockets. It ensures robust handling of disconnections and session resumption.

## Core Responsibilities

1.  **Connection Management**: Maintain a continuous WebSocket connection to the specified endpoint until explicitly stopped.
2.  **Bidirectional Communication**: Handle sending and receiving messages concurrently (use separate coroutines or threads).
3.  **Session Resumption**: Automatically reconnect and restore state when disconnections occur.

## Protocol Details

-   **Proto File**: `client_server_messages.proto`
-   **Server Message**: `BidiGenerateContentServerMessage`
-   **Client Message**: `BidiGenerateContentClientMessage`

## Session Resumption Logic

To support transparent session resumption, the manager must implement the following logic:

### 1. Enable Transparent Session Resumption
Modify the `session_resumption` field in the `setup` message (type `BidiGenerateContentSetup`) of the initial `BidiGenerateContentClientMessage`. Always set the `transparent` field to `true` in the `SessionResumptionConfig`. This enables the model to return `last_consumed_client_message_index` in `SessionResumptionUpdate` messages, indicating when to update the buffer.

-   **Proto Reference**: `client_server_messages.proto`
    -   `BidiGenerateContentSetup.session_resumption` (type `SessionResumptionConfig`)
    -   `SessionResumptionConfig.transparent` (bool)

### 2. Handle Session Handle Updates
Listen for `session_resumption_update` messages in the stream from the server.

-   If `resumable` is true and a `new_handle` is provided, store it.
-   This handle is required for reconnecting to the same session.

### 3. Message Buffering and Pruning
Maintain a buffer of sent messages to replay if a disconnection occurs.

-   **Indexing**: The user-managed message index MUST begin at **1**. The server reserves index **0** for the initial configuration.
-   Increment the index by 1 for each subsequent message sent.
-   **Pruning**: Use the `last_consumed_client_message_index` from the server's `session_resumption_update` to remove acknowledged messages from the buffer.
-   **Reset on Resumption**: Upon reconnection, ensure the index is reset to **1** for the first message transmitted via the new connection.

### 4. Handling Disconnections
Catch disconnections and initiate resumption:

-   **Proactive Reconnection**: If the server sends a `go_away` signal, proactively reconnect using the latest handle.
-   **Error Handling**: Catch WebSocket errors (specifically error codes **1000** or **1006**) in both sending and receiving loops. Trigger the reconnection process on these errors.
-   **Unexpected Errors**: For other unexpected errors, the session manager
    should be stopped and raise that error immediately. Subsequent user
    send/receive function calls should raise exceptions with stop reasons.
-   **Reconnection Errors**: Exceptions can also occur during the reconnection process itself. These must be handled correctly, for example, by implementing retries with exponential backoff or failing gracefully if the connection cannot be re-established.

### 5. Reconnection with Message Replay
When a disconnection occurs:

1.  Establish a new websocket connection and pass the stored session handle.
2.  Resend all messages remaining in the buffer BEFORE sending / receiving any
    other messages. Do not modify the buffer until receiving the resumption
    handle update, since there could be connection failure during this time and
    a new retry will be needed.
3.  The first message sent from the buffer on the new connection MUST be marked with index **1**. THIS IS VERY IMPORTANT.

## Gotchas

-   **Index 0**: Never use index 0 for user messages; it is reserved for the
    first config message.
-   **Concurrent Loops**: Ensure the receive loop can detect disconnections and
    trigger reconnection even if the send loop is idle, and vice versa.
-   **Handle Expiry**: Session handles may have an expiry; handle failures to
    reconnect with an expired handle by starting a fresh session if necessary.
