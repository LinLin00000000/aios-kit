#!/usr/bin/env python3
"""Focused regression tests for Secret intake prompt defaults."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from unittest.mock import call, patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("aios_cli", ROOT / "scripts" / "aios.py")
assert SPEC and SPEC.loader
AIOS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AIOS)


class SecretIntakePromptTests(unittest.TestCase):
    def secret_field(self, **extra: object) -> dict[str, object]:
        return {"name": "api_key", "label": "API Key", "type": "password", "secret": True, "required": True, **extra}

    def test_default_translation_api_key_does_not_confirm(self) -> None:
        request = AIOS.default_translation_request()
        api_key_field = next(field for field in request["fields"] if field["name"] == "api_key")
        self.assertIs(api_key_field["confirm"], False)

    def test_non_boolean_confirmation_is_rejected(self) -> None:
        request = AIOS.default_translation_request()
        api_key_field = next(field for field in request["fields"] if field["name"] == "api_key")
        api_key_field["confirm"] = "yes"
        issues = AIOS.request_manifest_issues(request)
        self.assertTrue(any(issue["path"].endswith(".confirm") for issue in issues))

    def test_omitted_confirmation_prompts_once(self) -> None:
        with patch.object(AIOS.getpass, "getpass", return_value="copied-key") as prompt:
            self.assertEqual(AIOS.prompt_field(self.secret_field()), "copied-key")
        prompt.assert_called_once_with("API Key: ")

    def test_explicit_false_confirmation_prompts_once(self) -> None:
        with patch.object(AIOS.getpass, "getpass", return_value="copied-key") as prompt:
            self.assertEqual(AIOS.prompt_field(self.secret_field(confirm=False)), "copied-key")
        prompt.assert_called_once_with("API Key: ")

    def test_explicit_true_confirmation_prompts_twice(self) -> None:
        with patch.object(AIOS.getpass, "getpass", side_effect=["manual-secret", "manual-secret"]) as prompt:
            self.assertEqual(AIOS.prompt_field(self.secret_field(confirm=True)), "manual-secret")
        self.assertEqual(prompt.call_args_list, [call("API Key: "), call("Confirm API Key: ")])


if __name__ == "__main__":
    unittest.main()