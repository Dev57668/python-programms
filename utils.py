import hashlib
import logging
import os
import shutil
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import tempfile


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

def atomic_write(file_path: Path, content: bytes) -> None:
    """Write bytes to a file atomically."""
    resolved = file_path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path_str = tempfile.mkstemp(dir=resolved.parent, prefix=resolved.name + ".", suffix=".tmp")
    temp_path = Path(temp_path_str)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, resolved)
    except Exception as e:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise e

def atomic_copy(src_path: Path, dst_path: Path) -> None:
    """Copy a file atomically by streaming."""
    resolved_src = src_path.resolve()
    resolved_dst = dst_path.resolve()
    resolved_dst.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path_str = tempfile.mkstemp(dir=resolved_dst.parent, prefix=resolved_dst.name + ".", suffix=".tmp")
    temp_path = Path(temp_path_str)
    try:
        with open(resolved_src, "rb") as fsrc, os.fdopen(fd, "wb") as fdst:
            while chunk := fsrc.read(65536):
                fdst.write(chunk)
            fdst.flush()
            os.fsync(fdst.fileno())
        shutil.copystat(resolved_src, temp_path)
        os.replace(temp_path, resolved_dst)
    except Exception as e:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise e

def atomic_copy_and_hash(src_path: Path, dst_path: Path) -> tuple[str, int]:
    """Copy a file atomically by streaming and compute its SHA-256 hash simultaneously."""
    resolved_src = src_path.resolve()
    resolved_dst = dst_path.resolve()
    resolved_dst.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path_str = tempfile.mkstemp(dir=resolved_dst.parent, prefix=resolved_dst.name + ".", suffix=".tmp")
    temp_path = Path(temp_path_str)
    
    sha256 = hashlib.sha256()
    file_size = 0
    
    try:
        with open(resolved_src, "rb") as fsrc, os.fdopen(fd, "wb") as fdst:
            while chunk := fsrc.read(65536):
                sha256.update(chunk)
                file_size += len(chunk)
                fdst.write(chunk)
            fdst.flush()
            os.fsync(fdst.fileno())
        shutil.copystat(resolved_src, temp_path)
        os.replace(temp_path, resolved_dst)
        return sha256.hexdigest(), file_size
    except Exception as e:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise e

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


def parse_time_string(time_str: str) -> datetime:
    """
    Parse a time string into a datetime object.
    Supports:
    - ISO datetime (e.g. 2026-09-29T10:00:00)
    - HH:MM (today)
    - Relative time (10m, 2h, 1d)
    """
    now = datetime.now()
    
    # Relative time
    m = re.match(r"^(\d+)([mhd])$", time_str.strip().lower())
    if m:
        val = int(m.group(1))
        unit = m.group(2)
        if unit == "m":
            return now - timedelta(minutes=val)
        elif unit == "h":
            return now - timedelta(hours=val)
        elif unit == "d":
            return now - timedelta(days=val)

    # HH:MM today
    m = re.match(r"^(\d{1,2}):(\d{2})$", time_str.strip())
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        return now.replace(hour=h, minute=mn, second=0, microsecond=0)

    # Fallback to standard ISO parsing
    return datetime.fromisoformat(time_str)


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
