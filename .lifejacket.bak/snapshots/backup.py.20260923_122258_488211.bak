"""
Backup Engine for Code Lifejacket.
Creates timestamped shadow copies preserving relative folder hierarchy,
performs duplicate prevention using SHA-256 hashing,
enforces snapshot retention limits, and handles file deletions safely.
"""

import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from config import Config
from database import Database
from utils import (
    compute_file_hash,
    format_size,
    format_timestamp,
    format_timestamp_filename,
    get_relative_path,
)

logger = logging.getLogger("lifejacket")


class BackupEngine:
    """Manages snapshot backups, deduplication, and retention for a project."""

    def __init__(self, project_dir: Path, config: Optional[Config] = None):
        """
        Initialize the backup engine for a project.
        
        Args:
            project_dir: Root directory of the project being protected.
            config: Optional Config instance. If None, default Config is loaded.
        """
        self.project_dir = Path(project_dir).resolve()
        self.config = config or Config()

        # Lifejacket hidden storage directory
        self.lifejacket_dir = self.project_dir / self.config.snapshot_directory_name
        self.snapshots_dir = self.lifejacket_dir / "snapshots"
        self.db_path = self.lifejacket_dir / "metadata.json"

        # Ensure directories exist
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self.db = Database(self.db_path)

    def create_snapshot(
        self,
        file_path: Path,
        event_type: str = "modified"
    ) -> Optional[Dict[str, Any]]:
        """
        Create a timestamped shadow copy of a source file if content has changed.
        
        Args:
            file_path: Absolute or relative path to the source file.
            event_type: 'created' or 'modified'.
            
        Returns:
            Snapshot record dictionary if a snapshot was created, or None if skipped/failed.
        """
        resolved_path = Path(file_path).resolve()

        # 1. Verify file exists and is accessible
        if not resolved_path.is_file():
            logger.debug(f"Snapshot skipped: {resolved_path} is not a valid file or was deleted.")
            return None

        # 2. Check extension and ignored directory rules
        if not self.config.is_monitored_file(resolved_path):
            logger.debug(f"Snapshot skipped: extension of {resolved_path} is not monitored.")
            return None

        if self.config.is_ignored_path(resolved_path, self.project_dir):
            logger.debug(f"Snapshot skipped: {resolved_path} is in an ignored directory.")
            return None

        # 3. Calculate relative path within the project
        relative_path_str = get_relative_path(resolved_path, self.project_dir)

        # 4. Compute SHA-256 hash to detect duplicates
        current_hash = compute_file_hash(resolved_path)
        if not current_hash:
            logger.warning(f"Could not read {relative_path_str} (file may be locked). Will retry on next change.")
            return None

        last_hash = self.db.get_last_hash(relative_path_str)
        if last_hash == current_hash:
            logger.info(
                f"[Deduplication] Content unchanged for {relative_path_str} (SHA-256: {current_hash[:8]}...). Snapshot skipped."
            )
            return None

        # 5. Build snapshot path preserving relative directory structure
        timestamp_str = format_timestamp_filename(datetime.now())
        rel_path_obj = Path(relative_path_str)

        # Structure: .lifejacket/snapshots/<rel_dir>/<filename>.<timestamp>.bak
        dest_subdir = self.snapshots_dir / rel_path_obj.parent
        dest_subdir.mkdir(parents=True, exist_ok=True)

        snapshot_filename = f"{rel_path_obj.name}.{timestamp_str}.bak"
        snapshot_dest_path = dest_subdir / snapshot_filename

        # 6. Copy file preserving file metadata
        try:
            shutil.copy2(resolved_path, snapshot_dest_path)
            file_size = snapshot_dest_path.stat().st_size
        except (OSError, PermissionError) as e:
            logger.error(f"Failed to create snapshot copy for {relative_path_str}: {e}")
            if snapshot_dest_path.exists():
                try:
                    snapshot_dest_path.unlink()
                except OSError:
                    pass
            return None

        # Relative path of the snapshot from project root
        snapshot_rel_str = get_relative_path(snapshot_dest_path, self.project_dir)

        # 7. Record snapshot in database
        record = self.db.add_snapshot(
            relative_path=relative_path_str,
            snapshot_path=snapshot_rel_str,
            file_hash=current_hash,
            file_size=file_size,
            event_type=event_type
        )

        logger.info(
            f"[Lifejacket Snapshot #{record['id']}] Saved: {relative_path_str} ({format_size(file_size)}) [SHA: {current_hash[:8]}]"
        )

        # 8. Enforce snapshot retention limits (prune oldest if exceeded)
        pruned_records = self.db.prune_old_snapshots(relative_path_str, self.config.max_snapshots)
        for pruned in pruned_records:
            pruned_file = self.project_dir / pruned["snapshot_path"]
            if pruned_file.exists():
                try:
                    pruned_file.unlink()
                    logger.debug(f"Pruned oldest snapshot #{pruned['id']} for {relative_path_str}")
                except OSError as e:
                    logger.warning(f"Could not remove pruned file {pruned_file}: {e}")

        return record

    def handle_deletion(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """
        Record when a tracked source file has been deleted from the project.
        All previous snapshots remain safely preserved in .lifejacket/.
        
        Args:
            file_path: Path to the deleted file.
            
        Returns:
            Deletion record dict or None if file was unmonitored.
        """
        resolved_path = Path(file_path).resolve()
        relative_path_str = get_relative_path(resolved_path, self.project_dir)

        # Check if the file is monitored
        if not self.config.is_monitored_file(resolved_path):
            return None

        if self.config.is_ignored_path(resolved_path, self.project_dir):
            return None

        deletion_record = self.db.record_deletion(relative_path_str)
        if deletion_record:
            logger.warning(
                f"[LIFEJACKET RESCUE ALERT] Tracked file was deleted: '{relative_path_str}'!\n"
                f"                         Previous versions are safely preserved in .lifejacket.\n"
                f"                         Run 'python main.py restore {relative_path_str}' to recover."
            )
        return deletion_record

    def clean(self) -> None:
        """Purge all stored snapshots and reset the database."""
        if self.snapshots_dir.exists():
            shutil.rmtree(self.snapshots_dir)
            self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.db.clear()
        logger.info("Cleared all snapshots and reset metadata.")
