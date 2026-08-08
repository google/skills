# WebLogic Migration Verification, Audit, & Traceability Guide

This guide provides detailed procedural instructions for executing Phase 6
(Verification, Audit, & Traceability) of the WebLogic migration workflow.

## 1. Map Endpoints (Traceability Matrix)

Compile an API mapping table showing before/after routes:

*   Legacy URLs (e.g., Struts `/editProfile.do` or EJB remote methods) vs.
    Migrated REST URLs (e.g., `/api/profile/save`).
*   Map incoming parameter formats (Form payload vs. JSON payload).

## 2. Validate Integration, Database Schema & Security Gates

Locally spin up the migrated services (running in Dev mode or against a
Dockerized test database) and execute verification assertions:

*   **Execute Integration and Security Assertions**: Run mock HTTP calls (e.g.,
    using `curl` or automated integration scripts) to verify:
    *   *Access Verification on Secured Routes*: Verify that endpoints mapped to
        legacy security constraints (secured routes) return `401 Unauthorized`
        (or `403 Forbidden`) when queried without credentials or with an invalid
        token.
    *   *Access Verification on Public Routes*: Verify that routes that were
        public in the legacy monolith are successfully accessible without any
        credentials (returning `200 OK` and expected schema payload).
    *   *Authorized Access*: Ensure secured routes process requests successfully
        (returning `200 OK` and correct schema) only when a valid
        cryptographically signed token (or mock token if mock mode is flagged)
        is supplied.
    *   *Schema Alignment*: Response JSON structures match original payloads and
        database mappings are correctly persisted.

## 3. Generate Migration Audit Report (`walkthrough.md`)

Create a UI Artifact named `walkthrough.md` using the `write_to_file` tool. You
MUST provide `ArtifactMetadata` with `RequestFeedback: true` and `UserFacing:
true`. Include the following mandatory sections:

1.  **Structural Comparison**: Total classes migrated, excluded utility
    libraries, and service boundary summaries.
2.  **Refactoring Decisions & Deviations**: List any architectural trade-offs,
    deviations from the original approved `wls-migration-plan.md` plan, or
    custom modifications (like custom bean configurations or package shifts)
    made during refactoring, along with their justifications.
3.  **Compilation & Test Suite Verification**: Document the build outcomes
    (compilation logs summary) and test suite results (e.g., number of
    unit/integration tests passed, failed, or skipped) to verify functional
    equivalence and compilation success.
4.  **Endpoint Matrix**: Before/After trace paths, specifying whether each
    endpoint is secured or public.
5.  **Security Warnings & Flags**: If any temporary mock security configurations
    or dev secrets are active (e.g., mock tokens, `NoOpPasswordEncoder`, default
    local passwords), list them here as critical security findings to be
    addressed prior to production release.
6.  **Validation Log**: Output snippets of test executions (or local compile
    success reports) demonstrating that all migrated services are functioning
    correctly.
