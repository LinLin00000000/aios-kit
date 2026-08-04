#!/usr/bin/env python3
"""Regression tests for the three supported aios-kit CLI entrypoints."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CliEntrypointTests(unittest.TestCase):
    def test_module_entrypoint_loads_local_sibling_module(self) -> None:
        env = {
            "HOME": str(Path.home()),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            # Safe-path mode removes cwd; package-style invocation still
            # needs the project root as an explicit import location.
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(ROOT),
            "PYTHONSAFEPATH": "1",
        }
        result = subprocess.run(
            [sys.executable, "-m", "scripts.aios", "--help"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage:", result.stdout)

        direct = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "aios.py"), "--help"],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
        )
        self.assertEqual(direct.returncode, 0, direct.stderr)
        self.assertIn("usage:", direct.stdout)

    def test_shell_wrapper_works_in_safe_path_and_preserves_cli_errors(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            env = {
                "HOME": home,
                "LC_ALL": "C",
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": "",
                "PYTHONSAFEPATH": "1",
            }
            wrapper = str(ROOT / "aios")
            help_result = subprocess.run(
                [wrapper, "--help"],
                cwd=home,
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            self.assertIn("usage:", help_result.stdout)

            invalid = subprocess.run(
                [wrapper, "t080-invalid-command"],
                cwd=home,
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(invalid.returncode, 2, invalid.stderr)
            self.assertIn("error:", invalid.stderr)
            self.assertNotIn("Traceback", invalid.stderr)


if __name__ == "__main__":
    unittest.main()
