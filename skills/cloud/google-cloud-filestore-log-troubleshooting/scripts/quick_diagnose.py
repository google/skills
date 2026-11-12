#!/usr/bin/env python3
"""Google Cloud Filestore Log-Based Troubleshooting CLI Runner.

Diagnoses Filestore client mount failures (ETIMEDOUT, EACCES, EPERM), network
reachability, VPC ingress firewall rules, export ACLs, and Cloud Audit logging
drift. Emits verified non-destructive remediation commands with interactive
confirmation.
"""

import argparse
import contextlib
import datetime
import json
import os
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import diagnose_lib  # pylint: disable=g-import-not-at-top

# Re-export pure evaluation functions for backward compatibility & unit tests
METRICS_ENV = diagnose_lib.METRICS_ENV
resolve_network_info = diagnose_lib.resolve_network_info
check_port_allowed = diagnose_lib.check_port_allowed
check_export_acl = diagnose_lib.check_export_acl
build_non_destructive_export_json = (
    diagnose_lib.build_non_destructive_export_json
)
_build_acl_remediation = diagnose_lib.build_acl_remediation
_build_fw_remediation = diagnose_lib.build_fw_remediation


def get_cmd_env() -> Dict[str, str]:
  """Constructs process environment with Cloud SDK metrics attribution."""
  return {**os.environ, "CLOUDSDK_METRICS_REQUEST_ATTRIBUTION": METRICS_ENV}


def run_cmd(cmd: List[str], check: bool = False) -> Tuple[int, str, str]:
  """Executes a shell command and returns (returncode, stdout, stderr)."""
  res = subprocess.run(
      cmd, capture_output=True, text=True, env=get_cmd_env(), check=False
  )
  if check and res.returncode != 0:
    raise RuntimeError(f"Command failed: {' '.join(cmd)}\nError: {res.stderr}")
  return res.returncode, res.stdout, res.stderr


def _gcloud(subcmd: str, *args: str) -> Tuple[int, str, str]:
  """Runs gcloud subcmd with extra arguments."""
  return run_cmd(["gcloud", *subcmd.split(), *args])


def _gcloud_json(subcmd: str, *args: str) -> Any:
  """Runs gcloud with --format=json and returns parsed JSON or None."""
  code, out, _ = _gcloud(subcmd, *args, "--format=json")
  if code == 0 and out.strip():
    try:
      return json.loads(out)
    except json.JSONDecodeError:
      pass
  return None


def get_default_project() -> Optional[str]:
  """Gets the active gcloud configured project."""
  code, out, _ = _gcloud(
      "config get-value project", "--format=value(core.project)"
  )
  return out.strip() if code == 0 and out.strip() else None


def describe_filestore_instance(
    instance: str, location: str, project: str
) -> Optional[Dict[str, Any]]:
  """Retrieves Filestore instance metadata via gcloud using location/zone."""
  for loc_flag in (f"--location={location}", f"--zone={location}"):
    res = _gcloud_json(
        "filestore instances describe",
        instance,
        loc_flag,
        f"--project={project}",
    )
    if res is not None:
      return res
  print(
      f"[ERROR] Failed to fetch instance '{instance}' in '{location}'.",
      file=sys.stderr,
  )
  return None


def get_firewall_rules(
    network_name: str, host_project: str
) -> List[Dict[str, Any]]:
  """Retrieves all active VPC ingress firewall rules in the host network."""
  flt = "--filter=direction:INGRESS AND disabled:false"
  data = _gcloud_json(
      "compute firewall-rules list", flt, f"--project={host_project}"
  )
  if data is None:
    print(
        f"[WARN] Firewall fetch failed for '{host_project}'.", file=sys.stderr
    )
    return []
  return [
      r for r in data if r.get("network", "").split("/")[-1] == network_name
  ]


def get_recent_audit_logs(
    instance: Optional[str], project: str, limit: int = 5
) -> List[Dict[str, Any]]:
  """Queries recent Filestore admin audit logs for configuration drift."""
  ts = (
      datetime.datetime.now(datetime.timezone.utc)
      - datetime.timedelta(hours=24)
  ).strftime("%Y-%m-%dT%H:%M:%SZ")
  flt = (
      f'logName="projects/{project}/logs/cloudaudit.googleapis.com%2Factivity"'
      ' AND protoPayload.serviceName="file.googleapis.com" AND'
      f' timestamp>="{ts}"'
  )
  if instance:
    flt += f' AND protoPayload.resourceName=~".*{instance}.*"'
  return (
      _gcloud_json(
          "logging read", flt, f"--project={project}", f"--limit={limit}"
      )
      or []
  )


def get_client_csi_errors(project: str) -> List[str]:
  """Checks Cloud Logging for recent Filestore GKE CSI driver mount errors."""
  ts = (
      datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=3)
  ).strftime("%Y-%m-%dT%H:%M:%SZ")
  flt = (
      'resource.type="k8s_container" AND'
      ' resource.labels.container_name="gcp-filestore-driver" AND'
      f' severity>=ERROR AND timestamp>="{ts}"'
  )
  fmt = "--format=value(textPayload,jsonPayload.message)"
  code, out, _ = _gcloud(
      "logging read", flt, f"--project={project}", "--limit=3", fmt
  )
  return [l.strip() for l in out.splitlines() if l.strip()] if code == 0 else []


def list_all_filestore_instances(project: str) -> List[Dict[str, Any]]:
  """Retrieves all Filestore instances across all locations in the project."""
  data = _gcloud_json("filestore instances list", f"--project={project}")
  if data is None:
    print("[ERROR] Failed to list Filestore instances.", file=sys.stderr)
    return []
  return data


def _apply_remediations(
    remediations: List[Dict[str, Any]],
    instance: str,
    location: str,
    project: str,
) -> None:
  """Executes remediation commands when --apply-fix is passed."""
  print("[!] --apply-fix specified. Executing verified remediation commands...")
  for rem in remediations:
    if rem["type"] == "FIREWALL":
      print(f"Executing: {' '.join(rem['exec_args'])}")
      code, out, err = run_cmd(rem["exec_args"])
      ok = code == 0
      msg = f"[SUCCESS] Rule created:\n{out.strip()}" if ok else err.strip()
      print(msg, file=sys.stdout if ok else sys.stderr)
    elif rem["type"] == "EXPORT_ACL":
      with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
        json.dump(rem["payload"], tf, indent=2)
      try:
        cmd = [
            "gcloud",
            "filestore",
            "instances",
            "update",
            instance,
            f"--location={location}",
            f"--project={project}",
            f"--flags-file={tf.name}",
        ]
        print(f"Executing: {' '.join(cmd)}")
        code, out, err = run_cmd(cmd)
        ok = code == 0
        msg = f"[SUCCESS] ACL updated:\n{out.strip()}" if ok else err.strip()
        print(msg, file=sys.stdout if ok else sys.stderr)
      finally:
        if os.path.exists(tf.name):
          os.remove(tf.name)


def run_diagnostics(
    instance: str,
    location: str,
    project: str,
    client_ip: Optional[str] = None,
    client_subnet: Optional[str] = None,
    apply_fix: bool = False,
    sink: Optional[Dict[str, Any]] = None,
) -> Tuple[int, List[str], List[Dict[str, Any]]]:
  """Runs 4-phase diagnostic triage and returns (exit_code, causes, fixes)."""
  sep, subsep = "=" * 80, "-" * 80
  print(
      f"\n{sep}\n 🔍 FILESTORE LOG-BASED TROUBLESHOOTING REPORT\n{sep}\n"
      f" Target Instance : {instance}\n Location / Zone : {location}\n"
      f" GCP Project     : {project}"
  )
  if client_ip:
    print(f" Client IP       : {client_ip}")
  if client_subnet:
    print(f" Client Subnet   : {client_subnet}")
  print(f"{subsep}\n[*] Step 1: Querying Filestore instance configuration...")

  meta = describe_filestore_instance(instance, location, project)
  if not meta:
    print(
        "[FATAL] Unable to proceed without instance metadata.", file=sys.stderr
    )
    return 1, ["Failed to retrieve instance metadata."], []

  info = diagnose_lib.parse_instance_meta(meta, project)
  if sink is not None:
    sink["instance"] = info

  target_cidr = client_subnet or (f"{client_ip}/32" if client_ip else None)
  target_eval_ip = client_ip or client_subnet
  fw_rules = get_firewall_rules(info["vpc"], info["host_proj"])
  audit_logs = get_recent_audit_logs(instance, project)
  ev = diagnose_lib.evaluate_instance(
      info, fw_rules, target_eval_ip, target_cidr, audit_logs, project
  )
  print(
      diagnose_lib.format_single_report(
          info, ev, target_eval_ip, audit_logs, get_client_csi_errors(project)
      )
  )

  root_causes, remediations = ev["root_causes"], ev["remediations"]
  if root_causes:
    if apply_fix:
      _apply_remediations(remediations, instance, location, project)
    else:
      print(
          "👉 Would you like me to run this remediation command for you? (Yes"
          " / No)"
      )
  return 0, root_causes, remediations


def run_all_diagnostics(
    project: str,
    client_ip: Optional[str] = None,
    client_subnet: Optional[str] = None,
    sink: Optional[Dict[str, Any]] = None,
) -> int:
  """Runs diagnostics across all Filestore instances in the project."""
  sep = "=" * 80
  print(
      f"\n{sep}\n 🚀 DISCOVERING ALL FILESTORE INSTANCES IN PROJECT:"
      f" {project}\n{sep}"
  )
  instances = list_all_filestore_instances(project)
  if not instances:
    print(f"No Filestore instances found in project '{project}'.")
    return 0

  print(f"Found {len(instances)} instance(s). Running diagnostics...\n")
  summary_rows = []
  fw_cache: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
  project_audit_logs = get_recent_audit_logs(None, project, limit=25)
  target_ip = client_ip or client_subnet
  target_cidr = client_subnet or (f"{client_ip}/32" if client_ip else None)

  for inst_data in instances:
    info = diagnose_lib.parse_instance_meta(inst_data, project)
    key = (info["vpc"], info["host_proj"])
    if key not in fw_cache:
      fw_cache[key] = get_firewall_rules(*key)
    ev = diagnose_lib.evaluate_instance(
        info, fw_cache[key], target_ip, target_cidr, project_audit_logs, project
    )
    row = ev["summary_row"]
    summary_rows.append(row)
    print(
        f"  • {info['id']} ({info['location']}) | Tier: {info['tier']} | IP:"
        f" {info['ip']} | Port 2049: {row['port_2049']} | Status:"
        f" {row['status']}"
    )

  print(
      f"\n{sep}\n 📊 AUDIT & DIAGNOSTIC SUMMARY TABLE ({len(summary_rows)}"
      f" INSTANCES)\n{sep}\n| Instance ID | Location | Tier | Filestore IP"
      " | Network | Port 2049 | Export ACL | Status |\n| :--- | :--- | :--- |"
      " :--- | :--- | :--- | :--- | :--- |"
  )
  for r in summary_rows:
    print(
        f"| `{r['instance']}` | {r['location']} | {r['tier']} | `{r['ip']}` |"
        f" `{r['network']}` | {r['port_2049']} | {r['acl']} |"
        f" **{r['status']}** |"
    )
  print()
  if sink is not None:
    sink["instances"] = summary_rows
  return 0


def main():
  parser = argparse.ArgumentParser(
      description="Google Cloud Filestore Log-Based Troubleshooting Tool",
      formatter_class=argparse.RawDescriptionHelpFormatter,
      epilog=(
          "Examples:\n  quick_diagnose.py --instance=finance-share"
          " --location=us-central1-b --project=analytics-prod"
          " --client-subnet=10.128.0.0/20\n  quick_diagnose.py --all"
          " --project=analytics-prod --json\n\nExit codes: 0 = Diagnosis"
          " completed (inspect verdict for HEALTHY vs BLOCKED); 1 ="
          " Execution/metadata fetch error."
      ),
  )
  parser.add_argument("--instance", help="Filestore Instance ID")
  parser.add_argument("--location", help="Location / Zone / Region")
  parser.add_argument("--zone", help="Backward-compatible alias for --location")
  parser.add_argument(
      "--all", action="store_true", help="Diagnose all instances"
  )
  parser.add_argument("--project", help="GCP Project ID")
  parser.add_argument("--client-ip", help="Client internal IP")
  parser.add_argument("--client-subnet", help="Client Subnet CIDR")
  parser.add_argument("--apply-fix", action="store_true", help="Execute fix")
  parser.add_argument(
      "--json",
      action="store_true",
      help="Emit machine-readable JSON on stdout (narrative report on stderr)",
  )

  args = parser.parse_args()
  project = args.project or get_default_project()
  if not project:
    print("[ERROR] Specify --project=<PROJECT_ID>", file=sys.stderr)
    sys.exit(1)

  location = args.location or args.zone
  if not args.all and (not args.instance or not location):
    print(
        "[ERROR] Both --instance and --location (or --zone) are required unless"
        " --all is specified.",
        file=sys.stderr,
    )
    sys.exit(1)

  sink: Dict[str, Any] = {}
  redirect = (
      contextlib.redirect_stdout(sys.stderr)
      if args.json
      else contextlib.nullcontext()
  )
  with redirect:
    if args.all:
      exit_code = run_all_diagnostics(
          project, args.client_ip, args.client_subnet, sink=sink
      )
      root_causes, remediations = [], []
    else:
      exit_code, root_causes, remediations = run_diagnostics(
          args.instance,
          location,
          project,
          args.client_ip,
          args.client_subnet,
          args.apply_fix,
          sink=sink,
      )

  if args.json:
    is_blocked = bool(root_causes) or any(
        "BLOCKED" in r.get("status", "") for r in sink.get("instances", [])
    )
    payload: Dict[str, Any] = {
        "project": project,
        "mode": "fleet" if args.all else "instance",
        "client_ip": args.client_ip,
        "client_subnet": args.client_subnet,
        "root_causes": root_causes,
        "remediations": remediations,
        "verdict": "BLOCKED" if is_blocked else "HEALTHY",
        **sink,
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")

  sys.exit(exit_code)


if __name__ == "__main__":
  main()
