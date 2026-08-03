from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "aios.py"
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("aios_doctor_cli", CLI)
assert SPEC and SPEC.loader
AIOS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AIOS)


def tree_fingerprint(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class DoctorJsonCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="aios-doctor-test-")
        self.home = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_cli(self, *args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        for key in (
            "AIOS_ROOT",
            "AIOS_HOME",
            "AIOS_AGENT_SKILLS_DIR",
            "AIOS_SKILLS_DIR",
            "HERMES_HOME",
            "PYTHONPYCACHEPREFIX",
        ):
            env.pop(key, None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.update(extra_env or {})
        return subprocess.run(
            [sys.executable, str(CLI), "--home", str(self.home), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            env=env,
        )

    def test_json_contract_is_versioned_compact_read_only_and_exit_aligned(self) -> None:
        before = tree_fingerprint(self.home)
        first = self.run_cli("doctor", "--json")
        second = self.run_cli("doctor", "--json")
        after = tree_fingerprint(self.home)

        self.assertIn(first.returncode, (0, 1), first.stderr)
        self.assertEqual(first.returncode, second.returncode)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(first.stderr, "")
        self.assertEqual(first.stdout.count("\n"), 1)
        self.assertNotIn("\n", first.stdout[:-1])
        self.assertEqual(before, after, "doctor must not create or mutate instance files")

        payload = json.loads(first.stdout)
        self.assertEqual(set(payload), {"checks", "ok", "problems", "schema", "version"})
        self.assertEqual(payload["schema"], "aios.doctor.v1")
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["ok"], first.returncode == 0)
        self.assertEqual([check["id"] for check in payload["checks"]], ["instance", "skillpack", "assets"])
        for check in payload["checks"]:
            self.assertEqual(set(check), {"id", "messages", "ok"})
            self.assertIsInstance(check["ok"], bool)
            self.assertIsInstance(check["messages"], list)
            self.assertTrue(all(isinstance(message, str) for message in check["messages"]))
        assets_messages = next(check["messages"] for check in payload["checks"] if check["id"] == "assets")
        isolated_asset = str(self.home / "projects" / "lins-living-loop")
        self.assertTrue(any(isolated_asset in message for message in assets_messages))
        self.assertEqual(bool(payload["problems"]), not payload["ok"])
        for problem in payload["problems"]:
            self.assertEqual(set(problem), {"check", "code", "message"})
            self.assertEqual(problem["code"], "doctor_failed")
            self.assertIn(problem["check"], {"instance", "skillpack", "assets"})

    def test_healthy_isolated_instance_returns_zero_with_no_problems(self) -> None:
        required = (
            self.home / "aios" / "config",
            self.home / "aios" / "vault" / "ops" / "projects",
            self.home / "aios" / "work",
            self.home / "aios" / "skills",
            self.home / ".agents" / "skills",
            self.home / "aios" / "modules" / "lins-living-loop",
            self.home / "aios" / "state",
            self.home / "aios" / "logs",
            self.home / "aios" / "cache",
        )
        for path in required:
            path.mkdir(parents=True, exist_ok=True)
        (self.home / "aios" / "modules" / "lins-living-loop" / "SKILL.md").write_text(
            "---\nname: lins-living-loop\n---\n", encoding="utf-8"
        )
        fake_bin = self.home / "bin"
        fake_bin.mkdir()
        for command in ("node", "npx"):
            executable = fake_bin / command
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
        before = tree_fingerprint(self.home)

        cp = self.run_cli(
            "doctor",
            "--json",
            extra_env={"PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", "")},
        )

        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertEqual(cp.stderr, "")
        payload = json.loads(cp.stdout)
        self.assertIs(payload["ok"], True)
        self.assertEqual(payload["problems"], [])
        self.assertTrue(all(check["ok"] for check in payload["checks"]))
        self.assertEqual(before, tree_fingerprint(self.home))

    def test_default_human_output_keeps_existing_sections_and_exit_behavior(self) -> None:
        first = self.run_cli("doctor")
        second = self.run_cli("doctor")

        self.assertEqual(first.returncode, second.returncode)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(first.stderr, "")
        self.assertEqual(
            [line for line in first.stdout.splitlines() if line.startswith("==")],
            ["== instance ==", "== skillpack ==", "== assets =="],
        )
        self.assertFalse(first.stdout.lstrip().startswith("{"))


class DoctorRedactionTests(unittest.TestCase):
    def test_central_redaction_removes_url_credentials_assignments_and_provider_keys(self) -> None:
        sensitive = "".join(("credential", "-value"))
        provider_value = "".join(("sk", "-", "A" * 24))
        query_name = "_".join(("access", "token"))
        assignment_name = "".join(("pass", "word"))
        raw = "\n".join(
            (
                f"origin: https://oauth2:{sensitive}@example.invalid/repo.git?{query_name}={sensitive}",
                f"{assignment_name}={sensitive}",
                f"provider: {provider_value}",
            )
        )

        redacted = AIOS.redact_output(raw, [])

        self.assertNotIn(sensitive, redacted)
        self.assertNotIn(provider_value, redacted)
        self.assertNotIn("oauth2:", redacted)
        self.assertIn("https://example.invalid/repo.git?***REDACTED***", redacted)
        self.assertGreaterEqual(redacted.count("***REDACTED***"), 3)

    def test_assets_human_doctor_redacts_configured_and_observed_git_output(self) -> None:
        sensitive = "".join(("fixture", "-credential"))
        provider_value = "".join(("sk", "-", "B" * 24))
        query_name = "_".join(("refresh", "token"))
        configured = f"https://oauth2:{sensitive}@example.invalid/repo.git?{query_name}={sensitive}"
        observed = f"https://user:{sensitive}@example.invalid/other.git?{query_name}={sensitive}"

        with tempfile.TemporaryDirectory(prefix="aios-doctor-assets-") as raw:
            asset_path = Path(raw)
            runs = [
                subprocess.CompletedProcess([], 0, stdout=observed + "\n", stderr=""),
                subprocess.CompletedProcess([], 0, stdout=f"## branch-{provider_value}\n", stderr=""),
            ]
            output = io.StringIO()
            with (
                patch.object(AIOS, "assets_manifest_path", return_value=ROOT / "manifests" / "local-assets.json"),
                patch.object(
                    AIOS,
                    "load_assets",
                    return_value={
                        "assets": [
                            {
                                "id": "fixture",
                                "kind": "repository",
                                "canonical_path": str(asset_path),
                                "remote": configured,
                            }
                        ]
                    },
                ),
                patch.object(AIOS.subprocess, "run", side_effect=runs),
                contextlib.redirect_stdout(output),
            ):
                with self.assertRaises(SystemExit) as stopped:
                    AIOS.assets_doctor(argparse.Namespace())

        self.assertEqual(stopped.exception.code, 0)
        rendered = output.getvalue()
        self.assertNotIn(sensitive, rendered)
        self.assertNotIn(provider_value, rendered)
        self.assertNotIn("oauth2:", rendered)
        self.assertIn("https://example.invalid/other.git?***REDACTED***", rendered)
        self.assertIn("https://example.invalid/repo.git?***REDACTED***", rendered)


if __name__ == "__main__":
    unittest.main()
