# Reporting & Performance UI-to-API Mapping

This reference maps Google Ads UI reports, charts, and metrics to their Google
Ads API equivalents.

## 1. Services

Use this service to run reporting queries:

| UI Feature / Screen | API Service               | Notes / Details          |
| :------------------ | :------------------------ | :----------------------- |
| **All Reports /     | `GoogleAdsService.Search` | Run GAQL queries against |
: Tables**            : / `SearchStream`          : any reporting view or    :
:                     :                           : resource to fetch        :
:                     :                           : performance data.        :

## 2. Reporting Resources

Use these resources in the FROM clause of your GAQL queries to build reports:

### Performance Views

*   `shopping_performance_view`: Query Shopping campaign performance (e.g.,
    product item IDs, category).
    *   *Shopping Cross-Sell Parity Gap:* Dimensions like "Item ID sold" or
        "Product Title sold" are **NOT available** in the Google Ads API.
    *   *Alternative:* You must query cross-sell metrics (e.g.,
        `metrics.cross_sell_conversions` or
        `metrics.cross_sell_conversions_value`) grouped by the *clicked* product
        (using `segments.product_item_id` or `segments.product_title`) in
        `shopping_performance_view`.
*   `click_view`: Query individual click-level details (GCLID, click type,
    device).
*   `landing_page_view`: Report on landing page performance and URL parameters.
*   `expanded_landing_page_view`: Report on expanded final URLs served.
*   `travel_activity_performance_view` / `hotel_performance_view`: Query
    performance for Travel and Hotel campaigns.

### Insights & Search Terms

*   `search_term_view`: Query search terms that triggered ads and their
    performance (impressions, clicks, conversions).
*   `campaign_search_term_insight` / `customer_search_term_insight`: Query
    search term categories and trends.
*   `dynamic_search_ads_search_term_view`: View search term performance
    specifically for Dynamic Search Ads.
*   `paid_organic_search_term_view`: Compare paid and organic search queries.
*   `ai_max_search_term_ad_combination_view`: Query ad combinations for AI Max
    (Search campaign automation) queries.

### Other Utilities

*   `batch_job`: Track batch mutation job statuses (`BatchJobService`).
