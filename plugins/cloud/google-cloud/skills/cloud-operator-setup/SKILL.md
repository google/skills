---
name: cloud-operator-setup
metadata:
  version: "1.5.0"
  category: CloudInfrastructureAndServices
description: >-
  Sets up the user's personal operator agent in a Google Cloud organization via
  the `autocloud` MCP server: finds the organization, checks or creates
  the agent, saves the organization (and the project, if any), and offers to
  share the user's existing Google Cloud operating context with the operator
  agent's memory. Use when the user runs this skill, asks to set up Cloud
  Operator or their operator agent (also in a named organization, but not for
  the whole organization as its administrator), asks to create their agent, or
  chooses setup when the cloud-operator skill asks. Don't use for ordinary GCP
  requests or installing gcloud.
---

# Set up the operator agent

Walk the user through setting up the operator agent one step at a time, in
plain terms (don't name this skill's steps, sections or cases). Follow
the `cloud-operator` skill's `agentId` rules if installed. If the `autocloud`
MCP server doesn't offer `ask_cloud_operator`, it's disconnected: don't set it
up another way. Tell the user how
to sign in again and reconnect, and stop until it's connected
([Server not connected](#server-not-connected)).

If the `cloud-operator` skill sent you here after a call returned "not found"
or "has not been initialized yet" and the user chose this organization, use the
organization it found and go straight to checking the organization (step 2, item
1), skipping the check call and the "Ask where" question.

**Remembering:** where this skill says to remember something, keep it for the
rest of this conversation. Don't create or edit any file to remember it. If
your client has a built-in memory feature, you can also save it there for later
conversations; without one, asking again in a new conversation is fine.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Steps

Each user has one personal operator agent in each Google Cloud organization
they work in, which works on all the projects in that organization. There is no
operator project to choose or create, and no project-level agent: set up the
agent in an organization. Every call names the organization by its numeric ID
(`organizations/{org_id}`). Never set `project`, even when the user asks to set
it up for a project: that call always fails with `RUN_NOT_ALLOWED`. A project
is optional: use one only to find its organization.

1. **Check gcloud and find the organization ID.** Check whether gcloud is
   installed and signed in (gcloud and Application Default Credentials). If
   it's installed but not signed in, ask them to run `gcloud auth login` and
   `gcloud auth application-default login`, or go on without it. Then use the
   organization the user named or that you remember. Otherwise:
   - **Without gcloud** (for example in a web client): ask for the numeric
     organization ID (the console's project picker shows it).
   - **With gcloud:** use the organization of a project the user named, or
     ask which organization (its ID, its domain such as `acme.com`, or a
     project in it). For a domain, run
     `gcloud organizations list --filter="displayName={domain}" --format=json`
     and use the result if there's exactly one. For a project, run
     `gcloud projects get-ancestors {project_id} --format=json` and use the
     `id` of the entry whose `type` is `organization`; if there's none, tell
     the user Cloud Operator doesn't support projects outside an organization
     yet, and stop. Only if they know neither the organization nor a project
     in it, run `gcloud organizations list --format=json`, which only lists
     the organizations they can see: if it shows one, use it; if it shows
     several, ask which one, or for a project in it; if it shows none, ask
     them to get the organization ID or a project in it from an administrator
     or the Google Cloud console.

   If a lookup fails, don't conclude anything about the project: ask for the
   organization. Never guess. Tell the user in one line which organization
   you're using, and that the agent works per organization: "Your operator
   agent works per organization, so I'm setting it up in organization
   `{org_id}`." (add "for project `{project_id}`" when they named one). The
   user asked for setup, so go on even if you remember that Cloud Operator
   wasn't available there. Forget that once the check call works; if it still
   isn't available, remember it (see [Troubleshooting](#troubleshooting)).
2. **Check or create the agent:**
   - Unless the user said they have no agent in that organization, check first:
     call `ask_cloud_operator` with `organization` set to
     `organizations/{org_id}` and "In one line, what can you help me with in
     project {project_id}? Don't create anything." (leave out the project if
     there's none). Tell the user first that it's one read-only check that
     creates nothing, and that it can take 1–3 minutes.
   - If it fails with "personal operator agent … has not been initialized yet",
     or with `agent "…/agents/{id}" not found` on a call without an `agentId`
     (or the user said they have none), there's no agent there, or Cloud
     Operator is turned off for the organization (the error doesn't say which):
     1. **Check the organization, with gcloud.** Any user with access can make
        this call; it creates nothing:

        ```bash
        curl -sS -w '\nHTTP %{http_code}\n' \
          -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
          "https://geminicloudassist.googleapis.com/v1alpha/organizations/{org_id}/locations/global:getOrgEnablement"
        ```

        `{"enabled": true}` means it's on. A 200 response without `enabled` (for
        example `{}`) means it's turned off, and a 403 response with
        `IAM_PERMISSION_DENIED` (for example `Permission
        'geminicloudassist.agents.list' denied`) means no access: see
        [Turned off or no access](#turned-off-or-no-access). On any
        other result, or without gcloud, go on (the console shows these cases).
     2. **Ask where.** Unless they already chose this organization (they named
        it for setup, or it was just turned on or they were just given access
        there), tell them
        they have no operator agent there yet, and ask whether to create one
        there or use another organization where they have one. For another
        organization, go back to step 1.
     3. **Create it in the console.** Walk them through it one step at a time,
        signed in with the same account, and wait for confirmation: open
        `https://console.cloud.google.com/autocloud/agent/create?organizationId={org_id}`,
        click **Get started** to accept the preview terms, choose whether to
        allow data sharing (it's optional), click **Create agent**, and wait
        until it shows **Launch agent** (up to 5 minutes). If the page asks to
        enable Gemini for the organization, says to contact an administrator,
        or shows a permission error, see
        [Turned off or no access](#turned-off-or-no-access).

     Once the agent exists, run the check call above (waiting about a minute
     and retrying up to 3 times if the new agent isn't ready yet). If the user
     was setting up for a request, send that request again afterwards.
   - If the check call fails with `Permission 'geminicloudassist.agents.invoke'
     denied`, `ORG_DISABLED` or `AGENTS_DISABLED`, see
     [Turned off or no access](#turned-off-or-no-access). If it fails with
     "Consumer 'organizations/{id}' is invalid", the organization ID is wrong:
     ask for it again. If it fails with a sign-in error but
     `gcloud auth application-default print-access-token` works, the sign-in is
     fine: check the organization (item 1 above); if it's on, the server's
     connection is the problem: see [Server not connected](#server-not-connected)
     rather than creating an agent. For another error, see
     [Troubleshooting](#troubleshooting).
3. **Remember and offer to share context:** once the check call works,
   remember the organization, with the project if there is one (and `agentId`
   if not their own), and tell the user the operator works, with the
   organization, the project if any, and the agent. In that same reply, if the
   `cloud-operator-share-context` skill is available and you don't remember a
   "Cloud Operator context: shared on" or "declined on" note, ask in one line
   whether to scan agent instruction files, local memory, skills and
   workflows, and the repository's GCP docs for context they or their team
   already have about operating in Google Cloud (environments, projects,
   product preferences, best practices, architecture guidance, runbooks) and
   share it with the operator agent's memory — noting they'll see the list
   first. Read nothing else until they agree.
   - **Yes:** run `cloud-operator-share-context` (from its collection step).
   - **No:** remember "Cloud Operator context: declined on {date}", and don't
     offer again in this conversation.
   - **No answer:** remember nothing.
   Then send any request that was waiting when setup started (don't send
   it again if you already did in step 2).

## Turned off or no access

Cloud Operator is turned off for the organization, or the user has no access
there. Two cases need no administrator:

- **"organization-level agents are not enabled"** (it comes only from creating
  an agent): Cloud Operator isn't available for that organization yet. Tell
  the user, remember it (see [Troubleshooting](#troubleshooting)), and don't
  name a role, retry, or send them to the console to create an agent: none of
  that helps.
- **No access in their home organization, just after the first use there:**
  users get access in their own (home) organization automatically, but only a
  few minutes after anyone there first uses or creates an operator agent. If
  the domain of their account (`gcloud config get-value account`) is the
  organization's display name (`gcloud organizations describe {org_id}
  --format="value(displayName)"`, its primary domain), or they say the
  organization is their own company's, tell them, wait about 2 minutes, and
  repeat the call that failed, for up to about 10 minutes in all. If the
  organization can't be read and they don't know, repeat it once after about
  2 minutes. If it still fails, go on below.

Otherwise only an administrator of the organization can fix either. Use the
`cloud-operator-admin-setup` skill from its "Coming from setup" section, with
the organization ID and the case (turned off, or no access): it
checks whether the user is an administrator, lets an administrator turn it on
or grant access after confirming, and gives anyone else a message for their
administrator. Without that skill, tell the user an administrator turns it on
at
`https://console.cloud.google.com/gemini/admin/onboarding?organizationId={org_id}`,
or grants them `roles/geminicloudassist.user` on the organization.

Offer another organization meanwhile. When it's fixed, wait about a minute (a
few minutes after a role grant, repeating the check call about every 2 minutes
for up to about 15 minutes) and run the check call in step 2 again (they
may already have an agent). If it's still turned off (an administrator chose
**Not now**, or a check after they said it's fixed still shows it off),
remember it (see [Troubleshooting](#troubleshooting)).

## Troubleshooting

### Server not connected

When the `autocloud` MCP server offers no tools, or a call fails with a sign-in
error (for example a 401, "invalid authentication credentials", "Incompatible
auth server", or "Authentication required"):

1. Tell the user in one line that Cloud Operator is disconnected, and why if
   you know (for example, their sign-in expired).
2. Give both fix steps, in order (but check the sign-in first if you can):
   - **If the sign-in works** (`gcloud auth application-default
     print-access-token` prints a token; you can run it yourself), don't tell
     them to sign in again. First do **Check the organization** (in step 2 of
     the setup above): if it's turned off or they have no access, follow
     [Turned off or no access](#turned-off-or-no-access) instead. If it's on,
     or you can't run the check (for example, gcloud doesn't run in your
     sandbox), give the reconnect step, and say the organization wasn't
     checked if you couldn't.
   - **If you can't check the sign-in** (for example, gcloud doesn't run in
     your sandbox), give both steps below: sign in again, then reconnect.
   - **Sign in again.** The user runs `gcloud auth application-default login`
     (you can't: it opens a browser). If a call failed, see
     [Other errors](#other-errors); if `autocloud` offers no tools, still
     reconnect. If the server instead signs in through your own
     MCP settings (OAuth), the user signs in again there.
   - **Reconnect the server.** In Claude Code: `/mcp`, select `autocloud`,
     **Reconnect** (for ADC servers, **Authenticate** doesn't work). In other
     agents, the user restarts the agent. Don't name a command or menu you
     aren't sure you have.
3. Otherwise, stop, and continue the setup once the user says it's connected.
   If it still fails after the user reconnects, don't repeat these steps: say
   their sign-in and the organization look fine, suggest quitting and
   restarting the agent once (not another Reconnect), and stop there.

### Other errors

For an error not listed here, follow the `cloud-operator` skill's
troubleshooting table if it's installed.

When an answer below means Cloud Operator can't be used there (a project
without an organization, `RUN_NOT_ALLOWED` on all 3 attempts with
`organization`, `ORG_DISABLED` or `AGENTS_DISABLED` (or `getOrgEnablement`
showing it off) that stays off, "organization-level agents are not enabled",
or a personal account), remember it with what it applies to and the date, so
that you don't call it there again until the user asks to try again. Write a
`RUN_NOT_ALLOWED` note exactly as "Cloud Operator: not available for
organization {org_id} (RUN_NOT_ALLOWED with organization), {date}": the
`cloud-operator` skill forgets one that doesn't say "with organization".

| Error | Likely cause | What to do |
| --- | --- | --- |
| "… can only be created with an end-user credential" (`USER_CREDENTIAL_REQUIRED`), or "agent_id must be explicitly specified when authenticating as a service account" | The credentials belong to a service account, not to the user | The user signs in with their own account: `gcloud auth application-default login`. If `GOOGLE_APPLICATION_CREDENTIALS` points to a key file, they unset it, because it overrides that sign-in. |
| A permission error when creating the agent, or "The caller does not have permission" | The account can't create or use an operator agent in that organization | See [Turned off or no access](#turned-off-or-no-access). |
| "agent … is not ready to serve yet" | The agent was just created | Wait about a minute and retry the check call, up to 3 times. |
| "This method is not available in this project." (`RUN_NOT_ALLOWED`) from a call that set `project` | Cloud Operator doesn't take project-level calls; this says nothing about the organization | Don't retry with `project`, and don't remember that Cloud Operator isn't available. Make the check call again with `organization` set to the project's organization. |
| "This method is not available in this project." (`RUN_NOT_ALLOWED`) from a call that set `organization` | Cloud Operator isn't available for that organization yet | This check can fail intermittently, especially just after the agent is created, so retry up to 2 more times, about 30 seconds apart (3 attempts in all). If all 3 fail, tell the user Cloud Operator isn't available for that organization yet, remember it, and don't send them to create an agent. |
| "AutoCloud is disabled for organization …" (`ORG_DISABLED`), or "… agents are disabled …" (`AGENTS_DISABLED`) | An administrator turned Cloud Operator off for the organization, or hasn't turned it on | See [Turned off or no access](#turned-off-or-no-access). |
| "Permission denied on resource project {id}" | If `{id}` is the organization ID, `organization` was sent without the `organizations/` prefix. Otherwise the project ID is wrong, or the account can't see the project | Send `organizations/{org_id}`, or check the project ID with the user. |
| An error that personal accounts aren't supported, or the user signs in with a personal Google Account (for example @gmail.com) | Cloud Operator doesn't support personal Google Accounts yet | Tell the user. |
