# Advanced Custom Agents — `defineCustomAgent`

> `ai.defineCustomAgent` is experimental and comes from
> `package:genkit/experimental.dart`. Read [agents.md](agents.md) and
> [agent state](agents-state.md) first.

`defineAgent` runs a single prompt + tool loop. When you need **full control of
the turn** — multiple sequential model calls, custom logic between them, manual
message/state management, or custom progress streaming — use
`ai.defineCustomAgent`. You provide the handler that runs the turn.

- [When to use it](#when-to-use-it): Lines 19-29
- [Signature](#signature): Lines 31-62
- [Example: multi-step research agent](#example-multi-step-research-agent): Lines 64-174
- [Custom status streaming](#custom-status-streaming): Lines 176-199

---

## When to use it

Reach for `defineCustomAgent` when a turn needs to:

- make **multiple model calls** with your own orchestration between them;
- run **multi-step workflows** (decompose → research → synthesize);
- **manually manage** messages and custom state;
- **stream custom status** updates to the client mid-turn.

Otherwise prefer `defineAgent` (simpler; custom state still works — see
[agent state](agents-state.md)).

## Signature

```dart
Agent<State> defineCustomAgent<State>({
  required String name,
  String? description,
  SchemanticType<State>? stateSchema,
  SessionStore? store,
  ClientTransform? clientTransform,
  required AgentFn fn, // (SessionRunner sess, AgentFnOptions options) => Future<AgentResult>
});
```

The handler receives a session runner `sess` and `AgentFnOptions options`
(`options.sendChunk(...)` streams chunks to the client; `options.context` holds
the ambient [per-turn context](agents.md#per-turn-ambient-context) — e.g. auth,
derived server-side for remote agents). It returns an `AgentResult`, typically
carrying the final `message` for the turn (`AgentResult.message` is nullable —
pass `message: null` when the turn produced no message).

Key `sess` methods:

- `sess.run((input, ctx) async {...})` — runs the turn; adds `input.message`
  (the incoming user message) to the session before calling your callback, so
  `sess.getMessages()` includes it. `input.message?.content` holds the parts.
- `sess.getMessages()` — the full message history.
- `sess.addMessages([...])` — append messages (e.g. your final model response).
- `sess.updateCustom(mutator)` / `sess.getCustom()` — read and mutate typed
  custom state directly on the runner (no `ai.currentSession()` needed). The
  mutator is `(State? state) => State`; each call auto-emits a `customPatch`
  chunk. Its typing follows `stateSchema` — with the map schema below the state
  is `Map<String, dynamic>?`; with a generated `.$schema` it's your typed class.

## Example: multi-step research agent

```dart
import 'package:genkit/genkit.dart';
import 'package:genkit/experimental.dart'; // defineCustomAgent, SessionRunner
import 'package:schemantic/schemantic.dart';

import 'genkit.dart';

Map<String, dynamic> _state(Map<String, dynamic>? custom) {
  if (custom == null) {
    return {'subQuestions': <dynamic>[], 'subAnswers': <dynamic>[]};
  }
  return custom;
}

final researchAgent = ai.defineCustomAgent(
  name: 'researchAgent',
  stateSchema: .map(.string(), .dynamicSchema()),
  fn: (sess, options) async {
    Message? lastMessage;

    await sess.run((input, ctx) async {
      final userText = input.message?.content.firstOrNull?.text ?? '';

      // Step 1: decompose (a fast model). Mutating custom state auto-emits a
      // `customPatch` chunk so the client's tracked state stays live.
      sess.updateCustom((s) {
        final state = _state(s);
        state['status'] = 'Decomposing question into sub-topics…';
        return state;
      });

      final decompose = await ai.generate(
        model: liteModel,
        prompt: 'Break this into 2-3 sub-questions. Return ONLY a JSON array '
            'of strings.\nUser question: "$userText"',
        use: [retry()],
        outputFormat: 'json',
        outputSchema: SchemanticType.list(SchemanticType.string()),
      );
      final subQuestions =
          (decompose.output ?? [userText]).map((e) => e.toString()).toList();

      sess.updateCustom((s) {
        final state = _state(s);
        state['subQuestions'] = subQuestions;
        state['subAnswers'] = <dynamic>[];
        return state;
      });

      // Step 2: research each sub-question (main model).
      final subAnswers = <Map<String, dynamic>>[];
      for (var i = 0; i < subQuestions.length; i++) {
        sess.updateCustom((s) {
          final state = _state(s);
          state['status'] =
              'Researching (${i + 1}/${subQuestions.length})';
          return state;
        });
        final research = await ai.generate(
          use: [retry()],
          prompt: 'Answer concisely in 2-3 paragraphs.\n\n'
              'Question: ${subQuestions[i]}',
        );
        subAnswers.add({'question': subQuestions[i], 'answer': research.text});
      }
      sess.updateCustom((s) {
        final state = _state(s);
        state['subAnswers'] = subAnswers;
        return state;
      });

      // Step 3: synthesize and STREAM the final answer to the client.
      sess.updateCustom((s) {
        final state = _state(s);
        state['status'] = 'Synthesizing final response…';
        return state;
      });

      final synthesis = ai.generateStream(
        use: [retry()],
        prompt: 'Synthesize a unified markdown answer to "$userText" from:\n'
            '${subAnswers.map((a) => '${a['question']}: ${a['answer']}').join('\n\n')}',
      );
      await for (final chunk in synthesis) {
        options.sendChunk(AgentStreamChunk(modelChunk: chunk.modelChunk));
      }
      final finalResponse = await synthesis.onResult;
      lastMessage = finalResponse.message;
      if (lastMessage != null) sess.addMessages([lastMessage!]);

      sess.updateCustom((s) {
        final state = _state(s);
        state['status'] = 'Done';
        return state;
      });

      return null;
    });

    return AgentResult(
      message: lastMessage ??
          Message(
            role: Role.model,
            content: [TextPart(text: 'Research complete.')],
          ),
    );
  },
);
```

## Custom status streaming

Calling `sess.updateCustom(...)` during the turn automatically emits a
`customPatch` chunk, so the `remoteAgent` client's tracked
[custom state](agents-state.md) (e.g. the `status` field) stays live
**mid-stream** without any extra wiring. Stream model output separately with
`options.sendChunk(AgentStreamChunk(modelChunk: ...))`.

Seed and run a custom agent exactly like a regular one:

```dart
final chat = researchAgent.chat(
  state: SessionState(
    custom: {'subQuestions': <dynamic>[], 'subAnswers': <dynamic>[]},
    messages: [],
    artifacts: [],
  ),
);
final turn = chat.sendStream(text: 'Impacts of electric vehicles?');
await for (final chunk in turn.stream) {
  // chunk.text for model output; chunk.custom['status'] for live progress
}
await turn.response;
```
