---
name: litert-google-tensor
description: >-
  Compiles LiteRT (.tflite) models ahead-of-time for Google Tensor TPUs
  (Tensor G5 on Pixel 10, Tensor G6 on Pixel 11) locally on Linux x86_64 or
  on Google Colab (--colab on macOS, Windows, or ARM hosts),
  benchmarks them on a USB-attached Pixel with LiteRT's benchmark_model
  (NPU latency, peak memory, TPU tile time, TPU energy, optional CPU baseline),
  and packages compiled models for an Android Gradle app as a Google Play AI
  pack with the Tensor NPU runtime module and a Kotlin loader, applies it to
  the app and verifies it on a Pixel. Use when the
  user asks to compile, AOT-compile, or prepare a .tflite model for the Pixel
  TPU/NPU, check whether a .tflite is already Tensor-compiled, measure
  on-device NPU performance of a compiled model, or package or deploy a
  compiled model into their Android app (or replace the one it ships). Don't
  use for Qualcomm, MediaTek, or Samsung NPUs, GPU-only benchmarking,
  LiteRT-LM or LLM (.litertlm) models, on-device JIT compilation, non-Gradle
  builds, or publishing to Google Play.
metadata:
  version: "1.0.0"
  category: AiAndMachineLearning
---

# LiteRT on Google Tensor: compile, benchmark, package for apps

Three scriptable workflows for Pixel TPUs:

1.  **Compile** a plain `.tflite` into a Google Tensor AOT-compiled `.tflite`
    with the public LiteRT Python API (`ai_edge_litert.aot`), locally on Linux
    `x86_64` or on a Google Colab VM (`--colab`, via `google-colab-cli`) when
    the user is on macOS/Windows or lacks a Linux box.
2.  **Benchmark** a compiled model on a connected Pixel with LiteRT's
    `benchmark_model`, NPU-only, optionally next to a CPU baseline, including
    TPU tile time (pure TPU compute time) and TPU energy per inference.
3.  **Package** compiled builds for an Android (Gradle) app as a Google Play AI
    pack with the Google Tensor NPU runtime and a Kotlin loader (or, for an app
    that already ships Google Tensor builds, only the files to replace), apply
    the plan to the project when the user agrees, and check the app on a Pixel.

Everything runs synchronously in the user's terminal; the scripts never start
background processes and always clean up what they pushed to the phone or
allocated on Colab. All paths below are relative to this skill's directory
(`SKILL_DIR`).

Path | Purpose
---- | -------
[assets/versions.json](assets/versions.json) | LiteRT versions the scripts use (single source)
[scripts/check_compiled.py](scripts/check_compiled.py) | Is this `.tflite` already Tensor-compiled?
[scripts/compile_model.py](scripts/compile_model.py) | AOT compile (local Linux `x86_64` or `--colab`)
[scripts/benchmark_on_device.py](scripts/benchmark_on_device.py) | adb push -> benchmark -> parse -> cleanup
[scripts/package_ai_pack.py](scripts/package_ai_pack.py) | Compiled builds -> AI pack + Gradle modules for an app, or an update of one
[scripts/install_and_verify.py](scripts/install_and_verify.py) | Build the app, install it like Google Play, read the NPU/CPU result
[assets/templates/](assets/templates/) | Gradle, Kotlin, `INTEGRATION.md` and `UPDATE.md` templates (`package_ai_pack.py`)
[references/compile-flags.md](references/compile-flags.md) | API, compiler flags, script options, `--colab`
[references/benchmark-flags.md](references/benchmark-flags.md) | What the benchmark runs, binaries, writing the report, example output
[references/app-integration.md](references/app-integration.md) | Packaging for an app: contents, checks, delivery modes, applying the plan, checking on a Pixel
[references/troubleshooting.md](references/troubleshooting.md) | Symptom -> fix tables
[references/contributing.md](references/contributing.md) | Maintainers: adopting a new LiteRT release

Every script supports `--help` and `--dry-run` and is Python 3 standard library
only, so it runs with any `python3`, with two exceptions that import LiteRT: a
local compile (`compile_model.py` without `--colab`, `--dry-run` or
`--print-install`) must use the virtualenv's interpreter
(`<venv>/bin/python SKILL_DIR/scripts/compile_model.py ...`, or activate the
venv first), and a real `package_ai_pack.py` run (not `--dry-run` or
`--check-project`) needs a Python with `ai-edge-litert` (the compile venv
works; the Beta SDK is not needed).

## Prerequisites (tell the user up front)

| Need | Compile (local) | Compile (`--colab`) | Benchmark | Package (app) |
|---|---|---|---|---|
| **Google Tensor SDK Beta access** - sign up at https://services.google.com/fb/forms/tensor_ml_sdk_experimental_access (overview: https://developers.google.com/edge/litert/next/tensor-sdk). Google emails a download link for `litert_plugin_compiler.tar.gz`; the compiler cannot be installed without it. | required | required (`--sdk-tarball` or `--sdk-url`) | - | - |
| Host OS | Linux **x86_64**, >= 16 GB RAM | any OS (`colab` CLI on PATH; runs on a remote Colab Linux `x86_64` VM) | any OS with `adb` | any OS where `ai-edge-litert` installs (the compile venv's Linux `x86_64` host works) |
| Python environment | Local venv with `ai-edge-litert` + `ai-edge-litert-sdk-google-tensor` at the version in `versions.json` (`compile_model.py --print-install`) | Any local `python3` + `google-colab-cli` (`compile_model.py --print-install --colab`); SDK is installed on the Colab VM automatically | any `python3` (stdlib only) | a Python with `ai-edge-litert` (the compile venv works; the SDK package is not needed) |
| `adb` on PATH, Pixel 10/11 with USB debugging enabled | - | - | required | step 7 (install and check the app) |
| A JDK the app's Gradle supports (`JAVA_HOME`), the Android SDK, the project's `./gradlew` | - | - | - | steps 6-7 (build, install); bundletool is downloaded once |
| `libLiteRtDispatch_GoogleTensor.so` - downloaded automatically from the public LiteRT binaries bucket (same directory as `benchmark_model`), or supplied with `--dispatch-lib` | - | - | required | - (the app gets it from Google Maven) |
| Internet | once for `pip install` | required (Colab VM + `pip install`) | once to fetch `benchmark_model` + dispatch lib (cached in `~/.cache/litert-google-tensor/`) unless supplied locally | - (the app's Gradle build downloads the LiteRT Maven artifacts) |

Supported targets: `Tensor_G5` (Pixel 10 family) and `Tensor_G6` (Pixel 11
family), as listed by the public Tensor SDK docs; Pixel 9 and older are not.

## Step 0 - Collect parameters

Ask the user only for what is missing; never invent values:

Parameter                           | How to get it
----------------------------------- | -------------
Model path                          | Absolute path to the `.tflite`. Confirm it exists.
Goal                                | check only, compile only, benchmark only, compile + benchmark, or package for an app (step 5). Infer it from the request ("how fast is it on the TPU vs CPU" = compile if needed + benchmark with a CPU baseline; "put it in my app" / "deploy it" = package); do not add an unrequested device run.
Target SoC                          | For a **compile**, the user's stated device wins (Pixel 10 family = `Tensor_G5`, Pixel 11 family = `Tensor_G6`), even if a different Pixel is attached. For a **benchmark**, the attached phone decides: `adb shell getprop ro.soc.model` -> `Tensor G5` => `Tensor_G5`, `Tensor G6` => `Tensor_G6` (the benchmark script reads and enforces this itself).
Output path                         | Default `<output-dir>/<stem>_Google_<target>.tflite`. `compile_model.py` refuses to overwrite an existing file (exit 2): run `check_compiled.py` on the existing file and reuse it, or pass `--output-name`, or `--overwrite` after asking. When a second build is needed next to an existing one, name it `<stem>_Google_<target>.<YYYYMMDD-HHMM>.tflite` (e.g. `--output-name model_Google_Tensor_G5.20260107-0930.tflite`) or, for a flag variant, `<stem>_Google_<target>.<flag-summary>.tflite` (`...G5.half-maxsharding.tflite`); keep the `_Google_<target>` part so the file stays recognisable.
Device serial                       | Only if `adb devices` lists more than one device.
Dispatch library / benchmark binary | Optional. Both are downloaded automatically from the same public bucket directory and cached. Only ask if the user wants a specific build, or if the host is offline: then `--benchmark-bin <benchmark_model>` plus `--dispatch-lib <libLiteRtDispatch_GoogleTensor.so \| dir \| .zip \| .aar>` (also env `LITERT_GOOGLE_TENSOR_DISPATCH_LIB`) use local copies and no network is touched.
CPU baseline                        | Optional; needs the path of the **original uncompiled** model (ask for it if only a compiled file was given; the benchmark script rejects a compiled file here with exit 2).
Run counts / mode                   | Defaults 5 warmup / 50 measured, `burst` performance mode. `benchmark_model` treats counts as **minimums** and also runs at least 0.5 s warmup / 1 s measured, so fast models execute more runs than requested. If the user states exact counts, say so and ask whether to disable the floors (`--extra-arg=--min_secs=0 --extra-arg=--warmup_min_secs=0`); "steady-state" / "sustained" requests map to `--performance-mode sustained_performance`.
TPU tile time                       | On by default, nothing to ask: a second, hooked NPU pass. `--no-tile-time` turns it off; the hooked pass itself (it repeats the NPU run, so slow models take about twice as long) is skipped only with `--no-tile-time --no-power`.
TPU energy                          | On by default, nothing to ask: the power metric of the same hooked pass (the TPU rail's energy per inference). `--no-power` skips it. The script leaves it off, and says why, for a dispatch library whose power hook predates the fix.
Compile mode                        | Local Linux `x86_64` by default. Use `--colab` when the host is not Linux `x86_64` (macOS/Windows/ARM) or when the user asks to compile on Google Colab; ask for the Beta tarball path (`--sdk-tarball` / `GOOGLE_TENSOR_SDK_BETA`) or URL (`--sdk-url` / `GOOGLE_TENSOR_ML_SDK_URL`) before running.
Compiler flags                      | Default to the compiler defaults; only set flags the user asks for or that troubleshooting requires (see [references/compile-flags.md](references/compile-flags.md)).
App deployment level                | Packaging jobs only; nothing to ask up front. After step 5, tell the user the plan is ready (`INTEGRATION.md`, or `UPDATE.md` for an update) and ask whether you should apply it to their project (step 6). After that, offer to install the app on their Pixel and check it uses the NPU (step 7).
New integration or update           | Packaging jobs only. Ask whether the app already ships Google Tensor builds (an AI pack with folders like `model#group_Google_Tensor_G5` under its `src/main/assets`). If it does, it is an **update** (step 5b): ask for the project root (the folder with `settings.gradle.kts` or `settings.gradle`). The pack, model file, device groups, delivery mode and app module then come from the project, so do not ask for them.
Builds to package                   | One compiled build per target SoC (`Tensor_G5`, `Tensor_G6`) plus the **original uncompiled** model they were compiled from (the app's CPU path). Compile missing targets first (step 2); a build is per SoC, so a Pixel 11 needs a `Tensor_G6` build. For an update, build every SoC the app already ships.
Delivery mode                       | New integrations only (an update keeps the app's). When Google Play puts the model on the phone: `install-time` (default; installed with the app, ready at first launch), `fast-follow` (downloaded right after install) or `on-demand` (downloaded when the app asks). Explain each in one sentence ([references/app-integration.md](references/app-integration.md#delivery-modes-asked-in-step-0)) and use the default when the user has no preference.
Pack / model names, app module      | New integrations only. Defaults: pack name = the original's file name made valid, model name = pack name, app module `app`, Kotlin package `com.example.litert`. Ask only when the user's project differs (another app module name, their package).
Quick test (optional)               | New integrations only. Offer it when the user wants to try the model on their own Pixel before setting up bundletool: `--quick-test` adds a copy of each build and the steps for `./gradlew installDebug -PtensorQuickTest=<SoC>`, which puts the build and the NPU runtime in the debug APK. Local testing only; release builds are unaffected.

## Commands or a plan only (the user says not to run anything)

Run nothing - not even the read-only scripts - and give the same steps as a
real run, in the same order, as commands the user can paste:

1.  Start with `check_compiled.py` on every input model (step 1), **before**
    any install or compile command; checking only the compiled output
    afterwards is not enough.
2.  For installs, give `python3 SKILL_DIR/scripts/compile_model.py
    --print-install [--colab]` as the command that produces them (step 2a),
    then the lines it prints with the user's paths filled in (venv,
    `export GOOGLE_TENSOR_SDK_BETA=<their tarball>` before `pip install`) and
    each version written as `<version printed by --print-install>`. Never
    copy a version number from `versions.json` or from memory.
3.  Give no results, not even estimates: latency, speed-up, memory and ops
    offloaded come only from the scripts' output. Say where they will appear
    (for a benchmark, the table `benchmark_on_device.py` prints and saves as
    `report.md`).
4.  When the plan changes the user's app project (step 6), say that nothing
    in the project changes until they approve, and end by asking whether you
    should apply it.

## Step 1 - Check whether the model is already compiled

```bash
python3 SKILL_DIR/scripts/check_compiled.py /abs/path/model.tflite [--expect-target Tensor_G5]
```

Run it on every model file involved (the model to compile or benchmark, the
CPU-baseline file, and an existing output file you are about to reuse). For a
benchmark job read the phone first (`adb shell getprop ro.soc.model` prints
`Tensor G5` or `Tensor G6`) and pass the underscore form as `--expect-target`
(`Tensor G5` -> `--expect-target Tensor_G5`), so one check answers both
"compiled?" and "for this phone?" (a plain model exits 1 either way); the
benchmark script enforces the match again anyway (exit 4).

| Exit | Meaning | Next action |
|---|---|---|
| 0 | compiled for Google Tensor (SoC printed) | skip compile; report the SoC (and the `Compile info` line if a `.compile.json` sidecar exists). Continue to step 3 only if the goal includes a benchmark. No sidecar (compiled elsewhere, flags unknown): for a plain "how fast is it" job, benchmark the file as-is and say "compile flags unknown"; when the user needs to know how it was built (or wants a reproducible comparison), compile the original with the defaults under a new `--output-name` and compare SHA-256 (`sha256sum` of both files, or `output_sha256` in the new sidecar): compilation is deterministic, so an identical hash proves the existing file is a default build ([references/compile-flags.md](references/compile-flags.md)). Never `--overwrite` to find out. |
| 1 | plain (uncompiled) model | go to step 2 if compiling; this is the correct file for `--cpu-baseline` |
| 2 | compiled for a different SoC than `--expect-target` | compiled models are SoC-specific (a `Tensor_G5` file never runs on a `Tensor_G6` TPU, and a `Tensor_G6` file never runs on a `Tensor_G5` TPU; there is no runtime fallback, and `--allow-mismatch` only produces dispatch errors). Tell the user which SoC the phone has, then offer, in this order: an existing `*_Google_<phone target>.tflite` build of the same model in the project (verify it with this check first; do not benchmark it unless the user says so), attaching the matching phone, or recompiling the **original** uncompiled export for the phone's target. |
| 3 | not a `.tflite` / missing | fix the path |
| 4 | compiled by another toolchain: an Edge TPU custom op (`edgetpu-custom-op...`) instead of LiteRT's `DISPATCH_OP` | not usable here: LiteRT cannot recompile it or run it on the Google Tensor TPU, and the CPU cannot run it (so it is no `--cpu-baseline` or `--fallback` either; the scripts refuse it). Ask for the original model it was compiled from and compile that (step 2) |

The `LiteRtStamp` is authoritative (the `_Google_Tensor_G5` suffix is only a
naming convention) and records the SoC but **not** the compiler flags: those
come from the `<model>.compile.json` sidecar that `compile_model.py` writes
next to its output; without it, say "flags unknown" rather than guessing.

## Step 2 - Compile (Linux x86_64 or Google Colab via `--colab`)

### 2a. One-time environment

The SDK pip package contains no compiler by itself: at install time it unpacks
the Beta tarball that `GOOGLE_TENSOR_SDK_BETA` points to (same flow as the
public codelab). Ask the user for the tarball path first, then print the
install commands for the LiteRT version the skill pins in `versions.json`:

```bash
python3 SKILL_DIR/scripts/compile_model.py --print-install [--colab]
```

**Local Linux `x86_64`** (`--print-install`): runs with any `python3` and prints
comment lines (the pinned version, when and on what it was last verified, the
supported Python range, and whether this host and Python qualify) followed by:

```text
python3 -m venv ~/.venvs/litert-tensor && source ~/.venvs/litert-tensor/bin/activate
pip install --upgrade pip
export GOOGLE_TENSOR_SDK_BETA=/abs/path/litert_plugin_compiler.tar.gz   # from the Beta e-mail
pip install --no-cache-dir ai-edge-litert==<pinned> ai-edge-litert-sdk-google-tensor==<pinned>
```

**Remote Google Colab** (`--print-install --colab`) - for macOS, Windows,
non-x86 Linux, or when compiling on Colab without a local Linux venv: installs
`google-colab-cli` into `~/.venvs/colab-cli`
([how `--colab` works](references/compile-flags.md#compiling-on-google-colab---colab)).
Never ask the user to run a terminal command for OAuth: when `--colab` needs
one-time OAuth, show its printed URL in chat, ask the user for the code, and
re-run with `--colab-auth-code <CODE>`.

*   Tell the user before installing anything. Run the printed commands with the
    real tarball path and never type a LiteRT version yourself: the runtime and
    SDK packages must be one version (`WARNING` when they differ; `NOTE` when
    they match each other but not the pin). Use `-nightly` packages only when
    the user explicitly asks for nightlies.
*   If `--print-install` warns about the Python version, create the venv with
    a `python3.N` in the supported range. Install errors:
    [references/troubleshooting.md](references/troubleshooting.md#environment-and-install).

**If the user has no Beta access yet:** say so plainly - the compiler cannot be
installed until Google e-mails the tarball link (sign-up form above) - and do
not install anything or allocate a Colab VM meanwhile (`--colab` checks for the
tarball before `colab new`). Still useful now: run `check_compiled.py` on their
files, confirm the host and phone SoC, and run `--dry-run` / `--print-install`.

### 2b. Compile

```bash
# Local Linux x86_64 (using the virtualenv's interpreter):
python3 SKILL_DIR/scripts/compile_model.py /abs/path/model.tflite \
  --target Tensor_G5 --output-dir /abs/path/compiled

# Remote Google Colab VM (any OS, any local python3 + google-colab-cli):
python3 SKILL_DIR/scripts/compile_model.py /abs/path/model.tflite \
  --target Tensor_G5 --colab --sdk-tarball /abs/path/litert_plugin_compiler.tar.gz \
  --output-dir /abs/path/compiled
# -> /abs/path/compiled/model_Google_Tensor_G5.tflite
```

The script prints the compilation report, re-verifies the Tensor stamp, writes
`<output>.compile.json` (flags, ops offloaded / total, package versions,
SHA-256s) and never overwrites an existing output (exit 2) unless
`--overwrite` is given. Ops left on the CPU in the report mean the strict NPU
benchmark will fail (step 3, `--allow-cpu-fallback`). Every compiler, script
and Colab option: [references/compile-flags.md](references/compile-flags.md).

*   If the compiler crashes with an internal error - or the user reports that it
    did with the defaults (no need to reproduce the crash) - use
    `--truncation-type half --sharding-intensity maximum` (public FAQ guidance)
    and tell the user which flags produced the artifact. `half` changes the
    numerics (16-bit floats on the TPU), so tell the user to validate the
    model's outputs against the original before relying on it.
*   Report a compile-only job from the script's output and sidecar only:

    ```markdown
    **Compiled:** <output path> (<bytes from "Compiled model written to" line>)
    **Target / flags:** <cli_flags from the sidecar, or "--target X (compiler defaults)">
    **Ops offloaded:** <N / M from the "Ops offloaded to the TPU" line>
    **LiteRT:** <"packages" from the sidecar, plus the script's WARNING/NOTE line if it printed one>
    **Verified:** check_compiled.py -> <its Status line>
    ```

Exit codes: 0 ok, 2 bad input, 3 already compiled, 4 unsupported host,
5 LiteRT packages or Beta compiler library missing (message includes the
install fix), 6 compile failed (compiler log errors are printed),
7 output verification failed.

## Step 3 - Benchmark on the device

```bash
python3 SKILL_DIR/scripts/benchmark_on_device.py \
  --model /abs/path/compiled/model_Google_Tensor_G5.tflite \
  [--cpu-baseline /abs/path/model.tflite] [--serial SERIAL] \
  [--dispatch-lib /abs/path/libLiteRtDispatch_GoogleTensor.so] \
  [--output-dir /abs/path/results]
```

The script refuses a model compiled for another SoC than the phone's (exit 4;
`--dry-run` never contacts the phone, so it proves nothing about the match),
fetches `benchmark_model` and `libLiteRtDispatch_GoogleTensor.so` once from the
bucket release in `versions.json` (cached; `downloaded from <url>` means a
first download - tell the user what was fetched), runs the strict NPU
benchmark, a second hooked NPU pass for TPU tile time and TPU energy, and the
optional CPU baseline on the **uncompiled** model in a fresh
`/data/local/tmp/litert_benchmark/run-*` directory, which it deletes even on
failure. It writes `report.md`, `results.json` and the logs to `--output-dir`
(nothing after exit 2/3/4 or `--dry-run`). Each step and flag:
[references/benchmark-flags.md](references/benchmark-flags.md#what-the-script-does).

The script is NPU-only by design (`--extra-arg` cannot switch the accelerator,
and an uncompiled model is rejected with exit 2); GPU or non-Tensor runs
(`benchmark_model --use_gpu=true` etc. directly) are outside this skill. Other
options (`--num-runs`, `--performance-mode`, `--signature`,
`--allow-cpu-fallback`, `--no-tile-time`, `--no-power`, ...) are in `--help`.

*   **Offline host:** pass both `--benchmark-bin` and `--dispatch-lib`; a
    `--dry-run` then shows `user-provided: <path>` for both binaries without
    touching the phone or the network - the proof the user wants first.
*   **Binary versions:** keep `benchmark_model` and the dispatch library from
    the **same** bucket release (the default does; `--benchmark-url
    .../binaries/<release>/android_arm64/benchmark_model` pins another one and
    the dispatch URL follows). If a provenance md5 differs from
    `verified.binaries` in `versions.json`, rerun with `--refresh-binary`
    ([details](references/benchmark-flags.md#choosing-binary-versions)).

## Step 4 - Report

Nothing in the report is typed by hand. `benchmark_on_device.py` prints a
Markdown header + table (also saved as `report.md` and as the `markdown` field
of `results.json`) in which every value is read from the device or the run.
Paste that block verbatim and add only the context the script cannot know:

```markdown
**Summary:** <NPU "Inference avg" from the table> ms on the TPU vs <CPU "Inference avg"> ms on the CPU (<the N.NNx value from the script's "NPU speed-up vs CPU" line>); peak memory <NPU> vs <CPU> MB; <strict NPU | CPU fallback allowed>. TPU tile time <"TPU tile time / inference" row> ms per inference. TPU energy <"TPU energy / inference" row> mJ per inference.

<header and table exactly as printed by benchmark_on_device.py, including any "Unexpected log lines" section>

**Notes:** <what the Log check line reports: "none" when both logs show 0 unexpected lines and no profiler retry; otherwise each unexpected line with its meaning from references/benchmark-flags.md or troubleshooting.md, plus anything the user should validate>
```

When nothing ran (check exit 2, benchmark exit 2/3/4/5, no device), report
the same way - from output, not from memory:

```markdown
**Not run:** <the script's ERROR line verbatim>

- Device: <the "Device: ..." line printed by benchmark_on_device.py, or the `adb devices -l` line>
- Model: <the "Status: ..." line from check_compiled.py>
- Nothing was pushed to or removed from the phone.

**Options:** <the next actions from step 1 / troubleshooting, most specific first>
```

*   NEVER type, round, or "tidy up" numbers, and NEVER reuse values from an
    earlier run or from any example in this skill - copy the script output.
    Prose numbers (the Summary line) must be character-for-character the
    table's values. Never edit `report.md` (script output); if the user wants
    the answer saved, write `summary.md` next to it.
*   Before writing the Summary and Notes, read
    [Writing the report](references/benchmark-flags.md#writing-the-report)
    (no CPU baseline, combined compile + benchmark jobs, run counts, CPU
    fallback, mixed LiteRT releases, speed-up below 1x, TPU tile time/energy).

## Step 5 - Package for an app (Gradle)

Two cases (Step 0, "New integration or update"); what the package contains and
how the script checks it: [references/app-integration.md](references/app-integration.md).

*   **5a - New integration:** an AI pack written by LiteRT's own exporter from
    the files as they are (byte-identical, nothing recompiled), the Google
    Tensor NPU runtime as an install-time feature module (from Google Maven),
    the original model for the app's CPU path, a Kotlin loader, and an
    `INTEGRATION.md` with every remaining step for the user's project.
*   **5b - Update** (the app already ships Google Tensor builds):
    `--update-project` only reads the project and prepares the files to
    replace, under the app's own paths and names, plus an `UPDATE.md`.

```bash
# 5a -> <fallback dir>/app_package/<pack name>/INTEGRATION.md and the modules
<venv>/bin/python SKILL_DIR/scripts/package_ai_pack.py \
  --compiled /abs/path/compiled/model_Google_Tensor_G5.tflite \
  [--compiled /abs/path/compiled/model_Google_Tensor_G6.tflite] \
  --fallback /abs/path/model.tflite \
  [--delivery install-time|fast-follow|on-demand] [--pack-name NAME] \
  [--model-name NAME] [--app-module app] [--kotlin-package com.example.litert] \
  [--quick-test] [--output-dir /abs/path/app_package/NAME]

# 5b -> <fallback dir>/app_update/<pack>/UPDATE.md, update.json, files/<paths>
<venv>/bin/python SKILL_DIR/scripts/package_ai_pack.py \
  --update-project /abs/path/to/app-project \
  --compiled /abs/path/compiled/model_Google_Tensor_G5.tflite \
  [--compiled /abs/path/compiled/model_Google_Tensor_G6.tflite] \
  --fallback /abs/path/model.tflite \
  [--pack-name NAME] [--model-name NAME] [--cpu-asset PATH|none]
```

1.  Run `check_compiled.py` on every file first (step 1), and package builds
    that passed the strict benchmark (step 3).
2.  Run with `--dry-run` first (any `python3`), then for real with a Python
    that has `ai-edge-litert`. The script refuses mismatched inputs and never
    replaces a directory it did not write.
3.  For 5b, show the user the verdict and the file list: `drop-in` (only
    model files change), `structural` (`UPDATE.md` section 2 lists the other
    changes; list them and ask how to proceed before anything else) or
    `up-to-date`. A `Runtime` check of `device` means the new builds must pass
    the strict benchmark with the app's own runtime library first (`UPDATE.md`
    section 4).
4.  Paste the script's `**Packaged:** ...` or `**Update plan:** ...` block
    verbatim, add one line (the delivery mode or the verdict in plain words,
    and "next: `<output-dir>/INTEGRATION.md`" or `UPDATE.md`), then ask: "The
    integration plan is ready (`INTEGRATION.md`). Do you want me to apply it
    to your project?" (or "The update plan is ready (`UPDATE.md`). ..."). If
    yes, go to step 6. Publishing to Google Play stays with the user.

Exit codes: 0 ok, 2 bad input (missing file, duplicate SoC, invalid name,
output exists, a build that differs from its sidecar, or a project
`--update-project` cannot update as is), 3 wrong model kind (uncompiled
`--compiled`, compiled `--fallback`), 5 LiteRT not importable or its exporter
API changed (the message has the fix), 7 post-export verification failed
(nothing is left at `--output-dir`).

## Step 6 - Apply the plan to the user's project (when they say yes)

You apply the plan; the user approves it once. Before changing anything,
show the **whole plan** and get **one approval**. Then ask **separately** for
each risky item (the check marks them): upgrading the Android Gradle plugin
or Kotlin, adding Kotlin, raising `minSdk`, limiting the app to arm64-v8a
(devices without it can no longer install the app), changing the app's
LiteRT version, replacing project files that differ from the package,
removing a SoC. A declined item is skipped; say what will not work without
it.

*   **6a - New integration:** the plan is the `fail` items of a read-only check
    (any `python3`, no LiteRT), each with its fix:

    ```bash
    python3 SKILL_DIR/scripts/package_ai_pack.py --check-project /abs/path/to/app-project \
      --package <output-dir of step 5a> [--app-module app] [--json]
    ```

*   **6b - Update:** the plan is `UPDATE.md` (the file table and section 2).

Follow the procedure in
[references/app-integration.md](references/app-integration.md#applying-the-plan-skillmd-step-6)
(backups, edits merged in the project's own style, re-check, one build). Never
delete or reformat unrelated code, and never touch signing configs.

## Step 7 - Install and check on a Pixel (when the user agrees)

Builds the user's app, installs it on the attached Pixel the way Google Play
would (bundletool local testing, for the phone's device group), and reads
the loader's `LITERT_TENSOR_RESULT` line:

```bash
python3 SKILL_DIR/scripts/install_and_verify.py --project /abs/path/to/app-project \
  [--app-module app] [--variant debug|release|<flavor>Debug] [--serial <id>] \
  [--uninstall-first] [--dry-run]
```

Run `--dry-run` first: it shows the phone, its device group and whether the
NPU path is expected. Exit 7 means the app is already installed and local
testing cannot update it: ask the user (uninstalling deletes the app's data on
the phone), then rerun with `--uninstall-first`. The app must call
`TensorModelLoader.load()`; if it loads the model on a particular screen, tell
the user to open it while the script waits. Report the script's block
verbatim: `"path":"npu"` is the pass; for `"path":"cpu"` on a phone the app
has a build for, the `npu_error` says why. Requirements and exit codes:
[references/app-integration.md](references/app-integration.md#checking-on-a-pixel-skillmd-step-7).

## Rules

*   ALWAYS run `check_compiled.py` before compiling or benchmarking, on every
    model file involved - the compiler cannot recompile a compiled model, and
    the TPU cannot run an uncompiled one.
*   ALWAYS verify the device SoC matches the model's stamp (the benchmark
    script does) - a `Tensor_G5` model on a `Tensor_G6` phone fails with an
    opaque dispatch error, wasting a debugging round.
*   ALWAYS use the original uncompiled model for `--cpu-baseline` - compiled
    models contain `DISPATCH_OP` nodes that only the NPU can execute.
*   ALWAYS clean up the per-run device directory (automatic; after an
    interrupted run list the base first, then remove only its `run-*` entries:
    `adb shell ls -la <base>` and `adb shell rm -rf <base>/run-*`, where
    `<base>` is `/data/local/tmp/litert_benchmark` or the `--device-dir` that
    was used). NEVER `rm -rf` the base directory itself - users keep their own
    binaries and models there.
*   NEVER combine `--use_cpu=true` with `--require_full_delegation=true` -
    `benchmark_model` aborts on that combination.
*   NEVER install packages into the system interpreter or without telling the
    user; use a virtualenv so pinned LiteRT versions do not break other work.
*   NEVER type LiteRT version numbers into install commands or download URLs
    yourself - take them from `compile_model.py --print-install` and the
    scripts' default URLs, which all read `versions.json`, so every job uses the
    pair that was verified together. Use another release only when the user
    asks for one (`--benchmark-url`, or the pip pair at that version), and say
    so in the report. Changing the pin is a maintainer task
    ([references/contributing.md](references/contributing.md)).
*   NEVER treat macOS, Windows, or ARM hosts as a compile blocker or give manual
    browser Colab notebook steps - run `compile_model.py --colab` directly.
*   NEVER leave adb, benchmark, or Colab VM sessions running in the background -
    every command here is bounded by a timeout and returns before the next step
    (`compile_model.py --colab` stops any Colab VM it creates unless
    `--keep-colab-session` is passed).
*   NEVER guess compile flags or overwrite an existing output without asking
    (`compile_model.py` exits 2; use `--output-name` or ask before
    `--overwrite`).
*   ALWAYS package for an app with `package_ai_pack.py` (it calls LiteRT's
    exporter and verifies the result), and with `--update-project` (step 5b)
    when the app already ships Google Tensor builds; NEVER create or edit AI
    pack folders, the device-targeting XML or the runtime modules by hand, and
    NEVER copy a new package's `ai_packs/` over an existing pack - the app's
    group names and the place of its CPU copy can differ.
*   ALWAYS ask before changing the user's project, show the whole plan, and
    get one approval; ask separately for each risky item (step 6) and before
    `install_and_verify.py --uninstall-first`. NEVER change signing configs.
*   NEVER put a compiled build where the app runs on the CPU (base assets,
    `--fallback`): only the original uncompiled model.
*   NEVER publish to Google Play, sign, or upload anything for the user; the
    skill stops at the package and the local-testing steps.

## Troubleshooting

Every script error names its fix; look up the error line or exit code in
[references/troubleshooting.md](references/troubleshooting.md).

## Public references

[LiteRT NPU guide](https://developers.google.com/edge/litert/next/npu),
[Google Tensor with LiteRT](https://developers.google.com/edge/litert/next/tensor-sdk),
[compilation flags](https://developers.google.com/edge/tensor-sdk/compilation-flags),
[Tensor SDK FAQ](https://developers.google.com/edge/tensor-sdk/tensor-faqs),
[release notes / compatibility](https://developers.google.com/edge/tensor-sdk/release-notes),
[benchmark_model](https://developers.google.com/edge/litert/next/benchmark),
[codelab](https://codelabs.developers.google.com/codelabs/google-tensor-ml-sdk),
[Play for On-device AI](https://developer.android.com/google/play/on-device-ai).

## Contributions

To contribute or modify this skill or its references, follow the
[contribution guidelines](references/contributing.md) before making changes.
