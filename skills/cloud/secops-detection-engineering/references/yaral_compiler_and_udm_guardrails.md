# Google SecOps YARA-L 2.0 Compiler & UDM Schema Guardrails

<!-- disableFinding(LINE_OVER_80) -->
<!-- disableFinding(SNIPPET_INVALID_LANGUAGE) -->

This reference defines the compiler syntax rules, type-checking constraints, aggregation invariants, and log-source UDM field mappings required to author zero-compile-error YARA-L 2.0 detection rules in Google SecOps.

## Table of Contents

- [1. Core YARA-L 2.0 Compiler & Section Structure Invariants](#1-core-yara-l-20-compiler-section-structure-invariants): Lines 19-43
- [2. `outcome:` Aggregations & Dynamic Risk Scoring](#2-outcome-aggregations-dynamic-risk-scoring): Lines 46-64
- [3. Regex Syntax, `strings.coalesce()`, Reference Lists & CIDR Filtering](#3-regex-syntax-stringscoalesce-reference-lists-cidr-filtering): Lines 68-80
- [4. UDM Schema Paths, Valid Enums, Entity Joins & Composite Detections](#4-udm-schema-paths-valid-enums-entity-joins-composite-detections): Lines 84-95
- [5. Log-Source Specific UDM Field & Parser Guardrails](#5-log-source-specific-udm-field-parser-guardrails): Lines 99-108
- [6. Verified Reference Rule Blueprints](#6-verified-reference-rule-blueprints): Lines 112-273

---

## 1. Core YARA-L 2.0 Compiler & Section Structure Invariants

1. **Canonical Section Order (`meta -> events -> match -> outcome -> condition -> options`)**:
   - Declare sections strictly in canonical order. Omitting optional sections (`match:`, `outcome:`, `options:`) is valid, but reordering sections (such as `outcome:` before `match:`) fails compilation.
2. **Placeholder Assignment & Single-Source Function Calls**:
   - Declare placeholder variables on the left-hand side (`$host = $e.principal.hostname`).
   - In `events:`, non-boolean functions (`strings.concat`, `strings.coalesce`, `re.capture`) cannot mix a bound placeholder variable and an event field (`strings.concat($prefix, "-", $e.principal.asset_id)` fails). Inline `re.capture($e.target.resource.name, ...)` directly inside `strings.concat(...)` so all arguments reference `$e`.
3. **Direct Event Field Assignment for `match:` Variables**:
   - Every variable in `match:` must directly reference at least one `$e.{field}` in its assignment expression (never transitive placeholder-to-placeholder chains):
     ```yaral
     $appliance = strings.to_upper(
       re.capture(
         strings.coalesce($e.principal.hostname, $e.intermediary.hostname),
         `^([^.]+)`
       )
     )
     ```
4. **Zero-Value Exclusion on Direct vs. Function-Assigned `match:` Variables**:
   - Direct field bindings (`$user = $e.principal.user.userid`) automatically exclude `""` and `0` from `match:` grouping (`$user != ""` is redundant).
   - Function-assigned placeholders (`$host = strings.coalesce(...)` or `re.capture(...)`) bypass automatic zero-value exclusion; explicitly add `$host != ""` whenever all inputs can be empty so NULL events do not merge into a single correlation bucket.
5. **Strict `condition:` Comparison Predicates**:
   - Comparisons in `condition:` must evaluate single event/outcome variables against literals (`$e and $total >= 10 and $rate >= 5`). Compute arithmetic rates in `outcome:` first (`$rate = ($total * 3600) / ($time_span + 1)`).
6. **Streaming `SINGLE_EVENT` (`< 0.5 min`) vs. Windowed Watermark Latency (`match:`)**:
   - Adding any `match:` block routes the rule into the windowed pipeline (~25-30m P90 watermark latency). For high-severity atomic events (`cluster-admin` RBAC bindings, offensive binaries, SA key creation), omit `match:` for streaming `SINGLE_EVENT` execution and scope `$e.metadata.log_type` explicitly.

---

## 2. `outcome:` Aggregations & Dynamic Risk Scoring

1. **The 7 Valid Outcome Aggregation Functions**:
   - Use only `max()`, `min()`, `sum()`, `count()`, `count_distinct()`, `array()`, and `array_distinct()` (`avg()`, `mean()`, and `stddev()` do not exist).
2. **Mandatory Aggregation When `match:` Is Present**:
   - Whenever `match:` is present, **every** `outcome:` variable referencing an event field or scalar constant must use an aggregation function (`$risk_score = max(85)`).
   - Never nest another `$outcome_var` inside an aggregate (`max($base_score)` fails); aggregate raw event expressions first and combine via top-level arithmetic (`$risk_score = $base_score + $bonus_score`).
3. **Repeated UDM Fields Require Aggregation Even Without `match:`**:
   - All IP arrays (`principal.ip`, `target.ip`, `src.ip`, `intermediary.ip`) and email lists (`principal.user.email_addresses`) are `repeated string` fields; assigning them in `outcome:` always requires `array_distinct()` or `array()`, even in single-event rules:
     ```yaral
     $source_ips = array_distinct(strings.coalesce($e.principal.ip, $e.intermediary.ip))
     ```
4. **Flat Additive `if()` Expressions (No Nested `else if()`)**:
   - Decompose multi-tier dynamic risk scoring into flat additive outcome variables rather than nested `else if()`:
     ```yaral
     $base_score = max(if($e.security_result.action = "ALLOW", 60, 25))
     $priv_bonus = max(if(re.regex($e.target.user.userid, `^(root|admin)$`) nocase, 30, 0))
     $risk_score = $base_score + $priv_bonus
     ```

---

## 3. Regex Syntax, `strings.coalesce()`, Reference Lists & CIDR Filtering

1. **Backtick Raw String Literals (`` `...` ``) & Trailing `nocase` Placement**:
   - Prefer backtick raw strings (``re.regex($field, `\\netsh\.exe$`) nocase``) so regex metacharacters like `\.` only need single RE2 escaping (double-quoted `"\."` fails with `invalid char escape`), whereas literal backslashes still require `\\` so sequences like `\n` or `\t` are not parsed by RE2 as control characters. Never embed a literal backtick inside a backtick string.
   - Always place `nocase` **outside** the regex literal or `re.regex()` call (`$e.target.process.file.full_path = /\\cmd\.exe$/ nocase` or ``re.regex($f, `pattern`) nocase``). Never use `/pattern/i` or bare `(?i)` without `nocase`.
2. **RE2 Word-Boundary (`\b`) CLI Flag & Path Traps**:
   - In RE2, `-`, `/`, `\`, and `.` are non-word characters (`\W`): `\b-group=` never matches `"Seatbelt.exe -group=all"` after whitespace, and `\bnmap\b` false-positives on `/var/lib/dpkg/info/nmap-common.postinst`. Anchor CLI flags and tools with `(?:^|[\s"'])-(?:group|outputfile)\b` and `(?:^|[\s;|&"'(]|/){tool}(?:\s|$)`.
3. **`strings.coalesce()` Strict `[string]` Type Homogeneity**:
   - Every argument to `strings.coalesce()` must be a `string`. Passing `INT64` (`network.dns.questions.type`, `target.port`) or UDM `ENUM` (`metadata.event_type`, `security_result.action`, `extensions.auth.type`) fails compilation; extract enum/integer fields into separate variables.
4. **No Inline `in ("a", "b")` Tuples & Reference List Verification**:
   - Inline tuples (`$field in ("a", "b")`) fail with `unexpected token '('`. Reserve `in` strictly for Reference Lists (`in %list`, `in regex %list`, `in cidr %list`) and Data Tables (`in %table.col`) confirmed to exist in the tenant (`in regex %list` does not accept trailing `nocase`; use `strings.to_lower($f) in regex %list`). For inline sets, use parenthesized `or` chains on enums and ``re.regex($f, `^(a|b)$`) nocase`` on strings.
5. **CIDR Subnet Filtering (`net.ip_in_range_cidr`)**:
   - Filter RFC 1918 ranges, Google Cloud IAP (`35.235.240.0/20`), and dark-space subnets via `net.ip_in_range_cidr($e.target.ip, "10.0.0.0/8")`.

---

## 4. UDM Schema Paths, Valid Enums, Entity Joins & Composite Detections

1. **No `udm.` Prefix, No `network.ip` Field & No Mixed `raw = /.../` Predicates**:
   - Start UDM paths at top-level namespaces (`metadata.log_type`, `principal.hostname`, `target.process.command_line`, `extracted.fields["..."]`, `additional.fields["..."]`). `network.ip` does not exist (query `principal.ip`, `target.ip`, `src.ip`, or `intermediary.ip`), and `raw = /.../` cannot mix with UDM predicates.
2. **Valid `metadata.event_type` & `extensions.auth.type` Enums**:
   - Use exact `EventType` enums: `NETWORK_DNS` (not `DNS_QUERY`), `PROCESS_LAUNCH` (not `PROCESS_EXECUTION`), `NETWORK_HTTP` / `NETWORK_CONNECTION` (not `HTTP_REQUEST`), and `FILE_OPEN` / `FILE_READ` / `FILE_CREATION` / `FILE_MODIFICATION` / `FILE_DELETION` / `FILE_COPY` / `FILE_MOVE` (not `FILE_ACCESS`).
   - `extensions.auth.type` only accepts `AUTHTYPE_UNSPECIFIED`, `MACHINE`, `SSO`, `VPN`, `PHYSICAL`, or `TACACS`; match OAuth client auth methods in `extensions.auth.auth_details` or `security_result.detection_fields["client_auth_method"]`.
3. **`PROCESS_LAUNCH` Child vs. Parent Fields & Cross-Platform Shell Alternation**:
   - Spawned child process, CLI, SHA-256, and PE PDB path populate `target.process.*`; parent process populates `principal.process.*`. Separate Windows `.exe` interpreters from POSIX shells: ``re.regex($e.target.process.file.full_path, `(\\(powershell|pwsh|cmd|wscript|cscript)\.exe|/(ba|z|da)?sh)$`) nocase``.
4. **Multi-Tenant `ENTITY_CONTEXT` Joins & Composite Detections (`alert_state = "NOT_ALERTING"`)**:
   - In multi-VPC/MSSP tenants with overlapping RFC 1918 space, join `$src_ip = $e.principal.ip` and `$ns = $e.principal.namespace` alongside `$entity.graph.entity.hostname = $hostname` (`$entity.graph.metadata.entity_type = "ASSET"`).
   - Set noisy producer rules to `alert_state = "NOT_ALERTING"` and correlate multi-stage chains in Composite Detections via `$d.detection.id` (never `$d.detection.detection.id`), `$d.detection.detection_time.seconds`, `$d.detection.detection.rule_name`, and `$d.detection.detection.rule_id`.

---

## 5. Log-Source Specific UDM Field & Parser Guardrails

| Log Source (`metadata.log_type`) | Critical UDM Schema & Detection Engineering Guardrails |
| :--- | :--- |
| **`GCP_CLOUDAUDIT`** | • Structured `protoPayload` only (`extracted.fields["textPayload"]` is empty).<br>• **True IAM Denials vs. Operational `"BLOCK"`**: Non-zero gRPC codes (`5 NOT_FOUND`, `6 ALREADY_EXISTS`, `8 RESOURCE_EXHAUSTED`, `9 FAILED_PRECONDITION`) map to `action = "BLOCK"`. Require `($e.security_result.detection_fields["status_code"] = "7" or $e.security_result.detection_fields["status_code"] = "16" or $e.network.http.response_code = 403 or $e.network.http.response_code = 401)`.<br>• **SA Exclusions**: Exclude only Google-managed agents (`@(gcp-sa-[a-z0-9-]+\.iam|cloudservices|compute-system\.iam|container-engine-robot\.iam)\.gserviceaccount\.com$`). **Never** exclude `developer`, `appspot`, `cloudbuild`, or customer `*.iam.gserviceaccount.com`.<br>• **GCE LRO Dedup & `key_id`**: Add `$e.additional.fields["operation_last"] != "true"` on mutating GCE LROs (`attachDisk`, `insert`, `setCommonInstanceMetadata`) and reference `security_result.detection_fields["key_id"]` only in `outcome:` (NULL on OAuth/WIF tokens). |
| **`GCP_SECURITYCENTER_MISCONFIGURATION`** | • Suppress asset-deletion `INACTIVE` and muted findings via `$e.security_result.alert_state = "ALERTING"`, `$e.security_result.detection_fields["state"] = "ACTIVE"`, and `$e.security_result.detection_fields["mute"] != "MUTED"`.<br>• Coalesce VM names via `target.resource.attribute.labels["resource_displayName"]`, `target.asset.attribute.labels["assetDisplayName"]`, and ``re.capture($e.target.resource.name, `/instances/([^/]+)$`)``. |
| **`KUBERNETES_AUDIT`** | • `security_result.description` holds RBAC reason (`authorization.k8s.io/reason`), not payloads; `metadata.description` holds audit stage (`RequestReceived`, `ResponseStarted`, `ResponseComplete`).<br>• **Mutations**: Require `ResponseComplete`, `response_code >= 200` and `< 300`, `action = "ALLOW"`, and `$e.additional.fields["objectRef_namespace"]`.<br>• **Subresources (`/exec`, `/portforward`, `/binding`)**: **Never** exclude `system:node:*` or `system:serviceaccount:kube-system:*`. Match `/exec` commands across both `target.url` and `extracted.fields["textPayload"]`. Filter `/portforward` on `ResponseStarted` + `response_code = 101` (`$user, $namespace over 30m`). Normalize `/binding` workloads via end-anchored `re.replace()`. |
| **`WINEVTLOG` & `WINDOWS_DEFENDER_AV`** | • **`4624`/`4625` Hostname Coalescing**: On NTLM `Logon Type 3`, `target.hostname` is NULL and target server maps to `about.resource.name`; coalesce `$e.target.hostname, $e.about.resource.name, $e.target.administrative_domain, $e.principal.hostname`.<br>• **Dual-Stream Dedup**: Threshold via `count_distinct($fail.metadata.product_log_id)` (`RecordNumber`) and use `>=` on `.seconds`.<br>• **`WINDOWS_DEFENDER_AV`**: Unescaped `&amp;` in `raw_xml` downgrades records to `GENERIC_EVENT`; coalesce hostname (`labels.compute.googleapis.com/resource_name` / `<Computer>`) and EventID (`additional.fields["EventID"]` / `<EventID>`). |
| **`LINUX_SYSMON`, `AUDITD` & `NIX_SYSTEM`** | • Scope process rules to `LINUX_SYSMON`, `AUDITD`, `NIX_SYSTEM`, `WINDOWS_SYSMON`, and `WINEVTLOG` (never `JOURNALD`; note `NIX_SYSTEM` maps `sudo` to `USER_LOGIN`).<br>• **Empty `principal.ip` Negation**: Guard IP exclusions on host events with `($e.principal.ip = "" or not $e.principal.ip = "192.0.2.10")`.<br>• **`UT_NAMESIZE` (32 chars)**: Normalize long OS Login usernames via ``re.capture($user, `^(.{1,32})`)`` and join `$login` (`NIX_SYSTEM`) to retain SSH client IPs. |
| **`GCP_DNS`, `GCP_FIREWALL`, `PFSENSE` & `EMM_AUDIT`** | • **`GCP_DNS`**: Forwarding zones without `sourceIP` map to `GENERIC_EVENT`; coalesce `network.dns.questions.name` and `extracted.fields["jsonPayload.queryName"]` (`\.?$`), and detect tunneling at single-label `>= 37` chars (`questions.type != 33`).<br>• **`GCP_FIREWALL` vs. `PFSENSE`**: Filter `$e.principal.ip != "0.0.0.0"` and read VM names from `resource.name` on `GCP_FIREWALL`. On `PFSENSE`, coalesce `principal.hostname` and `intermediary.hostname`, never end-anchor `metadata.description`, and exclude UDP source ports `53`/`123` + `data_length != "0"` in scan rules.<br>• **`EMM_AUDIT`**: Coalesce `extracted.fields["jsonPayload.message"]`, `security_result.description`, and `metadata.description`. |

---

## 6. Verified Reference Rule Blueprints

Run `python3 scripts/validate_yaral_rule.py --input {file_path}` to verify section ordering, `match:` windows, `outcome:` aggregations, external `nocase` placement, and `net.ip_in_range_cidr()` checks on `.yaral` or Markdown files.

```yaral
rule gcp_iam_permission_enumeration_burst {
  meta:
    author = "Google SecOps Detection Engineering"
    description = "Detects rapid GCP IAM GetIamPolicy or TestIamPermissions enumeration bursts while excluding Terraform state refreshes"
    severity = "High"
    priority = "High"
    mitre_attack_technique = "T1069.003"
    version = "1.0.0"

  events:
    $e.metadata.log_type = "GCP_CLOUDAUDIT"
    re.regex($e.metadata.product_event_type, `(GetIamPolicy|TestIamPermissions)$`) nocase
    $principal_email = strings.to_lower($e.principal.user.userid)
    $principal_email != ""
    not re.regex($principal_email, `@(gcp-sa-[a-z0-9-]+\.iam|cloudservices|compute-system\.iam|container-engine-robot\.iam)\.gserviceaccount\.com$`) nocase
    (
      re.regex($e.metadata.product_event_type, `TestIamPermissions$`) nocase or
      not re.regex($e.network.http.user_agent, `(Terraform|terraform-provider|Pulumi|Config-Connector)`) nocase
    )

  match:
    $principal_email over 15m

  outcome:
    $base_score = max(70)
    $cli_bonus = max(if(re.regex($e.network.http.user_agent, `(python|requests|gcloud|curl)`) nocase, 15, 0))
    $risk_score = $base_score + $cli_bonus
    $total_api_calls = count($e.metadata.id)
    $distinct_resources = count_distinct($e.target.resource.name)
    $methods = array_distinct($e.metadata.product_event_type)
    $source_ips = array_distinct($e.principal.ip)
    $service_account_keys = array_distinct($e.security_result.detection_fields["key_id"])

  condition:
    $e and ($total_api_calls >= 15 or $distinct_resources > 10)
}
```

```yaral
rule outbound_non_rfc1918_tftp_config_exfiltration {
  meta:
    author = "Google SecOps Detection Engineering"
    description = "Detects outbound UDP port 69 TFTP transfers from internal network infrastructure to external IP addresses"
    severity = "Critical"
    priority = "High"
    mitre_attack_technique = "T1048.003"
    version = "1.0.0"

  events:
    $e.metadata.event_type = "NETWORK_CONNECTION"
    $e.network.ip_protocol = "UDP"
    $e.target.port = 69
    $e.principal.ip != "0.0.0.0"
    not net.ip_in_range_cidr($e.target.ip, "10.0.0.0/8")
    not net.ip_in_range_cidr($e.target.ip, "172.16.0.0/12")
    not net.ip_in_range_cidr($e.target.ip, "192.168.0.0/16")
    not net.ip_in_range_cidr($e.target.ip, "127.0.0.0/8")
    $src_host = strings.coalesce($e.principal.hostname, $e.intermediary.hostname, $e.principal.resource.name)
    $src_host != ""

  match:
    $src_host over 15m

  outcome:
    $risk_score = max(95)
    $transfer_count = count($e.metadata.id)
    $source_ips = array_distinct($e.principal.ip)
    $external_destinations = array_distinct($e.target.ip)

  condition:
    $e and $transfer_count >= 1
}
```

```yaral
rule kubernetes_cluster_admin_rbac_binding {
  meta:
    author = "Google SecOps Detection Engineering"
    description = "Streaming single-event detection for Kubernetes ClusterRoleBinding or RoleBinding grants referencing cluster-admin or system:masters"
    severity = "Critical"
    priority = "High"
    mitre_attack_technique = "T1098.006"
    version = "1.0.0"

  events:
    $e.metadata.log_type = "KUBERNETES_AUDIT"
    $e.metadata.description = "ResponseComplete"
    $e.security_result.action = "ALLOW"
    $e.network.http.response_code >= 200
    $e.network.http.response_code < 300
    ($e.network.http.method = "create" or $e.network.http.method = "patch" or $e.network.http.method = "update")
    re.regex($e.target.resource.name, `(clusterrolebindings|rolebindings)/`) nocase
    re.regex($e.extracted.fields["textPayload"], `"roleRef":\{[^}]*"name":"(cluster-admin|system:masters|admin)"`) nocase
    not re.regex($e.principal.user.userid, `^(system:kube-controller-manager|system:apiserver|system:addon-manager)$`) nocase

  outcome:
    $risk_score = if(re.regex($e.extracted.fields["textPayload"], `"name":"(cluster-admin|system:masters)"`) nocase, 95, 80)
    $actor = $e.principal.user.userid
    $binding_resource = $e.target.resource.name
    $target_namespace = $e.additional.fields["objectRef_namespace"]
    $source_ips = array_distinct($e.principal.ip)

  condition:
    $e
}
```

```yaral
rule windows_brute_force_followed_by_logon_success {
  meta:
    author = "Google SecOps Detection Engineering"
    description = "Correlates deduplicated Windows 4625 logon failures followed by a 4624 interactive or network logon on the same target host"
    severity = "High"
    priority = "High"
    mitre_attack_technique = "T1110.001"
    version = "1.0.0"

  events:
    $fail.metadata.log_type = "WINEVTLOG"
    $fail.metadata.event_type = "USER_LOGIN"
    $fail.metadata.product_event_type = "4625"
    $fail.security_result.action = "BLOCK"

    $succ.metadata.log_type = "WINEVTLOG"
    $succ.metadata.event_type = "USER_LOGIN"
    $succ.metadata.product_event_type = "4624"
    $succ.security_result.action = "ALLOW"

    $target_user = strings.to_lower($fail.target.user.userid)
    $target_user = strings.to_lower($succ.target.user.userid)
    $target_user != ""
    not re.regex($target_user, `(\$$|^(anonymous logon|guest|system|local service|network service)$)`) nocase

    $target_host = strings.to_lower(
      strings.coalesce($fail.target.hostname, $fail.about.resource.name, $fail.principal.hostname)
    )
    $target_host = strings.to_lower(
      strings.coalesce($succ.target.hostname, $succ.about.resource.name, $succ.principal.hostname)
    )
    $target_host != ""

    $succ.metadata.event_timestamp.seconds >= $fail.metadata.event_timestamp.seconds

  match:
    $target_host, $target_user over 15m

  outcome:
    $unique_failed_attempts = count_distinct($fail.metadata.product_log_id)
    $successful_logons = count_distinct($succ.metadata.product_log_id)
    $risk_score = max(85)
    $source_ips = array_distinct($fail.principal.ip)
    $success_ips = array_distinct($succ.principal.ip)

  condition:
    $fail and $succ and $unique_failed_attempts >= 10 and $successful_logons >= 1
}
```
