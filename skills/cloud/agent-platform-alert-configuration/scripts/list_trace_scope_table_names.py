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

This script identifies tables containing trace span data for a given GCP
project.
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


def list_trace_scopes(project_id: str, token: str) -> list[dict]:
  """Lists all trace scopes for the given GCP project.

  Args:
      project_id: The GCP project ID.
      token: OAuth2 access token.

  Returns:
      A list of dictionaries representing trace scopes.
  """
  url = (
      'https://observability.googleapis.com/v1/projects/'
      f'{project_id}/locations/global/traceScopes'
  )
  headers = {'Authorization': f'Bearer {token}'}
  response = requests.get(url, headers=headers, timeout=10)
  if response.status_code != 200:
    print(f'Error listing trace scopes: {response.text}', file=sys.stderr)
    return []
  return response.json().get('traceScopes', [])


def get_bucket_location(project_id: str, token: str) -> str | None:
  """Finds the location of the '_Trace' log bucket for the given GCP project.

  Args:
      project_id: The ID of the GCP project to query.
      token: OAuth2 access token.

  Returns:
      The location string (e.g., 'us-central1') of the '_Trace' bucket, or None
      if it cannot be found or an error occurs.
  """
  url = (
      'https://observability.googleapis.com/v1/projects/'
      f'{project_id}/locations/-/buckets'
  )
  headers = {'Authorization': f'Bearer {token}'}
  response = requests.get(url, headers=headers, timeout=10)
  if response.status_code != 200:
    print(
        f'Error listing buckets for {project_id}: {response.text}',
        file=sys.stderr,
    )
    return None
  buckets = response.json().get('buckets', [])
  for bucket in buckets:
    if bucket.get('name', '').endswith('/buckets/_Trace'):
      match = re.match(
          r'projects/[^/]+/locations/([^/]+)/buckets/_Trace', bucket['name']
      )
      if match:
        return match.group(1)
  return None


def main():
  parser = argparse.ArgumentParser(
      description='Derive Observability Analytics table names for a project.'
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

  scopes = list_trace_scopes(project_id, token)
  if not scopes:
    print(f'No trace scopes found for project {project_id}')
    sys.exit(0)

  target_projects = set()
  for scope in scopes:
    resources = scope.get('resourceNames', [])
    for resource in resources:
      if resource.startswith('projects/'):
        target_projects.add(resource.split('/')[1])
  if not target_projects:
    target_projects.add(project_id)

  table_names = []
  for proj in target_projects:
    location = get_bucket_location(proj, token)
    if location:
      table_name = f'{proj}.{location}._Trace.Spans._AllSpans'
      table_names.append(table_name)
    else:
      print(
          f'Could not find _Trace bucket location for project {proj}',
          file=sys.stderr,
      )

  if table_names:
    for table_name in table_names:
      print(table_name)
  else:
    print('No table names found.')


if __name__ == '__main__':
  main()
