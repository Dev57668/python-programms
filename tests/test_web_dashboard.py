"""
Tests for the web dashboard API and the stale-delete watcher fix.
"""

import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

from codevault.config import Config
from codevault.recovery import RecoveryEngine
from codevault.watcher import CodeVaultEventHandler
from codevault.web.server import DashboardApi, make_handler


class TestDashboardApi(unittest.TestCase):
    """Exercises the JSON API over a real local HTTP server."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp()).resolve()
        self.config = Config()
        self.engine = RecoveryEngine(self.test_dir, self.config)
        self.backup = self.engine.backup_engine

        self.source = self.test_dir / "calc.py"
        self.source.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        self.snap1 = self.backup.create_snapshot(self.source, event_type="created")
        self.source.write_text("def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n", encoding="utf-8")
        self.snap2 = self.backup.create_snapshot(self.source)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(DashboardApi(self.test_dir, self.config)))
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _get(self, path):
        with urllib.request.urlopen(self.base + path) as r:
            return json.loads(r.read())

    def _post(self, path, body, content_type="application/json"):
        req = urllib.request.Request(
            self.base + path, data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": content_type},
        )
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_index_served(self):
        with urllib.request.urlopen(self.base + "/") as r:
            self.assertIn(b"CodeVault", r.read())

    def test_overview_and_files(self):
        overview = self._get("/api/overview")
        self.assertEqual(overview["stats"]["snapshots"], 2)
        self.assertEqual(overview["stats"]["protected_files"], 1)
        files = self._get("/api/files")
        self.assertEqual([f["path"] for f in files], ["calc.py"])
        self.assertEqual(files[0]["snapshots"], 2)

    def test_history_newest_first(self):
        history = self._get("/api/history?path=calc.py")
        self.assertEqual([s["id"] for s in history["snapshots"]], [self.snap2["id"], self.snap1["id"]])

    def test_diff_between_snapshots(self):
        diff = self._get(f"/api/diff?from={self.snap1['id']}&to={self.snap2['id']}")
        self.assertEqual(diff["added"], 3)
        self.assertEqual(diff["removed"], 0)
        added = [l["text"] for l in diff["lines"] if l["kind"] == "add"]
        self.assertIn("def sub(a, b):", added)

    def test_restore_deleted_file(self):
        self.source.unlink()
        self.backup.handle_deletion(self.source)
        self.assertEqual(len(self._get("/api/deleted")), 1)

        status, body = self._post("/api/restore", {"id": self.snap1["id"]})
        self.assertEqual(status, 200, body)
        self.assertEqual(self.source.read_text(encoding="utf-8"), "def add(a, b):\n    return a + b\n")

    def test_pin_and_verify(self):
        status, _ = self._post("/api/pin", {"id": self.snap1["id"], "pinned": True})
        self.assertEqual(status, 200)
        self.assertEqual(self._get("/api/overview")["stats"]["pinned"], 1)

        status, result = self._post("/api/verify", {})
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])
        self.assertEqual(result["counts"]["valid"], 2)

    def test_post_requires_json(self):
        status, _ = self._post("/api/restore", {"id": self.snap1["id"]}, content_type="text/plain")
        self.assertEqual(status, 415)

    def test_unknown_snapshot(self):
        status, body = self._post("/api/restore", {"id": 9999})
        self.assertEqual(status, 404)
        self.assertIn("error", body)


class TestRestoreErrorMessage(unittest.TestCase):
    """CLI output from a failed restore becomes a dashboard message without CLI hints."""

    def test_messages(self):
        from codevault.web.server import _restore_error
        self.assertIn("integrity check", _restore_error("\n[Error] Snapshot integrity verification failed!\n  Expected: x"))
        self.assertEqual(_restore_error("\n[Error] Snapshot file missing on disk: /a/b\n"), "Snapshot file missing on disk: /a/b")
        self.assertTrue(_restore_error(""))


class TestStaleDeleteEvent(unittest.TestCase):
    """A delete event for a path that still exists must not mark it deleted."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp()).resolve()
        self.engine = RecoveryEngine(self.test_dir, Config())
        self.backup = self.engine.backup_engine

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_existing_file_not_marked_deleted(self):
        source = self.test_dir / "main.py"
        source.write_text("print(1)\n", encoding="utf-8")
        self.backup.create_snapshot(source)

        handler = CodeVaultEventHandler(self.backup, self.backup.config)
        handler.on_deleted(SimpleNamespace(is_directory=False, src_path=str(source)))
        handler._cancel_timer(str(source))

        self.assertEqual(self.backup.db.get_tracked_files()["main.py"]["status"], "active")
        self.assertEqual(self.backup.db.get_deletions(), [])


if __name__ == "__main__":
    unittest.main()
