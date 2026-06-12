# Dataplex Catalog Search for Bigtable

This document provides patterns for searching Bigtable data assets in the
Dataplex Universal Catalog.

## Searching Entries

Searches for entries matching a query in a specific Google Cloud project and
location.

```bash
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
  -H "Content-Type: application/json" \
  "https://dataplex.googleapis.com/v1/projects/${BIGTABLE_PROJECT}/locations/{location}:searchEntries" \
  -d '{"query": "{search_term} system=Bigtable"}'
```

*Example:* Search for "customer list" in `us-east1`:

```bash
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
  -H "Content-Type: application/json" \
  "https://dataplex.googleapis.com/v1/projects/my-project/locations/us-east1:searchEntries" \
  -d '{"query": "customer list system=Bigtable"}'
```
