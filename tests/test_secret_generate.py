#!/usr/bin/env python3
"""Focused tests for non-interactive machine secret generation."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "aios.py"


class SecretGenerateTests(unittest.TestCase):
    def run_cli(self, home: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), "--home", str(home), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

    def write_request(self, home: Path, request_id: str, *, secret_id: str = "fixture.machine") -> Path:
        pending = home / "aios" / "vault" / "secrets" / "requests" / "pending"
        pending.mkdir(parents=True, exist_ok=True)
        path = pending / f"{request_id}.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "request_id": request_id,
                    "kind": "secret_intake",
                    "secret_id": secret_id,
                    "title": "Machine-only test secret",
                    "fields": [
                        {"name": "session_secret", "type": "password", "secret": True, "required": True},
                        {"name": "redis_password", "type": "password", "secret": True, "required": True, "generate": True, "length": 16},
                        {"name": "environment", "type": "string", "secret": False, "required": True, "default": "test"},
                    ],
                    "item": {
                        "kind": "machine_secret",
                        "intended_use": ["tests"],
                        "metadata": {"agent_can_read_plaintext": False},
                    },
                    "consumers": [],
                    "replicas": [],
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_dry_run_lists_fields_without_creating_layout_or_values(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aios-secret-generate-") as raw_home:
            home = Path(raw_home)
            request_path = self.write_request(home, "req_dry_run")
            result = self.run_cli(home, "secret", "generate", "req_dry_run", "--dry-run", "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["generated_fields"], ["session_secret", "redis_password"])
            self.assertEqual(payload["default_fields"], ["environment"])
            self.assertFalse(payload["secret_values_exposed"])
            self.assertEqual(request_path.read_text(encoding="utf-8").startswith("{"), True)
            secrets_root = home / "aios" / "vault" / "secrets"
            self.assertFalse((secrets_root / "values").exists())
            self.assertFalse((secrets_root / "items").exists())
            self.assertFalse((secrets_root / "receipts").exists())
            self.assertFalse((secrets_root / "audit.jsonl").exists())

    def test_generate_persists_shared_outputs_and_redacts_values(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aios-secret-generate-") as raw_home:
            home = Path(raw_home)
            self.write_request(home, "req_generate")
            result = self.run_cli(home, "secret", "generate", "req_generate", "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["secret_id"], "fixture.machine")
            self.assertEqual(payload["generated_fields"], ["session_secret", "redis_password"])
            self.assertFalse(payload["secret_values_exposed"])

            secrets_root = home / "aios" / "vault" / "secrets"
            value_path = secrets_root / "values" / "fixture.machine.json"
            item_path = secrets_root / "items" / "fixture.machine.yaml"
            receipt_path = secrets_root / "receipts" / "req_generate.json"
            done_path = secrets_root / "requests" / "done" / "req_generate.json"
            self.assertTrue(value_path.exists())
            self.assertTrue(item_path.exists())
            self.assertTrue(receipt_path.exists())
            self.assertTrue(done_path.exists())
            self.assertFalse((secrets_root / "requests" / "pending" / "req_generate.json").exists())

            values = json.loads(value_path.read_text(encoding="utf-8"))["values"]
            generated_values = [values["session_secret"], values["redis_password"]]
            self.assertEqual(len(values["session_secret"]), 64)
            self.assertRegex(values["session_secret"], r"^[0-9a-f]{64}$")
            self.assertEqual(len(values["redis_password"]), 32)
            self.assertRegex(values["redis_password"], r"^[0-9a-f]{32}$")
            output = result.stdout + result.stderr
            for value in generated_values:
                self.assertNotIn(value, output)
                self.assertNotIn(value, receipt_path.read_text(encoding="utf-8"))
                self.assertNotIn(value, item_path.read_text(encoding="utf-8"))
            audit = (secrets_root / "audit.jsonl").read_text(encoding="utf-8")
            self.assertIn('"event": "generate_completed"', audit)
            for value in generated_values:
                self.assertNotIn(value, audit)

    def test_human_credential_and_missing_default_fail_closed(self) -> None:
        cases = [
            (
                "req_api_key",
                [{"name": "api_key", "type": "password", "secret": True, "required": True}],
                "human-provided credential",
            ),
            (
                "req_missing_default",
                [{"name": "environment", "type": "string", "secret": False, "required": True}],
                "non-secret fields must define a default",
            ),
        ]
        for request_id, fields, message in cases:
            with self.subTest(request_id=request_id), tempfile.TemporaryDirectory(prefix="aios-secret-generate-") as raw_home:
                home = Path(raw_home)
                path = self.write_request(home, request_id)
                data = json.loads(path.read_text(encoding="utf-8"))
                data["fields"] = fields
                path.write_text(json.dumps(data), encoding="utf-8")
                result = self.run_cli(home, "secret", "generate", request_id)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertFalse((home / "aios" / "vault" / "secrets" / "values" / "fixture.machine.json").exists())
                self.assertTrue(path.exists())

    def test_small_length_is_rejected_before_generation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aios-secret-generate-") as raw_home:
            home = Path(raw_home)
            path = self.write_request(home, "req_small_length")
            data = json.loads(path.read_text(encoding="utf-8"))
            data["fields"][0]["length"] = 8
            path.write_text(json.dumps(data), encoding="utf-8")
            result = self.run_cli(home, "secret", "generate", "req_small_length")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("at least 16 bytes", result.stderr)
            self.assertFalse((home / "aios" / "vault" / "secrets" / "values" / "fixture.machine.json").exists())

    def test_existing_secret_requires_force_and_force_replaces(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aios-secret-generate-") as raw_home:
            home = Path(raw_home)
            self.write_request(home, "req_first")
            first = self.run_cli(home, "secret", "generate", "req_first", "--json")
            self.assertEqual(first.returncode, 0, first.stderr)
            value_path = home / "aios" / "vault" / "secrets" / "values" / "fixture.machine.json"
            old_values = json.loads(value_path.read_text(encoding="utf-8"))["values"]

            self.write_request(home, "req_second")
            refused = self.run_cli(home, "secret", "generate", "req_second")
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("pass --force", refused.stderr)
            self.assertEqual(json.loads(value_path.read_text(encoding="utf-8"))["values"], old_values)
            self.assertTrue((home / "aios" / "vault" / "secrets" / "requests" / "pending" / "req_second.json").exists())

            replaced = self.run_cli(home, "secret", "generate", "req_second", "--force", "--json")
            self.assertEqual(replaced.returncode, 0, replaced.stderr)
            new_values = json.loads(value_path.read_text(encoding="utf-8"))["values"]
            self.assertNotEqual(new_values, old_values)
            self.assertNotIn(new_values["session_secret"], replaced.stdout + replaced.stderr)
            self.assertFalse((home / "aios" / "vault" / "secrets" / "requests" / "pending" / "req_second.json").exists())
            self.assertTrue((home / "aios" / "vault" / "secrets" / "requests" / "done" / "req_second.json").exists())


if __name__ == "__main__":
    unittest.main()
