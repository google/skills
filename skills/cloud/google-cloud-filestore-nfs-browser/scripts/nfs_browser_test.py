"""Unit tests for Filestore NFS File Browser CLI and companion modules."""

import io
import os
import sys
import unittest
from unittest import mock

# Add scripts directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import formatters
import jump_host_engine
import nfs_browser


class FormattersTest(unittest.TestCase):

  def test_format_size_bytes(self):
    self.assertEqual(formatters.format_size(500), "500 B")
    self.assertEqual(formatters.format_size(1024), "1.0 KB")
    self.assertEqual(formatters.format_size(1024 * 1024), "1.0 MB")
    self.assertEqual(formatters.format_size(1024 * 1024 * 1024), "1.0 GB")

  def test_format_tree_output_human(self):
    res = {
        "path": "/logs",
        "entries": [
            {"name": "sub", "type": "dir", "path": "/logs/sub"},
            {"name": "app.log", "type": "file", "size_bytes": 2048},
        ],
    }
    with mock.patch("sys.stdout", new_callable=io.StringIO) as fake_out:
      formatters.format_tree_output(res, "/logs", as_json=False)
      output = fake_out.getvalue()
      self.assertIn("Filestore Directory Tree: /logs", output)
      self.assertIn("📁 sub/", output)
      self.assertIn("📄 app.log", output)
      self.assertIn("Total entries listed: 2", output)

  def test_format_search_output(self):
    res = {
        "matches": [
            {"file": "/logs/err.log", "line": 42, "content": "Fatal OOM"}
        ]
    }
    with mock.patch("sys.stdout", new_callable=io.StringIO) as fake_out:
      formatters.format_search_output(res, as_json=False)
      output = fake_out.getvalue()
      self.assertIn("Search Results (1 matches)", output)
      self.assertIn("/logs/err.log:42 -> Fatal OOM", output)

  def test_format_read_output_text(self):
    res = {
        "file": "/logs/app.log",
        "start_line": 1,
        "end_line": 2,
        "total_lines": 10,
        "content": "line1\nline2",
        "is_binary": False,
    }
    with mock.patch("sys.stdout", new_callable=io.StringIO) as fake_out:
      formatters.format_read_output(res, as_json=False)
      output = fake_out.getvalue()
      self.assertIn("Content of /logs/app.log (Lines 1-2 of 10)", output)
      self.assertIn("line1\nline2", output)

  def test_format_read_output_binary(self):
    res = {
        "file": "/backups/db.tar.gz",
        "size_bytes": 1048576,
        "is_binary": True,
    }
    with mock.patch("sys.stdout", new_callable=io.StringIO) as fake_out:
      formatters.format_read_output(res, as_json=False)
      output = fake_out.getvalue()
      self.assertIn("Binary File: /backups/db.tar.gz", output)
      self.assertIn("Raw content suppressed", output)

  def test_format_stat_output(self):
    res = {
        "path": "/data",
        "size_bytes": 4096,
        "mode": "0755",
        "is_dir": True,
        "uid": 1000,
        "gid": 1000,
        "mtime": 1700000000,
    }
    with mock.patch("sys.stdout", new_callable=io.StringIO) as fake_out:
      formatters.format_stat_output(res, as_json=False)
      output = fake_out.getvalue()
      self.assertIn("Metadata for /data", output)
      self.assertIn("Type:        Directory", output)
      self.assertIn("Permissions: 0755", output)


class HTTPBridgeEngineTest(unittest.TestCase):

  @mock.patch.object(nfs_browser.HTTPBridgeEngine, "_call")
  def test_bridge_tree(self, mock_call):
    mock_call.return_value = {"entries": []}
    engine = nfs_browser.HTTPBridgeEngine("https://bridge-service-url")
    res = engine.tree("/logs", depth=2, max_entries=50)
    mock_call.assert_called_once_with(
        "/api/v1/tree", {"path": "/logs", "depth": 2, "max_entries": 50}
    )
    self.assertEqual(res, {"entries": []})

  @mock.patch.object(nfs_browser.HTTPBridgeEngine, "_call")
  def test_bridge_read_slice(self, mock_call):
    mock_call.return_value = {"content": "data"}
    engine = nfs_browser.HTTPBridgeEngine("https://bridge-service-url")
    engine.read("/file.txt", head=None, tail=None, lines="10:20")
    mock_call.assert_called_once_with(
        "/api/v1/read",
        {
            "path": "/file.txt",
            "head": None,
            "tail": None,
            "start_line": 10,
            "end_line": 20,
        },
    )


class SSHJumpHostEngineTest(unittest.TestCase):

  @mock.patch.object(jump_host_engine.SSHJumpHostEngine, "_exec")
  def test_jump_host_tree(self, mock_exec):
    mock_exec.return_value = {"entries": []}
    engine = jump_host_engine.SSHJumpHostEngine(
        project="proj", zone="zone-a", vm="jump-vm", mount_point="/mnt/share"
    )
    res = engine.tree("/backups", depth=1, max_entries=100)
    mock_exec.assert_called_once()
    self.assertEqual(res, {"entries": []})

  @mock.patch.object(jump_host_engine.SSHJumpHostEngine, "_exec")
  def test_jump_host_stat(self, mock_exec):
    mock_exec.return_value = {"size_bytes": 100}
    engine = jump_host_engine.SSHJumpHostEngine(
        project="proj", zone="zone-a", vm="jump-vm"
    )
    res = engine.stat("/backups/file.tar.gz")
    mock_exec.assert_called_once()
    self.assertEqual(res, {"size_bytes": 100})


class CLITest(unittest.TestCase):

  def test_attribution_constants(self):
    self.assertEqual(
        nfs_browser.USER_AGENT,
        "agent-skills/1.0 (skill:google-cloud-filestore-nfs-browser)",
    )
    self.assertEqual(
        jump_host_engine.METRICS_ENV,
        "agent-skills/1.0 (skill:google-cloud-filestore-nfs-browser)",
    )
    self.assertEqual(
        jump_host_engine._load_attribution(fallback="UNUSED"),
        "agent-skills/1.0 (skill:google-cloud-filestore-nfs-browser)",
    )
    self.assertEqual(
        jump_host_engine._load_attribution(
            fallback="fallback-token", attr_path="/nonexistent/attribution.md"
        ),
        "fallback-token",
    )

  @mock.patch("nfs_browser.HTTPBridgeEngine.tree")
  def test_cli_tree_with_bridge(self, mock_tree):
    mock_tree.return_value = {"entries": [], "path": "/"}
    test_args = [
        "nfs_browser.py",
        "tree",
        "--bridge-url=https://bridge.run.app",
        "--path=/",
        "--depth=1",
    ]
    with mock.patch.object(sys, "argv", test_args):
      with mock.patch("sys.stdout", new_callable=io.StringIO):
        nfs_browser.main()
    mock_tree.assert_called_once_with("/", 1, 100)


if __name__ == "__main__":
  unittest.main()
