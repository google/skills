---
trigger: always_on
description: Routing map for the Google Cloud skill catalog.
---

# Google Cloud Skill Routing

This plugin bundles a small subset of the Google Cloud skills. Check which
ones are actually available to you rather than assuming from this file. Many
more exist in the same public catalog and are **not bundled here** - you
cannot read or load those from this plugin until you fetch them.

When a request needs depth the bundled skills do not cover, name the likely
catalog skill and fetch it. Catalog names are predictable:

- `gke-*` - GKE clusters, networking, storage, scaling, cost, AI inference, troubleshooting
- `agent-platform-*` - model deploy, tuning, RAG, eval, endpoints, prompts
- `google-cloud-solution-*` - multi-product reference architectures
- `google-cloud-waf-*` - Well-Architected Framework pillars
- `genkit-*`, `gemini-*` - Genkit SDKs, Gemini APIs
- `cloud-logging-*`, `cloud-monitoring-*` - observability
- `<product>-basics` - BigQuery, Bigtable, Spanner, AlloyDB, Cloud SQL, Cloud Run, Firebase, Storage

If `finding-google-skills` is available to you, use it to search the catalog
rather than guessing from the prefixes above; it fetches the current index and
returns exact entry points. Otherwise browse
https://github.com/google/skills/tree/main/skills/cloud

## How a catalog skill reaches you

Fetching is the normal path and installs nothing. `finding-google-skills`
retrieves a skill's `SKILL.md` over the network and you follow it for the current
request. Nothing is written to the user's system, nothing is added to this
plugin, and the skill is gone when the session ends. Prefer it.

Installing is something the user does with their own tooling. An installed skill
lands in the user's own skills directory, not in this plugin. Whether it works
without a restart depends on their agent, so do not promise it is available
immediately.

A catalog skill never becomes part of this plugin. The plugin's contents are
fixed at the version the user installed, and neither path changes that.

Do not offer installation as the only route to a skill you could fetch. Sessions
are often sandboxed and cannot install without elevated privileges or user
action, so an instruction to install a skill may be something the user cannot act
on.

Never infer a skill's contents from its name. If an answer needs a skill you
cannot read, say so instead of answering from memory.
