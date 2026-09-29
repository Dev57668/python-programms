# CodeVault: Product Requirements Document

## 1. Overview
CodeVault is a 100% Python, local-only "shadow backup" tool. A background watcher runs inside a project folder and silently saves a timestamped snapshot of every code file each time it is saved. If a file is overwritten, corrupted, or deleted before it was ever committed, the developer can recover it with one CLI command.

**It does not replace Git.** Git protects committed history. CodeVault protects the work that has *not* been committed yet.

## 2. Problem
Students and developers lose work by accident: overwriting a file with the wrong version, `rm` on the wrong path, a bad find-and-replace, an IDE crash, or a merge gone wrong. Git can't help when nothing was committed. Editor undo history disappears when the editor closes.

## 3. Goals
- G1. Never lose more than a few seconds of saved work.
- G2. Zero-effort: start once, forget it, runs silently.
- G3. Storage-efficient: identical content is stored once; old snapshots are cleaned up automatically.
- G4. Recovery is simple and safe: a few commands, never destructive by surprise.
- G5. Minimal dependencies, easy to install, runs on macOS/Linux/Windows.

## 4. Non-Goals
- No GUI, no web framework, no cloud sync, no accounts.
- Not a Git replacement: no branching, merging, or remotes.
- No binary/large-file backup (configurable size cap).
- No cross-machine sharing in v1.

## 5. Target Users
1. Students working on programming assignments (primary).
2. Solo developers on small projects.
3. Anyone who wants an "undo safety net" beneath Git.

## 6. User Stories
- As a user, I run `init` and `start` once and CodeVault protects my project automatically.
- As a user, I can see what is protected and how much space it uses (`status`).
- As a user, I can see the history of a file (`timeline`) and what changed between versions (`diff`).
- As a user, I can restore a file to any earlier snapshot without losing the current version.
- As a user, I can recover a file I deleted, or roll a whole project back to a point in time.
- As a user, I can preview cleanup with `--dry-run` before anything is deleted.
- As a user, I can pin an important snapshot so cleanup never removes it.

## 7. Functional Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| FR-1 | Watch a project folder recursively for create/modify/delete/move events (watchdog) | Done |
| FR-2 | Snapshot a file on save; hash with SHA-256; skip if identical to the latest snapshot | Done |
| FR-3 | Store snapshot metadata in SQLite; content in a hidden local store | Done |
| FR-4 | `restore` a file to a previous snapshot | Done |
| FR-5 | `status` dashboard: protected files, total snapshots, deleted files, storage used | Done |
| FR-6 | Automatic retention: remove oldest snapshots past the configured limit | Done |
| FR-7 | `clean --dry-run` and `purge` (explicit, confirmed delete-all) | Done |
| FR-8 | `timeline`: mini local version history per file/project | Done |
| FR-9 | `diff`: show what changed between two snapshots, or snapshot vs. current | To verify/build |
| FR-10 | Deleted-file tracking and `deleted` listing + restore | To verify/build |
| FR-11 | Project-level restore to a point in time (`restore-project --at`) | To build |
| FR-12 | Debounce rapid save events; handle editors that save via temp-file + rename | To build |
| FR-13 | Ignore rules (`.git`, `__pycache__`, `.venv`, `node_modules`, the store itself, custom globs) | To build |
| FR-14 | Background daemon control: `start`, `stop`, PID file, log file, single instance per project | To build |
| FR-15 | Safe restore: always snapshot the current file first ("pre-restore" snapshot) | To build |
| FR-16 | `pin` / `unpin` snapshots exempt from retention | To build |
| FR-17 | `verify`: integrity check (hashes match stored blobs, no orphan rows/files) | To build |
| FR-18 | Config file with validation and `config show/set` | To verify |
| FR-19 | Installable package with a `codevault` console command | To build |

## 8. Non-Functional Requirements
- **Reliability:** a crash mid-snapshot must never corrupt the store (write temp file, then atomic rename; SQLite WAL + transactions).
- **Performance:** snapshot of a typical source file < 50 ms; idle CPU near zero.
- **Privacy:** all data stays on the local machine.
- **Safety:** destructive commands require confirmation or an explicit `--yes`.
- **Portability:** use `pathlib`; no OS-specific code without a fallback.
- **Quality:** pytest suite covering snapshot, dedupe, retention, restore, delete handling; runs in CI.

## 9. CLI Surface (summary)
`init`, `start`, `stop`, `status`, `timeline`, `diff`, `restore`, `restore-project`, `deleted`, `pin`, `unpin`, `clean`, `purge`, `verify`, `config`. Full behaviour is defined in `DESIGN.md`.

## 10. Success Metrics
- A deleted or overwritten file is recoverable in under 30 seconds using the CLI.
- Duplicate saves add no new storage.
- Storage stays within the configured limits under a 1-hour simulated editing session.
- Test suite passes on Python 3.10, 3.11, and 3.12.

## 11. Risks
| Risk | Mitigation |
|------|------------|
| Editors fire many events per save | Debounce (e.g. 300–500 ms) per path |
| Atomic-save editors delete and recreate files | Treat rename-over as a modify; confirm before flagging as deleted |
| Store grows unbounded | Retention by count and age, plus orphan-blob garbage collection |
| Watcher snapshots its own store | Always ignore the store directory |
| Two processes writing the DB | PID lock file, SQLite WAL, short transactions |

## 12. Milestones
1. **M1: Hardening:** ignore rules, debounce, safe restore, `.gitignore` cleanup.
2. **M2: Recovery features:** diff, deleted files, project restore, pin.
3. **M3: Daemon and packaging:** start/stop, PID, logs, `pyproject.toml`, console script.
4. **M4: Quality:** tests, `verify`, CI, README with examples, v1.0 release.
