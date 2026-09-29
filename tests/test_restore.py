"""
Unit tests for file restoration and overwrite protection.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from config import Config
from recovery import RecoveryEngine


class TestFileRestore(unittest.TestCase):
    """Test suite for recovering files and enforcing overwrite safety."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.config = Config()
        self.recovery_engine = RecoveryEngine(self.test_dir, self.config)
        self.backup_engine = self.recovery_engine.backup_engine

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_restore_deleted_file(self):
        """Restores a deleted file to its exact original location and content."""
        code_file = self.test_dir / "models" / "user.py"
        code_file.parent.mkdir(parents=True, exist_ok=True)
        code_file.write_text("class User:\n    pass\n", encoding="utf-8")

        # Create snapshot
        self.backup_engine.create_snapshot(code_file)

        # Simulate accidental deletion
        code_file.unlink()
        self.assertFalse(code_file.exists())

        # Restore file
        success = self.recovery_engine.restore_file(code_file, force=True, interactive=False)
        self.assertTrue(success)
        self.assertTrue(code_file.exists())
        self.assertEqual(code_file.read_text(encoding="utf-8"), "class User:\n    pass\n")

    def test_restore_specific_version_by_id(self):
        """Restores a specific earlier version selected by its snapshot ID."""
        code_file = self.test_dir / "index.js"
        
        # Version 1
        code_file.write_text("const version = 1;", encoding="utf-8")
        snap1 = self.backup_engine.create_snapshot(code_file)

        # Version 2
        code_file.write_text("const version = 2;", encoding="utf-8")
        snap2 = self.backup_engine.create_snapshot(code_file)

        # Restore Version 1 specifically
        success = self.recovery_engine.restore_file(
            code_file,
            snapshot_id=snap1["id"],
            force=True,
            interactive=False
        )
        self.assertTrue(success)
        self.assertEqual(code_file.read_text(encoding="utf-8"), "const version = 1;")

    def test_overwrite_protection_requires_confirmation(self):
        """Existing file must not be overwritten if force is False and non-interactive."""
        code_file = self.test_dir / "config.py"
        code_file.write_text("DEBUG = False", encoding="utf-8")
        snap1 = self.backup_engine.create_snapshot(code_file)

        # Change file on disk
        code_file.write_text("DEBUG = True # Unsaved changes", encoding="utf-8")

        # Attempt restore without force in non-interactive mode
        success = self.recovery_engine.restore_file(
            code_file,
            snapshot_id=snap1["id"],
            force=False,
            interactive=False
        )
        self.assertFalse(success, "Should refuse to overwrite without explicit confirmation")
        # Ensure disk file was NOT overwritten
        self.assertEqual(code_file.read_text(encoding="utf-8"), "DEBUG = True # Unsaved changes")

    def test_restore_recreates_missing_parent_directories(self):
        """If the parent directory tree was also deleted, restore recreates it."""
        nested_file = self.test_dir / "deep" / "nested" / "path" / "app.py"
        nested_file.parent.mkdir(parents=True, exist_ok=True)
        nested_file.write_text("print('nested')", encoding="utf-8")

        self.backup_engine.create_snapshot(nested_file)

        # Delete entire tree
        shutil.rmtree(self.test_dir / "deep")
        self.assertFalse(nested_file.exists())

        # Restore
        success = self.recovery_engine.restore_file(nested_file, force=True, interactive=False)
        self.assertTrue(success)
        self.assertTrue(nested_file.exists())
    def test_interactive_menu_selection_by_number(self):
        """User can select snapshot by menu number (e.g. 1) instead of ID and confirm with 'y'."""
        from unittest.mock import patch

        code_file = self.test_dir / "app.py"
        code_file.write_text("v1_code", encoding="utf-8")
        self.backup_engine.create_snapshot(code_file)

        code_file.write_text("v2_code", encoding="utf-8")
        self.backup_engine.create_snapshot(code_file)

        # File on disk currently has v2_code. User selects menu item '1' and confirms with 'y'
        with patch("builtins.input", side_effect=["1", "y"]):
            success = self.recovery_engine.restore_file(code_file, interactive=True)

        self.assertTrue(success)
        self.assertEqual(code_file.read_text(encoding="utf-8"), "v1_code")

    def test_interactive_menu_cancelled_by_zero(self):
        """Entering '0' in the interactive menu cleanly aborts restoration."""
        from unittest.mock import patch

        code_file = self.test_dir / "app.py"
        code_file.write_text("original", encoding="utf-8")
        self.backup_engine.create_snapshot(code_file)

        with patch("builtins.input", side_effect=["0"]):
            success = self.recovery_engine.restore_file(code_file, interactive=True)

        self.assertFalse(success)
        self.assertEqual(code_file.read_text(encoding="utf-8"), "original")

    def test_interactive_confirmation_denied(self):
        """Selecting a snapshot but entering 'n' at confirmation cancels without modifying file."""
        from unittest.mock import patch

        code_file = self.test_dir / "app.py"
        code_file.write_text("version_1", encoding="utf-8")
        self.backup_engine.create_snapshot(code_file)

        code_file.write_text("version_current", encoding="utf-8")

        # Select menu item 1, but reject confirmation with 'n'
        with patch("builtins.input", side_effect=["1", "n"]):
            success = self.recovery_engine.restore_file(code_file, interactive=True)

        self.assertFalse(success)
    def test_recover_wizard_full_flow(self):
        """Test recover_file_wizard displays headers, table, warning and restores on 'y'."""
        import io
        from contextlib import redirect_stdout
        from unittest.mock import patch

        code_file = self.test_dir / "target.py"
        code_file.write_text("v1_target", encoding="utf-8")
        self.backup_engine.create_snapshot(code_file)

        code_file.write_text("v2_target", encoding="utf-8")
        self.backup_engine.create_snapshot(code_file)

        # File exists on disk (ACTIVE). User selects '1' and confirms with 'y'
        buf = io.StringIO()
        with redirect_stdout(buf), patch("builtins.input", side_effect=["1", "y"]):
            success = self.recovery_engine.recover_file_wizard(code_file)

        output = buf.getvalue()
        self.assertTrue(success)
        self.assertIn("CODE LIFEJACKET - RECOVERY", output)
        self.assertIn("Status:     ACTIVE", output)
        self.assertIn("Selection | ID", output)
        self.assertIn("Timestamp", output)
        self.assertIn("SHA-256", output)
        self.assertIn("[WARNING] Current file exists and will be OVERWRITTEN!", output)
        self.assertEqual(code_file.read_text(encoding="utf-8"), "v1_target")

    def test_recover_wizard_deleted_file(self):
        """Test recover_file_wizard correctly detects DELETED / MISSING status."""
        import io
        from contextlib import redirect_stdout
        from unittest.mock import patch

        code_file = self.test_dir / "missing.py"
        code_file.write_text("precious_code", encoding="utf-8")
        self.backup_engine.create_snapshot(code_file)

        code_file.unlink()

        buf = io.StringIO()
        with redirect_stdout(buf), patch("builtins.input", side_effect=["1", "y"]):
            success = self.recovery_engine.recover_file_wizard(code_file)

        output = buf.getvalue()
        self.assertTrue(success)
        self.assertIn("Status:     DELETED / MISSING", output)
        self.assertTrue(code_file.exists())
        self.assertEqual(code_file.read_text(encoding="utf-8"), "precious_code")

    def test_recover_wizard_invalid_input_recovery(self):
        """Test recover_file_wizard reprompts on invalid input without crashing and allows cancel."""
        from unittest.mock import patch

        code_file = self.test_dir / "sample.py"
        code_file.write_text("sample", encoding="utf-8")
        self.backup_engine.create_snapshot(code_file)

        # User enters bad input first ('foo', '99'), then cancels ('0')
        with patch("builtins.input", side_effect=["foo", "99", "0"]):
            success = self.recovery_engine.recover_file_wizard(code_file)

        self.assertFalse(success)

    def test_recover_wizard_ctrl_c_handled(self):
        """Test recover_file_wizard handles KeyboardInterrupt cleanly."""
        from unittest.mock import patch

        code_file = self.test_dir / "sample.py"
        code_file.write_text("sample", encoding="utf-8")
        self.backup_engine.create_snapshot(code_file)

        with patch("builtins.input", side_effect=KeyboardInterrupt):
            success = self.recovery_engine.recover_file_wizard(code_file)

        self.assertFalse(success)


if __name__ == "__main__":
    unittest.main()

