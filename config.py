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
        Check if any part of the path falls within an ignored directory or matches a glob pattern.
        
        Args:
            target_path: Path to inspect.
            base_dir: Optional base project root to calculate relative path parts.
            
        Returns:
            True if the path should be ignored, False otherwise.
        """
        try:
            if base_dir:
                rel_path = target_path.resolve().relative_to(base_dir.resolve())
            else:
                rel_path = target_path
        except ValueError:
            rel_path = target_path

        # Always ignore the lifejacket directory
        if self.snapshot_directory_name in rel_path.parts:
            return True

        import fnmatch
        rel_str = str(rel_path)

        for pattern in self.ignored_directories:
            p = pattern.replace("**/", "*").replace("/**", "*")
            
            # Entire path match
            if fnmatch.fnmatch(rel_str, p):
                return True
                
            # Any parent matches
            for parent in rel_path.parents:
                if str(parent) != ".":
                    if fnmatch.fnmatch(str(parent), p):
                        return True
                        
            # Single part matches (for simple directory names without slashes)
            if "/" not in pattern and "\\" not in pattern:
                if any(fnmatch.fnmatch(part, pattern) for part in rel_path.parts):
                    return True
        return False

    def save(self) -> None:
        """Save the current configuration to config.json."""
        data = {
            "monitored_extensions": list(self.monitored_extensions),
            "ignored_directories": list(self.ignored_directories),
            "max_snapshots": self.max_snapshots,
            "max_age_days": self.max_age_days,
            "debounce_time": self.debounce_time,
            "snapshot_directory_name": self.snapshot_directory_name,
            "log_level": self.log_level
        }
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[Error] Failed to save config to {self.config_path}: {e}")

    def show(self) -> None:
        """Display the effective configuration."""
        print("\n" + "=" * 60)
        print("  Code Lifejacket - Effective Configuration")
        print("=" * 60)
        
        def format_val(current, default):
            return f"{current} (Default)" if current == default else f"{current} (Custom)"
            
        print(f"Extensions:          {format_val(sorted(list(self.monitored_extensions)), sorted(self.DEFAULT_MONITORED_EXTENSIONS))}")
        print(f"Ignore Patterns:     {format_val(sorted(list(self.ignored_directories)), sorted(self.DEFAULT_IGNORED_DIRECTORIES))}")
        print(f"Max Snapshots:       {format_val(self.max_snapshots, self.DEFAULT_MAX_SNAPSHOTS)}")
        print(f"Max Age Days:        {format_val(self.max_age_days, self.DEFAULT_MAX_AGE_DAYS)}")
        print(f"Debounce Time (s):   {format_val(self.debounce_time, self.DEFAULT_DEBOUNCE_TIME)}")
        print(f"Snapshot Directory:  {format_val(self.snapshot_directory_name, self.DEFAULT_SNAPSHOT_DIR_NAME)}")
        print(f"Log Level:           {format_val(self.log_level, self.DEFAULT_LOG_LEVEL)}")
        print("=" * 60)

    def set_key(self, key: str, value: str) -> bool:
        """
        Update a configuration key. 
        Returns True if successful, False if validation fails.
        """
        try:
            if key == "max_snapshots":
                val = int(value)
                if val < 1:
                    raise ValueError("Must be >= 1")
                self.max_snapshots = val
                
            elif key == "max_age_days":
                val = int(value)
                if val < 1:
                    raise ValueError("Must be >= 1")
                self.max_age_days = val
                
            elif key == "debounce_time" or key == "debounce_ms":
                # Handle ms or s based on value if it's debounce_ms but let's just parse float
                val = float(value)
                if key == "debounce_ms":
                    val = val / 1000.0
                if val < 0.1:
                    raise ValueError("Must be >= 0.1s")
                self.debounce_time = val
                
            elif key == "log_level":
                val = value.upper()
                if val not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
                    raise ValueError("Invalid log level")
                self.log_level = val
                
            elif key == "snapshot_directory_name":
                if not value or "/" in value or "\\" in value:
                    raise ValueError("Invalid directory name")
                self.snapshot_directory_name = value
                
            elif key == "ignore_patterns" or key == "ignored_directories":
                # Parse comma-separated list
                patterns = [p.strip() for p in value.split(",") if p.strip()]
                if not patterns:
                    raise ValueError("Cannot be empty")
                self.ignored_directories = set(patterns)
                
            elif key == "monitored_extensions":
                exts = [p.strip().lower() for p in value.split(",") if p.strip()]
                if not exts:
                    raise ValueError("Cannot be empty")
                # Format to ensure starts with '.'
                self.monitored_extensions = {ext if ext.startswith(".") else f".{ext}" for ext in exts}
                
            else:
                print(f"[Error] Unsupported configuration key: {key}")
                return False
                
            self.save()
            print(f"[OK] Set '{key}' to '{value}'")
            print("Configuration will apply after the next daemon restart.")
            return True
            
        except ValueError as e:
            print(f"[Error] Invalid value for '{key}': {e}")
            return False
