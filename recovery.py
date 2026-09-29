"""
Recovery Engine for Code Lifejacket.
Handles inspecting snapshot history, restoring deleted or overwritten files,
presenting repository status, and managing snapshot cleanup safely.
"""

import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from backup import BackupEngine
from config import Config
from database import Database
from utils import format_size, get_relative_path

logger = logging.getLogger("lifejacket")


class RecoveryEngine:
    """Manages file recovery, history inspection, and status reporting."""

    def __init__(self, project_dir: Path, config: Optional[Config] = None):
        """
        Initialize the recovery engine.
        
        Args:
            project_dir: Root directory of the project.
            config: Optional Config instance.
        """
        self.project_dir = Path(project_dir).resolve()
        self.config = config or Config()
        self.backup_engine = BackupEngine(self.project_dir, self.config)
        self.db: Database = self.backup_engine.db

    def get_file_history(self, target_file: Path) -> List[Dict[str, Any]]:
        """
        Retrieve all available snapshots for a given file.
        
        Args:
            target_file: Absolute or relative path to the file.
            
        Returns:
            List of snapshot record dictionaries.
        """
        resolved_file = Path(target_file).resolve()
        relative_path = get_relative_path(resolved_file, self.project_dir)
        return self.db.get_snapshots_for_file(relative_path)

    def print_history(self, target_file: Path) -> None:
        """Print formatted history for a given file."""
        resolved_file = Path(target_file).resolve()
        relative_path = get_relative_path(resolved_file, self.project_dir)
        snapshots = self.get_file_history(resolved_file)

        print("\n" + "=" * 70)
        print(f"  Code Lifejacket - File History")
        print("=" * 70)
        print(f"File:       {relative_path}")

        # Check current status on disk
        if resolved_file.exists():
            print(f"Status:     ACTIVE (exists on disk)")
        else:
            print(f"Status:     DELETED / MISSING (safe in Lifejacket backups)")

        if not snapshots:
            print("\nNo snapshots found for this file.")
            print("=" * 70 + "\n")
            return

        print(f"Snapshots:  {len(snapshots)} version(s) available")
        print("-" * 70)
        print(f"{'ID':<6}{'Timestamp':<22}{'Size':<12}{'Event':<12}{'SHA-256 (Prefix)':<16}")
        print("-" * 70)

        for s in snapshots:
            snap_id = str(s.get("id", ""))
            ts = s.get("timestamp", "N/A")
            size_str = format_size(s.get("size", 0))
            event_type = s.get("event_type", "modified")
            sha_prefix = s.get("hash", "")[:12]
            print(f"{snap_id:<6}{ts:<22}{size_str:<12}{event_type:<12}{sha_prefix:<16}")

        print("=" * 70)
        print(f"To restore a version: python main.py restore {relative_path} --id <ID>\n")

    def select_snapshot_interactively(
        self,
        target_file: Path,
        snapshots: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Display an interactive recovery menu and let user select a snapshot by number.
        
        Args:
            target_file: Path to destination file.
            snapshots: List of available snapshot dictionaries.
            
        Returns:
            The selected snapshot dictionary, or None if user cancels.
        """
        resolved_file = Path(target_file).resolve()
        relative_path = get_relative_path(resolved_file, self.project_dir)

        print("\n" + "=" * 76)
        print("  Code Lifejacket - Interactive Recovery Menu")
        print("=" * 76)
        print(f"File:       {relative_path}")
        if resolved_file.exists():
            print(f"Status:     ACTIVE (exists on disk)")
        else:
            print(f"Status:     DELETED / MISSING (safe in Lifejacket backups)")
        print(f"Location:   {resolved_file}")
        print("\nAvailable Snapshots:")
        print("-" * 76)
        print(f"{'#':<4}{'Timestamp':<22}{'Size':<10}{'Event':<11}{'SHA-256 Prefix':<16}{'ID':<6}{'Notes'}")
        print("-" * 76)

        total = len(snapshots)
        for idx, s in enumerate(snapshots, start=1):
            ts = s.get("timestamp", "N/A")
            size_str = format_size(s.get("size", 0))
            event_type = s.get("event_type", "modified")
            sha_prefix = s.get("hash", "")[:12]
            snap_id = f"#{s.get('id', '')}"
            is_latest = " [LATEST]" if idx == total else ""
            print(f"{idx:<4}{ts:<22}{size_str:<10}{event_type:<11}{sha_prefix:<16}{snap_id:<6}{is_latest}")

        print("-" * 76)
        print("[0] Cancel recovery")
        print("=" * 76)

        prompt_str = f"Select a snapshot by number (1-{total}) [Default: {total} (latest)]: "
        try:
            choice = input(prompt_str).strip()
            if not choice:
                # Default to latest
                return snapshots[-1]

            if choice in ("0", "q", "quit", "exit", "cancel"):
                print("Restoration cancelled.")
                return None

            # Check if user entered a menu number 1..total
            if choice.isdigit():
                num = int(choice)
                if 1 <= num <= total:
                    return snapshots[num - 1]
                # Also accept snapshot ID directly as convenience fallback
                for s in snapshots:
                    if s.get("id") == num:
                        return s

            print(f"[Error] Invalid selection '{choice}'. Please enter a number between 1 and {total}.")
            return None
        except (EOFError, KeyboardInterrupt):
            print("\nRestoration cancelled.")
            return None

    def confirm_restoration(
        self,
        target_file: Path,
        snapshot: Dict[str, Any],
        relative_path: str
    ) -> bool:
        """
        Display snapshot details and prompt user for confirmation before restoring.
        
        Args:
            target_file: Path to destination file.
            snapshot: Chosen snapshot dictionary.
            relative_path: Relative path string.
            
        Returns:
            True if user confirmed, False otherwise.
        """
        exists_on_disk = target_file.exists()
        snap_id = snapshot.get("id", "")
        ts = snapshot.get("timestamp", "N/A")
        size_str = format_size(snapshot.get("size", 0))
        event_type = snapshot.get("event_type", "modified")
        sha_full = snapshot.get("hash", "")
        sha_prefix = sha_full[:12] if sha_full else "N/A"

        print("\n" + "-" * 76)
        print("  Restoration Confirmation")
        print("-" * 76)
        print(f"Target File:      {relative_path}")
        print(f"Destination:      {target_file}")
        print(f"Snapshot Version: #{snap_id} ({event_type})")
        print(f"Timestamp:        {ts}")
        print(f"Size:             {size_str}")
        print(f"SHA-256 Prefix:   {sha_prefix}")
        if exists_on_disk:
            print("Disk Status:      [WARNING] Current file exists and will be OVERWRITTEN!")
        else:
            print("Disk Status:      Restoring deleted file to original path.")
        print("-" * 76)

        try:
            prompt = "Proceed with restoration? (y/N): "
            response = input(prompt).strip().lower()
            if response in ("y", "yes"):
                return True
            print("Restoration cancelled by user. Target file was not modified.")
            return False
        except (EOFError, KeyboardInterrupt):
            print("\nRestoration cancelled.")
            return False

    def restore_file(
        self,
        target_file: Path,
        snapshot_id: Optional[int] = None,
        force: bool = False,
        interactive: bool = True
    ) -> bool:
        """
        Restore a file from a selected snapshot.
        Presents an interactive menu to pick by number, and confirms before restoring.
        
        Args:
            target_file: Destination file path.
            snapshot_id: Specific snapshot ID to restore (optional).
            force: If True, bypass confirmation prompts (e.g. CLI --yes flag).
            interactive: Whether to prompt for input if needed.
            
        Returns:
            True if restoration was successful, False otherwise.
        """
        resolved_dest = Path(target_file).resolve()
        relative_path = get_relative_path(resolved_dest, self.project_dir)
        snapshots = self.db.get_snapshots_for_file(relative_path)

        if not snapshots:
            print(f"\n[Error] No snapshots found for '{relative_path}'. Cannot restore.")
            return False

        # Select which snapshot to restore
        chosen_snapshot: Optional[Dict[str, Any]] = None

        if snapshot_id is not None:
            for s in snapshots:
                if s["id"] == snapshot_id:
                    chosen_snapshot = s
                    break
            if not chosen_snapshot:
                print(f"\n[Error] Snapshot ID #{snapshot_id} not found for '{relative_path}'.")
                return False
        else:
            if interactive:
                chosen_snapshot = self.select_snapshot_interactively(resolved_dest, snapshots)
                if not chosen_snapshot:
                    return False
            else:
                # Default to latest snapshot in non-interactive mode
                chosen_snapshot = snapshots[-1]

        # Locate snapshot source file
        source_rel_path = chosen_snapshot.get("snapshot_path")
        source_abs_path = self.project_dir / source_rel_path

        if not source_abs_path.is_file():
            print(f"\n[Error] Snapshot file missing on disk: {source_abs_path}")
            return False

        # Confirmation prompt check before restoring
        if not force:
            if interactive:
                confirmed = self.confirm_restoration(resolved_dest, chosen_snapshot, relative_path)
                if not confirmed:
                    return False
            else:
                # Non-interactive mode without force: protect against overwrite
                if resolved_dest.exists():
                    print(f"\n[Safety Alert] File already exists at: {resolved_dest}")
                    print("Aborting: File exists and --yes was not provided.")
                    return False
                else:
                    print("Aborting: Confirmation required and --yes was not provided.")
                    return False

        # Perform the safe copy
        try:
            resolved_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_abs_path, resolved_dest)
            
            # Update tracked file status in db
            tracked = self.db.get_tracked_files()
            if relative_path in tracked:
                tracked[relative_path]["status"] = "active"
                tracked[relative_path]["last_hash"] = chosen_snapshot.get("hash")
                self.db._save()

            print(f"\n[Success] Restored '{relative_path}' from Snapshot #{chosen_snapshot['id']}")
            print(f"          Created at: {chosen_snapshot.get('timestamp')}")
            print(f"          Restored to: {resolved_dest}")
            return True
        except (OSError, PermissionError) as e:
            print(f"\n[Error] Failed to restore file: {e}")
            return False

    def recover_file_wizard(self, target_file: Path, force: bool = False) -> bool:
        """
        Interactive recovery command wizard for python main.py recover <file>.
        
        Requirements:
        1. Display 'CODE LIFEJACKET - RECOVERY'
        2. Show file path and current status: ACTIVE / DELETED / MISSING
        3. List every available snapshot in a numbered table:
           Selection | ID | Timestamp | Size | Event | SHA-256
        4. Let the user select a snapshot by selection number
        5. Show the selected snapshot details
        6. If the destination file already exists, clearly warn:
           [WARNING] Current file exists and will be OVERWRITTEN!
        7. Ask: Proceed with restoration? (y/N):
        8. Only restore when the user enters y/Y
        9. Handle invalid input without crashing
        10. Handle Ctrl+C gracefully
        """
        try:
            resolved_dest = Path(target_file).resolve()
            relative_path = get_relative_path(resolved_dest, self.project_dir)
            snapshots = self.db.get_snapshots_for_file(relative_path)

            print("\n" + "=" * 76)
            print("  CODE LIFEJACKET - RECOVERY")
            print("=" * 76)
            print(f"File Path:  {relative_path}")
            print(f"Full Path:  {resolved_dest}")

            if resolved_dest.exists():
                print("Status:     ACTIVE")
            else:
                print("Status:     DELETED / MISSING")

            if not snapshots:
                print("\n[Error] No snapshots available for this file. Cannot recover.")
                print("=" * 76 + "\n")
                return False

            total = len(snapshots)
            print(f"\nAvailable Snapshots ({total} version(s)):")
            print("-" * 76)
            print(f"{'Selection':<9} | {'ID':<6} | {'Timestamp':<20} | {'Size':<10} | {'Event':<10} | {'SHA-256'}")
            print("-" * 76)

            for idx, s in enumerate(snapshots, start=1):
                snap_id = str(s.get("id", ""))
                ts = s.get("timestamp", "N/A")
                size_str = format_size(s.get("size", 0))
                event_type = s.get("event_type", "modified")
                sha_prefix = s.get("hash", "")[:12]
                is_latest = " [LATEST]" if idx == total else ""
                print(f"{idx:<9} | {snap_id:<6} | {ts:<20} | {size_str:<10} | {event_type:<10} | {sha_prefix}{is_latest}")

            print("-" * 76)
            print("[0] Cancel recovery")
            print("=" * 76)

            # Prompt user for snapshot selection by number
            chosen_snapshot = None
            selection_num = total

            while chosen_snapshot is None:
                try:
                    prompt_str = f"Select snapshot number (1-{total}) [Default: {total} (latest)]: "
                    user_input = input(prompt_str).strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nRestoration cancelled.")
                    return False

                if not user_input:
                    chosen_snapshot = snapshots[-1]
                    selection_num = total
                    break

                if user_input in ("0", "q", "quit", "exit", "cancel"):
                    print("Restoration cancelled.")
                    return False

                if user_input.isdigit():
                    num = int(user_input)
                    if 1 <= num <= total:
                        chosen_snapshot = snapshots[num - 1]
                        selection_num = num
                        break
                    # Also accept entering database ID directly as fallback
                    for idx, s in enumerate(snapshots, start=1):
                        if s.get("id") == num:
                            chosen_snapshot = s
                            selection_num = idx
                            break
                    if chosen_snapshot:
                        break

                print(f"[Invalid input] '{user_input}' is not a valid selection. Please choose a number between 1 and {total} (or 0 to cancel).")

            # Show selected snapshot details
            source_rel_path = chosen_snapshot.get("snapshot_path")
            source_abs_path = self.project_dir / source_rel_path

            if not source_abs_path.is_file():
                print(f"\n[Error] Snapshot file missing on disk: {source_abs_path}")
                return False

            exists_on_disk = resolved_dest.exists()
            snap_id = chosen_snapshot.get("id", "")
            ts = chosen_snapshot.get("timestamp", "N/A")
            size_str = format_size(chosen_snapshot.get("size", 0))
            event_type = chosen_snapshot.get("event_type", "modified")
            sha_full = chosen_snapshot.get("hash", "")
            sha_prefix = sha_full[:12] if sha_full else "N/A"

            print("\n" + "-" * 76)
            print("  Selected Snapshot Details")
            print("-" * 76)
            print(f"Selection:        {selection_num}")
            print(f"Snapshot ID:      #{snap_id}")
            print(f"Timestamp:        {ts}")
            print(f"Size:             {size_str}")
            print(f"Event:            {event_type}")
            print(f"SHA-256 Prefix:   {sha_prefix}")
            print(f"SHA-256 Full:     {sha_full}")
            print(f"Target Path:      {resolved_dest}")

            if exists_on_disk:
                print("\n[WARNING] Current file exists and will be OVERWRITTEN!")
            else:
                print("\nFile status: Restoring deleted/missing file to original path.")
            print("-" * 76)

            # Confirmation prompt: only restore when user enters y/Y
            if not force:
                try:
                    confirm = input("Proceed with restoration? (y/N): ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print("\nRestoration cancelled.")
                    return False

                if confirm not in ("y", "yes"):
                    print("Restoration cancelled by user. Target file was not modified.")
                    return False

            # Restore the file
            try:
                resolved_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_abs_path, resolved_dest)

                # Update database tracked file status
                tracked = self.db.get_tracked_files()
                if relative_path in tracked:
                    tracked[relative_path]["status"] = "active"
                    tracked[relative_path]["last_hash"] = chosen_snapshot.get("hash")
                    self.db._save()

                print(f"\n[Success] Restored '{relative_path}' from Snapshot #{chosen_snapshot['id']}")
                print(f"          Created at: {chosen_snapshot.get('timestamp')}")
                print(f"          Restored to: {resolved_dest}")
                return True
            except (OSError, PermissionError) as e:
                print(f"\n[Error] Failed to restore file: {e}")
                return False

        except (EOFError, KeyboardInterrupt):
            print("\nRestoration cancelled.")
            return False
        except Exception as e:
            logger.error(f"Error during recover wizard: {e}", exc_info=True)
            print(f"\n[Error] An unexpected error occurred: {e}")
            return False

    def get_status_data(self) -> Dict[str, Any]:
        """
        Calculate repository protection and snapshot metrics.
        Returns a dictionary containing all calculated values.
        
        Requirements fulfilled:
        1. Calculate protected file count.
        2. Calculate total snapshot count.
        3. Calculate total snapshot storage.
        4. Detect currently missing/deleted tracked files.
        5. Show the latest snapshot timestamp.
        6. Show each tracked file and its snapshot count.
        7. Clearly distinguish ACTIVE and DELETED files.
        8. Handle an empty project gracefully.
        9. Handle missing database gracefully.
        11. Do not scan .lifejacket, .git, .venv, venv, or __pycache__.
        """
        tracked_files = self.db.get_tracked_files()
        all_snapshots = self.db.get_all_snapshots()

        # Calculate snapshot storage (only inspecting .lifejacket/snapshots)
        total_size = 0
        if self.backup_engine.snapshots_dir.exists():
            for root, _, files in os.walk(self.backup_engine.snapshots_dir):
                for f in files:
                    try:
                        total_size += (Path(root) / f).stat().st_size
                    except OSError:
                        pass

        # Calculate active and deleted files
        active_count = 0
        deleted_count = 0
        file_activity = []

        for rel_path, meta in tracked_files.items():
            file_abs = self.project_dir / rel_path
            file_snaps = [s for s in all_snapshots if s.get("relative_path") == rel_path]
            snap_count = len(file_snaps) if file_snaps else meta.get("snapshot_count", 0)

            if file_abs.exists():
                status = "ACTIVE"
                active_count += 1
            else:
                status = "DELETED"
                deleted_count += 1

            file_activity.append({
                "file": rel_path,
                "snapshots": snap_count,
                "status": status
            })

        # Sort file activity: DELETED files first, then alphabetically
        file_activity.sort(key=lambda x: (0 if x["status"] == "DELETED" else 1, x["file"]))

        # Latest snapshot timestamp
        last_snapshot_ts = "None"
        if all_snapshots:
            last_snapshot_ts = all_snapshots[-1].get("timestamp", "None")

        is_active = (active_count > 0 or len(all_snapshots) > 0)
        protection_str = "● ACTIVE" if is_active else "○ INACTIVE"

        return {
            "project_dir": str(self.project_dir),
            "is_active": is_active,
            "protection_status": protection_str,
            "protected_files_count": active_count,
            "total_snapshots_count": len(all_snapshots),
            "deleted_files_count": deleted_count,
            "total_backup_size_bytes": total_size,
            "total_backup_size_formatted": format_size(total_size),
            "last_snapshot": last_snapshot_ts,
            "file_activity": file_activity,
            "lifejacket_dir": self.config.snapshot_directory_name,
            "max_snapshots": self.config.max_snapshots
        }

    def print_status(self) -> None:
        """
        Display the professional Code Lifejacket status dashboard.
        Clean, readable format compatible with Windows Git Bash.
        """
        data = self.get_status_data()

        # Handle console encoding safely for Git Bash and Windows cmd
        prot_str = data["protection_status"]
        try:
            prot_str.encode(getattr(sys.stdout, "encoding", "utf-8") or "utf-8")
        except (UnicodeEncodeError, LookupError, AttributeError):
            prot_str = prot_str.replace("●", "[*]").replace("○", "[ ]")

        print("\n" + "=" * 60)
        print("              CODE LIFEJACKET - STATUS")
        print("=" * 60)
        print("\nProject:")
        print(f"{data['project_dir']}")
        print("\nProtection:")
        print(f"{prot_str}")
        print(f"\nProtected Files:       {data['protected_files_count']}")
        print(f"Total Snapshots:       {data['total_snapshots_count']}")
        print(f"Deleted Files:          {data['deleted_files_count']}")
        print(f"Total Backup Size:     {data['total_backup_size_formatted']}")
        print(f"Last Snapshot:         {data['last_snapshot']}")
        print("\n" + "-" * 60)
        print("FILE ACTIVITY")
        print("-" * 60)
        print(f"\n{'File':<25}{'Snapshots':<13}{'Status'}")
        print("-" * 60)

        if not data["file_activity"]:
            print("No tracked files yet.")
        else:
            for item in data["file_activity"]:
                filename = item["file"]
                if len(filename) > 23:
                    filename = "..." + filename[-20:]
                print(f"{filename:<25}{item['snapshots']:<13}{item['status']}")

        print("\n" + "-" * 60)
        print("STORAGE")
        print("-" * 60)
        print(f"\nLifejacket Directory: {data['lifejacket_dir']}")
        print(f"Storage Used: {data['total_backup_size_formatted']}")
        print(f"Maximum Snapshots: {data['max_snapshots']}")
        print("-" * 60 + "\n")

    def print_all_snapshots(self) -> None:
        """Display a table of all snapshots saved across the project."""
        snapshots = self.db.get_all_snapshots()

        print("\n" + "=" * 80)
        print("  Code Lifejacket - All Stored Snapshots")
        print("=" * 80)

        if not snapshots:
            print("No snapshots stored yet. Run 'python main.py watch <dir>' to start monitoring.")
            print("=" * 80 + "\n")
            return

        print(f"{'ID':<6}{'File Path':<35}{'Timestamp':<20}{'Size':<10}{'SHA-256':<10}")
        print("-" * 80)
        for s in snapshots:
            snap_id = str(s.get("id", ""))
            rel_path = s.get("relative_path", "")
            if len(rel_path) > 33:
                rel_path = "..." + rel_path[-30:]
            ts = s.get("timestamp", "N/A")
            size_str = format_size(s.get("size", 0))
            sha_prefix = s.get("hash", "")[:8]
            print(f"{snap_id:<6}{rel_path:<35}{ts:<20}{size_str:<10}{sha_prefix:<10}")

        print("=" * 80 + "\n")

    def clean(self, force: bool = False) -> bool:
        """
        Clear all snapshots and metadata with user confirmation.
        
        Args:
            force: If True, bypass confirmation prompt.
            
        Returns:
            True if cleaned, False if cancelled.
        """
        if not force:
            print(f"\n[Warning] This will permanently remove all snapshots in:")
            print(f"          {self.backup_engine.snapshots_dir}")
            try:
                confirm = input("Are you sure you want to proceed? (y/N): ").strip().lower()
                if confirm not in ("y", "yes"):
                    print("Clean cancelled.")
                    return False
            except (EOFError, KeyboardInterrupt):
                print("\nClean cancelled.")
                return False

        self.backup_engine.clean()
        print("\n[Success] Cleaned all snapshots and reset metadata.")
        return True
