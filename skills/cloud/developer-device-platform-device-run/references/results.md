# Results

## Bucket layout

```
gs://BUCKET/automation/
├── inputs/
│   └── <timestamp>/          # auto-uploaded local inputs
└── sessions/
    └── SESSION_ID/
        ├── job-000/          # first device in --device
        │   ├── execution-000/
        │   │   ├── logcat.txt
        │   │   ├── output.log    # may be missing in Preview; see below
        │   │   ├── artifacts/    # --paths-to-pull, device path preserved
        │   │   │   └── data/local/tmp/...
        │   │   └── ...           # junit.xml, ...
        │   ├── execution-000-rerun-000/  # retry, if --flaky-test-attempts > 1
        │   └── junit.xml         # instrumentation: merged job-level report
        └── job-001/          # second device in --device
```

*   **`output.log`**: stdout and stderr of your executable only. During
    Preview, `android-executable` runs may not export it. If stdout matters,
    use a wrapper script that redirects it to a file under `/data/local/tmp`
    and pull that file. Check `output.log` if present, then the pulled log,
    then `logcat.txt`.
*   **`logcat.txt`**: device-wide Android system log; collected for every job.
*   **`execution-NNN/`**: one folder per shard. Retries (when
    `--flaky-test-attempts` is greater than 1) appear as
    `execution-NNN-rerun-MMM/`. Report which attempt passed.
*   **Instrumentation**: `junit.xml` per execution, and a merged `junit.xml`
    (older runs: `test_results_merged.xml`) directly under `job-NNN/`.

## Download

```bash
mkdir -p ./ddp_results
gcloud storage cp -r "gs://BUCKET/automation/sessions/SESSION_ID/" ./ddp_results/
```

Find pulled files by searching recursively under each job folder rather than
assuming an exact subpath.

## Mapping jobs to devices

Job folders are numbered `job-000`, `job-001`, ... in the order devices were
passed to `--device`. Keep that list with the session ID so rows can be labeled.
For extra safety in script runs, record the device model on the device (`getprop
ro.product.model`) into an output file.

## Reporting

Summarize per device: device ID, job folder, result, the outputs the user cares
about, and the `gs://` session path. List failed or missing jobs explicitly; a
missing output file usually means the run failed, so check `output.log` (if
present) or a pulled stdout log first, then `logcat.txt`.
