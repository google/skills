# Conversions UI-to-API Mapping

This reference maps Google Ads Conversions UI configuration and upload workflows
to their Google Ads API equivalents.

## 1. Services

Use these services to configure conversion goals, upload conversions, or adjust
conversion data:

| UI Feature /  | API Service                         | Notes / Details      |
: Screen        :                                     :                      :
| :------------ | :---------------------------------- | :------------------- |
| **Conversion  | `ConversionActionService`           | Create and manage    |
: Actions**     :                                     : conversion actions   :
:               :                                     : (e.g., track         :
:               :                                     : purchase, lead form, :
:               :                                     : sign-up).            :
| **Conversion  | `ConversionValueRuleService` /      | Adjust conversion    |
: Value Rules** : `ConversionValueRuleSetService`     : values dynamically   :
:               :                                     : based on conditions  :
:               :                                     : like location,       :
:               :                                     : device, or audience. :
| **Upload      | `ConversionUploadService`           | Upload offline       |
: Conversions   :                                     : conversions (e.g.,   :
: (Offline)**   :                                     : click conversions    :
:               :                                     : via                  :
:               :                                     : GCLID/GBRAID/WBRAID, :
:               :                                     : call conversions).   :
| **Adjust      | `ConversionAdjustmentUploadService` | Adjust uploaded      |
: Conversions   :                                     : conversions (e.g.,   :
: (Upload)**    :                                     : restate values,      :
:               :                                     : retract              :
:               :                                     : conversions).        :
| **User Data / | `UserDataService` /                 | Upload customer      |
: Enhanced      : `OfflineUserDataJobService`         : match data or        :
: Conversions** :                                     : customer data for    :
:               :                                     : enhanced conversions :
:               :                                     : (e.g., hashed        :
:               :                                     : emails, phone        :
:               :                                     : numbers).            :
| **Conversion  | `CampaignConversionGoalService` /   | Configure            |
: Goals**       : `CustomerConversionGoalService` /   : campaign-level or    :
:               : `CustomConversionGoalService`       : account-level        :
:               :                                     : conversion goals and :
:               :                                     : custom goals.        :

## 2. Reporting Resources

Use these resources in GAQL queries to report on conversion setups and results:

*   `conversion_action`: Retrieve conversion action configurations, tracking
    status, and category.
*   `conversion_value_rule` / `conversion_value_rule_set`: Query conversion
    value rules and their applications.
*   `campaign_conversion_goal` / `customer_conversion_goal` /
    `custom_conversion_goal`: View conversion goal configurations.
*   `call_view`: Query call metrics and associated call conversions.
*   `cart_data_sales_view`: Report on cart data and sales metrics (for merchants
    tracking cart conversions).
*   `lead_form_submission_data`: Retrieve leads collected via lead form assets.
*   `local_services_lead` / `local_services_lead_conversation`: Query leads and
    conversions for Local Services Ads.
