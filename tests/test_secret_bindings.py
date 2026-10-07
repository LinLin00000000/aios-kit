#!/usr/bin/env python3
"""Fake-only CLI regressions for shared, allow-listed Secret consumers."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "aios.py"
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("aios_bindings_cli", CLI)
assert SPEC and SPEC.loader
AIOS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AIOS)


class SecretBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="aios-secret-bindings-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.root = self.home / "aios"
        self.registry = self.root / "vault" / "secrets"
        self.env = {"PATH": os.defpath, "HOME": str(self.home), "TMPDIR": str(self.home), "PYTHONDONTWRITEBYTECODE": "1"}
        for name in ("items", "consumers", "values", "requests/pending"):
            (self.registry / name).mkdir(parents=True)
        for site in ("a", "b"):
            self.write("items", f"fixture.{site}", {
                "id": f"fixture.{site}", "kind": "account_pat", "status": "configured", "consumers": [],
                "fields": {"pat": {"secret": True}, "account": {"secret": False}, "unused": {"secret": True}},
            })
            self.write("values", f"fixture.{site}", {
                "secret_id": f"fixture.{site}", "values": {"pat": f"FAKE-PAT-{site}", "account": site, "unused": f"FAKE-UNUSED-{site}"},
            })
        self.consumer = {
            "id": "fixture.shared", "kind": "consumer",
            "bindings": {"a": {"uses_secret": "fixture.a"}, "b": {"uses_secret": "fixture.b"}},
            "runtime": {"kind": "env", "env_map": {"SELECTED_PAT": "pat", "SELECTED_ACCOUNT": "account"}},
        }
        self.save_consumer()

    def write(self, category: str, name: str, data: dict) -> Path:
        path = self.registry / category / f"{name}{'.json' if category == 'values' else '.yaml'}"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def save_consumer(self) -> Path:
        return self.write("consumers", "fixture.shared", self.consumer)

    def cli(self, *args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(CLI), "--home", str(self.home), *args], cwd=ROOT, env=self.env,
                              input=input_text, text=True, capture_output=True)

    def run_binding(self, binding: str | None, script: str = "print('CHILD_STARTED')") -> subprocess.CompletedProcess[str]:
        args = ["secret", "run", "--consumer", "fixture.shared"]
        if binding is not None:
            args += ["--binding", binding]
        return self.cli(*args, "--", sys.executable, "-c", script)

    def assert_denied(self, result: subprocess.CompletedProcess[str], message: str) -> None:
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(message, result.stderr)
        self.assertNotIn("CHILD_STARTED", result.stdout)
        self.assertEqual((self.registry / "audit.jsonl").read_text() if (self.registry / "audit.jsonl").exists() else "", "")

    def test_each_binding_injects_only_selected_fields_and_audits_identity(self) -> None:
        for site in ("a", "b"):
            script = ("import os; "
                      f"assert os.environ['SELECTED_PAT'] == 'FAKE-PAT-{site}'; "
                      f"assert os.environ['SELECTED_ACCOUNT'] == '{site}'; "
                      "assert 'unused' not in os.environ; "
                      "assert not any(v.startswith('FAKE-UNUSED-') for v in os.environ.values()); "
                      f"assert 'FAKE-PAT-{'b' if site == 'a' else 'a'}' not in os.environ.values(); "
                      "print('SELECTED_ONLY')")
            result = self.run_binding(site, script)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "SELECTED_ONLY")
        events = [json.loads(line) for line in (self.registry / "audit.jsonl").read_text().splitlines()]
        self.assertEqual([(e["secret_id"], e["binding"]) for e in events], [("fixture.a", "a"), ("fixture.b", "b")])
        self.assertNotIn("FAKE-PAT", json.dumps(events))

    def test_multi_binding_requires_explicit_selection(self) -> None:
        self.assert_denied(self.run_binding(None), "--binding is required")

    def test_unknown_binding_is_not_sanitized_or_used_as_secret_id(self) -> None:
        for key in ("fixture.a", "../a", "a!", "", "missing"):
            with self.subTest(key=key):
                self.assert_denied(self.run_binding(key), "unknown consumer binding")

    def test_disabled_or_retired_binding_is_refused(self) -> None:
        for extra in ({"enabled": False}, {"status": "retired"}, {"status": "disabled"}):
            with self.subTest(extra=extra):
                self.consumer["bindings"]["a"] = {"uses_secret": "fixture.a", **extra}
                self.save_consumer()
                self.assert_denied(self.run_binding("a"), "not enabled")

    def test_item_retired_and_unknown_status_are_refused_before_value_read(self) -> None:
        (self.registry / "values" / "fixture.a.json").unlink()
        for status in ("retired", "disabled", "unknown"):
            with self.subTest(status=status):
                item = {"id": "fixture.a", "status": status, "fields": {"pat": {"secret": True}, "account": {"secret": False}}}
                self.write("items", "fixture.a", item)
                self.assert_denied(self.run_binding("a"), "not runnable")

    def test_fixed_missing_or_empty_status_remains_compatible(self) -> None:
        self.consumer.pop("bindings")
        self.consumer["uses_secret"] = "fixture.a"
        self.save_consumer()
        original = json.loads((self.registry / "items" / "fixture.a.yaml").read_text())
        for status in (..., None, ""):
            with self.subTest(status=status):
                item = dict(original)
                if status is ...:
                    item.pop("status")
                else:
                    item["status"] = status
                self.write("items", "fixture.a", item)
                result = self.run_binding(None)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_single_binding_can_default(self) -> None:
        self.consumer["bindings"].pop("b")
        self.save_consumer()
        self.assertEqual(self.run_binding(None).returncode, 0)
        event = json.loads((self.registry / "audit.jsonl").read_text().splitlines()[-1])
        self.assertEqual(event["binding"], "a")

    def test_multi_binding_still_requires_selection_when_other_binding_disabled(self) -> None:
        self.consumer["bindings"]["b"]["enabled"] = False
        self.save_consumer()
        self.assert_denied(self.run_binding(None), "--binding is required")

    def test_fixed_consumer_legacy_env_map_and_audit_remain_compatible(self) -> None:
        self.consumer.pop("bindings")
        self.consumer.pop("runtime")
        self.consumer.update({"uses_secret": "fixture.a", "env_map": {"SELECTED_PAT": "pat"}})
        self.save_consumer()
        self.assert_denied(self.run_binding("a"), "fixed consumer does not accept --binding")
        result = self.run_binding(None, "import os; assert os.environ['SELECTED_PAT'] == 'FAKE-PAT-a'; print('LEGACY_OK')")
        self.assertEqual(result.returncode, 0, result.stderr)
        event = json.loads((self.registry / "audit.jsonl").read_text().splitlines()[-1])
        self.assertEqual(event["secret_id"], "fixture.a")
        self.assertNotIn("binding", event)

    def test_invalid_binding_schema_and_dual_mode_fail_closed(self) -> None:
        cases = [
            {"uses_secret": "fixture.a"},
            {"bindings": {}},
            {"bindings": []},
            {"bindings": {"a": "fixture.a"}},
            {"bindings": {"a": {"uses_secret": ""}}},
            {"bindings": {"../a": {"uses_secret": "fixture.a"}}},
            {"bindings": {"a": {"uses_secret": "../fixture.a"}}},
            {"bindings": {"a": {"uses_secret": "fixture.a", "enabled": "false"}}},
            {"bindings": {"a": {"uses_secret": "fixture.a", "status": "typo"}}},
            {"bindings": {"a": {"uses_secret": "fixture.a", "env_map": {"ALL": "unused"}}}},
        ]
        for replacement in cases:
            with self.subTest(replacement=replacement):
                consumer = {**self.consumer, **replacement}
                self.write("consumers", "fixture.shared", consumer)
                result = self.run_binding("a")
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("CHILD_STARTED", result.stdout)
                self.assertEqual((self.registry / "audit.jsonl").read_text() if (self.registry / "audit.jsonl").exists() else "", "")
                validation = self.cli("secret", "validate", "--json")
                self.assertNotEqual(validation.returncode, 0)
                self.assertFalse(json.loads(validation.stdout)["ok"])

    def test_no_arbitrary_secret_option(self) -> None:
        result = self.cli("secret", "run", "--consumer", "fixture.shared", "--secret", "fixture.a", "--", sys.executable, "-c", "print('CHILD_STARTED')")
        self.assert_denied(result, "unrecognized arguments")

    def test_validate_doctor_and_list_resolve_binding_references_without_value_reads(self) -> None:
        for path in (self.registry / "values").glob("*.json"):
            path.write_text("NOT A VALUE DOCUMENT", encoding="utf-8")
        for command in ("validate", "doctor"):
            result = self.cli("secret", command, "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report["ok"])
            self.assertEqual(report["counts"]["binding_consumers"], 1)
            self.assertEqual(report["counts"]["consumer_bindings"], 2)
        result = self.cli("secret", "list", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        items = json.loads(result.stdout)["items"]
        for site, item in zip(("a", "b"), items):
            self.assertEqual(item["consumers"], ["fixture.shared"])
            self.assertEqual(item["consumer_bindings"][0]["binding"], site)

    def test_show_metadata_derives_binding_links_without_reading_backend(self) -> None:
        path = self.registry / "items" / "fixture.a.yaml"
        item = json.loads(path.read_text())
        item["fields"]["pat"]["value"] = "FAKE-PAT-METADATA"
        self.write("items", "fixture.a", item)
        (self.registry / "values" / "fixture.a.json").write_text("BROKEN BACKEND")
        result = self.cli("secret", "show", "fixture.a", "--metadata")
        self.assertEqual(result.returncode, 0, result.stderr)
        metadata = json.loads(result.stdout)
        self.assertEqual(metadata["consumers"], ["fixture.shared"])
        self.assertEqual(metadata["consumer_bindings"][0]["binding"], "a")
        self.assertNotIn("FAKE-PAT-METADATA", result.stdout)

    def test_validator_checks_all_binding_items_and_shared_env_map_fields(self) -> None:
        for field in ("missing", "unused"):
            self.consumer["runtime"]["env_map"]["SELECTED_PAT"] = field
            self.save_consumer()
            if field == "unused":
                path = self.registry / "items" / "fixture.b.yaml"
                item = json.loads(path.read_text())
                item["fields"].pop("unused")
                self.write("items", "fixture.b", item)
            result = self.cli("secret", "validate", "--json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("field not defined on item", result.stdout)
        self.consumer["bindings"]["b"]["uses_secret"] = "fixture.absent"
        self.save_consumer()
        result = self.cli("secret", "doctor", "--json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing secret item", result.stdout)

    def test_runtime_checks_metadata_fields_before_loading_values(self) -> None:
        self.consumer["runtime"]["env_map"]["SELECTED_PAT"] = "backend_only"
        self.save_consumer()
        (self.registry / "values" / "fixture.a.json").unlink()
        self.assert_denied(self.run_binding("a"), "field not defined on item")

    def test_redacts_selected_secrets_and_preserves_child_exit(self) -> None:
        result = self.run_binding("a", "import sys; print('FAKE-PAT-a'); print('FAKE-UNUSED-a', file=sys.stderr); sys.exit(7)")
        self.assertEqual(result.returncode, 7)
        self.assertNotIn("FAKE-PAT-a", result.stdout)
        self.assertNotIn("FAKE-UNUSED-a", result.stderr)
        self.assertIn("REDACTED", result.stdout)
        event = json.loads((self.registry / "audit.jsonl").read_text().splitlines()[-1])
        self.assertEqual(event["exit_code"], 7)

    def test_binding_rotate_is_explicitly_unsupported_and_does_not_write(self) -> None:
        self.consumer["rotation"] = {"fields": ["pat"]}
        self.save_consumer()
        path = self.registry / "values" / "fixture.a.json"
        before = path.read_bytes()
        result = self.cli("secret", "rotate", "fixture.a", "--consumer", "fixture.shared", "--field", "pat", input_text="FAKE-NEW-PAT")
        self.assert_denied(result, "binding consumers do not support rotation")
        self.assertEqual(path.read_bytes(), before)
        result = self.cli("secret", "validate", "--json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("binding consumers do not support rotation", result.stdout)

    def request(self, consumer: dict) -> dict:
        return {"request_id": "req_fixture", "kind": "secret_intake", "secret_id": "fixture.a",
                "fields": [{"name": "pat", "type": "password", "secret": True, "generate": True},
                           {"name": "account", "type": "string", "secret": False, "default": "a"}],
                "consumers": [consumer], "replicas": []}

    def test_request_cannot_create_binding_consumers(self) -> None:
        manifest = self.home / "request.json"
        manifest.write_text(json.dumps(self.request(self.consumer)))
        result = self.cli("secret", "request", "create", "--manifest", str(manifest), "--dry-run", "--json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requests cannot register binding consumers", result.stdout)

    def test_request_cannot_overwrite_shared_or_changed_fixed_consumers(self) -> None:
        incoming = {"id": "fixture.shared", "uses_secret": "fixture.a", "runtime": self.consumer["runtime"]}
        for existing in (self.consumer, {**incoming, "uses_secret": "fixture.b"},
                         {**incoming, "runtime": {"kind": "env", "env_map": {"ALL": "unused"}}},
                         {**incoming, "metadata": {"preserve": True}}):
            with self.subTest(existing=existing):
                consumer_path = self.write("consumers", "fixture.shared", existing)
                before = consumer_path.read_bytes()
                request = self.request(incoming)
                self.write("requests/pending", "req_fixture", request)
                value_path = self.registry / "values" / "fixture.a.json"
                value_before = value_path.read_bytes()
                result = self.cli("secret", "generate", "req_fixture", "--force", "--json")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("existing consumer conflicts", result.stderr)
                self.assertEqual(consumer_path.read_bytes(), before)
                self.assertEqual(value_path.read_bytes(), value_before)
                self.assertFalse((self.registry / "receipts" / "req_fixture.json").exists())
                self.assertTrue((self.registry / "requests/pending" / "req_fixture.yaml").exists())
                manifest = self.home / "request.json"
                manifest.write_text(json.dumps(request))
                result = self.cli("secret", "request", "create", "--manifest", str(manifest), "--dry-run", "--json")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("existing consumer conflicts", result.stdout)

    def test_intake_conflict_is_checked_before_any_prompt(self) -> None:
        incoming = {"id": "fixture.shared", "uses_secret": "fixture.a", "runtime": self.consumer["runtime"]}
        self.write("requests/pending", "req_fixture", self.request(incoming))
        args = type("Args", (), {"home": str(self.home), "request_id": "req_fixture", "dry_run": False, "force": True})()
        with patch.dict(os.environ, self.env, clear=True), patch.object(AIOS, "prompt_field") as prompt:
            with self.assertRaisesRegex(SystemExit, "existing consumer conflicts"):
                AIOS.secret_intake(args)
            prompt.assert_not_called()

    def test_request_reuses_consistent_fixed_consumer_without_rewriting(self) -> None:
        incoming = {"id": "fixture.shared", "uses_secret": "fixture.a", "env_map": {"SELECTED_PAT": "pat"}}
        existing = {**incoming, "schema_version": 1, "kind": "consumer", "updated_at": "historical-timestamp"}
        path = self.write("consumers", "fixture.shared", existing)
        before = path.read_bytes()
        self.write("requests/pending", "req_fixture", self.request(incoming))
        result = self.cli("secret", "generate", "req_fixture", "--force", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(path.read_bytes(), before)

    def test_unselected_value_backend_is_never_loaded(self) -> None:
        (self.registry / "values" / "fixture.b.json").write_text("BROKEN UNSELECTED BACKEND")
        result = self.run_binding("a")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_fixed_consumer_also_refuses_retired_item(self) -> None:
        self.consumer.pop("bindings")
        self.consumer["uses_secret"] = "fixture.a"
        self.save_consumer()
        path = self.registry / "items" / "fixture.a.yaml"
        item = json.loads(path.read_text())
        item["status"] = "retired"
        self.write("items", "fixture.a", item)
        (self.registry / "values" / "fixture.a.json").unlink()
        self.assert_denied(self.run_binding(None), "not runnable")

    def test_direct_pending_binding_request_is_rejected_without_values_or_consumer_changes(self) -> None:
        request = self.request(self.consumer)
        self.write("requests/pending", "req_fixture", request)
        consumer_path = self.registry / "consumers" / "fixture.shared.yaml"
        value_path = self.registry / "values" / "fixture.a.json"
        consumer_before, value_before = consumer_path.read_bytes(), value_path.read_bytes()
        result = self.cli("secret", "generate", "req_fixture", "--force", "--json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requests cannot register binding consumers", result.stderr)
        self.assertEqual(consumer_path.read_bytes(), consumer_before)
        self.assertEqual(value_path.read_bytes(), value_before)

    def test_all_consumers_preflight_before_any_consumer_is_written(self) -> None:
        new = {"id": "fixture.new", "uses_secret": "fixture.a", "env_map": {"SELECTED_PAT": "pat"}}
        conflict = {**new, "id": "fixture.shared"}
        request = self.request(new)
        request["consumers"].append(conflict)
        self.write("requests/pending", "req_fixture", request)
        result = self.cli("secret", "generate", "req_fixture", "--force", "--json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("existing consumer conflicts", result.stderr)
        self.assertFalse((self.registry / "consumers" / "fixture.new.yaml").exists())
        request["consumers"] = [new, new]
        self.write("requests/pending", "req_fixture", request)
        result = self.cli("secret", "generate", "req_fixture", "--force", "--json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate consumer registration", result.stderr)
        self.assertFalse((self.registry / "consumers" / "fixture.new.yaml").exists())

    def test_new_fixed_request_registers_default_source_and_can_run(self) -> None:
        incoming = {"id": "fixture.new", "runtime": {"env_map": {"SELECTED_PAT": "pat"}}}
        self.write("requests/pending", "req_fixture", self.request(incoming))
        result = self.cli("secret", "generate", "req_fixture", "--force", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        doc = AIOS.load_yaml_doc(self.registry / "consumers" / "fixture.new.yaml")
        self.assertEqual(doc["uses_secret"], "fixture.a")
        self.assertEqual(doc["runtime"]["kind"], "env")
        self.assertEqual(doc["runtime"]["env_map"], doc["env_map"])
        result = self.cli("secret", "run", "--consumer", "fixture.new", "--", sys.executable, "-c",
                          "import os; assert len(os.environ['SELECTED_PAT']) == 64; print('REGISTERED_OK')")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "REGISTERED_OK")

    def test_missing_source_in_existing_consumer_is_not_synthesized_for_reuse(self) -> None:
        incoming = {"id": "fixture.shared", "uses_secret": "fixture.a", "env_map": {"SELECTED_PAT": "pat"}}
        existing = {"id": "fixture.shared", "env_map": {"SELECTED_PAT": "pat"}}
        self.write("consumers", "fixture.shared", existing)
        self.write("requests/pending", "req_fixture", self.request(incoming))
        result = self.cli("secret", "generate", "req_fixture", "--force", "--json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("existing consumer conflicts", result.stderr)

    def test_exclusive_consumer_create_never_overwrites_competing_registration(self) -> None:
        incoming = {"id": "fixture.race", "uses_secret": "fixture.a", "env_map": {"SELECTED_PAT": "pat"}}
        competing = {**incoming, "uses_secret": "fixture.b"}
        target = self.registry / "consumers" / "fixture.race.yaml"
        original_open = AIOS.os.open

        def racing_open(path, flags, mode=0o777, **kwargs):
            if Path(path) == target:
                target.write_text(json.dumps(competing))
            return original_open(path, flags, mode, **kwargs)

        with patch.dict(os.environ, self.env, clear=True), patch.object(AIOS.os, "open", side_effect=racing_open):
            with self.assertRaisesRegex(SystemExit, "existing consumer conflicts"):
                AIOS.write_consumer_from_request(self.home, "fixture.a", incoming)
        self.assertEqual(json.loads(target.read_text()), competing)

    def test_pending_registration_conflicts_are_checked_but_done_history_is_not(self) -> None:
        incoming = {"id": "fixture.shared", "uses_secret": "fixture.a", "env_map": {"SELECTED_PAT": "pat"}}
        request = self.request(incoming)
        pending = self.write("requests/pending", "req_fixture", request)
        result = self.cli("secret", "doctor", "--json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("existing consumer conflicts", result.stdout)
        done = self.registry / "requests" / "done" / pending.name
        done.parent.mkdir(exist_ok=True)
        pending.rename(done)
        result = self.cli("secret", "validate", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])

    def test_equivalent_runtime_kind_defaults_are_normalized_for_reuse(self) -> None:
        incoming = {"id": "fixture.shared", "uses_secret": "fixture.a", "runtime": {"kind": "env", "env_map": {"SELECTED_PAT": "pat"}}}
        existing = {**incoming, "runtime": {"env_map": {"SELECTED_PAT": "pat"}}}
        path = self.write("consumers", "fixture.shared", existing)
        before = path.read_bytes()
        self.write("requests/pending", "req_fixture", self.request(incoming))
        result = self.cli("secret", "generate", "req_fixture", "--force", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(path.read_bytes(), before)

    def test_shared_missing_or_empty_status_is_refused_before_value_read(self) -> None:
        original = json.loads((self.registry / "items" / "fixture.a.yaml").read_text())
        (self.registry / "values" / "fixture.a.json").unlink()
        for single in (False, True):
            if single:
                self.consumer["bindings"].pop("b")
                self.save_consumer()
            for status in (..., None, ""):
                with self.subTest(single=single, status=status):
                    item = dict(original)
                    if status is ...:
                        item.pop("status")
                    else:
                        item["status"] = status
                    self.write("items", "fixture.a", item)
                    self.assert_denied(self.run_binding(None if single else "a"), "not runnable")

    def test_malformed_fields_container_is_refused_before_value_read(self) -> None:
        (self.registry / "values" / "fixture.a.json").write_text("BROKEN FAKE BACKEND")
        for fields in (None, [], "bad-fields"):
            with self.subTest(fields=fields):
                self.write("items", "fixture.a", {"id": "fixture.a", "status": "configured", "fields": fields})
                self.assert_denied(self.run_binding("a"), "item fields must be an object")
                result = self.cli("secret", "validate", "--json")
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(json.loads(result.stdout)["ok"])

    def test_invalid_field_metadata_or_classification_is_refused_before_backend_read(self) -> None:
        original = json.loads((self.registry / "items" / "fixture.a.yaml").read_text())
        (self.registry / "values" / "fixture.a.json").write_text("BROKEN FAKE BACKEND")
        cases = [(None, "must be an object"), ([], "must be an object"), ("bad", "must be an object"),
                 ({}, "explicit boolean"), ({"type": "password"}, "explicit boolean"),
                 ({"secret": "true"}, "explicit boolean"), ({"secret": 1}, "explicit boolean"),
                 ({"secret": False, "type": "password"}, "classification disagree"),
                 ({"secret": False, "type": "secret"}, "classification disagree"),
                 ({"secret": False, "type": "token"}, "classification disagree"),
                 ({"secret": True, "value": "FAKE-METADATA-VALUE"}, "must not store plaintext")]
        for meta, message in cases:
            with self.subTest(meta=meta):
                item = {**original, "fields": {**original["fields"], "pat": meta}}
                self.write("items", "fixture.a", item)
                result = self.run_binding("a")
                self.assert_denied(result, message)
                self.assertNotIn("FAKE-METADATA-VALUE", result.stdout + result.stderr)
                result = self.cli("secret", "validate", "--json")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stdout)
                self.assertNotIn("FAKE-METADATA-VALUE", result.stdout)

    def snapshot(self) -> dict:
        paths = [self.root, *self.root.rglob("*")]
        return {str(path.relative_to(self.home)): (path.is_dir(), path.stat().st_mode & 0o777,
                                                   None if path.is_dir() else path.read_bytes()) for path in paths}

    def test_native_validate_is_read_only_after_one_consumer_publication(self) -> None:
        for path in (self.registry, self.registry / "items", self.registry / "consumers"):
            path.chmod(0o750)
        before = self.snapshot()
        incoming = {"id": "fixture.published", "uses_secret": "fixture.a", "env_map": {"SELECTED_PAT": "pat"}}
        with patch.dict(os.environ, self.env, clear=True):
            AIOS.write_consumer_from_request(self.home, "fixture.a", incoming)
        after_publish = self.snapshot()
        new_path = str((self.registry / "consumers" / "fixture.published.yaml").relative_to(self.home))
        self.assertEqual(set(after_publish) - set(before), {new_path})
        self.assertEqual({p: after_publish[p] for p in before}, before)
        self.assertEqual(after_publish[new_path][1], 0o600)
        result = self.cli("secret", "validate", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])
        self.assertEqual(self.snapshot(), after_publish)

    def test_validate_missing_root_does_not_create_layout(self) -> None:
        missing_home = self.home / "never-created"
        missing_root = missing_home / "aios"
        result = subprocess.run([sys.executable, str(CLI), "--home", str(missing_home), "secret", "validate", "--json"],
                                cwd=ROOT, env=self.env, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(json.loads(result.stdout)["ok"])
        self.assertFalse(missing_root.exists())

    def test_consumer_json_serialization_failure_never_creates_file(self) -> None:
        incoming = {"id": "fixture.serialize", "uses_secret": "fixture.a", "env_map": {"SELECTED_PAT": "pat"}}
        target = self.registry / "consumers" / "fixture.serialize.yaml"
        original_dumps = AIOS.json.dumps

        def failed_serialization(data, **kwargs):
            if kwargs.get("indent") == 2:
                raise ValueError("fake serialization failure")
            return original_dumps(data, **kwargs)

        with patch.dict(os.environ, self.env, clear=True), patch.object(AIOS.json, "dumps", side_effect=failed_serialization):
            with self.assertRaisesRegex(ValueError, "fake serialization failure"):
                AIOS.write_consumer_from_request(self.home, "fixture.a", incoming)
        self.assertFalse(target.exists())

    def consumer_write_failure(self, *, replace: bool) -> tuple[Path, dict]:
        incoming = {"id": "fixture.write-fail", "uses_secret": "fixture.a", "env_map": {"SELECTED_PAT": "pat"}}
        target = self.registry / "consumers" / "fixture.write-fail.yaml"
        competing = {**incoming, "uses_secret": "fixture.b"}
        original_fdopen = AIOS.os.fdopen

        def broken_fdopen(fd, *args, **kwargs):
            handle = original_fdopen(fd, *args, **kwargs)

            class BrokenWriter:
                def __enter__(self):
                    return self

                def write(self, text):
                    handle.write(text[:1])
                    handle.flush()
                    if replace:
                        target.unlink()
                        target.write_text(json.dumps(competing))
                    raise OSError("fake consumer write failure")

                def __exit__(self, *args):
                    handle.close()

            return BrokenWriter()

        with patch.dict(os.environ, self.env, clear=True), patch.object(AIOS.os, "fdopen", side_effect=broken_fdopen):
            with self.assertRaisesRegex(OSError, "fake consumer write failure"):
                AIOS.write_consumer_from_request(self.home, "fixture.a", incoming)
        return target, competing

    def test_consumer_write_error_removes_only_its_own_partial_file(self) -> None:
        target, _ = self.consumer_write_failure(replace=False)
        self.assertFalse(target.exists())

    def test_consumer_write_error_preserves_replaced_inode(self) -> None:
        target, competing = self.consumer_write_failure(replace=True)
        self.assertEqual(json.loads(target.read_text()), competing)

    def test_late_second_consumer_conflict_preserves_values_and_pending_but_may_leave_first(self) -> None:
        first = {"id": "fixture.first", "uses_secret": "fixture.a", "env_map": {"SELECTED_PAT": "pat"}}
        second = {**first, "id": "fixture.second"}
        request = self.request(first)
        request["consumers"].append(second)
        pending = self.write("requests/pending", "req_fixture", request)
        target = self.registry / "consumers" / "fixture.second.yaml"
        competing = {**second, "uses_secret": "fixture.b"}
        value_path = self.registry / "values" / "fixture.a.json"
        value_before = value_path.read_bytes()
        original_open = AIOS.os.open

        def racing_open(path, flags, mode=0o777, **kwargs):
            if Path(path) == target:
                target.write_text(json.dumps(competing))
            return original_open(path, flags, mode, **kwargs)

        args = type("Args", (), {"home": str(self.home), "request_id": "req_fixture", "dry_run": False,
                                  "force": True, "json": True})()
        with patch.dict(os.environ, self.env, clear=True), patch.object(AIOS.os, "open", side_effect=racing_open):
            with self.assertRaisesRegex(SystemExit, "existing consumer conflicts"):
                AIOS.secret_generate(args)
        self.assertTrue((self.registry / "consumers" / "fixture.first.yaml").exists())
        self.assertEqual(json.loads(target.read_text()), competing)
        self.assertEqual(value_path.read_bytes(), value_before)
        self.assertTrue(pending.exists())
        self.assertFalse((self.registry / "receipts" / "req_fixture.json").exists())

    def test_show_conservatively_redacts_ambiguous_and_malformed_field_metadata(self) -> None:
        cases = [{"type": "password", "value": "FAKE-QUERY-CANARY"},
                 {"value": "FAKE-QUERY-CANARY"},
                 {"secret": "false", "value": "FAKE-QUERY-CANARY"},
                 {"secret": 0, "value": "FAKE-QUERY-CANARY"},
                 {"secret": False, "type": "TOKEN", "value": "FAKE-QUERY-CANARY"},
                 {"secret": False, "type": ["FAKE-QUERY-CANARY"], "value": "FAKE-QUERY-CANARY"},
                 "FAKE-QUERY-CANARY", ["FAKE-QUERY-CANARY"], None]
        for field in cases:
            with self.subTest(field=field):
                self.write("items", "fixture.a", {"id": "fixture.a", "fields": {"pat": field,
                           "account": {"type": "string", "secret": False, "value": "PUBLIC-ACCOUNT"}}})
                result = self.cli("secret", "show", "fixture.a", "--metadata")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("FAKE-QUERY-CANARY", result.stdout + result.stderr)
                self.assertEqual(json.loads(result.stdout)["fields"]["account"]["value"], "PUBLIC-ACCOUNT")
        for fields in ("FAKE-QUERY-CANARY", ["FAKE-QUERY-CANARY"], None):
            with self.subTest(fields=fields):
                self.write("items", "fixture.a", {"id": "fixture.a", "fields": fields})
                result = self.cli("secret", "show", "fixture.a", "--metadata")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("FAKE-QUERY-CANARY", result.stdout + result.stderr)

    def test_bad_consumers_are_isolated_and_queries_report_incomplete_references(self) -> None:
        for name, content in (("broken", "bindings: [FAKE-PARSE-CANARY"),
                              ("scalar", '"FAKE-PARSE-CANARY"'),
                              ("empty", json.dumps({"id": "empty", "bindings": {}})),
                              ("bad-key", json.dumps({"id": "bad-key", "bindings": {"FAKE-PARSE-CANARY!": {"uses_secret": "fixture.a"}}}))):
            (self.registry / "consumers" / f"{name}.yaml").write_text(content)
        before = self.snapshot()
        for command in (("list", "--json"), ("show", "fixture.a", "--metadata")):
            result = self.cli("secret", *command)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("FAKE-PARSE-CANARY", result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertFalse(report["consumer_references_complete"])
            self.assertEqual(len(report["consumer_reference_problems"]), 4)
            items = report["items"] if "items" in report else [report]
            for item in items:
                self.assertEqual(item["consumers"], ["fixture.shared"])
                self.assertFalse(item["consumer_references_complete"])
        self.assertEqual(self.snapshot(), before)
        validation = self.cli("secret", "validate", "--json")
        self.assertNotEqual(validation.returncode, 0)
        self.assertFalse(json.loads(validation.stdout)["ok"])
        self.assertNotIn("FAKE-PARSE-CANARY", validation.stdout + validation.stderr)
        self.consumer["bindings"] = {}
        self.save_consumer()
        self.assert_denied(self.run_binding(None), "non-empty object")

    def test_list_show_and_validate_are_read_only_without_chmod(self) -> None:
        for path in (self.root, self.registry, self.registry / "items", self.registry / "consumers"):
            path.chmod(0o750)
        before = self.snapshot()
        for command in (("list", "--json"), ("list",), ("show", "fixture.a", "--metadata"), ("validate", "--json")):
            result = self.cli("secret", *command)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.snapshot(), before)

    def test_empty_instance_queries_do_not_initialize_layout(self) -> None:
        missing_home = self.home / "empty-home"
        missing_home.mkdir()
        for command in (("list", "--json"), ("list",), ("show", "fixture.absent", "--metadata"), ("validate", "--json")):
            result = subprocess.run([sys.executable, str(CLI), "--home", str(missing_home), "secret", *command],
                                    cwd=ROOT, env=self.env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0 if command[0] == "list" else 1)
            if command == ("list", "--json"):
                report = json.loads(result.stdout)
                self.assertEqual(report["items"], [])
                self.assertTrue(report["consumer_references_complete"])
            elif command[0] == "validate":
                report = json.loads(result.stdout)
                self.assertFalse(report["ok"])
                self.assertTrue(any(problem["message"] == "missing secret root" and
                                    problem["path"] == str(missing_home / "aios/vault/secrets")
                                    for problem in report["problems"]))
            self.assertEqual(list(missing_home.iterdir()), [])

    def test_current_consumers_derive_only_from_source_and_legacy_declarations_are_separate(self) -> None:
        path = self.registry / "items" / "fixture.a.yaml"
        item = json.loads(path.read_text())
        item["consumers"] = ["fixture.old", "fixture.shared"]
        self.write("items", "fixture.a", item)
        before = path.read_bytes()
        for command in (("list", "--json"), ("show", "fixture.a", "--metadata")):
            result = self.cli("secret", *command)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            view = report["items"][0] if "items" in report else report
            self.assertEqual(view["consumers"], ["fixture.shared"])
            self.assertEqual(view["declared_consumers"], ["fixture.old", "fixture.shared"])
            self.assertEqual(path.read_bytes(), before)

    def test_alternate_metadata_formats_work_for_list_show_validate_and_run(self) -> None:
        for suffix in (".yml", ".json"):
            with self.subTest(suffix=suffix):
                for category, name in (("items", "fixture.a"), ("consumers", "fixture.shared")):
                    source = next((self.registry / category).glob(f"{name}.*"))
                    target = source.with_suffix(suffix)
                    source.rename(target)
                for command in (("list", "--json"), ("show", "fixture.a", "--metadata"), ("validate", "--json")):
                    result = self.cli("secret", *command)
                    self.assertEqual(result.returncode, 0, result.stderr)
                result = self.run_binding("a")
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_duplicate_item_files_are_rejected_before_value_read_or_overwrite(self) -> None:
        original = self.registry / "items" / "fixture.a.yaml"
        duplicate = original.with_suffix(".json")
        duplicate.write_bytes(original.read_bytes())
        before = {p: p.read_bytes() for p in (original, duplicate, self.registry / "values" / "fixture.a.json")}
        for command in (("list", "--json"), ("show", "fixture.a", "--metadata"), ("validate", "--json")):
            result = self.cli("secret", *command)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("multiple metadata files", result.stdout + result.stderr)
        self.assert_denied(self.run_binding("a"), "multiple metadata files")
        self.write("requests/pending", "req_fixture", self.request({"id": "fixture.new", "env_map": {"PAT": "pat"}}))
        result = self.cli("secret", "generate", "req_fixture", "--force", "--json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("multiple metadata files", result.stderr)
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        self.assertFalse((self.registry / "consumers" / "fixture.new.yaml").exists())

    def test_duplicate_consumer_files_are_excluded_from_query_and_fail_closed(self) -> None:
        path = self.registry / "consumers" / "fixture.shared.yaml"
        path.with_suffix(".yml").write_bytes(path.read_bytes())
        for command in (("list", "--json"), ("show", "fixture.a", "--metadata")):
            result = self.cli("secret", *command)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertFalse(report["consumer_references_complete"])
            self.assertIn("multiple metadata files", json.dumps(report["consumer_reference_problems"]))
            view = report["items"][0] if "items" in report else report
            self.assertEqual(view["consumers"], [])
        self.assert_denied(self.run_binding("a"), "multiple metadata files")
        validation = self.cli("secret", "validate", "--json")
        self.assertNotEqual(validation.returncode, 0)
        self.assertIn("multiple metadata files", validation.stdout)

    def test_alternate_consumer_registration_conflicts_and_reuse_never_create_yaml_mirror(self) -> None:
        incoming = {"id": "fixture.shared", "uses_secret": "fixture.a", "env_map": {"SELECTED_PAT": "pat"}}
        original = self.registry / "consumers" / "fixture.shared.yaml"
        alternate = original.with_suffix(".json")
        original.rename(alternate)
        before = alternate.read_bytes()
        self.write("requests/pending", "req_fixture", self.request(incoming))
        result = self.cli("secret", "generate", "req_fixture", "--force", "--json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("existing consumer conflicts", result.stderr)
        self.assertEqual(alternate.read_bytes(), before)
        self.assertFalse(original.exists())
        alternate.write_text(json.dumps({**incoming, "schema_version": 1, "kind": "consumer"}))
        before = alternate.read_bytes()
        result = self.cli("secret", "generate", "req_fixture", "--force", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(alternate.read_bytes(), before)
        self.assertFalse(original.exists())

    def test_duplicate_consumer_registration_is_rejected_during_dry_run_and_write(self) -> None:
        incoming = {"id": "fixture.shared", "uses_secret": "fixture.a", "env_map": {"SELECTED_PAT": "pat"}}
        path = self.write("consumers", "fixture.shared", incoming)
        path.with_suffix(".yml").write_bytes(path.read_bytes())
        request = self.request(incoming)
        manifest = self.home / "request.json"
        manifest.write_text(json.dumps(request))
        result = self.cli("secret", "request", "create", "--manifest", str(manifest), "--dry-run", "--json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("multiple metadata files", result.stdout)
        self.write("requests/pending", "req_fixture", request)
        result = self.cli("secret", "generate", "req_fixture", "--force", "--json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("multiple metadata files", result.stderr)

    def test_force_replaces_existing_alternate_item_without_creating_yaml_mirror(self) -> None:
        original = self.registry / "items" / "fixture.a.yaml"
        alternate = original.with_suffix(".yml")
        original.rename(alternate)
        self.write("requests/pending", "req_fixture", self.request({"id": "fixture.new", "env_map": {"PAT": "pat"}}))
        result = self.cli("secret", "generate", "req_fixture", "--force", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(original.exists())
        self.assertEqual(AIOS.load_yaml_doc(alternate)["id"], "fixture.a")

    def test_malformed_selected_consumer_parse_error_is_safe_and_fail_closed(self) -> None:
        self.save_consumer().write_text("bindings: [FAKE-SELECTED-PARSE-CANARY")
        result = self.run_binding("a")
        self.assert_denied(result, "could not parse metadata object")
        self.assertNotIn("FAKE-SELECTED-PARSE-CANARY", result.stdout + result.stderr)

    def test_metadata_id_must_match_filename_for_query_validate_and_run(self) -> None:
        item = {"id": "fixture.a", "status": "configured", "fields": {"pat": {"secret": True}}}
        self.write("items", "fixture.alias", item)
        result = self.cli("secret", "show", "fixture.alias", "--metadata")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("id must match canonical filename", result.stderr)
        result = self.cli("secret", "validate", "--json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("id does not match canonical filename", result.stdout)
        self.consumer["id"] = "fixture.other"
        self.save_consumer()
        self.assert_denied(self.run_binding("a"), "id must match canonical filename")
        result = self.cli("secret", "list", "--json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("id must match canonical filename", result.stderr)

    def request_contract_cases(self) -> list[tuple[str, dict, str]]:
        cases = []
        for key, values in (("secret_id", ["fixture item", "fixture/item", "fixture.", "!!!", "", None, 123, False, ["fixture"], {"id": "fixture"}]),
                            ("consumer_id", ["fixture consumer", "fixture/consumer", "fixture.", "!!!", "", None, 123, False, ["fixture"], {"id": "fixture"}]),
                            ("uses_secret", [None, "", 123, True, [], {}, " fixture.contract", "fixture/contract", "fixture.other"]),
                            ("type", [None, ["FAKE-TYPE-CANARY"], {"type": "FAKE-TYPE-CANARY"}, 123, False])):
            for value in values:
                consumer = {"id": f"fixture.contract.consumer.{len(cases)}", "env_map": {"PAT": "pat"}}
                request = self.request(consumer)
                request.update({"request_id": f"req_contract_{len(cases)}", "secret_id": f"fixture.contract.{len(cases)}"})
                if key == "secret_id":
                    request["secret_id"] = value
                    issue_path = "secret_id"
                elif key == "consumer_id":
                    consumer["id"] = value
                    issue_path = "consumers[0].id"
                elif key == "uses_secret":
                    # Numeric/boolean sources previously passed through str equality.
                    if isinstance(value, (int, bool)):
                        request["secret_id"] = str(value)
                    consumer["uses_secret"] = value
                    issue_path = "consumers[0].uses_secret"
                else:
                    request["fields"][0]["type"] = value
                    issue_path = "fields[0].type"
                cases.append((f"{key}={value!r}", request, issue_path))
        return cases

    def request_outputs_snapshot(self) -> dict[str, bytes]:
        # Layout init may create directories/audit or chmod them. Assert only the
        # owned data/publication surface, not a nonexistent absolute no-I/O promise.
        return {str(path.relative_to(self.registry)): path.read_bytes()
                for category in ("items", "consumers", "values", "receipts", "requests/done")
                for path in (self.registry / category).glob("*") if path.is_file()}

    def test_request_contract_create_dry_run_rejects_raw_invalid_ids_sources_and_types(self) -> None:
        for label, request, issue_path in self.request_contract_cases():
            with self.subTest(case=label):
                manifest = self.home / "contract-request.json"
                manifest.write_text(json.dumps(request))
                before = self.request_outputs_snapshot()
                result = self.cli("secret", "request", "create", "--manifest", str(manifest), "--dry-run", "--json")
                self.assertNotEqual(result.returncode, 0)
                report = json.loads(result.stdout)
                self.assertFalse(report["ok"])
                self.assertTrue(any(issue["path"] == issue_path for issue in report["issues"]), report)
                self.assertNotIn("FAKE-TYPE-CANARY", result.stdout + result.stderr)
                self.assertEqual(self.request_outputs_snapshot(), before)
                self.assertFalse((self.registry / "requests/pending" / f"{request['request_id']}.yaml").exists())

    def test_request_contract_direct_pending_generate_rejects_before_publication(self) -> None:
        for label, request, issue_path in self.request_contract_cases():
            with self.subTest(case=label):
                pending = self.write("requests/pending", request["request_id"], request)
                pending_before = pending.read_bytes()
                before = self.request_outputs_snapshot()
                result = self.cli("secret", "generate", request["request_id"], "--force", "--json")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("invalid secret request manifest", result.stderr)
                self.assertIn(issue_path, result.stderr)
                self.assertNotIn("FAKE-TYPE-CANARY", result.stdout + result.stderr)
                self.assertEqual(self.request_outputs_snapshot(), before)
                self.assertTrue(pending.exists())
                self.assertEqual(pending.read_bytes(), pending_before)

    def test_request_contract_intake_rejects_before_any_prompt_or_publication(self) -> None:
        for label, request, issue_path in self.request_contract_cases():
            with self.subTest(case=label):
                pending = self.write("requests/pending", request["request_id"], request)
                pending_before = pending.read_bytes()
                before = self.request_outputs_snapshot()
                args = type("Args", (), {"home": str(self.home), "request_id": request["request_id"],
                                          "dry_run": False, "force": True})()
                with patch.dict(os.environ, self.env, clear=True), \
                        patch.object(AIOS, "prompt_field", return_value="FAKE-INTAKE-CONTRACT") as prompt, \
                        patch.object(AIOS.sys.stdin, "isatty", return_value=True), \
                        patch.object(AIOS.sys.stdout, "isatty", return_value=True):
                    with self.assertRaisesRegex(SystemExit, "invalid secret request manifest") as error:
                        AIOS.secret_intake(args)
                    self.assertIn(issue_path, str(error.exception))
                    self.assertNotIn("FAKE-TYPE-CANARY", str(error.exception))
                    prompt.assert_not_called()
                self.assertEqual(self.request_outputs_snapshot(), before)
                self.assertTrue(pending.exists())
                self.assertEqual(pending.read_bytes(), pending_before)

    def test_request_contract_valid_canonical_and_omitted_source_remain_readable_and_runnable(self) -> None:
        for explicit in (False, True):
            with self.subTest(explicit_source=explicit):
                secret_id = f"fixture.contract.control.{int(explicit)}"
                consumer = {"id": f"{secret_id}.consumer", "env_map": {"PAT": "pat"}}
                if explicit:
                    consumer["uses_secret"] = secret_id
                request = self.request(consumer)
                request.update({"request_id": f"req_contract_control_{int(explicit)}", "secret_id": secret_id})
                manifest = self.home / "valid-contract-request.json"
                manifest.write_text(json.dumps(request))
                result = self.cli("secret", "request", "create", "--manifest", str(manifest), "--dry-run", "--json")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(json.loads(result.stdout)["ok"])
                pending = self.write("requests/pending", request["request_id"], request)
                result = self.cli("secret", "generate", request["request_id"], "--json")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(pending.exists())
                self.assertTrue((self.registry / "receipts" / f"{request['request_id']}.json").exists())
                doc = AIOS.load_secret_metadata(self.registry / "consumers" / f"{consumer['id']}.yaml")
                self.assertEqual(doc["uses_secret"], secret_id)
                self.assertIsInstance(doc["uses_secret"], str)
                result = self.cli("secret", "show", secret_id, "--metadata")
                self.assertEqual(result.returncode, 0, result.stderr)
                result = self.cli("secret", "validate", "--json")
                self.assertEqual(result.returncode, 0, result.stderr)
                result = self.cli("secret", "run", "--consumer", consumer["id"], "--", sys.executable, "-c",
                                  "import os; assert len(os.environ['PAT']) == 64; print('VALID_CONTRACT')")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "VALID_CONTRACT")


if __name__ == "__main__":
    unittest.main()
