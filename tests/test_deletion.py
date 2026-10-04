"""
Unit tests for deletion detection and snapshot preservation.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from codevault.config import Config
from codevault.recovery import RecoveryEngine


class TestDeletionProtection(unittest.TestCase):
    """Test suite for detecting deletions and safeguarding snapshot archives."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.config = Config()
        self.recovery_engine = RecoveryEngine(self.test_dir, self.config)
        self.backup_engine = self.recovery_engine.backup_engine

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_deletion_recorded_in_metadata(self):
        """Deleting a tracked file must record a deletion incident."""
        source_file = self.test_dir / "worker.go"
        source_file.write_text("package main\n", encoding="utf-8")
        snap = self.backup_engine.create_snapshot(source_file)

        # Simulate deletion
        source_file.unlink()
        del_record = self.backup_engine.handle_deletion(source_file)

        self.assertIsNotNone(del_record)
        self.assertEqual(del_record["relative_path"], "worker.go")
        self.assertEqual(del_record["last_known_hash"], snap["hash"])

        # Check database status
        tracked = self.backup_engine.db.get_tracked_files()
        self.assertEqual(tracked["worker.go"]["status"], "deleted")

        deletions = self.backup_engine.db.get_deletions()
        self.assertEqual(len(deletions), 1)

    def test_snapshots_preserved_after_deletion(self):
        """When source file is deleted, all past snapshots must remain intact."""
        source_file = self.test_dir / "App.java"
        source_file.write_text("public class App {}", encoding="utf-8")
        snap = self.backup_engine.create_snapshot(source_file)

        # Delete source file
        source_file.unlink()
        self.backup_engine.handle_deletion(source_file)

        # Snapshot file MUST still exist
        snapshot_file = self.test_dir / snap["snapshot_path"]
        self.assertTrue(
            snapshot_file.exists(),
            "Snapshot file must remain intact even if original source was deleted!"
        )
        self.assertEqual(snapshot_file.read_text(encoding="utf-8"), "public class App {}")

    def test_untracked_deletion_safely_ignored(self):
        """Deleting a non-monitored or unbacked file should not create records."""
        random_file = self.test_dir / "notes.txt"
        del_record = self.backup_engine.handle_deletion(random_file)
        self.assertIsNone(del_record)


if __name__ == "__main__":
    unittest.main()
