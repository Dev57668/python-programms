"""
Main CLI Entrypoint for Code Lifejacket — Accidental Delete Recovery System.

Supported commands:
  python main.py watch <directory>       Start real-time filesystem monitoring
  python main.py status <directory>      View repository protection status
  python main.py history <file>          Show version history of a file
  python main.py recover <file>          Interactive step-by-step recovery wizard
  python main.py restore <file>          Restore a deleted or overwritten file
  python main.py snapshots <directory>   List all saved snapshots in the project
  python main.py clean <directory>       Purge snapshots and reset metadata
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

# Ensure UTF-8 console output on Windows and Git Bash
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from config import Config
from recovery import RecoveryEngine
from utils import setup_logger
from watcher import LifejacketWatcher


def find_project_root(target_path: Path, config: Config) -> Path:
    """
    Determine the project root directory from a target file or folder
    by searching upwards for the snapshot directory or using current working dir.
    """
    resolved = target_path.resolve()
    snap_dir_name = config.snapshot_directory_name

    # Check if target is a file or directory
    start_dir = resolved.parent if resolved.is_file() else resolved

    # Traverse upwards
    current = start_dir
    while current != current.parent:
        if (current / snap_dir_name).exists():
            return current
        current = current.parent

    # Check current working directory
    cwd = Path.cwd().resolve()
    if (cwd / snap_dir_name).exists():
        return cwd

    return start_dir


def handle_watch(args: argparse.Namespace, config: Config) -> None:
    """Handle 'watch' command."""
    target_dir = Path(args.directory).resolve()
    if not target_dir.exists() or not target_dir.is_dir():
        print(f"[Error] '{args.directory}' is not a valid directory.")
        sys.exit(1)

    watcher = LifejacketWatcher(target_dir, config)
    watcher.start()


def handle_status(args: argparse.Namespace, config: Config) -> None:
    """Handle 'status' command."""
    target_dir = Path(args.directory).resolve()
    project_root = find_project_root(target_dir, config)
    engine = RecoveryEngine(project_root, config)
    engine.print_status()


def handle_history(args: argparse.Namespace, config: Config) -> None:
    """Handle 'history' command."""
    target_file = Path(args.file).resolve()
    project_root = find_project_root(target_file, config)
    engine = RecoveryEngine(project_root, config)
    engine.print_history(target_file)


def handle_restore(args: argparse.Namespace, config: Config) -> None:
    """Handle 'restore' command."""
    target_file = Path(args.file).resolve()
    project_root = find_project_root(target_file, config)
    engine = RecoveryEngine(project_root, config)
    
    out_path = Path(args.to).resolve() if args.to else None
    
    success = engine.restore_file(
        target_file=target_file,
        snapshot_id=args.id,
        force=args.yes,
        interactive=not args.yes,
        out_path=out_path,
        at_time=args.at
    )
    if not success:
        sys.exit(1)


def handle_recover(args: argparse.Namespace, config: Config) -> None:
    """Handle 'recover' command."""
    target_file = Path(args.file).resolve()
    project_root = find_project_root(target_file, config)
    engine = RecoveryEngine(project_root, config)
    success = engine.recover_file_wizard(
        target_file=target_file,
        force=args.yes
    )
    if not success:
        sys.exit(1)


def handle_snapshots(args: argparse.Namespace, config: Config) -> None:
    """Handle 'snapshots' command."""
    target_dir = Path(args.directory).resolve()
    project_root = find_project_root(target_dir, config)
    engine = RecoveryEngine(project_root, config)
    engine.print_all_snapshots()


def handle_clean(args: argparse.Namespace, config: Config) -> None:
    """Handle 'clean' command."""
    target_dir = Path(args.directory).resolve()
    project_root = find_project_root(target_dir, config)
    engine = RecoveryEngine(project_root, config)
    engine.clean(force=args.yes)


def handle_deleted(args: argparse.Namespace, config: Config) -> None:
    """Handle 'deleted' command."""
    target_dir = Path(args.directory).resolve()
    project_root = find_project_root(target_dir, config)
    engine = RecoveryEngine(project_root, config)
    engine.print_deleted_files()


def handle_restore_project(args: argparse.Namespace, config: Config) -> None:
    """Handle 'restore-project' command."""
    target_dir = Path(args.directory).resolve()
    project_root = find_project_root(target_dir, config)
    engine = RecoveryEngine(project_root, config)
    success = engine.restore_project(
        at_time=args.at,
        dry_run=args.dry_run,
        force=args.yes
    )
    if not success:
        sys.exit(1)


def main() -> None:
    """Main CLI command parser and dispatcher."""
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="Code Lifejacket - Accidental Delete Recovery System for Programmers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py watch .
  python main.py status .
  python main.py history src/app.py
  python main.py recover src/app.py
  python main.py restore src/app.py
  python main.py restore src/app.py --id 2 --yes
  python main.py snapshots .
  python main.py clean .
        """
    )

    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to custom config.json"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose debug logging"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: watch
    watch_parser = subparsers.add_parser("watch", help="Start real-time filesystem monitoring")
    watch_parser.add_argument("directory", nargs="?", default=".", help="Project directory to monitor (default: .)")

    # Command: status
    status_parser = subparsers.add_parser("status", help="Display repository backup status")
    status_parser.add_argument("directory", nargs="?", default=".", help="Project directory (default: .)")

    # Command: history
    history_parser = subparsers.add_parser("history", help="Show snapshot history for a file")
    history_parser.add_argument("file", help="Path to source file")

    # Command: recover (interactive recovery wizard)
    recover_parser = subparsers.add_parser("recover", help="Interactive recovery wizard for a file")
    recover_parser.add_argument("file", help="Path to source file to recover")
    recover_parser.add_argument("-y", "--yes", action="store_true", help="Bypass confirmation prompt")

    # Command: restore
    restore_parser = subparsers.add_parser("restore", help="Restore a file from a snapshot")
    restore_parser.add_argument("file", help="Path to source file to restore")
    restore_parser.add_argument("--id", type=int, default=None, help="Snapshot ID to restore (optional)")
    restore_parser.add_argument("--to", type=str, default=None, help="Output path (never touches the original)")
    restore_parser.add_argument("--at", type=str, default=None, help="Time to restore to (e.g. 10m, 2h, HH:MM)")
    restore_parser.add_argument("-y", "--yes", action="store_true", help="Bypass overwrite confirmation prompt")

    # Command: snapshots
    snaps_parser = subparsers.add_parser("snapshots", help="List all saved snapshots in the project")
    snaps_parser.add_argument("directory", nargs="?", default=".", help="Project directory (default: .)")

    # Command: clean
    clean_parser = subparsers.add_parser("clean", help="Purge all snapshots and reset metadata")
    clean_parser.add_argument("directory", nargs="?", default=".", help="Project directory (default: .)")
    clean_parser.add_argument("-y", "--yes", action="store_true", help="Bypass confirmation prompt")

    # Command: deleted
    deleted_parser = subparsers.add_parser("deleted", help="Show previously tracked files that are currently missing")
    deleted_parser.add_argument("directory", nargs="?", default=".", help="Project directory (default: .)")

    # Command: restore-project
    restore_project_parser = subparsers.add_parser("restore-project", help="Restore the entire project to a specific point in time")
    restore_project_parser.add_argument("directory", nargs="?", default=".", help="Project directory to restore")
    restore_project_parser.add_argument("--at", type=str, required=True, help="Time to restore to (e.g. 10m, 2h, HH:MM)")
    restore_project_parser.add_argument("--dry-run", action="store_true", help="Preview what would happen without making changes")
    restore_project_parser.add_argument("-y", "--yes", action="store_true", help="Bypass confirmation prompt")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Initialize configuration
    config_path = Path(args.config) if args.config else None
    config = Config(config_path)

    # Setup logger
    log_level = "DEBUG" if args.verbose else config.log_level
    setup_logger(log_level=log_level)

    # Dispatch commands
    commands = {
        "watch": handle_watch,
        "status": handle_status,
        "history": handle_history,
        "recover": handle_recover,
        "restore": handle_restore,
        "snapshots": handle_snapshots,
        "clean": handle_clean,
        "deleted": handle_deleted,
        "restore-project": handle_restore_project,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args, config)


if __name__ == "__main__":
    main()

