# Troubleshooting

Symptom                                                   | Likely cause                                                                          | Fix
:-------------------------------------------------------- | :------------------------------------------------------------------------------------ | :--
`sessions submit android-executable` not found            | Old gcloud or missing beta component                                                  | Ask the user, then run `gcloud components install beta` or `gcloud components update`.
Bucket error on submit                                    | `--bucket-name` points to a bucket that does not exist, or includes `gs://` or a path | Create the bucket first, or omit the flag to use `PROJECT_ID-devicerun`. Pass the name only.
Job `TIMED_OUT`                                           | Default timeout is `5m`                                                               | Set `--executable-timeout` / `--instrumentation-timeout` (max `3h`).
`CANNOT LINK EXECUTABLE` / library not found              | Shared library not pushed or not on the loader path                                   | Push the `.so` with `--other-files-to-push` and set `LD_LIBRARY_PATH` via `--executable-env-vars` (direct call) or `export` (script).
Feature silently falls back (for example GPU to CPU)      | Runtime-loaded (`dlopen`) library missing                                             | Same as above; confirm in `output.log` (if present), a pulled stdout log, or `logcat.txt` that the library loaded.
Binary receives one mangled argument                      | Space-separated args passed as one element                                            | Rewrite as comma-separated `--executable-args`; use `^SEP^` for values with commas.
`Permission denied` running a pushed binary from a script | Pushed file is not executable                                                         | `chmod 755` it in the script before running.
Output file missing                                       | Run failed before writing it, or wrong `--paths-to-pull` path                         | Check `output.log` (may be missing in Preview) or a pulled stdout log, then `logcat.txt`; write outputs under `/data/local/tmp`.
Session `SUSPENDED`                                       | Quota                                                                                 | Tell the user; wait or cancel.
Job `ERROR` with your own bucket                          | Setup or permission problem                                                           | Inspect the result cause with `sessions describe SESSION_ID --full`; verify the bucket exists and is in the same project.
Pending session ran an unexpected script version          | Shared `gs://` script was overwritten after submission                                | Use local paths (auto-uploaded per run) or a unique `gs://` path per run.
