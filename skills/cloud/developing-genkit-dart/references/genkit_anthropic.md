# Genkit Anthropic Plugin (`genkit_anthropic`)

The Anthropic plugin for Genkit Dart, used for interacting with the Claude
models.

## Usage

Requires `ANTHROPIC_API_KEY` to be passed to the init block.

```dart
import 'dart:io';
import 'package:genkit/genkit.dart';
import 'package:genkit_anthropic/genkit_anthropic.dart';

void main() async {
  final ai = Genkit(
    plugins: [
      anthropic(apiKey: Platform.environment['ANTHROPIC_API_KEY']!),
    ],
  );

  final response = await ai.generate(
    model: anthropic.model('claude-sonnet-4-5'),
    prompt: 'Tell me a joke about a developer.',
    use: [retry()], // recommended for reliable runs
  );
  
  print(response.text);
}
```

## Claude Thinking Configurations

Provides specific configurations for utilizing Claude 3.7+ "thinking" model
capabilities.

```dart
final response = await ai.generate(
  model: anthropic.model('claude-sonnet-4-5'),
  prompt: 'Solve this 24 game: 2, 3, 10, 10',
  config: AnthropicOptions(
    thinking: AnthropicThinkingConfig(budgetTokens: 2048),
  ),
);

// The thinking content is available in the message parts
print(response.message?.content);
```

> **Multi-turn reasoning is preserved.** Thinking blocks are re-sent on later
> turns of a thinking + tool loop, so reasoning is not dropped on the second
> turn. The signature metadata key is `thoughtSignature` (matching the Gemini
> plugins and Genkit JS), and redacted thinking comes back as
> `CustomPart(custom: {redactedThinking})`. History persisted by older versions
> still replays.

> **Overloads are retried.** HTTP 529 (overloaded) maps to `UNAVAILABLE`, so the
> `retry()` middleware retries it instead of surfacing a non-retriable error.
