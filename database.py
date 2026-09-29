import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from utils import format_timestamp

class Database:
    """Manages metadata persistence for snapshots, tracked files, and deletions using SQLite."""

    def __init__(self, db_path: Path):
        """
        Initialize database.
        
        Args:
            db_path: Path to the database file. If this ends in metadata.json,
                     it will be converted to vault.db in the same directory.
        """
        original_path = Path(db_path)
        if original_path.name == "metadata.json":
            self.db_path = original_path.parent / "vault.db"
            self.json_path = original_path
        else:
            self.db_path = original_path
            self.json_path = original_path.with_name("metadata.json")

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._migrate_if_needed()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a configured new SQLite connection."""
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute('''
                CREATE TABLE IF NOT EXISTS meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            ''')
            conn.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', '1')")

            conn.execute('''
                CREATE TABLE IF NOT EXISTS files (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    path         TEXT NOT NULL UNIQUE,
                    status       TEXT NOT NULL DEFAULT 'active'
                                 CHECK (status IN ('active', 'deleted')),
                    first_seen   TEXT NOT NULL,
                    last_seen    TEXT NOT NULL,
                    deleted_at   TEXT
                )
            ''')

            conn.execute('''
                CREATE TABLE IF NOT EXISTS blobs (
                    hash         TEXT PRIMARY KEY,
                    size         INTEGER NOT NULL,
                    stored_size  INTEGER NOT NULL,
                    compressed   INTEGER NOT NULL DEFAULT 0 CHECK (compressed IN (0, 1)),
                    created_at   TEXT NOT NULL
                )
            ''')

            conn.execute('''
                CREATE TABLE IF NOT EXISTS snapshots (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id      INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
                    blob_hash    TEXT    NOT NULL REFERENCES blobs(hash),
                    snapshot_path TEXT   NOT NULL,
                    created_at   TEXT    NOT NULL,
                    event_type   TEXT    NOT NULL,
                    pinned       INTEGER NOT NULL DEFAULT 0 CHECK (pinned IN (0, 1)),
                    note         TEXT
                )
            ''')

            conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_file_time ON snapshots(file_id, created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_blob      ON snapshots(blob_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_time      ON snapshots(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_files_status        ON files(status)")

    def _migrate_if_needed(self) -> None:
        """Migrate existing metadata.json if it exists."""
        if not self.json_path.exists():
            return
        
        migrated_path = self.json_path.with_name(self.json_path.name + ".migrated")
        
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                content = json.load(f)
        except Exception:
            return

        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            
            # Insert tracked files
            tracked_files = content.get("tracked_files", {})
            for path, meta in tracked_files.items():
                conn.execute('''
                    INSERT OR IGNORE INTO files (path, status, first_seen, last_seen, deleted_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    path, 
                    meta.get("status", "active"), 
                    meta.get("first_seen", format_timestamp()),
                    meta.get("last_modified", format_timestamp()),
                    None
                ))

            # Insert deletions
            deletions = content.get("deletions", [])
            for deletion in deletions:
                path = deletion.get("relative_path")
                ts = deletion.get("timestamp")
                conn.execute("UPDATE files SET status = 'deleted', deleted_at = ? WHERE path = ?", (ts, path))
                # Also create file if missing
                conn.execute('''
                    INSERT OR IGNORE INTO files (path, status, first_seen, last_seen, deleted_at)
                    VALUES (?, 'deleted', ?, ?, ?)
                ''', (path, ts, ts, ts))

            # Insert snapshots and blobs
            snapshots = content.get("snapshots", [])
            for snap in snapshots:
                path = snap.get("relative_path")
                blob_hash = snap.get("hash")
                size = snap.get("size", 0)
                ts = snap.get("timestamp")
                snapshot_path = snap.get("snapshot_path")
                event_type = snap.get("event_type", "modified")
                
                # Blob
                if blob_hash:
                    conn.execute('''
                        INSERT OR IGNORE INTO blobs (hash, size, stored_size, compressed, created_at)
                        VALUES (?, ?, ?, 0, ?)
                    ''', (blob_hash, size, size, ts))

                # Snapshot
                # Get file id
                file_row = conn.execute("SELECT id FROM files WHERE path = ?", (path,)).fetchone()
                if file_row and blob_hash:
                    file_id = file_row["id"]
                    
                    # Check if exists to make idempotent
                    exists = conn.execute("SELECT 1 FROM snapshots WHERE snapshot_path = ?", (snapshot_path,)).fetchone()
                    if not exists:
                        conn.execute('''
                            INSERT INTO snapshots (file_id, blob_hash, snapshot_path, created_at, event_type)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (file_id, blob_hash, snapshot_path, ts, event_type))

        # Rename the json file safely
        try:
            self.json_path.rename(migrated_path)
        except OSError:
            pass

    def get_last_hash(self, relative_path: str) -> Optional[str]:
        with self._get_connection() as conn:
            row = conn.execute('''
                SELECT s.blob_hash
                FROM snapshots s
                JOIN files f ON s.file_id = f.id
                WHERE f.path = ?
                ORDER BY s.created_at DESC, s.id DESC
                LIMIT 1
            ''', (relative_path,)).fetchone()
            if row:
                return row["blob_hash"]
            return None

    def add_snapshot(
        self,
        relative_path: str,
        snapshot_path: str,
        file_hash: str,
        file_size: int,
        event_type: str = "modified"
    ) -> Dict[str, Any]:
        with self._get_connection() as conn:
            conn.execute("BEGIN EXCLUSIVE")
            now_str = format_timestamp()

            # Insert or update file
            conn.execute('''
                INSERT INTO files (path, status, first_seen, last_seen)
                VALUES (?, 'active', ?, ?)
                ON CONFLICT(path) DO UPDATE SET 
                    status = 'active',
                    last_seen = excluded.last_seen,
                    deleted_at = NULL
            ''', (relative_path, now_str, now_str))
            
            file_row = conn.execute("SELECT id FROM files WHERE path = ?", (relative_path,)).fetchone()
            file_id = file_row["id"]

            # Insert blob if not exists
            conn.execute('''
                INSERT OR IGNORE INTO blobs (hash, size, stored_size, compressed, created_at)
                VALUES (?, ?, ?, 0, ?)
            ''', (file_hash, file_size, file_size, now_str))

            # Insert snapshot
            cursor = conn.execute('''
                INSERT INTO snapshots (file_id, blob_hash, snapshot_path, created_at, event_type)
                VALUES (?, ?, ?, ?, ?)
            ''', (file_id, file_hash, snapshot_path, now_str, event_type))
            
            snapshot_id = cursor.lastrowid
            
            return {
                "id": snapshot_id,
                "relative_path": relative_path,
                "snapshot_path": snapshot_path,
                "timestamp": now_str,
                "hash": file_hash,
                "size": file_size,
                "event_type": event_type
            }

    def record_deletion(self, relative_path: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            conn.execute("BEGIN EXCLUSIVE")
            file_row = conn.execute("SELECT id, status FROM files WHERE path = ?", (relative_path,)).fetchone()
            
            if not file_row or file_row["status"] == "deleted":
                return None
            
            now_str = format_timestamp()
            conn.execute("UPDATE files SET status = 'deleted', deleted_at = ? WHERE path = ?", (now_str, relative_path))
            
            # Get last hash and snapshot path
            last_snap = conn.execute('''
                SELECT blob_hash, snapshot_path 
                FROM snapshots 
                WHERE file_id = ? 
                ORDER BY created_at DESC, id DESC 
                LIMIT 1
            ''', (file_row["id"],)).fetchone()
            
            return {
                "relative_path": relative_path,
                "timestamp": now_str,
                "last_known_hash": last_snap["blob_hash"] if last_snap else None,
                "last_snapshot_path": last_snap["snapshot_path"] if last_snap else None
            }

    def get_snapshots_for_file(self, relative_path: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute('''
                SELECT s.id, f.path as relative_path, s.snapshot_path, s.created_at as timestamp, 
                       s.blob_hash as hash, b.size, s.event_type
                FROM snapshots s
                JOIN files f ON s.file_id = f.id
                JOIN blobs b ON s.blob_hash = b.hash
                WHERE f.path = ?
                ORDER BY s.created_at ASC, s.id ASC
            ''', (relative_path,)).fetchall()
            
            return [dict(row) for row in rows]

    def get_all_snapshots(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute('''
                SELECT s.id, f.path as relative_path, s.snapshot_path, s.created_at as timestamp, 
                       s.blob_hash as hash, b.size, s.event_type
                FROM snapshots s
                JOIN files f ON s.file_id = f.id
                JOIN blobs b ON s.blob_hash = b.hash
                ORDER BY s.created_at ASC, s.id ASC
            ''').fetchall()
            
            return [dict(row) for row in rows]

    def get_tracked_files(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            rows = conn.execute('''
                SELECT f.id, f.path, f.first_seen, f.last_seen, f.status,
                       (SELECT blob_hash FROM snapshots WHERE file_id = f.id ORDER BY created_at DESC, id DESC LIMIT 1) as last_hash,
                       (SELECT COUNT(*) FROM snapshots WHERE file_id = f.id) as snapshot_count
                FROM files f
            ''').fetchall()
            
            result = {}
            for row in rows:
                result[row["path"]] = {
                    "first_seen": row["first_seen"],
                    "last_modified": row["last_seen"],
                    "last_hash": row["last_hash"],
                    "status": row["status"],
                    "snapshot_count": row["snapshot_count"]
                }
            self._cached_tracked = result
            return result

    def _save(self) -> None:
        """Compatibility method for older code that modified tracked files in-place and saved."""
        if hasattr(self, '_cached_tracked'):
            with self._get_connection() as conn:
                conn.execute("BEGIN EXCLUSIVE")
                for path, meta in self._cached_tracked.items():
                    conn.execute("UPDATE files SET status = ? WHERE path = ?", (meta["status"], path))

    def get_deletions(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute('''
                SELECT f.path, f.deleted_at,
                       (SELECT blob_hash FROM snapshots WHERE file_id = f.id ORDER BY created_at DESC, id DESC LIMIT 1) as last_known_hash,
                       (SELECT snapshot_path FROM snapshots WHERE file_id = f.id ORDER BY created_at DESC, id DESC LIMIT 1) as last_snapshot_path
                FROM files f
                WHERE f.status = 'deleted'
            ''').fetchall()
            
            return [{
                "relative_path": row["path"],
                "timestamp": row["deleted_at"],
                "last_known_hash": row["last_known_hash"],
                "last_snapshot_path": row["last_snapshot_path"]
            } for row in rows]

    def prune_old_snapshots(self, relative_path: str, max_allowed: int) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            conn.execute("BEGIN EXCLUSIVE")
            
            # Fetch all snapshots for file ordered by time ascending
            rows = conn.execute('''
                SELECT s.id, f.path as relative_path, s.snapshot_path, s.created_at as timestamp, 
                       s.blob_hash as hash, b.size, s.event_type
                FROM snapshots s
                JOIN files f ON s.file_id = f.id
                JOIN blobs b ON s.blob_hash = b.hash
                WHERE f.path = ?
                ORDER BY s.created_at ASC, s.id ASC
            ''', (relative_path,)).fetchall()
            
            if len(rows) <= max_allowed:
                return []
                
            excess_count = len(rows) - max_allowed
            to_remove = rows[:excess_count]
            
            removed_dicts = []
            for row in to_remove:
                # Ensure we never delete a file while another snapshot still references the same path
                same_path_refs = conn.execute(
                    "SELECT COUNT(*) FROM snapshots WHERE snapshot_path = ? AND id != ?", 
                    (row["snapshot_path"], row["id"])
                ).fetchone()[0]
                
                conn.execute("DELETE FROM snapshots WHERE id = ?", (row["id"],))
                
                row_dict = dict(row)
                if same_path_refs > 0:
                    # Modify dict so caller won't delete the physical file
                    row_dict["snapshot_path"] = "/dev/null/do_not_delete" 
                
                removed_dicts.append(row_dict)

            return removed_dicts

    def clear(self) -> None:
        with self._get_connection() as conn:
            conn.execute("BEGIN EXCLUSIVE")
            conn.execute("DELETE FROM snapshots")
            conn.execute("DELETE FROM blobs")
            conn.execute("DELETE FROM files")
