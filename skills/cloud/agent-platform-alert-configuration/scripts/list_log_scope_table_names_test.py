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

"""Unit tests for list_log_scope_table_names.py."""

import io
import unittest
from unittest import mock

import google.auth.exceptions


# pylint: disable=g-import-not-at-top
import list_log_scope_table_names  # pytype: disable=import-error


class TestListLogScopeTableNames(unittest.TestCase):

  @mock.patch("google.auth.default")
  @mock.patch("google.auth.transport.requests.Request")
  def test_get_access_token_success(self, _, mock_auth_default):
    mock_credentials = mock.Mock()
    mock_credentials.token = "test-token"
    mock_auth_default.return_value = (mock_credentials, "test-project")

    token = list_log_scope_table_names.get_access_token()

    self.assertEqual(token, "test-token")
    mock_credentials.refresh.assert_called_once()

  @mock.patch("requests.get")
  def test_list_log_buckets_names_success(self, mock_get):
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "buckets": [
            {"name": "projects/test-project/locations/global/buckets/_Default"},
            {"name": "projects/test-project/locations/us-central1/buckets/b1"},
        ]
    }
    mock_get.return_value = mock_response

    bucket_names = list_log_scope_table_names.list_log_buckets_names(
        "test-project", "test-token"
    )

    self.assertEqual(
        bucket_names,
        [
            "projects/test-project/locations/global/buckets/_Default",
            "projects/test-project/locations/us-central1/buckets/b1",
        ],
    )
    mock_get.assert_called_once_with(
        "https://logging.googleapis.com/v2/projects/test-project/locations/-/buckets",
        headers={"Authorization": "Bearer test-token"},
        timeout=10,
    )

  @mock.patch("requests.get")
  def test_list_log_buckets_names_failure(self, mock_get):
    mock_response = mock.Mock()
    mock_response.status_code = 403
    mock_response.text = "Permission Denied"
    mock_get.return_value = mock_response

    with mock.patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
      bucket_names = list_log_scope_table_names.list_log_buckets_names(
          "test-project", "test-token"
      )

    self.assertEqual(bucket_names, [])
    self.assertIn("Error listing log scopes:", mock_stderr.getvalue())

  @mock.patch("requests.get")
  def test_get_bucket_all_logs_views_found(self, mock_get):
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "views": [
            {
                "name": (
                    "projects/test-project/locations/global/buckets/_Default/views/_AllLogs"
                )
            },
            {
                "name": (
                    "projects/test-project/locations/global/buckets/_Default/views/custom"
                )
            },
        ]
    }
    mock_get.return_value = mock_response

    view_name = list_log_scope_table_names.get_bucket_all_logs_views(
        "projects/test-project/locations/global/buckets/_Default", "test-token"
    )

    self.assertEqual(
        view_name,
        "projects/test-project/locations/global/buckets/_Default/views/_AllLogs",
    )
    mock_get.assert_called_once_with(
        "https://logging.googleapis.com/v2/projects/test-project/locations/global/buckets/_Default/views",
        headers={"Authorization": "Bearer test-token"},
        timeout=10,
    )

  @mock.patch("requests.get")
  def test_get_bucket_all_logs_views_not_found(self, mock_get):
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "views": [{
            "name": (
                "projects/test-project/locations/global/buckets/_Default/views/custom"
            )
        }]
    }
    mock_get.return_value = mock_response

    view_name = list_log_scope_table_names.get_bucket_all_logs_views(
        "projects/test-project/locations/global/buckets/_Default", "test-token"
    )

    self.assertIsNone(view_name)

  @mock.patch("requests.get")
  def test_get_bucket_all_logs_views_error(self, mock_get):
    mock_response = mock.Mock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_get.return_value = mock_response

    with mock.patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
      view_name = list_log_scope_table_names.get_bucket_all_logs_views(
          "projects/test-project/locations/global/buckets/_Default",
          "test-token",
      )

    self.assertIsNone(view_name)
    self.assertIn("Error listing bucket views for", mock_stderr.getvalue())

  def test_parse_table_name_from_bucket_view_success(self):
    table_name = list_log_scope_table_names.parse_table_name_from_bucket_view(
        "projects/test-project/locations/global/buckets/_Default/views/_AllLogs"
    )
    self.assertEqual(table_name, "test-project.global._Default._AllLogs")

  def test_parse_table_name_from_bucket_view_none(self):
    table_name = list_log_scope_table_names.parse_table_name_from_bucket_view(
        None
    )
    self.assertIsNone(table_name)

  def test_parse_table_name_from_bucket_view_no_match(self):
    table_name = list_log_scope_table_names.parse_table_name_from_bucket_view(
        "invalid-view-string"
    )
    self.assertIsNone(table_name)

  @mock.patch("list_log_scope_table_names.get_access_token")
  @mock.patch("list_log_scope_table_names.list_log_buckets_names")
  @mock.patch("list_log_scope_table_names.get_bucket_all_logs_views")
  def test_main_success(
      self, mock_get_views, mock_list_buckets, mock_get_token
  ):
    mock_get_token.return_value = "test-token"
    mock_list_buckets.return_value = [
        "projects/test-project/locations/global/buckets/_Default",
        "projects/test-project/locations/global/buckets/missing",
    ]
    mock_get_views.side_effect = lambda bucket, token: (
        f"{bucket}/views/_AllLogs" if "_Default" in bucket else None
    )

    with (
        mock.patch(
            "sys.argv",
            ["list_log_scope_table_names.py", "--project_id", "test-project"],
        ),
        mock.patch("sys.stdout", new_callable=io.StringIO) as mock_stdout,
        mock.patch("sys.stderr", new_callable=io.StringIO) as mock_stderr,
    ):
      list_log_scope_table_names.main()

    output = mock_stdout.getvalue()
    err_output = mock_stderr.getvalue()

    self.assertIn("test-project.global._Default._AllLogs", output)
    self.assertIn(
        "Could not find _AllLogs bucket view location for bucket"
        " projects/test-project/locations/global/buckets/missing",
        err_output,
    )

  @mock.patch("list_log_scope_table_names.get_access_token")
  @mock.patch("list_log_scope_table_names.list_log_buckets_names")
  def test_main_no_buckets(self, mock_list_buckets, mock_get_token):
    mock_get_token.return_value = "test-token"
    mock_list_buckets.return_value = []

    with (
        mock.patch(
            "sys.argv",
            ["list_log_scope_table_names.py", "--project_id", "test-project"],
        ),
        mock.patch("sys.stdout", new_callable=io.StringIO) as mock_stdout,
        self.assertRaises(SystemExit) as cm,
    ):
      list_log_scope_table_names.main()

    self.assertEqual(cm.exception.code, 0)
    self.assertIn(
        "No log buckets found for project test-project", mock_stdout.getvalue()
    )

  @mock.patch("list_log_scope_table_names.get_access_token")
  def test_main_token_failure(self, mock_get_token):
    mock_get_token.side_effect = google.auth.exceptions.GoogleAuthError(
        "Auth failed"
    )

    with (
        mock.patch(
            "sys.argv",
            ["list_log_scope_table_names.py", "--project_id", "test-project"],
        ),
        mock.patch("sys.stderr", new_callable=io.StringIO) as mock_stderr,
        self.assertRaises(SystemExit) as cm,
    ):
      list_log_scope_table_names.main()

    self.assertEqual(cm.exception.code, 1)
    self.assertIn(
        "Failed to get credentials: Auth failed", mock_stderr.getvalue()
    )


if __name__ == "__main__":
  unittest.main()
