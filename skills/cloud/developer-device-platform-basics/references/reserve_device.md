# Reserve Device

To reserve a device session, send a POST request to the API:

```bash
curl -s -X POST \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "androidDevice": {
      "androidModelId": "{model_id}",
      "androidVersionId": "{version_id}"
    }
  }' \
  "https://devicestreaming.googleapis.com/v1/projects/${PROJECT_ID}/deviceSessions"
```
