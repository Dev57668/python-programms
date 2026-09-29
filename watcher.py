"""
File Watcher Module for Code Lifejacket.
Leverages watchdog to monitor filesystem events in real-time,
applies debouncing to suppress duplicate editor-save bursts,
and guarantees watcher resilience through comprehensive exception shielding.
"""

import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict, Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from backup import BackupEngine
from config import Config

logger = logging.getLogger("lifejacket")


class LifejacketEventHandler(FileSystemEventHandler):
    """
    Handles filesystem events (modified, created, deleted) with debouncing
    and exception shielding so the watcher process never crashes.
    """

    def __init__(self, backup_engine: BackupEngine, config: Config):
        super().__init__()
        self.backup_engine = backup_engine
        self.config = config
        self.debounce_seconds = config.debounce_time

        # Debounce management
        self._lock = threading.Lock()
        self._debounce_timers: Dict[str, threading.Timer] = {}

    def _cancel_timer(self, file_path_str: str) -> None:
        """Cancel any running debounce timer for a file."""
        with self._lock:
            timer = self._debounce_timers.pop(file_path_str, None)
            if timer:
                timer.cancel()

    def _schedule_backup(self, file_path_str: str, event_type: str) -> None:
        """Schedule a debounced snapshot creation."""
        with self._lock:
            # If an existing timer is running for this file, cancel it and reset
            existing = self._debounce_timers.get(file_path_str)
            if existing:
                existing.cancel()

            timer = threading.Timer(
                self.debounce_seconds,
                self._execute_backup,
                args=[file_path_str, event_type]
            )
            self._debounce_timers[file_path_str] = timer
            timer.daemon = True
            timer.start()

    def _execute_backup(self, file_path_str: str, event_type: str) -> None:
        """Execute the backup after the debounce delay has expired."""
        with self._lock:
            self._debounce_timers.pop(file_path_str, None)

        try:
            target_path = Path(file_path_str)
            # If file was deleted in the interim, let deletion handler process it
            if not target_path.exists():
                return
            self.backup_engine.create_snapshot(target_path, event_type=event_type)
        except Exception as e:
            # Exception shield: never crash the watcher because of one problematic file
            logger.error(f"[Watcher Exception Shield] Error backing up '{file_path_str}': {e}", exc_info=True)

    def on_modified(self, event: FileSystemEvent) -> None:
        """Triggered when a file is modified."""
        if event.is_directory:
            return

        target_path = Path(event.src_path)
        try:
            if not self.config.is_monitored_file(target_path):
                return
            if self.config.is_ignored_path(target_path, self.backup_engine.project_dir):
                return

            self._schedule_backup(str(target_path), "modified")
        except Exception as e:
            logger.debug(f"Error handling on_modified for {event.src_path}: {e}")

    def on_created(self, event: FileSystemEvent) -> None:
        """Triggered when a new file is created."""
        if event.is_directory:
            return

        target_path = Path(event.src_path)
        try:
            if not self.config.is_monitored_file(target_path):
                return
            if self.config.is_ignored_path(target_path, self.backup_engine.project_dir):
                return

            self._schedule_backup(str(target_path), "created")
        except Exception as e:
            logger.debug(f"Error handling on_created for {event.src_path}: {e}")

    def on_deleted(self, event: FileSystemEvent) -> None:
        """Triggered when a file is deleted."""
        if event.is_directory:
            return

        target_path = Path(event.src_path)
        try:
            # Cancel any pending backup timer for this deleted file
            self._cancel_timer(str(target_path))

            if not self.config.is_monitored_file(target_path):
                return
            if self.config.is_ignored_path(target_path, self.backup_engine.project_dir):
                return

            self.backup_engine.handle_deletion(target_path)
        except Exception as e:
            logger.error(f"[Watcher Exception Shield] Error handling deletion for '{event.src_path}': {e}")


class LifejacketWatcher:
    """Manages the watchdog observer lifecycle."""

    def __init__(self, project_dir: Path, config: Optional[Config] = None):
        self.project_dir = Path(project_dir).resolve()
        self.config = config or Config()
        self.backup_engine = BackupEngine(self.project_dir, self.config)
        self.event_handler = LifejacketEventHandler(self.backup_engine, self.config)
        self.observer = Observer()
        self._running = False

    def scan_and_snapshot_existing(self) -> int:
        """
        Initial pass: scans project directory on startup and creates initial
        snapshots for all existing source files if not already backed up.
        Returns count of files backed up.
        """
        count = 0
        for root, dirs, files in os.walk(self.project_dir):
            root_path = Path(root)
            # Prune ignored directories from recursion for performance
            dirs[:] = [
                d for d in dirs
                if not self.config.is_ignored_path(root_path / d, self.project_dir)
            ]

            for file_name in files:
                file_path = root_path / file_name
                if self.config.is_monitored_file(file_path):
                    if not self.config.is_ignored_path(file_path, self.project_dir):
                        res = self.backup_engine.create_snapshot(file_path, event_type="initial")
                        if res:
                            count += 1
        return count

    def start(self) -> None:
        """Start monitoring the project directory."""
        if not self.project_dir.exists():
            print(f"[Error] Directory not found: {self.project_dir}")
            return

        print("\n" + "=" * 70)
        print("  Code Lifejacket - Real-Time Accidental Delete Recovery System")
        print("=" * 70)
        print(f"Monitoring:          {self.project_dir}")
        print(f"File Extensions:     {', '.join(sorted(self.config.monitored_extensions))}")
        print(f"Debounce Window:     {self.config.debounce_time}s")
        print(f"Max Snapshots/file:  {self.config.max_snapshots}")
        print(f"Storage Directory:   {self.backup_engine.snapshots_dir}")
        print("-" * 70)
        print("Scanning existing source files...")

        initial_count = self.scan_and_snapshot_existing()
        print(f"Initial scan complete. {initial_count} new file snapshot(s) cataloged.")
        print("-" * 70)
        print("Lifejacket is ACTIVE. Press Ctrl+C at any time to stop.\n")

        self.observer.schedule(self.event_handler, str(self.project_dir), recursive=True)
        self.observer.start()
        self._running = True

        try:
            while self._running and self.observer.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nShutting down Code Lifejacket watcher...")
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop the watchdog observer safely."""
        self._running = False
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join(timeout=2.0)
        print("Code Lifejacket watcher stopped.")
