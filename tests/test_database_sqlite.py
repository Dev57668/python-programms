import json
import sqlite3
import multiprocessing
from pathlib import Path
import pytest
from database import Database as NewDatabase
from tests.old_database import Database as OldDatabase

@pytest.fixture
def json_fixture(tmp_path):
    json_path = tmp_path / "metadata.json"
    content = {
        "version": "1.0",
        "next_snapshot_id": 2,
        "tracked_files": {
            "src/app.py": {
                "first_seen": "2026-09-23 12:00:15",
                "last_modified": "2026-09-23 12:15:30",
                "last_hash": "a1b2c3d4",
                "status": "active",
                "snapshot_count": 1
            }
        },
        "snapshots": [
            {
                "id": 1,
                "relative_path": "src/app.py",
                "snapshot_path": "snapshots/src/app.py.1.bak",
                "timestamp": "2026-09-23 12:15:30",
                "hash": "a1b2c3d4",
                "size": 512,
                "event_type": "modified"
            }
        ],
        "deletions": [
            {
                "relative_path": "src/old.py",
                "timestamp": "2026-09-23 11:00:00",
                "last_known_hash": "b2c3d4e5",
                "last_snapshot_path": "snapshots/src/old.py.bak"
            }
        ]
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(content, f)
    return json_path

def assert_same_shape(val1, val2):
    if isinstance(val1, dict):
        assert isinstance(val2, dict)
        assert set(val1.keys()) == set(val2.keys())
        for k in val1:
            if val1[k] is not None and val2[k] is not None:
                assert type(val1[k]) == type(val2[k])
    elif isinstance(val1, list):
        assert isinstance(val2, list)
        assert len(val1) == len(val2)
        for item1, item2 in zip(val1, val2):
            assert_same_shape(item1, item2)
    else:
        assert type(val1) == type(val2)

def test_fresh_db_creation(tmp_path):
    db_path = tmp_path / "vault.db"
    db = NewDatabase(db_path)
    assert db_path.exists()
    
    with sqlite3.connect(db_path) as conn:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = [t[0] for t in tables]
        assert "meta" in table_names
        assert "files" in table_names
        assert "blobs" in table_names
        assert "snapshots" in table_names

def test_differential_api(tmp_path):
    old_db_path = tmp_path / "old" / "metadata.json"
    old_db_path.parent.mkdir()
    new_db_path = tmp_path / "new" / "metadata.json"
    new_db_path.parent.mkdir()
    
    old_db = OldDatabase(old_db_path)
    new_db = NewDatabase(new_db_path)
    
    # 1. Add snapshot
    old_snap = old_db.add_snapshot("file.py", "snap1", "hash1", 100)
    new_snap = new_db.add_snapshot("file.py", "snap1", "hash1", 100)
    assert_same_shape(old_snap, new_snap)
    
    # 2. Add duplicate hash
    old_db.add_snapshot("file2.py", "snap2", "hash1", 100)
    new_db.add_snapshot("file2.py", "snap2", "hash1", 100)
    
    # 3. Record deletion
    old_del = old_db.record_deletion("file.py")
    new_del = new_db.record_deletion("file.py")
    assert_same_shape(old_del, new_del)
    
    # 4. Get tracked files
    assert_same_shape(old_db.get_tracked_files(), new_db.get_tracked_files())
    
    # 5. Get all snapshots
    assert_same_shape(old_db.get_all_snapshots(), new_db.get_all_snapshots())
    
    # 6. Prune old snapshots
    old_pruned = old_db.prune_old_snapshots("file2.py", 0)
    new_pruned = new_db.prune_old_snapshots("file2.py", 0)
    assert_same_shape(old_pruned, new_pruned)
    
    # 7. Clear
    old_db.clear()
    new_db.clear()
    assert_same_shape(old_db.get_all_snapshots(), new_db.get_all_snapshots())

def test_prune_keeps_newest(tmp_path):
    db_path = tmp_path / "vault.db"
    db = NewDatabase(db_path)
    
    db.add_snapshot("file.py", "snap1", "hash1", 100)
    db.add_snapshot("file.py", "snap2", "hash2", 100)
    db.add_snapshot("file.py", "snap3", "hash3", 100)
    
    pruned = db.prune_old_snapshots("file.py", 1)
    assert len(pruned) == 2
    hashes_pruned = {p["hash"] for p in pruned}
    assert hashes_pruned == {"hash1", "hash2"}
    
    rem = db.get_all_snapshots()
    assert len(rem) == 1
    assert rem[0]["hash"] == "hash3"

def test_prune_does_not_delete_referenced(tmp_path):
    db_path = tmp_path / "vault.db"
    db = NewDatabase(db_path)
    
    db.add_snapshot("file.py", "snap1", "hash1", 100)
    db.add_snapshot("file2.py", "snap1", "hash1", 100)
    
    pruned = db.prune_old_snapshots("file.py", 0)
    assert len(pruned) == 1
    assert pruned[0]["snapshot_path"] == "/dev/null/do_not_delete"

def test_migration_twice_harmless(json_fixture, tmp_path):
    db = NewDatabase(json_fixture)
    assert json_fixture.with_name("metadata.json.migrated").exists()
    
    json_fixture.with_name("metadata.json.migrated").rename(json_fixture)
    
    db2 = NewDatabase(json_fixture)
    snaps = db2.get_all_snapshots()
    assert len(snaps) == 1
    assert json_fixture.with_name("metadata.json.migrated").exists()

def test_migration_interrupted_rename(json_fixture, tmp_path):
    db = NewDatabase(json_fixture)
    assert json_fixture.with_name("metadata.json.migrated").exists()
    
    json_fixture.with_name("metadata.json.migrated").rename(json_fixture)
    
    db.add_snapshot("file.py", "snap", "hash", 100)
    
    db2 = NewDatabase(json_fixture)
    snaps = db2.get_all_snapshots()
    assert len(snaps) == 2
    assert json_fixture.with_name("metadata.json.migrated").exists()

def test_record_deletion(tmp_path):
    db_path = tmp_path / "vault.db"
    db = NewDatabase(db_path)
    
    db.add_snapshot("file.py", "snap1", "hash1", 100)
    
    del_rec = db.record_deletion("file.py")
    assert del_rec["relative_path"] == "file.py"
    assert del_rec["last_known_hash"] == "hash1"
    
    tracked = db.get_tracked_files()
    assert tracked["file.py"]["status"] == "deleted"

def test_clear_leaves_schema_intact(tmp_path):
    db_path = tmp_path / "vault.db"
    db = NewDatabase(db_path)
    
    db.add_snapshot("file.py", "snap1", "hash1", 100)
    db.clear()
    
    with sqlite3.connect(db_path) as conn:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = [t[0] for t in tables]
        assert "meta" in table_names
        assert "files" in table_names
        assert "blobs" in table_names
        assert "snapshots" in table_names
    
    assert len(db.get_all_snapshots()) == 0

def mp_writer(db_path, prefix):
    db = NewDatabase(db_path)
    for i in range(50):
        db.add_snapshot(f"{prefix}.py", f"{prefix}_{i}.bak", f"hash_{prefix}_{i}", 100)

def test_multiprocessing(tmp_path):
    db_path = tmp_path / "vault.db"
    db = NewDatabase(db_path)
    
    p1 = multiprocessing.Process(target=mp_writer, args=(db_path, "p1"))
    p2 = multiprocessing.Process(target=mp_writer, args=(db_path, "p2"))
    
    p1.start()
    p2.start()
    
    p1.join()
    p2.join()
    
    assert p1.exitcode == 0
    assert p2.exitcode == 0
    
    assert len(db.get_all_snapshots()) == 100
