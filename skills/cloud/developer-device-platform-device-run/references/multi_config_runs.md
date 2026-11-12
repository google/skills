# Running a binary with several configurations

- [Choose an approach](#choose-an-approach): Lines 12-23
- [Wrapper script](#wrapper-script): Lines 24-128
- [Optional variations](#optional-variations): Lines 129-142

A direct call runs the binary once, with the same arguments on every device. To
run the same binary several times per device with different configurations
(different flags, inputs or environment variables), choose one of two
approaches.

## Choose an approach

Approach                                | Use when
:-------------------------------------- | :-------
**One session per configuration**       | Configurations are independent, you want a separate job status and result for each one, and they don't need to run on the same physical device.
**Wrapper script, one session**         | Configurations should run one after another on the same device allocation, later steps depend on earlier ones, or you want a single submission.

For one session per configuration, submit the direct call (see
[android_executable.md](android_executable.md)) once per configuration, with a
distinct `--labels` value (for example `config=a`) on each session. The rest of
this page covers the wrapper script.

## Wrapper script

Pass a `/system/bin/sh` script as `--executable`, push the real binary with
`--other-files-to-push`, and run the binary once per configuration inside the
script.

### Output contract

The script writes one folder per configuration under a single output directory,
which is then pulled with `--paths-to-pull`:

```
/data/local/tmp/out/
├── _device.txt           # device model, from getprop
└── <tag>/                # one folder per configuration
    ├── config.txt        # the env vars and args used
    ├── output.log        # stdout and stderr of the binary
    ├── exit_code         # exit code of the binary
    └── ...               # any files the binary writes to $RUN_OUT_DIR
```

### Template

Adapt `BIN` and the `run` lines. Keep the output contract.

```sh
#!/system/bin/sh
WORK="/data/local/tmp"
BIN="$WORK/my_binary"
OUT="$WORK/out"
# Only needed if the binary uses .so files pushed next to it.
export LD_LIBRARY_PATH="$WORK"
chmod 755 "$BIN"
rm -rf "$OUT" && mkdir -p "$OUT"

# Job folders are only numbered; record the hardware.
getprop ro.product.model > "$OUT/_device.txt"

FAILED=0

# run <tag> [VAR=value ...] -- <args...>
# Runs the binary once and records its config, output and exit code.
run() {
  tag="$1"; shift
  dir="$OUT/$tag"
  mkdir -p "$dir"
  envs=""
  while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do
    envs="$envs $1"; shift
  done
  [ "$1" = "--" ] && shift
  echo "env:$envs args: $*" > "$dir/config.txt"
  env $envs RUN_OUT_DIR="$dir" "$BIN" "$@" >"$dir/output.log" 2>&1
  code=$?
  echo "$code" > "$dir/exit_code"
  [ "$code" -ne 0 ] && FAILED=1
}

run default    -- --input="$WORK/input.dat"
run strict     -- --input="$WORK/input.dat" --strict
run feature_on FEATURE_X=1 -- --input="$WORK/input.dat"

echo "ALL DONE"
exit "$FAILED"
```

Notes:

*   The script does not stop at the first failure: every configuration runs and
    records its own exit code. It exits non-zero at the end if any configuration
    failed, so the failure is not hidden behind a successful script exit.
*   Environment variable values and arguments must not contain spaces in this
    template. Use a separate `run` line or a pushed config file if they do.
*   `RUN_OUT_DIR` is optional. Use it if your binary can write extra output
    files there (for example via an `--output_dir="$RUN_OUT_DIR"` flag of your
    own); otherwise ignore it.

### Submit

Pass the script as a local path so each run uploads a fresh copy:

```bash
gcloud beta device-run sessions submit android-executable \
  --project="${PROJECT_ID}" --location=global \
  --device="pa3q-35,m2q-36" \
  --executable=./run_all.sh \
  --other-files-to-push="gs://my-bucket/bin/my_binary=/data/local/tmp/my_binary,gs://my-bucket/data/input.dat=/data/local/tmp/input.dat" \
  --paths-to-pull="/data/local/tmp/out" \
  --executable-timeout=60m \
  --labels=purpose=multi-config \
  --async
```

`--executable-timeout` covers the whole script. Size it for all configurations
together, not for a single run.

### Read results

After downloading (see [results.md](results.md)), search recursively for every
`**/out/*/exit_code` file under each job folder (pulled files are stored under
`execution-NNN/artifacts/data/local/tmp/out/`). For each configuration, report
the tag, `config.txt`, the exit code, and any outputs the user cares about from
`output.log` or the configuration folder. Label rows with `_device.txt` (fall
back to the job folder name). Report non-zero exit codes explicitly.

## Optional variations

Add these only when the task needs them:

*   **Repeat a configuration** several times (for flaky or noisy runs): call
    `run` in a loop with tags such as `strict_1`, `strict_2`.
*   **Setup or discarded runs**: run preparation steps, or a run whose output
    you don't keep (for example a warm-up), before the recorded runs. Send
    their output to a separate folder or `/dev/null` so it isn't reported.
*   **Pause between configurations** (`sleep N`) when one run can affect the
    next.
*   **Per-configuration time limit**: if one configuration can stop
    responding, wrap the call in `timeout <seconds>` (if available on the
    device) so it does not use up the whole session timeout.
