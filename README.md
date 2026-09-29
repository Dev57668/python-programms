# Code Lifejacket — Accidental Delete Recovery System

> **A lightweight, real-time local shadow backup and accidental deletion recovery system for programmers.**  
> Built strictly with **100% pure Python 3** (no web servers, no JavaScript, no unnecessary runtime bloat).

---

## Table of Contents

- [The Problem](#the-problem)
- [The Solution](#the-solution)
- [Architecture & Storage](#architecture--storage)
- [Supported File Types](#supported-file-types)
- [Installation (Windows Quickstart)](#installation-windows-quickstart)
- [CLI Commands & Usage](#cli-commands--usage)
- [Example Recovery Scenario](#example-recovery-scenario)
- [Configuration (`config.json`)](#configuration-configjson)
- [Running Automated Tests](#running-automated-tests)
- [Limitations](#limitations)
- [Future Improvements](#future-improvements)

---

## The Problem

Every developer has faced this nightmare:
- Running `git checkout .` or `rm -rf` by mistake and wiping uncommitted work.
- Overwriting a complex algorithm while testing an experimental refactor.
- Accidentally hitting Delete on a file in an IDE without an undo buffer.
- Cloud drives or synchronization tools creating conflicts and losing code changes.

Traditional backup tools (like cloud sync or periodic system backups) are either too slow, too heavy, or fail to track rapid micro-changes made during active coding sessions. Git only protects what you explicitly commit or stash.

---

## The Solution

**Code Lifejacket** acts as an automatic safety net for your working directory:
1. **Real-time File Monitoring**: Uses Python's `watchdog` library to detect file creations and modifications instantly.
2. **Instant Timestamped Shadow Copies**: Every modification creates a preserved snapshot in a local `.lifejacket/snapshots/` folder.
3. **Smart Duplicate Prevention**: Calculates SHA-256 hashes of file contents; if you save without changing code, no redundant snapshot is created.
4. **Accidental Deletion Shield**: If a tracked source file is deleted, all past snapshots remain intact in `.lifejacket`, and a rescue incident is logged.
5. **Interactive & Safe Recovery**: Restore any previous version with a single command. Lifejacket **never overwrites** an existing file without explicit confirmation.
6. **Debounced & Resilient**: Handles rapid IDE multi-write bursts gracefully and shields against permission or file-locking crashes.

---

## Architecture & Storage

```
code-lifejacket/
├── main.py              # CLI entry point and argument parsing
├── watcher.py           # Real-time watchdog observer with debounce logic
├── backup.py            # Snapshot creation, deduplication, and retention engine
├── recovery.py          # Version history querying, safe file restore, status reporting
├── database.py          # Thread-safe JSON metadata store (.lifejacket/metadata.json)
├── config.py            # Settings loader and path rule validators
├── utils.py             # SHA-256 hashing, path math, formatting, logging
├── config.json          # User-configurable parameters
├── requirements.txt     # Dependencies (watchdog)
├── README.md            # System documentation
└── tests/               # Automated unit & E2E tests
    ├── test_backup.py
    ├── test_duplicate.py
    ├── test_history.py
    ├── test_restore.py
    ├── test_deletion.py
    └── test_e2e_cli.py
```

### Storage Layout Inside Watched Project

When Code Lifejacket monitors a project, it creates a hidden `.lifejacket` directory:

```
my_project/
├── .lifejacket/
│   ├── metadata.json                 # Tracks versions, SHA-256 hashes, deletion logs
│   └── snapshots/                    # Mirror directory structure
│       └── src/
│           ├── app.py.20260923_120000_123456.bak
│           └── app.py.20260923_121530_789012.bak
└── src/
    └── app.py
```

---

## Supported File Types

By default, Code Lifejacket monitors modern programming source files:
- Python (`.py`)
- Java (`.java`)
- C++ (`.cpp`)
- C (`.c`)
- JavaScript (`.js`)
- TypeScript (`.ts`)
- Go (`.go`)
- Rust (`.rs`)

*(You can add or remove extensions at any time in `config.json`)*.

---

## Installation (Windows Quickstart)

Open **PowerShell** or **Command Prompt** in the `code-lifejacket` project directory:

### 1. Create the virtual environment
```powershell
python -m venv venv
```

### 2. Activate the virtual environment
**In PowerShell:**
```powershell
.\venv\Scripts\Activate.ps1
```
*(If PowerShell restricts script execution, run: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`)*

**In Command Prompt (cmd.exe):**
```cmd
.\venv\Scripts\activate.bat
```

### 3. Install dependencies
```powershell
pip install -r requirements.txt
```

---

## CLI Commands & Usage

### 1. Start Watching a Directory
```powershell
# Watch the current directory
python main.py watch .

# Watch a specific project path
python main.py watch "C:\Users\dev maurya\Desktop\my_app"
```
*Lifejacket performs an initial scan on startup, catalogs existing source files, and continues monitoring in real-time. Press `Ctrl+C` to stop.*

### 2. View Repository Protection Status
```powershell
python main.py status
# Or specify a directory:
python main.py status .
```
Displays the professional real-time status dashboard:
```
============================================================
              CODE LIFEJACKET - STATUS
============================================================

Project:
C:\...\python project

Protection:
● ACTIVE

Protected Files:       15
Total Snapshots:       28
Deleted Files:          2
Total Backup Size:     142 KB
Last Snapshot:         2026-09-23 18:15:42

------------------------------------------------------------
FILE ACTIVITY
------------------------------------------------------------

File                     Snapshots    Status
------------------------------------------------------------
main.py                  5            ACTIVE
watcher.py               4            ACTIVE
victim.py                2            ACTIVE
calculator.py            3            DELETED

------------------------------------------------------------
STORAGE
------------------------------------------------------------

Lifejacket Directory: .lifejacket
Storage Used: 142 KB
Maximum Snapshots: 50
------------------------------------------------------------
```

### 3. View Snapshot History for a File
```powershell
python main.py history src/calculator.py
```
Example Output:
```
======================================================================
  Code Lifejacket - File History
======================================================================
File:       src/calculator.py
Status:     DELETED / MISSING (safe in Lifejacket backups)
Snapshots:  3 version(s) available
----------------------------------------------------------------------
ID    Timestamp             Size        Event       SHA-256 (Prefix)
----------------------------------------------------------------------
1     2026-09-23 12:00:15   420 B       created     a1b2c3d4e5f6    
2     2026-09-23 12:15:30   512 B       modified    e7f8a9b0c1d2    
3     2026-09-23 12:30:45   640 B       modified    4a5b6c7d8e9f    
======================================================================
To restore a version: python main.py restore src/calculator.py --id <ID>
```

### 4. Interactive Recovery Wizard
```powershell
python main.py recover src/calculator.py
```
Launches the interactive recovery wizard:
```
============================================================================
  CODE LIFEJACKET - RECOVERY
============================================================================
File Path:  src/calculator.py
Full Path:  C:\...\src\calculator.py
Status:     ACTIVE  (or DELETED / MISSING)

Available Snapshots (3 version(s)):
----------------------------------------------------------------------------
Selection | ID     | Timestamp            | Size       | Event      | SHA-256
----------------------------------------------------------------------------
1         | 1      | 2026-09-23 12:00:15  | 420 B      | created    | a1b2c3d4e5f6
2         | 2      | 2026-09-23 12:15:30  | 512 B      | modified   | e7f8a9b0c1d2
3         | 3      | 2026-09-23 12:30:45  | 640 B      | modified   | 4a5b6c7d8e9f [LATEST]
----------------------------------------------------------------------------
[0] Cancel recovery
============================================================================
Select snapshot number (1-3) [Default: 3 (latest)]: 2

----------------------------------------------------------------------------
  Selected Snapshot Details
----------------------------------------------------------------------------
Selection:        2
Snapshot ID:      #2
Timestamp:        2026-09-23 12:15:30
Size:             512 B
Event:            modified
SHA-256 Prefix:   e7f8a9b0c1d2
SHA-256 Full:     e7f8a9b0c1d2...
Target Path:      C:\...\src\calculator.py

[WARNING] Current file exists and will be OVERWRITTEN!
----------------------------------------------------------------------------
Proceed with restoration? (y/N): y

[Success] Restored 'src/calculator.py' from Snapshot #2
```

### 5. Direct Restoration by Snapshot ID
```powershell
# Restore a specific snapshot ID directly
python main.py restore src/calculator.py --id 2

# Restore and bypass confirmation prompt (ideal for scripting)
python main.py restore src/calculator.py --id 2 --yes
```

### 6. List All Saved Snapshots
```powershell
python main.py snapshots .
```
Lists every shadow copy created across the entire project.

### 7. Clean Snapshots
```powershell
python main.py clean .
# Or without prompt:
python main.py clean . --yes
```
Purges the `.lifejacket/snapshots/` folder and resets metadata.

---

## Example Recovery Scenario

### Step 1: Start Lifejacket Watcher
```powershell
python main.py watch .
```

### Step 2: You write code in `service.py`
```python
def process_payment(amount):
    print(f"Processing ${amount}")
```
*Lifejacket automatically saves Snapshot #1.*

### Step 3: You modify and test new changes
```python
def process_payment(amount):
    # Experimental refactor
    raise Exception("Payment gateway error")
```
*Lifejacket automatically saves Snapshot #2.*

### Step 4: Accidental Disaster strikes!
You accidentally delete `service.py`:
```powershell
Remove-Item service.py
```
Lifejacket's watcher instantly alerts you:
```
[LIFEJACKET RESCUE ALERT] Tracked file was deleted: 'service.py'!
                         Previous versions are safely preserved in .lifejacket.
                         Run 'python main.py restore service.py' to recover.
```

### Step 5: Check Status & Recover
```powershell
python main.py status .
```
Output shows `service.py` marked as **DELETED (Recoverable)**.

Now recover Version 1 (before the bug was introduced):
```powershell
python main.py restore service.py --id 1 --yes
```
Output:
```
[Success] Restored 'service.py' from Snapshot #1
          Created at: 2026-09-23 12:00:15
          Restored to: C:\...\service.py
```
Your code is back instantly!

---

## Configuration (`config.json`)

You can customize Lifejacket behavior by editing `config.json`:

```json
{
  "monitored_extensions": [
    ".py",
    ".java",
    ".cpp",
    ".c",
    ".js",
    ".ts",
    ".go",
    ".rs"
  ],
  "ignored_directories": [
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "env",
    "__pycache__",
    ".lifejacket",
    ".idea",
    ".vscode"
  ],
  "max_snapshots": 50,
  "debounce_time": 1.0,
  "snapshot_directory_name": ".lifejacket",
  "log_level": "INFO"
}
```

- **`monitored_extensions`**: File extensions to track.
- **`ignored_directories`**: Folders that will be ignored during recursive scanning.
- **`max_snapshots`**: Maximum number of snapshots preserved per file before the oldest is pruned.
- **`debounce_time`**: Seconds to wait after a write event to prevent redundant backups during rapid typing or multi-write editor flushes.
- **`snapshot_directory_name`**: Hidden folder name (default: `.lifejacket`).

---

## Running Automated Tests

Run the test suite using Python's built-in `unittest` framework:

```powershell
python -m unittest discover -s tests -v
```

This verifies:
- Snapshot creation and relative folder hierarchy preservation
- Duplicate detection via SHA-256 hashing
- Snapshot history retrieval and ordering
- File restoration and overwrite safety
- Deletion detection and archive preservation
- End-to-end CLI execution

---

## Limitations

1. **Local Filesystem Scope**: Snapshots are stored locally on your machine inside `.lifejacket`. If your physical drive fails, Lifejacket does not provide off-site cloud replication.
2. **Text & Source Files Optimized**: Designed specifically for source code files, not massive binary blobs (like large `.mp4` or `.iso` files).
3. **Editor Atomic Saves**: Some editors write to a temporary file and atomically rename it over the original. Lifejacket's debounce mechanism handles this, but debounce window should be kept at 1.0s or higher on slower disks.

---

## Future Improvements

- **Visual Unified Diff View**: Add a `python main.py diff <file> --id <ID>` command to show side-by-side terminal syntax diffs using standard `difflib`.
- **Git Hook Integration**: Automatically trigger a snapshot whenever a Git rebase, reset, or checkout operation begins.
- **Compressed Snapshots**: Add optional `.gz` compression for snapshot files to minimize disk footprint on large projects.
- **Custom Project Ignore Rules**: Support reading `.gitignore` files automatically in addition to `config.json`.
