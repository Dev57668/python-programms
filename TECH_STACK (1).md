# CodeVault: Tech Stack

**Principle:** pure Python, minimal dependencies. Only `watchdog` is a runtime dependency; everything else is the standard library.

## Runtime

| Concern | Choice | Why |
|---------|--------|-----|
| Language | Python 3.10+ | Modern typing, `pathlib`, widely available |
| File monitoring | `watchdog` | Cross-platform real-time filesystem events |
| Hashing | `hashlib` (SHA-256) | Content-addressed dedupe; detects identical saves |
| Copying | `shutil` + temp file + `os.replace` | Fast, atomic writes so the store can't be half-written |
| Metadata | `sqlite3` (stdlib) | Zero-install, transactional, queryable history |
| Timestamps | `datetime` (UTC, ISO-8601) | Sortable, timezone-safe |
| CLI | `argparse` (subcommands) | No dependency, good enough for this command set |
| Diffs | `difflib` (unified diff) | Stdlib, no external tool required |
| Compression (optional) | `zlib` / `gzip` | Shrinks stored snapshots; toggle in config |
| Ignore matching | `fnmatch` / `pathlib.match` | Simple glob rules |
| Logging | `logging` with `RotatingFileHandler` | Daemon log without unbounded growth |
| Terminal colour | plain ANSI codes (auto-disabled when not a TTY / `NO_COLOR` set) | Keeps it dependency-free |
| Config | `json` (`config.json`) | Already used in the repo |
| Background process | `subprocess` detach + PID file (cross-platform) | No daemon library needed |

## Development

| Concern | Choice |
|---------|--------|
| Tests | `pytest` (+ `pytest-cov`), `tmp_path` fixtures for isolated projects |
| Lint / format | `ruff` (lint + format) |
| Types (optional) | `mypy` |
| Packaging | `pyproject.toml` with a `[project.scripts]` entry: `codevault = codevault.cli:main` |
| CI | GitHub Actions: pytest on 3.10 / 3.11 / 3.12, on Ubuntu and macOS |
| IDE | Antigravity |
| VCS | Git + GitHub, feature branches + Pull Requests |

## Suggested project layout

```
python-programms/            (consider renaming repo to `codevault`)
├── pyproject.toml
├── README.md
├── LICENSE                  (MIT)
├── .gitignore
├── docs/                    (PRD, TECH_STACK, SCHEMA, DESIGN, TASKS)
├── src/codevault/
│   ├── __init__.py
│   ├── cli.py               (argparse; formerly main.py)
│   ├── config.py
│   ├── database.py
│   ├── watcher.py
│   ├── backup.py            (snapshot creation)
│   ├── recovery.py          (restore, restore-project, diff)
│   ├── retention.py         (clean, purge, garbage collection)
│   ├── daemon.py            (start/stop, PID, logging)
│   └── utils.py
└── tests/
```

The current flat layout works. Move to `src/` only if you're both ready to update imports in one coordinated PR.

## Dependencies file

`requirements.txt` (or `pyproject.toml`):
```
watchdog>=4.0
```
Dev extras: `pytest`, `pytest-cov`, `ruff`.
