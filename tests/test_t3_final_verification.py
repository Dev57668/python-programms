import tempfile
import shutil
import pytest
from pathlib import Path

from config import Config
from backup import BackupEngine
from watcher import LifejacketWatcher

@pytest.fixture
def test_env(tmp_path):
    test_dir = tmp_path / "project"
    test_dir.mkdir()
    cfg = Config()
    cfg.debounce_time = 0.0
    cfg.ignored_directories = {"**/node_modules", "build/**", "*.tmp"}
    engine = BackupEngine(test_dir, cfg)
    yield test_dir, cfg, engine

class DummyEvent:
    def __init__(self, src_path, dest_path=None, is_directory=False):
        self.src_path = str(src_path)
        self.dest_path = str(dest_path) if dest_path else None
        self.is_directory = is_directory

def test_case_1_rename(test_env):
    """1. A tracked file renamed from src/a.py -> src/b.py retains all existing snapshot history."""
    test_dir, cfg, engine = test_env
    watcher = LifejacketWatcher(test_dir, cfg)
    handler = watcher.event_handler
    
    (test_dir / "src").mkdir()
    src_a = test_dir / "src" / "a.py"
    src_a.write_text("v1")
    engine.create_snapshot(src_a)
    src_a.write_text("v2")
    engine.create_snapshot(src_a)
    
    src_b = test_dir / "src" / "b.py"
    event = DummyEvent(src_a, src_b)
    handler.on_moved(event)
    
    snaps = engine.db.get_snapshots_for_file("src/b.py")
    assert len(snaps) == 2

def test_case_2_move(test_env):
    """2. A tracked file moved from src/a.py -> utils/a.py retains its history."""
    test_dir, cfg, engine = test_env
    watcher = LifejacketWatcher(test_dir, cfg)
    handler = watcher.event_handler
    
    (test_dir / "src").mkdir()
    (test_dir / "utils").mkdir()
    
    src_a = test_dir / "src" / "a.py"
    src_a.write_text("v1")
    engine.create_snapshot(src_a)
    
    utils_a = test_dir / "utils" / "a.py"
    event = DummyEvent(src_a, utils_a)
    handler.on_moved(event)
    
    snaps = engine.db.get_snapshots_for_file("utils/a.py")
    assert len(snaps) == 1

def test_case_3_move_outside(test_env):
    """3. A tracked file moved outside the monitored project is recorded as deleted, while its previous snapshots remain recoverable."""
    test_dir, cfg, engine = test_env
    watcher = LifejacketWatcher(test_dir, cfg)
    handler = watcher.event_handler
    
    src = test_dir / "a.py"
    src.write_text("v1")
    engine.create_snapshot(src)
    
    outside = test_dir.parent / "a.py"
    event = DummyEvent(src, outside)
    handler.on_moved(event)
    
    files = engine.db.get_tracked_files()
    assert files["a.py"]["status"] == "deleted"
    
    snaps = engine.db.get_snapshots_for_file("a.py")
    assert len(snaps) == 1  # Recoverable

def test_case_4_move_ignored(test_env):
    """4. A tracked file moved INTO an ignored directory does not cause a new snapshot and does not lose its historical snapshots."""
    test_dir, cfg, engine = test_env
    watcher = LifejacketWatcher(test_dir, cfg)
    handler = watcher.event_handler
    
    src = test_dir / "a.py"
    src.write_text("v1")
    engine.create_snapshot(src)
    
    (test_dir / "build").mkdir()
    ignored_dest = test_dir / "build" / "a.py"
    event = DummyEvent(src, ignored_dest)
    handler.on_moved(event)
    
    files = engine.db.get_tracked_files()
    assert files["a.py"]["status"] == "deleted"
    
    snaps = engine.db.get_snapshots_for_file("a.py")
    assert len(snaps) == 1

def test_case_5_and_6_globs(test_env):
    """5. A file matching an ignore glob is never snapshotted.
       6. `**/node_modules`, `build/**`, and `*.tmp` behave as intended.
    """
    test_dir, cfg, engine = test_env
    
    # 5/6 - **/node_modules
    (test_dir / "project" / "node_modules").mkdir(parents=True)
    nm_file = test_dir / "project" / "node_modules" / "a.py"
    nm_file.write_text("test")
    assert engine.create_snapshot(nm_file) is None
    
    # 5/6 - build/**
    (test_dir / "build" / "outputs").mkdir(parents=True)
    build_file = test_dir / "build" / "outputs" / "a.py"
    build_file.write_text("test")
    assert engine.create_snapshot(build_file) is None
    
    # 5/6 - *.tmp
    tmp_file = test_dir / "file.tmp"
    tmp_file.write_text("test")
    # Add .tmp to monitored extensions so create_snapshot checks it against ignores
    cfg.monitored_extensions.add(".tmp")
    assert engine.create_snapshot(tmp_file) is None
