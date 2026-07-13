---
name: google-ads-api-ui-mapping
description: >-
  Maps Google Ads UI features, screens, and report tables to Google Ads API resources,
  services, and GAQL queries. Helps developers translate user-facing UI concepts into
  API code.
  Use this skill when:
  - The user asks how to implement a specific Google Ads UI feature or setting via the API.
  - The user provides a screenshot or URL of the Google Ads UI and asks how to fetch its data.
  - The user is trying to map UI reports or dimensions to the API.
  - The user asks about API-parity for specific front-end UI features (e.g., Performance Max targeting, AI Max).
  Don't use for:
  - General Google Ads API questions not involving a UI concept.
  - Troubleshooting API code errors unrelated to UI feature mapping.
  - Questions about Google Ads features that are exclusively front-end and have no API representation.
  - Queries about other Google APIs or services.
compatibility: "Requires standard network access to resolve dynamic Google Ads API versions."
metadata:
  author: google-ads-api-team
  version: "1.0"
  category: GoogleAds
---

# Google Ads UI to API Mapping Guide

This skill helps developers translate front-end Google Ads UI concepts, screens,
and workflows into back-end Google Ads API services, resources, and Google Ads
Query Language (GAQL) fields.

## Crucial Requirement: Dynamic Version Resolution

To ensure code stability and security, you **MUST** resolve the latest stable
major version of the Google Ads API dynamically. Do not hardcode version numbers
(like `v24`). Follow the version resolution flow described in the
[google-ads-api-quickstart](../google-ads-api-quickstart/SKILL.md#crucial-requirement-dynamic-version-resolution--runtime-resolution)
skill.

--------------------------------------------------------------------------------

## 1. Mapping Procedure

When a user asks how to translate a UI feature, dashboard, or screenshot to the
API, follow this systematic process:

### Step 1: Identify the Campaign/Entity Type

*   Determine if the feature belongs to a specific campaign type (e.g., Search,
    Display, Shopping, Performance Max, Demand Gen).
*   In the API, campaign types are defined by the `advertising_channel_type` and
    `advertising_channel_sub_type` fields on the `Campaign` resource.

### Step 2: Search for Semantic Equivalents

*   UI names and API field names often differ. Do not search only for literal UI
    strings.
*   **Common Naming Disconnects:**
    *   UI: "Audience Signal" (PMax) -> API: `AssetGroupSignal`
    *   UI: "Final URL Expansion" -> API: `Campaign.url_expansion_opt_out`
        (inverted boolean logic: `false` means opt-in/expand URLs)
    *   UI: "URL Exclusions" (Campaign level) -> API: `CampaignCriterion` with a
        `webpage` criterion (using WebpageInfo) where `negative = true`.
    *   UI: "Item ID sold" (Shopping Cross-sell) -> API: Not directly queryable
        as a dimension. The API only exposes cross-sell *metrics* (e.g.,
        `metrics.cross_sell_conversions_value`) that must be queried against the
        *clicked* product.

### Step 3: Map UI Reports to API Views

*   If the user wants to fetch data from a UI report table, map the report type
    to the corresponding API report view (e.g., `shopping_performance_view`,
    `detail_placement_view`).
*   Verify field availability in the target view. Some dimensions visible in the
    UI may not exist in the API, or may require segmenting differently.

--------------------------------------------------------------------------------

## 2. UI-to-API Reference Directory

For a comprehensive list of UI-to-API mappings, refer to the following guides
split by functionality type / user journey:

*   [Account Management](references/account_management.md) — Account discovery,
    user access, and third-party product linkages.
*   [Billing & Invoicing](references/billing.md) — Billing setups, payment
    profiles, budgets, and invoices.
*   [Campaign Structure](references/campaign_structure.md) — Campaigns, ad
    groups, shared budgets, and labels.
*   [Bidding Management](references/bidding.md) — Portfolio bidding strategies,
    seasonal adjustments, and bid modifiers.
*   [Creatives & Assets](references/creatives_and_assets.md) — Ads, asset
    library uploads, PMax asset groups, and previews.
*   [Conversions Tracking](references/conversions.md) — Conversion actions,
    value rules, and offline conversion uploads.
*   [Audience & Targeting](references/audience_and_targeting.md) — Audiences,
    custom segments, customer match, and criterion targeting (keywords,
    locations, placements, exclusions).
*   [Planning & Optimization](references/planning_and_recommendations.md) —
    Keyword planner, reach planner, Recommendations, and simulations.
*   [Reporting & Performance](references/reporting_and_performance.md) —
    Reporting views (e.g., Shopping performance, placement performance, click
    views, search terms).
*   [Change History](references/change_history.md) — Querying account change
    history and status updates.

--------------------------------------------------------------------------------

## 3. Handling API Parity Gaps

If a UI feature is not supported in the Google Ads API:

1.  **Acknowledge the Gap:** Explicitly state that the feature is currently
    unavailable or unsupported in the API.
2.  **Explain the Limitation:** Tell the user *why* it cannot be queried
    directly (e.g., "conversions by placement for PMax are server-side
    aggregated and not exposed via GAQL").
3.  **Propose Alternatives:** Offer the closest functional equivalent or
    alternative query pattern. E.g., for cross-sell analytics, query the
    cross-sell metrics (like `cross_sell_conversions`) grouped by the *clicked*
    product.

> [!IMPORTANT] **PMax Placement Performance Parity Rule:** When asked about
> querying placement performance or conversions for Performance Max campaigns,
> the response **MUST** explicitly state that conversions by placement for
> Performance Max campaigns are **NOT** supported in the Google Ads API. The
> response **MUST** suggest using `detail_placement_view` or
> `group_placement_view` to query placement performance impressions instead as
> the alternative.

--------------------------------------------------------------------------------

## 4. Detailed Setup Guides

### Workflow A: Building a Performance Max Campaign with Audience Signals

> [!IMPORTANT] **PMax Order of Operations Requirement:** When the user asks how
> to add audience signals or targeting to a Performance Max campaign, you
> **MUST** explain the entire PMax setup context. Do not just show the
> `AssetGroupSignal` creation. You **MUST** explicitly state and detail the
> following order of operations: `Campaign Budget -> Campaign -> Asset Group ->
> Assets -> Asset Group Asset -> Asset Group Signal` You **MUST** instruct the
> developer to: 1. Create a `Campaign` with `advertising_channel_type =
> PERFORMANCE_MAX`. 2. Create an `AssetGroup`. 3. Link `Asset`s. 4. Use
> `AssetGroupSignal` to attach targeting criteria (like `Audience` or
> `SearchTheme`) to the `AssetGroup`.

To build a PMax campaign programmatically, you must execute requests in the
following sequence:

1.  **Create Campaign Budget**:
    *   Service: `CampaignBudgetService`
    *   Fields: `amount_micros`, `delivery_method` (standard),
        `explicitly_shared` (typically `false` for campaign-specific budget).
2.  **Create Campaign**:
    *   Service: `CampaignService`
    *   Fields:
        *   `advertising_channel_type` = `PERFORMANCE_MAX`
        *   `status` = `PAUSED` (recommended for testing)
        *   `bidding_strategy_type` = `MAXIMIZE_CONVERSION_VALUE` or
            `MAXIMIZE_CONVERSIONS` (PMax only supports automated bidding
            strategies).
        *   `campaign_budget` = Resource name of budget from Step 1.
3.  **Create Asset Group**:
    *   Service: `AssetGroupService`
    *   Fields:
        *   `campaign` = Resource name of the campaign from Step 2.
        *   `name` = Name of the asset group.
        *   `final_urls` = List of landing page URLs.
        *   `status` = `PAUSED` or `ENABLED`.
4.  **Upload Assets**:
    *   Service: `AssetService`
    *   Details: Upload raw assets (text, images, logos) to get their resource
        names. PMax has minimum asset requirements (e.g., headlines,
        descriptions, images).
5.  **Link Assets to Asset Group**:
    *   Service: `AssetGroupAssetService`
    *   Fields:
        *   `asset_group` = Resource name of the asset group from Step 3.
        *   `asset` = Resource name of the uploaded asset from Step 4.
        *   `field_type` = The asset field type (e.g., `HEADLINE`,
            `DESCRIPTION`, `MARKETING_IMAGE`).
6.  **Create Audience Signals (Targeting)**:
    *   Service: `AssetGroupSignalService`
    *   Fields:
        *   `asset_group` = Resource name of the asset group from Step 3.
        *   `audience` = `AudienceInfo` structure linking to an `Audience`
            resource (created via `AudienceService`).
        *   OR `search_theme` = `SearchThemeInfo` containing the target search
            term.

### Workflow B: Activating Search Campaign Automation (AI Max)

> [!IMPORTANT] **AI Max Context Requirement:** When asked about AI Max, the
> response **MUST** clarify that AI Max is a feature concept specifically for
> Search campaigns, and is **NOT** applicable to Performance Max campaigns.

To map the "AI Max" experience to a Search campaign:

1.  **Smart Bidding**: Set the campaign bidding strategy to
    `MAXIMIZE_CONVERSIONS` or `MAXIMIZE_CONVERSION_VALUE`.
2.  **Broad Match Keywords**: Set the campaign-level keyword match type to broad
    match:
    *   Field: `Campaign.keyword_match_type` = `BROAD`
3.  **Final URL Expansion**: Set `Campaign.url_expansion_opt_out` to `false`.

--------------------------------------------------------------------------------

## 5. Code Generation Guidelines

When generating code to demonstrate a UI mapping request:

1.  **Language Selection**: Check if the user has specified a preferred language
    (Python, Java, .NET, PHP, Ruby, Perl) or REST. If not, use Python.
2.  **Clean Inputs**: Strip hyphens from customer IDs before passing them to the
    API.
3.  **Dynamic Version Imports**: Ensure import namespaces use the resolved API
    version (e.g., `com.google.ads.googleads.v24` for Java, or namespace imports
    for C#/PHP/Python).
