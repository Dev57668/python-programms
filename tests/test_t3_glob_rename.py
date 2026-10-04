import tempfile
import shutil
import pytest
from pathlib import Path
from collections import namedtuple

from codevault.config import Config
from codevault.backup import BackupEngine
from codevault.watcher import CodeVaultEventHandler, CodeVaultWatcher

@pytest.fixture
def test_env(tmp_path):
    test_dir = tmp_path / "project"
    test_dir.mkdir()
    cfg = Config()
    cfg.debounce_time = 0.0
    engine = BackupEngine(test_dir, cfg)
    yield test_dir, cfg, engine

class DummyEvent:
    def __init__(self, src_path, dest_path=None, is_directory=False):
        self.src_path = str(src_path)
        self.dest_path = str(dest_path) if dest_path else None
        self.is_directory = is_directory

def test_config_glob_ignore(test_env):
    test_dir, cfg, engine = test_env
    cfg.ignored_directories = {".git", "**/node_modules", "*.tmp", "build/**"}
    
    # exact ignored directory
    assert cfg.is_ignored_path(test_dir / ".git" / "config", test_dir) is True
    
    # nested ignored directory
    assert cfg.is_ignored_path(test_dir / "frontend" / "node_modules" / "test.js", test_dir) is True
    assert cfg.is_ignored_path(test_dir / "node_modules" / "test.js", test_dir) is True
    
    # glob file pattern
    assert cfg.is_ignored_path(test_dir / "test.tmp", test_dir) is True
    assert cfg.is_ignored_path(test_dir / "src" / "temp.tmp", test_dir) is True
    
    # ignored subtree
    assert cfg.is_ignored_path(test_dir / "build" / "output.js", test_dir) is True
    assert cfg.is_ignored_path(test_dir / "build" / "dist" / "output.js", test_dir) is True
    
    # .lifejacket always excluded
    assert cfg.is_ignored_path(test_dir / ".lifejacket" / "vault.db", test_dir) is True
    
    # Should not ignore valid files
    assert cfg.is_ignored_path(test_dir / "src" / "main.py", test_dir) is False

def test_rename_preserves_history(test_env):
    test_dir, cfg, engine = test_env
    watcher = CodeVaultWatcher(test_dir, cfg)
    handler = watcher.event_handler
    
    src = test_dir / "old.py"
    src.write_text("v1")
    engine.create_snapshot(src)
    
    # Add a second snapshot
    src.write_text("v2")
    engine.create_snapshot(src)
    
    snaps = engine.db.get_snapshots_for_file("old.py")
    assert len(snaps) == 2
    
    dest = test_dir / "new.py"
    dest.write_text("v2")
    
    # tracked-file rename
    event = DummyEvent(src, dest)
    handler.on_moved(event)
    
    # history survives rename
    new_snaps = engine.db.get_snapshots_for_file("new.py")
    assert len(new_snaps) == 2
    old_snaps = engine.db.get_snapshots_for_file("old.py")
    assert len(old_snaps) == 0

def test_tracked_file_move(test_env):
    test_dir, cfg, engine = test_env
    watcher = CodeVaultWatcher(test_dir, cfg)
    handler = watcher.event_handler
    
    (test_dir / "src").mkdir()
    (test_dir / "dest").mkdir()
    
    src = test_dir / "src" / "move.py"
    src.write_text("content")
    engine.create_snapshot(src)
    
    dest = test_dir / "dest" / "move.py"
    dest.write_text("content")
    
    # Move
    event = DummyEvent(src, dest)
    handler.on_moved(event)
    
    new_snaps = engine.db.get_snapshots_for_file("dest/move.py")
    assert len(new_snaps) == 1

def test_move_into_ignored_directory(test_env):
    test_dir, cfg, engine = test_env
    watcher = CodeVaultWatcher(test_dir, cfg)
    handler = watcher.event_handler
    cfg.ignored_directories = {"node_modules"}
    
    src = test_dir / "script.py"
    src.write_text("v1")
    engine.create_snapshot(src)
    
    (test_dir / "node_modules").mkdir()
    dest = test_dir / "node_modules" / "script.py"
    dest.write_text("v1")
    
    event = DummyEvent(src, dest)
    handler.on_moved(event)
    
    # Should be treated as deletion
    snaps = engine.db.get_snapshots_for_file("script.py")
    assert len(snaps) == 1
    
    files = engine.db.get_tracked_files()
    assert files["script.py"]["status"] == "deleted"

def test_move_out_of_project(test_env):
    test_dir, cfg, engine = test_env
    watcher = CodeVaultWatcher(test_dir, cfg)
    handler = watcher.event_handler
    
    src = test_dir / "app.py"
    src.write_text("v1")
    engine.create_snapshot(src)
    
    outside = test_dir.parent / "app.py"
    
    event = DummyEvent(src, outside)
    handler.on_moved(event)
    
    files = engine.db.get_tracked_files()
    assert files["app.py"]["status"] == "deleted"

def test_duplicate_move_events(test_env):
    test_dir, cfg, engine = test_env
    watcher = CodeVaultWatcher(test_dir, cfg)
    handler = watcher.event_handler
    
    src = test_dir / "dup.py"
    src.write_text("content")
    engine.create_snapshot(src)
    
    dest = test_dir / "dup_renamed.py"
    dest.write_text("content")
    
    event1 = DummyEvent(src, dest)
    event2 = DummyEvent(src, dest)
    
    handler.on_moved(event1)
    # Should not crash on duplicate move event if the source file is no longer in active DB
    handler.on_moved(event2)
    
    new_snaps = engine.db.get_snapshots_for_file("dup_renamed.py")
    assert len(new_snaps) == 1
