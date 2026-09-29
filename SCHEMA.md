# CodeVault: Data Schema

> This is the **target reference schema**. Your existing `database.py` may already have a subset of it. Compare the two and migrate rather than rewriting from scratch (see task T2 in `TASKS.md`).

## Storage layout (per project)

```
<project>/.lifejacket/          # store directory name is configurable; pick one final name
├── vault.db                    # SQLite metadata
├── objects/                    # content-addressed snapshot data
│   └── ab/cdef0123...          # first 2 hex chars = folder, rest = filename (SHA-256)
├── config.json                 # per-project settings
├── daemon.pid                  # exists only while the watcher runs
└── daemon.log                  # rotating log
```

The store directory must always be in the ignore list, or the watcher would snapshot its own snapshots.

## SQLite DDL

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Schema version for future migrations
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- INSERT OR IGNORE INTO meta VALUES ('schema_version', '1');

-- One row per unique file path (relative to project root, forward slashes)
CREATE TABLE IF NOT EXISTS files (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    path         TEXT NOT NULL UNIQUE,
    status       TEXT NOT NULL DEFAULT 'active'
                 CHECK (status IN ('active', 'deleted')),
    first_seen   TEXT NOT NULL,          -- ISO-8601 UTC
    last_seen    TEXT NOT NULL,
    deleted_at   TEXT                    -- NULL while active
);

-- One row per unique content blob (deduplicated by hash)
CREATE TABLE IF NOT EXISTS blobs (
    hash         TEXT PRIMARY KEY,       -- SHA-256 hex of ORIGINAL content
    size         INTEGER NOT NULL,       -- original size in bytes
    stored_size  INTEGER NOT NULL,       -- bytes on disk (differs if compressed)
    compressed   INTEGER NOT NULL DEFAULT 0 CHECK (compressed IN (0, 1)),
    created_at   TEXT NOT NULL
);

-- One row per snapshot event
CREATE TABLE IF NOT EXISTS snapshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id      INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    blob_hash    TEXT    NOT NULL REFERENCES blobs(hash),
    snapshot_path TEXT   NOT NULL, -- DEVIATION: stores path to keep physical files where they are
    created_at   TEXT    NOT NULL,
    event_type   TEXT    NOT NULL
                 CHECK (event_type IN ('create', 'modify', 'delete', 'pre_restore')),
    pinned       INTEGER NOT NULL DEFAULT 0 CHECK (pinned IN (0, 1)),
    note         TEXT
);

CREATE INDEX IF NOT EXISTS idx_snapshots_file_time ON snapshots(file_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_snapshots_blob      ON snapshots(blob_hash);
CREATE INDEX IF NOT EXISTS idx_snapshots_time      ON snapshots(created_at);
CREATE INDEX IF NOT EXISTS idx_files_status        ON files(status);
```

## Design rules

1. **Dedupe:** before inserting a snapshot, compare the new hash to the file's latest snapshot. If equal, do nothing.
2. **Atomic write order:** write blob to a temp file → `os.replace` into `objects/` → insert `blobs` and `snapshots` rows in **one transaction**. If anything fails, roll back and remove the temp file.
3. **Deletes:** mark `files.status = 'deleted'`, set `deleted_at`, and add a `delete` event pointing at the last known blob. The content is already stored, so recovery always works.
4. **Resurrection:** if a deleted path reappears, set `status = 'active'`, clear `deleted_at`, and add a `create` snapshot.
5. **Retention:** per file, keep the newest `max_snapshots_per_file`; also drop anything older than `max_age_days` if set. **Never delete pinned rows.** Always keep at least the latest snapshot of each file.
6. **Garbage collection:** after retention, delete `blobs` rows (and their files in `objects/`) that no snapshot references:
   ```sql
   SELECT hash FROM blobs WHERE hash NOT IN (SELECT DISTINCT blob_hash FROM snapshots);
   ```
7. **Paths:** always store project-relative paths with `/` separators, so a store works across OSes.

## Key queries

```sql
-- status: protected files, snapshots, deleted files, storage
SELECT COUNT(*) FROM files WHERE status = 'active';
SELECT COUNT(*) FROM snapshots;
SELECT COUNT(*) FROM files WHERE status = 'deleted';
SELECT COALESCE(SUM(stored_size), 0) FROM blobs;

-- timeline for one file
SELECT s.id, s.created_at, s.event_type, b.size, s.pinned
FROM snapshots s JOIN files f ON f.id = s.file_id JOIN blobs b ON b.hash = s.blob_hash
WHERE f.path = ? ORDER BY s.created_at DESC LIMIT ?;

-- project state at a point in time (latest snapshot per file at or before T)
SELECT f.path, s.blob_hash
FROM files f
JOIN snapshots s ON s.id = (
    SELECT id FROM snapshots
    WHERE file_id = f.id AND created_at <= ?
    ORDER BY created_at DESC, id DESC LIMIT 1
)
WHERE s.event_type != 'delete';

-- recently deleted files
SELECT path, deleted_at FROM files WHERE status = 'deleted' ORDER BY deleted_at DESC;
```

## Config (`config.json`)

```json
{
  "store_dir": ".lifejacket",
  "max_snapshots_per_file": 50,
  "max_age_days": 30,
  "max_file_size_mb": 5,
  "debounce_ms": 400,
  "compress": true,
  "watch_extensions": [".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".html", ".css", ".md", ".json"],
  "ignore": [".git", "__pycache__", ".venv", "node_modules", "*.pyc", ".DS_Store"]
}
```
