# Packaging a compiled model for an Android app

Reference for `scripts/package_ai_pack.py` (SKILL.md steps 5 and 6) and
`scripts/install_and_verify.py` (step 7). The user-facing steps live in the
`INTEGRATION.md` the script writes next to each package (template:
`assets/templates/INTEGRATION.md`); this file explains what the package
contains, why, and how to check it. Everything here uses public tools only:
Gradle, the Android Gradle plugin, Google Play, bundletool and LiteRT's
published Maven and PyPI packages.

## Contents

- [How it fits together](#how-it-fits-together): Lines 30-77
  - [Why `model#group_other` holds a placeholder](#why-modelgroup_other-holds-a-placeholder): Lines 57-66
  - [Why the script calls LiteRT's exporter](#why-the-script-calls-literts-exporter): Lines 68-77
- [Delivery modes (asked in Step 0)](#delivery-modes-asked-in-step-0): Lines 79-96
- [Runtime facts behind the generated files](#runtime-facts-behind-the-generated-files): Lines 98-112
- [Checking a package](#checking-a-package): Lines 114-145
- [Quick test without bundletool (`--quick-test`)](#quick-test-without-bundletool---quick-test): Lines 147-165
- [Updating builds an app already ships](#updating-builds-an-app-already-ships): Lines 167-224
  - [What the script reads](#what-the-script-reads): Lines 174-186
  - [Verdicts](#verdicts): Lines 188-213
  - [Delivering an update](#delivering-an-update): Lines 215-224
- [Applying the plan (SKILL.md step 6)](#applying-the-plan-skillmd-step-6): Lines 226-314
  - [New integration (6a)](#new-integration-6a): Lines 235-301
  - [Update (6b)](#update-6b): Lines 303-314
- [Checking on a Pixel (SKILL.md step 7)](#checking-on-a-pixel-skillmd-step-7): Lines 316-371
- [Public references](#public-references): Lines 373-386

## How it fits together

The package works for an app with no LiteRT or NPU support yet: together with
the `INTEGRATION.md` steps it adds the LiteRT runtime
(`com.google.ai.edge.litert:litert`), the Google Tensor NPU runtime
(`libLiteRtDispatch_GoogleTensor.so`, in the runtime feature module), the
models and the loading code. Nothing is copied from the phone or built from
source: the TPU driver the runtime uses ships on the Pixel itself.

| Piece | What it is | Where it comes from |
|---|---|---|
| AI pack `ai_packs/<pack>/` | Google Play AI pack (`com.android.ai-pack` Gradle plugin) with one folder per device group: `model#group_Google_Tensor_G5/<model>.tflite`, `model#group_Google_Tensor_G6/...`, and `model#group_other/placeholder.txt` | Written by LiteRT's exporter, `ai_edge_litert.aot.ai_pack.export_lib`, from the compiled files as they are (byte-identical); the script adds `build.gradle.kts` and replaces the `other` copy with a placeholder |
| `device_targeting_configuration.xml` | Defines the device groups: `Google_Tensor_G5` = SoC manufacturer `Google`, model `Tensor G5` (same for G6) | Written by the exporter |
| `litert_npu_runtime_libraries/google_tensor_runtime/` | Install-time dynamic feature module delivering `libLiteRtDispatch_GoogleTensor.so`, only to the pack's device groups | Generated from `assets/templates/`; the library itself is the Maven artifact `com.google.ai.edge.litert:litert-npu-runtime-google-tensor` |
| `litert_npu_runtime_libraries/runtime_strings/` | Library module holding the feature module's title string | Generated from `assets/templates/` |
| `cpu_gpu/<model>_cpu_gpu.tflite` | The original model, for the app's base assets (`litert/`): the CPU path | Copy of `--fallback` |
| `kotlin/TensorModelLoader.kt` | Loads the Tensor build on packaged Pixels, else the CPU model; logs one result line | Generated from `assets/templates/` |
| `quick_test/<SoC>/assets/model/<model>.tflite` (only with `--quick-test`) | A copy of each Tensor build for the optional quick test (below) | Copy of the exporter's output, byte-identical |
| `model_io.json` | Input/output names, shapes and types of the original model | Read with `ai_edge_litert.interpreter.Interpreter` |
| `pack.json` | Provenance: every source path and SHA-256, sidecar flags, versions, the checks that passed | Written by the script |

Google Play splits the bundle by device group: a Pixel 10 (Tensor G5)
installs the `Google_Tensor_G5` variant of the pack and the runtime module;
other phones get the `other` variant (the placeholder) and no runtime module,
and run the CPU model from the base assets. The app always opens
`model/<model>.tflite`; Play strips the `#group_...` suffix.

### Why `model#group_other` holds a placeholder

The app needs the original model in its base assets anyway: it is the
fallback when the TPU path fails on a Pixel (for example on an Android build
without NPU support). If the pack's `other` folder also held the original,
phones outside the Tensor groups would download it twice with `install-time`
delivery. The placeholder keeps the folder (bundletool requires every
device-group folder set to be consistent) without the second copy. The
exporter uses the same technique for its MediaTek pack. This is the only
change the script makes to the exporter's output, and its checks confirm it.

### Why the script calls LiteRT's exporter

The pack layout and the device-targeting XML come from
`export_lib.export()`, so they follow LiteRT when the pinned version changes.
The script builds the exporter's input from files on disk (one
`GoogleTensorBackend` per stamped SoC plus a `FallbackBackend` for the
original); neither touches the compiler, so packaging needs `ai-edge-litert`
but not the Google Tensor SDK Beta, and nothing is recompiled. If the
exporter's API changes, the script exits 5 instead of guessing a layout
(`references/contributing.md` covers adopting such a release).

## Delivery modes (asked in Step 0)

One line in the pack's `build.gradle.kts`
(`dynamicDelivery { deliveryType = "..." }`) decides when Google Play puts
the model on the phone. In every mode a phone receives only its own group's
files.

| Mode | When the model arrives | What the app needs | Pick it when |
|---|---|---|---|
| `install-time` (default) | With the app, ready at first launch | Nothing extra; the loader reads it as an asset | Most apps; the simplest and most robust |
| `fast-follow` | Downloaded automatically right after install | Play AI Delivery library (pulled in by LiteRT) and the `FOREGROUND_SERVICE` / `FOREGROUND_SERVICE_DATA_SYNC` permissions | Large models needed soon after install |
| `on-demand` | When the app asks for it | Same as `fast-follow`; the loader starts the download | Large models used only in an optional feature |

Explain it to users in one sentence per mode and default to `install-time`
when they have no preference. Limits from Play for On-device AI: an AI pack
can be up to 1.5 GB (compressed), an app up to 4 GB; downloads over 200 MB on
mobile data need the user's confirmation, which the generated loader does not
show (it falls back to the CPU model).

## Runtime facts behind the generated files

Fact                                                                                                                                                                                                                                                                                                                                                                                | Consequence in the package
----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------
The Google Tensor NPU runtime is the Maven artifact `com.google.ai.edge.litert:litert-npu-runtime-google-tensor`; its AAR holds `jni/arm64-v8a/libLiteRtDispatch_GoogleTensor.so` and declares `<uses-native-library>` for `libedgetpu_litert.so` and `libedgetpu_util.so` (observed with 2.3.0 and 2.3.2)                                                                          | The feature module only needs the Maven dependency; no `.so` files or manifest entries are copied by hand
The runtime and `com.google.ai.edge.litert:litert` must be one release                                                                                                                                                                                                                                                                                                              | Both versions come from `maven_release` in `versions.json`; the checks and INTEGRATION.md say so
LiteRT's Kotlin API (`litert-api`) is compiled with a recent Kotlin: 2.3.0 and 2.3.2 carry Kotlin metadata 2.4.0, which Kotlin 2.3 reads and Kotlin 2.1 rejects with `was compiled with an incompatible version of Kotlin` (checked 2026-10-14, 2.3.2 on 2026-10-27)                                                                                                                | INTEGRATION.md requires Kotlin `kotlin_min` (from `versions.json`) or newer
LiteRT finds the dispatch library by listing the app's native library directory                                                                                                                                                                                                                                                                                                     | INTEGRATION.md requires `packaging { jniLibs { useLegacyPackaging = true } }`
AI packs cannot contain native code                                                                                                                                                                                                                                                                                                                                                 | The runtime is a feature module, not part of the pack
bundletool requires every module with native libraries to support the same ABIs; LiteRT's own AAR ships more ABIs than the runtime AAR (observed with 2.3.0 and AGP 8.13.1: a base module with `[ARM64_V8A, ARMEABI_V7A, X86_64]` next to the runtime module's `[ARM64_V8A]` fails `packageDebugBundle` with `All modules with native libraries must support the same set of ABIs`) | INTEGRATION.md limits the app to arm64-v8a (`abiFilters`); `--check-project` requires it and marks it risky, because devices without arm64-v8a can then no longer install the app
A module that names a device group the device-targeting XML does not define makes bundletool reject the bundle; all AI packs with group folders must use the same set of groups                                                                                                                                                                                                     | The runtime module lists exactly the pack's groups; with several models, package them with the same SoCs
`NpuCompatibilityChecker.GoogleTensor` accepts Android 16 (API 36) or newer, excluding builds whose ID starts with `BP2A`                                                                                                                                                                                                                                                           | The loader uses LiteRT's own check plus the packaged SoC list, so older Pixels and builds go straight to the CPU model
`CompiledModel.Options(Accelerator.NPU)` adds the CPU automatically                                                                                                                                                                                                                                                                                                                 | A partly delegated build still runs in the app (slower); the strict benchmark (step 3) is the gate that catches it
`benchmark_model` uses the `burst` TPU performance mode; LiteRT's Kotlin `CompiledModel.Options` has no Google Tensor options                                                                                                                                                                                                                                                       | In-app latency can differ from the benchmark; measure in the app before quoting numbers
The dispatch library in the Maven AAR is a different build than the one in the public binaries bucket that the benchmark downloads, even at the same release (2.3.0, observed 2026-10-14: 579,024 vs 629,984 bytes; the same sizes for Maven 2.3.2 and bucket 2.3.1, 2026-10-27)                                                                                                    | To benchmark with the exact library the app ships, pass the AAR: `benchmark_on_device.py --dispatch-lib <litert-npu-runtime-google-tensor-<release>.aar>` (it extracts the `.so`) and say in the report which library was used. The AAR is at `https://dl.google.com/dl/android/maven2/com/google/ai/edge/litert/litert-npu-runtime-google-tensor/<release>/litert-npu-runtime-google-tensor-<release>.aar`, `<release>` being `maven_release`. Observed 2026-10-14 with 2.3.0 on a Pixel 10: the AAR's library passes the strict benchmark and reports TPU tile time, with the same results as the bucket build within run-to-run noise (efficientnet_b7: 26.10 vs 25.61 ms average, 17.75 vs 17.72 ms tile time). If a build's TPU tile time line says `unavailable`, that build has no telemetry hook; the latency rows are still valid. The 2.3.0 AAR's library has the old power hook (checked 2026-10-26: its tile time counts 2 calls per run, corrected by the script), so its **TPU energy** line says `unavailable`; for an app on 2.3.0 the energy comes from runs with the default bucket binaries. The 2.3.2 AAR's library has the fixed hooks (observed 2026-10-27 on a Pixel 10: strict pass, TPU tile time and TPU energy both `1 call per run, one per dispatch invoke`; efficientnet_b7: 26.45 ms average, 17.891 ms tile time, 21.438 mJ energy, vs 26.86 ms, 18.168 ms and 21.643 mJ with the bucket's 2.3.1 library in the next run)

## Checking a package

Before writing, `package_ai_pack.py` checks that each `--compiled` file is
stamped for `Tensor_G5`/`Tensor_G6` with one build per SoC, that `--fallback`
is uncompiled, and that each build matches its `.compile.json` (SHA-256,
target) and was compiled from `--fallback` (only that last check can be
overridden, with `--allow-source-mismatch`). It writes into a staging
directory and never replaces a directory it did not write; `--overwrite`
replaces only its own package.

`package_ai_pack.py` verifies the package before moving it into place (exit 7
otherwise, and nothing is left at `--output-dir`); `pack.json` lists the
checks:

1. The pack folders are exactly one `model#group_Google_Tensor_Gx` per build
   plus `model#group_other`.
2. Each packed model is byte-identical to its input and stamped for its
   folder's SoC; `model#group_other` holds only the placeholder.
3. The device-targeting XML defines exactly those groups, each with
   `system-on-chip manufacturer="Google" model="Tensor Gx"`.
4. The runtime module is delivered to the same groups.
5. The CPU model is byte-identical to `--fallback`.
6. No generated file has an unfilled template placeholder.

On a phone, after the user built and installed the app (INTEGRATION.md,
"Test on a Pixel before releasing"; `install_and_verify.py` does both checks,
see "Checking on a Pixel" below):

- `adb shell pm path <application id>` lists a `google_tensor_runtime` split
  on a packaged Pixel (and the pack split for `install-time` delivery).
- `adb logcat -s LiteRtTensor` shows `LITERT_TENSOR_RESULT {"path":"npu", ...}`
  when the model runs on the TPU; `"path":"cpu"` comes with `npu_error`.

## Quick test without bundletool (`--quick-test`)

Local testing as Google Play would deliver needs bundletool, because
`./gradlew installDebug` installs the base APK only: no AI pack and no
runtime feature module, so the loader falls back to the CPU model. The
optional quick test avoids that for trying a model on one's own Pixel:

| Piece | What it does |
|---|---|
| `quick_test/<SoC>/assets/model/<model>.tflite` | Copied to `<app module>/tensor_quick_test/`: a copy of each Tensor build (byte-identical, checked) |
| Gradle block in the app module (INTEGRATION.md) | Only with `-PtensorQuickTest=<SoC>`: adds `tensor_quick_test/<SoC>/assets` to the **debug** assets and `litert-npu-runtime-google-tensor` as a `debugImplementation` dependency, so the debug APK itself carries the build at `model/<model>.tflite` and `libLiteRtDispatch_GoogleTensor.so` |
| `TensorModelLoader.kt` | Reads the build from the app's assets when it is there, whatever the delivery mode; otherwise from the AI pack as usual |

Without the property, nothing changes, and release builds never change, so
Google Play users are unaffected. It does not test device-group splitting or
pack delivery: run the bundletool steps before a release. Verified
2026-10-14 on a Pixel 10 with `on-demand` delivery: the debug APK alone ran
the build on the NPU. `--update-project` also replaces existing
`tensor_quick_test/<SoC>/` copies.

## Updating builds an app already ships

`package_ai_pack.py --update-project <project root>` (SKILL.md step 5b) is
for an app that already has a Google Tensor setup - made with this skill,
with LiteRT's NPU guide, or by hand - and gets new builds. Usually only the
model files change; the runtime, device groups, Gradle files and code stay.

### What the script reads

It never writes to the project. It skips comments, `build/` and hidden
folders.

| Piece | How it is found |
|---|---|
| AI pack | A module with an `aiPack { }` (or `assetPack { }`) block and `<folder>#group_<group>/` folders under `src/main/assets`; `packName` and `deliveryType` come from that block. `--pack-name` picks one if several ship Google Tensor builds |
| Model | The `.tflite` in the pack's Tensor group folders (`--model-name` if several). The new builds keep its folder and file name, so the app opens the same path |
| Device groups | The XML named by `deviceTargetingConfig = file(...)` in the module that lists the pack in `assetPacks`. A group belongs to a SoC when its only `system-on-chip` selector is `manufacturer="Google" model="Tensor Gx"`, so the app's own group names work. Without the XML, each folder's build stamp decides |
| CPU copy | `<folder>#group_<defaultGroup>/<file>` in the pack (LiteRT's default layout), `<module>/src/main/assets/litert/<model>_cpu_gpu.tflite` or the loader's `CPU_MODEL_ASSET` (this skill's layout), else `--cpu-asset` |
| Runtime | `com.google.ai.edge.litert:litert-npu-runtime-google-tensor` and `:litert` in the build files (a literal, one `$variable` from the build file or `gradle.properties`, or a `gradle/libs.versions.toml` alias), a local runtime `.aar`, or a bundled `libLiteRtDispatch_GoogleTensor.so`; plus the `<dist:device-group>` list of the module that holds it |
| Loader | A source file with `PACKAGED_SOC_MODELS` (the generated `TensorModelLoader.kt`) for this pack |

### Verdicts

The new files come from LiteRT's exporter, byte-identical to the inputs as
in a new package, and go to `files/<path in the project>`: one per SoC plus
the CPU copy(s). `UPDATE.md` section 2 lists every change beyond them:

| Situation | Verdict | What `UPDATE.md` says |
|---|---|---|
| Same SoCs, same inputs and outputs | `drop-in` | Copy the files; nothing else changes |
| A SoC the app does not ship yet | `structural` | Its group element for the XML (taken from the exporter's XML), a folder in every AI pack with device-group folders (bundletool requires the same groups everywhere), the group in the runtime module's manifest, the SoC in `PACKAGED_SOC_MODELS` |
| A SoC the app ships gets no new build | `structural` | Compile it (recommended), or remove that SoC from the app (folders, group, runtime-module line, loader entry); otherwise its phones keep the previous model |
| Inputs or outputs changed in shape, type or count | `structural` | Update the app's pre- and post-processing. Compared with LiteRT's interpreter on the app's CPU copy and the new original, so only in a real run; changed names alone are `info` |
| No runtime, or `litert` and the runtime at different known releases | `structural` | Add the runtime (a new package has it), or use one release for both |
| The pack also has builds for other SoCs (other vendors) | `structural` | Those builds still hold the previous model |
| The project already has these files | `up-to-date` | Nothing to copy; also the check after copying |

The `Runtime` check compares the app's runtime with `maven_release`: `pass`
when equal, `device` when different or unknown. With `device`, the new
builds must pass the strict benchmark with the app's own library before
release. `benchmark_on_device.py --dispatch-lib` accepts the app bundle
(`.aab`, the library exactly as shipped), the runtime AAR or the `.so`.

Before moving the plan into place, the script checks that every staged file
is byte-identical to its input and stamped for its group's SoC (the CPU copy
uncompiled), and that the project files it plans to replace still have the
SHA-256 it read (exit 7 otherwise).

### Delivering an update

- AI packs ship with app releases: Google Play has no model-only update.
  The app bundle needs a higher `versionCode`; Play rejects a reused one.
- `install-time`: the new model arrives with the app update. `fast-follow`
  and `on-demand`: the app update invalidates packs downloaded before; Play
  downloads `fast-follow` packs again right after the update, and
  `on-demand` packs when the app requests them (the generated loader does,
  and uses the CPU model until then).
- bundletool local testing cannot update an installed app: uninstall first.

## Applying the plan (SKILL.md step 6)

The agent applies a package or an update to the user's project only after
the user says yes: one approval for the whole plan, then a separate OK for
each risky item. The scripts never write to the project; the agent copies
the files and edits the build files itself. For an update, the plan is
`UPDATE.md`, and the dry run of `--update-project` must report every file
`unchanged` afterwards.

### New integration (6a)

1.  Ask for the project root (the folder with `settings.gradle.kts` or
    `settings.gradle`). If it is a git checkout with uncommitted changes
    (`git status --porcelain`), say so in the plan and suggest committing
    first.
2.  Get the plan (read-only, any `python3`, no LiteRT):
    `python3 scripts/package_ai_pack.py --check-project <project root>
    --package <output-dir of step 5a> [--app-module app] [--json]`. Every
    requirement of `INTEGRATION.md` comes back as `pass`, `fail` or `warn`
    (checks below). The `fail` items are the plan; offer the `warn` items (for
    example the optional quick test) as options.
3.  Show the plan once: the files to copy, the files to edit with their
    snippets, and the risky items marked. Get the approval, then the separate
    OKs.
4.  Apply it: run the copy commands; make the edits with your file-editing
    tool, merged into the existing blocks (`android { }`, `defaultConfig`,
    `dependencies`, the version catalog when the project uses one) in the
    file's own style. Never delete or reformat unrelated code, and never touch
    signing configs.
5.  Re-run step 2 until nothing fails (apart from declined items).
6.  Build once from the project root: `./gradlew :<app module>:bundleDebug`.
    Fix errors your edits caused; report errors that were there before instead
    of fixing them.
7.  Report what changed, and how the app uses the model: `INTEGRATION.md` step
    9 has the loader call, `model_io.json` the inputs and outputs. If the user
    tells you where the model is used, offer to write that code (the pre- and
    post-processing depend on their app, so show it first). Then offer
    SKILL.md step 7.

`--check-project` compares the project with every requirement of the
package's `INTEGRATION.md`. It reads the project like `--update-project`
(skipping comments, `build/` and hidden folders), needs no LiteRT and
writes nothing. Each check is `pass`, `fail` or `warn`. A `fail` comes with
its fix - `copy` (a shell command that copies from the package) or `edit`
(the file, and a snippet in the project's Kotlin or Groovy DSL) - and is
`risky` when it needs its own OK. `--json` prints the same as one object
(`checks`, `summary.to_do`, `summary.risky`). "The package's release" below
is the LiteRT release in its `pack.json` (`maven_release` when it was
written).

| Check | Passes when | Risky when it fails because |
|---|---|---|
| AI pack module | `ai_packs/<pack>/` holds every file of the package, byte-identical, and its build file sets the package's `packName` and `deliveryType` | Project files differ from the package (they would be replaced) |
| Runtime modules | `litert_npu_runtime_libraries/google_tensor_runtime/` and `.../runtime_strings/` exist; the runtime module names no other runtime release or app module, and its manifest delivers it to the pack's device groups | - |
| Device-targeting XML | The XML named by the app's `deviceTargetingConfig` (else `<app>/device_targeting_configuration.xml`) defines the package's groups with the same selectors | - |
| CPU model | `<app>/src/main/assets/litert/<model>_cpu_gpu.tflite` is the package's original model | Another file is there |
| Model loader | A `TensorModelLoader.kt` for this pack opens `model/<model>.tflite` with the package's delivery mode and SoC list | It exists but differs (it would be replaced) |
| Quick test (optional) | Only for `--quick-test` packages: the copies in `<app>/tensor_quick_test/` and the Gradle block are there; at most `warn` | - |
| Settings includes | `settings.gradle(.kts)` includes the pack and both runtime modules | - |
| App: `assetPacks`, `dynamicFeatures` | The app module lists the pack and the runtime module | - |
| App: bundle device targeting | `bundle { deviceTargetingConfig = file(...) ; deviceGroup { enableSplit = true ; defaultGroup = "other" } }` | - |
| App: native libraries extracted | `useLegacyPackaging = true`, or `android:extractNativeLibs="true"` in the manifest | - |
| App: `minSdk` | 31 or higher (`warn` when the app's build file does not set it, e.g. a convention plugin does) | It is below 31: phones below Android 12 could no longer install the app |
| App: ABI filters | `abiFilters` names `arm64-v8a` only (`warn` when it is set from a value the check cannot read) | It is missing or names other ABIs: devices without arm64-v8a could no longer install the app |
| App: LiteRT dependency | `com.google.ai.edge.litert:litert` at the package's release (`warn` when the version cannot be read) | The app uses another LiteRT release |
| App: `runtime_strings` dependency | The app module depends on the `runtime_strings` module | - |
| `gradle.properties` | `android.experimental.enableDeviceTargetingConfigApi=true` | - |
| App: download permissions | Only for `fast-follow` / `on-demand`: `FOREGROUND_SERVICE` and `FOREGROUND_SERVICE_DATA_SYNC` are declared | - |
| Android Gradle plugin | 8.10 or newer (`warn` when the version is not found) | It is older: the upgrade affects the whole build |
| Kotlin | The Kotlin Android plugin at `kotlin_min` of the package or newer (`warn` when the version is not found, or with AGP 9 or newer when no plugin is applied) | It is older, or the app has no Kotlin |

Exit 0 means nothing is left to do, which is also the proof after applying;
exit 1 lists the work; exit 2 is bad input (no project, no package, no app
module). Not checked: the app code that calls the loader (where the app uses
the model is the app's choice) and signing configs, which the agent never
touches.

### Update (6b)

The plan is `UPDATE.md`: the file table and section 2. Get one approval for
the files and the non-risky edits, and separate OKs for the risky ones
(removing a SoC, changing the runtime or LiteRT version, replacing a loader
with local changes; changed model inputs or outputs need app code changes, so
show that code first). Then: copy each project file you replace to
`<output-dir>-backup/<path>` (not inside `<output-dir>`, which `--overwrite`
replaces), copy `files/<path>` to `<project>/<path>`, make the section 2
changes, and raise `versionCode`. Re-run the step 5b command with `--dry-run`:
every file must show `unchanged`. Build once (as in 6a, step 6), then offer
SKILL.md step 7.

## Checking on a Pixel (SKILL.md step 7)

`./gradlew installDebug` cannot test the package: it installs no AI pack and
no feature module. `install_and_verify.py --project <project root>`
installs the app the way Google Play would, with bundletool's local testing:

1. It finds the app module (the only one that applies
   `com.android.application`, or `--app-module`), its device-targeting XML
   and the group of each Google Tensor SoC; the Android SDK (`--sdk`,
   `ANDROID_HOME`, `ANDROID_SDK_ROOT`, `local.properties`, the default
   folders), adb, Java (`JAVA_HOME`, else `java` on PATH), the project's
   `./gradlew` (or `--gradle`) and the newest `aapt2` in the SDK.
2. It reads the phone's model, SoC (`ro.soc.model`), API level and build ID,
   picks the device group of that SoC, and says whether LiteRT will use the
   NPU there (the conditions of `NpuCompatibilityChecker` above). `--dry-run`
   stops here and downloads nothing.
3. It builds `:<app>:bundleDebug` (`--variant` picks another variant, e.g.
   `release` or a product-flavor variant such as `freeDebug`) and reads the
   application id from the bundle. If that app is already installed, it
   stops here with exit 7 (local testing cannot update an app); with
   `--uninstall-first` it uninstalls it once the new APK set is built.
4. It runs `bundletool build-apks --local-testing` and `install-apks
   --device-groups=<group>`: what Google Play would install on this phone,
   including the AI pack and the runtime feature module.
5. It lists the installed splits (`pm path`) and checks for
   `libLiteRtDispatch_GoogleTensor.so` in the app's native library folder.
6. It starts the launcher activity and waits for the loader's
   `LITERT_TENSOR_RESULT` line in the app process's log.

bundletool is `--bundletool` (a `bundletool-all` jar, or a folder of
bundletool jars), else `bundletool-all-<bundletool_release>.jar` from
https://github.com/google/bundletool/releases, cached in
`~/.cache/litert-google-tensor/`. The output folder (`--output-dir`, default
`./litert_app_verify/<timestamp>/`) holds `results.json`, `report.md` and
the Gradle and bundletool logs; the `.apks` file is deleted unless
`--keep-apks`. The app stays installed. The script never signs for release
or uploads, and uninstalls an installed copy only with `--uninstall-first`.

| Result | Meaning |
|---|---|
| `"path":"npu"`, exit 0 | The Tensor build ran on the TPU, installed as Google Play would install it |
| `"path":"cpu"` where the NPU is not expected, exit 0 | The correct fallback: no build for the phone's SoC, Android below API 36, or a `BP2A` build (the report's `Expected path: CPU (...)` says which) |
| `"path":"cpu"` on a phone with a build, exit 1 | Part of the setup is missing: the `npu_error`, the installed splits and the dispatch-library line say which (`troubleshooting.md`) |
| No result line, exit 6 | The app did not call `TensorModelLoader.load()` within `--timeout` (it may load the model on another screen), or it crashed |

The script needs a JDK the project's Gradle supports (`JAVA_HOME`), the
Android SDK (adb), the project's `./gradlew` (or `--gradle`, which may carry
options such as `-Pname=value`), and a Pixel with USB debugging. Run
`--dry-run` first; an app with product flavors needs `--variant` (for example
`freeDebug`). Exit codes: 0 ran on the NPU (or on the CPU where no Tensor
build is expected; with `--no-launch`: installed), 1 CPU on a phone with a
Tensor build, 2 environment (project, tools, device), 3 Gradle build failed,
4 bundletool failed, 6 no result line, 7 already installed. After exit 7, ask
the user before rerunning with `--uninstall-first` (uninstalling deletes the
app's data on the phone); after exit 6, have the user open the screen that
loads the model while the script waits, or raise `--timeout`.

## Public references

- LiteRT NPU guide (AI packs, runtime modules, `CompiledModel`):
  https://developers.google.com/edge/litert/next/npu
- Play for On-device AI (AI packs, delivery modes, device targeting, local
  testing): https://developer.android.com/google/play/on-device-ai
- Play Feature Delivery: https://developer.android.com/guide/playcore/feature-delivery
- LiteRT Kotlin API (`AiPackModelProvider`, `ModelSelector`, ...):
  https://developers.google.com/edge/api/litert/kotlin
- LiteRT's AI-pack exporter source:
  https://github.com/google-ai-edge/LiteRT/blob/main/litert/python/aot/ai_pack/export_lib.py
- bundletool: https://github.com/google/bundletool/releases
- Google Maven (`com.google.ai.edge.litert`):
  https://maven.google.com/web/index.html#com.google.ai.edge.litert
