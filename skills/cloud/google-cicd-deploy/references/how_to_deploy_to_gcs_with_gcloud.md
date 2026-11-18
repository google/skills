# How to Deploy to Google Cloud Storage with `gcloud`

This document outlines the standard procedure for deploying static applications
(e.g., websites and single-page applications) to a Google Cloud Storage (GCS)
bucket using the `gcloud storage` command-line tool.

--------------------------------------------------------------------------------

## Step 1: Gather Deployment Parameters

Before executing any commands, the following parameters must be identified:

*   **`PROJECT_ID`**: The Google Cloud project where the bucket will be hosted.
*   **`BUCKET_NAME`**: The name of the GCS bucket (e.g.,
    `gs://my-static-site-bucket`).
*   **`LOCATION`**: The geographic location for the bucket (e.g.,
    `us-central1`).
*   **`SOURCE_PATH`**: The local directory containing the build artifacts (e.g.,
    `./dist`, `./build`).
*   **`DESTINATION_DIR`**: (Optional) The directory within the bucket to upload
    to.
*   **`MAIN_FILE`**: The entry point of the application (e.g., `index.html`).
    This is **identified automatically** by inspecting the build artifacts.

--------------------------------------------------------------------------------

## Step 2: Prepare the Storage Bucket

### 1. Create the Bucket (if it doesn't exist)

```bash
gcloud storage buckets create gs://<BUCKET_NAME> \
    --project=<PROJECT_ID> \
    --location=<LOCATION>
```

### 2. Enable Public Access (Requires User Confirmation)

Warn the user that granting `roles/storage.objectViewer` to `allUsers` exposes
all files in the bucket publicly on the internet, and obtain explicit
confirmation before running:

```bash
gcloud storage buckets add-iam-policy-binding gs://<BUCKET_NAME> \
    --member=allUsers \
    --role=roles/storage.objectViewer \
    --project=<PROJECT_ID>
```

--------------------------------------------------------------------------------

## Step 3: Deploy Build Artifacts

Use `gcloud storage cp -r` to upload the static build output directory (e.g.,
`./dist/` or `./build/`, never the repository root) to the bucket.

### Best Practice: Avoid Uploading Dotfiles and Repository Metadata

Unlike Cloud Build or `gcloud run deploy`, `gcloud storage cp` does **not**
respect `.gitignore` or `.gcloudignore` (and does not accept an `--exclude`
flag). Never use `<SOURCE_PATH>/**` or run against the repository root—upload
`<SOURCE_PATH>/*` from the clean build output directory (`./dist`, `./build`) so
POSIX globbing omits leading-dot files (`.git`, `.env`, `.gcp-deploy`):

```bash
gcloud storage cp -r <SOURCE_PATH>/* gs://<BUCKET_NAME>/<DESTINATION_DIR> \
    --project=<PROJECT_ID>
```

--------------------------------------------------------------------------------

## Step 4: Verification

After the upload is complete, the application can be accessed via the standard
GCS public URL:

`https://storage.googleapis.com/<BUCKET_NAME>/<MAIN_FILE>`
