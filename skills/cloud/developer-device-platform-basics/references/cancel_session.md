# Cancel Session

To cancel a device session, send a POST request with an empty body (`{}`) to the
cancel endpoint:

```bash
curl -s -X POST \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{}" \
  "https://devicestreaming.googleapis.com/v1/{session_name}:cancel"
```
