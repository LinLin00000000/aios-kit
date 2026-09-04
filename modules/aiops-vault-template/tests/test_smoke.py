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

    def test_service_template_declares_visibility(self):
        record = json.loads((ROOT / "templates" / "service.json").read_text(encoding="utf-8"))
        self.assertIn(record["visibility"], {"public", "private"})

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
            for service_id, name, summary, visibility in [
                ("example-api", "Example API", "Fictional API service for public tests.", "public"),
                ("notes-web", "Notes Web", "Fictional local notes website.", "private"),
            ]:
                directory = services / service_id
                directory.mkdir(parents=True)
                record = {
                    "schema": "aios.ops.service.v1",
                    "id": service_id,
                    "name": name,
                    "summary": summary,
                    "visibility": visibility,
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
                [["id", "name", "summary", "visibility"], ["id", "name", "summary", "visibility"]],
            )
            self.assertEqual(
                {item["id"]: item["visibility"] for item in catalog["services"]},
                {"example-api": "public", "notes-web": "private"},
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
            self.assertEqual(context["service"]["visibility"], "public")
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

            for query in (
                "unregistered semantic request",
                "please inspect example-api health",
                "what is wrong with Example API today",
            ):
                with self.subTest(non_exact_query=query):
                    non_exact = subprocess.run(
                        [sys.executable, str(SCRIPT), "service", query],
                        env=env,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    self.assertEqual(non_exact.returncode, 1)
                    self.assertIn("services --json", non_exact.stderr)

    def test_check_rejects_cross_service_selector_collisions(self):
        scenarios = {
            "name_vs_name": [
                ("alpha", "Shared Name", []),
                ("beta", "shared-name", []),
            ],
            "alias_vs_id": [
                ("alpha", "Alpha Service", ["beta"]),
                ("beta", "Beta Service", []),
            ],
            "empty_after_normalization": [
                ("alpha", "Alpha Service", ["---"]),
            ],
        }
        for scenario, records in scenarios.items():
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as td:
                vault = Path(td) / "vault"
                (vault / "scripts").mkdir(parents=True)
                for path, content in {
                    "README.md": "# Synthetic vault\n",
                    "resources.md": "# Synthetic resources\n",
                    "maintenance-log.schema.md": "# Synthetic schema\n",
                    "maintenance-log.jsonl": "",
                    "scripts/aiops.py": "# existence marker for check\n",
                }.items():
                    (vault / path).write_text(content, encoding="utf-8")
                for service_id, name, aliases in records:
                    directory = vault / "services" / service_id
                    directory.mkdir(parents=True)
                    (directory / "service.json").write_text(
                        json.dumps(
                            {
                                "schema": "aios.ops.service.v1",
                                "id": service_id,
                                "name": name,
                                "summary": "Fully synthetic collision fixture.",
                                "visibility": "private",
                                "aliases": aliases,
                                "references": [],
                            }
                        ),
                        encoding="utf-8",
                    )
                env = os.environ.copy()
                env["AIOPS_ROOT"] = str(vault)
                out = subprocess.run(
                    [sys.executable, str(SCRIPT), "check"],
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
                self.assertIn("selector", (out.stdout + out.stderr).lower())

    def test_check_requires_valid_visibility(self):
        for label, visibility in [("missing", None), ("invalid", "pending")]:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                vault = Path(td) / "vault"
                (vault / "scripts").mkdir(parents=True)
                for path, content in {
                    "README.md": "# Synthetic vault\n",
                    "resources.md": "# Synthetic resources\n",
                    "maintenance-log.schema.md": "# Synthetic schema\n",
                    "maintenance-log.jsonl": "",
                    "scripts/aiops.py": "# existence marker for check\n",
                }.items():
                    (vault / path).write_text(content, encoding="utf-8")
                record = {
                    "schema": "aios.ops.service.v1",
                    "id": "visibility-fixture",
                    "name": "Visibility Fixture",
                    "summary": "Synthetic visibility validation fixture.",
                    "aliases": [],
                    "references": [],
                }
                if visibility is not None:
                    record["visibility"] = visibility
                directory = vault / "services" / "visibility-fixture"
                directory.mkdir(parents=True)
                (directory / "service.json").write_text(json.dumps(record), encoding="utf-8")
                env = os.environ.copy()
                env["AIOPS_ROOT"] = str(vault)
                out = subprocess.run(
                    [sys.executable, str(SCRIPT), "check"],
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self.assertNotEqual(out.returncode, 0)
                self.assertIn("visibility", (out.stdout + out.stderr).lower())

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
