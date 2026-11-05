#!/usr/bin/env python3
"""Unit tests for the gcloud-backed db_resources_loader."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db_resources_loader  # pylint: disable=g-import-not-at-top


def _completed(
    stdout: str = "", stderr: str = "", returncode: int = 0
) -> subprocess.CompletedProcess[str]:
  return subprocess.CompletedProcess(
      args=["gcloud"], returncode=returncode, stdout=stdout, stderr=stderr
  )


_FRAMEWORKS = [
    # Builtin AW
    {
        "name": "organizations/123/locations/global/frameworks/builtin-fw-aw",
        "category": ["ASSURED_WORKLOADS", "XYZ"],
        "cloudControlDetails": [{
            "name": (
                "organizations/123/locations/global/cloudControls/"
                "builtin-cc-aw-1"
            )
        }],
    },
    # Builtin Not-AW
    {
        "name": (
            "organizations/123/locations/global/frameworks/builtin-fw-notaw"
        ),
        "category": ["OTHER"],
    },
    # Custom Framework
    {"name": "organizations/123/locations/global/frameworks/custom-fw-1"},
]
_CLOUD_CONTROLS = [
    # Builtin referenced in AW framework
    {
        "name": (
            "organizations/123/locations/global/cloudControls/builtin-cc-aw-1"
        )
    },
    # Builtin NOT referenced in AW framework
    {
        "name": (
            "organizations/123/locations/global/cloudControls/builtin-cc-not-aw"
        )
    },
    # Custom CC
    {"name": "organizations/123/locations/global/cloudControls/custom-cc-1"},
]


def _fake_gcloud(command, **unused_kwargs):
  """Stands in for `subprocess.run` with canned `gcloud ... list` output."""
  kind = command[2]
  payload = {"frameworks": _FRAMEWORKS, "cloud-controls": _CLOUD_CONTROLS}[kind]
  return _completed(stdout=json.dumps(payload))


class RunGcloudListTest(unittest.TestCase):

  @mock.patch.object(db_resources_loader.subprocess, "run")
  def test_runs_expected_gcloud_command_and_parses_json(self, mock_run):
    mock_run.return_value = _completed(
        stdout=json.dumps([{"name": "fw-1"}, {"name": "fw-2"}])
    )

    res = db_resources_loader.run_gcloud_list("frameworks", "123")

    self.assertEqual(res, [{"name": "fw-1"}, {"name": "fw-2"}])
    mock_run.assert_called_once()
    self.assertEqual(
        mock_run.call_args.args[0],
        [
            "gcloud",
            "compliance-manager",
            "frameworks",
            "list",
            "--organization=123",
            "--location=global",
            "--page-size=1000",
            "--format=json",
            "--quiet",
        ],
    )
    kwargs = mock_run.call_args.kwargs
    self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
    self.assertTrue(kwargs["capture_output"])
    self.assertFalse(kwargs["check"])
    self.assertEqual(
        kwargs["timeout"], db_resources_loader.GCLOUD_TIMEOUT_SECONDS
    )

  @mock.patch.object(db_resources_loader.subprocess, "run")
  def test_passes_the_requested_location(self, mock_run):
    mock_run.return_value = _completed(stdout="[]")

    db_resources_loader.run_gcloud_list("frameworks", "123", "europe-west1")

    command = mock_run.call_args.args[0]
    self.assertIn("--location=europe-west1", command)
    self.assertNotIn("--location=global", command)

  @mock.patch.object(db_resources_loader.subprocess, "run")
  def test_warns_when_a_list_is_exactly_one_full_page(self, mock_run):
    page = db_resources_loader.GCLOUD_PAGE_SIZE
    for count, expect_warning in ((page - 1, False), (page, True)):
      with self.subTest(count=count):
        mock_run.return_value = _completed(
            stdout=json.dumps([{"name": f"cc-{i}"} for i in range(count)])
        )
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
          items = db_resources_loader.run_gcloud_list("cloud-controls", "123")

        self.assertEqual(len(items), count)
        self.assertEqual("WARNING" in stderr.getvalue(), expect_warning)
        if expect_warning:
          self.assertIn("may be incomplete", stderr.getvalue())

  @mock.patch.object(db_resources_loader.subprocess, "run")
  def test_cloud_controls_use_the_kebab_case_command_group(self, mock_run):
    mock_run.return_value = _completed(stdout="[]")

    self.assertEqual(
        db_resources_loader.run_gcloud_list("cloud-controls", "123"), []
    )

    self.assertEqual(
        mock_run.call_args.args[0][:4],
        ["gcloud", "compliance-manager", "cloud-controls", "list"],
    )

  @mock.patch.object(db_resources_loader.subprocess, "run")
  def test_nonzero_exit_reports_only_the_error_line(self, mock_run):
    mock_run.return_value = _completed(
        returncode=1,
        stderr=(
            "Parsed [location] resource: organizations/123/locations/global\n"
            "ERROR: (gcloud.compliance-manager.frameworks.list)"
            " PERMISSION_DENIED: caller lacks permission\n"
            "- '@type': type.googleapis.com/google.rpc.DebugInfo\n"
            '  detail: "[ORIGINAL ERROR] generic::permission_denied: stack"\n'
        ),
    )

    with self.assertRaises(db_resources_loader.GcloudError) as ctx:
      db_resources_loader.run_gcloud_list("frameworks", "123")

    message = str(ctx.exception)
    self.assertIn("`gcloud compliance-manager frameworks list` failed", message)
    self.assertIn("exit code 1", message)
    self.assertIn("PERMISSION_DENIED: caller lacks permission", message)
    self.assertNotIn("ERROR:", message)
    self.assertNotIn("DebugInfo", message)
    self.assertNotIn("Parsed [location]", message)

  @mock.patch.object(db_resources_loader.subprocess, "run")
  def test_nonzero_exit_without_error_line_uses_first_lines(self, mock_run):
    mock_run.return_value = _completed(
        returncode=2, stderr="one\ntwo\nthree\nfour\n"
    )

    with self.assertRaises(db_resources_loader.GcloudError) as ctx:
      db_resources_loader.run_gcloud_list("frameworks", "123")

    self.assertIn("one two three", str(ctx.exception))
    self.assertNotIn("four", str(ctx.exception))

  @mock.patch.object(db_resources_loader.subprocess, "run")
  def test_long_error_line_is_truncated(self, mock_run):
    mock_run.return_value = _completed(
        returncode=1, stderr="ERROR: " + "x" * 5000
    )

    with self.assertRaises(db_resources_loader.GcloudError) as ctx:
      db_resources_loader.run_gcloud_list("frameworks", "123")

    self.assertLess(len(str(ctx.exception)), 1200)

  @mock.patch.object(db_resources_loader.subprocess, "run")
  def test_missing_gcloud_cli(self, mock_run):
    mock_run.side_effect = FileNotFoundError("gcloud")

    with self.assertRaisesRegex(
        db_resources_loader.GcloudError, "gcloud CLI was not found"
    ):
      db_resources_loader.run_gcloud_list("frameworks", "123")

  @mock.patch.object(db_resources_loader.subprocess, "run")
  def test_gcloud_that_cannot_be_executed(self, mock_run):
    mock_run.side_effect = PermissionError(13, "Permission denied", "gcloud")

    with self.assertRaisesRegex(
        db_resources_loader.GcloudError,
        "Could not run the gcloud CLI: .*Permission denied",
    ):
      db_resources_loader.run_gcloud_list("frameworks", "123")

  @mock.patch.object(db_resources_loader.subprocess, "run")
  def test_timeout(self, mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="gcloud", timeout=1)

    with self.assertRaisesRegex(db_resources_loader.GcloudError, "timed out"):
      db_resources_loader.run_gcloud_list("cloud-controls", "123")

  @mock.patch.object(db_resources_loader.subprocess, "run")
  def test_invalid_json(self, mock_run):
    mock_run.return_value = _completed(stdout="not json")

    with self.assertRaisesRegex(
        db_resources_loader.GcloudError, "did not return valid JSON"
    ):
      db_resources_loader.run_gcloud_list("frameworks", "123")

  @mock.patch.object(db_resources_loader.subprocess, "run")
  def test_json_that_is_not_a_list(self, mock_run):
    mock_run.return_value = _completed(stdout='{"frameworks": []}')

    with self.assertRaisesRegex(
        db_resources_loader.GcloudError, "did not return a JSON list"
    ):
      db_resources_loader.run_gcloud_list("frameworks", "123")


class NormalizeOrganizationIdTest(unittest.TestCase):

  def test_accepts_digits_and_resource_name_form(self):
    for raw in ("123", " 123\n", "organizations/123"):
      with self.subTest(raw=raw):
        self.assertEqual(
            db_resources_loader.normalize_organization_id(raw), "123"
        )

  def test_rejects_anything_that_is_not_a_numeric_id(self):
    for raw in (
        "",
        "abc",
        "organizations/",
        "organizations/abc",
        "12 3",
        "123 --project=other",
        "--organization=123",
        "123/../../etc",
        "folders/123",
    ):
      with self.subTest(raw=raw):
        with self.assertRaises(ValueError):
          db_resources_loader.normalize_organization_id(raw)


class LocationsTest(unittest.TestCase):

  def test_shipped_file_is_well_formed(self):
    data = json.loads(
        db_resources_loader.LOCATIONS_FILE.read_text(encoding="utf-8")
    )
    entries = data["locations"]
    ids = [entry["id"] for entry in entries]

    self.assertEqual(
        data["default_location"], db_resources_loader.DEFAULT_LOCATION
    )
    self.assertIn(db_resources_loader.DEFAULT_LOCATION, ids)
    self.assertEqual(len(ids), len(set(ids)))
    for entry in entries:
      with self.subTest(location=entry["id"]):
        self.assertRegex(entry["id"], r"^[a-z][a-z0-9-]*$")
        # `prod-*` names are backend environment names that the API rejects.
        self.assertFalse(entry["id"].startswith("prod-"))
        self.assertTrue(entry["description"].strip())

  def test_load_locations_maps_every_id_to_its_description(self):
    data = json.loads(
        db_resources_loader.LOCATIONS_FILE.read_text(encoding="utf-8")
    )

    locations = db_resources_loader.load_locations()

    self.assertEqual(
        locations, {e["id"]: e["description"] for e in data["locations"]}
    )
    self.assertIn("australia-southeast1", locations)

  def test_load_locations_rejects_unusable_files(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
      missing = pathlib.Path(tmp_dir, "missing.json")
      invalid = pathlib.Path(tmp_dir, "invalid.json")
      invalid.write_text("not json")
      wrong_shape = pathlib.Path(tmp_dir, "wrong_shape.json")
      wrong_shape.write_text(json.dumps({"locations": [{"id": "global"}]}))

      for path in (missing, invalid, wrong_shape):
        with self.subTest(path=path.name):
          with self.assertRaisesRegex(
              ValueError, "Could not read the supported locations"
          ):
            db_resources_loader.load_locations(path)

  def test_locations_file_is_found_next_to_a_linked_script(self):
    # A build system can link each script file on its own: the path the module
    # reports is then a link, and the real file is in another directory.
    with tempfile.TemporaryDirectory() as tmp_dir:
      real_dir = pathlib.Path(tmp_dir, "store")
      skill_dir = pathlib.Path(tmp_dir, "skill")
      real_dir.mkdir()
      (skill_dir / "scripts").mkdir(parents=True)
      (skill_dir / "assets").mkdir()
      real_script = real_dir / "db_resources_loader.py"
      real_script.write_bytes(
          pathlib.Path(db_resources_loader.__file__).read_bytes()
      )
      linked_script = skill_dir / "scripts" / "db_resources_loader.py"
      linked_script.symlink_to(real_script)
      spec = importlib.util.spec_from_file_location(
          "linked_db_resources_loader", linked_script
      )
      module = importlib.util.module_from_spec(spec)
      with mock.patch.dict(sys.modules, {spec.name: module}):
        spec.loader.exec_module(module)

      self.assertEqual(
          module.LOCATIONS_FILE, skill_dir / "assets" / "locations.json"
      )

  def test_normalize_location_accepts_exact_ids(self):
    for raw, expected in (
        ("global", "global"),
        (" us-east1\n", "us-east1"),
        ("europe-west1", "europe-west1"),
    ):
      with self.subTest(raw=raw):
        self.assertEqual(db_resources_loader.normalize_location(raw), expected)

  def test_normalize_location_rejects_everything_else(self):
    for raw in (
        "",
        "GLOBAL",
        "prod-us-central1",
        "us-east",
        "Sydney",
        "us-east1 --project=other",
        "europe-west1/../x",
    ):
      with self.subTest(raw=raw):
        with self.assertRaisesRegex(ValueError, "Unknown location"):
          db_resources_loader.normalize_location(raw)


class FetchAndFilterTest(unittest.TestCase):

  @mock.patch.object(db_resources_loader, "run_gcloud_list")
  def test_filters_builtin_resources_and_keeps_custom(self, mock_list):
    mock_list.side_effect = lambda kind, org, location: {
        "frameworks": _FRAMEWORKS,
        "cloud-controls": _CLOUD_CONTROLS,
    }[kind]

    store = db_resources_loader.fetch_and_filter_db_resources("123")

    self.assertEqual(
        [c.args for c in mock_list.call_args_list],
        [("frameworks", "123", "global"), ("cloud-controls", "123", "global")],
    )
    self.assertEqual(store.organization_id, "123")
    self.assertEqual(store.location, "global")
    self.assertIn("builtin-fw-aw", store.frameworks)
    self.assertNotIn("builtin-fw-notaw", store.frameworks)
    self.assertIn("custom-fw-1", store.frameworks)

    self.assertIn("builtin-cc-aw-1", store.cloud_controls)
    self.assertNotIn("builtin-cc-not-aw", store.cloud_controls)
    self.assertIn("custom-cc-1", store.cloud_controls)

  @mock.patch.object(db_resources_loader, "run_gcloud_list")
  def test_keeps_builtin_hipaa_but_no_other_non_assured_workloads_builtin(
      self, mock_list
  ):
    hipaa = {
        "name": "organizations/123/locations/global/frameworks/builtin-hipaa",
        "category": ["INDUSTRY_DEFINED_STANDARD"],
    }
    other = {
        "name": (
            "organizations/123/locations/global/frameworks/"
            "builtin-other-standard"
        ),
        "category": ["INDUSTRY_DEFINED_STANDARD"],
    }
    mock_list.side_effect = lambda kind, org, location: {
        "frameworks": [hipaa, other],
        "cloud-controls": [],
    }[kind]

    store = db_resources_loader.fetch_and_filter_db_resources("123")

    # HIPAA has no `cloudControlDetails`: it loads without underlying controls.
    self.assertEqual(sorted(store.frameworks), ["builtin-hipaa"])
    self.assertEqual(store.cloud_controls, {})

  @mock.patch.object(db_resources_loader, "run_gcloud_list")
  def test_forwards_and_records_the_location(self, mock_list):
    mock_list.return_value = []

    store = db_resources_loader.fetch_and_filter_db_resources("123", "us-east1")

    self.assertEqual(store.location, "us-east1")
    self.assertEqual(
        [c.args for c in mock_list.call_args_list],
        [
            ("frameworks", "123", "us-east1"),
            ("cloud-controls", "123", "us-east1"),
        ],
    )

  @mock.patch.object(db_resources_loader, "run_gcloud_list")
  def test_gcloud_failure_propagates(self, mock_list):
    mock_list.side_effect = db_resources_loader.GcloudError("boom")

    with self.assertRaisesRegex(db_resources_loader.GcloudError, "boom"):
      db_resources_loader.fetch_and_filter_db_resources("123")


class LoadDBResourcesTest(unittest.TestCase):

  @mock.patch.object(db_resources_loader, "fetch_and_filter_db_resources")
  def test_uses_cache_unless_refresh_requested(self, mock_fetch):
    now = time.time()
    valid_store = db_resources_loader.DBResourcesStore(
        last_synced_epoch=now - 3600.0,
        organization_id="123",
        frameworks={"builtin-fw": {"type": "BUILT_IN"}},
        cloud_controls={"builtin-cc": {"type": "BUILT_IN"}},
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
      cache_path = os.path.join(tmp_dir, "db_resources_cache_123.json")
      # Write a valid cache
      pathlib.Path(cache_path).write_text(valid_store.to_json())

      loaded = db_resources_loader.load_db_resources(
          organization_id="123", cache_dir=tmp_dir, refresh_cache=False
      )
      self.assertEqual(loaded.frameworks, valid_store.frameworks)
      mock_fetch.assert_not_called()

      # Now force refresh
      mock_fetch.return_value = db_resources_loader.DBResourcesStore(
          last_synced_epoch=now,
          organization_id="123",
          frameworks={"builtin-fw2": {"type": "BUILT_IN"}},
          cloud_controls={"builtin-cc2": {"type": "BUILT_IN"}},
      )
      loaded2 = db_resources_loader.load_db_resources(
          organization_id="123", cache_dir=tmp_dir, refresh_cache=True
      )
      self.assertIn("builtin-fw2", loaded2.frameworks)
      mock_fetch.assert_called_once_with("123", "global")

  @mock.patch.object(db_resources_loader, "fetch_and_filter_db_resources")
  def test_incomplete_cache_is_refetched(self, mock_fetch):
    mock_fetch.return_value = db_resources_loader.DBResourcesStore(
        last_synced_epoch=time.time(),
        organization_id="123",
        frameworks={"builtin-fw": {}},
        cloud_controls={"builtin-cc": {}},
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
      incomplete = db_resources_loader.DBResourcesStore(
          last_synced_epoch=time.time(), organization_id="123"
      )
      pathlib.Path(tmp_dir, "db_resources_cache_123.json").write_text(
          incomplete.to_json()
      )

      loaded = db_resources_loader.load_db_resources("123", cache_dir=tmp_dir)

    self.assertIn("builtin-fw", loaded.frameworks)
    mock_fetch.assert_called_once_with("123", "global")

  @mock.patch.object(db_resources_loader, "fetch_and_filter_db_resources")
  def test_non_global_location_uses_its_own_cache_file(self, mock_fetch):
    mock_fetch.return_value = db_resources_loader.DBResourcesStore(
        last_synced_epoch=time.time(),
        organization_id="123",
        frameworks={"custom-fw": {}},
        cloud_controls={"custom-cc": {}},
        location="europe-west1",
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
      store = db_resources_loader.load_db_resources(
          "123", cache_dir=tmp_dir, location="europe-west1"
      )

      self.assertEqual(store.location, "europe-west1")
      self.assertEqual(
          os.listdir(tmp_dir), ["db_resources_cache_123_europe-west1.json"]
      )
      mock_fetch.assert_called_once_with("123", "europe-west1")

      # A second call is served from that file.
      again = db_resources_loader.load_db_resources(
          "123", cache_dir=tmp_dir, location="europe-west1"
      )
      self.assertEqual(again.location, "europe-west1")
      mock_fetch.assert_called_once()

  @mock.patch.object(db_resources_loader, "fetch_and_filter_db_resources")
  def test_cache_file_without_a_location_counts_as_global(self, mock_fetch):
    legacy = {
        "last_synced_epoch": 1.0,
        "organization_id": "123",
        "frameworks": {"fw": {}},
        "cloud_controls": {"cc": {}},
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
      pathlib.Path(tmp_dir, "db_resources_cache_123.json").write_text(
          json.dumps(legacy)
      )

      loaded = db_resources_loader.load_db_resources("123", cache_dir=tmp_dir)

    self.assertEqual(loaded.location, "global")
    self.assertIn("fw", loaded.frameworks)
    mock_fetch.assert_not_called()

  @mock.patch.object(db_resources_loader, "fetch_and_filter_db_resources")
  def test_cache_of_another_location_is_not_reused(self, mock_fetch):
    mock_fetch.return_value = db_resources_loader.DBResourcesStore(
        last_synced_epoch=time.time(),
        organization_id="123",
        frameworks={"fw-global": {}},
        cloud_controls={"cc-global": {}},
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
      # The file with the `global` name holds the catalog of another location.
      other = db_resources_loader.DBResourcesStore(
          last_synced_epoch=time.time(),
          organization_id="123",
          frameworks={"fw-us": {}},
          cloud_controls={"cc-us": {}},
          location="us",
      )
      pathlib.Path(tmp_dir, "db_resources_cache_123.json").write_text(
          other.to_json()
      )

      loaded = db_resources_loader.load_db_resources("123", cache_dir=tmp_dir)

    self.assertEqual(loaded.location, "global")
    self.assertIn("fw-global", loaded.frameworks)
    mock_fetch.assert_called_once_with("123", "global")

  @mock.patch.object(db_resources_loader.subprocess, "run")
  def test_fetches_through_gcloud_and_writes_cache(self, mock_run):
    mock_run.side_effect = _fake_gcloud

    with tempfile.TemporaryDirectory() as tmp_dir:
      store = db_resources_loader.load_db_resources(
          "organizations/123", cache_dir=tmp_dir
      )

      self.assertEqual(
          [c.args[0][2] for c in mock_run.call_args_list],
          ["frameworks", "cloud-controls"],
      )
      self.assertEqual(
          sorted(store.frameworks), ["builtin-fw-aw", "custom-fw-1"]
      )
      self.assertEqual(
          sorted(store.cloud_controls), ["builtin-cc-aw-1", "custom-cc-1"]
      )
      cache_file = pathlib.Path(tmp_dir, "db_resources_cache_123.json")
      self.assertTrue(cache_file.exists())

      # A second call is served from the cache without invoking gcloud.
      mock_run.reset_mock()
      again = db_resources_loader.load_db_resources("123", cache_dir=tmp_dir)
      mock_run.assert_not_called()
      self.assertEqual(again.frameworks, store.frameworks)

  @mock.patch.object(db_resources_loader.subprocess, "run")
  def test_invalid_organization_id_never_reaches_gcloud(self, mock_run):
    with tempfile.TemporaryDirectory() as tmp_dir:
      with self.assertRaises(ValueError):
        db_resources_loader.load_db_resources("../../x", cache_dir=tmp_dir)

    mock_run.assert_not_called()

  @mock.patch.object(db_resources_loader.subprocess, "run")
  def test_unknown_location_never_reaches_gcloud(self, mock_run):
    with tempfile.TemporaryDirectory() as tmp_dir:
      with self.assertRaisesRegex(ValueError, "Unknown location"):
        db_resources_loader.load_db_resources(
            "123", cache_dir=tmp_dir, location="prod-us-central1"
        )

    mock_run.assert_not_called()


class MainTest(unittest.TestCase):

  def _run_main(self, argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    with mock.patch.object(sys, "argv", ["db_resources_loader.py", *argv]):
      with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(
          stderr
      ):
        try:
          db_resources_loader.main()
          exit_code = 0
        except SystemExit as e:
          exit_code = e.code
    return exit_code, stdout.getvalue(), stderr.getvalue()

  @mock.patch.object(db_resources_loader.subprocess, "run")
  def test_writes_output_file(self, mock_run):
    mock_run.side_effect = _fake_gcloud

    with tempfile.TemporaryDirectory() as tmp_dir:
      out_path = os.path.join(tmp_dir, "out", "loaded.json")
      exit_code, stdout, _ = self._run_main([
          "-o",
          "123",
          "--output_path",
          out_path,
          "--cache_dir",
          os.path.join(tmp_dir, "cache"),
      ])

      self.assertEqual(exit_code, 0)
      self.assertIn("Successfully loaded and saved 2 frameworks", stdout)
      written = json.loads(pathlib.Path(out_path).read_text())
      self.assertEqual(written["organization_id"], "123")
      self.assertEqual(written["location"], "global")
      self.assertIn("builtin-fw-aw", written["frameworks"])
      self.assertIn("builtin-cc-aw-1", written["cloud_controls"])

  @mock.patch.object(db_resources_loader.subprocess, "run")
  def test_location_flag_selects_the_location(self, mock_run):
    mock_run.side_effect = _fake_gcloud

    with tempfile.TemporaryDirectory() as tmp_dir:
      out_path = os.path.join(tmp_dir, "loaded.json")
      exit_code, _, _ = self._run_main([
          "-o",
          "123",
          "--output_path",
          out_path,
          "--cache_dir",
          os.path.join(tmp_dir, "cache"),
          "--location",
          "us-east1",
      ])

      self.assertEqual(exit_code, 0)
      written = json.loads(pathlib.Path(out_path).read_text())
      self.assertEqual(written["location"], "us-east1")
      self.assertEqual(
          os.listdir(os.path.join(tmp_dir, "cache")),
          ["db_resources_cache_123_us-east1.json"],
      )

    self.assertEqual(mock_run.call_count, 2)
    for call in mock_run.call_args_list:
      self.assertIn("--location=us-east1", call.args[0])

  @mock.patch.object(db_resources_loader.subprocess, "run")
  def test_gcloud_failure_exits_nonzero_with_message(self, mock_run):
    mock_run.return_value = _completed(
        returncode=1, stderr="ERROR: (gcloud) API not enabled"
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
      out_path = os.path.join(tmp_dir, "loaded.json")
      exit_code, stdout, stderr = self._run_main([
          "-o",
          "123",
          "--output_path",
          out_path,
          "--cache_dir",
          tmp_dir,
      ])

      self.assertEqual(exit_code, 1)
      self.assertEqual(stdout, "")
      self.assertIn("ERROR: ", stderr)
      self.assertIn("API not enabled", stderr)
      self.assertNotIn("Traceback", stderr)
      self.assertFalse(os.path.exists(out_path))

  @mock.patch.object(db_resources_loader.subprocess, "run")
  def test_location_rejected_by_the_api_is_reported_by_name(self, mock_run):
    mock_run.return_value = _completed(
        returncode=1,
        stderr=(
            "ERROR: (gcloud.compliance-manager.frameworks.list)"
            " PERMISSION_DENIED: Location eu is not found or access is"
            " unauthorized.\n"
        ),
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
      out_path = os.path.join(tmp_dir, "loaded.json")
      exit_code, stdout, stderr = self._run_main([
          "-o",
          "123",
          "--output_path",
          out_path,
          "--cache_dir",
          tmp_dir,
          "--location",
          "eu",
      ])

      self.assertEqual(exit_code, 1)
      self.assertEqual(stdout, "")
      self.assertIn("Location eu is not found", stderr)
      self.assertNotIn("Traceback", stderr)
      # Neither an output file nor a cache file is left behind.
      self.assertEqual(os.listdir(tmp_dir), [])

  @mock.patch.object(db_resources_loader.subprocess, "run")
  def test_location_that_is_not_in_the_list_exits_nonzero(self, mock_run):
    with tempfile.TemporaryDirectory() as tmp_dir:
      exit_code, _, stderr = self._run_main([
          "-o",
          "123",
          "--output_path",
          os.path.join(tmp_dir, "loaded.json"),
          "--cache_dir",
          tmp_dir,
          "--location",
          "prod-us-central1",
      ])

    self.assertEqual(exit_code, 1)
    self.assertIn("Unknown location 'prod-us-central1'", stderr)
    self.assertNotIn("Traceback", stderr)
    mock_run.assert_not_called()

  @mock.patch.object(db_resources_loader.subprocess, "run")
  def test_invalid_organization_id_exits_nonzero(self, mock_run):
    with tempfile.TemporaryDirectory() as tmp_dir:
      exit_code, _, stderr = self._run_main([
          "-o",
          "not-an-org",
          "--output_path",
          os.path.join(tmp_dir, "loaded.json"),
          "--cache_dir",
          tmp_dir,
      ])

    self.assertEqual(exit_code, 1)
    self.assertIn("Invalid organization ID", stderr)
    mock_run.assert_not_called()


if __name__ == "__main__":
  unittest.main()
