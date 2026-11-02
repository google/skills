---
name: cloud-armor-crs-rule-upgrader
metadata:
  category: Security
  version: "1.0.1"
description: >-
  Upgrades Google Cloud Armor security policies from OWASP CRS 3.0 and 3.3 to OWASP CRS 4.22. Preserves signature opt-in and opt-out lists, translates evaluatePreconfiguredExpr to native evaluatePreconfiguredWaf dictionary parameters, remaps signature IDs to v042200, drops retired signature IDs, and updates structured preconfiguredWafConfig fine-tuning exclusions. Evaluates operational risk (High Breaking Change, Medium Attention Required, Low Clean Upgrade) including Method Enforcement breaking changes (PUT/PATCH/DELETE blocking) and sensitivity coverage expansions. Supports both in-place rule upgrades and smooth preview mode deployments with priority spacing and a 200-rule quota guardrail. Use when a user or agent needs to audit, upgrade, or transition Cloud Armor WAF rules to CRS 4.22. Don't use for non-WAF Cloud Armor rules (IP rate-limiting, geo-blocking, reCAPTCHA) or AWS/Azure WAF migrations.
---

# Cloud Armor OWASP Rule Upgrader (CRS 3.0/3.3 -> 4.22)

<!-- disableFinding(LINE_OVER_80) -->

This skill guides Network Security Agents and Google Cloud practitioners through
auditing, assessing, and upgrading Google Cloud Armor security policies from
legacy OWASP Core Rule Set (CRS) 3.0 or 3.3 to OWASP CRS 4.22.

## Usage Attribution

**MUST READ**: Before executing any `gcloud`, REST API, or MCP command, you
MUST read and follow the instructions in
[Usage Attribution](references/attribution.md).

--------------------------------------------------------------------------------

## Prerequisites and Environment Setup

Before auditing or modifying Google Cloud Armor security policies, ensure the
following prerequisites are met:

1.  **Google Cloud SDK**: Install or update the
    [Google Cloud CLI (`gcloud`)](https://docs.cloud.google.com/sdk/docs/install-sdk).
2.  **Project Selection and Active Billing**: Select your target Google Cloud
    project and verify that an active billing account is attached:

    ```bash
    gcloud config set project PROJECT_ID
    gcloud billing projects describe PROJECT_ID --format="value(billingEnabled)"
    ```

3.  **API Enablement**: Enable the Compute Engine API (for Cloud Armor security
    policies) and Cloud Logging API (for preview mode telemetry):

    ```bash
    gcloud services enable compute.googleapis.com logging.googleapis.com
    ```

4.  **Authentication**:
    -   **Interactive CLI**: `gcloud auth login`
    -   **Application Default Credentials (ADC)**: `gcloud auth
        application-default login`
    -   **Service Accounts**: Set
        `GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"`.
5.  **Required IAM Roles**:
    -   `roles/compute.securityAdmin`: Required to create, update, delete, or
        import Cloud Armor security policies and rules (use
        `roles/compute.securityViewer` for read-only policy audits).
    -   `roles/logging.viewer`: Required to inspect HTTP load balancer preview
        telemetry in Cloud Logging.
6.  **Scope and Regional Availability**:
    -   Cloud Armor security policies can be **Global** (default for global
        external Application Load Balancers) or **Regional** (for regional
        external Application Load Balancers, for example, `--region=us-central1`;
        set a default region via `gcloud config set compute/region us-central1`).
        See [Google Cloud Locations](https://cloud.google.com/about/locations)
        for regional availability.
7.  **Pricing and Resource Cleanup**:
    -   Cloud Armor incurs charges per security policy, per rule, and per
        million requests depending on your tier (Standard vs. Enterprise); check
        [Google Cloud Armor Pricing](https://cloud.google.com/armor/pricing)
        for current rates.
    -   **Teardown / Cleanup**: Always delete temporary `--preview` rules
        (`gcloud compute security-policies rules delete PREVIEW_PRIORITY
        --security-policy="POLICY_NAME"`) or standalone test policies (`gcloud
        compute security-policies delete TEST_POLICY_NAME`) after cutover to
        avoid leaving orphan rules that consume policy quota or incur recurring
        rule charges.

--------------------------------------------------------------------------------

## Quick Start and CLI Helper

For automated, deterministic parsing, signature remapping, and preview-mode
priority allocation, invoke the bundled standalone Python CLI:

```bash
# In-Place Upgrade (Report Summary)
python3 scripts/upgrade_policy.py /path/to/policy.json --mode=in-place --format=report

# In-Place Upgrade (Output gcloud commands)
python3 scripts/upgrade_policy.py /path/to/policy.json --mode=in-place --format=gcloud

# Preview Mode Upgrade (Generates preview rules at priority - 5)
python3 scripts/upgrade_policy.py /path/to/policy.json --mode=preview --format=gcloud

# Direct stdin piping from gcloud describe
gcloud compute security-policies describe POLICY_NAME --format=json | \
  python3 scripts/upgrade_policy.py - --mode=preview --format=json
```

See [gcloud_recipes.md](references/gcloud_recipes.md) for full command
workflows.

## Core Upgrade Workflow for Network Security Agent

> [!IMPORTANT] **Mandatory Agent Response Behaviors**: 1. **Explain Both Upgrade
> Modes**: Whenever discussing an upgrade (even if the user asks specifically
> about Preview Mode or In-Place), ALWAYS explain BOTH **In-Place Upgrade**
> (direct in-situ rule replacement, immediate enforcement, zero extra quota) and
> **Preview Mode** (preview rules deployed at lower numeric priority numbers
> with `preview = true`, zero risk of blocking traffic, allows telemetry
> inspection in Cloud Logging before cutover). 2. **Handling Policy Audit
> Inquiries**: When asked to audit or inspect a policy (such as
> `'ecommerce-waf'`), if policy JSON is not provided or `gcloud describe` cannot
> reach Google Cloud resources, immediately provide the `gcloud compute
> security-policies describe POLICY_NAME --format=json` command and guide the
> user through the audit checks: - Check for legacy OWASP 3.0 / 3.3 rulesets
> (`sqli-stable`, `xss-stable`, `rce-stable`, `methodenforcement-stable`, or
> `evaluatePreconfiguredExpr`). - Report in-scope WAF rules versus pass-through
> custom rules (such as IP allowlists `SRC_IPS_V1`, rate limiting, or default
> rules `priority: 2147483647`). - Highlight signature count expansions under
> CRS 4.22 (for example, RCE expanding from 11/15 to 44 signatures; SQLi
> expanding to 60 signatures).

When interacting with a customer to upgrade a Cloud Armor security policy,
execute this 5-step workflow:

1.  **Discover and Fetch**: Identify the target security policy and fetch its
    JSON definition.
2.  **Audit and Classify Risk**: Inspect rules, signature count expansions, and
    operational risk levels.
3.  **Confirm Mode and Method Risk**: Align with the customer on Preview Mode
    versus In-Place Upgrade, method enforcement risk, and quota or priority
    constraints.
4.  **Transform Rules**: Translate ruleset names, CEL expressions, signature
    IDs, and `preconfiguredWafConfig` exclusions to CRS 4.22.
5.  **Execute and Verify**: Apply the upgrade via `gcloud` and verify telemetry
    in Cloud Logging.

### Step 1: Policy Discovery and Ingestion

1.  Identify the target security policy name and Google Cloud project.
2.  Fetch the current policy definition via `gcloud`:

    ```bash
    gcloud compute security-policies describe POLICY_NAME --project=PROJECT_ID --format="json"
    ```

    *If policy JSON is not provided or executing in conversational mode, provide
    the `gcloud describe` command and outline the audit criteria below.*

3.  Inspect the `rules` list:

    -   Identify in-scope WAF rules: calls to `evaluatePreconfiguredWaf` or
        `evaluatePreconfiguredExpr` using legacy 3.0 / 3.3 rulesets
        (`sqli-stable`, `xss-stable`, `rce-stable`, `methodenforcement-stable`,
        etc.).
    -   Identify out-of-scope rules: pass-through custom rules (such as pure IP
        allowlists `SRC_IPS_V1`, rate limiting, header matches without WAF
        calls, or default rules `priority: 2147483647`). Pass these through
        unchanged.
    -   Highlight signature coverage expansions (for example, RCE expanding from
        11/15 to 44 signatures; SQLi expanding to 60 signatures in CRS 4.22).

### Step 2: Audit and Risk Classification

Evaluate each in-scope rule against standard operational risk categories:

<!-- mdformat off -->

| Risk Level | Impact Category | Criteria and Recommended Action |
| :--- | :--- | :--- |
| 🔴 **High Risk** | **Breaking Change** | Immediate risk of blocking legitimate production traffic upon cutover. Example: `methodenforcement-v422-stable` only permits `GET`, `HEAD`, `POST`, `OPTIONS`, and **blocks `PUT`, `PATCH`, `DELETE`** requests. Requires customer confirmation and API path/signature exemptions. |
| 🟡 **Medium Risk** | **Attention Required** | Behavioral shifts that should be validated in Preview Mode before enforcement:<br>• **Coverage Expansion**: Sensitivity level 4 activates significantly more signatures (for example, RCE expands from 11/15 to 44 signatures; SQLi expands to 60 signatures).<br>• **Deprecated Exemption Lost**: Legacy rule opted out of any of the 15 retired CRS 3.0/3.3 IDs (`981172`, `981173`, `980130`, `949110`; SQLi: `942110`; RCE: `932100`, `932105`, `932106`, `932110`, `932115`, `932150`; Scanner Detection: `913101`, `913102`, `913110`, `913120`), which are omitted in 4.22.<br>• **Custom Filter Continuity**: Preserved custom header/cookie/query/IP conditions combined with WAF calls. |
| 🟢 **Low Risk** | **Clean Upgrade** | Direct 1:1 ruleset translation with preserved active opt-outs and no expected behavioral divergence (for example, standard SQLi or XSS rules). |
| ⚪ **No Action** | **Pass-Through** | Non-OWASP rules (pure IP allowlist/denylist, rate limiting, default rule). Carried over unchanged. |

<!-- mdformat on -->

### Step 3: Upgrade Mode Selection and User Alignment

Engage the customer with findings before applying changes:

1.  **Report Findings**: State how many WAF rules will be upgraded, signature
    coverage expansions, and any deprecated signatures being retired.
2.  **Method Enforcement Warning**: If `methodenforcement` is present, warn: >
    *"Notice: Method Enforcement in CRS 4.22 permits only GET, HEAD, POST, and
    OPTIONS. If your application handles REST API updates (PUT, PATCH, DELETE),
    these methods will be blocked with HTTP 403. Would you like to add an
    exemption for API paths or opt out of rule id911100?"*
3.  **Explain Differences Between Modes**:
    -   **Preview Mode (Recommended)**: Keeps existing legacy rules actively
        enforcing while deploying corresponding upgraded CRS 4.22 preview rules
        with `preview = true` at a lower numeric priority number (higher
        evaluation priority, for example, `PRIORITY - 5`). Traffic is evaluated
        first by preview rules and logged to Cloud Logging without blocking,
        ensuring zero risk of downtime or false positives prior to cutover.
        Requires sufficient quota under the 200-rule limit.
    -   **In-Place Upgrade**: Directly modifies the CEL expressions and
        `preconfiguredWafConfig` on existing rule priority numbers in-situ.
        Immediate enforcement with zero additional rule overhead, but carries
        cutover risk if new signatures or method enforcement block valid
        traffic.
4.  **Quota Guardrail (200 Rules)**:
    -   Calculate projected rule count: `current_total_rules +
        in_scope_waf_rules`.
    -   If projected count > 200, alert the customer: > *"Cloud Armor enforces a
        maximum limit of 200 rules per security policy. Deploying in Preview
        Mode would require PROJECTED_COUNT rules. The upgrade cannot proceed
        in Preview Mode. We must either perform an In-Place Upgrade or
        consolidate rules."*
5.  **Priority Spacing Guardrail (Preview Mode)**:
    -   If an in-scope WAF rule at `PRIORITY` immediately follows another rule
        at `PREV_PRIORITY` with no free integer priority slot between them
        (for example, `999` and `1000`, or a WAF rule at priority `0`), alert
        the customer: > *"Rule PRIORITY cannot be deployed in Preview Mode
        because the preceding rule at priority PREV_PRIORITY leaves no open
        priority number between PREV_PRIORITY and PRIORITY (and placing the
        preview rule above PREV_PRIORITY would change evaluation order). To use
        Preview Mode, please readjust your rule priorities to leave at least one
        open priority slot before PRIORITY, or choose an In-Place Upgrade."*
    -   **Do NOT automatically re-number existing customer rules**: Because rule
        priorities act as primary identifiers in Cloud Armor and are often tied
        to Terraform/IaC resources and SIEM alerting filters, never silently
        shift existing customer rule priorities to make room. If the customer
        explicitly asks you to readjust their rule priorities for them, first
        warn them about potential Terraform/IaC state drift and confirm the
        exact new priority numbers before executing any priority changes.

### Step 4: Rule Transformation Logic

#### A. Ruleset Name Translation

Translate legacy ruleset names according to the mapping table in
[ruleset_mappings.md](references/ruleset_mappings.md):

-   Stable: `sqli-stable` to `sqli-v422-stable`, `rce-stable` to
    `rce-v422-stable`
-   Canary: `sqli-canary` to `sqli-v422-canary`
-   3.3 Stable: `sqli-v33-stable` to `sqli-v422-stable`, `nodejs-v33-stable`
    to `generic-v422-stable`

#### B. CEL Opt-Out and Opt-In Translation

-   Legacy `evaluatePreconfiguredExpr(ruleset, ['id1', 'id2'])` is strictly an
    **opt-out (disabled)** list.
-   Convert to native 4.22 syntax:

    ```cel
    evaluatePreconfiguredWaf('sqli-v422-stable', {'opt_out_rule_ids': ['owasp-crs-v042200-id942120-sqli']})
    ```
-   Remap signature IDs: `owasp-crs-v030001-idSIGNATURE_ID-GROUP` to
    `owasp-crs-v042200-idSIGNATURE_ID-GROUP`. *(Exception: Standalone CVE
    signatures such as `cve-canary` signatures `owasp-crs-v030001-id*-cve` and
    `google-mrs-*` retain their original IDs and must not be remapped to
    `v042200` or dropped).*
-   Drop all 15 deprecated CRS 3.0/3.3 signature numbers (`981172`, `981173`,
    `980130`, `949110`; SQLi: `942110`; RCE: `932100`, `932105`, `932106`,
    `932110`, `932115`, `932150`; Scanner Detection: `913101`, `913102`,
    `913110`, `913120`).

#### C. Fine-Tuning (`preconfiguredWafConfig`)

For rules with structured `preconfiguredWafConfig.exclusions[]`:

-   Update `targetRuleSet` to the CRS 4.22 equivalent.
-   Remap `targetRuleIds` to `v042200` and drop deprecated IDs. **Warning**: If
    an exclusion's `targetRuleIds` list becomes empty (`[]`) after dropping
    retired IDs, remove the entire exclusion entry rather than leaving
    `targetRuleIds: []` (otherwise an empty `targetRuleIds` list exempts the
    entire ruleset).
-   Carry over all field exclusions (`requestHeadersToExclude`,
    `requestCookiesToExclude`, `requestQueryParamsToExclude`,
    `requestUrisToExclude`, `requestBodiesToExclude`) and match operators
    without modification.
-   Details in [fine_tuning_and_cel.md](references/fine_tuning_and_cel.md).

### Step 5: Execution Delivery and Verification

#### Delivering In-Place Upgrade

Execute `gcloud compute security-policies rules update`:

```bash
gcloud compute security-policies rules update PRIORITY \
  --security-policy="POLICY_NAME" \
  --project=PROJECT_ID \
  --expression="UPGRADED_EXPRESSION"
```

#### Delivering Preview Mode Upgrade

Deploy preview rules at a numeric priority strictly between the immediately
preceding rule and `ENFORCED_PRIORITY` (`PREV_PRIORITY < PREVIEW_PRIORITY <
ENFORCED_PRIORITY`) using `rules create`:

```bash
gcloud compute security-policies rules create PREVIEW_PRIORITY \
  --security-policy="POLICY_NAME" \
  --project=PROJECT_ID \
  --expression="UPGRADED_EXPRESSION" \
  --action="ACTION" \
  --preview \
  --description="PREVIEW: Upgraded CRS 4.22 Rule for Priority ENFORCED_PRIORITY"
```

#### Telemetry Verification in Cloud Logging

Instruct the customer to inspect preview logs before cutover:

```bash
gcloud logging read '
  resource.type="http_load_balancer" AND
  jsonPayload.enforcedSecurityPolicy.name="POLICY_NAME" AND
  jsonPayload.previewSecurityPolicy.matchedRulePriority:*
' --project=PROJECT_ID --limit=20
```

--------------------------------------------------------------------------------

## Critical Gotchas and Domain Rules

1.  **`evaluatePreconfiguredExpr` is NEVER Opt-In**: The array in legacy
    `evaluatePreconfiguredExpr` was strictly an exclusion (opt-out) list.
    Treating it as opt-in would inadvertently disable all other signatures in
    that ruleset!
2.  **Never Re-introduce Deprecated Signatures**: All 15 retired CRS 3.0/3.3
    signature numbers (`981172`, `981173`, `980130`, `949110`; SQLi: `942110`;
    RCE: `932100`, `932105`, `932106`, `932110`, `932115`, `932150`; Scanner
    Detection: `913101`, `913102`, `913110`, `913120`) were removed in CRS 4.22.
    Keeping them in `opt_out_rule_ids` or `targetRuleIds` causes Cloud Armor API
    schema rejections.
3.  **Method Enforcement Defaults**: CRS 4.22 Method Enforcement blocks `PUT`,
    `PATCH`, and `DELETE`. Never perform a silent in-place upgrade of method
    enforcement without user confirmation.
4.  **Preview Rule Priorities and Cutover Safety**: Cloud Armor evaluates rules
    in ascending priority order (`0` to `2147483647`). A preview rule must
    evaluate *before* the enforcing rule it previews, but *after* any preceding
    rule (`PREV_PRIORITY < PREVIEW_PRIORITY < ENFORCED_PRIORITY`) so it never
    crosses intervening `allow` or custom rules. During cutover to full
    enforcement, update the original `ENFORCED_PRIORITY` rule in-place to CRS
    4.22 and delete `PREVIEW_PRIORITY` rather than promoting `PREVIEW_PRIORITY`
    in place.
5.  **Atomic Import for Structured Exclusions**: When a policy contains complex
    `preconfiguredWafConfig` blocks, prefer exporting the policy JSON,
    transforming it, and applying it via `gcloud compute security-policies
    import` to ensure atomic updates.
6.  **Preserve Standalone CVE Signatures (`cve-canary`)**: `cve-canary` is an
    out-of-band rule for specific vulnerabilities (for example, Log4j
    CVE-2021-44228 / CVE-2021-45046, React RCE CVE-2025-55182). Its signature
    IDs (`owasp-crs-v030001-id044228-cve`, `id144228-cve`, `id244228-cve`,
    `id344228-cve`) are valid and retain the `v030001` prefix. Only upgrade the
    syntax to `evaluatePreconfiguredWaf('cve-canary', ...)`; never rewrite them
    to `v042200` or drop them as deprecated.

--------------------------------------------------------------------------------

## References and Resources

-   [ruleset_mappings.md](references/ruleset_mappings.md): Full CRS 3.0 / 3.3 to
    4.22 ruleset mapping, sensitivity levels, and signature counts.
-   [fine_tuning_and_cel.md](references/fine_tuning_and_cel.md): CEL syntax
    options, structured `preconfiguredWafConfig` exclusions, and method
    enforcement mitigations.
-   [gcloud_recipes.md](references/gcloud_recipes.md): Copy-pasteable `gcloud`
    recipes for audit, preview mode, and Cloud Logging queries.
-   [upgrade_policy.py](scripts/upgrade_policy.py): Deterministic CLI helper
    script.
-   [contributing.md](references/contributing.md): Domain and code invariants
    for maintaining this skill.
