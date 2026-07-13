# Bidding UI-to-API Mapping

This reference maps Google Ads Bidding UI settings and tools to their Google Ads
API equivalents.

## 1. Services

Use these services to configure bid strategies and bid adjustments:

| UI Feature /     | API Service                           | Notes / Details   |
: Screen           :                                       :                   :
| :--------------- | :------------------------------------ | :---------------- |
| **Bid Strategies | `BiddingStrategyService`              | Create and manage |
: (Portfolio)**    :                                       : portfolio bidding :
:                  :                                       : strategies (e.g., :
:                  :                                       : target CPA,       :
:                  :                                       : target ROAS,      :
:                  :                                       : maximize          :
:                  :                                       : conversions).     :
| **Bid Exclusions | `BiddingDataExclusionService`         | Set bid           |
: (Advanced)**     :                                       : exclusions (data  :
:                  :                                       : exclusions) to    :
:                  :                                       : ignore temporary  :
:                  :                                       : website issues or :
:                  :                                       : conversion        :
:                  :                                       : tracking outages. :
| **Seasonality    | `BiddingSeasonalityAdjustmentService` | Apply seasonal    |
: Adjustments**    :                                       : bid adjustments   :
:                  :                                       : for expected      :
:                  :                                       : short-term        :
:                  :                                       : conversion rate   :
:                  :                                       : changes (e.g.,    :
:                  :                                       : sales events).    :
| **Campaign Bid   | `CampaignBidModifierService`          | Apply bid         |
: Modifiers**      :                                       : adjustments at    :
:                  :                                       : the campaign      :
:                  :                                       : level (e.g.,      :
:                  :                                       : target specific   :
:                  :                                       : device types or   :
:                  :                                       : locations).       :
| **Ad Group Bid   | `AdGroupBidModifierService`           | Apply bid         |
: Modifiers**      :                                       : adjustments at    :
:                  :                                       : the ad group      :
:                  :                                       : level (e.g.,      :
:                  :                                       : target            :
:                  :                                       : demographics or   :
:                  :                                       : devices).         :

## 2. Reporting Resources

Use these resources in GAQL queries to report on bidding configurations and
performance:

*   `bidding_strategy`: View details and statuses of portfolio bidding
    strategies.
*   `accessible_bidding_strategy`: Report on bidding strategies shared from
    manager accounts.
*   `bidding_data_exclusion`: Query active and historical data exclusions.
*   `bidding_seasonality_adjustment`: Query seasonality adjustment
    configurations.
*   `campaign_bid_modifier`: Report on device, location, or demographic
    adjustments at the campaign level.
*   `ad_group_bid_modifier`: Report on ad group level bid adjustments.
