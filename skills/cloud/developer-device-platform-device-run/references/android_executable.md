# Android executable sessions

`gcloud beta device-run sessions submit android-executable` runs a native
Android executable (or a `/system/bin/sh` script) on one or more devices. A job
is created for each device passed to `--device`.

## Flags

For the full, current flag list see
https://docs.cloud.google.com/developer-device-platform/device-run/android-executable.md.txt
and `gcloud beta device-run sessions submit android-executable --help`. The
flags you need most often:

*   `--device=ID[,ID...]` (required): catalog IDs; one job per device.
*   `--executable=PATH` (required): binary or script, `gs://` or local path.
*   `--executable-args=ARG,...`: comma-separated; each element is one argument.
*   `--executable-env-vars=K=V,...`: environment variables for the process.
*   `--executable-timeout=DURATION`: `1m` to `3h`, **default `5m`**.
*   `--other-files-to-push=SRC=DEST,...` and `--paths-to-pull=PATH,...`.

## Direct call (binary as the executable)

Use this when every device runs one configuration.

```bash
gcloud beta device-run sessions submit android-executable \
  --project="${PROJECT_ID}" --location=global \
  --device="pa3q-35,m2q-36" \
  --executable=gs://my-bucket/bin/my_runner \
  --executable-args="--input=/data/local/tmp/input.dat,--threads=4,--out=/data/local/tmp/out.json" \
  --other-files-to-push="gs://my-bucket/data/input.dat=/data/local/tmp/input.dat" \
  --paths-to-pull="/data/local/tmp/out.json" \
  --executable-timeout=30m \
  --labels=purpose=smoke \
  --async
```

Notes:

*   Push files under `/data/local/tmp`, and have the binary write outputs there
    so `--paths-to-pull` can collect them.
*   `--executable-args` applies to the whole session: every device gets the same
    arguments. For several configurations, submit several sessions or use a
    wrapper script ([multi_config_runs.md](multi_config_runs.md)).

### Arguments containing commas

Prefix the value with `^SEP^` to choose another separator:

```bash
--executable-args="^;^--shape=1,224,224,3;--threads=4"
```

### Shared libraries

Push `.so` dependencies next to the binary and point the loader at them. In a
direct call DDP starts the binary itself, not through a shell, so `export
LD_LIBRARY_PATH=...` (or any shell syntax) cannot be used. Set the variable
with a flag instead:

```bash
--other-files-to-push="gs://my-bucket/lib/libfoo.so=/data/local/tmp/libfoo.so" \
--executable-env-vars="LD_LIBRARY_PATH=/data/local/tmp"
```

Libraries opened at runtime with `dlopen` (for example GPU delegates) also need
`LD_LIBRARY_PATH`, even though the binary starts without them. If one is
missing, the binary often falls back silently (for example from GPU to CPU)
instead of failing. After the run, confirm the library actually loaded by
searching the job's `output.log` (if present), a pulled stdout log file, or
`logcat.txt` for the library name or the log line it prints when it
initializes, and tell the user how you checked. (During Preview, `output.log`
may be missing; see [results.md](results.md).)

When answering a shared-library question, always tell the user:

1.  Which `.so` files are pushed and where (`--other-files-to-push`).
2.  That `LD_LIBRARY_PATH` is set with `--executable-env-vars` **because a
    direct call has no shell, so `export` does not work**. (Inside a wrapper
    script, `export` is fine.)
3.  How to confirm any `dlopen`-loaded library was really used.

## Script as the executable

Pass a `/system/bin/sh` script as `--executable` when the run needs several
steps (several configurations, setup, device info, custom output layout). Push
the real binary with `--other-files-to-push`, and in the script:

*   `chmod 755` the pushed binary before running it.
*   `export` environment variables (the script has a shell).
*   Write all outputs into one directory and pull that directory.

See [multi_config_runs.md](multi_config_runs.md) for a template.
