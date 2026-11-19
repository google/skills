# Media Generation

## Contents

- [Image Generation and Editing (Nano Banana)](#image-generation-and-editing-nano-banana) (L11-L53)
- [Video Generation and Editing with Gemini Omni](#video-generation-and-editing-with-gemini-omni) (L55-L155)
- [Video Generation with Veo](#video-generation-with-veo) (L157-L187)
- [Text-to-Speech (TTS)](#text-to-speech-tts) (L189-L268)
- [Music Generation with Lyria](#music-generation-with-lyria) (L270-L291)

## Image Generation and Editing (Nano Banana)

Use `gemini-nano-banana-2.1` for high-resolution/pro image generation and editing, or `gemini-3.1-flash-lite-image` for fast, lightweight generation (do not use deprecated `imagen-3.0*` models). Configure `types.ImageConfig` with `aspect_ratio` (e.g., `"1:1"`, `"16:9"`, `"9:16"`, `"4:3"`, `"3:4"`) and `image_size` (`"1K"`, `"2K"`, or `"4K"`).

```python
from google import genai
from google.genai import types

client = genai.Client()

response = client.models.generate_content(
    model="gemini-nano-banana-2.1",
    contents="A futuristic city at sunset",
    config=types.GenerateContentConfig(
        image_config=types.ImageConfig(aspect_ratio="16:9", image_size="2K")
    ),
)

for part in response.parts:
    if part.text is not None:
        print(part.text)
    elif part.inline_data is not None:
        image = part.as_image()
        image.save("generated_image.png")
```

For iterative image editing, use multi-turn chat (`client.chats.create`):

```python
from google import genai
from PIL import Image

client = genai.Client()
chat = client.chats.create(model="gemini-nano-banana-2.1")

response = chat.send_message(["Add lemons and limes to this ceramic bowl", Image.open("bowl.png")])
for i, part in enumerate(response.parts):
    if part.inline_data is not None:
        part.as_image().save(f"edited_{i}.png")

# Continue refining in subsequent turns
followup = chat.send_message("Now change the bowl color to cobalt blue")
```

## Video Generation and Editing with Gemini Omni

`gemini-omni-1.2-flash` generates and edits video with synchronized audio at up to 4K via the **Interactions API** (`client.interactions.create` — **not** `generate_content` or `generate_videos`). Every output includes [C2PA metadata](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/content-credentials.md.txt) and a [SynthID watermark](https://deepmind.google/technologies/synthid/).

- **Task (`interactions.VideoConfig.task`)**: `"text_to_video"`, `"image_to_video"` (first frame), `"reference_to_video"` (style/subject guide images, audio, or video), `"edit"` (source video <= 15s + optional ref images), `"upscale"`, or `"extend"`.
- **Format (`interactions.VideoResponseFormat`)**: `aspect_ratio` (`"16:9"` or `"9:16"`), `duration` (`"3s"` to `"15s"`, e.g. `"10s"`), `resolution` (lowercase `"360p"`, `"720p"`, `"1080p"`, or `"4k"`), `delivery` (`"uri"` with `gcs_uri="gs://your-bucket/..."`, or omit for inline base64 bytes).

```python
import base64
import time
from google import genai
from google.genai import interactions

client = genai.Client()
omni_model = "gemini-omni-1.2-flash"


def save_video(interaction, path: str = "output.mp4") -> None:
    contents = [c for step in interaction.steps if step.type == "model_output" for c in step.content]
    with open(path, "wb") as f:
        f.write(base64.b64decode(contents[0].data))


# 1. Text-to-video (up to 4K; set delivery="uri" + gcs_uri="gs://..." to write to GCS)
interaction = client.interactions.create(
    model=omni_model,
    input="A hard-shell suitcase rolling down a city street at sunset, cinematic tracking shot.",
    generation_config=interactions.GenerationConfig(
        video_config=interactions.VideoConfig(task="text_to_video")
    ),
    response_format=interactions.VideoResponseFormat(
        aspect_ratio="16:9",
        duration="10s",
        resolution="4k",
    ),
)
save_video(interaction)
```

```python
# 2. Image-to-video (first frame via inline base64 or {"type": "image", "mime_type": ..., "uri": "gs://..."})
with open("suitcase.png", "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode("utf-8")

i2v = client.interactions.create(
    model=omni_model,
    input=[
        {"type": "text", "text": "The suitcase stands up, unzips, and travel stickers pop out."},
        {"type": "image", "mime_type": "image/png", "data": img_b64},
    ],
    generation_config=interactions.GenerationConfig(
        video_config=interactions.VideoConfig(task="image_to_video")
    ),
)
save_video(i2v, "i2v.mp4")

# 3. Reference-to-video (multiple subject/style reference images)
ref_inputs = []
for img_path, mime in [("woman.jpeg", "image/jpeg"), ("arcade-game.png", "image/png")]:
    with open(img_path, "rb") as f:
        ref_inputs.append({"type": "image", "mime_type": mime, "data": base64.b64encode(f.read()).decode("utf-8")})

r2v = client.interactions.create(
    model=omni_model,
    input=[{"type": "text", "text": "The woman walks up to the arcade game and starts playing."}, *ref_inputs],
    generation_config=interactions.GenerationConfig(
        video_config=interactions.VideoConfig(task="reference_to_video")
    ),
    response_format=interactions.VideoResponseFormat(aspect_ratio="9:16", duration="7s"),
)
save_video(r2v, "r2v.mp4")

# 4. Video editing (source video <= 15s + optional reference image)
edited = client.interactions.create(
    model=omni_model,
    input=[
        {"type": "text", "text": "Change the dog to a cat, remove the backpack, and add a propeller hat."},
        {"type": "image", "mime_type": "image/png", "uri": "gs://your-bucket/ref-cat.png"},
        {"type": "video", "mime_type": "video/mp4", "uri": "gs://your-bucket/source_dog.mp4"},
    ],
    generation_config=interactions.GenerationConfig(video_config=interactions.VideoConfig(task="edit")),
)
save_video(edited, "edited.mp4")

# 5. Async background generation & polling
bg = client.interactions.create(model=omni_model, input="Ocean waves crashing on basalt cliffs.", background=True)
while bg.status not in ("completed", "failed"):
    time.sleep(10)
    bg = client.interactions.get(id=bg.id)
if bg.status == "completed":
    save_video(bg, "async.mp4")

# 6. Multi-turn iterative refinement (pass prior interaction.steps + new user_input)
turn2 = client.interactions.create(
    model=omni_model,
    input=interaction.steps + [
        {"type": "user_input", "content": [{"type": "text", "text": "Restyle this video as stop-motion claymation."}]}
    ],
)
save_video(turn2, "turn2.mp4")
```

## Video Generation with Veo

Start with `veo-3.1-fast-generate-001` (fast, cost-efficient default) or `veo-3.1-lite-generate-001` (low-cost preview), and upgrade to `veo-3.1-generate-001` when needed. Veo runs asynchronously via `client.models.generate_videos` + `client.operations.get` (never `generate_content`).

```python
import time
from google import genai
from google.genai import types

client = genai.Client()

operation = client.models.generate_videos(
    model="veo-3.1-fast-generate-001",
    prompt="A cat floating in space",
    # image=Image.open("first_frame.png"),  # Optional starting PIL image
    config=types.GenerateVideosConfig(
        aspect_ratio="16:9",
        duration_seconds=6,  # Veo 3.1 supports 4, 6, or 8 seconds
        number_of_videos=1,
        person_generation="dont_allow",
        output_gcs_uri="gs://your-bucket/veo-outputs",
    ),
)

while not operation.done:
    time.sleep(20)
    operation = client.operations.get(operation)

if operation.response:
    print(operation.result.generated_videos[0].video.uri)
```

## Text-to-Speech (TTS)

Synthesize single- or multi-speaker WAV audio with `gemini-3.8-flash-tts` (studio fidelity, 132 languages) or `gemini-3.8-flash-lite-tts` (low latency, 103 languages; requires `google-genai>=2.33.0`). Expressive style is controlled via `types.SpeechMetadata(style=...)` (plus `speaker=...` with `multi_speaker_voice_config`) and inline vocal tags (`<laugh>`, `<sigh>`, `<short pause>`).

```python
from google import genai
from google.genai import types

client = genai.Client()

response = client.models.generate_content(
    model="gemini-3.8-flash-tts",
    contents=[
        types.Content(
            role="user",
            parts=[
                types.Part(
                    text="Have a wonderful day! <short pause> Welcome aboard.",
                    speech_metadata=types.SpeechMetadata(style="cheerful and friendly"),
                )
            ],
        )
    ],
    config=types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore")
            )
        ),
    ),
)

# inline_data.data contains decoded WAV bytes
with open("out.wav", "wb") as f:
    f.write(response.candidates[0].content.parts[0].inline_data.data)

# Multi-speaker TTS (mutually exclusive with voice_config; provide exactly 2 speakers)
dialogue = client.models.generate_content(
    model="gemini-3.8-flash-tts",
    contents=[
        types.Content(
            role="user",
            parts=[
                types.Part(
                    text="Welcome to the show!",
                    speech_metadata=types.SpeechMetadata(speaker="Alex", style="cheerful"),
                ),
                types.Part(
                    text="Thanks for having me.",
                    speech_metadata=types.SpeechMetadata(speaker="Sam", style="warm"),
                ),
            ],
        )
    ],
    config=types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                speaker_voice_configs=[
                    types.SpeakerVoiceConfig(
                        speaker="Alex",
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore")
                        ),
                    ),
                    types.SpeakerVoiceConfig(
                        speaker="Sam",
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
                        ),
                    ),
                ]
            )
        ),
    ),
)
with open("dialogue.wav", "wb") as f:
    f.write(dialogue.candidates[0].content.parts[0].inline_data.data)
```

## Music Generation with Lyria

Generate `audio/mp3` music from text (and optional image) prompts via `client.interactions.create` (`location="global"`) using `lyria-3-pro-preview` (full tracks up to 184s) or `lyria-3-clip-preview` (30s clips). For GA `:predict` WAV output (32.8s), use `lyria-002`.

```python
import base64
from google import genai

client = genai.Client()

interaction = client.interactions.create(
    model="lyria-3-clip-preview",
    input="Upbeat synthwave track with a driving bassline and retro arpeggios.",
)

for step in interaction.steps:
    if step.type == "model_output":
        for item in step.content:
            if item.type == "audio":
                with open("music.mp3", "wb") as f:
                    f.write(base64.b64decode(item.data))
```
