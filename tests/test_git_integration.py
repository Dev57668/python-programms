"""
Tests for git awareness (pushed / committed / local-only versions)
and AI tool attribution (hook, hooks install, labelled checkpoints).
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from codevault.backup import BackupEngine
from codevault.config import Config
from codevault.gitinfo import COMMITTED, LOCAL, PUSHED, GitRepo, git_blob_hash, github_web_url
from codevault.web.server import DashboardApi

HAS_GIT = shutil.which("git") is not None
MAIN = Path(__file__).resolve().parent.parent / "main.py"


def git(cwd, *args):
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
        cwd=str(cwd), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def run_cli(cwd, *args, stdin=None):
    return subprocess.run(
        [sys.executable, str(MAIN), *args], cwd=str(cwd), input=stdin,
        capture_output=True, text=True, encoding="utf-8",
    )


class TestGitHelpers(unittest.TestCase):

    def test_blob_hash_matches_git(self):
        if not HAS_GIT:
            self.skipTest("git not installed")
        data = b"print('hello')\n"
        out = subprocess.run(["git", "hash-object", "--stdin"], input=data, capture_output=True, check=True)
        self.assertEqual(git_blob_hash(data), out.stdout.decode().strip())

    def test_github_web_url(self):
        self.assertEqual(github_web_url("git@github.com:me/repo.git"), "https://github.com/me/repo")
        self.assertEqual(github_web_url("https://github.com/me/repo.git"), "https://github.com/me/repo")
        self.assertEqual(github_web_url("https://token@github.com/me/repo"), "https://github.com/me/repo")
        self.assertIsNone(github_web_url("https://gitlab.com/me/repo.git"))
        self.assertIsNone(github_web_url(None))


@unittest.skipUnless(HAS_GIT, "git not installed")
class TestGitAwareness(unittest.TestCase):
    """A project with one pushed commit, one unpushed commit and an uncommitted edit."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.remote = self.tmp / "remote.git"
        self.project = self.tmp / "project"
        self.project.mkdir()
        git(self.tmp, "init", "-q", "--bare", str(self.remote))
        git(self.project, "init", "-q")
        git(self.project, "checkout", "-q", "-b", "main")
        (self.project / ".gitignore").write_text(".lifejacket/\n", encoding="utf-8")
        self.src = self.project / "app.py"
        self.engine = BackupEngine(self.project, Config())

        self.src.write_text("v1\n", encoding="utf-8")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-qm", "v1")
        git(self.project, "remote", "add", "origin", str(self.remote))
        git(self.project, "push", "-q", "-u", "origin", "main")
        self.s_pushed = self.engine.create_snapshot(self.src)

        self.src.write_text("v2\n", encoding="utf-8")
        git(self.project, "commit", "-qam", "v2")
        self.s_committed = self.engine.create_snapshot(self.src)

        self.src.write_text("v3\n", encoding="utf-8")
        self.s_local = self.engine.create_snapshot(self.src, note="claude · Edit")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_classifies_each_version(self):
        repo = GitRepo(self.project)
        classify = repo.classifier()
        state = {}
        for snap in (self.s_pushed, self.s_committed, self.s_local):
            blob = repo.snapshot_blob(snap["id"], self.project / snap["snapshot_path"])
            state[snap["id"]] = classify("app.py", blob)
        self.assertEqual(state[self.s_pushed["id"]], PUSHED)
        self.assertEqual(state[self.s_committed["id"]], COMMITTED)
        self.assertEqual(state[self.s_local["id"]], LOCAL)

    def test_summary_and_status(self):
        repo = GitRepo(self.project)
        summary = repo.summary()
        self.assertEqual(summary["branch"], "main")
        self.assertEqual(summary["upstream"], "origin/main")
        self.assertEqual(summary["ahead"], 1)
        self.assertEqual(summary["behind"], 0)
        self.assertEqual([c["subject"] for c in summary["unpushed_commits"]], ["v2"])
        # First entry keeps its leading status column (" M app.py")
        self.assertEqual(repo.working_changes(), {"app.py": "modified"})

    def test_dashboard_git_endpoint(self):
        api = DashboardApi(self.project, Config())
        data = api.git({})
        self.assertTrue(data["is_repo"])
        self.assertEqual(data["version_counts"], {"pushed": 1, "committed": 1, "local": 1})
        self.assertEqual(len(data["at_risk"]), 1)
        self.assertEqual(data["at_risk"][0]["path"], "app.py")
        self.assertEqual(data["at_risk"][0]["sources"], ["claude"])
        self.assertEqual(data["changes"], [{"path": "app.py", "status": "modified", "tracked": True}])

        history = api.history({"path": "app.py"})
        self.assertEqual([s["git"] for s in history["snapshots"]], [LOCAL, COMMITTED, PUSHED])

    def test_open_project_switches_and_excludes_vault(self):
        other = self.tmp / "other"
        other.mkdir()
        git(other, "init", "-q")
        api = DashboardApi(self.tmp / "remote.git", Config())
        result = api.open_project({"target": str(other)})
        self.assertEqual(result["project_dir"], str(other))
        self.assertEqual(api.files({}), [])
        self.assertIn("/.lifejacket/", (other / ".git" / "info" / "exclude").read_text(encoding="utf-8"))
        self.assertEqual(api.projects({})["recent"][:2], [str(other), str(self.tmp / "remote.git")])

    def test_open_project_rejects_missing_folder(self):
        from codevault.web.server import ApiError
        api = DashboardApi(self.project, Config())
        with self.assertRaises(ApiError):
            api.open_project({"target": str(self.tmp / "nope")})
        self.assertEqual(api.project_dir, self.project)

    def test_not_a_repo(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        self.assertFalse(GitRepo(plain).is_repo)
        self.assertEqual(DashboardApi(plain, Config()).git({}), {"is_repo": False})


class TestAiAttribution(unittest.TestCase):

    def setUp(self):
        self.project = Path(tempfile.mkdtemp()).resolve()
        self.config = Config()

    def tearDown(self):
        shutil.rmtree(self.project, ignore_errors=True)

    def _hook(self, event, path):
        payload = {
            "hook_event_name": event, "tool_name": "Edit", "cwd": str(self.project),
            "tool_input": {"file_path": str(path)},
        }
        return run_cli(self.project, "hook", "claude", stdin=json.dumps(payload))

    def test_hook_snapshots_before_and_after_ai_edit(self):
        src = self.project / "service.py"
        src.write_text("def run():\n    pass\n", encoding="utf-8")
        self.assertEqual(self._hook("PreToolUse", src).returncode, 0)
        src.write_text("def run():\n    return 42\n", encoding="utf-8")
        self.assertEqual(self._hook("PostToolUse", src).returncode, 0)

        snaps = BackupEngine(self.project, self.config).db.get_snapshots_for_file("service.py")
        self.assertEqual([s["event_type"] for s in snaps], ["pre_ai", "ai_edit"])
        self.assertEqual([s["note"] for s in snaps], ["claude · before Edit", "claude · Edit"])

    def test_hook_labels_snapshot_the_watcher_already_took(self):
        src = self.project / "service.py"
        src.write_text("x = 1\n", encoding="utf-8")
        engine = BackupEngine(self.project, self.config)
        watcher_snap = engine.create_snapshot(src)  # watcher got there first, no label
        self._hook("PostToolUse", src)
        snaps = engine.db.get_snapshots_for_file("service.py")
        self.assertEqual(len(snaps), 1)
        self.assertEqual(snaps[0]["id"], watcher_snap["id"])
        self.assertEqual(snaps[0]["note"], "claude · Edit")

    def test_hook_ignores_bad_input(self):
        result = run_cli(self.project, "hook", "claude", stdin="not json")
        self.assertEqual(result.returncode, 0)

    def test_hooks_install_and_remove(self):
        settings = self.project / ".claude" / "settings.json"
        settings.parent.mkdir()
        settings.write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}}), encoding="utf-8")

        for _ in range(2):  # installing twice must not duplicate hooks
            self.assertEqual(run_cli(self.project, "hooks", "install", "claude", str(self.project)).returncode, 0)
        data = json.loads(settings.read_text(encoding="utf-8"))
        self.assertEqual(data["permissions"], {"allow": ["Bash(ls)"]})
        for event in ("PreToolUse", "PostToolUse"):
            self.assertEqual(len(data["hooks"][event]), 1)
            self.assertIn("codevault.cli hook claude", data["hooks"][event][0]["hooks"][0]["command"])

        self.assertEqual(run_cli(self.project, "hooks", "remove", "claude", str(self.project)).returncode, 0)
        data = json.loads(settings.read_text(encoding="utf-8"))
        self.assertNotIn("hooks", data)
        self.assertEqual(data["permissions"], {"allow": ["Bash(ls)"]})

    def test_snapshot_command_labels_checkpoint(self):
        (self.project / "a.py").write_text("a = 1\n", encoding="utf-8")
        (self.project / "b.js").write_text("let b = 2;\n", encoding="utf-8")
        result = run_cli(self.project, "snapshot", ".", "--source", "antigravity", "--note", "before agent run")
        self.assertEqual(result.returncode, 0, result.stderr)
        db = BackupEngine(self.project, self.config).db
        for name in ("a.py", "b.js"):
            snaps = db.get_snapshots_for_file(name)
            self.assertEqual(snaps[-1]["event_type"], "checkpoint")
            self.assertEqual(snaps[-1]["note"], "antigravity · before agent run")


if __name__ == "__main__":
    unittest.main()
