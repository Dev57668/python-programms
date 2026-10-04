"""
Database Module for CodeVault.
Stores metadata, file snapshot histories, content hashes, and deletion records
in a thread-safe JSON file inside .lifejacket/metadata.json.
"""

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from codevault.utils import format_timestamp


class Database:
    """Manages metadata persistence for snapshots, tracked files, and deletions."""

    def __init__(self, db_path: Path):
        """
        Initialize database.
        
        Args:
            db_path: Path to the metadata.json file.
        """
        self.db_path = Path(db_path)
        self.lock = threading.Lock()
        self.data: Dict[str, Any] = {
            "version": "1.0",
            "next_snapshot_id": 1,
            "tracked_files": {},
            "snapshots": [],
            "deletions": []
        }
        self._load()

    def _load(self) -> None:
        """Load database from disk. If missing or corrupted, initializes empty state."""
        with self.lock:
            if not self.db_path.exists():
                return

            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    content = json.load(f)
                    self.data["version"] = content.get("version", "1.0")
                    self.data["next_snapshot_id"] = content.get("next_snapshot_id", 1)
                    self.data["tracked_files"] = content.get("tracked_files", {})
                    self.data["snapshots"] = content.get("snapshots", [])
                    self.data["deletions"] = content.get("deletions", [])
            except Exception:
                # If file exists but is corrupted, do not crash
                pass

    def _save(self) -> None:
        """Atomically save database state to disk using a temporary file."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.db_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            temp_path.replace(self.db_path)
        except Exception as e:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise e

    def get_last_hash(self, relative_path: str) -> Optional[str]:
        """
        Get the SHA-256 hash of the most recent snapshot for a file.
        
        Args:
            relative_path: Relative path of the file.
            
        Returns:
            Last SHA-256 string or None if never backed up.
        """
        with self.lock:
            file_meta = self.data["tracked_files"].get(relative_path)
            if file_meta:
                return file_meta.get("last_hash")
            return None

    def add_snapshot(
        self,
        relative_path: str,
        snapshot_path: str,
        file_hash: str,
        file_size: int,
        event_type: str = "modified"
    ) -> Dict[str, Any]:
        """
        Record a new snapshot in the database.
        
        Args:
            relative_path: Relative path of the source file.
            snapshot_path: Relative path of the saved snapshot backup.
            file_hash: SHA-256 hash of the backed-up file.
            file_size: Size of the file in bytes.
            event_type: Type of event ('created' or 'modified').
            
        Returns:
            The created snapshot record dictionary.
        """
        with self.lock:
            snapshot_id = self.data["next_snapshot_id"]
            self.data["next_snapshot_id"] += 1

            now_str = format_timestamp(datetime.now())

            record = {
                "id": snapshot_id,
                "relative_path": relative_path,
                "snapshot_path": snapshot_path,
                "timestamp": now_str,
                "hash": file_hash,
                "size": file_size,
                "event_type": event_type
            }

            self.data["snapshots"].append(record)

            # Update tracked_files metadata
            if relative_path not in self.data["tracked_files"]:
                self.data["tracked_files"][relative_path] = {
                    "first_seen": now_str,
                    "last_modified": now_str,
                    "last_hash": file_hash,
                    "status": "active",
                    "snapshot_count": 1
                }
            else:
                entry = self.data["tracked_files"][relative_path]
                entry["last_modified"] = now_str
                entry["last_hash"] = file_hash
                entry["status"] = "active"
                entry["snapshot_count"] = entry.get("snapshot_count", 0) + 1

            self._save()
            return record

    def record_deletion(self, relative_path: str) -> Optional[Dict[str, Any]]:
        """
        Record a deletion event for a tracked file.
        
        Args:
            relative_path: Relative path of the deleted file.
            
        Returns:
            Deletion record dict or None if file was not tracked.
        """
        with self.lock:
            file_meta = self.data["tracked_files"].get(relative_path)
            if not file_meta:
                return None

            file_meta["status"] = "deleted"
            now_str = format_timestamp(datetime.now())

            # Find latest snapshot path
            latest_snapshot = None
            for s in reversed(self.data["snapshots"]):
                if s["relative_path"] == relative_path:
                    latest_snapshot = s["snapshot_path"]
                    break

            deletion_record = {
                "relative_path": relative_path,
                "timestamp": now_str,
                "last_known_hash": file_meta.get("last_hash"),
                "last_snapshot_path": latest_snapshot
            }

            self.data["deletions"].append(deletion_record)
            self._save()
            return deletion_record

    def get_snapshots_for_file(self, relative_path: str) -> List[Dict[str, Any]]:
        """Return all snapshot records for a given relative path (chronological)."""
        with self.lock:
            return [
                s for s in self.data["snapshots"]
                if s["relative_path"] == relative_path
            ]

    def get_all_snapshots(self) -> List[Dict[str, Any]]:
        """Return a copy of all snapshot records."""
        with self.lock:
            return list(self.data["snapshots"])

    def get_tracked_files(self) -> Dict[str, Any]:
        """Return a copy of all tracked files and their status."""
        with self.lock:
            return dict(self.data["tracked_files"])

    def get_deletions(self) -> List[Dict[str, Any]]:
        """Return a copy of all deletion records."""
        with self.lock:
            return list(self.data["deletions"])

    def prune_old_snapshots(self, relative_path: str, max_allowed: int) -> List[Dict[str, Any]]:
        """
        Identify and remove snapshot records exceeding max_allowed for a file.
        Returns the list of removed records so their physical files can be deleted.
        """
        with self.lock:
            file_snaps = [
                s for s in self.data["snapshots"]
                if s["relative_path"] == relative_path
            ]

            if len(file_snaps) <= max_allowed:
                return []

            # Remove oldest
            excess_count = len(file_snaps) - max_allowed
            to_remove = file_snaps[:excess_count]
            remove_ids = {s["id"] for s in to_remove}

            self.data["snapshots"] = [
                s for s in self.data["snapshots"]
                if s["id"] not in remove_ids
            ]

            if relative_path in self.data["tracked_files"]:
                self.data["tracked_files"][relative_path]["snapshot_count"] = max(
                    0, self.data["tracked_files"][relative_path].get("snapshot_count", len(file_snaps)) - excess_count
                )

            self._save()
            return to_remove

    def clear(self) -> None:
        """Reset the database to an empty state."""
        with self.lock:
            self.data = {
                "version": "1.0",
                "next_snapshot_id": 1,
                "tracked_files": {},
                "snapshots": [],
                "deletions": []
            }
            self._save()
