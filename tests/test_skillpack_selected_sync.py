#!/usr/bin/env python3
"""Focused tests for selected-entry, CAS-preserving skillpack sync."""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("aios_cli_selected", ROOT / "scripts" / "aios.py")
assert SPEC and SPEC.loader
AIOS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AIOS)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SelectedSkillpackSyncTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[dict, Path, list[dict]]:
        source_root = root / "sources"
        for name in ("alpha", "beta"):
            skill = source_root / name
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(f"---\nname: {name}\n---\n# {name}\n", encoding="utf-8")
        manifest = {
            "name": "test-pack",
            "defaults": {"mode": "copy"},
            "first_party": [
                {"id": "alpha", "skill": "alpha", "path": "alpha", "enabled": True, "targets": "universal"},
                {"id": "beta", "skill": "beta", "path": "beta", "enabled": True, "targets": "universal"},
            ],
        }
        rows = [
            {"kind": "external", "id": "vendor", "skill": "vendor", "target": "universal", "mode": "copy", "opaque": [1, 2]},
            {"kind": "first_party", "id": "alpha", "skill": "alpha", "target": "universal", "mode": "copy", "installed_hash": "old-alpha", "extra": {"keep": True}},
            {"kind": "first_party", "id": "beta", "skill": "beta", "target": "universal", "mode": "copy", "installed_hash": "old-beta", "extra": {"byte": "stable"}},
        ]
        state_path = root / "state" / "install-state.json"
        state_path.parent.mkdir()
        state_path.write_text(json.dumps({"schema": "aios-kit.install-state.v1", "pack": "test-pack", "managed": rows, "updated_at": "old"}, indent=2) + "\n", encoding="utf-8")
        return manifest, state_path, rows

    def _args(self, home: Path, state_sha: str, *, apply: bool) -> argparse.Namespace:
        return argparse.Namespace(
            home=str(home), apply=apply, dry_run=not apply, prune=False,
            mode="symlink", force=False, target="universal", state_dir=None,
            first_party_only=True, only=["alpha"], expected_state_sha256=state_sha,
        )

    def test_parser_accepts_repeatable_only_and_expected_state_sha(self) -> None:
        args = AIOS.build_parser().parse_args([
            "skillpack", "dev-link", "--dry-run", "--only", "alpha",
            "--only", "beta", "--expected-state-sha256", "a" * 64,
        ])
        self.assertEqual(args.only, ["alpha", "beta"])
        self.assertEqual(args.expected_state_sha256, "a" * 64)

    def test_apply_changes_only_selected_row_and_preserves_other_rows(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aios-selected-test-") as td:
            root = Path(td)
            manifest, state_path, original_rows = self._fixture(root)
            runtime = root / "runtime"
            source_root = root / "sources"
            expected = sha256(state_path)
            os.chmod(state_path, 0o640)
            stdout = io.StringIO()
            with (
                mock.patch.object(AIOS, "load_skillpack", return_value=manifest),
                mock.patch.object(AIOS, "state_path", return_value=state_path),
                mock.patch.object(AIOS, "target_dirs", return_value={"universal": runtime}),
                mock.patch.object(AIOS, "resolve_repo_path", side_effect=lambda p, home=None: source_root / str(p)),
                contextlib.redirect_stdout(stdout),
            ):
                AIOS.skillpack_sync(self._args(root / "home", expected, apply=True))
            post = json.loads(state_path.read_text(encoding="utf-8"))
            by_skill = {row["skill"]: row for row in post["managed"]}
            self.assertEqual([row["skill"] for row in post["managed"]], ["vendor", "alpha", "beta"])
            self.assertEqual(by_skill["vendor"], original_rows[0])
            self.assertEqual(by_skill["beta"], original_rows[2])
            self.assertNotEqual(by_skill["alpha"], original_rows[1])
            self.assertEqual(by_skill["alpha"]["mode"], "symlink")
            self.assertEqual(state_path.stat().st_mode & 0o777, 0o640)
            self.assertTrue((runtime / "alpha").is_symlink())
            self.assertFalse((runtime / "beta").exists())
            delta_lines = [line for line in stdout.getvalue().splitlines() if line.startswith("STATE ROW DELTA ")]
            self.assertEqual(len(delta_lines), 1)
            delta = json.loads(delta_lines[0].removeprefix("STATE ROW DELTA "))
            self.assertEqual(delta["key"], {"target": "universal", "skill": "alpha"})
            self.assertEqual(delta["operation"], "update")

    def test_dry_run_renders_exact_row_delta_without_writes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aios-selected-test-") as td:
            root = Path(td)
            manifest, state_path, _ = self._fixture(root)
            runtime = root / "runtime"
            source_root = root / "sources"
            before = state_path.read_bytes()
            stdout = io.StringIO()
            with (
                mock.patch.object(AIOS, "load_skillpack", return_value=manifest),
                mock.patch.object(AIOS, "state_path", return_value=state_path),
                mock.patch.object(AIOS, "target_dirs", return_value={"universal": runtime}),
                mock.patch.object(AIOS, "resolve_repo_path", side_effect=lambda p, home=None: source_root / str(p)),
                contextlib.redirect_stdout(stdout),
            ):
                AIOS.skillpack_sync(self._args(root / "home", sha256(state_path), apply=False))
            self.assertEqual(state_path.read_bytes(), before)
            self.assertFalse(runtime.exists())
            self.assertIn(f"STATE PREIMAGE SHA256 {hashlib.sha256(before).hexdigest()}", stdout.getvalue())
            delta_line = next(line for line in stdout.getvalue().splitlines() if line.startswith("STATE ROW DELTA "))
            delta = json.loads(delta_line.removeprefix("STATE ROW DELTA "))
            self.assertEqual(delta["before"]["installed_hash"], "old-alpha")
            self.assertEqual(delta["after"]["installed_hash"], AIOS.hash_dir(source_root / "alpha"))

    def test_apply_rejects_stale_expected_state_before_projection(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aios-selected-test-") as td:
            root = Path(td)
            manifest, state_path, _ = self._fixture(root)
            runtime = root / "runtime"
            source_root = root / "sources"
            args = self._args(root / "home", "0" * 64, apply=True)
            with (
                mock.patch.object(AIOS, "load_skillpack", return_value=manifest),
                mock.patch.object(AIOS, "state_path", return_value=state_path),
                mock.patch.object(AIOS, "target_dirs", return_value={"universal": runtime}),
                mock.patch.object(AIOS, "resolve_repo_path", side_effect=lambda p, home=None: source_root / str(p)),
                self.assertRaisesRegex(SystemExit, "install-state CAS mismatch"),
            ):
                AIOS.skillpack_sync(args)
            self.assertFalse(runtime.exists())

    def test_scoped_prune_removes_one_state_only_dangling_symlink(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aios-selected-prune-test-") as td:
            root = Path(td)
            manifest, state_path, original_rows = self._fixture(root)
            manifest["first_party"] = [
                item for item in manifest["first_party"] if item["skill"] != "alpha"
            ]
            runtime = root / "runtime"
            runtime.mkdir()
            dangling = runtime / "alpha"
            dangling.symlink_to(root / "missing-alpha", target_is_directory=True)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["managed"][1]["installed_path"] = str(dangling)
            state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
            args = self._args(root / "home", sha256(state_path), apply=True)
            args.only = ["alpha"]
            args.prune = True
            stdout = io.StringIO()
            with (
                mock.patch.object(AIOS, "load_skillpack", return_value=manifest),
                mock.patch.object(AIOS, "state_path", return_value=state_path),
                mock.patch.object(AIOS, "target_dirs", return_value={"universal": runtime}),
                contextlib.redirect_stdout(stdout),
            ):
                AIOS.skillpack_sync(args)
            post = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual([row["skill"] for row in post["managed"]], ["vendor", "beta"])
            self.assertEqual(post["managed"][0], original_rows[0])
            self.assertEqual(post["managed"][1], original_rows[2])
            self.assertFalse(dangling.exists())
            self.assertFalse(dangling.is_symlink())
            delta_line = next(line for line in stdout.getvalue().splitlines() if line.startswith("STATE ROW DELTA "))
            delta = json.loads(delta_line.removeprefix("STATE ROW DELTA "))
            self.assertEqual(delta["operation"], "delete")

    def test_unknown_only_entry_fails_closed_before_projection(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aios-selected-test-") as td:
            root = Path(td)
            manifest, state_path, _ = self._fixture(root)
            runtime = root / "runtime"
            args = self._args(root / "home", sha256(state_path), apply=False)
            args.only = ["missing"]
            with (
                mock.patch.object(AIOS, "load_skillpack", return_value=manifest),
                mock.patch.object(AIOS, "state_path", return_value=state_path),
                mock.patch.object(AIOS, "target_dirs", return_value={"universal": runtime}),
                self.assertRaisesRegex(SystemExit, "unknown --only skill"),
            ):
                AIOS.skillpack_sync(args)
            self.assertFalse(runtime.exists())

    def test_selected_apply_requires_explicit_expected_state_sha(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aios-selected-test-") as td:
            root = Path(td)
            manifest, state_path, _ = self._fixture(root)
            runtime = root / "runtime"
            args = self._args(root / "home", sha256(state_path), apply=True)
            args.expected_state_sha256 = None
            with (
                mock.patch.object(AIOS, "load_skillpack", return_value=manifest),
                mock.patch.object(AIOS, "state_path", return_value=state_path),
                mock.patch.object(AIOS, "target_dirs", return_value={"universal": runtime}),
                self.assertRaisesRegex(SystemExit, "requires --expected-state-sha256"),
            ):
                AIOS.skillpack_sync(args)
            self.assertFalse(runtime.exists())


if __name__ == "__main__":
    unittest.main()
