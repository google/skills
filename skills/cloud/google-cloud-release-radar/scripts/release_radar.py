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
"""Google Cloud Release Radar CLI (Python Standard Library).

Tracks, queries, and summarizes official Google Cloud release notes across 370+
products and curated product bundles using a customizable watchlist.

Capabilities:
- Manage personal or project watchlists (--add, --remove, --set-products,
  --list-subscriptions, --list-catalog, --dry-run).
- Concurrently fetch official Atom/RSS release note feeds for subscribed
  products and curated product bundles (All AI Products, All Data Products,
  All App Mod Products, All Security Products).
- Strip noisy "Libraries" boilerplate sections and diff entry hashes against
  local state so "--since-last-check" only returns genuinely new updates.
- Enrich brief release notes by fetching linked docs.cloud.google.com pages
  (preferring raw Markdown via .md.txt URLs).
- Optional Google Chat delivery via incoming webhook (--notify-webhook).
"""

import argparse
from concurrent import futures
import datetime
import email.utils
import hashlib
import html
from html import parser as html_parser
import json
import os
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
CATALOG_PATH = os.path.join(SKILL_DIR, "references", "catalog.json")
SKILL_MD_PATH = os.path.join(SKILL_DIR, "SKILL.md")

DEFAULT_CONFIG_DIR = os.path.expanduser(
    os.environ.get(
        "GOOGLE_CLOUD_RELEASE_RADAR_DIR",
        "~/.config/google-cloud-release-radar",
    )
)
DEFAULT_SUBSCRIPTIONS_PATH = os.path.join(
    DEFAULT_CONFIG_DIR, "subscriptions.json"
)
DEFAULT_STATE_PATH = os.path.join(DEFAULT_CONFIG_DIR, "seen_state.json")

USER_AGENT = (
    "Mozilla/5.0 (compatible; GoogleCloudReleaseRadar/1.0) "
    "agent-skills/1.0 (skill:google-cloud-release-radar)"
)

LABEL_ICONS = {
    "feature": "✨",
    "announcement": "📣",
    "changed": "🔧",
    "change": "🔧",
    "breaking": "🚨",
    "fixed": "🐛",
    "fix": "🐛",
    "deprecated": "⚠️",
    "deprecation": "⚠️",
    "issue": "⚠️",
    "security": "🔒",
    "libraries": "📦",
}


class HTMLToMarkdownParser(html_parser.HTMLParser):
  """Lightweight stdlib HTML-to-Markdown converter for release notes."""

  def __init__(self, base_url: str = "https://docs.cloud.google.com"):
    super().__init__()
    self.base_url = base_url
    self.parts: list[str] = []
    self._href: str | None = None
    self._link_text: list[str] = []
    self._in_li = False

  def _emit(self, text: str) -> None:
    if self._href is not None:
      self._link_text.append(text)
    else:
      self.parts.append(text)

  def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
    attr_map = dict(attrs)
    if tag in ("h1", "h2", "h3", "h4"):
      self._emit("\n#### ")
    elif tag == "p":
      if not self._in_li:
        self._emit("\n")
    elif tag == "br":
      self._emit("\n")
    elif tag == "li":
      self._in_li = True
      self._emit("\n  - ")
    elif tag in ("strong", "b"):
      self._emit("**")
    elif tag in ("em", "i"):
      self._emit("_")
    elif tag == "code":
      self._emit("`")
    elif tag == "a":
      href = attr_map.get("href") or ""
      if href.startswith("/"):
        href = self.base_url + href
      self._href = href
      self._link_text = []

  def handle_endtag(self, tag: str):
    if tag in ("h1", "h2", "h3", "h4"):
      self._emit("\n")
    elif tag == "p":
      if not self._in_li:
        self._emit("\n")
    elif tag == "li":
      self._in_li = False
    elif tag in ("strong", "b"):
      self._emit("**")
    elif tag in ("em", "i"):
      self._emit("_")
    elif tag == "code":
      self._emit("`")
    elif tag == "a":
      label = re.sub(r"\s+", " ", "".join(self._link_text)).strip()
      href = self._href
      self._href = None
      self._link_text = []
      if href and label:
        self.parts.append(f"[{label}]({href})")
      elif label:
        self.parts.append(label)

  def handle_data(self, data: str):
    self._emit(data)

  def get_markdown(self) -> str:
    """Returns the accumulated Markdown string with normalized whitespace."""
    raw = "".join(self.parts)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw.splitlines()]
    cleaned: list[str] = []
    for line in lines:
      if not line:
        if cleaned and cleaned[-1]:
          cleaned.append("")
      else:
        if line.startswith("- "):
          cleaned.append("  " + line)
        else:
          cleaned.append(line)
    return "\n".join(cleaned).strip()


def html_to_markdown(raw_html: str) -> str:
  """Converts a raw HTML snippet into clean Markdown."""
  if not raw_html:
    return ""
  parser = HTMLToMarkdownParser()
  parser.feed(html.unescape(raw_html))
  return parser.get_markdown()


def remove_libraries_section(raw_html: str) -> str:
  """Replaces verbose <h3>Libraries</h3> sections with a compact summary."""
  if not raw_html:
    return ""
  if re.search(
      r"<h3>\s*Libraries\s*</h3>(.|\n)*?<h3>", raw_html, flags=re.IGNORECASE
  ):
    return re.sub(
        r"<h3>\s*Libraries\s*</h3>(.|\n)*?<h3>",
        "<h3>Libraries Updated</h3>\n<h3>",
        raw_html,
        flags=re.IGNORECASE,
    )
  if re.search(r"<h3>\s*Libraries\s*</h3>", raw_html, flags=re.IGNORECASE):
    return re.sub(
        r"<h3>\s*Libraries\s*</h3>(.|\n)*",
        "<h3>Libraries Updated</h3>",
        raw_html,
        flags=re.IGNORECASE,
    )
  return raw_html


def extract_release_types(raw_html: str) -> list[str]:
  """Extracts release note types (FEATURE, DEPRECATION, FIX, etc.)."""
  headers = re.findall(r"<h3[^>]*>(.*?)</h3>", raw_html, flags=re.IGNORECASE)
  badges = re.findall(
      r'class="devsite-label[^"]*"[^>]*>(.*?)</span>',
      raw_html,
      flags=re.IGNORECASE,
  )
  found: list[str] = []
  for h in headers + badges:
    clean = re.sub(r"<[^>]+>", "", html.unescape(h)).strip().upper()
    if clean and clean not in found:
      found.append(clean)
  return found or ["UPDATE"]


def parse_date_flexible(date_str: str) -> datetime.date | None:
  """Parses ISO-8601 (Atom) or RFC-2822 (RSS) date strings into a date."""
  if not date_str:
    return None
  s = date_str.strip()
  try:
    return datetime.date.fromisoformat(s[:10])
  except ValueError:
    pass
  try:
    dt = email.utils.parsedate_to_datetime(s)
    return dt.date()
  except (TypeError, ValueError):
    pass
  for fmt in (
      "%d %b %Y %H:%M:%S %Z",
      "%a, %d %b %Y %H:%M:%S %z",
      "%B %d, %Y",
  ):
    try:
      return datetime.datetime.strptime(s, fmt).date()
    except ValueError:
      continue
  return None


def load_catalog() -> dict[str, object]:
  """Loads the bundled Google Cloud feed catalog from references/catalog.json."""
  if not os.path.exists(CATALOG_PATH):
    print(
        f"ERROR: Feed catalog not found at {CATALOG_PATH}. Verify the skill "
        "directory contains references/catalog.json.",
        file=sys.stderr,
    )
    sys.exit(1)
  with open(CATALOG_PATH, "r", encoding="utf-8") as f:
    return json.load(f)


def parse_watchlist_from_skill_md() -> dict[str, list[str]]:
  """Reads the default watchlist block from SKILL.md if present."""
  result: dict[str, list[str]] = {
      "products": [],
      "bundles": [],
  }
  if not os.path.exists(SKILL_MD_PATH):
    return result
  try:
    with open(SKILL_MD_PATH, "r", encoding="utf-8") as f:
      content = f.read()
    block_m = re.search(
        r"<!-- WATCHLIST_START -->(.*?)<!-- WATCHLIST_END -->",
        content,
        re.DOTALL,
    )
    if not block_m:
      return result
    block = block_m.group(1)
    for key, label in [
        ("products", "Products"),
        ("bundles", "Bundles"),
    ]:
      m = re.search(rf"-\s*\*\*{label}\*\*:\s*(.+)", block, flags=re.IGNORECASE)
      if m:
        raw_val = m.group(1).strip()
        if raw_val.lower() not in ("none", "[]", "-"):
          items = [
              i.strip().strip("`")
              for i in raw_val.split(",")
              if i.strip() and i.strip().lower() != "none"
          ]
          result[key] = items
  except OSError:
    pass
  return result


def sync_watchlist_to_skill_md(subs: dict[str, object]) -> None:
  """Updates the <!-- WATCHLIST_START --> block in SKILL.md when writable."""
  if not os.path.exists(SKILL_MD_PATH) or not os.access(SKILL_MD_PATH, os.W_OK):
    return
  try:
    with open(SKILL_MD_PATH, "r", encoding="utf-8") as f:
      content = f.read()
    if "<!-- WATCHLIST_START -->" not in content:
      return

    def _fmt(key: str) -> str:
      items = subs.get(key)
      if isinstance(items, list) and items:
        return ", ".join(str(x) for x in items)
      return "None"

    new_block = (
        "<!-- WATCHLIST_START -->\n"
        f"- **Products**: {_fmt('products')}\n"
        f"- **Bundles**: {_fmt('bundles')}\n"
        "<!-- WATCHLIST_END -->"
    )
    updated = re.sub(
        r"<!-- WATCHLIST_START -->.*?<!-- WATCHLIST_END -->",
        new_block,
        content,
        flags=re.DOTALL,
    )
    with open(SKILL_MD_PATH, "w", encoding="utf-8") as f:
      f.write(updated)
  except OSError:
    pass


def load_subscriptions(
    sub_path: str = DEFAULT_SUBSCRIPTIONS_PATH,
) -> dict[str, object]:
  """Loads subscriptions from JSON file, falling back to an empty watchlist."""
  if os.path.exists(sub_path):
    try:
      with open(sub_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)
      return {
          "products": loaded.get("products", []),
          "bundles": loaded.get("bundles", []),
      }
    except (OSError, json.JSONDecodeError):
      pass
  from_md = parse_watchlist_from_skill_md()
  if any(from_md.values()):
    return from_md
  return {
      "products": [],
      "bundles": [],
  }


def save_subscriptions(
    subs: dict[str, object], sub_path: str = DEFAULT_SUBSCRIPTIONS_PATH
) -> None:
  """Persists subscriptions to JSON and syncs the SKILL.md watchlist block."""
  os.makedirs(os.path.dirname(os.path.abspath(sub_path)), exist_ok=True)
  clean_subs: dict[str, object] = {
      "products": subs.get("products", []),
      "bundles": subs.get("bundles", []),
      "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
  }
  with open(sub_path, "w", encoding="utf-8") as f:
    json.dump(clean_subs, f, indent=2, ensure_ascii=False)
  sync_watchlist_to_skill_md(clean_subs)


def resolve_catalog_matches(
    query_terms: list[str], catalog: dict[str, object]
) -> dict[str, list[dict[str, str]] | list[str]]:
  """Resolves user product or bundle names/slugs to feed objects."""
  matched_products: dict[str, dict[str, str]] = {}
  matched_bundles: list[str] = []

  bundles_map = catalog.get("bundles", {})
  if not isinstance(bundles_map, dict):
    bundles_map = {}
  expanded_product_names: list[str] = []

  for raw_term in query_terms:
    term = raw_term.strip()
    if not term:
      continue
    term_lower = term.lower()

    bundle_hit = False
    for b_name, b_items in bundles_map.items():
      if (
          term_lower == b_name.lower()
          or (
              term_lower in ("all ai", "ai products")
              and b_name == "All AI Products"
          )
          or (
              term_lower in ("all data", "data products")
              and b_name == "All Data Products"
          )
          or (
              term_lower in ("all security", "security products")
              and b_name == "All Security Products"
          )
          or (
              term_lower in ("all app mod", "app mod products")
              and b_name == "All App Mod Products"
          )
      ):
        matched_bundles.append(b_name)
        expanded_product_names.extend(b_items)
        bundle_hit = True
    if bundle_hit:
      continue

    expanded_product_names.append(term)

  all_terms = [t.strip() for t in expanded_product_names if t.strip()]
  products_list = catalog.get("products", [])

  alias_map = {
      "gke": "google kubernetes engine",
      "gcs": "cloud storage",
      "bq": "bigquery",
      "pubsub": "pub/sub",
      "iam": "identity and access management",
      "gemini enterprise": "gemini enterprise",
      "gemini platform": "gemini platform",
      "cloud spanner": "spanner",
      "google cloud spanner": "spanner",
  }

  for term in all_terms:
    t_low = term.lower()
    search_low = alias_map.get(t_low, t_low)
    stripped_cloud = re.sub(r"^(google\s+)?cloud\s+", "", search_low).strip()

    exact_found = False
    if isinstance(products_list, list):
      for p in products_list:
        if search_low in (p["name"].lower(), p["id"].lower()) or (
            stripped_cloud
            and stripped_cloud in (p["name"].lower(), p["id"].lower())
        ):
          matched_products[p["url"]] = p
          exact_found = True

    if exact_found:
      continue

    if isinstance(products_list, list):
      for p in products_list:
        if search_low in p["name"].lower() or search_low in p["id"].lower():
          matched_products[p["url"]] = p

  return {
      "bundles": matched_bundles,
      "products": list(matched_products.values()),
  }


def fetch_feed_entries(
    feed_info: dict[str, str],
    category_kind: str,
    cutoff_date: datetime.date,
    max_entries_per_feed: int = 5,
) -> list[dict[str, object]]:
  """Fetches and parses an Atom or RSS XML feed since cutoff_date."""
  url = feed_info["url"]
  source_name = feed_info["name"]
  entries_out: list[dict[str, object]] = []

  try:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
      xml_bytes = resp.read()
    root = ET.fromstring(xml_bytes)
  except (urllib.error.URLError, ET.ParseError, TimeoutError, OSError):
    return entries_out

  items = [
      el
      for el in root.iter()
      if el.tag.endswith("entry") or el.tag.endswith("item")
  ]

  for item in items[: max_entries_per_feed * 2]:
    title_text = ""
    updated_str = ""
    content_html = ""
    link_href = ""
    entry_id = ""

    for child in item:
      tag = child.tag.split("}")[-1]
      if tag == "title" and child.text:
        title_text = child.text.strip()
      elif (
          tag in ("updated", "pubDate", "published")
          and child.text
          and not updated_str
      ):
        updated_str = child.text.strip()
      elif (
          tag in ("content", "description", "summary")
          and child.text
          and not content_html
      ):
        content_html = child.text.strip()
      elif tag == "link" and not link_href:
        link_href = child.attrib.get("href") or (child.text or "").strip()
      elif tag in ("id", "guid") and child.text:
        entry_id = child.text.strip()

    pub_date = parse_date_flexible(updated_str)
    if not pub_date or pub_date < cutoff_date:
      continue

    cleaned_html = remove_libraries_section(content_html)
    release_types = extract_release_types(cleaned_html)
    markdown_body = html_to_markdown(cleaned_html)

    digest_input = (
        f"{source_name}|{pub_date.isoformat()}|{title_text}|{markdown_body}"
    )
    digest_hash = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()

    entries_out.append({
        "kind": category_kind,
        "source_id": feed_info["id"],
        "source_name": source_name,
        "feed_url": url,
        "entry_id": entry_id or f"{url}#{pub_date.isoformat()}",
        "title": title_text or f"{source_name} Update ({pub_date.isoformat()})",
        "date": pub_date.isoformat(),
        "types": release_types,
        "link": link_href or url,
        "markdown": markdown_body,
        "raw_html": cleaned_html,
        "hash": digest_hash,
    })
    if len(entries_out) >= max_entries_per_feed:
      break

  return entries_out


def enrich_sparse_entry(entry: dict[str, object]) -> dict[str, object]:
  """Enriches brief product release notes using docs.cloud.google.com .md.txt."""
  md = str(entry.get("markdown", ""))
  if len(md) > 280 or entry.get("kind") != "product":
    return entry
  urls = [
      u
      for u in re.findall(r"\((https://docs\.cloud\.google\.com/[^)]+)\)", md)
      if "release-notes" not in u
  ]
  if not urls:
    return entry
  doc_url = urls[0].split("#")[0].rstrip("/")
  md_txt_url = doc_url if doc_url.endswith(".md.txt") else f"{doc_url}.md.txt"
  try:
    req = urllib.request.Request(md_txt_url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=8) as resp:
      raw_md = resp.read().decode("utf-8", errors="replace")
    first_para = ""
    for line in raw_md.splitlines():
      stripped = line.strip()
      if stripped and not stripped.startswith(("#", "!", "[", "|", "---")):
        first_para = stripped
        break
    if first_para and first_para not in md:
      entry = dict(entry)
      entry["markdown"] = f"{md}\n  - **Doc Summary**: {first_para[:300]}"
      return entry
  except (urllib.error.URLError, TimeoutError, OSError):
    pass

  try:
    req = urllib.request.Request(doc_url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=8) as resp:
      doc_html = resp.read().decode("utf-8", errors="replace")
    desc_m = re.search(
        r'<meta\s+name="description"\s+content="([^"]+)"', doc_html
    )
    if desc_m:
      desc = html.unescape(desc_m.group(1)).strip()
      if desc and desc not in md:
        entry = dict(entry)
        entry["markdown"] = f"{md}\n  - **Doc Summary**: {desc}"
  except (urllib.error.URLError, TimeoutError, OSError):
    pass
  return entry


def load_seen_state(state_path: str = DEFAULT_STATE_PATH) -> dict[str, object]:
  """Loads previously seen entry hashes from the state file."""
  if os.path.exists(state_path):
    try:
      with open(state_path, "r", encoding="utf-8") as f:
        return json.load(f)
    except (OSError, json.JSONDecodeError):
      pass
  return {"seen_hashes": {}, "last_checked_at": None}


def save_seen_state(
    entries: list[dict[str, object]], state_path: str = DEFAULT_STATE_PATH
) -> None:
  """Saves seen entry hashes to the state file for deduplication."""
  state = load_seen_state(state_path)
  seen_hashes = state.get("seen_hashes", {})
  if not isinstance(seen_hashes, dict):
    seen_hashes = {}
  for e in entries:
    seen_hashes[str(e["entry_id"])] = str(e["hash"])
  state["seen_hashes"] = seen_hashes
  state["last_checked_at"] = datetime.datetime.now(
      datetime.timezone.utc
  ).isoformat()
  os.makedirs(os.path.dirname(os.path.abspath(state_path)), exist_ok=True)
  with open(state_path, "w", encoding="utf-8") as f:
    json.dump(state, f, indent=2, ensure_ascii=False)


def format_markdown_report(
    entries: list[dict[str, object]],
    subs: dict[str, object],
    days: int,
    since_last_check: bool,
    type_filter: str | None = None,
) -> str:
  """Formats fetched entries into a clean, grouped Markdown report."""
  now_str = datetime.datetime.now(datetime.timezone.utc).strftime(
      "%Y-%m-%d %H:%M UTC"
  )
  prods = subs.get("products", [])
  if isinstance(prods, list) and prods:
    prod_str = ", ".join(str(x) for x in prods)
  else:
    prod_str = "None"
  lines = [
      "# 📡 Google Cloud Release Radar",
      "",
      f"- **Generated At**: {now_str}",
      f"- **Window**: Last {days} day(s)"
      + (" (New since last check only)" if since_last_check else ""),
      f"- **Tracked Products**: {prod_str}",
  ]
  bundles = subs.get("bundles")
  if isinstance(bundles, list) and bundles:
    lines.append(f"- **Tracked Bundles**: {', '.join(str(x) for x in bundles)}")
  if type_filter:
    lines.append(f"- **Type Filter**: `{type_filter.upper()}`")
  lines.extend(["", "---", ""])

  if not entries:
    lines.append(
        f"ℹ️ **No matching updates published in the last {days} day(s)** for"
        " your selected products and bundles."
    )
    return "\n".join(lines)

  prod_entries = [e for e in entries if e["kind"] == "product"]

  if prod_entries:
    lines.append(f"## 🚀 Product Release Notes ({len(prod_entries)} update(s))")
    lines.append("")
    for e in prod_entries:
      types_list = e.get("types", [])
      if not isinstance(types_list, list):
        types_list = ["UPDATE"]
      badges = " · ".join(
          f"{LABEL_ICONS.get(str(t).lower(), '📌')} `{t}`" for t in types_list
      )
      lines.append(
          f"### [{e['source_name']}]({e['link']}) — _{e['date']}_ ({badges})"
      )
      lines.append("")
      lines.append(str(e["markdown"]))
      lines.append("")

  return "\n".join(lines).strip()


def send_to_google_chat_webhook(report_md: str, webhook_url: str) -> None:
  """Sends the release digest to an external Google Chat incoming webhook."""
  payload = json.dumps({"text": report_md}).encode("utf-8")
  req = urllib.request.Request(
      webhook_url,
      data=payload,
      headers={
          "Content-Type": "application/json",
          "User-Agent": USER_AGENT,
      },
  )
  try:
    with urllib.request.urlopen(req, timeout=15) as resp:
      print(
          f"Sent digest to Google Chat webhook (HTTP {resp.status}).",
          file=sys.stderr,
      )
  except urllib.error.URLError as err:
    print(
        f"ERROR: Failed to send digest to Google Chat webhook: {err}",
        file=sys.stderr,
    )
    sys.exit(1)


_TYPE_ALIASES: dict[str, tuple[str, ...]] = {
    "DEPRECATION": ("DEPRECATION", "DEPRECATED"),
    "DEPRECATED": ("DEPRECATION", "DEPRECATED"),
    "FIX": ("FIX", "FIXED"),
    "FIXED": ("FIX", "FIXED"),
    "SECURITY": ("SECURITY", "SECURITY BULLETIN"),
}


def _matches_wanted_types(
    entry: dict[str, object], wanted_types: set[str]
) -> bool:
  """Returns True if entry matches any of the requested release note types."""
  raw_types = entry.get("types")
  entry_types = raw_types if isinstance(raw_types, list) else ["UPDATE"]
  md_upper = str(entry.get("markdown", "")).upper()
  expanded_wanted: set[str] = set()
  for wt in wanted_types:
    wt_upper = wt.upper()
    expanded_wanted.update(_TYPE_ALIASES.get(wt_upper, (wt_upper,)))
  for wt in expanded_wanted:
    if wt in md_upper:
      return True
    for rt in entry_types:
      if wt in str(rt).upper():
        return True
  return False


def main() -> None:
  """Parses CLI arguments and executes the Release Radar workflow."""
  parser = argparse.ArgumentParser(
      description=(
          "Track, query, and summarize official Google Cloud release notes "
          "across products and curated bundles."
      )
  )
  parser.add_argument(
      "--subscriptions-file",
      default=DEFAULT_SUBSCRIPTIONS_PATH,
      help="Path to subscriptions.json watchlist file",
  )
  parser.add_argument(
      "--state-file",
      default=DEFAULT_STATE_PATH,
      help="Path to seen_state.json for deduplicating previously seen entries",
  )
  parser.add_argument(
      "--list-subscriptions",
      action="store_true",
      help="Print currently subscribed products and bundles",
  )
  parser.add_argument(
      "--list-catalog",
      nargs="?",
      const="ALL",
      default=None,
      help="List available products and curated bundles (optional keyword)",
  )
  parser.add_argument(
      "--add",
      default=None,
      help=(
          "Comma-separated list of products or curated bundles to add to the "
          "watchlist"
      ),
  )
  parser.add_argument(
      "--remove",
      default=None,
      help="Comma-separated list of items to remove from the watchlist",
  )
  parser.add_argument(
      "--set-products",
      default=None,
      help="Replace the tracked products list with these comma-separated items",
  )
  parser.add_argument(
      "--check",
      action="store_true",
      help="Check latest releases for all subscribed watchlist items",
  )
  parser.add_argument(
      "--query",
      default=None,
      help=(
          "Ad-hoc comma-separated product or bundle names to check without "
          "modifying saved subscriptions"
      ),
  )
  parser.add_argument(
      "--days",
      type=int,
      default=14,
      help="Lookback window in days (default: 14)",
  )
  parser.add_argument(
      "--type",
      default=None,
      help=(
          "Filter by release note type (e.g. FEATURE, DEPRECATION, BREAKING, "
          "FIX, SECURITY)"
      ),
  )
  parser.add_argument(
      "--since-last-check",
      action="store_true",
      help="Only show entries that have changed since the last check",
  )
  parser.add_argument(
      "--enrich-docs",
      action="store_true",
      help=(
          "Fetch linked docs.cloud.google.com pages (.md.txt) for brief "
          "release notes"
      ),
  )
  parser.add_argument(
      "--output",
      choices=["markdown", "json"],
      default="markdown",
      help="Output format (markdown or json)",
  )
  parser.add_argument(
      "--notify-webhook",
      default=os.environ.get("GCHAT_WEBHOOK_URL"),
      help="Optional Google Chat incoming webhook URL",
  )
  parser.add_argument(
      "--dry-run",
      action="store_true",
      help=(
          "Preview subscription updates or resolved feed URLs without writing "
          "files or making network requests"
      ),
  )

  args = parser.parse_args()
  if args.days < 1:
    print(
        "ERROR: --days must be a positive integer (>= 1).",
        file=sys.stderr,
    )
    sys.exit(2)

  catalog = load_catalog()
  subs = load_subscriptions(args.subscriptions_file)

  if args.list_catalog is not None:
    kw = "" if args.list_catalog == "ALL" else args.list_catalog.lower()
    print("### 📦 Curated Product Bundles")
    bundles_dict = catalog.get("bundles", {})
    if isinstance(bundles_dict, dict):
      for b_name, b_list in bundles_dict.items():
        if not kw or kw in b_name.lower():
          print(f"- **{b_name}** ({len(b_list)} items)")
    products_list = catalog.get("products", [])
    prods = [
        p["name"]
        for p in (products_list if isinstance(products_list, list) else [])
        if not kw or kw in p["name"].lower() or kw in p["id"].lower()
    ]
    print(f"\n### ☁️ Google Cloud Products ({len(prods)} matching)")
    for p_name in prods[:100]:
      print(f"- {p_name}")
    if len(prods) > 100:
      print(f"  ... and {len(prods) - 100} more (pass a keyword to filter).")
    return

  modified_subs = False
  if args.set_products is not None:
    terms = [t.strip() for t in args.set_products.split(",") if t.strip()]
    resolved = resolve_catalog_matches(terms, catalog)
    prod_objs = resolved["products"]
    subs["products"] = sorted(
        {p["name"] for p in prod_objs if isinstance(p, dict)}
    )
    if resolved["bundles"]:
      subs["bundles"] = sorted(set(str(b) for b in resolved["bundles"]))
    modified_subs = True

  if args.add:
    terms = [t.strip() for t in args.add.split(",") if t.strip()]
    resolved = resolve_catalog_matches(terms, catalog)
    existing_raw = subs.get("products", [])
    existing = (
        {str(x) for x in existing_raw}
        if isinstance(existing_raw, list)
        else set()
    )
    for item in resolved["products"]:
      if isinstance(item, dict):
        existing.add(item["name"])
    subs["products"] = sorted(existing)
    if resolved["bundles"]:
      existing_bundles = subs.get("bundles", [])
      b_set = (
          {str(x) for x in existing_bundles}
          if isinstance(existing_bundles, list)
          else set()
      )
      subs["bundles"] = sorted(b_set | {str(b) for b in resolved["bundles"]})
    modified_subs = True

  if args.remove:
    rem_terms = [t.strip().lower() for t in args.remove.split(",") if t.strip()]
    for key in ("products", "bundles"):
      existing_raw = subs.get(key, [])
      if isinstance(existing_raw, list):
        subs[key] = [
            item
            for item in existing_raw
            if not any(rt in str(item).lower() for rt in rem_terms)
        ]
    modified_subs = True

  if modified_subs:
    if args.dry_run:
      print(
          f"[DRY RUN] Would update subscriptions in {args.subscriptions_file}:",
          file=sys.stderr,
      )
      print(json.dumps(subs, indent=2))
    else:
      save_subscriptions(subs, args.subscriptions_file)
      print(
          f"Updated subscriptions in {args.subscriptions_file}.",
          file=sys.stderr,
      )
      print(json.dumps(subs, indent=2))
    if not (args.check or args.query):
      return

  if args.list_subscriptions:
    print(json.dumps(subs, indent=2))
    return

  if args.query:
    q_terms = [t.strip() for t in args.query.split(",") if t.strip()]
    resolved = resolve_catalog_matches(q_terms, catalog)
    active_subs_display: dict[str, object] = {
        "products": [
            p["name"] for p in resolved["products"] if isinstance(p, dict)
        ],
        "bundles": resolved["bundles"],
    }
  else:
    all_sub_terms: list[str] = []
    for key in ("products", "bundles"):
      items = subs.get(key, [])
      if isinstance(items, list):
        all_sub_terms.extend(str(x) for x in items)
    if not all_sub_terms and not args.dry_run:
      print(
          "WATCHLIST_EMPTY: Your Google Cloud Release Radar watchlist is "
          "currently empty. Please set up your watchlist first using "
          '`--set-products "<products>"` or `--add "<items>"` (for example: '
          '`python3 scripts/release_radar.py --add "BigQuery,Looker"`).',
      )
      return
    resolved = resolve_catalog_matches(all_sub_terms, catalog)
    active_subs_display = subs

  tasks: list[tuple[dict[str, str], str]] = []
  for p in resolved["products"]:
    if isinstance(p, dict):
      tasks.append((p, "product"))

  if args.dry_run:
    print(
        json.dumps(
            {
                "dry_run": True,
                "days": args.days,
                "type_filter": args.type,
                "since_last_check": args.since_last_check,
                "enrich_docs": args.enrich_docs,
                "feeds_to_fetch": [
                    {"kind": kind, "name": f["name"], "url": f["url"]}
                    for f, kind in tasks
                ],
            },
            indent=2,
        )
    )
    return

  cutoff = datetime.date.today() - datetime.timedelta(days=max(1, args.days))

  all_entries: list[dict[str, object]] = []
  with futures.ThreadPoolExecutor(max_workers=32) as ex:
    futs = [
        ex.submit(fetch_feed_entries, feed_obj, kind, cutoff)
        for feed_obj, kind in tasks
    ]
    for fut in futures.as_completed(futs):
      all_entries.extend(fut.result())

  if args.type:
    wanted_types = {
        t.strip().upper() for t in args.type.split(",") if t.strip()
    }
    all_entries = [
        e for e in all_entries if _matches_wanted_types(e, wanted_types)
    ]

  if args.since_last_check:
    seen_raw = load_seen_state(args.state_file).get("seen_hashes", {})
    seen_state = seen_raw if isinstance(seen_raw, dict) else {}
    all_entries = [
        e
        for e in all_entries
        if seen_state.get(str(e["entry_id"])) != str(e["hash"])
    ]

  all_entries.sort(
      key=lambda x: (str(x["date"]), str(x["source_name"])), reverse=True
  )

  if args.enrich_docs:
    with futures.ThreadPoolExecutor(max_workers=10) as ex:
      all_entries = list(ex.map(enrich_sparse_entry, all_entries))

  save_seen_state(all_entries, args.state_file)

  if args.output == "json":
    print(json.dumps(all_entries, indent=2, ensure_ascii=False))
    return

  report = format_markdown_report(
      all_entries,
      active_subs_display,
      days=args.days,
      since_last_check=args.since_last_check,
      type_filter=args.type,
  )
  print(report)

  if args.notify_webhook:
    send_to_google_chat_webhook(report, webhook_url=args.notify_webhook)


if __name__ == "__main__":
  main()
