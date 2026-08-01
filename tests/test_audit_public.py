#!/usr/bin/env python3
"""Focused regression tests for the public audit's assignment detector."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("audit_public", ROOT / "scripts" / "audit_public.py")
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class AuditPublicAssignmentTests(unittest.TestCase):
    def test_reference_expressions_are_not_secret_values(self) -> None:
        for line in (
            'token = applied["token"]',
            'token = make_runtime_identifier()',
            'api_key = next(field for field in fields if field["name"] == "api_key")',
            'password: ${PASSWORD}',
            'uses_secret: "ai-api.translation.default"',
            'source_secret_ref: "ai-api.translation.default"',
            '"TRANSLATE_API_KEY": credential_value,',
        ):
            with self.subTest(line=line):
                self.assertIsNone(AUDIT.token_assignment_value(line))

    def test_literal_secret_like_assignments_remain_detected(self) -> None:
        key = "".join(("to", "ken"))
        api_key_name = "".join(("api", "_key"))
        refresh_key = "_".join(("refresh", key))
        client_secret = "_".join(("client", "secret"))
        samples = (
            f'{key} = "literal-' + "value-1234567890" + '"',
            "password: 'correct-" + "horse-battery-staple'",
            f'{api_key_name} = "fixture-' + "value-1234567890" + '"',
            f"{key}: fixture-" + "value-1234567890",
            "".join(("pass", "word", ": ", "correct", "horse", "battery", "staple")),
            f"{refresh_key}=fixture-" + "value-1234567890",
            f'{client_secret}: "fixture-' + "value-1234567890" + '"',
            f'"{key}": "fixture-' + "value-1234567890" + '",',
            f'{key} = "' + "aaaaaaaa" + '"',
            f'{key}=' + "aaaaaaaa",
        )
        for line in samples:
            with self.subTest(line=line):
                self.assertIsNotNone(AUDIT.token_assignment_value(line))


if __name__ == "__main__":
    unittest.main()