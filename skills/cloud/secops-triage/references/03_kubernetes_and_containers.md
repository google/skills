# Kubernetes Control Plane, Containers, Artifact Registry & Port-Forward Forensics

<!-- disableFinding(LINE_OVER_80) -->

## Table of Contents

- [1. Artifact Registry & Container Supply Chain Triage](#1-artifact-registry-container-supply-chain-triage): Lines 15-44
- [2. Kubernetes Control Plane, Registry & CloudFox Hunting Selectors](#2-kubernetes-control-plane-registry-cloudfox-hunting-selectors): Lines 48-69
- [3. Unmasking Obfuscated Principals in GCS Data Access Audit Logs](#3-unmasking-obfuscated-principals-in-gcs-data-access-audit-logs): Lines 73-89
- [4. Multi-Log Correlation Runbook: Overcoming the Port-Forward Protocol Blind Spot](#4-multi-log-correlation-runbook-overcoming-the-port-forward-protocol-blind-spot): Lines 93-141
- [5. Custom JSON Container Logs Routed to Unparsed `GENERIC_EVENT` Feeds](#5-custom-json-container-logs-routed-to-unparsed-generic_event-feeds): Lines 145-159

---

## 1. Artifact Registry & Container Supply Chain Triage

### A. Cloud Logging & Audit Caveats

* **Data Access Logs Disabled by Default**: Image layer uploads (`docker push`, `artifactregistry.repositories.uploadArtifacts`) generate `DATA_WRITE` events under Data Access audit logs. In GCP, Data Access logs are disabled by default. If not explicitly enabled, the push event itself will not appear in `GCP_CLOUDAUDIT`.
* **Resource-Level IAM Policy Grants**: Container write roles (`roles/artifactregistry.writer`, `roles/storage.objectAdmin`, `roles/storage.objectCreator`) are frequently bound directly at the repository resource (`//artifactregistry.googleapis.com/projects/<PROJECT>/locations/<LOC>/repositories/<REPO>`) rather than project IAM. Project-level queries (`gcloud projects get-iam-policy`) will miss these permissions. Always check resource-level policies or query the principal's effective permissions.

### B. UDM Query for Artifact Staging and Modification
```sql
metadata.log_type = "GCP_CLOUDAUDIT"
target.application = "artifactregistry.googleapis.com"
(
  principal.user.userid = "<SA_EMAIL>" or
  principal.ip = "<SUSPICIOUS_IP>"
)
(
  metadata.product_event_type = /.*(upload|create|update|put|tag).*/ nocase or
  principal.user.attribute.permissions.name = /.*(uploadArtifacts|files\.upload|tags\.update|tags\.create).*/
)
```

### C. Hunting for Malicious Image Pulls or Manifest Reads
```sql
metadata.log_type = "GCP_CLOUDAUDIT"
target.application = "artifactregistry.googleapis.com"
(
  metadata.product_event_type = /.*(GetDockerImage|Download|GetVersion).*/ or
  target.resource.name = /.*<IMAGE_NAME_OR_DIGEST>.*/
)
```

---

## 2. Kubernetes Control Plane, Registry & CloudFox Hunting Selectors

### A. Tuning ServiceAccount Persistence vs. In-Cluster Operators
To prevent alert storms from operators (e.g. `strimzi-cluster-operator`, ingress controllers, Helm):

1. **Filter Automated Operators**: `not strings.contains($e.network.http.user_agent, "operator")` and `not strings.starts_with($e.principal.user.user_display_name, "system:serviceaccount:")`.
2. **Elevate Human / External Actors**: Assign higher risk scores to `system:admin`, non-serviceaccount UIDs, or connections from Google Cloud IAP (`35.235.240.0/20`).
3. **Account for Query Strings**: Regex on endpoint URLs must use `(?:\?.*)?$` to avoid dropping requests with `?fieldManager=...`.

### B. High-Density UDM Hunting Selectors (`KUBERNETES_AUDIT` & `GCP_CLOUDAUDIT`)

| Rule / Detection Name | MITRE ATT&CK | UDM `log_type` & Target | High-Density UDM Predicates & Exclusions | Window & Scoring Logic | Key Outcome / Triage Artifacts |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`K8s_Container_Exfiltration_Kubectl_Cp`**<br>*(Container `tar cf -` Exfiltration)* | `T1567`, `T1059` | `KUBERNETES_AUDIT` | • `$e.target.url = /.*\/exec\?.*command=tar.*/`<br>• `$e.network.http.response_code = 101` *(SPDY/WebSocket upgrade)* | Single Event<br>(`severity = Critical`) | • `target_pod`: `$e.target.resource.name`<br>• `is_iap_tunneled`: `if(re.regex($e.principal.ip, "^35\\.235\\.(?:24[0-9]\|25[0-5])\\."), "TRUE", "FALSE")` |
| **`K8s_Interactive_Root_Shell_Ingress`**<br>*(Interactive Container Shell)* | `T1059.004` | `KUBERNETES_AUDIT` | • `$e.target.url = /.*\/exec\?.*command=%2Fbin%2F(bash\|sh).*/`<br>• `$e.target.url = /.*stdin=true&stdout=true&tty=true.*/`<br>• `$e.network.http.response_code = 101` | Single Event<br>(`severity = High`) | • `actor_user`: `$e.principal.user.userid`<br>• `request_uri`: `$e.target.url` |
| **`K8s_Namespace_Secrets_Enumeration`**<br>*(Bulk Namespace Secrets `LIST`)* | `T1552.007` | `KUBERNETES_AUDIT` | • `$e.network.http.method = "LIST"`<br>• `$e.target.url = /.*\/api\/v1\/namespaces\/[^\/]+\/secrets(?:\?limit=\d+)?/`<br>• `$e.network.http.response_code = 200` | Single Event<br>(`severity = High`) | • `actor_user`: `$e.principal.user.userid`<br>• `namespace`: `$e.target.namespace` |
| **`K8s_PrivEsc_BindClusterAdmin`**<br>*(RoleBinding / ClusterRoleBinding to `cluster-admin`)* | `T1098` | `KUBERNETES_AUDIT` | • `($e.target.url = /.*\/apis\/rbac\.authorization\.k8s\.io\/v1\/(clusterrolebindings\|rolebindings).*/ or $e.target.resource.resource_subtype = /^(clusterrolebindings\|rolebindings)$/)`<br>• `$e.network.http.method = /^(POST\|PUT\|PATCH\|CREATE)$/` and `$e.metadata.description = "ResponseComplete"` and `$e.network.http.response_code >= 200` and `$e.network.http.response_code <= 299` and `$e.security_result.action = "ALLOW"`<br>• Unmapped `roleRef.name` extracted from `extracted.fields["textPayload"]` (`re.regex($e.extracted.fields["textPayload"], "\"roleRef\":\\s*\\{[^}]*\"name\":\\s*\"cluster-admin\"")`) or `$e.target.url`<br>• Exclude system controllers: `not strings.starts_with($e.principal.user.userid, "system:serviceaccount:kube-system:")` and `not strings.starts_with($e.principal.user.userid, "system:kube-controller-manager")` | Single Event<br>• `risk_score`: `85` | • `actor_user`: `strings.coalesce($e.principal.user.userid, $e.principal.user.user_display_name)`<br>• `binding_name`: `$e.target.resource.name`<br>• `is_iap_tunneled` |
| **`K8s_Etcd_Tampering_And_Exfiltration`**<br>*(Interactive `etcdctl` Pod Exec)* | `T1552` | `KUBERNETES_AUDIT` | • `($e.target.url = /.*\/pods\/etcd[^\/]*\/exec.*/ or $e.target.resource.name = /pods\/[^\/]+\/etcd/)`<br>• `($e.target.url = /.*[\?&]command=etcdctl(&\|$)/ or $e.extracted.fields["textPayload"] = /command=etcdctl/)`<br>• Exclude automated control-plane `etcdctl` health probes (`endpoint health`, `endpoint status`, `member list`, `alarm list`) unless chained with state-mutating/dump subcommands (`get`, `put`, `del`, `snapshot`, `role`, `user`, `auth`, `member`, `make-mirror`) | Single Event<br>• `risk_score`: `if(re.regex($e.target.url, "[\?&]command=(snapshot\|del\|put)(&\|$)"), 95, 80)` | • `threat_intent`: `"CRITICAL_EXFILTRATION_OR_TAMPERING"` vs `"CONTROL_PLANE_RECONNAISSANCE"`<br>• `target_pod`: `$e.target.resource.name` |
| **`GCP_New_Container_Image_Added`**<br>*(Real-Time Image Push to Artifact Registry / GCR)* | `T1610` | `GCP_CLOUDAUDIT` | • **Vector 1 (Artifact Registry)**: `$e.target.application = "artifactregistry.googleapis.com"` and `re.regex($e.metadata.product_event_type, "(?i)ArtifactRegistry\\.(CreateTag\|UploadArtifact\|DockerPush)")`<br>• **Vector 2 (Legacy GCR)**: `$e.target.application = "storage.googleapis.com"` and `$e.metadata.product_event_type = "storage.objects.create"` and `re.regex($e.target.resource.name, "artifacts\\.[^\\/]+\\.appspot\\.com\\/containers\\/images\\/sha256:")`<br>• Exclude internal service agents: `not re.regex($e.principal.user.email_addresses, ".*@(gcp-sa-.*\|.*-robot.*)\\.iam\\.gserviceaccount\\.com$")` | Single Event<br>(`risk_score = 60`) | • `uploader`: `$e.principal.user.email_addresses`<br>• `uploaded_resource`: `$e.target.resource.name`<br>• `user_agent`: `$e.network.http.user_agent` |
| **`Suspicious_MultiService_Cloud_Enumeration_GoSDK`**<br>*(CloudFox Multi-Threaded Go SDK Sweep)* | `T1580`, `T1526` | `GCP_CLOUDAUDIT`<br>`$principal_user = $e.principal.user.email_addresses` | • `re.regex($e.network.http.user_agent, "(?i)(google-api-go-client\|Go-http-client)")`<br>• Read-only enumeration methods: `re.regex($e.metadata.product_event_type, "(?i)\\.(get\|list\|describe\|getIamPolicy)$")`<br>• Exclude Google service agents (`@gcp-sa-*`, `*-robot*`, `@cloudservices.gserviceaccount.com`) | `$principal_user over 5m`<br>Threshold: `count_distinct($e.metadata.product_event_type) >= 10` | • `queried_methods`: `array_distinct($e.metadata.product_event_type)`<br>• `targeted_projects`: `array_distinct($e.target.resource.name)` |
| **`k8s_Pod_PortForward_Access`**<br>*(Interactive `kubectl port-forward` Tunnel)* | `T1090` | `KUBERNETES_AUDIT`<br>`$user = strings.to_lower($e.principal.user.user_display_name)`<br>`$namespace = $e.additional.fields["objectRef_namespace"]`<br>`$pod = $e.additional.fields["objectRef_name"]` | • `$e.metadata.description = "ResponseStarted"` and `$e.network.http.response_code = 101` and `$e.security_result.action = "ALLOW"` *(eliminates 66.7% stage duplicates and >5m `ResponseComplete` close duplicates)*<br>• `$e.target.resource.resource_subtype = "pods"` and `strings.contains(strings.to_lower($e.target.url), "/portforward")`<br>• Exclude control-plane loopback `Go-http-client/1.1` (`$user = "system:admin"` from `127.0.0.1`/`::1` with `strings.starts_with($e.network.http.user_agent, "Go-http-client/")`) and CI smoke-test automation (`$user = "ci-deployer"` on `^(ingress-health\|metrics-probe\|ci-smoke-test)-`) | `$user, $namespace over 30m`<br>*(never group by `$audit_id` or use `re.replace()` pod-hash regexes on `/portforward`)*<br>• `risk_score = 95` if `$user` starts with `system:node:` or `system:serviceaccount:kube-system:`<br>• `25` for observability pods, else `60` | • `target_pods`: `array_distinct($pod)` *(`$e.target.resource.name` is NULL on `/portforward`)*<br>• `target_namespace`: `array_distinct($namespace)`<br>• `via_iap_proxy`: `max(if(net.ip_in_range_cidr($e.principal.ip, "35.235.240.0/20"), 1, 0))` |
| **`k8s_Exec_NonstandardPodScheduled`**<br>*(Unapproved Pod `/binding` & Naked Pod Execution)* | `T1610` | `KUBERNETES_AUDIT`<br>`$cluster, $namespace, $workload` | • `($e.network.http.method = "CREATE" or $e.network.http.method = "POST")` and `$e.metadata.description = "ResponseComplete"` and `$e.network.http.response_code >= 200` and `$e.network.http.response_code <= 299` and `$e.security_result.action = "ALLOW"`<br>• `re.regex($e.target.url, "/api/v1/namespaces/[^/]+/pods/[^/]+/binding$")`<br>• Extract pod & strip suffix: `$pod_name = strings.coalesce(re.capture($e.target.url, "/api/v1/namespaces/[^/]+/pods/([^/]+)/binding$"), re.capture($e.target.resource.name, "pods/[^/]+/([^/]+)$"), $e.target.resource.name)` and `$workload = re.replace($pod_name, "-(?:[a-f0-9]{8,10}-[a-z0-9]{5}\|[a-z0-9]{5}\|[0-9]+)$", "")`<br>• `not $workload in %k8s_pod_names.pod_name` | `$cluster, $namespace, $workload over 30m`<br>*(spans 25m 3-node rolling restarts)*<br>• `risk_score`: `if($pod_name = $workload, 90, 75)` *(90 for naked `kubectl run` pods)* | • `worker_node`: `array_distinct(re.capture($e.extracted.fields["textPayload"], "\"target\":\\s*\\{[^}]*\"kind\":\\s*\"Node\"[^}]*\"name\":\\s*\"([^\"]+)\""))` *(actual worker node, NOT scheduler leader `resource.labels.node_id`)*<br>• `pod_instances`: `array_distinct($pod_name)` |

---

## 3. Unmasking Obfuscated Principals in GCS Data Access Audit Logs

When investigating Google Cloud Storage `data_access` denial events where `principalEmail` is omitted and `status.message` masks the identity (e.g. `na...e@ic...s`):

1. **Pivot to Admin Activity**: In GCP Logs Explorer or `gcloud logging read`, query `cloudaudit.googleapis.com%2Factivity` logs matching the `callerIp` from the denial:
   ```sql
   logName=~"cloudaudit.googleapis.com%2Factivity"
   protoPayload.requestMetadata.callerIp="<ATTACKER_IP>"
   protoPayload.authenticationInfo.principalEmail:*
   timestamp >= "<START_TIME>" AND timestamp <= "<END_TIME>"
   ```
2. **Pivot via OAuth Client ID**: If the caller used the Google Cloud SDK or automated scripts, query by client ID:
   ```sql
   protoPayload.authenticationInfo.oauthInfo.oauthClientId="<OAUTH_CLIENT_ID>"
   protoPayload.requestMetadata.callerIp="<ATTACKER_IP>"
   protoPayload.authenticationInfo.principalEmail:*
   ```

---

## 4. Multi-Log Correlation Runbook: Overcoming the Port-Forward Protocol Blind Spot

Because `kubectl port-forward` negotiates target port numbers inside binary SPDY/WebSocket multiplexed streams after the HTTP 101 handshake, the forwarded port **never appears in `KUBERNETES_AUDIT`**. Correlate with host-level logs on the worker node hosting the target pod:

1. **Step 1: Identify Target Pod and Worker Node**:
   From the alert, note `$target_pod`, `$target_namespace`, and `$caller_ip`. Run `kubectl get pod -n <namespace> <pod_name> -o wide` or query container inventory to identify the hosting node (e.g. `k8s-worker-01`).

2. **Step 2: Linux Sysmon Event ID 3 (Network Connect) Correlation**:
   On the worker node, `containerd` or `kubelet` establishes a loopback connection to satisfy the forwarded stream:
   ```sql
   metadata.log_type = "LINUX_SYSMON"
   metadata.event_type = "NETWORK_CONNECTION"
   principal.hostname = "<NODE_HOSTNAME>"
   (target.process.file.names = "containerd" or target.process.file.names = "containerd-shim-runc-v2" or target.process.file.names = "kubelet")
   (target.ip = "127.0.0.1" or target.ip = "<POD_IP>")
   timestamp >= "<ALERT_TIME - 30s>" and timestamp <= "<ALERT_TIME + 2m>"
   ```
   *Inspect `target.port` to identify the forwarded destination port (e.g. 5432, 6379, 2379, 80).*

3. **Step 3: Systemd Journald / Kubelet Log Correlation**:
   Query Kubelet stream logs for tunnel entry messages:
   ```sql
   metadata.log_type = "JOURNALD"
   principal.hostname = "<NODE_HOSTNAME>"
   extracted.fields["MESSAGE"] = /portforward\.go.*Entering tunnel for/
   timestamp >= "<ALERT_TIME - 30s>" and timestamp <= "<ALERT_TIME + 2m>"
   ```
   *The log format explicitly records: `portforward.go: Entering tunnel for pod <namespace>/<pod> Port:<PORT>`.*

4. **Step 4: Linux AuditD Syscall Correlation**:
   Look for `connect()` syscalls (`syscall = 42` on x86_64) executed by the container runtime:
   ```sql
   metadata.log_type = "AUDITD"
   principal.hostname = "<NODE_HOSTNAME>"
   target.process.file.full_path = "/usr/bin/containerd"
   additional.fields["a2"] = /.*/ // sockaddr structure containing port and destination
   ```

### Multi-Cluster Threat Hunting Query for Port-Forwards
Hunt for unauthorized interactive port-forward tunnels across all clusters (e.g. `prod`, `staging`, `edge`):
```sql
metadata.log_type = "KUBERNETES_AUDIT"
(
  target.resource.resource_subtype = "pods/portforward" or
  target.url = /.*\/api\/v1\/namespaces\/[^\/]+\/pods\/[^\/]+\/portforward.*/
)
network.http.method = "POST"
network.http.response_code != 403
```

---

## 5. Custom JSON Container Logs Routed to Unparsed `GENERIC_EVENT` Feeds

When custom Kubernetes JSON application logs (for example, edge telemetry or service-mesh monitors running on `GKE`, `K3s`, or self-managed clusters) are routed to a custom or misclassified `metadata.log_type` that lacks a dedicated entity mapping (`metadata.event_type = "GENERIC_EVENT"`):

* **Parser & Timestamp Invariants**:
  * Standard UDM entity fields (`principal.*`, `target.*`, `src.*`, `network.*`, `security_result.*`) may be **NULL**.
  * Batch shippers can overwrite `metadata.event_timestamp` with `metadata.ingested_timestamp` (+10 to 15 minutes batch skew). Inspect `$e.extracted.fields["jsonPayload.ts"]` or `$e.extracted.fields["timestamp"]` for the true application event timestamp.
* **Key `extracted.fields` Pivot Selectors**:
  * `$project = $e.extracted.fields["resource.labels.project_id"]`
  * `$node = $e.extracted.fields["resource.labels.node_id"]` (for example, `k3s-node-01`, `k8s-worker-01`)
  * `$pod = $e.extracted.fields["resource.labels.pod_name"]`
  * `$asset_id = $e.extracted.fields["jsonPayload.msg.asset_id"]`
  * `$error_detail = $e.extracted.fields["jsonPayload.msg.details"]`
* **Workload Identity Federation (`sts.googleapis.com`) & Service Account Key IDs**:
  * Kubernetes workloads federating into GCP via `sts.googleapis.com` token exchange do not use exported JSON service account keys, leaving `$e.security_result.detection_fields["key_id"]` **NULL**. Reference `detection_fields["key_id"]` exclusively in `outcome:` (`$sa_key_id = array_distinct($e.security_result.detection_fields["key_id"])`) rather than filtering on it in `events:`.
