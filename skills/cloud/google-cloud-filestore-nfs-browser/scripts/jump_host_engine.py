"""GCE Jump Host SSH execution engine for Filestore NFS File Browser."""

import base64
import json
import os
import re
import subprocess
from typing import Any, Dict, Optional

_DEFAULT_METRICS_ENV = (
    "agent-skills/1.0 (skill:google-cloud-filestore-nfs-browser)"
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

BINARY_CHECK_BYTES = 1024
MAX_SEARCH_FILE_SIZE_BYTES = 50 * 1024 * 1024
MAX_CONTEXT_SNIPPET_LENGTH = 200
DEFAULT_HEAD_LINES = 100


def _build_remote_tree_script(
    mount: str, path: str, depth: int, max_entries: int
) -> str:
  """Builds a Python script string to execute tree traversal on the remote host."""
  return f"""
import os, json
root = os.path.join({repr(mount)}, {repr(path.lstrip('/'))})
mount = {repr(mount)}
if not os.path.exists(root):
  print(json.dumps({{"error": "Path not found: " + root}}))
  exit(0)
entries = []
for r, dirs, files in os.walk(root):
  d = 0 if r == root else os.path.relpath(r, root).count(os.sep) + 1
  if d >= {int(depth)}:
    dirs.clear()
  for name in sorted(dirs):
    entries.append({{"name": name, "type": "dir", "path": "/" + os.path.relpath(os.path.join(r, name), mount)}})
    if len(entries) >= {int(max_entries)}:
      break
  if len(entries) >= {int(max_entries)}:
    break
  if d < {int(depth)}:
    for name in sorted(files):
      st = os.stat(os.path.join(r, name))
      entries.append({{"name": name, "type": "file", "size_bytes": st.st_size, "path": "/" + os.path.relpath(os.path.join(r, name), mount)}})
      if len(entries) >= {int(max_entries)}:
        break
  if len(entries) >= {int(max_entries)}:
    break
print(json.dumps({{"path": {repr(path)}, "entries": entries, "total_entries": len(entries)}}))
"""


def _build_remote_search_script(
    mount: str,
    path: str,
    pattern: Optional[str],
    grep: Optional[str],
    max_results: int,
) -> str:
  """Builds a Python script string to execute filename glob and regex search remotely."""
  return f"""
import os, re, fnmatch, json
root = os.path.join({repr(mount)}, {repr(path.lstrip('/'))})
mount = {repr(mount)}
pat = {repr(pattern)}
rgx = re.compile({repr(grep)}) if {repr(grep)} else None
matches = []
for r, _, files in os.walk(root):
  for f in sorted(files):
    if pat and not fnmatch.fnmatch(f, pat):
      continue
    fp = os.path.join(r, f)
    rel = "/" + os.path.relpath(fp, mount)
    if rgx:
      try:
        if os.path.getsize(fp) > {MAX_SEARCH_FILE_SIZE_BYTES}:
          continue
        with open(fp, "rb") as fh:
          if b"\\x00" in fh.read({BINARY_CHECK_BYTES}):
            continue
        with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
          for idx, line in enumerate(fh, 1):
            if rgx.search(line):
              matches.append({{"file": rel, "line": idx, "content": line.strip()[:{MAX_CONTEXT_SNIPPET_LENGTH}]}})
              if len(matches) >= {int(max_results)}:
                break
      except Exception:
        pass
    else:
      matches.append({{"file": rel}})
    if len(matches) >= {int(max_results)}:
      break
  if len(matches) >= {int(max_results)}:
    break
print(json.dumps({{"matches": matches}}))
"""


def _build_remote_read_script(
    mount: str,
    path: str,
    head: Optional[int],
    tail: Optional[int],
    lines: Optional[str],
) -> str:
  """Builds a Python script string to read a safe file slice remotely."""
  return f"""
import os, collections, json
mount_base = os.path.realpath({repr(mount)})
fp = os.path.realpath(os.path.join(mount_base, {repr(path.lstrip('/'))}))
if os.path.commonpath([mount_base, fp]) != mount_base:
  print(json.dumps({{"error": "Access denied: path traversal"}}))
  exit(0)
if not os.path.exists(fp):
  print(json.dumps({{"error": "File not found: " + fp}}))
  exit(0)
with open(fp, "rb") as fh:
  if b"\\x00" in fh.read({BINARY_CHECK_BYTES}):
    print(json.dumps({{"file": {repr(path)}, "is_binary": True, "size_bytes": os.path.getsize(fp)}}))
    exit(0)
head, tail, l_spec = {repr(head)}, {repr(tail)}, {repr(lines)}
s, e, tot, sel = 1, 0, 0, []
with open(fp, "r", encoding="utf-8", errors="replace") as fh:
  if tail:
    ring = collections.deque(enumerate(fh, 1), maxlen=tail)
    if ring:
      s, e, tot, sel = ring[0][0], ring[-1][0], ring[-1][0], [line for _, line in ring]
    else:
      s, e, tot, sel = 1, 0, 0, []
  elif l_spec and ":" in l_spec:
    p1, p2 = map(int, l_spec.split(":"))
    s = p1
    for idx, line in enumerate(fh, 1):
      if idx >= p1 and idx <= p2:
        sel.append(line)
      elif idx > p2:
        break
    e = p1 + len(sel) - 1 if sel else p1
    tot = max(e, p2)
  else:
    limit = head if head else {DEFAULT_HEAD_LINES}
    for idx, line in enumerate(fh, 1):
      if idx <= limit:
        sel.append(line)
      else:
        break
    e, tot = len(sel), len(sel)
print(json.dumps({{"file": {repr(path)}, "start_line": s, "end_line": e, "total_lines": tot, "content": "".join(sel), "is_binary": False}}))
"""


def _build_remote_stat_script(mount: str, path: str) -> str:
  """Builds a Python script string to inspect POSIX file attributes remotely."""
  return f"""
import os, stat, json
mount_base = os.path.realpath({repr(mount)})
fp = os.path.realpath(os.path.join(mount_base, {repr(path.lstrip('/'))}))
if os.path.commonpath([mount_base, fp]) != mount_base:
  print(json.dumps({{"error": "Access denied: path traversal"}}))
  exit(0)
if not os.path.exists(fp):
  print(json.dumps({{"error": "Path not found: " + fp}}))
  exit(0)
st = os.stat(fp)
print(json.dumps({{"path": {repr(path)}, "size_bytes": st.st_size, "mode": oct(stat.S_IMODE(st.st_mode)), "is_dir": stat.S_ISDIR(st.st_mode), "uid": st.st_uid, "gid": st.st_gid, "mtime": int(st.st_mtime)}}))
"""


class SSHJumpHostEngine:
  """Executes read-only operations on a GCE VM in the VPC via gcloud compute ssh."""

  def __init__(
      self,
      project: str,
      zone: str,
      vm: str,
      mount_point: str = "/mnt/filestore",
  ):
    self.project = project
    self.zone = zone
    self.vm = vm
    self.mount = mount_point.rstrip("/")

  def _exec(self, script: str) -> Dict[str, Any]:
    """Executes a Python script remotely via SSH and parses JSON output."""
    env = os.environ.copy()
    env["CLOUDSDK_METRICS_REQUEST_ATTRIBUTION"] = METRICS_ENV
    cmd = [
        "gcloud",
        "compute",
        "ssh",
        self.vm,
        f"--project={self.project}",
        f"--zone={self.zone}",
        "--quiet",
    ]
    # Encode script via base64 to avoid shell quote and escaping issues over SSH
    encoded_script = base64.b64encode(script.encode("utf-8")).decode("ascii")
    decoded_expr = f"exec(base64.b64decode('{encoded_script}').decode('utf-8'))"
    remote_cmd = f'python3 -c "import base64; {decoded_expr}"'
    # Try direct SSH first, fallback to IAP tunnel
    for iap_flag in [[], ["--tunnel-through-iap"]]:
      full_cmd = cmd + iap_flag + [f"--command={remote_cmd}"]
      res = subprocess.run(
          full_cmd, capture_output=True, text=True, env=env, check=False
      )
      if res.returncode == 0:
        try:
          return json.loads(res.stdout)
        except json.JSONDecodeError:
          return {"output": res.stdout.strip()}
    raise RuntimeError(
        f"GCE SSH failed: {res.stderr.strip() or res.stdout.strip()}"
    )

  def tree(self, path: str, depth: int, max_entries: int) -> Dict[str, Any]:
    script = _build_remote_tree_script(self.mount, path, depth, max_entries)
    return self._exec(script)

  def search(
      self,
      path: str,
      pattern: Optional[str],
      grep: Optional[str],
      max_results: int,
  ) -> Dict[str, Any]:
    script = _build_remote_search_script(
        self.mount, path, pattern, grep, max_results
    )
    return self._exec(script)

  def read(
      self,
      path: str,
      head: Optional[int],
      tail: Optional[int],
      lines: Optional[str],
  ) -> Dict[str, Any]:
    script = _build_remote_read_script(self.mount, path, head, tail, lines)
    return self._exec(script)

  def stat(self, path: str) -> Dict[str, Any]:
    script = _build_remote_stat_script(self.mount, path)
    return self._exec(script)
