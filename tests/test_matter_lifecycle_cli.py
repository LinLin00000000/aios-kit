from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "aios.py"


class MatterLifecycleCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="aios-matter-test-")
        self.home = Path(self.tmp.name)
        self.work = self.home / "aios" / "work"
        self.work.mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_cli(self, *args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
        cp = subprocess.run(
            [sys.executable, str(CLI), "--home", str(self.home), *args],
            cwd=str(ROOT), text=True, capture_output=True,
        )
        if ok and cp.returncode != 0:
            self.fail(f"command failed {args}:\nstdout={cp.stdout}\nstderr={cp.stderr}")
        return cp

    def create_worksite(self, name: str, *, matter: dict[str, object] | None = None, status: str = "completed") -> Path:
        wd = self.work / name
        (wd / "internal").mkdir(parents=True)
        (wd / "mission.md").write_text(f"# {name}\n\nstatus: {status}\n", encoding="utf-8")
        (wd / "final-report.md").write_text("# final\n", encoding="utf-8")
        if matter is not None:
            (wd / "internal" / "matter.json").write_text(json.dumps(matter), encoding="utf-8")
        return wd

    def test_index_query_and_curated_view(self) -> None:
        wd = self.create_worksite(
            "20260712-100000_workflow-core",
            matter={
                "schema": "aios.workflow.state.v0",
                "id": "matter_workflow_core",
                "title": "Workflow Core",
                "status": "dogfooding_active",
                "aliases": ["workflow", "workflow core"],
                "current_focus": "Workbench MVP",
                "lifecycle": {"state": "active", "attention": "paused", "reopenable": True},
                "delivery": {"featured": ["final-report.md"], "limit": 4},
            },
        )
        self.create_worksite("20260711-090000_old-workflow-research", status="completed")
        index = json.loads(self.run_cli("matter", "index", "--json").stdout)
        self.assertEqual(index["schema"], "aios.matter.index.v1")
        self.assertEqual(index["counts"]["active"], 1)
        self.assertEqual(index["counts"]["reopenable"], 1)
        record = json.loads(self.run_cli("matter", "get", "workflow").stdout)
        self.assertEqual(record["id"], "matter_workflow_core")
        self.assertEqual(record["attention"], "paused")
        self.assertEqual(record["delivery_paths"], ["mission.md", "final-report.md"])
        listed = json.loads(self.run_cli("matter", "list", "--reopenable", "--json").stdout)
        self.assertEqual([row["id"] for row in listed], ["matter_workflow_core"])
        exact_list = json.loads(self.run_cli("matter", "list", "--query", "workflow", "--json").stdout)
        self.assertEqual([row["id"] for row in exact_list], ["matter_workflow_core"])

        report = json.loads(self.run_cli("matter", "view", "build", "--json").stdout)
        view = Path(report["path"])
        self.assertTrue((view / "index.html").exists())
        top_html = (view / "index.html").read_text(encoding="utf-8")
        self.assertIn("打开或可继续", top_html)
        self.assertIn("已关闭或已归档", top_html)
        item = view / "matter_workflow_core"
        self.assertTrue((item / "index.html").exists())
        self.assertEqual((item / "files" / "mission.md").resolve(), (wd / "mission.md").resolve())
        self.assertFalse((item / "internal").exists())

    def test_closeout_plan_and_quarantine_restore(self) -> None:
        wd = self.create_worksite(
            "20260712-110000_closed-task",
            matter={
                "id": "matter_closed",
                "title": "Closed Task",
                "status": "completed",
                "lifecycle": {"state": "closed", "attention": "none", "reopenable": False},
            },
        )
        cache = wd / "internal" / "agents" / "worker" / "__pycache__"
        cache.mkdir(parents=True)
        (cache / "x.pyc").write_bytes(b"cache")
        plan = json.loads(self.run_cli("lll", "closeout-plan", "matter_closed").stdout)
        self.assertEqual(plan["schema"], "aios.lll.closeout-plan.v1")
        self.assertIn("final-report.md", plan["promote_candidates"])
        self.assertNotIn("mission.md", plan["promote_candidates"])
        self.assertIn("final-report.md", plan["requires_approval"])
        self.assertEqual(plan["asset_retention_gate"]["status"], "awaiting_agent_assessment")
        self.assertFalse(plan["asset_retention_gate"]["automatic_promotion"])
        self.assertTrue(plan["asset_retention_gate"]["requires_explicit_user_trigger"])
        self.assertTrue(any(x["path"].endswith("__pycache__") for x in plan["quarantine_candidates"]))

        applied = json.loads(self.run_cli("lll", "quarantine", "matter_closed", "--apply").stdout)
        self.assertFalse(wd.exists())
        self.assertTrue(Path(applied["destination"]).exists())
        token = applied["token"]
        self.run_cli("lll", "restore", token, "--apply")
        self.assertTrue(wd.exists())
        manifest = self.home / "aios" / "state" / "matters" / "quarantine" / f"{token}.json"
        self.assertEqual(json.loads(manifest.read_text())["status"], "restored")

    def test_open_reopenable_matter_cannot_be_quarantined(self) -> None:
        self.create_worksite(
            "20260712-120000_open-task",
            matter={
                "id": "matter_open",
                "title": "Open Task",
                "status": "active",
                "lifecycle": {"state": "active", "reopenable": True},
            },
        )
        cp = self.run_cli("lll", "quarantine", "matter_open", "--apply", ok=False)
        self.assertNotEqual(cp.returncode, 0)
        self.assertIn("open/reopenable", cp.stderr + cp.stdout)


if __name__ == "__main__":
    unittest.main()
