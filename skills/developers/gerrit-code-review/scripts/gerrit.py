#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Standalone Gerrit Code Review REST API CLI.

Interacts with Gerrit servers over the standard HTTPS REST API using argparse
and the Python 3 standard library exclusively so the CLI runs standalone without
third-party dependencies. Handles authentication via ~/.gitcookies or
~/.netrc, strips Gerrit's )]}' XSSI prefixes, detects review hosts from git
remotes, and wraps untrusted free-text output in <untrusted_gerrit_data>
delimiters.
"""

from __future__ import annotations

import argparse
import base64
from collections.abc import Mapping, Sequence
import http.cookiejar
import json
import netrc
import os
import re
import subprocess
import sys
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

SHORTLINK_HOSTS: Mapping[str, str] = {
    "r.android.com": "https://android-review.googlesource.com",
    "android-review": "https://android-review.googlesource.com",
    "crrev.com": "https://chromium-review.googlesource.com",
    "chromium-review": "https://chromium-review.googlesource.com",
    "fxrev.dev": "https://fuchsia-review.googlesource.com",
    "fuchsia-review": "https://fuchsia-review.googlesource.com",
}

_CLOSING_TAG_PATTERN = re.compile(r"</\s*untrusted_gerrit_data", re.IGNORECASE)

# Safety cap on pages fetched by `search --all`.
_MAX_SEARCH_PAGES = 50


class UsageError(Exception):
  """Raised when required CLI arguments are missing or invalid."""


def _require_value(value: str | None, description: str) -> str:
  """Returns value if non-empty, or raises UsageError."""
  if not value:
    raise UsageError(f"Missing required argument: {description}.")
  return value


def format_untrusted_envelope(
    content: str, host: str, change_id: str | None = None
) -> str:
  """Wraps untrusted Gerrit text in a breakout-safe defensive envelope.

  Args:
    content: Free-text output fetched from Gerrit.
    host: Canonical Gerrit review host URL.
    change_id: Optional change identifier when scoped to a single change, or
      None for multi-change search results.

  Returns:
    Envelope-wrapped text with any literal closing tag escaped.
  """
  safe_content = _CLOSING_TAG_PATTERN.sub("&lt;/untrusted_gerrit_data", content)
  safe_host = host.replace('"', "%22")
  attrs = f'host="{safe_host}"'
  if change_id is not None:
    safe_change = str(change_id).replace('"', "%22")
    attrs += f' change="{safe_change}"'
  body = safe_content.rstrip("\n")
  if body:
    return f"<untrusted_gerrit_data {attrs}>\n{body}\n</untrusted_gerrit_data>"
  return f"<untrusted_gerrit_data {attrs}>\n</untrusted_gerrit_data>"


def _print_untrusted(
    lines: Sequence[str] | str, host: str, change_id: str | None = None
) -> None:
  """Prints text inside an <untrusted_gerrit_data> envelope."""
  text = lines if isinstance(lines, str) else "\n".join(lines)
  print(format_untrusted_envelope(text, host=host, change_id=change_id))


def _print_json_maybe_untrusted(
    data: Any,
    args: argparse.Namespace,
    host: str,
    change_id: str | None = None,
) -> None:
  """Prints JSON raw with --json, otherwise inside the untrusted envelope."""
  text = json.dumps(data, indent=2)
  if getattr(args, "json", False):
    print(text)
  else:
    _print_untrusted(
        text, host=host, change_id=None if change_id is None else str(change_id)
    )


def normalize_host(host_input: str | None) -> str | None:
  """Normalizes a host URL or shortlink identifier to a canonical review URL.

  Args:
    host_input: Raw host string, shortlink domain, or None.

  Returns:
    Canonical scheme://host URL, or None when host_input is empty.
  """
  if not host_input:
    return None
  host = host_input.strip().rstrip("/")
  if not host:
    return None
  for short, full in SHORTLINK_HOSTS.items():
    if (
        host == short
        or host == f"https://{short}"
        or host == f"http://{short}"
        or host.startswith(f"https://{short}/")
        or host.startswith(f"http://{short}/")
    ):
      return full
  if not host.startswith("http://") and not host.startswith("https://"):
    host = "https://" + host
  parsed = urllib.parse.urlparse(host)
  # Drop userinfo (user@host) so credentials never leak into the host URL.
  hostname = (parsed.hostname or "").lower()
  if not hostname:
    return None
  if hostname.endswith(".googlesource.com") and not hostname.endswith(
      "-review.googlesource.com"
  ):
    prefix = hostname[: -len(".googlesource.com")]
    hostname = f"{prefix}-review.googlesource.com"
  netloc = f"{hostname}:{parsed.port}" if parsed.port else hostname
  scheme = parsed.scheme or "https"
  return f"{scheme}://{netloc}"


def _is_known_gerrit_url(url: str) -> bool:
  """Returns True for URLs that clearly point at a Gerrit-backed git host."""
  hostname = (urllib.parse.urlparse(url).hostname or "").lower()
  return hostname.endswith(".googlesource.com") or any(
      hostname == short for short in SHORTLINK_HOSTS
  )


def _git_toplevel() -> str | None:
  """Returns the root of the enclosing git checkout, or None."""
  try:
    return (
        subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], stderr=subprocess.DEVNULL
        )
        .decode("utf-8")
        .strip()
        or None
    )
  except (subprocess.CalledProcessError, FileNotFoundError, OSError):
    return None


def detect_git_host() -> str | None:
  """Detects the Gerrit review host from git remotes or .gitreview.

  Returns:
    Normalized Gerrit review host URL, or None if none can be determined.
  """
  try:
    cmd = [
        "git",
        "--no-pager",
        "config",
        "--get-regexp",
        r"^remote\..*\.(review|url)$",
    ]
    git_output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode(
        "utf-8"
    )
    review_url = None
    remote_url = None
    for line in git_output.strip().splitlines():
      parts = line.split(None, 1)
      if len(parts) != 2:
        continue
      config_key, config_val = parts[0], parts[1].strip()
      if config_key.endswith(".review") and not review_url:
        review_url = normalize_host(config_val)
      elif not remote_url:
        # Only trust plain remote URLs on known Gerrit hosts; a github.com
        # origin must never be mistaken for a Gerrit server.
        if config_val.startswith(("sftp://", "ssh://")):
          match = re.search(r"@([^:/]+)(?::\d+)?(?:/|$)", config_val)
          if match and _is_known_gerrit_url(f"https://{match.group(1)}"):
            remote_url = normalize_host(match.group(1))
        elif config_val.startswith(
            ("https://", "http://")
        ) and _is_known_gerrit_url(config_val):
          remote_url = normalize_host(config_val)
    if review_url:
      return review_url
    if remote_url:
      return remote_url
  except (subprocess.CalledProcessError, FileNotFoundError, OSError):
    # Not in a git repository or git binary unavailable; fall back to .gitreview
    pass

  toplevel = _git_toplevel()
  gitreview_path = os.path.join(toplevel or os.getcwd(), ".gitreview")
  if os.path.exists(gitreview_path):
    try:
      with open(gitreview_path, "r", encoding="utf-8") as review_file:
        for line in review_file:
          stripped = line.strip()
          if stripped.startswith("host="):
            return normalize_host(stripped.split("=", 1)[1])
    except OSError:
      # Ignore unreadable .gitreview and require explicit --host.
      pass
  return None


def get_cookiefile_path(custom_path: str | None = None) -> str | None:
  """Finds the path to the configured git cookiefile, or None if absent.

  Args:
    custom_path: Explicit --cookiefile value, if any.

  Returns:
    Path to an existing cookie file, or None.

  Raises:
    UsageError: If an explicit custom_path does not exist. Silently falling
      back to another cookie file could authenticate as a different identity.
  """
  if custom_path:
    expanded_custom = os.path.expanduser(custom_path)
    if not os.path.exists(expanded_custom):
      raise UsageError(f"--cookiefile '{custom_path}' does not exist.")
    return expanded_custom
  try:
    configured = (
        subprocess.check_output(
            ["git", "config", "--get", "http.cookiefile"],
            stderr=subprocess.DEVNULL,
        )
        .decode("utf-8")
        .strip()
    )
    if configured:
      expanded_cfg = os.path.expanduser(configured)
      if os.path.exists(expanded_cfg):
        return expanded_cfg
  except (subprocess.CalledProcessError, FileNotFoundError, OSError):
    # Ignore missing git config and check default ~/.gitcookies location.
    pass
  default_path = os.path.expanduser("~/.gitcookies")
  if os.path.exists(default_path):
    return default_path
  return None


def load_gitcookies(
    cookie_jar: http.cookiejar.CookieJar, cookiefile_path: str | None
) -> None:
  """Loads Netscape-format ~/.gitcookies entries (including #HttpOnly_)."""
  if not cookiefile_path or not os.path.exists(cookiefile_path):
    return

  try:
    with open(
        cookiefile_path, "r", encoding="utf-8", errors="replace"
    ) as cookie_file:
      for raw_line in cookie_file:
        line = raw_line.strip()
        if not line or (
            line.startswith("#") and not line.startswith("#HttpOnly_")
        ):
          continue
        if line.startswith("#HttpOnly_"):
          line = line[len("#HttpOnly_") :]
        parts = line.split("\t")
        if len(parts) < 7:
          continue
        domain, _, path, secure, expires, name, value = parts[:7]
        try:
          exp_int = int(expires) if expires else None
        except ValueError:
          exp_int = None
        # An expiry of 0 marks a session cookie; CookieJar would treat
        # expires=0 as already expired and never send it.
        if not exp_int:
          exp_int = None
        cookie = http.cookiejar.Cookie(
            version=0,
            name=name,
            value=value,
            port=None,
            port_specified=False,
            domain=domain,
            domain_specified=domain.startswith("."),
            domain_initial_dot=domain.startswith("."),
            path=path,
            path_specified=bool(path),
            secure=(secure.upper() == "TRUE"),
            expires=exp_int,
            discard=False,
            comment=None,
            comment_url=None,
            rest={"HttpOnly": ""},
        )
        cookie_jar.set_cookie(cookie)
  except OSError:
    # Proceed without cookies if the cookie file cannot be read.
    pass


def _load_netrc_auth(hostname: str) -> str | None:
  """Returns a Basic Authorization value from ~/.netrc for hostname, or None."""
  try:
    auth = netrc.netrc().authenticators(hostname)
  except FileNotFoundError:
    return None
  except (netrc.NetrcParseError, OSError) as err:
    # netrc also raises NetrcParseError for insecure file permissions.
    sys.stderr.write(f"Warning: ignoring unreadable ~/.netrc: {err}\n")
    return None
  if not auth:
    return None
  login, _, password = auth
  if not login or not password:
    return None
  raw_creds = f"{login}:{password}".encode("utf-8")
  return "Basic " + base64.b64encode(raw_creds).decode("ascii")


_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


# HTTP statuses meaning "this REST endpoint does not exist on this server".
_ENDPOINT_MISSING_STATUSES = frozenset({404, 405})


class GerritHttpError(RuntimeError):
  """Raised on non-2xx Gerrit HTTP responses, carrying the status code.

  Attributes:
    status: HTTP status code returned by the Gerrit server.
  """

  def __init__(self, status: int, message: str):
    """Initializes the instance."""
    super().__init__(message)
    self.status = status


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
  """Refuses HTTP redirects so credentials never reach a redirect target."""

  def redirect_request(self, req, fp, code, msg, headers, newurl):
    """Returns None so urllib raises HTTPError for the 3xx response."""
    return None


class GerritClient:
  """Authenticated HTTP REST client for a Gerrit Code Review server.

  Attributes:
    host: Normalized Gerrit review host URL (scheme://host).
    cookie_jar: CookieJar populated from the configured git cookiefile.
    netrc_auth: Basic Authorization header value from ~/.netrc, if any.
    cookiefile: Resolved path to the git cookiefile, if loaded.
    opener: urllib OpenerDirector configured with cookie_jar.
    has_host_cookie: Whether cookie_jar holds a cookie matching host.
    anonymous: Whether requests omit credentials and drop the /a/ prefix.
  """

  def __init__(
      self,
      host: str,
      cookiefile: str | None = None,
      anonymous: bool = False,
  ):
    """Initializes the Gerrit REST client for a specific review host.

    Args:
      host: Gerrit review host URL or shortlink.
      cookiefile: Optional explicit path to a Netscape-format cookie file.
      anonymous: If True, never send credentials and use unauthenticated
        endpoints (no /a/ prefix). Also used automatically when no credentials
        for the host can be loaded.

    Raises:
      UsageError: If host is empty or an explicit cookiefile does not exist.
    """
    normalized = normalize_host(host)
    if not normalized:
      raise UsageError(
          "Gerrit host URL is required. Pass --host or configure a git remote."
      )
    self.host = normalized
    parsed = urllib.parse.urlparse(self.host)
    hostname = parsed.hostname or ""
    self.cookie_jar = http.cookiejar.CookieJar()
    self.netrc_auth: str | None = None
    self.cookiefile: str | None = None

    # Never send cookies or Basic credentials over plain http, except to a
    # loopback address (used by local test servers).
    secure_transport = parsed.scheme == "https" or hostname in _LOOPBACK_HOSTS
    if not anonymous and not secure_transport:
      sys.stderr.write(
          "Warning: refusing to send credentials to non-https host"
          f" {self.host}; using anonymous access.\n"
      )
    if not anonymous and secure_transport:
      self.cookiefile = get_cookiefile_path(cookiefile)
      if self.cookiefile:
        load_gitcookies(self.cookie_jar, self.cookiefile)
      self.netrc_auth = _load_netrc_auth(hostname)

    self.opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(self.cookie_jar),
        _NoRedirectHandler(),
    )
    self.has_host_cookie = self._jar_has_cookie_for_host()
    self.anonymous = not (self.has_host_cookie or self.netrc_auth)

  def _jar_has_cookie_for_host(self) -> bool:
    """Returns True if the cookie jar holds a cookie for this review host."""
    probe = urllib.request.Request(f"{self.host}/a/")
    self.cookie_jar.add_cookie_header(probe)
    return probe.has_header("Cookie")

  def request(
      self,
      endpoint: str,
      method: str = "GET",
      payload: Any = None,
      raw_response: bool = False,
  ) -> Any:
    """Executes an HTTP request against a Gerrit REST API endpoint.

    Args:
      endpoint: REST path relative to the host (such as
        '/a/changes/123/detail').
      method: HTTP verb ('GET', 'POST', 'PUT', 'DELETE').
      payload: Optional JSON-serializable body, string, or raw bytes.
      raw_response: If True, returns raw response bytes without XSSI parsing.

    Returns:
      Parsed JSON value, plain text, raw bytes, or None on empty body.

    Raises:
      GerritHttpError: On HTTP status errors.
      RuntimeError: On network transport failures.
    """
    if self.anonymous and endpoint.startswith("/a/"):
      # Unauthenticated REST uses the same paths without the /a/ prefix.
      endpoint = endpoint[2:]
    if endpoint.startswith("/"):
      url = f"{self.host}{endpoint}"
    else:
      url = f"{self.host}/{endpoint}"

    request_bytes: bytes | None = None
    headers = {"User-Agent": "gerrit-skill-cli/1.0"}
    if payload is not None:
      if isinstance(payload, (dict, list)):
        request_bytes = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
      elif isinstance(payload, str):
        request_bytes = payload.encode("utf-8")
      else:
        request_bytes = payload

    http_req = urllib.request.Request(
        url, data=request_bytes, headers=headers, method=method
    )
    if self.netrc_auth and not self.has_host_cookie:
      # Unredirected so urllib never forwards credentials to a redirect target.
      http_req.add_unredirected_header("Authorization", self.netrc_auth)
    try:
      with self.opener.open(http_req) as http_resp:
        body_bytes = http_resp.read()
        if raw_response:
          return body_bytes
        text = body_bytes.decode("utf-8", errors="replace")
        if text.startswith(")]}'\n"):
          text = text[5:]
        elif text.startswith(")]}'"):
          text = text[4:]
        text = text.strip()
        if not text:
          return None
        try:
          return json.loads(text)
        except json.JSONDecodeError:
          return text
    except urllib.error.HTTPError as err:
      if 300 <= err.code < 400:
        location = err.headers.get("Location", "an unspecified location")
        raise GerritHttpError(
            err.code,
            f"HTTP {err.code}: {url} redirected to {location}. Redirects are"
            " not followed; check that credentials are valid and that --host"
            " is the canonical https:// review host.",
        ) from err
      err_body = err.read().decode("utf-8", errors="replace").strip()
      if err_body.startswith(")]}'\n"):
        err_body = err_body[5:].strip()
      raise GerritHttpError(
          err.code, f"HTTP {err.code} {err.reason}: {err_body}"
      ) from err
    except urllib.error.URLError as err:
      raise RuntimeError(
          f"Network error accessing {url}: {err.reason}"
      ) from err


def compute_change_size(insertions: int | None, deletions: int | None) -> str:
  """Computes Gerrit's T-shirt size badge (XS, S, M, L, XL)."""
  delta = (insertions or 0) + (deletions or 0)
  if delta < 10:
    return "XS"
  if delta < 50:
    return "S"
  if delta < 250:
    return "M"
  if delta < 1000:
    return "L"
  return "XL"


def _quote_id(identifier: Any) -> str:
  """URL-encodes a change, project, or comment identifier without safe '/'."""
  return urllib.parse.quote(str(identifier), safe="")


def _read_message_arg(args: argparse.Namespace) -> str:
  """Reads message text from --message or --message-file."""
  message_text = getattr(args, "message", None)
  message_file = getattr(args, "message_file", None)
  if message_file:
    with open(message_file, "r", encoding="utf-8") as msg_handle:
      message_text = msg_handle.read()
  if not message_text:
    raise UsageError("Must provide --message or --message-file.")
  return message_text


def _matches_author(author_obj: Mapping[str, Any], author_filter: str) -> bool:
  """Checks whether an author matches a filter, case-insensitively.

  A filter starting with '@' (e.g. '@example.com') matches only the email
  domain suffix, because display names are user-chosen and spoofable. Any
  other filter must equal the author's email, username, or full display name
  exactly; substring matches are never accepted.

  Args:
    author_obj: Gerrit AccountInfo dict.
    author_filter: Domain suffix ('@example.com') or exact identity.

  Returns:
    True if the author matches the filter.
  """
  needle = author_filter.strip().lower()
  email = str(author_obj.get("email", "")).lower()
  if needle.startswith("@"):
    return email.endswith(needle)
  return needle in (
      email,
      str(author_obj.get("username", "")).lower(),
      str(author_obj.get("name", "")).lower(),
  )


def cmd_change(client: GerritClient, args: argparse.Namespace) -> None:
  """Outputs change metadata and revision summary."""
  change_id = _require_value(args.change, "change")
  opts = ["o=CURRENT_REVISION", "o=CURRENT_COMMIT", "o=DETAILED_ACCOUNTS"]
  if args.revision and args.revision != "current":
    opts.append("o=ALL_REVISIONS")
  endpoint = f"/a/changes/{_quote_id(change_id)}/detail?{'&'.join(opts)}"
  change_data = client.request(endpoint) or {}

  if args.json:
    print(json.dumps(change_data, indent=2))
    return

  owner = change_data.get("owner", {})
  ins = change_data.get("insertions", 0)
  dels = change_data.get("deletions", 0)
  size = compute_change_size(ins, dels)
  lines = [
      f"Change-Id: {change_data.get('change_id', '')}",
      f"Number: {change_data.get('_number', '')}",
      f"Subject: {change_data.get('subject', '')}",
      f"Status: {change_data.get('status', '')}",
      f"Owner: {owner.get('name', 'Unknown')} ({owner.get('email', 'N/A')})",
      f"Project: {change_data.get('project', '')}",
      f"Branch: {change_data.get('branch', '')}",
  ]
  if change_data.get("topic"):
    lines.append(f"Topic: {change_data.get('topic')}")
  if change_data.get("revert_of"):
    lines.append(f"Revert-Of: {change_data.get('revert_of')}")
  if change_data.get("cherry_pick_of_change"):
    cp_change = change_data.get("cherry_pick_of_change")
    cp_ps = change_data.get("cherry_pick_of_patch_set", "")
    lines.append(f"Cherry-Pick-Of: {cp_change} (patchset {cp_ps})")
  lines.append(f"Size: {size} (+{ins}, -{dels})")

  rev_id = change_data.get("current_revision")
  revisions = change_data.get("revisions", {})
  if rev_id and rev_id in revisions:
    ps_num = revisions[rev_id].get("_number")
    lines.append(f"Current-Revision: {rev_id[:8]} (patchset {ps_num})")
  if args.revision and args.revision != "current":
    wanted = str(args.revision)
    for sha, rev_info in revisions.items():
      if sha.startswith(wanted) or str(rev_info.get("_number")) == wanted:
        lines.append(
            f"Requested-Revision: {sha[:8]} (patchset"
            f" {rev_info.get('_number')}, uploaded"
            f" {rev_info.get('created', 'unknown')})"
        )
        break
    else:
      lines.append(f"Requested-Revision: {wanted} (not found on change)")

  _print_untrusted(lines, host=client.host, change_id=str(change_id))


def _format_unified_diff(
    file_path: str, diff_info: Mapping[str, Any]
) -> list[str]:
  """Renders a Gerrit DiffInfo as unified diff lines with @@ hunk headers.

  Args:
    file_path: Repository path of the file.
    diff_info: Gerrit DiffInfo with 'content' chunks ('ab', 'a', 'b', 'skip').

  Returns:
    Unified diff lines for the file, or an empty list if nothing changed.
  """
  change_type = diff_info.get("change_type")
  old_name = "/dev/null" if change_type == "ADDED" else f"a/{file_path}"
  new_name = "/dev/null" if change_type == "DELETED" else f"b/{file_path}"
  out: list[str] = []
  a_line = b_line = 1
  hunk: list[str] = []
  hunk_a_start = hunk_b_start = 1
  hunk_a_count = hunk_b_count = 0

  def flush() -> None:
    if any(line[:1] in ("-", "+") for line in hunk):
      out.append(
          f"@@ -{hunk_a_start},{hunk_a_count} +{hunk_b_start},{hunk_b_count} @@"
      )
      out.extend(hunk)

  for chunk in diff_info.get("content", []):
    if "skip" in chunk:
      flush()
      a_line += int(chunk["skip"])
      b_line += int(chunk["skip"])
      hunk = []
      hunk_a_start, hunk_b_start = a_line, b_line
      hunk_a_count = hunk_b_count = 0
      continue
    for unchanged in chunk.get("ab", []):
      hunk.append(f" {unchanged}")
      hunk_a_count += 1
      hunk_b_count += 1
    for removed in chunk.get("a", []):
      hunk.append(f"-{removed}")
      hunk_a_count += 1
    for added in chunk.get("b", []):
      hunk.append(f"+{added}")
      hunk_b_count += 1
    a_line += len(chunk.get("ab", [])) + len(chunk.get("a", []))
    b_line += len(chunk.get("ab", [])) + len(chunk.get("b", []))
  flush()
  if not out:
    return []
  return [f"--- {old_name}", f"+++ {new_name}", *out]


def cmd_diff(client: GerritClient, args: argparse.Namespace) -> None:
  """Outputs unified diff for a change or between two patch sets."""
  change_id = _require_value(args.change, "change")
  quoted_change = _quote_id(change_id)
  rev = _quote_id(args.revision or "current")
  if args.base:
    quoted_base = _quote_id(args.base)
    files_ep = (
        f"/a/changes/{quoted_change}/revisions/{rev}/files/?base={quoted_base}"
    )
    changed_files = client.request(files_ep) or {}
    diff_lines: list[str] = []
    for file_path in sorted(changed_files.keys()):
      if file_path in ("/COMMIT_MSG", "/MERGE_LIST"):
        continue
      quoted_path = _quote_id(file_path)
      diff_ep = (
          f"/a/changes/{quoted_change}/revisions/{rev}/files/{quoted_path}"
          f"/diff?base={quoted_base}&context=3"
      )
      diff_info = client.request(diff_ep)
      if not diff_info:
        continue
      diff_lines.extend(_format_unified_diff(file_path, diff_info))
    output_text = "\n".join(diff_lines)
    if args.raw:
      if output_text:
        print(output_text)
    else:
      _print_untrusted(output_text, host=client.host, change_id=str(change_id))
    return

  endpoint = f"/a/changes/{quoted_change}/revisions/{rev}/patch"
  raw_b64 = client.request(endpoint, raw_response=True)
  decoded_bytes = base64.b64decode(raw_b64)
  if args.raw:
    sys.stdout.buffer.write(decoded_bytes)
  else:
    patch_text = decoded_bytes.decode("utf-8", errors="replace")
    _print_untrusted(patch_text, host=client.host, change_id=str(change_id))


def cmd_files(client: GerritClient, args: argparse.Namespace) -> None:
  """Lists files modified in a change."""
  change_id = _require_value(args.change, "change")
  rev = _quote_id(args.revision or "current")
  endpoint = f"/a/changes/{_quote_id(change_id)}/revisions/{rev}/files/"
  files_map = client.request(endpoint) or {}
  if args.json:
    print(json.dumps(files_map, indent=2))
  else:
    # File paths are author-controlled, so they go inside the envelope too.
    _print_untrusted(
        sorted(files_map.keys()), host=client.host, change_id=str(change_id)
    )


def cmd_content(client: GerritClient, args: argparse.Namespace) -> None:
  """Outputs decoded file content from a change."""
  change_id = _require_value(args.change, "change")
  file_path = _require_value(args.path, "--path")
  rev = _quote_id(args.revision or "current")
  endpoint = (
      f"/a/changes/{_quote_id(change_id)}/revisions/{rev}"
      f"/files/{_quote_id(file_path)}/content"
  )
  raw_b64 = client.request(endpoint, raw_response=True)
  decoded_bytes = base64.b64decode(raw_b64)
  if args.raw:
    sys.stdout.buffer.write(decoded_bytes)
  else:
    file_text = decoded_bytes.decode("utf-8", errors="replace")
    _print_untrusted(file_text, host=client.host, change_id=str(change_id))


def cmd_commit_message(client: GerritClient, args: argparse.Namespace) -> None:
  """Views or updates the commit message on a change."""
  change_id = _require_value(args.change, "change")
  quoted_change = _quote_id(change_id)
  if args.action == "get":
    rev = _quote_id(args.revision or "current")
    endpoint = f"/a/changes/{quoted_change}/revisions/{rev}/commit"
    commit_data = client.request(endpoint) or {}
    if args.json:
      print(json.dumps(commit_data, indent=2))
    else:
      _print_untrusted(
          commit_data.get("message", ""),
          host=client.host,
          change_id=str(change_id),
      )
  elif args.action == "set":
    new_message = _read_message_arg(args)
    payload: dict[str, Any] = {"message": new_message}
    if args.notify:
      payload["notify"] = args.notify
    client.request(
        f"/a/changes/{quoted_change}/message", method="PUT", payload=payload
    )
    print("Commit message updated.")


def _parse_comment_range(range_spec: str) -> dict[str, int]:
  """Parses 'start_line,start_col:end_line,end_col' into Gerrit CommentRange."""
  try:
    start_part, end_part = range_spec.split(":", 1)
    start_line, start_col = start_part.split(",", 1)
    end_line, end_col = end_part.split(",", 1)
    return {
        "start_line": int(start_line),
        "start_character": int(start_col),
        "end_line": int(end_line),
        "end_character": int(end_col),
    }
  except ValueError as err:
    raise UsageError(
        f"Invalid --range '{range_spec}'. Expected"
        " start_line,start_col:end_line,end_col."
    ) from err


def cmd_comments(client: GerritClient, args: argparse.Namespace) -> None:
  """Lists, posts, replies to, or publishes review comments."""
  change_id = _require_value(args.change, "change")
  quoted_change = _quote_id(change_id)
  if args.action == "list":
    if args.revision:
      rev = _quote_id(args.revision)
      endpoint = f"/a/changes/{quoted_change}/revisions/{rev}/comments"
    else:
      endpoint = f"/a/changes/{quoted_change}/comments"
    comments_by_file = client.request(endpoint) or {}
    if args.json:
      print(json.dumps(comments_by_file, indent=2))
      return

    output_blocks: list[str] = []
    for file_path, comment_items in sorted(comments_by_file.items()):
      replied_ids = {
          item.get("in_reply_to")
          for item in comment_items
          if item.get("in_reply_to")
      }
      for item in comment_items:
        is_leaf_unresolved = item.get("id") not in replied_ids and bool(
            item.get("unresolved")
        )
        if args.unresolved and not is_leaf_unresolved:
          continue
        author_obj = item.get("author", {})
        if args.author and not _matches_author(author_obj, args.author):
          continue
        line_num = item.get("line", "-")
        state = "UNRESOLVED" if item.get("unresolved") else "RESOLVED"
        author_label = (
            author_obj.get("name") or author_obj.get("email") or "Unknown"
        )
        msg_body = item.get("message", "").strip()
        output_blocks.append(
            f"[{item.get('id')}] {file_path}:{line_num} ({state})"
            f" {author_label}:\n  {msg_body}\n"
        )
    _print_untrusted(output_blocks, host=client.host, change_id=str(change_id))

  elif args.action == "post":
    target_path = _require_value(args.path, "--path")
    msg_body = _read_message_arg(args)
    rev = _quote_id(args.revision or "current")
    draft_payload: dict[str, Any] = {
        "path": target_path,
        "message": msg_body,
        "unresolved": not args.resolved,
    }
    if args.line is not None:
      draft_payload["line"] = args.line
    if args.range:
      draft_payload["range"] = _parse_comment_range(args.range)
    if args.tag:
      draft_payload["tag"] = args.tag
    endpoint = f"/a/changes/{quoted_change}/revisions/{rev}/drafts"
    created = client.request(endpoint, method="PUT", payload=draft_payload)
    print(f"Draft comment created: id={(created or {}).get('id')}")

  elif args.action == "reply":
    parent_id = _require_value(args.comment_id, "--comment-id")
    msg_body = _read_message_arg(args)
    all_comments = client.request(f"/a/changes/{quoted_change}/comments") or {}
    parent_comment = None
    parent_path = None
    for file_path, comment_items in all_comments.items():
      for item in comment_items:
        if item.get("id") == parent_id:
          parent_comment = item
          parent_path = file_path
          break
      if parent_comment:
        break

    if not parent_comment:
      raise RuntimeError(
          f"Parent comment with ID '{parent_id}' not found on change."
      )

    patch_set = _quote_id(parent_comment.get("patch_set", "current"))
    if args.resolved:
      reply_unresolved = False
    elif args.unresolved:
      reply_unresolved = True
    else:
      # Keep the thread's current state so an acknowledgment doesn't reopen
      # a resolved thread.
      reply_unresolved = bool(parent_comment.get("unresolved", False))
    reply_payload: dict[str, Any] = {
        "path": parent_path,
        "in_reply_to": parent_id,
        "message": msg_body,
        "unresolved": reply_unresolved,
    }
    for preserved_key in ("line", "range", "side"):
      if preserved_key in parent_comment:
        reply_payload[preserved_key] = parent_comment[preserved_key]
    if args.tag:
      reply_payload["tag"] = args.tag

    endpoint = f"/a/changes/{quoted_change}/revisions/{patch_set}/drafts"
    created = client.request(endpoint, method="PUT", payload=reply_payload)
    print(f"Draft reply created: id={(created or {}).get('id')}")

  elif args.action == "publish":
    rev = _quote_id(args.revision or "current")
    review_payload: dict[str, Any] = {"drafts": "PUBLISH_ALL_REVISIONS"}
    if args.message or args.message_file:
      review_payload["message"] = _read_message_arg(args)
    if args.labels:
      parsed_labels: dict[str, int] = {}
      for pair in args.labels.split(","):
        if "=" not in pair:
          raise UsageError(
              f"Invalid label vote '{pair}'. Expected Label-Name=value."
          )
        label_name, vote_str = pair.split("=", 1)
        try:
          parsed_labels[label_name.strip()] = int(vote_str.strip())
        except ValueError as err:
          raise UsageError(
              f"Invalid label vote '{pair}'. Vote must be an integer."
          ) from err
      review_payload["labels"] = parsed_labels
    if args.tag:
      review_payload["tag"] = args.tag
    if args.notify:
      review_payload["notify"] = args.notify
    if args.attention:
      review_payload["add_to_attention_set"] = [
          {"user": args.attention, "reason": "Review published"}
      ]
    endpoint = f"/a/changes/{quoted_change}/revisions/{rev}/review"
    client.request(endpoint, method="POST", payload=review_payload)
    print("Draft comments published.")


def cmd_drafts(client: GerritClient, args: argparse.Namespace) -> None:
  """Lists, views, updates, deletes, or discards unpublished draft comments."""
  change_id = _require_value(args.change, "change")
  quoted_change = _quote_id(change_id)
  if args.action == "list":
    drafts_map = client.request(f"/a/changes/{quoted_change}/drafts") or {}
    if args.json:
      print(json.dumps(drafts_map, indent=2))
      return
    lines: list[str] = []
    for file_path, draft_items in sorted(drafts_map.items()):
      for item in draft_items:
        ps_num = item.get("patch_set", "current")
        line_num = item.get("line", "-")
        state = "UNRESOLVED" if item.get("unresolved") else "RESOLVED"
        msg_body = item.get("message", "").strip()
        lines.append(
            f"[{item.get('id')}] ps={ps_num} {file_path}:{line_num} ({state}):"
            f"\n  {msg_body}\n"
        )
    _print_untrusted(lines, host=client.host, change_id=str(change_id))

  elif args.action == "get":
    draft_id = _quote_id(_require_value(args.draft_id, "--draft-id"))
    rev = _quote_id(args.revision or "current")
    endpoint = f"/a/changes/{quoted_change}/revisions/{rev}/drafts/{draft_id}"
    draft_item = client.request(endpoint) or {}
    if args.json:
      print(json.dumps(draft_item, indent=2))
      return
    file_path = draft_item.get("path", "")
    line_num = draft_item.get("line", "-")
    state = "UNRESOLVED" if draft_item.get("unresolved") else "RESOLVED"
    summary = (
        f"[{draft_item.get('id')}] {file_path}:{line_num} ({state}):\n"
        f"  {draft_item.get('message', '').strip()}"
    )
    _print_untrusted(summary, host=client.host, change_id=str(change_id))

  elif args.action == "update":
    draft_id = _quote_id(_require_value(args.draft_id, "--draft-id"))
    new_message = _read_message_arg(args)
    rev = _quote_id(args.revision or "current")
    endpoint = f"/a/changes/{quoted_change}/revisions/{rev}/drafts/{draft_id}"
    existing = client.request(endpoint) or {}
    update_payload: dict[str, Any] = {"message": new_message}
    for preserved_key in (
        "path",
        "line",
        "range",
        "side",
        "in_reply_to",
        "unresolved",
        "tag",
    ):
      if preserved_key in existing:
        update_payload[preserved_key] = existing[preserved_key]
    if args.resolved:
      update_payload["unresolved"] = False
    elif args.unresolved:
      update_payload["unresolved"] = True
    if args.tag:
      update_payload["tag"] = args.tag
    updated = client.request(endpoint, method="PUT", payload=update_payload)
    print(f"Draft {(updated or {}).get('id', args.draft_id)} updated.")

  elif args.action == "delete":
    draft_id = _quote_id(_require_value(args.draft_id, "--draft-id"))
    rev = _quote_id(args.revision or "current")
    endpoint = f"/a/changes/{quoted_change}/revisions/{rev}/drafts/{draft_id}"
    client.request(endpoint, method="DELETE")
    print(f"Draft {args.draft_id} deleted.")

  elif args.action == "discard":
    drafts_map = client.request(f"/a/changes/{quoted_change}/drafts") or {}
    deleted_count = 0
    for draft_items in drafts_map.values():
      for item in draft_items:
        draft_id = _quote_id(item.get("id"))
        patch_set = _quote_id(item.get("patch_set", "current"))
        client.request(
            f"/a/changes/{quoted_change}/revisions/{patch_set}/drafts/"
            f"{draft_id}",
            method="DELETE",
        )
        deleted_count += 1
    print(f"Discarded {deleted_count} draft(s).")


def cmd_messages(client: GerritClient, args: argparse.Namespace) -> None:
  """Lists or posts change-level review messages."""
  change_id = _require_value(args.change, "change")
  quoted_change = _quote_id(change_id)
  if args.action == "list":
    messages = client.request(f"/a/changes/{quoted_change}/messages") or []
    if args.author:
      messages = [
          msg
          for msg in messages
          if _matches_author(msg.get("author", {}), args.author)
      ]
    if args.json:
      print(json.dumps(messages, indent=2))
      return
    blocks = []
    for msg in messages:
      author_obj = msg.get("author", {})
      author_name = (
          author_obj.get("name") or author_obj.get("email") or "Unknown"
      )
      ps_label = msg.get("_revision_number", "?")
      blocks.append(
          f"[{msg.get('date', '')}] (patchset {ps_label}) {author_name}:\n"
          f"{msg.get('message', '').strip()}\n"
      )
    _print_untrusted(blocks, host=client.host, change_id=str(change_id))

  elif args.action == "post":
    msg_body = _read_message_arg(args)
    payload: dict[str, Any] = {"message": msg_body}
    if args.tag:
      payload["tag"] = args.tag
    if args.notify:
      payload["notify"] = args.notify
    client.request(
        f"/a/changes/{quoted_change}/revisions/current/review",
        method="POST",
        payload=payload,
    )
    print("Message posted.")


def cmd_reviewers(client: GerritClient, args: argparse.Namespace) -> None:
  """Lists, adds, or removes reviewers and CCs on a change."""
  change_id = _require_value(args.change, "change")
  quoted_change = _quote_id(change_id)
  if args.action == "list":
    reviewers = client.request(f"/a/changes/{quoted_change}/reviewers") or []
    if args.json:
      print(json.dumps(reviewers, indent=2))
    elif args.emails_only:
      for reviewer in reviewers:
        email = reviewer.get("email")
        if email:
          print(email)
    else:
      # Display names are user-chosen free text.
      _print_untrusted(
          [
              f"{reviewer.get('name', 'Unknown')} <{reviewer.get('email', '')}>"
              f" (id: {reviewer.get('_account_id')})"
              for reviewer in reviewers
          ],
          host=client.host,
          change_id=str(change_id),
      )
  elif args.action == "add":
    reviewer_id = _require_value(args.reviewer, "--reviewer")
    state = args.state or "REVIEWER"
    reviewer_entry = {"reviewer": reviewer_id, "state": state}
    if args.ready:
      client.request(
          f"/a/changes/{quoted_change}/revisions/current/review",
          method="POST",
          payload={"ready": True, "reviewers": [reviewer_entry]},
      )
    else:
      client.request(
          f"/a/changes/{quoted_change}/reviewers",
          method="POST",
          payload=reviewer_entry,
      )
    print(f"Added {reviewer_id} as {state}.")
  elif args.action == "remove":
    reviewer_id = _require_value(args.reviewer, "--reviewer")
    client.request(
        f"/a/changes/{quoted_change}/reviewers/{_quote_id(reviewer_id)}",
        method="DELETE",
    )
    print(f"Removed {reviewer_id}.")


def cmd_checks(client: GerritClient, args: argparse.Namespace) -> None:
  """Fetches check runs (and legacy robot comments if supported)."""
  change_id = _require_value(args.change, "change")
  quoted_change = _quote_id(change_id)
  rev = _quote_id(args.revision or "current")
  checks: list[Any] = []
  checks_available = False
  for checks_ep in (
      f"/a/changes/{quoted_change}/revisions/{rev}/checks/",
      f"/a/changes/{quoted_change}/revisions/{rev}/checks~checks",
  ):
    try:
      result = client.request(checks_ep)
    except GerritHttpError as err:
      if err.status in _ENDPOINT_MISSING_STATUSES:
        # Checks plugin not installed on this host; try the fallback path.
        continue
      raise
    if not isinstance(result, list):
      raise RuntimeError(
          f"Unexpected checks response from {checks_ep}: {result!r:.200}"
      )
    checks = result
    checks_available = True
    break

  robot_comments: dict[str, Any] = {}
  robot_comments_available = False
  try:
    rc_result = client.request(
        f"/a/changes/{quoted_change}/revisions/{rev}/robotcomments"
    )
    robot_comments_available = True
    if isinstance(rc_result, dict):
      robot_comments = rc_result
  except GerritHttpError as err:
    # Gerrit 3.13+ removed /robotcomments; only tolerate a missing endpoint.
    if err.status not in _ENDPOINT_MISSING_STATUSES:
      raise

  if args.json:
    print(
        json.dumps(
            {
                "checks_available": checks_available,
                "checks": checks,
                "robotcomments": robot_comments,
            },
            indent=2,
        )
    )
    return

  if not checks_available and not robot_comments_available:
    print(
        f"Checks API is not available on {client.host} (no checks plugin)."
        " Inspect label votes such as Verified with 'change --json' instead."
    )
    return
  if not checks and not robot_comments:
    print(f"No checks found for change {change_id}.")
    return

  lines: list[str] = []
  for check in checks:
    checker_name = (
        check.get("checker_name") or check.get("checker_uuid") or "check"
    )
    state = check.get("state", "UNKNOWN")
    url = check.get("url", "")
    summary = f"{checker_name}: {state}"
    if url:
      summary += f" ({url})"
    lines.append(summary)
  for file_path, items in sorted(robot_comments.items()):
    for item in items:
      robot_id = item.get("robot_id", "robot")
      line_num = item.get("line", "-")
      msg = item.get("message", "").strip()
      lines.append(f"[robot:{robot_id}] {file_path}:{line_num}: {msg}")
  _print_untrusted(lines, host=client.host, change_id=str(change_id))


def cmd_cherry_pick(client: GerritClient, args: argparse.Namespace) -> None:
  """Cherry-picks a change onto another destination branch."""
  change_id = _require_value(args.change, "change")
  destination = _require_value(args.destination, "--destination")
  rev = _quote_id(args.revision or "current")
  payload: dict[str, Any] = {"destination": destination}
  if args.message or args.message_file:
    payload["message"] = _read_message_arg(args)
  if args.allow_conflicts:
    payload["allow_conflicts"] = True
  endpoint = f"/a/changes/{_quote_id(change_id)}/revisions/{rev}/cherrypick"
  created = client.request(endpoint, method="POST", payload=payload) or {}
  cp_of = created.get("cherry_pick_of_change")
  print(
      f"Cherry-pick created: number={created.get('_number')},"
      f" change_id={created.get('change_id')},"
      f" cherry_pick_of_change={cp_of}"
  )


def cmd_search(client: GerritClient, args: argparse.Namespace) -> None:
  """Searches for changes matching a Gerrit query string."""
  query_str = _require_value(args.query, "query")
  limit = args.limit if args.limit is not None else 10
  encoded_query = urllib.parse.quote(query_str, safe="+:")
  skip = args.skip
  max_pages = _MAX_SEARCH_PAGES if args.all else 1
  changes: list[dict[str, Any]] = []
  more_changes = False
  for _ in range(max_pages):
    endpoint = f"/a/changes/?q={encoded_query}&n={limit}"
    if skip:
      endpoint += f"&S={skip}"
    page = client.request(endpoint) or []
    changes.extend(page)
    skip += len(page)
    more_changes = bool(page) and bool(page[-1].get("_more_changes"))
    if not more_changes:
      break
  if more_changes:
    if args.all:
      sys.stderr.write(
          f"Stopped after {_MAX_SEARCH_PAGES} pages; more results are"
          f" available. Rerun with --skip={skip} to continue.\n"
      )
    else:
      sys.stderr.write(
          f"More results available: rerun with --skip={skip}, or pass --all"
          " to fetch every page.\n"
      )
  if args.json:
    print(json.dumps(changes, indent=2))
    return

  lines = []
  for change in changes:
    owner_name = change.get("owner", {}).get("name", "Unknown")
    lines.append(
        f"[{change.get('_number')}] {change.get('subject')}"
        f" ({change.get('status')}) - {owner_name}"
    )
  _print_untrusted(lines, host=client.host)


def cmd_submit(client: GerritClient, args: argparse.Namespace) -> None:
  """Submits an approved change."""
  change_id = _require_value(args.change, "change")
  endpoint = f"/a/changes/{_quote_id(change_id)}/submit"
  submitted = client.request(endpoint, method="POST", payload={}) or {}
  print(f"Change {change_id} submitted (status: {submitted.get('status')}).")


def cmd_abandon(client: GerritClient, args: argparse.Namespace) -> None:
  """Abandons a change."""
  change_id = _require_value(args.change, "change")
  payload: dict[str, Any] = {}
  if args.message:
    payload["message"] = args.message
  if args.notify:
    payload["notify"] = args.notify
  endpoint = f"/a/changes/{_quote_id(change_id)}/abandon"
  abandoned = client.request(endpoint, method="POST", payload=payload) or {}
  print(f"Change {change_id} abandoned (status: {abandoned.get('status')}).")


def cmd_topic(client: GerritClient, args: argparse.Namespace) -> None:
  """Views, sets, or deletes the topic on a change."""
  change_id = _require_value(args.change, "change")
  endpoint = f"/a/changes/{_quote_id(change_id)}/topic"
  if args.delete:
    client.request(endpoint, method="DELETE")
    print(f"Topic deleted from change {change_id}.")
  elif args.topic is not None:
    client.request(endpoint, method="PUT", payload={"topic": args.topic})
    print(f"Topic set to '{args.topic}'.")
  else:
    topic = client.request(endpoint)
    _print_untrusted(
        str(topic or ""), host=client.host, change_id=str(change_id)
    )


def cmd_hashtags(client: GerritClient, args: argparse.Namespace) -> None:
  """Adds or removes hashtags on a change."""
  change_id = _require_value(args.change, "change")
  payload: dict[str, Any] = {}
  if args.add:
    payload["add"] = [tag.strip() for tag in args.add.split(",") if tag.strip()]
  if args.remove:
    payload["remove"] = [
        tag.strip() for tag in args.remove.split(",") if tag.strip()
    ]
  endpoint = f"/a/changes/{_quote_id(change_id)}/hashtags"
  updated_tags = client.request(endpoint, method="POST", payload=payload)
  formatted = (
      ", ".join(updated_tags)
      if isinstance(updated_tags, list)
      else str(updated_tags or "")
  )
  _print_untrusted(
      f"Hashtags: {formatted}", host=client.host, change_id=str(change_id)
  )


def cmd_labels(client: GerritClient, args: argparse.Namespace) -> None:
  """Lists labels and votes on a change, or repository label definitions."""
  if args.project:
    quoted_project = _quote_id(args.project)
    endpoint = f"/a/projects/{quoted_project}/labels/?inherited"
    if args.branch:
      quoted_branch = urllib.parse.quote(args.branch, safe="")
      endpoint += f"&voteable-on-ref={quoted_branch}"
    definitions = client.request(endpoint)
    _print_json_maybe_untrusted(definitions, args, host=client.host)
    return

  change_id = _require_value(args.change, "change or --project")
  detail = client.request(f"/a/changes/{_quote_id(change_id)}/detail") or {}
  _print_json_maybe_untrusted(
      detail.get("labels", {}), args, host=client.host, change_id=change_id
  )


def cmd_attention(client: GerritClient, args: argparse.Namespace) -> None:
  """Lists, adds to, or removes from a change's attention set."""
  change_id = _require_value(args.change, "change")
  quoted_change = _quote_id(change_id)
  if args.user and args.remove:
    quoted_user = _quote_id(args.user)
    payload = {"reason": args.reason or "action taken"}
    client.request(
        f"/a/changes/{quoted_change}/attention/{quoted_user}/delete",
        method="POST",
        payload=payload,
    )
    print(f"Removed {args.user} from attention set.")
  elif args.user:
    payload = {"user": args.user, "reason": args.reason or "needs review"}
    client.request(
        f"/a/changes/{quoted_change}/attention",
        method="POST",
        payload=payload,
    )
    print(f"Added {args.user} to attention set.")
  else:
    detail = client.request(f"/a/changes/{quoted_change}/detail") or {}
    _print_json_maybe_untrusted(
        detail.get("attention_set", {}),
        args,
        host=client.host,
        change_id=change_id,
    )


def _add_change_args(subparser: argparse.ArgumentParser) -> None:
  """Adds positional and --change flag arguments to a subparser."""
  subparser.add_argument("change", nargs="?", help="Change number or Change-Id")
  subparser.add_argument(
      "--change", dest="change_flag", help="Change number or Change-Id"
  )


def build_parser() -> argparse.ArgumentParser:
  """Builds and returns the top-level CLI ArgumentParser."""
  root_common = argparse.ArgumentParser(add_help=False)
  root_common.add_argument(
      "--host",
      default=None,
      help=(
          "Gerrit review host URL (e.g."
          " https://android-review.googlesource.com)"
      ),
  )
  root_common.add_argument(
      "--cookiefile",
      default=None,
      help="Path to git cookiefile (defaults to ~/.gitcookies)",
  )
  root_common.add_argument(
      "--anonymous",
      action="store_true",
      default=False,
      help="Send no credentials and use unauthenticated endpoints",
  )

  common = argparse.ArgumentParser(add_help=False)
  common.add_argument(
      "--host",
      default=argparse.SUPPRESS,
      help=(
          "Gerrit review host URL (e.g."
          " https://android-review.googlesource.com)"
      ),
  )
  common.add_argument(
      "--cookiefile",
      default=argparse.SUPPRESS,
      help="Path to git cookiefile (defaults to ~/.gitcookies)",
  )
  common.add_argument(
      "--anonymous",
      action="store_true",
      default=argparse.SUPPRESS,
      help="Send no credentials and use unauthenticated endpoints",
  )

  parser = argparse.ArgumentParser(
      description="Standalone Gerrit Code Review REST API CLI.",
      parents=[root_common],
  )
  subparsers = parser.add_subparsers(dest="subcommand", required=True)

  p_change = subparsers.add_parser(
      "change",
      aliases=["info"],
      help="View change details and metadata",
      parents=[common],
  )
  _add_change_args(p_change)
  p_change.add_argument("--revision", help="Revision SHA or patch set number")
  p_change.add_argument("--json", action="store_true", help="Output raw JSON")

  p_diff = subparsers.add_parser(
      "diff", help="View unified code diff", parents=[common]
  )
  _add_change_args(p_diff)
  p_diff.add_argument("--revision", help="Revision SHA or patch set number")
  p_diff.add_argument(
      "--base", help="Base patch set number for inter-patchset diff"
  )
  p_diff.add_argument(
      "--raw",
      action="store_true",
      help="Output raw unified diff without <untrusted_gerrit_data> delimiters",
  )

  p_files = subparsers.add_parser(
      "files", help="List modified files in a change", parents=[common]
  )
  _add_change_args(p_files)
  p_files.add_argument("--revision", help="Revision SHA or patch set number")
  p_files.add_argument("--json", action="store_true", help="Output raw JSON")

  p_content = subparsers.add_parser(
      "content",
      help="View decoded file content from a change",
      parents=[common],
  )
  _add_change_args(p_content)
  p_content.add_argument(
      "--path", required=True, help="File path within the repository"
  )
  p_content.add_argument("--revision", help="Revision SHA or patch set number")
  p_content.add_argument(
      "--raw",
      action="store_true",
      help="Output raw bytes without <untrusted_gerrit_data> delimiters",
  )

  p_cm = subparsers.add_parser(
      "commit-message",
      help="View or update a change's commit message",
      parents=[common],
  )
  p_cm.add_argument("action", choices=["get", "set"], help="get or set")
  _add_change_args(p_cm)
  p_cm.add_argument("--revision", help="Revision SHA or patch set number")
  p_cm.add_argument("--message", help="New commit message")
  p_cm.add_argument(
      "--message-file", help="Path to file containing commit message"
  )
  p_cm.add_argument("--notify", help="Notification level (NONE, OWNER, ALL)")
  p_cm.add_argument("--json", action="store_true", help="Output raw JSON")

  p_comments = subparsers.add_parser(
      "comments",
      help="List, post, reply to, or publish review comments",
      parents=[common],
  )
  p_comments.add_argument(
      "action", choices=["list", "post", "reply", "publish"]
  )
  _add_change_args(p_comments)
  p_comments.add_argument("--revision", help="Revision SHA or patch set number")
  p_comments.add_argument("--path", help="File path for inline comment")
  p_comments.add_argument("--line", type=int, help="Line number for comment")
  p_comments.add_argument(
      "--range",
      help="Character range (start_line,start_col:end_line,end_col)",
  )
  p_comments.add_argument("--comment-id", help="Parent comment ID for reply")
  p_comments.add_argument("--message", help="Comment or review message text")
  p_comments.add_argument("--message-file", help="Path to message text file")
  p_comments.add_argument(
      "--resolved", action="store_true", help="Mark draft comment resolved"
  )
  p_comments.add_argument(
      "--unresolved",
      action="store_true",
      help="list: only unresolved threads; post/reply: mark unresolved",
  )
  p_comments.add_argument(
      "--author",
      help=(
          "Filter by email domain ('@example.com') or exact email, username,"
          " or display name"
      ),
  )
  p_comments.add_argument(
      "--labels", help="Comma-separated label votes (e.g. Code-Review=1)"
  )
  p_comments.add_argument(
      "--attention", help="User email to add to attention set on publish"
  )
  p_comments.add_argument("--tag", help="Review tag (e.g. autogenerated:agent)")
  p_comments.add_argument(
      "--notify", help="Notification level (NONE, OWNER, OWNER_REVIEWERS, ALL)"
  )
  p_comments.add_argument("--json", action="store_true", help="Output raw JSON")

  p_drafts = subparsers.add_parser(
      "drafts", help="Manage unpublished draft comments", parents=[common]
  )
  p_drafts.add_argument(
      "action", choices=["list", "get", "update", "delete", "discard"]
  )
  _add_change_args(p_drafts)
  p_drafts.add_argument("--draft-id", help="Draft comment ID")
  p_drafts.add_argument("--revision", help="Revision SHA or patch set number")
  p_drafts.add_argument("--message", help="Updated draft message text")
  p_drafts.add_argument(
      "--message-file", help="Path to file with updated draft message"
  )
  p_drafts.add_argument(
      "--resolved", action="store_true", help="Mark draft resolved on update"
  )
  p_drafts.add_argument(
      "--unresolved",
      action="store_true",
      help="Mark draft unresolved on update",
  )
  p_drafts.add_argument("--tag", help="Optional tag on updated draft")
  p_drafts.add_argument("--json", action="store_true", help="Output raw JSON")

  p_messages = subparsers.add_parser(
      "messages", help="List or post change messages", parents=[common]
  )
  p_messages.add_argument("action", choices=["list", "post"])
  _add_change_args(p_messages)
  p_messages.add_argument(
      "--author",
      help=(
          "Filter by email domain ('@example.com') or exact email, username,"
          " or display name"
      ),
  )
  p_messages.add_argument("--message", help="Message text to post")
  p_messages.add_argument("--message-file", help="Path to message text file")
  p_messages.add_argument("--tag", help="Optional tag (e.g. autogenerated:ci)")
  p_messages.add_argument("--notify", help="Notification level (NONE, ALL)")
  p_messages.add_argument("--json", action="store_true", help="Output raw JSON")

  p_rev = subparsers.add_parser(
      "reviewers", help="Manage reviewers and CCs", parents=[common]
  )
  p_rev.add_argument("action", choices=["list", "add", "remove"])
  _add_change_args(p_rev)
  p_rev.add_argument("--reviewer", help="Reviewer email address")
  p_rev.add_argument(
      "--state",
      choices=["REVIEWER", "CC"],
      default="REVIEWER",
      help="Reviewer role state",
  )
  p_rev.add_argument(
      "--ready", action="store_true", help="Mark WIP change ready for review"
  )
  p_rev.add_argument(
      "--emails-only",
      action="store_true",
      help="Print one reviewer email per line",
  )
  p_rev.add_argument("--json", action="store_true", help="Output raw JSON")

  p_checks = subparsers.add_parser(
      "checks",
      help="View presubmit check runs and robot comments",
      parents=[common],
  )
  _add_change_args(p_checks)
  p_checks.add_argument("--revision", help="Revision SHA or patch set number")
  p_checks.add_argument("--json", action="store_true", help="Output raw JSON")

  p_cp = subparsers.add_parser(
      "cherry-pick",
      help="Cherry-pick a change onto another branch",
      parents=[common],
  )
  _add_change_args(p_cp)
  p_cp.add_argument(
      "--destination", required=True, help="Target destination branch"
  )
  p_cp.add_argument("--message", help="Custom commit message for cherry-pick")
  p_cp.add_argument(
      "--message-file", help="Path to file with custom commit message"
  )
  p_cp.add_argument("--revision", help="Source revision to cherry-pick")
  p_cp.add_argument(
      "--allow-conflicts",
      action="store_true",
      help="Create WIP cherry-pick even if git conflicts occur",
  )

  p_search = subparsers.add_parser(
      "search", help="Search for changes", parents=[common]
  )
  p_search.add_argument("query", nargs="?", help="Gerrit search query string")
  p_search.add_argument(
      "--query", dest="query_flag", help="Gerrit search query string"
  )
  p_search.add_argument("--limit", type=int, default=10, help="Max results")
  p_search.add_argument(
      "--skip", type=int, default=0, help="Number of results to skip (S=)"
  )
  p_search.add_argument(
      "--all",
      action="store_true",
      help=(
          "Fetch every page of results (up to"
          f" {_MAX_SEARCH_PAGES} pages of --limit each)"
      ),
  )
  p_search.add_argument("--json", action="store_true", help="Output raw JSON")

  p_submit = subparsers.add_parser(
      "submit", help="Submit an approved change", parents=[common]
  )
  _add_change_args(p_submit)

  p_abandon = subparsers.add_parser(
      "abandon", help="Abandon a change", parents=[common]
  )
  _add_change_args(p_abandon)
  p_abandon.add_argument("--message", help="Reason for abandoning")
  p_abandon.add_argument("--notify", help="Notification level")

  p_topic = subparsers.add_parser(
      "topic", help="View, set, or delete a change topic", parents=[common]
  )
  _add_change_args(p_topic)
  p_topic.add_argument("--topic", help="Topic name to set")
  p_topic.add_argument("--delete", action="store_true", help="Delete topic")

  p_tags = subparsers.add_parser(
      "hashtags", help="Add or remove hashtags on a change", parents=[common]
  )
  _add_change_args(p_tags)
  p_tags.add_argument("--add", help="Comma-separated hashtags to add")
  p_tags.add_argument("--remove", help="Comma-separated hashtags to remove")

  p_labels = subparsers.add_parser(
      "labels",
      help="List change label votes or project label definitions",
      parents=[common],
  )
  _add_change_args(p_labels)
  p_labels.add_argument(
      "--project", help="Project repository name to inspect label definitions"
  )
  p_labels.add_argument(
      "--branch", help="Branch/ref filter for voteable project labels"
  )
  p_labels.add_argument("--json", action="store_true", help="Output raw JSON")

  p_attn = subparsers.add_parser(
      "attention",
      help="List or modify the attention set on a change",
      parents=[common],
  )
  _add_change_args(p_attn)
  p_attn.add_argument("--user", help="User email address")
  p_attn.add_argument("--reason", help="Reason for attention set update")
  p_attn.add_argument(
      "--remove", action="store_true", help="Remove user from attention set"
  )
  p_attn.add_argument("--json", action="store_true", help="Output raw JSON")

  return parser


_DISPATCH_TABLE = {
    "change": cmd_change,
    "info": cmd_change,
    "diff": cmd_diff,
    "files": cmd_files,
    "content": cmd_content,
    "commit-message": cmd_commit_message,
    "comments": cmd_comments,
    "drafts": cmd_drafts,
    "messages": cmd_messages,
    "reviewers": cmd_reviewers,
    "checks": cmd_checks,
    "cherry-pick": cmd_cherry_pick,
    "search": cmd_search,
    "submit": cmd_submit,
    "abandon": cmd_abandon,
    "topic": cmd_topic,
    "hashtags": cmd_hashtags,
    "labels": cmd_labels,
    "attention": cmd_attention,
}


def main(argv: Sequence[str] | None = None) -> int:
  """CLI entry point returning POSIX exit status."""
  parser = build_parser()
  args = parser.parse_args(argv)

  if getattr(args, "change_flag", None):
    args.change = args.change_flag
  if getattr(args, "query_flag", None):
    args.query = args.query_flag

  host = args.host or detect_git_host()
  if not host:
    sys.stderr.write(
        "Error: Gerrit host URL is required. Pass --host (for example,"
        " --host=https://android-review.googlesource.com) or run inside a git"
        " repository with configured Gerrit remotes.\n"
    )
    return 2

  handler = _DISPATCH_TABLE.get(args.subcommand)
  if handler is None:
    parser.print_help()
    return 2

  try:
    client = GerritClient(
        host=host, cookiefile=args.cookiefile, anonymous=args.anonymous
    )
    handler(client, args)
    return 0
  except UsageError as err:
    sys.stderr.write(f"Usage error: {err}\n")
    return 2
  except (RuntimeError, OSError, ValueError) as err:
    sys.stderr.write(f"Error: {err}\n")
    return 1


if __name__ == "__main__":
  sys.exit(main())
