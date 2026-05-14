# Skill Lifecycle Management

This document covers state-changing actions (uploading, updating, deleting)
for a skill.

## Upload Skill
Upload a new skill into the Skill Registry using either a zipped package or a
folder.

### Supported Flags

*   `--skill-id` (Required): The unique identifier for the skill.
*   `--display-name` (Required): The human-readable name of the skill.
*   `--description` (Required): A description of what the skill does.
*   `--zip-file` (Required, mutually exclusive with `--folder`): Path to a local
    `.zip` file containing the skill.
*   `--folder` (Required, mutually exclusive with `--zip-file`): Path to a local
    folder containing the skill.

```bash
# Option 1: Upload a skill from a folder (recommended)
python3 scripts/skill_registry_ops.py upload \
  --skill-id "my-sample-skill" \
  --display-name "My Sample Skill" \
  --description "A test skill uploaded via script." \
  --folder "/path/to/skill/folder"

# Option 2: Upload a skill using a .zip file
python3 scripts/skill_registry_ops.py upload \
  --skill-id "my-sample-skill" \
  --display-name "My Sample Skill" \
  --description "A test skill uploaded via script." \
  --zip-file "/path/to/skill.zip"
```
*Note: This returns a long-running operation ID. See `monitor-operations.md`.*

## Update Skill
Update an existing skill's metadata or files. At least one update parameter
must be provided (`--display-name`, `--description`, `--zip-file`, or
`--folder`).

### Supported Flags

*   `--skill-id` (Required): The unique identifier for the skill.
*   `--display-name` (Optional): A new display name for the skill.
*   `--description` (Optional): A new description for the skill.
*   `--zip-file` (Optional, Mutually exclusive with `--folder`): Path to a new
    `.zip` file payload.
*   `--folder` (Optional, Mutually exclusive with `--zip-file`): Path to a new
    folder payload.

```bash
python3 scripts/skill_registry_ops.py update \
  --skill-id "my-sample-skill" \
  --display-name "Updated Name" \
  --description "Updated description." \
  --folder "/path/to/updated/skill/folder"
```
*Note: This returns a long-running operation ID. See `monitor-operations.md`.*

## Delete Skill
Remove a specific skill from the registry forever.

### Supported Flags

*   `--skill-id` (Required): The unique identifier for the skill to delete.

```bash
python3 scripts/skill_registry_ops.py delete --skill-id "my-skill"
```
*Note: This returns a long-running operation ID. See `monitor-operations.md`.*
