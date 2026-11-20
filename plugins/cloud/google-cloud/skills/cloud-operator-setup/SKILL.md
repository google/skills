---
name: cloud-operator-setup
metadata:
  version: "1.1.0"
  category: CloudInfrastructureAndServices
description: >-
  Sets up the user's personal operator agent in a Google Cloud organization via
  the `ask_cloud_operator` MCP tool (the autocloud server, or any server that
  offers it): finds the project's organization, checks or creates
  the agent, saves the project and organization, and offers to share the user's
  existing Google Cloud operating context with the operator agent's memory. Use
  when the user runs this skill, asks to set up the operator or create their
  operator agent, or chooses setup when the cloud-operator skill asks. Don't
  use for ordinary GCP requests or installing gcloud.
---

# Set up the operator agent

Walk the user through setting up the operator agent one step at a time. Follow
the `cloud-operator` skill's `agentId` rules if installed. If no MCP server
offers `ask_cloud_operator` (the plugins name it `autocloud`, but any server
name works),
tell the user it isn't connected, help them sign in with Application Default
Credentials (`gcloud auth application-default login`), and stop until they
reconnect.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Steps

Each user has one personal operator agent in each Google Cloud organization
they work in, which works on the projects in that organization. There is no
operator project to choose or create.

1. **Choose the project and find its organization:** ask which Google Cloud
   project they want the operator to work on (unless already named). Suggest
   their default `gcloud` project or the project in local memory only as an
   option; don't use either without asking. Then find the project's
   organization as the `cloud-operator` skill does (`gcloud projects
   get-ancestors {project_id} --format=json`, the `id` of the entry whose
   `type` is `organization`; ask if that fails, never guess). If the project
   has no organization, tell the user Cloud Operator doesn't support projects
   outside an organization yet, and stop. Tell the user in one line which
   organization and project you're using. The user asked for setup, so go on
   even if local memory notes that Cloud Operator wasn't available there.
   Remove that note once the check call works; if it still isn't available,
   save or keep the note (see [Troubleshooting](#troubleshooting)).
2. **Check or create the agent:**
   - Unless the user said they have no agent in that organization, check first:
     call `ask_cloud_operator` with `organization` set to
     `organizations/{org_id}` and "In one line, what can you help me with in
     project {project_id}? Don't create anything." Tell the user first that
     it's one read-only check that creates nothing, and that it can take 1–3
     minutes.
   - If it fails with "personal operator agent … has not been initialized yet",
     or with `agent "…/agents/{id}" not found` on a call without an `agentId`
     (or the user said they have none), create it:
     - **If the MCP server has a tool that creates the operator agent**
       (`manage_agent` with `action=CREATE`, or one whose description says it
       creates the personal operator agent), tell the user in one line that
       they have no operator agent in that organization yet and that you'll
       create it with that tool, and ask them to confirm and whether to allow
       data sharing with Google (it's optional; leave it off unless they say
       yes). Don't create it until they confirm.
       Then call the tool with `organization` set to `organizations/{org_id}`
       and their data-sharing choice passed explicitly (`false` unless they said
       yes). If the tool has no data-sharing input, use the console steps below
       instead, where the user chooses. Before the check call, wait up to 5
       minutes for the agent's state to be `ACTIVE`: an operation that is done
       can still report `CREATING`. If the tool says the agent already exists,
       don't create another: go on to the check call.
     - **Otherwise**, walk them through it one step at a time, signed in with
       the same account, and wait for confirmation: open
       `https://console.cloud.google.com/autocloud/agent/create?organizationId={org_id}`,
       click **Get started** to accept the preview terms, choose whether to
       allow data sharing (it's optional), click **Create agent**, and wait
       until it shows **Launch agent** (up to 5 minutes).

     Once the agent exists, run the check call above (waiting about a minute
     and retrying up to 3 times if the new agent isn't ready yet). If the user
     was setting up for a request, send that request again afterwards.
   - If creating the agent or the check call fails with another error, see
     [Troubleshooting](#troubleshooting).
3. **Save and offer to share context:** once the check call works, save the
   project and its organization in local memory (and `agentId` if not their
   own) and tell the user the operator works, with the organization, the
   project and the agent. In that same reply, if the
   `cloud-operator-share-context` skill is available and local memory has no
   "Cloud Operator context: shared on" or "declined on" note, ask in one line
   whether to scan agent instruction files, local memory, skills and
   workflows, and the repository's GCP docs for context they or their team
   already have about operating in Google Cloud (environments, projects,
   product preferences, best practices, architecture guidance, runbooks) and
   share it with the operator agent's memory — noting they'll see the list
   first. Read nothing else until they agree.
   - **Yes:** run `cloud-operator-share-context` (from its collection step).
   - **No:** note "Cloud Operator context: declined on {date}" in local memory.
   - **No answer:** note nothing.
   Then return to any request that was waiting when setup started.

## Troubleshooting

For an error not listed here, follow the `cloud-operator` skill's
troubleshooting table if it's installed.

When an answer below means Cloud Operator can't be used there (a project
without an organization, `RUN_NOT_ALLOWED` on all 3 attempts,
`ORG_DISABLED`, or a personal account), save it in local memory with what it
applies to and the date, for example "Cloud Operator: not available for
organization 123456789012 (RUN_NOT_ALLOWED), 2026-11-19", so that later
conversations don't call it there until the user asks to try again.

| Error | Likely cause | What to do |
| --- | --- | --- |
| "… can only be created with an end-user credential" (`USER_CREDENTIAL_REQUIRED`), or "agent_id must be explicitly specified when authenticating as a service account" | The credentials belong to a service account, not to the user | The user signs in with their own account: `gcloud auth application-default login`. If `GOOGLE_APPLICATION_CREDENTIALS` points to a key file, they unset it, because it overrides that sign-in. |
| A permission error when creating the agent, or "The caller does not have permission" | The account can't create or use an operator agent in that organization | Tell the user that an administrator of the organization controls access; don't name a role to request. Users in the organization need no role to create their own agent. |
| "agent … is not ready to serve yet" | The agent was just created | Wait about a minute and retry the check call, up to 3 times. |
| "This method is not available in this project." (`RUN_NOT_ALLOWED`) | Cloud Operator isn't available for that organization yet | This check can fail intermittently, especially just after the agent is created, so retry up to 2 more times, about 30 seconds apart (3 attempts in all). If all 3 fail, tell the user Cloud Operator isn't available for that organization yet, save it in local memory, and don't send them to create an agent. |
| "AutoCloud is disabled for organization …" (`ORG_DISABLED`), or "… agents are disabled …" | An administrator turned Cloud Operator off for the organization, or hasn't turned it on | Tell the user to ask an administrator of the organization. |
| "Permission denied on resource project {id}" | If `{id}` is the organization ID, `organization` was sent without the `organizations/` prefix. Otherwise the project ID is wrong, or the account can't see the project | Send `organizations/{org_id}`, or check the project ID with the user. |
| An error that personal accounts aren't supported, or the user signs in with a personal Google Account (for example @gmail.com) | Cloud Operator doesn't support personal Google Accounts yet | Tell the user. |
