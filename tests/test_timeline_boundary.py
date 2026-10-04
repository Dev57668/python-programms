import sys
import pathlib
import pytest
from pathlib import Path
import subprocess

def test_timeline_boundary_filtering(tmp_path):
    project_dir = tmp_path / "timeline_boundary_project"
    project_dir.mkdir()
    
    src_dir = project_dir / "src"
    src_dir.mkdir()
    
    app_file = src_dir / "app.py"
    app_file.write_text("A\n", encoding="utf-8")
    
    application_file = src_dir / "application.py"
    application_file.write_text("B\n", encoding="utf-8")
    
    from backup import BackupEngine
    from config import Config
    
    config = Config(project_dir / ".lifejacket" / "config.json")
    engine = BackupEngine(project_dir, config)
    
    # Create snapshots for both
    engine.create_snapshot(app_file, "modified")
    engine.create_snapshot(application_file, "modified")
    
    import pathlib
    root = pathlib.Path(__file__).parent.parent.resolve()
    main_script = str(root / "main.py")
    
    # Test timeline specific file src/app.py
    res = subprocess.run([sys.executable, main_script, "timeline", "src/app.py"], cwd=str(project_dir), capture_output=True, text=True)
    
    # Should contain src/app.py but NOT src/application.py
    assert "src/app.py" in res.stdout
    assert "src/application.py" not in res.stdout
