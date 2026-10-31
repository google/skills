# Multi-Tenant MSSP Disambiguation & CMDB (Snipe-IT) Entity Enrichment

<!-- disableFinding(LINE_OVER_80) -->

## Table of Contents

- [1. ITAM & CMDB Entity Context Enrichment (Snipe-IT)](#1-itam-cmdb-entity-context-enrichment-snipe-it): Lines 14-20
- [2. MSSP Multi-Tenancy & Overlapping RFC 1918 Disambiguation in GCP](#2-mssp-multi-tenancy-overlapping-rfc-1918-disambiguation-in-gcp): Lines 24-92
- [3. Google SecOps Data RBAC & Terraform Detection-as-Code (`google-beta` Provider)](#3-google-secops-data-rbac-terraform-detection-as-code-google-beta-provider): Lines 96-120
- [4. Automated SOAR Alert-to-Case Entity Overlap Clustering & `cases:merge` REST Workflow](#4-automated-soar-alert-to-case-entity-overlap-clustering-casesmerge-rest-workflow): Lines 124-165

---

## 1. ITAM & CMDB Entity Context Enrichment (Snipe-IT)

### A. How Entity Context Joins Work

* **Ingestion Type**: `log_type = "SNIPE_IT"` maps to `event.idm.entity.entity` (UDM Entity Graph), not event telemetry.
* **UI & Alert Enrichment (Automatic)**: SecOps automatically stitches Snipe-IT hardware specs, serial number, owner, and office location onto every alert and asset/user timeline view in the console.
* **Rule Engine Evaluation (Explicit)**: To trigger or elevate alerts based on asset status or classification, explicitly join `$entity.graph.entity...` in the YARA-L rule.

---

## 2. MSSP Multi-Tenancy & Overlapping RFC 1918 Disambiguation in GCP

In multi-tenant MSSP architectures ("Mothership" single-instance model) or complex multi-VPC GCP environments, multiple projects share overlapping RFC 1918 private IP spaces (e.g., `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`). Google SecOps disambiguates assets and prevents false cross-tenant correlation using **Asset Namespaces**, **Cloud Asset Inventory (CAI)**, and **UDM Entity Graphs**.

### A. Asset Identity Primitive
Google SecOps represents asset identity as a composite key:
`Asset Identity = (IP_or_Hostname, Asset_Namespace)`

Relevant UDM Fields:

- `principal.namespace`
- `target.namespace`
- `src.namespace` / `intermediary.namespace`
- `entity.namespace` / `entity.asset.attribute.labels`

### B. Automatic Parser Extraction vs. Ingestion Tagging

1. **Automatic In-Parser Extraction (`GCP_VPC_FLOW`)**:
   Native GCP VPC Flow log parsers automatically extract source/dest VPC and project IDs from the payload:
   ```c
   principal.namespace = "%{jsonPayload.src_vpc.project_id}:%{jsonPayload.src_vpc.vpc_name}"
   target.namespace    = "%{jsonPayload.dest_vpc.project_id}:%{jsonPayload.dest_vpc.vpc_name}"
   ```
   *Result:* Two identical private IPs (e.g. `10.128.0.5`) in different projects resolve to distinct namespaces: `tenant-a-prod:vpc-main` vs. `tenant-b-prod:vpc-main`.

2. **Ingestion-Level Feed & Forwarder Namespacing**:
   For telemetry lacking VPC headers (e.g., OS Syslog, Windows Event Logs, internal Zeek/Suricata sensors, host EDR):
   - **Feed Management**: Explicitly set the **Asset Namespace** on the GCS / PubSub feed pulling from each tenant's log sink (e.g. `tenant-a-gcp`).
   - **SecOps Linux Forwarder / BindPlane**:
     ```yaml
     metadata:
       namespace: "tenant-a-network"
     collectors:
       - syslog:
           common:
             metadata:
               namespace: "tenant-a-vpc-prod"
     ```

### C. Entity Graph Aliasing via Cloud Asset Inventory (CAI)
Continuous ingestion of `GCP_COMPUTE_CONTEXT` and `GCP_RESOURCE_MANAGER_CONTEXT` maps:

- `networkInterfaces[].networkIP` -> `entity.asset.ip`
- Subnetwork / Network URIs (`projects/<proj>/global/networks/<vpc>`) -> VPC network scope
- Canonical Resource Name (`//compute.googleapis.com/projects/<proj>/zones/<zone>/instances/<inst>`) -> `entity.asset.asset_id`

When an event arrives with `principal.ip = 10.128.0.5` in namespace `tenant-a:vpc-1`, the entity graph resolves it exclusively to Tenant A's Compute Engine instance, hostname, and IAM service account.

### D. High-Density UDM Hunting Selectors for CMDB & Multi-Tenant Rules

| Rule / Detection Name | MITRE ATT&CK | UDM `log_type` & Entity Joins | High-Density UDM Predicates & Partitioning | Window & Threshold | Key Outcome / Triage Artifacts |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`Activity_From_Stolen_Or_Decommissioned_Asset`**<br>*(Snipe-IT CMDB Entity Graph Join + MSSP RFC 1918 Composite Key)* | `T1078` | Any Event (`USER_LOGIN`, `NETWORK_CONNECTION`) joined with `SNIPE_IT` (`$entity.graph.entity`) | • `$src_ip = $e.principal.ip` and `$src_namespace = $e.principal.namespace` (`net.ip_in_range_cidr($e.principal.ip, "10.0.0.0/8")`)<br>• `$hostname = $e.principal.hostname` joined with `$entity.graph.entity.hostname = $hostname` (`$entity.graph.metadata.product_name = "SNIPE_IT"`, `$entity.graph.metadata.entity_type = "ASSET"`)<br>• `$status = $entity.graph.entity.asset.attribute.labels["status_label"]`<br>• `re.regex($status, "^(Stolen\|Lost\|Archived\|Decommissioned\|Pending Disposal)$") nocase`<br>• **Mandatory Composite Partitioning**: Always include both `$src_ip` and `$src_namespace` in `match:` (`$src_ip, $src_namespace, $hostname over 5m`) - never drop `$src_ip` when joining on `$hostname` | `$src_ip, $src_namespace, $hostname over 5m`<br>(`severity = Critical`) | • `asset_owner`: `array_distinct($entity.graph.entity.user.user_display_name)`<br>• `hardware_serial`: `array_distinct($entity.graph.entity.asset.hardware.serial_number)`<br>• `current_status`: `array_distinct($status)` |
| **`MultiTenant_RFC1918_Lateral_Reconnaissance`**<br>*(Composite IP + Namespace Sliding Window)* | `T1046` | `GCP_VPC_FLOW` / `ZEEK` / `SURICATA`<br>`event_type = "NETWORK_CONNECTION"` | • `$e.principal.ip = $src_ip` and `$e.principal.namespace = $src_namespace`<br>• `net.ip_in_range_cidr($e.target.ip, "10.0.0.0/8")`<br>• **Composite Partitioning**: Partition `match:` by both `$src_ip` and `$src_namespace` to prevent cross-tenant RFC 1918 false joins | `$src_ip, $src_namespace over 10m`<br>Threshold: `count($e.metadata.id) > 50` | • `tenant_namespace`: `$src_namespace`<br>• `distinct_targets`: `count_distinct($e.target.ip)` |

### E. UDM Threat Hunting Query Patterns

- **Investigate Activity for a Specific Tenant's Overlapping IP**:
  ```sql
  metadata.event_type = "NETWORK_CONNECTION"
  principal.ip = "10.128.0.5"
  principal.namespace = "tenant-a-prod:vpc-main"
  ```

- **Hunt for Assets Missing Namespace Tagging (Untagged Assets)**:
  ```sql
  principal.ip = /^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)/
  (principal.namespace = "" or principal.namespace = "untagged")
  ```

---

## 3. Google SecOps Data RBAC & Terraform Detection-as-Code (`google-beta` Provider)

When managing multi-tenant MSSP / sub-agency access boundaries, Data Tables, Reference Lists, and YARA-L 2.0 rule deployments as code (`GoogleCloudPlatform/secops-toolkit` `modules/secops-*`), use the `google-beta` Terraform resources below:

### A. Data RBAC (`google_chronicle_data_access_label` & `google_chronicle_data_access_scope`)

1. **Custom Data Access Labels (`google_chronicle_data_access_label`)**:
   * Define fine-grained UDM predicate labels via `udm_query` (for example, `principal.hostname = "win-finance-01"` or `metadata.log_type = "GCP_CLOUDAUDIT"`).
2. **Data Access Scopes (`google_chronicle_data_access_scope`)**:
   * Bind principals to scopes using `allowed_data_access_labels` and `denied_data_access_labels` across 4 selector types:
     * `log_type` (e.g., `"GCP_CLOUDAUDIT"`, `"WINEVTLOG"`)
     * `data_access_label` (referencing a `google_chronicle_data_access_label` ID)
     * `asset_namespace` (e.g., `"tenant-a-prod:vpc-main"`)
     * `ingestion_label` (`ingestion_label_key` + `ingestion_label_value`)
   * **Deny-Only Scope Invariant (`allow_all`)**: When a scope defines only `denied_data_access_labels` (with an empty `allowed_data_access_labels` list), set `allow_all = true` (`allow_all = length(denied_data_access_labels) != 0 and length(allowed_data_access_labels) == 0`).

### B. Terraform Data Tables, Reference Lists & YARA-L Rule Deployments

1. **Data Tables (`google_chronicle_data_table` & `google_chronicle_data_table_row`)**:
   * Define schema columns via `column_info` blocks (`column_index`, `original_column`, `column_type` [`STRING`, `CIDR`, `REGEX`], `key_column = true|false`, `mapped_column_path` for UDM entity mapping, and `repeated_values = true|false`).
   * Populate rows via `google_chronicle_data_table_row` (`values = [...]`, optional `row_time_to_live = "24h"` / `"720h"`).
2. **Reference Lists (`google_chronicle_reference_list`)**:
   * Set `syntax_type` to `REFERENCE_LIST_SYNTAX_TYPE_PLAIN_TEXT_STRING`, `REFERENCE_LIST_SYNTAX_TYPE_REGEX`, or `REFERENCE_LIST_SYNTAX_TYPE_CIDR` with `entries { value = "..." }`.
3. **YARA-L Rules & Deployment State (`google_chronicle_rule` & `google_chronicle_rule_deployment`)**:
   * Provision rule text via `google_chronicle_rule` (`text = file(...)`, `deletion_policy = "FORCE"`) and decouple runtime execution state via `google_chronicle_rule_deployment` (`enabled = true`, `alerting = true`, `archived = false`, `run_frequency = "LIVE"` | `"HOURLY"` | `"DAILY"`).

---

## 4. Automated SOAR Alert-to-Case Entity Overlap Clustering & `cases:merge` REST Workflow

When detections generate related single-alert cases across overlapping assets, users, or IPs, use the Google SecOps `v1beta` Case Management REST API (`https://{region}-chronicle.googleapis.com/v1beta/projects/{project_id}/locations/{region}/instances/{instance_id}`) to extract alert entities, cluster connected components via Union-Find, and merge related cases into the oldest anchor case.

### A. Step-by-Step Entity Extraction & Noise Token Denylist

1. **Fetch Open Cases (`GET /v1beta/{parent}/cases`)**:
   * Query `GET /v1beta/{parent}/cases?filter=status="OPENED"&pageSize=100` (paginating via `nextPageToken`).
   * Record each case's numeric `id`, `displayName`, `priority`, `stage`, `type` (`"TEST"` vs. `"EXTERNAL"` / unset), and `createTime`.
2. **Fetch Case Alerts & Extract `involvedEntities` (`GET /v1beta/{parent}/cases/{case_id}/caseAlerts/{case_alert_id}/involvedEntities`)**:
   * For each open case, list `cases/{case_id}/caseAlerts`, then call `GET /v1beta/{parent}/cases/{case_id}/caseAlerts/{case_alert_id}/involvedEntities` (or inspect `involvedRelations[]` on the `CaseAlert` resource, where `from` and `to` `EntityKey` objects expose `.type` and `.identifier`).
   * Extract every entity where `type` belongs to the **6 High-Signal Correlation Entity Types**:
     * **`ADDRESS`** (IPv4/IPv6), **`USERUNIQNAME`** (Users/UPNs/SAs), **`HOSTNAME`** (Hosts/FQDNs), **`DESTINATIONURL`** (URLs), **`DOMAIN`** (Domains), **`FILEHASH`** (MD5/SHA1/SHA256).
3. **Mandatory Entity Noise Denylist (Preventing Super-Cluster Explosion)**:
   * **Never** cluster cases on generic metadata or status entity types: exclude `type` in `{"GENERIC", "THREATSIGNATURE", "PROCESS"}` (unless process path is host-qualified).
   * Normalize extracted `identifier` values (`identifier.strip().upper()`) and **discard any entity whose normalized identifier is in the Noise Token Denylist**:
     `{"OUTCOME", "UNKNOWN", "TRUE", "FALSE", "NONE", "NULL", "N/A", "LOCALHOST", "127.0.0.1", "0.0.0.0", "::1", "SYSTEM", "LOCAL SERVICE", "NETWORK SERVICE", "ANONYMOUS LOGON", "-"}` (or identifiers shorter than 3 characters).

### B. Union-Find Connected Components & Mandatory `TEST` vs. Production Guard

1. **`TEST` vs. Production Separation Invariant (Pre-Merge Guard)**:
   * Never merge `TEST` cases with production (`EXTERNAL`) cases; Before adding an edge `(case_A, case_B)` to the Union-Find graph, enforce:
     `is_test(case_A) == is_test(case_B)` where `is_test(c) == (c.type == "TEST")`
2. **Union-Find Clustering & Anchor Case Selection**:
   * Partition open cases into two disjoint pools (`TEST` cases vs. non-`TEST` cases).
   * Within each pool, build an inverted index `entity_key = (type, identifier.lower()) -> [case_id, ...]`.
   * For every `entity_key` shared by `2 <= k <= max_fanout` cases (default `max_fanout = 25` to avoid merging fleet-wide proxy/DC IPs), union their connected components (`uf.union(case_ids[0], cid)`).
   * For each resulting connected component with `>= 2` cases, sort member cases by `createTime` ascending (tie-breaking by lowest numeric `int(case.id)`) and select the **oldest case** as the target anchor (`caseToMergeWith`).

### C. Executing `POST /v1beta/{parent}/cases:merge` (Dry-Run First)

1. **Dry-Run Verification Table**: Present proposed merge clusters (`Anchor Case ID`, `Merged Case IDs`, `Case Type [TEST/PROD]`, `Shared Entity Keys`) for dry-run confirmation before live execution.
2. **Merge API Payload (`POST /v1beta/{parent}/cases:merge`)**:
   ```json
   {
     "casesIds": [1042, 1045, 1049],
     "caseToMergeWith": 1042
   }
   ```
   * **`casesIds`** (`array<int64>`): All numeric case IDs in the connected component (including `caseToMergeWith`).
   * **`caseToMergeWith`** (`int64`): The numeric ID of the oldest anchor case that absorbs the alerts, entities, and timeline comments of the other cases.
   * **Response Handling**: Check `response.isRequestValid`, `response.newCaseId`, and `response.errors[]` (`MergeCasesResponse`) to verify zero partial failures.
