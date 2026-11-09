# Genkit Middleware (`genkit_middleware`)

A collection of useful middleware for Genkit Dart to enhance your agent's
capabilities. Register plugins when initializing Genkit:

```dart
import 'package:genkit/genkit.dart';
import 'package:genkit_middleware/genkit_middleware.dart';

void main() {
  final ai = Genkit(
    plugins: [
      FilesystemPlugin(),
      SkillsPlugin(),
      ToolApprovalPlugin(),
    ],
  );
}
```

- [Filesystem Middleware](#filesystem-middleware): Lines 28-43
- [Skills Middleware](#skills-middleware): Lines 45-60
- [Tool Approval Middleware](#tool-approval-middleware): Lines 62-105
- [Custom Middleware (core package:genkit)](#custom-middleware-core-packagegenkit): Lines 107-168

---

## Filesystem Middleware
Allows the agent to list, read, write, and search/replace files within a
restricted root directory.

```dart
final response = await ai.generate(
  prompt: 'Check the logs in the current directory.',
  use: [
    filesystem(rootDirectory: '/path/to/secure/workspace'),
  ],
);
```

**Tools Provided:**

- `list_files`, `read_file`, `write_file`, `search_and_replace`

## Skills Middleware
Injects specialized instructions (skills) into the system prompt from `SKILL.md`
files located in specified directories.

```dart
final response = await ai.generate(
  prompt: 'Help me debug this issue.',
  use: [
    skills(skillPaths: ['/path/to/skills']),
  ],
);
```

**Tools Provided:**

- `use_skill`: Retrieve the full content of a skill by name.

## Tool Approval Middleware
Intercepts tool execution for specified tools and requires explicit approval.
Returns `FinishReason.interrupted`.

A tool is allowed through only if it is in the `approved` list or its request's
`resumed` payload carries `{ 'tool-approved': true }`. To approve on resume,
re-issue the paused `ToolRequestPart` with `.restart({'tool-approved': true})` —
the builder nests the payload under `metadata.resumed`, exactly what the
middleware reads.

```dart
final response = await ai.generate(
  prompt: 'Delete the database.',
  use: [
    // Require approval for all tools EXCEPT those below
    toolApproval(approved: ['read_file', 'list_files']),
  ],
);

if (response.finishReason == FinishReason.interrupted) {
  // `response.interrupts` is a List<ToolRequestPart>.
  final interrupt = response.interrupts.first;

  // Ask user for approval
  final isApproved = await askUser();

  if (isApproved) {
    final resumeResponse = await ai.generate(
      messages: response.messages, // Pass history
      toolChoice: ToolChoice.none, // Prevent immediate re-call
      interruptRestart: [
        // `.restart(...)` nests the payload under `metadata.resumed`.
        interrupt.restart({'tool-approved': true}),
      ],
    );
  }
}
```

> **Agent-side resume.** When resuming an agent chat rather than a raw
> `ai.generate` call, the interrupts are `AgentInterrupt`s; pass the same
> `.restart(...)` builder directly to `chat.resume`:
> `chat.resume(restart: [interrupt.restart({'tool-approved': true})])`.
> See [human-in-the-loop](agents-human-in-the-loop.md).

## Custom Middleware (core `package:genkit`)

Extend `GenerateMiddleware` and override the hooks you need (`generate`,
`model`, `tool`). Register it with `ai.defineGenerateMiddleware` and call the
returned definition to build the ref for `use:`. `create` runs once per
`generate` call; `ctx.ai` is a `GenkitAI` the middleware can use for its own
calls (classifiers, guardrails).

```dart
class LoggingMiddleware extends GenerateMiddleware {
  @override
  Future<ModelResponse> model(
    ModelRequest request,
    ActionFnArg<ModelResponseChunk, ModelRequest, void> ctx,
    Future<ModelResponse> Function(
      ModelRequest request,
      ActionFnArg<ModelResponseChunk, ModelRequest, void> ctx,
    ) next,
  ) async {
    print('Calling the model with ${request.messages.length} messages');
    return next(request, ctx);
  }
}

final logging = ai.defineGenerateMiddleware<void>(
  name: 'logging',
  create: (config, ctx) => LoggingMiddleware(),
);

await ai.generate(prompt: 'Hello', use: [logging(), retry(maxRetries: 2)]);
```

For typed config, pass `configSchema: MyOptions.$schema` (a schemantic type)
and call `logging(MyOptions(...))`.

To ship middleware in a plugin, build the definition with the top-level
`generateMiddleware` (it does not register anything) and return it from
`GenkitPlugin.middleware()`. The definition is callable, so a named-parameter
helper is a one-liner:

```dart
final loggerDef = generateMiddleware<LoggerOptions>(
  name: 'logger',
  configSchema: LoggerOptions.$schema,
  create: (config, ctx) => LoggerMiddleware(verbose: config?.verbose ?? false),
);

class LoggerPlugin extends GenkitPlugin {
  @override
  String get name => 'logger';

  @override
  List<GenerateMiddlewareDef> middleware() => [loggerDef];
}

GenerateMiddlewareRef<LoggerOptions> logger({bool? verbose}) =>
    loggerDef(LoggerOptions(verbose: verbose));
```

There is no `defineMiddleware`. Prefer calling the definition over
`middlewareRef(name: ...)`, which is only needed to reference middleware by
name without its definition.
