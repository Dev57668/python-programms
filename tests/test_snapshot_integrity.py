import hashlib
from pathlib import Path
from config import Config
from backup import BackupEngine

def test_snapshot_integrity(tmp_path):
    """
    Regression test: Verifies that the hash stored in the snapshot record 
    perfectly matches the actual snapshot file bytes on disk, ensuring no race condition 
    between reading for hash and reading for copy.
    """
    cfg = Config()
    engine = BackupEngine(tmp_path, cfg)
    
    # Create a source file
    source_file = tmp_path / "test_race.py"
    source_file.write_text("print('version 1')", encoding="utf-8")
    
    # Create snapshot
    record = engine.create_snapshot(source_file)
    
    assert record is not None
    db_hash = record["hash"]
    snapshot_path = tmp_path / record["snapshot_path"]
    
    assert snapshot_path.exists()
    
    # Verify hash of the snapshot file directly
    sha256 = hashlib.sha256()
    with open(snapshot_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
            
    actual_hash = sha256.hexdigest()
    
    assert db_hash == actual_hash, "Stored hash must perfectly match the snapshot file contents"

    # Let's also verify modifying the file and capturing another snapshot
    source_file.write_text("print('version 2')", encoding="utf-8")
    record2 = engine.create_snapshot(source_file)
    
    assert record2 is not None
    db_hash2 = record2["hash"]
    snapshot_path2 = tmp_path / record2["snapshot_path"]
    
    sha256_2 = hashlib.sha256()
    with open(snapshot_path2, "rb") as f:
        while chunk := f.read(65536):
            sha256_2.update(chunk)
            
    actual_hash2 = sha256_2.hexdigest()
    
    assert db_hash2 == actual_hash2
