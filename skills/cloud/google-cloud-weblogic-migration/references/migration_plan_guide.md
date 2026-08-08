# WebLogic Migration: Technical Stack Alignment & Plan Review Guide

This guide explains how to conduct dynamic technical stack alignment with the
user and manage the interactive review and refinement loop for
`wls-migration-plan.md` during **Phase 2 (Technical Stack Alignment &
Decomposition Review)**.

--------------------------------------------------------------------------------

## Table of Contents

*   [1. Dynamic & Context-Relevant Technical Stack Alignment](#1-dynamic--context-relevant-technical-stack-alignment)
    (Line 22)
*   [2. Initial Generation of wls-migration-plan.md](#2-initial-generation-of-wls-migration-planmd)
    (Line 131)
*   [3. Interactive Human Reviewer Feedback & Refinement Loop](#3-interactive-human-reviewer-feedback--refinement-loop)
    (Line 213)
*   [4. Review Findings Checklist](#4-review-findings-checklist) (Line 243)

--------------------------------------------------------------------------------

## 1. Dynamic & Context-Relevant Technical Stack Alignment

Once you have finalized your microservice topology and exclusion patterns
internally in Phase 1, you must proactively align with the user on target cloud
modernization choices using the `ask_question` tool. Do not write the
`wls-migration-plan.md` artifact yet.

### Dynamic Alignment Rules

The technical stack alignment questions listed below represent strong, highly
relevant baseline examples. However, **you must NOT treat this as a rigid,
static checklist**. Based on your static analysis and blocker discovery in Phase
1, you must dynamically evaluate what technical choices and architectural
decisions are **genuinely relevant** to *this specific monolith*:

*   **Add Custom Questions for Discovered Blockers**: If Phase 1 uncovered
    unique middleware dependencies, custom JCA resource adapters,
    weblogic-specific security providers (JAAS LoginModules), RMI/CORBA
    integrations, third-party scheduling libraries (Quartz/EJB Timers), or
    weblogic-specific caching (Coherence), you MUST formulate and ask custom
    clarifying questions to align on their modernization strategy.
*   **Omit Irrelevant Questions**: If the application has no database
    interactions or no local file I/O, do NOT ask database or file storage
    questions.
*   **Skip Pre-Answered Questions**: If the user's initial prompt or workspace
    context already explicitly specifies target selections (e.g. they requested
    "Migrate this app to Spring Boot on GKE"), do **not** ask those questions.
    Automatically pre-fill the selections and proceed.
*   **Consolidate Questions**: Group all independent alignment questions (e.g.,
    target framework, GCP target service, UI modernization, database choice,
    JMS, sessions) into a single `ask_question` tool call using its native array
    structure. This allows the user to answer them all in a single UI modal,
    reducing human-in-the-loop wait times from multiple turns to one. Only ask
    sequential questions if a later question strictly depends on the answer to a
    previous one.
*   **Tool Execution Fallback**: If the `ask_question` tool is available (e.g.
    in antigravity), you MUST use it to present selectable options. If you are
    running in a generic orchestrator where `ask_question` is not available,
    print the questions and options together as standard markdown text in your
    response and wait for the user to reply.
*   **Ensure Unambiguous Questions & Options**: All questions and options MUST
    be clear, precise, and single-focused. Do NOT group distinct technical
    choices into a single option (e.g., do not combine "React/Angular" into
    "React/Angular SPA"; instead, list "React SPA" and "Angular SPA" as separate
    options). The options must represent concrete, actionable decisions that the
    agent can execute during the refactoring phase.
*   Always include an opinionated, contextually relevant recommendation as the
    first option (prefix the option text with `(Recommended)`), with a short one
    sentence justification.

### Baseline Alignment Questions (Ask Sequentially as Relevant)

1.  **Select Target Framework and Build System**: e.g., `(Recommended) Spring
    Boot with Maven` (if Spring is partially used), or `(Recommended) Quarkus
    with Maven` (for optimal serverless performance).
2.  **Select Target GCP Service**: e.g. `(Recommended) Google Kubernetes Engine`
    (for most enterprise apps), `(Recommended) Cloud Run` (for most web apps) or
    `(Recommended) Cloud Functions` (for event-driven tasks).
3.  **Modernize Web Tier (Presentation Layer)**: Ask how to modernize legacy
    JSPs/Struts UI. Provide options:

    *   `(Recommended) Decouple into a standalone Angular SPA calling REST APIs`
    *   `(Recommended) Decouple into a standalone React SPA calling REST APIs`
    *   `Refactor into server-rendered Spring Boot Thymeleaf`
    *   `Port JSPs directly to embedded Tomcat Jasper`

4.  **Confirm Packaging Preference**: e.g., `(Recommended) Maven Multi-module in
    a Single Repo with a separation of SPA application from the backend`.

5.  **Address Cloud-Unfriendly Patterns & State**: Explicitly prompt the user
    for architectural decisions on discovered blockers using the tool. Provide
    options like:

    *   **HTTP Sessions**: e.g., `(Recommended) Migrate stateful sessions to
        Google Cloud Memorystore (Redis)` or `Refactor to stateless JWTs`
    *   **Batch Processing**: e.g., `(Recommended) Extract batch jobs into
        independent Cloud Run Jobs`
    *   **Email (JavaMail)**: e.g., `(Recommended) Route emails through SendGrid
        API`
    *   **Legacy Remoting (RMI/CORBA)**: e.g., `(Recommended) Refactor to REST
        over HTTP`

6.  **Modernize File Storage (if File I/O is detected)**: If the application
    contains local file operations (`java.io` or `java.nio`), ask how to
    modernize file storage. Provide options:

    *   `(Recommended) Migrate local file access to Google Cloud Storage (GCS)
        (standard cloud object storage)`
    *   `Mount Google Cloud Filestore (NFS) (shared POSIX-compliant file system
        for legacy file operations and concurrent locking)`
    *   `Mount Google Cloud Parallelstore (Managed Lustre) (ultra-high
        performance scratch space for heavy computing/analytics workloads)`

7.  **Select Target Cloud Database (if Database / Oracle / PointBase
    dependencies are detected)**: If the application queries relational
    databases or contains Oracle/PointBase SQL dialects (`(+)` joins, `NVL`,
    `DUAL`, sequences), ask how to modernize the database layer. Provide
    options:

    *   `(Recommended) Google Cloud SQL for PostgreSQL (fully managed relational
        database with standard ANSI SQL / dialect translation)`
    *   `(Recommended) Google Cloud AlloyDB for PostgreSQL (ultra-high
        performance PostgreSQL-compatible enterprise database)`
    *   `Google Cloud SQL for MySQL`
    *   `Google Cloud SQL for SQL Server`
    *   `Google Cloud Spanner (globally distributed relational database)`

--------------------------------------------------------------------------------

## 2. Initial Generation of `wls-migration-plan.md`

Once target stack choices and architectural decisions are aligned, generate the
formal migration plan for human review:

1.  Run the analysis script a final time targeting **only** your selected
    resolution in **markdown** format. Output the result to scatch space
    (e.g.`/tmp/wls_migration_report_raw.md`). Pass your finalized
    `--exclude-patterns` and edge weights to the CLI.

    ```bash
    python3 <script_install_folder>/scripts/cli.py analyze /path/to/target/codebase --format markdown --resolution 1.0 --exclude-patterns ".*Base.*" --output /tmp/wls_migration_report_raw.md
    ```

2.  **Enforce Template Integrity**: Structure your final `wls-migration-plan.md`
    to match the **exact 10-section template** defined in
    [analysis_guide.md](./analysis_guide.md#L108-L139). Do NOT simply dump the
    raw CLI output. You MUST copy, reorganize, and enrich the CLI output to fit
    the template. Ensure NO sections are omitted.

3.  **Integrate Alignments**: Explicitly integrate the user's dynamic technical
    stack selections (such as React/Angular SPA, Spring/Quarkus, and specific
    cloud data mappings) into the appropriate report sections.

4.  **Populate Shared Utility Evaluation (Section 5)**: Explain the
    architectural strategy for the excluded classes (e.g., DTOs/Value Objects).
    Define whether they will be shared via a common Maven module, duplicated, or
    refactored.

5.  **Populate Risks, Warnings, & Architectural Call-Outs (Section 8)**:
    Document all identified risks, including:

    *   Any tool failures during Phase 1 (e.g., if the AST parser crashed and
        you had to fall back to lexical metrics, document this as a risk to
        boundary accuracy).
    *   Database translation risks (e.g., PointBase/Oracle proprietary SQL
        features).
    *   Security concerns (e.g., hardcoded credentials, custom authenticator
        migration).

6.  **Manual Singleton Consolidation**: If the raw CLI report contains
    disconnected singletons (e.g. standalone web filters or 1-class actions
    without database tables) that Louvain could not merge, you MUST manually
    consolidate them in the markdown report (e.g. folding DAOs into their
    respective business services or grouping filters into an API Gateway/common
    library).

7.  **Append Contextualized Deployment & Testing Strategies**: You must
    dynamically author and append two new sections to the bottom of the report
    based on the user's specific alignment choices:

    *   **9. Deployment & Infrastructure-as-Code (IaC) Plan**: Explicitly list
        which Terraform scripts (`main.tf`, `variables.tf`, `outputs.tf`),
        Kubernetes manifests, or `gcloud` commands you will generatively author
        in Phase 5 to deploy their specific target (e.g., Cloud Run vs Cloud
        Functions vs GKE) and provision their requested services (e.g., Cloud
        SQL, Memorystore).
    *   **10. Testing Strategy**: Explicitly explain how you will generatively
        author net-new test suites (e.g., `@WebMvcTest` for Spring Boot vs
        `@QuarkusTest` for Quarkus) to cover their new endpoints, and note that
        un-portable legacy tests (like Cactus) will be strategically disabled
        and documented.

8.  **Tool Execution Fallback**:

    *   If running in antigravity, use the `write_to_file` tool to save the
        customized content as a UI Artifact named `wls-migration-plan.md` (MUST
        include `ArtifactMetadata` with `RequestFeedback: true` and `UserFacing:
        true` to trigger the UI approval flow).
    *   If running in a generic orchestrator, simply save the file as
        `wls-migration-plan.md` using standard file writes, print a summary in
        your response, and explicitly ask the user to type "Approved" to
        proceed.

> [!IMPORTANT] **Wait for Approval**: Once you have saved the
> `wls-migration-plan.md` artifact, you **MUST STOP calling tools immediately to
> end your turn**. Do NOT run any further commands, do not ask further
> questions, and do not perform any other steps in this turn. Wait for the user
> to review the plan and approve it or provide feedback.

--------------------------------------------------------------------------------

## 3. Interactive Human Reviewer Feedback & Refinement Loop

`wls-migration-plan.md` is an **iterative, living review artifact**. When the
human reviewer inspects the plan and leaves review comments or feedback (e.g.,
requesting boundary adjustments, service renaming, package moves, custom
exclusions, or alternative cloud data mappings), you must enter an interactive
refinement loop:

1.  **Read & Analyze Comments**: Read all human reviewer comments and feedback
    attached to the plan.
2.  **Execute Adjustments**:
    *   If the reviewer requests changes to microservice boundaries or
        exclusions, re-run `cli.py` with adjusted weights, `--exclude-patterns`,
        or `--confirmed-utilities`, and re-integrate stack selections.
    *   If the reviewer requests naming changes, package relocations, or
        architectural tweaks, edit the markdown structure directly.
3.  **Overwrite Plan Artifact**: Overwrite the `wls-migration-plan.md` artifact
    with the refined architecture (ensuring `RequestFeedback: true` and
    `UserFacing: true` remain set).
4.  **STOP Calling Tools Immediately**: End your turn immediately upon
    overwriting the artifact to let the human reviewer inspect the updated plan.

> [!IMPORTANT] **Repeat Until Approved**: Repeat this interactive feedback loop
> as many times as necessary until all reviewer comments are satisfactorily
> addressed and the human reviewer explicitly approves the plan (clicking
> "Proceed" or typing "Approved"). Only then may you advance to Phase 3
> (Incremental Refactoring).

--------------------------------------------------------------------------------

## 4. Review Findings Checklist

When reviewing or refining `wls-migration-plan.md`, ensure the following aspects
are verified:

*   **Executive Summary**: Assess the general size of the monolith and total
    WebLogic API dependencies.
*   **Build & Environment**: Verify the target Java version, identify Maven or
    Ant configurations, and check for any local legacy libraries (`lib/*.jar`).
*   **Technical Inventory**: Check EJB volumes, JMS usages, and JNDI lookup
    occurrences. Look for advanced features like Work Managers and SOAP Web
    Services.
*   **Data Access & Security**: Identify JDBC/JPA configurations and
    declarative/programmatic security roles.
*   **Cloud-Unfriendly Patterns**: Note occurrences of local File I/O, HTTP
    Sessions, Batch processing, RMI/CORBA, JMX, and JavaMail.
*   **Proposed Decomposition (Topological Analysis)**: Review the mathematically
    generated microservice boundaries (including the Mermaid diagram) that
    partition packages and database tables to minimize coupling. Ensure
    `wls-migration-plan.md` accurately reflects the final high-quality
    microservices.
