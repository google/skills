# Phase 2: Draft Bucket Create Plan

This phase maps the user's workload to a use case, verifies bucket name
availability, and drafts a secure-by-default bucket configuration plan.

## Step 1: Apply Secure-by-Default Settings

Always recommend and configure these defaults unless the user explicitly
requests otherwise. If the user wants to change them, obtain explicit
confirmation and warn of the security risks (a stricter value of the same
setting, such as a longer soft-delete duration, needs no confirmation, but
disabling or loosening a default always does; if the user explicitly asked for
immediate output without confirmation, follow Handling Conflicts step 3, still
warning):

*   **Uniform Bucket-Level Access (UBLA)**: Enabled.
*   **Restrict Encryption Types**: Restrict Customer-Supplied Encryption Keys
    (CSEK) unless explicitly required.
*   **Soft Delete**: Enabled with the default 7-day retention duration.
    *   *Exception*: For **Rapid/Zonal** buckets, soft delete is NOT supported
        and MUST be disabled (`0` duration).
*   **Public Access Prevention (PAP)**: Enforced.
    *   *Exception*: Set PAP to `inherited` (`--no-public-access-prevention`)
        only when the workload explicitly requires public access (e.g., Static
        Website Hosting, Public VOD Media Hosting) and the user has indicated
        this.

--------------------------------------------------------------------------------

## Step 2: Determine the Use Case

Match the user's workload to the single primary use-case reference file listed
in `SKILL.md` (`sensitive_data.md`, `media_hosting.md`, `ugc_ingestion.md`,
`static_website.md`, `archiving_compliance.md`, `backup_dr.md`,
`log_storage.md`, `storage_for_ai.md`) by default—read multiple use-case files
only when the user explicitly requests combining two distinct use cases. For
**general-purpose** application data buckets without a specialized workload, do
not read any use-case file—apply the Secure-by-Default settings above
(`STANDARD` storage class, `UBLA`, `PAP`, `7d Soft Delete`, `Restrict CSEK`). If
the workload is unclear, apply these defaults and ask the user for
clarification.

Include all **Required** and **Highly Recommended** features and ecosystem
recommendations (`Cloud Monitoring`, `Cloud Logging`, `Storage Insights`,
`Storage Transfer Service`) from the matched reference file(s) in your plan.
*Note: Ecosystem tools are prose architectural recommendations—do NOT search for
or generate separate CLI commands for them unless explicitly requested.*

--------------------------------------------------------------------------------

## Handling Conflicts with Best Practices

If the user explicitly requests a setting that contradicts **Required** or
**Highly Recommended** best practices:

1.  **Warn / Advise Against**: Explain why the requested setting is not
    recommended (e.g., dual-region `nam4` for backups incurs higher cost than
    necessary).
2.  **Recommend Best Practice**: State the recommended alternative from the
    reference file (e.g., Regional bucket + Storage Transfer Service (STS) for
    Backup/DR).
3.  **Confirmation vs. Immediate Output**: In interactive mode, ask whether to
    adopt the recommendation or keep the original request. If the user asked for
    immediate output without confirmation, generate the commands using the
    user's explicitly requested parameters (e.g., `--location=nam4`) while still
    surfacing the warning and recommended alternative.

--------------------------------------------------------------------------------

## Location, Zonal, Retention, and IP Filtering Rules

### Location / Region Handling

*   **Do NOT run commands** like `gcloud compute regions list` or `gcloud
    compute zones list` to verify locations.
*   **Predefined Dual-Regions (`nam4`, `eur4`, `asia1`)**: When `nam4`
    (`us-east1`, `us-central1`), `eur4` (`europe-north1`, `europe-west4`), or
    `asia1` (`asia-northeast1`, `asia-northeast2`) is specified—even if its
    constituent regions are also mentioned—set `--location=nam4` (or
    `eur4`/`asia1`) directly and **NEVER** use `--placement` (Cloud Storage
    rejects custom placement for predefined dual-region pairs with `400`).
*   **Invalid Locations**: If an invalid location (e.g., `Kenya`) is requested:
    (1) state it is not a valid Cloud Storage location, (2) cite
    `https://cloud.google.com/storage/docs/locations`, (3) suggest valid nearby
    regions, and (4) do NOT generate creation commands.

### Zonal Buckets (Rapid Bucket) Constraints

For zonal buckets (AI/ML co-location):

*   **Storage Class**: MUST be `RAPID` (never `STANDARD`).
*   **Soft Delete**: MUST be disabled (`0` duration).
*   **Hierarchical Namespace & UBLA**: Both MUST be enabled.
*   **Location & Placement**: Set location to the region (e.g., `us-east4`) and
    placement to the zone (e.g., `us-east4-a`). Trust the user's zone without
    searching.

### Retention Policy (Bucket Lock vs. Object Lock) & IP Filtering

*   **Bucket Lock vs. Object Lock**: Bucket Lock applies a uniform bucket-wide
    retention period; Object Lock (`--enable-per-object-retention`, set at
    bucket creation) allows per-object `retainUntilTime` WORM timestamps.
    Locking either policy is **permanent and irreversible**.
*   **IP Filtering**: Max 200 CIDR blocks and 25 VPC networks. Regional
    endpoints work with IP filtering only through Private Service Connect (PSC),
    and gRPC direct path is not supported from IPv4-only VMs (IPv6 must be
    enabled on the VPC network). Do NOT use IP filtering if accessed by
    **BigQuery**, **App Engine Standard** (without VPC), or **Cloud Shell**.

--------------------------------------------------------------------------------

## Step 3: Verify Bucket Name Availability

*   **Unspecified Bucket Name Rule**: If the user did not provide a bucket name,
    propose `<project-id>-<use-case>-<6-char-hex>` with a random 6-character hex
    suffix (e.g., `bucket-architect-test-audit-logs-8f4a2c`; drop
    `<project-id>-` if no project ID was given).
*   **Skip Rule**: If the user explicitly instructed NOT to run any `gcloud`/all
    commands, do NOT run this check; report status as `⚠️ Not verified` (citing
    user instruction) and **warn that bucket creation will fail with a 409
    conflict error if the name is already taken**. *(An instruction not to
    execute bucket creation or mutating commands does NOT skip this read-only
    check.)*
*   **Batch Execution**: Run this check as the 5th command in the same single
    shell command as the 4 Phase 1 project checks (`SKILL.md` Step 2), always
    including the inline `CLOUDSDK_METRICS_ENVIRONMENT` prefix. Do **not**
    re-run it for an unchanged name; if the name changes (the user edits it, or
    you propose a replacement), check the new name before using it unless the
    user explicitly forbade running commands.

Outcome                                                                                                                           | HTTP      | Status          | Agent Action
:-------------------------------------------------------------------------------------------------------------------------------- | :-------- | :-------------- | :-----------
Error contains `not found: 404`                                                                                                   | 404       | ✅ Available     | Proceed with the draft plan and output.
Prints bucket metadata, OR error contains `does not have permission` / `buckets.get` denied (even with `"(or it may not exist)"`) | 200 / 403 | ❌ Name taken    | Report that the bucket name is already taken (`403` always means taken by another project; never re-run `describe` with `--project` or dummy names). For **`gcloud` CLI creation**, do **NOT** output `gcloud storage buckets create` for the taken name—ask the user for a different bucket name. For **SDK/Terraform/REST code snippets**, warn that the literal name is taken and must be changed before running (never reuse an existing bucket, whose settings may not match the plan), and still provide the requested code snippet without running extra `describe` commands.
Other failure (auth, network, VPC-SC, command restriction)                                                                        | none      | ⚠️ Not verified | Proceed with plan, state reason, and warn creation will fail with a 409 error if the name is taken.

--------------------------------------------------------------------------------

## Step 4: Present the Draft Plan

> [!CAUTION]
>
> If the plan includes **Bucket Lock** or **Object Lock**, you **MUST** warn
> that locking the policy is permanent and irreversible—once locked, the
> retention period cannot be shortened or removed, and data cannot be deleted or
> overwritten by anyone (including project admins and Cloud Support) until it
> expires. Proceed only after explicitly confirming whether the user wants to
> set the policy to "Locked" or "Unlocked" and for how long. A mode and duration
> stated in the prompt count as confirmation; for an immediate-output request
> without them, don't stop: use Unlocked or placeholders with this warning, and
> never choose Locked yourself.

Present a concise Draft Bucket Creation Plan including the core settings below
plus only the active workload-specific settings and `Other Recommendations`
(omit `Disabled`/`None` bullets for unused features unless asked by the user).
If the user explicitly requested the final commands or code in their prompt,
replace the closing question with a one-line reminder to review the plan and
continue to Phase 3 in the same response:

```markdown
### Draft Bucket Creation Plan

Based on your requirements, we will configure a bucket optimized for **[Use Case Name]**:

*   **Bucket Name**: `[bucket-name]` (✅ Available | ❌ Already exists / Taken | ⚠️ Not verified: [reason])
*   **Project**: `[project-id]`
*   **Location**: `[location]` (and **Placement**: `[zone/regions]` if applicable)
*   **Storage Class**: `[STANDARD | NEARLINE | COLDLINE | ARCHIVE | RAPID]`
*   **UBLA**: Enabled (✅ Secure Default)
*   **Public Access Prevention (PAP)**: Enforced (or `inherited` if public access is required)
*   **Encryption**: `[Google-managed | CMEK: <key>]` with CSEK Restricted (✅ Secure Default)
*   **Soft Delete**: `[7 Days (Default) | <N> Days | 0 Days (Disabled for RAPID)]`
*   **Workload Settings**: `[Include active settings: Autoclass, HNS, OLM rules, Retention Policy, Versioning, CORS, Website Config, Labels, IP Filtering]`
*   **Other Recommendations**: `[Concise prose summary: e.g., Cloud Audit Logs, Cloud Monitoring, Storage Insights, STS]`

Does this draft plan look correct? Please confirm if you'd like to proceed or if you want to make any adjustments.
```
