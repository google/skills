# Genkit Python Examples

Minimal patterns for common Genkit APIs. Examples use **Google AI** (`GoogleAI`, `googleai/...`); other providers use the same patterns with the right plugin and model prefix.

## Public imports

Use public packages only — `genkit`, `genkit_google_genai`, `genkit_fastapi`,
`genkit_middleware`, `genkit_evaluators`, `genkit.agent`, `genkit.embedder`,
`genkit.evaluator`, `genkit.model`, etc. Do not import internal modules
(`genkit._core`, …).

```python
from genkit import Genkit, ActionRunContext
from genkit_google_genai import GoogleAI

ai = Genkit(plugins=[GoogleAI()], model='googleai/gemini-flash-latest')
```

For agents, see [Agents](agents.md) (`from genkit.agent import ...`).

---

## Structured output

```python
from pydantic import BaseModel, TypeAdapter

class CityInfo(BaseModel):
    name: str
    population: int
    country: str

response = await ai.generate(
    prompt='Give facts about Tokyo.',
    output_format='json',
    output_schema=CityInfo,
)
city = response.output

# Arrays
schema = TypeAdapter(list[CityInfo]).json_schema()
response = await ai.generate(
    prompt='List 3 cities.',
    output_format='array',
    output_schema=schema,
)
```

Output formats: `'text'`, `'json'`, `'array'`, `'enum'`, `'jsonl'`.

---

## Streaming (text)

```python
sr = ai.generate_stream(prompt='Tell me a story.')
async for chunk in sr.stream:
    if chunk.text:
        print(chunk.text, end='', flush=True)
final = await sr.response  # final.text
```

You do **not** need to drain `.stream` for the turn to finish — `await sr.response`
completes even if you break out of the loop early (same idea as agent
`send_stream`).

---

## Text and media parts

```python
# Non-streaming
response = await ai.generate(prompt='...')
for media in response.media:
    print(media.content_type, (media.url or '')[:80])

# Streaming — media usually complete on the final response
from genkit import MediaPart

sr = ai.generate_stream(prompt='...')
async for chunk in sr.stream:
    if chunk.text:
        print(chunk.text, end='', flush=True)
final = await sr.response
for media in final.media:
    print(media.content_type, (media.url or '')[:80])

if final.message:
    for part in final.message.content:
        if isinstance(part.root, MediaPart) and part.root.media:
            print(part.root.media.content_type)
```

---


## Sending image / media input

The section above covers **model-produced** media. To *send* an image to Gemini,
build a user `Message` with text + `MediaPart` (URL or data URI):

```python
from genkit import Media, MediaPart, Message, Part, Role, TextPart

image_url = 'https://example.com/cat.jpg'  # or data:image/png;base64,...
msg = Message(
    role=Role.USER,
    content=[
        Part(root=TextPart(text='What is in this image?')),
        Part(root=MediaPart(media=Media(url=image_url, content_type='image/jpeg'))),
    ],
)
response = await ai.generate(messages=[msg])
print(response.text)
```

Prefer a vision-capable model (`googleai/gemini-flash-latest`). URLs are
fetched **server-side** — hotlink-blocked or thumbnail URLs often fail.
Prefer a direct image URL or a data URI:

```python
import base64
b64 = base64.b64encode(Path('cat.png').read_bytes()).decode()
url = f'data:image/png;base64,{b64}'
```


## Streaming + structured output

```python
class StoryAnalysis(BaseModel):
    title: str
    genre: str
    summary: str

sr = ai.generate_stream(
    prompt='Write a short story then analyze it.',
    output_format='json',
    output_schema=StoryAnalysis,
)
async for chunk in sr.stream:
    if chunk.text:
        print(chunk.text, end='', flush=True)
final = await sr.response
analysis = final.output
```

---

## Flows

```python
class SummarizeInput(BaseModel):
    text: str

@ai.flow()
async def summarize(input: SummarizeInput) -> str:
    response = await ai.generate(prompt=f'Summarize: {input.text}')
    return response.text
```

---

## Streaming flows

```python
@ai.flow()
async def stream_story(subject: str, ctx: ActionRunContext) -> str:
    sr = ai.generate_stream(prompt=f'Story about {subject}.')
    full = ''
    async for chunk in sr.stream:
        if chunk.text:
            ctx.send_chunk(chunk.text)
            full += chunk.text
    return full
```

---

## Tools

Parameters must be a **Pydantic `BaseModel`** (bare scalars → 400 from Gemini). Use **`@ai.tool()`**, not `@ai.define_tool()`.

```python
class WeatherInput(BaseModel):
    city: str

@ai.tool()
async def get_weather(input: WeatherInput) -> str:
    return f'Sunny in {input.city}'

response = await ai.generate(prompt='Weather in Paris?', tools=[get_weather])
```

---

## Embeddings

```python
from genkit_google_genai import GoogleAI

embedder = GoogleAI.embedding('gemini-embedding-001')
embeddings = await ai.embed(embedder=embedder, content='The sky is blue.')
vector = embeddings[0].embedding

embeddings = await ai.embed_many(
    embedder=embedder,
    content=['The sky is blue.', 'Grass is green.'],
)
```

Common embedders: `googleai/gemini-embedding-001` (text), `googleai/gemini-embedding-2`
(multimodal: text, image, video). Plain string ids (`embedder='googleai/gemini-embedding-001'`)
also work.

Multimodal input goes in a `Document`:

```python
from genkit import Document

image_embeddings = await ai.embed(
    embedder=GoogleAI.embedding('gemini-embedding-2'),
    content=Document.from_media('data:image/png;base64,...', 'image/png'),
)
```
