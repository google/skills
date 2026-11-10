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

"""Installs the user's app on a Pixel the way Google Play would.

It then checks that the model runs on the Google Tensor TPU.

For an Android (Gradle) app set up with package_ai_pack.py (SKILL.md steps 5
and 6). The script:

  1. finds the app module, its device-targeting XML, the Android SDK, adb,
     Java, Gradle (the project's ./gradlew) and bundletool;
  2. reads the attached Pixel's SoC and picks its device group;
  3. builds the app bundle (:<app module>:bundleDebug, or the bundle task of
     --variant, e.g. bundleRelease or bundleFreeDebug);
  4. runs bundletool build-apks --local-testing and install-apks for that
     device group: what Google Play would install on this phone;
  5. checks the installed splits and the Google Tensor dispatch library;
  6. starts the app and waits for TensorModelLoader's LITERT_TENSOR_RESULT
     log line ("path":"npu" or "cpu").

bundletool comes from --bundletool (a bundletool-all jar, or a folder of
jars), else bundletool-all-<bundletool_release>.jar from GitHub, cached in
~/.cache/litert-google-tensor/ (bundletool_release is in versions.json).

Local testing cannot update an installed app. If the app is installed, the
script stops (exit 7) unless --uninstall-first is passed. Uninstalling
deletes the app's data on the phone, so ask the user first. The app stays
installed afterwards. The script never signs for release or uploads.

Exit codes
----------
0 the model ran on the TPU, or on the CPU on a phone the app has no Google
  Tensor build for; with --no-launch: installed
1 the app used the CPU on a phone it has a Google Tensor build for
2 bad arguments or environment (project, app module, SDK, adb, Java, Gradle,
  device)
3 the Gradle build failed
4 bundletool failed (download, build-apks or install-apks)
6 no LITERT_TENSOR_RESULT line within --timeout (the app must call
  TensorModelLoader.load(): open the screen that uses the model)
7 the app is already installed: rerun with --uninstall-first once the user
  agrees
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
from typing import Any
import urllib.request
import xml.etree.ElementTree as ET

SKILL_DIR = pathlib.Path(__file__).resolve().parent.parent
VERSIONS_FILE = SKILL_DIR / "assets" / "versions.json"
CACHE_DIR = pathlib.Path.home() / ".cache" / "litert-google-tensor"
BUNDLETOOL_URL = ("https://github.com/google/bundletool/releases/download/"
                  "{v}/bundletool-all-{v}.jar")
BUNDLETOOL_MAIN = "com.android.tools.build.bundletool.BundleToolMain"
SETTINGS_FILES = ("settings.gradle.kts", "settings.gradle")
BUILD_FILES = ("build.gradle.kts", "build.gradle")
DTC_NS = "http://schemas.android.com/apk/config"
LOG_TAG = "LiteRtTensor"
RESULT_PREFIX = "LITERT_TENSOR_RESULT "
DISPATCH_LIB = "libLiteRtDispatch_GoogleTensor.so"
TENSOR_SOC_RE = re.compile(r"Tensor G\d+")

_COMMENT_RE = re.compile(
    r"(\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*')|//[^\n]*|/\*.*?\*/", re.S
)
_INCLUDE_RE = re.compile(r"\binclude\s*\(([^)]*)\)|\binclude[ \t]+([^\n]+)")
_QUOTED_RE = re.compile(r"[\"'](:?[\w.\-:]+)[\"']")
_DTC_RE = re.compile(
    r"\bdeviceTargetingConfig\b\s*(?:=|\.set\s*\()?\s*"
    r"(?P<fn>rootProject\.file|project\.file|layout\.projectDirectory\.file|"
    r"file)\s*\(\s*[\"'](?P<path>[^\"']+)[\"']"
)
_APP_PLUGIN_RE = re.compile(
    r"com\.android\.application|android\.application(?![\w.])")
_APPLY_FALSE_RE = re.compile(r"[^\n]*?\bapply\s*\(?\s*false\b")


class VerifyError(Exception):
  """A failure with the exit code to return and a message naming the fix."""

  def __init__(self, code: int, message: str):
    super().__init__(message)
    self.code = code


def parse_args(argv=None) -> argparse.Namespace:
  """Parses the command-line arguments (default: sys.argv[1:])."""
  p = argparse.ArgumentParser(
      description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  p.add_argument("--project", required=True,
                 help="Root of the app's Gradle project (the folder with "
                 "settings.gradle.kts).")
  p.add_argument("--app-module",
                 help="Gradle path of the app module (default: the only "
                 "module that applies com.android.application).")
  p.add_argument("--variant", default="debug",
                 help="Build variant to bundle: debug (default), release, or "
                 "a product-flavor variant such as freeDebug. bundletool "
                 "signs the APKs with the debug key for local testing.")
  p.add_argument("--serial", help="adb serial (required if >1 device).")
  p.add_argument("--gradle",
                 help="Gradle command, split on spaces, so it can carry "
                 "options such as -Pname=value (default: the project's "
                 "gradlew, else gradle on PATH).")
  p.add_argument("--bundletool",
                 help="A bundletool-all jar, or a folder of bundletool jars "
                 "(default: cached download of bundletool_release).")
  p.add_argument("--sdk", help="Android SDK folder (default: ANDROID_HOME, "
                 "ANDROID_SDK_ROOT, local.properties, ~/Android/Sdk).")
  p.add_argument("--uninstall-first", action="store_true",
                 help="Uninstall an installed copy of the app first (deletes "
                 "its data on the phone: ask the user).")
  p.add_argument("--no-launch", action="store_true",
                 help="Stop after installing; do not start the app.")
  p.add_argument("--timeout", type=int, default=120,
                 help="Seconds to wait for the LITERT_TENSOR_RESULT line "
                 "(default 120).")
  p.add_argument("--output-dir",
                 help="Where to write logs, results.json and report.md "
                 "(default ./litert_app_verify/<timestamp>).")
  p.add_argument("--keep-apks", action="store_true",
                 help="Keep the .apks file bundletool built (it is large).")
  p.add_argument("--dry-run", action="store_true",
                 help="Check the project, tools and phone and print the "
                 "plan; build and install nothing.")
  p.add_argument("--json", action="store_true",
                 help="Print a JSON summary only.")
  return p.parse_args(argv)


# --------------------------------------------------------------------------
# Project
# --------------------------------------------------------------------------


def _read(path: pathlib.Path) -> str:
  try:
    return path.read_text(encoding="utf-8", errors="replace")
  except OSError:
    return ""


def _strip(text: str) -> str:
  return _COMMENT_RE.sub(lambda m: m.group(1) or "", text)


def applies_app_plugin(text: str) -> bool:
  """True if a build file applies the Android application plugin.

  A root build file that only declares it (``... apply false``) does not.

  Args:
    text: Contents of the build file, with comments stripped.

  Returns:
    Whether the build file applies the plugin.
  """
  return any(not _APPLY_FALSE_RE.match(text, m.end())
             for m in _APP_PLUGIN_RE.finditer(text))


def find_project(raw: str) -> tuple[pathlib.Path, pathlib.Path]:
  root = pathlib.Path(raw).expanduser().resolve()
  for name in SETTINGS_FILES:
    if (root / name).is_file():
      return root, root / name
  raise VerifyError(2, f"no settings.gradle.kts or settings.gradle in {root}: "
                    "pass the root folder of the app's Gradle project.")


def find_app_module(root: pathlib.Path, settings: pathlib.Path,
                    wanted: str | None) -> dict[str, Any]:
  """{dir, gradle_path, build_file, text} of the app module."""
  paths = {":": root}
  for m in _INCLUDE_RE.finditer(_strip(_read(settings))):
    for path in _QUOTED_RE.findall(m.group(1) or m.group(2) or ""):
      gradle_path = ":" + path.lstrip(":")
      paths[gradle_path] = root.joinpath(*gradle_path[1:].split(":"))
  modules = []
  for gradle_path, folder in paths.items():
    build = next((folder / n for n in BUILD_FILES if (folder / n).is_file()),
                 None)
    if build:
      modules.append({"dir": folder, "gradle_path": gradle_path,
                      "build_file": build, "text": _strip(_read(build))})
  if wanted:
    want = ":" + wanted.strip(":")
    for module in modules:
      if module["gradle_path"] == want:
        return module
    raise VerifyError(2, f"--app-module {wanted}: not an included module with "
                      f"a build file in {settings}.")
  apps = [m for m in modules if applies_app_plugin(m["text"])]
  if len(apps) != 1:
    found = ", ".join(m["gradle_path"] for m in apps) or "none"
    raise VerifyError(2, f"cannot tell the app module (modules applying "
                      f"com.android.application: {found}); pass --app-module.")
  return apps[0]


def device_groups(app: dict[str, Any],
                  root: pathlib.Path) -> tuple[dict[str, Any], str | None]:
  """({"Tensor G5": group}, XML path) from the app's device-targeting XML."""
  m = _DTC_RE.search(app["text"])
  if not m:
    return {}, None
  path = pathlib.Path(m.group("path")).expanduser()
  if not path.is_absolute():
    path = (root if m.group("fn") == "rootProject.file"
            else app["dir"]) / path
  try:
    tree = ET.parse(path).getroot()
  except (OSError, ET.ParseError) as e:
    raise VerifyError(2, f"cannot read the device-targeting XML {path}: {e}"
                      ) from e
  groups = {}
  for group in tree.iter(f"{{{DTC_NS}}}device-group"):
    socs = [(s.get("manufacturer"), s.get("model"))
            for s in group.iter(f"{{{DTC_NS}}}system-on-chip")]
    if len(socs) == 1 and socs[0][0] == "Google" and TENSOR_SOC_RE.fullmatch(
        socs[0][1] or ""):
      groups[socs[0][1]] = group.get("name")
  return groups, str(path)


def bundle_task(gradle_path: str, variant: str) -> str:
  """Bundle task of a variant: (":app", "freeDebug") -> ":app:bundleFreeDebug".

  The root project as the app module (":") gives ":bundleFreeDebug".

  Args:
    gradle_path: Gradle path of the app module, e.g. ":app".
    variant: Build variant name, e.g. "debug" or "freeDebug".

  Returns:
    The Gradle path of the variant's bundle task.
  """
  return f"{gradle_path.rstrip(':')}:bundle{variant[0].upper()}{variant[1:]}"


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------


def find_sdk(explicit: str | None, root: pathlib.Path) -> pathlib.Path | None:
  local = re.search(r"(?m)^\s*sdk\.dir\s*=\s*(.+?)\s*$",
                    _read(root / "local.properties"))
  candidates = [explicit, os.environ.get("ANDROID_HOME"),
                os.environ.get("ANDROID_SDK_ROOT"),
                local.group(1).replace("\\:", ":") if local else None,
                str(pathlib.Path.home() / "Android" / "Sdk"),
                str(pathlib.Path.home() / "Library" / "Android" / "sdk")]
  for c in candidates:
    if c and (pathlib.Path(c) / "platform-tools").is_dir():
      return pathlib.Path(c)
  return None


def find_aapt2(sdk: pathlib.Path | None) -> pathlib.Path | None:
  """aapt2 of the newest build-tools (bundletool jars without aapt2)."""
  if not sdk:
    return None

  def version(path: pathlib.Path) -> list[int]:
    return [int(x) if x.isdigit() else 0
            for x in path.parent.name.replace("-", ".").split(".")]

  found = sorted((sdk / "build-tools").glob("*/aapt2*"), key=version)
  return found[-1] if found else None


def find_tools(args: argparse.Namespace, root: pathlib.Path) -> dict[str, Any]:
  """Finds the Android SDK, adb, Java, Gradle and aapt2.

  Args:
    args: Parsed command-line arguments.
    root: Root folder of the app's Gradle project.

  Returns:
    {"sdk", "adb", "java", "gradle", "aapt2"}: the SDK folder (or None), the
    adb and java paths, the Gradle command (a list) and aapt2 (or None).

  Raises:
    VerifyError: adb, java or Gradle is not found.
  """
  sdk = find_sdk(args.sdk, root)
  adb_path = shutil.which("adb") or (
      str(sdk / "platform-tools" / "adb") if sdk else None)
  java_home = os.environ.get("JAVA_HOME")
  java = (str(pathlib.Path(java_home) / "bin" / "java") if java_home
          else shutil.which("java"))
  wrapper = root / ("gradlew.bat" if os.name == "nt" else "gradlew")
  gradle = (args.gradle.split() if args.gradle else
            [str(wrapper)] if wrapper.is_file() else
            [shutil.which("gradle")] if shutil.which("gradle") else None)
  missing = [name for name, value in (("adb", adb_path), ("java", java),
                                      ("Gradle", gradle)) if not value]
  if missing:
    raise VerifyError(
        2, f"{', '.join(missing)} not found. Install the Android SDK "
        "platform-tools (adb) and a JDK the project's Gradle supports (set "
        "JAVA_HOME), and run from a project with ./gradlew (or pass "
        "--gradle).")
  return {"sdk": sdk, "adb": adb_path, "java": java, "gradle": gradle,
          "aapt2": find_aapt2(sdk)}


def read_bundletool_release() -> str | None:
  try:
    value = json.loads(VERSIONS_FILE.read_text(encoding="utf-8")).get(
        "bundletool_release")
  except (OSError, ValueError):
    return None
  return value if isinstance(value, str) else None


def bundletool_command(args: argparse.Namespace, java: str,
                       dry_run: bool) -> tuple[list[str], str]:
  """(command prefix, where it comes from)."""
  if args.bundletool:
    path = pathlib.Path(args.bundletool).expanduser().resolve()
    if path.is_dir():
      return ([java, "-cp", str(path / "*"), BUNDLETOOL_MAIN],
              f"jars in {path}")
    if path.is_file():
      return [java, "-jar", str(path)], str(path)
    raise VerifyError(2, f"--bundletool {path} does not exist.")
  release = read_bundletool_release()
  if not release:
    raise VerifyError(2, f"no bundletool_release in {VERSIONS_FILE}: restore "
                      "the file, or pass --bundletool.")
  jar = CACHE_DIR / f"bundletool-all-{release}.jar"
  url = BUNDLETOOL_URL.format(v=release)
  if not jar.is_file() and not dry_run:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    part = jar.with_suffix(".part")
    try:
      with urllib.request.urlopen(url, timeout=120) as response, open(
          part, "wb") as out:
        shutil.copyfileobj(response, out)
      part.replace(jar)
    except OSError as e:
      part.unlink(missing_ok=True)
      raise VerifyError(4, f"cannot download {url} ({e}). Download a "
                        "bundletool-all jar yourself and pass --bundletool."
                        ) from e
  return [java, "-jar", str(jar)], (
      str(jar) if jar.is_file() else f"{url} (not downloaded yet)")


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def run(cmd: list[str], log: pathlib.Path, code: int, what: str,
        cwd: pathlib.Path | None = None) -> str:
  """Runs ``cmd`` with its output in ``log``; raises VerifyError on failure."""
  with open(log, "w", encoding="utf-8") as f:
    proc = subprocess.run(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT,
                          check=False)
  text = log.read_text(encoding="utf-8", errors="replace")
  if proc.returncode != 0:
    tail = "\n".join(text.splitlines()[-25:])
    raise VerifyError(code, f"{what} failed (exit {proc.returncode}); log: "
                      f"{log}\n{tail}")
  return text


def adb(tools: dict[str, Any], serial: str | None, *args: str,
        timeout: int = 60, check: bool = True) -> str:
  cmd = [tools["adb"]] + (["-s", serial] if serial else []) + list(args)
  try:
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout, check=False)
  except (OSError, subprocess.TimeoutExpired) as e:
    raise VerifyError(2, f"{' '.join(cmd)}: {e}") from e
  if check and proc.returncode != 0:
    raise VerifyError(2, f"{' '.join(cmd)} failed: {proc.stderr.strip()}")
  return proc.stdout


def pick_device(tools: dict[str, Any], serial: str | None) -> str:
  lines = adb(tools, None, "devices").splitlines()[1:]
  devices = [l.split()[0] for l in lines if l.strip().endswith("device")]
  if serial:
    if serial not in devices:
      raise VerifyError(2, f"device {serial} is not in `adb devices`.")
    return serial
  if len(devices) != 1:
    raise VerifyError(2, f"need exactly one device, found "
                      f"{devices or 'none'}: connect the Pixel (USB "
                      "debugging on) or pass --serial.")
  return devices[0]


def device_info(tools: dict[str, Any], serial: str) -> dict[str, Any]:
  def prop(name: str) -> str:
    return adb(tools, serial, "shell", "getprop", name).strip()

  sdk = prop("ro.build.version.sdk")
  return {"serial": serial, "model": prop("ro.product.model"),
          "soc": prop("ro.soc.model"),
          "sdk": int(sdk) if sdk.isdigit() else 0,
          "build_id": prop("ro.build.id")}


def npu_reason(device: dict[str, Any]) -> str | None:
  """Why LiteRT will not use the Google Tensor NPU here, or None."""
  if not TENSOR_SOC_RE.fullmatch(device["soc"]):
    return f"not a Google Tensor phone (SoC {device['soc'] or 'unknown'})"
  if device["sdk"] < 36:
    return f"Android API {device['sdk']}; the NPU needs API 36 or newer"
  if device["build_id"].startswith("BP2A"):
    return f"build {device['build_id']} has no NPU support"
  return None


def wait_for_result(tools: dict[str, Any], serial: str, package: str,
                    timeout: int) -> dict[str, Any] | None:
  """Polls logcat for the app's LITERT_TENSOR_RESULT line.

  Args:
    tools: The tools from find_tools().
    serial: adb serial of the device.
    package: Application id of the installed app.
    timeout: Seconds to wait for the line.

  Returns:
    The JSON after the LITERT_TENSOR_RESULT prefix, or None on timeout.
  """
  deadline = time.time() + timeout
  hint_at = time.time() + 20
  while time.time() < deadline:
    time.sleep(2)
    pid = adb(tools, serial, "shell", "pidof", package, check=False).strip()
    if pid:
      log = adb(tools, serial, "logcat", "-d", f"--pid={pid.split()[0]}",
                "-s", f"{LOG_TAG}:I", check=False)
      for line in log.splitlines():
        if RESULT_PREFIX in line:
          try:
            return json.loads(line.split(RESULT_PREFIX, 1)[1])
          except ValueError:
            continue
    if time.time() > hint_at:
      print("Waiting for LITERT_TENSOR_RESULT. If the app loads the model "
            "later (on a particular screen), open it on the phone now.",
            flush=True)
      hint_at = deadline
  return None


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def verify(args: argparse.Namespace) -> dict[str, Any]:
  """Builds and installs the app, starts it and waits for its result line.

  With --dry-run it only checks the project, tools and phone and returns the
  plan; with --no-launch it stops after installing.

  Args:
    args: Parsed command-line arguments.

  Returns:
    The plan and, unless --dry-run, the install and launch results; "status"
    is "dry-run", "installed", "ran" or "no_result".

  Raises:
    VerifyError: A step failed; its code is the exit code to return.
  """
  if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", args.variant):
    raise VerifyError(2, f"--variant {args.variant}: pass a build variant "
                      "name such as debug, release or freeDebug.")
  root, settings = find_project(args.project)
  app = find_app_module(root, settings, args.app_module)
  groups, xml = device_groups(app, root)
  tools = find_tools(args, root)
  bundletool, bundletool_src = bundletool_command(args, tools["java"],
                                                  args.dry_run)
  serial = pick_device(tools, args.serial)
  device = device_info(tools, serial)
  group = groups.get(device["soc"])
  reason = npu_reason(device) or (
      None if group else f"the app has no Google Tensor build for "
      f"{device['soc']} (groups: {', '.join(groups.values()) or 'none'})")
  task = bundle_task(app["gradle_path"], args.variant)
  plan = {
      "project": str(root),
      "app_module": app["gradle_path"],
      "device_targeting_config": xml,
      "device": device,
      "device_group": group,
      "expect_npu": reason is None,
      "npu_reason": reason,
      "gradle": " ".join(tools["gradle"] + [task]),
      "bundletool": bundletool_src,
      "aapt2": str(tools["aapt2"]) if tools["aapt2"] else None,
  }
  if args.dry_run:
    return dict(plan, status="dry-run")

  out = pathlib.Path(args.output_dir or pathlib.Path.cwd() / "litert_app_verify"
                     / datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
  out = out.expanduser().resolve()
  out.mkdir(parents=True, exist_ok=True)
  print(f"Building {task} ...", flush=True)
  run(tools["gradle"] + ["-p", str(root), "--console=plain", task],
      out / "gradle.log", 3, "the Gradle build", cwd=root)
  bundle_dir = app["dir"] / "build" / "outputs" / "bundle" / args.variant
  aabs = sorted(bundle_dir.glob("*.aab"), key=lambda p: p.stat().st_mtime)
  if not aabs:
    raise VerifyError(3, f"the build wrote no .aab to {bundle_dir}. If the "
                      "app has product flavors, pass --variant with the "
                      "flavor (for example freeDebug).")
  aab = aabs[-1]
  package = run(bundletool + ["dump", "manifest", f"--bundle={aab}",
                              "--xpath=/manifest/@package"],
                out / "bundletool_dump.log", 4, "bundletool dump").strip()
  package = package.splitlines()[-1].strip() if package else ""
  if not re.fullmatch(r"[\w.]+", package):
    raise VerifyError(4, f"cannot read the application id from {aab}.")
  installed = adb(tools, serial, "shell", "pm", "path", package,
                  check=False).strip()
  if installed and not args.uninstall_first:
    raise VerifyError(7, f"{package} is already installed on {serial}, and "
                      "local testing cannot update an installed app. Ask "
                      "the user, then rerun with --uninstall-first (it "
                      "deletes the app's data on the phone).")
  apks = out / "app.apks"
  print(f"bundletool build-apks --local-testing ({aab.name}) ...", flush=True)
  run(bundletool + ["build-apks", f"--bundle={aab}", f"--output={apks}",
                    "--local-testing", "--overwrite"]
      + ([f"--aapt2={tools['aapt2']}"] if tools["aapt2"] else []),
      out / "build_apks.log", 4, "bundletool build-apks")
  if installed:  # only now that the new APK set is ready
    adb(tools, serial, "uninstall", package, check=False)
  print(f"Installing for device group {group or '(default)'} ...", flush=True)
  run(bundletool + ["install-apks", f"--apks={apks}", f"--device-id={serial}",
                    f"--adb={tools['adb']}"]
      + ([f"--device-groups={group}"] if group else []),
      out / "install_apks.log", 4, "bundletool install-apks")
  if not args.keep_apks:
    apks.unlink(missing_ok=True)
  splits = [line.split("/")[-1] for line in adb(
      tools, serial, "shell", "pm", "path", package).split()]
  dump = adb(tools, serial, "shell", "dumpsys", "package", package,
             check=False)
  lib_dir = re.search(r"legacyNativeLibraryDir=(\S+)", dump)
  abi = re.search(r"primaryCpuAbi=(\S+)", dump)
  dispatch = None
  if lib_dir and abi and abi.group(1) != "null":
    sub = {"arm64-v8a": "arm64", "armeabi-v7a": "arm"}.get(abi.group(1),
                                                           abi.group(1))
    listing = adb(tools, serial, "shell", "ls", f"{lib_dir.group(1)}/{sub}",
                  check=False)
    dispatch = DISPATCH_LIB in listing
  result = dict(plan, package=package, aab=str(aab), splits=splits,
                dispatch_library_installed=dispatch, output_dir=str(out))
  if args.no_launch:
    return dict(result, status="installed")
  component = adb(tools, serial, "shell", "cmd", "package",
                  "resolve-activity", "--brief", "-c",
                  "android.intent.category.LAUNCHER", package,
                  check=False).strip().splitlines()
  if component and "/" in component[-1]:
    adb(tools, serial, "shell", "am", "start", "-W", "-n", component[-1])
  else:
    adb(tools, serial, "shell", "monkey", "-p", package, "-c",
        "android.intent.category.LAUNCHER", "1")
  loaded = wait_for_result(tools, serial, package, args.timeout)
  return dict(result, status="ran" if loaded else "no_result",
              loader=loaded)


def report_markdown(result: dict[str, Any]) -> str:
  """Formats a verify() result as the Markdown report (stdout, report.md)."""
  device = result["device"]
  lines = [
      f"**Device:** {device['model']} ({device['soc']}, API {device['sdk']}, "
      f"build {device['build_id']}); device group "
      f"`{result['device_group'] or 'none'}`",
      f"**App:** `{result.get('package', '?')}` from {result['app_module']} "
      f"({result['project']})",
  ]
  if result.get("splits"):
    lines.append("**Installed:** " + ", ".join(result["splits"]))
    lines.append("**Dispatch library on the phone:** " + {
        True: "yes", False: "NO", None: "unknown"}[
            result["dispatch_library_installed"]])
  loader = result.get("loader")
  if loader:
    verdict = loader.get("path")
    lines.append(f"**Result:** `\"path\":\"{verdict}\"`, load "
                 f"{loader.get('load_ms')} ms"
                 + (f", npu_error: {loader['npu_error']}"
                    if loader.get("npu_error") else ""))
  elif result["status"] == "no_result":
    lines.append("**Result:** no LITERT_TENSOR_RESULT line")
  if not result["expect_npu"]:
    lines.append(f"**Expected path:** CPU ({result['npu_reason']})")
  if result.get("output_dir"):
    lines.append(f"**Logs:** {result['output_dir']}")
  return "\n".join(lines)


def main(argv=None) -> int:
  args = parse_args(argv)
  try:
    result = verify(args)
  except VerifyError as e:
    if args.json:
      print(json.dumps({"status": "error", "exit_code": e.code,
                        "error": str(e)}, indent=2))
    else:
      print(f"ERROR: {e}", file=sys.stderr)
    return e.code
  except KeyboardInterrupt:
    print("Interrupted.", file=sys.stderr)
    return 130
  loader = result.get("loader")
  if result["status"] == "dry-run":
    code = 0
  elif result["status"] == "installed":
    code = 0
  elif not loader:
    code = 6
  elif loader.get("path") == "npu" or not result["expect_npu"]:
    code = 0
  else:
    code = 1
  result["exit_code"] = code
  if result.get("output_dir"):
    out = pathlib.Path(result["output_dir"])
    (out / "results.json").write_text(json.dumps(result, indent=2) + "\n",
                                      encoding="utf-8")
    (out / "report.md").write_text(report_markdown(result) + "\n",
                                   encoding="utf-8")
  if args.json:
    print(json.dumps(result, indent=2))
  elif result["status"] == "dry-run":
    print("Dry run: project, tools and phone checked; nothing built or "
          "installed.")
    for key in ("project", "app_module", "device_targeting_config",
                "device_group", "expect_npu", "npu_reason", "gradle",
                "bundletool", "aapt2"):
      print(f"  {key}: {result[key]}")
  else:
    print()
    print(report_markdown(result))
    if code == 1:
      print("FAIL: the app used the CPU on a phone it has a Google Tensor "
            "build for (see npu_error, and references/troubleshooting.md).")
    elif code == 6:
      print("No result line: the app must call TensorModelLoader.load(). "
            "Open the screen that uses the model, or rerun with a longer "
            "--timeout.")
  return code


if __name__ == "__main__":
  sys.exit(main())
