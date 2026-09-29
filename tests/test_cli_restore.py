import subprocess
import pytest
import sys
from pathlib import Path

def test_cli_restore(tmp_path):
    # Setup project directory
    project_dir = tmp_path / "my_project"
    project_dir.mkdir()
    
    # Create test file
    src = project_dir / "cli_test.py"
    src.write_text("v1", encoding="utf-8")
    
    # Create snapshot using Python API to set up
    from config import Config
    from backup import BackupEngine
    cfg = Config()
    engine = BackupEngine(project_dir, cfg)
    s1 = engine.create_snapshot(src)
    
    src.write_text("v2", encoding="utf-8")
    s2 = engine.create_snapshot(src)
    
    # Test restore command
    result = subprocess.run(
        [sys.executable, "main.py", "restore", str(src), "--id", str(s1["id"]), "--yes"],
        cwd=".",
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"Restore command failed: {result.stderr}"
    assert "Restored" in result.stdout
    assert src.read_text(encoding="utf-8") == "v1"

def test_cli_recover(tmp_path):
    # Setup project directory
    project_dir = tmp_path / "my_project2"
    project_dir.mkdir()
    
    src = project_dir / "cli_rec.py"
    src.write_text("v1", encoding="utf-8")
    
    from config import Config
    from backup import BackupEngine
    cfg = Config()
    engine = BackupEngine(project_dir, cfg)
    s1 = engine.create_snapshot(src)
    
    src.write_text("v2", encoding="utf-8")
    
    # Test recover command
    result = subprocess.run(
        [sys.executable, "main.py", "recover", str(src), "--yes"],
        cwd=".",
        input="\n",
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"Recover command failed: {result.stderr}"
    assert src.read_text(encoding="utf-8") == "v1"

