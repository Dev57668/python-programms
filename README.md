# CodeVault

CodeVault is a lightweight local shadow-backup tool for developers. It watches a project directory and preserves timestamped snapshots of source files so uncommitted work can be recovered after accidental deletion, overwrite, or unwanted changes.

**CodeVault complements Git. It does not replace Git.**
While Git is for commits, branches, collaboration, and remote history, CodeVault provides local protection of recent/uncommitted states, rapid snapshot recovery, and protection from accidental local deletion/overwrite.

## The Problem
A developer can spend hours editing code before committing it. An accidental delete, overwrite, or unwanted change can destroy that uncommitted work instantly.

## The Solution
CodeVault watches your local directory and saves continuous file snapshots in the background. If you make a mistake before you've had a chance to `git commit`, CodeVault lets you review history, diff versions, and instantly restore your file.

## Features
- **Real-time file monitoring**: Background daemon silently watches for file modifications.
- **Source-code snapshots**: Captures versions of your files as they change.
- **SHA-256 deduplication**: Only stores files when content actually changes.
- **SQLite metadata storage**: Fast and robust transactional storage.
- **Atomic snapshot writing & restoration**: Safe operations that won't corrupt your files.
- **Pre-restore protection**: Creates an automatic backup of the current file state before applying any restoration.
- **Snapshot history & Diff**: Easily view timeline events and unified diffs.
- **Deleted-file recovery**: Safely recovers files that were accidentally deleted.
- **Project restore**: Restore the entire project to a specific historical time.
- **Rename/move tracking**: Retains file history even if the file is moved or renamed.
- **Glob ignore patterns**: Fully ignores node_modules, build directories, or standard git paths.
- **Retention policies & Pinned snapshots**: Automatically prunes old snapshots unless explicitly pinned.
- **Purge & Cleanup**: Tools to completely wipe or clean up snapshots.

## Installation

Create a virtual environment:
```bash
python3 -m venv .venv
```

Activate it:
* macOS/Linux: `source .venv/bin/activate`
* Windows: `.venv\Scripts\activate`

Install the package in editable mode:
```bash
python -m pip install -e .
```

Verify the installation:
```bash
codevault --help
```
*(Note: `python main.py --help` remains fully supported as a compatibility launcher).*

## Quick Start

1. Enter a project directory.
2. Start CodeVault watching in the background:
   ```bash
   codevault start .
   ```
3. Edit and save source files.
4. Check status:
   ```bash
   codevault status .
   ```
5. View history of a file:
   ```bash
   codevault history src/app.py
   ```
6. Recover an accidentally deleted or modified file interactively:
   ```bash
   codevault recover src/app.py
   ```

## Complete CLI Reference

`codevault watch <dir>`
Start real-time filesystem monitoring in the foreground.

`codevault start <dir>`
Start the CodeVault watcher daemon in the background.

`codevault stop <dir>`
Stop the CodeVault watcher daemon.

`codevault status <dir>`
Display repository backup status and daemon state.

`codevault history <file>`
Show snapshot history for a specific file.

`codevault recover <file>`
Interactive step-by-step recovery wizard for a file.

`codevault restore <file>`
Restore a file from a snapshot.
*Example:* `codevault restore src/app.py --id 2 --yes`

`codevault restore-project <dir>`
Restore the entire project to a specific point in time.
*Example:* `codevault restore-project . --at "2026-10-04 15:30:00" --dry-run`

`codevault deleted <dir>`
Show previously tracked files that are currently missing/deleted.

`codevault snapshots <dir>`
List all saved snapshots in the project.

`codevault pin <file> --id <ID>`
Pin a snapshot to prevent it from being deleted during cleanup.

`codevault unpin <file> --id <ID>`
Unpin a previously pinned snapshot.

`codevault pins <dir>`
List all pinned snapshots in the project.

`codevault clean <dir>`
Perform retention cleanup (pruning unpinned snapshots exceeding retention policies).

`codevault purge <dir>`
Delete all local CodeVault snapshots and metadata.

`codevault verify <dir>`
Verify integrity of all snapshots against their expected SHA-256 hashes.

`codevault diff <file> --from <ID> --to <ID>`
Show a unified diff between two snapshots.

`codevault timeline <path>`
Show chronological events (snapshot creations, deletions, renames) for a file or directory.

`codevault config show <dir>`
Display current configuration settings.

`codevault config set <dir> <key> <value>`
Update a configuration setting.

## Recovery Example
1. Developer edits `src/utils.py`. CodeVault creates snapshots in the background.
2. Developer accidentally deletes `src/utils.py`.
3. Running `codevault deleted .` shows the missing file.
4. Running `codevault history src/utils.py` displays the available historical snapshots.
5. Developer runs `codevault recover src/utils.py`. The interactive wizard previews the content, diffs the changes, and allows restoring the selected version seamlessly.

## Configuration
Configuration is maintained automatically in `.lifejacket/config.json`.
You can update configuration using the CLI:
`codevault config set . <key> <value>`

Supported keys:
- `max_snapshots`: Maximum number of unpinned snapshots to retain per file (Integer).
- `max_age_days`: Maximum age in days for unpinned snapshots (Integer).
- `ignore_patterns`: List of glob patterns to ignore (e.g. `**/node_modules`, `*.tmp`).

*(Note: Configuration changes only take effect after the daemon is restarted).*

## Safety Model
CodeVault takes extreme precautions to ensure your data is safe:
- **Pre-restore protection**: Restoring a file will automatically create a backup of its current overwritten state.
- **Atomic operations**: Snapshot writes and project restorations are fully atomic, eliminating partial-write corruption.
- **SHA-256 Integrity**: `codevault verify` can cryptographically validate that your snapshots are mathematically perfect.
- **Pinned snapshots**: Important snapshots can be pinned and will always survive retention purges.
- **Project-local**: Data stays tightly bound to the project boundary in `.lifejacket/`. CodeVault will never scan or destroy files outside of the project root.

*Limitations*: CodeVault is an emergency local recovery tool. It does not replace offsite backups or Git remotes.

## Storage Layout
CodeVault stores all runtime data directly in the local project directory inside `.lifejacket`. The Python package installation handles the logic, but the data is strictly project-local.

```text
project/
├── source_code.py
└── .lifejacket/
    ├── vault.db        (SQLite Database)
    ├── daemon.json     (Daemon PID state)
    ├── config.json     (Project configuration)
    └── snapshots/      (SHA-256 indexed snapshot files)
```

## Architecture
```text
codevault/
├── __init__.py       (Version details)
├── cli.py            (Argparse CLI routing & command logic)
├── daemon.py         (Background detachment & lifecycle manager)
├── watcher.py        (Watchdog filesystem event listener)
├── backup.py         (Orchestration & file ingestion)
├── database.py       (SQLite schema & transactional metadata)
├── recovery.py       (Diffing, timelines, restoration execution)
└── utils.py          (Hashing, formatting, atomic copy helpers)
```
**Flow:**
User → `CLI` → `Watcher / Daemon` → `Backup Engine` → `SHA-256 + Atomic Copy` → `SQLite Metadata` → `Recovery / Diff`

## Testing & CI
Run the comprehensive test suite with:
```bash
pytest -q
```
*Current test count: 100 tests (Passing).*
A GitHub Actions CI workflow (`.github/workflows/tests.yml`) executes the entire suite across macOS, Linux, and Windows matrices.

## License
MIT License
