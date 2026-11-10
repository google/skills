# Contributing to litert-google-tensor

Read this before changing the skill, and follow the runbook below whenever a
new LiteRT release is adopted. Agents running a user job never need this
file.

## Contents

- [Invariants (DO NOT BREAK)](#invariants-do-not-break): Lines 17-95
- [`versions.json`](#versionsjson): Lines 97-130
  - [Why two release fields](#why-two-release-fields): Lines 110-130
- [Adopting a new LiteRT release](#adopting-a-new-litert-release): Lines 132-226
- [Updating the benchmark output parser](#updating-the-benchmark-output-parser): Lines 228-248
- [Editing Principles](#editing-principles): Lines 250-265
- [Validation](#validation): Lines 267-293

## Invariants (DO NOT BREAK)

- **`versions.json` is the only place a LiteRT version is pinned.**
  `compile_model.py` reads `pip_release` and `python`; `benchmark_on_device.py`
  reads `binaries_release` (default download URLs) and `pip_release` (the
  report's Versions line); `package_ai_pack.py` reads `maven_release` (the
  Gradle coordinates it writes), `kotlin_min` (INTEGRATION.md) and
  `pip_release` (its install hint); `install_and_verify.py` reads
  `bundletool_release` (its default bundletool download).
  `SKILL.md` and `references/` never repeat a pinned value as an
  instruction; they say `<pinned>` or point to `compile_model.py
  --print-install`. A version number anywhere else labels an observation
  ("observed with 2.1.6", "bucket listing checked 2026-10-07") and keeps the
  version or date it was observed on.
- **One version for the runtime and SDK packages.** The pip line always pins
  `ai-edge-litert` and `ai-edge-litert-sdk-google-tensor` to the same
  `pip_release`; the compile-time WARNING exists because a mixed pair is not
  supported.
- **`benchmark_model` and `libLiteRtDispatch_GoogleTensor.so` come from one
  bucket release directory by default** (the dispatch URL is derived from the
  benchmark URL). `binaries_release` must name a directory that ships both.
- **Scripts are standard-library Python 3 and stand alone.** Each script reads
  `versions.json` itself (no shared helper module), so `--help`, `--dry-run`
  and `--print-install` keep working with any `python3`, without LiteRT, and
  with a missing or broken `versions.json`. Only the default download and the
  installed-vs-pinned comparison may then fail, and their messages must name
  the file.
- **All scripts classify models the same way.** Each one checks the bytes
  itself: LiteRT build = `DISPATCH_OP` + `LiteRtStamp` (+ the SoC), other
  toolchain = an `edgetpu-custom-op` custom op without them, plain =
  neither. Change a marker in `check_compiled.py`, `compile_model.py`,
  `benchmark_on_device.py` and `package_ai_pack.py` together.
- **Sidecar and results keys are an interface.** `check_compiled.py` reads
  `cli_flags`, `ops_offloaded` and `ops_total` from `<model>.compile.json`,
  `benchmark_on_device.py` reads those plus `packages` (Versions line) and
  copies the whole sidecar into `results.json`; `package_ai_pack.py` checks
  `output_sha256`, `target` and `input_sha256` and copies `cli_flags`,
  `ops_offloaded`, `ops_total`, `fully_compiled`, `packages`, `compiled_at`
  and `compiled_via` into `pack.json`; rename a key only together with every
  reader. Keep the `results.json` keys documented in
  `benchmark-flags.md`.
- **Report values come from script output only.** The example output in
  `benchmark-flags.md` is verbatim from one real run: never edit its numbers
  or lines. To refresh it, replace the whole block with a new run's
  `report.md` and update `verified.evidence` in `versions.json`.
- **The packager leaves the AI-pack layout to LiteRT.** `package_ai_pack.py`
  builds `export_lib.export()`'s input from the files on disk and never writes
  pack folders or the device-targeting XML itself. Its only change to the
  exporter's output is the `model#group_other` placeholder. When the
  exporter's API or output changes, the script must fail (exit 5 or 7) and
  this file must be updated; never add a hand-written fallback layout.
- **Update mode only reads the user's project.** `--update-project` writes
  nothing there: it copies the exporter's output files to the app's existing
  paths under `<output-dir>/files/` and describes every other change in
  `UPDATE.md`. It matches device groups by the SoC in the app's XML (never
  renames them), takes the group element for a new SoC from the exporter's
  XML, and keeps the app's pack name, folder and file names.
- **Only the agent changes the user's project, and only after approval.**
  `--check-project` and `--update-project` only read it. SKILL.md step 6
  has the agent apply the plan after one approval, with a separate OK for
  each item the check marks `risky`; keep `risky` on every fix that changes
  more than the integration itself (build tool versions, adding Kotlin,
  `minSdk`, the app's ABIs, the app's LiteRT release, replacing the user's
  own files).
  `install_and_verify.py` uninstalls only with `--uninstall-first`, and
  nothing in the skill signs for release, publishes or uploads.
- **Templates follow LiteRT's published module layout.** `assets/templates/`
  mirrors the `google_tensor_runtime` and `runtime_strings` modules of the
  LiteRT NPU guide (https://developers.google.com/edge/litert/next/npu), with
  one deliberate difference: the runtime module is delivered to exactly the
  pack's device groups. Placeholders are `{{NAME}}`; the script fails on any
  unfilled one.
- **Everything the skill ships is public.** Scripts, templates and docs use
  only public endpoints and tools (PyPI, Google Maven, the public binaries
  bucket, Gradle, bundletool): no company-internal paths, links or services.
-   **No leftover processes, device files, or Colab sessions.** Tests and runs
    must not leave adb or `benchmark_model` running, must not touch a phone
    unless the change needs one, and must stop any Colab VM session created by
    `compile_model.py --colab` unless `--keep-colab-session` was requested.

## `versions.json`

| Field | Read by | Format and meaning |
|---|---|---|
| `pip_release` | `compile_model.py` (`--print-install`, exit-5 install hints, WARNING/NOTE, sidecar `pinned_pip_release`); `benchmark_on_device.py` (Versions line) | PyPI version string `X.Y.Z` (validated against `\d[0-9A-Za-z.+!_-]*`) of both pip packages. |
| `binaries_release` | `benchmark_on_device.py` (default `--benchmark-url`, hence also the dispatch URL; Versions line) | A directory name under `https://storage.googleapis.com/litert/binaries/` (`latest`, `nightly` or `X.Y.Z`; validated against `[A-Za-z0-9._-]+`). |
| `maven_release` | `package_ai_pack.py` (Gradle files, INTEGRATION.md, `pack.json`) | Google Maven version that exists for both `com.google.ai.edge.litert:litert` and `com.google.ai.edge.litert:litert-npu-runtime-google-tensor` (validated against `\d[0-9A-Za-z.+_-]*`). Check: `https://dl.google.com/dl/android/maven2/com/google/ai/edge/litert/group-index.xml`. |
| `kotlin_min` | `package_ai_pack.py` (INTEGRATION.md requirements, `pack.json`) | `MAJOR.MINOR`: the oldest Kotlin that can read the Kotlin metadata of `litert-api` at `maven_release`. A Kotlin compiler reads metadata up to one minor version newer than itself, so metadata 2.4.0 needs Kotlin 2.3. Check: `javap -v` on any class of the AAR's `classes.jar` shows `mv` (the metadata version); confirm by building an app with the package applied (step 6a) on exactly that Kotlin. |
| `bundletool_release` | `scripts/install_and_verify.py` (default download of `bundletool-all-<v>.jar`) | A bundletool release that exists on GitHub with a `bundletool-all-<v>.jar` asset (https://github.com/google/bundletool/releases); 1.18.0 or newer (local testing of AI packs). |
| `python` | `compile_model.py --print-install` | `MAJOR.MINOR-MAJOR.MINOR`: the interpreters with published wheels for `pip_release`. |
| `verified` | printed by `--print-install` as `Last verified: ...` | Free-form strings: `date`, `evidence` (which run proves the pair works), `device`, `host`, `binaries` (the bucket build, ideally with the md5 from the provenance line), and `app` (the latest end-to-end app check on a Pixel: date, device, delivery modes, `maven_release`, bundletool and build tool versions). |
| `_comment` | people | Ignored by the scripts. |

### Why two release fields

The bucket and the pip index are separate sources, and one field could not
serve both:

- Numbered bucket directories before 2.3.0 ship no Google Tensor dispatch
  library (bucket table in `benchmark-flags.md`), so earlier pins took the
  binaries from `latest`.
- The pip index users install from can lag the bucket. Many organizations
  install through a pip mirror or proxy that holds newly published
  third-party releases back for a while: on 2026-10-07 the bucket and PyPI
  had 2.3.0, while such a mirror offered only 2.2.0 and older.
- The Tensor SDK compatibility matrix names the stable `ai-edge-litert`
  release to compile with
  (https://developers.google.com/edge/tensor-sdk/release-notes#compatibility),
  and it can be older than the newest bucket release.

A split pin is fine once verified; the report then says `DIFFERENT releases
(the pair verified in versions.json)`. With both fields on one numbered
release it says `same release`; with a rolling `latest` it can only say
`not comparable`. Close the gap when the index catches up (runbook below).

## Adopting a new LiteRT release

Not every release needs adopting. Do it when a release fixes something users
hit, adds a SoC, or the Tensor SDK release notes require it, or periodically.
Until then the skill keeps working on the old pin; pinning exists for exactly
that.

Where releases show up: `https://pypi.org/project/ai-edge-litert/#history`,
the bucket's release directories
(`https://storage.googleapis.com/storage/v1/b/litert/o?prefix=binaries/&delimiter=/&fields=prefixes`),
and the compatibility matrix in
https://developers.google.com/edge/tensor-sdk/release-notes#compatibility.

You need a Linux x86_64 host, the Beta tarball, a Pixel 10 (and a Pixel 11 if
available) and a model with a known-good earlier result (e.g. the public
`selfie_multiclass_256x256` of the example in `benchmark-flags.md`).

1. **Check what exists (no install).**
    - PyPI has `ai-edge-litert` and `ai-edge-litert-sdk-google-tensor` at the
     same version `V` (`https://pypi.org/pypi/<package>/V/json` answers).
    - The pip index users install from offers both at `V`
     (`python3 -m pip index versions <package>`). A pip mirror or proxy
     (configured in `pip.conf` or `PIP_INDEX_URL`) can lag PyPI. If either
     package is missing there, leave `pip_release` as it is and move only
     `binaries_release`.
    - `https://storage.googleapis.com/storage/v1/b/litert/o?prefix=binaries/V/android_arm64/&fields=items(name,size,md5Hash,updated)`
     lists both `benchmark_model` and `libLiteRtDispatch_GoogleTensor.so`. If
     the dispatch library is missing, leave `binaries_release` as it is and
     move only `pip_release`.
    -   Compare that listing's `md5Hash` of the dispatch library with the pinned
        build's (`verified.binaries`): the same md5 means nothing changed on the
        Google Tensor side, whatever the release notes say (the first `2.3.1`
        upload of 2026-10-20 carried `2.3.0`'s library byte for byte). Release
        directories can be re-uploaded (`2.3.1` was, on 2026-10-23), so note
        both md5s and expect them in step 5's provenance lines.
    - Google Maven lists `litert` and `litert-npu-runtime-google-tensor` at
     `V` (group index above). If not, leave `maven_release` as it is.
    - When `maven_release` moves: read the Kotlin metadata version of the new
     `litert-api` (`javap -v`, field `mv`) and update `kotlin_min`.
    - The release notes say whether the existing Beta tarball still applies.
2. **Edit `versions.json`**: `pip_release` and `binaries_release` as far as
   step 1 allows, `python` if the wheel matrix changed. Leave `verified` for
   step 6.
3. **Install into a fresh venv** (skip if `pip_release` did not change). Run
   `python3 scripts/compile_model.py --print-install` and run the printed
   commands with `GOOGLE_TENSOR_SDK_BETA` set, changing only the venv path
   (e.g. `~/.venvs/litert-tensor-V`) so the working venv stays intact. The
   SDK package's `data/` directory must contain `liblitert_plugin_compiler.so`.
   If the install rejects the tarball, the tarball is tied to an SDK version:
   stop and revert, or get the matching tarball first.
4. **Compile** with the new venv (or the existing one if step 3 was skipped):
   `<venv>/bin/python scripts/compile_model.py <model> --target Tensor_G5
   --output-dir <dir>`. Expect exit 0 with no WARNING or NOTE, the sidecar's
   `packages` at `pip_release`, `fully_compiled: true`, and op counts like the
   previous release's (a different `output_sha256` across compiler releases is
   normal; note it).
5.  **Benchmark on the phone**: `python3 scripts/benchmark_on_device.py --model
    <compiled> --cpu-baseline <original> --refresh-binary --output-dir <dir>`.
    Expect exit 0, every table row filled, the Versions line as intended
    (`same release` when both fields name one release, otherwise
    `DIFFERENT releases (the pair verified in versions.json)`), and
    `0 unexpected` in the Log check. New benign log lines go into
    `_BENIGN_LOG_LINES` and the benign table in `benchmark-flags.md`; exit 6
    "printed no results in the format this script parses" means the parser needs
    updating (next section). Check the TPU telemetry too: the **TPU tile time**
    line must name a known call pattern
    (`1 call per run, one per dispatch invoke` with the `2.3.1` binaries
    re-uploaded on 2026-10-23, observed 2026-10-26; `2 calls per run` with
    `2.3.0`, 2026-10-09). The formula needs no change for either; a new pattern
    needs a row in the table under "TPU tile time" in `benchmark-flags.md`. The
    **TPU energy** line must say `1 call per run, one per dispatch invoke` too
    (`2.3.1` re-upload, 2026-10-26), or name why not. The provenance lines must
    show the md5s noted in step 1.
6. **Record the evidence** in `versions.json` `verified`: date, the run's
   output directory or run id, device, host, and the binaries build (release
   and md5 from the provenance lines). To make this run the documented
   example, replace the example block in `benchmark-flags.md` with its
   `report.md`, unchanged.
7. **Re-verify the version-labelled observations** and add new ones labelled
   with `V`:
   - `compile-flags.md`: the "How the SDK package install works" table (sdist
     behaviour, error strings, `SKIP_SDK_DOWNLOAD`, host gating), the Python
     wheels row, the `GOOGLE_TENSOR_BACKEND_ENABLED` note.
   - `troubleshooting.md`: rows that name a version.
   - `benchmark-flags.md`: the bucket table (re-check the listing and update
     its "checked" date), the output format block, the benign log lines, the
     interoperability note.
8. **Packaging** (when `pip_release` or `maven_release` changed): diff the
   new release's `ai_edge_litert/aot/ai_pack/export_lib.py` against the old
   one, then package a build and run steps 6 and 7 on a Pixel 10 (and a
   Pixel 11 if available).
9. Run the checks under "Validation" and send the change for review with the
   evidence from steps 4-6 and 8.

If a step fails, revert `versions.json`; nothing else depends on the attempt.

## Updating the benchmark output parser

When a `benchmark_model` build exits 0 but `benchmark_on_device.py` stops with
exit 6 "printed no results in the format this script parses":

1. Take `npu.log` from the run's output directory.
2. Extend `_PATTERNS` (and, if needed, `_DELEGATION_RE`, `_PHASE_STATS`,
   `_LEGACY_TIMINGS`, `_LEGACY_PEAK`) in `benchmark_on_device.py`. Keep the
   existing patterns working: older builds stay in users' caches.
3. Replace the block under "Output format parsed by the script" in
   `benchmark-flags.md` with the new results block, verbatim.
4. Re-run and check that every table row is filled.

The dispatch library's hook reports are parsed the same way: `_TILE_TOTAL_RE` /
`_TILE_COUNT_RE` (tile time) and `_POWER_TOTAL_RE` / `_POWER_COUNT_RE` (energy).
If a library changes their format, the header says `no report`: extend the
patterns and replace the report blocks under "TPU tile time" and "TPU energy" in
`benchmark-flags.md`. `_POWER_OLD_MARKER` (a log string only the old power hook
has) keeps the power metric off for old libraries; drop it once no supported
library carries the old hook (the Maven runtime AAR did up to 2.3.0, and apps
built with it keep shipping it; the 2.3.2 AAR does not, checked 2026-10-27).

## Editing Principles

- `SKILL.md` holds the workflow an agent follows during a user job;
  `references/` hold tables and details it loads on demand. A fact lives in
  one place, and the other links to it.
- Keep the `SKILL.md` body under 500 lines, link every file under
  `references/`, `scripts/` and `assets/` from `SKILL.md` with a relative
  Markdown link, and keep the table of contents at the top of each reference
  over 100 lines in sync (anchor links and line hints) when you edit it.
- Instructions name no version; observations always name the version or
  date they were made on.
- Every script error names its fix, and exit codes match the scripts'
  docstrings, `SKILL.md` and the references. A new failure mode gets a
  `troubleshooting.md` row.
- Python style: 2-space indentation, 80 columns for new lines, standard
  library only.

## Validation

Run from the skill directory; none of these needs a phone, the network or
LiteRT:

```bash
python3 -m py_compile scripts/*.py
python3 -c "import json; json.load(open('assets/versions.json'))"
python3 scripts/compile_model.py --print-install
python3 scripts/compile_model.py --print-install --colab
python3 scripts/compile_model.py --help
python3 scripts/check_compiled.py --help
python3 scripts/benchmark_on_device.py --help
python3 scripts/benchmark_on_device.py --model <any compiled .tflite> --dry-run
python3 scripts/package_ai_pack.py --help
python3 scripts/install_and_verify.py --help
```

`--print-install` must show the new pin, and `--dry-run` the default URLs for
`binaries_release` (it needs an `adb` on PATH but does not run it). Search the
docs for leftover numbers: in `SKILL.md` and `references/`, `==` must be
followed by `<pinned>` and `binaries/` by `<release>`, a non-numeric
directory such as `latest`, or a labelled observation. Changes to the compile
or benchmark paths also need steps 3-5 of the runbook on real hardware.

Links in the skill must be public: no URLs that need a company network,
VPN or login, and no short links that only resolve inside one organization.
