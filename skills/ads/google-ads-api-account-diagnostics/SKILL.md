---
name: google-ads-api-account-diagnostics
description: >-
  Diagnoses Google Ads account performance issues such as conversion loss (value or volume), low lead flow/volume, and lost impression share (opportunities) due to ad rank, bids, or budgets. Use when troubleshooting sudden performance drops, analyzing campaign impression share metrics, investigating low lead flow, or searching for bidding and budget constraints. Don't use for setting up new campaigns, uploading conversion events directly, or general Google Mobile Ads SDK integration issues (use gma-android-integrate instead).
metadata:
  category: GoogleAds
  author: google-ads-api-team
  version: "1.0"
---

# Google Ads API Account Performance Diagnostics Skill

This skill provides instructions on how to use the Google Ads MCP server tools to diagnose common account performance issues.

## Workflows

### Identifying Active Client Accounts
Most diagnostics tasks require sending GAQL queries to a specific customer account. If the customer ID is not explicitly provided by the user, you must first call the `list_accessible_customers` (or `customers_list_accessible_customers`) tool to retrieve the customer resource names/IDs you have access to.

Once you have the list of accessible customer IDs, query the `customer_client` resource using the `search` tool under those customer accounts to find active client customer accounts. Make sure to select only enabled client accounts and filter out manager accounts:
```sql
SELECT
  customer_client.id,
  customer_client.descriptive_name,
  customer_client.status,
  customer_client.manager
FROM customer_client
WHERE customer_client.status = 'ENABLED' AND customer_client.manager = FALSE
```
Only run subsequent diagnostic queries against the enabled client customer IDs retrieved from this list. Do not query deactivated or manager accounts, as doing so will cause API errors.

### Using the MCP Tools Directly
To retrieve information and run queries, you must call the `search` tool on the MCP server directly (with arguments like `customer_id`, `fields`, `resource`, and `conditions`). Do not write or execute custom Python scripts or use the Google Ads client library to query the API, as they will fail authentication inside the evaluation sandbox.

### 1. Conversion and Conversion Value Loss

When conversions or conversion value suddenly decline, use the following steps to diagnose the issue.

**Steps:**
1.  **Discover Fields**: Use `get_resource_metadata` with resource `campaign` or `ad_group` to ensure you have the correct field names.
2.  **Query Performance**: Use `search` to retrieve performance data.
    *   **Resource**: `campaign` or `ad_group`
    *   **Fields**: Include `campaign.name`, `metrics.conversions`, `metrics.conversions_value`, `metrics.cost_micros`.
    *   **Segments**: To isolate the loss, include segments like `segments.date`, `segments.device`, `segments.conversion_action`.
    *   **Conditions**: Compare the period of decline with a previous period (e.g., `segments.date >= '{start_date}'`).
    *   *Gotcha*: `metrics.cost_micros` must be divided by 1,000,000 to get standard currency amounts.

    **Example GAQL Query:**
    To query performance data for a customer account `{customer_id}` between `{start_date}` and `{end_date}`:
    ```sql
    SELECT
      campaign.name,
      metrics.conversions,
      metrics.conversions_value,
      metrics.cost_micros,
      segments.date,
      segments.device,
      segments.conversion_action
    FROM campaign
    WHERE segments.date >= '{start_date}' AND segments.date <= '{end_date}'
    ```

3.  **Analyze**: Check if the loss is limited to certain devices (e.g., mobile vs desktop) or specific conversion actions.
4.  **Check Uploads**: If using offline imports, query `offline_conversion_upload_conversion_action_summary` to verify upload pipeline health. If the query returns no results, report that no offline uploads exist for the account and proceed.

    **Example GAQL Query:**
    To check upload pipeline health for a customer account `{customer_id}`:
    ```sql
    SELECT
      offline_conversion_upload_conversion_action_summary.conversion_action_name,
      offline_conversion_upload_conversion_action_summary.successful_event_count,
      offline_conversion_upload_conversion_action_summary.total_event_count,
      offline_conversion_upload_conversion_action_summary.status
    FROM offline_conversion_upload_conversion_action_summary
    ```

### 2. Opportunities Lost (Impression Share)

To identify lost opportunities due to ad rank, bids, or budgets, analyze impression share metrics.

**Steps:**
1.  **Query Impression Share**: Use `search` to retrieve impression share metrics.
    *   **Resource**: `campaign`
    *   **Fields**: Include `campaign.name`, `metrics.search_impression_share`, `metrics.search_rank_lost_impression_share`, `metrics.search_budget_lost_impression_share`.
    *   *Gotcha*: Impression share values in the API are returned as decimals (e.g., 0.35 = 35%) or formatted strings (e.g., `"< 0.10"`).

    **Example GAQL Query:**
    To query impression share metrics for a customer account `{customer_id}` between `{start_date}` and `{end_date}`:
    ```sql
    SELECT
      campaign.name,
      metrics.search_impression_share,
      metrics.search_rank_lost_impression_share,
      metrics.search_budget_lost_impression_share
    FROM campaign
    WHERE segments.date >= '{start_date}' AND segments.date <= '{end_date}'
    ```

2.  **Analyze**:
    *   High `search_budget_lost_impression_share` indicates opportunities lost due to limited budget.
    *   High `search_rank_lost_impression_share` indicates opportunities lost due to low ad rank (bid or quality issues).

### 3. Low Lead Flow Diagnostics

When a user asks "why is my lead flow low these past few days?", follow this systematic approach.

**Steps:**
1.  **Confirm Drop**: Query conversions segmented by date for the last few days vs the previous period.
2.  **Isolate Cause**:
    *   Check if **Traffic** (clicks, impressions) dropped.
    *   Check if **Conversion Rate** (conversions/clicks) dropped.
3.  **If Traffic Dropped**: Check Impression Share metrics (see Workflow 2) to see if it's a budget or rank issue, or if search volume generally declined.
4.  **If Conversion Rate Dropped**: Check breakdowns by `segments.device` or `segments.conversion_action` to see if a specific area is failing.
5.  **Check Changes**: Query the `change_event` resource to see if any changes were made to bids, budgets, or targeting around the time the drop started.
    *   *Gotcha (change_event constraints)*: Queries to the `change_event` resource:
        *   Must specify a `LIMIT` clause of less than or equal to 10000.
        *   Must filter by date (`change_event.change_date_time`) within the past 30 days.
        *   Cannot select performance metrics (e.g., `metrics.*` is not supported; only `change_event` attributes and allowed resource fields can be selected).

    **Example GAQL Query:**
    To query change events for a customer account `{customer_id}` between `{start_date}` and `{end_date}`:
    ```sql
    SELECT
      change_event.change_date_time,
      change_event.change_resource_name,
      change_event.resource_change_operation,
      change_event.changed_fields
    FROM change_event
    WHERE change_event.change_date_time >= '{start_date}' AND change_event.change_date_time <= '{end_date}'
    LIMIT 10000
    ```

### 4. Offline Upload Pipeline Diagnostics

When offline conversion uploads for a specific action (e.g., store-purchase) stop showing up or fail, use the following steps to diagnose the issue.

**Steps:**
1.  **Retrieve Client Accounts**: If `{customer_id}` is not provided, first call the `list_accessible_customers` (or `customers_list_accessible_customers`) tool to retrieve the customer resource names/IDs you have access to. Then, query the `customer_client` resource to find active client customer accounts, ensuring you filter out manager accounts and deactivated/canceled accounts to avoid query errors.

    **Example GAQL Query:**
    ```sql
    SELECT
      customer_client.id,
      customer_client.descriptive_name,
      customer_client.status,
      customer_client.manager
    FROM customer_client
    WHERE customer_client.status = 'ENABLED' AND customer_client.manager = FALSE
    ```

2.  **Verify Pipeline Health**: Query `offline_conversion_upload_conversion_action_summary` for the active client account.
    *   **Fields**: Include `offline_conversion_upload_conversion_action_summary.conversion_action_name`, `offline_conversion_upload_conversion_action_summary.successful_event_count`, `offline_conversion_upload_conversion_action_summary.total_event_count`, and `offline_conversion_upload_conversion_action_summary.status`.

    **Example GAQL Query:**
    ```sql
    SELECT
      offline_conversion_upload_conversion_action_summary.conversion_action_name,
      offline_conversion_upload_conversion_action_summary.successful_event_count,
      offline_conversion_upload_conversion_action_summary.total_event_count,
      offline_conversion_upload_conversion_action_summary.status
    FROM offline_conversion_upload_conversion_action_summary
    ```

3.  **Analyze**:
    *   *Gotcha*: If the query to `offline_conversion_upload_conversion_action_summary` returns no results or is empty (indicating there are no offline conversion uploads configured or active for the customer account), immediately stop/break the diagnostic workflow. Report directly to the user that no offline conversion upload data or summaries exist in the accessible account(s), rather than retrying or attempting to generate custom scripts.
    *   If results are returned, verify the upload success rate by comparing `successful_event_count` with `total_event_count`. Check the `status` field to diagnose failures.

