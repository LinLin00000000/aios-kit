#!/usr/bin/env python3
"""Focused CLI-surface tests for the O70 provider-neutral routes."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "aios.py"


class AiosRouteCliTests(unittest.TestCase):
    def run_cli(self, home: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), "--home", str(home), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

    def test_route_help_is_discoverable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aios-route-help-") as raw_home:
            home = Path(raw_home)
            top = self.run_cli(home, "--help")
            self.assertEqual(top.returncode, 0, top.stderr)
            for command in ("resource", "decision"):
                self.assertIn(command, top.stdout)
                result = self.run_cli(home, command, "--help")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout)
            self.assertIn("resolve", self.run_cli(home, "resource", "--help").stdout)
            self.assertIn("check", self.run_cli(home, "decision", "--help").stdout)

    def test_malformed_existing_registry_fails_closed_as_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            registry = home / "aios" / "vault" / "ops" / "projects" / "registry.jsonl"
            registry.parent.mkdir(parents=True, exist_ok=True)
            registry.write_text("{not-json}\n", encoding="utf-8")

            result = self.run_cli(home, "resource", "resolve", "anything", "--json")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stderr, "")
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt["verdict"], "BLOCKED")
            self.assertEqual(receipt["failure_class"], "INVALID_RESOURCE_SOURCE")

    def test_missing_routes_return_structured_fail_closed_receipts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aios-route-missing-") as raw_home:
            home = Path(raw_home)
            cases = [
                (("resource", "resolve", "missing", "--json"), "aios.resource-resolution.v1", "MISSING_RESOURCE"),
            ]
            for argv, schema, failure_class in cases:
                with self.subTest(argv=argv):
                    result = self.run_cli(home, *argv)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn("Traceback", result.stderr)
                    receipt = json.loads(result.stdout)
                    self.assertEqual(receipt["schema"], schema)
                    self.assertEqual(receipt["verdict"], "BLOCKED")
                    self.assertEqual(receipt["failure_class"], failure_class)
                    self.assertNotIn("provider", receipt)


if __name__ == "__main__":
    unittest.main()
