# Session Status

To check the status of a device session, send a GET request to the API:

```bash
curl -s -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  "https://devicestreaming.googleapis.com/v1/{session_name}"
```
