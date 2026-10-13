#!/usr/bin/env python3
"""Fake-only first-import contract at the real CLI/backend/consumer boundary."""
from __future__ import annotations

import fcntl
import importlib.util
import io
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "aios.py"
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("aios_stdin_cli", CLI)
assert SPEC and SPEC.loader
AIOS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AIOS)
# Explicit fake fixture, never a platform credential.
SENTINEL = "FAKE-STDIN-IMPORT-SENTINEL-DO-NOT-USE"


class SecretStdinIntakeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="aios-secret-import-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.root = self.home / "instance"
        self.registry = self.root / "vault" / "secrets"
        self.env = {"PATH": os.defpath, "HOME": str(self.home), "AIOS_ROOT": str(self.root),
                    "TMPDIR": str(self.home), "PYTHONDONTWRITEBYTECODE": "1"}
        self.request = {
            "schema_version": 1, "kind": "secret_intake", "request_id": "req_import",
            "secret_id": "fixture.import", "title": "Test-only import",
            "fields": [
                {"name": "api_key", "type": "password", "secret": True, "required": True},
                {"name": "environment", "type": "enum", "secret": False, "required": True,
                 "choices": ["test", "dev"], "default": "test"},
            ],
            "item": {"kind": "api_token", "metadata": {"agent_can_read_plaintext": False}},
            "consumers": [{"id": "fixture.consumer", "runtime": {"kind": "env", "env_map": {
                "FIXTURE_API_KEY": "api_key", "FIXTURE_ENV": "environment"}},
                "rotation": {"fields": ["api_key"]}}],
            "replicas": [],
        }
        self.pending = self.save_request()

    def save_request(self) -> Path:
        path = self.registry / "requests" / "pending" / f"{self.request['request_id']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.request), encoding="utf-8")
        return path

    def cli(self, *args: str, raw: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run([sys.executable, str(CLI), "--home", str(self.home), *args],
                              env=self.env, cwd=ROOT, input=raw, capture_output=True, timeout=15)

    def intake(self, raw: bytes | None = None, *args: str) -> subprocess.CompletedProcess[bytes]:
        if raw is None:
            raw = json.dumps({"api_key": SENTINEL}).encode()
        return self.cli("secret", "intake", "req_import", "--json-stdin", *args, raw=raw)

    def assert_clean(self, result: subprocess.CompletedProcess[bytes]) -> None:
        self.assertNotIn(SENTINEL.encode(), result.stdout + result.stderr)
        self.assertNotIn(b"Traceback", result.stderr)
        for path in self.registry.rglob("*"):
            if path.is_file() and path.parent.name != "values":
                self.assertNotIn(SENTINEL.encode(), path.read_bytes(), str(path.relative_to(self.registry)))

    def assert_unpublished(self) -> None:
        for category in ("items", "values", "receipts", "consumers", "replicas", "requests/done"):
            self.assertFalse(any((self.registry / category).glob("*.json")))
            self.assertFalse(any((self.registry / category).glob("*.yaml")))
        self.assertTrue(self.pending.exists())
        self.assertEqual((self.registry / "audit.jsonl").read_text() if (self.registry / "audit.jsonl").exists() else "", "")

    def test_real_stdin_backend_consumer_use_and_rotate(self) -> None:
        result = self.intake()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_clean(result)
        value_path = self.registry / "values" / "fixture.import.json"
        self.assertEqual(json.loads(value_path.read_text())["values"], {"api_key": SENTINEL, "environment": "test"})
        self.assertEqual(value_path.stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.pending.exists())
        receipt = json.loads((self.registry / "receipts" / "req_import.json").read_text())
        self.assertFalse(receipt["secret_values_exposed"])
        self.assertEqual(receipt["secret_fields"], ["api_key"])
        # Expected fake value stays in an explicit test file, not command argv.
        child = self.home / "fake_consumer.py"
        child.write_text("import os\nassert os.environ['FIXTURE_API_KEY'] == " + repr(SENTINEL) +
                         "\nassert os.environ['FIXTURE_ENV'] == 'test'\nprint('CONSUMER_USED_KEY')\n"
                         "print(os.environ['FIXTURE_API_KEY'])\n")
        result = self.cli("secret", "run", "--consumer", "fixture.consumer", "--", sys.executable, str(child))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"CONSUMER_USED_KEY", result.stdout)
        self.assertIn(b"***REDACTED***", result.stdout)
        self.assert_clean(result)
        for args in (("list", "--json"), ("show", "fixture.import", "--metadata"),
                     ("validate", "--json"), ("doctor", "--json"), ("verify", "fixture.import", "--offline")):
            result = self.cli("secret", *args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assert_clean(result)
        result = self.cli("secret", "rotate", "fixture.import", "--consumer", "fixture.consumer", "--json-stdin",
                          raw=json.dumps({"api_key": "FAKE-ROTATED-IMPORT"}).encode())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(b"FAKE-ROTATED-IMPORT", result.stdout + result.stderr)
        self.assertEqual(json.loads(value_path.read_text())["values"]["api_key"], "FAKE-ROTATED-IMPORT")

    def test_bad_inputs_are_redacted_retryable_and_unpublished(self) -> None:
        cases = [b"", SENTINEL.encode(), b'{"api_key": "' + SENTINEL.encode(), b"[]", b"null",
                 json.dumps({"api_key": SENTINEL, SENTINEL: SENTINEL}).encode(),
                 json.dumps({"api_key": SENTINEL, "environment": SENTINEL}).encode(),
                 b'{}', b'{"api_key": ""}', b'{"api_key": "  "}', b'{"api_key": 123}',
                 b'{"api_key": null}', b'{"api_key": {"nested": "' + SENTINEL.encode() + b'"}}',
                 b'{"api_key":"one","api_key":"' + SENTINEL.encode() + b'"}',
                 b'{"api_key":"\\u0000"}', b'{"api_key":"\\ud800"}', b'{"api_key": NaN}',
                 b'\xff' + SENTINEL.encode(), b'{"api_key":"' + b'x' * (128 * 1024) + SENTINEL.encode() + b'"}']
        for index, raw in enumerate(cases):
            with self.subTest(case=index):
                result = self.intake(raw)
                self.assertNotEqual(result.returncode, 0)
                self.assert_clean(result)
                self.assert_unpublished()
        self.assertEqual(self.intake().returncode, 0)

    def test_invalid_field_contracts_fail_before_import(self) -> None:
        base = json.loads(json.dumps(self.request))
        changes = [{"secret": None}, {"secret": "false"}, {"secret": False}, {"type": 7},
                   {"type": "unknown"}, {"name": 7}, {"name": "bad-name"}, {"required": "yes"},
                   {"default": "not-allowed"}, {"choices": "bad"}]
        for index, change in enumerate(changes):
            with self.subTest(case=index):
                self.request = json.loads(json.dumps(base))
                self.request["fields"][0].update(change)
                self.save_request()
                result = self.intake()
                self.assertNotEqual(result.returncode, 0)
                self.assert_clean(result)
                self.assert_unpublished()
        for default in (None, 7, "", "bad", "\x00"):
            with self.subTest(default=default):
                self.request = json.loads(json.dumps(base))
                self.request["fields"][1]["default"] = default
                self.save_request()
                result = self.intake()
                self.assertNotEqual(result.returncode, 0)
                self.assert_clean(result)
                self.assert_unpublished()

    def test_default_pipe_is_rejected_and_force_cannot_bypass_first_import(self) -> None:
        result = self.cli("secret", "intake", "req_import", raw=json.dumps({"api_key": SENTINEL}).encode())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"non-TTY", result.stderr)
        self.assert_clean(result)
        result = self.intake(None, "--force")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"--force is forbidden", result.stderr)
        self.assert_unpublished()
        self.assert_clean(result)

    def test_existing_item_or_backend_never_overwritten(self) -> None:
        for category, suffix in (("items", ".yaml"), ("values", ".json")):
            with self.subTest(category=category):
                path = self.registry / category / ("fixture.import" + suffix)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("EXISTING-DO-NOT-READ")
                before = path.read_bytes()
                result = self.intake()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b"already exists", result.stderr)
                self.assertEqual(path.read_bytes(), before)
                self.assertTrue(self.pending.exists())
                self.assertFalse((self.registry / "consumers" / "fixture.consumer.yaml").exists())
                self.assert_clean(result)
                path.unlink()  # Exact fake fixture path only.

    def test_late_conflicts_are_rechecked_before_any_publication(self) -> None:
        args = type("Args", (), {"home": str(self.home), "request_id": "req_import", "dry_run": False,
                                  "force": False, "json_stdin": True})()
        original = AIOS.read_secret_intake_stdin
        def late_conflict(fields, defaults):
            values = original(fields, defaults)
            path = self.registry / "consumers" / "fixture.consumer.yaml"
            path.write_text(json.dumps({"id": "fixture.consumer", "uses_secret": "fixture.other"}))
            return values
        stream = io.TextIOWrapper(io.BytesIO(json.dumps({"api_key": SENTINEL}).encode()))
        with patch.dict(os.environ, self.env, clear=True), patch.object(AIOS.sys, "stdin", stream), \
                patch.object(AIOS, "read_secret_intake_stdin", side_effect=late_conflict):
            with self.assertRaisesRegex(SystemExit, "existing consumer conflicts"):
                AIOS.secret_intake(args)
        self.assertFalse((self.registry / "items" / "fixture.import.yaml").exists())
        self.assertFalse((self.registry / "values" / "fixture.import.json").exists())
        self.assertFalse((self.registry / "receipts" / "req_import.json").exists())
        self.assertTrue(self.pending.exists())

    def test_batch_consumer_replica_and_completion_conflicts_publish_nothing(self) -> None:
        first = self.request["consumers"][0]
        self.request["consumers"].append({**first, "id": "fixture.second"})
        path = self.registry / "consumers" / "fixture.second.yaml"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"id": "fixture.second", "uses_secret": "fixture.other"}))
        self.save_request()
        result = self.intake()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.registry / "consumers" / "fixture.consumer.yaml").exists())
        self.assertFalse((self.registry / "values" / "fixture.import.json").exists())
        self.assert_clean(result)
        path.unlink()
        self.request["replicas"] = [{"id": "fixture.replica", "keys": {"EXAMPLE_KEY": "api_key"}}]
        path = self.registry / "replicas" / "fixture.replica.yaml"
        path.write_text(json.dumps({"id": "fixture.replica", "source_secret_ref": "fixture.other"}))
        self.save_request()
        result = self.intake()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"replica conflicts", result.stderr)
        self.assertFalse((self.registry / "consumers" / "fixture.consumer.yaml").exists())
        self.assert_clean(result)
        path.unlink()
        path = self.registry / "receipts" / "req_import.json"
        path.write_text("EXISTING-RECEIPT")
        result = self.intake()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(path.read_text(), "EXISTING-RECEIPT")
        self.assertFalse((self.registry / "consumers" / "fixture.consumer.yaml").exists())
        self.assert_clean(result)

    def test_busy_publication_lock_is_retryable(self) -> None:
        self.registry.mkdir(parents=True, exist_ok=True)
        with (self.registry / ".registration.lock").open("w") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.intake()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"busy", result.stderr)
            self.assert_clean(result)
            self.assert_unpublished()
        self.assertEqual(self.intake().returncode, 0)

    def test_concurrent_first_imports_have_one_winner_and_no_overwrite(self) -> None:
        processes = []
        for index in range(4):
            self.request["request_id"] = f"req_race_{index}"
            self.save_request()
            process = subprocess.Popen([sys.executable, str(CLI), "--home", str(self.home),
                                        "secret", "intake", self.request["request_id"], "--json-stdin"],
                                       env=self.env, cwd=ROOT, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            assert process.stdin
            process.stdin.write(json.dumps({"api_key": SENTINEL}).encode())
            process.stdin.close()
            process.stdin = None
            processes.append(process)
        try:
            results = []
            for process in processes:
                stdout, stderr = process.communicate(timeout=15)
                result = subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
                self.assert_clean(result)
                results.append(result)
            self.assertEqual(sum(result.returncode == 0 for result in results), 1)
            self.assertEqual(len(list((self.registry / "receipts").glob("*.json"))), 1)
            self.assertEqual(len(list((self.registry / "requests" / "pending").glob("req_race_*.json"))), 3)
            self.assertTrue(self.pending.exists())  # Unused setUp request stays untouched.
            self.assertEqual(json.loads((self.registry / "values" / "fixture.import.json").read_text())["values"]["api_key"], SENTINEL)
            events = (self.registry / "audit.jsonl").read_text().splitlines()
            self.assertEqual(len(events), 1)
            self.assertEqual(json.loads(events[0])["event"], "intake_completed")
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait()

    def test_audit_failure_does_not_claim_whole_transaction_atomicity(self) -> None:
        args = type("Args", (), {"home": str(self.home), "request_id": "req_import", "dry_run": False,
                                  "force": False, "json_stdin": True})()
        stream = io.TextIOWrapper(io.BytesIO(json.dumps({"api_key": SENTINEL}).encode()))
        with patch.dict(os.environ, self.env, clear=True), patch.object(AIOS.sys, "stdin", stream), \
                patch.object(AIOS, "append_secret_audit", side_effect=OSError("synthetic disk failure")):
            with self.assertRaisesRegex(OSError, "synthetic disk failure"):
                AIOS.secret_intake(args)
        self.assertFalse(self.pending.exists())
        self.assertTrue((self.registry / "requests" / "done" / "req_import.json").exists())
        self.assertTrue((self.registry / "receipts" / "req_import.json").exists())
        self.assertEqual((self.registry / "audit.jsonl").read_text(), "")
        self.assert_clean(subprocess.CompletedProcess([], 1, b"", b""))

    def test_dry_run_does_not_parse_or_publish_input(self) -> None:
        result = self.intake(SENTINEL.encode(), "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_clean(result)
        self.assert_unpublished()

    def test_real_tty_still_uses_hidden_prompt(self) -> None:
        # A real kernel PTY, not an isatty/getpass spoof. Send only after prompt.
        self.request["fields"] = self.request["fields"][:1]
        self.request["consumers"][0]["runtime"]["env_map"].pop("FIXTURE_ENV")
        self.save_request()
        master, slave = pty.openpty()
        try:
            process = subprocess.Popen([sys.executable, str(CLI), "--home", str(self.home),
                                        "secret", "intake", "req_import"], env=self.env, cwd=ROOT,
                                       stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
            output = b""
            deadline = time.monotonic() + 10
            while b"api_key: " not in output and time.monotonic() < deadline:
                if select.select([master], [], [], 0.2)[0]:
                    output += os.read(master, 4096)
            self.assertIn(b"api_key: ", output)
            os.write(master, SENTINEL.encode() + b"\n")
            while process.poll() is None and time.monotonic() < deadline:
                if select.select([master], [], [], 0.2)[0]:
                    output += os.read(master, 4096)
            self.assertEqual(process.wait(timeout=2), 0)
            while select.select([master], [], [], 0)[0]:
                output += os.read(master, 4096)
            self.assertNotIn(SENTINEL.encode(), output)
            self.assertIn(b"Secret intake completed", output)
        finally:
            if 'process' in locals() and process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            os.close(slave)


if __name__ == "__main__":
    unittest.main()
