# Describe Device

To see detailed information about a specific device in DDP, send a GET request
to the API using the CATALOG_ID from `gcloud beta device-run devices list`:

```bash
curl \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  "https://devicerun.googleapis.com/v1alpha/projects/${PROJECT_ID}/locations/global/devices/${CATALOG_ID}"
```
