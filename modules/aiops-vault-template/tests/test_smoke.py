import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "aiops.py"


class SmokeTests(unittest.TestCase):
    def test_example_jsonl_parses(self):
        path = ROOT / "maintenance-log.example.jsonl"
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertGreaterEqual(len(lines), 1)
        for line in lines:
            obj = json.loads(line)
            self.assertIn("summary", obj)
            self.assertNotIn("SECRET", json.dumps(obj))

    def test_cli_check_on_repo_examples(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td) / "vault"
            subprocess.check_call(
                [sys.executable, str(ROOT / "scripts" / "install.py"), "--vault", str(vault), "--agent", "none"]
            )
            out = subprocess.check_output(
                [sys.executable, str(vault / "scripts" / "aiops.py"), "check"],
                cwd=vault,
                text=True,
            )
            self.assertIn("check passed", out)

    def test_installed_absolute_script_detects_own_vault(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td) / "vault"
            subprocess.check_call(
                [sys.executable, str(ROOT / "scripts" / "install.py"), "--vault", str(vault), "--agent", "none"]
            )
            out = subprocess.check_output(
                [sys.executable, str(vault / "scripts" / "aiops.py"), "check"],
                cwd=ROOT,
                text=True,
            )
            self.assertIn("check passed", out)
            self.assertNotIn("WARN", out)

    def test_cli_slice_commands(self):
        env = os.environ.copy()
        env["AIOPS_ROOT"] = str(ROOT)
        out = subprocess.check_output(
            [sys.executable, str(SCRIPT), "resources", "--section", "Service Inventory"],
            env=env,
            text=True,
        )
        self.assertIn("example-api", out)
        out = subprocess.run(
            [sys.executable, str(SCRIPT), "host", "demo-vps"],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
        )
        self.assertEqual(out.returncode, 0)
        self.assertIn("demo-vps", out.stdout)

    def test_service_catalog_then_exact_dynamic_load(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td) / "vault"
            services = vault / "services"
            for service_id, name, summary in [
                ("example-api", "Example API", "Fictional API service for public tests."),
                ("notes-web", "Notes Web", "Fictional local notes website."),
            ]:
                directory = services / service_id
                directory.mkdir(parents=True)
                record = {
                    "schema": "aios.ops.service.v1",
                    "id": service_id,
                    "name": name,
                    "summary": summary,
                    "aliases": [name.lower()],
                    "references": [
                        {
                            "kind": "current_state",
                            "path": "resources.md",
                            "selector": service_id,
                        }
                    ],
                }
                if service_id == "example-api":
                    record["details"] = "service-card.md"
                    (directory / "service-card.md").write_text(
                        f"# {name}\n\nDetailed runbook for {service_id}.\n",
                        encoding="utf-8",
                    )
                (directory / "service.json").write_text(
                    json.dumps(record),
                    encoding="utf-8",
                )
            env = os.environ.copy()
            env["AIOPS_ROOT"] = str(vault)
            catalog = json.loads(
                subprocess.check_output(
                    [sys.executable, str(SCRIPT), "services", "--json"],
                    env=env,
                    text=True,
                )
            )
            self.assertEqual(catalog["schema"], "aios.ops.service-catalog.v1")
            self.assertEqual(
                [sorted(item) for item in catalog["services"]],
                [["id", "name", "summary"], ["id", "name", "summary"]],
            )
            self.assertNotIn("Detailed runbook", json.dumps(catalog))

            context = json.loads(
                subprocess.check_output(
                    [sys.executable, str(SCRIPT), "service", "example api", "--json"],
                    env=env,
                    text=True,
                )
            )
            self.assertEqual(context["service"]["id"], "example-api")
            self.assertIn("Detailed runbook for example-api", context["details"])
            self.assertEqual(context["details_path"], "services/example-api/service-card.md")

            referenced_only = json.loads(
                subprocess.check_output(
                    [sys.executable, str(SCRIPT), "service", "notes-web", "--json"],
                    env=env,
                    text=True,
                )
            )
            self.assertIsNone(referenced_only["details"])
            self.assertIsNone(referenced_only["details_path"])
            self.assertEqual(referenced_only["service"]["references"][0]["selector"], "notes-web")

            non_exact = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "service",
                    "unregistered semantic request",
                ],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(non_exact.returncode, 1)
            self.assertIn("services --json", non_exact.stderr)

    def test_cli_log_query(self):
        env = os.environ.copy()
        env["AIOPS_ROOT"] = str(ROOT)
        out = subprocess.check_output(
            [sys.executable, str(SCRIPT), "log", "--query", "example maintenance", "--summary"],
            env=env,
            text=True,
        )
        self.assertIn("example", out.lower())


if __name__ == "__main__":
    unittest.main()
