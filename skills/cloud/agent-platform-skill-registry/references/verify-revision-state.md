# Verify Revision State

This document provides an end-to-end recipe to verify that a skill revision
published to the Skill Registry is actually the revision loaded by a consuming
agent.

## Why This Matters

The Skill Registry distinguishes between:

1.  **Registry default revision** — the revision that the registry marks as
    current for a given skill.
2.  **Runtime-loaded revision** — the revision that a particular agent instance
    has actually loaded and is using.

These are **different facts**. A long-lived or offline agent may still hold an
older revision in its cache even after the registry default changes. Successful
publication does not guarantee consumption.

This recipe helps operators and agents avoid overclaiming by making the
distinction explicit.

---

## Verification Recipe

### Step 1: Upload or update the skill

Perform the upload or update operation. Capture the returned operation ID.

```bash
python3 scripts/skill_registry_ops.py upload \
  --skill-id "my-sample-skill" \
  --display-name "My Sample Skill" \
  --description "A test skill." \
  --folder "/path/to/skill/folder"
```

*Returns an `OPERATION_ID`.*

### Step 2: Monitor the LRO to terminal success

```bash
python3 scripts/skill_registry_ops.py monitor \
  --operation-id "projects/my-project/locations/us-central1/operations/123456789"
```

Wait for the operation to report `done: true`. Record the result.

### Step 3: Get the mutable skill and record the default revision

```bash
python3 scripts/skill_registry_ops.py get --skill-id "my-sample-skill"
```

From the response, extract the `default_revision` field. This is the revision
that the registry considers current.

### Step 4: Fetch the immutable revision metadata

```bash
python3 scripts/skill_registry_ops.py get-revision \
  --skill-id "my-sample-skill" \
  --revision-id "<default-revision-id-from-step-3>"
```

Record the full resource name and metadata of this revision.

### Step 5: Report the verification result

Produce a structured result like the following:

```json
{
  "operation_succeeded": true,
  "registry_default_revision": {
    "revision_id": "abc123",
    "resource_name": "projects/my-project/locations/us-central1/skillRegistries/my-sample-skill/revisions/abc123",
    "create_time": "2026-07-23T12:00:00Z"
  },
  "runtime_loaded_revision": "unknown"
}
```

> **Important:** The `runtime_loaded_revision` field **must** be reported as
> `"unknown"` unless the consuming agent or loader explicitly reports which
> revision it loaded. Registry state is not runtime consumption evidence.

---

## Acceptance Test

A useful test to validate this recipe:

1.  Agent A loads revision `r1` of a skill.
2.  An operator updates the skill; the registry default becomes `r2`.
3.  Agent A continues running **without a reload**.
4.  Run the verification recipe.

The result must be able to say:

- `registry_default_revision`: `r2`
- `runtime_loaded_revision`: `unknown` (or `r1` if the loader reports it)

rather than implying that successful publication proves consumption.

---

## Related

- [Manage Skills](./manage-skills.md) — Upload, update, and delete skills
- [Query Skills](./query-skills.md) — Search, list, and inspect skills
- [Monitor Operations](./monitor-operations.md) — Check LRO status
