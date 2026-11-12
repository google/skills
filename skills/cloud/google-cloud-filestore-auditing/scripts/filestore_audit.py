#!/usr/bin/env python3
"""Google Cloud Filestore Comprehensive Audit & Remediation Engine.

Audits Google Cloud Filestore instances across GCP projects for:
1. Disaster Recovery & Backup Protection (unprotected shares & stale backups)
2. Security & Access Governance (NFS export options, 0.0.0.0/0 exposure,
ROOT_SQUASH)
3. Reliability & Zone Isolation Compliance (Physical Zone Isolation PZI/PZS,
performance limits)
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

_DEFAULT_METRICS_ENV = (
    "agent-skills/1.0 (skill:google-cloud-filestore-auditing)"
)
DEFAULT_STALE_BACKUP_DAYS = 7


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


def run_command(cmd: List[str]) -> Tuple[int, str, str]:
  """Executes a subprocess command with attribution and returns (returncode, stdout, stderr)."""
  env = os.environ.copy()
  env["CLOUDSDK_METRICS_REQUEST_ATTRIBUTION"] = METRICS_ENV
  try:
    proc = subprocess.run(
        cmd, capture_output=True, text=True, check=False, env=env
    )
    return proc.returncode, proc.stdout, proc.stderr
  except (OSError, subprocess.SubprocessError) as e:
    return 1, "", str(e)


def parse_rfc3339_timestamp(ts_str: str) -> Optional[datetime.datetime]:
  """Parses RFC3339 timestamp strings to datetime objects."""
  if not ts_str:
    return None
  ts_clean = re.sub(r"\.\d+", "", ts_str).replace("Z", "+00:00")
  try:
    return datetime.datetime.fromisoformat(ts_clean)
  except ValueError:
    return None


class FilestoreAuditor:
  """Auditor engine for Google Cloud Filestore fleets."""

  def __init__(
      self,
      project_id: str,
      instance_id: Optional[str] = None,
      location: str = "-",
      stale_backup_days: int = DEFAULT_STALE_BACKUP_DAYS,
  ):
    self.project_id = project_id
    self.target_instance = instance_id
    self.location = location
    self.stale_backup_days = stale_backup_days

  def fetch_instances(self) -> List[Dict[str, Any]]:
    """Fetches all Filestore instances across locations in the project."""
    cmd = [
        "gcloud",
        "filestore",
        "instances",
        "list",
        f"--project={self.project_id}",
        "--format=json",
    ]
    rc, stdout, stderr = run_command(cmd)
    if rc != 0:
      raise RuntimeError(f"Failed to fetch instances: {stderr.strip()}")
    try:
      instances = json.loads(stdout) if stdout.strip() else []
      if self.target_instance:
        instances = [
            i
            for i in instances
            if i.get("name", "").split("/")[-1] == self.target_instance
        ]
      return instances
    except json.JSONDecodeError:
      return []

  def fetch_backups(self) -> List[Dict[str, Any]]:
    """Fetches all Filestore backups across all regions in the project."""
    # Note: gcloud filestore backups list without --region lists all backups
    # across the project. Do NOT pass --location=- as it is unsupported.
    cmd = [
        "gcloud",
        "filestore",
        "backups",
        "list",
        f"--project={self.project_id}",
        "--format=json",
    ]
    rc, stdout, stderr = run_command(cmd)
    if rc != 0:
      raise RuntimeError(f"Failed to fetch backups: {stderr.strip()}")
    try:
      return json.loads(stdout) if stdout.strip() else []
    except json.JSONDecodeError as e:
      raise RuntimeError(f"Failed to parse backups JSON output: {e}") from e

  def _audit_disaster_recovery(
      self,
      inst_name: str,
      share_name: str,
      loc_flag: str,
      backup_region: str,
      matched_backups: List[Dict[str, Any]],
  ) -> Tuple[List[Dict[str, Any]], str, Optional[int]]:
    """Evaluates disaster recovery and backup coverage for a single instance."""
    findings: List[Dict[str, Any]] = []
    backup_count = len(matched_backups)
    latest_backup_date = "None"
    days_since_backup = None

    if backup_count == 0:
      findings.append({
          "category": "Disaster Recovery",
          "severity": "HIGH",
          "check": "Missing Backup Protection",
          "message": (
              f"Instance has 0 backups on file share '{share_name}'. "
              "Disaster recovery is not configured."
          ),
          "remediation": (
              f"gcloud filestore backups create {inst_name}-backup-$(date"
              f" +%Y%m%d) --project={self.project_id} --instance={inst_name}"
              f" --file-share={share_name} {loc_flag} --region={backup_region}"
          ),
      })
    else:
      parsed_dates = []
      for b in matched_backups:
        c_time = parse_rfc3339_timestamp(b.get("createTime", ""))
        if c_time:
          parsed_dates.append((c_time, b))

      if parsed_dates:
        parsed_dates.sort(key=lambda x: x[0], reverse=True)
        latest_dt, _ = parsed_dates[0]
        latest_backup_date = latest_dt.strftime("%Y-%m-%d %H:%M UTC")
        days_since_backup = (
            datetime.datetime.now(datetime.timezone.utc) - latest_dt
        ).days

        if days_since_backup > self.stale_backup_days:
          findings.append({
              "category": "Disaster Recovery",
              "severity": "MEDIUM",
              "check": "Stale Backup",
              "message": (
                  f"Latest backup is {days_since_backup} days old "
                  f"(exceeds SLA threshold of {self.stale_backup_days} days)."
              ),
              "remediation": (
                  "Take an updated backup snapshot or configure automated "
                  "scheduled backups via Cloud Scheduler."
              ),
          })

    return findings, latest_backup_date, days_since_backup

  def _audit_security(
      self, primary_share: Dict[str, Any]
  ) -> List[Dict[str, Any]]:
    """Evaluates security access governance (NFS exports, root squashing)."""
    findings: List[Dict[str, Any]] = []
    export_rules = primary_share.get("nfsExportOptions", [])
    if not export_rules:
      findings.append({
          "category": "Security",
          "severity": "MEDIUM",
          "check": "Default Open NFS Export",
          "message": (
              "No explicit NFS export options configured. The share defaults"
              " to open client access within the VPC network with"
              " NO_ROOT_SQUASH."
          ),
          "remediation": (
              "Configure explicit nfsExportOptions restricting ipRanges and "
              "enforcing ROOT_SQUASH under advanced access control."
          ),
      })
      return findings

    for idx, rule in enumerate(export_rules):
      ip_ranges = rule.get("ipRanges", [])
      squash_mode = rule.get("squashMode", "SQUASH_MODE_UNSPECIFIED")
      access_mode = rule.get("accessMode", "ACCESS_MODE_UNSPECIFIED")

      is_world_exposed = any(
          ip in ["0.0.0.0/0", "0.0.0.0", "::/0"] for ip in ip_ranges
      )
      if is_world_exposed:
        findings.append({
            "category": "Security",
            "severity": "CRITICAL" if access_mode == "READ_WRITE" else "HIGH",
            "check": "Overly Permissive NFS Network Export",
            "message": (
                f"Export rule #{idx+1} exposes share to 0.0.0.0/0 (all IPs) "
                f"with accessMode='{access_mode}'."
            ),
            "remediation": (
                "Restrict ipRanges to specific authorized VPC subnet CIDRs or"
                " GKE node pool IP blocks."
            ),
        })

      if squash_mode == "NO_ROOT_SQUASH":
        sec_sev = "CRITICAL" if is_world_exposed else "HIGH"
        findings.append({
            "category": "Security",
            "severity": sec_sev,
            "check": "Missing Root Squashing (NO_ROOT_SQUASH)",
            "message": (
                f"Export rule #{idx+1} has squashMode='NO_ROOT_SQUASH'."
                " Remote root clients retain superuser UID 0 privileges on"
                " the share."
            ),
            "remediation": (
                "Change squashMode to 'ROOT_SQUASH' and specify anonUid:"
                " 65534 / anonGid: 65534 to enforce least-privilege POSIX"
                " mapping."
            ),
        })

    return findings

  def _audit_compliance(
      self, inst: Dict[str, Any], tier: str
  ) -> Tuple[List[Dict[str, Any]], bool, bool]:
    """Evaluates architectural reliability and zone isolation compliance (PZI/PZS)."""
    findings: List[Dict[str, Any]] = []
    satisfies_pzi = inst.get("satisfiesPzi", False)
    satisfies_pzs = inst.get("satisfiesPzs", False)

    if not satisfies_pzi:
      findings.append({
          "category": "Compliance",
          "severity": "MEDIUM",
          "check": "Physical Zone Isolation (PZI) Non-Compliant",
          "message": (
              "Instance does not satisfy Physical Zone Isolation (PZI) "
              f"(satisfiesPzi={satisfies_pzi})."
          ),
          "remediation": (
              "Provision replacement instances in PZI-compliant zones or"
              " migrate to Regional tier."
          ),
      })

    if tier in ["ENTERPRISE", "REGIONAL"] and not satisfies_pzs:
      findings.append({
          "category": "Compliance",
          "severity": "HIGH",
          "check": "Physical Zone Separation (PZS) Non-Compliant",
          "message": (
              "Enterprise/Regional tier instance does not satisfy Physical"
              f" Zone Separation (satisfiesPzs={satisfies_pzs}). Replicas may"
              " share physical facilities."
          ),
          "remediation": (
              "Verify multi-zone configuration across distinct physical domains"
              " within the region."
          ),
      })

    return findings, satisfies_pzi, satisfies_pzs

  def audit_instance(
      self, inst: Dict[str, Any], project_backups: List[Dict[str, Any]]
  ) -> Dict[str, Any]:
    """Runs all audit checks against a single Filestore instance."""
    full_name = inst.get("name", "")
    inst_name = full_name.split("/")[-1] if "/" in full_name else full_name
    parts = full_name.split("/")
    inst_location = parts[3] if len(parts) >= 4 else "unknown"
    tier = inst.get("tier", "UNKNOWN")
    file_shares = inst.get("fileShares", [])
    networks = inst.get("networks", [])

    primary_share = file_shares[0] if file_shares else {}
    share_name = primary_share.get("name", "vol1")
    capacity_gb = primary_share.get("capacityGb", "N/A")

    # Determine location type and backup target region
    is_regional = (
        tier in ["ENTERPRISE", "REGIONAL"] or len(inst_location.split("-")) < 3
    )
    if is_regional:
      backup_region = inst_location
      loc_flag = f"--instance-location={inst_location}"
    else:
      loc_parts = inst_location.split("-")
      backup_region = (
          f"{loc_parts[0]}-{loc_parts[1]}"
          if len(loc_parts) >= 2
          else inst_location
      )
      loc_flag = f"--instance-zone={inst_location}"

    # Match backups to instance
    matched_backups = []
    for b in project_backups:
      src_inst = b.get("sourceInstance", "")
      if src_inst == full_name or (
          src_inst and full_name.endswith(src_inst.strip("/"))
      ):
        matched_backups.append(b)

    dr_findings, latest_backup_date, days_since_backup = (
        self._audit_disaster_recovery(
            inst_name, share_name, loc_flag, backup_region, matched_backups
        )
    )
    sec_findings = self._audit_security(primary_share)
    comp_findings, satisfies_pzi, satisfies_pzs = self._audit_compliance(
        inst, tier
    )

    findings = dr_findings + sec_findings + comp_findings

    reserved_ip_range = "N/A"
    connect_mode = "DIRECT_PEERING"
    if networks:
      reserved_ip_range = networks[0].get("reservedIpRange", "N/A")
      connect_mode = networks[0].get("connectMode", "DIRECT_PEERING")

    perf_limits = inst.get("performanceLimits", {})
    max_write_iops = perf_limits.get("maxWriteIops", "N/A")
    max_read_throughput_bps = perf_limits.get("maxReadThroughputBps", "0")
    try:
      throughput_mb = int(max_read_throughput_bps) // (1024 * 1024)
      max_throughput = f"{throughput_mb} MB/s" if throughput_mb > 0 else "N/A"
    except (ValueError, TypeError):
      max_throughput = "N/A"

    return {
        "instance_id": inst_name,
        "location": inst_location,
        "is_regional": is_regional,
        "backup_region": backup_region,
        "tier": tier,
        "capacity_gb": capacity_gb,
        "file_share": share_name,
        "reserved_ip_range": reserved_ip_range,
        "connect_mode": connect_mode,
        "max_write_iops": max_write_iops,
        "max_throughput": max_throughput,
        "satisfies_pzi": satisfies_pzi,
        "satisfies_pzs": satisfies_pzs,
        "backup_count": len(matched_backups),
        "latest_backup_date": latest_backup_date,
        "days_since_backup": days_since_backup,
        "findings": findings,
    }

  def run_audit(self) -> Dict[str, Any]:
    """Executes the full audit across instances and returns structured report."""
    instances = self.fetch_instances()
    backups = self.fetch_backups()

    audited_instances = [
        self.audit_instance(inst, backups) for inst in instances
    ]

    total_instances = len(audited_instances)
    crit_count = 0
    high_count = 0
    med_count = 0
    for i in audited_instances:
      for f in i["findings"]:
        sev = f.get("severity")
        if sev == "CRITICAL":
          crit_count += 1
        elif sev == "HIGH":
          high_count += 1
        elif sev == "MEDIUM":
          med_count += 1

    unprotected_backups = sum(
        1 for i in audited_instances if i["backup_count"] == 0
    )
    pzi_compliant = sum(1 for i in audited_instances if i["satisfies_pzi"])

    if crit_count > 0:
      posture_grade = "Grade F (Critical Security Exposures Detected)"
      status_badge = "🔴 CRITICAL RISK"
    elif high_count > 0:
      posture_grade = "Grade C (Action Required - High Risk Findings)"
      status_badge = "🟠 ELEVATED RISK"
    elif med_count > 0:
      posture_grade = "Grade B (Moderate - Configuration Gaps Identified)"
      status_badge = "🟡 MODERATE"
    else:
      posture_grade = "Grade A (Healthy & Compliant)"
      status_badge = "🟢 HEALTHY"

    if total_instances > 0:
      protected_ratio = (
          total_instances - unprotected_backups
      ) / total_instances
      coverage_pct = round(protected_ratio * 100, 1)
    else:
      coverage_pct = 100.0

    return {
        "project_id": self.project_id,
        "total_instances": total_instances,
        "posture_grade": posture_grade,
        "status_badge": status_badge,
        "metrics": {
            "critical_findings": crit_count,
            "high_findings": high_count,
            "medium_findings": med_count,
            "unprotected_instances": unprotected_backups,
            "pzi_compliant_count": pzi_compliant,
            "backup_coverage_pct": coverage_pct,
        },
        "instances": audited_instances,
    }


def _render_scorecard(report: Dict[str, Any]) -> List[str]:
  """Renders the Executive Posture Scorecard section."""
  lines: List[str] = [
      f"## Executive Posture Scorecard: `{report['project_id']}`",
      "",
      "| Metric | Status | Details |",
      "| :--- | :--- | :--- |",
      (
          f"| **Overall Health Posture** | **{report['status_badge']}** |"
          f" {report['posture_grade']} |"
      ),
      (
          f"| **Instances Audited** | `{report['total_instances']}` | Total"
          " Filestore instances evaluated |"
      ),
  ]
  m = report["metrics"]
  lines.append(
      f"| **Backup Protection Rate** | **{m['backup_coverage_pct']}%** |"
      f" `{report['total_instances'] - m['unprotected_instances']}/{report['total_instances']}`"
      " instances have active backups |"
  )
  lines.append(
      f"| **Critical & High Security Findings** | `{m['critical_findings']}"
      f" Critical, {m['high_findings']} High` | Open exports, root squash, or"
      " missing backups |"
  )
  lines.append(
      "| **PZI Isolation Compliance** |"
      f" `{m['pzi_compliant_count']}/{report['total_instances']}` | Physical"
      " Zone Isolation adherence |"
  )
  lines.append("")
  return lines


def _render_findings_matrix(report: Dict[str, Any]) -> List[str]:
  """Renders the Priority Findings & Remediation Matrix section."""
  lines: List[str] = ["## Priority Findings & Remediation Matrix", ""]
  all_findings = []
  for inst in report["instances"]:
    for f in inst["findings"]:
      all_findings.append((inst["instance_id"], f))

  if not all_findings:
    lines.append(
        "🎉 **No security, compliance, or backup risks detected! All instances"
        " are compliant.**"
    )
    lines.append("")
    return lines

  sev_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
  all_findings.sort(key=lambda x: sev_order.get(x[1]["severity"], 99))

  lines.append(
      "| Severity | Instance ID | Category | Finding Description |"
      " Remediation Plan |"
  )
  lines.append("| :--- | :--- | :--- | :--- | :--- |")
  for inst_id, f in all_findings:
    sev_emoji = {
        "CRITICAL": "🚨 **CRITICAL**",
        "HIGH": "⚠️ **HIGH**",
        "MEDIUM": "ℹ️ **MEDIUM**",
        "LOW": "🟢 **LOW**",
    }.get(f["severity"], f["severity"])
    lines.append(
        f"| {sev_emoji} | `{inst_id}` | {f['category']} | {f['message']} |"
        f" {f['remediation']} |"
    )
  lines.append("")
  return lines


def _render_inventory_table(report: Dict[str, Any]) -> List[str]:
  """Renders the Filestore Instance Inventory & Compliance Status table."""
  lines: List[str] = [
      "## Filestore Instance Inventory & Compliance Status",
      "",
      (
          "| Instance ID | Location | Tier | Capacity | Reserved CIDR | Write"
          " IOPS | Throughput | PZI | PZS | Backups | Latest Backup |"
      ),
      (
          "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
          " :--- | :--- |"
      ),
  ]
  for i in report["instances"]:
    pzi_str = "✅ Yes" if i["satisfies_pzi"] else "❌ No"
    if i["tier"] in ["REGIONAL", "ENTERPRISE"]:
      pzs_str = "✅ Yes" if i["satisfies_pzs"] else "❌ No"
    else:
      pzs_str = "N/A"
    b_count_str = (
        "🔴 0" if i["backup_count"] == 0 else f"✅ {i['backup_count']}"
    )
    lines.append(
        f"| `{i['instance_id']}` | `{i['location']}` | `{i['tier']}` |"
        f" `{i['capacity_gb']} GiB` | `{i['reserved_ip_range']}` |"
        f" `{i['max_write_iops']}` | `{i['max_throughput']}` | {pzi_str} |"
        f" {pzs_str} | {b_count_str} | {i['latest_backup_date']} |"
    )
  lines.append("")
  return lines


def _render_remediation_actions(report: Dict[str, Any]) -> List[str]:
  """Renders Automated Remediation Actions (Disaster Recovery) section."""
  unprotected = [i for i in report["instances"] if i["backup_count"] == 0]
  if not unprotected:
    return []

  lines: List[str] = [
      "## Automated Remediation Actions (Disaster Recovery)",
      "",
      (
          "To create baseline backups for unprotected instances, execute the"
          " following commands:"
      ),
      "```bash",
  ]
  for i in unprotected:
    loc_flag = (
        f"--instance-location={i['location']}"
        if i["is_regional"]
        else f"--instance-zone={i['location']}"
    )
    lines.append(
        f'CLOUDSDK_METRICS_REQUEST_ATTRIBUTION="{METRICS_ENV}" \\\n'
        f"gcloud filestore backups create {i['instance_id']}-backup-$(date"
        " +%Y%m%d) \\\n"
        f"    --project={report['project_id']} \\\n"
        f"    --instance={i['instance_id']} \\\n"
        f"    --file-share={i['file_share']} \\\n"
        f"    {loc_flag} \\\n"
        f"    --region={i['backup_region']}"
    )
  lines.append("```")
  lines.append("")
  lines.append(
      "> **Confirmation Required**: Would you like me to execute these backup"
      " creation commands for the unprotected instances? Please confirm to"
      " proceed."
  )
  lines.append("")
  return lines


def render_markdown_report(report: Dict[str, Any]) -> str:
  """Renders the audit report in clean GitHub-flavored markdown."""
  lines: List[str] = [
      f"# Filestore Comprehensive Audit Report: `{report['project_id']}`",
      "",
  ]
  lines.extend(_render_scorecard(report))
  lines.extend(_render_findings_matrix(report))
  lines.extend(_render_inventory_table(report))
  lines.extend(_render_remediation_actions(report))
  return "\n".join(lines)


def main():
  parser = argparse.ArgumentParser(
      description="Google Cloud Filestore Comprehensive Audit Engine."
  )
  parser.add_argument(
      "--project", required=True, help="GCP Project ID to audit"
  )
  parser.add_argument(
      "--instance", help="Specific Filestore Instance ID (optional)"
  )
  parser.add_argument(
      "--location", default="-", help="GCP zone or region (default: '-')"
  )
  parser.add_argument(
      "--stale-backup-days",
      type=int,
      default=DEFAULT_STALE_BACKUP_DAYS,
      help=(
          "Threshold in days to flag stale backups"
          f" (default: {DEFAULT_STALE_BACKUP_DAYS})"
      ),
  )
  parser.add_argument(
      "--format",
      choices=["markdown", "json"],
      default="markdown",
      help="Output format (markdown or json)",
  )

  args = parser.parse_args()

  auditor = FilestoreAuditor(
      project_id=args.project,
      instance_id=args.instance,
      location=args.location,
      stale_backup_days=args.stale_backup_days,
  )

  try:
    report = auditor.run_audit()
  except (RuntimeError, ValueError, OSError, json.JSONDecodeError) as e:
    err_msg = str(e)
    if args.format == "json":
      print(json.dumps({"error": err_msg}))
    else:
      print(f"**Error executing audit:** {err_msg}")
    sys.exit(1)

  if args.format == "json":
    print(json.dumps(report, indent=2))
  else:
    print(render_markdown_report(report))


if __name__ == "__main__":
  main()
