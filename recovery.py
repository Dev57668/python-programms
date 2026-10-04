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
from utils import format_size, get_relative_path, parse_time_string, compute_file_hash, atomic_copy

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
            pinned_mark = "*" if s.get("pinned", 0) else ""
            print(f"{snap_id:<6}{ts:<22}{size_str:<12}{event_type:<12}{sha_prefix:<16}{pinned_mark}")

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
            pinned_mark = "[PINNED] " if s.get("pinned", 0) else ""
            is_latest = "[LATEST]" if idx == total else ""
            print(f"{idx:<4}{ts:<22}{size_str:<10}{event_type:<11}{sha_prefix:<16}{snap_id:<6}{pinned_mark}{is_latest}")

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
        interactive: bool = True,
        out_path: Optional[Path] = None,
        at_time: Optional[str] = None
    ) -> bool:
        """
        Restore a file from a selected snapshot.
        Presents an interactive menu to pick by number, and confirms before restoring.
        
        Args:
            target_file: Destination file path.
            snapshot_id: Specific snapshot ID to restore (optional).
            force: If True, bypass confirmation prompts (e.g. CLI --yes flag).
            interactive: Whether to prompt for input if needed.
            out_path: If provided, restores to this path without touching original.
            at_time: If provided, finds the latest snapshot at or before this time.
            
        Returns:
            True if restoration was successful, False otherwise.
        """
        resolved_src = Path(target_file).resolve()
        relative_path = get_relative_path(resolved_src, self.project_dir)
        snapshots = self.db.get_snapshots_for_file(relative_path)
        dest_file = out_path if out_path else resolved_src

        if not snapshots:
            print(f"\n[Error] No snapshots found for '{relative_path}'.")
            print(f"        Did you mean another file in {resolved_src.parent.name}/?")
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
                print("        Use 'python main.py history <file>' to see available IDs.")
                return False
        elif at_time is not None:
            try:
                target_dt = parse_time_string(at_time)
            except ValueError:
                print(f"\n[Error] Invalid time format: '{at_time}'.")
                print("        Use ISO datetime, HH:MM, or relative like 10m, 2h, 1d.")
                return False
            
            from datetime import datetime
            best_s = None
            for s in sorted(snapshots, key=lambda x: x.get("timestamp", "")):
                try:
                    s_dt = datetime.strptime(s.get("timestamp", ""), "%Y-%m-%d %H:%M:%S")
                    if s_dt <= target_dt:
                        best_s = s
                except ValueError:
                    pass
            if best_s:
                chosen_snapshot = best_s
            else:
                print(f"\n[Error] No snapshots found at or before {at_time} for '{relative_path}'.")
                print("        Use 'python main.py history <file>' to see available snapshots.")
                return False
        else:
            if interactive:
                chosen_snapshot = self.select_snapshot_interactively(resolved_src, snapshots)
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
                confirmed = self.confirm_restoration(dest_file, chosen_snapshot, relative_path)
                if not confirmed:
                    return False
            else:
                # Non-interactive mode without force: protect against overwrite
                if dest_file.exists():
                    print(f"\n[Safety Alert] File already exists at: {dest_file}")
                    print("Aborting: File exists and --yes was not provided.")
                    return False
                else:
                    print("Aborting: Confirmation required and --yes was not provided.")
                    return False

        # Perform the safe copy
        try:
            # Snapshot Integrity Verification
            actual_hash = compute_file_hash(source_abs_path)
            expected_hash = chosen_snapshot.get("hash")
            if actual_hash != expected_hash:
                print(f"\n[Error] Snapshot integrity verification failed!")
                print(f"        Expected SHA-256: {expected_hash}")
                print(f"        Actual SHA-256:   {actual_hash}")
                print("        The snapshot file is corrupted or modified. Restoration aborted.")
                return False

            if not out_path and dest_file.exists():
                current_hash = compute_file_hash(dest_file)
                if current_hash and current_hash != chosen_snapshot.get("hash"):
                    self.backup_engine.create_snapshot(dest_file, event_type="pre_restore")

            dest_file.parent.mkdir(parents=True, exist_ok=True)
            atomic_copy(source_abs_path, dest_file)
            
            if not out_path:
                # Update tracked file status in db
                tracked = self.db.get_tracked_files()
                if relative_path in tracked:
                    tracked[relative_path]["status"] = "active"
                    tracked[relative_path]["last_hash"] = chosen_snapshot.get("hash")
                    self.db._save()

            print(f"\n[Success] Restored '{relative_path}' from Snapshot #{chosen_snapshot['id']}")
            print(f"          Created at: {chosen_snapshot.get('timestamp')}")
            print(f"          Restored to: {dest_file}")
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
                # Snapshot Integrity Verification
                actual_hash = compute_file_hash(source_abs_path)
                expected_hash = chosen_snapshot.get("hash")
                if actual_hash != expected_hash:
                    print(f"\n[Error] Snapshot integrity verification failed!")
                    print(f"        Expected SHA-256: {expected_hash}")
                    print(f"        Actual SHA-256:   {actual_hash}")
                    print("        The snapshot file is corrupted or modified. Restoration aborted.")
                    return False

                resolved_dest.parent.mkdir(parents=True, exist_ok=True)
                atomic_copy(source_abs_path, resolved_dest)

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
        
        from daemon import DaemonManager
        dm = DaemonManager(self.project_dir, self.project_dir / self.config.snapshot_directory_name)
        daemon_info = dm.status()

        # Handle console encoding safely for Git Bash and Windows cmd
        # Override protection string based on daemon status
        prot_str = "ACTIVE" if daemon_info["status"] == "RUNNING" else "INACTIVE"
        try:
            prot_str.encode(getattr(sys.stdout, "encoding", "utf-8") or "utf-8")
        except (UnicodeEncodeError, LookupError, AttributeError):
            prot_str = prot_str.replace("●", "[*]").replace("○", "[ ]")

        print("\n" + "=" * 60)
        print("              CODE LIFEJACKET - STATUS")
        print("=" * 60)
        
        print("\nProtection:")
        print(prot_str)
        
        print("\nDaemon:")
        print(daemon_info["status"])
        
        if daemon_info["pid"]:
            print("\nPID:")
            print(daemon_info["pid"])

        print("\nProject:")
        print(f"{data['project_dir']}")

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

    def purge(self, force: bool = False) -> bool:
        """
        DELETE ALL LOCAL CODEVAULT SNAPSHOTS AND METADATA.
        
        Args:
            force: If True, bypass confirmation prompt.
            
        Returns:
            True if cleaned, False if cancelled.
        """
        if not force:
            print(f"\n[Warning] This is irreversible and will permanently remove all snapshots in:")
            print(f"          {self.backup_engine.snapshots_dir}")
            try:
                confirm = input("Are you sure you want to proceed? (y/N): ").strip().lower()
                if confirm not in ("y", "yes"):
                    print("[ERROR] Purge cancelled.")
                    return False
            except (EOFError, KeyboardInterrupt):
                print("\n[ERROR] Purge cancelled.")
                return False

        self.backup_engine.purge()
        print("\n[OK] Purge complete.")
        return True

    def print_deleted_files(self) -> None:
        """Print files that were previously tracked but are currently missing."""
        deletions = self.db.get_deletions()
        print("\n" + "=" * 70)
        print("  Code Lifejacket - Deleted Files")
        print("=" * 70)
        
        if not deletions:
            print("No deleted files found.")
            print("=" * 70 + "\n")
            return
            
        print(f"{'File':<30}{'Deleted At':<22}{'Snapshots':<10}{'Latest Snapshot':<22}")
        print("-" * 84)
        for d in deletions:
            rel_path = d["relative_path"]
            del_at = d["timestamp"] or "Unknown"
            snaps = self.db.get_snapshots_for_file(rel_path)
            num_snaps = len(snaps)
            latest_snap = snaps[-1].get("timestamp", "N/A") if snaps else "N/A"
            print(f"{rel_path:<30}{del_at:<22}{num_snaps:<10}{latest_snap:<22}")
        print("=" * 84)
        print("To restore a deleted file: python main.py restore <deleted-file> --id <ID>\n")

    def restore_project(self, at_time: str, dry_run: bool = False, force: bool = False) -> bool:
        target_dt = parse_time_string(at_time)
        if not target_dt:
            print(f"\n[Error] Invalid time format: '{at_time}'.")
            print("        Use ISO datetime, HH:MM, or relative like 10m, 2h, 1d.")
            return False

        all_files = self.db.get_tracked_files()
        plan_restore = []
        plan_skip_not_exist = []
        plan_overwrite = []
        plan_missing_now = []
        plan_not_in_history = []
        
        from datetime import datetime
        for rel_path, meta in all_files.items():
            abs_path = self.project_dir / rel_path
            snaps = self.db.get_snapshots_for_file(rel_path)
            best_s = None
            for s in sorted(snaps, key=lambda x: x.get("timestamp", "")):
                try:
                    s_dt = datetime.strptime(s.get("timestamp", ""), "%Y-%m-%d %H:%M:%S")
                    if s_dt <= target_dt:
                        best_s = s
                except ValueError:
                    pass
            
            if best_s:
                plan_restore.append({
                    "relative_path": rel_path,
                    "snapshot": best_s,
                    "abs_path": abs_path,
                    "exists_now": abs_path.exists()
                })
                if abs_path.exists():
                    plan_overwrite.append(rel_path)
                else:
                    plan_missing_now.append(rel_path)
            else:
                plan_skip_not_exist.append(rel_path)
                if abs_path.exists():
                    plan_not_in_history.append(rel_path)

        if dry_run:
            print("\n" + "=" * 70)
            print("  Code Lifejacket - Project Restore Preview (DRY RUN)")
            print("=" * 70)
            print(f"Target Time: {target_dt}")
            print(f"Files to restore: {len(plan_restore)}")
            print(f"Files to skip (did not exist then): {len(plan_skip_not_exist)}")
            print(f"Files that would be overwritten: {len(plan_overwrite)}")
            print(f"Files that existed then but are missing now: {len(plan_missing_now)}")
            print(f"Files currently present not part of historical state: {len(plan_not_in_history)}")
            return True

        if not force:
            print("\n" + "=" * 70)
            print("  Code Lifejacket - Project Restore Plan")
            print("=" * 70)
            print(f"Target Time: {target_dt}")
            print(f"Files to restore: {len(plan_restore)}")
            print(f"Files to skip (did not exist then): {len(plan_skip_not_exist)}")
            print(f"Files that would be overwritten: {len(plan_overwrite)}")
            print(f"Files that existed then but are missing now: {len(plan_missing_now)}")
            print(f"Files currently present not part of historical state: {len(plan_not_in_history)}")
            print("-" * 70)
            try:
                confirm = input("Proceed with project restoration? (y/N): ").strip().lower()
                if confirm not in ("y", "yes"):
                    print("Restoration cancelled.")
                    return False
            except (EOFError, KeyboardInterrupt):
                print("\nRestoration cancelled.")
                return False

        # Verify ALL hashes
        for item in plan_restore:
            s = item["snapshot"]
            source_abs_path = self.project_dir / s["snapshot_path"]
            if not source_abs_path.is_file():
                print(f"\n[Error] Snapshot file missing on disk: {source_abs_path}")
                return False
            actual_hash = compute_file_hash(source_abs_path)
            expected_hash = s.get("hash")
            if actual_hash != expected_hash:
                print(f"\n[Error] Snapshot integrity verification failed for {item['relative_path']}!")
                print("        The snapshot file is corrupted. Restoration aborted.")
                return False

        # Restore
        for item in plan_restore:
            self.restore_file(
                target_file=item["abs_path"],
                snapshot_id=item["snapshot"]["id"],
                force=True,
                interactive=False
            )
        
        print("\n[Success] Project restore completed.")
        return True

    def set_pin(self, target_file: Path, snapshot_id: int, pin: bool) -> None:
        """Pin or unpin a specific snapshot."""
        resolved_file = Path(target_file).resolve()
        relative_path = get_relative_path(resolved_file, self.project_dir)
        
        # Verify the file is tracked
        tracked = self.db.get_tracked_files()
        if relative_path not in tracked and not any(s['relative_path'] == relative_path for s in self.db.get_all_snapshots()):
            print(f"[Error] File '{relative_path}' is unknown to CodeVault.")
            return
            
        snapshot = self.db.get_snapshot_by_id(snapshot_id)
        if not snapshot or snapshot["relative_path"] != relative_path:
            print(f"[ERROR] Snapshot not found.")
            return
            
        if bool(snapshot.get("pinned", 0)) == pin:
            print(f"[WARNING] Snapshot #{snapshot_id} is already {'pinned' if pin else 'unpinned'}.")
            return
            
        success = self.db.set_pin_status(snapshot_id, pin)
        if success:
            print(f"[OK] Snapshot {'pinned' if pin else 'unpinned'}.")
        else:
            print(f"[ERROR] Failed to update pin status for Snapshot #{snapshot_id}.")

    def print_pins(self) -> None:
        """Display all pinned snapshots."""
        snapshots = self.db.get_all_snapshots()
        pinned_snaps = [s for s in snapshots if s.get("pinned", 0) == 1]
        
        print("\n" + "=" * 80)
        print("  CODEVAULT - PINNED SNAPSHOTS")
        print("=" * 80)
        
        if not pinned_snaps:
            print("No pinned snapshots found.")
            print("=" * 80 + "\n")
            return
            
        print(f"{'File':<35}{'ID':<6}{'Timestamp':<22}{'Size':<10}{'Hash':<10}{'Pinned':<6}")
        print("-" * 90)
        for s in pinned_snaps:
            file_path = s["relative_path"]
            snap_id = f"#{s['id']}"
            ts = s["timestamp"]
            size_str = format_size(s.get("size", 0))
            hash_str = s.get("hash", "")[:8]
            print(f"{file_path:<35}{snap_id:<6}{ts:<22}{size_str:<10}{hash_str:<10}{'Yes':<6}")
        print("=" * 90 + "\n")

    def clean_retention(self, dry_run: bool = False) -> None:
        """Perform RETENTION CLEANUP based on max_snapshots and max_age_days."""
        all_snapshots = self.db.get_all_snapshots()
        if not all_snapshots:
            print("No snapshots to clean.")
            return
            
        # Group snapshots by file
        files_snaps = {}
        for s in all_snapshots:
            files_snaps.setdefault(s["relative_path"], []).append(s)
            
        removable_ids = []
        removable_size = 0
        protected_count = 0
        total_size_before = sum(s.get("size", 0) for s in all_snapshots)
        
        for rel_path, snaps in files_snaps.items():
            # Prune using the existing database logic, but rollback the transaction so we just get the list
            # Actually, `prune_old_snapshots` deletes them. We should run it in a transaction and rollback if dry-run?
            # No, `clean` asks for confirmation first. So we need to calculate WITHOUT deleting!
            # Let's duplicate the logic here to calculate what would be removed.
            
            # Sort by timestamp ascending
            snaps.sort(key=lambda x: (x["timestamp"], x["id"]))
            
            max_allowed = self.config.max_snapshots
            max_age_days = self.config.max_age_days
            from datetime import datetime, timedelta
            cutoff_date = datetime.now() - timedelta(days=max_age_days)
            
            newest_id = snaps[-1]["id"]
            keep_due_to_count = set(s["id"] for s in snaps[-max_allowed:])
            
            for s in snaps:
                if s["id"] == newest_id:
                    protected_count += 1
                    continue
                if s.get("pinned", 0) == 1:
                    protected_count += 1
                    continue
                    
                s_dt = datetime.strptime(s["timestamp"], "%Y-%m-%d %H:%M:%S")
                is_old = s_dt < cutoff_date
                is_excess = s["id"] not in keep_due_to_count
                
                if is_old or is_excess:
                    removable_ids.append(s["id"])
                    removable_size += s.get("size", 0)
                else:
                    protected_count += 1

        snaps_before = len(all_snapshots)
        snaps_after = snaps_before - len(removable_ids)
        size_remaining = total_size_before - removable_size

        if dry_run:
            print("\n" + "=" * 60)
            print("  Code Lifejacket - Retention Cleanup (DRY RUN)")
            print("=" * 60)
            print(f"Snapshots before:   {snaps_before}")
            print(f"Removable:          {len(removable_ids)}")
            print(f"Pinned/protected:   {protected_count}")
            print(f"Snapshots after:    {snaps_after}")
            print(f"Storage before:     {format_size(total_size_before)}")
            print(f"Storage recovered:  {format_size(removable_size)}")
            print(f"Storage remaining:  {format_size(size_remaining)}")
            print("=" * 60 + "\n")
            return

        print("\n" + "=" * 60)
        print("  Code Lifejacket - Retention Cleanup")
        print("=" * 60)
        print(f"Snapshots before:   {snaps_before}")
        print(f"Removable:          {len(removable_ids)}")
        print(f"Pinned/protected:   {protected_count}")
        print(f"Snapshots after:    {snaps_after}")
        print(f"Storage before:     {format_size(total_size_before)}")
        print(f"Storage recovered:  {format_size(removable_size)}")
        print(f"Storage remaining:  {format_size(size_remaining)}")
        print("=" * 60)

        if not removable_ids:
            print("Nothing to clean.\n")
            return

        try:
            confirm = input("Proceed with cleanup? (y/N): ").strip().lower()
            if confirm not in ("y", "yes"):
                print("[ERROR] Cleanup cancelled.")
                return
        except (EOFError, KeyboardInterrupt):
            print("\n[ERROR] Cleanup cancelled.")
            return

        # Perform cleanup safely
        for rel_path in files_snaps:
            removed = self.db.prune_old_snapshots(rel_path, self.config.max_snapshots, self.config.max_age_days)
            for r in removed:
                if r["snapshot_path"] != "/dev/null/do_not_delete":
                    disk_path = self.project_dir / r["snapshot_path"]
                    if disk_path.exists():
                        try:
                            disk_path.unlink()
                        except OSError:
                            pass
        
        print("\n[OK] Cleanup complete.\n")

    def verify_snapshots(self) -> bool:
        """Verify integrity of all snapshots referenced by the database."""
        snapshots = self.db.get_all_snapshots()
        if not snapshots:
            print("No snapshots to verify.")
            return True
            
        print("\n============================================================")
        print("CODEVAULT - VERIFY")
        print("============================================================")
        
        valid_count = 0
        missing_count = 0
        corrupt_count = 0
        
        for s in snapshots:
            file_path = s["relative_path"]
            snap_id = f"#{s['id']}"
            disk_path = self.project_dir / s["snapshot_path"]
            
            if not disk_path.exists():
                print(f"✗ {file_path:<20}{snap_id:<6}MISSING")
                missing_count += 1
                continue
                
            actual_hash = compute_file_hash(disk_path)
            expected_hash = s.get("hash")
            
            # Compare stored size if available and if it doesn't match, or hash doesn't match
            expected_size = s.get("size")
            actual_size = disk_path.stat().st_size if disk_path.exists() else None
            
            if actual_hash != expected_hash or (expected_size is not None and actual_size != expected_size):
                print(f"✗ {file_path:<20}{snap_id:<6}CORRUPTED")
                corrupt_count += 1
            else:
                print(f"✓ {file_path:<20}{snap_id:<6}VALID")
                valid_count += 1
                
        print("\nSummary:")
        print(f"Valid:      {valid_count}")
        print(f"Corrupted:  {corrupt_count}")
        print(f"Missing:    {missing_count}")
        
        if missing_count == 0 and corrupt_count == 0:
            print("\n[OK] Verification complete.")
        
        return missing_count == 0 and corrupt_count == 0
