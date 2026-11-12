"""Core pure-Python evaluation library for Filestore log-based troubleshooting.

Provides network URI resolution, priority-sorted VPC ingress firewall
evaluation, subnet CIDR containment checks, non-destructive nfsExportOptions
merging, instance health evaluation, and report formatting.
"""

import ipaddress
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

_DEFAULT_METRICS_ENV = (
    "agent-skills/1.0 (skill:google-cloud-filestore-log-troubleshooting)"
)


def _load_attribution(
    fallback: str = _DEFAULT_METRICS_ENV, attr_path: Optional[str] = None
) -> str:
  """Loads the attribution token from references/attribution.md."""
  path = attr_path or os.path.join(
      os.path.dirname(os.path.abspath(__file__)),
      "..",
      "references",
      "attribution.md",
  )
  try:
    with open(path, encoding="utf-8") as f:
      match = re.search(
          r'CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="([^"]+)"', f.read()
      )
      if match:
        return match.group(1)
  except OSError:
    pass
  return fallback


METRICS_ENV = _load_attribution()


def resolve_network_info(
    networks: List[Dict[str, Any]], default_project: str
) -> Tuple[str, str, str]:
  """Extracts network name, host project ID (Shared VPC), and primary IP."""
  if not networks:
    return "default", default_project, "UNKNOWN"
  net_uri = networks[0].get("network", "")
  parts = net_uri.split("/")
  if "projects" in parts and len(parts) - parts.index("projects") >= 2:
    host_project = parts[parts.index("projects") + 1]
    vpc_network = parts[-1]
  else:
    host_project = default_project
    vpc_network = parts[-1] if net_uri else "default"
  ip_addrs = networks[0].get("ipAddresses", [])
  return vpc_network, host_project, (ip_addrs[0] if ip_addrs else "UNKNOWN")


def parse_instance_meta(meta: Dict[str, Any], project: str) -> Dict[str, Any]:
  """Extracts normalized Filestore instance metadata fields."""
  vpc, host_proj, ip = resolve_network_info(meta.get("networks", []), project)
  shares = meta.get("fileShares", [])
  share = shares[0] if shares else {}
  parts = meta.get("name", "").split("/")
  return {
      "id": parts[5] if len(parts) >= 6 else meta.get("name", ""),
      "location": parts[3] if len(parts) >= 6 else "unknown",
      "tier": meta.get("tier", "UNKNOWN"),
      "state": meta.get("state", "UNKNOWN"),
      "vpc": vpc,
      "host_proj": host_proj,
      "ip": ip,
      "share": share.get("name", "share"),
      "capacity_gb": int(share.get("capacityGb", 1024)),
      "exports": share.get("nfsExportOptions", []),
  }


def _port_matches(port: int, ports: List[str]) -> bool:
  """Checks if port matches any port spec (e.g. '2049' or '2045-2050')."""
  if not ports:
    return True
  for p in ports:
    lo, _, hi = p.partition("-")
    try:
      if int(lo) <= port <= int(hi or lo):
        return True
    except ValueError:
      continue
  return False


def check_port_allowed(
    rules: List[Dict[str, Any]], client_ip: Optional[str], port: int = 2049
) -> Tuple[bool, Optional[str], Optional[str]]:
  """Evaluates whether TCP port is permitted by priority-sorted rules."""
  target_net = None
  if client_ip:
    try:
      target_net = ipaddress.ip_network(client_ip, strict=False)
    except ValueError:
      pass

  for r in sorted(rules, key=lambda x: x.get("priority", 1000)):
    is_deny = "denied" in r
    blocks = r.get("denied", []) if is_deny else r.get("allowed", [])
    if not any(
        b.get("IPProtocol", "").lower() in ("tcp", "all")
        and _port_matches(port, b.get("ports", []))
        for b in blocks
    ):
      continue

    src_ranges = r.get("sourceRanges", [])
    ip_matched = (
        not target_net
        or (target_net.version == 4 and "0.0.0.0/0" in src_ranges)
        or (target_net.version == 6 and "::/0" in src_ranges)
    )
    if not ip_matched and target_net:
      for sr in src_ranges:
        try:
          sr_net = ipaddress.ip_network(sr, strict=False)
          if (is_deny and target_net.overlaps(sr_net)) or (
              not is_deny and target_net.subnet_of(sr_net)
          ):
            ip_matched = True
            break
        except (ValueError, TypeError):
          continue

    if ip_matched:
      name, prio = r.get("name", "unnamed-rule"), r.get("priority", 1000)
      if is_deny:
        msg = f"Blocked by explicit DENY rule '{name}' (priority {prio})"
        return False, name, msg
      return True, name, f"Allowed by rule '{name}' (priority {prio})"

  return False, None, "No matching ingress firewall rule found allowing port"


def check_export_acl(
    export_options: List[Dict[str, Any]], client_ip: str
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
  """Validates whether client_ip / CIDR is permitted by nfsExportOptions."""
  if not export_options:
    return True, "Default allowlist (0.0.0.0/0) active with READ_WRITE", None
  try:
    target_net = ipaddress.ip_network(client_ip, strict=False)
  except ValueError:
    return False, f"Invalid client IP format: {client_ip}", None

  for opt in export_options:
    for r in opt.get("ipRanges", []):
      try:
        if target_net.subnet_of(ipaddress.ip_network(r, strict=False)):
          mode = opt.get("accessMode", "READ_WRITE")
          squash = opt.get("squashMode", "NO_ROOT_SQUASH")
          msg = f"Matched rule '{r}' (mode: {mode}, squash: {squash})"
          return True, msg, opt
      except (ValueError, TypeError):
        continue
  msg = "Client IP is not covered by any allowed CIDR in nfsExportOptions"
  return False, msg, None


def build_non_destructive_export_json(
    existing_options: List[Dict[str, Any]],
    new_cidr: str,
    share_name: str,
    capacity_gb: int,
) -> Dict[str, Any]:
  """Generates non-destructive merged --flags-file payload preserving rules."""
  merged = []
  for opt in existing_options or []:
    entry: Dict[str, Any] = {
        "access-mode": opt.get(
            "accessMode", opt.get("access-mode", "READ_WRITE")
        ),
        "ip-ranges": list(opt.get("ipRanges", opt.get("ip-ranges", []))),
        "squash-mode": opt.get(
            "squashMode", opt.get("squash-mode", "NO_ROOT_SQUASH")
        ),
    }
    if "anonUid" in opt or "anon-uid" in opt:
      entry["anon-uid"] = opt.get("anonUid", opt.get("anon-uid"))
    if "anonGid" in opt or "anon-gid" in opt:
      entry["anon-gid"] = opt.get("anonGid", opt.get("anon-gid"))
    merged.append(entry)

  merged.append({
      "access-mode": "READ_WRITE",
      "ip-ranges": [new_cidr],
      "squash-mode": "NO_ROOT_SQUASH",
  })
  return {
      "--file-share": {
          "name": share_name,
          "capacity": capacity_gb,
          "nfs-export-options": merged,
      }
  }


def build_acl_remediation(
    instance: str, location: str, project: str, info: Dict[str, Any], cidr: str
) -> Dict[str, Any]:
  """Builds non-destructive export ACL update command descriptor."""
  payload = build_non_destructive_export_json(
      info["exports"], cidr, info["share"], info["capacity_gb"]
  )
  return {
      "type": "EXPORT_ACL",
      "desc": (
          f"Non-destructively append client subnet '{cidr}' to Filestore"
          " nfsExportOptions"
      ),
      "payload": payload,
      "cmd": (
          "PATCH_FILE=$(mktemp /tmp/filestore-export-patch.XXXXXX.json)\n"
          "cat << 'EOF' >"
          f' "${{PATCH_FILE}}"\n{json.dumps(payload, indent=2)}\nEOF\n'
          f'CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="{METRICS_ENV}" \\\n'
          f"gcloud filestore instances update {instance} \\\n"
          f"    --location={location} --project={project} \\\n"
          '    --flags-file="${PATCH_FILE}"\nrm -f "${PATCH_FILE}"'
      ),
  }


def build_fw_remediation(info: Dict[str, Any], cidr: str) -> Dict[str, Any]:
  """Builds VPC ingress firewall rule creation command descriptor."""
  rule_name = f"allow-{info['vpc']}-filestore-nfs"
  fw_args = [
      "gcloud",
      "compute",
      "firewall-rules",
      "create",
      rule_name,
      f"--network={info['vpc']}",
      "--direction=INGRESS",
      "--priority=1000",
      "--action=ALLOW",
      "--rules=tcp:2049,udp:2049,tcp:111,udp:111",
      f"--source-ranges={cidr}",
      f"--project={info['host_proj']}",
  ]
  return {
      "type": "FIREWALL",
      "desc": (
          "Create VPC ingress firewall rule allowing NFS ports 2049 & 111 from"
          f" '{cidr}'"
      ),
      "exec_args": fw_args,
      "cmd": (
          f'CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="{METRICS_ENV}" \\\n'
          f"gcloud compute firewall-rules create {rule_name} \\\n   "
          f' --network="{info["vpc"]}" --direction=INGRESS --priority=1000 \\\n'
          "    --action=ALLOW --rules=tcp:2049,udp:2049,tcp:111,udp:111 \\\n  "
          f'  --source-ranges="{cidr}" --project="{info["host_proj"]}"'
      ),
  }


def evaluate_instance(
    info: Dict[str, Any],
    fw_rules: List[Dict[str, Any]],
    target_eval_ip: Optional[str],
    target_cidr: Optional[str],
    audit_logs: List[Dict[str, Any]],
    project: str,
) -> Dict[str, Any]:
  """Evaluates instance state, export ACL, firewall rules, and audit drift."""
  root_causes: List[str] = []
  remediations: List[Dict[str, Any]] = []
  blockers: List[str] = []

  if info["state"] != "READY":
    root_causes.append(
        f"Filestore instance is in state '{info['state']}' (must be READY to"
        " accept NFS mounts)."
    )
    blockers.append(f"State: {info['state']}")

  acl_ok, acl_msg, matched = True, "Default/untested", None
  if target_eval_ip:
    acl_ok, acl_msg, matched = check_export_acl(info["exports"], target_eval_ip)
    if not acl_ok:
      root_causes.append(
          "EACCES (Permission Denied by Server): Client IP is not in Filestore"
          " export allowlist."
      )
      blockers.append("ACL: Client IP rejected")
      remediations.append(
          build_acl_remediation(
              info["id"],
              info["location"],
              project,
              info,
              target_cidr or "10.128.0.0/20",
          )
      )

  port_2049_open, _, reason_2049 = check_port_allowed(
      fw_rules, target_eval_ip, port=2049
  )
  port_111_open, _, _ = check_port_allowed(fw_rules, target_eval_ip, port=111)
  if not port_2049_open:
    root_causes.append(
        "ETIMEDOUT (Connection Timed Out): VPC firewall does not permit ingress"
        " on NFS port 2049."
    )
    blockers.append("FW: Port 2049 blocked")
    remediations.append(build_fw_remediation(info, target_cidr or "10.0.0.0/8"))

  inst_drift = any(
      info["id"] in log.get("protoPayload", {}).get("resourceName", "")
      for log in audit_logs
  )
  overall = f"BLOCKED ({', '.join(blockers)})" if blockers else "HEALTHY"
  if inst_drift:
    overall += " [Audit: Recent config drift]"

  return {
      "root_causes": root_causes,
      "remediations": remediations,
      "acl_ok": acl_ok,
      "acl_msg": acl_msg,
      "matched_rule": matched,
      "port_2049_open": port_2049_open,
      "reason_2049": reason_2049,
      "port_111_open": port_111_open,
      "summary_row": {
          "instance": info["id"],
          "location": info["location"],
          "tier": info["tier"],
          "ip": info["ip"],
          "network": info["vpc"],
          "port_2049": "OPEN" if port_2049_open else "BLOCKED",
          "acl": "PASS" if acl_ok else "FAIL",
          "status": overall,
      },
  }


def format_single_report(
    info: Dict[str, Any],
    ev: Dict[str, Any],
    target_eval_ip: Optional[str],
    audit_logs: List[Dict[str, Any]],
    csi_errors: List[str],
) -> str:
  """Formats the 4-phase narrative diagnostic report for a single instance."""
  subsep = "-" * 80
  lines = [
      f"    • State        : {info['state']}",
      f"    • Tier         : {info['tier']}",
      f"    • Filestore IP : {info['ip']}",
      f"    • VPC Network  : {info['vpc']} (Host Project: {info['host_proj']})",
      f"    • Share Name   : {info['share']} ({info['capacity_gb']} GiB)",
      f"    • Export ACLs  : {len(info['exports'])} rule(s) configured\n",
  ]
  if target_eval_ip:
    lines.append(
        f"[*] Step 2: Evaluating Export ACLs for '{target_eval_ip}'..."
    )
    if ev["acl_ok"]:
      lines.append(f"    [PASS] Export ACL: {ev['acl_msg']}")
      matched = ev["matched_rule"] or {}
      if matched.get("accessMode") == "READ_ONLY":
        lines.append("    [NOTE] Share is READ_ONLY. Writes fail with EROFS.")
      if matched.get("squashMode") == "ROOT_SQUASH":
        lines.append("    [NOTE] ROOT_SQUASH active. UID 0 maps to nobody.")
    else:
      lines.append(f"    [FAIL] Export ACL Violation: {ev['acl_msg']}")
  else:
    lines.append(
        "[*] Step 2: Client IP not provided. Active export allowlists:"
    )
    for idx, opt in enumerate(info["exports"], 1):
      lines.append(
          f"    Rule #{idx}: IP={opt.get('ipRanges')},"
          f" Mode={opt.get('accessMode')}"
      )
    if not info["exports"]:
      lines.append("    (Default 0.0.0.0/0 allowlist active with READ_WRITE)")
    lines.append("")

  lines.append(
      f"[*] Step 3: Inspecting VPC ingress firewall rules on '{info['vpc']}'"
      f" ({info['host_proj']})..."
  )
  p_tag = "[PASS]" if ev["port_2049_open"] else "[FAIL]"
  p_txt = "Ingress NFS TCP Port 2049" + (
      "" if ev["port_2049_open"] else " is BLOCKED"
  )
  lines.append(f"    {p_tag} {p_txt}: {ev['reason_2049']}")
  if not ev["port_111_open"]:
    lines.append(
        "    [WARN] Ingress RPC portmapper (TCP/UDP 111) not explicitly allowed"
        " (required for NFSv3)."
    )

  lines.append(
      "\n[*] Step 4: Scanning Cloud Logging for recent drift and client"
      " errors..."
  )
  if audit_logs:
    lines.append(
        f"    • Detected {len(audit_logs)} administrative change(s) in past"
        " 24h:"
    )
    for log in audit_logs:
      ts = log.get("timestamp", "")
      principal = (
          log.get("protoPayload", {})
          .get("authenticationInfo", {})
          .get("principalEmail", "Unknown")
      )
      method = log.get("protoPayload", {}).get("methodName", "").split(".")[-1]
      lines.append(f"      - [{ts}] {method} by {principal}")
  else:
    lines.append(
        "    • No administrative drift detected on instance in past 24h."
    )

  for err_msg in csi_errors[:2]:
    lines.append(f"    • Recent GKE CSI driver error: {err_msg}")

  lines.append(f"\n{subsep}\n 📋 DIAGNOSTIC SUMMARY\n{subsep}")
  if not ev["root_causes"]:
    lines.append(
        "  ✅ All baseline network firewall and export ACL checks PASSED.\n"
        "     Filestore instance is healthy and reachable on port 2049."
    )
  else:
    lines.append(f"  ❌ Identified {len(ev['root_causes'])} Blocker(s):")
    for idx, rc in enumerate(ev["root_causes"], 1):
      lines.append(f"     {idx}. {rc}")
    lines.append(
        f"\n{subsep}\n 🛠️ RECOMMENDED REMEDIATION COMMAND(S)\n{subsep}"
    )
    for idx, rem in enumerate(ev["remediations"], 1):
      lines.append(
          f" Action {idx} ({rem['type']}): {rem['desc']}\n\n{rem['cmd']}\n"
      )
  return "\n".join(lines)
