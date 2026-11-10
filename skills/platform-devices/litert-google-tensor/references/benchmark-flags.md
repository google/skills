# On-device benchmarking reference

`scripts/benchmark_on_device.py` drives LiteRT's `benchmark_model` tool
(public docs: https://developers.google.com/edge/litert/next/benchmark) over
adb. This page lists the exact flags it uses, what the tool prints, and where
the two binary dependencies come from.

## Contents

- [What the script does](#what-the-script-does): Lines 28-80
- [Files pushed to the phone](#files-pushed-to-the-phone): Lines 82-174
  - [The public binaries bucket](#the-public-binaries-bucket): Lines 111-136
  - [Other ways to get `libLiteRtDispatch_GoogleTensor.so`](#other-ways-to-get-liblitertdispatch_googletensorso): Lines 138-156
  - [Choosing binary versions](#choosing-binary-versions): Lines 158-174
- [Flags used](#flags-used): Lines 176-216
  - [NPU run (strict, the default)](#npu-run-strict-the-default): Lines 178-205
  - [CPU baseline run (`--cpu-baseline <original.tflite>`)](#cpu-baseline-run---cpu-baseline-originaltflite): Lines 207-216
- [TPU tile time](#tpu-tile-time): Lines 218-294
- [TPU energy](#tpu-energy): Lines 296-346
- [Output format parsed by the script](#output-format-parsed-by-the-script): Lines 348-440
  - [Log lines that are expected (benign)](#log-lines-that-are-expected-benign): Lines 396-421
  - [Profiler summary vs. the table](#profiler-summary-vs-the-table): Lines 423-440
- [Writing the report](#writing-the-report): Lines 442-510
- [Example script output (one real run; never reuse these numbers)](#example-script-output-one-real-run-never-reuse-these-numbers): Lines 512-691
  - [Example with TPU tile time and energy (real run; never reuse the numbers)](#example-with-tpu-tile-time-and-energy-real-run-never-reuse-the-numbers): Lines 641-691
- [Accuracy notes](#accuracy-notes): Lines 693-699

## What the script does

In order:

1.  Selects the device, reads `ro.soc.model`, and refuses to run a model
    compiled for another SoC (exit 4, before anything is downloaded or pushed;
    `--allow-mismatch` overrides). `--dry-run` skips this - it never contacts
    the device - so a dry run proves nothing about the SoC match.
2.  Resolves `benchmark_model` and `libLiteRtDispatch_GoogleTensor.so` (local
    copies, else one-time downloads from the public bucket, cached; sources,
    cache and provenance records: "Files pushed to the phone" below) and prints
    where each came from. `downloaded from <url>` means this was the first
    time - tell the user what was fetched; `fetch date not recorded` marks a
    copy cached by an older version of the script (`--refresh-binary`
    re-downloads it and records the fetch).
3.  Pushes them with the model to a fresh
    `/data/local/tmp/litert_benchmark/run-<timestamp>-<pid>/` (`--device-dir`
    changes the base). Files already on the phone are never overwritten or
    deleted. Leftovers from an interrupted run are therefore always
    `<base>/run-*`: if the user asks to clean up, `adb shell ls -la <base>`
    first and remove only `run-*` entries (never the base or anything else in
    it).
4.  Reads the thermal status (`dumpsys thermalservice`), then runs the NPU
    benchmark in strict mode (flags under "Flags used" below), retrying once
    without the profiler if that run fails.
5.  Runs the same NPU benchmark once more, without profiler and memory monitor,
    with `LITERT_VENDOR_HOOK_ARGS` pointing at a hook config in the run
    directory that enables the TPU tile-time and power metrics, and divides the
    hooks' totals (`Total TPU tile time`, `Total Energy`) by that pass's own
    warmup + measured runs. The hooks' own counts are only checks: older
    dispatch libraries count every inference 1 + D times (D = dispatch nodes, so
    2x for a normal compiled model), which is why the hooks' `Average` lines are
    never used; an old power hook is not used at all (the script checks the
    library first). Checks and evidence: "TPU tile time" and "TPU energy"
    below.
6.  Optionally runs the CPU baseline on the **uncompiled** model
    (`--use_cpu=true`, same run counts).
7.  Prints the Markdown header + table, writes `results.json`, `report.md` (the
    same block as a file), `npu.log`, `tile_time.log` (the hooked pass, + the
    hooks' `tile_time_report.txt` and `power_report.txt`), `cpu.log`,
    `npu_profile.txt`, `cpu_profile.txt`, and deletes the per-run device
    directory (even on failure). `--output-dir` is only created once a benchmark
    actually ran - after exit 2/3/4 or `--dry-run` there are no logs to look
    for.

Useful options (all in `--help`): `--num-runs`, `--warmup-runs`, `--signature`,
`--performance-mode
{extreme_power_saver,power_saver,balanced,high_performance,sustained_performance,burst}`
(benchmark default `burst`), `--cpu-num-threads`, `--extra-arg=--min_secs=5`
(extra `benchmark_model` flags; they cannot switch the accelerator),
`--device-dir`, `--benchmark-bin` + `--dispatch-lib` (local copies, offline),
`--serial`, `--allow-cpu-fallback`, `--keep-device-files`, `--refresh-binary`,
`--no-tile-time`, `--no-power`, `--dry-run`.

## Files pushed to the phone

Everything goes to a fresh per-run directory
`/data/local/tmp/litert_benchmark/run-<timestamp>-<pid>/` (base overridable
with `--device-dir`) and only that directory is deleted afterwards (unless
`--keep-device-files`). Files that were already in the base directory - e.g.
your own `benchmark_model` or models from earlier manual runs - are never
overwritten or removed; the base directory itself is removed only if the run
created it.

File                                | Purpose                                                                                                                                     | Source
----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ------
`benchmark_model`                   | android_arm64 LiteRT benchmark binary                                                                                                       | `--benchmark-bin`, else downloaded once from `--benchmark-url` (default `https://storage.googleapis.com/litert/binaries/<release>/android_arm64/benchmark_model`, `<release>` = `binaries_release` in `versions.json`; `--help` prints the resolved URL).
`libLiteRtDispatch_GoogleTensor.so` | Google Tensor dispatch (NPU runtime) library loaded through `--dispatch_library_path`                                                       | `--dispatch-lib`, else `$LITERT_GOOGLE_TENSOR_DISPATCH_LIB`, else downloaded once from `--dispatch-url` (default: `libLiteRtDispatch_GoogleTensor.so` in the same directory as `--benchmark-url`).
`<model>.tflite`                    | the compiled model (and the uncompiled one for `--cpu-baseline`)                                                                            | user
`tpu_hooks.textproto`               | config of the hooked pass (TPU tile-time and power metrics); the hooks write their reports to `tpu_tile.txt` and `tpu_power.txt` next to it | written by the script (not with both `--no-tile-time` and `--no-power`)

Downloads are cached in `~/.cache/litert-google-tensor/` (override with
`LITERT_GOOGLE_TENSOR_CACHE`; `--refresh-binary` re-downloads) under the name
`<release>_android_arm64_<file>`, `<release>` being the bucket directory the
file came from (e.g. `latest_android_arm64_benchmark_model` for a
`--benchmark-url` under `binaries/latest/`). Next to each
download, `<file>.json` records the URL, the UTC fetch time, size, SHA-256 and
the bucket's `x-goog-generation` / md5 / crc32c response headers; the
provenance lines show the fetch time and md5 from it. A cached copy of a
rolling release stays the build that was first downloaded, and that md5 is
what identifies it. The dispatch library links against the TPU driver that
ships on the Pixel itself, so nothing else needs to be pushed.

### The public binaries bucket

`https://storage.googleapis.com/litert/binaries/<release>/android_arm64/` holds
prebuilt LiteRT tools and runtime libraries built together from one release, so
`<release>` is the unit of versioning. The skill's default release is
`binaries_release` in `versions.json`. Known contents (bucket listing checked
2026-10-26):

`<release>`                           | `benchmark_model` | `libLiteRtDispatch_GoogleTensor.so`
------------------------------------- | ----------------- | -----------------------------------
`latest`, `nightly`, `2.3.0`, `2.3.1` | yes               | yes
`2.1.6`, `2.2.0`                      | yes               | **no** - the download 404s; supply `--dispatch-lib`

`latest/` is not a copy of the newest numbered directory: on 2026-10-07 its
`benchmark_model` and dispatch library had different sizes and md5s than
`2.3.0/`'s. The directory listing (with each object's `md5Hash`) is public:
`https://storage.googleapis.com/storage/v1/b/litert/o?prefix=binaries/latest/android_arm64/`.

A numbered directory can be re-uploaded too. `2.3.1/` was first uploaded on
2026-10-20 with a dispatch library byte-identical to `2.3.0/`'s (md5
`VuNepRvYbhpk4UjeRM2JvA==`, still with the double-counting hook described under
"TPU tile time"), then replaced on 2026-10-23 17:54 UTC by a rebuild with the
hook fix (md5 `tp26wryZhjaU3IYIz2w7/g==`; its `benchmark_model` was rebuilt too,
with only the build stamp changed). A cache filled before a re-upload keeps the
old build under the same file name: when a provenance line's md5 differs from
`verified.binaries` in `versions.json`, rerun with `--refresh-binary`.

### Other ways to get `libLiteRtDispatch_GoogleTensor.so`

1. **GitHub release assets** - `litert_npu_runtime_libraries.zip` under
   https://github.com/google-ai-edge/LiteRT/releases. `--dispatch-lib` accepts
   the `.zip` (or an `.aar`, which is also a zip) and extracts the `.so`,
   preferring an `arm64-v8a`/`arm64` entry when several exist.
2. **Build from source** - follow "How do I build a Google Tensor dispatch
   library?" in https://developers.google.com/edge/tensor-sdk/tensor-faqs
   (Bazel target `litert/vendors/google_tensor/dispatch:dispatch_api.so`).

Whatever the source, prefer the dispatch library and `benchmark_model` from the
same LiteRT release (the default does this). Nearby releases do interoperate
(`latest` binary + `2.3.0` library and the reverse both ran fine on a Pixel 10);
a far-apart pair is the first thing to suspect if the run dies right after the
`Loading shared library: .../libLiteRtDispatch_GoogleTensor.so` line. Compiler
and runtime releases can differ too: a model compiled with ai-edge-litert 2.1.6
ran fully delegated on the `2.3.0` binaries (Pixel 10, 2026-10-07) and on the
`2.3.1` binaries (2026-10-26); the report's **Versions** line shows which pair a
run used.

### Choosing binary versions

Keep `benchmark_model` and the dispatch library from the **same** release
directory of the bucket (the default does: both come from `binaries_release` in
`versions.json`); pass
`--benchmark-url .../binaries/<release>/android_arm64/benchmark_model` to pin
another one and the dispatch URL follows. A rolling directory (`latest/`,
`nightly/`) changes over time, but a cached copy stays the build that was first
downloaded until `--refresh-binary`; the md5 in its provenance line tells builds
apart. A numbered directory can be re-uploaded as well (bucket notes above): if
a provenance md5 differs from `verified.binaries` in `versions.json`, rerun with
`--refresh-binary`. Local files carry no version string the script could
compare, so for `--benchmark-bin`/`--dispatch-lib` the rule is "both from the
same download"; if that is uncertain, re-download both from one directory. Not
every versioned directory ships the Google Tensor dispatch library (which ones
do: the bucket table above) - if the download 404s, use the default URLs or
supply `--dispatch-lib` from one of the other sources above.

## Flags used

### NPU run (strict, the default)

```text
benchmark_model --graph=<model> --use_npu=true --use_cpu=false
                --require_full_delegation=true
                --dispatch_library_path=/data/local/tmp/litert_benchmark/run-<id>
                --num_runs=50 --warmup_runs=5
                --report_peak_memory_footprint=true --use_profiler=true
                [--signature_to_run_for=<key>]
                [--google_tensor_performance_mode=<mode>]
```

| Flag | Default in tool | Why the skill sets it |
|---|---|---|
| `--use_npu` | `false` | Select the NPU accelerator. |
| `--use_cpu` | `true` | Must be `false` together with `--require_full_delegation=true`; the tool aborts with "Requesting full delegation and CPU acceleration are incompatible" otherwise. |
| `--require_full_delegation` | `false` | Fail instead of silently timing CPU fallback ops. `--allow-cpu-fallback` removes this pair. |
| `--dispatch_library_path` | `""` | Directory containing `libLiteRtDispatch_GoogleTensor.so`. |
| `--num_runs` / `--warmup_runs` | `50` / `1` | Skill uses 50 / 5 (`--num-runs`, `--warmup-runs`). These are **minimums**: the tool also runs for at least `--min_secs` (default 1.0 s) and warms up for at least `--warmup_min_secs` (default 0.5 s), so a fast model reports more runs than requested (e.g. a 15 ms model: 65 measured / 31 warmup). The "Runs" row shows the actual counts. For exact counts add `--extra-arg=--min_secs=0 --extra-arg=--warmup_min_secs=0`. |
| `--report_peak_memory_footprint` | `false` | Adds "Peak memory" to the results (`--no-peak-memory` to disable). |
| `--use_profiler` | `false` | Enables runtime profiling; the summary is saved to `npu_profile.txt`. For a fully delegated model it shows one `DELEGATE` node, not TPU-internal ops. If the profiled run fails the script retries once without it. |
| `--google_tensor_performance_mode` | `burst` (set by the tool when `--use_npu`) | `--performance-mode` one of `extreme_power_saver`, `power_saver`, `balanced`, `high_performance`, `sustained_performance`, `burst`. |
| `--signature_to_run_for` | `""` | Multi-signature models (`--signature`). |

Other upstream `benchmark_model` flags (`--min_secs`, `--max_secs` (default 150
s), `--warmup_min_secs`, `--input_layer_value_range`, ...) can be appended with
`--extra-arg=--flag=value` (NPU run and hooked pass; the CPU baseline keeps the
defaults so the two columns stay comparable).

### CPU baseline run (`--cpu-baseline <original.tflite>`)

```text
benchmark_model --graph=<original> --use_cpu=true --num_runs=50 --warmup_runs=5
                --report_peak_memory_footprint=true --use_profiler=true
                [--num_threads=N]
```

The baseline must be the **uncompiled** model: a compiled model's TPU
partitions are `DISPATCH_OP` custom ops that the CPU cannot execute.

## TPU tile time

On by default (`--no-tile-time` skips it) and never fails the job: a problem
shows up in the header line as `unavailable`, `failed`, `no report` or
`inconsistent` with the reason, the table row shows `-`, and the latency numbers
are unaffected.

After the NPU run the script runs `benchmark_model` once more with the NPU flags
minus `--use_profiler=true` and `--report_peak_memory_footprint=true`, prefixed
with `LITERT_VENDOR_HOOK_ARGS=<run dir>/tpu_hooks.textproto`. This hooked pass
also measures the TPU energy (next section); its config holds one block per
metric (`--no-tile-time` or `--no-power` drops one, both together skip the
pass):

```text
tpu_tile_time_metrics_config {
  dump_tpu_tile_time_metrics: true
  tpu_tile_time_metrics_dump_path: "<run dir>/tpu_tile.txt"
}
power_config {
  dump_power_metrics: true
  power_dump_path: "<run dir>/tpu_power.txt"
}
```

`libLiteRtDispatch_GoogleTensor.so` adds up `hardware_execution_time_us` (pure
TPU execution time) of every dispatch invoke and, when the model is torn down,
writes a report (saved as `tile_time_report.txt`; the same block is logged at
INFO level, which the script uses if the file is missing). The `2.3.1` library
(re-upload of 2026-10-23) wrote this one in the run of the example below:

```text
==== Google Tensor TPU Tile Time Metrics ====
Total inferences: 66
Total TPU tile time (us): 1169131
Average TPU tile time (us): 17714.11
Min TPU tile time (us): 17466
Median TPU tile time (us): 17698.00
P95 TPU tile time (us): 17865
==================================
```

Older libraries (`2.3.0`, and `2.3.1` as first uploaded on 2026-10-20) write
only the first three numbers, and their `Total inferences` and `Average` are
wrong: each inference reaches the hook 1 + D times (once from the LiteRT
runtime's `Run`, once per dispatch invoke; D from
`Replacing D out of M node(s)`), but only the dispatch calls add tile time. For
the same model, the `2.3.0` library reported `Total inferences: 144` and
`Average TPU tile time (us): 8844` for 72 runs (2026-10-09), half the real
17.689 ms. With either kind of library the script reports
`Total TPU tile time / (warmup + measured runs of this pass)` (above: 1169131 us
/ 66 runs = 17.714 ms), uses the hook's count only as a check, and does not copy
the `Min`/`Median`/`P95` lines into the report:

`Total inferences` / runs             | Meaning                                                                                                                     | Result
------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- | ------
D (1 for a normal compiled model)     | one call per dispatch invoke (`2.3.1` re-upload, observed 2026-10-26; `nightly`, 2026-10-23; Maven `2.3.2` AAR, 2026-10-27) | per inference = total / runs
1 + D (2 for a normal compiled model) | the double count (`2.3.0` binaries, observed 2026-10-09; first `2.3.1` upload, 2026-10-23; Maven `2.3.0` AAR, 2026-10-26)   | same
1                                     | the hook counts runs                                                                                                        | same
anything else                         | unexplained, e.g. a multi-signature model whose first `Replacing` line belongs to another subgraph                          | `inconsistent`: totals only

-   The pass's own latency is not reported: the hook adds about 3% per inference
    (+0.77 ms on a 23.7 ms model, mean of 3 interleaved pairs, Pixel 10,
    2026-10-09). Its run counts can differ from the NPU run's (time floors), so
    the tile time uses its own pass's counts.
-   `tile_time.log` status lines:
    `Successfully retrieved and registered vendor hooks in CompiledModel.` =
    hook active; `Accelerator returned null hooks.` = the dispatch library has
    no hooks. Builds from the LiteRT GitHub source compile them out; the
    Google-built bucket libraries have them (checked for `2.3.0` and `latest` on
    2026-10-09, `2.3.1` on 2026-10-26), and so do the libraries in the Maven
    `litert-npu-runtime-google-tensor` AARs (`2.3.0` on 2026-10-14, `2.3.2` on
    2026-10-27).
-   The hook parses its config by substring after stripping all whitespace: only
    lowercase `true` enables a metric, a commented-out key still counts, and the
    dump paths cannot contain whitespace (the script refuses such a
    `--device-dir`).

## TPU energy

On by default (`--no-power` skips it) and, like the tile time, never fails the
job. The `power_config` block above turns on the dispatch library's power metric
in the same hooked pass: the energy counter of the TPU rail in the phone's
on-device power monitor. The fixed hook (the `2.3.1` library as re-uploaded on
2026-10-23, and the library in the Maven `2.3.2` AAR) reads that counter when
the first dispatch invoke starts and again when the model is torn down, counts
dispatch invokes, and writes this report (saved as `power_report.txt`; the same
numbers are logged at INFO level, which the script uses if the file is missing),
from the run of the example below:

```text
Average TPU Energy consumed per inference(uJ): 21279.485
Total Energy (uJ): 1404446
Inference count: 66
```

The script reports `Total Energy / (warmup + measured runs of the pass)` as
**TPU energy / inference (mJ)** (here 1404446 uJ / 66 runs = 21.279 mJ) and uses
the hook's count only as a check. The total spans the whole pass, so the value
includes the TPU's energy in the idle gaps of the benchmark loop and at
teardown: it is the energy per inference of back-to-back inference, for
comparing models, builds and performance modes on the same phone, not a lab
measurement of one isolated inference. It is measured with the tile-time metric
on; `--no-tile-time` gives a power-only pass (21.474 vs 22.076 mJ for the
example model in two single runs, 2026-10-26).

`Inference count` / runs              | Meaning                                                                                              | Result
------------------------------------- | ---------------------------------------------------------------------------------------------------- | ------
D (1 for a normal compiled model)     | one call per dispatch invoke (`2.3.1` re-upload, observed 2026-10-26; Maven `2.3.2` AAR, 2026-10-27) | per inference = total / runs
1 + D (2 for a normal compiled model) | the old power hook (`2.3.0` and the first `2.3.1` upload, observed 2026-10-23)                       | `unreliable`: no value
anything else                         | unexplained                                                                                          | `inconsistent`: totals only

-   The old power hook reads the counter around every call. With the example
    model that slowed inference from about 24 ms to 102.54 ms, and its per-call
    windows caught 56,700 uJ for 56 runs, where the fixed hook's 21.7 mJ per
    inference would make about 1.2 million (2026-10-23). The script therefore
    checks the dispatch library before the pass: if it contains the old hook's
    log string `failed HandlePowerRuntimeStop`, the power metric stays off and
    the header says `unavailable` (the Maven `litert-npu-runtime-google-tensor`
    2.3.0 AAR has the old hook, checked 2026-10-26; the 2.3.2 AAR has the fixed
    one, 2026-10-27). The count check catches an old hook the string check
    misses (`unreliable`).
-   `unavailable - the power hook could not read the TPU energy counter:
    '<line>'` quotes the hook's own log line
    (`Google TensorHook failed HandlePowerRuntimeStart: ...` or
    `Skipping power metrics dump ...`): the phone did not let the shell process
    read its power monitor. Latency and tile time are unaffected.
-   With the fixed hook the power metric adds no per-inference work (it only
    counts), so it does not slow the pass.

## Output format parsed by the script

Recent LiteRT binaries print a results block like this one (verbatim from an
earlier Pixel 10 run; the `2.3.0` and `2.3.1` binaries print the same format,
checked 2026-10-07 and 2026-10-26; the parser strips the `INFO: [file:line]`
prefixes):

```text
INFO: Running benchmark for at least 5 iterations and at least 0.5 seconds but terminate if exceeding 150 seconds.
INFO: count=31 first=14065 curr=17133 min=11374 max=17700 avg=15934.7 std=1771 p5=11961 median=16478 p95=17661

INFO: Running benchmark for at least 50 iterations and at least 1 seconds but terminate if exceeding 150 seconds.
INFO: count=65 first=16308 curr=17045 min=10667 max=17784 avg=15125.2 std=2501 p5=11016 median=16621 p95=17564

INFO: [benchmark_litert_model.h:89]
========== BENCHMARK RESULTS ==========
INFO: [benchmark_litert_model.h:92] Signature name:       <placeholder signature>
INFO: [benchmark_litert_model.h:94] Model initialization: 502.36 ms
INFO: [benchmark_litert_model.h:96] Warmup (first):       14.06 ms
INFO: [benchmark_litert_model.h:98] Warmup (avg):         15.93 ms (31 runs)
INFO: [benchmark_litert_model.h:100] Inference (avg):      15.13 ms (65 runs)
INFO: [benchmark_litert_model.h:104] Inference (min):      10.67 ms
INFO: [benchmark_litert_model.h:106] Inference (max):      17.78 ms
INFO: [benchmark_litert_model.h:108] Inference (std):      2.50
INFO: [benchmark_litert_model.h:115] Throughput:           49.59 MB/s
INFO: [benchmark_litert_model.h:124]
Memory Usage:
INFO: [benchmark_litert_model.h:126] Init footprint:       80.24 MB
INFO: [benchmark_litert_model.h:128] Overall footprint:    80.99 MB
INFO: [benchmark_litert_model.h:132] Peak memory:          124.37 MB
INFO: [benchmark_litert_model.h:138] ======================================
<profiler summary when --use_profiler=true: one DELEGATE node for a fully compiled model>
```

The two `Running benchmark for at least ...` lines show the time floors
(`--warmup_min_secs`, `--min_secs`) that made this 15 ms model run 31 / 65
times instead of the requested 5 / 50. Each is followed by a per-phase stats
line in **microseconds** (`count=... min= max= avg= std= p5= median= p95=`);
the first is the warmup phase, the second (its `count=` equals the measured
run count) is the measured phase, and it is the only place percentiles
appear. The script converts its `p5`/`median`/`p95` to ms for the
`Inference p5 / p50 / p95 (ms)` table row and `results.json`
(`inference_p5_ms`, `inference_p50_ms`, `inference_p95_ms`). Earlier in the
log, `Replacing 1 out of 1 node(s) with delegate (DispatchDelegate)` confirms
full delegation (the script copies it into the `Delegation (runtime)` header
line), and `Loading shared library: .../libLiteRtDispatch_GoogleTensor.so`
confirms which dispatch library was used.

### Log lines that are expected (benign)

Seen in every successful strict run on a Pixel 10; do not report them as
problems:

Line                                                                                                                                                                                                                                                                                                                                | Meaning
----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------
`WARNING: [compiled_model.cc:815] Compiler plugin path is provided in the environment, but the model is pre-compiled. Plugins won't be applied.`                                                                                                                                                                                    | Normal for an AOT-compiled model: there is nothing left to compile on device.
`WARNING: [dispatch_delegate_kernel.cc:793] MediaTek dispatch API returned contradictory buffer requirements for Float32 tensor ...: expected size=8 bytes / But dispatch API returned: 64 bytes`                                                                                                                                   | Buffer-size padding reported by shared dispatch-delegate code; the "MediaTek" wording is a mislabel on Google Tensor. Seen with tiny tensors; the run completes and the results are valid.
`INFO: [litert_dispatch.cc:186] Loading shared library: .../libLiteRtDispatch_GoogleTensor.so`, `SouthBound context created.`, `SouthBound symbols resolved by 'libedgetpu_litert.so'`, `Found GoogleTensorOptions`                                                                                                                 | The Google Tensor dispatch library loaded and bound to the on-device TPU driver.
`VERBOSE: Replacing N out of N node(s) with delegate (DispatchDelegate) node, yielding 1 partitions ...`                                                                                                                                                                                                                            | Full delegation. `N out of M` with N < M would mean CPU fallback (strict mode then fails).
`INFO: [compiled_model.cc:1065] Accelerator returned null hooks.`                                                                                                                                                                                                                                                                   | Informational in `npu.log` / `cpu.log` (no hook configured there). In `tile_time.log` it means the dispatch library has no telemetry hooks, and TPU tile time is `unavailable`.
`INFO: [compiled_model.cc:1056] Successfully retrieved and registered vendor hooks in CompiledModel.`, the `==== Google Tensor TPU Tile Time Metrics ====` block, `Google TensorHook: TPU metrics dumped to ...`, `Power hook has generated following data:` with its three lines, `Google TensorHook: Power metrics dumped to ...` | `tile_time.log` only: the hooks are active and wrote their reports (INFO level, so the Log check does not count them).

A line that is **not** benign: the run ending right after `Loading shared
library:` with no `Replacing ...` line (unusable dispatch library), or
`Failed to invoke SB invocation context` / `Node number 1 (DELEGATE) failed to
invoke` (model compiled for another SoC, see `troubleshooting.md`).

`benchmark_on_device.py` applies this list itself: the two WARNING patterns
above are counted as `known-benign` in the report's **Log check** line, and
every other WARNING/ERROR-level line (including the abseil-style `E0000 ...`
lines of the TPU driver) is listed verbatim under **Unexpected log lines**
(see the example output below). Treat a non-zero unexpected count as
something to explain in the report's Notes, not as an automatic failure - the
table values are still real if `benchmark_model` exited 0.

### Profiler summary vs. the table

With `--use_profiler=true` the log ends with a per-op table containing a
single `DELEGATE` row for a fully compiled model. Its `[avg ms]` covers only
the delegate invoke and is lower than the table's `Inference (avg)`, which
also includes input/output buffer handling. Report the table value; the
profile is saved to `npu_profile.txt` for reference only.

Older binaries print the upstream TFLite one-liner instead
(`Inference timings in us: Init: ..., First inference: ..., Warmup (avg): ...,
Inference (avg): ...` and `Overall peak memory footprint (MB) via periodic
monitoring: ...`); the parser understands both. Raw logs are always kept in the
output directory (`npu.log`, `cpu.log`). A binary that exits 0 but prints
neither format (and none of the crash markers such as `Benchmarking failed`)
stops the script with exit 6 `... printed no results in the format this
script parses`, naming the binary and keeping the log; the profiler retry is
skipped because it cannot help. Updating the parser for a new format is part
of `contributing.md`.

## Writing the report

SKILL.md step 4 has the Summary / Notes template around the script's block.
Nothing in that block is typed by hand; each field comes from the device or
the run:

Report field                                | Comes from
------------------------------------------- | ----------
Device name, SoC, Android version           | `ro.product.model`, `ro.soc.model`, `ro.build.version.release` on the attached phone (a Pixel 11 reports itself as Pixel 11 / Tensor G6)
Model name, size, compiled-for SoC          | the `.tflite` file and its `LiteRtStamp`
**Compile** (flags, ops offloaded / total)  | the `<model>.compile.json` sidecar next to the model; `unknown` when the model was compiled elsewhere - never fill it in from memory
**Versions**                                | the sidecar's `ai-edge-litert` version (the LiteRT that compiled the model) vs the bucket release in the binaries' URLs (`user-provided` for local files): `same release`, `DIFFERENT releases`, or why the two cannot be compared (no sidecar, a rolling `latest`/`nightly` build, local files, binaries from two sources); also stored as `versions` in `results.json`
**Delegation (runtime)**                    | the `Replacing N out of M node(s) with delegate (DispatchDelegate)` line of this run's `npu.log` - the ground truth that everything ran on the TPU
Mode, requested run counts, NPU flags       | the flags actually passed to `benchmark_model`
**Thermal before NPU run**                  | `dumpsys thermalservice`: the throttling status (0 = none) is the signal; the sensor value is one reading, informational only
**TPU tile time** (header line + table row) | the tile-time pass: the hook's `Total TPU tile time` ÷ that pass's warmup + measured runs. The header names the hook's call count and what it means (`1 call per run, one per dispatch invoke`, or `2 calls per run (... the known double count, corrected)` with older dispatch libraries); `unavailable`, `failed`, `no report` or `inconsistent` (count matches no known pattern: totals only) carry the reason instead
**TPU energy** (header line + table row)    | the same hooked pass: the power hook's `Total Energy` (the TPU rail from the first inference to the model's teardown, idle gaps included) ÷ that pass's warmup + measured runs, in mJ. The header names the hook's call count (`1 call per run, one per dispatch invoke`); `unavailable` (an old power hook, which the script does not enable, or a phone that refused the energy counter), `failed`, `no report`, `unreliable` (old hook's count pattern) or `inconsistent` carry the reason instead
Binary / dispatch library provenance        | the resolver (`downloaded from <url>`, `cached download of <url>`, `user-provided: <path>`); downloads end with `(fetched <UTC time>, md5 <hash>)` recorded at download time, which identifies the build of a rolling release
All timings, memory, actual run counts      | parsed from the `BENCHMARK RESULTS` block of this run's log
**Inference p5 / p50 / p95 (ms)**           | the measured-phase `count=N ... p5= median= p95=` stats line of the log (microseconds, converted to ms by the script); these are the only percentiles `benchmark_model` produces - there is no p99
**Log check**                               | the script's scan of `npu.log` / `cpu.log` / `tile_time.log`: WARNING/ERROR-level lines that match the benign list above ("Log lines that are expected") are only counted (`N known-benign`); any other such line is listed verbatim under **Unexpected log lines** after the table (de-duplicated, with a repeat count), and the line also says whether the profiler retry happened. No grepping of the logs is needed.

Without a CPU baseline the Summary line is just `**Summary:** <NPU "Inference
avg"> ms per inference on the TPU (<strict NPU | CPU fallback allowed>, no CPU
comparison requested); peak memory <NPU> MB.` plus the same TPU tile time and
TPU energy sentences. Drop each of those two sentences when its header line says
`not measured`, `unavailable`, `failed`, `no report`, `unreliable` or
`inconsistent`, and give the header's reason in the Notes.

Combined compile + benchmark job: present only the benchmark block (its
**Compile** header line already carries the sidecar's flags and op counts)
and start the Notes with one line of compile context - that the input was
uncompiled and was compiled first, the output path, and that nothing existing
was overwritten (`compile_model.py` made sure of that). The SKILL.md step 2b
compile-only block is for jobs that end at the compile.

What to say in the Summary and Notes:

-   Report the **actual** run counts from the table: `benchmark_model` treats
    `--num_runs`/`--warmup_runs` as minimums and also runs for at least 1 s /
    0.5 s, so fast models show more runs than requested ("Flags used" above;
    the example output below is from a real run).
-   The **Mode** line says whether the run was strict NPU or allowed CPU
    fallback; call that out in prose as well, because fallback numbers mix NPU
    and CPU time.
-   The **Versions** line compares the LiteRT that compiled the model with the
    release that ran it. Mention `DIFFERENT releases`, a
    `but SDK package X (DIFFERENT)` or binaries from two sources in the Notes -
    numbers from such a mix are harder to compare with other runs - unless the
    line ends with `(the pair verified in versions.json)`.
    `not comparable (...)` and `cannot compare` need no comment beyond the line.
-   A speed-up below 1x is a real result, not a setup error, for tiny models
    (per-inference NPU dispatch overhead of a few ms dominates); say so instead
    of hunting for thermal or configuration problems.
-   The per-op profile (`npu_profile.txt`) shows one `DELEGATE` node whose
    average is lower than the table's `Inference avg` (it excludes input/output
    handling); report the table value, not the profile value.
-   **TPU tile time** is pure TPU hardware time, so it is below `Inference avg`
    (which adds host and driver work). Quote it from the table only, never from
    the hook's own lines in `tile_time.log` / `tile_time_report.txt`: older
    dispatch libraries inflate its `Total inferences`, so their `Average` is too
    low (half for a normal compiled model), while the table value is right with
    every library.
-   **TPU energy** is the TPU rail's energy (the phone's on-device power
    monitor) for the whole hooked pass divided by its runs, so it includes the
    TPU's idle gaps between back-to-back inferences: compare it between models,
    builds and `--performance-mode`s on the same phone, and do not present it as
    a lab power measurement or as the energy of one isolated inference. Quote it
    from the table only.

## Example script output (one real run; never reuse these numbers)

Everything below was printed by `benchmark_on_device.py` for a Pixel 10 with
the public `selfie_multiclass_256x256` model compiled by `compile_model.py`
(so the `.compile.json` sidecar existed); each field is read from the device,
the sidecar or the run, so on a Pixel 11 the first line reads `Pixel 11 ...
SoC Tensor G6` without any change to the skill. Expect every number to differ
between runs (the same phone gave 14.10, 14.48, 15.13, 15.38, 16.10 and
16.25 ms avg in different runs). Without a sidecar the `Compile` line reads
`unknown - no <model>.compile.json next to the model (compiled elsewhere); see
Delegation below`.

**Example only** - values from one past run on one phone; they are never
reused. Your run prints its own.

```markdown
**Device:** Pixel 10 (serial localhost:41015), SoC Tensor G5, Android 17
**Model:** selfie_multiclass_256x256_Google_Tensor_G5.tflite (8,110,864 bytes (8.1 MB), compiled for Tensor_G5)
**Compile:** --target Tensor_G5; 175 / 175 ops offloaded (from selfie_multiclass_256x256_Google_Tensor_G5.tflite.compile.json)
**Versions:** compiled with ai-edge-litert 2.1.6; runtime binaries from bucket release '2.3.0' - DIFFERENT releases (the pair verified in versions.json)
**Delegation (runtime):** 1 of 1 node(s) replaced by DispatchDelegate at run time
**Mode:** strict NPU (--use_cpu=false --require_full_delegation=true); requested 5 warmup / 50 measured runs (actual counts in the table)
**Thermal before NPU run:** throttling status 0 (none); TPU sensor 45.0 C (single reading, informational)
**Benchmark binary:** downloaded from https://storage.googleapis.com/litert/binaries/2.3.0/android_arm64/benchmark_model (fetched 2026-10-07 07:22:39 UTC, md5 i+CfsHfR9Ao6uje4HUySvg==)
**Dispatch library:** downloaded from https://storage.googleapis.com/litert/binaries/2.3.0/android_arm64/libLiteRtDispatch_GoogleTensor.so (fetched 2026-10-07 07:22:37 UTC, md5 VuNepRvYbhpk4UjeRM2JvA==)
**NPU flags:** `--graph=/data/local/tmp/litert_benchmark/run-20261007-072235-139177/selfie_multiclass_256x256_Google_Tensor_G5.tflite --use_npu=true --use_cpu=false --require_full_delegation=true --dispatch_library_path=/data/local/tmp/litert_benchmark/run-20261007-072235-139177 --num_runs=50 --warmup_runs=5 --report_peak_memory_footprint=true --use_profiler=true`
**Log check:** npu.log: 0 unexpected WARNING/ERROR lines (1 known-benign); cpu.log: 0 unexpected WARNING/ERROR lines (0 known-benign); profiler retry: none
**Logs:** results/binaries_2.3.0

| Metric | NPU (Tensor_G5) | CPU baseline |
|---|---|---|
| Model file | selfie_multiclass_256x256_Google_Tensor_G5.tflite | selfie_multiclass_256x256.tflite |
| Model init (ms) | 254.38 | 57.33 |
| Warmup first (ms) | 13.13 | 138.93 |
| Warmup avg (ms) | 13.37 | 122.17 |
| Inference avg (ms) | 14.10 | 117.89 |
| Inference min / max (ms) | 8.09 / 31.03 | 115.49 / 118.67 |
| Inference std (ms) | 4.03 | 0.61 |
| Inference p5 / p50 / p95 (ms) | 8.621 / 14.017 / 19.585 | 116.654 / 118.072 / 118.462 |
| Peak memory (MB) | 124.99 | 205.75 |
| Runs (warmup / measured) | 37 / 70 | 5 / 50 |

NPU speed-up vs CPU (avg latency): **8.36x**
```

The percentile row comes from the measured-phase stats line that
`benchmark_model` logs in microseconds (`INFO: count=70 ... p5=8621
median=14017 p95=19585`), converted to ms by the script; p5 / median / p95 are
the only percentiles the tool produces (no p99). The row is omitted when the
log has no such line.

Two header lines in more detail:

* **Versions** (right after **Compile**):
  `<compile part>; <runtime part> - <verdict>`. The compile part is
  `compiled with ai-edge-litert <version from the sidecar's packages>` (plus
  `but SDK package <v> (DIFFERENT)` when the sidecar's SDK package differs),
  `compile version unknown (no compile sidecar)` or
  `compile version not recorded in the sidecar`. The runtime part is
  `runtime binaries from bucket release '<release>'` (from the URLs),
  `... from user-provided files` / `... from a custom URL`, or both binaries
  named separately when they differ. The verdict is `same release`,
  `DIFFERENT releases` (with `(the pair verified in versions.json)` appended
  when that is exactly the pinned pair), `not comparable (<reason>)` for a
  rolling release (`latest`, `nightly`), local files or a URL without a
  release, `cannot compare` without a sidecar version, or
  `the two runtime binaries come from different sources`. In the example,
  2.1.6 and 2.3.0 were the pinned pair at the time (why they differed: "Why
  two release fields" in `contributing.md`), and this run is what verified
  it.
* **Benchmark binary** / **Dispatch library** end with the fetch record:
  `(fetched <UTC time>, md5 <base64 md5 from the bucket>)`, or
  `sha256 <first 16 hex digits>` when the server sent no md5, or
  `(fetch date not recorded; --refresh-binary re-downloads and records it)`
  for files cached before the record existed. `downloaded from` marks the run
  that fetched the file (as in the example); later runs say
  `cached download of`.

The **Log check** line is the script's own scan of the logs (see "Log lines
that are expected" above): `1 known-benign` here is the plugin-path warning
that every AOT-compiled model triggers. When a log contains any other
WARNING/ERROR-level line, the count is non-zero and an **Unexpected log
lines** section follows the table, listing each distinct line verbatim (with
`(xN)` when it repeats, at most 8 shown), e.g. for a model compiled for the
wrong SoC and run with `--allow-mismatch`:

```text
**Unexpected log lines** (not in the benign list of references/benchmark-flags.md; judge them before reporting):
- npu.log: `ERROR: [litert_dispatch_invocation_context.cc:238] Failed to wait for SB invocation context`
- npu.log: `ERROR: Node number 1 (DELEGATE) failed to invoke. (x4301)`
```

`profiler retry: yes - ...` means the first, profiled NPU attempt failed and
the table comes from the retry without `--use_profiler` (first attempt's log:
`npu_profiled_attempt.log`).

When the NPU is slower than the CPU the last line adds `- the CPU was faster
by N.NNx (expected for tiny models: per-inference NPU dispatch overhead
dominates)`; a 568-byte single-`Add` model measured 2.85 ms on the TPU versus
0.08 ms on the CPU, which is overhead, not a configuration problem.

The same text is stored in `results.json` under `"markdown"`, next to the
structured fields (`device`, `thermal_before_npu_run`, `model`, `compile` (the
sidecar contents or `null`), `versions` (`compiled_with`, `runtime_release` of
`benchmark_model` and `dispatch_library`, the `pinned` pair from
`versions.json`, and `match`: `same`, `different`, `unverified`, `unknown` or
`mixed_runtime`), `npu` (including `delegated_nodes` / `total_nodes`), `cpu`,
`tpu_tile_time` (`status` (`ok`, `skipped`, `unavailable`, `failed`,
`no_report`, `inconsistent`), `reason`, `runs`, `warmup_runs`, `measured_runs`,
`dispatch_nodes`, `total_us`, `hook_count`, `count_ratio`, `count_meaning`,
`per_inference_ms`, `source` (`file` or `log`), `hook_registered`,
`pass_inference_avg_ms`, `flags`, `env`), `tpu_energy` (`status` (`ok`,
`skipped`, `unavailable`, `failed`, `no_report`, `unreliable`, `inconsistent`),
`reason`, `runs`, `warmup_runs`, `measured_runs`, `dispatch_nodes`, `total_uj`,
`hook_count`, `count_ratio`, `count_meaning`, `per_inference_mj`, `source`,
`hook_registered`, `flags`, `env`), `benchmark_binary`, `dispatch_library`,
`log_check` (per log: `benign_lines`, `unexpected_total`, `unexpected_lines`;
plus `retried_without_profiler`)), and written as `report.md` in the output
directory. In the printed block, paths under the current working directory are
shown relative to it (run from the project directory, the last line reads
`**Logs:** results/binaries_2.3.0`; paths elsewhere stay absolute);
`results.json` keeps the full paths.

Thermal line: the status (`0 (none)` ... `6 (shutdown)`, from
`dumpsys thermalservice`) is the meaningful part. The TPU sensor reading is
shown when the phone exposes one, but on the Pixel 10 used for these runs it
reported a constant `45.0 C` across hours and workloads, so do not read a
temperature trend into it.

### Example with TPU tile time and energy (real run; never reuse the numbers)

The example above was recorded before the TPU tile time and energy existed. A
current run adds the **TPU tile time** and **TPU energy** header lines and table
rows, and `tile_time.log` in the Log check. Verbatim `report.md` of a Pixel 10
run (2026-10-26, `2.3.1` binaries as re-uploaded on 2026-10-23, a 143 MB
`efficientnet_b7` compiled by `compile_model.py`, with a CPU baseline; this is
the run `verified.evidence` in `versions.json` names):

```markdown
**Device:** Pixel 10 (serial localhost:41015), SoC Tensor G5, Android 17
**Model:** efficientnet_b7_Google_Tensor_G5.tflite (142,963,424 bytes (143.0 MB), compiled for Tensor_G5)
**Compile:** --target Tensor_G5; 930 / 930 ops offloaded (from efficientnet_b7_Google_Tensor_G5.tflite.compile.json)
**Versions:** compiled with ai-edge-litert 2.1.6; runtime binaries from bucket release '2.3.1' - DIFFERENT releases (the pair verified in versions.json)
**Delegation (runtime):** 1 of 1 node(s) replaced by DispatchDelegate at run time
**Mode:** strict NPU (--use_cpu=false --require_full_delegation=true); requested 5 warmup / 50 measured runs (actual counts in the table)
**Thermal before NPU run:** throttling status 0 (none); TPU sensor 45.0 C (single reading, informational)
**TPU tile time:** from the dispatch library's hook (LITERT_VENDOR_HOOK_ARGS) in a separate hooked pass of 66 runs (16 warmup + 50 measured; warmups included): 1169.13 ms in total; the hook counted 66 = 1 call per run, one per dispatch invoke; per inference = total / 66 runs
**TPU energy:** from the dispatch library's power hook (LITERT_VENDOR_HOOK_ARGS) in the hooked pass of 66 runs (16 warmup + 50 measured; warmups included): 1404.45 mJ on the TPU rail from the first inference to the model's teardown, idle gaps included; the hook counted 66 = 1 call per run, one per dispatch invoke; per inference = total / 66 runs
**Benchmark binary:** cached download of https://storage.googleapis.com/litert/binaries/2.3.1/android_arm64/benchmark_model (fetched 2026-10-26 05:01:54 UTC, md5 bx6O455Ns4gjZWozKljNfQ==)
**Dispatch library:** cached download of https://storage.googleapis.com/litert/binaries/2.3.1/android_arm64/libLiteRtDispatch_GoogleTensor.so (fetched 2026-10-26 05:01:52 UTC, md5 tp26wryZhjaU3IYIz2w7/g==)
**NPU flags:** `--graph=/data/local/tmp/litert_benchmark/run-20261026-053057-3366899/efficientnet_b7_Google_Tensor_G5.tflite --use_npu=true --use_cpu=false --require_full_delegation=true --dispatch_library_path=/data/local/tmp/litert_benchmark/run-20261026-053057-3366899 --num_runs=50 --warmup_runs=5 --report_peak_memory_footprint=true --use_profiler=true`
**Log check:** npu.log: 0 unexpected WARNING/ERROR lines (2 known-benign); cpu.log: 0 unexpected WARNING/ERROR lines (0 known-benign); tile_time.log: 0 unexpected WARNING/ERROR lines (2 known-benign); profiler retry: none
**Logs:** bench_2.3.1_energy

| Metric | NPU (Tensor_G5) | CPU baseline |
|---|---|---|
| Model file | efficientnet_b7_Google_Tensor_G5.tflite | efficientnet_b7.tflite |
| Model init (ms) | 85.22 | 155.21 |
| Warmup first (ms) | 35.02 | 207.79 |
| Warmup avg (ms) | 25.06 | 202.04 |
| Inference avg (ms) | 26.33 | 200.05 |
| Inference min / max (ms) | 22.61 / 29.68 | 195.37 / 201.41 |
| Inference std (ms) | 1.98 | 0.96 |
| Inference p5 / p50 / p95 (ms) | 22.923 / 27.494 / 28.109 | 198.724 / 200.283 / 200.964 |
| TPU tile time / inference (ms) | 17.714 | - |
| TPU energy / inference (mJ) | 21.279 | - |
| Peak memory (MB) | 253.54 | 646.82 |
| Runs (warmup / measured) | 20 / 50 | 5 / 50 |

NPU speed-up vs CPU (avg latency): **7.60x**
```

The hooked pass ran 66 times and the NPU run 70 times (different warmup time
floors); the tile time and the energy use the hooked pass's own count. TPU tile
time (17.714 ms) is below `Inference avg` (26.33 ms) because it excludes host
and driver work. The hook counted one call per run, so its own
`Average TPU tile time (us): 17714.11` agrees with the table; on the `2.3.0`
binaries (2026-10-09) the same model gave 17.689 ms while the hook's own average
said 8844 us, half the real value. The TPU energy (21.279 mJ) is the power
report's `Total Energy (uJ): 1404446` divided by the 66 runs.

## Accuracy notes

* `benchmark_model` runs as a shell binary, which the LiteRT docs note is not
  identical to in-app performance (different process priority, no app
  sandbox). Use it for relative comparisons and regressions.
* Keep the phone unplugged from heavy workloads, screen on, and not thermally
  throttled; repeat runs if `Inference (std)` is large relative to the mean.
