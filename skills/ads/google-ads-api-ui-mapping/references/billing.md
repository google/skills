# Billing UI-to-API Mapping

This reference maps Google Ads Billing and Invoicing UI workflows to their
Google Ads API equivalents.

## 1. Services

Use these services for billing setup and budget management:

| UI Feature / Screen | API Service                    | Notes / Details       |
| :------------------ | :----------------------------- | :-------------------- |
| **Billing Transfers | `BillingSetupService`          | Manage billing        |
: / Setup**           :                                : setups, including     :
:                     :                                : linking a payments    :
:                     :                                : profile to a customer :
:                     :                                : account.              :
| **Budget            | `AccountBudgetProposalService` | Create proposals to   |
: Allocations**       :                                : change billing        :
:                     :                                : budgets (e.g., adjust :
:                     :                                : spend limits,         :
:                     :                                : start/end dates).     :
| **Payments          | `PaymentsAccountService`       | Retrieve payments     |
: Accounts**          :                                : accounts associated   :
:                     :                                : with the customer to  :
:                     :                                : configure billing.    :
| **Incentives /      | `IncentiveService`             | Manage promotional    |
: Promos**            :                                : codes and incentives  :
:                     :                                : applied to the        :
:                     :                                : account.              :

## 2. Reporting Resources

Use these resources in GAQL queries to report on billing and invoicing details:

*   `billing_setup`: View the active and pending billing configurations for the
    account.
*   `account_budget`: View account-level budgets, start/end times, and total
    spend limits.
*   `account_budget_proposal`: Track historical and pending billing budget
    proposals.
*   `invoice`: Retrieve invoices, tax documents, and adjustment details (e.g.,
    PDF links, billing dates).
*   `applied_incentive`: Query promotions and discounts applied to the account.
*   `hotel_reconciliation`: Reconcile billing for Hotel campaigns
    (commission-based bidding).
