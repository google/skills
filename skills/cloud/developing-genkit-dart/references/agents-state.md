# Working with Agent State

> Read [agents.md](agents.md) first.

Beyond message history, an agent session can hold typed **custom state** — your
own structured data (a task list, a workflow status, counters, etc.). Tools read
and mutate it during a turn, and it is automatically synced to the
[`remoteAgent`](agents.md#consume-an-agent-from-a-client-remoteagent) client via
`customPatch` chunks (so the client's tracked state stays live mid-stream).

- [Declare the state shape](#declare-the-state-shape): Lines 18-55
- [Read and mutate state inside tools](#read-and-mutate-state-inside-tools): Lines 57-160
- [Seed and read state (server-side)](#seed-and-read-state-server-side): Lines 162-186
- [Auto-sync to the remoteAgent client](#auto-sync-to-the-remoteagent-client): Lines 188-227

---

## Declare the state shape

Pass a `stateSchema` (a schemantic `.$schema`) to `defineAgent`. It's validated
when a snapshot is loaded.

```dart
import 'package:genkit/genkit.dart';
import 'package:genkit/experimental.dart'; // defineAgent, currentSession
import 'package:schemantic/schemantic.dart';

import 'genkit.dart';

part 'task_agent.g.dart';

@Schema()
abstract class $TaskItem {
  int get id;
  String get title;
  bool get done;
}

@Schema()
abstract class $TaskState {
  List<$TaskItem> get tasks;
  int get nextId;
}

final taskAgent = ai.defineAgent(
  name: 'taskAgent',
  stateSchema: TaskState.$schema,
  system: "You manage the user's task list. Use the tools to modify it.",
  tools: [addTask /*, toggleTask, removeTask */],
  use: [retry()],
);
```

`stateSchema` works with the standard `defineAgent` — you do **not** need
`defineCustomAgent` for custom state.

## Read and mutate state inside tools

Tools call `ai.currentSession<State>()` to access the live, **typed** session,
then `session.getCustom()` / `session.updateCustom(mutator)`. `updateCustom` is
fully typed: the mutator is `(State? state) => State` — it receives the current
typed state (`null` before it's first set) and returns the new state. Each call
auto-emits a `customPatch` chunk to the client.

```dart
@Schema()
abstract class $AddTaskInput {
  @Field(description: 'Short description of the task')
  String get title;
}

@Schema()
abstract class $ToggleTaskInput {
  @Field(description: 'The task ID to toggle')
  int get id;
}

final addTask = ai.defineTool(
  name: 'addTask',
  description: 'Add a new task. Returns the created task.',
  inputSchema: AddTaskInput.$schema,
  outputSchema: TaskItem.$schema,
  fn: (input, _) async {
    final session = ai.currentSession<TaskState>()!;
    late TaskItem newTask;
    session.updateCustom((state) {
      state ??= TaskState(tasks: [], nextId: 1);
      newTask = TaskItem(id: state.nextId, title: input.title, done: false);
      state.tasks = [...state.tasks, newTask];
      state.nextId += 1;
      return state;
    });
    return .response(newTask);
  },
);
```

Because the state is typed, you work with the generated `TaskState` / `TaskItem`
classes directly — no manual `Map` munging or `fromJson`. Assign back to the
setters (e.g. `state.tasks = [...]`) so the mutated values are written to the
session.

> **Make computed/optional state fields nullable.** Non-nullable schemantic
> getters are hard casts and throw (`Null is not a subtype of num`) when a
> partially populated state blob is reloaded (e.g. a computed field that was
> never written). Make such fields nullable or give them a `defaultValue`. See
> [non-nullable getters throw on partial
> data](schemantic.md#non-nullable-getters-throw-on-partial-data).

> **Prefer whole-collection tools over append-one-item tools.** The model may
> emit several tool calls in a single **parallel** batch. Each
> `session.updateCustom` reads the current custom state, mutates, and writes it
> back; when the calls run in one batch they all read the same base and the last
> write wins, silently dropping the others. An incremental `addTask` tool is
> only
> safe if the model calls it sequentially. For anything the model may batch,
> prefer a single idempotent "replace the whole collection" tool (e.g.
> `setTasks(items: [...])`) that writes the entire collection in one call.

`ai.currentSession<State>()` returns `null` when called outside an active
session
(e.g. a tool invoked without a running agent turn), so only use it inside agent
tools.

For tools that look up and mutate an existing item, a small shared helper keeps
the not-found handling in one place:

```dart
Map<String, dynamic> _mutateTaskById(
  int id,
  Map<String, dynamic> Function(List<TaskItem> tasks, int idx) onFound,
) {
  final session = ai.currentSession<TaskState>()!;
  var result = <String, dynamic>{'success': false};
  session.updateCustom((state) {
    state ??= TaskState(tasks: [], nextId: 1);
    final tasks = state.tasks;
    final idx = tasks.indexWhere((t) => t.id == id);
    if (idx >= 0) {
      result = onFound(tasks, idx);
      // Reassign so the mutated list is written back to the session state.
      state.tasks = tasks;
    } else {
      result = {'success': false, 'error': 'Task $id not found'};
    }
    return state;
  });
  return result;
}

final toggleTask = ai.defineTool(
  name: 'toggleTask',
  description: 'Toggle a task done/undone by its ID.',
  inputSchema: ToggleTaskInput.$schema,
  fn: (input, _) async => .response(_mutateTaskById(input.id, (tasks, idx) {
    tasks[idx].done = !tasks[idx].done;
    return {'success': true, 'task': tasks[idx].toJson()};
  })),
);
```

## Seed and read state (server-side)

Seed initial custom state when opening a chat. The `state` argument is a
`SessionState`: custom data goes under `.custom` (alongside `messages` and
`artifacts`).

```dart
final chat = taskAgent.chat(
  state: SessionState(
    custom: {'tasks': <dynamic>[], 'nextId': 1},
    messages: [],
    artifacts: [],
  ),
);

final res = await chat.send(text: 'Add a task: buy groceries');
print(res.state); // res.state returns the custom state directly
```

> **Typed state.** When you supply a `stateSchema`, `res.state` / `chat.state`
> (and `snapshot.custom`) are **parsed into the typed `State` object** (here a
> `TaskState`), not a raw `Map`. `Agent`/`AgentChat`/`AgentResponse` are generic
> over `State`, so the type flows through automatically. Without a
> `stateSchema`,
> `state` is an untyped view over the JSON.

## Auto-sync to the `remoteAgent` client

When you talk to the agent over HTTP, the `remoteAgent` client tracks custom
state for you. Seed it the same way (`state.custom`), read live updates off each
streamed chunk (`chunk.custom`), and read the authoritative state off
`chat.state` after the turn completes.

```dart
import 'package:genkit/client.dart';
import 'package:genkit/experimental_client.dart'; // remoteAgent

final agent = remoteAgent(url: '/api/taskAgent');
final chat = agent.chat(
  state: SessionState(
    custom: {'tasks': <dynamic>[], 'nextId': 1},
    messages: [],
    artifacts: [],
  ),
);

final turn = chat.sendStream(text: 'Add buy groceries, then mark it done');
await for (final chunk in turn.stream) {
  // Live custom state arrives via customPatch chunks:
  if (chunk.custom != null) {
    // e.g. render (chunk.custom as Map)['tasks']
  }
  // chunk.text for model output
}
final res = await turn.response;

// Authoritative state after the turn:
print(res.state);
print(chat.state);
```

State updates ride on the streamed chunks — there is no `onStateChange`
subscription. For live mid-stream status updates from a multi-step custom agent,
see [advanced custom agents](agents-custom.md), which emit `customPatch` chunks
as
state changes.
