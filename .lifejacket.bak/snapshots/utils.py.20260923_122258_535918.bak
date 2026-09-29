"""
Utility functions for Code Lifejacket.
Includes SHA-256 hashing, path helpers, timestamp formatters, and logging setup.
"""

import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional


def compute_file_hash(file_path: Path) -> Optional[str]:
    """
    Compute the SHA-256 hex digest of a file in 64KB chunks.
    
    Args:
        file_path: Path to the target file.
        
    Returns:
        SHA-256 hexadecimal string, or None if the file cannot be read.
    """
    if not file_path.is_file():
        return None

    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha256.update(chunk)
        return sha256.hexdigest()
    except (OSError, PermissionError) as e:
        logging.getLogger("lifejacket").debug(f"Unable to read file for hashing {file_path}: {e}")
        return None


def format_timestamp(dt: Optional[datetime] = None) -> str:
    """Return a human-readable timestamp (e.g., 2026-09-23 12:30:15)."""
    if dt is None:
        dt = datetime.now()
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_timestamp_filename(dt: Optional[datetime] = None) -> str:
    """
    Return a filesystem-safe timestamp with microsecond precision
    to prevent snapshot collision during rapid modifications.
    """
    if dt is None:
        dt = datetime.now()
    return dt.strftime("%Y%m%d_%H%M%S_%f")


def format_size(size_bytes: int) -> str:
    """Format byte count into a human-friendly string (e.g., 12.4 KB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


def get_relative_path(file_path: Path, base_dir: Path) -> str:
    """
    Convert an absolute or arbitrary file path to a relative path
    relative to base_dir, using standard forward slashes.
    """
    try:
        rel = file_path.resolve().relative_to(base_dir.resolve())
        return rel.as_posix()
    except ValueError:
        return file_path.name


def setup_logger(log_file: Optional[Path] = None, log_level: str = "INFO") -> logging.Logger:
    """
    Configure and return the root logger for Code Lifejacket.
    
    Args:
        log_file: Optional file path to write log entries to.
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR).
        
    Returns:
        Configured Logger instance.
    """
    logger = logging.getLogger("lifejacket")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Avoid duplicate handlers if already configured
    if not logger.handlers:
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # File handler (if specified)
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

    return logger
