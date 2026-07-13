# Planning & Recommendations UI-to-API Mapping

This reference maps Google Ads Planning Tools, Recommendations, and Experiments
in the UI to their Google Ads API equivalents.

## 1. Services

Use these services to retrieve optimization recommendations, forecast campaign
performance, or manage experiments:

UI Feature / Screen                 | API Service                                     | Notes / Details
:---------------------------------- | :---------------------------------------------- | :--------------
**Recommendations Page**            | `RecommendationService`                         | Retrieve optimization recommendations (e.g., bid strategy adjustments, keyword additions).
**Apply / Dismiss Recommendations** | `RecommendationService.MutateRecommendations`   | Apply or dismiss optimization suggestions to improve optimization score.
**Keyword Planner**                 | `KeywordPlanService` / `KeywordPlanIdeaService` | Retrieve search volume, historical data, and forecasts for keyword ideas.
**Reach Planner**                   | `ReachPlanService`                              | Generate reach forecasts for video, display, and search campaign plans.
**Experiments & A/B Tests**         | `ExperimentService` / `ExperimentArmService`    | Create, configure, and promote campaign experiments (split testing).
**Audience Insights**               | `AudienceInsightsService`                       | Retrieve descriptive insights about audience segments and customer interests.
**Recommendations Subscriptions**   | `RecommendationSubscriptionService`             | Manage auto-apply recommendation settings.

## 2. Reporting Resources

Use these resources in GAQL queries to report on optimization suggestions,
planning tools, and simulations:

*   `recommendation`: Report on available recommendations, types, and potential
    impact.
*   `recommendation_subscription`: View active auto-apply recommendations
    settings.
*   `experiment` / `experiment_arm`: Query campaign experiments and A/B test
    groups.
*   `campaign_simulation` / `ad_group_simulation` /
    `ad_group_criterion_simulation`: View bid simulations showing estimated
    performance changes (clicks, cost, impressions) at different bid or budget
    levels.
*   `keyword_plan` / `keyword_plan_campaign` / `keyword_plan_ad_group` /
    `keyword_plan_ad_group_keyword`: View configurations for Keyword Planner
    projects.
