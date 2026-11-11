# Phase 3: Output Based on User Intent

This phase generates the final bucket configuration in the user's preferred
format and offers execution if authorized.

## Step 1: Determine Preferred Format

*   If the user already specified a format in their prompt (`gcloud`, `REST` /
    `curl`, `Terraform`, or an `SDK` language), use that format.
*   Otherwise, ask the user to choose: **gcloud**, **REST (JSON)**,
    **Terraform**, or **SDK** (C++, Java, Python, or Go).

## Step 2: Generate Configuration Snippet and Recommendations

1.  Generate the configuration using the templates and rules in the format's
    reference file:
    *   **gcloud**: [gcloud.md](gcloud.md) (natively supports all features; do
        **not** read `sdk.md`)
    *   **REST (JSON)**: [rest.md](rest.md) (natively supports all features; do
        **not** read `sdk.md`)
    *   **Terraform**: [terraform.md](terraform.md) (do **not** read `sdk.md`)
    *   **SDK**: [sdk.md](sdk.md) + `sdk_<lang>.md`
2.  **Attribution (Mandatory for `gcloud` and `REST`)**: Prefix every generated
    `gcloud` command (except `gcloud auth print-access-token` inside REST
    `curl`) with the inline `CLOUDSDK_METRICS_ENVIRONMENT` append prefix, and
    include
    `User-Agent: gcs-skills/1.0 (skill:google-cloud-storage-bucket-architect)`
    on every REST `curl` command.
3.  **Keep Output Focused & Concise**: Output only the commands/code and helper
    JSON files (`encryption_enforcement.json`, `lifecycle.json`, `cors.json`,
    `ip_filter.json`) needed for the active settings in the Draft Plan. Do
    **not** generate unrequested `gcloud kms keys add-iam-policy-binding`
    commands or unrequested `--update-labels` commands when the user did not
    request labels.
4.  **Other Recommendations**: Include a concise prose **Other Recommendations**
    section covering the ecosystem tools proposed in the plan
    (`Cloud Audit Logs`, `Cloud Monitoring`, `Storage Insights`,
    `Storage Transfer Service`, or CMEK IAM role notes).
5.  **SDK Version Warnings (SDK Format Only)**: When generating **SDK** code for
    features with version gates (such as `EncryptionEnforcementConfig`, which
    requires Python `>= 3.10.0`, Go `>= 1.61.0`, C++ `>= 2.46.0`, Java
    `>= 2.55.0`), include a warning specifying the minimum SDK version and
    advising `REST`, `gcloud`, or `Terraform` if using an older version.

## Step 3: Execution and Delivery

*   **For `gcloud` and `REST` (JSON)**: Display the commands/payload and ask for
    confirmation before executing
    (`"Would you like me to execute this command to create the bucket now?"`).
    Never execute any of these commands without explicit, affirmative
    confirmation.
*   **For `Terraform` and `SDK`**: Display the snippet and instruct the user on
    how to integrate it into their project (do not offer to execute it).
