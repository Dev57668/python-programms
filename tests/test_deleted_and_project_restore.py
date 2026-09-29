import os
import shutil
import tempfile
import pytest
from pathlib import Path
from datetime import datetime, timedelta

from config import Config
from recovery import RecoveryEngine
from backup import BackupEngine
from utils import format_timestamp

@pytest.fixture
def test_env():
    test_dir = Path(tempfile.mkdtemp())
    cfg = Config()
    # Speed up tests
    cfg.backup_debounce_seconds = 0
    engine = BackupEngine(test_dir, cfg)
    recovery = RecoveryEngine(test_dir, cfg)
    yield test_dir, engine, recovery
    shutil.rmtree(test_dir, ignore_errors=True)

def test_deleted_command(test_env, capsys):
    test_dir, engine, recovery = test_env
    
    file1 = test_dir / "file1.py"
    file1.write_text("v1")
    engine.create_snapshot(file1)
    
    # Simulate deletion
    file1.unlink()
    engine.db.record_deletion("file1.py")
    
    recovery.print_deleted_files()
    captured = capsys.readouterr()
    assert "file1.py" in captured.out
    assert "1" in captured.out # number of snapshots

def test_restore_deleted_file(test_env, capsys):
    test_dir, engine, recovery = test_env
    
    file1 = test_dir / "file1.py"
    file1.write_text("v1")
    s1 = engine.create_snapshot(file1)
    
    file1.unlink()
    engine.db.record_deletion("file1.py")
    
    # Restore the deleted file
    success = recovery.restore_file(file1, snapshot_id=s1["id"], force=True)
    assert success is True
    assert file1.read_text() == "v1"
    
    # Check it's no longer deleted
    recovery.print_deleted_files()
    captured = capsys.readouterr()
    assert "No deleted files found." in captured.out

def test_project_restore_historical_timestamp(test_env, capsys):
    test_dir, engine, recovery = test_env
    
    file1 = test_dir / "file1.py"
    file1.write_text("v1")
    s1 = engine.create_snapshot(file1)
    
    # Fake the timestamp to 2 hours ago
    t_v1 = datetime.now() - timedelta(hours=2)
    with engine.db._get_connection() as conn:
        conn.execute("UPDATE snapshots SET created_at = ? WHERE id = ?", (format_timestamp(t_v1), s1["id"]))
        
    file1.write_text("v2")
    s2 = engine.create_snapshot(file1)
    
    file2 = test_dir / "new_file.py"
    file2.write_text("v1")
    s3 = engine.create_snapshot(file2)
    
    # Restore project to 1 hour ago
    success = recovery.restore_project(at_time="1h", force=True)
    assert success is True
    
    assert file1.read_text() == "v1"
    assert file2.exists() is True # Preserved outside snapshot state

def test_project_restore_with_deleted_files(test_env, capsys):
    test_dir, engine, recovery = test_env
    
    file1 = test_dir / "file1.py"
    file1.write_text("v1")
    s1 = engine.create_snapshot(file1)
    
    # Fake timestamp
    t_v1 = datetime.now() - timedelta(hours=2)
    with engine.db._get_connection() as conn:
        conn.execute("UPDATE snapshots SET created_at = ? WHERE id = ?", (format_timestamp(t_v1), s1["id"]))
        
    file1.unlink()
    engine.db.record_deletion("file1.py")
    
    success = recovery.restore_project(at_time="1h", force=True)
    assert success is True
    assert file1.read_text() == "v1"

def test_project_restore_dry_run(test_env, capsys):
    test_dir, engine, recovery = test_env
    
    file1 = test_dir / "file1.py"
    file1.write_text("v1")
    s1 = engine.create_snapshot(file1)
    
    # Fake timestamp
    t_v1 = datetime.now() - timedelta(hours=2)
    with engine.db._get_connection() as conn:
        conn.execute("UPDATE snapshots SET created_at = ? WHERE id = ?", (format_timestamp(t_v1), s1["id"]))
        
    file1.write_text("v2")
    
    file2 = test_dir / "new_file.py"
    file2.write_text("new_content")
    engine.create_snapshot(file2)
    
    success = recovery.restore_project(at_time="1h", dry_run=True)
    assert success is True
    
    captured = capsys.readouterr()
    assert "Project Restore Preview (DRY RUN)" in captured.out
    assert "Files to restore: 1" in captured.out
    assert "Files currently present not part of historical state: 1" in captured.out
    assert file1.read_text() == "v2"
    assert file2.exists()

def test_project_restore_cancelled_confirmation(test_env, capsys, monkeypatch):
    test_dir, engine, recovery = test_env
    
    file1 = test_dir / "file1.py"
    file1.write_text("v1")
    s1 = engine.create_snapshot(file1)
    
    # Fake timestamp
    t_v1 = datetime.now() - timedelta(hours=2)
    with engine.db._get_connection() as conn:
        conn.execute("UPDATE snapshots SET created_at = ? WHERE id = ?", (format_timestamp(t_v1), s1["id"]))
        
    file1.write_text("v2")
    
    # Cancel the restoration
    monkeypatch.setattr('builtins.input', lambda _: 'n')
    success = recovery.restore_project(at_time="1h", force=False)
    
    assert success is False
    assert file1.read_text() == "v2" # Filesystem unchanged

def test_project_restore_overwrite_confirmation(test_env, capsys, monkeypatch):
    test_dir, engine, recovery = test_env
    
    file1 = test_dir / "file1.py"
    file1.write_text("v1")
    s1 = engine.create_snapshot(file1)
    
    # Fake timestamp
    t_v1 = datetime.now() - timedelta(hours=2)
    with engine.db._get_connection() as conn:
        conn.execute("UPDATE snapshots SET created_at = ? WHERE id = ?", (format_timestamp(t_v1), s1["id"]))
        
    file1.write_text("v2")
    
    monkeypatch.setattr('builtins.input', lambda _: 'n')
    success = recovery.restore_project(at_time="1h", force=False)
    assert success is False
    assert file1.read_text() == "v2"

def test_project_restore_corrupted_snapshot(test_env, capsys):
    test_dir, engine, recovery = test_env
    
    file1 = test_dir / "file1.py"
    file1.write_text("v1")
    s1 = engine.create_snapshot(file1)
    
    # Fake timestamp
    t_v1 = datetime.now() - timedelta(hours=2)
    with engine.db._get_connection() as conn:
        conn.execute("UPDATE snapshots SET created_at = ? WHERE id = ?", (format_timestamp(t_v1), s1["id"]))
    
    # Corrupt the snapshot file
    snap_path = test_dir / s1["snapshot_path"]
    snap_path.write_text("corrupted")
    
    success = recovery.restore_project(at_time="1h", force=True)
    assert success is False
    
    captured = capsys.readouterr()
    assert "Snapshot integrity verification failed" in captured.out

def test_project_restore_nested_directories(test_env):
    test_dir, engine, recovery = test_env
    
    nested = test_dir / "nested" / "dir"
    nested.mkdir(parents=True)
    file1 = nested / "file1.py"
    file1.write_text("v1")
    engine.create_snapshot(file1)
    
    # Fake timestamp
    t_v1 = datetime.now() - timedelta(hours=2)
    with engine.db._get_connection() as conn:
        conn.execute("UPDATE snapshots SET created_at = ? WHERE id = 1", (format_timestamp(t_v1),))
        
    file1.write_text("v2")
    
    recovery.restore_project(at_time="1h", force=True)
    assert file1.read_text() == "v1"

def test_project_restore_no_matching_snapshot(test_env):
    test_dir, engine, recovery = test_env
    
    file1 = test_dir / "file1.py"
    file1.write_text("v1")
    engine.create_snapshot(file1)
    
    # Restore to a time before any snapshots existed
    # wait, at_time='1d' means 1 day ago. The snapshot was just created.
    # So there should be no valid snapshots at that time.
    success = recovery.restore_project(at_time="1d", force=True)
    assert success is True # Should succeed but restore nothing
    # File is unchanged
    assert file1.read_text() == "v1"
