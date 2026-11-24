"""Example of using the GenAI SDK with Gemini on Vertex AI."""

from google import genai
import google.auth

# Get default project ID from environment
_, project_id = google.auth.default()

# Initialize GenAI Client with Vertex AI backend
# Use location="global" for Preview models (Gemini 2.0)
client = genai.Client(enterprise=True, project=project_id, location="global")

response = client.models.generate_content(
    model="gemini-4-argon", contents="Why is the sky blue?"
)
print(response.text)
