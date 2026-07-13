# Campaign Structure UI-to-API Mapping

This reference maps Google Ads Campaign Structure UI components to their Google
Ads API equivalents.

## 1. Services

Use these services to build and modify campaigns, ad groups, and associated
settings:

| UI Feature / Screen  | API Service                   | Notes / Details       |
| :------------------- | :---------------------------- | :-------------------- |
| **Campaigns List /   | `CampaignService`             | Create and configure  |
: Settings**           :                               : campaigns (e.g.,      :
:                      :                               : name, status, type,   :
:                      :                               : network settings,     :
:                      :                               : bidding strategy).    :
| **Ad Groups List /   | `AdGroupService`              | Create and manage ad  |
: Settings**           :                               : groups under a        :
:                      :                               : campaign.             :
| **Shared Budgets**   | `CampaignBudgetService`       | Manage campaign       |
:                      :                               : budgets (shared       :
:                      :                               : across campaigns or   :
:                      :                               : campaign-specific).   :
| **Campaign Groups**  | `CampaignGroupService`        | Group multiple        |
:                      :                               : campaigns together to :
:                      :                               : track overall         :
:                      :                               : performance (e.g.,    :
:                      :                               : portfolio tracking).  :
| **Labels**           | `LabelService` /              | Apply organizational  |
:                      : `CampaignLabelService` /      : tags (labels) to      :
:                      : `AdGroupLabelService`         : campaigns, ad groups, :
:                      :                               : or ads.               :
| **Smart Campaigns**  | `SmartCampaignSettingService` | Manage settings       |
:                      :                               : specifically for      :
:                      :                               : Smart campaigns.      :
| **Shared Libraries** | `SharedSetService` /          | Create and associate  |
:                      : `CampaignSharedSetService`    : shared sets (e.g.,    :
:                      :                               : negative keyword      :
:                      :                               : lists, placement      :
:                      :                               : exclusion lists) to   :
:                      :                               : campaigns.            :
| **Campaign Drafts**  | `CampaignDraftService`        | Create and manage     |
:                      :                               : drafts before         :
:                      :                               : applying changes to   :
:                      :                               : campaigns.            :

## 2. Reporting Resources

Use these resources in GAQL queries to report on campaign hierarchy and
settings:

*   `campaign`: Query campaign metadata, statuses, and performance metrics.
*   `ad_group`: Query ad group metadata and metrics.
*   `campaign_budget`: View campaign budget amounts and delivery methods.
*   `campaign_group`: Report on campaign groups.
*   `label`: Query label metadata (e.g., name, color).
*   `campaign_label` / `ad_group_label`: Report on label-to-entity mappings.
*   `shared_set` / `campaign_shared_set`: Report on negative keyword lists and
    other shared sets linked to campaigns.
*   `smart_campaign_setting`: View configurations for Smart campaigns.
