"""
Configuration Module for Code Lifejacket.
Handles loading and validating user configuration from config.json.
Provides helper methods for path filtering and file extension checking.
"""

import json
from pathlib import Path
from typing import List, Optional, Set


class Config:
    """Manages application settings for Code Lifejacket."""

    # Default settings if config.json is missing or incomplete
    DEFAULT_MONITORED_EXTENSIONS = [
        ".py", ".java", ".cpp", ".c", ".js", ".ts", ".go", ".rs"
    ]
    DEFAULT_IGNORED_DIRECTORIES = [
        ".git", "node_modules", "venv", ".venv", "env",
        "__pycache__", ".lifejacket", ".idea", ".vscode"
    ]
    DEFAULT_MAX_SNAPSHOTS = 50
    DEFAULT_MAX_AGE_DAYS = 30
    DEFAULT_DEBOUNCE_TIME = 1.0
    DEFAULT_SNAPSHOT_DIR_NAME = ".lifejacket"
    DEFAULT_LOG_LEVEL = "INFO"

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize configuration.
        
        Args:
            config_path: Optional path to a config.json file.
                         If None, searches in the current directory or defaults.
        """
        self.monitored_extensions: Set[str] = set(self.DEFAULT_MONITORED_EXTENSIONS)
        self.ignored_directories: Set[str] = set(self.DEFAULT_IGNORED_DIRECTORIES)
        self.max_snapshots: int = self.DEFAULT_MAX_SNAPSHOTS
        self.max_age_days: int = self.DEFAULT_MAX_AGE_DAYS
        self.debounce_time: float = self.DEFAULT_DEBOUNCE_TIME
        self.snapshot_directory_name: str = self.DEFAULT_SNAPSHOT_DIR_NAME
        self.log_level: str = self.DEFAULT_LOG_LEVEL

        # Determine config file path
        if config_path is None:
            config_path = Path(__file__).resolve().parent / "config.json"

        self.config_path = Path(config_path)
        self.load()

    def load(self) -> None:
        """Load configuration from config.json if it exists."""
        if not self.config_path.exists():
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "monitored_extensions" in data:
                self.monitored_extensions = {
                    ext.lower() if ext.startswith(".") else f".{ext.lower()}"
                    for ext in data["monitored_extensions"]
                }
            if "ignored_directories" in data:
                self.ignored_directories = set(data["ignored_directories"])
            if "max_snapshots" in data:
                self.max_snapshots = max(1, int(data["max_snapshots"]))
            if "max_age_days" in data:
                self.max_age_days = max(1, int(data["max_age_days"]))
            if "debounce_time" in data:
                self.debounce_time = max(0.1, float(data["debounce_time"]))
            if "snapshot_directory_name" in data:
                self.snapshot_directory_name = str(data["snapshot_directory_name"])
            if "log_level" in data:
                self.log_level = str(data["log_level"]).upper()

        except Exception as e:
            # Fall back gracefully to defaults if config parsing fails
            print(f"[Warning] Failed to load config from {self.config_path}: {e}. Using defaults.")

    def is_monitored_file(self, file_path: Path) -> bool:
        """
        Check if a file should be tracked based on its extension.
        
        Args:
            file_path: Path to the target file.
            
        Returns:
            True if the file extension is in monitored_extensions, False otherwise.
        """
        return file_path.suffix.lower() in self.monitored_extensions

    def is_ignored_path(self, target_path: Path, base_dir: Optional[Path] = None) -> bool:
        """
        Check if any part of the path falls within an ignored directory.
        
        Args:
            target_path: Path to inspect.
            base_dir: Optional base project root to calculate relative path parts.
            
        Returns:
            True if the path should be ignored, False otherwise.
        """
        try:
            if base_dir:
                rel_parts = target_path.resolve().relative_to(base_dir.resolve()).parts
            else:
                rel_parts = target_path.parts
        except ValueError:
            rel_parts = target_path.parts

        for part in rel_parts:
            # Check against explicitly ignored directory names
            if part in self.ignored_directories:
                return True
            # Also ignore the configured snapshot directory name
            if part == self.snapshot_directory_name:
                return True
            # Ignore hidden directories like .git, .cache, etc.
            if part.startswith(".") and part not in (".", ".."):
                if part in self.ignored_directories or part == self.snapshot_directory_name:
                    return True

        return False
