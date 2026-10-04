import os
import shutil
import tempfile
import pytest
from pathlib import Path
import time
from datetime import datetime, timedelta

from codevault.config import Config
from codevault.recovery import RecoveryEngine
from codevault.backup import BackupEngine

@pytest.fixture
def test_env(tmp_path):
    test_dir = tmp_path / 'project'
    test_dir.mkdir()
    cfg = Config()
    cfg.debounce_time = 0
    engine = BackupEngine(test_dir, cfg)
    recovery = RecoveryEngine(test_dir, cfg)
    yield test_dir, cfg, engine, recovery

def test_pin_unpin_duplicate(test_env, capsys):
    test_dir, cfg, engine, recovery = test_env
    
    file1 = test_dir / "pin.py"
    file1.write_text("v1")
    engine.create_snapshot(file1)
    
    snaps = recovery.db.get_snapshots_for_file("pin.py")
    snap_id = snaps[0]["id"]
    
    # Pin
    recovery.set_pin(file1, snap_id, True)
    assert recovery.db.get_snapshot_by_id(snap_id)["pinned"] == 1
    
    # Duplicate Pin
    recovery.set_pin(file1, snap_id, True)
    out = capsys.readouterr().out
    assert "already pinned" in out
    
    # Unpin
    recovery.set_pin(file1, snap_id, False)
    assert recovery.db.get_snapshot_by_id(snap_id)["pinned"] == 0

def test_unknown_snapshot_pin(test_env, capsys):
    test_dir, cfg, engine, recovery = test_env
    file1 = test_dir / "pin.py"
    recovery.set_pin(file1, 999, True)
    out = capsys.readouterr().out
    assert "not found" in out or "unknown" in out

def test_print_pins(test_env, capsys):
    test_dir, cfg, engine, recovery = test_env
    file1 = test_dir / "pin.py"
    file1.write_text("v1")
    engine.create_snapshot(file1)
    
    snap_id = recovery.db.get_snapshots_for_file("pin.py")[0]["id"]
    recovery.set_pin(file1, snap_id, True)
    
    recovery.print_pins()
    out = capsys.readouterr().out
    assert "pin.py" in out
    assert str(snap_id) in out

def test_verify_snapshots(test_env, capsys):
    test_dir, cfg, engine, recovery = test_env
    
    # Valid
    f1 = test_dir / "v.py"
    f1.write_text("v1")
    engine.create_snapshot(f1)
    
    # Corrupt
    f2 = test_dir / "c.py"
    f2.write_text("v1")
    engine.create_snapshot(f2)
    s2 = recovery.db.get_snapshots_for_file("c.py")[0]
    (test_dir / s2["snapshot_path"]).write_text("corrupted bytes")
    
    # Missing
    f3 = test_dir / "m.py"
    f3.write_text("v1")
    engine.create_snapshot(f3)
    s3 = recovery.db.get_snapshots_for_file("m.py")[0]
    (test_dir / s3["snapshot_path"]).unlink()
    
    success = recovery.verify_snapshots()
    assert not success
    
    out = capsys.readouterr().out
    assert "VALID" in out
    assert "CORRUPTED" in out
    assert "MISSING" in out
    assert "Valid:      1" in out
    assert "Corrupted:  1" in out
    assert "Missing:    1" in out

def test_purge_command(test_env, capsys, monkeypatch):
    test_dir, cfg, engine, recovery = test_env
    
    f1 = test_dir / "p.py"
    f1.write_text("v1")
    engine.create_snapshot(f1)
    
    # Cancelled
    monkeypatch.setattr("builtins.input", lambda _: "n")
    assert not recovery.purge()
    assert len(recovery.db.get_all_snapshots()) == 1
    
    # Purge force
    assert recovery.purge(force=True)
    assert len(recovery.db.get_all_snapshots()) == 0
    assert len(list((test_dir / ".lifejacket" / "snapshots").glob("*"))) == 0 # Empty
    assert f1.read_text() == "v1" # Project files untouched

def test_retention_clean_command_dry_run(test_env, capsys):
    test_dir, cfg, engine, recovery = test_env
    cfg.max_snapshots = 1
    
    f1 = test_dir / "r.py"
    f1.write_text("v1")
    # Call internal DB method so it skips backup pruning logic
    engine.db.add_snapshot("r.py", "s1", "h1", 100)
    engine.db.add_snapshot("r.py", "s2", "h2", 100)
    
    assert len(recovery.db.get_all_snapshots()) == 2
    
    recovery.clean_retention(dry_run=True)
    out = capsys.readouterr().out
    assert "(DRY RUN)" in out
    assert "Removable:          1" in out
    assert "Snapshots after:    1" in out
    assert len(recovery.db.get_all_snapshots()) == 2

def test_retention_clean_command_execution(test_env, capsys, monkeypatch):
    test_dir, cfg, engine, recovery = test_env
    cfg.max_snapshots = 2
    
    f1 = test_dir / "r.py"
    # Bypass create_snapshot to avoid auto-prune
    for i in range(4):
        p = f"s{i}"
        (test_dir / ".lifejacket" / "snapshots").mkdir(parents=True, exist_ok=True)
        (test_dir / ".lifejacket" / "snapshots" / p).write_text(f"v{i}")
        engine.db.add_snapshot("r.py", f".lifejacket/snapshots/{p}", f"h{i}", 100)
        
    snaps = recovery.db.get_snapshots_for_file("r.py")
    recovery.set_pin(f1, snaps[0]["id"], True) # Pin the oldest
    
    monkeypatch.setattr("builtins.input", lambda _: "y")
    recovery.clean_retention()
    
    remaining = recovery.db.get_snapshots_for_file("r.py")
    # Kept: newest 2 (max_snapshots), and oldest 1 (pinned) = 3 snapshots remaining
    assert len(remaining) == 3
    assert remaining[0]["id"] == snaps[0]["id"]
    assert remaining[1]["id"] == snaps[2]["id"]
    assert remaining[2]["id"] == snaps[3]["id"]

def test_max_age_days(test_env):
    test_dir, cfg, engine, recovery = test_env
    cfg.max_age_days = 30
    cfg.max_snapshots = 100
    
    f1 = test_dir / "age.py"
    engine.db.add_snapshot("age.py", "s1", "h1", 100)
    engine.db.add_snapshot("age.py", "s2", "h2", 100)
    
    # Fake time for the first snapshot
    snaps = recovery.db.get_snapshots_for_file("age.py")
    old_dt = datetime.now() - timedelta(days=40)
    
    with recovery.db._get_connection() as conn:
        conn.execute("UPDATE snapshots SET created_at = ? WHERE id = ?", 
                     (old_dt.strftime("%Y-%m-%d %H:%M:%S"), snaps[0]["id"]))
                     
    # Call prune directly
    removed = recovery.db.prune_old_snapshots("age.py", cfg.max_snapshots, cfg.max_age_days)
    assert len(removed) == 1
    assert removed[0]["id"] == snaps[0]["id"]
    
    remaining = recovery.db.get_snapshots_for_file("age.py")
    assert len(remaining) == 1
    assert remaining[0]["id"] == snaps[1]["id"]

def test_shared_snapshot_path_safety(test_env):
    test_dir, cfg, engine, recovery = test_env
    cfg.max_snapshots = 1
    
    # Manually populate DB to ensure we control the state
    engine.db.add_snapshot("f1.py", "same_snap", "h1", 100)
    engine.db.add_snapshot("f2.py", "same_snap", "h1", 100)
    engine.db.add_snapshot("f1.py", "new_snap", "h2", 100)
    
    removed = recovery.db.prune_old_snapshots("f1.py", cfg.max_snapshots, cfg.max_age_days)
    assert len(removed) == 1
    
    # The physical file shouldn't be deleted by cleanup loop in engine since it's guarded by prune output
    # `database.py` mutates snapshot_path to /dev/null/do_not_delete
    assert removed[0]["snapshot_path"] == "/dev/null/do_not_delete"
