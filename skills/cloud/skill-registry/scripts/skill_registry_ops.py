"""A script to perform operations on the Skill Registry."""

import argparse
import base64
import io
import json
import os
import sys
import urllib.parse
import zipfile
import google.auth
from google.auth.transport.requests import Request
import requests


def get_access_token():
  credentials, _ = google.auth.default()
  credentials.refresh(Request())
  return credentials.token


def get_endpoint(region):
  return f"{region}-aiplatform.googleapis.com"


def upload(args):
  """Uploads a new skill in the Skill Registry.

  Args:
    args: The command line arguments.
  """
  token = get_access_token()
  endpoint = get_endpoint(args.location)
  url = f"https://{endpoint}/v1beta1/projects/{args.project}/locations/{args.location}/skills?skillId={args.skill_id}"

  headers = {
      "Authorization": f"Bearer {token}",
      "Content-Type": "application/json",
  }

  if args.zip_file:
    with open(args.zip_file, "rb") as f:
      zip_bytes = f.read()
  elif args.folder:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
      for root, _, files in os.walk(args.folder):
        for file in files:
          file_path = os.path.join(root, file)
          arcname = os.path.relpath(file_path, args.folder)
          zip_file.write(file_path, arcname)
    zip_bytes = zip_buffer.getvalue()
  else:
    raise ValueError("Must provide either --zip-file or --folder")

  zipped_filesystem = base64.b64encode(zip_bytes).decode("utf-8")

  payload = {
      "displayName": args.display_name,
      "description": args.description,
      "zippedFilesystem": zipped_filesystem,
  }

  print(f"Uploading skill {args.skill_id} at {endpoint}...")
  response = requests.post(url, headers=headers, json=payload)

  if response.status_code >= 400:
    print(f"Error: {response.status_code} - {response.text}")
    sys.exit(1)

  print("Response:")
  print(json.dumps(response.json(), indent=2))


def search(args):
  """Searches for skills in the Skill Registry."""
  token = get_access_token()
  endpoint = get_endpoint(args.location)
  query_encoded = urllib.parse.quote(args.query)
  url = f"https://{endpoint}/v1beta1/projects/{args.project}/locations/{args.location}/skills:retrieve?query={query_encoded}&topK={args.top_k}"

  headers = {
      "Authorization": f"Bearer {token}",
      "Content-Type": "application/json",
  }

  print(f"Searching skills at {endpoint} with query '{args.query}'...")
  response = requests.get(url, headers=headers)

  if response.status_code >= 400:
    print(f"Error: {response.status_code} - {response.text}")
    sys.exit(1)

  print("Response:")
  print(json.dumps(response.json(), indent=2))


def get_skill(args):
  """Gets a skill from the Skill Registry."""
  token = get_access_token()
  endpoint = get_endpoint(args.location)
  url = f"https://{endpoint}/v1beta1/projects/{args.project}/locations/{args.location}/skills/{args.skill_id}"

  headers = {
      "Authorization": f"Bearer {token}",
  }

  print(f"Getting skill {args.skill_id} at {endpoint}...")
  response = requests.get(url, headers=headers)

  if response.status_code >= 400:
    print(f"Error: {response.status_code} - {response.text}")
    sys.exit(1)

  print("Response:")
  print(json.dumps(response.json(), indent=2))


def list_skills(args):
  """Lists skills in the Skill Registry."""
  token = get_access_token()
  endpoint = get_endpoint(args.location)
  url = f"https://{endpoint}/v1beta1/projects/{args.project}/locations/{args.location}/skills"

  headers = {
      "Authorization": f"Bearer {token}",
  }

  print(f"Listing skills at {endpoint}...")
  response = requests.get(url, headers=headers)

  if response.status_code >= 400:
    print(f"Error: {response.status_code} - {response.text}")
    sys.exit(1)

  print("Response:")
  print(json.dumps(response.json(), indent=2))


def delete_skill(args):
  """Deletes a skill from the Skill Registry."""
  token = get_access_token()
  endpoint = get_endpoint(args.location)
  url = f"https://{endpoint}/v1beta1/projects/{args.project}/locations/{args.location}/skills/{args.skill_id}"

  headers = {
      "Authorization": f"Bearer {token}",
  }

  print(f"Deleting skill {args.skill_id} at {endpoint}...")
  response = requests.delete(url, headers=headers)

  if response.status_code >= 400:
    print(f"Error: {response.status_code} - {response.text}")
    sys.exit(1)

  print("Response:")
  print(json.dumps(response.json(), indent=2))


def update_skill(args):
  """Updates an existing skill in the Skill Registry."""
  token = get_access_token()
  endpoint = get_endpoint(args.location)

  update_mask_parts = []
  payload = {}

  if args.display_name:
    update_mask_parts.append("displayName")
    payload["displayName"] = args.display_name

  if args.description:
    update_mask_parts.append("description")
    payload["description"] = args.description

  if args.zip_file or args.folder:
    if args.zip_file:
      with open(args.zip_file, "rb") as f:
        zip_bytes = f.read()
    elif args.folder:
      zip_buffer = io.BytesIO()
      with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for root, _, files in os.walk(args.folder):
          for file in files:
            file_path = os.path.join(root, file)
            arcname = os.path.relpath(file_path, args.folder)
            zip_file.write(file_path, arcname)
      zip_bytes = zip_buffer.getvalue()

    zipped_filesystem = base64.b64encode(zip_bytes).decode("utf-8")

    update_mask_parts.append("zippedFilesystem")
    payload["zippedFilesystem"] = zipped_filesystem

  if not update_mask_parts:
    print(
        "Error: must provide at least one field to update (--display-name,"
        " --description, --zip-file, --folder)"
    )
    sys.exit(1)

  update_mask = ",".join(update_mask_parts)
  url = f"https://{endpoint}/v1beta1/projects/{args.project}/locations/{args.location}/skills/{args.skill_id}?updateMask={update_mask}"

  headers = {
      "Authorization": f"Bearer {token}",
      "Content-Type": "application/json",
  }

  print(f"Updating skill {args.skill_id} at {endpoint}...")
  response = requests.patch(url, headers=headers, json=payload)

  if response.status_code >= 400:
    print(f"Error: {response.status_code} - {response.text}")
    sys.exit(1)

  print("Response:")
  print(json.dumps(response.json(), indent=2))


def list_skill_revision(args):
  """Lists revisions of a skill in the Skill Registry."""
  token = get_access_token()
  endpoint = get_endpoint(args.location)
  url = f"https://{endpoint}/v1beta1/projects/{args.project}/locations/{args.location}/skills/{args.skill_id}/revisions"

  headers = {
      "Authorization": f"Bearer {token}",
  }

  print(f"Listing revisions for skill {args.skill_id} at {endpoint}...")
  response = requests.get(url, headers=headers)

  if response.status_code >= 400:
    print(f"Error: {response.status_code} - {response.text}")
    sys.exit(1)

  print("Response:")
  print(json.dumps(response.json(), indent=2))


def get_skill_revision(args):
  """Gets a specific revision of a skill from the Skill Registry."""
  token = get_access_token()
  endpoint = get_endpoint(args.location)
  url = f"https://{endpoint}/v1beta1/projects/{args.project}/locations/{args.location}/skills/{args.skill_id}/revisions/{args.revision_id}"

  headers = {
      "Authorization": f"Bearer {token}",
  }

  print(
      f"Getting skill {args.skill_id} revision {args.revision_id} at"
      f" {endpoint}..."
  )
  response = requests.get(url, headers=headers)

  if response.status_code >= 400:
    print(f"Error: {response.status_code} - {response.text}")
    sys.exit(1)

  print("Response:")
  print(json.dumps(response.json(), indent=2))


def monitor(args):
  """Monitors the status of a long-running operation."""
  token = get_access_token()
  endpoint = get_endpoint(args.location)
  op_id = args.operation_id.lstrip("/")
  url = f"https://{endpoint}/v1beta1/{op_id}"

  headers = {
      "Authorization": f"Bearer {token}",
  }

  print(f"Monitoring operation {args.operation_id} at {endpoint}...")
  response = requests.get(url, headers=headers)

  if response.status_code >= 400:
    print(f"Error: {response.status_code} - {response.text}")
    sys.exit(1)

  print("Response:")
  print(json.dumps(response.json(), indent=2))


def main():
  parser = argparse.ArgumentParser(
      description="Skill Registry Operations Utility"
  )
  parser.add_argument("--project", default=os.environ.get("GCP_PROJECT_ID"))
  parser.add_argument("--location", default=os.environ.get("GCP_LOCATION"))

  subparsers = parser.add_subparsers(dest="action", required=True)

  upload_parser = subparsers.add_parser("upload")
  upload_parser.add_argument("--skill-id", required=True)
  upload_parser.add_argument("--display-name", required=True)
  upload_parser.add_argument("--description", required=True)

  group = upload_parser.add_mutually_exclusive_group(required=True)
  group.add_argument("--zip-file")
  group.add_argument("--folder")

  search_parser = subparsers.add_parser("search")
  search_parser.add_argument("--query", required=True)
  search_parser.add_argument("--top-k", type=int, default=5)

  get_parser = subparsers.add_parser("get")
  get_parser.add_argument("--skill-id", required=True)

  subparsers.add_parser("list")

  delete_parser = subparsers.add_parser("delete")
  delete_parser.add_argument("--skill-id", required=True)

  update_parser = subparsers.add_parser("update")
  update_parser.add_argument("--skill-id", required=True)
  update_parser.add_argument("--display-name", required=False)
  update_parser.add_argument("--description", required=False)
  update_group = update_parser.add_mutually_exclusive_group(required=False)
  update_group.add_argument("--zip-file")
  update_group.add_argument("--folder")

  list_rev_parser = subparsers.add_parser("list-revision")
  list_rev_parser.add_argument("--skill-id", required=True)

  get_rev_parser = subparsers.add_parser("get-revision")
  get_rev_parser.add_argument("--skill-id", required=True)
  get_rev_parser.add_argument("--revision-id", required=True)

  monitor_parser = subparsers.add_parser("monitor")
  monitor_parser.add_argument("--operation-id", required=True)

  args = parser.parse_args()

  missing = []
  if not args.project:
    missing.append("GCP_PROJECT_ID")
  if not args.location:
    missing.append("GCP_LOCATION")

  if missing:
    print(
        f"ERROR: Missing required environment variables: {', '.join(missing)}"
    )
    sys.exit(1)

  if args.action == "upload":
    upload(args)
  elif args.action == "search":
    search(args)
  elif args.action == "get":
    get_skill(args)
  elif args.action == "list":
    list_skills(args)
  elif args.action == "delete":
    delete_skill(args)
  elif args.action == "update":
    update_skill(args)
  elif args.action == "list-revision":
    list_skill_revision(args)
  elif args.action == "get-revision":
    get_skill_revision(args)
  elif args.action == "monitor":
    monitor(args)


if __name__ == "__main__":
  main()
