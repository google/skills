---
name: cloud-operator-share-context
metadata:
  version: "1.0.0"
  category: CloudInfrastructureAndServices
description: >-
  Shares Google Cloud operating context the user or their team already have —
  environments, projects, services and regions, product preferences, best
  practices, architecture guidance, runbooks — found in agent instruction
  files, local memory, skills and workflows, and the repository's GCP docs,
  with the operator agent's memory after the user reviews the list. Use when
  the user runs this skill, accepts the cloud-operator or cloud-operator-setup
  skill's offer to share their existing Google Cloud context, or asks to share,
  import or save that context or a GCP fact for the operator agent. Don't use
  for ordinary GCP requests, which go to the cloud-operator skill.
---

# Share existing Google Cloud context with the operator agent

Scan agent instruction files, local memory, skills and workflows, and the
repository's GCP docs for context the user or their team already have about
operating in Google Cloud, show it to the user, and copy what they approve into
the operator agent's memory. Use the cloud-operator skill's `project`,
`agentId` and secrets rules, including asking before using their default gcloud
project. Save the project once a call works.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## One fact

If the user runs this skill with a fact, asks to save one GCP fact, or picks
their version after a conflict ([Send](#send), step 6), skip the review. Follow
[Send](#send), `/reflect` included, with the message "Please remember this about
how I work in Google Cloud for future sessions. It's current and replaces
anything you have that conflicts: {fact}". Then confirm in one line.

## Existing Google Cloud context

1. **Ask first**, unless the user just agreed to an offer that named the
   sources. Name them: agent instruction files (`CLAUDE.md`, `AGENTS.md`,
   `GEMINI.md`, `.claude/rules`), local memory, skills and workflows written
   for this user, and GCP docs in this repository. Say that the share takes
   only notes about how they operate in Google Cloud, takes no secrets, and
   shows the list before sending. If local memory notes a confirmed earlier
   share ("shared on"), say when and offer only what's new. Check local memory
   only for an earlier "shared on" note; read nothing else until they agree. If
   they say no, note "declined" (step 4) and stop.
2. **Collect** in three groups, copying what the sources say (names, dates,
   reasons) rather than searching past transcripts:
   - **Facts and preferences:** environments (test, staging, prod) and their
     projects, other projects of interest, the services they manage, regions,
     networks, where IaC and state live, naming, owners, product preferences,
     best practices, architecture guidance (standard patterns, approved
     services, network/landing-zone conventions) and other standing choices.
   - **What happened:** incidents and fixes, migrations, decisions and failed
     attempts, each with its date and outcome.
   - **How things are done:** deploys, rollbacks, failovers, incident
     response, quota or access requests, each as a short summary naming its
     resources, and where its runbook is.

   Put any other note about how they operate in Google Cloud in the closest
   group. Leave out secrets, personal and non-GCP notes, and live state such as
   metrics or bills. Mark notes that apply to one repository only. When local
   sources disagree, keep the newer one (by its date) or ask; a conflict with
   what the operator already has is settled after the save ([Send](#send),
   step 6). If nothing qualifies, say so and stop.
3. **Show the list**, one line per note with its source, and ask: all, some or
   none?
4. **Send** the picks, then **note** in local memory "Cloud Operator context:
   shared on {date}", "declined on {date}" (no or none) or, if `/reflect`
   doesn't confirm, "not confirmed on {date}". Note nothing if a call failed.
   Only "shared on" and "declined on" stop the cloud-operator and
   cloud-operator-setup skills' offers.

## Send

1. Use one new operator session for the whole share: no `contextId` at first,
   then each reply's `context_id`.
2. Write in plain language and the user's voice, without tags or structured
   formats, which the safety filter can reject. Describe procedures as what the
   user does. Leave out empty groups, and above about 30 notes send one group
   per message:

   ```text
   These are notes about how I and my team operate in Google Cloud. Please remember them for future sessions and skip what you already have. If one conflicts with what you know, keep yours and tell me which, with your version and when you learned it. Reply with one line per note.

   Facts and preferences:
   - ...
   What happened:
   - ...
   How we do things:
   - ...
   ```

3. If a call fails with a permission error while earlier calls worked, retry
   once in a new session with everything sent so far, in the same wording, so
   the operator skips notes it already saved. If that fails, tell the user the
   operator refused; mention IAM only if other calls fail too.
4. Send `/reflect` alone, once, after the last message, without waiting on
   anything such as a conflict. The operator may save during the turn too;
   `/reflect` saves everything now.
5. If its reply doesn't say the conversation is being saved (for example,
   "nothing new to save"), the save isn't confirmed and memory may be off. Tell
   the user they can retry later by running this skill again.
6. Otherwise, report briefly what was shared, skipped or flagged. If the
   operator kept its own version of a note, show the user both versions, each
   with its source and date if known: theirs from the list, the operator's from
   its reply. Ask once, for all conflicts, which version is current. Where they
   pick theirs, send it with [One fact](#one-fact), all in one message; it
   replaces the operator's version. Where they pick the operator's or don't
   answer, leave it. If the operator still keeps its own version after that,
   tell the user and stop.
