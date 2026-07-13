# Change History UI-to-API Mapping

This reference maps Google Ads Change History UI screens to their Google Ads API
equivalents.

## 1. Services

*   **No Mutate Services**: Change history is read-only. There are **NO**
    standalone services like `ChangeEventService` or `ChangeStatusService` in
    the Google Ads API.
*   **Query Service**: To retrieve change history, you must use
    `GoogleAdsService.Search` or `SearchStream`.

## 2. Reporting Resources

Use these resources in the FROM clause of your GAQL queries to report on changes
made to the account:

| UI Feature / Screen      | API Resource    | Notes / Details                 |
| :----------------------- | :-------------- | :------------------------------ |
| **Change History Report  | `change_event`  | Tracks granular changes to      |
: (Details)**              :                 : resources (Campaigns, Ad        :
:                          :                 : Groups, Ads, Criteria, Budgets, :
:                          :                 : Assets). Details include the    :
:                          :                 : resource name, the changed      :
:                          :                 : fields, old vs. new values, the :
:                          :                 : user email who made the change, :
:                          :                 : the client application used,    :
:                          :                 : and the timestamp.              :
| **Change History (Status | `change_status` | Represents the most recent      |
: Sync)**                  :                 : change status of a resource.    :
:                          :                 : Used primarily by developers to :
:                          :                 : optimize synchronization (e.g., :
:                          :                 : check if a Campaign changed     :
:                          :                 : since a specific timestamp to   :
:                          :                 : decide whether to fetch it      :
:                          :                 : again).                         :
