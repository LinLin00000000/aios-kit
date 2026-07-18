#!/usr/bin/env python3
"""Focused stdlib regression tests for the federated Source CLI."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "aios.py"


class SourceCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="aios-source-test-")
        self.home = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_cli(self, *args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(CLI), "--home", str(self.home), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if ok and result.returncode != 0:
            self.fail(f"command failed: {args}\nstdout={result.stdout}\nstderr={result.stderr}")
        if not ok and result.returncode == 0:
            self.fail(f"command unexpectedly passed: {args}\nstdout={result.stdout}")
        return result

    def source_record(self, source_id: str, *aliases: str) -> dict[str, object]:
        return {
            "id": source_id,
            "name": source_id.title(),
            "kind": "data_root",
            "aliases": list(aliases),
            "status": "active",
            "locations": [{"kind": "local", "path": f"~/{source_id.title()}"}],
            "authority": "source_registry",
            "owner_ref": "",
            "access_mode": "read_only_reference",
            "sync_mode": "none",
            "backup_status": "unknown",
            "sensitivity": "private",
            "include": [],
            "exclude": [],
            "notes": "",
        }

    def add_source(self, *extra: str) -> None:
        self.run_cli(
            "source", "add",
            "--id", "notes",
            "--name", "Notes",
            "--kind", "data_root",
            "--path", "~/Notes",
            "--alias", "knowledge",
            *extra,
        )

    def test_add_get_list_and_validate(self) -> None:
        self.add_source()
        item = json.loads(self.run_cli("source", "get", "knowledge", "--json").stdout)
        self.assertEqual(item["id"], "notes")
        listed = json.loads(self.run_cli("source", "list", "--json").stdout)
        self.assertEqual([row["id"] for row in listed], ["notes"])
        self.assertIn("1 explicit", self.run_cli("source", "validate").stdout)

    def test_invalid_location_kind_is_rejected_without_partial_registry_write(self) -> None:
        result = self.run_cli(
            "source", "add",
            "--id", "broken",
            "--name", "Broken",
            "--kind", "data_root",
            "--path", "~/Broken",
            "--location-kind", "github",
            ok=False,
        )
        self.assertIn("location kind", result.stderr + result.stdout)
        registry = self.home / "aios" / "vault" / "ops" / "sources" / "registry.jsonl"
        self.assertFalse(registry.exists(), "invalid add must not leave a partial registry record")

    def test_alias_cannot_shadow_an_existing_source_id(self) -> None:
        self.add_source()
        result = self.run_cli(
            "source", "add",
            "--id", "archive",
            "--name", "Archive",
            "--kind", "data_root",
            "--path", "~/Archive",
            "--alias", "notes",
            ok=False,
        )
        self.assertIn("conflicts with existing identity", result.stderr + result.stdout)
        rows = (self.home / "aios" / "vault" / "ops" / "sources" / "registry.jsonl").read_text().splitlines()
        self.assertEqual(len(rows), 1, "rejected alias must not append a second record")

    def test_project_projection_and_alias_are_federated_without_duplication(self) -> None:
        projects = self.home / "aios" / "vault" / "ops" / "projects"
        projects.mkdir(parents=True)
        (projects / "registry.jsonl").write_text(
            json.dumps({
                "id": "demo-project",
                "name": "Demo Project",
                "status": "idea",
                "aliases": ["demo"],
                "locations": [{"kind": "local", "path": "~/projects/demo"}],
            }) + "\n",
            encoding="utf-8",
        )
        (projects / "aliases.yaml").write_text("aliases:\n  demo: demo-project\n", encoding="utf-8")

        listed = json.loads(self.run_cli("source", "list", "--json").stdout)
        self.assertEqual([row["id"] for row in listed], ["demo-project"])
        self.assertEqual(listed[0]["record_type"], "project_projection")
        idea_only = json.loads(self.run_cli("source", "list", "--status", "idea", "--json").stdout)
        self.assertEqual([row["id"] for row in idea_only], ["demo-project"])
        self.assertEqual(json.loads(self.run_cli("source", "get", "demo", "--json").stdout)["id"], "demo-project")
        self.assertEqual(json.loads(self.run_cli("project", "get", "demo", "--json").stdout)["id"], "demo-project")

        result = self.run_cli(
            "source", "add",
            "--id", "notes",
            "--name", "Notes",
            "--kind", "data_root",
            "--path", "~/Notes",
            "--alias", "demo",
            ok=False,
        )
        self.assertIn("existing identity", result.stderr + result.stdout)

    def test_inline_alias_cannot_be_silently_hijacked(self) -> None:
        sources = self.home / "aios" / "vault" / "ops" / "sources"
        sources.mkdir(parents=True)
        (sources / "registry.jsonl").write_text(
            json.dumps(self.source_record("old", "shared")) + "\n",
            encoding="utf-8",
        )
        result = self.run_cli(
            "source", "add", "--id", "new", "--name", "New", "--kind", "data_root",
            "--path", "~/New", "--alias", "shared", ok=False,
        )
        self.assertIn("conflicts with existing identity", result.stderr + result.stdout)
        self.assertEqual(json.loads(self.run_cli("source", "get", "shared").stdout)["id"], "old")
        self.assertIn("ok", self.run_cli("source", "validate").stdout)

    def test_validate_rejects_cross_record_inline_alias_collision(self) -> None:
        sources = self.home / "aios" / "vault" / "ops" / "sources"
        sources.mkdir(parents=True)
        rows = [self.source_record("one", "shared"), self.source_record("two", "shared")]
        (sources / "registry.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows),
            encoding="utf-8",
        )
        result = self.run_cli("source", "validate", ok=False)
        self.assertIn("source identity shared: claimed by one, two", result.stdout)

    def test_validate_rejects_alias_file_hijacking_inline_alias(self) -> None:
        sources = self.home / "aios" / "vault" / "ops" / "sources"
        sources.mkdir(parents=True)
        rows = [self.source_record("old", "shared"), self.source_record("new")]
        (sources / "registry.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows),
            encoding="utf-8",
        )
        (sources / "aliases.yaml").write_text("aliases:\n  shared: new\n", encoding="utf-8")
        result = self.run_cli("source", "validate", ok=False)
        self.assertIn("source identity shared: claimed by new, old", result.stdout)


if __name__ == "__main__":
    unittest.main()
