---
name: cloud-databases-onboarding
metadata:
  version: "1.0.2"
  category: Databases
description: >-
  Guides users through discovering their database requirements, recommends a
  Google Cloud database based on a recommendation matrix, and assists in database
  creation. Use when a user asks 'What database service should I use?', 'Help me pick
  a database', or when a user wants to create a new database on Google Cloud.
  Don't use for general Google Cloud maintenance, managing existing databases, or database migrations.
---

# Google Cloud Database Onboarding Skill

This skill provides domain instructions, decision matrices, and
Infrastructure-as-Code workflows to guide users through discovering their exact
database requirements, selecting an optimal Google Cloud database service, and
drafting starter resource provisioning code for user review.

## Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read [Usage Attribution](references/attribution.md). For commands executed
directly in the terminal (never in generated scripts, Terraform, or user code),
prefix `gcloud` with
`CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="agent-skills/1.0 (skill:cloud-databases-onboarding)"`
and append `agent-skills/1.0 (skill:cloud-databases-onboarding)` to `User-Agent` headers.

## Validation & Progressive Disclosure

A validation script is provided to verify the skill's reference files and
formatting:

```bash
python3 scripts/database_onboarding_skill.py --verify
```

*   **Reading / Progressive Disclosure:** When interacting with a user during a
    conversation, load reference files progressively. Follow the Just-in-Time
    (JiT) loading instructions outlined in the phases below.

--------------------------------------------------------------------------------

## Workflow & Just-in-Time (JiT) Instructions

This workflow operates in three distinct sequential phases. Evaluate the active
conversation history to determine the current phase and follow the corresponding
instructions:

### Phase 1: Requirement Discovery & Information Gathering

When a user asks `"What database should I use?"` or requires guidance on Google
Cloud database selection, you must initiate the Discovery phase.

1.  **Load Discovery Instructions (JiT):** Read the complete contents of
    `references/onboarding_prompts.md` using `view_file`.
2.  **Execute Discovery:** Follow the detailed Phase 1 instructions in
    `onboarding_prompts.md` to gather core requirements (data model, workload,
    scale, and migration context) using user-friendly phrasing and enforcing
    constraints (such as the 90% confidence rule) before proposing any
    recommendation.

### Phase 2: Recommendation Analysis & Matrix Consultation

Once you have gathered sufficient explicit discovery context, you must determine
the optimal Google Cloud database recommendation.

1.  **Consult Matrix & Formulate Recommendation (JiT):** Follow the Phase 2
    instructions in `references/onboarding_prompts.md`. This involves distilling
    requirements, calling the database selection tool (or consulting
    `references/recommendation_matrix.txt` directly if the tool is unavailable),
    and formulating a single recommendation.
2.  **Deliver Recommendation:** Deliver the recommendation to the user, mapping
    destination codes to plain English, explaining the reasoning, and offering
    to help with provisioning as detailed in `onboarding_prompts.md`.

### Phase 3: Implementation & Provisioning (Plan-Validate-Execute Pattern)

When the user accepts the recommendation and requests to provision or modify
cloud resources, follow the Phase 3 instructions in
`references/onboarding_prompts.md` using a strict **Plan-Validate-Execute** pattern.
Limit your actions to creating and validating draft artifacts for user review.

1.  **Analyze the Workspace:** Scan the user's workspace/open files/related
    directories with database resources scripts.
2.  **Obtain User Confirmation:** If the target infrastructure files are not
    clear, ask the user explicitly to confirm the file paths or target directory
    before modifying anything.
3.  **Draft Infrastructure Plan (Plan):** Create or edit the necessary Terraform
    configuration files or any other relevant scripts necessary to provision the
    resources. When creating or editing Terraform files or any other database
    resource provisioning script, you MUST:

    *   Add a stamped header comment at the top of every generated Terraform
        file/ shell script or any other resource provisioning script. (e.g., `#
        Generated with cloud onboarding skills selector @date`, replacing
        `@date` with the current date/timestamp).
    *   Add a custom default tag like `resource_generated_by = "cloud db
        onboarding skill"` under the `default_tags` block or as a resource
        label/tag.
    *   **gcloud CLI Generation**: When drafting `gcloud` CLI commands or shell
        scripts, you MUST follow the instructions in the `gcloud` skill.
        Specifically:
        *   Always use `gcloud beta` command group for database provisioning
            (e.g., `gcloud beta <group> <resource> create`).
        *   Validate leaf-level syntax using `gcloud help <leaf_command>` prior
            to proposing commands.
        *   Append explicit `--project=<PROJECT_ID>` and explicit location flags
            (`--region`, `--zone`, or `--location`).
        *   Use `--dry-run` or `--validate-only` preview flags where supported.
        *   Include custom label/tag flags (e.g.
            `--labels=resource_generated_by=cloud_db_onboarding_skill`) on
            generated `gcloud` provisioning commands.
        *   **Do NOT include `--quiet` (`-q`)**: Provisioning commands are
            drafted for interactive human user review and execution, so do NOT
            include non-interactive `--quiet` or `-q` flags.
        *   **No Live Write Execution**: The skill MUST ONLY draft provisioning
            commands or code for user review and MUST NOT execute mutating/write
            infrastructure operations directly.

4.  **Validate Infrastructure Code (Validate):** Before finalizing, you must
    validate the drafted infrastructure code to verify syntax and configuration
    correctness. *Why this matters:* Validating Terraform code ensures that
    configuration blocks, IAM bindings, and instance sizing are
    syntax-error-free and strictly enforceable before code review.

5.  **Create Pull Request (Execute):** Once validation succeeds with zero
    errors, automatically create a Pull request containing the validated
    Terraform/shell/scripts updates for user review. Leave live infrastructure
    changes (`terraform apply` or `gcloud` commands) to human review or
    automated CI/CD pipelines.

--------------------------------------------------------------------------------

## Supporting Resources & Documentation

- [Google Cloud Databases Overview](https://cloud.google.com/products/databases)
-   Use the `gcloud` skill for CLI command formatting and validation.
