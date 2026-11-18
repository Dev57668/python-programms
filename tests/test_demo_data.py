"""Checks the data behind the interactive hosted demo (codevault/web/static/demo/projects.json)."""

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "codevault/web/static/demo/projects.json"


class TestDemoProjects(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.projects = json.loads(DATA.read_text(encoding="utf-8"))["projects"]

    def test_three_sample_projects(self):
        self.assertEqual([p["name"] for p in self.projects], ["gradebook-app", "todo-cli", "weather-bot"])

    def test_snapshot_ids_unique_and_chronological(self):
        for p in self.projects:
            ids = [s["id"] for s in p["snapshots"]]
            self.assertEqual(len(ids), len(set(ids)), p["name"])
            ordered = sorted(p["snapshots"], key=lambda s: -s["ago_min"])
            by_file = {}
            for s in ordered:
                by_file.setdefault(s["path"], []).append(s["id"])
            for path, seq in by_file.items():
                self.assertEqual(seq, sorted(seq), f"{p['name']}:{path} ids must grow with time")

    def test_recorded_hashes_match_content(self):
        for p in self.projects:
            for s in p["snapshots"]:
                if s.get("hash"):
                    self.assertEqual(hashlib.sha256(s["content"].encode()).hexdigest(), s["hash"], f"{p['name']} #{s['id']}")

    def test_git_states_are_valid_and_ordered(self):
        order = {"pushed": 0, "committed": 1, "local": 2}
        for p in self.projects:
            by_file = {}
            for s in sorted(p["snapshots"], key=lambda s: -s["ago_min"]):
                self.assertIn(s["git"], order)
                by_file.setdefault(s["path"], []).append(order[s["git"]])
            for path, seq in by_file.items():  # once a version is local-only, later ones can't be "pushed"
                self.assertEqual(seq, sorted(seq), f"{p['name']}:{path}")

    def test_deleted_files_have_snapshots(self):
        for p in self.projects:
            paths = {s["path"] for s in p["snapshots"]}
            for path in p["deleted"]:
                self.assertIn(path, paths)

    def test_build_script_ships_the_data(self):
        with tempfile.TemporaryDirectory() as out:
            subprocess.run(["bash", str(ROOT / "scripts/build_landing.sh"), out], check=True, cwd=ROOT, capture_output=True)
            self.assertTrue((Path(out) / "demo/projects.json").exists())
            self.assertIn("demo.js", (Path(out) / "dashboard/index.html").read_text())


if __name__ == "__main__":
    unittest.main()
