# Creatives & Assets UI-to-API Mapping

This reference maps Google Ads Creative and Asset UI components to their Google
Ads API equivalents.

## 1. Services

Use these services to upload media, create assets, and link them to campaigns or
ad groups:

| UI Feature / Screen | API Service                  | Notes / Details         |
| :------------------ | :--------------------------- | :---------------------- |
| **Ads Management**  | `AdService` /                | Create and configure    |
:                     : `AdGroupAdService`           : ads (e.g., Responsive   :
:                     :                              : Search Ads, Display     :
:                     :                              : Ads, App Ads).          :
| **Asset Library     | `AssetService`               | Upload raw assets       |
: (Upload)**          :                              : (e.g., images, logos,   :
:                     :                              : videos, HTML5) or       :
:                     :                              : create text assets      :
:                     :                              : (headlines,             :
:                     :                              : descriptions).          :
| **Asset Groups      | `AssetGroupService`          | Create and manage asset |
: (PMax)**            :                              : groups specifically for :
:                     :                              : Performance Max         :
:                     :                              : campaigns.              :
| **Asset Group       | `AssetGroupAssetService`     | Link uploaded assets to |
: Linkages**          :                              : an `AssetGroup` with    :
:                     :                              : specific roles (e.g.,   :
:                     :                              : `HEADLINE`,             :
:                     :                              : `MARKETING_IMAGE`).     :
| **Campaign Asset    | `CampaignAssetService`       | Attach assets (like     |
: Links**             :                              : sitelinks, callouts,    :
:                     :                              : lead forms) directly to :
:                     :                              : a campaign.             :
| **Ad Group Asset    | `AdGroupAssetService`        | Attach assets directly  |
: Links**             :                              : to an ad group.         :
| **Customer Asset    | `CustomerAssetService`       | Attach assets at the    |
: Links**             :                              : account level (applies  :
:                     :                              : to all campaigns).      :
| **Ad Customizers**  | `CustomizerAttributeService` | Configure ad            |
:                     : / `AdGroupCustomizerService` : customizers (e.g., text :
:                     :                              : replacement based on    :
:                     :                              : targeting).             :
| **YouTube Video     | `YouTubeVideoUploadService`  | Upload videos directly  |
: Upload**            :                              : to YouTube for use in   :
:                     :                              : video campaigns.        :
| **Ad Previews**     | `ShareablePreviewService`    | Generate shareable      |
:                     :                              : preview links for ads   :
:                     :                              : to verify layout.       :

## 2. Reporting Resources

Use these resources in GAQL queries to report on creatives, assets, and
combinations:

*   `ad`: Retrieve raw ad metadata and landing URLs.
*   `ad_group_ad`: Query ad group ad metrics, status, and policy approvals.
*   `asset`: View assets in the account, their types (e.g., `IMAGE`, `TEXT`,
    `LEAD_FORM`), and performance ratings.
*   `asset_group`: Query Performance Max asset group performance.
*   `asset_group_asset`: Report on asset-to-asset group assignments and
    performance ratings.
*   `campaign_asset` / `ad_group_asset` / `customer_asset`: Report on asset
    linkages and extensions at various levels.
*   `ad_group_ad_asset_view`: View performance metrics of assets within
    responsive search ads.
*   `ad_group_ad_asset_combination_view`: View performance metrics of asset
    combinations served to users.
*   `asset_group_top_combination_view`: View top-performing asset combinations
    for PMax.
*   `media_file`: Query uploaded media files (e.g., images, zip archives).
