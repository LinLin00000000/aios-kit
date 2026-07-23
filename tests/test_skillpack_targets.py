#!/usr/bin/env python3
"""Focused regression tests for AIOS-to-skills-CLI target translation."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("aios_cli", ROOT / "scripts" / "aios.py")
assert SPEC and SPEC.loader
AIOS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AIOS)


class SkillpackTargetTests(unittest.TestCase):
    def test_hermes_uses_current_skills_cli_agent_id(self) -> None:
        self.assertEqual(AIOS.skills_cli_agent("hermes"), "hermes-agent")

    def test_other_targets_pass_through(self) -> None:
        self.assertEqual(AIOS.skills_cli_agent("universal"), "universal")


if __name__ == "__main__":
    unittest.main()
