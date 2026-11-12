# Device selection

- [List the catalog](#list-the-catalog): Lines 20-29
- [Resolve a name to an ID](#resolve-a-name-to-an-id): Lines 30-52
- [Several OS versions](#several-os-versions-of-the-same-device): Lines 53-81
- [Other choices](#other-choices-when-several-devices-match): Lines 82-93
- [No match](#no-match): Lines 94-99
- [Confirm before submitting](#confirm-before-submitting): Lines 100-105
- [Details for one device](#details-for-one-device): Lines 106-114

`--device` takes catalog IDs such as `frankel-36`: a device codename plus the
Android API level. Users usually ask for a device by the name it is sold under
("Pixel 10", "Galaxy S22"). Always resolve the name against the live catalog;
the catalog changes, so never rely on a remembered mapping.

For what the catalog contains and its columns, see
https://docs.cloud.google.com/developer-device-platform/device-catalog.md.txt
and `gcloud beta device-run devices list --help`. This page covers choosing.

## List the catalog

```bash
gcloud beta device-run devices list --project="${PROJECT_ID}" --location=global
```

Only devices whose `PRODUCTS` include `Automation` can run Device Run sessions.
Availability shows as `HIGH`, `MEDIUM`, `LOW` or `NONE` in the default table,
and as `AVAILABILITY_HIGH` and so on in the raw `availability.available` field.

## Resolve a name to an ID

Filter on the display name, then pick the **exact** match. A substring filter
for "Pixel 9" also returns "Pixel 9 Pro", "Pixel 9 Pro XL" and "Pixel 9 Pro
Fold", so compare the full name before choosing.

```bash
gcloud beta device-run devices list --project="${PROJECT_ID}" --location=global \
  --filter="platform=ANDROID AND supportedProducts:automation AND displayName~'Pixel 10'" \
  --format="table(name.basename():label=ID,displayName,osVersion,hardwareType,availability.available)"
```

Example output (illustrative; always check the live catalog):

```
ID               NAME               OS_VERSION  HARDWARE_TYPE  AVAILABLE
frankel-36       Pixel 10           36          PHYSICAL       AVAILABILITY_HIGH
blazer-36        Pixel 10 Pro       36          PHYSICAL       AVAILABILITY_LOW
mustang-36       Pixel 10 Pro XL    36          PHYSICAL       AVAILABILITY_MEDIUM
```

Here "Pixel 10" resolves to `frankel-36`.

## Several OS versions of the same device

One device model is often listed once per Android version, for example
`shiba-34`, `shiba-35` and `shiba-36` for a Pixel 8. The OS version can change
the result of a run, so never pick one silently.

*   **User named a version** ("Pixel 8 on Android 15", "API 35"): use that ID.
    If it is not offered, say so, list the versions that are, and ask.
*   **User did not name a version and more than one exists**: show every
    version you found, with its availability, and recommend one (usually the
    newest with good availability). Ask the user to pick one, several, or all
    before submitting. For example (illustrative; use the live catalog):

    ```
    Pixel 8 is available on several Android versions:
      shiba-34  Android 14 (API 34)  AVAILABILITY_HIGH
      shiba-35  Android 15 (API 35)  AVAILABILITY_MEDIUM
      shiba-36  Android 16 (API 36)  AVAILABILITY_HIGH   <- recommended
    Which should I use? You can also pick several; each becomes its own job.
    ```

*   **Running on several versions**: pass all chosen IDs to `--device` (for
    example `--device="shiba-34,shiba-36"`). One session runs one job per ID, so
    this is the easiest way to compare behavior across Android versions.
*   **Only one version exists**: use it, and still state the version in the
    confirmation.
*   **Dry runs or no chance to ask**: use the recommended version in the
    command, and list the other versions next to it so the user can swap the ID.

## Other choices when several devices match

*   **Family names** ("a Pixel 9", "recent Pixels"): list the exact matches and
    their variants, and ask the user, or pick the base model and say so.
*   **Physical vs virtual**: prefer `PHYSICAL` for performance, hardware or
    GPU-dependent work. `VIRTUAL` devices (for example `mediumphone-arm-36`)
    suit quick functional checks and usually have high availability.
*   **Availability**: `AVAILABILITY_LOW` or `AVAILABILITY_NONE` can mean long
    queue times. Warn the user and suggest an alternative.
*   **Variants** with suffixes such as `(Camera-enabled)` or `(16K page size)`
    are different devices; only choose them when the user needs that feature.

## No match

If nothing matches the name (or the requested OS version is not offered), say
so, show the closest options from the catalog, and ask the user to choose. Never
invent an ID.

## Confirm before submitting

State the mapping you used in the confirmation, for example: "Pixel 10 →
`frankel-36` (Android 16, API 36, physical)". This makes job folders
(`job-000`, `job-001`, ...) easy to read later; see [results.md](results.md).

## Details for one device

```bash
gcloud beta device-run devices describe DEVICE_ID \
  --project="${PROJECT_ID}" --location=global
```

The output includes the supported ABIs (for example `arm64-v8a`); make sure
your executable was built for one of them.
