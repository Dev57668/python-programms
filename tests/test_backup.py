"""
Unit tests for snapshot creation and backup functionality.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from backup import BackupEngine
from config import Config


class TestBackupEngine(unittest.TestCase):
    """Test suite for snapshot creation, relative paths, and pruning."""

    def setUp(self):
        # Create isolated temporary directory for testing
        self.test_dir = Path(tempfile.mkdtemp())
        self.config = Config()
        self.config.snapshot_directory_name = ".lifejacket"
        self.config.max_snapshots = 3
        self.backup_engine = BackupEngine(self.test_dir, self.config)

    def tearDown(self):
        # Clean up temporary test files
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_snapshot_creation(self):
        """Verify snapshot is created preserving nested relative folder structure."""
        src_dir = self.test_dir / "src" / "components"
        src_dir.mkdir(parents=True, exist_ok=True)
        code_file = src_dir / "app.py"
        code_file.write_text("print('version 1')", encoding="utf-8")

        record = self.backup_engine.create_snapshot(code_file, event_type="created")

        self.assertIsNotNone(record)
        self.assertEqual(record["relative_path"], "src/components/app.py")
        self.assertEqual(record["event_type"], "created")

        # Verify physical snapshot file exists
        snapshot_file = self.test_dir / record["snapshot_path"]
        self.assertTrue(snapshot_file.exists())
        self.assertEqual(snapshot_file.read_text(encoding="utf-8"), "print('version 1')")

    def test_unmonitored_extension_skipped(self):
        """Files with unmonitored extensions (e.g. .txt, .md) should be skipped."""
        doc_file = self.test_dir / "notes.txt"
        doc_file.write_text("plain text", encoding="utf-8")

        record = self.backup_engine.create_snapshot(doc_file)
        self.assertIsNone(record)

    def test_ignored_directory_skipped(self):
        """Files inside ignored directories (.git, node_modules) should be skipped."""
        git_dir = self.test_dir / ".git"
        git_dir.mkdir()
        git_file = git_dir / "hook.py"
        git_file.write_text("# git hook", encoding="utf-8")

        record = self.backup_engine.create_snapshot(git_file)
        self.assertIsNone(record)

    def test_max_snapshots_retention_pruning(self):
        """Oldest snapshots should be pruned when count exceeds max_snapshots."""
        code_file = self.test_dir / "counter.py"

        # Create 4 distinct versions (max_snapshots is set to 3)
        for i in range(1, 5):
            code_file.write_text(f"count = {i}\n", encoding="utf-8")
            self.backup_engine.create_snapshot(code_file)

        snapshots = self.backup_engine.db.get_snapshots_for_file("counter.py")
        self.assertEqual(len(snapshots), 3)

        # Ensure oldest (count = 1) was pruned and latest remains
        remaining_hashes = [s["hash"] for s in snapshots]
        latest_file = self.test_dir / snapshots[-1]["snapshot_path"]
        self.assertEqual(latest_file.read_text(encoding="utf-8"), "count = 4\n")


if __name__ == "__main__":
    unittest.main()
