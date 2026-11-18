#!/usr/bin/env python3
"""Records the dashboard's JSON API for a made-up sample project into demo/api.json.

The hosted demo (GitHub Pages / Vercel) has no Python server, so demo.js answers the
dashboard's /api calls from this file. Run from the repo root: python scripts/build_demo_data.py
"""
import json
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from codevault.backup import BackupEngine  # noqa: E402
from codevault.config import Config  # noqa: E402
from codevault.web.server import DashboardApi  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "codevault/web/static/demo/api.json"


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "Demo", "GIT_AUTHOR_EMAIL": "demo@example.com",
                        "GIT_COMMITTER_NAME": "Demo", "GIT_COMMITTER_EMAIL": "demo@example.com",
                        "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": str(cwd)})


root = Path(tempfile.mkdtemp())
proj = root / "gradebook-app"
(proj / "tests").mkdir(parents=True)
remote = root / "origin.git"
subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
git(proj, "init", "-q", "-b", "main")
git(proj, "remote", "add", "origin", str(remote))

eng = BackupEngine(proj, Config())
snaps = []  # (path, minutes_ago) in creation order, so timestamps can be spread out afterwards


def save(rel, text, mins, event="modified", note=None):
    (proj / rel).write_text(text)
    time.sleep(1.1)  # snapshot file names carry a one-second timestamp
    r = eng.create_snapshot(proj / rel, event_type=event, note=note)
    if r:
        snaps.append((r["id"], mins))


GRADES = '''def average(scores):
    return sum(scores) / len(scores)
'''
APP = '''from grades import average


def report(name, scores):
    print(name, average(scores))
'''
UTILS = '''def clamp(x, lo, hi):
    return max(lo, min(hi, x))
'''
TEST = '''from grades import average


def test_average():
    assert average([2, 4]) == 3
'''
# Stage 1: pushed
save("grades.py", GRADES, 400, "created")
save("app.py", APP, 395, "created")
save("utils.py", UTILS, 390, "created")
save("tests/test_grades.py", TEST, 385, "created")
git(proj, "add", "-A"); git(proj, "commit", "-qm", "Initial gradebook")
git(proj, "push", "-q", "-u", "origin", "main")
# Stage 2: committed, not pushed
GRADES2 = GRADES + '''

def best(scores):
    return max(scores)
'''
save("grades.py", GRADES2, 300)
git(proj, "add", "-A"); git(proj, "commit", "-qm", "Add best()")
# Stage 3: local only, with AI edits
APP3 = APP + '''

def top_student(rows):
    return max(rows, key=lambda r: average(r[1]))[0]
'''
save("app.py", APP, 200, note="claude · before edit")
save("app.py", APP3, 199, event="modified", note="claude · edit")
GRADES4 = GRADES2.replace("return sum(scores) / len(scores)", "return sum(scores) / len(scores) if scores else 0.0")
save("grades.py", GRADES4, 120)
GRADES5 = GRADES4 + '''

def curve(scores, points=5):
    return [min(100, s + points) for s in scores]
'''
save("grades.py", GRADES5, 45, note="claude · edit")
save("utils.py", UTILS + "\n\ndef pct(a, b):\n    return round(100 * a / b)\n", 30)
save("tests/test_grades.py", TEST + "\n\ndef test_best():\n    from grades import best\n    assert best([1, 9]) == 9\n", 12)
# A scratch file that was deleted
save("scratch.py", "print('trying things')\n", 150, "created")
(proj / "scratch.py").unlink()
eng.handle_deletion(proj / "scratch.py")

# Spread timestamps over the last ~6 hours, relative to the newest ("now").
now = datetime.now()
db = sqlite3.connect(proj / ".lifejacket" / "vault.db")
for sid, mins in snaps:
    db.execute("UPDATE snapshots SET created_at=? WHERE id=?",
               ((now - timedelta(minutes=mins)).strftime("%Y-%m-%d %H:%M:%S"), sid))
db.execute("UPDATE files SET deleted_at=?, last_seen=? WHERE deleted_at IS NOT NULL",
           (2*[(now - timedelta(minutes=140)).strftime("%Y-%m-%d %H:%M:%S")]))
db.execute("UPDATE snapshots SET pinned=1 WHERE id=?", (snaps[0][0],))
db.commit(); db.close()

# Record every GET the dashboard can make.
api = DashboardApi(proj, Config())
rec = {}


def put(route, fn, **q):
    key = route + ("?" + "&".join(f"{k}={v}" for k, v in q.items()) if q else "")
    rec[key] = json.loads(json.dumps(fn(q), default=str))


put("/api/overview", api.overview)
put("/api/files", api.files)
put("/api/timeline", api.timeline)
put("/api/deleted", api.deleted)
put("/api/git", api.git)
put("/api/projects", api.projects)
rec["/api/overview"]["daemon"] = {"status": "RUNNING", "pid": 4242}
files = rec["/api/files"]
paths = [f["path"] if "path" in f else f["relative_path"] for f in files]
for p in sorted(set(paths) | {"scratch.py"}):
    put("/api/history", api.history, path=p)
    ids = [s["id"] for s in rec[f"/api/history?path={p}"]["snapshots"]]
    ordered = sorted(ids)
    for i, sid in enumerate(ordered):
        put("/api/snapshot", api.snapshot, id=sid)
        if i:
            put("/api/diff", api.diff, **{"from": ordered[i - 1], "to": sid})
        try:
            put("/api/diff", api.diff, **{"from": sid, "to": "current"})
        except Exception:
            pass  # deleted file: the dashboard shows its own message
rec["_recorded_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(rec, separators=(",", ":")))
print(f"{len(rec)} responses, {OUT.stat().st_size // 1024} KB -> {OUT}")
