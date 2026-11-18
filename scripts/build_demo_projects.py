#!/usr/bin/env python3
"""Builds demo/projects.json, the data behind the interactive hosted demo.

The hosted site (Vercel / GitHub Pages) has no Python server. demo.js therefore runs a small
in-browser copy of the dashboard backend, and this file is its starting data:

* gradebook-app  - converted from demo/api.json, which scripts/build_demo_data.py records by running
                   the real CodeVault engine on a sample project (real SHA-256 hashes and git states).
* todo-cli, weather-bot - two small hand-written sample projects so "Switch project" has somewhere to go.

Every timestamp is stored as "minutes ago" so the demo always looks fresh. Run from the repo root:
    python scripts/build_demo_data.py && python scripts/build_demo_projects.py
"""
import hashlib
import json
from datetime import datetime
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "codevault/web/static/demo"
CONFIG = {
    "monitored_extensions": [".c", ".cpp", ".go", ".java", ".js", ".py", ".rs", ".ts"],
    "ignored_directories": [".git", ".idea", ".lifejacket", ".venv", ".vscode", "__pycache__", "env", "node_modules", "venv"],
    "max_snapshots": 10,
    "max_age_days": 30,
    "debounce_time": 1.0,
    "snapshot_directory_name": ".lifejacket",
}


def sha1(text):
    return hashlib.sha1(text.encode()).hexdigest()


def snap(path, ago, event, content, git, note=None, pinned=0):
    return {"path": path, "ago_min": ago, "event": event, "content": content, "git": git, "note": note, "pinned": pinned}


def gradebook():
    d = json.loads((STATIC / "api.json").read_text())
    snaps = {}
    for key, val in d.items():
        if key.startswith("/api/history"):
            for s in val["snapshots"]:
                snaps[s["id"]] = s
    for key, val in d.items():
        if key.startswith("/api/snapshot"):
            snaps[val["id"]]["content"] = val["content"]
    ts = lambda s: datetime.strptime(s["timestamp"], "%Y-%m-%d %H:%M:%S")  # noqa: E731
    newest = max(ts(s) for s in snaps.values())
    out = []
    for i in sorted(snaps):
        s = snaps[i]
        out.append({"id": i, "path": s["relative_path"], "ago_min": round((newest - ts(s)).total_seconds() / 60) + 12,
                    "event": s["event_type"], "content": s["content"], "hash": s["hash"], "git": s["git"],
                    "note": s["note"], "pinned": s["pinned"]})
    g = d["/api/git"]
    deleted = {x["path"]: round((newest - datetime.strptime(x["deleted_at"], "%Y-%m-%d %H:%M:%S")).total_seconds() / 60) + 12
               for x in d["/api/deleted"]}
    return {
        "name": "gradebook-app", "dir": "~/Documents/gradebook-app", "branch": g["branch"], "upstream": g["upstream"],
        "ahead": g["ahead"], "behind": 0, "remote_behind": 0, "config": CONFIG,
        "commits": [{"sha": c["sha"], "subject": c["subject"], "ago_min": 14, "pushed": False} for c in g["unpushed_commits"]],
        "deleted": deleted, "snapshots": out,
    }


TODO_V1 = 'tasks = []\n\n\ndef add(title):\n    tasks.append({"title": title, "done": False})\n'
TODO_V2 = TODO_V1 + '\n\ndef complete(index):\n    tasks[index]["done"] = True\n'
TODO_V3 = TODO_V2.replace('{"title": title, "done": False}', '{"title": title, "done": False, "due": due}').replace("def add(title):", "def add(title, due=None):")
TODO_V4 = TODO_V3 + '\n\ndef overdue(today):\n    return [t for t in tasks if t["due"] and t["due"] < today and not t["done"]]\n'
TODO_V5 = ('from datetime import date\n\ntasks = []\n\n\ndef add(title, due=None):\n    tasks.append({"title": title, "done": False, "due": due})\n\n\n'
           'def complete(index):\n    tasks[index]["done"] = True\n\n\ndef overdue(today=None):\n    today = today or date.today().isoformat()\n'
           '    return [t for t in tasks if t["due"] and t["due"] < today and not t["done"]]\n')
STORE_V1 = 'import json\n\n\ndef save(tasks, path="tasks.json"):\n    with open(path, "w") as f:\n        json.dump(tasks, f)\n'
STORE_V2 = STORE_V1 + '\n\ndef load(path="tasks.json"):\n    try:\n        with open(path) as f:\n            return json.load(f)\n    except FileNotFoundError:\n        return []\n'
TEST_V1 = 'import todo\n\n\ndef test_add():\n    todo.add("milk")\n    assert todo.tasks[0]["title"] == "milk"\n'
DRAFT = '# idea: sync tasks between machines\n# maybe a tiny HTTP endpoint?\n'


def todo_cli():
    s = [
        snap("todo.py", 300, "created", TODO_V1, "pushed"), snap("storage.py", 290, "created", STORE_V1, "pushed"),
        snap("tests/test_todo.py", 280, "created", TEST_V1, "pushed"), snap("old_draft.py", 200, "created", DRAFT, "local"),
        snap("todo.py", 220, "modified", TODO_V2, "pushed"), snap("storage.py", 120, "modified", STORE_V2, "local", pinned=1),
        snap("todo.py", 95, "modified", TODO_V3, "committed"), snap("todo.py", 40, "modified", TODO_V4, "local", "claude \u00b7 before edit"),
        snap("todo.py", 38, "modified", TODO_V5, "local", "claude \u00b7 edit"),
    ]
    s.sort(key=lambda x: -x["ago_min"])
    for i, x in enumerate(s, 1):
        x["id"] = i
    return {"name": "todo-cli", "dir": "~/Documents/todo-cli", "branch": "main", "upstream": "origin/main", "ahead": 1, "behind": 0,
            "remote_behind": 2, "config": CONFIG,
            "commits": [{"sha": sha1("Add due dates"), "subject": "Add due dates", "ago_min": 90, "pushed": False}],
            "deleted": {"old_draft.py": 150}, "snapshots": s}


BOT_V1 = 'const { forecast } = require("./api");\n\nasync function reply(city) {\n  const f = await forecast(city);\n  return `${city}: ${f.temp}\u00b0C`;\n}\n\nmodule.exports = { reply };\n'
BOT_V2 = BOT_V1.replace("return `${city}: ${f.temp}\u00b0C`;", "return `${city}: ${f.temp}\u00b0C, ${f.sky}`;")
BOT_V3 = BOT_V2.replace("const f = await forecast(city);", "const f = await forecast(city.trim());")
BOT_V4 = ('const { forecast } = require("./api");\nconst { line } = require("./format");\n\nasync function reply(city) {\n'
          '  const f = await forecast(city.trim());\n  return line(city, f);\n}\n\nmodule.exports = { reply };\n')
API_V1 = 'async function forecast(city) {\n  const res = await fetch(`https://example.test/weather?q=${city}`);\n  return res.json();\n}\n\nmodule.exports = { forecast };\n'
API_V2 = API_V1.replace("const res = await fetch(`https://example.test/weather?q=${city}`);", "const res = await fetch(`https://example.test/weather?q=${encodeURIComponent(city)}`);\n  if (!res.ok) throw new Error(`weather API ${res.status}`);")
FMT_V1 = 'function line(city, f) {\n  return `${city}: ${f.temp}\u00b0C, ${f.sky}`;\n}\n\nmodule.exports = { line };\n'


def weather_bot():
    s = [
        snap("bot.js", 400, "created", BOT_V1, "pushed"), snap("api.js", 390, "created", API_V1, "pushed"),
        snap("bot.js", 260, "modified", BOT_V2, "pushed"), snap("api.js", 150, "modified", API_V2, "local", pinned=1),
        snap("bot.js", 70, "modified", BOT_V3, "local", "antigravity \u00b7 before agent run", pinned=1),
        snap("format.js", 52, "created", FMT_V1, "local", "antigravity \u00b7 after agent run"),
        snap("bot.js", 51, "modified", BOT_V4, "local", "antigravity \u00b7 after agent run"),
    ]
    s.sort(key=lambda x: -x["ago_min"])
    for i, x in enumerate(s, 1):
        x["id"] = i
    return {"name": "weather-bot", "dir": "~/Documents/weather-bot", "branch": "dev", "upstream": "origin/dev", "ahead": 0, "behind": 0,
            "remote_behind": 0, "config": CONFIG,
            "commits": [], "deleted": {}, "snapshots": s}


if __name__ == "__main__":
    data = {"version": 2, "projects": [gradebook(), todo_cli(), weather_bot()]}
    (STATIC / "projects.json").write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
    print("wrote", STATIC / "projects.json", sum(len(p["snapshots"]) for p in data["projects"]), "snapshots")
