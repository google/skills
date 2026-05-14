# Monitor Operations

This document covers how to monitor the status of Long-Running Operations (LRO)
returned by lifecycle management actions (uploading, updating, or deleting a
skill).

## Check Operation Status

Check the status of a long-running operation using its `OPERATION_ID` (or full
resource name).

### Supported Flags

*   `--operation-id` (Required): The unique identifier or full resource name of
    the long-running operation returned from previous commands.

```bash
python3 scripts/skill_registry_ops.py monitor \
  --operation-id "projects/my-project/locations/us-central1/operations/123456789"
```
