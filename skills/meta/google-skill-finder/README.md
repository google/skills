# google-skill-finder

**Ninety-plus skills in this [google/skills](https://github.com/google/skills) repo. This one helps an agent find the right one — and hand you the command to install it.**

## The problem

The `google/skills` repository keeps growing: Google Cloud, GKE, BigQuery, Gemini /
Agent Platform, Google Ads, Google Analytics, and more. That breadth is the point —
but it creates a discovery problem. To pick the right skill an agent would have to
know the catalog by heart, or clone the repo and read 90+ `SKILL.md` files. Neither
scales, and stuffing every skill's description into the model's context on every
request is exactly the token bloat skills are meant to avoid.

## What this skill does

`google-skill-finder` is a phone directory for the repo. Install this one skill and
an agent can, on demand:

1. **Search** a bundled catalog of every skill — name, one-line purpose, and its
   exact install command.
2. **Return** the copy-paste command for the match:
   `npx skills add google/skills --skill <skill-name> -y`
3. **Refresh** the catalog from the live listing when something looks missing, so a
   stale snapshot never causes a false "no such skill."

No repo clone. No guesswork. One install, and the whole catalog is one lookup away.

## How it's built

```
google-skill-finder/
├── SKILL.md                  # lean instructions the agent loads on activation
├── README.md                 # this file
├── references/
│   └── catalog.md            # the full skill catalog, grouped by category
└── scripts/
    └── refresh_catalog.py    # rebuilds catalog.md from the live CLI listing
```

This layout follows the [Agent Skills specification](https://agentskills.io/specification):
`SKILL.md` for instructions, `references/` for docs read on demand, `scripts/` for
executable helpers. Two design choices make those pieces pull their weight.

## Key features

### 1. Minimal context by design (token-efficient)

The value here is what the model *doesn't* load until it needs to. Each tier is
pulled in only when the task reaches for it:

| Tier | What loads | Size (approx) | When |
| --- | --- | --- | --- |
| 1 | `name` + `description` | ~100 tokens (< 1 KB) | always |
| 2 | `SKILL.md` body | ~3 KB · ~500 words | when the skill activates |
| 3 | `references/catalog.md` | ~50 KB · ~6.5k words | only when finding a skill |

So the catalog can list every skill in the repo while costing almost nothing on
requests that have nothing to do with skill discovery. The heavy file sits in
`references/` and is read only at the moment of the lookup.

### 2. Built-in refresh, so it never goes stale

The catalog ships as a dated snapshot, and the skill can rebuild it on demand. It
asks the CLI for the current list of skills, reads the result, and updates the
catalog when it has changed — so the directory keeps pace with the repo on its own.

```mermaid
flowchart LR
    A[Ask CLI for<br/>current skills] --> B[Read the list]
    B --> C[Update the catalog<br/>if it changed]
```

## Install / uninstall

```bash
npx skills add google/skills --skill google-skill-finder -y   # add the finder
npx skills remove google-skill-finder -y                      # remove it
```

Once installed, finding any other skill is a single lookup that returns its own
`npx skills add ...` command.

## Takeaway

A large skill library is only as useful as it is discoverable. `google-skill-finder`
turns "which of these do I need, and how do I install it?" into a single on-demand
lookup — self-contained, cheap on context, and safe to refresh as the repo grows.
