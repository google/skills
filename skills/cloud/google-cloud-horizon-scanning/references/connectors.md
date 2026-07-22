# Connectors & Workflows Reference

This reference document contains the detailed schemas, onboarding questions, and
integration details for the Horizon Scanning skill.

## Table of Contents

-   [1. Onboarding Interview Details (L15-L54)](#L15-L54)
-   [2. Ingestion Payload Schemas (L57-L70)](#L57-L70)
-   [3. Integration Connectors Details (L74-L94)](#L74-L94)
-   [4. Enterprise Control Mapping & GRC Policy Drafting (L97-L111)](#L97-L111)


--------------------------------------------------------------------------------

## 1. Onboarding Interview Details

When configuration is missing or `--reconfigure` is passed, prompt the user with
these questions:

### Question 1: Enterprise Organization & Vertical Context

> *"What is your enterprise organization name, industry vertical, and core
> business operations?"* - **Industry Verticals**: `Legal / Law Firm`,
> `Financial Services & Banking`, `Healthcare & Life Sciences`, `Technology &
> Cloud`, `Retail & E-Commerce`, `Energy & Utilities`, `Public Sector /
> Government`.

### Question 2: Target Jurisdictions & Regional Scope

> *"Which global jurisdictions or regulatory bodies need to be monitored?"* -
> **Regions**: `US Federal & State`, `European Union (EU/EEA)`, `United
> Kingdom`, `LATAM (Brazil, Mexico)`, `APAC / ASEAN`, `Global / Multilateral
> (OECD, G7)`.

### Question 3: Regulatory Focus Themes & Risk Appetite

> *"What specific regulatory topics or compliance frameworks should be flagged
> vs. ignored?"* - **Focus Themes**: AI/ML Governance (EU AI Act, NIST), Data
> Privacy & Protection (GDPR, CCPA), Cybersecurity & Operational Resilience
> (NIS2, DORA, CISA), Children's Online Safety, Competition / Digital Markets,
> Financial Regulation, ESG & Energy Transparency. - **Exclusion Rules**:
> Ceremonial resolutions, general political news, press releases, non-tech files
> lacking digital/data components.

### Question 4: Enterprise Connectors & Output Targets

> *"Where should extracted regulatory intelligence and alerts be delivered?"* -
> **Options**: - `1. BigQuery / Database Ingestion`: SQL / JSON insertion schema
> for enterprise data warehouse. - `2. Jira / ServiceNow Ticket Dispatch`:
> Automated issue creation for legal/compliance review. - `3. Google Workspace /
> Drive Sync`: Report generation in Google Docs / Drive repository. - `4.
> Webhook / Messaging Alerts`: Event payload for Slack, Microsoft Teams, or
> custom REST Webhook.

--------------------------------------------------------------------------------

## 2. Ingestion Payload Schemas

For complex, multi-step regulatory dispatch and policy workflows, utilize and
copy the structured JSON output payload templates located in the `assets/`
subfolder as dedicated, reusable schema files:

-   **Standard Ingestion Payload**: See
    [assets/ingestion_payload_schema.json](../assets/ingestion_payload_schema.json).
-   **Excluded Item Audit Payload**: See
    [assets/excluded_item_schema.json](../assets/excluded_item_schema.json).
-   **Jira Task Dispatch Payload**: See
    [assets/jira_task_schema.json](../assets/jira_task_schema.json).
-   **ServiceNow GRC Risk Payload**: See
    [assets/servicenow_risk_schema.json](../assets/servicenow_risk_schema.json).

--------------------------------------------------------------------------------

## 3. Integration Connectors Details

Enterprise customers can integrate this skill with the following targets:

| Connector Category  | Target Enterprise         | Purpose                    |
:                     : Integration               :                            :
| :------------------ | :------------------------ | :------------------------- |
| **Data Warehouses** | Google Cloud BigQuery,    | Store & query historical   |
:                     : Snowflake, PostgreSQL     : regulatory ingestion       :
:                     :                           : datasets.                  :
| **Issue Trackers**  | Jira Software, ServiceNow | Auto-create regulatory     |
:                     : GRC, GitHub Issues        : risk review tickets &      :
:                     :                           : legal action items.        :
| **Cloud Storage**   | Google Cloud Storage      | Store raw PDF bill texts & |
:                     : (GCS), Google Drive, Box  : generated legal summary    :
:                     :                           : reports.                   :
| **Event Webhooks**  | Slack, Microsoft Teams,   | Trigger real-time alert    |
:                     : REST Webhooks             : notifications for          :
:                     :                           : high-priority legal        :
:                     :                           : updates.                   :

--------------------------------------------------------------------------------

## 4. Enterprise Control Mapping & GRC Policy Drafting

Translate regulatory shifts into internal Governance, Risk & Compliance (GRC)
controls:

1.  **Control Objective Formulation**: Use the naming convention
    `CO-REG-[AGENCY]-[TOPIC]-[YEAR]`.
2.  **Underlying Controls Table**: | Control ID | Control Name | Implementation
    Action | Evidence of Compliance | Target Systems | | :--- | :--- | :---
    | :--- | :--- | | `UC-REG-01.1` | Incident Escalation | Implement 4-hour
    automated ICT incident notification workflow. | SIEM event logs, API audit
    trails. | Cloud SIEM, Identity | | `UC-REG-01.2` | Vendor Risk Audit |
    Maintain continuous third-party cloud audit registry. | Vendor PIA
    assessments, SOC2 reports. | GRC System, Procurement |
