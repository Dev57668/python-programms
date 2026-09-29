"""
End-to-End CLI tests for Code Lifejacket.
Spawns subprocesses to verify CLI commands work exactly as expected from the shell.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TestCLIEndToEnd(unittest.TestCase):
    """Verifies all main.py subcommands via real subprocess execution."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.main_script = Path(__file__).resolve().parent.parent / "main.py"
        # Create a sample source file in sandbox
        self.sample_file = self.test_dir / "calculator.py"
        self.sample_file.write_text("def add(x, y):\n    return x + y\n", encoding="utf-8")

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _run_cli(self, *args):
        """Helper to run python main.py <args> in the test environment."""
        cmd = [sys.executable, str(self.main_script)] + list(args)
        result = subprocess.run(
            cmd,
            cwd=str(self.test_dir),
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
        return result

    def test_status_command(self):
        """Verify python main.py status works on project dir."""
        result = self._run_cli("status", str(self.test_dir))
        self.assertEqual(result.returncode, 0)
        self.assertIn("CODE LIFEJACKET - STATUS", result.stdout)

    def test_full_recovery_flow(self):
        """Simulate initial backup, modification, accidental deletion, and restore."""
        from backup import BackupEngine
        from config import Config

        cfg = Config()
        engine = BackupEngine(self.test_dir, cfg)
        
        # 1. Create initial snapshot
        engine.create_snapshot(self.sample_file)

        # 2. Modify file and create 2nd snapshot
        self.sample_file.write_text("def add(x, y):\n    # v2\n    return x + y\n", encoding="utf-8")
        engine.create_snapshot(self.sample_file)

        # 3. Check history CLI
        hist_result = self._run_cli("history", str(self.sample_file))
        self.assertEqual(hist_result.returncode, 0)
        self.assertIn("calculator.py", hist_result.stdout)
        self.assertIn("2 version(s) available", hist_result.stdout)

        # 4. Check snapshots CLI
        snaps_result = self._run_cli("snapshots", str(self.test_dir))
        self.assertEqual(snaps_result.returncode, 0)
        self.assertIn("calculator.py", snaps_result.stdout)

        # 5. Simulate accidental deletion!
        self.sample_file.unlink()
        engine.handle_deletion(self.sample_file)
        self.assertFalse(self.sample_file.exists())

        # Verify status shows deleted
        status_result = self._run_cli("status", str(self.test_dir))
        self.assertIn("DELETED", status_result.stdout)

        # 6. Restore the file with CLI --yes
        restore_result = self._run_cli("restore", str(self.sample_file), "--yes")
        self.assertEqual(restore_result.returncode, 0)
        self.assertIn("[Success] Restored 'calculator.py'", restore_result.stdout)
        self.assertTrue(self.sample_file.exists())
        self.assertIn("# v2", self.sample_file.read_text(encoding="utf-8"))

        # 7. Clean CLI
        clean_result = self._run_cli("clean", str(self.test_dir), "--yes")
        self.assertEqual(clean_result.returncode, 0)
        self.assertIn("Cleaned all snapshots", clean_result.stdout)

    def test_recover_command_cli(self):
        """Verify python main.py recover <file> interactive command via CLI subprocess."""
        from backup import BackupEngine
        from config import Config

        cfg = Config()
        engine = BackupEngine(self.test_dir, cfg)
        engine.create_snapshot(self.sample_file)

        # Modify and create snapshot 2
        self.sample_file.write_text("def add(x, y):\n    # v2\n    return x + y\n", encoding="utf-8")
        engine.create_snapshot(self.sample_file)

        # Delete file
        self.sample_file.unlink()
        self.assertFalse(self.sample_file.exists())

        # Run python main.py recover calculator.py with simulated inputs:
        # "1" (select item 1), then "y" (confirm restoration)
        cmd = [sys.executable, str(self.main_script), "recover", str(self.sample_file)]
        proc = subprocess.run(
            cmd,
            cwd=str(self.test_dir),
            input="1\ny\n",
            capture_output=True,
            text=True,
            encoding="utf-8"
        )

        self.assertEqual(proc.returncode, 0)
        self.assertIn("CODE LIFEJACKET - RECOVERY", proc.stdout)
        self.assertIn("Status:     DELETED / MISSING", proc.stdout)
        self.assertIn("Selection", proc.stdout)
        self.assertIn("Proceed with restoration? (y/N):", proc.stdout)
        self.assertIn("[Success] Restored 'calculator.py'", proc.stdout)
        self.assertTrue(self.sample_file.exists())


if __name__ == "__main__":
    unittest.main()

