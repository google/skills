# Account Management UI-to-API Mapping

This reference maps Google Ads Account Management UI workflows to their Google
Ads API equivalents.

## 1. Services

Use these services for mutating or managing account settings, access, and
linkages:

| UI Feature /    | API Service                               | Notes /        |
: Screen          :                                           : Details        :
| :-------------- | :---------------------------------------- | :------------- |
| **Account       | `CustomerService.ListAccessibleCustomers` | Retrieve the   |
: Discovery /     :                                           : list of        :
: Setup**         :                                           : customers that :
:                 :                                           : the            :
:                 :                                           : authenticating :
:                 :                                           : user has       :
:                 :                                           : direct or      :
:                 :                                           : indirect       :
:                 :                                           : access to.     :
| **Account       | `CustomerUserAccessService`               | Manage user    |
: Access &        :                                           : access levels  :
: Security**      :                                           : (ADMIN, WRITE, :
:                 :                                           : READ, etc.)    :
:                 :                                           : for a specific :
:                 :                                           : customer       :
:                 :                                           : account.       :
| **Manager       | `CustomerManagerLinkService`              | Link or unlink |
: Links**         :                                           : client         :
:                 :                                           : accounts to a  :
:                 :                                           : Manager        :
:                 :                                           : Account.       :
| **Client        | `CustomerClientLinkService`               | Accept or      |
: Links**         :                                           : reject manager :
:                 :                                           : link requests  :
:                 :                                           : from a client  :
:                 :                                           : account        :
:                 :                                           : perspective.   :
| **User Access   | `CustomerUserAccessInvitationService`     | Invite new     |
: Invitations**   :                                           : users to       :
:                 :                                           : access a       :
:                 :                                           : Google Ads     :
:                 :                                           : account.       :
| **Product       | `ProductLinkService` /                    | Link Google    |
: Links**         : `ProductLinkInvitationService`            : Ads to other   :
:                 :                                           : Google         :
:                 :                                           : products       :
:                 :                                           : (e.g.,         :
:                 :                                           : Merchant       :
:                 :                                           : Center, Google :
:                 :                                           : Analytics,     :
:                 :                                           : Firebase,      :
:                 :                                           : YouTube).      :
| **Account Link  | `AccountLinkService`                      | Link Google    |
: (Third-Party)** :                                           : Ads to         :
:                 :                                           : third-party    :
:                 :                                           : accounts       :
:                 :                                           : (e.g.,         :
:                 :                                           : third-party    :
:                 :                                           : app analytics  :
:                 :                                           : tools).        :
| **Advertiser    | `IdentityVerificationService`             | Manage         |
: Verification**  :                                           : advertiser     :
:                 :                                           : identity       :
:                 :                                           : verification.  :

## 2. Reporting Resources

Use these resources in GAQL queries (from the `google_ads_service` FROM clause)
to report on account settings and metadata:

*   `customer`: Retrieve customer details (e.g., descriptive name, currency,
    timezone, auto-tagging).
*   `customer_client`: Retrieve hierarchical customer-client relationships under
    a Manager Account.
*   `customer_user_access`: Report on users who have access to the account and
    their access levels.
*   `customer_user_access_invitation`: Track pending user invitations.
*   `customer_manager_link`: Query active or pending manager links.
*   `customer_client_link`: Query active or pending client links.
*   `product_link` / `product_link_invitation`: Report on linked products.
*   `data_link`: Track link status for shared data between Google Ads and other
    platforms.
