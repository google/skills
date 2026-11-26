---
name: cloud-operator-admin-setup
metadata:
  version: "1.0.0"
  category: CloudInfrastructureAndServices
description: >-
  Sets up and manages the Cloud Operator Agent ("Gemini for Google Cloud
  operations" in the console) for a Google Cloud organization: turning it on or
  off, its organization-wide settings, and user access. Use when an
  organization administrator wants to set it up for the whole organization or
  change it, or when Cloud Operator is turned off for the organization or the
  user has no access there. Don't use when someone asks to set up Cloud
  Operator or their operator agent for themselves, even in a named
  organization (use `cloud-operator-setup`).
---

# Set up Cloud Operator for an organization

Go through the steps in order: show the current value, explain each option in
a sentence, and wait for their answer. Ask Steps 5–7 together, in one message:
they can keep all of them or name the ones to change. Every choice is the
administrator's: never recommend accepting the preview terms or any setting,
and change only what they chose. Their choice is the confirmation, and so is a
request that names the new value (for example "don't allow memory"); turning
Cloud Operator on or back on, and granting a role, always need their reply
first (Step 4, Give a user access). Send a change once they choose it; for
Steps 5–7, send only the ones they changed, in one request. Talk to the user in
plain terms: don't name this skill's steps, sections or cases.

| They ask to | Do |
| --- | --- |
| Set up Cloud Operator for the whole organization (as its administrator) | Steps 1–8 |
| Change one setting | Steps 1–3, that step (Step 4 first if it's off), Step 8 |
| Turn Cloud Operator back on | Steps 1–4, then Step 8 |
| Turn Cloud Operator off | [Turn it off](#turn-it-off) |
| Give someone access | [Give a user access](#give-a-user-access) |
| Their agent can't be created because it's turned off or they have no access (sent by another skill) | [Coming from setup](#coming-from-setup) |

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

## Step 1: gcloud

The calls below need gcloud signed in as an administrator of the organization,
with Application Default Credentials
(`gcloud auth application-default print-access-token` works); say which
account you'll use. Both sign-ins must be the same account: the API calls use
Application Default Credentials, while the role grant and
`gcloud config get-value account` use the gcloud sign-in. You can't see the
Application Default Credentials account directly, so ask them to confirm they
used the same account for both. Ask it in the same reply as Step 3's read;
you need their answer only before the first change. If it's installed but not
signed in, they run `gcloud auth login` and
`gcloud auth application-default login`. Otherwise, or if signing in fails,
use [the console](#without-gcloud-the-console), or they install gcloud
(https://docs.cloud.google.com/sdk/docs/install-sdk.md.txt) first. Without
gcloud, don't reach the APIs another way (for example by reading credential
files or creating tokens).

## Step 2: Organization ID

Calls use the numeric ID. Take it from the user or the error they saw, or ask
for its ID, domain or a project in it: resolve a domain with
`gcloud organizations list --filter="displayName={domain}" --format=json`
(if several match, ask which), a project with
`gcloud projects get-ancestors {project_id} --format=json` (the `id` of the
entry whose `type` is `organization`; if there's none, Cloud Operator works
only in organizations: stop). If a lookup fails or finds nothing, ask for the
ID; never guess. Before changing anything, say which organization and account
you're using, for example "Setting up Cloud Operator for organization
{org_id} as {account}."

## Step 3: Read the settings

```bash
curl -sS -w '\nHTTP %{http_code}\n' \
  -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
  "https://geminicloudassist.googleapis.com/v1alpha/organizations/{org_id}/locations/global/agentAdminSettings"
```

| Result | Do |
| --- | --- |
| 200 | Keep the `etag`. Show Gemini usage (`enablementState`), agent memory (`memoryDisabled`), agent actions (`effectiveMutationMode`) and data sharing (`effectiveDataSharingAvailability`) |
| 403 `IAM_PERMISSION_DENIED` | The account can't manage these settings (an Organization Administrator can). If they asked to set up Cloud Operator without saying it's for the whole organization, they may only want their own agent: use `cloud-operator-setup` instead (it tells turned off from no access). If it may be the wrong account, they switch (Step 1); otherwise give them the [message for their administrator](#message-for-an-administrator) and stop |
| 401, or `ACCESS_TOKEN_TYPE_UNSUPPORTED` | Credentials: Step 1 once more, then the console |
| 400 "Consumer 'organizations/{id}' is invalid", or 404 | Wrong ID: ask for it; if they confirm it, stop |
| Anything else | Show the error and offer the console |

The response leaves out false fields: no `memoryDisabled` means memory is
allowed, no `writePreviewEnrolled` means not enrolled.

## Step 4: Gemini usage

| `enablementState` | Tell them | Choice | On yes, send |
| --- | --- | --- | --- |
| `ENABLED` | It's on, under the [preview terms](#preview-terms) | — | — |
| `EXCLUDED`, no `disableTime` | It isn't on. Name the `exclusionReasons` (for example VPC Service Controls, CMEK, Assured Workloads, data residency, a Business Associate Agreement, EU billing), or if there are none, that it isn't on by default. Then [what enabling doesn't change](#what-enabling-doesnt-change) and the [preview terms](#preview-terms) | **Enable** / **Not now** | `{"previewAcceptance": true, "agentsDisabled": false, "etag": "{etag}"}`, `updateMask=previewAcceptance,agentsDisabled` |
| `EXCLUDED` with `disableTime` | Google turned it off then, for those reasons; sessions can be exported until `disableTime` + 30 days, then everything is deleted. Then as above | **Restore** / **Not now** | Same |
| `DISABLED_BY_ADMIN` | An administrator turned it off on `disableTime`; agents and sessions are deleted 30 days later (give that date with its year: it can fall in the next year). Then the [preview terms](#preview-terms) | **Restore** / **Not now** | `{"agentsDisabled": false, "etag": "{etag}"}`, `updateMask=agentsDisabled` |

[Send it](#sending-a-change) only after an explicit **Enable** or **Restore**
in their reply, even when they asked to turn it on or back on (show the state
and the terms first), and check the response shows `ENABLED`. If a Restore
comes back `EXCLUDED`, continue with that row: name the `exclusionReasons`,
and send **Enable** (with `previewAcceptance`) only on their choice. Then read
the settings again (Step 3) and use that read for Steps 5–7: enabling can change
`writePreviewEnrolled`, `effectiveDataSharingAvailability` and the `etag`.
Then continue as routed. On **Not now**,
stop: the other settings can't change while it's off ([coming from
setup](#coming-from-setup), go back to the skill that sent them).

## Step 5: Agent memory

**Allow** (users can turn on memory, so their agents remember context across
sessions) or **Don't allow** (no memories saved or recalled in new sessions;
existing ones are paused, not deleted). If it changes, send `memoryDisabled`
(`true` = don't allow).

## Step 6: Agent actions

Without `writePreviewEnrolled`, agents stay read only (the organization isn't
in the write preview): say so and skip. Otherwise, from `effectiveMutationMode`:
**Read only** (agents inspect resources, logs and metrics but change nothing) or
**Read and write** (they can also create and update resources; every change
needs the user's approval). If it changes, send `mutationMode` (`READ_ONLY` or
`WRITE_WITH_APPROVAL`). "Write actions are in private preview" means not
enrolled.

## Step 7: Data sharing

If `effectiveDataSharingAvailability` is `NOT_AVAILABLE_IN_REGION` (billed in
the EEA, Switzerland or the UK), say so and skip. Otherwise **Allow** (users may
opt in to sharing interaction data with Google; off for each user until they do)
or **Don't allow** (no one can opt in). If it changes, send
`dataSharingWithGoogleDisabled` (`true` = don't allow).

## Step 8: Summary

Read the settings again and show the four values. Tell them changes take about
a minute to apply. Offer `cloud-operator-setup` for their own agent.

## Coming from setup

`cloud-operator-setup` (or `cloud-operator`) sends a user here when their
operator agent can't be created or used because Cloud Operator is turned off
for the organization, or they have no access there. They may not be an
administrator. You already have the organization ID, and the other skill says
which case it is. If it doesn't, do a Step 3 read first: `ENABLED` means no
access, anything else means turned off; if the read returns 403 (here that
doesn't stop you), ask the user what the page or error said, and if that
doesn't tell, cover both cases. If
gcloud stops working here (for example a 401), use the **Without gcloud** reply
below instead of the full console walkthrough. When done, go back to the skill
that sent them, saying what changed (or that nothing did); after a change, that
skill waits about a minute and runs its check call again before anything
else.

- **Without gcloud:** you can't check, so cover both in one reply: an
  administrator turns it on at
  `https://console.cloud.google.com/gemini/admin/onboarding?organizationId={org_id}`
  (**Enable Gemini**, which accepts the preview terms for the whole
  organization) or grants access under **IAM & Admin** > **IAM**; anyone else
  sends the [message for their administrator](#message-for-an-administrator).
- **Turned off:** say which organization and account you're using, and do Step
  3. On 403, they aren't an administrator: give them the enable
  [message](#message-for-an-administrator). On 200, do Step 4 only (if it's
  already `ENABLED`, the problem is access instead: continue with **No access**
  below); the other settings keep their defaults and can be changed later.
- **No access:** users get access without a role only in their own (home)
  organization, the one their account belongs to; elsewhere an administrator
  grants `roles/geminicloudassist.user`. First check whether this is their home
  organization: compare the domain of their account (`gcloud config get-value
  account`) with the organization's name (`gcloud organizations describe
  {org_id} --format="value(displayName)"`, its primary domain).
  - **Same:** their home organization, where users normally have access, so an
    administrator has restricted it.
  - **Different** (most likely another organization; a secondary domain of the
    same company is possible): they need the role.
  - **Can't tell** (the organization can't be read): cover both in one reply.

  In every case, check whether they can grant it themselves (read-only):

  ```bash
  curl -sS -w '\nHTTP %{http_code}\n' -X POST \
    -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
    -H "Content-Type: application/json" \
    -d '{"permissions": ["resourcemanager.organizations.setIamPolicy"]}' \
    "https://cloudresourcemanager.googleapis.com/v3/organizations/{org_id}:testIamPermissions"
  ```

  If it returns HTTP 200 with the permission, confirm that gcloud and
  Application Default Credentials are signed in as the same account (as in
  Step 1), then offer to grant
  `roles/geminicloudassist.user`
  to their own account, saying it lets them create and use their own operator
  agent in that organization; if they accept, run the grant in
  [Give a user access](#give-a-user-access) directly (their acceptance is the
  confirmation; you already have the organization). If it returns HTTP 200
  without it, give them the access [message](#message-for-an-administrator)
  (in their home organization, asking to restore access instead). On any other
  error, you can't tell: cover both in one reply.

## Give a user access

Users can create an agent without a role only in their home organization;
elsewhere they need `roles/geminicloudassist.user` on the organization. Give
it when a user's call to their agent fails with a permission error (for example
`Permission 'geminicloudassist.agents.invoke' denied`), or when the
administrator asks to give someone access. Do Steps 1–2 unless coming from
setup, which already has them. If you don't know
whether Cloud Operator is on, also run Step 3: if it's off, say the role won't
help until it is, and if it returns 403, skip the check and go on since it only
means they can't read the settings. Get the member
(`user:{email}`, `group:{email}` or `domain:{domain}`; never guess) unless the
caller gave it. Confirm once what it allows (creating and using their own
operator agent in that organization) and wait for their yes, even when they
named the member; skip this only when another skill sent you here after the
user agreed there. Then grant only that role:

```bash
gcloud organizations add-iam-policy-binding {org_id} \
  --member="{member}" --role="roles/geminicloudassist.user" --condition=None
```

A permission error means the account can't change the organization's IAM
policy. An allowed-domains error means the organization's domain-restricted
sharing policy blocks that domain: tell them (a member from an allowed domain
would work) and don't change the policy. Without gcloud: **IAM &
Admin** > **IAM** in the console. It can take a few minutes to apply. If another
skill sent them, go back to it, saying whether it was granted.

## Turn it off

After Steps 1–3 (if it isn't `ENABLED`, it's already off: say so and stop),
warn them: all
operator agents in the organization stop immediately; users have 30 days to
export their sessions; then all agents and sessions are permanently deleted;
they can restore it within those 30 days. Ask them to type `disable` to
confirm; anything else cancels. Then [send](#sending-a-change)
`{"agentsDisabled": true, "etag": "{etag}"}` with
`updateMask=agentsDisabled`, check for `DISABLED_BY_ADMIN`, and give the
deletion date with its year (`disableTime` + 30 days; it can fall in the next
year).

## Without gcloud: the console

Ask for the numeric organization ID (you can't look it up) and walk them
through
`https://console.cloud.google.com/gemini/admin/onboarding?organizationId={org_id}`
as an administrator (without the ID, leave out `?organizationId=…` and they
pick the organization at the top).

- **Welcome page:** "enabled" → **Continue to settings**. "Disabled" → it shows
  the preview terms; **Enable Gemini** accepts them for the whole organization,
  then **Continue to settings**. A page to create their own agent instead means
  they aren't an administrator: [message for their
  administrator](#message-for-an-administrator).
- **Organization settings:** the same choices as Steps 4–7: **Gemini usage**
  (**Restore**, or **Disable** with the [warning](#turn-it-off) and typing
  `disable`), **Agent memory**, **Agent actions** (shown only if enrolled),
  **Data sharing**; then **Save**.
- **Access:** **IAM & Admin** > **IAM**, role `roles/geminicloudassist.user`.

## Reference

### Sending a change

Send only the changed fields, named in `updateMask` (comma-separated), with
the `etag` from your last read:

```bash
curl -sS -w '\nHTTP %{http_code}\n' -X PATCH \
  -H "Authorization: Bearer $(gcloud auth application-default print-access-token)" \
  -H "Content-Type: application/json" \
  -d '{"memoryDisabled": true, "etag": "{etag}"}' \
  "https://geminicloudassist.googleapis.com/v1alpha/organizations/{org_id}/locations/global/agentAdminSettings?updateMask=memoryDisabled"
```

The response is the updated settings: check the value and keep its `etag`. A
409 `ABORTED` ("Provided etag is out of date") means the settings changed
since your read: read again. If none of the values you showed them changed
(only the `etag`, as right after enabling), resend with the new `etag`
without asking. Otherwise show what changed and ask again about your change
(skip it if it's already there). For any other error (for example a 403 when
the account can read the settings but not change them), show it and stop.

### What enabling doesn't change

With VPC Service Controls (`VPC_SC`), agents still can't reach projects inside
a service perimeter. With EU billing (`EU_BILLING_ACCOUNT`), data sharing stays
off. Mention the ones that apply.

### Preview terms

Show in full before enabling or restoring: "This product is subject to the
Pre-GA Offerings Terms in the General Service Terms section of the Service
Specific Terms (https://cloud.google.com/terms/service-terms) and the
Additional Terms for Generative AI Preview Products
(https://cloud.google.com/trustedtester/aitos), and should not be used with
personal data or other data subject to legal or regulatory compliance
requirements. By enabling it, you acknowledge and agree to these
terms on behalf of your organization. You can turn it off at any time."

### Message for an administrator

- **Enable:** "Please turn on Gemini for Google Cloud operations (Cloud
  Operator) for our organization {org_id}. As an organization administrator,
  open
  https://console.cloud.google.com/gemini/admin/onboarding?organizationId={org_id}
  or run the cloud-operator-admin-setup skill."
- **Access:** "Please grant me ({email}) roles/geminicloudassist.user on
  organization {org_id} so I can create my Gemini for Google Cloud operations
  (Cloud Operator) agent:
  `gcloud organizations add-iam-policy-binding {org_id} --member="user:{email}"
  --role="roles/geminicloudassist.user" --condition=None`"

Adjust it to what they need, for example "turn it back on".
