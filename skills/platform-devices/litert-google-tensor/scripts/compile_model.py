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

"""AOT-compiles a .tflite model for a Google Tensor TPU (Tensor_G5 / Tensor_G6).

Thin, reproducible wrapper around the public LiteRT Python AOT API:

    from ai_edge_litert.aot import aot_compile as aot_lib
    from ai_edge_litert.aot.vendors.google_tensor import target as gt_target
    aot_lib.aot_compile(model, output_dir=..., target=gt_target.Target(...),
                        keep_going=False, google_tensor_<flag>=...)

Requirements (see SKILL.md):
  * Local compile: Linux x86_64 host (the Google Tensor compiler plugin only
    ships for it) and a virtualenv with ``ai-edge-litert`` +
    ``ai-edge-litert-sdk-google-tensor`` installed with
    ``GOOGLE_TENSOR_SDK_BETA`` pointing at the Beta compiler tarball (Google
    Tensor SDK Beta access required). Without the tarball the SDK package has
    no compiler library and this script exits with 5.
  * Remote Colab compile (``--colab``, any host OS including macOS/Windows):
    ``google-colab-cli`` (``colab``) on PATH and the Beta compiler tarball
    (``--sdk-tarball`` or ``GOOGLE_TENSOR_SDK_BETA``; or ``--sdk-url`` /
    ``GOOGLE_TENSOR_ML_SDK_URL``). Provisions a Colab Linux x86_64 VM, uploads
    this script, ``versions.json``, the model and the tarball, installs the
    pinned LiteRT pair on the VM, compiles there, downloads ``<output>.tflite``
    and ``<output>.compile.json``, and stops the VM.
  * ``--print-install`` (add ``--colab`` for the Colab setup) prints the
    install commands for the version pinned in the skill's ``versions.json``
    (any python3, any host, no LiteRT needed).

The script sets GOOGLE_TENSOR_BACKEND_ENABLED=1 before importing LiteRT; the
public Tensor SDK FAQ requires it when using the stable ``ai-edge-litert``
package (it is harmless otherwise). Before compiling it compares the installed
LiteRT packages: a WARNING when ``ai-edge-litert`` and the SDK package differ,
a NOTE when they differ from the pin in ``versions.json``.

Output: ``<output-dir>/<model-stem>_Google_<target>.tflite`` (override with
--output-name; an existing file is never overwritten unless --overwrite is
given) plus a ``<output>.compile.json`` sidecar recording the flags, the
compiler's partition report (ops offloaded / total), the package versions and
checksums, so later reports do not depend on anyone retyping them. The
partition report is also printed on stdout.

Exit codes
----------
0  success                      5  LiteRT packages, Beta compiler library or
2  bad arguments or input file     google-colab-cli (--colab) missing
3  model is already compiled    6  compilation failed
   (by LiteRT, or by another    7  output verification failed
   toolchain: Edge TPU op)
4  unsupported host platform
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import platform
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Any

SUPPORTED_TARGETS = ("Tensor_G5", "Tensor_G6")
TRUNCATION_TYPES = ("auto", "bfloat16", "half", "no_truncation")
SHARDING_INTENSITIES = ("minimal", "moderate", "extensive", "maximum")
COLAB_AUTH_MODES = ("oauth2", "adc")
COLAB_BIN_ENV = "LITERT_GOOGLE_TENSOR_COLAB_BIN"
COLAB_EXIT_MARKER = "LITERT_COLAB_EXIT_CODE="
COLAB_PROBE_MARKER = "LITERT_COLAB_PROBE="
PUBLIC_COLAB_TUTORIAL = (
    "https://github.com/google-ai-edge/litert-samples/blob/main/"
    "samples/litert/colab/LiteRT_AOT_Compilation_Tutorial.ipynb"
)

TFLITE_FILE_IDENTIFIER = b"TFL3"
DISPATCH_OP_MARKER = b"DISPATCH_OP"
BUILD_STAMP_KEY = b"LiteRtStamp"
# Custom op of models compiled by the Edge TPU compiler (and older Google
# Tensor tooling), same check as check_compiled.py.
LEGACY_TPU_OP_RE = re.compile(rb"edgetpu-custom-op[\w-]*")
SOC_MODEL_RE = re.compile(rb"Tensor_G\d+")
# "Subgraph 0 fully compiled:\t175 / 175 ops offloaded to 1 partitions."
PARTITION_RE = re.compile(
    r"(\d+)\s*/\s*(\d+)\s+ops offloaded to\s+(\d+)\s+partitions"
)

# Name of the native compiler shipped in the Beta SDK tarball; the LiteRT
# wheel's plugin adapter dlopens it from the SDK package's data/ directory.
COMPILER_LIB_NAME = "liblitert_plugin_compiler.so"

# The skill's single source of LiteRT versions (change it only as described in
# references/contributing.md). Nothing in this script hard-codes a version.
VERSIONS_FILE = (
    pathlib.Path(__file__).resolve().parent.parent / "assets" / "versions.json"
)
# (runtime package, Google Tensor SDK package); the two must be one version.
LITERT_PAIRS = (
    ("ai-edge-litert", "ai-edge-litert-sdk-google-tensor"),
    ("ai-edge-litert-nightly", "ai-edge-litert-sdk-google-tensor-nightly"),
)
DEFAULT_VENV = "~/.venvs/litert-tensor"
TARBALL_PLACEHOLDER = "/abs/path/litert_plugin_compiler.tar.gz"


def load_versions() -> dict[str, Any]:
  """Reads versions.json; raises ValueError with a readable message."""
  try:
    data = json.loads(VERSIONS_FILE.read_text(encoding="utf-8"))
  except (OSError, ValueError) as e:
    raise ValueError(f"cannot read {VERSIONS_FILE}: {e}") from e
  if not isinstance(data, dict):
    raise ValueError(f"{VERSIONS_FILE} must hold a JSON object")
  release = data.get("pip_release")
  if not isinstance(release, str) or not re.fullmatch(
      r"\d[0-9A-Za-z.+!_-]*", release
  ):
    raise ValueError(
        f"{VERSIONS_FILE}: 'pip_release' must be a version "
        "string such as 'X.Y.Z'"
    )
  if not isinstance(data.get("python"), str):
    raise ValueError(
        f"{VERSIONS_FILE}: 'python' must be a range string "
        "'MAJOR.MINOR-MAJOR.MINOR'"
    )
  return data


def pip_install_line(release: str) -> str:
  return (
      f"pip install --no-cache-dir ai-edge-litert=={release} "
      f"ai-edge-litert-sdk-google-tensor=={release}"
  )


def install_hint(release: str | None) -> str:
  """Install instructions for the exit-5 messages, with the pinned version."""
  pip_line = (
      pip_install_line(release)
      if release
      else pip_install_line("<V>") + f"   # <V>: pip_release in {VERSIONS_FILE}"
  )
  return (
      "The Google Tensor compiler ships as a Beta SDK tarball"
      " (litert_plugin_compiler.tar.gz) that you receive by email after"
      " signing up at\n "
      " https://services.google.com/fb/forms/tensor_ml_sdk_experimental_access\nInstall"
      " it inside a virtualenv (Linux x86_64 only; compile_model.py"
      " --print-install prints every command):\n  export"
      f" GOOGLE_TENSOR_SDK_BETA={TARBALL_PLACEHOLDER}\n  {pip_line}\n(add"
      " --force-reinstall when the packages are already installed;"
      " --no-cache-dir matters because pip otherwise reuses a previously built"
      " SDK wheel that has no compiler library in it.)"
  )


def colab_install_hint(release: str | None) -> str:
  """Install instructions for remote Colab compilation (--colab)."""
  ver = release or f"<V> (pip_release in {VERSIONS_FILE})"
  return (
      "To compile on a remote Google Colab Linux x86_64 VM (--colab):\n"
      "  1. Install google-colab-cli (https://github.com/googlecolab/"
      "google-colab-cli):\n"
      "       uv tool install google-colab-cli   # or: pip install "
      "google-colab-cli\n"
      "  2. Authenticate once (browser OAuth or gcloud ADC):\n"
      "       colab --auth oauth2 sessions\n"
      "     or, for headless ADC (--colab-auth adc):\n"
      "       gcloud auth application-default login --scopes="
      "openid,https://www.googleapis.com/auth/cloud-platform,"
      "https://www.googleapis.com/auth/userinfo.email,"
      "https://www.googleapis.com/auth/colaboratory\n"
      "  3. Provide the Beta SDK tarball (litert_plugin_compiler.tar.gz from "
      "the sign-up e-mail):\n"
      f"       export GOOGLE_TENSOR_SDK_BETA={TARBALL_PLACEHOLDER}\n"
      "     (or pass --sdk-tarball FILE, or --sdk-url URL). The script then "
      f"installs ai-edge-litert + ai-edge-litert-sdk-google-tensor {ver} on "
      "the Colab VM automatically.\n"
      f"Public Colab tutorial: {PUBLIC_COLAB_TUTORIAL}"
  )


def _python_range(spec: str) -> tuple[tuple[int, int], tuple[int, int]] | None:
  """'3.10-3.13' -> ((3, 10), (3, 13)); None for any other format."""
  m = re.fullmatch(r"\s*(\d+)\.(\d+)\s*-\s*(\d+)\.(\d+)\s*", spec)
  if not m:
    return None
  major_lo, minor_lo, major_hi, minor_hi = (int(x) for x in m.groups())
  return (major_lo, minor_lo), (major_hi, minor_hi)


def print_install(colab: bool = False) -> int:
  """--print-install: the pinned install commands, ready to paste."""
  try:
    versions = load_versions()
  except ValueError as e:
    print(f"ERROR: {e}", file=sys.stderr)
    return 2
  release = versions["pip_release"]
  host = f"{sys.platform}/{platform.machine()}"
  host_ok = sys.platform == "linux" and platform.machine() == "x86_64"
  here = platform.python_version()
  lines = [
      f"# ai-edge-litert + ai-edge-litert-sdk-google-tensor {release} "
      f"(pip_release in {VERSIONS_FILE})"
  ]
  verified = versions.get("verified")
  if isinstance(verified, dict) and verified:
    lines.append(
        "# Last verified: "
        + "; ".join(f"{key}: {value}" for key, value in verified.items())
    )
  if colab or not host_ok:
    lines += [
        (
            f"# Remote Google Colab compile (this host: {host}; no local Linux "
            "x86_64 or LiteRT venv needed)."
        ),
        (
            "# Uses google-colab-cli"
            " (https://github.com/googlecolab/google-colab-cli) and the Beta"
            " tarball litert_plugin_compiler.tar.gz (or unpacked"
            " google_tensor_ml_sdk/ dir) from the sign-up e-mail."
        ),
        f"# Public Colab tutorial: {PUBLIC_COLAB_TUTORIAL}",
        "uv tool install google-colab-cli   # or: pip install google-colab-cli",
        (
            f"python3 {pathlib.Path(__file__).resolve()} /abs/path/model.tflite"
            f" --target Tensor_G5 --colab --sdk-tarball {TARBALL_PLACEHOLDER}"
        ),
    ]
    if colab:
      print("\n".join(lines))
      return 0
    lines.append(
        "# --- Or, if you move to a Linux x86_64 machine for local compile: ---"
    )
  host_note = ""
  if not host_ok:
    host_note = (
        " - NOT supported locally; run these on a Linux x86_64 machine "
        "or add --colab to compile on Google Colab"
    )
  lines.append(
      f"# Needs: Linux x86_64 (this host: {host}{host_note}"
      f"), Python {versions['python']} (this Python: {here}), and the Beta "
      "tarball litert_plugin_compiler.tar.gz from the sign-up e-mail."
  )
  lines.append(
      "# No Linux x86_64 machine? Run with --print-install --colab for the "
      "remote Google Colab setup."
  )
  supported = _python_range(versions["python"])
  if supported and not supported[0] <= sys.version_info[:2] <= supported[1]:
    lines.append(
        f"# WARNING: Python {here} is outside {versions['python']}; "
        "create the venv with a Python in that range (e.g. "
        f"python{supported[1][0]}.{supported[1][1]} -m venv ...)."
    )
  lines += [
      f"python3 -m venv {DEFAULT_VENV} && source {DEFAULT_VENV}/bin/activate",
      "pip install --upgrade pip",
      (
          f"export GOOGLE_TENSOR_SDK_BETA={TARBALL_PLACEHOLDER}"
          "   # from the Beta e-mail"
      ),
      pip_install_line(release),
  ]
  print("\n".join(lines))
  return 0


def installed_litert_versions() -> dict[str, str]:
  """{distribution: version} of the LiteRT packages in this interpreter."""
  found = {}
  try:
    import importlib.metadata as md  # pylint: disable=g-import-not-at-top
  except ImportError:
    return found
  for pair in LITERT_PAIRS:
    for dist in pair:
      try:
        found[dist] = md.version(dist)
      except md.PackageNotFoundError:
        pass
  return found


def version_warnings(
    installed: dict[str, str], pinned: str | None
) -> list[tuple[str, str]]:
  """(level, message) pairs about the installed LiteRT packages.

  WARNING: a runtime package and its Google Tensor SDK package differ (they
  must be one version). NOTE (only without a WARNING): the stable pair is not
  the pin in versions.json - allowed, and the sidecar records what was used.

  Args:
    installed: {distribution: version} from installed_litert_versions().
    pinned: The pip_release pinned in versions.json, or None if unavailable.

  Returns:
    The (level, message) pairs; level is "WARNING" or "NOTE".
  """
  reinstall = (
      f"{pip_install_line(pinned)} --force-reinstall"
      if pinned
      else "see compile_model.py --print-install"
  )
  messages = []
  for runtime, sdk in LITERT_PAIRS:
    a, b = installed.get(runtime), installed.get(sdk)
    if a and b and a != b:
      messages.append((
          "WARNING",
          (
              f"{runtime} {a} and {sdk} {b} differ; they "
              "must be the same version. Reinstall both with "
              f"GOOGLE_TENSOR_SDK_BETA set: {reinstall}"
          ),
      ))
  stable = LITERT_PAIRS[0]
  if (
      pinned
      and installed
      and not messages
      and any(installed.get(dist) != pinned for dist in stable)
  ):
    have = [
        f"{d} {installed[d]}" if d in installed else f"{d} not installed"
        for d in stable
    ]
    have += [f"{d} {v}" for d, v in installed.items() if d not in stable]
    messages.append((
        "NOTE",
        (
            f"installed {', '.join(have)}; versions.json pins "
            f"{pinned}. The compile uses the installed packages (the "
            "sidecar records them). For the pinned pair, with "
            f"GOOGLE_TENSOR_SDK_BETA set: {reinstall}"
        ),
    ))
  return messages


def fmt_size(num_bytes: int) -> str:
  """'8,110,864 bytes (8.1 MB)'; MB = 10^6 bytes, same as the other scripts."""
  text = f"{num_bytes:,} bytes"
  if num_bytes >= 100_000:
    text += f" ({num_bytes / 1e6:.1f} MB)"
  return text


def sha256_of(path: pathlib.Path) -> str:
  digest = hashlib.sha256()
  with open(path, "rb") as fh:
    for chunk in iter(lambda: fh.read(1 << 20), b""):
      digest.update(chunk)
  return digest.hexdigest()


def _inspect(path: pathlib.Path) -> dict[str, Any]:
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


def build_backend_kwargs(args: argparse.Namespace) -> dict[str, Any]:
  """Maps CLI flags to the ``google_tensor_*`` kwargs the backend accepts.

  Only flags that differ from the compiler defaults are forwarded, so the
  default behaviour is exactly the compiler's documented default behaviour.

  Args:
    args: Parsed command-line arguments.

  Returns:
    {kwarg name: value} for aot_compile; empty when every flag is default.
  """
  kwargs = {}
  if args.truncation_type != "auto":
    kwargs["google_tensor_truncation_type"] = args.truncation_type
  if args.sharding_intensity:
    kwargs["google_tensor_sharding_intensity"] = args.sharding_intensity
  if args.int64_to_int32:
    kwargs["google_tensor_int64_to_int32"] = True
  if args.large_model_support:
    kwargs["google_tensor_enable_large_model_support"] = True
  if args.enable_4bit:
    kwargs["google_tensor_enable_4bit_compilation"] = True
  if args.extra_options_path:
    kwargs["google_tensor_extra_options_path"] = str(
        pathlib.Path(args.extra_options_path).expanduser().resolve()
    )
  return kwargs


def parse_args(argv=None) -> argparse.Namespace:
  """Parses the command-line arguments (default: sys.argv[1:])."""
  p = argparse.ArgumentParser(
      description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
  )
  p.add_argument("model", nargs="?", help="Input .tflite model (uncompiled).")
  p.add_argument(
      "--target",
      choices=SUPPORTED_TARGETS,
      help=(
          "Google Tensor SoC: Tensor_G5 = Pixel 10 family, "
          "Tensor_G6 = Pixel 11 family. Required (as is the "
          "model) unless --print-install is given."
      ),
  )
  p.add_argument(
      "--output-dir",
      help="Where to write the compiled model (default: <model dir>/compiled).",
  )
  p.add_argument(
      "--output-name",
      help="Output file name (default: <model stem>_Google_<target>.tflite).",
  )
  g = p.add_argument_group(
      "Google Tensor compiler flags",
      "See references/compile-flags.md. Defaults match "
      "the public compiler defaults.",
  )
  g.add_argument(
      "--truncation-type",
      default="auto",
      choices=TRUNCATION_TYPES,
      help="Float precision used on the TPU (default: auto).",
  )
  g.add_argument(
      "--sharding-intensity",
      choices=SHARDING_INTENSITIES,
      help=(
          "How aggressively to split the model for parallelism "
          "(compiler default: minimal)."
      ),
  )
  g.add_argument(
      "--int64-to-int32",
      action="store_true",
      help="Allow the compiler to narrow int64 to int32.",
  )
  g.add_argument(
      "--large-model-support",
      action="store_true",
      help="Required for models larger than 2 GB.",
  )
  g.add_argument(
      "--enable-4bit",
      action="store_true",
      help="Enable compilation of 4-bit convolution weights.",
  )
  g.add_argument(
      "--extra-options-path",
      help="Binary file with extra compiler options (advanced).",
  )
  c = p.add_argument_group(
      "Remote Google Colab compilation (any host OS, via google-colab-cli)",
      "Use --colab when this machine is not Linux x86_64 (e.g. macOS/Windows) "
      "or has no local LiteRT setup. See --print-install --colab.",
  )
  c.add_argument(
      "--colab",
      action="store_true",
      help=(
          "Compile on a remote Google Colab Linux x86_64 VM using "
          "google-colab-cli ('colab'). Uploads the model and Beta SDK "
          "tarball, runs this script on the VM, downloads the compiled "
          ".tflite and .compile.json sidecar, and stops the VM."
      ),
  )
  c.add_argument(
      "--sdk-tarball",
      help=(
          "Path to litert_plugin_compiler.tar.gz from the Beta e-mail "
          "(default: $GOOGLE_TENSOR_SDK_BETA); uploaded by --colab."
      ),
  )
  c.add_argument(
      "--sdk-url",
      help=(
          "Download URL for the Beta compiler tarball (default: "
          "$GOOGLE_TENSOR_ML_SDK_URL); used by --colab when --sdk-tarball "
          "is not set."
      ),
  )
  c.add_argument(
      "--colab-bin",
      help=(
          "google-colab-cli executable (default: "
          f"${COLAB_BIN_ENV}, else 'colab' on PATH)."
      ),
  )
  c.add_argument(
      "--colab-auth",
      choices=COLAB_AUTH_MODES,
      help=(
          "Auth mode passed as global --auth to colab (oauth2 or adc; "
          "default: colab's own default)."
      ),
  )
  c.add_argument(
      "--colab-auth-code",
      help=(
          "One-time Google OAuth authorization code to complete colab login "
          "non-interactively (after visiting the URL printed by a previous "
          "--colab run)."
      ),
  )
  c.add_argument(
      "--colab-session",
      help=(
          "Colab session name to create or reuse (default: "
          "litert-gt-<pid>). An already-active session is reused and kept."
      ),
  )
  c.add_argument(
      "--colab-high-mem",
      action="store_true",
      help="Request a High-RAM Colab VM (--high-mem; requires Colab Pro).",
  )
  c.add_argument(
      "--keep-colab-session",
      action="store_true",
      help=(
          "Keep a newly created Colab VM running after the compile so a "
          "later --colab-session NAME run can skip installing the SDK."
      ),
  )
  c.add_argument(
      "--colab-timeout",
      type=int,
      default=900,
      help=(
          "Timeout in seconds for the remote Colab compile step (default: 900)."
      ),
  )
  p.add_argument(
      "--keep-going",
      action="store_true",
      help="Continue past backend errors instead of failing fast.",
  )
  p.add_argument(
      "--keep-intermediates",
      action="store_true",
      help=(
          "Keep the compiler's intermediate files under "
          "<output-dir>/_intermediates."
      ),
  )
  p.add_argument(
      "--overwrite",
      action="store_true",
      help=(
          "Replace an existing output file (default: refuse with "
          "exit 2 so a previous artifact is never clobbered)."
      ),
  )
  p.add_argument(
      "--no-report-file",
      action="store_true",
      help="Do not write the <output>.compile.json sidecar.",
  )
  p.add_argument(
      "--force",
      action="store_true",
      help=(
          "(experimental) Skip the already-compiled check. The "
          "compiler cannot recompile DISPATCH_OP partitions, so "
          "this normally fails; compile the original export "
          "instead."
      ),
  )
  p.add_argument(
      "--dry-run",
      action="store_true",
      help="Validate inputs and print the plan; do not compile.",
  )
  p.add_argument(
      "--json",
      action="store_true",
      help="Print a JSON summary as the last line of stdout.",
  )
  p.add_argument(
      "--print-install",
      action="store_true",
      help=(
          "Print the commands that install the LiteRT packages "
          "pinned in the skill's versions.json into a new "
          "virtualenv (or, with --colab, the google-colab-cli "
          "setup), then exit (exit 2 if versions.json is "
          "unreadable). Needs no LiteRT, works on any host and "
          "ignores the other arguments."
      ),
  )
  args = p.parse_args(argv)
  if not args.print_install:
    missing = [
        name
        for name, value in (("model", args.model), ("--target", args.target))
        if not value
    ]
    if missing:
      p.error("the following arguments are required: " + ", ".join(missing))
  return args


def _safe_name(name: str) -> str:
  return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def _resolve_colab_bin(explicit: str | None) -> str | None:
  """Locates the google-colab-cli executable."""
  candidate = explicit or os.environ.get(COLAB_BIN_ENV)
  if candidate:
    found = shutil.which(candidate)
    if found:
      return found
    p = pathlib.Path(candidate).expanduser()
    return str(p.resolve()) if p.is_file() else None
  found = shutil.which("colab")
  if found:
    return found
  for fallback in (
      pathlib.Path.home() / ".local" / "bin" / "colab",
      pathlib.Path.home() / ".venvs" / "colab-cli" / "bin" / "colab",
  ):
    if fallback.is_file():
      return str(fallback)
  return None


def _colab_python(colab_bin: str) -> str:
  """Returns the Python interpreter backing the ``colab`` console script."""
  try:
    first = (
        pathlib.Path(colab_bin)
        .read_text(encoding="utf-8", errors="ignore")
        .splitlines()[0]
    )
    if first.startswith("#!"):
      interp = first[2:].strip().split()[0]
      if os.path.isfile(interp):
        return interp
  except OSError:
    pass
  sibling = pathlib.Path(colab_bin).resolve().parent / "python3"
  return str(sibling) if sibling.is_file() else sys.executable


def _colab_oauth_helper(
    colab_bin: str, auth_code: str | None = None
) -> tuple[bool, str]:
  """Starts or completes colab-cli OAuth2 without an interactive TTY."""
  py = _colab_python(colab_bin)
  helper = (
      "import importlib.resources as res, json, os, sys\n"
      "from colab_cli import auth as ca\n"
      "from google_auth_oauthlib.flow import InstalledAppFlow\n"
      "cfg_dir = os.path.dirname(ca.TOKEN_CONFIG_PATH)\n"
      "os.makedirs(cfg_dir, exist_ok=True)\n"
      "pending = os.path.join(cfg_dir, 'pending_oauth.json')\n"
      "cfg_res = res.files('colab_cli').joinpath('oauth_config.json')\n"
      "client_cfg = json.loads(cfg_res.read_text())\n"
      "flow = InstalledAppFlow.from_client_config(client_cfg, "
      "ca.PUBLIC_SCOPES)\n"
      "flow.redirect_uri = ca.REMOTE_REDIRECT_URI\n"
      f"code = {auth_code!r}\n"
      "if code:\n"
      "  if os.path.exists(pending):\n"
      "    data = json.loads(open(pending).read())\n"
      "    flow.code_verifier = data.get('code_verifier')\n"
      "  flow.fetch_token(code=code.strip())\n"
      "  open(ca.TOKEN_CONFIG_PATH, 'w').write(flow.credentials.to_json())\n"
      "  if os.path.exists(pending):\n"
      "    os.remove(pending)\n"
      "  print('OAUTH_OK')\n"
      "else:\n"
      "  url, _ = flow.authorization_url(prompt='consent', "
      "token_usage='remote')\n"
      "  open(pending, 'w').write(json.dumps({'code_verifier': "
      "flow.code_verifier}))\n"
      "  print('OAUTH_URL=' + url)\n"
  )
  try:
    p = subprocess.run(
        [py, "-c", helper],
        cwd=tempfile.gettempdir(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
  except (OSError, subprocess.SubprocessError) as e:
    return False, str(e)
  if p.returncode != 0:
    return False, (p.stderr or p.stdout or "").strip()
  for ln in (p.stdout or "").splitlines():
    if ln == "OAUTH_OK":
      return True, ""
    if ln.startswith("OAUTH_URL="):
      return False, ln[len("OAUTH_URL=") :]
  return False, (p.stdout or "").strip()


def _run_colab(
    colab_bin: str,
    auth: str | None,
    subargs: list[str],
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
  """Runs ``colab [--auth MODE] <subargs>`` with a timeout."""
  cmd = [colab_bin]
  if auth:
    cmd += ["--auth", auth]
  cmd += subargs
  return subprocess.run(
      cmd,
      cwd=tempfile.gettempdir(),
      stdin=subprocess.DEVNULL,
      capture_output=True,
      text=True,
      timeout=timeout,
      check=False,
  )


def _build_remote_probe_script(
    remote_dir: str, pinned_release: str | None
) -> str:
  """Python snippet run via ``colab exec`` to prepare ``remote_dir``."""
  all_dists = list(LITERT_PAIRS[0] + LITERT_PAIRS[1])
  return (
      "import importlib.metadata as md, json, os, pathlib, platform, sys\n"
      f"remote_dir = {remote_dir!r}\n"
      "os.makedirs(f'{remote_dir}/scripts', exist_ok=True)\n"
      "os.makedirs(f'{remote_dir}/assets', exist_ok=True)\n"
      "os.makedirs(f'{remote_dir}/out', exist_ok=True)\n"
      "installed = {}\n"
      f"for dist in {all_dists!r}:\n"
      "  try:\n"
      "    installed[dist] = md.version(dist)\n"
      "  except md.PackageNotFoundError:\n"
      "    pass\n"
      "has_lib = False\n"
      "try:\n"
      "  import ai_edge_litert_sdk_google_tensor as gt_sdk\n"
      "  libs = gt_sdk.path_to_sdk_libs()\n"
      f"  has_lib = bool(libs and (pathlib.Path(libs) / {COMPILER_LIB_NAME!r})"
      ".is_file())\n"
      "except Exception:\n"
      "  has_lib = False\n"
      "info = {\n"
      "  'host': f'{sys.platform}/{platform.machine()}',\n"
      "  'python': platform.python_version(),\n"
      "  'installed': installed,\n"
      "  'has_compiler_lib': has_lib,\n"
      f"  'pinned': {pinned_release!r},\n"
      "}\n"
      f"print({COLAB_PROBE_MARKER!r} + json.dumps(info))\n"
  )


def _build_remote_compile_script(
    remote_dir: str,
    remote_model: str,
    output_name: str,
    args: argparse.Namespace,
    remote_extra_options: str | None,
    needs_sdk_install: bool,
    remote_tarball: str | None,
    sdk_url: str | None,
    pinned_release: str | None,
) -> str:
  """Python script executed on the Colab VM to install the SDK and compile."""
  remote_argv = [
      f"{remote_dir}/scripts/compile_model.py",
      remote_model,
      "--target",
      args.target,
      "--output-dir",
      f"{remote_dir}/out",
      "--output-name",
      output_name,
      "--overwrite",
  ]
  if args.truncation_type != "auto":
    remote_argv += ["--truncation-type", args.truncation_type]
  if args.sharding_intensity:
    remote_argv += ["--sharding-intensity", args.sharding_intensity]
  for flag, enabled in (
      ("--int64-to-int32", args.int64_to_int32),
      ("--large-model-support", args.large_model_support),
      ("--enable-4bit", args.enable_4bit),
      ("--keep-going", args.keep_going),
      ("--no-report-file", args.no_report_file),
      ("--force", args.force),
  ):
    if enabled:
      remote_argv.append(flag)
  if remote_extra_options:
    remote_argv += ["--extra-options-path", remote_extra_options]

  release_spec = f"=={pinned_release}" if pinned_release else ""
  pkgs = [
      f"ai-edge-litert{release_spec}",
      f"ai-edge-litert-sdk-google-tensor{release_spec}",
  ]
  return (
      "import ctypes, glob, os, subprocess, sys\n"
      f"for first_part in sorted(glob.glob({remote_dir!r} + '/*.part000')):\n"
      "  target = first_part[:-len('.part000')]\n"
      "  parts = sorted(glob.glob(target + '.part*'))\n"
      "  with open(target, 'wb') as out_fh:\n"
      "    for part in parts:\n"
      "      with open(part, 'rb') as in_fh:\n"
      "        out_fh.write(in_fh.read())\n"
      "      os.remove(part)\n"
      "def _ensure_libcxx():\n"
      "  try:\n"
      "    ctypes.CDLL('libc++.so.1')\n"
      "    return\n"
      "  except OSError:\n"
      "    pass\n"
      "  print('Installing libc++ runtime on Colab VM ...', flush=True)\n"
      "  subprocess.run(['apt-get', 'update', '-qq'], check=False)\n"
      "  r = subprocess.run(\n"
      "      ['apt-get', 'install', '-y', '-qq', 'libc++1', 'libc++abi1'],\n"
      "      check=False,\n"
      "  )\n"
      "  if r.returncode != 0:\n"
      "    subprocess.run(\n"
      "        ['apt-get', 'install', '-y', '-qq', 'libc++-18-dev',\n"
      "         'libc++abi-18-dev'],\n"
      "        check=False,\n"
      "    )\n"
      "_ensure_libcxx()\n"
      f"if {needs_sdk_install!r}:\n"
      "  env = os.environ.copy()\n"
      f"  if {remote_tarball!r}:\n"
      f"    env['GOOGLE_TENSOR_SDK_BETA'] = {remote_tarball!r}\n"
      f"  elif {sdk_url!r}:\n"
      f"    env['GOOGLE_TENSOR_ML_SDK_URL'] = {sdk_url!r}\n"
      f"  pkgs = {pkgs!r}\n"
      "  print('Installing ' + ' '.join(pkgs) + ' on Colab VM ...', "
      "flush=True)\n"
      "  pip_cmd = [\n"
      "      sys.executable, '-m', 'pip', 'install', '--no-cache-dir',\n"
      "      '--force-reinstall', *pkgs,\n"
      "  ]\n"
      "  p = subprocess.run(pip_cmd, env=env, text=True, "
      "capture_output=True)\n"
      "  if p.returncode != 0:\n"
      "    sys.stdout.write(p.stdout or '')\n"
      "    sys.stderr.write(p.stderr or '')\n"
      f"    print({COLAB_EXIT_MARKER!r} + '5', flush=True)\n"
      "    raise SystemExit(0)\n"
      f"cmd = [sys.executable, *{remote_argv!r}]\n"
      "p = subprocess.run(cmd, text=True, capture_output=True)\n"
      "if p.stdout:\n"
      "  sys.stdout.write(p.stdout)\n"
      "if p.stderr:\n"
      "  sys.stderr.write(p.stderr)\n"
      f"out_file = {f'{remote_dir}/out/{output_name}'!r}\n"
      "chunk_max = 20 * 1024 * 1024\n"
      "if p.returncode == 0 and os.path.isfile(out_file):\n"
      "  sz = os.path.getsize(out_file)\n"
      "  if sz > chunk_max:\n"
      "    n_parts = (sz + chunk_max - 1) // chunk_max\n"
      "    with open(out_file, 'rb') as fh:\n"
      "      for idx in range(n_parts):\n"
      "        with open(f'{out_file}.part{idx:03d}', 'wb') as pf:\n"
      "          pf.write(fh.read(chunk_max))\n"
      "    print('LITERT_COLAB_OUT_PARTS=' + str(n_parts), flush=True)\n"
      f"print({COLAB_EXIT_MARKER!r} + str(p.returncode), flush=True)\n"
  )


def _resolve_sdk_input(
    raw_path: pathlib.Path,
) -> tuple[str | None, pathlib.Path | None]:
  """Resolves --sdk-tarball (archive, unpacked SDK dir, or compiler .so)."""
  if not raw_path.exists():
    return None, None
  if raw_path.is_file():
    lower = raw_path.name.lower()
    if lower.endswith((".tar.gz", ".tgz", ".tar", ".zip")):
      return "archive", raw_path
    with raw_path.open("rb") as fh:
      magic = fh.read(4)
    if magic != b"\x7fELF" and raw_path.name != COMPILER_LIB_NAME:
      return "archive", raw_path
    sdk_dir = raw_path.parent
  else:
    sdk_dir = raw_path
    if (
        not (sdk_dir / COMPILER_LIB_NAME).is_file()
        and (sdk_dir / "google_tensor_ml_sdk" / COMPILER_LIB_NAME).is_file()
    ):
      sdk_dir = sdk_dir / "google_tensor_ml_sdk"
  for parent in (sdk_dir.parent, sdk_dir.parent.parent):
    sibling = parent / "litert_plugin_compiler.tar.gz"
    if sibling.is_file():
      print(f"NOTE: using sibling SDK archive {sibling} for {raw_path}.")
      return "archive", sibling
  if (sdk_dir / COMPILER_LIB_NAME).is_file() and (
      sdk_dir / "third_party"
  ).is_dir():
    return "dir", sdk_dir
  return "incomplete", sdk_dir


def run_colab_compile(
    args: argparse.Namespace,
    model: pathlib.Path,
    output_dir: pathlib.Path,
    output_name: str,
    output_path: pathlib.Path,
    report_path: pathlib.Path,
    pinned_release: str | None,
    plan: dict[str, object],
) -> int:
  """Offloads compilation to a Google Colab Linux x86_64 VM via colab CLI.

  Args:
    args: Parsed command-line arguments.
    model: Resolved path to the input .tflite file.
    output_dir: Local directory where the compiled artifact will be written.
    output_name: Filename for the compiled .tflite model.
    output_path: Full local path for the compiled .tflite model.
    report_path: Full local path for the .compile.json sidecar.
    pinned_release: Pinned LiteRT release string from versions.json, or None.
    plan: Dictionary summarizing the compile plan.

  Returns:
    Process exit code (0 on success, non-zero on failure).
  """
  colab_bin = _resolve_colab_bin(args.colab_bin)
  if not colab_bin:
    print(
        "ERROR: google-colab-cli ('colab') not found on PATH.\n"
        + colab_install_hint(pinned_release),
        file=sys.stderr,
    )
    return 5

  sdk_tarball_str = args.sdk_tarball or os.environ.get("GOOGLE_TENSOR_SDK_BETA")
  sdk_url = args.sdk_url or os.environ.get("GOOGLE_TENSOR_ML_SDK_URL")
  sdk_kind = None
  sdk_tarball = None
  if sdk_tarball_str:
    raw_sdk = pathlib.Path(sdk_tarball_str).expanduser().resolve()
    sdk_kind, sdk_tarball = _resolve_sdk_input(raw_sdk)
    if sdk_kind is None:
      print(
          f"ERROR: Google Tensor SDK beta file not found: {raw_sdk}\n"
          + colab_install_hint(pinned_release),
          file=sys.stderr,
      )
      return 5
    if sdk_kind == "incomplete":
      print(
          f"ERROR: {raw_sdk} is a standalone {COMPILER_LIB_NAME} without the "
          "SDK's third_party/ toolchain directory. Pass the full "
          "litert_plugin_compiler.tar.gz archive (or the unpacked "
          "google_tensor_ml_sdk/ directory containing both "
          f"{COMPILER_LIB_NAME} and third_party/).\n"
          + colab_install_hint(pinned_release),
          file=sys.stderr,
      )
      return 5
  elif not sdk_url and not args.colab_session:
    print(
        "ERROR: Google Tensor SDK Beta tarball not specified (pass "
        "--sdk-tarball /abs/path/litert_plugin_compiler.tar.gz or export "
        "GOOGLE_TENSOR_SDK_BETA).\n"
        + colab_install_hint(pinned_release),
        file=sys.stderr,
    )
    return 5

  session_name = args.colab_session or f"litert-gt-{os.getpid()}"
  if args.colab_auth_code:
    ok, msg = _colab_oauth_helper(colab_bin, args.colab_auth_code)
    if not ok:
      print(
          f"ERROR: failed to exchange --colab-auth-code: {msg}",
          file=sys.stderr,
      )
      return 5
    print("Saved Google Colab OAuth token.")

  try:
    sessions_proc = _run_colab(
        colab_bin, args.colab_auth, ["sessions"], timeout=60
    )
  except (OSError, subprocess.SubprocessError) as e:
    print(
        f"ERROR: failed to run '{colab_bin} sessions': {e}\n"
        + colab_install_hint(pinned_release),
        file=sys.stderr,
    )
    return 5
  if sessions_proc.returncode != 0:
    detail = (
        (sessions_proc.stderr or "") + "\n" + (sessions_proc.stdout or "")
    ).strip()
    if args.colab_auth != "adc" and (
        "To authorize colab-cli" in detail
        or "Enter the authorization code" in detail
        or "EOFError" in detail
    ):
      _, auth_url = _colab_oauth_helper(colab_bin, None)
      if auth_url.startswith("http"):
        print(
            "ERROR: Google Colab CLI needs one-time OAuth authorization.\n"
            "Ask the user to open this URL in their browser and paste the "
            "authorization code back in chat (no terminal command needed):\n\n"
            f"  {auth_url}\n\n"
            "Then re-run this exact command with: "
            "--colab-auth-code <CODE>",
            file=sys.stderr,
        )
        return 5
    print(
        f"ERROR: 'colab sessions' failed (exit {sessions_proc.returncode}): "
        f"{detail}\n"
        + colab_install_hint(pinned_release),
        file=sys.stderr,
    )
    return 5

  session_reused = bool(
      args.colab_session
      and re.search(
          rf"(?:\[{re.escape(session_name)}\]|\b{re.escape(session_name)}\b)",
          sessions_proc.stdout or "",
      )
  )
  if not session_reused and sdk_tarball is None and not sdk_url:
    print(
        f"ERROR: Colab session '{session_name}' is not active and no Beta "
        "SDK tarball was provided (pass --sdk-tarball FILE or export "
        "GOOGLE_TENSOR_SDK_BETA).\n"
        + colab_install_hint(pinned_release),
        file=sys.stderr,
    )
    return 5

  scratch = pathlib.Path(tempfile.mkdtemp(prefix="litert_gt_colab_"))
  remote_dir = f"/content/litert_gt_{int(time.time())}_{os.getpid()}"
  created_session = False
  remote_dir_created = False

  def _terminate(signum, unused_frame):
    raise SystemExit(128 + signum)

  prev_handlers = {}
  for sig_name in ("SIGINT", "SIGTERM", "SIGHUP"):
    sig = getattr(signal, sig_name, None)
    if sig is not None:
      try:
        prev_handlers[sig] = signal.signal(sig, _terminate)
      except (OSError, ValueError):
        pass

  try:
    if session_reused:
      print(f"Reusing active Google Colab session '{session_name}'.")
    else:
      new_cmd = ["new", "-s", session_name]
      if args.colab_high_mem:
        new_cmd.append("--high-mem")
      print(
          "Provisioning Google Colab Linux x86_64 VM "
          f"(session '{session_name}') ..."
      )
      new_proc = _run_colab(colab_bin, args.colab_auth, new_cmd, timeout=180)
      if new_proc.returncode != 0:
        detail = (new_proc.stderr or new_proc.stdout or "").strip()
        print(
            f"ERROR: 'colab new -s {session_name}' failed "
            f"(exit {new_proc.returncode}): {detail}",
            file=sys.stderr,
        )
        return 5
      created_session = True

    probe_file = scratch / "probe.py"
    probe_file.write_text(
        _build_remote_probe_script(remote_dir, pinned_release),
        encoding="utf-8",
    )
    probe_proc = _run_colab(
        colab_bin,
        args.colab_auth,
        ["exec", "-s", session_name, "--timeout", "60", "-f", str(probe_file)],
        timeout=120,
    )
    if probe_proc.returncode != 0:
      detail = (probe_proc.stderr or probe_proc.stdout or "").strip()
      print(
          f"ERROR: failed to initialize remote Colab directory {remote_dir} "
          f"(exit {probe_proc.returncode}): {detail}",
          file=sys.stderr,
      )
      return 5
    remote_dir_created = True

    probe = {}
    for ln in (probe_proc.stdout or "").splitlines():
      if ln.startswith(COLAB_PROBE_MARKER):
        try:
          probe = json.loads(ln[len(COLAB_PROBE_MARKER) :])
        except ValueError:
          probe = {}
    remote_host = probe.get("host", "unknown")
    if probe and remote_host != "linux/x86_64":
      print(
          f"ERROR: remote Colab runtime is {remote_host}, expected "
          "linux/x86_64.",
          file=sys.stderr,
      )
      return 4

    installed_remote = probe.get("installed") or {}
    already_installed = bool(
        probe.get("has_compiler_lib")
        and (
            not pinned_release
            or (
                installed_remote.get("ai-edge-litert") == pinned_release
                and installed_remote.get("ai-edge-litert-sdk-google-tensor")
                == pinned_release
            )
        )
    )
    needs_sdk_install = not already_installed
    if needs_sdk_install and sdk_tarball is None and not sdk_url:
      print(
          f"ERROR: Colab session '{session_name}' does not have the Google "
          "Tensor compiler installed, and no Beta SDK tarball was provided. "
          "Pass --sdk-tarball /abs/path/litert_plugin_compiler.tar.gz "
          "(or export GOOGLE_TENSOR_SDK_BETA).",
          file=sys.stderr,
      )
      return 5

    print(
        f"Colab VM ready ({remote_host}, Python {probe.get('python', '?')}); "
        f"staging files in {remote_dir} ..."
    )
    uploads = [
        (
            pathlib.Path(__file__).resolve(),
            f"{remote_dir}/scripts/compile_model.py",
        ),
    ]
    if VERSIONS_FILE.is_file():
      uploads.append((VERSIONS_FILE, f"{remote_dir}/assets/versions.json"))
    remote_model = f"{remote_dir}/{_safe_name(model.name)}"
    uploads.append((model, remote_model))

    remote_extra_options = None
    if args.extra_options_path:
      extra_path = pathlib.Path(args.extra_options_path).expanduser().resolve()
      remote_extra_options = f"{remote_dir}/extra_{_safe_name(extra_path.name)}"
      uploads.append((extra_path, remote_extra_options))

    remote_tarball = None
    if needs_sdk_install and sdk_tarball is not None:
      if sdk_kind == "dir":
        packed = scratch / "litert_plugin_compiler.tar.gz"
        print(
            f"Packing unpacked SDK directory {sdk_tarball} into "
            f"{packed.name} ..."
        )
        with tarfile.open(packed, "w:gz") as tf:
          tf.add(sdk_tarball, arcname="google_tensor_ml_sdk")
        sdk_tarball = packed
      remote_tarball = f"{remote_dir}/{_safe_name(sdk_tarball.name)}"
      print(
          f"Uploading Beta SDK tarball {sdk_tarball.name} "
          f"({fmt_size(sdk_tarball.stat().st_size)}) to Colab ..."
      )
      uploads.append((sdk_tarball, remote_tarball))
    elif not needs_sdk_install:
      print(
          f"Reusing pre-installed LiteRT {pinned_release or 'packages'} on "
          f"Colab session '{session_name}'."
      )

    chunk_max = 20 * 1024 * 1024
    expanded_uploads: list[tuple[pathlib.Path, str]] = []
    for local_src, remote_dst in uploads:
      size = local_src.stat().st_size
      if size <= chunk_max:
        expanded_uploads.append((local_src, remote_dst))
      else:
        num_parts = (size + chunk_max - 1) // chunk_max
        print(
            f"Splitting {local_src.name} ({fmt_size(size)}) into {num_parts} "
            "parts for Colab upload ..."
        )
        with local_src.open("rb") as fh:
          for idx in range(num_parts):
            part_path = scratch / f"{_safe_name(local_src.name)}.part{idx:03d}"
            part_path.write_bytes(fh.read(chunk_max))
            expanded_uploads.append((part_path, f"{remote_dst}.part{idx:03d}"))

    for local_src, remote_dst in expanded_uploads:
      up_proc = _run_colab(
          colab_bin,
          args.colab_auth,
          ["upload", "-s", session_name, str(local_src), remote_dst],
          timeout=max(300, args.colab_timeout),
      )
      if up_proc.returncode != 0:
        detail = (up_proc.stderr or up_proc.stdout or "").strip()
        print(
            f"ERROR: 'colab upload' failed for {local_src} -> {remote_dst} "
            f"(exit {up_proc.returncode}): {detail}",
            file=sys.stderr,
        )
        return 5

    runner_file = scratch / "run_compile.py"
    runner_file.write_text(
        _build_remote_compile_script(
            remote_dir=remote_dir,
            remote_model=remote_model,
            output_name=output_name,
            args=args,
            remote_extra_options=remote_extra_options,
            needs_sdk_install=needs_sdk_install,
            remote_tarball=remote_tarball,
            sdk_url=sdk_url,
            pinned_release=pinned_release,
        ),
        encoding="utf-8",
    )
    print(f"Running AOT compilation on Colab session '{session_name}' ...")
    try:
      exec_proc = _run_colab(
          colab_bin,
          args.colab_auth,
          [
              "exec",
              "-s",
              session_name,
              "--timeout",
              str(args.colab_timeout),
              "-f",
              str(runner_file),
          ],
          timeout=args.colab_timeout + 60,
      )
    except subprocess.TimeoutExpired:
      print(
          "ERROR: remote Colab compilation timed out after "
          f"--colab-timeout {args.colab_timeout}s.",
          file=sys.stderr,
      )
      return 6

    remote_rc = None
    out_parts = 0
    out_lines = []
    for ln in (exec_proc.stdout or "").splitlines():
      if ln.startswith(COLAB_EXIT_MARKER):
        try:
          remote_rc = int(ln[len(COLAB_EXIT_MARKER) :].strip())
        except ValueError:
          remote_rc = 6
      elif ln.startswith("LITERT_COLAB_OUT_PARTS="):
        try:
          out_parts = int(ln[len("LITERT_COLAB_OUT_PARTS=") :].strip())
        except ValueError:
          out_parts = 0
      else:
        out_lines.append(ln)
    if out_lines:
      print("\n".join(out_lines))
    if exec_proc.stderr:
      sys.stderr.write(exec_proc.stderr)
    if exec_proc.returncode != 0 and remote_rc is None:
      print(
          f"ERROR: 'colab exec' failed (exit {exec_proc.returncode}).",
          file=sys.stderr,
      )
      return 6
    if remote_rc is None:
      remote_rc = 6
    if remote_rc != 0:
      return remote_rc

    output_dir.mkdir(parents=True, exist_ok=True)
    remote_out_model = f"{remote_dir}/out/{output_name}"
    if out_parts > 0:
      print(f"Downloading compiled model from Colab in {out_parts} parts ...")
      with output_path.open("wb") as out_fh:
        for idx in range(out_parts):
          part_local = scratch / f"dl.part{idx:03d}"
          dl_proc = _run_colab(
              colab_bin,
              args.colab_auth,
              [
                  "download",
                  "-s",
                  session_name,
                  f"{remote_out_model}.part{idx:03d}",
                  str(part_local),
              ],
              timeout=max(300, args.colab_timeout),
          )
          if dl_proc.returncode != 0 or not part_local.is_file():
            detail = (dl_proc.stderr or dl_proc.stdout or "").strip()
            print(
                f"ERROR: failed to download part {idx + 1}/{out_parts} of "
                f"{remote_out_model} (exit {dl_proc.returncode}): {detail}",
                file=sys.stderr,
            )
            return 7
          out_fh.write(part_local.read_bytes())
          part_local.unlink(missing_ok=True)
    else:
      dl_proc = _run_colab(
          colab_bin,
          args.colab_auth,
          ["download", "-s", session_name, remote_out_model, str(output_path)],
          timeout=max(300, args.colab_timeout),
      )
      if dl_proc.returncode != 0 or not output_path.is_file():
        detail = (dl_proc.stderr or dl_proc.stdout or "").strip()
        print(
            f"ERROR: failed to download compiled model {remote_out_model} "
            f"(exit {dl_proc.returncode}): {detail}",
            file=sys.stderr,
        )
        return 7

    out_info = _inspect(output_path)
    if not (out_info["compiled"] and args.target in out_info["soc_models"]):
      print(
          f"ERROR: {output_path} does not carry the expected Google Tensor "
          f"stamp for {args.target} (found {out_info['soc_models']}).",
          file=sys.stderr,
      )
      return 7

    summary = None
    if not args.no_report_file:
      remote_out_report = f"{remote_out_model}.compile.json"
      dl_rep = _run_colab(
          colab_bin,
          args.colab_auth,
          ["download", "-s", session_name, remote_out_report, str(report_path)],
          timeout=120,
      )
      if dl_rep.returncode != 0 or not report_path.is_file():
        detail = (dl_rep.stderr or dl_rep.stdout or "").strip()
        print(
            f"ERROR: failed to download compile sidecar {remote_out_report} "
            f"(exit {dl_rep.returncode}): {detail}",
            file=sys.stderr,
        )
        return 7
      try:
        summary = json.loads(report_path.read_text(encoding="utf-8"))
      except (OSError, ValueError) as e:
        print(
            f"ERROR: invalid downloaded sidecar {report_path}: {e}",
            file=sys.stderr,
        )
        return 7
      expected_sha = summary.get("output_sha256")
      actual_sha = sha256_of(output_path)
      if expected_sha and actual_sha != expected_sha:
        print(
            f"ERROR: SHA-256 mismatch on downloaded {output_path} "
            f"(expected {expected_sha}, got {actual_sha}).",
            file=sys.stderr,
        )
        return 7
      summary["input"] = str(model)
      summary["output"] = str(output_path)
      summary["compiled_via"] = "colab"
      summary["colab_session"] = session_name
      summary["local_host"] = plan["host"]
      report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(
        f"Compiled model downloaded to {output_path} "
        f"({fmt_size(out_info['size_bytes'])})."
    )
    if not args.no_report_file:
      print(f"Compile report written to {report_path}")
    if args.json and summary is not None:
      print(json.dumps(summary))
    return 0
  except KeyboardInterrupt:
    print(
        "\nInterrupted (Ctrl-C); cleaning up Google Colab resources ...",
        file=sys.stderr,
    )
    return 130
  finally:
    for sig, prev in prev_handlers.items():
      try:
        signal.signal(sig, prev)
      except (OSError, ValueError):
        pass
    if created_session and not args.keep_colab_session:
      try:
        _run_colab(
            colab_bin, args.colab_auth, ["stop", "-s", session_name], timeout=60
        )
        print(f"Stopped Google Colab session '{session_name}'.")
      except Exception as e:  # pylint: disable=broad-exception-caught
        print(
            f"WARNING: failed to stop Colab session '{session_name}': {e}. "
            f"Run: colab stop -s {session_name}",
            file=sys.stderr,
        )
    elif remote_dir_created:
      try:
        cleanup_file = scratch / "cleanup.py"
        cleanup_file.write_text(
            f"import shutil\nshutil.rmtree({remote_dir!r},"
            " ignore_errors=True)\n",
            encoding="utf-8",
        )
        _run_colab(
            colab_bin,
            args.colab_auth,
            [
                "exec",
                "-s",
                session_name,
                "--timeout",
                "30",
                "-f",
                str(cleanup_file),
            ],
            timeout=60,
        )
      except Exception:  # pylint: disable=broad-exception-caught
        pass
      print(
          f"Kept Google Colab session '{session_name}' active. Stop it when "
          f"done with: colab stop -s {session_name}"
      )
    shutil.rmtree(scratch, ignore_errors=True)


def main(argv=None) -> int:
  args = parse_args(argv)
  if args.print_install:
    return print_install(colab=args.colab)
  try:  # progress visible live when an agent captures stdout through a pipe
    sys.stdout.reconfigure(line_buffering=True)
  except (AttributeError, ValueError):
    pass

  if args.colab_timeout <= 0:
    print("ERROR: --colab-timeout must be positive.", file=sys.stderr)
    return 2
  if args.extra_options_path:
    extra_opt_file = pathlib.Path(args.extra_options_path).expanduser()
    if not extra_opt_file.is_file():
      print(
          f"ERROR: --extra-options-path not found: {extra_opt_file}",
          file=sys.stderr,
      )
      return 2

  model = pathlib.Path(args.model).expanduser().resolve()
  if not model.is_file():
    print(f"ERROR: model not found: {model}", file=sys.stderr)
    return 2
  info = _inspect(model)
  if not info["is_tflite"]:
    print(f"ERROR: {model} is not a .tflite flatbuffer.", file=sys.stderr)
    return 2
  if info["compiled"] and not args.force:
    print(
        f"ERROR: {model} is already compiled for "
        f"{', '.join(info['soc_models']) or 'an NPU'}. The compiler cannot "
        "recompile a compiled model; compile the ORIGINAL (uncompiled) "
        "export instead.",
        file=sys.stderr,
    )
    return 3
  if info["legacy_ops"] and not args.force:
    print(
        f"ERROR: {model} was compiled by another toolchain: it holds an Edge "
        f"TPU custom op ({', '.join(info['legacy_ops'])}) instead of TFLite "
        "ops, so the compiler finds nothing to compile. Compile the ORIGINAL "
        "model it was made from instead (check_compiled.py exits 4 for such "
        "files).",
        file=sys.stderr,
    )
    return 3

  output_dir = (
      pathlib.Path(args.output_dir).expanduser().resolve()
      if args.output_dir
      else model.parent / "compiled"
  )
  output_name = args.output_name or f"{model.stem}_Google_{args.target}.tflite"
  output_path = output_dir / output_name
  report_path = output_path.with_name(output_path.name + ".compile.json")
  backend_kwargs = build_backend_kwargs(args)
  # The flags exactly as given (minus paths), for the sidecar and reports.
  cli_flags = [f"--target {args.target}"]
  if args.truncation_type != "auto":
    cli_flags.append(f"--truncation-type {args.truncation_type}")
  if args.sharding_intensity:
    cli_flags.append(f"--sharding-intensity {args.sharding_intensity}")
  for name in (
      "int64_to_int32",
      "large_model_support",
      "enable_4bit",
      "keep_going",
  ):
    if getattr(args, name):
      cli_flags.append("--" + name.replace("_", "-"))
  if args.extra_options_path:
    cli_flags.append("--extra-options-path <file>")

  host_ok = sys.platform == "linux" and platform.machine() == "x86_64"
  output_exists = output_path.exists()
  try:
    pinned_release = load_versions()["pip_release"]
  except ValueError as e:
    pinned_release = None
    print(
        f"WARNING: {e}; the installed LiteRT versions will not be compared "
        "with the skill's pin.",
        file=sys.stderr,
    )

  plan = {
      "input": str(model),
      "input_size_bytes": info["size_bytes"],
      "target": args.target,
      "output": str(output_path),
      "output_exists": output_exists,
      "report_file": None if args.no_report_file else str(report_path),
      "keep_going": args.keep_going,
      "backend_kwargs": backend_kwargs,
      "host": f"{sys.platform}/{platform.machine()}",
      "host_supported": host_ok or args.colab,
      "pinned_pip_release": pinned_release,
  }
  if args.colab:
    plan["execution"] = "colab"
    plan["colab_session"] = args.colab_session or f"litert-gt-{os.getpid()}"
    plan["colab_high_mem"] = args.colab_high_mem
    plan["keep_colab_session"] = args.keep_colab_session
  print("Compile plan:")
  print(json.dumps(plan, indent=2))
  if output_exists and not args.overwrite:
    verb = "would stop" if args.dry_run else "stopping"
    print(
        f"{'NOTE' if args.dry_run else 'ERROR'}: output already exists: "
        f"{output_path} - {verb} so it is not overwritten. Check it with "
        "scripts/check_compiled.py and reuse it, or pass --output-name NAME, "
        "or --overwrite.",
        file=sys.stdout if args.dry_run else sys.stderr,
    )
    if not args.dry_run:
      return 2
  if args.dry_run:
    print("--dry-run: nothing compiled.")
    return 0 if (host_ok or args.colab) else 4

  if args.colab:
    return run_colab_compile(
        args,
        model,
        output_dir,
        output_name,
        output_path,
        report_path,
        pinned_release,
        plan,
    )

  if not host_ok:
    print(
        "ERROR: the Google Tensor compiler plugin only runs locally on Linux "
        f"x86_64 (this host is {plan['host']}). Either pass --colab (with "
        "google-colab-cli and --sdk-tarball /abs/path/litert_plugin_compiler"
        ".tar.gz) to compile on a remote Google Colab Linux x86_64 VM, or run "
        "the compile step on a Linux x86_64 machine; benchmarking can still "
        "be done from this host.",
        file=sys.stderr,
    )
    return 4

  # Progress bars render as hundreds of '\r' fragments in captured logs.
  os.environ.setdefault("TQDM_DISABLE", "1")
  # Must be set before importing ai_edge_litert.aot (stable package).
  os.environ.setdefault("GOOGLE_TENSOR_BACKEND_ENABLED", "1")
  try:
    from ai_edge_litert.aot import aot_compile as aot_lib  # pylint: disable=g-import-not-at-top
    from ai_edge_litert.aot.vendors.google_tensor import target as gt_target  # pylint: disable=g-import-not-at-top
  except ImportError as e:
    print(
        f"ERROR: cannot import the LiteRT AOT API ({e!r}).\n"
        f"{install_hint(pinned_release)}",
        file=sys.stderr,
    )
    return 5
  # Locate the native compiler library. The backend looks in the SDK package's
  # data/ directory first and falls back to $GOOGLE_TENSOR_COMPILER_LIB only
  # when the SDK package is not importable, so mirror that order here.
  sdk_libs = None
  try:
    import ai_edge_litert_sdk_google_tensor as gt_sdk  # pylint: disable=g-import-not-at-top

    sdk_libs = gt_sdk.path_to_sdk_libs()  # None when data/ was never populated
    sdk_source = (
        f"package ai_edge_litert_sdk_google_tensor {gt_sdk.__version__}"
    )
  except ImportError:
    sdk_source = "env GOOGLE_TENSOR_COMPILER_LIB"
    if os.environ.get("GOOGLE_TENSOR_COMPILER_LIB"):
      sdk_libs = pathlib.Path(os.environ["GOOGLE_TENSOR_COMPILER_LIB"])
  except NotImplementedError as e:  # raised on unsupported hosts
    print(f"ERROR: {e}", file=sys.stderr)
    return 4
  sdk_dir = pathlib.Path(sdk_libs) if sdk_libs else None
  found_libs = (
      sorted(sdk_dir.glob("*.so*")) if sdk_dir and sdk_dir.is_dir() else []
  )
  if not found_libs:
    where = (
        f"{sdk_dir} has no shared libraries"
        if sdk_dir
        else "the SDK package has no data/ directory"
    )
    print(
        f"ERROR: {COMPILER_LIB_NAME} not found ({sdk_source}: {where}).\n"
        "The ai-edge-litert-sdk-google-tensor package only contains the "
        "compiler when the Beta tarball was supplied at pip-install time.\n"
        + install_hint(pinned_release),
        file=sys.stderr,
    )
    return 5
  if not (sdk_dir / COMPILER_LIB_NAME).is_file():
    print(
        f"WARNING: {COMPILER_LIB_NAME} not found in {sdk_dir}; found "
        f"{[p.name for p in found_libs]}. Continuing, the compiler adapter "
        "will report whether it can load the library.",
        file=sys.stderr,
    )
  print(f"Compiler library directory: {sdk_dir} ({sdk_source})")
  installed = installed_litert_versions()
  for level, message in version_warnings(installed, pinned_release):
    print(
        f"{level}: {message}",
        file=sys.stderr if level == "WARNING" else sys.stdout,
    )

  target = gt_target.Target(gt_target.SocModel(args.target))
  output_dir.mkdir(parents=True, exist_ok=True)
  if args.keep_intermediates:
    work_dir = output_dir / "_intermediates"
    work_dir.mkdir(parents=True, exist_ok=True)
    tmp = None
  else:
    tmp = tempfile.TemporaryDirectory(prefix="litert_gt_compile_")
    work_dir = pathlib.Path(tmp.name)

  print(f"Compiling {model.name} for {target!r} ...")
  started = time.time()
  try:
    result = aot_lib.aot_compile(
        str(model),
        output_dir=str(work_dir),
        target=target,
        keep_going=args.keep_going,
        **backend_kwargs,
    )
  except Exception as e:  # pylint: disable=broad-exception-caught
    message = str(e)
    print(
        f"ERROR: compilation raised {type(e).__name__}: {message}",
        file=sys.stderr,
    )
    # aot_compile points at a log file ("See /tmp/xxx.error for details");
    # surface its ERROR lines so the user does not have to open it.
    error_lines = []
    log_match = re.search(r"See (\S+\.error) for details", message)
    if log_match and os.path.isfile(log_match.group(1)):
      with open(log_match.group(1), encoding="utf-8", errors="replace") as fh:
        error_lines = [ln.rstrip() for ln in fh if "ERROR" in ln]
      if error_lines:
        print("Compiler log errors:", file=sys.stderr)
        for ln in error_lines[-15:]:
          print(f"  {ln}", file=sys.stderr)
    if tmp:
      tmp.cleanup()
    if any(
        COMPILER_LIB_NAME in ln and "cannot open" in ln for ln in error_lines
    ):
      print(
          f"The compiler plugin could not load {COMPILER_LIB_NAME}.\n"
          + install_hint(pinned_release),
          file=sys.stderr,
      )
      return 5
    if info["compiled"] or info["legacy_ops"]:
      print(
          "The input was already a compiled model (--force only skipped the "
          "check): the compiler cannot recompile DISPATCH_OP partitions or "
          "Edge TPU custom ops and typically fails with 'compiled_result or "
          "num_byte_code is nullptr'. Compile the ORIGINAL (uncompiled) "
          "export instead.",
          file=sys.stderr,
      )
      return 6
    print(
        "See references/troubleshooting.md (e.g. retry with "
        "--truncation-type half --sharding-intensity maximum).",
        file=sys.stderr,
    )
    return 6
  elapsed = time.time() - started

  report = result.compilation_report()
  print("\n===== Compilation report =====")
  print(report)
  print("==============================\n")

  if result.failed_backends or not result.models_with_backend:
    print("ERROR: no compiled model was produced.", file=sys.stderr)
    for backend, err in result.failed_backends:
      print(f"  {backend.target_id}: {err}", file=sys.stderr)
    if tmp:
      tmp.cleanup()
    return 6

  _, compiled_model = result.models_with_backend[0]
  compiled_model.save(output_path, export_only=True)
  if tmp:
    tmp.cleanup()

  out_info = _inspect(output_path)
  if not (out_info["compiled"] and args.target in out_info["soc_models"]):
    print(
        f"ERROR: {output_path} does not carry the expected Google Tensor "
        f"stamp for {args.target} (found {out_info['soc_models']}).",
        file=sys.stderr,
    )
    return 7

  # Sum the per-subgraph "X / Y ops offloaded to Z partitions" lines.
  partitions = [tuple(int(x) for x in m) for m in PARTITION_RE.findall(report)]
  ops_offloaded = sum(p[0] for p in partitions) if partitions else None
  ops_total = sum(p[1] for p in partitions) if partitions else None
  compiler_lib = sdk_dir / COMPILER_LIB_NAME

  summary = {
      "status": "ok",
      "compiled_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
      "input": str(model),
      "input_size_bytes": info["size_bytes"],
      "input_sha256": sha256_of(model),
      "output": str(output_path),
      "output_size_bytes": out_info["size_bytes"],
      "output_sha256": sha256_of(output_path),
      "target": args.target,
      "cli_flags": cli_flags,
      "backend_kwargs": backend_kwargs,
      "ops_offloaded": ops_offloaded,
      "ops_total": ops_total,
      "partitions": sum(p[2] for p in partitions) if partitions else None,
      "fully_compiled": (ops_offloaded == ops_total) if partitions else None,
      "compilation_report": report,
      "packages": installed,
      "pinned_pip_release": pinned_release,
      "compiler_library_dir": str(sdk_dir),
      # Identifies the Beta tarball's compiler build behind this artifact.
      "compiler_library_sha256": (
          sha256_of(compiler_lib) if compiler_lib.is_file() else None
      ),
      "host": plan["host"],
      "elapsed_seconds": round(elapsed, 1),
  }
  print(
      f"Compiled model written to {output_path} "
      f"({fmt_size(out_info['size_bytes'])}) in {elapsed:.0f}s."
  )
  if ops_total is not None:
    if ops_offloaded == ops_total:
      partial_note = ""
    else:
      partial_note = (
          " - NOT fully compiled; a strict NPU benchmark will fail, see "
          "--allow-cpu-fallback in benchmark_on_device.py"
      )
    print(
        f"Ops offloaded to the TPU: {ops_offloaded} / {ops_total}"
        + partial_note
    )
  if not args.no_report_file:
    report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Compile report written to {report_path}")
  if args.json:
    print(json.dumps(summary))
  return 0


if __name__ == "__main__":
  sys.exit(main())
