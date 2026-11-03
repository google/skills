# Genkit Examples

This reference contains minimal, reproducible examples (MREs) for common Genkit patterns.

> **Disclaimer**: These examples use **Google AI** models (`googleAI`, `gemini-*`) for demonstration. The patterns apply to **any provider**. To use a different provider:
> 1. Search the docs for the correct plugin: `genkit docs:search "plugins"`.
> 2. Install and configure the plugin.
> 3. Swap the model reference in the code.

## Basic Text Generation

```ts
import { genkit } from "genkit";
import { googleAI } from "@genkit-ai/google-genai";

const ai = genkit({
  plugins: [googleAI()],
});

const { text } = await ai.generate({
  model: googleAI.model('gemini-flash-latest'),
  prompt: 'Tell me a story in a pirate accent',
});
```

## Structured Output

```ts
import { z } from 'genkit';

const JokeSchema = z.object({
  setup: z.string().describe('The setup of the joke'),
  punchline: z.string().describe('The punchline'),
});

const response = await ai.generate({
  model: googleAI.model('gemini-flash-latest'),
  prompt: 'Tell me a joke about developers.',
  output: { schema: JokeSchema },
});

// response.output is strongly typed
const joke = response.output; 
if (joke) {
  console.log(`${joke.setup} ... ${joke.punchline}`);
}
```

## Streaming

```ts
const { stream, response } = ai.generateStream({
  model: googleAI.model('gemini-flash-latest'),
  prompt: 'Tell a long story about a developer using Genkit.',
});

for await (const chunk of stream) {
  console.log(chunk.text);
}

// Await the final response
const finalResponse = await response;
console.log('Complete:', finalResponse.text);
```

## Advanced Configuration

### Thinking Mode

Enable "thinking" process for complex reasoning tasks.

```ts
const response = await ai.generate({
  model: googleAI.model('gemini-pro-latest'),
  prompt: 'what is heavier, one kilo of steel or one kilo of feathers',
  config: {
    thinkingConfig: {
      thinkingLevel: 'HIGH', // or 'LOW'
      includeThoughts: true, // Returns thought process in response
    },
  },
});
```

### Google Search Grounding

Enable models to access current information via Google Search.

```ts
const response = await ai.generate({
  model: googleAI.model('gemini-flash-latest'),
  prompt: 'What are the top tech news stories this week?',
  config: {
    googleSearchRetrieval: true,
  },
});

// Access grounding metadata (sources)
const groundingMetadata = (response.custom as any)?.candidates?.[0]?.groundingMetadata;
if (groundingMetadata) {
  console.log('Sources:', groundingMetadata.groundingChunks);
}
```

## Multimodal Generation

### Image Generation / Editing

Set `responseModalities: ['TEXT', 'IMAGE']` when using image generation models.
Image settings (aspect ratio, size) go in `config.imageConfig`.

```ts
// Generate an image
const { media } = await ai.generate({
  model: googleAI.model('gemini-nano-banana-2.1'),
  config: { responseModalities: ['TEXT', 'IMAGE'] },
  prompt: "generate a picture of a unicorn wearing a space suit on the moon",
});
// media.url contains the data URI
```

```ts
// Edit an image
const { media } = await ai.generate({
  model: googleAI.model('gemini-nano-banana-2.1'),
  config: { responseModalities: ['TEXT', 'IMAGE'] },
  prompt: [
    { text: "change the person's outfit to a banana costume" },
    { media: { url: "https://example.com/photo.jpg" } },
  ],
});
```

### Speech Generation (TTS)

Generate audio from text.

```ts
import { Buffer } from 'node:buffer';
import { writeFile } from 'node:fs/promises';

const { media } = await ai.generate({
  model: googleAI.model('gemini-3.8-flash-tts'),
  config: {
    speechConfig: {
      voiceConfig: {
        prebuiltVoiceConfig: { voiceName: 'Algenib' }, // Options: 'Puck', 'Charon', 'Kore', etc.
      },
    },
  },
  prompt: 'Genkit is an amazing library',
});

// gemini-3.8-flash-tts returns a complete WAV file (audio/wav) as a data URI.
// Streamed requests return raw PCM chunks unless you set
// config.audioFormat: { mimeType: 'audio/wav' }.
if (media?.url) {
  const wav = Buffer.from(media.url.slice(media.url.indexOf(',') + 1), 'base64');
  await writeFile('output.wav', wav);
}
```

Older preview TTS models (`gemini-2.5-*-preview-tts`, `gemini-3.1-flash-tts-preview`)
are deprecated and return raw PCM that needs conversion to WAV. Run
`genkit docs:search "speech audio"` for conversion code.

## Embeddings

```ts
const embedder = googleAI.embedder('gemini-embedding-001');

const embeddings = await ai.embed({ embedder, content: 'The sky is blue.' });
const vector = embeddings[0].embedding; // number[]

const batch = await ai.embedMany({
  embedder,
  content: ['The sky is blue.', 'Grass is green.'],
});

// Optional tuning (default is 3072 dimensions)
await ai.embed({
  embedder,
  content: 'The sky is blue.',
  options: { outputDimensionality: 768, taskType: 'RETRIEVAL_DOCUMENT' },
});
```

Common embedders: `gemini-embedding-001` (text), `gemini-embedding-2`
(multimodal: text, image, video). Plain string ids
(`embedder: 'googleai/gemini-embedding-001'`) also work.

Multimodal input is passed as a document:

```ts
const imageEmbeddings = await ai.embed({
  embedder: googleAI.embedder('gemini-embedding-2'),
  content: {
    content: [{ media: { url: 'data:image/png;base64,...', contentType: 'image/png' } }],
  },
});
```
