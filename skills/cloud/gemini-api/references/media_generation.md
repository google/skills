# Media Generation

## Image Generation
Generate images using `gemini-3.1-flash-image`.

```python
from google import genai
from google.genai import types

client = genai.Client()

response = client.models.generate_content(
    model="gemini-3.1-flash-image",
    contents="A dog reading a newspaper",
)

for part in response.parts:
    if part.text is not None:
        print(part.text)
    elif part.inline_data is not None:
        image = part.as_image()
        image.save("generated_image.png")
```

For high-resolution images, use `gemini-3-pro-image`.

```python
from google import genai
from google.genai import types

client = genai.Client()

response = client.models.generate_content(
    model="gemini-3-pro-image",
    contents="A dog reading a newspaper",
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

## Image Editing
It is recommended to use chat mode for editing images.

```python
from google import genai
from PIL import Image

client = genai.Client()

prompt = "A small white ceramic bowl with lemons and limes"
image = Image.open("fruit.png")

# Create the chat
chat = client.chats.create(model="gemini-3.1-flash-image")

# Send the image and ask for it to be edited
response = chat.send_message([prompt, image])

# Get the text and the image generated
for i, part in enumerate(response.candidates[0].content.parts):
    if part.text is not None:
        print(part.text)
    elif part.inline_data is not None:
        image = part.as_image()
        image.save(f"generated_image_{i}.png")

# Continue iterating
chat.send_message("Make the bowl blue")
```

## Video Generation with Gemini Omni

`gemini-omni-flash-preview` (Preview) generates and edits video (with synchronized audio) at 720p from text, images, and reference media. Unlike Veo, Omni uses the **Interactions API** (`client.interactions.create`), not `generate_content`/`generate_videos`.

Key configuration:

- **Task** (`interactions.VideoConfig.task`): `text_to_video`, `image_to_video`, `reference_to_video`, or `edit`. Set this to match your inputs and desired behavior.
- **Response format** (`interactions.VideoResponseFormat`): `aspect_ratio` (`16:9` or `9:16`), `duration` (`3s`-`10s`), and `delivery`. These can also be specified directly in the text prompt.
- **Delivery**: To save output to Cloud Storage, set `delivery="uri"` and `gcs_uri="gs://<GCS_BUCKET>"`. Otherwise, video bytes are returned inline (base64).

Notes on output: audio is generated alongside the video, resolution is 720p, and every video includes [C2PA metadata](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/content-credentials) and a [SynthID watermark](https://deepmind.google/technologies/synthid/).

Responses are returned as `interaction.steps`; collect the `content` from each `model_output` step. This helper extracts and saves the video bytes:

```python
import base64
from google import genai
from google.genai import interactions

client = genai.Client()

omni_model = "gemini-omni-flash-preview"


def save_video(interaction, path="output.mp4"):
    contents = []
    for step in interaction.steps:
        if step.type == "model_output":
            contents.extend(step.content)
    with open(path, "wb") as f:
        f.write(base64.b64decode(contents[0].data))
```

### Text-to-video

```python
prompt = "A hard-shell suitcase rolling down a city street at sunset, cinematic tracking shot."

interaction = client.interactions.create(
    model=omni_model,
    input=prompt,
    generation_config=interactions.GenerationConfig(
        video_config=interactions.VideoConfig(task="text_to_video")
    ),
    response_format=interactions.VideoResponseFormat(
        aspect_ratio="16:9",
        duration="9s",
        # delivery="uri",
        # gcs_uri="gs://<GCS_BUCKET>",
    ),
)

save_video(interaction)
```

### Image-to-video

Provide a starting image as the literal first frame. Pass images inline as base64 or by Cloud Storage `uri`.

```python
prompt = "The suitcase stands up, unzips, and colorful travel stickers pop out around it."

with open("suitcase.png", "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode("utf-8")

interaction = client.interactions.create(
    model=omni_model,
    input=[
        {"type": "text", "text": prompt},
        {"type": "image", "mime_type": "image/png", "data": img_b64},
    ],
    generation_config=interactions.GenerationConfig(
        video_config=interactions.VideoConfig(task="image_to_video")
    ),
)

save_video(interaction)
```

### Reference-to-video

Supply reference images (e.g., a character and a product) to guide generation. Reference media acts as a style/subject guide rather than the literal first frame. Video and audio reference inputs are not currently supported.

```python
prompt = "A woman walks up to the arcade game and starts playing. 9:16 aspect ratio. 7 second video."

images_input = []
for img_path in ["woman.jpeg", "arcade-game.png"]:
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")
        images_input.append({"type": "image", "mime_type": "image/jpeg", "data": img_b64})

interaction = client.interactions.create(
    model=omni_model,
    input=[{"type": "text", "text": prompt}, *images_input],
    generation_config=interactions.GenerationConfig(
        video_config=interactions.VideoConfig(task="reference_to_video")
    ),
)

save_video(interaction)
```

### Video editing

Add, remove, or alter objects in a source video, or restyle it. The source video must be under 10 seconds; you can also supply reference images to guide the edit.

```python
prompt = "Change the dog to a cat, remove the backpack, and add a propeller hat."

interaction = client.interactions.create(
    model=omni_model,
    input=[
        {"type": "text", "text": prompt},
        {"type": "image", "mime_type": "image/png", "uri": "gs://cloud-samples-data/generative-ai/image/chair-cat.png"},
        {"type": "video", "mime_type": "video/mp4", "uri": "gs://cloud-samples-data/generative-ai/video/dog_day1.mp4"},
    ],
    generation_config=interactions.GenerationConfig(
        video_config=interactions.VideoConfig(task="edit")
    ),
)

save_video(interaction)
```

### Async generation

Set `background=True` to generate a video you can check on later, then poll with `client.interactions.get`.

```python
import time

initial = client.interactions.create(model=omni_model, input=prompt, background=True)

interaction = initial
while interaction.status not in ["completed", "failed"]:
    time.sleep(10)
    interaction = client.interactions.get(id=initial.id)

if interaction.status == "completed":
    save_video(interaction)
```

### Multi-turn editing (chat)

Iteratively refine a video by passing the previous `interaction.steps` back into `input`, followed by the new user turn.

```python
interaction1 = client.interactions.create(
    model=omni_model,
    input="A claymation ball character rolling and then being stopped by a wall, stop motion.",
)

turn2_input = interaction1.steps + [
    {"type": "user_input", "content": [{"type": "text", "text": "Now make the same video in a doodle style."}]}
]

interaction2 = client.interactions.create(model=omni_model, input=turn2_input)

save_video(interaction2)
```

## Video Generation with Veo
Generate video using the Veo model. Usage of Veo can be costly, so check pricing for Veo. Start with the fast model (`veo-3.1-fast-generate-001`) since the result quality is usually sufficient, and swap to the larger model if needed.

```python
import time
from google import genai
from google.genai import types
from PIL import Image

client = genai.Client()

image = Image.open("image.png")  # Optional initial image

# Video generation is an async operation
operation = client.models.generate_videos(
    model="veo-3.1-fast-generate-001",
    prompt="a cat reading a book",
    image=image,
    config=types.GenerateVideosConfig(
        person_generation="dont_allow",
        aspect_ratio="16:9",
        number_of_videos=1,
        duration_seconds=5,
        output_gcs_uri="gs://your-bucket/your-prefix",
    ),
)

# Poll for completion
while not operation.done:
    time.sleep(20)
    operation = client.operations.get(operation)

if operation.response:
    print(operation.result.generated_videos[0].video.uri)
```
