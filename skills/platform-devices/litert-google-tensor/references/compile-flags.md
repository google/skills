# Google Tensor compilation reference

Source of truth: the public LiteRT Python AOT API (`ai_edge_litert.aot`) and
https://developers.google.com/edge/tensor-sdk/compilation-flags. Everything in
`scripts/compile_model.py` maps 1:1 onto what is listed here.

## Contents

- [Python API used by the skill](#python-api-used-by-the-skill): Lines 16-50
- [Compiler flags (`google_tensor_*` kwargs)](#compiler-flags-google_tensor_-kwargs): Lines 52-68
- [Script options](#script-options): Lines 70-93
- [Package versions](#package-versions): Lines 95-131
- [Compiling on Google Colab (`--colab`)](#compiling-on-google-colab---colab): Lines 133-182
- [Interpreting the compilation report](#interpreting-the-compilation-report): Lines 184-191

## Python API used by the skill

```python
import os
os.environ["GOOGLE_TENSOR_BACKEND_ENABLED"] = "1"   # before any LiteRT import

from ai_edge_litert.aot import aot_compile as aot_lib
from ai_edge_litert.aot.vendors.google_tensor import target as gt_target

target = gt_target.Target(gt_target.SocModel.TENSOR_G5)   # or TENSOR_G6
result = aot_lib.aot_compile(
    "/abs/path/model.tflite",
    output_dir="/abs/path/work",          # intermediates land here
    target=target,
    keep_going=False,                     # fail fast on backend errors
    google_tensor_truncation_type="auto", # any google_tensor_* flag as kwarg
)
print(result.compilation_report())        # per-subgraph partition stats
result.export("/abs/path/out", model_name="model")
# -> /abs/path/out/model_Google_Tensor_G5.tflite
```

Facts worth remembering:

Item                                | Value
----------------------------------- | -----
`SocModel` enum values              | `Tensor_G3`, `Tensor_G4`, `Tensor_G5`, `Tensor_G6`, `ALL` (case-sensitive strings)
Officially supported SoCs           | `Tensor_G5` (Pixel 10 family), `Tensor_G6` (Pixel 11 family)
Backend id / target id              | `GOOGLE` / `Google_Tensor_G5` (used as the export file suffix)
Default `output_dir`                | API: `<input dir>/_compiled_models/` when omitted. `compile_model.py` instead writes to `--output-dir` (default `<model dir>/compiled/`) and refuses to overwrite an existing file unless `--overwrite` is given.
`keep_going` default                | `True` (collects failures instead of raising) - the skill uses `False`
Env var for stable `ai-edge-litert` | `GOOGLE_TENSOR_BACKEND_ENABLED=1`, set **before** importing `ai_edge_litert.aot` (required by the public FAQ; the 2.1.6 Python wheel itself does not read it, so it is harmless and the script always sets it)
Compiler plugin location            | Resolved from the `ai-edge-litert-sdk-google-tensor` package (`path_to_sdk_libs()`); fallback env var `GOOGLE_TENSOR_COMPILER_LIB`
Host                                | Local: Linux `x86_64` only; 16 GB RAM minimum (64 GB recommended for large inputs). Non-Linux hosts (`darwin`, `win32`, `linux/aarch64`) can compile remotely on a Google Colab Linux `x86_64` VM via `--colab` (`google-colab-cli`).
What the output records             | The `LiteRtStamp` metadata holds the SoC only. The flags, the partition report (`ops_offloaded` / `ops_total`), the installed package versions (`packages`) next to the skill's pin (`pinned_pip_release`), and SHA-256 checksums of input, output and compiler library (`compiler_library_sha256`, which identifies the Beta tarball's compiler build) are written by `compile_model.py` to `<output>.compile.json` (plus `compiled_via: "colab"`, `colab_session`, and `local_host` when compiled with `--colab`); `check_compiled.py` and `benchmark_on_device.py` read that sidecar when it sits next to the model.

## Compiler flags (`google_tensor_*` kwargs)

| kwarg | CLI flag in `compile_model.py` | Values | Default | When to use |
|---|---|---|---|---|
| `google_tensor_truncation_type` | `--truncation-type` | `auto`, `bfloat16`, `half`, `no_truncation` | `auto` | Float precision on the TPU. `half` is the documented fix for compiler crashes on memory-constrained targets; it forces 16-bit floats, so the user must validate the outputs against the original model. |
| `google_tensor_sharding_intensity` | `--sharding-intensity` | `minimal`, `moderate`, `extensive`, `maximum` | `minimal` | How aggressively the graph is split. `maximum` pairs with `half` for crash recovery. |
| `google_tensor_int64_to_int32` | `--int64-to-int32` | bool | `False` | Models with int64 tensors the TPU cannot handle. |
| `google_tensor_enable_large_model_support` | `--large-model-support` | bool | `False` | Models larger than 2 GB. |
| `google_tensor_enable_4bit_compilation` | `--enable-4bit` | bool | `False` | Convolutions with 4-bit weights. |
| `google_tensor_extra_options_path` | `--extra-options-path` | path | `""` | Binary options file shipped with some pre-optimized models. |

The skill forwards only non-default values, so a plain
`compile_model.py model.tflite --target Tensor_G5` is identical to the
compiler's own defaults. Compilation is deterministic in practice: the same
input and flags produced byte-identical outputs (same SHA-256) in repeated
runs, which is how to tell whether an existing artifact matches a given flag
set when its sidecar is missing.

## Script options

`compile_model.py` sets `GOOGLE_TENSOR_BACKEND_ENABLED=1` (required by the
stable package), checks the installed LiteRT package versions against each
other and `versions.json`, calls `aot_compile(...,
target=Target(SocModel.TENSOR_G5), keep_going=False, google_tensor_*=...)`,
prints the compilation report, exports to `--output-dir`, re-verifies the
Tensor stamp and writes `<output>.compile.json` (flags, `ops offloaded /
total`, package versions, SHA-256 of input/output/compiler lib, elapsed time,
plus `compiled_via: "colab"` with `--colab`). Besides the compiler flags above
and the Colab flags below, it takes:

Flag                 | Purpose
-------------------- | -------
`--output-dir DIR`   | Where to write the compiled model (default `<model dir>/compiled`).
`--output-name NAME` | Output file name (default `<model stem>_Google_<target>.tflite`).
`--overwrite`        | Replace an existing output file (default: refuse with exit 2, so a previous artifact is never clobbered).
`--keep-going`       | Continue past backend errors instead of failing fast (`keep_going=True`).
`--keep-intermediates` | Keep the compiler's intermediate files under `<output-dir>/_intermediates`.
`--no-report-file`   | Do not write the `<output>.compile.json` sidecar.
`--json`             | Print a JSON summary as the last line of stdout.
`--dry-run`          | Validate inputs and print the plan; do not compile.
`--print-install`    | Print the install commands for the pinned LiteRT pair (with `--colab`: the `google-colab-cli` setup), then exit.
`--force`            | Experimental: skip the already-compiled check. The compiler cannot recompile `DISPATCH_OP` partitions, so this normally fails; compile the original export instead.

## Package versions

Pin LiteRT and the Google Tensor SDK package to the **same** version. The
skill's pin lives only in `versions.json` (`pip_release`, with the supported
`python` range and what it was last verified on); no script or instruction
repeats it, and a version number elsewhere in these references only labels
an observation made on that release. The public compatibility matrix lives at
https://developers.google.com/edge/tensor-sdk/release-notes#compatibility.

| Track | Install command |
|---|---|
| Stable (skill default) | printed by `python3 scripts/compile_model.py --print-install`: venv, then `export GOOGLE_TENSOR_SDK_BETA=/abs/path/litert_plugin_compiler.tar.gz` and `pip install --no-cache-dir ai-edge-litert==<pinned> ai-edge-litert-sdk-google-tensor==<pinned>` |
| Nightly | same, with `--pre ai-edge-litert-nightly ai-edge-litert-sdk-google-tensor-nightly` |

Before compiling, `compile_model.py` reads the installed versions
(`importlib.metadata`): `WARNING` on stderr when a runtime package and its SDK
package differ (stable or nightly pair), `NOTE` on stdout when the stable
pair matches itself but not the pin (allowed - the compile uses what is
installed). Both messages carry the reinstall line for the pinned pair. The
sidecar records `packages` (installed) and `pinned_pip_release`, so a report
never depends on which version someone believes was installed.

How the SDK package install works (verified against the published 2.1.6 sdist):

| Fact | Detail |
|---|---|
| Source distribution only | `ai-edge-litert-sdk-google-tensor` is an sdist; its `setup.py` runs a custom `build_py` that unpacks the compiler into `ai_edge_litert_sdk_google_tensor/data/`. |
| `GOOGLE_TENSOR_SDK_BETA` | **Required.** Absolute path to the Beta tarball (`.tar.gz`/`.zip`) from the sign-up e-mail. Missing -> `SDK location is not set. Aborting installation.`; wrong path -> `Google Tensor SDK beta file not found`. |
| `GOOGLE_TENSOR_ML_SDK_URL` | Alternative: a URL to download the tarball from (only used when `GOOGLE_TENSOR_SDK_BETA` is unset). |
| `SKIP_SDK_DOWNLOAD` | Installs the package without any compiler - only useful for testing; `compile_model.py` then exits 5. |
| Host gating | The unpack step only runs on Linux x86_64; elsewhere the package installs empty and `compile_model.py` exits 4. |
| What the wheel provides | `ai_edge_litert` ships the plugin adapter `libLiteRtCompilerPlugin_google_tensor.so`; it dlopens `liblitert_plugin_compiler.so` from the SDK `data/` directory (or `GOOGLE_TENSOR_COMPILER_LIB` when the SDK package is absent). |
| pip wheel cache | pip caches the SDK wheel it built; after a failed/empty first attempt re-install with `--no-cache-dir --force-reinstall`. |
| Python versions | Supported range: `python` in `versions.json` (printed by `--print-install`, which also warns when the current Python is outside it). Observed for 2.1.6: manylinux x86_64 wheels (cp313 verified: `cp313-manylinux_2_27_x86_64`). |

When a new release is adopted, re-check the rows above against its sdist
(`references/contributing.md` lists what to re-verify).

## Compiling on Google Colab (`--colab`)

When the user's machine is not Linux `x86_64` (e.g. macOS, Windows, or Linux
ARM) or they prefer not to install the compiler locally, `compile_model.py
--colab` runs the exact same compilation on a remote Google Colab Linux `x86_64`
VM using `google-colab-cli` (`https://github.com/googlecolab/google-colab-cli`),
while keeping the input/output `.tflite` and `<output>.compile.json` sidecar on
the local machine for `check_compiled.py` and `benchmark_on_device.py`.

If the user prefers an interactive browser notebook instead of the CLI, point
them to the official public Colab notebook:
https://github.com/google-ai-edge/litert-samples/blob/main/samples/litert/colab/LiteRT_AOT_Compilation_Tutorial.ipynb

CLI flag in `compile_model.py` | Default                                                | Purpose
------------------------------ | ------------------------------------------------------ | -------
`--colab`                      | `False`                                                | Run the compile step on a remote Google Colab Linux `x86_64` VM via `google-colab-cli` (`colab`).
`--sdk-tarball FILE`           | `$GOOGLE_TENSOR_SDK_BETA`                              | Local path to `litert_plugin_compiler.tar.gz` (from the Google Tensor SDK Beta e-mail) to upload to the Colab VM when installing `ai-edge-litert-sdk-google-tensor`.
`--sdk-url URL`                | `$GOOGLE_TENSOR_ML_SDK_URL`                            | Alternative to `--sdk-tarball`: download URL for the Beta tarball fetched directly by the Colab VM.
`--colab-session NAME`         | `litert-gt-<pid>`                                      | Session name for `colab`. If `NAME` is already listed in `colab sessions`, the script reuses that VM instead of calling `colab new` and leaves it running at the end; otherwise it creates `NAME` and stops it when done (unless `--keep-colab-session` is set).
`--keep-colab-session`         | `False`                                                | Keep a newly created Colab VM running after the compile so a subsequent `--colab-session NAME` run skips uploading the tarball and `pip install`.
`--colab-high-mem`             | `False`                                                | Pass `--high-mem` to `colab new` when creating a new Colab VM (useful for large models or when a standard VM runs out of memory).
`--colab-timeout SECS`         | `900`                                                  | Timeout in seconds for the remote Colab compile execution (`colab exec --timeout`).
`--colab-auth {oauth2,adc}`    | `colab` default (`oauth2`)                             | Authentication mode passed before the `colab` subcommand (`colab --auth <mode> <subcommand> ...`).
`--colab-auth-code CODE`       | `None`                                                 | Exchanges a one-time OAuth authorization code (from the URL printed by a previous `--colab` run) and saves `~/.config/colab-cli/token.json` so the user never has to run a terminal command.
`--colab-bin PATH`             | `$LITERT_GOOGLE_TENSOR_COLAB_BIN` or `colab` on `PATH` | Path to the `google-colab-cli` executable (also checks `~/.venvs/colab-cli/bin/colab` and `~/.local/bin/colab`).

How `compile_model.py --colab` works:

1.  **Local pre-flight before allocating a VM:** validates the input `.tflite`
    (refuses an already-compiled model with exit 3), checks output collision
    (exit 2 unless `--overwrite`), locates `colab` on `PATH`, and verifies that
    `--sdk-tarball` or `--sdk-url` is available before calling `colab new`.
2.  **Session check & probe:** runs `colab sessions` (read-only API call) to
    verify authentication and check if `--colab-session` is already active. On a
    reused session, probes whether `ai-edge-litert` and
    `ai-edge-litert-sdk-google-tensor` (at `versions.json`'s `pip_release`) and
    `liblitert_plugin_compiler.so` are already present; if so, skips uploading
    the Beta tarball and skips `pip install`.
3.  **Remote install & subprocess compile:** checks `ctypes.CDLL("libc++.so.1")`
    on the Colab VM (installing `libc++1 libc++abi1` via `apt-get` if missing,
    matching the public Colab tutorial), runs `pip install --no-cache-dir` with
    `GOOGLE_TENSOR_SDK_BETA` set, and invokes the uploaded `compile_model.py` in
    a **fresh child Python subprocess** (so newly installed C extensions and
    shared libraries load cleanly without needing `colab restart-kernel`).
4.  **Download & verification:** downloads `<output>.tflite` and
    `<output>.compile.json`, verifies the `LiteRtStamp` and `output_sha256`,
    stamps `"compiled_via": "colab"`, `"colab_session"`, and `"local_host"` into
    the sidecar, and stops the Colab VM in a `finally:` block (including on
    Ctrl-C / `SIGINT` / `SIGTERM`) whenever the script created the session and
    `--keep-colab-session` was not set.

## Interpreting the compilation report

`compilation_report()` prints, per backend, the partition statistics: how many
subgraphs/ops were offloaded to the TPU and which ops stayed on the CPU. A
model is only useful for the strict NPU benchmark (`--require_full_delegation`)
when **all** ops were offloaded; otherwise either fix the model (static shapes,
supported ops) or run `benchmark_on_device.py --allow-cpu-fallback`, accepting
that the reported latency then mixes NPU and CPU time.
