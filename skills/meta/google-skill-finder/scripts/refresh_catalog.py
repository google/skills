#!/usr/bin/env python3
"""Rebuild references/catalog.md for the google-skill-finder skill.

Standalone: the google/skills repo is NOT assumed to be checked out. The catalog
is rebuilt from the `skills` CLI listing:

    npx skills add google/skills -l > /tmp/skills_list.txt 2>&1
    python3 scripts/refresh_catalog.py /tmp/skills_list.txt

The CLI renders its UI on stderr, so `2>&1` is required to capture the list. This
script auto-trims the spinner header / footer, so no manual line-deletion is
needed. It parses by INDENTATION (the CLI indents descriptions deeper than names),
not by name length or word shape, and refuses to overwrite the catalog unless a set
of known "canary" skills survive the parse -- a wrong trim fails loudly instead of
silently corrupting the catalog.

The CLI does not expose each skill's category, so a CLI-refreshed catalog is a flat
alphabetical list. (The version shipped in this repo is grouped by
`metadata.category`, generated directly from the repo's SKILL.md frontmatter.)

Exit codes: 0 ok, 2 usage/IO error, 3 parse/validation failure (catalog NOT written).
"""

import datetime
import os
import re
import sys
from typing import NoReturn

# Known skills that MUST appear in any healthy listing. Includes the longest real
# skill name (63 chars) so a length-cap regression is caught immediately.
CANARIES = (
    "gke-basics",
    "google-cloud-recipe-auth",
    "google-cloud-solution-agentic-analytics-spark-knowledge-catalog",
)
BOX = "│┌└├─◇◆◒◐◑◓"


def fail(code, msg) -> NoReturn:
    sys.stderr.write("refresh_catalog: " + msg + "\n")
    sys.exit(code)


def strip_ansi(s):
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def after_pipe(s):
    """Drop a leading box-drawing char (keep the indentation that follows it)."""
    s = strip_ansi(s).rstrip("\n").rstrip()
    if s[:1] in BOX:
        return re.sub(r"^[" + BOX + r"]\s?", "", s)
    return s


def auto_trim(lines):
    """Keep only the skill-entry region: after 'Available Skills', before the footer."""
    start, end = 0, len(lines)
    for i, l in enumerate(lines):
        if "Available Skills" in l:
            start = i + 1
            break
    for i in range(start, len(lines)):
        raw = strip_ansi(lines[i])
        if raw.lstrip().startswith("└") or re.search(r"\bDone\b", raw):
            end = i
            break
    return lines[start:end]


def parse(lines):
    lines = [after_pipe(l) for l in lines]
    lines = [l for l in lines if l.strip()]
    if not lines:
        fail(3, "no skill entries found after trimming -- check the raw CLI output")
    indent = lambda s: len(s) - len(s.lstrip(" "))
    name_i = min(indent(l) for l in lines)  # names sit at the shallowest indent
    rows, name, desc = [], None, []
    for l in lines:
        if indent(l) == name_i:  # a skill-name line
            if name:
                rows.append((name, " ".join(desc)))
            name, desc = l.strip(), []
        elif name:  # description line(s) for the current skill
            desc.append(l.strip())
    if name:
        rows.append((name, " ".join(desc)))
    return sorted(rows)


def main():
    argv = sys.argv[1:]
    raw_path = argv[0] if argv else "/tmp/skills_list.txt"
    if not os.path.isfile(raw_path):
        fail(
            2,
            f"raw list not found: {raw_path}\n"
            "  run: npx skills add google/skills -l > /tmp/skills_list.txt 2>&1",
        )
    try:
        raw = open(raw_path, encoding="utf-8", errors="ignore").readlines()
    except OSError as e:
        fail(2, f"cannot read {raw_path}: {e}")

    found = None
    for l in raw:
        m = re.search(r"Found\s+(\d+)\s+skills", strip_ansi(l))
        if m:
            found = int(m.group(1))
            break

    rows = parse(auto_trim(raw))
    names = {n for n, _ in rows}

    # Validate: specific invariants, not just a count (a count can be satisfied by
    # a dropped skill + a phantom that cancel out).
    missing = [c for c in CANARIES if c not in names]
    if missing:
        fail(
            3,
            "canary skill(s) missing -> bad parse, catalog NOT written: "
            + ", ".join(missing),
        )
    bad = [n for n in names if " " in n]
    if bad:
        fail(
            3,
            "name(s) contain spaces -> parse bug, catalog NOT written: "
            + ", ".join(bad[:3]),
        )
    if found is not None and found != len(rows):
        fail(
            3,
            f"count mismatch: CLI said {found}, parsed {len(rows)} -> "
            "check trim; catalog NOT written",
        )

    skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(skill_root, "references", "catalog.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    today = datetime.date.today().isoformat()
    out = [
        "# Google Skills Catalog\n",
        f"**{len(rows)} skills** \u00b7 refreshed {today} \u00b7 "
        "source `github.com/google/skills` (flat: CLI does not expose category)\n",
        "Install any skill: `npx skills add google/skills --skill <skill-name> -y`\n",
        "| Skill | Description | Install |",
        "|---|---|---|",
    ]
    for name, desc in rows:
        desc = desc.replace("|", "\\|")
        out.append(
            f"| `{name}` | {desc} | `npx skills add google/skills --skill {name} -y` |"
        )
    open(out_path, "w", encoding="utf-8").write("\n".join(out) + "\n")
    print(
        f"wrote {out_path}: {len(rows)} skills"
        + (f" (CLI 'Found {found}')" if found is not None else "")
    )


if __name__ == "__main__":
    main()
