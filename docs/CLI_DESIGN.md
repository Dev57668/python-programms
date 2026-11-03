# CodeVault: Design (CLI / Terminal UX)

There is no GUI, so "design" here means the **command language, terminal output, and safety behaviour**. Consistency matters more than decoration.

## Principles
1. **Silent when working, clear when asked.** The watcher logs to a file; the CLI prints only what the user needs.
2. **Never destructive by surprise.** Restores keep a copy of what they overwrite; deletes preview first or ask to confirm.
3. **Actionable errors.** Say what went wrong *and* what to do next.
4. **Scriptable.** Plain text works when piped; `--json` on read commands for tooling.
5. **Accessible.** No information carried by colour alone; honour `NO_COLOR` and non-TTY output.

## Command tree

```
codevault init                              Create the store in the current project
codevault start [--foreground]              Start the background watcher
codevault stop                              Stop the watcher
codevault status [--json]                   Dashboard
codevault timeline [PATH] [--limit N] [--json]
codevault diff PATH [--from ID] [--to ID]   Default: latest snapshot vs current file
codevault restore PATH [--id ID | --at TIME] [--to OUTPUT_PATH] [--yes]
codevault restore-project --at TIME [--dry-run] [--yes]
codevault deleted [--json]                  List deleted files that can be recovered
codevault pin ID / unpin ID                 Protect a snapshot from cleanup
codevault clean [--dry-run]                 Apply retention rules
codevault purge [--yes]                     Delete ALL snapshots (asks for confirmation)
codevault verify                            Integrity check
codevault config show | set KEY VALUE
```

**Time format for `--at`:** ISO (`2026-09-29T14:30`), a time today (`14:30`), or relative (`10m`, `2h`, `1d`).

## Semantic colours
| Meaning | Colour | Also shown as |
|---------|--------|---------------|
| Success | green | `✔` (or `OK`) |
| Warning | yellow | `!` |
| Error | red | `✖` (or `ERROR`) |
| Deleted / destructive | red | `[deleted]` text |
| Secondary info (ids, times) | dim | n/a |
| Pinned | cyan | `[pinned]` text |

## Output mockups

### `status`
```
CodeVault  ·  /Users/you/assignment-3
Watcher        running (pid 4821)
─────────────────────────────────────
Protected files      42
Total snapshots      318
Deleted (recoverable) 3
Storage used         1.4 MB
Retention            50 per file · 30 days
Last snapshot        12s ago  (src/main.py)
```

### `timeline src/main.py`
```
src/main.py   ·  7 snapshots
 ID    WHEN                 EVENT     SIZE
 318   2026-09-29 14:31:05  modify    2.1 KB
 311   2026-09-29 14:12:40  modify    1.9 KB  [pinned]
 297   2026-09-29 13:02:11  create    1.2 KB
Restore one with:  codevault restore src/main.py --id 311
```

### `clean --dry-run`
```
Would remove 24 snapshots (410 KB) across 6 files. Pinned snapshots are kept.
No changes were made. Run `codevault clean` to apply.
```

### `restore` (safe)
```
Current src/main.py differs from snapshot 311.
✔ Saved current version as snapshot 319 (pre_restore)
✔ Restored src/main.py to snapshot 311 (2026-09-29 14:12:40)
```

### `purge`
```
This permanently deletes ALL 318 snapshots (1.4 MB) for this project.
Type the project folder name to confirm:
```

### Errors
```
✖ No snapshot found for 'src/mian.py'.
  Did you mean 'src/main.py'?  List files with: codevault timeline
```

## Behaviour rules
- **Restore:** if the target exists, create a `pre_restore` snapshot first; then write atomically. `--to` restores to a different path and never touches the original.
- **Restore-project:** always show a summary of files that will change, be added, or be removed; require `--yes` or interactive confirmation; `--dry-run` shows the plan only.
- **Diff:** unified diff, additions green, removals red; if output is not a TTY, plain unified diff (works with `patch`).
- **Purge:** requires typing the project folder name (or `--yes` in scripts).
- **Exit codes:** `0` success · `1` general error · `2` bad usage · `3` nothing to do / not found.
- **Help:** every subcommand has a one-line description and at least one example in `--help`.

## README structure (for the project page)
1. One-line pitch + "not a Git replacement" note
2. Install (`pip install .`) and 60-second quick start
3. Real `status` and `timeline` output (from the mockups above, replaced with real runs)
4. Command reference (table)
5. How it works (watcher → hash → dedupe → store → retention)
6. Configuration
7. Contributing + MIT license
