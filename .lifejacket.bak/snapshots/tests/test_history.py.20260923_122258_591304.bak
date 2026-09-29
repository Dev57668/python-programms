"""
Unit tests for history retrieval and metadata querying.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from config import Config
from recovery import RecoveryEngine


class TestHistoryRetrieval(unittest.TestCase):
    """Test suite for querying snapshot histories and metadata."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.config = Config()
        self.recovery_engine = RecoveryEngine(self.test_dir, self.config)
        self.backup_engine = self.recovery_engine.backup_engine

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_empty_history_for_new_file(self):
        """Unbacked files should have empty history."""
        untracked = self.test_dir / "ghost.py"
        history = self.recovery_engine.get_file_history(untracked)
        self.assertEqual(history, [])

    def test_chronological_history_records(self):
        """History should contain all versions in order with correct metadata."""
        code_file = self.test_dir / "algorithm.cpp"

        # Version 1
        code_file.write_text("int v = 1;", encoding="utf-8")
        snap1 = self.backup_engine.create_snapshot(code_file)

        # Version 2
        code_file.write_text("int v = 2; // updated", encoding="utf-8")
        snap2 = self.backup_engine.create_snapshot(code_file)

        # Version 3
        code_file.write_text("int v = 3; // final", encoding="utf-8")
        snap3 = self.backup_engine.create_snapshot(code_file)

        history = self.recovery_engine.get_file_history(code_file)
        self.assertEqual(len(history), 3)

        self.assertEqual(history[0]["id"], snap1["id"])
        self.assertEqual(history[1]["id"], snap2["id"])
        self.assertEqual(history[2]["id"], snap3["id"])

        self.assertEqual(history[0]["relative_path"], "algorithm.cpp")
        self.assertGreater(history[1]["size"], history[0]["size"])

    def test_multiple_files_history(self):
        """Multiple files should maintain independent history records."""
        file_a = self.test_dir / "a.rs"
        file_b = self.test_dir / "b.rs"

        file_a.write_text("fn a() {}", encoding="utf-8")
        self.backup_engine.create_snapshot(file_a)

        file_b.write_text("fn b1() {}", encoding="utf-8")
        self.backup_engine.create_snapshot(file_b)
        file_b.write_text("fn b2() {}", encoding="utf-8")
        self.backup_engine.create_snapshot(file_b)

        history_a = self.recovery_engine.get_file_history(file_a)
        history_b = self.recovery_engine.get_file_history(file_b)

        self.assertEqual(len(history_a), 1)
        self.assertEqual(len(history_b), 2)


if __name__ == "__main__":
    unittest.main()
