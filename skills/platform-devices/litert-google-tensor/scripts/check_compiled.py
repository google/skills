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

"""Reports whether a .tflite file is AOT-compiled for a Google Tensor TPU.

Dependency-free (standard library only), so it can run in any Python 3
environment before the LiteRT packages are installed.

Detection method
----------------
LiteRT's ahead-of-time compiler rewrites NPU partitions into a custom op named
``DISPATCH_OP`` and stamps the flatbuffer with a metadata entry keyed
``LiteRtStamp`` that records the SoC manufacturer (``Google``) and SoC model
(``Tensor_G5``, ``Tensor_G6``, ...). Both markers are plain byte strings, so a
byte search is sufficient and robust.

Models compiled by another toolchain - the Edge TPU compiler, or older
Google Tensor tooling that emits the same op - hold an ``edgetpu-custom-op``
custom op instead (e.g. ``edgetpu-custom-op-2``). They are neither plain nor
LiteRT builds: LiteRT cannot recompile or benchmark them on the Google Tensor
TPU, and the CPU cannot run them.

Exit codes
----------
0  compiled (and matches --expect-target when given)
1  valid .tflite that is NOT compiled (plain CPU/GPU model)
2  compiled, but for a different SoC than --expect-target
3  file missing / not a .tflite flatbuffer
4  compiled by another toolchain (Edge TPU custom op): not usable here
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any

TFLITE_FILE_IDENTIFIER = b"TFL3"  # flatbuffer identifier at byte offset 4..8
DISPATCH_OP_MARKER = b"DISPATCH_OP"
BUILD_STAMP_KEY = b"LiteRtStamp"
GOOGLE_MANUFACTURER = b"Google"
SOC_MODEL_RE = re.compile(rb"Tensor_G\d+")
# Custom op of models compiled by the Edge TPU compiler (and older Google
# Tensor tooling): edgetpu-custom-op, edgetpu-custom-op-2, ...
LEGACY_TPU_OP_RE = re.compile(rb"edgetpu-custom-op[\w-]*")

# Targets this skill supports (same list as compile_model.py --target). Any
# ``Tensor_G<n>`` stamp is still identified and printed, so artifacts compiled
# for an older SoC are reported by name instead of as "unknown".
SUPPORTED_TARGETS = ("Tensor_G5", "Tensor_G6")


def fmt_size(num_bytes: int) -> str:
  """'8,110,864 bytes (8.1 MB)'; MB = 10^6 bytes, same as compile/benchmark."""
  text = f"{num_bytes:,} bytes"
  if num_bytes >= 100_000:
    text += f" ({num_bytes / 1e6:.1f} MB)"
  return text


def _read_sidecar(path: pathlib.Path) -> dict[str, Any] | None:
  """Loads the ``<model>.compile.json`` written by compile_model.py, if any."""
  if not path.is_file():
    return None
  try:
    data = json.loads(path.read_text(encoding="utf-8"))
  except (OSError, ValueError):
    return None
  return data if isinstance(data, dict) else None


def inspect_model(path: pathlib.Path) -> dict[str, Any]:
  """Returns a dict describing the compilation state of ``path``."""
  data = path.read_bytes()
  is_tflite = len(data) >= 8 and data[4:8] == TFLITE_FILE_IDENTIFIER
  has_dispatch_op = DISPATCH_OP_MARKER in data
  has_stamp = BUILD_STAMP_KEY in data
  soc_models = sorted({m.decode("ascii") for m in SOC_MODEL_RE.findall(data)})
  compiled = is_tflite and has_dispatch_op and has_stamp
  legacy_ops = sorted({m.decode("ascii")
                       for m in LEGACY_TPU_OP_RE.findall(data)})
  return {
      "path": str(path),
      "size_bytes": len(data),
      "is_tflite": is_tflite,
      "compiled": compiled,
      "has_dispatch_op": has_dispatch_op,
      "has_build_stamp": has_stamp,
      "google_tensor": GOOGLE_MANUFACTURER in data and bool(soc_models),
      "soc_models": soc_models,
      # Compiled by another toolchain (Edge TPU custom op), not by LiteRT.
      "legacy_compiled": is_tflite and not compiled and bool(legacy_ops),
      "legacy_ops": legacy_ops,
  }


def main(argv=None) -> int:
  parser = argparse.ArgumentParser(
      description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
  )
  parser.add_argument("model", help="Path to the .tflite file to inspect.")
  parser.add_argument(
      "--expect-target",
      choices=SUPPORTED_TARGETS,
      help=(
          "SoC the model should be compiled for (the attached phone's "
          "ro.soc.model: 'Tensor G5' -> Tensor_G5). Exit 2 if the model is "
          "compiled for a different SoC."
      ),
  )
  parser.add_argument(
      "--json", action="store_true", help="Print machine-readable JSON only."
  )
  parser.add_argument(
      "--dry-run",
      action="store_true",
      help=(
          "Accepted for consistency with the other scripts; this check is "
          "read-only, so it changes nothing."
      ),
  )
  args = parser.parse_args(argv)

  path = pathlib.Path(args.model).expanduser()
  if not path.is_file():
    print(f"ERROR: file not found: {path}", file=sys.stderr)
    return 3

  info = inspect_model(path)
  if not info["is_tflite"]:
    info["verdict"] = "not_tflite"
    if args.json:
      print(json.dumps(info, indent=2))
    else:
      print(
          f"ERROR: {path} is not a .tflite flatbuffer (missing 'TFL3' "
          "identifier).",
          file=sys.stderr,
      )
    return 3

  if info["legacy_compiled"]:
    info["verdict"] = "legacy_compiled"
    code = 4
  elif not info["compiled"]:
    info["verdict"] = "not_compiled"
    code = 1
  elif args.expect_target and args.expect_target not in info["soc_models"]:
    info["verdict"] = "target_mismatch"
    code = 2
  else:
    info["verdict"] = "compiled"
    code = 0

  if args.json:
    print(json.dumps(info, indent=2))
    return code

  print(f"Model: {path} ({fmt_size(info['size_bytes'])})")
  if code == 4:
    print(
        "Status: compiled by ANOTHER toolchain - it holds an Edge TPU custom "
        f"op ({', '.join(info['legacy_ops'])}), not LiteRT's DISPATCH_OP. "
        "LiteRT cannot recompile it or run it on the Google Tensor TPU, and "
        "the CPU cannot run it, so do not use it for compiling, "
        "benchmarking, --cpu-baseline or an app. Get the ORIGINAL model it "
        "was compiled from and compile that with scripts/compile_model.py."
    )
  elif code == 1:
    print(
        "Status: NOT compiled - plain model (no DISPATCH_OP / LiteRtStamp "
        "markers). Use it as-is for --cpu-baseline or CPU/GPU runs; compile "
        "it with scripts/compile_model.py before benchmarking on the Google "
        "Tensor TPU."
    )
  else:
    socs = ", ".join(info["soc_models"]) or "unknown"
    print(f"Status: compiled for Google Tensor (SoC: {socs})")
    sidecar = path.with_name(path.name + ".compile.json")
    compile_info = _read_sidecar(sidecar)
    if compile_info:
      flags = compile_info.get("cli_flags") or ["(compiler defaults)"]
      ops = compile_info.get("ops_offloaded"), compile_info.get("ops_total")
      ops_text = (
          f"{ops[0]} / {ops[1]} ops offloaded"
          if None not in ops
          else "op counts not recorded"
      )
      print(f"Compile info ({sidecar.name}): {' '.join(flags)}; {ops_text}")
    else:
      print(
          "Note: the stamp records the SoC only, not the compiler flags "
          f"(no {sidecar.name} next to the model)."
      )
    if code == 2:
      print(
          f"WARNING: expected {args.expect_target}; this model will not "
          "run on that device's TPU. Recompile the ORIGINAL (uncompiled) "
          "model for the right target."
      )
  return code


if __name__ == "__main__":
  sys.exit(main())
