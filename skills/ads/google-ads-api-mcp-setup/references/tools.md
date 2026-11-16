# Google Ads MCP Server Tool Reference

All tools below are mounted by default across five namespaces (`customers`,
`search`, `metadata`, `labels`, and `assets`).

## Table of Contents

- [Read Tools](#read-tools): Lines 12-52
- [Partial Mutate Tools](#partial-mutate-tools): Lines 53-136
- [Read-Only Mode (`tools_config.yaml`)](#read-only-mode-tools_configyaml): Lines 137-150

## Read Tools

### 1. `customers_list_accessible_customers` (`list_accessible_customers`)

* **Purpose:** Returns the list of Google Ads customer IDs and account names
  that are accessible to the authenticated user.
* **How to Use:** Call first when starting a new session or when the target
  customer ID is unknown. Requires no arguments.
* **Example Intent:** *"What Google Ads accounts do I have access to?"*

### 2. `metadata_get_resource_metadata` (`get_resource_metadata`)

* **Purpose:** Retrieves selectable, filterable, and sortable GAQL fields,
  metrics, and segments for a Google Ads API resource type (e.g., `campaign`,
  `ad_group`, `customer`).
* **Arguments:**
  * `resource_name` (string, required): Resource name to inspect (e.g.,
    `campaign`).
  * `login_customer_id` (string, optional): Manager account ID when accessing a
    client account via a manager.
* **Example Intent:** *"What fields and metrics can I query for an ad group?"*

### 3. `search_search` (`search`)

* **Purpose:** Builds and executes GAQL `SearchStream` queries from structured
  parameters rather than a raw GAQL string.
* **Arguments:**
  * `customer_id` (string, required): 10-digit target Google Ads customer ID
    (digits only, no hyphens).
  * `resource` (string, required): Google Ads API resource name (e.g.,
    `campaign`).
  * `fields` (list of strings, required): Selectable fields, metrics, and
    segments (e.g., `["campaign.id", "campaign.name", "campaign.status",`
    `"metrics.impressions"]`).
  * `conditions` (`list[str]`, optional) and `orderings` (`list[str]`,
    optional): Structured filter and sort expressions.
  * `limit` (`int`, optional) and `login_customer_id` (string, optional): Row
    limit and manager account ID.
* **Example Intent:** *"Get the impressions and status of all enabled
  campaigns for account 1234567890."*

## Partial Mutate Tools

Mutate support covers standalone asset creation, local video uploads, and
account/entity label management. The server cannot link assets to campaigns or
ad groups, or create, modify, pause, or enable campaigns, ad groups, ads,
budgets, or bids.

### Propose-and-Confirm Safety Workflow

Every mutate tool enforces a two-step workflow:

1. **Propose (`validate_only=True`, default):** Validates inputs without
   committing changes (`assets_upload_video_asset` validates the local file
   and binds its size and modification timestamp) and returns `change_items`
   plus a stateless SHA-256 `checksum` bound to `customer_id` and payload.
2. **Confirm (`validate_only=False`):** After user approval, call the tool
   again with `validate_only=False`, the identical `customer_id` and
   arguments, and the `checksum` from step 1.

### 4. `assets_create_asset` (`create_asset`)

* **Purpose:** Creates standalone Google Ads assets (`TEXT`, `IMAGE`,
  `YOUTUBE_VIDEO`, `SITELINK`, `CALLOUT`, `STRUCTURED_SNIPPET`, or other
  `AssetService` types via `extra_params`).
* **Key Arguments:**
  * `customer_id` (string, required): 10-digit target Google Ads customer ID.
  * `asset_type` (string, required): Asset type (e.g., `TEXT`, `IMAGE`,
    `YOUTUBE_VIDEO`, `SITELINK`, `CALLOUT`, `STRUCTURED_SNIPPET`).
  * Type-specific fields: `text_asset_text` (`TEXT`), `callout_text`
    (`CALLOUT`), `structured_snippet_header` + `structured_snippet_values`
    (`STRUCTURED_SNIPPET`), `image_asset_path` (local stdio only) or base64
    `image_asset_data` + `image_asset_mime_type` (`IMAGE_PNG`, `IMAGE_JPEG`,
    `IMAGE_GIF`, up to 20 MB), `youtube_video_id`, or `sitelink_link_text` +
    `final_urls`.
  * `validate_only` (bool, optional, default `True`) and `checksum` (string,
    required when `validate_only=False`).

### 5. `assets_upload_video_asset` (`upload_video_asset`)

* **Purpose:** Uploads a local video file (`.3gp`, `.avi`, `.flv`, `.mkv`,
  `.mov`, `.mp4`, `.mpeg`, `.mpg`, `.ogg`, `.webm`, `.wmv`) to YouTube via
  the Google Ads API (local stdio mode only). Returns `video_upload_id`;
  poll `you_tube_video_upload` via `search_search` until
  `you_tube_video_upload.state = 'PROCESSED'`, then pass
  `you_tube_video_upload.video_id` to `assets_create_asset`.
* **Key Arguments:**
  * `customer_id` (string, required): 10-digit target Google Ads customer ID.
  * `video_path` (string, required): Local path to the video file.
  * `video_title` (string, required) and `video_description` (string, required).
  * `video_privacy` (string, optional), `youtube_channel_id` (string,
    optional), and `login_customer_id` (string, optional).
  * `validate_only` (bool, optional, default `True`) and `checksum` (string,
    required when `validate_only=False`).

### 6. `labels_manage_labels` (`manage_labels`)

* **Purpose:** Creates, updates, and removes account labels (including name,
  description, and hex background color).
* **Key Arguments:**
  * `customer_id` (string, required): 10-digit target Google Ads customer ID.
  * `operation` (string, required): `CREATE`, `UPDATE`, or `REMOVE`.
  * `name` (string, required for `CREATE`) and `label_id` (string, required
    for `UPDATE` and `REMOVE`).
  * `background_color` (string, optional), `description` (string, optional),
    `login_customer_id` (string, optional), `validate_only` (bool, optional,
    default `True`), and `checksum` (string, required when
    `validate_only=False`).

### 7. `labels_manage_label_associations` (`manage_label_associations`)

* **Purpose:** Creates or removes (`CREATE` / `REMOVE`; `UPDATE` unsupported)
  label associations on `CAMPAIGN`, `CUSTOMER`, `AD_GROUP`, and
  `AD_GROUP_CRITERION` resources (`AD_GROUP_AD` is unsupported).
* **Key Arguments:**
  * `customer_id` (string, required): 10-digit target Google Ads customer ID.
  * `operation` (string, required): `CREATE` or `REMOVE`.
  * `association_type` (string, required): `CAMPAIGN`, `CUSTOMER`,
    `AD_GROUP`, or `AD_GROUP_CRITERION`.
  * `resource_id` (optional for `CUSTOMER`, defaults to `customer_id`;
    composite `{ad_group_id}~{criterion_id}` for `AD_GROUP_CRITERION`),
    `label_id` (or `association_resource_name` for removals),
    `validate_only` (bool, optional, default `True`), and `checksum` (string,
    required when `validate_only=False`).

## Read-Only Mode (`tools_config.yaml`)

To enforce a strictly read-only deployment, set `labels: false` and
`assets: false` alongside enabled read namespaces in `tools_config.yaml` (or
point `GOOGLE_ADS_MCP_TOOLS_CONFIG` to that file):

```yaml
namespaces:
  customers: true
  search: true
  metadata: true
  labels: false
  assets: false
```
