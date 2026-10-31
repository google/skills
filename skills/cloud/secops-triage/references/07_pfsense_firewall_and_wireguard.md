# Netgate pfSense Plus (24.11 / 26.03.1) & WireGuard (`PFSENSE`) Detection & Triage Guide

<!-- disableFinding(LINE_OVER_80) -->

This reference documents the UDM parser quirks, syslog architecture, serial/console boot autologin forensics, and High-Density UDM Hunting Selectors for **Netgate pfSense Plus (`24.11-RELEASE` / `26.03.1-RELEASE amd64`)** ingested via Google Cloud Logging collectors (`log_type = "PFSENSE"`).

## Table of Contents

- [1. `PFSENSE` UDM Schema & Split-Brain Architecture](#1-pfsense-udm-schema-split-brain-architecture): Lines 18-50
- [2. Complete Catalog of WireGuard Config Strings on pfSense Plus 24.11](#2-complete-catalog-of-wireguard-config-strings-on-pfsense-plus-2411): Lines 54-86
- [3. `filterlog` Port-Scan False Positives: Orphaned DNS Replies (`unbound` RFC 5452) on WireGuard Tunnels](#3-filterlog-port-scan-false-positives-orphaned-dns-replies-unbound-rfc-5452-on-wireguard-tunnels): Lines 90-111
- [4. Serial (`ttyu0`) & Video (`ttyv0`) Console `root` Autologin vs. Human Intrusion Forensics](#4-serial-ttyu0-video-ttyv0-console-root-autologin-vs-human-intrusion-forensics): Lines 115-130
- [5. High-Density UDM Hunting Selectors for Netgate pfSense Plus](#5-high-density-udm-hunting-selectors-for-netgate-pfsense-plus): Lines 134-141

---

## 1. `PFSENSE` UDM Schema & Split-Brain Architecture

When pfSense RFC 5424 syslog messages are forwarded via `syslog-ng` and a GCP Cloud Logging collector (e.g. `generic_node` / `textPayload` JSON wrapper), Google SecOps's `PFSENSE` parser exhibits distinct field mapping behaviors depending on the originating FreeBSD syslog `appname`:

| Syslog `appname` | Facility / Priority | UDM `metadata.event_type` | Hostname Mapping (`principal` vs `intermediary`) | `target.resource.name` | `metadata.event_timestamp` Behavior | `metadata.description` Quirk |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`kernel`** | `0` (`6`) / `14` (`118`) | `STATUS_UPDATE` | **`principal.hostname`** & `principal.asset.hostname` populated.<br>*`intermediary.hostname` is NULL.* | NULL | **BUG:** Overwrites `event_timestamp` with `ingested_timestamp` (+10-15m skew on `Bootup complete` & `link state changed to DOWN`)! | Clean message text (e.g. `"Bootup complete"`, `"ice3: link state changed to DOWN"`). |
| **`syslogd`** *(no `proc_id`)* | `5` (`43` / `46`) | `GENERIC_EVENT` | **`intermediary.hostname`** populated.<br>***`principal.hostname` is NULL!*** | NULL | **BUG:** Overwrites `event_timestamp` with `ingested_timestamp`! | Clean message text (`"sendto: Connection refused"`, `"restart"`). |
| **`root`** | `1` (`13`) | `GENERIC_EVENT` | **`intermediary.hostname`** populated.<br>***`principal.hostname` is NULL!*** | NULL | Uses true syslog / JSON `timestamp`. | **BUG:** Over-captures trailing Cloud Logging JSON (`Bootup complete","timestamp":"..."}`). |
| **`login`** | `4` (`37` / `38`) | `USER_LOGIN` | **`intermediary.hostname`** populated.<br>***`principal.hostname` is NULL!*** | NULL | Uses true syslog / JSON `timestamp`. | Over-captures trailing Cloud Logging JSON (`login on ttyu0 as root","timestamp":"..."}`). |
| **`syslog-ng`** | `5` (`45`) | `GENERIC_EVENT` | Logs **bare short hostname** (`EDGE_FW_01`) instead of FQDN (`EDGE_FW_01.private`). | NULL | Uses true syslog / JSON `timestamp`. | Buffers boot logs in memory (~60s) until WireGuard `tun_wg0` establishes upstream connection (`fd='21'`). |
| **`php_wg`** | `1` (`11` / `13`) | `SETTING_MODIFICATION` | Both `principal.hostname` and `intermediary.hostname` populated. | **`"Wireguard"`** | Uses true syslog / JSON `timestamp`. | Contains script path or `NOTICE [Config] Configuration Change: (system): [pfSense-pkg-WireGuard] ...`. |
| **`php-fpm`** *(WebGUI)* | `1` / `4` | `GENERIC_EVENT` / `STATUS_UPDATE` | `principal.hostname` or `intermediary.hostname`. | **NULL** *(Empty!)* | Uses true syslog / JSON `timestamp`. | Contains WebGUI script path + `Configuration Change: (<actor>): [pfSense-pkg-WireGuard] ...`. |

### Critical Detection Engineering Rules for `PFSENSE`:

1. **Always Coalesce Hostnames**:
   Never bind to `$e.principal.hostname` alone (drops all `root` / `GENERIC_EVENT` logs) or `$e.intermediary.hostname` alone (drops all `kernel` / `STATUS_UPDATE` logs).
   ```text
   strings.coalesce($e.principal.hostname, $e.intermediary.hostname, $e.principal.asset.hostname)
   ```
2. **Never Anchor `metadata.description` at the End (`$`)**:
   Because `GENERIC_EVENT` logs include trailing Cloud Logging JSON (`","timestamp":"2026-09-15T..."}`), exact string comparisons (`=`) and end-anchored regexes (`/Bootup complete$/`) fail. Use start-anchored or unanchored regexes (`re.regex($e.metadata.description, "(?i)^Bootup complete")`).
3. **Normalize Short Hostnames Directly from Event Fields (Direct Event Field Assignment)**:
   When administrators change `System > General Setup > Domain` (e.g. `.corp.internal` -> `.internal`) and reboot, full FQDN grouping treats the firewall as two separate devices. Extract the short appliance name directly wrapping the UDM fields:
   ```text
   $appliance_name = strings.to_upper(
     re.capture(
       strings.coalesce($e.principal.hostname, $e.intermediary.hostname, $e.principal.asset.hostname),
       "^([^.]+)"
     )
   )
   ```

---

## 2. Complete Catalog of WireGuard Config Strings on pfSense Plus 24.11

In pfSense Plus 24.11 (`net/pfSense-pkg-WireGuard`), every `write_config()` call formats the message as:
```text
<script_path>: Configuration Change: (<actor>): [pfSense-pkg-WireGuard] <action_string>
```

### A. Interactive Peer & Tunnel Modifications (`php-fpm` / WebGUI or XMLRPC)
When an authenticated user (`<username>@<source_ip>`) modifies WireGuard via `vpn_wg_peers_edit.php`, `vpn_wg_tunnels_edit.php`, or `vpn_wg_settings.php`:

* **Peer Creation / Modification (`#1 Persistence Vector`):**
  * `[pfSense-pkg-WireGuard] Created peer (<peer_description_or_uuid>).`
  * `[pfSense-pkg-WireGuard] Updated peer (<peer_description_or_uuid>).`
  * `[pfSense-pkg-WireGuard] Enabled peer (<peer_description_or_uuid>).` / `Disabled peer` / `Toggled peer` / `Deleted peer`
* **Tunnel Creation / Modification:**
  * `[pfSense-pkg-WireGuard] Created tunnel (tun_wg<X>).`
  * `[pfSense-pkg-WireGuard] Updated tunnel (tun_wg<X>).`
  * `[pfSense-pkg-WireGuard] Enabled tunnel (tun_wg<X>).` / `Disabled tunnel` / `Toggled tunnel` / `Deleted tunnel`
* **Global Settings:**
  * `[pfSense-pkg-WireGuard] Saved settings.`

### B. Automated System / Boot Sync Strings (`(system)` Actor via `php_wg`)
Fired automatically by `/usr/local/pkg/wireguard/includes/wg_service.inc` under actor **`(system)`** during bootup, package installation/upgrade, or DNS reloads:

* `[pfSense-pkg-WireGuard] Applied package default settings as necessary.`
* `[pfSense-pkg-WireGuard] Installed interface group (WireGuard).`
* `[pfSense-pkg-WireGuard] Installed Unbound ACL group (WireGuard).` / `Updated Unbound ACL group (WireGuard).`
* `[pfSense-pkg-WireGuard] Installed earlyshellcmd(s).`
* `[pfSense-pkg-WireGuard] Deinstalled package components.`

### C. Non-Config Runtime Status Noise (No `Configuration Change:` Prefix)

* `/usr/local/pkg/wireguard/includes/wg_service.inc: Gateway, NONE AVAILABLE` *(Fired during bootup 1 second before `Bootup complete` when WAN gateway is not yet up).*

---

## 3. `filterlog` Port-Scan False Positives: Orphaned DNS Replies (`unbound` RFC 5452) on WireGuard Tunnels

### Architectural & State-Table Mechanics (`tun_wg0` State Resets)
When a Netgate pfSense appliance (`fw-branch-01.internal`, local WireGuard interface `tun_wg0` = `172.16.255.10`) communicates with an upstream VPN gateway/DNS peer (`172.16.255.1` / `VPNGW_HUB_01`):

1. **Outbound Randomized DNS Queries (`unbound` RFC 5452)**:
   - The local `unbound` DNS resolver sends recursive/forwarded queries from `172.16.255.10` to `172.16.255.1:53`.
   - To defend against DNS cache poisoning (RFC 5452 birthday attacks), `unbound` randomizes the client source port across the entire `1024-65535` range (e.g., `2477`, `36783`, `44669`, `57514`, `15643`...).
   - Each outgoing UDP packet creates a temporary state entry in pfSense's `pf` state table (`172.16.255.10:<random_port> -> 172.16.255.1:53`).
2. **State Table Purge / Tunnel Flap (`dpinger` / `/system.php`)**:
   - When `dpinger` detects packet loss or latency spikes on `tun_wg0` (`latency_alarm 500ms loss_alarm 20%`), or when `/system.php` reloads routes/interfaces (`check_reload_status`), pfSense automatically flushes active state table entries associated with that gateway/interface.
3. **Orphaned Inbound DNS Responses Blocked by Default Deny (`1000000103`)**:
   - When the delayed UDP DNS response packets (`src=172.16.255.1:53` -> `dst=172.16.255.10:<random_port>`) and ICMP Echo Replies (`icmp reply`) arrive back at `tun_wg0` after the state flush, `pf` finds no matching state entry.
   - `filterlog` drops every returning packet via the Default Deny IPv4 rule (`tracker=1000000103`, `action=block`, `direction=in`):
     `4,,,1000000103,tun_wg0,match,block,in,4,0x0,,63,0,0,none,17,udp,170,172.16.255.1,172.16.255.10,53,2477,150`
4. **Google SecOps Port-Scan False Positive & Entity Risk Inflation**:
   - Because `filterlog` records the packet as seen on the wire (`src=172.16.255.1:53` -> `dst=172.16.255.10:<random_port>`), Google SecOps's `PFSENSE` parser maps `$e.principal.ip = "172.16.255.1"`, **`$e.principal.port = 53`**, `$e.target.ip = "172.16.255.10"`, and **`$e.target.port = <random_port>`**.
   - Any port-scan rule that counts `count_distinct($e.target.port) > 50` without scoping UDP service response exclusions (`$e.network.ip_protocol = "UDP" and ($e.principal.port = 53 or $e.principal.port = 123)`) or filtering mid-stream TCP data segments (`data_length != "0"`) immediately fires false-positive `Alert` detections and inflates SecOps Risk Analytics (`ENTITY_RISK_CHANGE`) on the firewall's own `tun_wg0` IP. Using `data_length != "0"` instead of blanket TCP flag exclusions ensures `SYN-ACK` (`SA`), `ACK` (`-sA`), and `Maimon` (`-sM`) scans are still caught.
5. **`GCP_FIREWALL` Schema Differences (`0.0.0.0` Hairpin, `resource.name` VM Mapping & `subnetwork_id` Contamination)**:
   - Unlike `PFSENSE`, `GCP_FIREWALL` never populates `additional.fields["tcp_flags"]`, `additional.fields["data_length"]`, `principal.hostname`, or `target.hostname`.
   - **Denied `src_ip = "0.0.0.0"` Probe Exclusion**: Unroutable `0.0.0.0` hairpin/health-check probes (`TCP/8080` against `*-vpn-gw-0-*` VIPs denied by `65534` `deny-all-ingress` rules) collapse 50+ destination VMs into one `$src_ip = "0.0.0.0"` bucket in `Net_Recon_PortScan` unless `$e.principal.ip != "0.0.0.0"` is required.
   - **`principal.resource.name` & `target.resource.name` (Never `hostname`)**: Always extract VM names from `principal.resource.name` and `target.resource.name` (`jsonPayload.instance.vm_name`), and extract the GCP project ID via `re.capture($e.metadata.product_event_type, "^projects/([^/]+)/")` rather than `target.resource_ancestors.product_object_id` (which merges 19-digit numeric `subnetwork_id`s with project IDs).

---

## 4. Serial (`ttyu0`) & Video (`ttyv0`) Console `root` Autologin vs. Human Intrusion Forensics

When a Netgate pfSense Plus appliance boots up, Google SecOps ingests simultaneous `USER_LOGIN` events (`login on ttyv0 as root` and `login on ttyu0 as root`) `1-3 seconds` after `Bootup complete`. Use these four deterministic source-code proofs to distinguish automated `getty` console menu initialization from a human operator logging in via serial console:

1. **FreeBSD `/usr/bin/login` (`usr.bin/login/login.c` Lines 487-511) `fflag` (`-f`) vs. `ROOT LOGIN` (`<37>`) Split**:
   - `/usr/bin/login` always logs `syslog(LOG_INFO, "login on %s as %s", tty, pwd->pw_name)` (`<38>`, `priority="38"`, `severity="INFO"`), **but** checks `if (rootlogin && fflag == 0)` (line 504) before emitting `syslog(LOG_NOTICE, "ROOT LOGIN (%s) ON %s", username, tty)` (`<37>`, `priority="37"`, `severity="NOTICE"`).
   - **Automated Boot Autologin (`fflag == 1`)**: `getty` passes `-fp root` (`fflag = 1`, skip authentication). Line 504 evaluates to **false**, emitting **only** `<38> login on ttyv0/ttyu0 as root` and **never** `<37> ROOT LOGIN (root) ON <tty>`.
   - **Interactive Human `root` Login (`fflag == 0`)**: A human authenticating at a login prompt invokes `login -p root` (`fflag = 0`), which **must** emit both `<38> login on <tty> as root` AND **`<37> ROOT LOGIN (root) ON <tty>`**.
2. **Upstream pfSense `console_configure()` (`src/etc/inc/pfsense-utils.inc` Lines 1364-1408) & `getty` (`libexec/getty/main.c` Lines 332-400)**:
   - Unless **System > Advanced > Admin Access > Console Options > Password protect the console menu** (`<disableconsolemenu>`) is enabled, pfSense writes `"/usr/libexec/getty al.Pc"` for `ttyv0` and `"/usr/libexec/getty al.3wire"` for `ttyu0` into `/etc/ttys`.
   - In `/etc/gettytab` (lines 204-217), `al.Pc` and `al.3wire` define `:al=root:` (`AL = "root"`). In `libexec/getty/main.c`, when `AL` is set, `getty` **completely bypasses `getname()`** (never waiting for serial keystrokes) and immediately executes `execle("/usr/bin/login", "login", "-fp", "root", ...)` as soon as `/etc/pfSense-rc` (lines 711-716) exits `0` and `init(8)` finishes `Performing automatic boot verification...done.`.
3. **Post-Boot Interaction with an Already-Open Console Menu (`src/etc/rc.initial` Lines 89-164)**:
   - If a human connects a serial cable after boot and presses bare `Enter` (`opmode=''`) to wake/refresh the menu or selects `0) Logout`, `/etc/rc.initial` executes `/bin/kill $PPID ; exit` (line 161), terminating the `ttyu0` login process. `init(8)` immediately respawns `getty al.3wire ttyu0`, emitting a **standalone `login on ttyu0 as root` event** (without a matching `ttyv0` or `Bootup complete` event).
   - Selecting options `1..16` executes `/etc/rc.initial.*` scripts (`rc.initial.setports`, `rc.initial.setlanip`, `rc.initial.password`, `rc.initial.reboot`, `/bin/tcsh`, `/usr/local/sbin/pfSsh.php`).
4. **Pre-Outage `kernel` Link-Down vs. Unplanned Power Cycle Triage**:
   - Check `PROCESS_LAUNCH` for `/usr/sbin/cron` (`(root) CMD (/usr/sbin/newsyslog)` runs every 60 seconds at `:00`) and `dhclient` renewals. A multi-minute gap lacking graceful shutdown logs (`rc.shutdown`, `syslogd: exiting on signal 15`) followed by `root: NOTICE Bootup complete` proves an unplanned hard power outage. Remember to inspect raw `receiveTimestamp` / `textPayload` on `STATUS_UPDATE` (`kernel`) events such as `ice3: link state changed to DOWN`, as the `PFSENSE` parser shifts their UDM `metadata.event_timestamp` forward by 10-15 minutes into the middle of the power outage window.

---

## 5. High-Density UDM Hunting Selectors for Netgate pfSense Plus

| Rule / Detection Name | MITRE ATT&CK | UDM `log_type` & Match Keys | High-Density UDM Predicates & False-Positive Exclusions | Window & Additive Scoring | Key Outcome / Triage Artifacts |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`pfsense_power_cycle`**<br>*(Reboot & Domain Mutation Correlation)* | `T1529` | `PFSENSE`<br>`$appliance_name = strings.to_upper(re.capture(strings.coalesce($e.principal.hostname, $e.intermediary.hostname, $e.principal.asset.hostname), "^([^.]+)"))` | • `re.regex($e.metadata.description, "(?i)^Bootup complete")` *(no end `$` anchor to survive JSON bleed-through)* | `$appliance_name over 2h`<br>• Base: `25`<br>• Domain change bonus (`$distinct_fqdn_count > 1`): `+15`<br>• Boot loop bonus (`count >= 3`): `+25` | • `observed_fqdns`: `array_distinct(strings.coalesce(...))`<br>• `ingestion_skew_seconds`: `max(ingested_timestamp) - min(event_timestamp)` |
| **`pfsense_console_root_login`**<br>*(Serial `ttyu0` / VGA `ttyv0` Console Intrusion vs. Boot `autologin`)* | `T1078.003` / `T1091` | `PFSENSE`<br>`$appliance_name` (short hostname from `principal.hostname`, `intermediary.hostname`, `principal.asset.hostname`) | • `$login`: `metadata.event_type = "USER_LOGIN"` (or `principal.application = "login"`) and `re.regex($login.metadata.description, "(?i)(ROOT LOGIN\\s*\\(root\\)\\s*ON\\s*tty\|login on tty[uv][0-9]+ as root)")`<br>• **Boot `getty` (`al.Pc`/`al.3wire`) Autologin Disambiguation**: Join optional `$boot` (`re.regex($boot.metadata.description, "(?i)Bootup complete")`). When `$boot` is present within `30m` (accounting for `STATUS_UPDATE` timestamp skew) and both `ttyv0` and `ttyu0` fire in the same second without `ROOT LOGIN (root) ON`, classify as automated boot `autologin` (`login -fp root`). | `$appliance_name over 30m`<br>• Base boot `ttyv0`+`ttyu0` autologin: `15` (or suppress)<br>• Standalone `ttyu0` (`rc.initial` `Enter`/respawn outside boot): `+45`<br>• Interactive password `ROOT LOGIN (root) ON tty...` (`<37>`): `+70` (`85`) | • `console_ttys`: `re.capture($login.metadata.description, "tty[uv][0-9]+")`<br>• `is_interactive_auth`: `re.regex($login.metadata.description, "ROOT LOGIN")` |
| **`pfsense_wg_config_update`**<br>*(WireGuard Peer/Tunnel Persistence)* | `T1133` | `PFSENSE`<br>`$appliance_name` (short hostname) | • `($e.target.resource.name = "Wireguard" or re.regex($e.metadata.description, "(?i)(\\[pfSense-pkg-WireGuard\\]\|/vpn_wg_)"))`<br>• `re.regex($e.metadata.description, "(?i)Configuration Change:")`<br>• Exclude boot gateway noise: `not re.regex($e.metadata.description, "(?i)gateway")` | `$appliance_name over 5m`<br>• Base `(system)` sync: `25`<br>• Interactive user (`not (system)`): `+40`<br>• Peer/Tunnel created/updated/enabled: `+20` (total `85`) | • `config_actors`: `re.capture($e.metadata.description, "Configuration Change:\\s*\\(([^)]+)\\)")`<br>• `change_summaries` |
| **`Net_Recon_InternalSubnetPortScan`**<br>*(Hardened Vertical Port Scan on `filterlog`)* | `T1595` | `PFSENSE`<br>`event_type = "NETWORK_CONNECTION"`<br>`$src_ip, $target_ip` | • **UDP Orphaned Reply Exclusion**: `not ($e.network.ip_protocol = "UDP" and ($src_port = 53 or $src_port = 123))`<br>• **TCP State-Flush vs Scan Probe**: `not ($e.additional.fields["tcp_flags"] = "R" or $e.additional.fields["tcp_flags"] = "RA")` and `not ($e.network.ip_protocol = "TCP" and $e.additional.fields["data_length"] != "0" and $e.additional.fields["data_length"] != "")` *(0-byte scan probes pass; mid-stream data drops)*<br>• Exclude WireGuard peer IPs (`172.16.255.1`, `172.16.255.10`)<br>• Require `$dest_port < 49152 or action = "BLOCK" or ip_protocol = "TCP"` | `$src_ip, $target_ip over 5m`<br>Threshold: `count_distinct($dest_port) > 50`<br>• Risk score: `if($blocked_count > 10, 75, 50)` | • `pfsense_appliance` (short hostname)<br>• `interfaces`: `$e.additional.fields["interface"]`<br>• `tcp_flags`, `tracker_ids` |
