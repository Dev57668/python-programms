"""
Web Dashboard Server for CodeVault.

Serves a single-page dashboard plus a small JSON API on top of the existing
RecoveryEngine / Database layer. Uses only the standard library
(http.server), so it adds no runtime dependencies.

The server binds to 127.0.0.1 only. State-changing endpoints require a JSON
content type, which browsers cannot send cross-origin without a CORS preflight
(which this server never approves).
"""

import contextlib
import difflib
import io
import json
import mimetypes
import os
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from codevault.config import Config
from codevault.daemon import DaemonManager
from codevault.gitinfo import LOCAL, GitRepo
from codevault.recovery import RecoveryEngine
from codevault.utils import compute_file_hash, format_size

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_FILES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/app.js": "app.js",
    "/style.css": "style.css",
}
MAX_PREVIEW_BYTES = 256 * 1024


class ApiError(Exception):
    """An error that should be returned to the client with a status code."""

    def __init__(self, message: str, status: int = HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.status = status


def _captured(func, *args, **kwargs) -> Tuple[Any, str]:
    """Run an engine method that prints to stdout, returning (result, output)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            result = func(*args, **kwargs)
        except SystemExit:
            result = False
    return result, buf.getvalue().strip()


class DashboardApi:
    """JSON API backed by the CodeVault recovery engine for one project."""

    def __init__(self, project_dir: Path, config: Config):
        self.project_dir = Path(project_dir).resolve()
        self.config = config
        self.engine = RecoveryEngine(self.project_dir, config)
        self.db = self.engine.db
        self.daemon = DaemonManager(
            self.project_dir, self.project_dir / config.snapshot_directory_name
        )
        # Serialises mutating operations; reads go straight to SQLite.
        self.lock = threading.Lock()
        self._git: Optional[GitRepo] = None
        self._git_checked = 0.0
        # Watcher daemons started from the dashboard are our children; reap
        # them when they exit so stop() doesn't see a lingering zombie PID.
        self._children: set = set()
        if os.name != "nt":
            threading.Thread(target=self._reap_children, daemon=True).start()

    def _reap_children(self) -> None:
        while True:
            for pid in list(self._children):
                try:
                    done, _ = os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    done = pid
                if done:
                    self._children.discard(pid)
            time.sleep(0.2)

    # ---------- helpers ----------

    def _repo(self) -> Optional[GitRepo]:
        """The project's git repo, re-detected every 10s if absent (e.g. after git init)."""
        if self._git is None or (not self._git.is_repo and time.time() - self._git_checked > 10):
            self._git = GitRepo(self.project_dir)
            self._git_checked = time.time()
        return self._git if self._git.is_repo else None

    def _git_states(self, snapshots: List[Dict[str, Any]]) -> Dict[int, str]:
        """Map snapshot id -> pushed / committed / local for the given snapshots."""
        repo = self._repo()
        if not repo:
            return {}
        classify = repo.classifier()
        states = {}
        for s in snapshots:
            blob = repo.snapshot_blob(s["id"], self.project_dir / s["snapshot_path"])
            states[s["id"]] = classify(s["relative_path"], blob)
        return states

    def _working_changes(self, repo: GitRepo) -> Dict[str, str]:
        """git status for project files, excluding CodeVault's own storage."""
        return {
            rel: st for rel, st in repo.working_changes().items()
            if not self.config.is_ignored_path(self.project_dir / rel, self.project_dir)
        }

    def _snapshot(self, snapshot_id: Any) -> Dict[str, Any]:
        try:
            snap = self.db.get_snapshot_by_id(int(snapshot_id))
        except (TypeError, ValueError):
            raise ApiError("Invalid snapshot id")
        if not snap:
            raise ApiError("Snapshot not found", HTTPStatus.NOT_FOUND)
        return snap

    def _read_snapshot_text(self, snap: Dict[str, Any]) -> Optional[str]:
        path = self.project_dir / snap["snapshot_path"]
        if not path.is_file():
            raise ApiError(f"Snapshot #{snap['id']} is missing from disk", HTTPStatus.GONE)
        data = path.read_bytes()[:MAX_PREVIEW_BYTES]
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None

    def _tracked_path(self, rel_path: str) -> Path:
        """Resolve a tracked relative path, refusing anything outside the project."""
        if rel_path not in self.db.get_tracked_files():
            raise ApiError("File is not tracked by CodeVault", HTTPStatus.NOT_FOUND)
        target = (self.project_dir / rel_path).resolve()
        if self.project_dir not in target.parents:
            raise ApiError("Path escapes project directory", HTTPStatus.FORBIDDEN)
        return target

    # ---------- read endpoints ----------

    def overview(self, _q: Dict[str, str]) -> Dict[str, Any]:
        status = self.engine.get_status_data()
        snapshots = self.db.get_all_snapshots()
        return {
            "project_dir": status["project_dir"],
            "project_name": self.project_dir.name,
            "stats": {
                "protected_files": status["protected_files_count"],
                "snapshots": status["total_snapshots_count"],
                "deleted_files": status["deleted_files_count"],
                "storage_bytes": status["total_backup_size_bytes"],
                "storage": status["total_backup_size_formatted"],
                "pinned": sum(1 for s in snapshots if s.get("pinned")),
                "last_snapshot": status["last_snapshot"],
            },
            "daemon": self.daemon.status(),
            "activity": [
                {"t": s["timestamp"], "type": s["event_type"]} for s in snapshots
            ],
            "config": {
                "monitored_extensions": sorted(self.config.monitored_extensions),
                "ignored_directories": sorted(self.config.ignored_directories),
                "max_snapshots": self.config.max_snapshots,
                "max_age_days": self.config.max_age_days,
                "debounce_time": self.config.debounce_time,
                "snapshot_directory_name": self.config.snapshot_directory_name,
            },
        }

    def files(self, _q: Dict[str, str]) -> List[Dict[str, Any]]:
        tracked = self.db.get_tracked_files()
        snapshots = self.db.get_all_snapshots()
        latest: Dict[str, Dict[str, Any]] = {}
        for s in snapshots:
            latest[s["relative_path"]] = s
        states = self._git_states(snapshots)
        repo = self._repo()
        changes = self._working_changes(repo) if repo else {}
        local_counts: Dict[str, int] = {}
        for s in snapshots:
            if states.get(s["id"]) == LOCAL:
                local_counts[s["relative_path"]] = local_counts.get(s["relative_path"], 0) + 1
        result = []
        for rel_path, meta in tracked.items():
            last = latest.get(rel_path)
            result.append({
                "git": changes.get(rel_path),
                "local_only": local_counts.get(rel_path, 0) if repo else None,
                "path": rel_path,
                "exists": (self.project_dir / rel_path).exists(),
                "snapshots": meta.get("snapshot_count", 0),
                "last_modified": meta.get("last_modified"),
                "size": format_size(last["size"]) if last else "-",
                "last_hash": (meta.get("last_hash") or "")[:12],
            })
        result.sort(key=lambda f: (f["exists"], f["path"]))
        return result

    def history(self, q: Dict[str, str]) -> Dict[str, Any]:
        rel_path = q.get("path", "")
        snaps = self.db.get_snapshots_for_file(rel_path)
        states = self._git_states(snaps)
        repo = self._repo()
        web_url = None
        if repo:
            summary = repo.summary()
            if summary.get("web_url") and summary.get("upstream"):
                ref = summary["upstream"].split("/", 1)[-1]
                web_url = f"{summary['web_url']}/blob/{ref}/{repo.git_path(rel_path)}"
        return {
            "path": rel_path,
            "exists": (self.project_dir / rel_path).exists(),
            "is_repo": repo is not None,
            "github_url": web_url,
            "snapshots": [
                {**s, "size_str": format_size(s.get("size", 0)), "git": states.get(s["id"])}
                for s in reversed(snaps)
            ],
        }

    def snapshot(self, q: Dict[str, str]) -> Dict[str, Any]:
        snap = self._snapshot(q.get("id"))
        text = self._read_snapshot_text(snap)
        return {**snap, "binary": text is None, "content": text or ""}

    def diff(self, q: Dict[str, str]) -> Dict[str, Any]:
        old = self._snapshot(q.get("from"))
        old_text = self._read_snapshot_text(old)
        to = q.get("to", "current")
        if to == "current":
            current = self.project_dir / old["relative_path"]
            if not current.is_file():
                raise ApiError("File no longer exists on disk", HTTPStatus.NOT_FOUND)
            try:
                new_text = current.read_bytes()[:MAX_PREVIEW_BYTES].decode("utf-8")
            except UnicodeDecodeError:
                new_text = None
            new_label = "current file"
        else:
            new = self._snapshot(to)
            if new["relative_path"] != old["relative_path"]:
                raise ApiError("Snapshots belong to different files")
            new_text = self._read_snapshot_text(new)
            new_label = f"#{new['id']}"
        if old_text is None or new_text is None:
            raise ApiError("Unable to diff binary content")

        lines = []
        added = removed = 0
        diff = difflib.unified_diff(
            old_text.splitlines(), new_text.splitlines(), lineterm="", n=3
        )
        old_no = new_no = 0
        for line in diff:
            if line.startswith("---") or line.startswith("+++"):
                continue
            if line.startswith("@@"):
                # @@ -a,b +c,d @@
                parts = line.split()
                old_no = int(parts[1].split(",")[0][1:]) - 1
                new_no = int(parts[2].split(",")[0][1:]) - 1
                lines.append({"kind": "hunk", "text": line})
            elif line.startswith("+"):
                new_no += 1
                added += 1
                lines.append({"kind": "add", "text": line[1:], "new": new_no})
            elif line.startswith("-"):
                old_no += 1
                removed += 1
                lines.append({"kind": "del", "text": line[1:], "old": old_no})
            else:
                old_no += 1
                new_no += 1
                lines.append({"kind": "ctx", "text": line[1:], "old": old_no, "new": new_no})
        return {
            "path": old["relative_path"],
            "from_label": f"#{old['id']}",
            "to_label": new_label,
            "added": added,
            "removed": removed,
            "lines": lines,
        }

    def timeline(self, _q: Dict[str, str]) -> List[Dict[str, Any]]:
        events = self.db.get_timeline_events()
        return list(reversed(events))[:300]

    def git(self, _q: Dict[str, str]) -> Dict[str, Any]:
        repo = self._repo()
        if not repo:
            return {"is_repo": False}
        summary = repo.summary()
        changes = self._working_changes(repo)
        snapshots = self.db.get_all_snapshots()
        states = self._git_states(snapshots)
        tracked = self.db.get_tracked_files()

        # Files with versions that exist only on this machine (never committed).
        per_file: Dict[str, Dict[str, Any]] = {}
        for s in snapshots:
            if states.get(s["id"]) != LOCAL:
                continue
            entry = per_file.setdefault(s["relative_path"], {
                "path": s["relative_path"], "local_versions": 0, "sources": set(),
            })
            entry["local_versions"] += 1
            entry["latest_id"] = s["id"]
            entry["latest_ts"] = s["timestamp"]
            if s.get("note"):
                entry["sources"].add(s["note"].split(" · ")[0])
        at_risk = []
        for path, entry in per_file.items():
            entry["sources"] = sorted(entry["sources"])
            entry["exists"] = (self.project_dir / path).exists()
            entry["git"] = changes.get(path)
            at_risk.append(entry)
        at_risk.sort(key=lambda e: e["latest_ts"], reverse=True)

        counts = {k: sum(1 for v in states.values() if v == k) for k in ("pushed", "committed", "local")}
        return {
            **summary,
            "changes": [{"path": p, "status": st, "tracked": p in tracked} for p, st in sorted(changes.items())],
            "at_risk": at_risk,
            "version_counts": counts,
        }

    def deleted(self, _q: Dict[str, str]) -> List[Dict[str, Any]]:
        result = []
        for d in self.db.get_deletions():
            snaps = self.db.get_snapshots_for_file(d["relative_path"])
            result.append({
                "path": d["relative_path"],
                "deleted_at": d["timestamp"],
                "snapshots": len(snaps),
                "latest_id": snaps[-1]["id"] if snaps else None,
            })
        return result

    # ---------- write endpoints ----------

    def restore(self, body: Dict[str, Any]) -> Dict[str, Any]:
        snap = self._snapshot(body.get("id"))
        target = self._tracked_path(snap["relative_path"])
        with self.lock:
            ok, output = _captured(
                self.engine.restore_file,
                target_file=target,
                snapshot_id=snap["id"],
                force=True,
                interactive=False,
            )
        if not ok:
            raise ApiError(output or "Restore failed", HTTPStatus.INTERNAL_SERVER_ERROR)
        return {"ok": True, "message": f"Restored {snap['relative_path']} from snapshot #{snap['id']}"}

    def pin(self, body: Dict[str, Any]) -> Dict[str, Any]:
        snap = self._snapshot(body.get("id"))
        pinned = bool(body.get("pinned"))
        with self.lock:
            self.db.set_pin_status(snap["id"], pinned)
        return {"ok": True, "pinned": pinned}

    def verify(self, _body: Dict[str, Any]) -> Dict[str, Any]:
        results = []
        for s in self.db.get_all_snapshots():
            disk_path = self.project_dir / s["snapshot_path"]
            if not disk_path.exists():
                state = "missing"
            elif compute_file_hash(disk_path) != s.get("hash"):
                state = "corrupted"
            else:
                state = "valid"
            results.append({"id": s["id"], "path": s["relative_path"], "state": state})
        counts = {k: sum(1 for r in results if r["state"] == k) for k in ("valid", "corrupted", "missing")}
        return {"ok": counts["corrupted"] == 0 and counts["missing"] == 0, "counts": counts, "results": results}

    def git_fetch(self, _body: Dict[str, Any]) -> Dict[str, Any]:
        repo = self._repo()
        if not repo:
            raise ApiError("This project is not a git repository")
        if not repo.fetch():
            raise ApiError("git fetch failed. Check your network and that the remote is reachable", HTTPStatus.BAD_GATEWAY)
        return {"ok": True}

    def daemon_action(self, body: Dict[str, Any]) -> Dict[str, Any]:
        action = body.get("action")
        if action not in ("start", "stop"):
            raise ApiError("action must be 'start' or 'stop'")
        with self.lock:
            _, output = _captured(getattr(self.daemon, action))
            status = self.daemon.status()
            if action == "start" and status["pid"]:
                self._children.add(status["pid"])
        return {"ok": True, "message": output, "daemon": status}


def make_handler(api: DashboardApi):
    get_routes = {
        "/api/overview": api.overview,
        "/api/files": api.files,
        "/api/history": api.history,
        "/api/snapshot": api.snapshot,
        "/api/diff": api.diff,
        "/api/timeline": api.timeline,
        "/api/deleted": api.deleted,
        "/api/git": api.git,
    }
    post_routes = {
        "/api/restore": api.restore,
        "/api/pin": api.pin,
        "/api/verify": api.verify,
        "/api/daemon": api.daemon_action,
        "/api/git/fetch": api.git_fetch,
    }

    class Handler(BaseHTTPRequestHandler):
        server_version = "CodeVault"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            pass  # keep the terminal quiet during demos

        def _send_json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
            body = json.dumps(payload, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _run(self, func, arg) -> None:
            try:
                self._send_json(func(arg))
            except ApiError as e:
                self._send_json({"error": str(e)}, e.status)
            except Exception as e:  # surface unexpected errors to the UI
                self._send_json({"error": f"{type(e).__name__}: {e}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path in get_routes:
                query = {k: v[0] for k, v in parse_qs(url.query).items()}
                self._run(get_routes[url.path], query)
                return
            name = STATIC_FILES.get(url.path)
            if not name:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            data = (STATIC_DIR / name).read_bytes()
            ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:
            url = urlparse(self.path)
            func = post_routes.get(url.path)
            if not func:
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                self._send_json({"error": "Expected application/json"}, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._send_json({"error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
                return
            self._run(func, body)

    return Handler


def serve(project_dir: Path, config: Config, port: int = 8765, open_browser: bool = True) -> None:
    """Start the dashboard server and block until interrupted."""
    api = DashboardApi(project_dir, config)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(api))
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"[OK] CodeVault dashboard for {api.project_dir}")
    print(f"     Open {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[OK] Dashboard stopped.")
    finally:
        server.server_close()
