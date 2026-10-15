"""
Git awareness for CodeVault.

Answers "is this version of the file on GitHub, only committed locally,
or does it exist only in CodeVault?" by comparing git blob hashes of
snapshot content against the blobs recorded in the history of HEAD and
of the upstream branch (e.g. origin/main).

Read-only: only runs `git` query commands (plus an explicit, opt-in
`git fetch`). Uses the system `git` executable; no extra dependencies.
"""

import hashlib
import os
import re
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PUSHED = "pushed"        # content exists in the upstream branch history
COMMITTED = "committed"  # content committed locally but not pushed
LOCAL = "local"          # content never committed: only CodeVault has it


def git_blob_hash(data: bytes) -> str:
    """Compute the SHA-1 object id git would assign to this file content."""
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def github_web_url(remote_url: Optional[str]) -> Optional[str]:
    """Convert a GitHub remote URL (ssh or https) into its web URL."""
    if not remote_url:
        return None
    m = re.match(r"^(?:git@github\.com:|ssh://git@github\.com/|https?://(?:[^@/]+@)?github\.com/)([^/]+/[^/]+?)(?:\.git)?/?$", remote_url.strip())
    return f"https://github.com/{m.group(1)}" if m else None


class GitRepo:
    """Read-only view of the git repository containing a CodeVault project."""

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir).resolve()
        self._blob_cache: Dict[str, Set[Tuple[str, str]]] = {}
        self._snap_blob_cache: Dict[int, str] = {}
        self._lock = threading.Lock()
        top = self._git("rev-parse", "--show-toplevel")
        self.toplevel = Path(top).resolve() if top else None
        if self.toplevel:
            prefix = self.project_dir.relative_to(self.toplevel).as_posix()
            self.prefix = "" if prefix == "." else prefix + "/"
        else:
            self.prefix = ""

    @property
    def is_repo(self) -> bool:
        return self.toplevel is not None

    # ---------- plumbing ----------

    def _git(self, *args: str, timeout: float = 10.0, strip: bool = True) -> Optional[str]:
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0", LC_ALL="C")
        try:
            out = subprocess.run(
                ["git", *args], cwd=str(self.project_dir), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if out.returncode != 0:
            return None
        text = out.stdout.decode("utf-8", errors="replace")
        return text.strip() if strip else text

    def _rev(self, ref: str) -> Optional[str]:
        return self._git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")

    def git_path(self, rel_path: str) -> str:
        """Map a CodeVault project-relative path to a repo-relative path."""
        return self.prefix + rel_path

    def _blobs_for(self, commit: Optional[str]) -> Set[Tuple[str, str]]:
        """All (path, blob) pairs that ever appeared in the history of commit."""
        if not commit:
            return set()
        with self._lock:
            cached = self._blob_cache.get(commit)
            if cached is not None:
                return cached
        out = self._git("log", "--raw", "--no-abbrev", "--no-renames", "--root", "--format=", commit, timeout=60.0) or ""
        blobs: Set[Tuple[str, str]] = set()
        for line in out.splitlines():
            # :100644 100644 <old> <new> M\tpath
            if not line.startswith(":"):
                continue
            meta, _, path = line.partition("\t")
            parts = meta.split()
            if len(parts) >= 4 and not set(parts[3]) <= {"0"}:
                blobs.add((path, parts[3]))
        with self._lock:
            self._blob_cache[commit] = blobs
        return blobs

    # ---------- queries ----------

    def upstream(self) -> Optional[str]:
        return self._git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")

    def snapshot_blob(self, snapshot_id: int, snapshot_file: Path) -> Optional[str]:
        """Git blob id of a snapshot's content (snapshots are immutable, so cache by id)."""
        cached = self._snap_blob_cache.get(snapshot_id)
        if cached:
            return cached
        try:
            blob = git_blob_hash(snapshot_file.read_bytes())
        except OSError:
            return None
        self._snap_blob_cache[snapshot_id] = blob
        return blob

    def classifier(self):
        """
        Return a function (rel_path, blob) -> PUSHED | COMMITTED | LOCAL,
        built once per call so a whole list of snapshots shares the lookups.
        """
        head = self._rev("HEAD")
        up = self.upstream()
        up_sha = self._rev(up) if up else None
        head_blobs = self._blobs_for(head)
        up_blobs = self._blobs_for(up_sha)

        def classify(rel_path: str, blob: Optional[str]) -> str:
            if not blob:
                return LOCAL
            key = (self.git_path(rel_path), blob)
            if key in up_blobs:
                return PUSHED
            if key in head_blobs:
                return COMMITTED
            return LOCAL

        return classify

    def working_changes(self) -> Dict[str, str]:
        """Map project-relative path -> short status (modified/added/deleted/untracked/renamed)."""
        out = self._git("status", "--porcelain=v1", "-z", "--untracked-files=all", strip=False)
        if out is None:
            return {}
        result: Dict[str, str] = {}
        entries = out.split("\0")
        i = 0
        while i < len(entries):
            entry = entries[i]
            i += 1
            if len(entry) < 4:
                continue
            xy, path = entry[:2], entry[3:]
            if "R" in xy or "C" in xy:
                i += 1  # skip the original path that follows a rename
            if not path.startswith(self.prefix):
                continue
            rel = path[len(self.prefix):]
            if xy == "??":
                status = "untracked"
            elif "D" in xy:
                status = "deleted"
            elif "A" in xy:
                status = "added"
            elif "R" in xy:
                status = "renamed"
            else:
                status = "modified"
            result[rel] = status
        return result

    def summary(self) -> Dict[str, Any]:
        """Branch, upstream, ahead/behind, remote and recent unpushed commits."""
        if not self.is_repo:
            return {"is_repo": False}
        branch = self._git("rev-parse", "--abbrev-ref", "HEAD") or "HEAD"
        up = self.upstream()
        ahead = behind = 0
        if up:
            counts = self._git("rev-list", "--left-right", "--count", f"{up}...HEAD")
            if counts:
                b, a = counts.split()
                ahead, behind = int(a), int(b)
        remote_name = up.split("/", 1)[0] if up else "origin"
        remote_url = self._git("remote", "get-url", remote_name)
        last = self._git("log", "-1", "--format=%H%x1f%s%x1f%ci")
        last_commit = None
        if last:
            sha, subject, date = last.split("\x1f")
            last_commit = {"sha": sha, "subject": subject, "date": date}
        unpushed: List[Dict[str, str]] = []
        if up and ahead:
            log = self._git("log", "--format=%H%x1f%s%x1f%ci", f"{up}..HEAD", "-n", "20") or ""
            for line in log.splitlines():
                sha, subject, date = line.split("\x1f")
                unpushed.append({"sha": sha, "subject": subject, "date": date})
        return {
            "is_repo": True,
            "branch": branch,
            "upstream": up,
            "ahead": ahead,
            "behind": behind,
            "remote_url": remote_url,
            "web_url": github_web_url(remote_url),
            "last_commit": last_commit,
            "unpushed_commits": unpushed,
            "prefix": self.prefix,
        }

    def fetch(self) -> bool:
        """Update remote-tracking refs (read-only on the remote side)."""
        return self._git("fetch", "--quiet", "--no-tags", timeout=30.0) is not None
