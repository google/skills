---
name: secops-documentation
description: >-
  Authoring, reviewing, staging, and publishing technical documentation for Google Security Operations (SecOps) on DevSite. Enforces DevSite formatting standards, required variables, preview disclaimers, Table of Contents (TOC) management, and staging verification.
---

# SecOps Documentation (DevSite Publishing)

Follow these instructions when authoring, reviewing, staging, or publishing technical guides and documentation for Google Security Operations (`third_party/devsite/cloud/en/chronicle/`).

## 1. Document formatting and voice

When writing or updating Markdown documents under `chronicle/docs/`, you MUST adhere to the following standards:

- **Product Variables**: Never hardcode product names. Always use standard DevSite variables:
  - `{{google_secops_name}}` for "Google Security Operations".
  - `{{google_secops_name_short}}` for "Google SecOps" or "SecOps".
  - `{{gemini_name}}` for "Gemini".
- **Pre-GA Disclaimer**: For Private Preview or Public Preview features, include the pre-GA disclaimer near the top of the body block:
  ```markdown
  <<../_includes/_pre-ga-disclaimer.md>>
  ```
  *(Adjust relative path based on document depth).*
- **Sentence Case Headings**: All section headings must use sentence case (only capitalize the first word and proper nouns).
  - *Correct*: `## Setting up the MCP server`
  - *Incorrect*: `## Setting Up The MCP Server`
- **Phrasing**: Use `for example` instead of `e.g.`.
- **Code Symbols**: Wrap filenames, configuration parameters, and tool names in backticks (`settings.json`, `generate_threat_detection_opportunity`).
- **Community Help**: Always add `{{community_help}}` before the closing `{% endblock %}` tag.

## 2. Table of Contents (TOC) and tracking tags

- **Private Preview**:
  - Do **NOT** add Private Preview pages to the Table of Contents (`_toc_secops_guides.yaml`). Keep them unlinked to prevent premature discovery.
  - Use `secops_typo_fix` or `secops_caveat_fix` in the CL description to satisfy presubmit verification.
- **GA / Public Preview**:
  - Link the document in `_toc_secops_guides.yaml` under the appropriate section.
  - Add the corresponding tracking tag (for example, `secops_new_workflow_guide`) on a dedicated line in the CL description.

## 3. Staging verification

Before mailing any documentation CL for review, you MUST stage and verify the rendering:

1. **Compile and Stage**:
   ```bash
   /google/data/ro/projects/devsite/two/live/devsite2.par stage --cl=<CL_NUMBER>
   ```
2. **Link Staging in CL**:
   Add the staging preview link to the CL description using the standard DevSite block:
   ```text
   --- Staged --- (KEEP THIS LINE) ---
   *  https://cloud.devsite.google.com/chronicle/docs/...
   -------------- (KEEP THIS LINE) ---
   ```

## 4. Submission checklist

- Run `mdformat` on modified Markdown files before upload:
  ```bash
  /google/bin/releases/corpeng-engdoc/tools/mdformat --in_place <file.md>
  ```
- Verify presubmits pass with `0 errors`.
- Include `chronicle-editors` on review requests (`R=chronicle-editors` or `hg mail -m chronicle-editors`).
