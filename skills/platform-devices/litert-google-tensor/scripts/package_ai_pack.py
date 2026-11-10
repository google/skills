#!/usr/bin/env python3
# Copyright 2026 The Google AI Edge Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Packages Google Tensor-compiled .tflite builds for an Android (Gradle) app.

Turns builds made by compile_model.py (and ideally checked with
benchmark_on_device.py) into everything a Gradle app needs to ship them with
Google Play for On-device AI:

  * a Google Play AI pack written by LiteRT's own exporter,
    ``ai_edge_litert.aot.ai_pack.export_lib``, from the files as they are -
    nothing is recompiled, so the packed models are byte-identical to the
    inputs - plus the pack's build.gradle.kts;
  * the Google Tensor NPU runtime as an install-time feature module
    (``litert_npu_runtime_libraries/google_tensor_runtime``, Maven artifact
    ``com.google.ai.edge.litert:litert-npu-runtime-google-tensor``) and its
    ``runtime_strings`` module, delivered to the same device groups as the
    pack;
  * the original model for the app's base assets (the CPU path), a Kotlin
    loader (TensorModelLoader.kt), the model's input/output signature
    (model_io.json), provenance (pack.json) and a step-by-step INTEGRATION.md.

Output (--output-dir, default <fallback model dir>/app_package/<pack name>):

  INTEGRATION.md  pack.json  model_io.json
  cpu_gpu/<model>_cpu_gpu.tflite                (-> app assets litert/)
  ai_packs/device_targeting_configuration.xml   (-> app module)
  ai_packs/<pack>/build.gradle.kts
  ai_packs/<pack>/src/main/assets/model#group_Google_Tensor_G5/<model>.tflite
  ai_packs/<pack>/src/main/assets/model#group_other/placeholder.txt
  litert_npu_runtime_libraries/google_tensor_runtime/...
  litert_npu_runtime_libraries/runtime_strings/...
  kotlin/TensorModelLoader.kt

``model#group_other`` holds a placeholder instead of a second copy of the
original model: devices outside the Google Tensor groups use the base-asset
CPU model, so no device downloads the original twice (the exporter uses the
same placeholder technique for its MediaTek pack).

Update mode (--update-project <Gradle project root>) is for an app that
already ships Google Tensor builds in an AI pack and gets new ones. The script
reads the project without changing it: the pack, its device groups (matched
by SoC through the app's device-targeting XML), the runtime, the app's CPU
copy of the model and a generated TensorModelLoader. It runs the same input
checks and LiteRT export, then writes only the files to copy, under the
app's existing paths and names:

  UPDATE.md  update.json  model_io.json
  files/<path in the project>    (one per Tensor build, plus the CPU copy)

(default --output-dir: <fallback model dir>/app_update/<pack name>). The
verdict is "drop-in" (only model files change), "structural" (UPDATE.md
lists the other edits: a new or dropped SoC, the runtime, changed model
inputs or outputs) or "up-to-date" (the project already has these files).

Check mode (--check-project <Gradle project root> --package <package dir>)
reads a project and checks it against a package this script wrote: every
requirement of its INTEGRATION.md (files, settings includes, the app's
Gradle setup, gradle.properties, permissions, plugin versions) comes back as
pass, fail or warn, with the exact fix and whether the fix is risky
(upgrades, a higher minSdk, replacing changed files). Run before applying a
package, it lists the plan; after, it confirms the project is complete.

Only the export step imports LiteRT, so --help and --dry-run work with any
python3. A real run needs a Python with ``ai-edge-litert`` (the compile venv
works; the Google Tensor SDK Beta is not needed for packaging).

Exit codes
----------
0 success (--check-project: every requirement passes)
1 --check-project only: at least one requirement fails (the report says what
  to do)
2 bad input: missing file, duplicate SoC, invalid name, output exists, a
  build that differs from its .compile.json sidecar, broken versions.json;
  with --update-project also a project the script cannot update as is (no
  or several Tensor AI packs, unknown CPU copy, a group with several SoCs)
3 wrong model kind: an uncompiled --compiled file, a compiled --fallback, or
  a model compiled by another toolchain (Edge TPU custom op) for either
5 LiteRT not importable, or its AI-pack exporter API changed
7 post-export verification failed (nothing is left at --output-dir)
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.metadata
import json
import os
import pathlib
import re
import shlex
import shutil
import sys
from typing import Any
import xml.etree.ElementTree as ET

SKILL_DIR = pathlib.Path(__file__).resolve().parent.parent
VERSIONS_FILE = SKILL_DIR / "assets" / "versions.json"
TEMPLATES_DIR = SKILL_DIR / "assets" / "templates"
GENERATOR = "litert-google-tensor package_ai_pack.py"

SUPPORTED_TARGETS = ("Tensor_G5", "Tensor_G6")
PIXEL_FAMILY = {"Tensor_G5": "Pixel 10 family", "Tensor_G6": "Pixel 11 family"}
DELIVERY_TYPES = ("install-time", "fast-follow", "on-demand")

TFLITE_FILE_IDENTIFIER = b"TFL3"  # flatbuffer identifier at byte offset 4..8
DISPATCH_OP_MARKER = b"DISPATCH_OP"
BUILD_STAMP_KEY = b"LiteRtStamp"
GOOGLE_MANUFACTURER = b"Google"
SOC_MODEL_RE = re.compile(rb"Tensor_G\d+")
# Custom op of models compiled by the Edge TPU compiler (and older Google
# Tensor tooling), same check as check_compiled.py.
LEGACY_TPU_OP_RE = re.compile(rb"edgetpu-custom-op[\w-]*")

PACK_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
MODEL_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
KOTLIN_PACKAGE_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*")
APP_MODULE_RE = re.compile(r"[A-Za-z0-9_.-]+(:[A-Za-z0-9_.-]+)*")
PLACEHOLDER_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")

DTC_NS = "http://schemas.android.com/apk/config"
DIST_NS = "http://schemas.android.com/apk/distribution"
OTHER_GROUP_DIR = "model#group_other"
PLACEHOLDER_FILE = "placeholder.txt"
# Optional quick test (--quick-test): quick_test/<SoC>/assets/ in the package
# goes to <app module>/tensor_quick_test/; the Gradle property picks the SoC.
QUICK_TEST_DIR = "quick_test"
APP_QUICK_TEST_DIR = "tensor_quick_test"
QUICK_TEST_PROPERTY = "tensorQuickTest"
PLACEHOLDER_TEXT = (
    "Intentionally not a model. Devices outside the Google Tensor device\n"
    "groups of this AI pack run the original model from the app's base\n"
    "assets (litert/{model}_cpu_gpu.tflite), so they do not need a copy\n"
    "here. Written by {generator}.\n"
)

# Template file (relative to assets/templates/) -> output file (relative to the
# output directory). ``{pack}`` is replaced by the pack name.
TEMPLATE_OUTPUTS = (
    ("ai_pack/build.gradle.kts", "ai_packs/{pack}/build.gradle.kts"),
    (
        "google_tensor_runtime/build.gradle.kts",
        "litert_npu_runtime_libraries/google_tensor_runtime/build.gradle.kts",
    ),
    (
        "google_tensor_runtime/src/main/AndroidManifest.xml",
        "litert_npu_runtime_libraries/google_tensor_runtime/src/main/"
        + "AndroidManifest.xml",
    ),
    (
        "runtime_strings/build.gradle.kts",
        "litert_npu_runtime_libraries/runtime_strings/build.gradle.kts",
    ),
    (
        "runtime_strings/src/main/res/values/strings.xml",
        "litert_npu_runtime_libraries/runtime_strings/src/main/res/values/"
        + "strings.xml",
    ),
    ("TensorModelLoader.kt", "kotlin/TensorModelLoader.kt"),
)
RUNTIME_MANIFEST = TEMPLATE_OUTPUTS[2][1]

# Notes shown next to files in INTEGRATION.md's tree.
TREE_NOTES = {
    "INTEGRATION.md": "this guide",
    "pack.json": "provenance: sources, SHA-256, versions",
    "model_io.json": "input/output names, shapes and types",
    "ai_packs/device_targeting_configuration.xml": "-> <app module>/",
    "kotlin/TensorModelLoader.kt": "-> your sources",
}


class PackError(Exception):
  """A failure with the exit code to return and a message naming the fix."""

  def __init__(self, code: int, message: str):
    super().__init__(message)
    self.code = code


# --------------------------------------------------------------------------
# versions.json
# --------------------------------------------------------------------------


def read_versions() -> tuple[dict[str, Any], str | None]:
  """Returns (versions, error); never raises, so --help/--dry-run work."""
  try:
    data = json.loads(VERSIONS_FILE.read_text(encoding="utf-8"))
  except (OSError, ValueError) as e:
    return {}, f"cannot read {VERSIONS_FILE}: {e}"
  if not isinstance(data, dict):
    return {}, f"{VERSIONS_FILE} is not a JSON object"
  return data, None


def maven_release(versions: dict[str, Any], error: str | None) -> str:
  """The pinned Google Maven release of the LiteRT runtime artifacts."""
  release = versions.get("maven_release")
  if not isinstance(release, str) or not re.fullmatch(
      r"\d[0-9A-Za-z.+_-]*", release
  ):
    reason = error or "no valid 'maven_release' field"
    raise PackError(
        2,
        f"{reason}. The generated Gradle files need the LiteRT Maven "
        f"release from {VERSIONS_FILE}; restore that file from the skill.",
    )
  return release


def kotlin_min(versions: dict[str, Any], error: str | None) -> str:
  """Oldest Kotlin that can read the LiteRT Kotlin API at maven_release."""
  value = versions.get("kotlin_min")
  if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+(\.\d+)?",
                                                    value):
    reason = error or "no valid 'kotlin_min' field"
    raise PackError(
        2,
        f"{reason}. INTEGRATION.md needs the minimum Kotlin version from "
        f"{VERSIONS_FILE}; restore that file from the skill.",
    )
  return value


# --------------------------------------------------------------------------
# Model inspection (standard library only, same markers as check_compiled.py)
# --------------------------------------------------------------------------


def scan_model(path: pathlib.Path) -> dict[str, Any]:
  """SHA-256 plus the compile markers of ``path``, read in 1 MiB chunks."""
  digest = hashlib.sha256()
  markers = {DISPATCH_OP_MARKER: False, BUILD_STAMP_KEY: False,
             GOOGLE_MANUFACTURER: False}
  socs: set[str] = set()
  legacy: set[str] = set()
  head = b""
  carry = b""
  size = 0
  with open(path, "rb") as f:
    chunk = f.read(1 << 20)
    while chunk:
      if not size:
        head = chunk[:8]
      digest.update(chunk)
      size += len(chunk)
      nxt = f.read(1 << 20)
      window = carry + chunk
      for marker, seen in markers.items():
        if not seen and marker in window:
          markers[marker] = True
      for regex, found in ((SOC_MODEL_RE, socs), (LEGACY_TPU_OP_RE, legacy)):
        for m in regex.finditer(window):
          # A match touching the window end may continue in the next chunk;
          # the carried tail lets the next window see it whole.
          if nxt and m.end() == len(window):
            continue
          found.add(m.group().decode("ascii"))
      carry = window[-32:]
      chunk = nxt
  is_tflite = len(head) >= 8 and head[4:8] == TFLITE_FILE_IDENTIFIER
  compiled = (is_tflite and markers[DISPATCH_OP_MARKER]
              and markers[BUILD_STAMP_KEY])
  return {
      "path": path,
      "size_bytes": size,
      "sha256": digest.hexdigest(),
      "is_tflite": is_tflite,
      "compiled": compiled,
      "google_tensor": markers[GOOGLE_MANUFACTURER] and bool(socs),
      "soc_models": sorted(socs),
      # Compiled by another toolchain (Edge TPU custom op), not by LiteRT.
      "legacy_ops": [] if compiled or not is_tflite else sorted(legacy),
  }


def read_sidecar(model: pathlib.Path) -> dict[str, Any] | None:
  """The ``<model>.compile.json`` written by compile_model.py, if any."""
  sidecar = model.with_name(model.name + ".compile.json")
  if not sidecar.is_file():
    return None
  try:
    data = json.loads(sidecar.read_text(encoding="utf-8"))
  except (OSError, ValueError):
    return None
  return data if isinstance(data, dict) else None


def fmt_size(num_bytes: int) -> str:
  """'8,110,864 bytes (8.1 MB)'; MB = 10^6 bytes, as in the other scripts."""
  text = f"{num_bytes:,} bytes"
  if num_bytes >= 100_000:
    text += f" ({num_bytes / 1e6:.1f} MB)"
  return text


def group_of(soc: str) -> str:
  """'Tensor_G5' -> 'Google_Tensor_G5' (the exporter's device group name)."""
  return f"Google_{soc}"


def soc_display(soc: str) -> str:
  """'Tensor_G5' -> 'Tensor G5' (Build.SOC_MODEL / ro.soc.model)."""
  return soc.replace("_", " ")


def quick_test_file(soc: str, model: str) -> str:
  """Package path of a build for the optional quick test (--quick-test)."""
  return f"{QUICK_TEST_DIR}/{soc}/assets/model/{model}.tflite"


# --------------------------------------------------------------------------
# Arguments and pre-checks
# --------------------------------------------------------------------------


def parse_args(argv=None) -> argparse.Namespace:
  """Parses the command line and applies the defaults of a new integration."""
  parser = argparse.ArgumentParser(
      description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
  )
  parser.add_argument(
      "--compiled",
      action="append",
      metavar="TFLITE",
      help=(
          "A Google Tensor-compiled build (compile_model.py output); repeat "
          "for each SoC, at most one per SoC. Its .compile.json sidecar, "
          "when present, must describe this exact file. Required except "
          "with --check-project."
      ),
  )
  parser.add_argument(
      "--fallback",
      metavar="TFLITE",
      help=(
          "The ORIGINAL uncompiled model the builds were compiled from: the "
          "app's CPU path (base assets). Required except with "
          "--check-project."
      ),
  )
  parser.add_argument(
      "--pack-name",
      help=(
          "AI pack name and directory: a letter, then letters, digits or "
          "'_' (default: the fallback file name made valid). With "
          "--update-project: which of the app's packs to update, when "
          "several ship Google Tensor builds."
      ),
  )
  parser.add_argument(
      "--model-name",
      help=(
          "File name of the model inside the pack, without .tflite; the app "
          "opens model/<name>.tflite (default: the pack name). With "
          "--update-project: which model of the pack to update, when it "
          "holds several."
      ),
  )
  parser.add_argument(
      "--delivery",
      choices=DELIVERY_TYPES,
      help=(
          "When Google Play puts the model on the phone (default "
          "install-time: with the app, ready at first launch). "
          "--update-project keeps the app's delivery mode."
      ),
  )
  parser.add_argument(
      "--app-module",
      help=(
          "Gradle path of the app module, e.g. 'app' or 'apps:main' "
          "(default: app); used in the generated Gradle files. With "
          "--update-project: the module that lists the AI pack, when it "
          "cannot be found."
      ),
  )
  parser.add_argument(
      "--kotlin-package",
      help=(
          "package line of the generated TensorModelLoader.kt (default: "
          "com.example.litert)."
      ),
  )
  parser.add_argument(
      "--update-project",
      metavar="DIR",
      help=(
          "Update mode, for an app that already ships Google Tensor builds "
          "in an AI pack: the root of its Gradle project (the folder with "
          "settings.gradle.kts). The project is only read; the files to "
          "copy go to --output-dir with UPDATE.md."
      ),
  )
  parser.add_argument(
      "--quick-test",
      action="store_true",
      help=(
          "Also write quick_test/<SoC>/assets/: each Tensor build laid out "
          "for a debug APK that carries it together with the NPU runtime, so "
          "'./gradlew installDebug -PtensorQuickTest=<SoC>' runs the model on "
          "a Pixel without bundletool (local testing only; INTEGRATION.md "
          "has the steps)."
      ),
  )
  parser.add_argument(
      "--check-project",
      metavar="DIR",
      help=(
          "Check mode (read-only): is the Gradle project at DIR set up for "
          "the package given with --package? Lists every requirement as "
          "pass/fail/warn with the exact fix; exit 1 while something fails."
      ),
  )
  parser.add_argument(
      "--package",
      metavar="DIR",
      help=(
          "With --check-project: a package this script wrote (the folder "
          "with INTEGRATION.md and pack.json)."
      ),
  )
  parser.add_argument(
      "--cpu-asset",
      metavar="PATH",
      help=(
          "With --update-project: the app's copy of the original model for "
          "the CPU path, relative to the project root, when the script cannot "
          "find it; 'none' if the app keeps no CPU copy."
      ),
  )
  parser.add_argument(
      "--output-dir",
      help=(
          "Where to write the package (default: <fallback dir>/app_package/"
          "<pack name>, or app_update/<pack name> with --update-project). "
          "Must not exist unless --overwrite."
      ),
  )
  parser.add_argument(
      "--overwrite",
      action="store_true",
      help=(
          "Replace an existing --output-dir, but only one written by this "
          "script (it has a pack.json from package_ai_pack.py)."
      ),
  )
  parser.add_argument(
      "--allow-source-mismatch",
      action="store_true",
      help=(
          "Package even if a build's sidecar says it was compiled from a "
          "different file than --fallback (the CPU and TPU paths would then "
          "run different models)."
      ),
  )
  parser.add_argument(
      "--dry-run",
      action="store_true",
      help=(
          "Run every input check and print the plan; import nothing and "
          "write nothing."
      ),
  )
  parser.add_argument(
      "--json", action="store_true", help="Print a JSON summary only."
  )
  args = parser.parse_args(argv)
  # Flags the user passed (update mode rejects or checks them), then the
  # defaults of a new integration.
  args.explicit = {key for key in ("delivery", "app_module", "kotlin_package")
                   if getattr(args, key) is not None}
  args.delivery = args.delivery or "install-time"
  args.app_module = args.app_module or "app"
  args.kotlin_package = args.kotlin_package or "com.example.litert"
  return args


def default_pack_name(fallback: pathlib.Path) -> str:
  name = re.sub(r"[^A-Za-z0-9_]", "_", fallback.stem)
  if not name or not name[0].isalpha():
    name = "model_" + name
  return name


def legacy_message(flag: str, info: dict[str, Any]) -> str:
  """Error for a model compiled by another toolchain (Edge TPU custom op)."""
  return (
      f"{flag} {info['path'].name} was compiled by another toolchain: it "
      f"holds an Edge TPU custom op ({', '.join(info['legacy_ops'])}), which "
      "neither the Google Tensor runtime nor the CPU can run "
      "(check_compiled.py exits 4 for such files). Use the ORIGINAL model it "
      "was made from: as --fallback as is, and compiled with "
      "compile_model.py for --compiled."
  )


def check_names(args: argparse.Namespace, fallback: pathlib.Path) -> None:
  """Fills in, normalizes and validates the name flags of ``args``."""
  args.pack_name = args.pack_name or default_pack_name(fallback)
  if not PACK_NAME_RE.fullmatch(args.pack_name):
    raise PackError(
        2,
        f"invalid --pack-name {args.pack_name!r}: AI pack names start with a "
        "letter and contain only letters, digits and '_'.",
    )
  model = args.model_name or args.pack_name
  model = model[: -len(".tflite")] if model.endswith(".tflite") else model
  if not MODEL_NAME_RE.fullmatch(model):
    raise PackError(
        2,
        f"invalid --model-name {model!r}: use letters, digits, '_', '.' or "
        "'-', starting with a letter or digit.",
    )
  args.model_name = model
  if not KOTLIN_PACKAGE_RE.fullmatch(args.kotlin_package):
    raise PackError(
        2, f"invalid --kotlin-package {args.kotlin_package!r} (e.g. "
        "com.example.myapp.ml)."
    )
  module = args.app_module.lstrip(":")
  if not APP_MODULE_RE.fullmatch(module):
    raise PackError(
        2, f"invalid --app-module {args.app_module!r} (e.g. app or apps:main)."
    )
  args.app_module = module


def check_inputs(args: argparse.Namespace) -> tuple[dict[str, dict[str, Any]],
                                                    dict[str, Any], list[str]]:
  """Validates the models; returns (builds by SoC, fallback info, notes)."""
  notes: list[str] = []
  fallback_path = pathlib.Path(args.fallback).expanduser().resolve()
  if not fallback_path.is_file():
    raise PackError(2, f"--fallback not found: {fallback_path}")
  fallback = scan_model(fallback_path)
  if not fallback["is_tflite"]:
    raise PackError(2, f"--fallback is not a .tflite flatbuffer: "
                    f"{fallback_path}")
  if fallback["legacy_ops"]:
    raise PackError(3, legacy_message("--fallback", fallback))
  if fallback["compiled"]:
    raise PackError(
        3,
        f"--fallback {fallback_path.name} is a compiled build (SoC: "
        f"{', '.join(fallback['soc_models']) or 'unknown'}). Pass the "
        "ORIGINAL uncompiled model: compiled builds cannot run on the CPU.",
    )

  builds: dict[str, dict[str, Any]] = {}
  for raw in args.compiled:
    path = pathlib.Path(raw).expanduser().resolve()
    if not path.is_file():
      raise PackError(2, f"--compiled not found: {path}")
    info = scan_model(path)
    if not info["is_tflite"]:
      raise PackError(2, f"--compiled is not a .tflite flatbuffer: {path}")
    if info["legacy_ops"]:
      raise PackError(3, legacy_message("--compiled", info))
    if not (info["compiled"] and info["google_tensor"]):
      raise PackError(
          3,
          f"--compiled {path.name} is not compiled for Google Tensor. "
          "Compile it with compile_model.py first (check_compiled.py tells "
          "you which files are compiled).",
      )
    if len(info["soc_models"]) != 1:
      raise PackError(
          2,
          f"--compiled {path.name} names several SoCs "
          f"({', '.join(info['soc_models'])}); cannot tell which device "
          "group it belongs to.",
      )
    soc = info["soc_models"][0]
    if soc not in SUPPORTED_TARGETS:
      raise PackError(
          2,
          f"--compiled {path.name} is compiled for {soc}; this skill "
          f"packages {' and '.join(SUPPORTED_TARGETS)} builds only.",
      )
    if soc in builds:
      raise PackError(
          2,
          f"two --compiled builds for {soc}: {builds[soc]['path'].name} and "
          f"{path.name}. Pass one build per SoC.",
      )
    sidecar = read_sidecar(path)
    info["sidecar"] = sidecar
    if sidecar is None:
      notes.append(
          f"{path.name}: no .compile.json sidecar (not compiled by "
          "compile_model.py, or moved without it); flags and op counts "
          "unknown."
      )
    else:
      if sidecar.get("output_sha256") not in (None, info["sha256"]):
        raise PackError(
            2,
            f"{path.name} differs from the build its .compile.json describes "
            "(SHA-256 mismatch): the file changed after it was compiled. Use "
            "the build that was compiled and benchmarked, or recompile.",
        )
      if sidecar.get("target") not in (None, soc):
        raise PackError(
            2,
            f"{path.name}: the sidecar says {sidecar.get('target')} but the "
            f"file is stamped {soc}; the sidecar belongs to another build.",
        )
      source = sidecar.get("input_sha256")
      if source and source != fallback["sha256"]:
        if not args.allow_source_mismatch:
          raise PackError(
              2,
              f"{path.name} was compiled from a different file than "
              f"--fallback {fallback_path.name} (input SHA-256 in its "
              "sidecar). Pass the original it was compiled from, so the "
              "CPU and TPU paths run the same model, or add "
              "--allow-source-mismatch.",
          )
        notes.append(
            f"{path.name}: compiled from a different file than --fallback "
            "(--allow-source-mismatch)."
        )
      fully_compiled = sidecar.get("fully_compiled")
      if isinstance(fully_compiled, bool) and not fully_compiled:
        notes.append(
            f"{path.name}: only {sidecar.get('ops_offloaded')} / "
            f"{sidecar.get('ops_total')} ops run on the TPU; the rest run on "
            "the CPU in the app."
        )
    builds[soc] = info
  return dict(sorted(builds.items())), fallback, notes


def resolve_output_dir(args: argparse.Namespace,
                       fallback: dict[str, Any]) -> pathlib.Path:
  """Output directory of the package, checked against --overwrite."""
  if args.output_dir:
    out = pathlib.Path(args.output_dir).expanduser().resolve()
  else:
    out = fallback["path"].parent / "app_package" / args.pack_name
  if out.exists():
    if not args.overwrite:
      raise PackError(
          2,
          f"output already exists: {out}. Choose another --output-dir, or "
          "pass --overwrite to replace a package written by this script.",
      )
    if not _written_by_us(out):
      raise PackError(
          2,
          f"refusing to replace {out}: it is not empty and has no pack.json "
          "from package_ai_pack.py. Choose another --output-dir.",
      )
  return out


def _written_by_us(path: pathlib.Path) -> bool:
  """An empty directory, or a package or update plan from this script."""
  if path.is_dir() and not any(path.iterdir()):
    return True
  for summary in ("pack.json", "update.json"):
    try:
      data = json.loads((path / summary).read_text(encoding="utf-8"))
    except (OSError, ValueError):
      continue
    if isinstance(data, dict) and data.get("generator") == GENERATOR:
      return True
  return False


# --------------------------------------------------------------------------
# Export with LiteRT
# --------------------------------------------------------------------------


def installed_litert() -> str | None:
  for dist in ("ai-edge-litert", "ai-edge-litert-nightly"):
    try:
      return f"{dist} {importlib.metadata.version(dist)}"
    except importlib.metadata.PackageNotFoundError:
      continue
  return None


def export_with_litert(builds: dict[str, dict[str, Any]],
                       fallback: dict[str, Any],
                       ai_packs_dir: pathlib.Path, pack: str, model: str,
                       pip_release: str | None) -> None:
  """Writes the AI pack with ai_edge_litert.aot.ai_pack.export_lib."""
  pin = pip_release or "<pip_release in versions.json>"
  os.environ.setdefault("GOOGLE_TENSOR_BACKEND_ENABLED", "1")
  try:
    # pylint: disable=g-import-not-at-top
    from ai_edge_litert.aot.ai_pack import export_lib
    try:  # The module was renamed between LiteRT releases.
      from ai_edge_litert.aot.core import aot_types
    except ImportError:
      from ai_edge_litert.aot.core import types as aot_types
    from ai_edge_litert.aot.vendors import fallback_backend
    from ai_edge_litert.aot.vendors.google_tensor import google_tensor_backend
    # pylint: enable=g-import-not-at-top
  except ImportError as e:
    raise PackError(
        5,
        f"LiteRT's AI-pack exporter is not importable with {sys.executable} "
        f"({e}). Run this script with the Python of the venv that has "
        "ai-edge-litert (the compile venv works), or create one: "
        f"python3 -m venv ~/.venvs/litert-pack && ~/.venvs/litert-pack/bin/"
        f"pip install ai-edge-litert=={pin}. The Google Tensor SDK Beta is "
        "not needed for packaging.",
    ) from e

  try:
    tensor_backend = google_tensor_backend.GoogleTensorBackend
    models_with_backend = []
    for soc, info in builds.items():
      backend = tensor_backend.create(
          {"backend_id": tensor_backend.id(), "soc_model": soc}
      )
      models_with_backend.append(
          (backend, aot_types.Model.create_from_path(info["path"]))
      )
    other = fallback_backend.FallbackBackend
    models_with_backend.append((
        other.create({"backend_id": other.id()}),
        aot_types.Model.create_from_path(fallback["path"]),
    ))
    result = aot_types.CompilationResult(
        models_with_backend=models_with_backend
    )
    export_lib.export(result, ai_packs_dir, pack, model)
  except (AssertionError, AttributeError, KeyError, TypeError,
          ValueError) as e:
    raise PackError(
        5,
        f"LiteRT's AI-pack exporter failed ({type(e).__name__}: {e}) with "
        f"{installed_litert() or 'an unknown ai-edge-litert'}; this script "
        f"is verified with ai-edge-litert {pin}. Use that version "
        "(compile_model.py --print-install); if it already is, export_lib "
        "changed: see references/contributing.md.",
    ) from e


# --------------------------------------------------------------------------
# Generated files
# --------------------------------------------------------------------------


def render(template: str, values: dict[str, str]) -> str:
  """Fills the {{KEY}} placeholders of a skill template with ``values``."""
  path = TEMPLATES_DIR / template
  try:
    text = path.read_text(encoding="utf-8")
  except OSError as e:
    raise PackError(
        2,
        f"skill template missing: {path} ({e}). Install the whole skill "
        "folder, including assets/templates/.",
    ) from e
  for key, value in values.items():
    text = text.replace("{{" + key + "}}", value)
  left = sorted(set(PLACEHOLDER_RE.findall(text)))
  if left:
    raise PackError(
        7,
        f"template {template} has unfilled placeholders {left}: "
        "assets/templates/ and package_ai_pack.py are out of sync.",
    )
  return text


def template_values(args: argparse.Namespace, builds: dict[str, dict[str, Any]],
                    release: str, min_kotlin: str) -> dict[str, str]:
  """Values for the placeholders of the templates in assets/templates/."""
  socs = list(builds)
  groups = [group_of(s) for s in socs]
  indent = " " * 24
  module_dir = args.app_module.replace(":", "/")
  if args.delivery == "install-time":
    permissions = "nothing to add for `install-time` delivery."
  else:
    permissions = (
        f"`{args.delivery}` packs are downloaded by the Play AI Delivery "
        "library, which needs these permissions in\n"
        f"   `{module_dir}/src/main/AndroidManifest.xml`:\n\n"
        "   ```xml\n"
        '   <uses-permission android:name="android.permission.'
        'FOREGROUND_SERVICE" />\n'
        '   <uses-permission android:name="android.permission.'
        'FOREGROUND_SERVICE_DATA_SYNC" />\n'
        "   ```\n\n"
        "   The loader uses the CPU model when a download waits for Wi-Fi "
        "or for the\n"
        "   user's confirmation (downloads over 200 MB on mobile data); "
        "call\n"
        "   `AiPackManager.showConfirmationDialog()` yourself for large "
        "models."
    )
  return {
      "PACK_NAME": args.pack_name,
      "MODEL_NAME": args.model_name,
      "DELIVERY": args.delivery,
      "APP_MODULE": args.app_module,
      "APP_MODULE_DIR": module_dir,
      "APP_MODULE_LAST": args.app_module.split(":")[-1],
      "KOTLIN_PACKAGE": args.kotlin_package,
      "KOTLIN_MIN": min_kotlin,
      "LITERT_MAVEN_RELEASE": release,
      "DEVICE_GROUP_ELEMENTS": "\n".join(
          f'{indent}<dist:device-group dist:name="{g}"/>' for g in groups
      ),
      "SOC_MODELS_KOTLIN": ", ".join(f'"{soc_display(s)}"' for s in socs),
      "SOC_LIST_TEXT": ", ".join(
          f"{soc_display(s)}, {PIXEL_FAMILY.get(s, 'Pixel')}" for s in socs
      ),
      "GROUP_LIST": ", ".join(
          f"`{group_of(s)}` ({soc_display(s)}, "
          f"{PIXEL_FAMILY.get(s, 'Pixel')})" for s in socs
      ),
      "FIRST_GROUP": groups[0],
      "PERMISSIONS_STEP": permissions,
      # Filled with assets/templates/INTEGRATION_quick_test.md for --quick-test.
      "QUICK_TEST_SECTION": "",
      "FIRST_SOC": socs[0],
      "QUICK_TEST_SOCS": " and ".join(f"`{s}`" for s in socs),
  }


def read_model_io(model: pathlib.Path) -> dict[str, Any]:
  """Signatures (input/output names, shapes, types) of an uncompiled model.

  Args:
    model: The uncompiled .tflite model.

  Returns:
    {"source", "signatures"}, plus "error" if LiteRT could not read it.
  """
  data: dict[str, Any] = {"source": model.name, "signatures": []}
  try:
    # pylint: disable-next=g-import-not-at-top
    from ai_edge_litert.interpreter import Interpreter

    interpreter = Interpreter(model_path=str(model))

    def describe(details) -> dict[str, Any]:
      return {
          "shape": [int(x) for x in details["shape"]],
          "dtype": getattr(details["dtype"], "__name__",
                           str(details["dtype"])),
      }

    signatures = interpreter.get_signature_list() or {}
    for key in signatures:
      runner = interpreter.get_signature_runner(key)
      data["signatures"].append({
          "key": key,
          "inputs": [dict(name=n, **describe(d))
                     for n, d in runner.get_input_details().items()],
          "outputs": [dict(name=n, **describe(d))
                      for n, d in runner.get_output_details().items()],
      })
    if not signatures:
      data["signatures"].append({
          "key": "",
          "inputs": [dict(name=d["name"], **describe(d))
                     for d in interpreter.get_input_details()],
          "outputs": [dict(name=d["name"], **describe(d))
                      for d in interpreter.get_output_details()],
      })
  except Exception as e:  # pylint: disable=broad-exception-caught
    data["error"] = f"{type(e).__name__}: {e}"
  return data


def dump_model_io(data: dict[str, Any], path: pathlib.Path) -> None:
  """Writes read_model_io() output as model_io.json."""
  text = json.dumps(data, indent=2)
  # Keep shapes on one line: "shape": [1, 3, 224, 224].
  text = re.sub(
      r"\[\s*(-?\d+(?:\s*,\s*-?\d+)*)\s*\]",
      lambda m: "[" + ", ".join(x.strip() for x in m.group(1).split(",")) + "]",
      text,
  )
  path.write_text(text + "\n", encoding="utf-8")


def write_model_io(fallback: pathlib.Path, out: pathlib.Path) -> str | None:
  """Writes model_io.json from the original model; returns an error or None."""
  data = read_model_io(fallback)
  dump_model_io(data, out / "model_io.json")
  return data.get("error")


def tree_text(root: pathlib.Path) -> str:
  """The file tree of ``root`` for INTEGRATION.md, with notes on some files."""
  files = sorted(
      str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()
  )
  files = ["INTEGRATION.md"] + [f for f in files if f != "INTEGRATION.md"]

  def note(f: str) -> str | None:
    if f.startswith("cpu_gpu/"):
      return "-> <app module>/src/main/assets/litert/"
    if f.startswith(QUICK_TEST_DIR + "/"):
      return f"-> <app module>/{APP_QUICK_TEST_DIR}/ (optional quick test)"
    return TREE_NOTES.get(f)

  width = max(len(f) for f in files if note(f)) + 2
  return "\n".join(f"{f:<{width}}{note(f)}" if note(f) else f for f in files)


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------


def _verify_fail(message: str):
  raise PackError(7, f"post-export verification failed: {message}")


def check_exported_builds(stage: pathlib.Path, assets: pathlib.Path,
                          model: str,
                          builds: dict[str, dict[str, Any]]) -> list[str]:
  """Exporter output: one folder per SoC plus other, byte-identical builds."""
  passed: list[str] = []
  expected = {f"model#group_{group_of(s)}" for s in builds} | {OTHER_GROUP_DIR}
  found = {p.name for p in assets.iterdir()} if assets.is_dir() else set()
  if found != expected:
    _verify_fail(
        f"AI pack folders are {sorted(found)}, expected {sorted(expected)}.")
  passed.append("AI pack folders: " + ", ".join(sorted(expected)))

  for soc, info in builds.items():
    packed = assets / f"model#group_{group_of(soc)}" / f"{model}.tflite"
    if not packed.is_file():
      _verify_fail(f"missing {packed.relative_to(stage)}.")
    got = scan_model(packed)
    if got["sha256"] != info["sha256"]:
      _verify_fail(f"{packed.relative_to(stage)} is not byte-identical to "
                   f"{info['path']}.")
    if not got["compiled"] or got["soc_models"] != [soc]:
      _verify_fail(f"{packed.relative_to(stage)} is not stamped {soc}.")
    passed.append(f"{group_of(soc)}: byte-identical to {info['path'].name}, "
                  f"stamped {soc}")
  return passed


def check_exported_dtc(dtc: pathlib.Path,
                       builds: dict[str, dict[str, Any]]) -> str:
  """The exporter's XML defines exactly one Google SoC group per build."""
  groups = {group_of(s): soc_display(s) for s in builds}
  try:
    root = ET.parse(dtc).getroot()
  except (OSError, ET.ParseError) as e:
    _verify_fail(f"cannot parse {dtc.name}: {e}")
  found_groups = {}
  for group in root.findall(f"{{{DTC_NS}}}device-group"):
    socs = [(s.get("manufacturer"), s.get("model"))
            for s in group.iter(f"{{{DTC_NS}}}system-on-chip")]
    found_groups[group.get("name")] = socs
  want = {g: [("Google", m)] for g, m in groups.items()}
  if found_groups != want:
    _verify_fail(f"{dtc.name} defines {found_groups}, expected {want}.")
  return "device_targeting_configuration.xml: " + ", ".join(
      f'{g} = Google "{m}"' for g, m in groups.items())


def verify_package(stage: pathlib.Path, args: argparse.Namespace,
                   builds: dict[str, dict[str, Any]],
                   fallback: dict[str, Any]) -> list[str]:
  """Checks the staged package; returns the list of passed checks."""
  fail = _verify_fail
  assets = stage / "ai_packs" / args.pack_name / "src" / "main" / "assets"
  passed = check_exported_builds(stage, assets, args.model_name, builds)

  other = sorted(p.name for p in (assets / OTHER_GROUP_DIR).iterdir())
  if other != [PLACEHOLDER_FILE]:
    fail(f"{OTHER_GROUP_DIR} holds {other}, expected only {PLACEHOLDER_FILE}.")
  passed.append(f"{OTHER_GROUP_DIR}: placeholder only")

  groups = {group_of(s): soc_display(s) for s in builds}
  passed.append(check_exported_dtc(
      stage / "ai_packs" / "device_targeting_configuration.xml", builds))

  manifest = stage / RUNTIME_MANIFEST
  try:
    mroot = ET.parse(manifest).getroot()
  except (OSError, ET.ParseError) as e:
    fail(f"cannot parse the runtime module manifest: {e}")
  module_groups = sorted(
      g.get(f"{{{DIST_NS}}}name")
      for g in mroot.iter(f"{{{DIST_NS}}}device-group")
  )
  if module_groups != sorted(groups):
    fail(f"google_tensor_runtime is delivered to {module_groups}, but the "
         f"AI pack defines {sorted(groups)}.")
  passed.append("google_tensor_runtime delivered to the same groups")

  cpu = stage / "cpu_gpu" / f"{args.model_name}_cpu_gpu.tflite"
  if not cpu.is_file() or scan_model(cpu)["sha256"] != fallback["sha256"]:
    fail(f"{cpu.relative_to(stage)} is not byte-identical to "
         f"{fallback['path']}.")
  passed.append(f"CPU model: byte-identical to {fallback['path'].name}")

  quick = stage / QUICK_TEST_DIR
  found = sorted(p.relative_to(stage).as_posix() for p in quick.rglob("*")
                 if p.is_file()) if quick.is_dir() else []
  want = sorted(quick_test_file(s, args.model_name)
                for s in builds) if args.quick_test else []
  if found != want:
    fail(f"quick test files are {found}, expected {want}.")
  for soc, info in builds.items() if args.quick_test else ():
    got = scan_model(stage / quick_test_file(soc, args.model_name))
    if got["sha256"] != info["sha256"] or got["soc_models"] != [soc]:
      fail(f"{quick_test_file(soc, args.model_name)} is not byte-identical "
           f"to {info['path']}.")
  if args.quick_test:
    passed.append("quick test: one byte-identical build per SoC")

  for path in stage.rglob("*"):
    if path.is_file() and path.suffix in (".kts", ".xml", ".kt", ".md"):
      left = PLACEHOLDER_RE.findall(path.read_text(encoding="utf-8"))
      if left:
        fail(f"{path.relative_to(stage)} has unfilled placeholders {left}.")
  passed.append("generated files: no unfilled placeholders")
  return passed


# --------------------------------------------------------------------------
# Update mode (--update-project): new builds for a model the app ships
# --------------------------------------------------------------------------

UPDATE_SUMMARY = "update.json"
EXPORT_PACK = "tensor_update"  # names inside the staging export only
EXPORT_MODEL = "model"
SETTINGS_FILES = ("settings.gradle.kts", "settings.gradle")
BUILD_FILES = ("build.gradle.kts", "build.gradle")
SKIP_DIRS = frozenset({"build", "out", "node_modules"})
MAX_WALK_DEPTH = 16
MAX_SOURCE_BYTES = 1 << 20
TENSOR_SOC_RE = re.compile(r"Tensor G\d+")
GROUP_DIR_RE = re.compile(r"(?P<prefix>.+)#group_(?P<group>[A-Za-z0-9_]+)")
DISPATCH_LIB_NAME = "libLiteRtDispatch_GoogleTensor.so"
LITERT_MAVEN_GROUP = "com.google.ai.edge.litert"
RUNTIME_ARTIFACT = "litert-npu-runtime-google-tensor"
CORE_ARTIFACT = "litert"
RUNTIME_AAR_URL = (
    "https://dl.google.com/dl/android/maven2/com/google/ai/edge/litert/"
    "litert-npu-runtime-google-tensor/{release}/"
    "litert-npu-runtime-google-tensor-{release}.aar"
)
BENCHMARK_SCRIPT = SKILL_DIR / "scripts" / "benchmark_on_device.py"
# The element LiteRT's exporter writes for a group; a real run takes it from
# the exporter's own output instead.
DTC_GROUP_SNIPPET = (
    '<config:device-group name="{group}">\n'
    "    <config:device-selector>\n"
    '        <config:system-on-chip manufacturer="Google" model="{model}"/>\n'
    "    </config:device-selector>\n"
    "</config:device-group>"
)
VERDICTS = {
    "drop-in": "drop-in: only the model files change",
    "structural": "structural: the model files plus other changes",
    "up-to-date": "up to date: the project already has these exact files",
}
DELIVERY_UPDATE = {
    "install-time": "Phones get the new model with the app update.",
    "fast-follow": (
        "The app update invalidates the pack downloaded before; Google Play "
        "downloads the new one automatically right after the update."
    ),
    "on-demand": (
        "The app update invalidates the pack downloaded before; the new one "
        "is downloaded the next time the app requests it."
    ),
}

_COMMENT_RE = re.compile(
    r"(\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*')|//[^\n]*|/\*.*?\*/", re.S
)
_QUOTED_RE = re.compile(r"[\"'](:?[\w.\-:]+)[\"']")
_INCLUDE_RE = re.compile(r"\binclude\s*\(([^)]*)\)|\binclude[ \t]+([^\n]+)")
_PROJECT_DIR_RE = re.compile(
    r"project\(\s*[\"'](:?[\w.\-:]+)[\"']\s*\)\s*\.projectDir\s*=\s*"
    r"(?:file|File|new\s+File)\s*\(\s*(?:(?:settingsDir|rootDir)\s*,\s*)?"
    r"[\"']([^\"']+)[\"']"
)
_PACK_BLOCK_RE = re.compile(r"\b(aiPack|assetPack)\s*\{")
_SETTER = r"\s*(?:=|\.set\s*\(|[ \t]+)\s*"
_PACK_NAME_RE = re.compile(r"\bpackName\b" + _SETTER + r"[\"']([^\"']+)[\"']")
_DELIVERY_RE = re.compile(
    r"\bdeliveryType\b" + _SETTER + r"[\"']([\w\-]+)[\"']")
_DEFAULT_GROUP_RE = re.compile(
    r"\bdefaultGroup\b" + _SETTER + r"[\"']([A-Za-z0-9_]+)[\"']")
_DTC_RE = re.compile(
    r"\bdeviceTargetingConfig\b\s*(?:=|\.set\s*\()?\s*"
    r"(?P<fn>rootProject\.file|project\.file|layout\.projectDirectory\.file|"
    r"file)\s*\(\s*[\"'](?P<path>[^\"']+)[\"']"
)
_VERSION_CODE_RE = re.compile(r"\bversionCode\b\s*(?:=\s*|[ \t]+)(\d+)")
_APP_ID_RE = re.compile(
    r"\bapplicationId\b\s*(?:=\s*|[ \t]+)[\"']([\w.]+)[\"']")
_LOADER_CONSTS = {
    "pack": re.compile(r"\bAI_PACK_NAME\s*=\s*\"([^\"]*)\""),
    "model_path": re.compile(r"\bPACK_MODEL_PATH\s*=\s*\"([^\"]*)\""),
    "cpu_asset": re.compile(r"\bCPU_MODEL_ASSET\s*=\s*\"([^\"]*)\""),
    "delivery": re.compile(r"\bDELIVERY\s*=\s*\"([^\"]*)\""),
}
_LOADER_SOCS_RE = re.compile(
    r"\bPACKAGED_SOC_MODELS\b[^=\n]*=\s*setOf\(([^)]*)\)")


def _read_text(path: pathlib.Path) -> str:
  try:
    return path.read_text(encoding="utf-8", errors="replace")
  except OSError:
    return ""


def _strip_comments(text: str) -> str:
  """Gradle (Kotlin or Groovy) source without its // and /* */ comments."""
  return _COMMENT_RE.sub(lambda m: m.group(1) or "", text)


def _rel(path: pathlib.Path, root: pathlib.Path) -> str:
  try:
    return path.relative_to(root).as_posix()
  except ValueError:
    return str(path)


def _walk(top: pathlib.Path, max_depth: int = MAX_WALK_DEPTH):
  """os.walk below ``top``, skipping build outputs and hidden folders."""
  base = len(top.parts)
  for dirpath, dirnames, filenames in os.walk(top):
    here = pathlib.Path(dirpath)
    if len(here.parts) - base >= max_depth:
      dirnames[:] = []
    else:
      dirnames[:] = sorted(d for d in dirnames
                           if d not in SKIP_DIRS and not d.startswith("."))
    yield here, dirnames, sorted(filenames)


def _sha256(path: pathlib.Path) -> str:
  digest = hashlib.sha256()
  with open(path, "rb") as f:
    for chunk in iter(lambda: f.read(1 << 20), b""):
      digest.update(chunk)
  return digest.hexdigest()


def project_root(raw: str) -> tuple[pathlib.Path, pathlib.Path]:
  """(root, settings file) of the Gradle project given to --update-project."""
  root = pathlib.Path(raw).expanduser().resolve()
  if not root.is_dir():
    raise PackError(2, f"--update-project {root} is not a directory.")
  for name in SETTINGS_FILES:
    if (root / name).is_file():
      return root, root / name
  hint = ""
  for parent in list(root.parents)[:3]:
    if any((parent / name).is_file() for name in SETTINGS_FILES):
      hint = f" {parent} has one: is that the project root?"
      break
  raise PackError(
      2,
      f"no settings.gradle.kts or settings.gradle in {root}. Pass the root "
      f"folder of the app's Gradle project to --update-project.{hint}",
  )


def parse_settings(root: pathlib.Path,
                   settings: pathlib.Path) -> dict[str, pathlib.Path]:
  """{Gradle path: module directory} from the include lines of settings."""
  text = _strip_comments(_read_text(settings))
  modules: dict[str, pathlib.Path] = {}
  for m in _INCLUDE_RE.finditer(text):
    for path in _QUOTED_RE.findall(m.group(1) or m.group(2) or ""):
      gradle_path = ":" + path.lstrip(":")
      modules[gradle_path] = root.joinpath(*gradle_path[1:].split(":"))
  for m in _PROJECT_DIR_RE.finditer(text):
    modules[":" + m.group(1).lstrip(":")] = (root / m.group(2)).resolve()
  return modules


def inspect_project(raw_root: str) -> dict[str, Any]:
  """Reads the app's Gradle project; never writes to it."""
  root, settings = project_root(raw_root)
  gradle_paths = parse_settings(root, settings)
  by_dir = {d: p for p, d in gradle_paths.items()}
  modules, so_files, sources = [], [], []
  for here, _, files in _walk(root):
    build = next((name for name in BUILD_FILES if name in files), None)
    if build:
      modules.append({
          "dir": here,
          "rel": _rel(here, root),
          "build_file": _rel(here / build, root),
          "text": _strip_comments(_read_text(here / build)),
          "gradle_path": ":" if here == root else by_dir.get(here),
      })
    if DISPATCH_LIB_NAME in files:
      so_files.append(here / DISPATCH_LIB_NAME)
    if "src" in here.relative_to(root).parts:
      for name in files:
        path = here / name
        if name.endswith((".kt", ".java")) and _small(path):
          text = _read_text(path)
          if "SOC_MODEL" in text:
            sources.append((path, text))
  catalog, catalog_error = read_catalog(root)
  return {
      "root": root,
      "settings_rel": _rel(settings, root),
      "settings_text": _strip_comments(_read_text(settings)),
      "gradle_paths": set(gradle_paths),
      "modules": modules,
      "so_files": so_files,
      "sources": sources,
      "catalog": catalog,
      "catalog_error": catalog_error,
      "properties": _read_text(root / "gradle.properties"),
  }


def _small(path: pathlib.Path) -> bool:
  try:
    return path.stat().st_size <= MAX_SOURCE_BYTES
  except OSError:
    return False


def find_packs(project: dict[str, Any]) -> list[dict[str, Any]]:
  """AI packs (or asset packs) with device-group folders in their assets."""
  packs = []
  for module in project["modules"]:
    block = _PACK_BLOCK_RE.search(module["text"])
    assets = module["dir"] / "src" / "main" / "assets"
    if not block or not assets.is_dir():
      continue
    group_dirs = []
    for here, dirnames, _ in _walk(assets, max_depth=4):
      for name in list(dirnames):
        m = GROUP_DIR_RE.fullmatch(name)
        if m:
          dirnames.remove(name)
          group_dirs.append({
              "dir": here / name,
              "prefix": _rel(here / m.group("prefix"), assets),
              "group": m.group("group"),
          })
    if not group_dirs:
      continue
    name = _PACK_NAME_RE.search(module["text"])
    delivery = _DELIVERY_RE.search(module["text"])
    packs.append({
        "module": module,
        "kind": block.group(1),
        "name": name.group(1) if name else module["dir"].name,
        "delivery": (delivery.group(1) if delivery
                     and delivery.group(1) in DELIVERY_TYPES else None),
        "assets": assets,
        "group_dirs": group_dirs,
    })
  return packs


def find_dtcs(project: dict[str, Any]) -> list[dict[str, Any]]:
  """Device-targeting configs named by deviceTargetingConfig = file(...)."""
  root = project["root"]
  found = []
  for module in project["modules"]:
    m = _DTC_RE.search(module["text"])
    if not m:
      continue
    path = pathlib.Path(m.group("path")).expanduser()
    if not path.is_absolute():
      base = root if m.group("fn") == "rootProject.file" else module["dir"]
      path = base / path
    found.append({
        "module": module,
        "path": path,
        "rel": _rel(path, root),
        "groups": parse_dtc(path) if path.is_file() else None,
    })
  return found


def parse_dtc(path: pathlib.Path) -> dict[str, dict[str, Any]]:
  """{group name: {"socs": [(manufacturer, model), ...]}} of an XML config."""
  try:
    tree = ET.parse(path).getroot()
  except (OSError, ET.ParseError) as e:
    raise PackError(
        2,
        f"cannot read the app's device-targeting config {path} ({e}). "
        "bundletool cannot use it either: fix the XML, then re-run.",
    ) from e
  groups = {}
  for group in tree.iter(f"{{{DTC_NS}}}device-group"):
    groups[group.get("name")] = {"socs": [
        (s.get("manufacturer"), s.get("model"))
        for s in group.iter(f"{{{DTC_NS}}}system-on-chip")
    ]}
  return groups


def group_soc(info: dict[str, Any] | None) -> str | None:
  """'Tensor_G5' for a group that selects exactly one Google Tensor SoC.

  'several' when it selects a Google Tensor SoC among others (a compiled
  build runs on one SoC only); None when it selects no Google Tensor SoC.

  Args:
    info: A device group from parse_dtc(), or None.

  Returns:
    The SoC (e.g. 'Tensor_G5'), 'several' or None, as described above.
  """
  if not info:
    return None
  tensor = [model for maker, model in info["socs"]
            if maker == "Google" and model and TENSOR_SOC_RE.fullmatch(model)]
  if not tensor:
    return None
  if len(info["socs"]) > 1:
    return "several"
  return tensor[0].replace(" ", "_")


def _stamped_socs(group_dir: pathlib.Path) -> list[str]:
  socs = []
  for path in sorted(group_dir.glob("*.tflite")):
    info = scan_model(path)
    if info["compiled"] and info["google_tensor"]:
      socs += info["soc_models"]
  return socs


def app_module_for(pack: dict[str, Any], project: dict[str, Any],
                   args: argparse.Namespace) -> dict[str, Any] | None:
  """The module whose assetPacks lists ``pack`` (or the --app-module)."""
  modules = project["modules"]
  if "app_module" in args.explicit:
    want = args.app_module.strip(":")
    for module in modules:
      if ((module["gradle_path"] or "").strip(":") == want
          or module["rel"] == want.replace(":", "/")):
        return module
    raise PackError(
        2,
        f"--app-module {args.app_module}: no such module in "
        f"{project['root']}.",
    )
  pack_module = pack["module"]
  hits = []
  for module in modules:
    if module is pack_module or "assetPacks" not in module["text"]:
      continue
    paths = re.findall(r"[\"'](:[\w.\-:]+)[\"']", module["text"])
    if pack_module["gradle_path"] in paths or any(
        p.rsplit(":", 1)[-1] == pack_module["dir"].name for p in paths):
      hits.append(module)
  return hits[0] if len(hits) == 1 else None


def read_catalog(root: pathlib.Path) -> tuple[dict[str, Any], str | None]:
  """Libraries, plugins and versions of gradle/libs.versions.toml."""
  catalog: dict[str, Any] = {"libraries": {}, "plugins": {}, "versions": {}}
  path = root / "gradle" / "libs.versions.toml"
  if not path.is_file():
    return catalog, None
  text = _read_text(path)
  try:
    import tomllib  # pylint: disable=g-import-not-at-top
  except ImportError:  # Python < 3.11
    data = _mini_toml(text)
  else:
    try:
      data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
      return catalog, (f"cannot parse {path} ({e}); versions declared there "
                       "are unknown")
  versions = data.get("versions") or {}
  catalog["versions"] = versions
  for alias, spec in (data.get("libraries") or {}).items():
    group = name = version = None
    if isinstance(spec, str):
      parts = spec.split(":")
      group, name = (parts + [None, None])[:2]
      version = parts[2] if len(parts) > 2 else None
    elif isinstance(spec, dict):
      if isinstance(spec.get("module"), str):
        group, _, name = spec["module"].partition(":")
      else:
        group, name = spec.get("group"), spec.get("name")
      version = _catalog_version(spec.get("version", spec), versions)
    catalog["libraries"][alias] = {"group": group, "name": name,
                                   "version": version}
  for alias, spec in (data.get("plugins") or {}).items():
    plugin_id = version = None
    if isinstance(spec, str):
      plugin_id, _, version = spec.partition(":")
    elif isinstance(spec, dict):
      plugin_id = spec.get("id")
      version = _catalog_version(spec.get("version", spec), versions)
    catalog["plugins"][alias] = {"id": plugin_id, "version": version or None}
  return catalog, None


def _catalog_version(value, versions: dict[str, Any]) -> str | None:
  if isinstance(value, str):
    return value
  if isinstance(value, dict):
    if isinstance(value.get("ref"), str):
      return _catalog_version(versions.get(value["ref"]), {})
    for key in ("strictly", "require", "prefer"):
      if isinstance(value.get(key), str):
        return value[key]
  return None


def _mini_toml(text: str) -> dict[str, Any]:
  """The [versions] and [libraries] tables, for Pythons without tomllib."""
  data: dict[str, Any] = {}
  table = None
  for raw in text.splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
      continue
    header = re.fullmatch(r"\[\s*([\w.\-]+)\s*\]", line)
    if header:
      table = data.setdefault(header.group(1), {})
      continue
    entry = re.fullmatch(r"([\w.\-]+|\"[^\"]+\")\s*=\s*(.+)", line)
    if table is None or not entry:
      continue
    key, value = entry.group(1).strip('"'), entry.group(2).strip()
    if value.startswith("{"):
      item: dict[str, Any] = {}
      for k, v in re.findall(r"([\w.\-]+)\s*=\s*\"([^\"]*)\"", value):
        *parents, last = k.split(".")
        target = item
        for parent in parents:
          target = target.setdefault(parent, {})
        target[last] = v
      table[key] = item
    else:
      string = re.match(r"\"([^\"]*)\"", value)
      if string:
        table[key] = string.group(1)
  return data


def _resolve_version(raw: str, texts: list[str], properties: str,
                     catalog: dict[str, Any]) -> str | None:
  """A dependency version from a build file, following one variable."""
  if "$" not in raw:
    return raw
  ref = re.fullmatch(r"\$\{libs\.versions\.([\w.]+)\.get\(\)\}", raw)
  if ref:
    for key, value in catalog["versions"].items():
      if re.sub(r"[-_.]", ".", key) == ref.group(1):
        return _catalog_version(value, {})
    return None
  var = re.fullmatch(r"\$\{?([A-Za-z_]\w*)\}?", raw)
  if not var:
    return None
  name = re.escape(var.group(1))
  value = r"[\"']([^\"'$]+)[\"']"
  patterns = (
      rf"\b(?:val|var|def)\s+{name}\b(?:\s*:\s*String)?\s*=\s*{value}",
      rf"\bext\.{name}\s*=\s*{value}",
      rf"\bextra\[\s*\"{name}\"\s*\]\s*=\s*{value}",
      rf"\bset\(\s*\"{name}\"\s*,\s*{value}\s*\)",
      rf"(?m)^\s*{name}\s*=\s*{value}",
  )
  for text in texts:
    for pattern in patterns:
      hit = re.search(pattern, text)
      if hit:
        return hit.group(1)
  hit = re.search(rf"(?m)^\s*{name}\s*[=:]\s*([^\s#]+)", properties)
  return hit.group(1) if hit else None


def detect_runtime(project: dict[str, Any]) -> dict[str, Any]:
  """Where the app gets LiteRT and the Google Tensor dispatch library."""
  root = project["root"]
  catalog = project["catalog"]
  root_text = next(
      (m["text"] for m in project["modules"] if m["dir"] == root), "")
  found: dict[str, Any] = {"runtime": [], "core": [], "local_aars": [],
                           "so_files": []}
  for module in project["modules"]:
    text = module["text"]
    for key, artifact in (("runtime", RUNTIME_ARTIFACT),
                          ("core", CORE_ARTIFACT)):
      coordinate = re.compile(rf"[\"']{re.escape(LITERT_MAVEN_GROUP)}:"
                              rf"{re.escape(artifact)}:([^\"']+)[\"']")
      for m in coordinate.finditer(text):
        found[key].append({
            "module": module["rel"],
            "declared": f"{LITERT_MAVEN_GROUP}:{artifact}:{m.group(1)}",
            "version": _resolve_version(m.group(1), [text, root_text],
                                        project["properties"], catalog),
        })
      for alias, lib in catalog["libraries"].items():
        if (lib["group"], lib["name"]) != (LITERT_MAVEN_GROUP, artifact):
          continue
        accessor = "libs." + re.sub(r"[-_.]", ".", alias)
        if re.search(rf"\b{re.escape(accessor)}(?:\.asProvider\(\))?"
                     r"(?![\w.])", text):
          found[key].append({
              "module": module["rel"],
              "declared": f"{accessor} (gradle/libs.versions.toml)",
              "version": lib["version"],
          })
    for m in re.finditer(
        rf"[\"']([^\"']*{RUNTIME_ARTIFACT}[^\"']*\.aar)[\"']", text):
      found["local_aars"].append({"module": module["rel"],
                                  "path": m.group(1)})
  for path in project["so_files"]:
    found["so_files"].append({"path": _rel(path, root),
                              "sha256": _sha256(path),
                              "size_bytes": path.stat().st_size})
  return found


def runtime_delivery(project: dict[str, Any],
                     runtime: dict[str, Any]) -> list[dict[str, Any]]:
  """Modules holding the runtime, with the device groups they target."""
  root = project["root"]
  holders = {r["module"] for r in runtime["runtime"] + runtime["local_aars"]}
  for so in runtime["so_files"]:
    path = root / so["path"]
    owners = [m for m in project["modules"] if m["dir"] in path.parents]
    if owners:
      holders.add(max(owners, key=lambda m: len(m["dir"].parts))["rel"])
  result = []
  for module in project["modules"]:
    if module["rel"] not in holders:
      continue
    manifest = module["dir"] / "src" / "main" / "AndroidManifest.xml"
    groups: list[str] = []
    try:
      tree = ET.parse(manifest).getroot()
      groups = [g.get(f"{{{DIST_NS}}}name")
                for g in tree.iter(f"{{{DIST_NS}}}device-group")]
    except (OSError, ET.ParseError):
      pass
    result.append({"module": module["rel"],
                   "manifest": _rel(manifest, root), "groups": groups})
  return result


def find_loader(project: dict[str, Any],
                pack_name: str) -> dict[str, Any] | None:
  """The app's TensorModelLoader (written by this skill) for the pack."""
  for path, text in project["sources"]:
    if "PACKAGED_SOC_MODELS" not in text:
      continue
    loader: dict[str, Any] = {"file": _rel(path, project["root"])}
    for key, pattern in _LOADER_CONSTS.items():
      m = pattern.search(text)
      loader[key] = m.group(1) if m else None
    if loader["pack"] not in (None, pack_name):
      continue
    m = _LOADER_SOCS_RE.search(text)
    loader["socs"] = re.findall(r"\"([^\"]+)\"", m.group(1)) if m else None
    return loader
  return None


def locate_cpu_models(project: dict[str, Any], pack: dict[str, Any],
                      prefix: str, file_rel: str, default_group: str,
                      loader: dict[str, Any] | None, args: argparse.Namespace
                      ) -> tuple[list[pathlib.Path], str]:
  """The app's uncompiled copies of the model, and where they live."""
  root = project["root"]
  if args.cpu_asset:
    if args.cpu_asset.lower() == "none":
      return [], "none"
    path = pathlib.Path(args.cpu_asset).expanduser()
    path = (path if path.is_absolute() else root / path).resolve()
    if root not in path.parents or not path.is_file():
      raise PackError(
          2, f"--cpu-asset {args.cpu_asset}: no such file in {root}.")
    return [path], "custom"
  in_pack = pack["assets"] / f"{prefix}#group_{default_group}" / file_rel
  stem = pathlib.PurePosixPath(file_rel).stem
  names = [f"litert/{stem}_cpu_gpu.tflite"]
  if loader and loader.get("cpu_asset") and loader["cpu_asset"] not in names:
    names.insert(0, loader["cpu_asset"])
  in_base = []
  for module in project["modules"]:
    if module is pack["module"]:
      continue
    for name in names:
      path = module["dir"] / "src" / "main" / "assets" / name
      if path.is_file() and path not in in_base:
        in_base.append(path)
  found = ([in_pack] if in_pack.is_file() else []) + in_base
  if not found:
    seen = []
    for module in project["modules"]:
      assets = module["dir"] / "src" / "main" / "assets"
      if module is pack["module"] or not assets.is_dir():
        continue
      for here, _, files in _walk(assets, max_depth=4):
        seen += [_rel(here / f, root) for f in files if f.endswith(".tflite")]
    hint = (f" Models in the app's assets: {', '.join(seen[:5])}."
            if seen else "")
    raise PackError(
        2,
        "cannot tell where the app keeps the original (CPU) model of "
        f"{prefix}/{file_rel}: it is neither in {_rel(in_pack, root)} nor at "
        f"<module>/src/main/assets/{names[-1]}.{hint} Pass --cpu-asset "
        "<path in the project>, or --cpu-asset none if the app keeps no "
        "CPU copy.",
    )
  if in_pack.is_file():
    return found, "pack+base" if in_base else "pack"
  return found, "base"


def _file_entry(root: pathlib.Path, path: pathlib.Path, role: str,
                soc: str | None, group: str | None, new: dict[str, Any],
                old_scan: dict[str, Any] | None = None) -> dict[str, Any]:
  """Update-plan entry for one project file: its action, old and new model."""
  if old_scan is None and path.is_file():
    old_scan = scan_model(path)
  old = None
  if old_scan:
    old = {key: old_scan.get(key) for key in (
        "sha256", "size_bytes", "compiled", "soc_models", "legacy_ops")}
  if old is None:
    action = "add"
  elif old["sha256"] == new["sha256"]:
    action = "unchanged"
  else:
    action = "replace"
  return {
      "path": _rel(path, root),
      "role": role,
      "soc": soc,
      "group": group,
      "action": action,
      "source": str(new["path"]),
      "new": {"sha256": new["sha256"], "size_bytes": new["size_bytes"]},
      "old": old,
  }


def _verdict(files: list[dict[str, Any]], edits: list[dict[str, Any]]) -> str:
  if edits:
    return "structural"
  if all(f["action"] == "unchanged" for f in files):
    return "up-to-date"
  return "drop-in"


def _socs_text(socs) -> str:
  return ", ".join(soc_display(s) for s in socs) or "none"


def plan_update(args: argparse.Namespace, builds: dict[str, dict[str, Any]],
                fallback: dict[str, Any], project: dict[str, Any],
                pins: dict[str, Any], notes: list[str]) -> dict[str, Any]:
  """What to copy into the app, and what else the update needs."""
  root = project["root"]
  if project["catalog_error"]:
    notes.append(project["catalog_error"] + ".")
  packs = find_packs(project)
  dtcs = find_dtcs(project)
  for d in dtcs:
    if d["groups"] is None:
      notes.append(f"{d['module']['build_file']} names the device-targeting "
                   f"config {d['rel']}, which does not exist.")
  usable = [d for d in dtcs if d["groups"] is not None]

  # 1. The AI pack with the Google Tensor builds.
  candidates = []
  for pack in packs:
    app = app_module_for(pack, project, args)
    own = [d for d in usable if app is not None and d["module"] is app]
    dtc = own[0] if own else (usable[0] if len(usable) == 1 else None)
    groups = dtc["groups"] if dtc else {}
    tensor = any(group_soc(groups.get(g["group"])) for g in pack["group_dirs"])
    if not tensor and dtc is None:
      tensor = any(_stamped_socs(g["dir"]) for g in pack["group_dirs"])
    if tensor:
      candidates.append((pack, app, dtc))
  if not candidates:
    raise PackError(
        2,
        f"no AI pack with Google Tensor builds in {root} (looked for modules "
        "with an aiPack or assetPack block and src/main/assets/<folder>"
        "#group_<device group>/ folders). If the app has no Google Tensor "
        "setup yet, this is a new integration: run without --update-project "
        "and follow INTEGRATION.md.",
    )
  listed = ", ".join(f"{p['name']} ({p['module']['rel']})"
                     for p, _, _ in candidates)
  if args.pack_name:
    candidates = [c for c in candidates if args.pack_name in (
        c[0]["name"], c[0]["module"]["dir"].name)]
    if not candidates:
      raise PackError(
          2,
          f"--pack-name {args.pack_name}: no AI pack with Google Tensor "
          f"builds has that name. Found: {listed}.",
      )
  if len(candidates) > 1:
    raise PackError(
        2,
        f"several AI packs ship Google Tensor builds: {listed}. Pass "
        "--pack-name to pick one.",
    )
  pack, app, dtc = candidates[0]
  dtc_groups = dtc["groups"] if dtc else {}
  dtc_rel = dtc["rel"] if dtc else None
  default_group = "other"
  if app:
    m = _DEFAULT_GROUP_RE.search(app["text"])
    default_group = m.group(1) if m else default_group
  delivery = pack["delivery"]
  if "delivery" in args.explicit:
    if delivery and args.delivery != delivery:
      raise PackError(
          2,
          f"the AI pack {pack['name']} uses {delivery} delivery "
          f"({pack['module']['build_file']}), and --update-project keeps it. "
          "Drop --delivery, or change deliveryType there first.",
      )
    if not delivery:
      delivery = args.delivery
      notes.append(f"no deliveryType in {pack['module']['build_file']}; "
                   f"UPDATE.md assumes --delivery {delivery}.")

  # 2. The model in the pack: <prefix>#group_<group>/<file>.
  models: dict[tuple[str, str], int] = {}
  for g in pack["group_dirs"]:
    if g["group"] == default_group:
      continue
    for here, _, files in _walk(g["dir"], max_depth=3):
      for name in files:
        if name.endswith(".tflite"):
          key = (g["prefix"], _rel(here / name, g["dir"]))
          models[key] = models.get(key, 0) + 1
  shown = ", ".join(f"{p}/{f}" for p, f in models) or "none"
  keys = list(models)
  if args.model_name:
    want = args.model_name
    want = want[: -len(".tflite")] if want.endswith(".tflite") else want
    keys = [k for k in keys if pathlib.PurePosixPath(k[1]).stem == want]
    if not keys:
      raise PackError(
          2,
          f"--model-name {args.model_name}: no such model in the AI pack "
          f"{pack['name']}. Found: {shown}.",
      )
  if len(keys) > 1:
    raise PackError(
        2,
        f"the AI pack {pack['name']} holds several models: {shown}. Pass "
        "--model-name to pick one.",
    )
  if not keys:
    raise PackError(
        2, f"the AI pack {pack['name']} has no .tflite in its device-group "
        "folders.")
  prefix, file_rel = keys[0]
  model_path = f"{prefix}/{file_rel}"

  # 3. Its device groups, matched to SoCs by the XML (else by the stamps).
  by_group = {}
  for g in pack["group_dirs"]:
    if g["prefix"] != prefix or g["group"] == default_group:
      continue
    name = g["group"]
    current = g["dir"] / file_rel
    scan = scan_model(current) if current.is_file() else None
    stamp = (scan["soc_models"][0] if scan and scan["compiled"]
             and len(scan["soc_models"]) == 1 else None)
    if name in dtc_groups:
      soc = group_soc(dtc_groups[name])
      if soc == "several":
        socs = ", ".join(f"{a} {b}" for a, b in dtc_groups[name]["socs"])
        raise PackError(
            2,
            f"device group {name} in {dtc_rel} selects several SoCs "
            f"({socs}), but a compiled build runs on one SoC only. Give "
            "each SoC its own group (as LiteRT's exporter does), then re-run.",
        )
      if soc and stamp and stamp != soc:
        notes.append(
            f"{_rel(current, root)} is stamped {stamp}, but group {name} "
            f"selects {soc_display(soc)}: those phones get the wrong build "
            f"today. The update puts the {soc} build there.")
    else:
      soc = stamp
      if dtc:
        notes.append(f"group {name} is not defined in {dtc_rel}; bundletool "
                     "rejects bundles whose folders use undefined groups.")
    by_group[name] = {"dir": g["dir"], "soc": soc, "current": current,
                      "scan": scan}
  managed = {n: i for n, i in by_group.items()
             if i["soc"] in SUPPORTED_TARGETS}
  others = {n: i for n, i in by_group.items() if n not in managed}
  by_soc: dict[str, list[str]] = {}
  for name, info in managed.items():
    by_soc.setdefault(info["soc"], []).append(name)
  for soc, names in by_soc.items():
    if len(names) > 1:
      raise PackError(
          2,
          f"device groups {', '.join(names)} all hold {soc_display(soc)} "
          "builds; keep one group per SoC, then re-run.",
      )

  # 4. The files to copy.
  files: list[dict[str, Any]] = []
  groups_out: list[dict[str, Any]] = []
  added: list[dict[str, Any]] = []
  for soc, build in builds.items():
    if soc in by_soc:
      name = by_soc[soc][0]
      info = managed[name]
      files.append(_file_entry(root, info["current"], "tensor", soc, name,
                               build, info["scan"]))
      groups_out.append({"group": name, "soc": soc,
                         "action": files[-1]["action"]})
      continue
    defined = [n for n, g in dtc_groups.items() if group_soc(g) == soc]
    if len(defined) > 1:
      raise PackError(
          2,
          f"device groups {', '.join(defined)} in {dtc_rel} all select "
          f"{soc_display(soc)}; keep one group per SoC, then re-run.",
      )
    name = defined[0] if defined else group_of(soc)
    if not defined and name in dtc_groups:
      raise PackError(
          2,
          f"{dtc_rel} already defines a group {name} that does not select "
          f"{soc_display(soc)}; rename that group, then re-run.",
      )
    path = pack["assets"] / f"{prefix}#group_{name}" / file_rel
    files.append(_file_entry(root, path, "tensor", soc, name, build))
    groups_out.append({"group": name, "soc": soc, "action": "add"})
    added.append({"soc": soc, "group": name, "defined": bool(defined)})
  removed = [{"soc": i["soc"], "group": n, "dir": _rel(i["dir"], root)}
             for n, i in managed.items() if i["soc"] not in builds]
  for r in removed:
    groups_out.append({"group": r["group"], "soc": r["soc"],
                       "action": "no new build"})
  for name, info in others.items():
    groups_out.append({"group": name, "soc": info["soc"],
                       "action": "kept (not a SoC this skill compiles for)"})

  # The optional quick-test copies (<app module>/tensor_quick_test/<SoC>/).
  if app is not None and (app["dir"] / APP_QUICK_TEST_DIR).is_dir():
    quick_dir = app["dir"] / APP_QUICK_TEST_DIR
    for soc, build in builds.items():
      path = quick_dir / soc / "assets" / model_path
      if path.is_file():
        files.append(dict(_file_entry(root, path, "tensor", soc, None, build),
                          quick_test=True))
    stale = sorted(p.name for p in quick_dir.iterdir()
                   if p.name not in builds
                   and (p / "assets" / model_path).is_file())
    if stale:
      notes.append(f"{_rel(quick_dir, root)}/ also holds builds for "
                   f"{', '.join(stale)}, which get no new build: quick tests "
                   "on those phones keep the previous model.")

  loader = find_loader(project, pack["name"])
  cpu_paths, layout = locate_cpu_models(project, pack, prefix, file_rel,
                                        default_group, loader, args)
  for path in cpu_paths:
    files.append(_file_entry(root, path, "cpu", None, None, fallback))
    old = files[-1]["old"]
    if old and old["compiled"]:
      notes.append(f"{files[-1]['path']} holds a compiled build today, which "
                   "the CPU cannot run; the update puts the original there.")
    elif old and old["legacy_ops"]:
      notes.append(f"{files[-1]['path']} holds a model compiled by another "
                   "toolchain today (Edge TPU custom op), which the CPU "
                   "cannot run; the update puts the original there.")
  for f in files:
    if f["role"] == "tensor" and f["old"] and f["old"]["legacy_ops"]:
      notes.append(f"{f['path']} holds a build from another toolchain today "
                   "(Edge TPU custom op); the update replaces it with the "
                   "LiteRT build.")

  # 5. Checks, and the changes the project needs besides the files.
  edits: list[dict[str, Any]] = []
  checks: list[dict[str, Any]] = []

  def edit(kind: str, file: str | None, summary: str,
           snippet: str | None = None, lang: str = "", **extra) -> None:
    edits.append(dict(kind=kind, file=file, summary=summary,
                      snippet=snippet, lang=lang, **extra))

  def check(name: str, status: str, detail: str) -> None:
    checks.append({"check": name, "status": status, "detail": detail})

  app_socs = sorted(i["soc"] for i in managed.values())
  if added or removed:
    check("SoCs", "edit", f"the app ships {_socs_text(app_socs)}; new builds "
          f"for {_socs_text(builds)}")
  else:
    check("SoCs", "pass", f"the app ships {_socs_text(app_socs)}, and each "
          "has a new build")
  check("Names", "pass", f"kept: pack `{pack['name']}`, `{model_path}`, "
        + ", ".join(f"{soc_display(g['soc'])} in `{g['group']}`"
                    for g in groups_out if g["soc"] in builds))
  if cpu_paths:
    copies = ", ".join(f"`{_rel(p, root)}`" for p in cpu_paths)
    if all(f["action"] == "unchanged" for f in files if f["role"] == "cpu"):
      check("CPU model", "pass", f"{copies} already holds the original the "
            "new builds were compiled from")
    else:
      check("CPU model", "pass", f"{copies} gets the new original, so the "
            "CPU path runs the same model as the Tensor builds")
  else:
    check("CPU model", "info", "none (--cpu-asset none): phones outside the "
          "Google Tensor groups, and failed TPU loads, have no model")

  runtime = detect_runtime(project)
  delivered_by = runtime_delivery(project, runtime)
  pinned = pins.get("maven_release")
  rt_versions = sorted({r["version"] or "unknown" for r in runtime["runtime"]})
  core_versions = sorted({r["version"] or "unknown" for r in runtime["core"]})
  if runtime["runtime"]:
    if rt_versions == [pinned]:
      check("Runtime", "pass", f"`{RUNTIME_ARTIFACT}` {pinned}, the release "
            "this skill pins")
      required = False
      reason = ("the app uses the release this skill pins, but the library "
                "in that Maven artifact is a different build than the "
                "benchmark's default download.")
    elif "unknown" in rt_versions:
      declared = ", ".join(sorted({f"`{r['declared']}`"
                                   for r in runtime["runtime"]}))
      check("Runtime", "device", f"the version of `{RUNTIME_ARTIFACT}` "
            f"could not be read from {declared}")
      required = True
      reason = "the version of the app's Google Tensor runtime is unknown."
    else:
      check("Runtime", "device", f"the app uses `{RUNTIME_ARTIFACT}` "
            f"{', '.join(rt_versions)}; this skill pins "
            f"{pinned or 'an unknown release'}")
      required = True
      reason = (f"the app uses `{RUNTIME_ARTIFACT}` {', '.join(rt_versions)}"
                f", not the release this skill pins ({pinned}).")
    known_core = [v for v in core_versions if v != "unknown"]
    known_rt = [v for v in rt_versions if v != "unknown"]
    if known_core and known_rt and known_core != known_rt:
      edit("runtime-versions", None,
           f"`{LITERT_MAVEN_GROUP}:litert` is {', '.join(known_core)} but "
           f"`{RUNTIME_ARTIFACT}` is {', '.join(known_rt)}: use one release "
           "for both.")
    elif "unknown" in core_versions + rt_versions:
      notes.append(f"some LiteRT versions could not be read from the build "
                   f"files; {LITERT_MAVEN_GROUP}:litert and {RUNTIME_ARTIFACT} "
                   "must be one release.")
  elif runtime["so_files"] or runtime["local_aars"]:
    where = ([s["path"] for s in runtime["so_files"]]
             + [a["path"] for a in runtime["local_aars"]])
    check("Runtime", "device", "the app bundles the Google Tensor library "
          "itself (" + ", ".join(f"`{w}`" for w in where) + "); its release "
          "is unknown")
    required = True
    reason = "the release of the Google Tensor library in the app is unknown."
  else:
    check("Runtime", "edit", "no Google Tensor NPU runtime in the project")
    edit("runtime-missing", None,
         f"No Google Tensor NPU runtime found (`{LITERT_MAVEN_GROUP}:"
         f"{RUNTIME_ARTIFACT}` or `{DISPATCH_LIB_NAME}`), so the app cannot "
         "use the TPU. Add it as INTEGRATION.md describes: run "
         "package_ai_pack.py without --update-project to get the runtime "
         "module.")
    required = True
    reason = ("the app has no Google Tensor runtime yet (section 2): test "
              "with the release this skill pins.")

  for a in added:
    soc, name = a["soc"], a["group"]
    if not a["defined"]:
      if dtc:
        edit("device-group", dtc_rel,
             f"Define the device group `{name}` for {soc_display(soc)}: add "
             "this element inside `<config:device-targeting-config>`.",
             DTC_GROUP_SNIPPET.format(group=name, model=soc_display(soc)),
             "xml", group=name)
      else:
        edit("device-group", None,
             f"The app has no device-targeting config, which the group "
             f"`{name}` needs: see step 2 of INTEGRATION.md (run "
             "package_ai_pack.py without --update-project to get it).")
    for module in delivered_by:
      if module["groups"] and name not in module["groups"]:
        edit("runtime-groups", module["manifest"],
             f"Deliver the runtime to `{name}` too: add this line next to "
             "the other `<dist:device-group>` elements.",
             f'<dist:device-group dist:name="{name}"/>', "xml")
  users = []
  for other_pack in packs:
    for g in other_pack["group_dirs"]:
      label = f"{_rel(other_pack['assets'], root)}/{g['prefix']}#group_*"
      if (other_pack is not pack or g["prefix"] != prefix) and (
          label not in users):
        users.append(label)
  if added and users:
    edit("other-group-folders", None,
         "These folders also use device groups and need a variant for "
         + ", ".join(f"`{a['group']}`" for a in added) + " too (bundletool "
         "requires the same groups everywhere): "
         + ", ".join(f"`{u}`" for u in users) + ".")
  for r in removed:
    soc, name = r["soc"], r["group"]
    edit("no-new-build", r["dir"],
         f"`{name}` ({soc_display(soc)}) gets no new build, so those phones "
         f"would keep the previous model. Compile one (`compile_model.py "
         f"--target {soc}`) and re-run with it, or remove "
         f"{soc_display(soc)} from the app: delete `{r['dir']}/` (and the "
         f"`#group_{name}` folders of other packs), the `{name}` group in "
         f"`{dtc_rel or 'the device-targeting config'}`, its "
         "`<dist:device-group>` line in the runtime module's manifest, and "
         f"\"{soc_display(soc)}\" from the loader's SoC list.")
  holding = [n for n, i in others.items() if i["current"].is_file()]
  if holding:
    edit("other-socs", None,
         "Groups " + ", ".join(f"`{n}`" for n in holding) + " are for SoCs "
         "this skill does not compile for and still hold the previous model: "
         "rebuild them with their vendor's tools, or phones will run "
         "different models.")

  cpu_files = [f for f in files if f["role"] == "cpu"]
  if not cpu_files:
    check("Model inputs/outputs", "unknown", "the app keeps no uncompiled "
          "copy to compare with; compare your code with model_io.json")
  elif all(f["action"] == "unchanged" for f in cpu_files):
    check("Model inputs/outputs", "pass", "same original model as the app's "
          "(SHA-256 match)")
  else:
    check("Model inputs/outputs", "unknown", "compared in a real run (it "
          "needs ai-edge-litert)")

  new_socs = [soc_display(s) for s in builds]
  if loader:
    if loader["model_path"] and loader["model_path"] != model_path:
      notes.append(f"{loader['file']} opens {loader['model_path']}, but the "
                   f"pack's model is {model_path}.")
    if loader["socs"] is not None and sorted(loader["socs"]) != new_socs:
      soc_list = ", ".join(f'"{s}"' for s in new_socs)
      edit("loader", loader["file"],
           "Make the loader's SoC list match the new builds:",
           f"val PACKAGED_SOC_MODELS: Set<String> = setOf({soc_list})",
           "kotlin")
      check("Loader", "edit", f"`{loader['file']}` lists "
            f"{', '.join(loader['socs']) or 'no SoC'}")
    else:
      check("Loader", "pass", f"`{loader['file']}` (TensorModelLoader) "
            "lists the same SoCs")
  else:
    detail = ("no TensorModelLoader found; the app's own loading code stays "
              "as it is")
    readers = [_rel(p, root) for p, text in project["sources"]
               if "Build.SOC_MODEL" in text]
    if added and readers:
      detail += ("; check " + ", ".join(f"`{r}`" for r in readers[:3])
                 + ": they read Build.SOC_MODEL")
    check("Loader", "info", detail)

  if delivery:
    check("Delivery", "info", f"`{delivery}` (kept). "
          f"{DELIVERY_UPDATE[delivery]}")
  else:
    check("Delivery", "unknown", "no deliveryType in "
          f"`{pack['module']['build_file']}`")
  unverified = [s for s, b in builds.items()
                if (b.get("sidecar") or {}).get("input_sha256")
                != fallback["sha256"]]
  if unverified:
    check("Provenance", "info", "not verifiable for " + ", ".join(unverified)
          + " (no .compile.json, or compiled from another file)")
  else:
    check("Provenance", "pass", "every build was compiled from --fallback "
          "(its .compile.json)")

  app_info = None
  if app:
    code = _VERSION_CODE_RE.search(app["text"])
    app_id = _APP_ID_RE.search(app["text"])
    app_info = {
        "module": app["rel"],
        "gradle_path": app["gradle_path"] or ":" + app["rel"].replace(
            "/", ":"),
        "build_file": app["build_file"],
        "version_code": int(code.group(1)) if code else None,
        "application_id": app_id.group(1) if app_id else None,
    }
  else:
    notes.append(f"no module lists the AI pack {pack['name']} in assetPacks; "
                 "pass --app-module to name the app module.")

  libraries = []
  if app_info:
    task = _bundle_task(app_info)
    libraries.append(
        f"the app bundle, which holds the library exactly as the app ships "
        f"it: `{root / _bundle_path(app_info)}` (build it in the project "
        f"with `./gradlew {task}`)")
  known = [v for v in rt_versions if v != "unknown"]
  if not runtime["runtime"] and not runtime["so_files"] and pinned:
    known = [pinned]
  for version in known:
    libraries.append(f"the Maven AAR at {version}, downloaded from "
                     f"{RUNTIME_AAR_URL.format(release=version)}")
  libraries += [f"`{root / s['path']}`" for s in runtime["so_files"]]
  libraries += [f"`{a['path']}` (declared in `{a['module']}`)"
                for a in runtime["local_aars"]]

  return {
      "project": str(root),
      "pack": {
          "name": pack["name"],
          "module": pack["module"]["rel"],
          "gradle_path": pack["module"]["gradle_path"],
          "build_file": pack["module"]["build_file"],
          "kind": pack["kind"],
          "delivery": delivery,
      },
      "model_path": model_path,
      "default_group": default_group,
      "device_targeting_config": dtc_rel,
      "app_module": app_info,
      "cpu_layout": layout,
      "groups": groups_out,
      "files": files,
      "edits": edits,
      "checks": checks,
      "runtime": {
          "pinned_maven_release": pinned,
          "maven": runtime["runtime"],
          "litert": runtime["core"],
          "so_files": runtime["so_files"],
          "local_aars": runtime["local_aars"],
          "delivered_by": delivered_by,
      },
      "loader": loader,
      "device_check": {
          "required": required,
          "reason": reason,
          "libraries": libraries,
          "builds": [[soc, str(b["path"])] for soc, b in builds.items()],
      },
      "pins": pins,
      "verdict": _verdict(files, edits),
  }


def _bundle_task(app: dict[str, Any]) -> str:
  path = app["gradle_path"].rstrip(":")
  return f"{path}:bundleRelease"


def _bundle_path(app: dict[str, Any]) -> str:
  last = app["gradle_path"].strip(":").split(":")[-1] or "app"
  base = "" if app["module"] == "." else app["module"] + "/"
  return f"{base}build/outputs/bundle/release/{last}-release.aab"


def compare_io(old: dict[str, Any],
               new: dict[str, Any]) -> tuple[str, str, list[str]]:
  """(status, detail, changes) between the app's model and the new one."""
  for data, who in ((old, "the app's model"), (new, "the new model")):
    if data.get("error"):
      return "unknown", f"could not read {who} ({data['error']})", []
  before = {s["key"]: s for s in old["signatures"]}
  after = {s["key"]: s for s in new["signatures"]}
  changes: list[str] = []
  renamed: list[str] = []
  for key in sorted(set(before) | set(after)):
    label = f"signature '{key}'" if key else "model"
    if key not in after or key not in before:
      changes.append(f"{label}: {'removed' if key not in after else 'new'}")
      continue
    for side in ("inputs", "outputs"):
      a = {t["name"]: t for t in before[key][side]}
      b = {t["name"]: t for t in after[key][side]}
      if set(a) == set(b):
        pairs = [(a[n], b[n]) for n in a]
      elif len(a) == len(b):
        pairs = list(zip(before[key][side], after[key][side]))
        renamed += [f"{x['name']} -> {y['name']}" for x, y in pairs
                    if x["name"] != y["name"]]
      else:
        changes.append(f"{label}: {len(a)} {side} -> {len(b)}")
        continue
      for x, y in pairs:
        if (x["shape"], x["dtype"]) != (y["shape"], y["dtype"]):
          changes.append(f"{label} {side[:-1]} {y['name']}: {x['dtype']} "
                         f"{x['shape']} -> {y['dtype']} {y['shape']}")
  if changes:
    return "edit", "; ".join(changes), changes
  if renamed:
    return ("info", "same shapes and types, but tensor names changed ("
            + "; ".join(renamed) + "): code that uses names needs the new "
            "ones", [])
  return "pass", "same inputs and outputs (names, shapes and types)", []


def resolve_update_output(args: argparse.Namespace, fallback: dict[str, Any],
                          pack_name: str) -> tuple[pathlib.Path, str | None]:
  """Output directory of the update plan, and a note for a dry run."""
  if args.output_dir:
    out = pathlib.Path(args.output_dir).expanduser().resolve()
  else:
    safe = re.sub(r"[^\w.\-]", "_", pack_name)
    out = fallback["path"].parent / "app_update" / safe
  if not out.exists():
    return out, None
  if not _written_by_us(out):
    raise PackError(
        2,
        f"refusing to replace {out}: it is not empty and was not written by "
        "package_ai_pack.py. Choose another --output-dir.",
    )
  if args.overwrite:
    return out, "replacing it"
  if args.dry_run:
    return out, "exists: a real run needs --overwrite"
  raise PackError(
      2,
      f"output already exists: {out}. Choose another --output-dir, or pass "
      "--overwrite to replace an update written by this script.",
  )


def _exported_group(dtc_text: str, group: str) -> str | None:
  """The exporter's <config:device-group> element for ``group``."""
  m = re.search(rf'(?ms)^([ \t]*)(<config:device-group name="'
                rf'{re.escape(group)}">.*?</config:device-group>)', dtc_text)
  if not m:
    return None
  indent = m.group(1)
  lines = m.group(2).splitlines()
  return "\n".join(
      [lines[0]] + [x[len(indent):] if x.startswith(indent) else x
                    for x in lines[1:]])


def verify_update(stage: pathlib.Path, plan: dict[str, Any],
                  root: pathlib.Path) -> list[str]:
  """Checks the staged files against the plan and the project."""

  def fail(message: str):
    raise PackError(7, f"update verification failed: {message}")

  passed: list[str] = []
  planned = set()
  for item in plan["files"]:
    if item["action"] == "unchanged":
      continue
    staged = stage / "files" / item["path"]
    planned.add(staged)
    if not staged.is_file():
      fail(f"missing files/{item['path']}.")
    got = scan_model(staged)
    if got["sha256"] != item["new"]["sha256"]:
      fail(f"files/{item['path']} is not byte-identical to {item['source']}.")
    if item["role"] == "tensor" and (
        not got["compiled"] or got["soc_models"] != [item["soc"]]):
      fail(f"files/{item['path']} is not stamped {item['soc']}.")
    if item["role"] == "cpu" and got["compiled"]:
      fail(f"files/{item['path']} is a compiled build, but the app runs it "
           "on the CPU.")
    current = root / item["path"]
    if item["action"] == "replace":
      if (not current.is_file()
          or _sha256(current) != item["old"]["sha256"]):
        fail(f"{item['path']} changed in the project while the update was "
             "prepared; re-run.")
    elif current.exists():
      fail(f"{item['path']} appeared in the project while the update was "
           "prepared; re-run.")
    kind = (f"stamped {item['soc']}" if item["role"] == "tensor"
            else "uncompiled")
    passed.append(f"files/{item['path']}: byte-identical to "
                  f"{pathlib.Path(item['source']).name}, {kind}")
  files_dir = stage / "files"
  staged_files = set(files_dir.rglob("*")) if files_dir.is_dir() else set()
  extra = sorted(_rel(p, stage) for p in staged_files
                 if p.is_file() and p not in planned)
  if extra:
    fail(f"unexpected files in the update: {extra}.")
  return passed


def update_doc_values(summary: dict[str, Any]) -> dict[str, str]:
  """Values for assets/templates/UPDATE.md."""
  pack, app = summary["pack"], summary["app_module"]
  pins = summary["pins"]

  def cell(text) -> str:
    return str(text).replace("|", "\\|")

  def state(info: dict[str, Any] | None) -> str:
    if not info:
      return "-"
    return f"{fmt_size(info['size_bytes'])}, `{info['sha256'][:12]}`"

  rows = [f"| AI pack | `{pack['name']}` (`{pack['module']}`), "
          f"`{pack['delivery'] or 'unknown'}` delivery |"]
  for g in summary["groups"]:
    label = soc_display(g["soc"]) if g["soc"] else "other SoC"
    rows.append(f"| {label} | group `{g['group']}`: {g['action']} |")
  cpu = [f for f in summary["files"] if f["role"] == "cpu"]
  rows.append("| CPU model | " + (", ".join(
      f"`{f['path']}`: {f['action']}" for f in cpu) or "none in the app")
              + " |")
  runtime = next(c for c in summary["checks"] if c["check"] == "Runtime")
  rows.append(f"| App runtime | {cell(runtime['detail'])} |")

  table = ["| File in the project | Action | Now | New |", "|---|---|---|---|"]
  for f in summary["files"]:
    what = (f"{soc_display(f['soc'])} build" if f["role"] == "tensor"
            else "CPU model")
    if f.get("quick_test"):
      what += ", quick test"
    table.append(f"| `{f['path']}` | {f['action']} ({what}) | "
                 f"{state(f['old'])} | {state(f['new'])} |")

  if summary["edits"]:
    items = []
    for i, e in enumerate(summary["edits"], 1):
      where = f"**`{e['file']}`**: " if e["file"] else ""
      item = f"{i}. {where}{e['summary']}"
      if e.get("snippet"):
        block = [f"```{e.get('lang') or ''}"] + e["snippet"].splitlines()
        item += "\n\n" + "\n".join(
            "   " + x if x else "" for x in block + ["```"])
      items.append(item)
    edits = "\n\n".join(items)
  else:
    edits = ("None: the device groups, the runtime, the Gradle files and the "
             "code stay as they are.")

  checks = "\n".join(f"| {c['check']} | {c['status']} | {cell(c['detail'])} |"
                     for c in summary["checks"])

  dc = summary["device_check"]
  device = [("Required before release: " if dc["required"]
             else "Recommended: ") + "run each new build with the Google "
            f"Tensor library the app ships, because {dc['reason']}", "",
            "```bash"]
  for soc, path in dc["builds"]:
    device += [f"# On a Pixel with {soc_display(soc)}:",
               f"python3 {shlex.quote(str(BENCHMARK_SCRIPT))} "
               f"--model {shlex.quote(path)} --dispatch-lib <LIBRARY>"]
  device += ["```", "", "`<LIBRARY>` can be:", ""]
  device += [f"- {option}" for option in dc["libraries"]] or ["- (none found)"]
  device += ["", "If the strict NPU run fails with the app's library but "
             "passes with the default download, upgrade "
             f"`{LITERT_MAVEN_GROUP}:litert` and `{RUNTIME_ARTIFACT}` "
             f"together to {pins.get('maven_release')} (Kotlin "
             f"{pins.get('kotlin_min')} or newer)."]

  first = next((g["group"] for g in summary["groups"]
                if g["action"] in ("replace", "add", "unchanged")), "<group>")
  if app:
    bundle_task = _bundle_task(app)
    bundle = _bundle_path(app)
    code = app["version_code"]
    version_step = (f"Raise `versionCode` in `{app['build_file']}`"
                    + (f" (now {code})" if code is not None else "")
                    + ": Google Play accepts a new app bundle only with a "
                    "higher one.")
  else:
    bundle_task = ":<app module>:bundleRelease"
    bundle = "<app module>/build/outputs/bundle/release/<app>-release.aab"
    version_step = ("Raise `versionCode` in the app module's build file: "
                    "Google Play accepts a new app bundle only with a higher "
                    "one.")
  app_id = (app or {}).get("application_id") or "<your.application.id>"
  commands = [
      f"./gradlew {bundle_task}",
      "java -jar bundletool-all.jar build-apks --local-testing --overwrite \\",
      f"  --bundle={bundle} --output=/tmp/app.apks",
      f"adb uninstall {app_id}",
      "java -jar bundletool-all.jar install-apks --apks=/tmp/app.apks \\",
      f"  --device-groups={first}",
  ]
  if summary["loader"]:
    commands.append("adb logcat -s LiteRtTensor  # TensorModelLoader: "
                    "\"path\":\"npu\" or \"cpu\"")
  delivery = pack["delivery"]
  return {
      "MODEL_PATH": summary["model_path"],
      "GENERATED_AT": summary["generated_at"].replace("T", " "),
      "PROJECT_DIR": summary["project"],
      "VERDICT": VERDICTS[summary["verdict"]].capitalize(),
      "SUMMARY_ROWS": "\n".join(rows),
      "FILE_TABLE": "\n".join(table),
      "EDITS": edits,
      "CHECK_ROWS": checks,
      "DEVICE_CHECK": "\n".join(device),
      "VERSION_CODE_STEP": version_step,
      "TEST_COMMANDS": "\n".join("   " + c for c in commands),
      "DELIVERY_UPDATE": (DELIVERY_UPDATE[delivery] if delivery else
                          "Google Play updates the AI pack with the app."),
  }


def build_update(plan: dict[str, Any], builds: dict[str, dict[str, Any]],
                 fallback: dict[str, Any], out: pathlib.Path,
                 versions: dict[str, Any], notes: list[str]) -> dict[str, Any]:
  """Writes the update plan into a staging directory, verifies it, moves it."""
  root = pathlib.Path(plan["project"])
  stage = out.parent / f".{out.name}.staging-{os.getpid()}"
  if stage.exists():
    shutil.rmtree(stage)
  stage.mkdir(parents=True)
  try:
    export_dir = stage / ".export"
    export_with_litert(builds, fallback, export_dir, EXPORT_PACK,
                       EXPORT_MODEL, versions.get("pip_release"))
    assets = export_dir / EXPORT_PACK / "src" / "main" / "assets"
    verification = check_exported_builds(stage, assets, EXPORT_MODEL, builds)
    original = assets / OTHER_GROUP_DIR / f"{EXPORT_MODEL}.tflite"
    if (not original.is_file()
        or scan_model(original)["sha256"] != fallback["sha256"]):
      _verify_fail("the exporter's copy of the original differs from "
                   "--fallback.")
    dtc = export_dir / "device_targeting_configuration.xml"
    verification.append(check_exported_dtc(dtc, builds))
    dtc_text = dtc.read_text(encoding="utf-8")
    for e in plan["edits"]:
      if e["kind"] == "device-group" and e["snippet"]:
        e["snippet"] = _exported_group(dtc_text, e["group"]) or e["snippet"]

    for item in plan["files"]:
      if item["action"] == "unchanged":
        continue
      dest = stage / "files" / item["path"]
      dest.parent.mkdir(parents=True, exist_ok=True)
      if item["role"] == "tensor":
        source = (assets / f"model#group_{group_of(item['soc'])}"
                  / f"{EXPORT_MODEL}.tflite")
      else:
        source = fallback["path"]
      shutil.copyfile(source, dest)
    shutil.rmtree(export_dir)

    new_io = read_model_io(fallback["path"])
    dump_model_io(new_io, stage / "model_io.json")
    app_io = None
    old = next((f for f in plan["files"] if f["role"] == "cpu"
                and f["action"] == "replace" and not f["old"]["compiled"]),
               None)
    if old:
      app_io = read_model_io(root / old["path"])
      status, detail, changes = compare_io(app_io, new_io)
      io_check = next(c for c in plan["checks"]
                      if c["check"] == "Model inputs/outputs")
      io_check.update(status=status, detail=detail)
      if changes:
        plan["edits"].append({
            "kind": "model-io", "file": None, "lang": "", "snippet": None,
            "summary": "The model's inputs or outputs changed ("
                       + "; ".join(changes) + "): update the code that fills "
                       "the inputs and reads the outputs (model_io.json "
                       "lists the new ones).",
        })
    plan["verdict"] = _verdict(plan["files"], plan["edits"])
    verification += verify_update(stage, plan, root)

    summary = {
        "generator": GENERATOR,
        "mode": "update",
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
                        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        **plan,
        "model_io": {"new": new_io, "app": app_io},
        "litert": {
            "exporter": "ai_edge_litert.aot.ai_pack.export_lib",
            "exporter_package": installed_litert(),
            "pinned_pip_release": versions.get("pip_release"),
        },
        "verification": verification,
        "notes": notes,
    }
    (stage / UPDATE_SUMMARY).write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (stage / "UPDATE.md").write_text(
        render("UPDATE.md", update_doc_values(summary)), encoding="utf-8")
    if out.exists():
      shutil.rmtree(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    os.replace(stage, out)
    return summary
  finally:
    if stage.exists():
      shutil.rmtree(stage, ignore_errors=True)


def print_update_plan(plan: dict[str, Any], out: pathlib.Path,
                      out_note: str | None, notes: list[str]) -> None:
  """Prints the dry-run plan of an update: files, verdict, edits, checks."""
  pack = plan["pack"]
  print("Dry run: inputs and project checked; nothing imported or written.")
  print(f"Project: {plan['project']}")
  print(f"AI pack: {pack['name']} ({pack['module']}, "
        f"{pack['delivery'] or 'delivery unknown'}); the app opens "
        f"{plan['model_path']}")
  for f in plan["files"]:
    old = fmt_size(f["old"]["size_bytes"]) if f["old"] else "new file"
    print(f"  {f['action']:<9} {f['path']} ({old} -> "
          f"{fmt_size(f['new']['size_bytes'])}) <- {f['source']}")
  print(f"Verdict: {VERDICTS[plan['verdict']]}")
  for i, e in enumerate(plan["edits"], 1):
    where = f"{e['file']}: " if e["file"] else ""
    print(f"  {i}. {where}{e['summary']}")
    for line in (e.get("snippet") or "").splitlines():
      print(f"       {line}")
  print("Checks:")
  for c in plan["checks"]:
    print(f"  {c['status'].upper():<7} {c['check']}: {c['detail']}")
  print(f"Would write: {out}" + (f" ({out_note})" if out_note else ""))
  for note in notes:
    print(f"NOTE: {note}")


def update_report_markdown(summary: dict[str, Any], out: pathlib.Path) -> str:
  """The Markdown summary printed after an update plan is written."""
  pack = summary["pack"]
  check = {c["check"]: c for c in summary["checks"]}
  lines = [
      f"**Update plan:** {out} ({VERDICTS[summary['verdict']]})",
      f"**Project:** {summary['project']}; AI pack `{pack['name']}` "
      f"(`{pack['module']}`, `{pack['delivery'] or 'unknown'}` delivery); "
      f"the app opens `{summary['model_path']}`",
  ]
  for f in summary["files"]:
    old = fmt_size(f["old"]["size_bytes"]) if f["old"] else "new file"
    lines.append(f"**{f['action'].capitalize()}:** `{f['path']}` ({old} -> "
                 f"{fmt_size(f['new']['size_bytes'])})")
  edits = len(summary["edits"])
  lines += [
      "**Changes outside the model files:** "
      + (f"{edits} (UPDATE.md section 2)" if edits else "none"),
      f"**App runtime:** {check['Runtime']['status']} - "
      f"{check['Runtime']['detail']}",
      "**Model inputs/outputs:** "
      f"{check['Model inputs/outputs']['status']} - "
      f"{check['Model inputs/outputs']['detail']}",
      f"**Verified:** {len(summary['verification'])} checks passed "
      "(update.json lists them)",
      f"**Next:** {out / 'UPDATE.md'}",
  ]
  return "\n".join(lines)


def main_update(args: argparse.Namespace, versions: dict[str, Any],
                versions_error: str | None) -> int:
  """--update-project: plan (and with a real run, stage) the update."""
  if "kotlin_package" in args.explicit:
    raise PackError(
        2, "--kotlin-package is not used with --update-project: the app's "
        "own code is kept.")
  if args.quick_test:
    raise PackError(
        2, f"--quick-test is not used with --update-project: an existing "
        f"{APP_QUICK_TEST_DIR}/ folder of the app module is updated with the "
        "other files.")
  builds, fallback, notes = check_inputs(args)
  try:
    pins = {"maven_release": maven_release(versions, versions_error),
            "kotlin_min": kotlin_min(versions, versions_error)}
  except PackError:
    if not args.dry_run:
      raise
    pins = {"maven_release": None, "kotlin_min": None}
  project = inspect_project(args.update_project)
  plan = plan_update(args, builds, fallback, project, pins, notes)
  out, out_note = resolve_update_output(args, fallback, plan["pack"]["name"])
  if args.dry_run:
    if args.json:
      print(json.dumps({"dry_run": True, "mode": "update",
                        "output_dir": str(out), "output_note": out_note,
                        **plan, "notes": notes}, indent=2))
    else:
      print_update_plan(plan, out, out_note, notes)
    return 0
  if not args.json:
    print(f"Preparing the update of {plan['model_path']} in AI pack "
          f"'{plan['pack']['name']}' with LiteRT's export_lib ...", flush=True)
  summary = build_update(plan, builds, fallback, out, versions, notes)
  if args.json:
    print(json.dumps(dict(status="ok", output_dir=str(out), **summary),
                     indent=2))
  else:
    for note in summary["notes"]:
      print(f"NOTE: {note}")
    print()
    print(update_report_markdown(summary, out))
  return 0


# --------------------------------------------------------------------------
# Check mode (--check-project): is the app set up for a package?
# --------------------------------------------------------------------------

MIN_SDK = 31
MIN_AGP = (8, 10)
AGP_PLUGIN_IDS = ("com.android.application",)
AGP_CLASSPATH = "com.android.tools.build:gradle"
KOTLIN_PLUGIN_IDS = ("org.jetbrains.kotlin.android",)
KOTLIN_CLASSPATH = "org.jetbrains.kotlin:kotlin-gradle-plugin"
RUNTIME_MODULE_PATH = ":litert_npu_runtime_libraries:google_tensor_runtime"
STRINGS_MODULE_PATH = ":litert_npu_runtime_libraries:runtime_strings"
DOWNLOAD_PERMISSIONS = ("android.permission.FOREGROUND_SERVICE",
                        "android.permission.FOREGROUND_SERVICE_DATA_SYNC")
DEVICE_TARGETING_FLAG = "android.experimental.enableDeviceTargetingConfigApi"
_MIN_SDK_RE = re.compile(r"\bminSdk(?:Version)?\b\s*(?:=\s*|[ \t]+|\(\s*)(\d+)")
_LEGACY_PACKAGING_RE = re.compile(
    r"\buseLegacyPackaging\b\s*(?:=\s*|[ \t]+)true")
_EXTRACT_LIBS_RE = re.compile(r"extractNativeLibs\s*=\s*\"true\"")
_ENABLE_SPLIT_RE = re.compile(r"\benableSplit\b\s*(?:=\s*|[ \t]+)true")
_KOTLIN_APPLIED_RE = re.compile(
    r"org\.jetbrains\.kotlin\.android|kotlin\(\s*\"android\"\s*\)|"
    r"[\"']kotlin-android[\"']|plugins\.kotlin\b|plugins\.jetbrains\.kotlin")
_PROJECT_DEP_RE = re.compile(
    r"project\(\s*(?:path\s*[:=]\s*)?[\"'](:[\w.\-:]+)[\"']")
QUICK_TEST_BLOCK = {
    True: (
        'providers.gradleProperty("tensorQuickTest").orNull?.let { soc ->\n'
        '  android.sourceSets.getByName("debug")\n'
        '    .assets.srcDir("tensor_quick_test/$soc/assets")\n'
        "  dependencies.add(\n"
        '    "debugImplementation",\n'
        '    "com.google.ai.edge.litert:litert-npu-runtime-google-tensor:'
        '{release}",\n'
        "  )\n"
        "}"),
    False: (
        "def soc = providers.gradleProperty('tensorQuickTest').orNull\n"
        "if (soc != null) {\n"
        '  android.sourceSets.debug.assets.srcDir("tensor_quick_test/$soc/'
        'assets")\n'
        "  dependencies.add('debugImplementation',\n"
        "      'com.google.ai.edge.litert:litert-npu-runtime-google-tensor:"
        "{release}')\n"
        "}"),
}


def _version_tuple(text: str) -> tuple[int, ...]:
  return tuple(int(x) for x in re.findall(r"\d+", text)[:3])


_APP_PLUGIN_RE = re.compile(
    r"com\.android\.application|android\.application(?![\w.])")
_APPLY_FALSE_RE = re.compile(r"[^\n]*?\bapply\s*\(?\s*false\b")
_ABI_RE = re.compile(r"[\"'](arm64-v8a|armeabi-v7a|armeabi|x86_64|x86|"
                     r"riscv64|mips64|mips)[\"']")
RUNTIME_ABI = "arm64-v8a"  # the only ABI of the Google Tensor runtime AAR


def applies_app_plugin(text: str) -> bool:
  """True if a build file applies the Android application plugin.

  A root build file that only declares it (``... apply false``) does not.

  Args:
    text: The build file's source.

  Returns:
    Whether the build file applies the plugin.
  """
  return any(not _APPLY_FALSE_RE.match(text, m.end())
             for m in _APP_PLUGIN_RE.finditer(text))


def abi_filters(text: str) -> set[str] | None:
  """The ABIs a build file's abiFilters name, or None if it sets none."""
  found = None
  for m in re.finditer(r"\babiFilters\b", text):
    end = text.find("}", m.end())
    found = (found or set()) | set(
        _ABI_RE.findall(text[m.end():None if end < 0 else end]))
  return found


def plugin_version(project: dict[str, Any], plugin_ids: tuple[str, ...],
                   classpath: str) -> tuple[str | None, str | None]:
  """(version, where) of a Gradle plugin: catalog, plugins {}, classpath."""
  for plugin in project["catalog"]["plugins"].values():
    if plugin["id"] in plugin_ids and plugin["version"]:
      return plugin["version"], "gradle/libs.versions.toml"
  sources = [(project["settings_rel"], project["settings_text"])] + [
      (m["build_file"], m["text"]) for m in project["modules"]]
  for where, text in sources:
    for plugin_id in plugin_ids:
      m = re.search(rf"\bid\s*\(?\s*[\"']{re.escape(plugin_id)}[\"']\s*\)?"
                    r"\s*version\s*\(?\s*[\"']([^\"'$]+)[\"']", text)
      if m:
        return m.group(1), where
    if "org.jetbrains.kotlin.android" in plugin_ids:
      m = re.search(r"\bkotlin\s*\(\s*\"android\"\s*\)\s*version\s*"
                    r"\"([^\"$]+)\"", text)
      if m:
        return m.group(1), where
    m = re.search(rf"[\"']{re.escape(classpath)}:([^\"'$]+)[\"']", text)
    if m:
      return m.group(1), where
  return None, None


def load_package(raw: str) -> dict[str, Any]:
  """pack.json of a package written by this script, plus its folder."""
  folder = pathlib.Path(raw).expanduser().resolve()
  try:
    data = json.loads((folder / "pack.json").read_text(encoding="utf-8"))
  except (OSError, ValueError) as e:
    raise PackError(
        2,
        f"--package {folder}: no readable pack.json ({e}). Pass the folder "
        "package_ai_pack.py wrote (the one with INTEGRATION.md).",
    ) from e
  if not isinstance(data, dict) or data.get("generator") != GENERATOR:
    raise PackError(
        2, f"{folder / 'pack.json'} was not written by package_ai_pack.py.")
  return dict(data, folder=folder)


def find_app_module(project: dict[str, Any], args: argparse.Namespace,
                    packaged: str) -> tuple[dict[str, Any], str | None]:
  """The app module (--app-module, else the package's, else the only one)."""
  wanted = (args.app_module if "app_module" in args.explicit
            else packaged).strip(":")
  for module in project["modules"]:
    if ((module["gradle_path"] or "").strip(":") == wanted
        or module["rel"] == wanted.replace(":", "/")):
      return module, None
  apps = [m for m in project["modules"] if applies_app_plugin(m["text"])]
  if len(apps) == 1 and "app_module" not in args.explicit:
    name = apps[0]["gradle_path"] or apps[0]["rel"]
    return apps[0], (f"the package was made for the app module :{wanted}; "
                     f"this project's app module is {name}")
  names = ", ".join(m["gradle_path"] or m["rel"] for m in apps) or "none"
  raise PackError(
      2,
      f"no app module :{wanted} in {project['root']} (app modules found: "
      f"{names}). Pass --app-module.",
  )


def check_integration(pkg: dict[str, Any], project: dict[str, Any],
                      args: argparse.Namespace,
                      pins: dict[str, Any]) -> dict[str, Any]:
  """Every requirement of the package's INTEGRATION.md, checked."""
  root, folder = project["root"], pkg["folder"]
  pack, model, delivery = pkg["pack_name"], pkg["model_name"], pkg["delivery"]
  litert = pkg.get("litert") or {}
  release = litert.get("maven_release") or pins.get("maven_release")
  kotlin_need = litert.get("kotlin_min") or pins.get("kotlin_min") or "0"
  socs = [v["soc"] for v in pkg["variants"]]
  app, app_note = find_app_module(project, args,
                                  pkg.get("app_module") or "app")
  app_dir, app_rel, text = app["dir"], app["rel"], app["text"]
  app_path = app["gradle_path"] or ":" + app_rel.replace("/", ":")
  build_file = app["build_file"]
  kts = build_file.endswith(".kts")
  lang = "kotlin" if kts else "groovy"
  q = '"' if kts else "'"
  prefix = "" if app_rel == "." else app_rel + "/"
  checks: list[dict[str, Any]] = []

  def add(name: str, status: str, detail: str,
          fix: dict[str, Any] | None = None, risky: bool = False) -> None:
    checks.append({"check": name, "status": status, "detail": detail,
                   "fix": None if status == "pass" else fix,
                   "risky": risky and status == "fail"})

  def copy_fix(source: str, target: str, what: str) -> dict[str, Any]:
    src, dst = folder / source, root / target
    parent = shlex.quote(str(dst.parent))
    if src.is_dir():
      command = (f"mkdir -p {parent} && cp -r {shlex.quote(str(src))} "
                 f"{parent}/")
    else:
      command = (f"mkdir -p {parent} && cp {shlex.quote(str(src))} "
                 f"{shlex.quote(str(dst))}")
    return {"action": "copy", "file": target, "text": f"Copy {what}.",
            "snippet": command, "lang": "bash", "from": source}

  def edit_fix(file: str, what: str, snippet: str | None,
               snippet_lang: str = lang) -> dict[str, Any]:
    return {"action": "edit", "file": file, "text": what,
            "snippet": snippet, "lang": snippet_lang, "from": None}

  def same(a: pathlib.Path, b: pathlib.Path) -> bool:
    return b.is_file() and _sha256(a) == _sha256(b)

  # Files from the package: AI pack, runtime modules, XML, CPU model.
  pack_rel = f"ai_packs/{pack}"
  assets = sorted(p for p in (folder / pack_rel / "src").rglob("*")
                  if p.is_file())
  missing = [p for p in assets if not (root / p.relative_to(folder)).is_file()]
  differ = [p for p in assets if p not in missing
            and not same(p, root / p.relative_to(folder))]
  pack_build = next((root / pack_rel / n for n in BUILD_FILES
                     if (root / pack_rel / n).is_file()), None)
  if pack_build is None or missing or differ:
    detail = (f"{pack_rel}/ is missing" if not (root / pack_rel).exists()
              else f"{pack_rel}/: {len(missing)} file(s) missing, "
              f"{len(differ)} differ from the package")
    add("AI pack module", "fail", detail,
        copy_fix(pack_rel, pack_rel, f"the AI pack module {pack_rel}/"),
        risky=bool(differ))
  else:
    pack_text = _strip_comments(_read_text(pack_build))
    name = _PACK_NAME_RE.search(pack_text)
    pack_delivery = _DELIVERY_RE.search(pack_text)
    if (not name or name.group(1) != pack or not pack_delivery
        or pack_delivery.group(1) != delivery):
      add("AI pack module", "fail",
          f"{_rel(pack_build, root)} does not set packName \"{pack}\" and "
          f"deliveryType \"{delivery}\"",
          copy_fix(f"{pack_rel}/build.gradle.kts",
                   f"{pack_rel}/build.gradle.kts",
                   "the package's AI pack build file"), risky=True)
    else:
      add("AI pack module", "pass",
          f"{pack_rel}/: the models are byte-identical to the package")

  for module_name, gradle_path in (("google_tensor_runtime",
                                    RUNTIME_MODULE_PATH),
                                   ("runtime_strings", STRINGS_MODULE_PATH)):
    rel = f"litert_npu_runtime_libraries/{module_name}"
    if any((root / rel / n).is_file() for n in BUILD_FILES):
      add(f"Module {gradle_path}", "pass", f"{rel}/ is there")
    else:
      add(f"Module {gradle_path}", "fail", f"{rel}/ is missing",
          copy_fix(rel, rel, f"the {module_name} module"))
  runtime_dir = root / "litert_npu_runtime_libraries" / "google_tensor_runtime"
  runtime_build = next((runtime_dir / n for n in BUILD_FILES
                        if (runtime_dir / n).is_file()), None)
  if runtime_build:
    runtime_text = _strip_comments(_read_text(runtime_build))
    problems = []
    dep = re.search(rf"[\"']{re.escape(LITERT_MAVEN_GROUP)}:"
                    rf"{re.escape(RUNTIME_ARTIFACT)}:([^\"']+)[\"']",
                    runtime_text)
    if dep and "$" not in dep.group(1) and dep.group(1) != release:
      problems.append(f"it uses {RUNTIME_ARTIFACT} {dep.group(1)}, not "
                      f"{release}")
    project_dep = _PROJECT_DEP_RE.search(runtime_text)
    if project_dep and project_dep.group(1) != app_path:
      problems.append(f"it depends on project(\"{project_dep.group(1)}\"), "
                      f"but the app module is {app_path}")
    try:
      manifest = ET.parse(runtime_dir / "src" / "main"
                          / "AndroidManifest.xml").getroot()
      module_groups = {g.get(f"{{{DIST_NS}}}name")
                       for g in manifest.iter(f"{{{DIST_NS}}}device-group")}
    except (OSError, ET.ParseError):
      module_groups = set()
    lacking = [g for g in pkg["device_groups"] if g not in module_groups]
    if lacking:
      problems.append("its manifest does not deliver it to "
                      + ", ".join(lacking))
    if problems:
      add("Runtime module content", "fail", "; ".join(problems),
          edit_fix(_rel(runtime_build, root),
                   f"Depend on project(\"{app_path}\") and "
                   f"{LITERT_MAVEN_GROUP}:{RUNTIME_ARTIFACT}:{release}, and "
                   "list the pack's device groups in its manifest (copy the "
                   "package's module again if it was not changed on "
                   "purpose).",
                   f'implementation(project("{app_path}"))\n'
                   f'implementation("{LITERT_MAVEN_GROUP}:{RUNTIME_ARTIFACT}'
                   f':{release}")', "kotlin"))
    else:
      add("Runtime module content", "pass",
          f"depends on {app_path} and {RUNTIME_ARTIFACT}, delivered to the "
          "pack's groups")

  dtc = next((d for d in find_dtcs(project) if d["module"] is app), None)
  xml_path = (dtc["path"] if dtc
              else app_dir / "device_targeting_configuration.xml")
  xml_rel = _rel(xml_path, root)
  package_xml = folder / "ai_packs" / "device_targeting_configuration.xml"
  if not xml_path.is_file():
    add("Device-targeting XML", "fail", f"{xml_rel} is missing",
        copy_fix("ai_packs/device_targeting_configuration.xml", xml_rel,
                 "the device-targeting XML"))
  else:
    want, have = parse_dtc(package_xml), parse_dtc(xml_path)
    lacking = [g for g in want if have.get(g) != want[g]]
    if lacking:
      package_text = package_xml.read_text(encoding="utf-8")
      add("Device-targeting XML", "fail",
          f"{xml_rel} does not define {', '.join(lacking)} as the package "
          "does",
          edit_fix(xml_rel, "Add (or replace) these elements inside "
                   "<config:device-targeting-config>, unchanged.",
                   "\n".join(_exported_group(package_text, g) or g
                             for g in lacking), "xml"))
    else:
      add("Device-targeting XML", "pass",
          f"{xml_rel} defines " + ", ".join(want))

  cpu = pkg["other_devices"]["cpu_model"]
  cpu_rel = f"{prefix}src/main/assets/{cpu['app_asset']}"
  if same(folder / cpu["packed_as"], root / cpu_rel):
    add("CPU model", "pass", f"{cpu_rel} is the package's original model")
  else:
    add("CPU model", "fail",
        f"{cpu_rel} is " + ("a different file" if (root / cpu_rel).is_file()
                            else "missing"),
        copy_fix(cpu["packed_as"], cpu_rel, "the original (CPU) model"),
        risky=(root / cpu_rel).is_file())

  loader = find_loader(project, pack)
  want_socs = sorted(soc_display(s) for s in socs)
  package_dir = (pkg.get("kotlin_package") or "com.example.litert").replace(
      ".", "/")
  if loader is None:
    add("Model loader", "fail",
        "no TensorModelLoader.kt for this pack in the app's sources",
        copy_fix("kotlin/TensorModelLoader.kt",
                 f"{prefix}src/main/java/{package_dir}/TensorModelLoader.kt",
                 "TensorModelLoader.kt (its package line must match the "
                 "folder it goes into)"))
  else:
    wrong = []
    if loader["model_path"] != f"model/{model}.tflite":
      wrong.append(f"it opens {loader['model_path']}")
    if loader["delivery"] != delivery:
      wrong.append(f"its DELIVERY is {loader['delivery']}")
    if loader["socs"] is not None and sorted(loader["socs"]) != want_socs:
      wrong.append("its SoC list is " + ", ".join(loader["socs"]))
    if wrong:
      add("Model loader", "fail", f"{loader['file']}: " + "; ".join(wrong),
          copy_fix("kotlin/TensorModelLoader.kt", loader["file"],
                   "the package's TensorModelLoader.kt over it (keep its "
                   "package line)"), risky=True)
    else:
      add("Model loader", "pass", f"{loader['file']} matches the package")

  quick = pkg.get("quick_test")
  if quick:
    gaps = []
    for entry in quick["files"]:
      inside = pathlib.PurePosixPath(entry["packed_as"]).relative_to(
          QUICK_TEST_DIR)
      if not same(folder / entry["packed_as"],
                  app_dir / APP_QUICK_TEST_DIR / inside):
        gaps.append(entry["soc"])
    has_block = QUICK_TEST_PROPERTY in text
    if gaps or not has_block:
      add("Quick test (optional)", "warn",
          ("no build for " + ", ".join(gaps) + "; " if gaps else "")
          + ("the Gradle block is missing" if not has_block
             else "the Gradle block is there"),
          edit_fix(build_file,
                   f"Copy the package's {QUICK_TEST_DIR}/ to "
                   f"{prefix}{APP_QUICK_TEST_DIR}/ and add this block at the "
                   "end of the app's build file.",
                   QUICK_TEST_BLOCK[kts].format(release=release)))
    else:
      add("Quick test (optional)", "pass",
          f"{prefix}{APP_QUICK_TEST_DIR}/ and the Gradle block are there")

  # settings.gradle(.kts).
  settings_rel = project["settings_rel"]
  settings_kts = settings_rel.endswith(".kts")
  need = [f":ai_packs:{pack}", STRINGS_MODULE_PATH, RUNTIME_MODULE_PATH]
  lacking = [p for p in need if p not in project["gradle_paths"]]
  if lacking:
    add("Settings includes", "fail",
        f"{settings_rel} does not include {', '.join(lacking)}",
        edit_fix(settings_rel, "Add these lines.",
                 "\n".join(f'include("{p}")' if settings_kts
                           else f"include '{p}'" for p in lacking),
                 "kotlin" if settings_kts else "groovy"))
  else:
    add("Settings includes", "pass", "the pack and both runtime modules")

  # The app module's build file.
  def quoted(gradle_path: str) -> bool:
    return bool(re.search(rf"[\"']{re.escape(gradle_path)}[\"']", text))

  if "assetPacks" in text and quoted(f":ai_packs:{pack}"):
    add("App: assetPacks", "pass", f":ai_packs:{pack} is listed")
  else:
    add("App: assetPacks", "fail", f"{build_file} does not list "
        f":ai_packs:{pack} in assetPacks",
        edit_fix(build_file, "Inside android { } (add it to the list if "
                 "assetPacks already names other packs):",
                 f'assetPacks.add(":ai_packs:{pack}")' if kts
                 else f"assetPacks = [':ai_packs:{pack}']"))
  if "dynamicFeatures" in text and quoted(RUNTIME_MODULE_PATH):
    add("App: dynamicFeatures", "pass", f"{RUNTIME_MODULE_PATH} is listed")
  else:
    add("App: dynamicFeatures", "fail", f"{build_file} does not list "
        f"{RUNTIME_MODULE_PATH} in dynamicFeatures",
        edit_fix(build_file, "Inside android { } (add it to the list if "
                 "dynamicFeatures already names other modules):",
                 f'dynamicFeatures.add("{RUNTIME_MODULE_PATH}")' if kts
                 else f"dynamicFeatures = ['{RUNTIME_MODULE_PATH}']"))
  default_group = _DEFAULT_GROUP_RE.search(text)
  bundle_issues = []
  if dtc is None:
    bundle_issues.append("no deviceTargetingConfig")
  if not _ENABLE_SPLIT_RE.search(text):
    bundle_issues.append("no deviceGroup enableSplit = true")
  if not default_group or default_group.group(1) != "other":
    bundle_issues.append("defaultGroup is not \"other\"")
  if bundle_issues:
    add("App: bundle device targeting", "fail", "; ".join(bundle_issues),
        edit_fix(build_file, "Inside android { }:",
                 "bundle {\n"
                 f"  deviceTargetingConfig = file({q}"
                 f"{_rel(xml_path, app_dir)}{q})\n"
                 "  deviceGroup {\n"
                 "    enableSplit = true\n"
                 f"    defaultGroup = {q}other{q}\n"
                 "  }\n"
                 "}"))
  else:
    add("App: bundle device targeting", "pass",
        f"deviceTargetingConfig {xml_rel}, split by device group")
  manifest_text = _read_text(app_dir / "src" / "main" / "AndroidManifest.xml")
  if _LEGACY_PACKAGING_RE.search(text) or _EXTRACT_LIBS_RE.search(
      manifest_text):
    add("App: native libraries extracted", "pass",
        "useLegacyPackaging = true")
  else:
    add("App: native libraries extracted", "fail",
        "LiteRT finds the NPU runtime by listing the native library folder, "
        "so the libraries must be extracted at install",
        edit_fix(build_file, "Inside android { }:",
                 "packaging { jniLibs { useLegacyPackaging = true } }"))
  min_sdk = _MIN_SDK_RE.search(text)
  if not min_sdk:
    add("App: minSdk", "warn", f"no minSdk in {build_file} (it may come from "
        f"a convention plugin); it must be {MIN_SDK} or higher",
        edit_fix(build_file, f"Make sure minSdk is {MIN_SDK} or higher.",
                 None))
  elif int(min_sdk.group(1)) < MIN_SDK:
    add("App: minSdk", "fail", f"minSdk is {min_sdk.group(1)}; LiteRT needs "
        f"{MIN_SDK}: phones below Android 12 could no longer install the app",
        edit_fix(build_file, "In defaultConfig:",
                 f"minSdk = {MIN_SDK}" if kts else f"minSdk {MIN_SDK}"),
        risky=True)
  else:
    add("App: minSdk", "pass", f"minSdk {min_sdk.group(1)}")
  abis = abi_filters(text)
  abi_fix = edit_fix(build_file, "In defaultConfig:",
                     f'ndk {{ abiFilters.add("{RUNTIME_ABI}") }}' if kts
                     else f"ndk {{ abiFilters '{RUNTIME_ABI}' }}")
  narrows = ("bundletool needs the same ABIs in every module, and the Google "
             f"Tensor runtime has only {RUNTIME_ABI}; devices without "
             f"{RUNTIME_ABI} could no longer install the app")
  others = sorted((abis or set()) - {RUNTIME_ABI})
  if abis == {RUNTIME_ABI}:
    add("App: ABI filters", "pass", f"{RUNTIME_ABI} only")
  elif abis is None:
    add("App: ABI filters", "fail", "no abiFilters, so the app ships every "
        f"ABI of its native libraries; {narrows}", abi_fix, risky=True)
  elif others:
    add("App: ABI filters", "fail",
        f"abiFilters {'also ' if RUNTIME_ABI in abis else ''}names "
        f"{', '.join(others)}; {narrows}",
        dict(abi_fix, text=f"Make abiFilters {RUNTIME_ABI} only (remove "
             f"{', '.join(others)}):"), risky=True)
  else:
    add("App: ABI filters", "warn", "abiFilters is set from a value the "
        f"check cannot read; it must be {RUNTIME_ABI} only")
  runtime = detect_runtime(project)
  core = {r["version"] or "unknown" for r in runtime["core"]
          if r["module"] == app_rel}
  litert_dep = (f'implementation("{LITERT_MAVEN_GROUP}:litert:{release}")'
                if kts else
                f"implementation '{LITERT_MAVEN_GROUP}:litert:{release}'")
  if core == {release}:
    add("App: LiteRT dependency", "pass", f"litert {release}")
  elif not core:
    add("App: LiteRT dependency", "fail",
        f"{build_file} does not depend on {LITERT_MAVEN_GROUP}:litert",
        edit_fix(build_file, "In dependencies { }:", litert_dep))
  elif core == {"unknown"}:
    add("App: LiteRT dependency", "warn", "the litert version could not be "
        f"read; it must be {release}, the release of the runtime module")
  else:
    add("App: LiteRT dependency", "fail",
        f"the app uses litert {', '.join(sorted(core))}; the runtime module "
        f"needs {release} (one release for both)",
        edit_fix(build_file, "In dependencies { }:", litert_dep), risky=True)
  if re.search(rf"project\(\s*(?:path\s*[:=]\s*)?[\"']"
               rf"{re.escape(STRINGS_MODULE_PATH)}[\"']", text):
    add("App: runtime_strings dependency", "pass", STRINGS_MODULE_PATH)
  else:
    add("App: runtime_strings dependency", "fail",
        f"{build_file} does not depend on {STRINGS_MODULE_PATH}",
        edit_fix(build_file, "In dependencies { }:",
                 f'implementation(project("{STRINGS_MODULE_PATH}"))' if kts
                 else f"implementation project('{STRINGS_MODULE_PATH}')"))

  # gradle.properties, manifest permissions, plugin versions.
  if re.search(rf"(?m)^\s*{re.escape(DEVICE_TARGETING_FLAG)}\s*=\s*true\s*$",
               project["properties"]):
    add("gradle.properties", "pass", f"{DEVICE_TARGETING_FLAG}=true")
  else:
    add("gradle.properties", "fail", f"{DEVICE_TARGETING_FLAG}=true is "
        "missing (device targeting is ignored without it)",
        edit_fix("gradle.properties", "Add this line.",
                 f"{DEVICE_TARGETING_FLAG}=true", "properties"))
  if delivery != "install-time":
    lacking = [p for p in DOWNLOAD_PERMISSIONS if p not in manifest_text]
    if lacking:
      add("App: download permissions", "fail",
          f"{delivery} packs need " + ", ".join(lacking),
          edit_fix(f"{prefix}src/main/AndroidManifest.xml",
                   "Inside <manifest>:", "\n".join(
                       f'<uses-permission android:name="{p}" />'
                       for p in lacking), "xml"))
    else:
      add("App: download permissions", "pass", "FOREGROUND_SERVICE(_DATA_"
          "SYNC) declared")
  agp, agp_where = plugin_version(project, AGP_PLUGIN_IDS, AGP_CLASSPATH)
  if agp is None:
    add("Android Gradle plugin", "warn", "version not found; it must be "
        f"{'.'.join(map(str, MIN_AGP))} or newer for device targeting")
  elif _version_tuple(agp) < MIN_AGP:
    add("Android Gradle plugin", "fail",
        f"{agp} ({agp_where}); device targeting needs "
        f"{'.'.join(map(str, MIN_AGP))} or newer. Upgrading affects the "
        "whole build",
        edit_fix(agp_where, "Raise the Android Gradle plugin version to "
                 f"{'.'.join(map(str, MIN_AGP))} or newer (and Gradle to "
                 "what it requires).", None), risky=True)
  else:
    add("Android Gradle plugin", "pass", f"{agp} ({agp_where})")
  kotlin, kotlin_where = plugin_version(project, KOTLIN_PLUGIN_IDS,
                                        KOTLIN_CLASSPATH)
  if kotlin is None and not _KOTLIN_APPLIED_RE.search(text):
    built_in = agp is not None and _version_tuple(agp) >= (9,)
    add("Kotlin", "warn" if built_in else "fail",
        "the app module applies no Kotlin plugin, but TensorModelLoader.kt "
        "is Kotlin" + (" (AGP 9 may build it without one)" if built_in
                       else ""),
        edit_fix(build_file, "Apply the Kotlin Android plugin "
                 f"(org.jetbrains.kotlin.android) {kotlin_need} or newer.",
                 None), risky=not built_in)
  elif kotlin is None:
    add("Kotlin", "warn", f"version not found; it must be {kotlin_need} or "
        f"newer to read LiteRT {release}'s Kotlin API")
  elif _version_tuple(kotlin) < _version_tuple(kotlin_need):
    add("Kotlin", "fail", f"{kotlin} ({kotlin_where}); LiteRT {release}'s "
        f"Kotlin API needs {kotlin_need} or newer",
        edit_fix(kotlin_where, f"Raise the Kotlin version to {kotlin_need} "
                 "or newer.", None), risky=True)
  else:
    add("Kotlin", "pass", f"{kotlin} ({kotlin_where})")

  fails = [c for c in checks if c["status"] == "fail"]
  return {
      "project": str(root),
      "package": str(folder),
      "pack": pack,
      "delivery": delivery,
      "socs": socs,
      "app_module": {"module": app_rel, "gradle_path": app_path,
                     "build_file": build_file},
      "notes": [app_note] if app_note else [],
      "checks": checks,
      "summary": {
          "to_do": len(fails),
          "risky": [c["check"] for c in fails if c["risky"]],
          "warnings": sum(c["status"] == "warn" for c in checks),
          "passed": sum(c["status"] == "pass" for c in checks),
      },
  }


def print_check_report(result: dict[str, Any]) -> None:
  """Prints the --check-project report: each check, its fix and a summary."""
  app = result["app_module"]
  print(f"**Integration check:** {result['project']} for the package "
        f"{result['package']} (pack `{result['pack']}`, "
        f"`{result['delivery']}`, {_socs_text(result['socs'])})")
  print(f"**App module:** `{app['gradle_path']}` (`{app['build_file']}`)")
  for c in result["checks"]:
    print(f"  {c['status'].upper():<5} {c['check']}: {c['detail']}")
    fix = c["fix"]
    if fix:
      where = f" ({fix['file']})" if fix.get("file") else ""
      risky = " [needs a separate OK]" if c["risky"] else ""
      print(f"        fix{where}{risky}: {fix['text']}")
      for line in (fix.get("snippet") or "").splitlines():
        print(f"          {line}")
  s = result["summary"]
  risky = (f" ({len(s['risky'])} need a separate OK: "
           f"{', '.join(s['risky'])})" if s["risky"] else "")
  print(f"**Result:** {s['to_do']} to do{risky}, {s['warnings']} "
        f"warning(s), {s['passed']} passed")
  for note in result["notes"]:
    print(f"NOTE: {note}")


def main_check(args: argparse.Namespace, versions: dict[str, Any],
               versions_error: str | None) -> int:
  """--check-project (read-only): is the project set up for the package?"""
  del versions_error  # Unused.
  if args.compiled or args.fallback or args.update_project:
    raise PackError(
        2, "--check-project takes --package (the folder package_ai_pack.py "
        "wrote), not --compiled, --fallback or --update-project.")
  if not args.package:
    raise PackError(2, "--check-project needs --package <the folder "
                    "package_ai_pack.py wrote>.")
  pins = {"maven_release": versions.get("maven_release"),
          "kotlin_min": versions.get("kotlin_min")}
  pkg = load_package(args.package)
  project = inspect_project(args.check_project)
  result = check_integration(pkg, project, args, pins)
  if args.json:
    print(json.dumps(result, indent=2))
  else:
    print_check_report(result)
  return 1 if result["summary"]["to_do"] else 0


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def build_package(args: argparse.Namespace, builds: dict[str, dict[str, Any]],
                  fallback: dict[str, Any], out: pathlib.Path, release: str,
                  min_kotlin: str, versions: dict[str, Any],
                  notes: list[str]) -> dict[str, Any]:
  """Writes the package into a staging directory, verifies it, moves it."""
  stage = out.parent / f".{out.name}.staging-{os.getpid()}"
  if stage.exists():
    shutil.rmtree(stage)
  stage.mkdir(parents=True)
  try:
    ai_packs = stage / "ai_packs"
    export_with_litert(builds, fallback, ai_packs, args.pack_name,
                       args.model_name, versions.get("pip_release"))

    # D1: devices outside the Google Tensor groups use the base-asset CPU
    # model, so the exporter's copy of the original becomes a placeholder.
    other = (ai_packs / args.pack_name / "src" / "main" / "assets"
             / OTHER_GROUP_DIR)
    for path in other.iterdir():
      path.unlink()
    (other / PLACEHOLDER_FILE).write_text(
        PLACEHOLDER_TEXT.format(model=args.model_name, generator=GENERATOR),
        encoding="utf-8",
    )

    cpu_dir = stage / "cpu_gpu"
    cpu_dir.mkdir()
    shutil.copyfile(fallback["path"],
                    cpu_dir / f"{args.model_name}_cpu_gpu.tflite")

    # Optional quick test: each Tensor build where a debug APK's assets can
    # carry it (INTEGRATION.md, "Optional: quick test without bundletool").
    quick_test = None
    if args.quick_test:
      quick_test = {"app_dir": APP_QUICK_TEST_DIR,
                    "gradle_property": QUICK_TEST_PROPERTY, "files": []}
      for soc in builds:
        source = (ai_packs / args.pack_name / "src" / "main" / "assets"
                  / f"model#group_{group_of(soc)}"
                  / f"{args.model_name}.tflite")
        rel = quick_test_file(soc, args.model_name)
        (stage / rel).parent.mkdir(parents=True)
        shutil.copyfile(source, stage / rel)
        quick_test["files"].append({"soc": soc, "packed_as": rel})

    values = template_values(args, builds, release, min_kotlin)
    if quick_test:
      values["QUICK_TEST_SECTION"] = render("INTEGRATION_quick_test.md",
                                            values)
    for template, target in TEMPLATE_OUTPUTS:
      dest = stage / target.format(pack=args.pack_name)
      dest.parent.mkdir(parents=True, exist_ok=True)
      dest.write_text(render(template, values), encoding="utf-8")

    io_error = write_model_io(fallback["path"], stage)
    if io_error:
      notes.append(f"model_io.json: could not read the signature ({io_error}).")

    checks = verify_package(stage, args, builds, fallback)

    summary = {
        "generator": GENERATOR,
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
                        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pack_name": args.pack_name,
        "model_name": args.model_name,
        "delivery": args.delivery,
        "app_module": args.app_module,
        "kotlin_package": args.kotlin_package,
        "device_groups": [group_of(s) for s in builds],
        "variants": [
            {
                "device_group": group_of(soc),
                "soc": soc,
                "source": str(info["path"]),
                "size_bytes": info["size_bytes"],
                "sha256": info["sha256"],
                "packed_as": (f"ai_packs/{args.pack_name}/src/main/assets/"
                              f"model#group_{group_of(soc)}/"
                              f"{args.model_name}.tflite"),
                "sidecar": _sidecar_summary(info.get("sidecar")),
            }
            for soc, info in builds.items()
        ],
        "other_devices": {
            "ai_pack_folder": (f"ai_packs/{args.pack_name}/src/main/assets/"
                               f"{OTHER_GROUP_DIR}/{PLACEHOLDER_FILE}"),
            "cpu_model": {
                "source": str(fallback["path"]),
                "size_bytes": fallback["size_bytes"],
                "sha256": fallback["sha256"],
                "packed_as": f"cpu_gpu/{args.model_name}_cpu_gpu.tflite",
                "app_asset": f"litert/{args.model_name}_cpu_gpu.tflite",
            },
        },
        "quick_test": quick_test,
        "litert": {
            "maven_release": release,
            "kotlin_min": min_kotlin,
            "maven_artifacts": [
                f"com.google.ai.edge.litert:litert:{release}",
                "com.google.ai.edge.litert:litert-npu-runtime-google-tensor:"
                f"{release}",
            ],
            "exporter": "ai_edge_litert.aot.ai_pack.export_lib",
            "exporter_package": installed_litert(),
            "pinned_pip_release": versions.get("pip_release"),
        },
        "checks": checks,
        "notes": notes,
    }
    (stage / "pack.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    values["GENERATED_AT"] = summary["generated_at"].replace("T", " ")
    values["TREE"] = tree_text(stage)
    (stage / "INTEGRATION.md").write_text(
        render("INTEGRATION.md", values), encoding="utf-8"
    )

    if out.exists():
      shutil.rmtree(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    os.replace(stage, out)
    return summary
  finally:
    if stage.exists():
      shutil.rmtree(stage, ignore_errors=True)


def _sidecar_summary(sidecar: dict[str, Any] | None) -> dict[str, Any] | None:
  if not sidecar:
    return None
  keys = ("cli_flags", "ops_offloaded", "ops_total", "fully_compiled",
          "packages", "compiled_at", "compiled_via")
  return {k: sidecar[k] for k in keys if k in sidecar}


def report_markdown(summary: dict[str, Any], out: pathlib.Path) -> str:
  """The Markdown summary printed after a package is written."""
  files = [p for p in out.rglob("*") if p.is_file()]
  total = sum(p.stat().st_size for p in files)
  lines = [
      f"**Packaged:** {out} ({len(files)} files, {fmt_size(total)})",
      f"**AI pack:** `{summary['pack_name']}` (`{summary['delivery']}` "
      f"delivery); the app opens `model/{summary['model_name']}.tflite`",
  ]
  for v in summary["variants"]:
    sidecar = v["sidecar"]
    if sidecar:
      ops = (f"{sidecar.get('ops_offloaded')} / {sidecar.get('ops_total')} "
             "ops offloaded")
      origin = f"SHA-256 matches its .compile.json; {ops}"
    else:
      origin = "no .compile.json: flags unknown"
    lines.append(f"**{v['device_group']}:** {pathlib.Path(v['source']).name} "
                 f"({origin})")
  cpu = summary["other_devices"]["cpu_model"]
  lines += [
      f"**Other devices:** placeholder in `{OTHER_GROUP_DIR}`; CPU model "
      f"`{cpu['packed_as']}` -> app assets `{cpu['app_asset']}`",
  ]
  if summary.get("quick_test"):
    lines.append(
        f"**Quick test:** `{QUICK_TEST_DIR}/` -> `<app module>/"
        f"{APP_QUICK_TEST_DIR}/`, for `./gradlew installDebug "
        f"-P{QUICK_TEST_PROPERTY}=<SoC>` (local testing only; INTEGRATION.md, "
        "\"Optional: quick test without bundletool\")")
  lines += [
      "**LiteRT (Maven):** " + " + ".join(
          f"`{a}`" for a in summary["litert"]["maven_artifacts"]),
      f"**Exporter:** {summary['litert']['exporter']} "
      f"({summary['litert']['exporter_package']})",
      f"**Verified:** {len(summary['checks'])} checks passed (pack.json "
      "lists them)",
      f"**Next:** {out / 'INTEGRATION.md'}",
  ]
  return "\n".join(lines)


def print_plan(args: argparse.Namespace, builds: dict[str, dict[str, Any]],
               fallback: dict[str, Any], out: pathlib.Path, release: str,
               min_kotlin: str, notes: list[str]) -> None:
  """Prints the dry-run plan of a new package (nothing is written)."""
  print("Dry run: inputs checked; nothing imported or written.")
  for soc, info in builds.items():
    sidecar = "sidecar OK" if info.get("sidecar") else "no sidecar"
    print(f"  {group_of(soc)} <- {info['path']} "
          f"({fmt_size(info['size_bytes'])}, {sidecar})")
  print(f"  CPU model     <- {fallback['path']} "
        f"({fmt_size(fallback['size_bytes'])})")
  print(f"Pack: {args.pack_name} ({args.delivery}); model file "
        f"model/{args.model_name}.tflite; app module :{args.app_module}")
  print(f"LiteRT Maven release for the Gradle files: {release} (apps need "
        f"Kotlin {min_kotlin} or newer)")
  if args.quick_test:
    print(f"Quick test: {QUICK_TEST_DIR}/<SoC>/assets/ for "
          f"./gradlew installDebug -P{QUICK_TEST_PROPERTY}=<SoC> (local "
          "testing only)")
  print(f"Would write: {out}{' (replacing it)' if out.exists() else ''}")
  for note in notes:
    print(f"NOTE: {note}")


def main(argv=None) -> int:
  args = parse_args(argv)
  versions, versions_error = read_versions()
  try:
    if args.check_project:
      return main_check(args, versions, versions_error)
    if args.package:
      raise PackError(2, "--package needs --check-project.")
    if not args.compiled or not args.fallback:
      raise PackError(
          2, "--compiled and --fallback are required (or --check-project "
          "with --package to check a project).")
    if args.update_project:
      return main_update(args, versions, versions_error)
    if args.cpu_asset:
      raise PackError(2, "--cpu-asset needs --update-project.")
    fallback_path = pathlib.Path(args.fallback).expanduser()
    check_names(args, fallback_path)
    builds, fallback, notes = check_inputs(args)
    out = resolve_output_dir(args, fallback)
    if args.dry_run:
      try:
        release = maven_release(versions, versions_error)
        min_kotlin = kotlin_min(versions, versions_error)
      except PackError as e:
        release = min_kotlin = f"<unavailable: {e}>"
      if args.json:
        print(json.dumps({
            "dry_run": True, "output_dir": str(out),
            "pack_name": args.pack_name, "model_name": args.model_name,
            "delivery": args.delivery,
            "device_groups": [group_of(s) for s in builds],
            "maven_release": release, "kotlin_min": min_kotlin,
            "quick_test": args.quick_test,
            "notes": notes,
        }, indent=2))
      else:
        print_plan(args, builds, fallback, out, release, min_kotlin, notes)
      return 0
    release = maven_release(versions, versions_error)
    min_kotlin = kotlin_min(versions, versions_error)
    if not args.json:
      print(f"Packaging {', '.join(group_of(s) for s in builds)} for AI pack "
            f"'{args.pack_name}' with LiteRT's export_lib ...", flush=True)
    summary = build_package(args, builds, fallback, out, release, min_kotlin,
                            versions, notes)
  except PackError as e:
    if args.json:
      print(json.dumps({"status": "error", "exit_code": e.code,
                        "error": str(e)}, indent=2))
    else:
      print(f"ERROR: {e}", file=sys.stderr)
    return e.code
  except KeyboardInterrupt:
    print("Interrupted; nothing was left at the output directory.",
          file=sys.stderr)
    return 130

  if args.json:
    print(json.dumps(dict(status="ok", output_dir=str(out), **summary),
                     indent=2))
  else:
    for note in summary["notes"]:
      print(f"NOTE: {note}")
    print()
    print(report_markdown(summary, out))
  return 0


if __name__ == "__main__":
  sys.exit(main())
