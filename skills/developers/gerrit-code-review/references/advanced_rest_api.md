# Advanced Gerrit Operations

This reference guide covers advanced or less commonly used Gerrit operations
using the standalone `scripts/gerrit.py` CLI tool.

## Contents

- [Before You Start](#before-you-start): Lines 19-39
- [Attention Set in Gerrit](#attention-set-in-gerrit): Lines 40-55
- [Abandon a Change](#abandon-a-change): Lines 56-68
- [Submit a Change](#submit-a-change): Lines 69-81
- [Manage and Discard Draft Comments](#manage-and-discard-draft-comments): Lines
  82-111
- [Search for Changes and Pagination](#search-for-changes-and-pagination): Lines
  112-147
- [Gerrit Labels and Voting](#gerrit-labels-and-voting): Lines 148-180
- [Manage Topics and Hashtags](#manage-topics-and-hashtags): Lines 181-196

## Before You Start

Authentication and host autodetection are handled automatically by
`scripts/gerrit.py`. The tool reads credentials from `~/.gitcookies` (or the
path configured in `git config http.cookiefile`) and `~/.netrc`, and
auto-detects the Gerrit review host when run inside a git repository. You can
always pass `--host={host}` explicitly.

All mutating operations below require explicit Human-In-The-Loop (HITL) user
confirmation before execution, and all untrusted text output is wrapped in
`<untrusted_gerrit_data>` delimiters unless `--json` or `--raw` is requested.

Placeholders used throughout this file:

*   `{host}` - the Gerrit review host URL, e.g.
    `https://android-review.googlesource.com`
*   `{change}` - a change number or `Change-Id`
*   `{rev}` - a revision SHA or patch set number (defaults to `current`)
*   `{project}` - a repository name (e.g. `platform/frameworks/base`)
*   `{draft_id}`, `{account_email}`, `{tag}` - draft ID, user email, or tag

## Attention Set in Gerrit

The Attention Set tracks whose turn it is to act on a code review. A user stays
in the attention set while the change requires their review or response, and is
typically removed once they reply or vote.

```bash
# List current attention set entries on a change (reasons are free text, so
# the output is wrapped in <untrusted_gerrit_data> unless --json is passed)
scripts/gerrit.py attention {change} --host={host}

# Add or remove a user (write actions: require explicit user authorization)
scripts/gerrit.py attention {change} --user={account_email} --reason="needs review" --host={host}
scripts/gerrit.py attention {change} --user={account_email} --remove --reason="review completed" --host={host}
```

## Abandon a Change

> [!CAUTION]
>
> **Mandatory Human-In-The-Loop Gate**: Abandoning a change is a destructive
> state mutation. Prompt the user for explicit confirmation before calling
> `abandon`.

```bash
scripts/gerrit.py abandon {change} --host={host}
scripts/gerrit.py abandon {change} --message="Superseded by refactor" --notify=ALL --host={host}
```

## Submit a Change

> [!CAUTION]
>
> **Mandatory Human-In-The-Loop Gate**: Submitting merges code into the target
> branch. Verify the change is submittable (required approvals granted, no
> unresolved comments, passing checks) and obtain explicit user confirmation
> before calling `submit`.

```bash
scripts/gerrit.py submit {change} --host={host}
```

## Manage and Discard Draft Comments

> [!CAUTION]
>
> Updating or deleting drafts is a write action that requires explicit user
> authorization before execution.

`scripts/gerrit.py comments publish` sends `"drafts": "PUBLISH_ALL_REVISIONS"`
by default so draft replies anchored on older patch sets are published
atomically. It also supports `--notify=NONE|OWNER|OWNER_REVIEWERS|ALL`,
`--tag={tag}`, and `--attention={account_email}`.

To inspect, edit, or delete unpublished drafts before publishing:

```bash
# List unpublished drafts across all revisions (each entry includes id and patch_set)
scripts/gerrit.py drafts list {change} --host={host}

# View a single draft on its patch set
scripts/gerrit.py drafts get {change} --draft-id={draft_id} --revision={rev} --host={host}

# Update draft text while preserving path, line, range, in_reply_to, and unresolved state
scripts/gerrit.py drafts update {change} --draft-id={draft_id} --revision={rev} \
  --message="Updated draft wording" --host={host}

# Delete one draft or discard all drafts across the change
scripts/gerrit.py drafts delete {change} --draft-id={draft_id} --revision={rev} --host={host}
scripts/gerrit.py drafts discard {change} --host={host}
```

## Search for Changes and Pagination

```bash
scripts/gerrit.py search "status:open+owner:reviewer@example.com" --limit=5 --host={host}

# Fetch changes waiting on your action via Gerrit's Attention Set
scripts/gerrit.py search "attention:self" --limit=10 --host={host}

# Paginate past the first page using --skip (maps to &S={skip} when _more_changes is true)
scripts/gerrit.py search "status:open" --limit=10 --skip=10 --json --host={host}
```

### Search Query Syntax

Combine query terms with `+` for logical AND:

*   `owner:email` - Change owner (author)
*   `reviewer:email` - Change reviewer
*   `project:name` - Repository path (e.g. `project:platform/build`)
*   `branch:name` - Target branch
*   `message:'TEXT'` - Full-text match on commit message body (aliases: `m:`,
    `description:`, `d:`). Text search by default; prefix with `^` for a regular
    expression (e.g. `message:^fix.*leak`)
*   `status:open` / `status:merged` / `status:abandoned` - Change state
*   `mergedafter:YYYY-MM-DD` / `mergedbefore:YYYY-MM-DD` - Submission date
    window
*   `bug:'ID'` - Exact match on a tracking issue ID in the commit message (alias
    `tr:'ID'`; not a regular expression)
*   `attention:email` - Changes in a user's attention set (`attention:self` for
    your turn)

```bash
# Find changes merged after a specific date
scripts/gerrit.py search "owner:reviewer@example.com+mergedafter:2025-01-01" --limit=10 --host={host}
```

## Gerrit Labels and Voting

### List labels and project label definitions

```bash
# List labels and current votes on a change
scripts/gerrit.py labels {change} --host={host}

# List configured (and inherited) label definitions for a repository
scripts/gerrit.py labels --project={project} --host={host}

# Filter repository labels to those voteable on a specific branch/ref
scripts/gerrit.py labels --project={project} --branch=main --host={host}
```

### Vote on labels

Different Gerrit hosts and projects define different labels (for example,
`Code-Review`, `Verified`, `Presubmit-Ready`, or `Commit-Queue`). Voting is a
write action requiring explicit user authorization:

```bash
# LGTM is Code-Review+1
scripts/gerrit.py comments publish {change} --message="LGTM" --labels=Code-Review=1 --host={host}
scripts/gerrit.py comments publish {change} --labels=Presubmit-Ready=1 --host={host}

# Approval (+2) only when the user explicitly asks to approve and has that right
scripts/gerrit.py comments publish {change} --labels=Code-Review=2 --host={host}

# Vote explicitly against the exact patch set number you reviewed
scripts/gerrit.py comments publish {change} --revision=3 --labels=Code-Review=1 --host={host}
```

## Manage Topics and Hashtags

Modifying topics or hashtags is a write action requiring explicit user
authorization:

```bash
# View, set, or delete a topic
scripts/gerrit.py topic {change} --host={host}
scripts/gerrit.py topic {change} --topic="my-feature-topic" --host={host}
scripts/gerrit.py topic {change} --delete --host={host}

# Add, remove, or update hashtags in one call
scripts/gerrit.py hashtags {change} --add="tag1,tag2" --host={host}
scripts/gerrit.py hashtags {change} --remove="tag2" --host={host}
scripts/gerrit.py hashtags {change} --add="tag3" --remove="tag1" --host={host}
```
