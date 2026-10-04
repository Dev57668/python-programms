import pytest
from pathlib import Path
import subprocess
import os

def test_diff_valid(tmp_path):
    project_dir = tmp_path / "diff_project"
    project_dir.mkdir()
    
    file_path = project_dir / "test.py"
    file_path.write_text("Line 1\n", encoding="utf-8")
    
    # Init
    try:
        subprocess.run(["python3", "/Users/bhaveshlakhmani/Documents/antigravity/pyhtonproject/python-programms/main.py", "watch", str(project_dir)], cwd=str(project_dir), timeout=2)
    except subprocess.TimeoutExpired:
        pass
    
    # Run a snapshot by pretending we're backup engine or just running watch loop?
    # Better to just use BackupEngine directly to control snapshots
    from backup import BackupEngine
    from config import Config
    
    config = Config(project_dir / ".lifejacket" / "config.json")
    engine = BackupEngine(project_dir, config)
    
    file_path.write_text("Line 1\n", encoding="utf-8")
    engine.create_snapshot(file_path, "modified")
    
    file_path.write_text("Line 1\nLine 2\n", encoding="utf-8")
    engine.create_snapshot(file_path, "modified")
    
    file_path.write_text("Line 1\nLine 2\nLine 3\n", encoding="utf-8")
    engine.create_snapshot(file_path, "modified")
    
    # We should have 3 snapshots (IDs 1, 2, 3 usually)
    # Check history
    res = subprocess.run(["python3", "/Users/bhaveshlakhmani/Documents/antigravity/pyhtonproject/python-programms/main.py", "history", "test.py"], cwd=str(project_dir), capture_output=True, text=True)
    assert "test.py" in res.stdout
    
    # Let's diff 1 and 2
    
    diff_res = subprocess.run(["python3", "/Users/bhaveshlakhmani/Documents/antigravity/pyhtonproject/python-programms/main.py", "diff", "test.py", "--from", "1", "--to", "2"], cwd=str(project_dir), capture_output=True, text=True)
    assert "CODEVAULT - DIFF" in diff_res.stdout
    assert "+Line 2" in diff_res.stdout
    assert "-Line 3" not in diff_res.stdout
    
    # diff 2 and 3
    diff_res2 = subprocess.run(["python3", "/Users/bhaveshlakhmani/Documents/antigravity/pyhtonproject/python-programms/main.py", "diff", "test.py", "--from", "2", "--to", "3"], cwd=str(project_dir), capture_output=True, text=True)
    assert "+Line 3" in diff_res2.stdout

def test_diff_invalid_id(tmp_path):
    project_dir = tmp_path / "diff_inv"
    project_dir.mkdir()
    
    file_path = project_dir / "test.py"
    file_path.write_text("Line 1\n", encoding="utf-8")
    
    from backup import BackupEngine
    from config import Config
    
    config = Config(project_dir / ".lifejacket" / "config.json")
    engine = BackupEngine(project_dir, config)
    engine.create_snapshot(file_path, "modified")
    
    # Diff non-existent snapshot
    
    diff_res = subprocess.run(["python3", "/Users/bhaveshlakhmani/Documents/antigravity/pyhtonproject/python-programms/main.py", "diff", "test.py", "--from", "1", "--to", "999"], cwd=str(project_dir), capture_output=True, text=True)
    assert diff_res.returncode != 0
    assert "not found" in diff_res.stdout

