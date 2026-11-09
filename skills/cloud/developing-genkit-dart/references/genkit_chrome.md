# Genkit Chrome AI Plugin (`genkit_chrome`)

Chrome Built-in AI (Gemini Nano) plugin for Genkit Dart, allowing local offline
execution within a Chrome application.

## Usage

```dart
import 'package:genkit/genkit.dart';
import 'package:genkit_chrome/genkit_chrome.dart';

void main() async {
  final ai = Genkit(plugins: [ChromeAIPlugin()]);

  final stream = ai.generateStream(
    model: modelRef('chrome/gemini-nano'),
    prompt: 'Write a story about a robot.',
  );

  await for (final chunk in stream) {
    print(chunk.text);
  }
}
```
