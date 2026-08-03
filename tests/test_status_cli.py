from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "aios.py"
SKILL = ROOT / "skills" / "aios-agent" / "SKILL.md"


def tree_fingerprint(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class StatusCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="aios-status-test-")
        self.home = Path(self.tmp.name)
        ops = self.home / "aios" / "vault" / "ops"
        projects = ops / "projects"
        sources = ops / "sources"
        projects.mkdir(parents=True)
        sources.mkdir(parents=True)
        project_rows = [
            {"id": "alpha", "name": "Alpha", "status": "active"},
            {"id": "beta", "name": "Beta", "status": "paused"},
            {"id": "gamma", "name": "Gamma", "status": "active"},
        ]
        (projects / "registry.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in project_rows), encoding="utf-8"
        )
        (sources / "registry.jsonl").write_text(
            json.dumps(
                {
                    "id": "notes",
                    "name": "Notes",
                    "kind": "data_root",
                    "status": "active",
                    "locations": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        for key in ("AIOS_ROOT", "AIOS_HOME", "AIOS_AGENT_SKILLS_DIR", "AIOS_SKILLS_DIR", "PYTHONPYCACHEPREFIX"):
            env.pop(key, None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        cp = subprocess.run(
            [sys.executable, str(CLI), "--home", str(self.home), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            env=env,
        )
        if cp.returncode:
            self.fail(f"command failed {args}:\nstdout={cp.stdout}\nstderr={cp.stderr}")
        return cp

    def test_json_envelope_is_compact_stable_and_read_only(self) -> None:
        before = tree_fingerprint(self.home)
        first = self.run_cli("status", "--json").stdout
        second = self.run_cli("status", "--json").stdout
        after = tree_fingerprint(self.home)

        self.assertEqual(first, second)
        self.assertEqual(first.count("\n"), 1)
        self.assertNotIn(": ", first)
        self.assertEqual(before, after, "status must not create or mutate instance files")

        payload = json.loads(first)
        self.assertEqual(payload["schema"], "aios.status.v1")
        self.assertIs(payload["ok"], True)
        self.assertEqual(
            payload["paths"],
            {
                "agent_skills": str(self.home / ".agents" / "skills"),
                "modules": str(self.home / "aios" / "modules"),
                "ops": str(self.home / "aios" / "vault" / "ops"),
                "root": str(self.home / "aios"),
                "skills": str(self.home / "aios" / "skills"),
                "work": str(self.home / "aios" / "work"),
            },
        )
        self.assertEqual(payload["projects"], {"by_status": {"active": 2, "paused": 1}, "total": 3})
        self.assertEqual(
            payload["sources"],
            {"explicit": 1, "project_projections": 3, "total": 4},
        )

    def test_default_human_output_is_preserved(self) -> None:
        paths = {
            "root": self.home / "aios",
            "ops": self.home / "aios" / "vault" / "ops",
            "work": self.home / "aios" / "work",
            "skills": self.home / "aios" / "skills",
            "agent_skills": self.home / ".agents" / "skills",
            "modules": self.home / "aios" / "modules",
        }
        expected = "\n".join(
            [
                f"AIOS root: {paths['root']}",
                f"OPS vault: {paths['ops']}",
                f"Work root: {paths['work']}",
                f"AIOS skills metadata/cache: {paths['skills']}",
                f"Agent runtime skills: {paths['agent_skills']}",
                f"Modules: {paths['modules']}",
                "Projects: 3 {'active': 2, 'paused': 1}",
                "Sources: 4 (1 explicit + 3 project projections)",
                "",
            ]
        )
        self.assertEqual(self.run_cli("status").stdout, expected)


class AiosAgentRetentionWordingTests(unittest.TestCase):
    def test_closeout_uses_candidate_not_authorization_language(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        required = [
            "candidate deliverables",
            "Agent value assessment",
            "explicit user retention intent",
            "not selected or authorized",
            "one canonical deliverable plus exact evidence pointers",
            "full Worksite remains the provenance owner",
            "A high score is advice, never authorization.",
            "Prohibited before that precondition: asset creation, copying, linking, and promotion.",
        ]
        for phrase in required:
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
