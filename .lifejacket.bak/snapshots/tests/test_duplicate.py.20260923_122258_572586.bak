"""
Unit tests for duplicate detection and SHA-256 hashing.
"""

import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from backup import BackupEngine
from config import Config


class TestDuplicateDetection(unittest.TestCase):
    """Test suite for duplicate prevention using SHA-256 content hashes."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.config = Config()
        self.backup_engine = BackupEngine(self.test_dir, self.config)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_identical_content_skips_snapshot(self):
        """Saving identical content should NOT create redundant snapshots."""
        sample_code = "def add(a, b):\n    return a + b\n"
        file_path = self.test_dir / "math_ops.py"
        file_path.write_text(sample_code, encoding="utf-8")

        # 1. First save creates snapshot
        snap1 = self.backup_engine.create_snapshot(file_path)
        self.assertIsNotNone(snap1)

        # 2. Saving the exact same content again
        snap2 = self.backup_engine.create_snapshot(file_path)
        self.assertIsNone(snap2, "Duplicate content should return None (snapshot skipped)")

        # Verify only 1 snapshot exists in database
        snapshots = self.backup_engine.db.get_snapshots_for_file("math_ops.py")
        self.assertEqual(len(snapshots), 1)

    def test_modified_content_triggers_new_snapshot(self):
        """Modifying the content must create a new snapshot."""
        file_path = self.test_dir / "service.go"
        file_path.write_text("package main\n\nfunc Run() {}\n", encoding="utf-8")
        snap1 = self.backup_engine.create_snapshot(file_path)
        self.assertIsNotNone(snap1)

        # Modify content
        file_path.write_text("package main\n\nfunc Run() { println('v2') }\n", encoding="utf-8")
        snap2 = self.backup_engine.create_snapshot(file_path)
        self.assertIsNotNone(snap2)

        # Hashes should be different
        self.assertNotEqual(snap1["hash"], snap2["hash"])

        snapshots = self.backup_engine.db.get_snapshots_for_file("service.go")
        self.assertEqual(len(snapshots), 2)

    def test_sha256_hash_validity(self):
        """Verify the recorded hash matches the real SHA-256 digest."""
        content = b"const PORT = 3000;\nconsole.log(PORT);"
        file_path = self.test_dir / "server.ts"
        file_path.write_bytes(content)

        expected_hash = hashlib.sha256(content).hexdigest()
        snap = self.backup_engine.create_snapshot(file_path)

        self.assertIsNotNone(snap)
        self.assertEqual(snap["hash"], expected_hash)


if __name__ == "__main__":
    unittest.main()
