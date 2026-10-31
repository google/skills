# Endpoint Forensics: Volume Shadow Dumping, AuditD, Sysmon & Linux Container UAC

<!-- disableFinding(LINE_OVER_80) -->

## Table of Contents

- [1. Cloud Volume Shadow Dumping & Disk Attach Triage](#1-cloud-volume-shadow-dumping-disk-attach-triage): Lines 13-38
- [2. Endpoint Forensics for Volume Shadow Mounts & AuditD Telemetry](#2-endpoint-forensics-for-volume-shadow-mounts-auditd-telemetry): Lines 42-105
- [3. Linux Container & Kubernetes (`containerd` / K3s / RKE2) Host Forensics & UAC Collection](#3-linux-container-kubernetes-containerd-k3s-rke2-host-forensics-uac-collection): Lines 109-152

---

## 1. Cloud Volume Shadow Dumping & Disk Attach Triage

### A. Detect the 3-Step Volume Shadow Dumping Chain
Search for the complete snapshot -> disk clone -> attach lifecycle:
```sql
metadata.log_type = "GCP_CLOUDAUDIT"
target.application = "compute.googleapis.com"
(
  metadata.product_event_type = "v1.compute.snapshots.insert" or
  metadata.product_event_type = "v1.compute.disks.insert" or
  metadata.product_event_type = "v1.compute.instances.attachDisk"
)
```

### B. Prove Filesystem Mounts via GCE Serial Console Logs
```text
logName="projects/<PROJECT_ID>/logs/serialconsole.googleapis.com%2Fserial_port_1_output"
resource.labels.instance_id="<INSTANCE_ID>"
(
  textPayload=~"sdb" OR
  textPayload=~"EXT4" OR
  textPayload=~"XFS" OR
  textPayload=~"mounted" OR
  textPayload=~"Attached SCSI"
)
```

---

## 2. Endpoint Forensics for Volume Shadow Mounts & AuditD Telemetry

### A. Detecting Cloned Snapshot Probing & Mount Discovery
Adversaries mounting attached snapshot disks (e.g. `cloned-snapshot-disk-01` to `/mnt/...`) often trigger `EACCES` (Permission Denied) when inspecting `/root` directories with `0700` permissions:
```sql
metadata.log_type = "AUDITD"
(
  extracted.fields["textPayload"] = /.*syscall=257.*exit=-13.*/ or
  security_result.action = "BLOCK"
)
extracted.fields["textPayload"] = /.*proctitle=.*\/mnt\/.*/
```

### B. High-Density UDM Hunting Selectors for Disk Attach & AuditD Elevation

| Rule / Detection Name | MITRE ATT&CK | UDM `log_type` & Target | High-Density UDM Predicates & Temporal Sequence | Window & Scoring Logic | Key Outcome / Triage Artifacts |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`GCP_GCE_SuspiciousDiskAttach`**<br>*(CSI Driver Impersonation / Manual Disk Attach)* | `T1003`, `T1578` | `GCP_CLOUDAUDIT` | • `$e.metadata.product_event_type = "v1.compute.instances.attachDisk"`<br>• `$e.security_result.action = "ALLOW"`<br>• Exclude legitimate GKE/GCE CSI Driver: `not re.regex($e.network.http.user_agent, "^google-api-go-client/[\\d.]+\\s+GCE CSI Driver/v\\d+\\.\\d+\\.\\d+(?:-[a-zA-Z0-9.]+)?")` | Single Event<br>(`severity = High`) | • `actor_email`: `$e.principal.user.email_addresses`<br>• `attached_disk`: `$e.target.resource.name`<br>• `user_agent`: `$e.network.http.user_agent` |
| **`Endpoint_Access_Denied_Followed_By_Root_Elevation`**<br>*(AuditD `EACCES` Followed by `sudo su`)* | `T1068`, `T1548.003` | `AUDITD`<br>`$host = $denied.principal.hostname` | • **Event 1 (`$denied`)**: `extracted.fields["textPayload"] = /.*syscall=257.*exit=-13.*/` *(openat EACCES)*<br>• **Event 2 (`$elevate`)**: `extracted.fields["textPayload"] = /.*(sudo su\|comm="sudo").*exit=0.*/`<br>• **Temporal constraint**: `$denied.metadata.event_timestamp.seconds < $elevate.metadata.event_timestamp.seconds` and `$elevate.metadata.event_timestamp.seconds - $denied.metadata.event_timestamp.seconds <= 60` | `$host over 2m`<br>Condition: `$denied and $elevate` | • `host`: `$denied.principal.hostname`<br>• `denied_proctitle`: `$denied.extracted.fields["textPayload"]`<br>• `elevation_cmd`: `$elevate.extracted.fields["textPayload"]` |

### C. Decoding Hex-Encoded AuditD `proctitle` Strings (`7375646F007375` = `sudo su`)
In AuditD raw payloads (`extracted.fields["proctitle"]` and `extracted.fields["textPayload"]`), argument vectors with spaces or null bytes (`\x00`) are hex-encoded:

- **`sudo su`**: `7375646F007375` (`sudo\x00su`) or `7375646F007375002D` (`sudo\x00su\x00-`)
- **`ls --color=auto -l /mnt/...`**: `6C73002D2D636F6C6F723D6175746F002D6C002F6D6E742F...`
- Always match both ASCII `target.process.command_line` and hex-encoded `extracted.fields["proctitle"]` / `extracted.fields["textPayload"]` (`re.regex($e.extracted.fields["proctitle"], "(?i)7375646F007375")`).

### D. `LINUX_SYSMON` UDM Schema, `masscan` Raw-Socket Bypass & Root Attribution (`CurrentDirectory` + `auid` + `7375646F007375`)

| Rule / Detection Name | MITRE ATT&CK | UDM `log_type` & Target | High-Density UDM Predicates & Attribution Logic | Window & Scoring Logic | Key Outcome / Triage Artifacts |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`Linux_Masscan_RawSocket_Endpoint_Execution`**<br>*(Bypasses `LINUX_SYSMON` Event ID 3 `NetworkConnect`)* | `T1046` | `LINUX_SYSMON` / `AUDITD`<br>(`PROCESS_LAUNCH`, `FILE_CREATION`) | • **Why Event ID 3 Is Blind**: `masscan` uses a custom user-space TCP/IP stack (`AF_PACKET` / `SOCK_RAW`), completely bypassing the Linux kernel TCP/IP stack and `LINUX_SYSMON` Event ID 3 (`NetworkConnect`)<br>• **CLI Flag Detection (`PROCESS_LAUNCH`)**: `re.regex($e.target.process.command_line, "(--max-rate\|--banners\|--adapter-port\|--Wait\|--rate)")` or `target.process.file.full_path = /\/masscan$/`<br>• **Artifact Detection (`FILE_CREATION`)**: `target.file.full_path = /\/paused\.conf$/`<br>• **Kernel RST-Suppression Rule (`PROCESS_LAUNCH`)**: `iptables -A INPUT -p tcp --dport 40000:65535 -j DROP` (`re.regex($e.target.process.command_line, "iptables.*--dport\\s+40000:65535.*-j\\s+DROP")`) | Single Event or `$host over 15m` | • `cmd`: `array_distinct($e.target.process.command_line)`<br>• `working_dir`: `array_distinct(strings.coalesce($e.target.process.working_directory, $e.additional.fields["current_directory"], re.capture($e.extracted.fields["jsonPayload.MESSAGE"], "<Data Name=\"CurrentDirectory\">([^<]+)</Data>")))` |
| **`Linux_Root_Elevation_Attribution_Sysmon_Auditd`**<br>*(`sudo su` Attribution via `CurrentDirectory`, `auid` & Hex `proctitle`)* | `T1548.003` | `LINUX_SYSMON` (`$sysmon`) + `AUDITD` (`$auditd`) | • **`LINUX_SYSMON` Working Directory**: Coalesce `$cwd = strings.coalesce($sysmon.target.process.working_directory, $sysmon.additional.fields["current_directory"], re.capture($sysmon.extracted.fields["jsonPayload.MESSAGE"], "<Data Name=\"CurrentDirectory\">([^<]+)</Data>"))` (e.g., `/home/<operator>` persists across `sudo su`)<br>• **`AUDITD` Immutable Login UID (`auid`)**: The default `AUDITD` parser leaves `auid` unmapped; extract original human UID via `$auid = re.capture($auditd.extracted.fields["textPayload"], "\\bauid=([0-9]+)\\b")` (`$auid != "4294967295"`)<br>• **Hex `proctitle` Decoding**: Match `7375646F007375` (`sudo su`) in `$auditd.extracted.fields["proctitle"]` or `$auditd.extracted.fields["textPayload"]` | `$host over 15m`<br>Condition: `$sysmon and $auditd` | • `original_auid`: `array_distinct($auid)`<br>• `operator_cwd`: `array_distinct($cwd)`<br>• `hex_proctitle`: `array_distinct($auditd.extracted.fields["proctitle"])` |

* **`LINUX_SYSMON` UDM Field Mapping & Coalescing Reference**:
  * **Actor `ProcessId` & `User` (`EventIDs 2, 3, 7, 8, 9, 10, 11, 12, 13, 14, 15, 22, 23, 26`)**: Maps `<Data Name="ProcessId">` (and `<Data Name="SourceProcessId">` on `EID 8`/`10`) to `principal.process.pid` (while preserving `Execution/@ProcessID` in `observer.process.pid`) and `<Data Name="User">` to `principal.user.userid`.
  * **`EventID 1` (`PROCESS_LAUNCH`)**: Maps `ParentUser` -> `principal.user.userid`, `CurrentDirectory` -> `target.process.working_directory` + `additional.fields["current_directory"]`, `LogonId` -> `principal.network.session_id`, `LogonGuid` -> `additional.fields["logon_guid"]`, `TerminalSessionId` -> `additional.fields["terminal_session_id"]`, and `IntegrityLevel` -> `additional.fields["integrity_level"]`.
  * **`EventID 3` (`NETWORK_CONNECTION`)**: Maps `Initiated == "false"` -> `network.direction = "INBOUND"` (`"true"` -> `"OUTBOUND"`), normalizes OpenSSH proctitles in `<Data Name="Image">` (`sshd: user [priv]`, `sshd: user@pts/0`, `sshd -D [listener]`, `sshd-session: user [priv]`) into `principal.process.file.full_path = "/usr/sbin/sshd"`, `principal.process.command_line`, and `additional.fields["ssh_session_user"]`, routes numeric-only kernel socket `Image` values (`^[0-9]+$`) to `additional.fields["raw_image"]`, and tags Sysmon for Linux eBPF UDP `skb->data` offset anomalies (`SourceIp == "8.0.69.0"` and `SourcePort == 2577`) with `additional.fields["sysmon_linux_udp_offset_bug"] = "true"`.
  * **`EventID 4`, `5`, `11`, `16`, `23`, `26` & Non-XML `systemd-journald` Records**: Classifies `EventID 4` and Cloud Logging `systemd-journald` daemon records (`jsonPayload.MESSAGE` / `_EXE` / `_PID` / `_CMDLINE` / `_SYSTEMD_UNIT`) as `SERVICE_OTHER`, maps `EventID 5` `User` -> `target.user.userid` and `ProcessGuid` -> `target.process.product_specific_process_id`, parses `EventID 11` `CreationUtcTime` -> `target.file.last_modification_time`, maps `EventID 16` `Configuration` -> `target.file.full_path` + `ConfigurationFileHash` -> `target.file.{sha256,md5,sha1}`, and maps `EventID 23`/`26` `Archived` + `IsExecutable` + `target.file.{sha256,md5,sha1}`.
  * **32-Character Linux Username Truncation (`UT_NAMESIZE = 32`)**: Linux `utmp` / kernel login records truncate usernames at 32 characters (`UT_NAMESIZE`). Google Cloud OS Login usernames formed from long email addresses (`firstname_lastname_company_domain_com` > 32 chars) are truncated to 32 characters in `LINUX_SYSMON` (`principal.user.userid`) and `AUDITD`, whereas `GCP_CLOUDAUDIT` and `OSQUERY_EDR` log the full string. When joining `LINUX_SYSMON` with `GCP_CLOUDAUDIT` or `OSQUERY_EDR` on username, normalize both sides via `re.capture($user, "^(.{1,32})")`.
  * **UDM Search Repeated-Field Existential Negation (`NOT principal.ip =` vs. `!=`)**: On multi-IP events (where `GCP_COMPUTE_CONTEXT` populates `principal.ip = ["10.10.2.9", "169.254.169.254"]`), writing `principal.ip != "169.254.169.254"` in UDM Search evaluates to **TRUE** because `"10.10.2.9" != "169.254.169.254"`. Always use `NOT principal.ip = "169.254.169.254"`.

### E. Windows Defender AV (`WINDOWS_DEFENDER_AV`) & OSQuery / FleetDM (`OSQUERY_EDR`) Selectors

| Rule / Detection Name | MITRE ATT&CK | UDM `log_type` & Target | High-Density UDM Predicates & Parser Workarounds | Window & Scoring Logic | Key Outcome / Triage Artifacts |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`WinDefender_Tampering_Or_Malware_Detection`**<br>*(Covers EventID `1006`-`1008`, `1116`-`1119`, `5001`, `5004`, `5007`, `5010`, `5012`)* | `T1562.001` | `WINDOWS_DEFENDER_AV`<br>(`win-srv-01`, `pki-ca-01`, `wsus-01`) | • **Coalesce Hostname across `GENERIC_EVENT` XML Failures**: `$host = strings.to_lower(strings.coalesce(re.capture($e.principal.hostname, "^([^.]+)"), $e.extracted.fields["labels.compute.googleapis.com/resource_name"], re.capture($e.extracted.fields["jsonPayload.raw_xml"], "<Computer>([^<.]+)")))`<br>• **Coalesce EventID across normalized fields & `raw_xml`**: `$eid = strings.coalesce($e.additional.fields["EventID"], re.capture($e.security_result.description, "^EventID:\\s*([0-9]+)$"), re.capture($e.metadata.product_event_type, "^EventID:?\\s*([0-9]+)"), re.capture($e.extracted.fields["jsonPayload.raw_xml"], "<EventID>([0-9]+)</EventID>"))`<br>• **Exclude Baseline `LastMAPSFailureTimeString` Noise on `5007`**: `not ($eid = "5007" and re.regex($e.extracted.fields["jsonPayload.raw_xml"], "(?i)\\\\SpyNet\\\\LastMAPSFailureTime"))` | Single Event or `$host over 15m`<br>(`risk_score = 85` on `5001`/`5010`/`5012` or `DisableAntiSpyware`/`ExclusionPath`) | • `new_val`: `array_distinct(re.capture($e.extracted.fields["jsonPayload.raw_xml"], "<Data Name='New Value'>([^<]+)</Data>"))`<br>• `threat`: `array_distinct(re.capture($e.extracted.fields["jsonPayload.raw_xml"], "<Data Name='Threat Name'>([^<]+)</Data>"))`<br>• `threat_path`: `array_distinct(strings.coalesce($e.target.file.full_path, re.capture($e.extracted.fields["jsonPayload.raw_xml"], "<Data Name='Path'>([^<]+)</Data>")))` |
| **`WinDefender_Signature_Stale_Or_Update_Failure`**<br>*(Covers `EventID 2001` Update Failure & `EventID 1151` Signature Age)* | `T1562.001` | `WINDOWS_DEFENDER_AV` | • **Match**: `$eid = "2001"` or (`$eid = "1151"` and `re.regex($e.extracted.fields["jsonPayload.raw_xml"], "<Data Name='(?:Engine\|Platform) up-to-date'>false</Data>")`) | `$host over 1h` | • `err_code`: `array_distinct(re.capture($e.extracted.fields["jsonPayload.raw_xml"], "<Data Name='Error Code'>([^<]+)</Data>"))`<br>• `av_sig_age_days`: `array_distinct(re.capture($e.extracted.fields["jsonPayload.raw_xml"], "<Data Name='Antivirus security intelligence age'>([0-9]+)</Data>"))` |
| **`OSQuery_FleetDM_LOLBin_And_Parent_Anomaly_Hunt`**<br>*(`pack/Global/*` & `distributed_query` Differential vs. `pack/it-compliance/*` Snapshot)* | `T1059`, `T1547.001`, `T1053.005` | `OSQUERY_EDR`<br>`$asset_uuid = strings.coalesce($e.principal.asset_id, $e.extracted.fields["decorations.host_uuid"])` | • **Snapshot vs. Differential Mode**: Standard `OSQUERY_EDR` ingestion maps differential queries (`action="added"\|"removed"`) and snapshot queries (`action="snapshot"`) to `SETTING_MODIFICATION` / `SETTING_DELETION` or semantic UDM event types depending on parser version, with unmapped query columns available under `extracted.fields["columns.*"]`<br>• **Prefetch SQL `LIKE` Collision Trap**: `pack/Global/<binary>.exe` (`222`..`249`) queries `C:\Windows\Prefetch\*.pf` via unanchored `LIKE`; exclude `at.exe` (`WINSAT.EXE-*.pf`), `sc.exe` (`MSCORSVW.EXE-*.pf`), and `reg.exe` (`REGSVR32.EXE-*.pf`) by verifying `re.regex(strings.coalesce($e.target.file.full_path, $e.extracted.fields["columns.filename"]), "(?i)(?:^\|\\\\)(?:CERTUTIL\|REGSVR32\|SCHTASKS\|MSTSC\|CSCRIPT\|WHOAMI\|NET)\\.EXE-[A-F0-9]+\\.pf$")` and `not re.regex(strings.coalesce($e.target.file.full_path, $e.extracted.fields["columns.filename"]), "(?i)(?:WINSAT\|MSCORSVW)\\.EXE")` | `$asset_uuid, $query over 15m` | • `hosts`: `array_distinct($e.principal.hostname)`<br>• `cmd_line`: `array_distinct(strings.coalesce($e.target.process.command_line, $e.extracted.fields["columns.cmdline"]))`<br>• `bad_parent`: `array_distinct(strings.coalesce($e.target.process.file.full_path, $e.extracted.fields["columns.bad_parent_child_name"]))`<br>• `prefetch_file`: `array_distinct(strings.coalesce($e.target.file.full_path, $e.extracted.fields["columns.filename"]))` |

**`OSQUERY_EDR` SMBIOS Hardware UUID Correlation Across Hostname Renames**:

When endpoints are re-imaged or renamed mid-incident (for example, `CORP-LAPTOP-01` renamed to `US-WKSTN-01`), correlating solely on `principal.hostname` splits the host timeline. Join `OSQUERY_EDR` events on the immutable SMBIOS hardware UUID (`strings.coalesce($e.principal.asset_id, $e.extracted.fields["decorations.host_uuid"], $e.extracted.fields["hostIdentifier"])`) and aggregate observed hostnames via `array_distinct($e.principal.hostname)`:

| Example Hardware UUID (`decorations.host_uuid`) | Example MAC | Prior Hostname | Renamed Hostname | Query Mode |
| :--- | :--- | :--- | :--- | :--- |
| `00000000-0000-4000-8000-000000000001` | `00:00:5e:00:53:01` | `CORP-LAPTOP-01` | `US-WKSTN-01` | `action="snapshot"` (`pack/it-compliance/*`) |
| `00000000-0000-4000-8000-000000000002` | `00:00:5e:00:53:02` | `DEV-LAPTOP-02` | `SANDBOX-DEV-02` | `action="added"` (`pack/Global/*`) |

* **Common `OSQUERY_EDR` Differential Column Lookups (`extracted.fields["columns.*"]`)**:
  * **Process Parent Anomalies (`*_incorrect_parent_process`)**: `columns.bad_parent_child_name`, `columns.bad_parent_child_pid`.
  * **Network Connections & Listeners**: `columns.name`, `columns.path`, `columns.remote_address`, `columns.remote_port`, `columns.port`, `columns.protocol`.
  * **Windows Prefetch (`file` table queries)**: `columns.directory`, `columns.filename`, `columns.path`, `columns.btime`, `columns.mtime`, `columns.size`.
  * **Registry & Scheduled Tasks**: `columns.name`, `columns.type`, `columns.data`, `columns.action`, `columns.enabled`.

---

## 3. Linux Container & Kubernetes (`containerd` / K3s / RKE2) Host Forensics & UAC Collection

When collecting forensic artifacts from compromised Linux Kubernetes worker or control-plane nodes (`k8s-worker-01`, `k3s-node-01`) on GCE VMs using **UAC (Unix-like Artifacts Collector)** without installing additional tools on the host:

### A. UAC Custom YAML & `PATH` Guardrails (`tclahr/uac`)

1. **Standalone Dash Syntax Invariant:** UAC uses a custom shell parser (`lib/validate_artifact.sh`) rather than a standard YAML parser. Every item under `artifacts:` **must** begin with a standalone `-` on its own line:
   ```yaml
   artifacts:
     -
       description: Valid UAC entry
       supported_os: [linux]
   ```
   *(Writing `- description: ...` on a single line triggers `Invalid artifact format: expected '-' after 'artifacts:' mapping`.)*
2. **Filename Pattern Property:** Use `name_pattern: ["*.log", "*.yaml"]` (not `file_name:`).
3. **Hardcoded `PATH` (`__ua_path`) Override:** In `./uac`, UAC resets `PATH` to standard OS directories, stripping K3s/RKE2 statically linked binary directories (`/var/lib/rancher/rke2/bin`, `/var/lib/rancher/k3s/data/current/bin`). Append these paths to `__ua_path` in `./uac` so `condition: command_exists "crictl"` succeeds:
   ```sh
   __ua_path="${__ua_path}:/var/lib/rancher/rke2/bin:/opt/rke2/bin:/var/lib/rancher/k3s/data/current/bin:/opt/cni/bin"
   ```
4. **Pre-Deployment Validation:** Always validate custom artifacts and profiles before running collection:
   ```bash
   ./uac --validate-artifact artifacts/files/applications/kubernetes_node.yaml
   ./uac --validate-profile profiles/ir_triage.yaml
   ```

### B. Non-Standard Kubernetes (`K3s` / `RKE2`) Runtime Paths & Sockets

* **Containerd CRI Socket:** `/run/k3s/containerd/containerd.sock` (not `/run/containerd/containerd.sock`).
  * `crictl`: `crictl --runtime-endpoint unix:///run/k3s/containerd/containerd.sock <cmd>`
  * `ctr`: `ctr --address /run/k3s/containerd/containerd.sock --namespace k8s.io <cmd>`
* **OverlayFS Container Diff (`upperdir`) Without Execution:** To inspect dropped web shells or modified files inside running containers without running `kubectl exec` or `docker diff`, inspect the host mount table (`mount | grep -E "containerd.*overlay"`) or collect files directly from `/var/lib/rancher/rke2/agent/containerd/io.containerd.snapshotter.v1.overlayfs/snapshots/*/fs`.

### C. Essential File & Live Runtime Artifact Matrix

| Tier / ID | Artifact Category | Target Paths / Commands | Forensic Purpose |
| :--- | :--- | :--- | :--- |
| **File (A1)** | Pod & Container Logs | `/var/log/pods/**`, `/var/log/containers/**` | Captures container stdout/stderr even after pod deletion |
| **File (A2)** | Static Pod Manifests | `/var/lib/rancher/rke2/agent/pod-manifests`, `/etc/kubernetes/manifests` | Detects rogue static pod persistence bypassed via kubelet |
| **File (A3)** | Control Plane Datastore | `/var/lib/rancher/rke2/server/db/etcd`, `/var/lib/rancher/k3s/server/db` | Raw BoltDB/SQLite state containing cluster Secrets & RBAC |
| **File (A4)** | Kubeconfigs, Certs & Audit | `/etc/rancher`, `/var/lib/rancher/rke2/agent`, `/var/lib/rancher/rke2/server` | Node credentials, TLS keys, and local API `audit.log*` |
| **File (A5)** | CNI Network State | `/var/lib/cni`, `/etc/cni/net.d` | Maps ephemeral Pod IPs to containers for GCP VPC Flow Log correlation |
| **Live (B1)** | CRI Container & Image Dump | `crictl ... ps -a --verbose`, `images --verbose`, `foreach` -> `inspect %line%` | Image SHA256 digests, env vars (leaked secrets), privileged flags, mounts |
| **Live (B2)** | Host PID-to-Pod Mapping | `crictl ... inspectp %line%`, `grep -H -E "kubepods\|containerd" /proc/[0-9]*/cgroup` | Maps host PIDs to Kubernetes pod UIDs to spot hidden container processes |
| **Live (B3)** | GCP Node Metadata & IAM | `curl -s -f -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/?recursive=true&alt=json"` | Assesses GCP service account token exposure and IAM blast radius |
