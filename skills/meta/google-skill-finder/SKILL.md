---
name: google-skill-finder
description: Discover and install skills from the google/skills repository. Use when the user or agent asks which Google skills exist, wants to find a skill for a task (Google Cloud, GKE, BigQuery, Gemini/Agent Platform, Google Ads, Google Analytics, etc.), or needs the npx command to install one. Reads a bundled local catalog first; refreshes it from the live CLI when a match is not found locally.
license: Apache-2.0
compatibility: Refreshing the catalog requires Node.js (npx) and Python 3.
metadata:
  category: GettingStarted
---

# [Google Skill Finder](https://github.com/google/skills/tree/main/skills/meta/google-skill-finder/)

Finds the right skill in the [`google/skills`](https://github.com/google/skills)
repository and gives the exact command to install it. This skill is **standalone** —
the `google/skills` repo is not assumed to be checked out; the bundled catalog is
the phone directory.

## How to use

1. **Search the local catalog first.** Read [`references/catalog.md`](references/catalog.md).
   It lists every skill as `name`, description, and its install command, grouped by
   category. Match the user's need against the names/descriptions; return the best
   1-3 matches.
2. **Give the install command.** Every skill installs the same way:

   ```bash
   npx skills add google/skills --skill <skill-name> -y
   ```

   Example — installing `google-cloud-recipe-auth`:

   ```bash
   npx skills add google/skills --skill google-cloud-recipe-auth -y
   ```

3. **Report back** with the skill name, its short description, and the command.

## When a skill is NOT found locally (refresh)

`references/catalog.md` is a snapshot; its header carries a generation date. If it
looks stale or has no good match, refresh from the live CLI before concluding a
skill does not exist:

1. Capture the live listing (the CLI renders its UI on stderr, so `2>&1` is
   required):

   ```bash
   npx skills add google/skills -l > /tmp/skills_list.txt 2>&1
   ```

2. Rebuild the catalog:

   ```bash
   python3 scripts/refresh_catalog.py /tmp/skills_list.txt
   ```

   The script auto-trims the CLI's spinner header/footer, parses by indentation,
   and **refuses to overwrite** `references/catalog.md` unless known "canary" skills
   survive and the parsed count matches the CLI's `Found N skills` — so a bad parse
   fails loudly (exit 3) instead of silently corrupting the catalog.

3. Re-run the search against the refreshed catalog. Only then may you tell the user
   "no skill exists for this."

> ⚠️ The refresh path is reviewed and unit-tested on sample input but has **not yet
> been run against live `-l` output end-to-end**. If it errors, fall back to
> reporting the shipped snapshot and its date, and note it may be stale.

## Notes

- The install package is always `google/skills` (the GitHub `owner/repo`), never the
  local directory name or install path.
- The shipped `references/catalog.md` is grouped by each skill's `metadata.category`
  (generated from the repo). CLI refreshes are flat — the CLI does not expose
  category. Both are fine for searching by name/description.
- Keeping the full list in `references/` (loaded on demand) keeps this `SKILL.md`
  small, per the Agent Skills progressive-disclosure model.
