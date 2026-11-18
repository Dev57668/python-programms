# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

- Both pages are vanilla HTML/CSS/JS in `codevault/web/static/`, served by the stdlib `http.server` in `codevault/web/server.py` (`codevault ui`). No build step, no new dependencies.
- Landing page at `/`: tells the story of the product as the visitor scrolls, and links to the dashboard.
- Dashboard at `/dashboard`.

## Users

Developers, students and small teams who keep the dashboard open next to their editor (and AI coding tools such as Claude Code and Antigravity) while they work, glancing at it occasionally rather than staring at it. The landing page addresses developers deciding whether to install CodeVault.

## Product Purpose

CodeVault is a local shadow backup for source code. It watches a project, saves a timestamped, SHA-256-verified snapshot of each source file on every save, and lets the developer browse history, diff versions and restore deleted or overwritten files. It complements Git, it does not replace it: Git holds what was committed and pushed, CodeVault holds everything in between.

Success: a developer never loses uncommitted work, and can tell at a glance whether their work is safe.

## Positioning

The only copy of work that was never committed. CodeVault compares every snapshot with the project's Git history and labels it as on GitHub, committed but not pushed, or only on this machine, and records which AI tool made an edit (Claude Code hooks, labelled checkpoints for other tools).

## Operating Context

- Runs locally; the dashboard binds to 127.0.0.1 only. Started with `codevault ui .` from a project folder.
- The watcher runs as a background process (`codevault start`), or is started from the dashboard.
- Used alongside Git/GitHub and AI coding assistants that edit files directly.
- The dashboard's first job is answering "is my work safe?": watcher running, and how much work exists only on this machine.

## Capabilities and Constraints

- Real-time snapshots with debounce, SHA-256 dedupe, atomic writes, SQLite metadata, retention (max snapshots per file, max age) and pinning.
- History, unified diffs (between snapshots and against the current file), restore with an automatic pre-restore snapshot, deleted-file recovery, project restore to a point in time, integrity verification.
- Git awareness (read-only; "Check GitHub" runs `git fetch`), switching projects or cloning a GitHub URL from the dashboard.
- AI attribution: `codevault hooks install claude`, `codevault snapshot --source <tool>`.
- Monitored file types by default: `.py .js .ts .java .c .cpp .go .rs`.
- Pure Python; only runtime dependency is `watchdog`. MIT licensed.
- Terminology: "snapshot" (a saved copy), "watcher", "restore", "pin", "checkpoint". Do not call snapshots "versions" or "backups" in the UI.

## Brand Commitments

- Theme (user-confirmed, binding, latest): LIGHT ONLY — no dark theme. The look must be distinctive and clearly tied to CodeVault's own idea (snapshots between commits, git, safety), never generic or "AI-looking".
- Superseded: the dark navy/green look of commit 496e973 (user later said it looked plain and AI-generated).
- Rejected by the user: a grey-steel and brass "deposit box wall" redesign (archived in `.impeccable/archive/vault-redesign/`): its colours, the box wall, its plainness, and its fonts and layout.
- Standing user complaints that every design must answer: no pill shapes, far fewer icons, less data on any one page, nothing that looks AI-generated.

## Evidence on Hand

- README.md, PRD.md, docs/CLI_DESIGN.md (CLI output design), TASKS.md, SCHEMA.md, and a 123-test pytest suite with CI.
- No users, testimonials, download counts, benchmarks or press exist. Never invent them.

## Product Principles

1. Safety first: the state of the user's work is always the first thing shown.
2. Never destructive by surprise: restores keep a copy of what they overwrite, destructive actions name their consequence.
3. Quiet while working, clear when asked: a glanceable companion, not a wall of data.
4. Complements Git: speak the developer's Git vocabulary and never pretend to replace it.
5. Local and honest: no cloud, no hidden claims; every label is backed by a hash or a Git lookup.

## Accessibility & Inclusion

WCAG 2.1 AA contrast (light theme only), full keyboard operation, visible focus, `prefers-reduced-motion` respected, usable from 375px phones to wide desktops.
