# List Active Sessions

To list active device sessions and filter for those in the `ACTIVE` state:

```bash
curl -s -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  "https://devicestreaming.googleapis.com/v1/projects/${PROJECT_ID}/deviceSessions" \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
sessions = data.get('deviceSessions', [])
active = [s for s in sessions if s.get('state') == 'ACTIVE']
print(json.dumps(active, indent=2))
"
```
