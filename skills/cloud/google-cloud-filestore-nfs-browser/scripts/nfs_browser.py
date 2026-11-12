#!/usr/bin/env python3
"""Google Cloud Filestore NFS File Browser CLI.

Universal, read-only browser for Google Cloud Filestore NFS instances.
Supports Cloud Run Bridge (HTTP/OIDC) and GCE Jump Host (IAP SSH).
"""

import argparse
import json
import os
import subprocess
import sys
from typing import Any, Dict, Optional
import urllib.error
import urllib.parse
import urllib.request

# Ensure sibling helper modules in scripts/ can be imported cleanly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from formatters import format_read_output
from formatters import format_search_output
from formatters import format_stat_output
from formatters import format_tree_output
from jump_host_engine import METRICS_ENV as USER_AGENT
from jump_host_engine import SSHJumpHostEngine

BRIDGE_HTTP_TIMEOUT_SECONDS = 30

DEFAULT_DEPTH = 2
DEFAULT_MAX_ENTRIES = 100
DEFAULT_MAX_RESULTS = 25


def get_auth_token() -> Optional[str]:
  """Retrieves Google Cloud identity token for Cloud Run authentication."""
  try:
    env = {
        **os.environ,
        "CLOUDSDK_METRICS_REQUEST_ATTRIBUTION": USER_AGENT,
    }
    return subprocess.check_output(
        ["gcloud", "auth", "print-identity-token"],
        stderr=subprocess.DEVNULL,
        text=True,
        env=env,
    ).strip()
  except Exception:
    return None


class HTTPBridgeEngine:
  """Executes read-only operations via Cloud Run Serverless NFS Bridge."""

  def __init__(self, bridge_url: str):
    self.url = bridge_url.rstrip("/")

  def _call(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    query = urllib.parse.urlencode(
        {k: v for k, v in params.items() if v is not None}
    )
    req = urllib.request.Request(f"{self.url}{endpoint}?{query}")
    token = os.environ.get("FILESTORE_BRIDGE_TOKEN") or get_auth_token()
    if token:
      req.add_header("Authorization", f"Bearer {token}")
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "application/json")
    try:
      with urllib.request.urlopen(
          req, timeout=BRIDGE_HTTP_TIMEOUT_SECONDS
      ) as resp:
        return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
      raise RuntimeError(
          f"Bridge HTTP {e.code}: {e.read().decode('utf-8') or e.reason}"
      )
    except Exception as e:
      raise RuntimeError(f"Failed to connect to Bridge at {self.url}: {e}")

  def tree(self, path: str, depth: int, max_entries: int) -> Dict[str, Any]:
    return self._call(
        "/api/v1/tree",
        {"path": path, "depth": depth, "max_entries": max_entries},
    )

  def search(
      self,
      path: str,
      pattern: Optional[str],
      grep: Optional[str],
      max_results: int,
  ) -> Dict[str, Any]:
    return self._call(
        "/api/v1/search",
        {
            "path": path,
            "pattern": pattern,
            "grep": grep,
            "max_results": max_results,
        },
    )

  def read(
      self,
      path: str,
      head: Optional[int],
      tail: Optional[int],
      lines: Optional[str],
  ) -> Dict[str, Any]:
    s_line, e_line = (
        map(int, lines.split(":")) if lines and ":" in lines else (None, None)
    )
    return self._call(
        "/api/v1/read",
        {
            "path": path,
            "head": head,
            "tail": tail,
            "start_line": s_line,
            "end_line": e_line,
        },
    )

  def stat(self, path: str) -> Dict[str, Any]:
    return self._call("/api/v1/stat", {"path": path})


def main():
  common = argparse.ArgumentParser(add_help=False)
  common.add_argument(
      "--bridge-url",
      default=os.environ.get("FILESTORE_BRIDGE_URL"),
      help="Cloud Run Bridge URL",
  )
  common.add_argument(
      "--project", default=os.environ.get("GCP_PROJECT"), help="GCP Project ID"
  )
  common.add_argument("--zone", default="us-central1-a", help="GCE Zone")
  common.add_argument("--instance", help="Filestore instance ID")
  common.add_argument(
      "--jump-host-vm",
      "--jump-host",
      dest="jump_host_vm",
      help="GCE Jump Host VM name in VPC",
  )
  common.add_argument(
      "--mount",
      default="/mnt/filestore",
      help="NFS mount directory on jump host (default: /mnt/filestore)",
  )
  common.add_argument("--json", action="store_true", help="Output raw JSON")

  p = argparse.ArgumentParser(
      description="Filestore NFS File Browser CLI", parents=[common]
  )
  sub = p.add_subparsers(dest="command", required=True)

  p_tree = sub.add_parser("tree", help="List directory tree", parents=[common])
  p_tree.add_argument("--path", default="/", help="Path in share")
  p_tree.add_argument(
      "--depth", type=int, default=DEFAULT_DEPTH, help="Depth limit"
  )
  p_tree.add_argument(
      "--max-entries",
      type=int,
      default=DEFAULT_MAX_ENTRIES,
      help="Max entries",
  )

  p_search = sub.add_parser(
      "search", help="Search filenames or file contents", parents=[common]
  )
  p_search.add_argument("--path", default="/", help="Base search path")
  p_search.add_argument("--pattern", help="Filename glob (e.g. *.log)")
  p_search.add_argument("--grep", help="Regex content pattern")
  p_search.add_argument(
      "--max-results",
      type=int,
      default=DEFAULT_MAX_RESULTS,
      help="Max matches",
  )

  p_read = sub.add_parser("read", help="Read file slice", parents=[common])
  p_read.add_argument("--path", required=True, help="File path in share")
  p_read.add_argument("--head", type=int, help="First N lines")
  p_read.add_argument("--tail", type=int, help="Last N lines")
  p_read.add_argument("--lines", help="Line range (e.g. 10:50)")

  p_stat = sub.add_parser(
      "stat", help="Inspect file metadata", parents=[common]
  )
  p_stat.add_argument("--path", required=True, help="File or directory path")

  args = p.parse_args()

  if args.bridge_url:
    engine = HTTPBridgeEngine(args.bridge_url)
  elif args.jump_host_vm:
    engine = SSHJumpHostEngine(
        args.project or "",
        args.zone,
        args.jump_host_vm,
        mount_point=args.mount,
    )
  else:
    p.error(
        "Missing execution engine. Provide either --bridge-url (Engine 1: Cloud"
        " Run Bridge) or --jump-host-vm (Engine 2: GCE IAP SSH Jump Host)."
    )

  if args.command == "tree":
    res = engine.tree(args.path, args.depth, args.max_entries)
    format_tree_output(res, args.path, args.json)
  elif args.command == "search":
    res = engine.search(args.path, args.pattern, args.grep, args.max_results)
    format_search_output(res, args.json)
  elif args.command == "read":
    res = engine.read(args.path, args.head, args.tail, args.lines)
    format_read_output(res, args.json)
  elif args.command == "stat":
    res = engine.stat(args.path)
    format_stat_output(res, args.json)


if __name__ == "__main__":
  main()
