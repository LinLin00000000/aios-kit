#!/usr/bin/env python3
"""Focused tests for allow-listed, atomic Secret Registry field rotation."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "aios.py"


class SecretRotationTests(unittest.TestCase):
    def run_cli(self, home: Path, *args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), "--home", str(home), *args],
            cwd=ROOT,
            input=input_text,
            text=True,
            capture_output=True,
        )

    def seed(self, home: Path) -> None:
        secrets = home / "aios" / "vault" / "secrets"
        (secrets / "items").mkdir(parents=True, exist_ok=True)
        (secrets / "consumers").mkdir(parents=True, exist_ok=True)
        (secrets / "values").mkdir(parents=True, exist_ok=True)
        (secrets / "items" / "fixture.feishu.yaml").write_text(
            """schema_version: 1
id: fixture.feishu
kind: feishu_user_oauth
fields:
  app_id:
    type: text
    secret: false
  app_secret:
    type: password
    secret: true
  refresh_token:
    type: password
    secret: true
  user_access_token:
    type: password
    secret: true
  root_folder_token:
    type: password
    secret: true
""",
            encoding="utf-8",
        )
        (secrets / "consumers" / "fixture.feishu.refresh.yaml").write_text(
            """schema_version: 1
id: fixture.feishu.refresh
uses_secret: fixture.feishu
runtime:
  kind: env
  env_map:
    FEISHU_APP_ID: app_id
    FEISHU_APP_SECRET: app_secret
    FEISHU_REFRESH_TOKEN: refresh_token
rotation:
  fields:
    - refresh_token
    - user_access_token
""",
            encoding="utf-8",
        )
        (secrets / "values" / "fixture.feishu.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "schema": "aios.secret.values.v1",
                    "secret_id": "fixture.feishu",
                    "values": {
                        "app_id": "cli_fixture",
                        "app_secret": "fake-app-secret",
                        "refresh_token": "old-refresh",
                        "user_access_token": "old-access",
                        "root_folder_token": "root-folder",
                    },
                }
            ),
            encoding="utf-8",
        )

    def read_values(self, home: Path) -> dict[str, str]:
        path = home / "aios" / "vault" / "secrets" / "values" / "fixture.feishu.json"
        return json.loads(path.read_text(encoding="utf-8"))["values"]

    def test_single_field_rotation_is_redacted_and_persisted(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aios-secret-rotate-") as raw_home:
            home = Path(raw_home)
            self.seed(home)
            result = self.run_cli(
                home,
                "secret",
                "rotate",
                "fixture.feishu",
                "--consumer",
                "fixture.feishu.refresh",
                "--field",
                "refresh_token",
                input_text="new-refresh\n",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("secret_values_exposed: false", result.stdout)
            self.assertNotIn("new-refresh", result.stdout)
            values = self.read_values(home)
            self.assertEqual(values["refresh_token"], "new-refresh")
            self.assertEqual(values["user_access_token"], "old-access")

    def test_json_rotation_updates_only_allowlisted_fields(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aios-secret-rotate-") as raw_home:
            home = Path(raw_home)
            self.seed(home)
            result = self.run_cli(
                home,
                "secret",
                "rotate",
                "fixture.feishu",
                "--consumer",
                "fixture.feishu.refresh",
                "--json-stdin",
                input_text=json.dumps({"refresh_token": "new-refresh", "user_access_token": "new-access"}),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            values = self.read_values(home)
            self.assertEqual(values["refresh_token"], "new-refresh")
            self.assertEqual(values["user_access_token"], "new-access")
            self.assertEqual(values["root_folder_token"], "root-folder")

    def test_unallowlisted_field_fails_closed_without_write(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aios-secret-rotate-") as raw_home:
            home = Path(raw_home)
            self.seed(home)
            result = self.run_cli(
                home,
                "secret",
                "rotate",
                "fixture.feishu",
                "--consumer",
                "fixture.feishu.refresh",
                "--field",
                "root_folder_token",
                input_text="must-not-write\n",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not allow-listed", result.stderr)
            self.assertEqual(self.read_values(home)["root_folder_token"], "root-folder")


if __name__ == "__main__":
    unittest.main()
