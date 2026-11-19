# Live API

Stream low-latency bidirectional voice, video, and text over WebSockets using `gemini-3.8-live` and `client.aio.live.connect`.

- **Regional endpoint required**: Live API on Gemini platform requires a regional endpoint (for example, `location="us-central1"`), not `location="global"`.
- **Realtime chunks**: Pass exactly one keyword argument per `session.send_realtime_input(...)` call (`audio=types.Blob(...)` for raw 16kHz PCM audio or `media=types.Blob(...)` / PIL image for video frames).

```python
import asyncio
from google import genai
from google.genai import types


async def run_live_session(audio_bytes: bytes | None = None) -> None:
    # Live API requires a regional endpoint (e.g., us-central1), not global
    client = genai.Client(
        enterprise=True,
        project="your-project-id",
        location="us-central1",
    )
    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],  # Or types.Modality.TEXT
    )

    async with client.aio.live.connect(model="gemini-3.8-live", config=config) as session:
        if audio_bytes is not None:
            await session.send_realtime_input(
                audio=types.Blob(data=audio_bytes, mime_type="audio/pcm;rate=16000")
            )
        else:
            await session.send_client_content(
                turns=types.Content(
                    role="user",
                    parts=[types.Part.from_text(text="Hello! Can you hear me?")],
                ),
                turn_complete=True,
            )

        async for message in session.receive():
            if message.text:
                print(message.text, end="")
            elif message.data:
                # Raw PCM audio output bytes when Modality.AUDIO is active
                pass


asyncio.run(run_live_session())
```
