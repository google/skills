---
name: cloud-operator-setup
metadata:
  version: "1.0.0"
  category: CloudInfrastructureAndServices
description: >-
  Sets up the operator agent in a Google Cloud project via the autocloud MCP
  server: picks the operator project, creates or checks the user's operator
  agent, saves the project, and offers to share the user's existing Google
  Cloud operating context with the operator agent's memory. Use when the user
  runs this skill, asks to set up the operator or create their operator agent,
  or chooses setup when the cloud-operator skill asks. Don't use for ordinary
  GCP requests or installing gcloud.
---

# Set up the operator agent

Walk the user through setting up the operator agent one step at a time. Follow
the `cloud-operator` skill's `agentId` and troubleshooting rules if installed.
If `ask_cloud_operator` (on the `autocloud` MCP server) isn't available, tell
the user it isn't connected, help them sign in with Application Default
Credentials (`gcloud auth application-default login`), and stop until they
reconnect.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Steps

1. **Choose the project:** ask which Google Cloud project their operator agent
   is in, or will be in (unless already named). Suggest their default `gcloud`
   project or the project in local memory only as an option; don't use either
   without asking.
2. **Check or create the agent:**
   - Unless the user said they have no agent in `{project_id}`, check first:
     call `ask_cloud_operator` with `projects/{project_id}` and "In one line,
     what can you help me with in this project? Don't create anything." Tell
     the user first that it can take 1–3 minutes.
   - If it fails with "personal operator agent … has not been initialized yet"
     (or they said they have none), walk them through creating it one step at a
     time and wait for confirmation: open
     `https://console.cloud.google.com/autocloud/home?project={project_id}`,
     click **Create operator agent**, then click **Get started** when it says
     the agent is ready. Once they confirm, run the check call above (waiting
     about a minute and retrying up to 3 times if the new agent isn't ready
     yet).
3. **Save and offer to share context:** once the check call works, save
   `{project_id}` in local memory (and `agentId` if not their own) and tell the
   user the operator works, with `{project_id}` and the agent. In that same
   reply, if the `cloud-operator-share-context` skill is available and local
   memory has no "Cloud Operator context: shared on" or "declined on" note, ask
   in one line whether to scan agent instruction files, local memory, skills
   and workflows, and the repository's GCP docs for context they or their team
   already have about operating in Google Cloud (environments, projects,
   product preferences, best practices, architecture guidance, runbooks) and
   share it with the operator agent's memory — noting they'll see the list
   first. Read nothing else until they agree.
   - **Yes:** run `cloud-operator-share-context` (from its collection step).
   - **No:** note "Cloud Operator context: declined on {date}" in local memory.
   - **No answer:** note nothing.
   Then return to any request that was waiting when setup started.
