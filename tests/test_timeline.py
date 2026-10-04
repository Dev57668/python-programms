import sys
import pathlib
import pytest
from pathlib import Path
import subprocess
import os

def test_timeline_output(tmp_path):
    project_dir = tmp_path / "timeline_project"
    project_dir.mkdir()
    
    file1 = project_dir / "a.py"
    file1.write_text("A\n", encoding="utf-8")
    
    from backup import BackupEngine
    from config import Config
    
    config = Config(project_dir / ".lifejacket" / "config.json")
    engine = BackupEngine(project_dir, config)
    engine.create_snapshot(file1, "modified")
    
    # Move a.py to b.py
    file2 = project_dir / "b.py"
    file2.write_text("A\n", encoding="utf-8")
    file1.unlink()
    
    engine.handle_rename(file1, file2)
    
    # Add snapshot to b.py
    file2.write_text("A\nB\n", encoding="utf-8")
    engine.create_snapshot(file2, "modified")
    
    file2.unlink()
    engine.handle_deletion(file2)
    
    # Test timeline project
    
    res_proj = subprocess.run([sys.executable, str(pathlib.Path(__file__).parent.parent / "main.py"), "timeline", "."], cwd=str(project_dir), capture_output=True, text=True)
    assert "Timeline" in res_proj.stdout
    assert "CREATED" in res_proj.stdout
    assert "RENAMED" in res_proj.stdout
    assert "a.py -> b.py" in res_proj.stdout
    assert "MODIFIED" in res_proj.stdout
    assert "DELETED" in res_proj.stdout
    
    # Test timeline specific file
    res_file = subprocess.run([sys.executable, str(pathlib.Path(__file__).parent.parent / "main.py"), "timeline", "b.py"], cwd=str(project_dir), capture_output=True, text=True)
    assert "Timeline for b.py" in res_file.stdout
    assert "a.py -> b.py" in res_file.stdout # Should include rename
    assert "DELETED" in res_file.stdout

