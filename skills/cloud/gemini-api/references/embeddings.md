# Text and Multimodal Embeddings

Generate embeddings across text, images, documents, audio, and video in a single shared semantic space using `gemini-embedding-2` and `client.models.embed_content`. Do not use deprecated legacy models (`text-embedding-004`, `multimodal-embedding-001`, `multimodalembedding@001`).

**Key `types.EmbedContentConfig` options**:
- `output_dimensionality` (`int`, e.g., `768`, `1536`, `3072`): Truncates output vectors to the target dimension.
- `task_type` (`str`): e.g., `"RETRIEVAL_DOCUMENT"`, `"RETRIEVAL_QUERY"`, `"SEMANTIC_SIMILARITY"`, `"CLASSIFICATION"`, `"CLUSTERING"`.
- `title` (`str`): Optional document title (valid only when `task_type="RETRIEVAL_DOCUMENT"`).
- `auto_truncate` (`bool`), `document_ocr` (`bool`), `audio_track_extraction` (`bool`): Gemini platform controls for long inputs, PDFs, and video audio tracks.

```python
from google import genai
from google.genai import types

client = genai.Client()

# 1. Text embeddings (batch list of strings)
text_resp = client.models.embed_content(
    model="gemini-embedding-2",
    contents=[
        "How do I get a driver's license?",
        "How long is my driver's license valid?",
    ],
    config=types.EmbedContentConfig(
        task_type="RETRIEVAL_DOCUMENT",
        output_dimensionality=768,
    ),
)
text_vectors = [emb.values for emb in text_resp.embeddings]

# 2. Image embedding from Cloud Storage (or use types.Part.from_bytes for local files)
image_resp = client.models.embed_content(
    model="gemini-embedding-2",
    contents=types.Part.from_uri(
        file_uri="gs://your-bucket/product.jpg",
        mime_type="image/jpeg",
    ),
    config=types.EmbedContentConfig(output_dimensionality=768),
)
image_vector = image_resp.embeddings[0].values

# 3. Video embeddings (returns one embedding vector per processed video segment)
video_resp = client.models.embed_content(
    model="gemini-embedding-2",
    contents=types.Part.from_uri(
        file_uri="gs://your-bucket/video.mp4",
        mime_type="video/mp4",
    ),
    config=types.EmbedContentConfig(output_dimensionality=768),
)
video_segment_vectors = [emb.values for emb in video_resp.embeddings]
```

Because text, image, and video vectors share the same embedding space, compute cosine similarity or dot products directly across modalities (for example, matching a `"RETRIEVAL_QUERY"` text vector against stored image or video segment vectors).
