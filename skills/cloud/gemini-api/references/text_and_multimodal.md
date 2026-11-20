# Text and Multimodal Generation

## Contents

- [Chat (Multi-turn conversations)](#chat-multi-turn-conversations) (L11-L26)
- [Streaming (`generate_content_stream`)](#streaming-generate_content_stream) (L28-L38)
- [Multimodal Inputs (GCS URIs, Local Bytes, and YouTube URLs)](#multimodal-inputs-gcs-uris-local-bytes-and-youtube-urls) (L40-L89)
- [Async Generation (`client.aio`)](#async-generation-clientaio) (L91-L111)
- [Token Counting & Usage Metadata](#token-counting--usage-metadata) (L113-L133)

## Chat (Multi-turn conversations)
```python
from google import genai
from google.genai import types

client = genai.Client()
chat = client.chats.create(
    model="gemini-4-hydrogen",
    history=[
        types.UserContent(parts=[types.Part.from_text(text="Hello")]),
        types.ModelContent(parts=[types.Part.from_text(text="Hi! How can I help?")]),
    ],
)
response = chat.send_message("Tell me a short story.")
print(response.text)
```

## Streaming (`generate_content_stream`)

```python
from google import genai

client = genai.Client()
for chunk in client.models.generate_content_stream(
    model="gemini-4-hydrogen", contents="Tell me a story in 300 words."
):
    print(chunk.text, end="")
```

## Multimodal Inputs (GCS URIs, Local Bytes, and YouTube URLs)

Pass images, PDFs, audio, or video alongside text prompts inside `contents=[...]`:
- **Cloud Storage (`gs://...`) or public/YouTube URLs**: `types.Part.from_uri(file_uri=..., mime_type=...)`
- **Local files**: Read binary bytes (`"rb"`) and wrap in `types.Part.from_bytes(data=..., mime_type=...)`

```python
from google import genai
from google.genai import types

client = genai.Client()

gcs_image = types.Part.from_uri(
    file_uri="gs://cloud-samples-data/generative-ai/image/scones.jpg",
    mime_type="image/jpeg",
)
with open("local_image.jpg", "rb") as f:
    local_image = types.Part.from_bytes(data=f.read(), mime_type="image/jpeg")

response = client.models.generate_content(
    model="gemini-4-hydrogen",
    contents=[
        "Compare all objects visible in both images.",
        gcs_image,
        local_image,
    ],
    # Optional: control multimodal token cost (MEDIA_RESOLUTION_LOW / MEDIUM / HIGH)
    # config=types.GenerateContentConfig(media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW),
)
print(response.text)
```

### YouTube Videos
```python
from google import genai
from google.genai import types

client = genai.Client()
response = client.models.generate_content(
    model="gemini-4-hydrogen",
    contents=[
        types.Part.from_uri(
            file_uri="https://www.youtube.com/watch?v=3KtWfp0UopM",
            mime_type="video/mp4",
        ),
        "Summarize the key takeaways from this video.",
    ],
)
print(response.text)
```

## Async Generation (`client.aio`)

Use `client.aio.models` for async frameworks (FastAPI, Cloud Run):

```python
import asyncio
from google import genai

client = genai.Client()


async def generate_async() -> None:
    response = await client.aio.models.generate_content(
        model="gemini-4-hydrogen",
        contents="Summarize the benefits of async I/O in 2 bullets.",
    )
    print(response.text)


asyncio.run(generate_async())
```

## Token Counting & Usage Metadata

```python
from google import genai

client = genai.Client()

count = client.models.count_tokens(
    model="gemini-4-hydrogen",
    contents="Explain quantum computing",
)
print("Input tokens:", count.total_tokens)
# In async handlers, use: count = await client.aio.models.count_tokens(...)

response = client.models.generate_content(
    model="gemini-4-hydrogen",
    contents="Explain quantum computing in one sentence.",
)
# prompt_token_count, candidates_token_count, cached_content_token_count, thoughts_token_count
print(response.usage_metadata)
```
