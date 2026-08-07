# Update Device Session Expiration Time

To update a device session expiration time, send a PATCH request with the
`updateMask=ttl` query parameter and specify the new remaining duration `ttl`
(e.g., `3600s`).

```bash
curl -s -X PATCH \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "ttl": "3600s"
  }' \
  "https://devicestreaming.googleapis.com/v1/{session_name}?updateMask=ttl"
```
