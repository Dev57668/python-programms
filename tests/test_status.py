"""
Unit tests for status calculations and dashboard reporting.
"""

import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from backup import BackupEngine
from config import Config
from recovery import RecoveryEngine


class TestStatusDashboard(unittest.TestCase):
    """Test suite for repository protection status calculations."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.config = Config()
        self.recovery_engine = RecoveryEngine(self.test_dir, self.config)
        self.backup_engine = self.recovery_engine.backup_engine

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_empty_project_status(self):
        """Empty project should calculate clean 0s without crashing."""
        data = self.recovery_engine.get_status_data()

        self.assertFalse(data["is_active"])
        self.assertEqual(data["protection_status"], "○ INACTIVE")
        self.assertEqual(data["protected_files_count"], 0)
        self.assertEqual(data["total_snapshots_count"], 0)
        self.assertEqual(data["deleted_files_count"], 0)
        self.assertEqual(data["last_snapshot"], "None")
        self.assertEqual(data["file_activity"], [])
        self.assertEqual(data["total_backup_size_bytes"], 0)

        # Ensure print_status does not crash on empty project
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.recovery_engine.print_status()
        output = buf.getvalue()
        self.assertIn("CODE LIFEJACKET - STATUS", output)
        self.assertIn("INACTIVE", output)
        self.assertIn("No tracked files yet.", output)

    def test_protected_files_and_snapshots_counts(self):
        """Correctly tallies active files and total snapshot counts."""
        file_a = self.test_dir / "alpha.py"
        file_b = self.test_dir / "beta.py"

        file_a.write_text("print('alpha')", encoding="utf-8")
        self.backup_engine.create_snapshot(file_a)

        file_b.write_text("print('beta 1')", encoding="utf-8")
        self.backup_engine.create_snapshot(file_b)

        file_b.write_text("print('beta 2')", encoding="utf-8")
        snap_b2 = self.backup_engine.create_snapshot(file_b)

        data = self.recovery_engine.get_status_data()

        self.assertTrue(data["is_active"])
        self.assertEqual(data["protection_status"], "● ACTIVE")
        self.assertEqual(data["protected_files_count"], 2)
        self.assertEqual(data["total_snapshots_count"], 3)
        self.assertEqual(data["deleted_files_count"], 0)
        self.assertEqual(data["last_snapshot"], snap_b2["timestamp"])
        self.assertGreater(data["total_backup_size_bytes"], 0)

    def test_deleted_file_detection(self):
        """Detects missing/deleted tracked files and marks status appropriately."""
        file_victim = self.test_dir / "victim.py"
        file_survivor = self.test_dir / "survivor.py"

        file_victim.write_text("victim code", encoding="utf-8")
        self.backup_engine.create_snapshot(file_victim)

        file_survivor.write_text("survivor code", encoding="utf-8")
        self.backup_engine.create_snapshot(file_survivor)

        # Delete victim file
        file_victim.unlink()
        self.backup_engine.handle_deletion(file_victim)

        data = self.recovery_engine.get_status_data()

        self.assertEqual(data["protected_files_count"], 1)
        self.assertEqual(data["deleted_files_count"], 1)

        # Check file activity records
        activity_map = {item["file"]: item for item in data["file_activity"]}
        self.assertEqual(activity_map["victim.py"]["status"], "DELETED")
        self.assertEqual(activity_map["victim.py"]["snapshots"], 1)
        self.assertEqual(activity_map["survivor.py"]["status"], "ACTIVE")
        self.assertEqual(activity_map["survivor.py"]["snapshots"], 1)

    def test_missing_database_graceful(self):
        """If database file is deleted or corrupt, status calculation handles it gracefully."""
        db_file = self.recovery_engine.db.db_path
        if db_file.exists():
            db_file.unlink()

        # Re-initialize recovery engine on directory without database
        fresh_engine = RecoveryEngine(self.test_dir, self.config)
        data = fresh_engine.get_status_data()

        self.assertEqual(data["protected_files_count"], 0)
        self.assertEqual(data["total_snapshots_count"], 0)
        self.assertEqual(data["deleted_files_count"], 0)

    def test_ignored_directories_not_scanned(self):
        """Ignored directories (.git, node_modules, venv) must not appear in status."""
        git_dir = self.test_dir / ".git"
        git_dir.mkdir(parents=True, exist_ok=True)
        (git_dir / "config.py").write_text("# git", encoding="utf-8")

        venv_dir = self.test_dir / ".venv"
        venv_dir.mkdir(parents=True, exist_ok=True)
        (venv_dir / "site.py").write_text("# venv", encoding="utf-8")

        data = self.recovery_engine.get_status_data()
        activity_files = [item["file"] for item in data["file_activity"]]

        self.assertNotIn(".git/config.py", activity_files)
        self.assertNotIn(".venv/site.py", activity_files)

    def test_dashboard_output_layout(self):
        """Verify the printed status dashboard contains all required sections."""
        code_file = self.test_dir / "service.py"
        code_file.write_text("service code", encoding="utf-8")
        self.backup_engine.create_snapshot(code_file)

        buf = io.StringIO()
        with redirect_stdout(buf):
            self.recovery_engine.print_status()

        output = buf.getvalue()
        self.assertIn("CODE LIFEJACKET - STATUS", output)
        self.assertIn("Project:", output)
        self.assertIn("Protection:", output)
        self.assertIn("ACTIVE", output)
        self.assertIn("Protected Files:", output)
        self.assertIn("Total Snapshots:", output)
        self.assertIn("Deleted Files:", output)
        self.assertIn("Total Backup Size:", output)
        self.assertIn("Last Snapshot:", output)
        self.assertIn("FILE ACTIVITY", output)
        self.assertIn("STORAGE", output)
        self.assertIn("Lifejacket Directory:", output)
        self.assertIn("Maximum Snapshots:", output)
        self.assertIn("service.py", output)


if __name__ == "__main__":
    unittest.main()
