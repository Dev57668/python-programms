# CodeVault: Remaining Work and Prompts

> I could not see your source code, only the repo file list. Each task starts with an **audit step**: ask the agent to check what already exists before it builds anything. Skip tasks that turn out to be done.

## How to use this file
1. Put the five docs in a `docs/` folder in the repo (`PRD.md`, `TECH_STACK.md`, `SCHEMA.md`, `DESIGN.md`, `TASKS.md`).
2. Start each Antigravity session with the **Master Prompt**.
3. Do one task per branch: `git checkout -b feature/<task-name>` → prompt → run tests → commit → push → Pull Request.
4. Review the diff before accepting. Don't let the agent rewrite files you didn't ask about.

---

## Master Prompt (paste first, every session)

```
You are helping me finish "CodeVault", a 100% Python local code-recovery tool.
Read docs/PRD.md, docs/TECH_STACK.md, docs/SCHEMA.md and docs/DESIGN.md first and follow them.

Rules:
- Pure Python. The only runtime dependency is `watchdog`. No GUI, no web framework.
- Do not rewrite working code. Make the smallest change that completes the task.
- Snapshot writes must be atomic (temp file + os.replace, SQLite transaction).
- Use pathlib. Store project-relative paths with forward slashes.
- Destructive operations must be previewable or confirmed.
- Add or update pytest tests for everything you change, and run them.
- Before editing, list the files you will touch and why. After editing, summarise what changed.
```

---

## Suggested split between the two of you

| Person A: core engine | Person B: CLI, quality, release |
|---|---|
| T1 Repo cleanup *(do together first)* | T1 Repo cleanup *(do together first)* |
| T3 Ignore rules + debounce | T6 `diff` command |
| T4 Safe restore | T8 Daemon start/stop |
| T5 Deleted files + project restore | T9 Packaging |
| T2 Schema audit/migration | T10 Tests + CI |
| T7 Pin + `verify` | T11 README + release |

Agree who owns each file to avoid merge conflicts: A owns `watcher.py`, `backup.py`, `database.py`, `recovery.py`; B owns `main.py`/CLI, `daemon.py`, `tests/`, `README.md`, `pyproject.toml`.

---

## T1: Repo cleanup (M1)

**Do:** add `.gitignore`, untrack generated files, add LICENSE and description, decide the store folder name, move `victim.py` into `tests/` or `examples/`.

```
Audit the repo. Then:
1. Create .gitignore with __pycache__/, *.pyc, .venv/, .lifejacket/, .DS_Store, .pytest_cache/, dist/, *.egg-info/.
2. Give me the git commands to untrack __pycache__ and .lifejacket without deleting them locally.
3. Check where victim.py is used; if it is only a test target, propose moving it under tests/ and update any references.
4. Check config.json vs config.py and tell me which is the source of truth; propose one consolidation with minimal changes.
Do not change any application logic.
```

**Done when:** `git status` is clean after running the tool, and the repo shows no `__pycache__` or store data.

## T2: Schema audit and migration (M1)

```
Read docs/SCHEMA.md and database.py. Produce a table comparing the current schema to the target:
tables/columns that already match, that differ, and that are missing.
Then implement a `schema_version` in a `meta` table and a small migration function that upgrades an existing
database to the target schema without losing snapshots. Add tests that migrate a database created with the OLD
schema (create one in the test fixture). Do not change snapshot or restore logic yet.
```

## T3: Ignore rules and debounce (M1)

```
In watcher.py:
1. Load `ignore` globs and `watch_extensions` from config. Always ignore the store directory itself, .git,
   __pycache__, .venv, node_modules.
2. Debounce events per path (config `debounce_ms`, default 400): many events for one save must produce ONE snapshot.
3. Handle editors that save by writing a temp file and renaming it over the original: treat that as a modify, not a
   delete + create. Only mark a file deleted if it is still missing after the debounce window.
4. Skip files larger than `max_file_size_mb`.
Write pytest tests using tmp_path that simulate rapid repeated writes and an atomic-rename save.
```

## T4: Safe restore (M1)

```
In recovery.py, make `restore PATH [--id ID | --at TIME] [--to OUTPUT_PATH] [--yes]` safe:
- If the target file exists and differs from the snapshot, first create a `pre_restore` snapshot of it.
- Write the restored content atomically.
- `--to` restores to another path and never touches the original.
- Print output in the style of docs/DESIGN.md.
- Implement the `--at` time parser: ISO datetime, HH:MM today, or relative (10m, 2h, 1d).
Add tests: restore over a modified file (pre_restore snapshot exists), restore with --to, restore of an unknown id.
```

## T5: Deleted files and project restore (M2)

```
Audit whether deleted files are tracked (files.status / deleted_at / a 'delete' event). Implement what is missing per
docs/SCHEMA.md, including resurrection when a deleted path reappears. Then add:
- `codevault deleted` listing recoverable files.
- `codevault restore PATH` working for a deleted file (recreate it).
- `codevault restore-project --at TIME [--dry-run] [--yes]` using the "project state at time T" query in SCHEMA.md.
  Show a summary of files to change/add/remove first; require confirmation or --yes; take pre_restore snapshots of
  anything overwritten.
Tests: delete then recover, project restore on a 3-file fixture with a deleted file, dry-run changes nothing.
```

## T6: `diff` command (M2)

```
Add `codevault diff PATH [--from ID] [--to ID]` using difflib.unified_diff. Default compares the latest snapshot to
the current file on disk. Colour additions green and removals red only when stdout is a TTY and NO_COLOR is unset.
Handle binary/non-UTF-8 files by printing "binary files differ". Add tests for text diff, identical files, and binary.
```

## T7: Pin and verify (M2 → M4)

```
1. Add `pin ID` / `unpin ID` (snapshots.pinned). Make retention (`clean` and automatic) never delete pinned
   snapshots and always keep each file's latest snapshot. Show [pinned] in timeline.
2. Add `verify`: for every blob row check the file exists and its SHA-256 matches; report orphan files in objects/
   with no row, rows with no file, and snapshots pointing at missing blobs. Exit code 0 if clean, 1 otherwise.
   Do not auto-fix; only report.
3. After retention runs, garbage-collect blobs no snapshot references.
Add tests for each.
```

## T8: Daemon control (M3)

```
Implement `start`, `stop` and `start --foreground`:
- `start` launches the watcher as a detached background process, writes daemon.pid in the store directory, and
  refuses to start a second instance for the same project (check that the PID is actually alive).
- `stop` terminates it and removes a stale PID file safely.
- Log to daemon.log with RotatingFileHandler (1 MB x 3).
- `status` shows running / not running (pid).
Must work on macOS and Linux; use a Windows-safe approach for process creation flags. No new dependencies.
Add tests for the pid-file logic (mock the process check).
```

## T9: Packaging (M3)

```
Add pyproject.toml so `pip install .` provides a `codevault` command (console script → the CLI main()).
Runtime dependency: watchdog>=4.0. Optional dev extras: pytest, pytest-cov, ruff. Set the project name, version
0.1.0, MIT license, requires-python >=3.10. If moving to a src/codevault package layout, do it in ONE commit and fix
all imports and tests. Verify in a fresh venv: `pip install .` then `codevault --help`.
```

## T10: Tests and CI (M4)

```
Audit tests/ and report coverage with pytest --cov. Fill gaps so these are covered: snapshot creation, duplicate
detection, retention (count + age + pinned), clean --dry-run makes no changes, purge, restore, deleted-file
recovery, status numbers. Use tmp_path fixtures so tests never touch a real project. Add
.github/workflows/ci.yml: run pytest on Python 3.10/3.11/3.12 on ubuntu-latest and macos-latest.
```

## T11: README and release (M4)

```
Rewrite README.md using the structure at the end of docs/DESIGN.md: pitch and "not a Git replacement" note,
install, 60-second quick start, command reference table, how it works, configuration, contributing, license.
Use real command output, not invented output. Then propose CHANGELOG.md for v1.0.0 and the git commands to tag
and create a GitHub release.
```

---

## Definition of done for v1.0
- [ ] All PRD requirements FR-1 → FR-19 implemented or consciously deferred
- [ ] CI green on all matrix jobs
- [ ] `pip install .` then `codevault init && codevault start` works from a clean venv
- [ ] Repo has `.gitignore`, LICENSE, README with real output, tagged release
- [ ] Both teammates have merged at least one PR
