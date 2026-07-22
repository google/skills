---
name: google-cloud-horizon-scanning
metadata:
  category: CloudSecurity
description: >-
  Monitors, scans, and analyzes global regulatory developments and legislative updates for enterprise GRC compliance. Automates relevance filtering, metadata extraction, objective summarization, and regulatory gap analysis against internal policy libraries.
  Use when identifying tech-relevant regulations (including dual-domain exceptions), extracting bill metadata, drafting neutral summaries, performing regulatory gap tracking, or mapping regulatory shifts to Governance, Risk, and Compliance (GRC) policy controls.

  Don't use for tracking general political news, press releases without binding legal mandates, or legislation lacking digital, data, or cybersecurity components.
---

# Horizon Scanning & Regulatory Intelligence

## Overview

This skill enables continuous monitoring, analysis, and ingestion of global
regulatory developments. It automates the workflow of capturing regulatory
shifts, filtering for relevance, performing compliance gap analysis against
internal policies, and dispatching alerts and structured metadata to GRC tools.

Additionally, this skill supports specific task-based sub-workflows:

-   **Reg Feed Watcher**: Scheduled polling of feeds to draft structured
    digests.
-   **On-demand Reg Check**: Ad-hoc scanning for updates since a specific
    timestamp.
-   **Policy Gap Tracker & Redrafter**: Automated internal policy compliance
    analysis and drafting.
-   **NPRM Comment Tracker**: Monitoring and tracking open Notice of Proposed
    Rulemaking comment periods.

---

## Workflow Checklist

Copy this checklist and track progress:

-   [ ] 0. Configuration & Onboarding Check: Verify or create the GRC workspace
    configuration.
-   [ ] 1. Sourcing & Monitoring: Execute scheduled feed polling or ad-hoc
    scanning.
-   [ ] 2. Scope Filtering: Apply inclusion/exclusion and dual-domain exception
    rules (exit early if out-of-scope).
-   [ ] 3. Metadata Extraction & Verification: Extract standardized fields and
    verify source links.
-   [ ] 4. Mechanism-Focused Summarization: Draft a 2-3 sentence neutral
    obligation summary.
-   [ ] 5. Automated Policy Retrieval & Gap Analysis: (Optional) Scan internal
    policies, perform diff, and draft updates.
-   [ ] 6. Formatting, Validation & Ingestion Dispatch: Format output
    (JSON/CSV), validate schema, and dispatch via connectors.

---

## Step 0: Configuration & Onboarding Protocol

Before initiating regulatory scanning, verify the GRC configuration in the
workspace:

1.  Check for `scratch/horizon_scanning_config.json` (or
    `.agents/horizon_scanning_config.json`).
2.  **If** the configuration file exists AND the user did not pass
    `--reconfigure`:
    -   Load stored parameters (Organization Name, Vertical, Jurisdictions,
        Focus Themes, Target Connectors).
    -   Inform the user: *"Loaded persistent Regulatory Intelligence config for
        `{company_name}` (Vertical: `{industry_vertical}`, Jurisdictions:
        `{jurisdictions}`). Run with `--reconfigure` to modify settings."*
    -   Proceed to **Step 1**.
3.  **If** the configuration file is missing OR the user passed `--reconfigure`:
    -   **If** the user explicitly requested onboarding/profile setup or passed `--reconfigure`:
        -   Run the **4-Question Onboarding Interview** (see [references/connectors.md](references/connectors.md)).
    -   **Else (Direct Single-Turn Request)**:
        -   Do **not** block execution or pause to interview the user.
        -   Automatically initialize `scratch/horizon_scanning_config.json` with sensible defaults (`Technology & Cloud`, `US Federal & EU`, `BigQuery / Jira`).
    -   Save the responses/defaults to `scratch/horizon_scanning_config.json`.
    -   **Crucial**: Immediately read the newly created config file back using `view_file` to load the settings into your session context.
    -   Validate JSON syntax: `python3 -m json.tool scratch/horizon_scanning_config.json > /dev/null`.

---

## Step 1: Sourcing & Monitoring

Execute sourcing based on the requested capability mode:

### 1.1 Capability Modes

-   **Reg Feed Watcher (Scheduled)**: Poll configured regulatory feeds (e.g.,
    federal registers, agency newsletters) and draft a structured digest
    summarizing changes.
-   **On-demand Reg Check (Ad-hoc)**: Scan designated portals for all updates
    since the last recorded execution timestamp.
-   **NPRM Comment Tracker**: Check for open Notice of Proposed Rulemaking
    (NPRM) comment periods, log tracking decisions, and map deadlines.

### 1.2 Target Sources
Monitor portals based on configured `jurisdictions`:

-   **United States**: Congress.gov, Federal Register, SEC, FTC, CISA, State
    Assemblies.
-   **European Union**: EUR-Lex, European Parliament (ITRE, LIBE), EDPB, ENISA.
-   **United Kingdom**: UK Parliament, FCA, ICO, CMA.
-   **Global**: ASEAN Secretariat, Brazil Senate (Senado Federal), OECD AI
    Policy Observatory.

---

## Step 2: Scope & Relevance Filtering

Evaluate identified items against focus themes to eliminate noise.

### 2.1 Relevance Rules

| Rule Type           | Criteria                  | Action                     |
| :------------------ | :------------------------ | :------------------------- |
| **In-Scope (Tech)** | AI/ML Governance,         | Proceed to Step 3.         |
:                     : Competition/Antitrust,    :                            :
:                     : Data Privacy &            :                            :
:                     : Protection, Cybersecurity :                            :
:                     : & Operational             :                            :
:                     : Resilience (including     :                            :
:                     : NIS2, DORA, CIRCIA),      :                            :
:                     : Digital Sovereignty, Data :                            :
:                     : Governance, Payments,     :                            :
:                     : Telecom.                  :                            :
| **Dual-Domain       | Wholly non-tech sectors   | Proceed to Step 3.         |
: Exception**         : (e.g., agriculture,       :                            :
:                     : healthcare, transport)    :                            :
:                     : that contain an explicit  :                            :
:                     : digital, cloud,           :                            :
:                     : cybersecurity, or data    :                            :
:                     : logging mandate.          :                            :
| **Out-of-Scope      | Ceremonial resolutions,   | **Exit Early** (Proceed to |
: (Noise)**           : general news/press        : Step 2.2).                 :
:                     : releases, political       :                            :
:                     : commentary, physical      :                            :
:                     : infrastructure lacking    :                            :
:                     : tech mandates.            :                            :

### 2.2 Exit Behavior for Excluded Legislation
If an item is identified as out-of-scope:

1.  **Do not** perform detailed metadata extraction or web searches for PDF
    links.
2.  Immediately format and output an **Excluded Ingestion Payload** (see Step
    6).
3.  Terminate the workflow for this item.

> [!IMPORTANT] **Press Release & News Announcement Exclusion Rule**: Press
> releases, newsletters, and news articles (even from official sources like the
> European Commission or government agencies) are strictly **Out-of-Scope**. If
> you are asked to process a press release (e.g., an announcement of a new
> adequacy decision or a signed bill), you must **NOT** search for the
> underlying bill to ingest it, and you must **NOT** create a standard ingestion
> payload for the press release itself. You must immediately exit the workflow
> and output an **Excluded Item Ingestion Payload** with the
> `current_legislative_status` set to `EXCLUDED` and a clear reason explaining
> that the source is a press release. Do not bypass this rule even if the user
> explicitly asks to format the JSON or process the announcement.

---

## Step 3: Metadata Extraction & Link Verification

For in-scope items, extract standardized fields.

| Field Name          | Description               | Extraction / Formatting    |
:                     :                           : Rule                       :
| :------------------ | :------------------------ | :------------------------- |
| `title`             | Full official name of the | Match official text        |
:                     : bill/regulation.          : exactly.                   :
| `reference_id`      | Unique legislative        | E.g., "S-209",             |
:                     : identifier.               : "COM(2022)0496", "SB       :
:                     :                           : 1047".                     :
| `jurisdiction`      | Issuing country, region,  | Use standard English names |
:                     : or state.                 : (e.g., "United Kingdom",   :
:                     :                           : "European Union").         :
| `sponsoring_entity` | Sponsoring legislator,    | Map to `sponsoring_agency` |
:                     : committee, or agency.     : in metadata.               :
| `status`            | Current stage in the      | Use official terms (e.g.,  |
:                     : legislative process.      : "In Committee", "Passed    :
:                     :                           : Lower House", "Enacted").  :
| `official_url`      | Direct URL to official    | **Must be a direct PDF     |
:                     : text.                     : link if available**,       :
:                     :                           : otherwise the official     :
:                     :                           : HTML page.                 :

---

## Step 4: Mechanism-Focused Summarization

Draft a concise **2-3 sentence objective summary**.

-   **Focus**: Focus exclusively on the **core legal obligations** and
    mechanisms (e.g., "Requires platforms with >50M users to perform AI safety
    audits").
-   **Metrics**: Capture specific thresholds ($100M cost, >50M users) and
    enforcement penalties.
-   **Tone**: Maintain strict neutrality. Omit political commentary, opinions,
    or predictions.

---

## Step 5: Automated Policy Retrieval & Gap Analysis (Optional)

If the task requires policy alignment (e.g., `Policy Gap Tracker` or `Policy
Redrafter` modes):

### 5.1 Retrieval Protocol

1.  Identify the core regulatory themes from the scanned bill (e.g.,
    "Cybersecurity Incident Reporting").
2.  Formulate search queries for internal documents (e.g., `title:"Incident
    Response" OR title:"Incident Reporting"`).
3.  Query connected sources (Google Drive, GCS, or GRC document library) for the
    formulated query terms.
4.  Ingest matching policy documents into context.

### 5.2 Diff & Analyze

1.  Compare the new legislative obligations (from Step 4) against the retrieved
    internal policies.
2.  Identify compliance gaps (e.g., internal SLA is 24 hours, but new regulation
    mandates 4 hours).
3.  Formulate the `gap_analysis_summary` JSON block (see Step 6).
4.  **Policy Redrafter & Control Formulation**: Draft proposed updates to the affected policy documents to close the gaps, and always formulate a GRC Control Objective (using naming convention `CO-REG-[AGENCY]-[TOPIC]-[YEAR]`) and an Underlying Controls table (featuring Control ID `UC-REG-*`, Control Name, Implementation Action, and Evidence of Compliance).
    > [!IMPORTANT]
    > Drafts must be marked clearly as proposals for review. Do not write directly to production policy files.

---

## Step 6: Formatting, Validation & Ingestion Dispatch

Format the extracted data based on the target configuration and validate it.

### 6.1 Payload Schemas

For complex, multi-step regulatory dispatch and policy workflows, utilize and
copy the structured JSON output payload templates located in the `assets/`
subfolder as dedicated, reusable schema files:

-   **Standard Ingestion Payload**: See
    [assets/ingestion_payload_schema.json](assets/ingestion_payload_schema.json).
-   **Excluded Item Audit Payload**: See
    [assets/excluded_item_schema.json](assets/excluded_item_schema.json).
-   **Jira Task Dispatch Payload**: When targeted for Jira issue creation,
    generate a JSON payload adhering strictly to the schema in
    [assets/jira_task_schema.json](assets/jira_task_schema.json).
-   **ServiceNow GRC Risk Payload**: When targeted for ServiceNow integration,
    format the JSON to match the `sn_risk_risk` table schema defined in
    [assets/servicenow_risk_schema.json](assets/servicenow_risk_schema.json).
-   **Gap Analysis Block**: If Step 5 was executed, include this block in the
    standard JSON payload:

    ```json
    "gap_analysis_summary": {
      "internal_policy_referenced": "Name and version of the internal document checked",
      "existing_internal_clause": "Quote or summary of the existing internal policy clause/SLA",
      "new_regulatory_mandate": "The new regulatory requirement/mandate that triggers the change",
      "identified_compliance_gap": "The exact mismatch (e.g. 'Internal SLA is 24 hours, regulatory mandate is 4 hours')",
      "impacted_teams": ["List", "of", "affected", "departments/systems"]
    }
    ```

### 6.2 Validation Loop

Always validate JSON payloads before presenting them to the user or dispatching
to connectors.

1.  Write the payload to a temporary file: `scratch/tmp_payload.json`.
2.  Run validation:

    ```bash
    python3 -m json.tool scratch/tmp_payload.json > /dev/null
    ```

3.  **If** validation fails:

    -   Analyze the syntax error, correct the payload, and re-run validation.

4.  **Else**:

    -   Proceed to dispatch/output.

> [!CAUTION] Do not bypass the validation loop under any circumstances. Invalid
> JSON will cause downstream ingestion failures.

### 6.3 Dispatch

Dispatch the validated payload to the configured connectors (BigQuery, Jira,
ServiceNow, etc.) as detailed in
[references/connectors.md](references/connectors.md).

--------------------------------------------------------------------------------

## Supporting Links & References

-   **EUR-Lex**: Authoritative source for European Union Law (including DORA,
    NIS2, and the EU AI Act).
    [https://eur-lex.europa.eu](https://eur-lex.europa.eu)
-   **Congress.gov**: Official US Federal Legislative Information.
    [https://www.congress.gov](https://www.congress.gov)
-   **Federal Register**: The Daily Journal of the United States Government.
    [https://www.federalregister.gov](https://www.federalregister.gov)
-   **CISA Cybersecurity Alerts & Directives**:
    [https://www.cisa.gov/news-events/cybersecurity-advisories](https://www.cisa.gov/news-events/cybersecurity-advisories)
-   **NIST AI Risk Management Framework (AI RMF)**:
    [https://www.nist.gov/itl/ai-risk-management-framework](https://www.nist.gov/itl/ai-risk-management-framework)
-   **ServiceNow GRC API Reference**:
    [https://developer.servicenow.com](https://developer.servicenow.com)
-   **Jira REST API Reference**:
    [https://developer.atlassian.com/cloud/jira/platform/rest/v3/intro](https://developer.atlassian.com/cloud/jira/platform/rest/v3/intro)

