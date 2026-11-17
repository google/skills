# Cherry-Picking a Change to Another Branch

> [!CAUTION]
>
> Cherry-picking creates a new change (or new patch set) on the server and MUST
> be explicitly authorized by the user before execution.

Create the backport through Gerrit's cherry-pick command so Gerrit applies the
commit on the server and records the structured link back to the source change:

```bash
scripts/gerrit.py cherry-pick {source_change} --destination={target_branch} --host={host}
```

`scripts/gerrit.py cherry-pick` prints the new change's `number`, `change_id`,
and `cherry_pick_of_change`. Verify `cherry_pick_of_change` (also shown as
`Cherry-Pick-Of:` in `scripts/gerrit.py change {new_change}`) to confirm the
first link below, and compare `change_id` against the source change's
`Change-Id` to confirm the second. Pushing later patch sets preserves
`cherry_pick_of_change`.

Target the current revision (`--revision=current`, the default) to cherry-pick
the revision the source branch actually holds.

## Whether to supply `--message`

**Default: omit `--message`.** When omitted, Gerrit reuses the source commit
message verbatim, including its `Change-Id:` trailer. This is the right choice
for almost every backport.

Supply `--message` (or `--message-file`) only to reword the commit message, or
to strip post-submit footers (`Reviewed-on:`, `Reviewed-by:`) copied onto a
**merged** source change. Check
`scripts/gerrit.py commit-message get {source_change}` first if stripping merged
review footers is needed.

Two constraints apply whenever you pass `--message`:

*   **It replaces the original commit message wholesale.** Include every trailer
    you need to keep (such as `Bug:`); anything omitted is dropped.
*   **It must carry the source change's `Change-Id:` trailer.** Without it,
    Gerrit generates a fresh `Change-Id` and loses the Related Changes link
    below. Read `Change-Id` from `scripts/gerrit.py change {source_change}`
    first.

> [!WARNING]
>
> If a submit requirement on the destination branch checks commit-message
> footers, dropping a required footer makes the backport unsubmittable. Omit
> `--message` in that case.

Write the message to a file and pass `--message-file` (preferred), or use Bash
`$'...'` quoting. In plain double quotes `\n` stays two literal characters, so
the message collapses onto one line, `Change-Id:` is not parsed as a trailer,
and Gerrit silently assigns a fresh `Change-Id`:

```bash
printf '%s\n' '{new_subject}' '' 'Bug: {bug_id}' 'Change-Id: {source_change_id}' \
  > /tmp/cherry_pick_msg.txt
scripts/gerrit.py cherry-pick {source_change} --destination={target_branch} \
  --message-file=/tmp/cherry_pick_msg.txt --host={host}

# Equivalent inline form; note the $'...' quoting
scripts/gerrit.py cherry-pick {source_change} --destination={target_branch} \
  --message=$'{new_subject}\n\nBug: {bug_id}\nChange-Id: {source_change_id}' \
  --host={host}
```

Keep a blank line before the trailer block so `Change-Id:` is parsed as a git
trailer rather than body text.

## The two cherry-pick links in Gerrit

Gerrit surfaces two distinct relationships backed by different fields:

*   **"Cherry pick of"** on the change page reads `cherry_pick_of_change` and
    `cherry_pick_of_patch_set`. Only the REST `/cherrypick` endpoint sets these
    fields, which also power the `cherrypickof:` search operator.
*   **"Cherry picks"** under Related Changes groups changes within the same
    repository that share one `Change-Id` across branches (excluding abandoned
    changes). Reusing the source `Change-Id` on another branch is intentional in
    Gerrit because `(project, branch, Change-Id)` uniquely identifies a change.

Both relationships are scoped to a single repository; cross-repository backports
receive neither link.

Running `git cherry-pick` locally and pushing to `refs/for/{branch}` copies the
`Change-Id` (populating Related Changes) while leaving `cherry_pick_of_change`
unset (`git cherry-pick -x` only appends plain text). Always prefer
`scripts/gerrit.py cherry-pick` so both links are established.

## Failure modes

*   **Merge conflicts**: A conflicting cherry-pick fails by default. Passing
    `--allow-conflicts` creates the change with conflict markers in the tree,
    sets `contains_git_conflicts: true`, and marks the new change
    **work-in-progress** (suppressing reviewer notifications until readied).
*   **Existing destination change**: If an open change on the destination branch
    has the same `Change-Id`, Gerrit adds a new patch set to it instead of
    creating a duplicate; if that change is closed, the request fails.
