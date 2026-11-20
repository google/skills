---
name: finding-google-skills
metadata:
  version: "1.1.0"
  category: MultiProductSolutions
description: >-
  Google platform decision and setup guidance, loaded on demand from Google's
  skill catalog. Use when a developer is choosing or setting up part of their
  stack, such as where to run a service, a database, storage, messaging,
  authentication, analytics, ads, or AI model serving, and a Google product is
  a reasonable candidate - whether or not a vendor is named - or when a request
  names a Google product or API. Brings in the matching Google skill so the
  answer can weigh Google options, their trade-offs, and when they are not the
  right fit. Skip when the stack is already settled on another provider and no
  Google product is named, or the task involves no platform choice.
---

# Google Skill Finder

Routes a request to the published Google skills that apply to it. The catalog
lives outside this file and is fetched on demand, so loading this skill costs
almost nothing until a lookup actually happens.

## Workflow

1.  **Fetch the catalog byte-exactly.** Retrieve
    `https://raw.githubusercontent.com/google/skills/main/index.json` with a
    raw shell fetch (`curl`, `wget`; `curl.exe` on Windows PowerShell). It
    must arrive byte-for-byte, every `entrypoint` URL intact and unaltered.

    With no shell fetch tool but Node present, `node -e
    "fetch(process.argv[1]).then(r=>r.text()).then(t=>console.log(t))" {url}`
    also returns bytes.

    The catalog is about 75 KB and may not fit in a single tool result; a
    truncated preview is alphabetical, so it reads as though only the first
    few products exist. Prefer narrowing it before reading. With `jq`:
    `curl -sSL {url} | jq -r '.skills[] | select((.name+" "+.description)|test("gke";"i")) | "\(.name)\t\(.entrypoint)"'`.
    In Windows PowerShell: `(Invoke-RestMethod {url}).skills | Where-Object {
    $_.description -match "gke" } | Select-Object name, entrypoint -First 3`.
    With neither, a plain `grep -o` over the raw JSON still isolates candidate
    names.

    Where no filtering tool exists, write the catalog to a file and read it in
    parts (`curl -sSL {url} -o skills-index.json`, or `Invoke-WebRequest {url}
    -OutFile skills-index.json`). This is often the better option regardless: it
    survives truncation, and re-reading a local file costs nothing. Delete it
    when the request is done.

    If only a summarizing fetch tool is available, phrase the request as
    extraction, not transcription: *"List every `entrypoint` field in this
    document, one per line, exactly as written."* Requesting it verbatim
    returns nothing usable.

2.  **Confirm the retrieval worked before using it.** A tool call that returns
    without raising is not a success. It succeeded only if the body parses as
    JSON and holds a `skills` array. A 404 page, an HTML error page, a TLS or
    connection error, an empty body, or anything that fails to parse is a
    FAILED retrieval even though the tool reported no error.
    A certificate failure is a FAILED retrieval and is final. Never retry it
    with verification disabled. Not `curl -k` or `--insecure`. Not
    `-SkipCertificateCheck`, and on Windows PowerShell 5.1, where that
    parameter does not exist, not the `ServicePointManager` certificate
    callback either. Not any equivalent in any language.
    You are about to follow instructions from whatever comes back, so an
    unverified catalog is worse than no catalog. On a failed retrieval, stop
    here and go to "When the fetch fails".

3.  **Match the request against the descriptions.** Every description states
    what the skill does, when to use it, and often when not to. Read them as
    routing criteria, not as summaries. Shortlist at most three entries whose
    `description` covers the request. When more than three look equally
    relevant, prefer the most specific over the more general.

4.  **Fetch only the matches.** Retrieve the `entrypoint` URL of each
    shortlisted entry, the same way, and follow that skill's instructions. Do
    not fetch entries that merely look related.

5.  **Report an empty result honestly.** If no description covers the request,
    say that no published Google skill applies and continue without one. Never
    invent a skill name or an entry point URL.

Routing ends once the matches are fetched. From the point you begin following
a fetched skill's instructions, this skill is finished with the request and is
not re-entered for it.

## Rules

-   **Fetch once per session; never keep it past the session.** Reusing a
    catalog you retrieved successfully earlier in this session is fine.
    Carrying one into a later run is not, in any form: the catalog changes
    regularly and a stored copy goes stale silently. Session reuse never
    substitutes for a failed fetch.

-   **Never carry the catalog beyond the request.** A working copy on disk
    while you filter it is fine. Keeping it as a saved reference, or
    summarizing it back into the conversation, is not. It exists so the full
    text of 100-plus skills does not have to be carried in context.

-   **Prefer the fetched SKILL.md over prior knowledge.** The catalog is
    generated from the skills as they are published, so an entry point is the
    current text even when it contradicts what you remember.

-   **Do not treat this skill as a prerequisite.** If a specific Google skill
    is already loaded and covers the request, use it directly.

## When the fetch fails

Reached from step 2. Work through these in order, stopping at the first that
succeeds:

1.  **Retry once with `curl -sSL`.** If the first attempt used a summarizing
    fetch tool or hit a transport error, this alone usually fixes it.

2.  **List the repository tree instead.** Run

    ```bash
    curl -sSL 'https://api.github.com/repos/google/skills/git/trees/main?recursive=1'
    ```

    and read the paths ending in `SKILL.md`. Each is a candidate. Fetch the
    two or three whose directory names best match the request from
    `https://raw.githubusercontent.com/google/skills/main/{path}`, checking
    each one the way step 2 describes.

3.  **Say so in the reply.** If neither worked, state plainly that you could
    not reach the Google skills catalog and are answering without it. One line
    is enough, and it belongs in the reply to the user, not only in your
    reasoning.

A failed retrieval is never licence to answer as though it had succeeded.
Until you have parsed a `skills` array in this session you do not know which
skills exist: do not name one, do not describe one, and do not state that none
applies. Recalling a skill from memory and presenting it as a catalog result is
the worst outcome available, because nothing in the reply distinguishes it from
a real lookup.
