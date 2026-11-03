# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Helper script to derive Observability Analytics table names.

This script identifies tables containing log data for a given GCP project.
"""

import argparse
import re
import sys

import google.auth
import google.auth.exceptions
import google.auth.transport.requests
import requests


def get_access_token() -> str:
  """Gets an OAuth2 access token using Google Application Default Credentials.

  Returns:
      A string containing the OAuth2 access token.
  """
  credentials, _ = google.auth.default(
      scopes=['https://www.googleapis.com/auth/cloud-platform']
  )
  auth_req = google.auth.transport.requests.Request()
  credentials.refresh(auth_req)
  return credentials.token


def list_log_buckets_names(project_id: str, token: str) -> list[str]:
  """Lists all log bucket names for the given GCP project.

  Args:
      project_id: The GCP project ID.
      token: OAuth2 access token.

  Returns:
      A list of log bucket resource names.
  """
  url = (
      'https://logging.googleapis.com/v2/projects/'
      f'{project_id}/locations/-/buckets'
  )
  headers = {'Authorization': f'Bearer {token}'}
  response = requests.get(url, headers=headers, timeout=10)
  if response.status_code != 200:
    print(f'Error listing log scopes: {response.text}', file=sys.stderr)
    return []
  bucket_names = []
  for bucket in response.json().get('buckets', []):
    bucket_names.append(bucket.get('name', ''))
  return bucket_names


def get_bucket_all_logs_views(bucket_name: str, token: str) -> str | None:
  """Finds the location of the '_AllLogs' log bucket for the given GCP project.

  Args:
      bucket_name: The name of the log bucket to query the views for.
      token: OAuth2 access token.

  Returns:
      The name of the '_AllLogs' log bucket view if found, otherwise None.
  """
  url = f'https://logging.googleapis.com/v2/{bucket_name}/views'
  headers = {'Authorization': f'Bearer {token}'}
  response = requests.get(url, headers=headers, timeout=10)
  if response.status_code != 200:
    print(
        f'Error listing bucket views for {bucket_name}: {response.text}',
        file=sys.stderr,
    )
    return None
  views = response.json().get('views', [])
  for view in views:
    if view.get('name', '').endswith('/views/_AllLogs'):
      match = re.match(
          r'projects/[^/]+/locations/([^/]+)/buckets/([^/]+)/views/_AllLogs',
          view['name'],
      )
      if match:
        return view['name']
  return None


def parse_table_name_from_bucket_view(view_path: str | None) -> str | None:
  """Parses the table name from the log bucket view name.

  Args:
      view_path: The full resource path of the log bucket view.

  Returns:
      The derived table name for use in Observability Analytics queries, or None
      if parsing fails.
  """
  if not view_path:
    return None
  match = re.match(
      r'projects/([^/]+)/locations/([^/]+)/buckets/([^/]+)/views/([^/]+)',
      view_path,
  )
  if match:
    return (
        f'{match.group(1)}.{match.group(2)}.{match.group(3)}.{match.group(4)}'
    )
  return None


def main():
  parser = argparse.ArgumentParser(
      description=(
          'Derive Observability Analytics log table names for a project.'
      )
  )
  parser.add_argument(
      '--project_id', required=True, help='GCP Project ID to query.'
  )
  args = parser.parse_args()
  project_id = args.project_id

  try:
    token = get_access_token()
  except google.auth.exceptions.GoogleAuthError as e:
    print(f'Failed to get credentials: {e}', file=sys.stderr)
    sys.exit(1)

  buckets = list_log_buckets_names(project_id, token)
  if not buckets:
    print(f'No log buckets found for project {project_id}')
    sys.exit(0)

  table_names = []
  for bucket in buckets:
    all_logs_view_location = get_bucket_all_logs_views(bucket, token)
    if all_logs_view_location:
      table_name = parse_table_name_from_bucket_view(all_logs_view_location)
      if table_name:
        table_names.append(table_name)
    else:
      print(
          f'Could not find _AllLogs bucket view location for bucket {bucket}',
          file=sys.stderr,
      )

  if table_names:
    for table_name in table_names:
      print(table_name)
  else:
    print('No table names found.')


if __name__ == '__main__':
  main()
