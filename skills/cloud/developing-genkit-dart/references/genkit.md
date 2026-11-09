# Genkit Core Framework

Genkit Dart is an AI SDK for Dart that provides a unified interface for text
generation, structured output, tool calling, and agentic workflows.

- [Initialization](#initialization): Lines 23-34
- [Reliability: retry transient errors](#reliability-retry-transient-errors): Lines 36-56
- [Generate Text](#generate-text): Lines 58-68
- [Stream Responses](#stream-responses): Lines 70-80
- [Embed Text](#embed-text): Lines 82-96
- [Define Tools](#define-tools): Lines 98-144
- [Structured Output](#structured-output): Lines 146-168
- [Errors and finish reasons](#errors-and-finish-reasons): Lines 170-227
- [Cancellation](#cancellation): Lines 229-257
- [Telemetry (instrumentation)](#telemetry-instrumentation): Lines 259-280
- [Define Flows](#define-flows): Lines 282-331
- [Calling remote Flows from a dart client](#calling-remote-flows-from-a-dart-client): Lines 333-375
- [Calling remote Flows from a Javascript client](#calling-remote-flows-from-a-javascript-client): Lines 377-431
- [Data Models](#data-models): Lines 433-573

---

## Initialization

```dart
import 'package:genkit/genkit.dart';
import 'package:genkit_google_genai/genkit_google_genai.dart'; // Or any other plugin

void main() async {
  // Pass plugins to use into the Genkit constructor. Built-in middleware such
  // as `retry` needs no plugin.
  final ai = Genkit(plugins: [googleAI()]);
}
```

## Reliability: retry transient errors

Model backends routinely return transient errors (Gemini "high demand" surfaces
as `StatusCode.internal`, plus `unavailable` / `resourceExhausted` under load).
In practice `retry()` is close to mandatory for reliable runs. It is a **core**
middleware, always registered (no plugin, no extra package): just add
`use: [retry()]` to a call. By default it retries `unavailable`,
`deadlineExceeded`, `resourceExhausted`, `aborted`, and `internal`, and it works
the same on `generate`, `generateStream`, prompts, and flows. The examples below
add it where it matters.

```dart
retry(
  maxRetries: 5,
  initialDelay: const Duration(milliseconds: 500), // Durations, not ms ints
  maxDelay: const Duration(seconds: 30),
  statuses: [StatusCode.unavailable, StatusCode.resourceExhausted],
  // noRetryModel: true, // skip model retries (on by default)
  // retryTools: true,   // also retry failed tools (off by default)
)
```

## Generate Text

```dart
final response = await ai.generate(
  model: googleAI.gemini('gemini-flash-latest'), // Needs a model reference from a plugin
  prompt: 'Explain quantum computing in simple terms.',
  use: [retry()], // recommended; stream/embed/prompts/flows take the same `use:`
);

print(response.text);
```

## Stream Responses
```dart
final stream = ai.generateStream(
  model: googleAI.gemini('gemini-flash-latest'),
  prompt: 'Write a short story about a robot learning to paint.',
);

await for (final chunk in stream) {
  print(chunk.text);
}
```

## Embed Text

`ai.embed` takes either `document:` (one) or `documents:` (many) and always
returns `List<Embedding>`. There is no `embedMany`.

```dart
final embeddings = await ai.embed(
  documents: [
    DocumentData(content: [TextPart(text: 'Hello world')]),
  ],
  embedder: googleAI.textEmbedding('gemini-embedding-001'),
);

print(embeddings.first.embedding);
```

## Define Tools
Models can use define actions and access external data via custom defined tools.
Requires the `schemantic` library for schema definitions.

```dart
import 'package:schemantic/schemantic.dart';

@Schema()
abstract class $WeatherInput {
  String get location;
}

final weatherTool = ai.defineTool(
  name: 'getWeather',
  description: 'Gets the current weather for a location',
  inputSchema: WeatherInput.$schema,
  fn: (input, _) async {
    // Call your weather API here
    return .response('Weather in ${input.location}: 72°F and sunny');
  },
);

final response = await ai.generate(
  model: googleAI.gemini('gemini-flash-latest'),
  prompt: 'What\'s the weather like in San Francisco?',
  toolNames: ['getWeather'], // Use the tools
);
```

> **Tool functions return a `ToolResult`.** A tool's `fn` returns a
> `ToolResult<Output>`, built with dot-shorthand:
>
> - `return .response(output)` for a normal result.
> - `return .response(output, parts: [...])` to attach media parts alongside the
>   structured output (multipart), e.g. an image the tool produced.
> - `return .interrupt(data)` to pause the generation loop (see
>   [human-in-the-loop](agents-human-in-the-loop.md)).
>
> ```dart
> fn: (input, _) async => .response(
>   {'result': 'captured'},
>   parts: [MediaPart(media: Media(contentType: 'image/png', url: dataUri))],
> );
> ```
>
> Reading a tool's direct result (e.g. via `tool.call`) also yields a
> `ToolResult`; read `(result as ToolResponseResult).output`.

## Structured Output

You can ensure the generative model returns a typed JSON object by providing an
`outputSchema`.

```dart
@Schema()
abstract class $Person {
  String get name;
  int get age;
}

// ... inside main ...

final response = await ai.generate(
  model: googleAI.gemini('gemini-flash-latest'),
  prompt: 'Generate a person named John Doe, age 30',
  outputSchema: Person.$schema, // Force the model to return this schema
);

final person = response.output; // Typed Person object
print('Name: ${person.name}, Age: ${person.age}');
```

## Errors and finish reasons

`generate` and `generateStream` do **not** throw for model errors, throwing
tools, cancellation, or hitting `maxTurns`. They resolve to a response whose
`finishReason` tells you what happened; branch on it instead of wrapping the
call in `try`/`catch`:

```dart
final res = await ai.generate(
  model: googleAI.gemini('gemini-flash-latest'),
  prompt: 'hi',
  toolNames: ['myTool'],
);

switch (res.finishReason) {
  case FinishReason.failed:
    // A model error or a throwing tool. `res.error` is a structured
    // RuntimeError; `res.cause` is the thrown object (in-process only, it
    // does not cross the HTTP/reflection boundary).
    // - Model error: `cause` is what the model call threw. A GenkitException
    //   keeps its status; anything else maps to INTERNAL.
    // - Throwing tool: `cause` is a GenkitException (INTERNAL,
    //   'tool "x" failed: ...') wrapping the tool's error, so the original
    //   is one level down, on its own `.cause`.
    print(res.error?.status);
    final cause = res.cause;
    final original = cause is GenkitException ? cause.cause ?? cause : cause;
    if (original is SocketException) {/* retry later */}
  case FinishReason.aborted:
    // Cancelled, or hit maxTurns.
    print('aborted: ${res.finishMessage}');
  default:
    print(res.text);
}
```

Only a tool returning `.interrupt(...)` is treated as a turn outcome
(`FinishReason.interrupted`) rather than a failure. See
[human-in-the-loop](agents-human-in-the-loop.md).

### Resume from the last-good state

On a `failed` or `aborted` response, `res.messages` holds the **last-good
conversation state**: the request messages plus every tool turn that completed
before the failure/abort (the failing turn's own partial output is dropped).
You do not have to start over. Feed `res.messages` straight back into a fresh
`generate` (with a new, uncancelled token if you were cancelling) to continue
from where it stopped:

```dart
if (res.finishReason == FinishReason.failed ||
    res.finishReason == FinishReason.aborted) {
  final resumed = await ai.generate(
    model: googleAI.gemini('gemini-flash-latest'),
    messages: res.messages, // last-good history: pick up where it stopped
  );
}
```

## Cancellation

`generate`, `generateStream`, and action calls accept a `CancellationToken`. The
caller owns a `CancellationController` and hands its token to the call. These
are
stable core types from `package:genkit/genkit.dart` (and `client.dart`).

```dart
final controller = CancellationController();

final stream = ai.generateStream(
  model: googleAI.gemini('gemini-flash-latest'),
  prompt: 'Write a long, detailed essay about the history of the internet.',
  cancel: controller.token,
);

controller.cancel('user pressed stop');

// Chunks emitted before the cancel still arrive; the stream then closes.
await for (final chunk in stream) {
  stdout.write(chunk.text);
}

final res = await stream.onResult;
if (res.finishReason == FinishReason.aborted) {
  // res.messages holds the last-good history, so you can resume later.
  print('\nCancelled: ${res.finishMessage}');
}
```

## Telemetry (instrumentation)

Telemetry is a pluggable abstraction, not a hardcoded OpenTelemetry dependency.
By default Genkit is not instrumented. In the dev environment (under
`genkit start`) a built-in provider is auto-injected so the Developer UI
receives
traces with no setup, so most users never touch this API. For production, stack
one or more `Instrumentation` providers before creating `Genkit`:

```dart
import 'package:genkit/telemetry.dart';

void main() {
  configureInstrumentation(myInstrumentation());
  final ai = Genkit(plugins: [googleAI()]);
  // ...
}
```

Providers compose as a middleware chain, so multiple can be active at once. A
third-party platform can implement `Instrumentation` without taking an OTel
dependency.

## Define Flows
Wrap your AI logic in flows for better observability, testing, and deployment:

```dart
final jokeFlow = ai.defineFlow(
  name: 'tellJoke',
  inputSchema: .string(),
  outputSchema: .string(),
  fn: (topic, _) async {
    final response = await ai.generate(
      model: googleAI.gemini('gemini-flash-latest'),
      prompt: 'Tell me a joke about $topic',
    );
    return response.text; // Value return
  },
);

final joke = await jokeFlow('programming');
print(joke);
```

> **Top-level `final` flows are lazy.** A flow declared as a top-level `final`
> registers only when the symbol is first evaluated, so an empty `main()`
> registers nothing and `genkit flow:run` fails with `Process exited before
> runtime was ready`. Reference the flow from `main()` (or import a module that
> does) so its `defineFlow` call runs.

### Streaming Flows
Stream data from your flows using `context.sendChunk(...)` and returning the
final value:

```dart
final streamStory = ai.defineFlow(
  name: 'streamStory',
  inputSchema: .string(),
  outputSchema: .string(),
  streamSchema: .string(),
  fn: (topic, context) async {
    final stream = ai.generateStream(
      model: googleAI.gemini('gemini-flash-latest'),
      prompt: 'Write a story about $topic',
    );

    await for (final chunk in stream) {
      context.sendChunk(chunk.text); // Stream the chunks
    }
    return 'Story complete'; // Value return
  },
);
```

## Calling remote Flows from a dart client
The `genkit` package provides `package:genkit/client.dart` representing remote
Genkit actions that can be invoked or streamed using type-safe definitions.

1. Defines a remote action
```dart
import 'package:genkit/client.dart';

final stringAction = defineRemoteAction(
  url: 'http://localhost:3400/my-flow',
  inputSchema: .string(),
  outputSchema: .string(),
);
```

2. Call the Remote Action (Non-streaming)
```dart
final response = await stringAction(input: 'Hello from Dart!');
print('Flow Response: $response');
```

3. Call the Remote Action (Streaming)
Use the `.stream()` method on the action flow, and access `stream.onResult` to
wait on the async return value.
```dart
final streamAction = defineRemoteAction(
  url: 'http://localhost:3400/stream-story',
  inputSchema: .string(),
  outputSchema: .string(),
  streamSchema: .string(),
);

final stream = streamAction.stream(
  input: 'Tell me a short story about a Dart developer.',
);

await for (final chunk in stream) {
  print('Chunk: $chunk'); 
}

final finalResult = await stream.onResult;
print('\nFinal Response: $finalResult');
```

## Calling remote Flows from a Javascript client

Install `genkit` npm package:

```bash
npm install genkit
```

1. Call a remote flow (non-streaming)

```ts
import { runFlow } from 'genkit/beta/client';

async function callHelloFlow() {
  try {
    const result = await runFlow({
      url: 'http://127.0.0.1:3400/helloFlow', // Replace with your deployed flow's URL
      input: { name: 'Genkit User' },
    });
    console.log('Non-streaming result:', result.greeting);
  } catch (error) {
    console.error('Error calling helloFlow:', error);
  }
}

callHelloFlow();
```

2. Call a remote flow (streaming)

```ts
import { streamFlow } from 'genkit/beta/client';

async function streamHelloFlow() {
  try {
    const result = streamFlow({
      url: 'http://127.0.0.1:3400/helloFlow', // Replace with your deployed flow's URL
      input: { name: 'Streaming User' },
    });

    // Process the stream chunks as they arrive
    for await (const chunk of result.stream) {
      console.log('Stream chunk:', chunk);
    }

    // Get the final complete response
    const finalOutput = await result.output;
    console.log('Final streaming output:', finalOutput.greeting);
  } catch (error) {
    console.error('Error streaming helloFlow:', error);
  }
}

streamHelloFlow();
```

## Data Models

Genkit uses standard data models for representing prompts (messages & parts) and
responses. These classes are implemented using schemantic library.

```dart
import 'package:genkit/genkit.dart';
import 'package:schemantic/schemantic.dart';

@Schema()
abstract class $MyDataModel {
  // uses Genkit's Message schema (not schemantic's Message)
  List<$Message> get messages;
  List<$Part> get parts;
}

void example() {
  // --- Parts ---
  // A Text part
  final textPart = TextPart(text: 'some text', metadata: {'foo': 'bar'});

  // A Media/Image part
  final mediaPart = MediaPart(
    media: Media(url: 'https://...', contentType: 'image/png'),
    metadata: {'foo': 'bar'},
  );

  // A Tool Request initiated by the model
  final toolRequestPart = ToolRequestPart(
    toolRequest: ToolRequest(
      name: 'get_weather',
      ref: 'abc',
      input: {'location': 'Paris, France'},
    ),
    metadata: {'foo': 'bar'},
  );

  // The resulting data from a Tool execution
  final toolResponsePart = ToolResponsePart(
    toolResponse: ToolResponse(
      name: 'get_weather',
      ref: 'abc',
      output: {'temperature': '20C'},
    ),
    metadata: {'foo': 'bar'},
  );

  // Model reasoning (e.g. for Claude's "thinking" models)
  final reasoningPart = ReasoningPart(
    reasoning: 'thinking...',
    metadata: {'foo': 'bar'},
  );

  // A custom fallback part
  final customPart = CustomPart(
    custom: {'provider': {'specific': 'data'}},
    metadata: {'foo': 'bar'},
  );

  // --- Messages ---
  final systemMessage = Message(
    role: Role.system,
    content: [textPart, mediaPart],
    metadata: {'foo': 'bar'},
  );

  final userMessage = Message(
    role: Role.user,
    content: [textPart, mediaPart], // Can contain media (multimodal)
  );

  final modelMessage = Message(
    role: Role.model,
    // Models can emit text, tool requests, reasoning, or custom parts
    content: [textPart, toolRequestPart, reasoningPart, customPart],
  );

  // --- Ergonomic Data Access (schema_extensions.dart) ---
  // The Genkit SDK provides extensions on `Message` and `Part` to easily access fields
  // without needing to cast them manually.

  // Get concatenated text from all TextParts in a Message
  print(modelMessage.text); 
  
  // Get the first Media object from a Message
  print(modelMessage.media?.url);

  // Iterate over tool requests in a Message
  for (final toolReq in modelMessage.toolRequests) {
    print(toolReq.name);
  }

  // Inspect individual parts
  for (final part in modelMessage.content) {
    if (part.isText) print(part.text);
    if (part.isMedia) print(part.media?.url);
    if (part.isToolRequest) print(part.toolRequest?.name);
    if (part.isToolResponse) print(part.toolResponse?.name);
    if (part.isReasoning) print(part.reasoning);
    if (part.isCustom) print(part.custom);
  }

  // --- Streaming Chunks ---
  // Data emitted by ai.generateStream() calls
  final generateResponseChunk = ModelResponseChunk(
    content: [textPart],
    index: 0, // Index of the message this chunk belongs to
    aggregated: false, 
  );

  // Chunks also have text and media accessors
  print(generateResponseChunk.text);

  // --- Advanced: Schemas ---
  // Use Genkit type schemas directly in Schemantic validations
  final messageSchema = Message.$schema;
  final partSchema = Part.$schema;
  
  final mySchema = SchemanticType.map(
    .string(),
    .list(Message.$schema), // Requires a list of Messages
  );

  // --- Generate Response ---
  // ai.generate() returns a read-only GenerateResult<Output> view over the
  // underlying ModelResponse:
  final response = await ai.generate(...);
  
  print(response.text); // Concatenated text
  print(response.media?.url); // First media part
  print(response.toolRequests); // All tool requests
  print(response.interrupts); // Tool requests that triggered an interrupt
  print(response.messages); // Full history of the conversation, including the request and response
  print(response.output); // Structured typed output (if outputSchema was used)
  print(response.usage?.inputTokens); // int? token counts
  print(response.modelResponse); // the raw ModelResponse (modelRequest too)

  // Stream chunks are GenerateResponseChunk<Output>; `chunk.modelChunk` is the
  // raw ModelResponseChunk (e.g. to forward with ctx.sendChunk in a model).
}
```
