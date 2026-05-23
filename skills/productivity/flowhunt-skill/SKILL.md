---
name: flowhunt-skill
description: >-
  Automation discovery audit for business workflows. Walks through a
  5-question intake to understand current tools and pain points, then audits
  connected apps (Gmail, Google Calendar, Slack, task trackers) to surface
  concrete automation opportunities. Use when you want to identify repetitive
  manual tasks that could be automated, evaluate integration gaps between your
  tools, or generate a prioritized list of workflow automations to implement.
---

# FlowHunt Skill

FlowHunt Skill is an automation discovery audit that helps teams identify
and prioritize workflow automation opportunities across their existing tools.

## Installation

```bash
npx skills add heyneuron/flowhunt-skill
```

## How It Works

The skill runs a structured 5-question intake to understand your current
tool stack and workflow pain points, then audits connected services to
surface concrete automation opportunities with estimated time savings.

### Supported Integrations

- **Gmail** — Detects repetitive email patterns, routing bottlenecks, and
  manual reply workflows
- **Google Calendar** — Identifies scheduling friction and meeting
  preparation overhead
- **Slack** — Surfaces notification overload and manual coordination loops
- **Task Trackers** — Asana, Trello, Linear, Jira — finds handoff gaps and
  status-update toil

## Workflow

1. Answer 5 intake questions about your team size, tools, and top pain points
2. The skill audits your connected integrations for automation signals
3. Receive a prioritized automation roadmap with implementation guidance

## Output

The skill produces a structured report with:

- **Quick wins** (< 1 day to implement) — simple automations with high
  immediate value
- **Medium projects** (1–5 days) — integrations requiring moderate setup
- **Strategic automations** — larger initiatives worth investing in

## Source

- **Repository**: [heyneuron/flowhunt-skill](https://github.com/heyneuron/flowhunt-skill)
- **Author**: HeyNeuron (https://heyneuron.com)
