# Instrumentation sessions

`gcloud beta device-run sessions submit instrumentation` installs app APKs and
runs an instrumentation test APK on one or more devices (one job per device).

For the full, current flag list (sharding, orchestrator, retries, helper apps)
see https://docs.cloud.google.com/developer-device-platform/device-run.md.txt,
https://docs.cloud.google.com/sdk/gcloud/reference/beta/device-run and
`gcloud beta device-run sessions submit instrumentation --help`.

## Minimal example

```bash
gcloud beta device-run sessions submit instrumentation \
  --project="${PROJECT_ID}" --location=global \
  --device="pa3q-35" \
  --target-app=./app-debug.apk \
  --test=./app-debug-androidTest.apk \
  --test-targets="class com.example.LoginTest" \
  --instrumentation-timeout=20m \
  --async
```

`--test-targets` values use a space between the key and the value
(`class com.example.LoginTest`), never `=` (`class=com.example.LoginTest`).
`--instrumentation-timeout` defaults to `5m` (range `1m` to `3h`).

### Older gcloud versions

Prefer `--target-app`. Older gcloud releases don't have it: check
`gcloud beta device-run sessions submit instrumentation --help`. If `--help`
lists only `--apps`, or gcloud reports `unrecognized arguments: --target-app`,
use `--apps=./app-debug.apk` instead and tell the user that `--apps` is
deprecated in newer releases; suggest updating gcloud (ask before running
`gcloud components update`).

## Results

Each execution folder contains `junit.xml`; each job folder contains a merged
`junit.xml` (older runs: `test_results_merged.xml`). See
[results.md](results.md).
