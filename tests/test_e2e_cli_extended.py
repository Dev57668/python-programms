import sys
import subprocess
import shutil
import tempfile
import time
from pathlib import Path
from config import Config
from backup import BackupEngine

def test_cli_extended_commands(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    main_script = Path(__file__).resolve().parent.parent / "main.py"
    
    cfg = Config()
    cfg.debounce_time = 0
    engine = BackupEngine(project_dir, cfg)
    
    def run_cli(*args):
        return subprocess.run(
            [sys.executable, str(main_script)] + list(args),
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
    
    # Create file
    test_file = project_dir / "app.py"
    test_file.write_text("v1")
    
    # Take a snapshot
    engine.create_snapshot(test_file)
    
    # Timeline
    res = run_cli("timeline", "app.py")
    assert "app.py" in res.stdout
    
    # Edit file
    test_file.write_text("v2")
    engine.create_snapshot(test_file)
    
    # Diff
    res = run_cli("diff", "app.py", "--from", "1", "--to", "2")
    assert "CODEVAULT - DIFF" in res.stdout
    
    # Pin
    res = run_cli("pin", "app.py", "--id", "1")
    assert "[OK] Snapshot pinned" in res.stdout
    
    # Pins
    res = run_cli("pins")
    assert "app.py" in res.stdout
    
    # Unpin
    res = run_cli("unpin", "app.py", "--id", "1")
    assert "[OK] Snapshot unpinned" in res.stdout
    
    # Config set
    res = run_cli("config", "set", ".", "max_snapshots", "10")
    assert "[OK]" in res.stdout
    
    # Config show
    res = run_cli("config", "show", ".")
    assert "Max Snapshots" in res.stdout
    
    # Clean
    res = run_cli("clean", ".")
    assert "Clean complete" in res.stdout or "[OK]" in res.stdout or "Nothing to clean" in res.stdout
    
    # Purge
    res = run_cli("purge", "-y", ".")
    assert "[OK]" in res.stdout or "permanently deleted" in res.stdout or "Purge complete" in res.stdout
    
    # Verify
    res = run_cli("verify", ".")
    assert "Verification complete" in res.stdout or "[OK]" in res.stdout or "No snapshots to verify" in res.stdout
