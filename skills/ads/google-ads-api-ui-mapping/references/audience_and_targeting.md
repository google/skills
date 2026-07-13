# Audience & Targeting UI-to-API Mapping

This reference maps Google Ads Audiences and Targeting criteria in the UI to
their Google Ads API equivalents.

## 1. Services

Use these services to configure audiences, user lists, and campaign/ad group
targeting criteria:

| UI Feature /       | API Service                        | Notes / Details    |
: Screen             :                                    :                    :
| :----------------- | :--------------------------------- | :----------------- |
| **Audience         | `AudienceService`                  | Create and manage  |
: Builder**          :                                    : audiences composed :
:                    :                                    : of demographics,   :
:                    :                                    : segments, and      :
:                    :                                    : interests.         :
| **Audience Signals | `AssetGroupSignalService`          | Attach an          |
: (PMax)**           :                                    : `Audience` or      :
:                    :                                    : `SearchTheme` to a :
:                    :                                    : PMax campaign's    :
:                    :                                    : `AssetGroup`.      :
| **Audience         | `UserListService`                  | Create remarketing |
: Segments (User     :                                    : lists, customer    :
: Lists)**           :                                    : match lists, or    :
:                    :                                    : rule-based user    :
:                    :                                    : segments.          :
| **Custom           | `CustomAudienceService` /          | Manage custom      |
: Audiences**        : `CustomInterestService`            : segments built     :
:                    :                                    : from search terms, :
:                    :                                    : app downloads, or  :
:                    :                                    : places.            :
| **Customer Match   | `OfflineUserDataJobService`        | Build offline user |
: Uploads**          :                                    : lists by uploading :
:                    :                                    : customer data      :
:                    :                                    : (hashed emails,    :
:                    :                                    : phones).           :
| **Campaign         | `CampaignCriterionService`         | Add targeting or   |
: Targeting          :                                    : exclusions (e.g.,  :
: Criteria**         :                                    : locations,         :
:                    :                                    : languages,         :
:                    :                                    : negatives,         :
:                    :                                    : placements,        :
:                    :                                    : webpages) at the   :
:                    :                                    : campaign level.    :
| **Ad Group         | `AdGroupCriterionService`          | Add targeting or   |
: Targeting          :                                    : exclusions (e.g.,  :
: Criteria**         :                                    : keywords,          :
:                    :                                    : placements, age,   :
:                    :                                    : gender) at the ad  :
:                    :                                    : group level.       :
| **Account          | `CustomerNegativeCriterionService` | Exclude targeting  |
: Exclusions**       :                                    : criteria (e.g.,    :
:                    :                                    : negative keywords  :
:                    :                                    : or placements)     :
:                    :                                    : across the entire  :
:                    :                                    : account.           :
| **Geo / Location   | `GeoTargetConstantService`         | Search location    |
: Constants**        :                                    : constants          :
:                    :                                    : (countries,        :
:                    :                                    : cities, postal     :
:                    :                                    : codes) for         :
:                    :                                    : geotargeting.      :

## 2. Reporting Resources

Use these resources in GAQL queries to report on targeting criteria and
performance:

*   `audience`: Retrieve audience segment components.
*   `asset_group_signal`: Report on audience signals attached to Performance Max
    campaign asset groups.
*   `user_list`: Query remarketing lists, size, and membership statuses.
*   `campaign_criterion` / `ad_group_criterion`: Report on targeting criteria
    (e.g. keywords, demographics) and metrics.
*   `age_range_view` / `gender_view` / `income_range_view` /
    `parental_status_view`: Demographic performance reports.
*   `geographic_view` / `user_location_view`: Location performance reports.
*   `keyword_view`: Track performance metrics specifically for search keywords.
*   `detail_placement_view` / `group_placement_view`: Placement reporting
    ("Where ads showed").
*   `performance_max_placement_view`: View impression metrics by placement
    specifically for Performance Max campaigns.
*   `webpage_view`: View performance metrics for webpage targeting (dynamic
    search ads).
