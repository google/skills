#!/usr/bin/env python3
"""Tests for db_search.py."""

import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db_search  # pylint: disable=g-import-not-at-top


class DbSearchTest(unittest.TestCase):

  def setUp(self):
    super().setUp()
    self.test_data = {
        "frameworks": {
            "builtin-fw1": {
                "displayName": "Framework One",
                "description": "This is the first framework",
            },
            "builtin-hipaa": {
                "displayName": "HIPAA",
                "description": (
                    "Health Insurance Portability and Accountability Act"
                ),
            },
        },
        "cloud_controls": {
            "cc1": {
                "displayName": "Control One",
                "description": "First control",
            },
            "cc-health": {
                "displayName": "Health Control",
                "description": "Control for health data",
            },
        },
    }

    self.temp_dir = tempfile.TemporaryDirectory()
    self.json_path = os.path.join(self.temp_dir.name, "test_resources.json")
    with open(self.json_path, "w") as f:
      json.dump(self.test_data, f)

  def tearDown(self):
    self.temp_dir.cleanup()
    super().tearDown()

  def test_search_finds_matches(self):
    test_args = [
        "db_search.py",
        "--resources_json",
        self.json_path,
        "--query",
        "health",
    ]
    with mock.patch.object(sys, "argv", test_args):
      with mock.patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
        db_search.main()
        output = mock_stdout.getvalue()

    self.assertIn("Search Results for 'health'", output)
    self.assertIn("ID: builtin-hipaa | Name: HIPAA", output)
    self.assertIn("ID: cc-health | Name: Health Control", output)
    self.assertNotIn("builtin-fw1", output)
    self.assertNotIn("cc1", output)

  def test_search_case_insensitive(self):
    test_args = [
        "db_search.py",
        "--resources_json",
        self.json_path,
        "--query",
        "HIPAA",
    ]
    with mock.patch.object(sys, "argv", test_args):
      with mock.patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
        db_search.main()
        output = mock_stdout.getvalue()

    self.assertIn("Search Results for 'HIPAA'", output)
    self.assertIn("ID: builtin-hipaa | Name: HIPAA", output)
    self.assertNotIn("builtin-fw1", output)
    self.assertNotIn("cc1", output)

  def test_search_missing_file(self):
    test_args = [
        "db_search.py",
        "--resources_json",
        "non_existent.json",
        "--query",
        "health",
    ]
    with mock.patch.object(sys, "argv", test_args):
      with mock.patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
        with self.assertRaises(SystemExit) as cm:
          db_search.main()

        self.assertEqual(cm.exception.code, 1)
        output = mock_stderr.getvalue()
        self.assertIn("ERROR: Could not read non_existent.json", output)

  @mock.patch("builtins.open")
  def test_search_permission_error(self, mock_open):
    mock_open.side_effect = PermissionError("Permission denied")
    test_args = [
        "db_search.py",
        "--resources_json",
        self.json_path,
        "--query",
        "health",
    ]
    with mock.patch.object(sys, "argv", test_args):
      with mock.patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
        with self.assertRaises(SystemExit) as cm:
          db_search.main()

        self.assertEqual(cm.exception.code, 1)
        output = mock_stderr.getvalue()
        self.assertIn("ERROR: PERMISSION_DENIED", output)


if __name__ == "__main__":
  unittest.main()
