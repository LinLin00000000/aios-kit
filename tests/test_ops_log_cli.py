#!/usr/bin/env python3
"""Regression tests for native append-only OPS maintenance logging."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "aios.py"
REQUIRED = {"schema_version", "ts", "date", "actor", "type", "scope", "summary", "status"}


class OpsLogCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="aios-ops-log-test-")
        self.home = Path(self.tmp.name)
        self.ops = self.home / "aios" / "vault" / "ops"
        self.ops.mkdir(parents=True)
        self.log = self.ops / "maintenance-log.jsonl"
        self.log.write_text("", encoding="utf-8")
        self.log.chmod(0o600)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_cli(self, *args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(CLI), "--home", str(self.home), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        return result

    def append_args(self, scope: str, summary: str) -> tuple[str, ...]:
        return (
            "ops", "log", "append",
            "--actor", "test-agent",
            "--type", "maintenance",
            "--scope", scope,
            "--summary", summary,
            "--status", "done",
            "--object", "/tmp/example",
            "--change", "appended one event",
            "--verification", "readback passed",
            "--impact", "none",
            "--followup", "none",
            "--artifact", "/tmp/evidence",
            "--tag", "test",
            "--json",
        )

    def test_help_is_discoverable(self) -> None:
        for argv in (("ops", "--help"), ("ops", "log", "--help"), ("ops", "log", "append", "--help")):
            result = self.run_cli(*argv)
            self.assertIn("usage:", result.stdout)
        self.assertIn("append", self.run_cli("ops", "log", "--help").stdout)

    def test_append_writes_one_valid_line_and_returns_readback_receipt(self) -> None:
        result = self.run_cli(*self.append_args("demo", "one event"))
        receipt = json.loads(result.stdout)
        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["schema"], "aios.ops-log-append.v1")
        self.assertTrue(receipt["prefix_preserved"])
        self.assertTrue(receipt["readback_verified"])

        raw = self.log.read_bytes()
        self.assertTrue(raw.endswith(b"\n"))
        self.assertEqual(raw.count(b"\n"), 1)
        entry = json.loads(raw)
        self.assertTrue(REQUIRED <= entry.keys())
        self.assertEqual(entry["scope"], "demo")
        self.assertEqual(entry["objects"], ["/tmp/example"])
        self.assertEqual(entry["tags"], ["test"])

    def test_existing_prefix_is_byte_identical_after_append(self) -> None:
        first = json.dumps({
            "schema_version": 1,
            "ts": "2026-08-20T00:00:00+00:00",
            "date": "2026-08-20",
            "actor": "fixture",
            "type": "maintenance",
            "scope": "fixture",
            "summary": "prefix",
            "status": "done",
        }, separators=(",", ":")).encode() + b"\n"
        self.log.write_bytes(first)
        self.run_cli(*self.append_args("second", "second event"))
        after = self.log.read_bytes()
        self.assertEqual(after[: len(first)], first)
        self.assertEqual(after.count(b"\n"), 2)

    def test_invalid_existing_jsonl_fails_without_mutation(self) -> None:
        before = b"{broken-json}\n"
        self.log.write_bytes(before)
        result = self.run_cli(*self.append_args("blocked", "must not append"), ok=False)
        self.assertIn("invalid existing maintenance log", result.stderr)
        self.assertEqual(self.log.read_bytes(), before)

    def test_missing_terminal_newline_fails_without_mutation(self) -> None:
        before = json.dumps({"schema_version": 1}).encode()
        self.log.write_bytes(before)
        result = self.run_cli(*self.append_args("blocked", "must not append"), ok=False)
        self.assertIn("terminal newline", result.stderr)
        self.assertEqual(self.log.read_bytes(), before)

    def test_non_private_mode_fails_without_mutation(self) -> None:
        before = self.log.read_bytes()
        self.log.chmod(0o640)
        result = self.run_cli(*self.append_args("blocked", "mode guard"), ok=False)
        self.assertIn("mode must be 0600", result.stderr)
        self.assertEqual(self.log.read_bytes(), before)

    def test_symlink_log_is_rejected(self) -> None:
        target = self.ops / "target.jsonl"
        target.write_text("", encoding="utf-8")
        self.log.unlink()
        self.log.symlink_to(target)
        result = self.run_cli(*self.append_args("blocked", "symlink"), ok=False)
        self.assertIn("regular non-symlink", result.stderr)
        self.assertEqual(target.read_bytes(), b"")

    def test_concurrent_cli_writers_produce_complete_parseable_lines(self) -> None:
        processes = [
            subprocess.Popen(
                [sys.executable, str(CLI), "--home", str(self.home), *self.append_args(f"scope-{index}", f"event-{index}")],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for index in range(12)
        ]
        for process in processes:
            stdout, stderr = process.communicate(timeout=30)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertTrue(json.loads(stdout)["readback_verified"])
        lines = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 12)
        entries = [json.loads(line) for line in lines]
        self.assertEqual({entry["scope"] for entry in entries}, {f"scope-{index}" for index in range(12)})


if __name__ == "__main__":
    unittest.main()
