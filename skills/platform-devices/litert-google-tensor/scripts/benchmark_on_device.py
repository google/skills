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

"""Benchmarks a Google Tensor-compiled .tflite on an attached Pixel over adb.

What it does (all steps are synchronous; nothing is left running):
  1. Picks the adb device (or uses --serial), reads its SoC and checks that the
     model was compiled for it (``ro.soc.model`` -> ``Tensor_G5`` etc.).
  2. Resolves ``libLiteRtDispatch_GoogleTensor.so`` (--dispatch-lib: a .so, a
     directory, or a .zip/.aar that contains it; default: cached download from
     the public LiteRT binaries bucket) and the android_arm64
     ``benchmark_model`` binary (--benchmark-bin, else a cached download from
     the same bucket directory, so the two always come from one release). The
     default release is ``binaries_release`` in the skill's versions.json;
     each download's fetch date and md5 are recorded next to it and printed.
  3. Pushes model + binary + dispatch library to a fresh per-run directory
     /data/local/tmp/litert_benchmark/run-<timestamp>-<pid>/ (never overwrites
     or deletes files that were already on the phone).
  4. Runs an NPU-only benchmark:
       benchmark_model --graph=... --use_npu=true --use_cpu=false
                       --require_full_delegation=true
                       --dispatch_library_path=<device dir>
                       --num_runs=<--num-runs, default 50>
                       --warmup_runs=<--warmup-runs, default 5>
                       --report_peak_memory_footprint=true --use_profiler=true
     then the same NPU run once more, without profiler and memory monitor,
     with LITERT_VENDOR_HOOK_ARGS enabling the dispatch library's TPU
     tile-time and power hooks (--no-tile-time / --no-power turn them off;
     with both, this pass is skipped); and, with --cpu-baseline
     <original.tflite>, a CPU run of the uncompiled model for comparison.
  5. Parses the results, prints a Markdown header + table in which every value
     comes from the device or this run (device props, thermal status before
     the NPU run, the ``<model>.compile.json`` sidecar written by
     compile_model.py if present, a Versions line comparing the sidecar's
     LiteRT version with the release of the runtime binaries, the runtime
     "Replacing N out of M node(s)" delegation line, all timings, TPU tile time
     per inference (the hook's total divided by the runs benchmark_model made:
     older dispatch libraries count each inference 1 + D times, which makes
     the hook's own average wrong), TPU energy per inference (the power hook's
     TPU rail energy over the hooked pass divided by its runs; not measured
     with a dispatch library whose power hook predates the fix), and a log
     check that counts the known-benign WARNING lines and lists any other
     WARNING/ERROR line verbatim), writes
     results.json, report.md (the same block), npu.log, cpu.log,
     tile_time.log (the hooked pass), tile_time_report.txt / power_report.txt
     (the hooks' reports), npu_profile.txt / cpu_profile.txt to --output-dir,
     and deletes the per-run directory it created on the device (also on
     failure) unless --keep-device-files is given.

Standard library only; needs ``adb`` on PATH and a device with USB debugging.

Exit codes
----------
0 success            4 model/device SoC mismatch (see --allow-mismatch)
2 bad arguments      5 dispatch library or benchmark binary unavailable
3 adb/device problem 6 benchmark_model failed on device, or exited 0 with
                       output this script cannot parse (format change)
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
from typing import Any
import urllib.error
import urllib.request
import zipfile

DEFAULT_DEVICE_DIR = "/data/local/tmp/litert_benchmark"
# Public LiteRT prebuilt binaries. The same directory holds benchmark_model and
# libLiteRtDispatch_GoogleTensor.so built together, so a release directory
# ("latest", "nightly" or a version) is the unit of versioning. The default
# release is "binaries_release" in the skill's assets/versions.json, its single
# source of versions (see references/contributing.md); which release
# directories ship the Google Tensor dispatch library is listed in
# references/benchmark-flags.md.
BINARIES_BUCKET = "https://storage.googleapis.com/litert/binaries"
VERSIONS_FILE = (
    pathlib.Path(__file__).resolve().parent.parent / "assets" / "versions.json"
)


def _read_versions() -> tuple[dict[str, Any], str | None]:
  """Returns (versions.json contents, None) or ({}, error text).

  Never raises: --help, --dry-run and runs with local binaries must work even
  if the file is missing or broken; only a default download needs it.
  """
  try:
    data = json.loads(VERSIONS_FILE.read_text(encoding="utf-8"))
  except (OSError, ValueError) as e:
    return {}, f"cannot read {VERSIONS_FILE}: {e}"
  release = data.get("binaries_release") if isinstance(data, dict) else None
  if not isinstance(release, str) or not re.fullmatch(
      r"[A-Za-z0-9._-]+", release
  ):
    return {}, (
        f"{VERSIONS_FILE}: 'binaries_release' must be a bucket "
        "release directory name such as 'latest' or 'X.Y.Z'"
    )
  return data, None


VERSIONS, VERSIONS_ERROR = _read_versions()
DEFAULT_BINARIES_DIR = (
    f"{BINARIES_BUCKET}/{VERSIONS['binaries_release']}/android_arm64"
    if VERSIONS
    else None
)
DEFAULT_BENCHMARK_URL = (
    f"{DEFAULT_BINARIES_DIR}/benchmark_model" if DEFAULT_BINARIES_DIR else None
)
DISPATCH_LIB_NAME = "libLiteRtDispatch_GoogleTensor.so"
CACHE_DIR = pathlib.Path(
    os.environ.get(
        "LITERT_GOOGLE_TENSOR_CACHE",
        pathlib.Path.home() / ".cache" / "litert-google-tensor",
    )
)
DISPATCH_LIB_ENV = "LITERT_GOOGLE_TENSOR_DISPATCH_LIB"

# ``adb shell getprop ro.soc.model`` values (case-insensitive) -> AOT target.
SOC_PROP_TO_TARGET = {
    "tensor g3": "Tensor_G3",
    "tensor g4": "Tensor_G4",
    "tensor g5": "Tensor_G5",
    "tensor g6": "Tensor_G6",
}
PERFORMANCE_MODES = (
    "extreme_power_saver",
    "power_saver",
    "balanced",
    "high_performance",
    "sustained_performance",
    "burst",
)

TFLITE_FILE_IDENTIFIER = b"TFL3"
DISPATCH_OP_MARKER = b"DISPATCH_OP"
BUILD_STAMP_KEY = b"LiteRtStamp"
# Custom op of models compiled by the Edge TPU compiler (and older Google
# Tensor tooling), same check as check_compiled.py.
LEGACY_TPU_OP_RE = re.compile(rb"edgetpu-custom-op[\w-]*")
SOC_MODEL_RE = re.compile(rb"Tensor_G\d+")

_DISPATCH_DIR_TEXT = (
    DEFAULT_BINARIES_DIR or f"{BINARIES_BUCKET}/<release>/android_arm64"
)
DISPATCH_LIB_HELP = f"""\
{DISPATCH_LIB_NAME} is the on-device Google Tensor runtime library that
benchmark_model loads for --use_npu. Ways to provide it:
  1. Let this script download it from the same public directory as
     benchmark_model (default; see --benchmark-url / --dispatch-url):
       {_DISPATCH_DIR_TEXT}/{DISPATCH_LIB_NAME}
  2. Pass --dispatch-lib with the .so, a directory, or a .zip/.aar containing
     it (e.g. LiteRT GitHub release assets:
       https://github.com/google-ai-edge/LiteRT/releases),
     or export {DISPATCH_LIB_ENV}=<path>.
  3. Build it from source ('How do I build a Google Tensor dispatch library?'):
       https://developers.google.com/edge/tensor-sdk/tensor-faqs
Keep the dispatch library and benchmark_model from the same LiteRT release."""


class BenchmarkError(Exception):

  def __init__(self, code: int, message: str):
    super().__init__(message)
    self.code = code


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def inspect_model(path: pathlib.Path) -> dict[str, Any]:
  data = path.read_bytes()
  compiled = DISPATCH_OP_MARKER in data and BUILD_STAMP_KEY in data
  return {
      "is_tflite": len(data) >= 8 and data[4:8] == TFLITE_FILE_IDENTIFIER,
      "compiled": compiled,
      "soc_models": sorted({m.decode() for m in SOC_MODEL_RE.findall(data)}),
      "size_bytes": len(data),
      # Compiled by another toolchain (Edge TPU custom op), not by LiteRT.
      "legacy_ops": [] if compiled else sorted(
          {m.decode() for m in LEGACY_TPU_OP_RE.findall(data)}),
  }


def legacy_model_error(path: pathlib.Path, ops: list[str], role: str) -> str:
  return (
      f"ERROR: {role} {path.name} was compiled by another toolchain: it holds "
      f"an Edge TPU custom op ({', '.join(ops)}), which neither the Google "
      "Tensor runtime nor the CPU can run (check_compiled.py exits 4 for such "
      "files). Use the ORIGINAL model it was made from: compile it with "
      "scripts/compile_model.py for --model, or pass it as is for "
      "--cpu-baseline."
  )


def safe_name(path: pathlib.Path) -> str:
  return re.sub(r"[^A-Za-z0-9._-]", "_", path.name)


def fmt_size(num_bytes: int) -> str:
  """'8,110,864 bytes (8.1 MB)'; MB = 10^6 bytes, same as the other scripts."""
  text = f"{num_bytes:,} bytes"
  if num_bytes >= 100_000:
    text += f" ({num_bytes / 1e6:.1f} MB)"
  return text


def read_compile_sidecar(model: pathlib.Path) -> dict[str, Any] | None:
  """Loads ``<model>.compile.json`` (written by compile_model.py) if present."""
  sidecar = model.with_name(model.name + ".compile.json")
  if not sidecar.is_file():
    return None
  try:
    data = json.loads(sidecar.read_text(encoding="utf-8"))
  except (OSError, ValueError):
    return None
  return data if isinstance(data, dict) else None


# android.os.Temperature throttling status values.
THERMAL_STATUS_LABELS = {
    0: "none",
    1: "light",
    2: "moderate",
    3: "severe",
    4: "critical",
    5: "emergency",
    6: "shutdown",
}
_THERMAL_STATUS_RE = re.compile(r"Thermal Status:\s*(\d+)")
# Temperature{mValue=45.0, mType=9, mName=TPU, mStatus=0}; mType 9 = NPU.
_THERMAL_NPU_RE = re.compile(
    r"Temperature\{mValue=(-?[\d.]+), mType=9, mName=([^,}]+)"
)


def read_thermal(adb: "Adb") -> dict[str, Any]:
  """Best-effort snapshot of ``dumpsys thermalservice`` (never raises)."""
  info = {
      "status": None,
      "status_label": "unavailable",
      "npu_temp_c": None,
      "npu_sensor": None,
  }
  if adb.dry_run:
    return info
  try:
    out = adb.shell("dumpsys thermalservice", check=False, timeout=30).stdout
  except Exception:  # pylint: disable=broad-exception-caught
    return info
  m = _THERMAL_STATUS_RE.search(out or "")
  if m:
    info["status"] = int(m.group(1))
    info["status_label"] = THERMAL_STATUS_LABELS.get(info["status"], "unknown")
  m = _THERMAL_NPU_RE.search(out or "")
  if m:
    info["npu_temp_c"] = float(m.group(1))
    info["npu_sensor"] = m.group(2).strip()
  return info


def thermal_text(t: dict[str, Any]) -> str:
  if t["status"] is None:
    return "unavailable (dumpsys thermalservice gave no status)"
  text = f"throttling status {t['status']} ({t['status_label']})"
  if t["npu_temp_c"] is not None:
    text += (
        f"; {t['npu_sensor']} sensor {t['npu_temp_c']:.1f} C "
        "(single reading, informational)"
    )
  return text


# --------------------------------------------------------------------------
# TPU tile time (dispatch-library hook)
# --------------------------------------------------------------------------
# libLiteRtDispatch_GoogleTensor.so runs vendor hooks when
# LITERT_VENDOR_HOOK_ARGS (a config file path, or the config text) is set.
# Only the tile-time metric is enabled. Older dispatch libraries count every
# inference 1 + D times (once from the LiteRT runtime, once per dispatch
# invoke; D = dispatch nodes) but add tile time only on the dispatch path, so
# their own "Average" is wrong; fixed ones count once per dispatch invoke. The
# script divides the total by the runs benchmark_model really made, which is
# right for both.
HOOK_ENV = "LITERT_VENDOR_HOOK_ARGS"
HOOK_CONFIG_NAME = "tpu_hooks.textproto"
TILE_REPORT_NAME = "tpu_tile.txt"
POWER_REPORT_NAME = "tpu_power.txt"
_TILE_TOTAL_RE = re.compile(r"Total TPU tile time \(us\):\s*(\d+)")
_TILE_COUNT_RE = re.compile(r"Total inferences:\s*(\d+)")
_HOOKS_REGISTERED = "Successfully retrieved and registered vendor hooks"
_HOOKS_NULL = "Accelerator returned null hooks"
# Power metric (power_config): the TPU rail's energy counter of the phone's
# on-device power monitor. The fixed hook reads it when the first dispatch
# invoke starts and when the model is torn down, and counts dispatch invokes.
# Older builds read it around every call (several-fold slower inference) and
# count every inference 1 + D times; their numbers cannot be corrected, so the
# metric stays off for a library that carries this log string of the old code.
_POWER_TOTAL_RE = re.compile(r"Total Energy \(uJ\):\s*(\d+)")
_POWER_COUNT_RE = re.compile(r"Inference count:\s*(\d+)")
_POWER_OLD_MARKER = b"failed HandlePowerRuntimeStop"
_POWER_FAILURE_RE = re.compile(
    r"^.*(?:HandlePowerRuntime|ODPM|Final energy|Skipping power metrics|"
    r"PowerStats|RailEnergyData).*$",
    re.M,
)
_OLD_POWER_HOOK_REASON = (
    "this dispatch library's power hook predates the fix: it reads the TPU "
    "energy counter around every call (several-fold slower inference) and "
    "counts every inference 1 + D times, so its numbers are not usable and "
    "the power metric was not enabled; the default bucket binaries carry the "
    "fixed hook"
)


def hook_config(device_dir: str, tile: bool, power: bool) -> str:
  """Hook config enabling the TPU tile-time and/or the power (energy) metric.

  The hook strips all whitespace and matches keys as plain substrings, so only
  lowercase ``true`` enables a metric, a commented-out key would still count,
  and the dump paths must not contain whitespace (main() checks that).

  Args:
    device_dir: Per-run directory path on the device.
    tile: Whether to enable the TPU tile-time metric.
    power: Whether to enable the power metric (TPU energy).

  Returns:
    Textproto content for the vendor hook configuration file.
  """
  tile_path = f"{device_dir}/{TILE_REPORT_NAME}"
  power_path = f"{device_dir}/{POWER_REPORT_NAME}"
  text = ""
  if tile:
    text += (
        "tpu_tile_time_metrics_config {\n"
        "  dump_tpu_tile_time_metrics: true\n"
        f'  tpu_tile_time_metrics_dump_path: "{tile_path}"\n'
        "}\n"
    )
  if power:
    text += (
        "power_config {\n"
        "  dump_power_metrics: true\n"
        f'  power_dump_path: "{power_path}"\n'
        "}\n"
    )
  return text


def power_hook_is_old(lib: pathlib.Path) -> bool:
  """True if the dispatch library carries the pre-fix power hook."""
  try:
    return _POWER_OLD_MARKER in lib.read_bytes()
  except OSError:
    return False  # not downloaded yet (--dry-run): the pass checks the count


class Adb:
  """Minimal adb wrapper bound to one device serial."""

  def __init__(self, serial: str | None, dry_run: bool):
    self.serial = serial
    self.dry_run = dry_run
    self.adb = shutil.which("adb")
    if not self.adb:
      raise BenchmarkError(
          3,
          "adb not found on PATH. Install Android platform-tools: "
          "https://developer.android.com/tools/releases/platform-tools",
      )

  def _base(self) -> list[str]:
    return [self.adb] + (["-s", self.serial] if self.serial else [])

  def run(
      self,
      *args: str,
      timeout: int = 120,
      check: bool = True,
      capture: bool = True,
  ) -> subprocess.CompletedProcess[str]:
    """Runs ``adb [-s <serial>] <args>``; in dry-run mode only prints it.

    Args:
      *args: Arguments to adb, e.g. ``"shell", "getprop"``.
      timeout: Seconds before subprocess.TimeoutExpired is raised.
      check: Whether a non-zero exit code raises BenchmarkError.
      capture: Whether to capture adb's stdout and stderr (merged) as text
        instead of letting adb print to this script's output.

    Returns:
      The finished process; in dry-run mode a stand-in with exit code 0 and
      empty output.

    Raises:
      BenchmarkError: If ``check`` is set and adb exits with a non-zero code.
    """
    cmd = self._base() + list(args)
    if self.dry_run:
      print("  [dry-run] " + " ".join(shlex.quote(c) for c in cmd))
      return subprocess.CompletedProcess(cmd, 0, "", "")
    proc = subprocess.run(
        cmd,
        text=True,
        timeout=timeout,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        check=False,
    )
    if check and proc.returncode != 0:
      raise BenchmarkError(
          3,
          f"adb command failed ({proc.returncode}): "
          f"{' '.join(cmd)}\n{(proc.stdout or '').strip()}",
      )
    return proc

  def shell(
      self, command: str, timeout: int = 120, check: bool = True
  ) -> subprocess.CompletedProcess[str]:
    return self.run("shell", command, timeout=timeout, check=check)

  def getprop(self, name: str) -> str:
    if self.dry_run:
      return ""
    return self.shell(f"getprop {name}", check=False).stdout.strip()


def list_devices(adb_path: str) -> list[tuple[str, str]]:
  out = subprocess.run(
      [adb_path, "devices"], text=True, capture_output=True, check=False
  ).stdout
  devices = []
  for line in out.splitlines()[1:]:
    parts = line.split()
    if len(parts) >= 2:
      devices.append((parts[0], parts[1]))
  return devices


def pick_device(serial: str | None) -> str:
  """Returns the serial of the adb device to use.

  Args:
    serial: The --serial value, or None to pick the only ready device.

  Raises:
    BenchmarkError: If adb is missing, ``serial`` is not connected or not
      ready, or (without ``serial``) not exactly one device is ready.
  """
  adb_path = shutil.which("adb")
  if not adb_path:
    raise BenchmarkError(3, "adb not found on PATH.")
  devices = list_devices(adb_path)
  if serial:
    for s, state in devices:
      if s == serial:
        if state != "device":
          raise BenchmarkError(
              3,
              f"device {serial} is '{state}', not ready "
              "(accept the USB-debugging prompt on the phone).",
          )
        return serial
    raise BenchmarkError(3, f"device {serial} not found in `adb devices`.")
  ready = [s for s, state in devices if state == "device"]
  if not ready:
    states = ", ".join(f"{s} ({st})" for s, st in devices) or "none"
    raise BenchmarkError(
        3,
        "no ready adb device. Connected: "
        + states
        + ". USB: re-plug, enable USB debugging and accept the "
        "prompt. Forwarded phone (serial host:port): run "
        "`adb connect host:port` again; use `adb reconnect` "
        "rather than `adb kill-server` on shared hosts.",
    )
  if len(ready) > 1:
    raise BenchmarkError(
        3,
        "more than one device connected; pass --serial one of: "
        + ", ".join(ready),
    )
  return ready[0]


def _sha256(path: pathlib.Path) -> str:
  digest = hashlib.sha256()
  with open(path, "rb") as fh:
    for chunk in iter(lambda: fh.read(1 << 20), b""):
      digest.update(chunk)
  return digest.hexdigest()


def _gcs_hashes(headers) -> dict[str, str]:
  """{'md5': ..., 'crc32c': ...} (base64) from GCS ``x-goog-hash`` headers."""
  hashes = {}
  for value in headers.get_all("x-goog-hash") or []:
    for part in value.split(","):
      name, sep, digest = part.strip().partition("=")
      if sep and digest:
        hashes[name.lower()] = digest
  return hashes


def _meta_path(cached: pathlib.Path) -> pathlib.Path:
  return cached.with_name(cached.name + ".json")


def _read_download_meta(cached: pathlib.Path) -> dict[str, Any] | None:
  """The metadata written next to a download, if it belongs to this file."""
  try:
    meta = json.loads(_meta_path(cached).read_text(encoding="utf-8"))
  except (OSError, ValueError):
    return None
  if (
      not isinstance(meta, dict)
      or meta.get("size_bytes") != cached.stat().st_size
  ):
    return None  # unreadable, or written for another copy of the file
  return meta


def _fetch_text(meta: dict[str, Any] | None) -> str:
  """'fetched <UTC time>, md5 <base64>' for the provenance line."""
  if not meta:
    return (
        "fetch date not recorded; --refresh-binary re-downloads and records it"
    )
  when = str(meta.get("fetched_at", "?"))
  when = when.replace("T", " ").replace("Z", " UTC")
  if meta.get("gcs_md5"):
    return f"fetched {when}, md5 {meta['gcs_md5']}"
  return f"fetched {when}, sha256 {str(meta.get('sha256', '?'))[:16]}"


def _cached_download(
    url: str | None, refresh: bool, dry_run: bool, manual_flag: str
) -> tuple[pathlib.Path, str]:
  """Downloads ``url`` into the cache once; returns (path, provenance).

  Next to each download, ``<file>.json`` records the URL, the UTC fetch time,
  the SHA-256 and the bucket's generation/md5 (GCS response headers), so a
  cached copy of a rolling release ('latest', 'nightly') stays identifiable:
  its md5 can be compared with the bucket listing's ``md5Hash``.

  Args:
    url: File to download, or None if there is no default URL.
    refresh: Whether to download again even if a cached copy exists.
    dry_run: Whether to only print what would be downloaded.
    manual_flag: Flag that the error message suggests for passing a local
      copy instead, e.g. ``--benchmark-bin``.

  Returns:
    (cache path of the file, provenance text for the report); with
    ``dry_run`` and no cached copy, the path does not exist yet.

  Raises:
    BenchmarkError: If ``url`` is None or empty, or the download fails.
  """
  if not url:
    raise BenchmarkError(
        5,
        f"no default download URL ({VERSIONS_ERROR}). Pass --benchmark-url "
        f"{BINARIES_BUCKET}/<release>/android_arm64/benchmark_model, or "
        "--benchmark-bin and --dispatch-lib.",
    )
  tag = re.sub(r"[^A-Za-z0-9._-]", "_", url.split("/binaries/", 1)[-1])
  cached = CACHE_DIR / tag
  if cached.is_file() and not refresh:
    return cached, (
        f"cached download of {url} ({_fetch_text(_read_download_meta(cached))})"
    )
  if dry_run:
    print(f"  [dry-run] would download {url} -> {cached}")
    return cached, f"would download from {url}"
  cached.parent.mkdir(parents=True, exist_ok=True)
  print(f"Downloading {url} ...")
  part = cached.with_suffix(cached.suffix + ".part")
  try:
    with (
        urllib.request.urlopen(url, timeout=120) as resp,
        open(part, "wb") as f,
    ):
      shutil.copyfileobj(resp, f)
      headers = resp.headers
  except (urllib.error.URLError, OSError) as e:
    raise BenchmarkError(
        5,
        f"download failed ({e}). Download it manually from {url} and pass "
        f"{manual_flag}, or pick another release directory with "
        "--benchmark-url (.../binaries/<release>/android_arm64/...).",
    ) from e
  part.replace(cached)
  cached.chmod(0o755)
  hashes = _gcs_hashes(headers)
  meta = {
      "url": url,
      "fetched_at": (
          datetime.datetime.now(datetime.timezone.utc).strftime(
              "%Y-%m-%dT%H:%M:%SZ"
          )
      ),
      "size_bytes": cached.stat().st_size,
      "sha256": _sha256(cached),
      "gcs_generation": headers.get("x-goog-generation"),
      "gcs_md5": hashes.get("md5"),
      "gcs_crc32c": hashes.get("crc32c"),
  }
  try:
    _meta_path(cached).write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
  except OSError:
    pass  # the next run then reports "fetch date not recorded"
  return cached, f"downloaded from {url} ({_fetch_text(meta)})"


def resolve_dispatch_lib(
    spec: str | None,
    scratch: pathlib.Path,
    url: str | None,
    refresh: bool = False,
    dry_run: bool = False,
) -> tuple[pathlib.Path, str]:
  """Returns (local path, provenance) for libLiteRtDispatch_GoogleTensor.so.

  Order: --dispatch-lib, then $LITERT_GOOGLE_TENSOR_DISPATCH_LIB, then a cached
  download of ``url`` (the dispatch library next to benchmark_model).

  Args:
    spec: The --dispatch-lib value (the .so, a directory, or a .zip/.aar that
      contains it), or None.
    scratch: Temporary local directory to extract a .zip/.aar member into.
    url: Download URL for when no path is given, or None.
    refresh: Whether to download again even if a cached copy exists.
    dry_run: Whether to only print what would be downloaded.

  Raises:
    BenchmarkError: If the given path does not provide the library, or the
      download fails.
  """
  spec = spec or os.environ.get(DISPATCH_LIB_ENV)
  if not spec:
    return _cached_download(url, refresh, dry_run, "--dispatch-lib")
  path = pathlib.Path(spec).expanduser()
  if path.is_dir():
    hits = sorted(path.rglob(DISPATCH_LIB_NAME))
    if hits:
      hit = _prefer_arm64(hits)
      return hit, f"user-provided: {hit}"
    raise BenchmarkError(
        5, f"{DISPATCH_LIB_NAME} not found under {path}.\n" + DISPATCH_LIB_HELP
    )
  if path.is_file() and zipfile.is_zipfile(path):
    with zipfile.ZipFile(path) as zf:
      members = [
          m
          for m in zf.namelist()
          if m.endswith("/" + DISPATCH_LIB_NAME) or m == DISPATCH_LIB_NAME
      ]
      if not members:
        raise BenchmarkError(
            5, f"{DISPATCH_LIB_NAME} not inside {path}.\n" + DISPATCH_LIB_HELP
        )
      member = _prefer_arm64(members)
      dest = scratch / DISPATCH_LIB_NAME
      with zf.open(str(member)) as src, open(dest, "wb") as out:
        shutil.copyfileobj(src, out)
      print(f"Extracted {member} from {path.name}")
      return dest, f"extracted {member} from {path}"
  if path.is_file():
    with open(path, "rb") as f:
      is_elf = f.read(4) == b"\x7fELF"
    if is_elf:
      # Any ELF shared object is accepted whatever its local file name (e.g. a
      # renamed download); it is pushed to the device as DISPATCH_LIB_NAME.
      if path.name != DISPATCH_LIB_NAME:
        print(f"Note: using {path.name} as {DISPATCH_LIB_NAME}.")
      return path, f"user-provided: {path}"
  raise BenchmarkError(
      5,
      f"--dispatch-lib {spec} is not an ELF shared library, "
      "a directory, a .zip or an .aar.\n"
      + DISPATCH_LIB_HELP,
  )


def _prefer_arm64(candidates):
  for c in candidates:
    if "arm64-v8a" in str(c) or "arm64" in str(c):
      return c
  return candidates[0]


def resolve_benchmark_bin(
    spec: str | None, url: str | None, refresh: bool, dry_run: bool = False
) -> tuple[pathlib.Path, str]:
  """Returns (local path, provenance string) for the android_arm64 binary."""
  if spec:
    path = pathlib.Path(spec).expanduser()
    if not path.is_file():
      raise BenchmarkError(5, f"--benchmark-bin {path} does not exist.")
    return path, f"user-provided: {path}"
  return _cached_download(url, refresh, dry_run, "--benchmark-bin")


# --------------------------------------------------------------------------
# Output parsing
# --------------------------------------------------------------------------
_PATTERNS = {
    "signature": r"Signature name:[ \t]+(.+)",
    "init_ms": r"Model initialization:\s+([\d.]+) ms",
    "warmup_first_ms": r"Warmup \(first\):\s+([\d.]+) ms",
    "warmup_avg_ms": r"Warmup \(avg\):\s+([\d.]+) ms \((\d+) runs\)",
    "inference_avg_ms": r"Inference \(avg\):\s+([\d.]+) ms \((\d+) runs\)",
    "inference_min_ms": r"Inference \(min\):\s+([\d.]+) ms",
    "inference_max_ms": r"Inference \(max\):\s+([\d.]+) ms",
    "inference_std_ms": r"Inference \(std\):\s+([\d.]+)",
    "throughput_mb_s": r"Throughput:\s+([\d.]+) MB/s",
    "init_footprint_mb": r"Init footprint:\s+([\d.]+) MB",
    "overall_footprint_mb": r"Overall footprint:\s+([\d.]+) MB",
    "peak_memory_mb": r"Peak memory:\s+([\d.]+) MB",
}
# "Replacing 1 out of 1 node(s) with delegate (DispatchDelegate) node,
#  yielding 1 partitions for subgraph 0 (main)."
_DELEGATION_RE = re.compile(
    r"Replacing (\d+) out of (\d+) node\(s\) with delegate \((\w+)\)"
)
# Older binaries print the upstream TFLite one-liner in microseconds.
_LEGACY_TIMINGS = re.compile(
    r"Inference timings in us: Init: ([\d.e+]+), First inference: ([\d.e+]+), "
    r"Warmup \(avg\): ([\d.e+]+), Inference \(avg\): ([\d.e+]+)"
)
_LEGACY_PEAK = re.compile(
    r"Overall peak memory footprint \(MB\) via periodic monitoring: ([\d.]+)"
)
# Per-phase stats lines (microseconds), one for warmup and one for the measured
# phase; the only place benchmark_model reports percentiles:
# "INFO: count=200 first=12110 curr=16718 min=10557 max=17736 avg=15390.9
#  std=2115 p5=11716 median=16428 p95=17481"
_PHASE_STATS = re.compile(
    r"count=(\d+) first=[\d.]+ curr=[\d.]+ min=[\d.]+ max=[\d.]+ avg=[\d.]+ "
    r"std=[\d.]+ p5=([\d.]+) median=([\d.]+) p95=([\d.]+)"
)


def parse_benchmark_log(text: str) -> dict[str, Any]:
  """Parses benchmark_model output (current or legacy format) into a dict.

  Args:
    text: Output of one benchmark_model run.

  Returns:
    The values found (times in ms, memory in MB): the _PATTERNS keys,
    warmup_runs, measured_runs, delegated_nodes, total_nodes, delegate,
    inference_p5_ms, inference_p50_ms, inference_p95_ms and profile_summary.
    Keys whose line is not in the log are left out.
  """
  res = {}
  for key, pat in _PATTERNS.items():
    m = re.search(pat, text)
    if not m:
      continue
    if key == "signature":
      res[key] = m.group(1).strip()
    else:
      res[key] = float(m.group(1))
    if key == "warmup_avg_ms":
      res["warmup_runs"] = int(m.group(2))
    if key == "inference_avg_ms":
      res["measured_runs"] = int(m.group(2))
  m = _DELEGATION_RE.search(text)
  if m:
    res["delegated_nodes"] = int(m.group(1))
    res["total_nodes"] = int(m.group(2))
    res["delegate"] = m.group(3)
  # Percentiles of the measured phase: the stats line whose count matches the
  # measured-run count (else the last stats line before the results box).
  results_at = text.find("BENCHMARK RESULTS")
  phases = [
      m
      for m in _PHASE_STATS.finditer(text)
      if results_at == -1 or m.start() < results_at
  ]
  if phases:
    measured = [
        m for m in phases if int(m.group(1)) == res.get("measured_runs", -1)
    ]
    m = (measured or phases)[-1]
    res["inference_p5_ms"] = float(m.group(2)) / 1000.0
    res["inference_p50_ms"] = float(m.group(3)) / 1000.0
    res["inference_p95_ms"] = float(m.group(4)) / 1000.0
  if "inference_avg_ms" not in res:
    m = _LEGACY_TIMINGS.search(text)
    if m:
      init, first, warm, inf = (float(x) / 1000.0 for x in m.groups())
      res.update(
          init_ms=init,
          warmup_first_ms=first,
          warmup_avg_ms=warm,
          inference_avg_ms=inf,
      )
    m = _LEGACY_PEAK.search(text)
    if m:
      res["peak_memory_mb"] = float(m.group(1))
  # Op profile summary (when --use_profiler) is printed after the results box,
  # i.e. after the first all-'=' rule that follows "BENCHMARK RESULTS". Without
  # the profiler that tail only holds teardown log lines, which are not a
  # profile, so require one of the profiler's section headings.
  header = text.find("BENCHMARK RESULTS")
  if header != -1:
    closing = re.compile(r"^[^\n=]*={30,}[^\n=]*$", re.M).search(text, header)
    if closing:
      tail = text[closing.end() :].strip()
      if tail and re.search(
          r"Profiling Info|Operator-wise|node type", tail, re.I
      ):
        res["profile_summary"] = tail
  return res


# benchmark_model ends a failed run with "Benchmarking failed." and a non-zero
# exit code. The other markers also catch a crash that an old adb (one that
# does not forward the exit code) reports as exit 0.
_FAILURE_MARKERS = (
    "Benchmarking failed",
    "Segmentation fault",
    "Aborted",
    "Fatal signal",
    "CANNOT LINK EXECUTABLE",
)


def output_unrecognized(code: int, text: str, parsed: dict[str, Any]) -> bool:
  """True if benchmark_model exited 0 but printed no result this script parses.

  That points at a changed output format (a binary newer or older than
  _PATTERNS), not at a failed run, so retrying without the profiler would
  only run the whole benchmark again for the same result.

  Args:
    code: Exit code of the benchmark_model run.
    text: Output of the run.
    parsed: parse_benchmark_log() result for ``text``.

  Returns:
    True if ``code`` is 0, ``parsed`` has no inference average and ``text``
    has none of the _FAILURE_MARKERS.
  """
  return (
      code == 0
      and "inference_avg_ms" not in parsed
      and not any(marker in text for marker in _FAILURE_MARKERS)
  )


def unrecognized_output_error(
    label: str, text: str, bench_src: str, log_path: pathlib.Path, retried: bool
) -> str:
  """Returns the error for a run that exited 0 but printed no parsable result.

  Args:
    label: Name of the run, e.g. ``NPU``.
    text: Output of the run.
    bench_src: Provenance of the benchmark_model binary.
    log_path: Local file with the run's full log.
    retried: Whether the run was already a retry without the profiler.
  """
  what = (
      "printed nothing"
      if not text.strip()
      else "printed no results in the format this script parses"
  )
  tail = "\n".join(text.splitlines()[-20:])
  if retried:
    retry_note = ""
  else:
    retry_note = (
        " No profiler retry was attempted (it cannot fix a format change)."
    )
  return (
      f"{label} benchmark: benchmark_model exited 0 but {what}. The "
      "binary is probably newer or older than the parser (_PATTERNS in "
      f"benchmark_on_device.py). Binary: {bench_src}. Fix: run with the "
      "default release (versions.json) or pin a release whose output "
      f"parses with --benchmark-url {BINARIES_BUCKET}/<release>/"
      "android_arm64/benchmark_model, or update _PATTERNS for the new "
      "format."
      + retry_note
      + (f"\nLast lines:\n{tail}" if tail else "")
      + f"\nFull log: {log_path}"
  )


def analyze_tile_pass(code: int, text: str, report: str) -> dict[str, object]:
  """TPU tile time per inference from the tile pass, or why there is none.

  ``report`` is the hook's dump file (empty if missing); the same numbers are
  also in the log, which is the fallback. The per-inference value is
  ``Total TPU tile time / (warmup + measured runs)`` of this pass. The hook's
  own count is only a consistency check: it was (1 + D) x runs (D = dispatch
  nodes), i.e. 2x for a normal compiled model, with the 2.3.0 binaries
  (observed 2026-10-09), and D x runs with the 2.3.1 binaries re-uploaded on
  2026-10-23 (observed 2026-10-26).

  Args:
    code: Exit code from the tile-time benchmark pass.
    text: Captured stdout/stderr log from the tile-time pass.
    report: Contents of the hook's tile-time report file, or empty string.

  Returns:
    Dictionary describing the tile-time measurement status and metrics.
  """
  run = parse_benchmark_log(text)
  res: dict[str, object] = {
      "status": "failed",
      "reason": None,
      "hook_registered": _HOOKS_REGISTERED in text,
      "warmup_runs": run.get("warmup_runs"),
      "measured_runs": run.get("measured_runs"),
      "dispatch_nodes": run.get("delegated_nodes"),
      # Not reported as latency: the hook adds ~3% per inference (measured).
      "pass_inference_avg_ms": run.get("inference_avg_ms"),
  }
  if code == 124:
    res["reason"] = "the tile-time pass timed out (see tile_time.log)"
    return res
  if code != 0 or "inference_avg_ms" not in run:
    res["reason"] = (
        f"the tile-time pass failed (exit {code}); see tile_time.log"
    )
    return res
  if not res["hook_registered"]:
    res["status"] = "unavailable"
    if _HOOKS_NULL in text:
      res["reason"] = (
          "the dispatch library returned no telemetry hook ('Accelerator "
          "returned null hooks.'); builds from the LiteRT GitHub source have "
          "the hooks compiled out, the Google-built bucket binaries have them"
      )
    else:
      res["reason"] = "no 'registered vendor hooks' line in tile_time.log"
    return res
  source = "file"
  total, count = _TILE_TOTAL_RE.search(report), _TILE_COUNT_RE.search(report)
  if not (total and count):
    source = "log"
    total, count = _TILE_TOTAL_RE.search(text), _TILE_COUNT_RE.search(text)
  if not (total and count):
    res["status"] = "no_report"
    res["reason"] = "the hook wrote no tile report (neither file nor log lines)"
    return res
  runs = (res["warmup_runs"] or 0) + (res["measured_runs"] or 0)
  total_us, hook_count = int(total.group(1)), int(count.group(1))
  res.update(source=source, runs=runs, total_us=total_us, hook_count=hook_count)
  nodes = res["dispatch_nodes"]
  meaning = None
  if runs and hook_count % runs == 0:
    k = hook_count // runs
    res["count_ratio"] = k
    if nodes and k == nodes + 1:
      meaning = (
          f"{k} calls per run ({nodes} dispatch invoke"
          f"{'s' if nodes != 1 else ''} + 1 extra call from the LiteRT "
          "runtime: the known double count, corrected)"
      )
    elif nodes and k == nodes:
      meaning = (
          f"{k} call{'s' if k != 1 else ''} per run, one per dispatch invoke"
      )
    elif k == 1:
      meaning = "1 call per run"
    elif not nodes:
      meaning = f"{k} calls per run (dispatch node count not in the log)"
  elif runs:
    res["count_ratio"] = round(hook_count / runs, 3)
  if meaning is None:
    res["status"] = "inconsistent"
    res["reason"] = (
        f"the hook counted {hook_count} calls for {runs} runs, which matches "
        "no known pattern (1 + D, D or 1 per run; D = dispatch nodes), so no "
        "per-inference value is reported"
    )
    return res
  res.update(
      status="ok",
      count_meaning=meaning,
      per_inference_ms=total_us / runs / 1000.0,
  )
  return res


def tile_time_text(t: dict[str, object]) -> str:
  """Text of the **TPU tile time:** header line."""
  status = t["status"]
  if status == "skipped":
    return "not measured (--no-tile-time)"
  if status == "ok":
    return (
        f"from the dispatch library's hook ({HOOK_ENV}) in a separate hooked "
        f"pass of {t['runs']} runs ({t['warmup_runs']} warmup + "
        f"{t['measured_runs']} measured; warmups included): "
        f"{t['total_us'] / 1000:.2f} ms in total; the hook counted "
        f"{t['hook_count']} = {t['count_meaning']}; per inference = total / "
        f"{t['runs']} runs"
    )
  if t.get("total_us") is not None:
    return (
        f"{status} - {t['total_us'] / 1000:.2f} ms in total over "
        f"{t['runs']} runs, but {t['reason']}"
    )
  return f"{status.replace('_', ' ')} - {t['reason']}"


def analyze_power_pass(code: int, text: str, report: str) -> dict[str, object]:
  """TPU energy per inference from the hooked pass, or why there is none.

  ``report`` is the power hook's dump file (empty if missing); the same numbers
  are also in the log, which is the fallback. The hook's ``Total Energy`` is
  the TPU rail's energy from the start of the first dispatch invoke to the
  model's teardown, so it includes the TPU's idle gaps between inferences.
  The per-inference value is that total / (warmup + measured runs) of the
  pass, like the tile time. The hook's own count is a check: one call per
  dispatch invoke with the 2.3.1 binaries re-uploaded on 2026-10-23 (observed
  2026-10-26); 1 + D per run is the old power hook, whose totals miss most of
  the energy, so it gets no value.

  Args:
    code: Exit code of the hooked benchmark pass.
    text: Captured stdout/stderr log of the hooked pass.
    report: Contents of the power hook's report file, or empty string.

  Returns:
    Dictionary describing the energy measurement status and values.
  """
  run = parse_benchmark_log(text)
  res: dict[str, object] = {
      "status": "failed",
      "reason": None,
      "hook_registered": _HOOKS_REGISTERED in text,
      "warmup_runs": run.get("warmup_runs"),
      "measured_runs": run.get("measured_runs"),
      "dispatch_nodes": run.get("delegated_nodes"),
  }
  if code == 124:
    res["reason"] = "the hooked pass timed out (see tile_time.log)"
    return res
  if code != 0 or "inference_avg_ms" not in run:
    res["reason"] = f"the hooked pass failed (exit {code}); see tile_time.log"
    return res
  if not res["hook_registered"]:
    res["status"] = "unavailable"
    if _HOOKS_NULL in text:
      res["reason"] = (
          "the dispatch library returned no telemetry hook ('Accelerator "
          "returned null hooks.')"
      )
    else:
      res["reason"] = "no 'registered vendor hooks' line in tile_time.log"
    return res
  source = "file"
  total, count = _POWER_TOTAL_RE.search(report), _POWER_COUNT_RE.search(report)
  if not (total and count):
    source = "log"
    total, count = _POWER_TOTAL_RE.search(text), _POWER_COUNT_RE.search(text)
  if not (total and count):
    failure = _POWER_FAILURE_RE.search(text)
    if failure:
      res["status"] = "unavailable"
      res["reason"] = (
          "the power hook could not read the TPU energy counter: "
          f"'{failure.group(0).strip()[:200]}'"
      )
    else:
      res["status"] = "no_report"
      res["reason"] = (
          "the power hook wrote no report (neither file nor log lines)"
      )
    return res
  runs = (res["warmup_runs"] or 0) + (res["measured_runs"] or 0)
  total_uj, hook_count = int(total.group(1)), int(count.group(1))
  res.update(source=source, runs=runs, total_uj=total_uj, hook_count=hook_count)
  nodes = res["dispatch_nodes"]
  meaning = None
  if runs and hook_count % runs == 0:
    k = hook_count // runs
    res["count_ratio"] = k
    if nodes and k == nodes:
      meaning = (
          f"{k} call{'s' if k != 1 else ''} per run, one per dispatch invoke"
      )
    elif nodes and k == nodes + 1:
      res["status"] = "unreliable"
      res["reason"] = (
          f"the hook counted {hook_count} = {k} calls per run, the pattern of "
          "the old power hook, which reads the energy counter around every "
          "call and misses most of the energy, so no value is reported"
      )
      return res
    elif k == 1:
      meaning = "1 call per run"
  elif runs:
    res["count_ratio"] = round(hook_count / runs, 3)
  if meaning is None:
    res["status"] = "inconsistent"
    res["reason"] = (
        f"the hook counted {hook_count} calls for {runs} runs, which matches "
        "no known pattern (D or 1 per run; D = dispatch nodes), so no "
        "per-inference value is reported"
    )
    return res
  res.update(
      status="ok",
      count_meaning=meaning,
      per_inference_mj=total_uj / runs / 1000.0,
  )
  return res


def power_text(p: dict[str, object]) -> str:
  """Text of the **TPU energy:** header line."""
  status = p["status"]
  if status == "skipped":
    return "not measured (--no-power)"
  if status == "ok":
    return (
        f"from the dispatch library's power hook ({HOOK_ENV}) in the hooked "
        f"pass of {p['runs']} runs ({p['warmup_runs']} warmup + "
        f"{p['measured_runs']} measured; warmups included): "
        f"{p['total_uj'] / 1000:.2f} mJ on the TPU rail from the first "
        "inference to the model's teardown, idle gaps included; the hook "
        f"counted {p['hook_count']} = {p['count_meaning']}; per inference = "
        f"total / {p['runs']} runs"
    )
  if p.get("total_uj") is not None:
    return (
        f"{status} - {p['total_uj'] / 1000:.2f} mJ in total over "
        f"{p['runs']} runs, but {p['reason']}"
    )
  return f"{status.replace('_', ' ')} - {p['reason']}"


# --------------------------------------------------------------------------
# Log check: WARNING/ERROR-level lines the reader should look at
# --------------------------------------------------------------------------
# benchmark_model and the LiteRT runtime log as "WARNING: [file:line] ..." /
# "ERROR: ..."; the Google Tensor driver adds abseil-style "E0000 12:34:56 ..."
# lines. Lines matching _BENIGN_LOG_LINES appear in every successful strict run
# on a Pixel (documented in references/benchmark-flags.md) and are only
# counted; everything else is listed verbatim so nobody has to grep the log.
_ATTENTION_RE = re.compile(
    r"\b(?:WARNING|ERROR|FATAL|FAILED|[Ff]ailed|INTERNAL)\b"
    r"|^[EWF]\d{4} \d{2}:\d{2}"
)
_BENIGN_LOG_LINES = (
    re.compile(
        r"Compiler plugin path is provided in the environment, but the "
        r"model is pre-compiled"
    ),
    re.compile(r"dispatch API returned contradictory buffer requirements"),
)
_MAX_UNEXPECTED_LINES = 8  # shown in the report
_MAX_STORED_UNEXPECTED = 50  # kept in results.json


def check_log(text: str) -> dict[str, Any]:
  """Counts known-benign warning lines and collects unexpected ones.

  Unexpected lines are de-duplicated on a digit-normalised key (driver errors
  repeat with different timestamps); the first verbatim occurrence is kept
  with its repeat count.

  Args:
    text: Output of one benchmark_model run.

  Returns:
    Dict with the ``benign_lines`` count, the ``unexpected_total`` count
    (repeats included) and ``unexpected_lines``: up to _MAX_STORED_UNEXPECTED
    distinct lines, each suffixed with (xN) if it occurred N > 1 times.
  """
  benign = 0
  unexpected: dict[str, list[Any]] = {}
  for line in text.splitlines():
    line = line.strip()
    if not line or not _ATTENTION_RE.search(line):
      continue
    if any(p.search(line) for p in _BENIGN_LOG_LINES):
      benign += 1
      continue
    key = re.sub(r"\d+", "N", line)
    if key in unexpected:
      unexpected[key][1] += 1
    else:
      unexpected[key] = [line, 1]
  lines = [
      f"{line} (x{n})" if n > 1 else line for line, n in unexpected.values()
  ]
  return {
      "benign_lines": benign,
      "unexpected_total": sum(n for _, n in unexpected.values()),
      "unexpected_lines": lines[:_MAX_STORED_UNEXPECTED],
  }


def log_check_text(name: str, chk: dict[str, Any] | None) -> str:
  if chk is None:
    return f"{name}: not run"
  n = chk["unexpected_total"]
  return (
      f"{name}: {n} unexpected WARNING/ERROR line{'s' if n != 1 else ''} "
      f"({chk['benign_lines']} known-benign)"
  )


def unexpected_lines_md(checks: dict[str, dict[str, Any] | None]) -> str:
  """Markdown section listing unexpected log lines, or '' if none."""
  items = []
  for name, chk in checks.items():
    lines = (chk or {}).get("unexpected_lines", [])
    for line in lines[:_MAX_UNEXPECTED_LINES]:
      items.append(f"- {name}: `{line.replace('`', chr(39))}`")
    if len(lines) > _MAX_UNEXPECTED_LINES:
      items.append(
          f"- {name}: ... {len(lines) - _MAX_UNEXPECTED_LINES} more "
          "distinct lines (see the log file)"
      )
  if not items:
    return ""
  return (
      "\n\n**Unexpected log lines** (not in the benign list of "
      "references/benchmark-flags.md; judge them before reporting):\n"
      + "\n".join(items)
  )


# --------------------------------------------------------------------------
# Versions: the LiteRT that compiled the model vs the release that runs it
# --------------------------------------------------------------------------
def runtime_release(user_provided: bool, url: str | None) -> str:
  """Bucket release of a binary ('latest', 'X.Y.Z') or how it was given."""
  if user_provided:
    return "user-provided"
  m = re.search(r"/binaries/([^/]+)/android_arm64/", url or "")
  return m.group(1) if m else "custom URL"


def _source_text(release: str) -> str:
  return {
      "user-provided": "user-provided files",
      "custom URL": "a custom URL",
  }.get(release, f"bucket release '{release}'")


def versions_summary(
    sidecar: dict[str, Any] | None, bench_release: str, dispatch_release: str
) -> tuple[str, dict[str, Any]]:
  """Text of the **Versions:** header line and the results.json entry.

  Compares the ai-edge-litert version recorded in the compile sidecar with
  the bucket release the runtime binaries came from. Rolling releases
  ('latest', 'nightly') and local files carry no version number, so the line
  says why the two cannot be compared instead of guessing.

  Args:
    sidecar: Contents of the model's compile sidecar, or None if it has none.
    bench_release: runtime_release() of the benchmark_model binary.
    dispatch_release: runtime_release() of the dispatch library.

  Returns:
    (Versions line text, ``versions`` entry for results.json).
  """
  packages = (sidecar or {}).get("packages") or {}
  compiled = packages.get("ai-edge-litert") or packages.get(
      "ai-edge-litert-nightly"
  )
  sdk = packages.get("ai-edge-litert-sdk-google-tensor") or packages.get(
      "ai-edge-litert-sdk-google-tensor-nightly"
  )
  if compiled:
    compile_text = f"compiled with ai-edge-litert {compiled}"
    if sdk and sdk != compiled:
      compile_text += f" but SDK package {sdk} (DIFFERENT)"
  elif sidecar is None:
    compile_text = "compile version unknown (no compile sidecar)"
  else:
    compile_text = "compile version not recorded in the sidecar"
  if bench_release == dispatch_release:
    runtime_text = f"runtime binaries from {_source_text(bench_release)}"
  else:
    runtime_text = (
        f"benchmark_model from {_source_text(bench_release)}, "
        f"dispatch library from {_source_text(dispatch_release)}"
    )
  if bench_release != dispatch_release:
    match = "mixed_runtime"
    verdict = "the two runtime binaries come from different sources"
  elif not compiled:
    match, verdict = "unknown", "cannot compare"
  elif not re.fullmatch(r"\d+(\.\d+)+", bench_release):
    match = "unverified"
    reason = {
        "user-provided": "local files carry no version",
        "custom URL": "the URL names no release",
    }.get(bench_release, f"'{bench_release}' is a rolling build")
    verdict = f"not comparable ({reason})"
  elif compiled == bench_release:
    match, verdict = "same", "same release"
  else:
    match, verdict = "different", "DIFFERENT releases"
    if compiled == VERSIONS.get(
        "pip_release"
    ) and bench_release == VERSIONS.get("binaries_release"):
      verdict += " (the pair verified in versions.json)"
  entry = {
      "compiled_with": compiled,
      "runtime_release": {
          "benchmark_model": bench_release,
          "dispatch_library": dispatch_release,
      },
      "pinned": {
          "pip_release": VERSIONS.get("pip_release"),
          "binaries_release": VERSIONS.get("binaries_release"),
      },
      "match": match,
  }
  return f"{compile_text}; {runtime_text} - {verdict}", entry


# --------------------------------------------------------------------------
# Main flow
# --------------------------------------------------------------------------
def parse_args(argv=None) -> argparse.Namespace:
  """Parses command-line flags from ``argv`` (default: ``sys.argv[1:]``)."""
  p = argparse.ArgumentParser(
      description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
  )
  p.add_argument(
      "--model",
      required=True,
      help=(
          "Google Tensor AOT-compiled .tflite (from "
          "compile_model.py or any other Google Tensor compile; "
          "check with check_compiled.py)."
      ),
  )
  p.add_argument(
      "--dispatch-lib",
      help=(
          f"{DISPATCH_LIB_NAME}, or a directory/.zip/.aar containing "
          f"it (default: ${DISPATCH_LIB_ENV}, else a cached download "
          "of --dispatch-url)."
      ),
  )
  p.add_argument(
      "--benchmark-bin",
      help=(
          "Local android_arm64 benchmark_model binary. Default: "
          "download --benchmark-url once and cache it."
      ),
  )
  url_default_note = (
      "binaries_release in the skill's versions.json"
      if DEFAULT_BENCHMARK_URL
      else f"unavailable: {VERSIONS_ERROR}".replace("%", "%%")
  )
  p.add_argument(
      "--benchmark-url",
      default=DEFAULT_BENCHMARK_URL,
      help=(
          "Where to download benchmark_model from (default: "
          f"%(default)s; {url_default_note}). Use .../binaries/"
          "<release>/android_arm64/benchmark_model to pin a "
          "release ('latest', 'nightly', 'X.Y.Z', ...)."
      ),
  )
  p.add_argument(
      "--dispatch-url",
      help=(
          f"Where to download {DISPATCH_LIB_NAME} from (default: "
          "same directory as --benchmark-url)."
      ),
  )
  p.add_argument(
      "--refresh-binary",
      action="store_true",
      help=(
          "Re-download the benchmark binary and dispatch library "
          "even if cached."
      ),
  )
  p.add_argument("--serial", help="adb serial (required if >1 device).")
  p.add_argument(
      "--cpu-baseline",
      metavar="ORIGINAL_TFLITE",
      help="Also benchmark this UNCOMPILED model on the CPU.",
  )
  p.add_argument(
      "--cpu-num-threads",
      type=int,
      help="CPU threads for the baseline (default: runtime choice).",
  )
  p.add_argument("--num-runs", type=int, default=50)
  p.add_argument("--warmup-runs", type=int, default=5)
  p.add_argument(
      "--signature",
      help=(
          "Signature key to run (multi-signature "
          "models); passed as --signature_to_run_for."
      ),
  )
  p.add_argument(
      "--performance-mode",
      choices=PERFORMANCE_MODES,
      help="--google_tensor_performance_mode (benchmark default: burst).",
  )
  p.add_argument(
      "--no-profiler",
      action="store_true",
      help="Disable --use_profiler=true (op-level timing).",
  )
  p.add_argument(
      "--no-peak-memory",
      action="store_true",
      help="Disable --report_peak_memory_footprint=true.",
  )
  p.add_argument(
      "--no-tile-time",
      action="store_true",
      help=(
          "Do not read TPU tile time from the dispatch library's hook "
          f"({HOOK_ENV}). With --no-power too, the extra hooked NPU pass is "
          "skipped."
      ),
  )
  p.add_argument(
      "--no-power",
      action="store_true",
      help=(
          "Do not read TPU energy from the dispatch library's power hook "
          "(measured in the same hooked NPU pass as the TPU tile time)."
      ),
  )
  p.add_argument(
      "--extra-arg",
      action="append",
      default=[],
      help=(
          "Extra benchmark_model flag, e.g. --extra-arg=--min_secs=5 "
          "(repeatable; applied to the NPU run and the hooked pass)."
      ),
  )
  p.add_argument(
      "--device-dir",
      default=DEFAULT_DEVICE_DIR,
      help=(
          "Base scratch directory on the phone (default: "
          "%(default)s). Each run pushes into a fresh "
          "<base>/run-<timestamp>-<pid>/ subdirectory and deletes "
          "only that, so files already in the base directory are "
          "never overwritten or removed."
      ),
  )
  p.add_argument(
      "--keep-device-files",
      action="store_true",
      help="Do not delete the per-run device directory afterwards.",
  )
  p.add_argument(
      "--allow-mismatch",
      action="store_true",
      help="Run even if the model's SoC stamp != device SoC.",
  )
  p.add_argument(
      "--allow-cpu-fallback",
      action="store_true",
      help=(
          "Drop --use_cpu=false/--require_full_delegation=true so "
          "partially compiled models run with CPU fallback "
          "(numbers then mix NPU and CPU time)."
      ),
  )
  p.add_argument(
      "--timeout",
      type=int,
      default=900,
      help="Seconds allowed per benchmark run (default: 900).",
  )
  p.add_argument(
      "--output-dir",
      help=(
          "Where to write logs + results.json (default: "
          "./litert_benchmark_results/<timestamp>)."
      ),
  )
  p.add_argument(
      "--dry-run",
      action="store_true",
      help=(
          "Validate inputs and print the adb commands; do not touch the device."
      ),
  )
  return p.parse_args(argv)


def build_npu_args(args, remote_model: str, device_dir: str) -> list[str]:
  """Returns the benchmark_model flags for the NPU run.

  Args:
    args: Parsed command-line arguments.
    remote_model: Device path of the compiled model.
    device_dir: Device directory that holds the dispatch library.
  """
  flags = [
      f"--graph={shlex.quote(remote_model)}",
      "--use_npu=true",
  ]
  if not args.allow_cpu_fallback:
    # Strict mode: abort instead of silently running ops on the CPU.
    flags += ["--use_cpu=false", "--require_full_delegation=true"]
  flags += [
      f"--dispatch_library_path={shlex.quote(device_dir)}",
      f"--num_runs={args.num_runs}",
      f"--warmup_runs={args.warmup_runs}",
  ]
  if not args.no_peak_memory:
    flags.append("--report_peak_memory_footprint=true")
  if not args.no_profiler:
    flags.append("--use_profiler=true")
  if args.signature:
    flags.append(f"--signature_to_run_for={shlex.quote(args.signature)}")
  if args.performance_mode:
    flags.append(f"--google_tensor_performance_mode={args.performance_mode}")
  flags.extend(args.extra_arg)
  return flags


def build_cpu_args(args, remote_model: str) -> list[str]:
  """Returns the benchmark_model flags for the CPU baseline run.

  Args:
    args: Parsed command-line arguments.
    remote_model: Device path of the original (uncompiled) model.
  """
  flags = [
      f"--graph={shlex.quote(remote_model)}",
      "--use_cpu=true",
      f"--num_runs={args.num_runs}",
      f"--warmup_runs={args.warmup_runs}",
  ]
  if not args.no_peak_memory:
    flags.append("--report_peak_memory_footprint=true")
  if not args.no_profiler:
    flags.append("--use_profiler=true")
  if args.signature:
    flags.append(f"--signature_to_run_for={shlex.quote(args.signature)}")
  if args.cpu_num_threads:
    flags.append(f"--num_threads={args.cpu_num_threads}")
  return flags


def build_tile_args(npu_flags: list[str]) -> list[str]:
  """Returns flags for the hooked pass (NPU flags minus profiler/memory).

  Args:
    npu_flags: Command-line flags used for the main NPU benchmark pass.

  Returns:
    Filtered list of command-line flags for the hooked pass (TPU tile time
    and TPU energy).
  """
  drop = {"--use_profiler=true", "--report_peak_memory_footprint=true"}
  return [f for f in npu_flags if f not in drop]


def run_benchmark(
    adb: Adb,
    remote_bin: str,
    flags: list[str],
    log_path: pathlib.Path,
    timeout: int,
    label: str,
    env: str = "",
) -> tuple[int, str]:
  """Runs benchmark_model on the device and writes its output to ``log_path``.

  Args:
    adb: Device connection; in dry-run mode nothing is run.
    remote_bin: Device path of the benchmark_model binary.
    flags: benchmark_model flags, already shell-quoted where needed.
    log_path: Local file that receives the run's output.
    timeout: Seconds allowed for the run before adb is killed.
    label: Tag printed before the command, e.g. ``NPU``.
    env: Optional ``NAME=value`` prefix for the device shell command.

  Returns:
    (exit code, output text); (124, a timeout message) if the run timed out,
    (0, "") in dry-run mode.
  """
  cmd = (f"{env} " if env else "") + f"{shlex.quote(remote_bin)} "
  cmd += " ".join(flags)
  print(f"\n[{label}] adb shell {cmd}")
  if adb.dry_run:
    return 0, ""
  try:
    proc = adb.shell(cmd, timeout=timeout, check=False)
  except subprocess.TimeoutExpired:
    log_path.write_text(f"TIMEOUT after {timeout}s\n")
    return 124, f"timed out after {timeout}s"
  text = proc.stdout or ""
  log_path.write_text(text)
  return proc.returncode, text


def read_device_file(adb: Adb, path: str) -> str:
  """Contents of a small file on the phone, or '' if it cannot be read."""
  try:
    return (
        adb.shell(f"cat {shlex.quote(path)}", check=False, timeout=60).stdout
        or ""
    )
  except subprocess.TimeoutExpired:
    return ""


def fmt(v, digits=2):
  return "-" if v is None else f"{v:.{digits}f}"


def markdown_table(
    npu: dict[str, object],
    cpu: dict[str, object] | None,
    npu_name: str,
    cpu_name: str | None,
    soc: str,
    npu_only_rows: list[tuple[str, str]] | None = None,
) -> str:
  """Formats the NPU (and CPU baseline) results as a Markdown table.

  Args:
    npu: Parsed results of the NPU run (parse_benchmark_log).
    cpu: Parsed results of the CPU baseline run, or None for no CPU column.
    npu_name: File name of the compiled model.
    cpu_name: File name of the CPU baseline model, or None.
    soc: SoC label for the NPU column header.
    npu_only_rows: Extra (metric, value) rows that have no CPU value.

  Returns:
    The table, followed by an NPU speed-up line if both runs report an
    average latency.
  """
  cols = [f"NPU ({soc})"] + (["CPU baseline"] if cpu is not None else [])
  rows = [
      ("Model file", [npu_name] + ([cpu_name] if cpu is not None else [])),
      (
          "Model init (ms)",
          [fmt(npu.get("init_ms")), fmt((cpu or {}).get("init_ms"))],
      ),
      (
          "Warmup first (ms)",
          [
              fmt(npu.get("warmup_first_ms")),
              fmt((cpu or {}).get("warmup_first_ms")),
          ],
      ),
      (
          "Warmup avg (ms)",
          [
              fmt(npu.get("warmup_avg_ms")),
              fmt((cpu or {}).get("warmup_avg_ms")),
          ],
      ),
      (
          "Inference avg (ms)",
          [
              fmt(npu.get("inference_avg_ms")),
              fmt((cpu or {}).get("inference_avg_ms")),
          ],
      ),
      (
          "Inference min / max (ms)",
          [
              (
                  f"{fmt(npu.get('inference_min_ms'))} /"
                  f" {fmt(npu.get('inference_max_ms'))}"
              ),
              (
                  f"{fmt((cpu or {}).get('inference_min_ms'))} / "
                  f"{fmt((cpu or {}).get('inference_max_ms'))}"
              ),
          ],
      ),
      (
          "Inference std (ms)",
          [
              fmt(npu.get("inference_std_ms")),
              fmt((cpu or {}).get("inference_std_ms")),
          ],
      ),
  ]
  if "inference_p50_ms" in npu or "inference_p50_ms" in (cpu or {}):

    def _pct(d):
      return (
          f"{fmt(d.get('inference_p5_ms'), 3)} / "
          f"{fmt(d.get('inference_p50_ms'), 3)} / "
          f"{fmt(d.get('inference_p95_ms'), 3)}"
      )

    rows.append(("Inference p5 / p50 / p95 (ms)", [_pct(npu), _pct(cpu or {})]))
  rows += [(name, [value, "-"]) for name, value in npu_only_rows or []]
  rows += [
      (
          "Peak memory (MB)",
          [
              fmt(npu.get("peak_memory_mb")),
              fmt((cpu or {}).get("peak_memory_mb")),
          ],
      ),
      (
          "Runs (warmup / measured)",
          [
              (
                  f"{npu.get('warmup_runs', '-')} /"
                  f" {npu.get('measured_runs', '-')}"
              ),
              (
                  f"{(cpu or {}).get('warmup_runs', '-')} / "
                  f"{(cpu or {}).get('measured_runs', '-')}"
              ),
          ],
      ),
  ]
  width = 1 + len(cols)
  lines = ["| Metric | " + " | ".join(cols) + " |", "|" + "---|" * width]
  for name, values in rows:
    lines.append(f"| {name} | " + " | ".join(values[: len(cols)]) + " |")
  if cpu and npu.get("inference_avg_ms") and cpu.get("inference_avg_ms"):
    speedup = cpu["inference_avg_ms"] / npu["inference_avg_ms"]
    line = f"\nNPU speed-up vs CPU (avg latency): **{speedup:.2f}x**"
    if speedup < 1:
      line += (
          f" - the CPU was faster by {1 / speedup:.2f}x (expected for "
          "tiny models: per-inference NPU dispatch overhead dominates)"
      )
    lines.append(line)
  return "\n".join(lines)


def main(argv=None) -> int:
  args = parse_args(argv)
  # Agents usually capture stdout through a pipe; without this, progress lines
  # are block-buffered and only appear when the script exits.
  try:
    sys.stdout.reconfigure(line_buffering=True)
  except (AttributeError, ValueError):
    pass
  model = pathlib.Path(args.model).expanduser().resolve()
  if not model.is_file():
    print(f"ERROR: --model {model} not found.", file=sys.stderr)
    return 2
  minfo = inspect_model(model)
  if not minfo["is_tflite"]:
    print(f"ERROR: {model} is not a .tflite flatbuffer.", file=sys.stderr)
    return 2
  if minfo["legacy_ops"]:
    print(legacy_model_error(model, minfo["legacy_ops"], "--model"),
          file=sys.stderr)
    return 2
  if not minfo["compiled"]:
    print(
        f"ERROR: {model} is not AOT-compiled (no DISPATCH_OP/LiteRtStamp). "
        "An uncompiled model cannot run on the Google Tensor TPU; compile it "
        "first with scripts/compile_model.py.",
        file=sys.stderr,
    )
    return 2
  cpu_model = None
  if args.cpu_baseline:
    cpu_model = pathlib.Path(args.cpu_baseline).expanduser().resolve()
    if not cpu_model.is_file():
      print(f"ERROR: --cpu-baseline {cpu_model} not found.", file=sys.stderr)
      return 2
    cinfo = inspect_model(cpu_model)
    if cinfo["is_tflite"] and cinfo["legacy_ops"]:
      print(legacy_model_error(cpu_model, cinfo["legacy_ops"],
                               "--cpu-baseline"), file=sys.stderr)
      return 2
    if not cinfo["is_tflite"] or cinfo["compiled"]:
      print(
          "ERROR: --cpu-baseline must be the ORIGINAL uncompiled .tflite; a "
          "compiled model contains NPU-only DISPATCH_OP nodes and cannot run "
          "on the CPU.",
          file=sys.stderr,
      )
      return 2
  if args.signature:
    # Signature keys are stored verbatim in the flatbuffer, so a missing byte
    # string is a reliable "no such signature". benchmark_model itself only
    # prints a bare "Benchmarking failed." in that case (seen on device).
    key = args.signature.encode()
    for p in [model] + ([cpu_model] if cpu_model else []):
      if key not in p.read_bytes():
        print(
            f"ERROR: signature '{args.signature}' not found in {p.name} "
            "(no such signature key in the flatbuffer). Omit --signature "
            "to run the main subgraph, or check the model's signature list.",
            file=sys.stderr,
        )
        return 2

  stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
  out_dir = (
      pathlib.Path(args.output_dir).expanduser().resolve()
      if args.output_dir
      else pathlib.Path.cwd() / "litert_benchmark_results" / stamp
  )
  scratch = pathlib.Path(tempfile.mkdtemp(prefix="litert_gt_bench_"))
  base_dir = args.device_dir.rstrip("/") or DEFAULT_DEVICE_DIR
  # One fresh sub-directory per run: users often keep their own binaries and
  # models in the base directory, and the cleanup must never touch those.
  device_dir = f"{base_dir}/run-{stamp}-{os.getpid()}"
  base_existed = True  # only remove the base dir if this run created it
  pushed = False
  adb = None

  # Agents' tool runners usually SIGTERM a command on timeout; turn that (and
  # SIGHUP) into an exception so the ``finally`` cleanup below still runs.
  def _terminate(signum, frame):
    del frame  # Unused.
    raise SystemExit(128 + signum)

  for sig in ("SIGTERM", "SIGHUP"):
    if hasattr(signal, sig):
      signal.signal(getattr(signal, sig), _terminate)

  try:
    serial = args.serial if args.dry_run else pick_device(args.serial)
    adb = Adb(serial, args.dry_run)
    soc_prop = adb.getprop("ro.soc.model")
    device_target = SOC_PROP_TO_TARGET.get(soc_prop.strip().lower())
    device = {
        "serial": serial or "(dry-run)",
        "product_model": adb.getprop("ro.product.model"),
        "soc_model": soc_prop,
        "target": device_target,
        "android_version": adb.getprop("ro.build.version.release"),
        "abi": adb.getprop("ro.product.cpu.abi"),
    }
    if not args.dry_run:
      print(
          f"Device: {device['product_model']} ({serial}), SoC "
          f"'{soc_prop}' -> {device_target or 'unknown target'}, Android "
          f"{device['android_version']}, ABI {device['abi']}"
      )
      if device["abi"] and device["abi"] != "arm64-v8a":
        raise BenchmarkError(
            3,
            f"device ABI {device['abi']} is not arm64-v8a; "
            "the prebuilt benchmark_model is android_arm64.",
        )
      if device_target is None:
        print(
            f"WARNING: unrecognised ro.soc.model '{soc_prop}'; cannot verify "
            "that the model matches this device."
        )
      elif device_target not in minfo["soc_models"]:
        msg = (
            f"model is compiled for {', '.join(minfo['soc_models'])} but "
            f"the device is {device_target}. Recompile the ORIGINAL "
            f"(uncompiled) model with --target {device_target}; there is no "
            "runtime fallback."
        )
        if not args.allow_mismatch:
          raise BenchmarkError(4, msg)
        print("WARNING (--allow-mismatch): " + msg)

    dispatch_url = args.dispatch_url or (
        args.benchmark_url.rsplit("/", 1)[0] + "/" + DISPATCH_LIB_NAME
        if args.benchmark_url
        else None
    )
    dispatch_lib, dispatch_src = resolve_dispatch_lib(
        args.dispatch_lib,
        scratch,
        dispatch_url,
        args.refresh_binary,
        dry_run=args.dry_run,
    )
    bench_bin, bench_src = resolve_benchmark_bin(
        args.benchmark_bin,
        args.benchmark_url,
        args.refresh_binary,
        dry_run=args.dry_run,
    )
    # Same precedence as the resolvers: a local file wins over any URL.
    bench_release = runtime_release(
        bool(args.benchmark_bin), args.benchmark_url
    )
    dispatch_release = runtime_release(
        bool(args.dispatch_lib or os.environ.get(DISPATCH_LIB_ENV)),
        dispatch_url,
    )

    remote_bin = f"{device_dir}/benchmark_model"
    remote_model = f"{device_dir}/{safe_name(model)}"
    remote_cpu_model = (
        f"{device_dir}/{safe_name(cpu_model)}" if cpu_model else None
    )
    npu_flags = build_npu_args(args, remote_model, device_dir)
    cpu_flags = build_cpu_args(args, remote_cpu_model) if cpu_model else None
    # Hooked pass: the NPU run once more with the dispatch library's hooks
    # (TPU tile time and/or TPU energy) enabled through a config file in the
    # per-run directory; the hooks' reports go there too, so the normal
    # cleanup removes everything.
    remote_hook_config = f"{device_dir}/{HOOK_CONFIG_NAME}"
    remote_tile_report = f"{device_dir}/{TILE_REPORT_NAME}"
    remote_power_report = f"{device_dir}/{POWER_REPORT_NAME}"
    hook_env = f"{HOOK_ENV}={shlex.quote(remote_hook_config)}"
    tile = {"status": "skipped", "reason": "--no-tile-time"}
    power = {"status": "skipped", "reason": "--no-power"}
    want_tile, want_power = not args.no_tile_time, not args.no_power
    if (want_tile or want_power) and re.search(r'[\s"]', device_dir):
      bad_dir = {
          "status": "unavailable",
          "reason": (
              "the device directory contains whitespace or a double "
              "quote, which the hook's config parser cannot handle (pick "
              "another --device-dir)"
          ),
      }
      if want_tile:
        tile = dict(bad_dir)
      if want_power:
        power = dict(bad_dir)
      want_tile = want_power = False
    if want_power and power_hook_is_old(dispatch_lib):
      power = {"status": "unavailable", "reason": _OLD_POWER_HOOK_REASON}
      want_power = False
    hook_flags = build_tile_args(npu_flags) if want_tile or want_power else None
    metric_names = (("TPU tile time", want_tile), ("TPU energy", want_power))
    hook_label = " + ".join(name for name, on in metric_names if on)

    print(f"Benchmark binary: {bench_src}")
    print(f"Dispatch library: {dispatch_src}")
    print(f"Device scratch dir: {device_dir}")
    print(f"Logs/results dir: {out_dir}")

    print("\nPushing files ...")
    if not args.dry_run:
      base_existed = (
          adb.shell(f"test -d {shlex.quote(base_dir)}", check=False).returncode
          == 0
      )
    adb.shell(f"mkdir -p {shlex.quote(device_dir)}")
    pushed = True
    adb.run("push", str(bench_bin), remote_bin, timeout=300)
    adb.shell(f"chmod 755 {shlex.quote(remote_bin)}")
    adb.run(
        "push",
        str(dispatch_lib),
        f"{device_dir}/{DISPATCH_LIB_NAME}",
        timeout=300,
    )
    adb.run("push", str(model), remote_model, timeout=600)
    if cpu_model:
      adb.run("push", str(cpu_model), remote_cpu_model, timeout=600)
    if hook_flags:
      local_hook_config = scratch / HOOK_CONFIG_NAME
      local_hook_config.write_text(
          hook_config(device_dir, want_tile, want_power)
      )
      adb.run("push", str(local_hook_config), remote_hook_config, timeout=60)

    if args.dry_run:
      run_benchmark(adb, remote_bin, npu_flags, scratch / "x", 1, "NPU")
      if hook_flags:
        run_benchmark(
            adb,
            remote_bin,
            hook_flags,
            scratch / "t",
            1,
            hook_label,
            env=hook_env,
        )
        print(
            f"  [dry-run] {HOOK_CONFIG_NAME} pushed above:\n"
            + "\n".join(
                f"    {line}"
                for line in hook_config(
                    device_dir, want_tile, want_power
                ).splitlines()
            )
        )
      if not want_tile and tile["status"] != "skipped":
        print(f"  [dry-run] TPU tile time: {tile_time_text(tile)}")
      if not want_power and power["status"] != "skipped":
        print(f"  [dry-run] TPU energy: {power_text(power)}")
      if cpu_flags:
        run_benchmark(adb, remote_bin, cpu_flags, scratch / "y", 1, "CPU")
      print(
          "\n--dry-run: nothing was executed on the device and nothing was "
          "pushed; the adb commands above (and the cleanup command printed "
          "below) are what the real run would execute. The device was NOT "
          "contacted, so the SoC/ABI match was not verified; the real run "
          "does that first."
      )
      return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    thermal = read_thermal(adb)
    print(f"Thermal before NPU run: {thermal_text(thermal)}")
    code, text = run_benchmark(
        adb, remote_bin, npu_flags, out_dir / "npu.log", args.timeout, "NPU"
    )
    npu = parse_benchmark_log(text)
    timed_out = code == 124
    retried_without_profiler = False
    if (
        (code != 0 or "inference_avg_ms" not in npu)
        and not args.no_profiler
        and not timed_out
        and not output_unrecognized(code, text, npu)
    ):
      print(
          "NPU run failed with --use_profiler=true; retrying without the "
          "profiler (first attempt's log kept as npu_profiled_attempt.log) ..."
      )
      (out_dir / "npu.log").rename(out_dir / "npu_profiled_attempt.log")
      retry_flags = [f for f in npu_flags if f != "--use_profiler=true"]
      code, text = run_benchmark(
          adb, remote_bin, retry_flags, out_dir / "npu.log", args.timeout, "NPU"
      )
      npu = parse_benchmark_log(text)
      timed_out = code == 124
      retried_without_profiler = True
    npu_text = text
    if code != 0 or "inference_avg_ms" not in npu:
      if timed_out:
        raise BenchmarkError(
            6,
            f"NPU benchmark did not finish within --timeout {args.timeout}s "
            "(the adb process was killed, which also ends benchmark_model on "
            "the phone). Raise --timeout, or lower --num-runs / "
            "--extra-arg=--max_secs=N.",
        )
      if output_unrecognized(code, text, npu):
        raise BenchmarkError(
            6,
            unrecognized_output_error(
                "NPU",
                text,
                bench_src,
                out_dir / "npu.log",
                retried_without_profiler,
            ),
        )
      tail = "\n".join(text.splitlines()[-40:])
      raise BenchmarkError(
          6,
          f"NPU benchmark failed (exit {code}). Last lines:\n{tail}\n"
          f"Full log: {out_dir / 'npu.log'}",
      )
    if npu.get("profile_summary"):
      (out_dir / "npu_profile.txt").write_text(npu["profile_summary"])

    # Hooked-pass problems are reported in the header, never fatal: the NPU
    # latency results are already complete at this point.
    hook_text = None
    if hook_flags:
      code, hook_text = run_benchmark(
          adb,
          remote_bin,
          hook_flags,
          out_dir / "tile_time.log",
          args.timeout,
          hook_label,
          env=hook_env,
      )
      tile_report = power_report = ""
      if code != 124:
        if want_tile:
          tile_report = read_device_file(adb, remote_tile_report)
          if _TILE_TOTAL_RE.search(tile_report):
            (out_dir / "tile_time_report.txt").write_text(tile_report)
        if want_power:
          power_report = read_device_file(adb, remote_power_report)
          if _POWER_TOTAL_RE.search(power_report):
            (out_dir / "power_report.txt").write_text(power_report)
      if want_tile:
        tile = analyze_tile_pass(code, hook_text, tile_report)
        tile.update(flags=hook_flags, env=hook_env)
        print(f"TPU tile time: {tile_time_text(tile)}")
      if want_power:
        power = analyze_power_pass(code, hook_text, power_report)
        power.update(flags=hook_flags, env=hook_env)
        print(f"TPU energy: {power_text(power)}")

    cpu = None
    cpu_text = None
    if cpu_flags:
      code, text = run_benchmark(
          adb, remote_bin, cpu_flags, out_dir / "cpu.log", args.timeout, "CPU"
      )
      cpu = parse_benchmark_log(text)
      cpu_text = text
      if code != 0 or "inference_avg_ms" not in cpu:
        if output_unrecognized(code, text, cpu):
          reason = (
              "benchmark_model exited 0 but its output format was not "
              "recognized, see _PATTERNS"
          )
        else:
          reason = f"exit {code}"
        print(
            f"WARNING: CPU baseline failed ({reason}); see "
            f"{out_dir / 'cpu.log'}. Reporting NPU only."
        )
        cpu = None
      elif cpu.get("profile_summary"):
        (out_dir / "cpu_profile.txt").write_text(cpu["profile_summary"])
    log_checks = {
        "npu.log": check_log(npu_text),
        "cpu.log": check_log(cpu_text) if cpu_text is not None else None,
    }
    if hook_text is not None:
      log_checks["tile_time.log"] = check_log(hook_text)
    npu_only_rows = []
    if tile["status"] != "skipped":
      npu_only_rows.append((
          "TPU tile time / inference (ms)",
          fmt(tile.get("per_inference_ms"), 3),
      ))
    if power["status"] != "skipped":
      npu_only_rows.append((
          "TPU energy / inference (mJ)",
          fmt(power.get("per_inference_mj"), 3),
      ))

    soc_label = device_target or "/".join(minfo["soc_models"]) or "NPU"
    table = markdown_table(
        {k: v for k, v in npu.items() if k != "profile_summary"},
        {k: v for k, v in cpu.items() if k != "profile_summary"}
        if cpu
        else None,
        model.name,
        cpu_model.name if cpu_model else None,
        soc_label,
        npu_only_rows,
    )
    mode = (
        "NPU with CPU fallback allowed (--allow-cpu-fallback)"
        if args.allow_cpu_fallback
        else "strict NPU (--use_cpu=false --require_full_delegation=true)"
    )
    # Compile provenance: only from compile_model.py's sidecar, never guessed.
    sidecar = read_compile_sidecar(model)
    if sidecar:
      flags = " ".join(sidecar.get("cli_flags") or []) or "(compiler defaults)"
      if sidecar.get("ops_total") is not None:
        ops_text = (
            f"{sidecar.get('ops_offloaded')} / {sidecar['ops_total']} "
            "ops offloaded"
        )
      else:
        ops_text = "op counts not recorded"
      compile_text = f"{flags}; {ops_text} (from {model.name}.compile.json)"
    else:
      compile_text = (
          f"unknown - no {model.name}.compile.json next to the "
          "model (compiled elsewhere); see Delegation below"
      )
    versions_text, versions_entry = versions_summary(
        sidecar, bench_release, dispatch_release
    )
    if "delegated_nodes" in npu:
      delegation_text = (
          f"{npu['delegated_nodes']} of {npu['total_nodes']} "
          f"node(s) replaced by {npu.get('delegate')} at run "
          "time"
      )
      if npu["delegated_nodes"] != npu["total_nodes"]:
        delegation_text += " - NOT fully delegated"
    else:
      delegation_text = "no 'Replacing N out of M node(s)' line in npu.log"
    # Every value below comes from the device or this run; the report in
    # SKILL.md is meant to be this block pasted verbatim. Paths under the
    # current directory are shown relative to it to keep the block readable;
    # results.json keeps the full strings.
    cwd_prefix = os.getcwd().rstrip(os.sep) + os.sep

    def _short(text: str) -> str:
      return text.replace(cwd_prefix, "")

    retry_text = (
        "yes - the profiled attempt failed, see npu_profiled_attempt.log"
        if retried_without_profiler
        else "none"
    )
    log_check_line = "; ".join(
        log_check_text(name, chk) for name, chk in log_checks.items()
    )
    header = (
        f"**Device:** {device['product_model']} (serial {serial}), "
        f"SoC {soc_prop}, Android {device['android_version']}  \n"
        f"**Model:** {model.name} ({fmt_size(minfo['size_bytes'])}, "
        f"compiled for {'/'.join(minfo['soc_models']) or 'unknown SoC'})  \n"
        f"**Compile:** {compile_text}  \n"
        f"**Versions:** {versions_text}  \n"
        f"**Delegation (runtime):** {delegation_text}  \n"
        f"**Mode:** {mode}; requested {args.warmup_runs} warmup / "
        f"{args.num_runs} measured runs (actual counts in the table)  \n"
        f"**Thermal before NPU run:** {thermal_text(thermal)}  \n"
        f"**TPU tile time:** {tile_time_text(tile)}  \n"
        f"**TPU energy:** {power_text(power)}  \n"
        f"**Benchmark binary:** {_short(bench_src)}  \n"
        f"**Dispatch library:** {_short(dispatch_src)}  \n"
        f"**NPU flags:** `{' '.join(npu_flags)}`  \n"
        f"**Log check:** {log_check_line}; profiler retry: {retry_text}  \n"
        f"**Logs:** {_short(str(out_dir))}"
    )
    report_md = header + "\n\n" + table + unexpected_lines_md(log_checks)
    print("\n" + report_md)
    if cpu:
      cpu_entry = {
          "model": str(cpu_model),
          "flags": cpu_flags,
          **{k: v for k, v in cpu.items() if k != "profile_summary"},
      }
    else:
      cpu_entry = None
    results = {
        "timestamp": stamp,
        "device": device,
        "thermal_before_npu_run": thermal,
        "benchmark_binary": bench_src,
        "dispatch_library": dispatch_src,
        "model": {
            "path": str(model),
            "size_bytes": minfo["size_bytes"],
            "soc_models": minfo["soc_models"],
        },
        "compile": sidecar,
        "versions": versions_entry,
        "npu": {
            "flags": npu_flags,
            **{k: v for k, v in npu.items() if k != "profile_summary"},
        },
        "cpu": cpu_entry,
        "tpu_tile_time": tile,
        "tpu_energy": power,
        "log_check": {
            **log_checks,
            "retried_without_profiler": retried_without_profiler,
        },
        "markdown": report_md,
    }
    (out_dir / "results.json").write_text(json.dumps(results, indent=2))
    # The same block as a file, so "save the report" needs no retyping.
    (out_dir / "report.md").write_text(report_md + "\n")
    print(f"\nWrote {out_dir / 'results.json'} and {out_dir / 'report.md'}")
    return 0
  except BenchmarkError as e:
    print(f"ERROR: {e}", file=sys.stderr)
    return e.code
  except KeyboardInterrupt:
    print(
        "\nInterrupted (Ctrl-C); cleaning up the device directory ...",
        file=sys.stderr,
    )
    return 130
  finally:
    # Runs on success, errors, Ctrl-C (KeyboardInterrupt) and SIGTERM/SIGHUP
    # (SystemExit from _terminate). Killing the local adb client also ends
    # benchmark_model on the phone (verified: no process left behind).
    if adb is not None and pushed and not args.keep_device_files:
      try:
        adb.shell(f"rm -rf {shlex.quote(device_dir)}", check=False, timeout=60)
        if not base_existed:
          # rmdir only succeeds on an empty directory, so this can never take
          # anything else with it.
          adb.shell(f"rmdir {shlex.quote(base_dir)}", check=False, timeout=30)
        if not args.dry_run:
          print(f"Cleaned up {device_dir} on the device.")
      except Exception as e:  # pylint: disable=broad-exception-caught
        print(
            f"WARNING: device cleanup failed: {e}. Run: adb shell rm -rf "
            f"{device_dir}",
            file=sys.stderr,
        )
    elif adb is not None and pushed and not args.dry_run:
      print(
          f"Kept device files in {device_dir} (--keep-device-files). Remove "
          f"with: adb shell rm -rf {device_dir}"
      )
    shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
  sys.exit(main())
