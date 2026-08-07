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

"""Unit tests for list_trace_scope_table_names.py."""

import io
import unittest
from unittest import mock

import google.auth.exceptions


# pylint: disable=g-import-not-at-top
import list_trace_scope_table_names  # pytype: disable=import-error


class TestListTraceScopeTableNames(unittest.TestCase):

  @mock.patch("google.auth.default")
  @mock.patch("google.auth.transport.requests.Request")
  def test_get_access_token_success(self, mock_request, mock_auth_default):
    mock_credentials = mock.Mock()
    mock_credentials.token = "test-token"
    mock_auth_default.return_value = (mock_credentials, "test-project")

    token = list_trace_scope_table_names.get_access_token()

    self.assertEqual(token, "test-token")
    mock_credentials.refresh.assert_called_once()

  @mock.patch("requests.get")
  def test_list_trace_scopes_success(self, mock_get):
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "traceScopes": [{"resourceNames": ["projects/test-project"]}]
    }
    mock_get.return_value = mock_response

    scopes = list_trace_scope_table_names.list_trace_scopes(
        "test-project", "test-token"
    )

    self.assertEqual(scopes, [{"resourceNames": ["projects/test-project"]}])
    mock_get.assert_called_once_with(
        "https://observability.googleapis.com/v1/projects/test-project/locations/global/traceScopes",
        headers={"Authorization": "Bearer test-token"},
        timeout=10,
    )

  @mock.patch("requests.get")
  def test_list_trace_scopes_failure(self, mock_get):
    mock_response = mock.Mock()
    mock_response.status_code = 403
    mock_response.text = "Permission Denied"
    mock_get.return_value = mock_response

    with mock.patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
      scopes = list_trace_scope_table_names.list_trace_scopes(
          "test-project", "test-token"
      )

    self.assertEqual(scopes, [])
    self.assertIn("Error listing trace scopes:", mock_stderr.getvalue())

  @mock.patch("requests.get")
  def test_get_bucket_location_found(self, mock_get):
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "buckets": [
            {
                "name": (
                    "projects/test-project/locations/us-central1/buckets/other"
                )
            },
            {"name": "projects/test-project/locations/us-west1/buckets/_Trace"},
        ]
    }
    mock_get.return_value = mock_response

    location = list_trace_scope_table_names.get_bucket_location(
        "test-project", "test-token"
    )

    self.assertEqual(location, "us-west1")
    mock_get.assert_called_once_with(
        "https://observability.googleapis.com/v1/projects/test-project/locations/-/buckets",
        headers={"Authorization": "Bearer test-token"},
        timeout=10,
    )

  @mock.patch("requests.get")
  def test_get_bucket_location_not_found(self, mock_get):
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "buckets": [{
            "name": "projects/test-project/locations/us-central1/buckets/other"
        }]
    }
    mock_get.return_value = mock_response

    location = list_trace_scope_table_names.get_bucket_location(
        "test-project", "test-token"
    )

    self.assertIsNone(location)

  @mock.patch("requests.get")
  def test_get_bucket_location_error(self, mock_get):
    mock_response = mock.Mock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_get.return_value = mock_response

    with mock.patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
      location = list_trace_scope_table_names.get_bucket_location(
          "test-project", "test-token"
      )

    self.assertIsNone(location)
    self.assertIn(
        "Error listing buckets for test-project", mock_stderr.getvalue()
    )

  @mock.patch("list_trace_scope_table_names.get_access_token")
  @mock.patch("list_trace_scope_table_names.list_trace_scopes")
  @mock.patch("list_trace_scope_table_names.get_bucket_location")
  def test_main_success(
      self, mock_get_bucket, mock_list_scopes, mock_get_token
  ):
    mock_get_token.return_value = "test-token"
    mock_list_scopes.return_value = [
        {"resourceNames": ["projects/p1", "projects/p2"]}
    ]
    mock_get_bucket.side_effect = lambda proj, token: (
        "us-central1" if proj == "p1" else None
    )

    with (
        mock.patch(
            "sys.argv",
            ["list_trace_scope_table_names.py", "--project_id", "test-project"],
        ),
        mock.patch("sys.stdout", new_callable=io.StringIO) as mock_stdout,
        mock.patch("sys.stderr", new_callable=io.StringIO) as mock_stderr,
    ):
      list_trace_scope_table_names.main()

    output = mock_stdout.getvalue()
    err_output = mock_stderr.getvalue()

    self.assertIn("p1.us-central1._Trace.Spans._AllSpans", output)
    self.assertIn(
        "Could not find _Trace bucket location for project p2", err_output
    )

  @mock.patch("list_trace_scope_table_names.get_access_token")
  def test_main_token_failure(self, mock_get_token):
    mock_get_token.side_effect = google.auth.exceptions.GoogleAuthError(
        "Auth failed"
    )

    with (
        mock.patch(
            "sys.argv",
            ["list_trace_scope_table_names.py", "--project_id", "test-project"],
        ),
        mock.patch("sys.stderr", new_callable=io.StringIO) as mock_stderr,
        self.assertRaises(SystemExit) as cm,
    ):
      list_trace_scope_table_names.main()

    self.assertEqual(cm.exception.code, 1)
    self.assertIn(
        "Failed to get credentials: Auth failed", mock_stderr.getvalue()
    )


if __name__ == "__main__":
  unittest.main()
