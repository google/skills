# Phase 1: Project-Level Security Checks

> [!IMPORTANT]
>
> Always verify project-level security settings (TLS 1.2, HTTPS Only, Restrict
> HMAC, and Project Liens) before drafting a bucket configuration. If a project
> is insecure, warn the user and recommend remediation.

## Step 1: Execute Project Verification Commands

*   **When to Skip (`⚠️ Undetermined`)**: Do **NOT** run the 4 checks if the
    user explicitly instructs NOT to run any `gcloud` commands (or not to run
    any commands at all), or gave no project ID (never run them against a
    guessed, placeholder, or `gcloud config` default project; ask for the ID);
    report all 4 as `⚠️ Undetermined` with that reason. *(Note: An instruction
    not to execute bucket creation or modification commands does NOT skip these
    read-only checks.)*
*   **Parallel Execution**: Run the 4 read-only project checks exactly as
    written in `SKILL.md` Step 2, in the same single shell command as the Phase
    2 `gcloud storage buckets describe` check and in the same parallel batch as
    your reference file reads. Every `gcloud` command MUST keep the inline
    `CLOUDSDK_METRICS_ENVIRONMENT` append prefix.

## Step 2: Interpret and Present Results

If you ran the checks, open by noting that a secure bucket also relies on secure
project settings. Present a concise summary of the 4 checks using `✅ Secure`,
`❌ Insecure` (warn and list concise remediation bullets), or `⚠️ Undetermined`
(state the reason, recommend the user contact their system administrator for
help setting these values if they can't set them, and do not output manual
verification command blocks unless requested):

### Status Mapping Table

Check             | Target / Constraint                       | ✅ Secure Condition               | ❌ Insecure Condition                                      | ⚠️ Undetermined Condition
:---------------- | :---------------------------------------- | :------------------------------- | :-------------------------------------------------------- | :------------------------
**TLS 1.2**       | `constraints/gcp.restrictTLSVersion`      | Enforced; denies TLS < 1.2       | Not enforced / allows TLS < 1.2 / Org Policy API disabled | Permission denied (`orgpolicy.policy.get`), VPC-SC, or command restriction
**HTTPS Only**    | `constraints/storage.secureHttpTransport` | `spec.rules[0].enforce == true`  | Not enforced / Org Policy API disabled                    | Permission denied (`orgpolicy.policy.get`), VPC-SC, or command restriction
**Restrict HMAC** | `constraints/storage.restrictAuthTypes`   | Enforced; restricts HMAC keys    | Not enforced / Org Policy API disabled                    | Permission denied (`orgpolicy.policy.get`), VPC-SC, or command restriction
**Project Liens** | `liens list`                              | Non-empty list (at least 1 lien) | Empty list `[]`                                           | Permission denied (`resourcemanager.projects.get`), VPC-SC, or command restriction

### Example Output Presentation

```markdown
### Project-Level Security Posture Assessment

*   ❌ **TLS 1.2 Enforcement**: Insecure (Older TLS versions allowed).
*   ❌ **HTTPS Only**: Insecure (Non-secure HTTP transport allowed).
*   ❌ **Restrict HMAC Keys**: Insecure (HMAC key creation is not restricted).
*   ❌ **Project Liens**: Insecure (No active liens protect project from accidental deletion).

**Remediation Recommendations:**
*   **TLS 1.2 / HTTPS / HMAC**: Enforce `constraints/gcp.restrictTLSVersion`, `constraints/storage.secureHttpTransport`, and `constraints/storage.restrictAuthTypes`.
*   **Project Liens**: Create a project lien via `gcloud alpha resource-manager liens create` to prevent accidental project deletion.
```
