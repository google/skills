# GCP IAM, Service Account Keys, GCE Lateral Movement & Audit Rejections

<!-- disableFinding(LINE_OVER_80) -->

## Table of Contents

- [1. Service Account Key Provenance & Harvesting Analysis](#1-service-account-key-provenance-harvesting-analysis): Lines 13-69
- [2. GCE Lateral Movement & Startup Script Triage](#2-gce-lateral-movement-startup-script-triage): Lines 73-87
- [3. GCP Cloud Audit Permission Denials vs. Operational Rejections](#3-gcp-cloud-audit-permission-denials-vs-operational-rejections): Lines 91-127

---

## 1. Service Account Key Provenance & Harvesting Analysis

### A. Differentiating Key Generation vs. Pre-Existing Harvesting

- **Created During Incident**: Attacker created the key via `iam.serviceAccountKeys.create`.
- **Created Months Ago**: Attacker **harvested** an existing credential from:
  1. **Terraform State**: Check GCS for `.tfstate` downloads (`storage.googleapis.com`).
  2. **Node Filesystem**: Check `/etc/kubernetes/` or `/var/lib/kubelet/` on cluster VMs.
  3. **Kubernetes Secrets**: Check `KUBERNETES_AUDIT` for secret reads.
  4. **CI/CD Secrets**: Check GitHub Actions, CircleCI, or GitLab runner configs.

### B. Identify Who Created a Key (The 4 W's)
```sql
metadata.log_type = "GCP_CLOUDAUDIT"
(
  metadata.product_event_type = "google.iam.admin.v1.CreateServiceAccountKey" or
  metadata.product_event_type = "google.iam.admin.v1.CreateServiceAccount"
)
(
  target.resource.name = /.*<KEY_ID_OR_SA_NAME>.*/ or
  security_result.detection_fields["key_id"] = "<KEY_ID>"
)
```
*Note: `CreateServiceAccountKey` is normalized to `metadata.event_type = "USER_CHANGE_PASSWORD"` in UDM.*

### C. Tracing Operations by Exported Key ID in Logs Explorer
To isolate operations authenticated specifically by a compromised user-managed key:
```text
protoPayload.authenticationInfo.serviceAccountKeyName=~"<KEY_ID>"
timestamp >= "YYYY-MM-DDTHH:MM:SSZ"
```
*Inspect `protoPayload.methodName`, `protoPayload.resourceName`, and `protoPayload.requestMetadata.callerIp`.*

### D. Unmasking Who Created a Rogue Key
```sql
metadata.log_type = "GCP_CLOUDAUDIT"
metadata.product_event_type = /.*CreateServiceAccountKey.*/
target.resource.name = /.*<SERVICE_ACCOUNT_UID_OR_NAME>.*/
```

### E. GCP IAM Enumeration (`GCPPEAS.py`) Detection & Terraform De-Noising Architecture

When authoring or tuning YARA-L rules to detect GCP IAM permission/policy enumeration (`GCPPEAS.py` / `CloudPEASS`), enforce four architectural invariants:

1. **Case-Insensitive Method Matching (`gRPC` vs. `REST`)**:
   - gRPC-backed services (Cloud Resource Manager, IAM) log PascalCase methods (`GetIamPolicy`, `TestIamPermissions`), whereas REST-backed services (Cloud Storage, Compute Engine) log camelCase (`storage.buckets.getIamPolicy`, `v1.compute.instances.testIamPermissions`). Always use `(?i)(GetIamPolicy|TestIamPermissions)$`.
2. **Retain Workload Default Service Accounts (`169.254.169.254` Token Theft)**:
   - Attackers running `GCPPEAS.py` from a compromised GCE VM, GKE pod, or Cloud Function authenticate using the default metadata server token (`*-compute@developer.gserviceaccount.com` or `*@appspot.gserviceaccount.com`). Never exclude `developer`, `appspot`, or `cloudbuild` SAs; only exclude Google-owned internal control-plane agents (`@gcp-sa-*`, `@cloudservices`, `@compute-system`, `@container-engine-robot`).
3. **Catching Chunked Permission Batching (`distinct_resource_count = 1`)**:
   - `GCPPEAS.py` tests 500+ permissions in batches of $\le 100$ against `cloudresourcemanager.projects.testIamPermissions` on a single project (`distinct_resource_count = 1`, `distinct_service_count = 1`, `total_api_calls = 6-15+`). Combine three detection paths in `condition:`:
     - **Path 1 (Breadth):** `$distinct_resource_count > 10 and $distinct_service_count >= 2` (suppresses single-page Cloud Console Web UI loads).
     - **Path 2 (Depth / Chunking):** `$total_api_calls >= 15` (catches `GCPPEAS` testing 500+ permissions against 1 project).
     - **Path 3 (SDK/CLI Burst):** `$is_sdk_or_cli = 1 and $total_api_calls >= 6` (catches Python/`gcloud` enumeration in small microservice projects with $\le 10$ resources).
4. **Terraform De-Noising & Anti-Spoofing Filter**:
   - Developers running `terraform plan`/`apply` generate large bursts of `GetIamPolicy` calls and use `terraform-provider-google` (which embeds `google-api-go-client` in `network.http.user_agent`).
   - **Behavioral Invariant:** Terraform refreshes state exclusively via `GetIamPolicy` and **NEVER calls `TestIamPermissions`**.
   - Exclude Terraform User-Agents *only* on non-`TestIamPermissions` calls in `events:`, and omit `google-api-go-client` from `$is_sdk_or_cli`. This eliminates 100% of developer Terraform false positives while still catching attackers who spoof a Terraform User-Agent during `GCPPEAS` `TestIamPermissions` sweeps.

---

## 2. GCE Lateral Movement & Startup Script Triage

```sql
metadata.log_type = "GCP_CLOUDAUDIT"
target.application = "compute.googleapis.com"
metadata.product_event_type = /setMetadata|setCommonInstanceMetadata/ nocase
(
  target.resource.attribute.labels["AddedMetadataKeys"] = "startup-script" or
  target.resource.attribute.labels["ModifiedMetadataKeys"] = "startup-script" or
  metadata.ingestion_labels["instance_metadata_key_added"] = "startup-script" or
  metadata.ingestion_labels["ModifiedMetadataKeys"] = "startup-script" or
  target.resource.attribute.labels["AddedMetadataKeys"] = "startup-script-url" or
  target.resource.attribute.labels["ModifiedMetadataKeys"] = "startup-script-url"
)
```

---

## 3. GCP Cloud Audit Permission Denials vs. Operational Rejections

### A. The `action = "BLOCK"` Operational Error Parser Trap
When an API call fails in GCP, Cloud Audit logs emit a `status.code` (numeric gRPC code). Google SecOps's `GCP_CLOUDAUDIT` parser maps ANY non-zero gRPC status to `security_result.action = "BLOCK"` and `security_result.severity = "ERROR"`.

* **Mandatory Positive Filter**: Never use negative filtering (`status_code != "5"` and `status_code != "6"`), because codes `3`, `8`, `9`, `10`, and `13` also map to `action = "BLOCK"`. Always positively filter on `(security_result.detection_fields["status_code"] = "7" or security_result.detection_fields["status_code"] = "16")` (`PERMISSION_DENIED` / `UNAUTHENTICATED`) or `(network.http.response_code = 401 or network.http.response_code = 403)`.

| gRPC Code | Name | Meaning | Common Legitimate Source | Is IAM Denial? |
|---|---|---|---|---|
| **7** | `PERMISSION_DENIED` | Caller lacks IAM permission | Unauthorized caller, privilege escalation probe | **YES (403)** |
| **16** | `UNAUTHENTICATED` | Token missing, expired, or revoked | Expired service account key, invalid OAuth token | **YES (401)** |
| **3** | `INVALID_ARGUMENT` | Request parameters invalid or service enabled at org ancestor | CircleCI/Terraform disabling inherited service | **NO** |
| **9** | `FAILED_PRECONDITION` | Resource state prevents action (e.g. dependent services active) | Disabling BigQuery while GKE/Redis are enabled | **NO** |
| **5** | `NOT_FOUND` | Targeted resource does not exist | Automation checking resource existence | **NO** |
| **6** | `ALREADY_EXISTS` | Resource already created | Idempotent Terraform apply | **NO** |
| **8** | `RESOURCE_EXHAUSTED` | Quota or rate limit exceeded | High-throughput batch processing | **NO** |

### B. High-Density UDM Hunting Selectors for GCP IAM, Compute Disk Attach & Cloud Audit

| Rule / Detection Name | MITRE ATT&CK | UDM `log_type` & Key Fields | High-Density UDM Predicates & Exclusions | Window & Multi-Path Threshold | Key Outcome / Triage Artifacts |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`GCP_IAM_Enumeration_v2`**<br>*(GCPPEAS / CloudPEASS Sweep)* | `T1069.003` | `GCP_CLOUDAUDIT`<br>`$principal_email = $e.principal.user.email_addresses` | • `re.regex($e.metadata.product_event_type, "(?i)(GetIamPolicy\|TestIamPermissions)$")`<br>• If filtering denied calls (`action = "BLOCK"`), positively require `($e.security_result.detection_fields["status_code"] = "7" or $e.security_result.detection_fields["status_code"] = "16" or $e.network.http.response_code = 401 or $e.network.http.response_code = 403)`<br>• Exclude Google internal SAs: `not re.regex($principal_email, "(?i)@(gcp-sa-[a-z0-9-]+\\.iam\|cloudservices\|compute-system\\.iam\|container-engine-robot\\.iam)\\.gserviceaccount\\.com$")`<br>• **Terraform Spoof-Resistant Filter**: `(re.regex($e.metadata.product_event_type, "(?i)TestIamPermissions$") or not re.regex($e.network.http.user_agent, "(?i)(Terraform\|terraform-provider\|Pulumi\|Config-Connector)"))` | `$principal_email over 5m`<br>• Path 1: `$distinct_resource_count > 10 and $distinct_service_count >= 2`<br>• Path 2: `$total_api_calls >= 15`<br>• Path 3: `$is_sdk_or_cli = 1 and $total_api_calls >= 6`<br>*(where `$is_sdk_or_cli = max(if(re.regex($e.network.http.user_agent, "(?i)(python\|requests\|google-api-python-client\|gcloud\|curl)"), 1, 0))`)* | • `enumerated_methods`: `array_distinct($e.metadata.product_event_type)`<br>• `targeted_services`: `array_distinct($e.target.application)`<br>• `sample_resources`: `array_distinct($e.target.resource.name)` |
| **`GCP_GCE_PersistentDiskAttach_LRO_Dedup`**<br>*(Persistent Disk Attach `v1.compute.instances.attachDisk`)* | `T1003` / `T1578` | `GCP_CLOUDAUDIT`<br>`$disk_name = re.capture(strings.coalesce($e.target.resource_ancestors.name, $e.security_result.detection_fields["resource"]), "/disks/([^/]+)$")` | • `metadata.product_event_type = "v1.compute.instances.attachDisk"`<br>• **LRO 2x Alert Deduplication**: GCE Long-Running Operations emit both `operation.first=true` and `operation.last=true`. Require `$e.additional.fields["operation_last"] != "true"` in `events:` to suppress duplicate completion alerts<br>• **Attached Disk Extraction**: Extract `/disks/<disk_name>` from `$e.target.resource_ancestors.name` or `$e.security_result.detection_fields["resource"]` | `SINGLE_EVENT` or correlated with `$enum` over `1h` by `$principal_email` | • `attached_disk`: `array_distinct($disk_name)`<br>• `target_instance`: `array_distinct($e.target.resource.name)`<br>• `operation_id`: `array_distinct($e.additional.fields["operation_id"])` |
| **`GCP_Recon_ExcessivePermissionDeniedEvents_Tuned`**<br>*(True 403/7 & 401/16 Denials)* | `T1580` | `GCP_CLOUDAUDIT`<br>`$user_id = $gcp.principal.user.userid` | • True auth/permission denials only:<br>`($gcp.security_result.detection_fields["status_code"] = "7" or $gcp.security_result.detection_fields["status_code"] = "16" or $gcp.network.http.response_code = 401 or $gcp.network.http.response_code = 403)`<br>• Exclude noisy known workload SA: `$gcp.principal.user.userid != "known-noisy-workload-sa@<project-id>.iam.gserviceaccount.com"` | `$user_id over 1h`<br>Threshold: `count($gcp.metadata.id) >= 10` | • `denied_methods`: `array_distinct($gcp.metadata.product_event_type)`<br>• `status_codes`: `array_distinct($gcp.security_result.detection_fields["status_code"])`<br>• `source_ips`: `array_distinct($gcp.principal.ip)` |
| **`GCP_SCC_IPForwardingOnNonVPNServer`**<br>*(SCC `IP_FORWARDING_ENABLED` Rogue VM vs. WireGuard `wg`)* | `T1572` | `GCP_SECURITYCENTER_MISCONFIGURATION` <br>`$vm_name = strings.coalesce($e.target.resource.attribute.labels["resource_displayName"], $e.target.asset.attribute.labels["assetDisplayName"], re.capture($e.target.resource.name, "/instances/([^/]+)$"), re.capture($e.about.url, "/instances/([^?/#]+)"))` | • `metadata.product_event_type = "IP_FORWARDING_ENABLED"`<br>• Active & unmuted only: `$e.security_result.alert_state = "ALERTING"` AND `$e.security_result.detection_fields["state"] = "ACTIVE"` AND `$e.security_result.detection_fields["mute"] != "MUTED"`<br>• Exclude VPN, WireGuard (`wg`), NAT bastion, and pfSense routers: `not re.regex($vm_name, "(?i)(?:^\|[-_])(?:vpn\|vpngw\|wg\|wireguard\|nat[-_]?bastion\|nat[-_]?gw\|pfsense)(?:[-_]\|$)")` | `SINGLE_EVENT` (`< 0.5 min` Ingest-to-Detect)<br>• Dynamic Score (`40` base): `+30` if `folder_resourceFolderDisplayName != "Dev"` and `not re.regex(target.resource_ancestors.name, "(?i)-dev$")`; `+15` if `re.regex($vm_name, "(?i)^instance-[0-9]{8}-[0-9]{6}$")` *(wrapped in `max(if(...))`)* | • `instance_name`: `array_distinct($vm_name)`<br>• `gcp_project_id`: `array_distinct(strings.coalesce($e.target.resource_ancestors.name, $e.target.resource.attribute.labels["resource_projectDisplayName"]))`<br>• `gcp_folder_name`: `array_distinct(strings.coalesce($e.src.resource_ancestors.attribute.labels["folder_resourceFolderDisplayName"], "Root_Organization"))`<br>• `gcp_zone`: `$e.target.location.name` *(scalar)* |
| **`GCP_GCE_Access_IAPTunnelUse`**<br>*(IAP TCP Tunnel `AuthorizeUser` `SESSION_START`)* | `T1078.004` | `GCP_CLOUDAUDIT`<br>`$user_email = $e.principal.user.email_addresses`<br>`$project = $e.target.cloud.project.name` | • `$e.metadata.product_event_type = "AuthorizeUser"` and `$e.principal.user.attribute.permissions.name = "iap.tunnelInstances.accessViaIAP"` and `$e.security_result.action = "ALLOW"`<br>• **3-Phase LRO Deduplication (`53.5%` reduction)**: Exclude `SESSION_END` (`$e.network.http.user_agent != "(none supplied)"`) and `SESSION_CONTINUE` (`$e.extracted.fields["protoPayload.metadata.iap_tcp_session_info.phase"] != "SESSION_CONTINUE"`) | `$user_email, $project over 30m`<br>• `risk_score = 10` | • `target_ports`: `array_distinct($e.extracted.fields["protoPayload.requestMetadata.destinationAttributes.port"])` *(`22`/`3389` vs `30443`/`32022`/`443`)*<br>• `target_ips`: `array_distinct($e.target.ip)`<br>• `source_ips`: `array_distinct($e.principal.ip)`<br>• `user_agents`: `array_distinct($e.network.http.user_agent)` |
| **`GCP_LateralMovement_CrossProjectActivity`**<br>*(Cross-Project Admin / SSH / IAP vs. `%users_to_projects`)* | `T1078.004`, `T1098.004` | `GCP_CLOUDAUDIT`<br>`$userid = strings.to_lower($e.principal.user.email_addresses)`<br>`$accessed_project = strings.coalesce(re.capture($e.target.resource.name, "^projects/([^/]+)"), $e.target.cloud.project.name)` | • `($e.metadata.product_event_type = "google.iam.admin.v1.CreateServiceAccount" or $e.metadata.product_event_type = "AuthorizeUser" or $e.metadata.product_event_type = "v1.compute.projects.setCommonInstanceMetadata" or $e.metadata.product_event_type = "v1.compute.instances.setMetadata")` and `$e.security_result.action = "ALLOW"`<br>• **GCE LRO & IAP `SESSION_END` Dedup**: `$e.additional.fields["operation_last"] != "true"` and `$e.network.http.user_agent != "(none supplied)"`<br>• **Numeric Project Number Fix on `setCommonInstanceMetadata`**: Extract human-readable project slug from `$e.target.resource.name` (`^projects/([^/]+)`) before falling back to `$e.target.cloud.project.name`, and verify `not re.regex($accessed_project, "^\\d+$")`<br>• Join `%users_to_projects.userid = $userid` and check `not re.regex(%users_to_projects.projects, $accessed_project)` | `$userid, $accessed_project over 30m`<br>• `risk_score`: `50` for `CreateServiceAccount` / `setCommonInstanceMetadata` / `setMetadata`, `25` for `AuthorizeUser` | • `actions`: `array_distinct($e.metadata.product_event_type)`<br>• `target_resources`: `array_distinct($e.target.resource.name)`<br>• `source_ips`: `array_distinct($e.principal.ip)` |
| **`GCP_IAM_PAMRequestApproved`**<br>*(Privileged Access Manager `ApproveGrant` + `PAMActivateGrant`)* | `T1078.004` | `GCP_CLOUDAUDIT`<br>`$grant_id = re.capture(..., "/grants/([^/]+)$")` | • `$app`: `$app.target.application = "privilegedaccessmanager.googleapis.com"` and `strings.ends_with($app.metadata.product_event_type, ".ApproveGrant")` and `$app.security_result.action = "ALLOW"`<br>• `$act`: `$act.target.application = "privilegedaccessmanager.googleapis.com"` and `$act.metadata.product_event_type = "PAMActivateGrant"` and **`$act.target.resource.attribute.labels["state"] = "ACTIVE"`** *(eliminates `18.75%` `ACTIVATION_FAILED` errors when `org-admin` is requested on a project)* | `$grant_id over 5m`<br>• `risk_score = 75` if `strings.to_lower(re.capture($act.principal.user.userid, "^([^@]+)")) = strings.to_lower(re.capture($app.principal.user.userid, "^([^@]+)"))` *(cross-domain dual-account self-approval)*, else `25` | • `requester`: `array_distinct($act.principal.user.userid)`<br>• `approver`: `array_distinct($app.principal.user.userid)`<br>• `entitlement`: `array_distinct(re.capture($act.target.resource.name, "/entitlements/([^/]+)/grants/"))`<br>• `target_resource`: `array_distinct($act.target.resource.attribute.labels["resource"])`<br>• `requested_duration`: `array_distinct($act.target.resource.attribute.labels["requestedDuration"])`<br>• `requested_roles`: `array_distinct($act.target.resource.attribute.roles.name)` |
| **`GCP_CloudAudit_LoggingSink_And_WIP_Terraform_Tuned`**<br>*(Logging Sink & Workload Identity Pool Mutation vs. Ephemeral Rebuilds)* | `T1562.008`, `T1098` | `GCP_CLOUDAUDIT`<br>`$principal_email = $e.principal.user.email_addresses`<br>`$project = $e.target.cloud.project.name` | • **Logging Sink Mutation (`ConfigSink_Mutation`)**: `re.regex($e.metadata.product_event_type, "(?i)ConfigServiceV2\\.(DeleteSink\|UpdateSink\|CreateSink)$")` and exclude baseline log-router sinks on Terraform rebuilds: `not (re.regex($e.target.resource.name, "(?i)/sinks/(?:bindplane\|log_router)_[a-z0-9_]+_logs$") and re.regex($e.network.http.user_agent, "(?i)terraform"))`<br>• **Workload Identity Pool Mutation (`IAM_Federation_Change`)**: `re.regex($e.metadata.product_event_type, "(?i)WorkloadIdentityPools\\.(Delete\|Update\|Undelete)")` and exclude ephemeral Kubernetes pools on Terraform rebuilds: `not (re.regex($e.target.resource.name, "(?i)/workloadIdentityPools/[a-z0-9-]+-k8s-wi-pool-[a-z0-9]+$") and re.regex($e.network.http.user_agent, "(?i)terraform"))` | `$principal_email, $project over 15m`<br>• Cap resource-count risk bonus (or require `$total_events <= 5`) so multi-sink `terraform destroy` runs do not inflate composite cloud account detections to `risk_score = 85` | • `mutated_sinks_or_pools`: `array_distinct($e.target.resource.name)`<br>• `methods`: `array_distinct($e.metadata.product_event_type)`<br>• `user_agents`: `array_distinct($e.network.http.user_agent)` |

### C. Sandbox & Ephemeral CI Terraform Rebuild Exclusions (`sandbox-dev`)
Automated Terraform teardown/rebuild cycles (`terraform destroy` followed by `terraform apply`) in `sandbox-dev` or ephemeral CI projects delete and recreate:

1. **Baseline Cloud Logging Router Sinks**: `projects/<proj>/sinks/(bindplane|log_router)_<source>_logs`.
2. **Ephemeral Kubernetes Workload Identity Pools**: `projects/<proj>/locations/global/workloadIdentityPools/<cluster>-k8s-wi-pool-<suffix>`.

Without exclusions, deleting baseline log sinks emits bulk `DeleteSink` alerts and inflates composite cloud account detections. Exclude baseline sink and Workload Identity Pool naming patterns when `network.http.user_agent` matches `terraform` and cap multi-resource risk bonuses.
