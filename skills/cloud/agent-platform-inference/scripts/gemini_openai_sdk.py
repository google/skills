"""Example of using the OpenAI SDK with Gemini on Vertex AI."""

import google.auth
import google.auth.transport.requests
import openai


def get_gcp_access_token() -> str | None:
  creds, _ = google.auth.default()
  # Refresh credentials using a Request transport object to obtain a fresh
  # OAuth access token for the OpenAI client authorization header.
  creds.refresh(google.auth.transport.requests.Request())
  return creds.token


# Get default project ID from environment
_, project_id = google.auth.default()

client = openai.OpenAI(
    base_url=f"https://aiplatform.googleapis.com/v1/projects/{project_id}/locations/global/endpoints/openapi",
    api_key=get_gcp_access_token(),
)

response = client.chat.completions.create(
    model="google/gemini-4-argon",
    messages=[{"role": "user", "content": "Why is the sky blue?"}],
)
print(response.choices[0].message.content)
