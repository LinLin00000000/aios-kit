#!/usr/bin/env python3
"""Focused end-to-end tests for the minimal Matter materials CLI."""
from __future__ import annotations

import concurrent.futures
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "aios.py"
MAX_BYTES = 16 * 1024 * 1024


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def tree_fingerprint(root: Path) -> tuple[tuple[Any, ...], ...]:
    """Capture bytes and mtimes without following symlinks."""
    if not root.exists() and not root.is_symlink():
        return ()
    rows: list[tuple[Any, ...]] = []
    paths = [root, *sorted(root.rglob("*"), key=lambda item: item.as_posix())]
    for path in paths:
        st = path.lstat()
        rel = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            rows.append((rel, "symlink", st.st_mode, st.st_size, st.st_mtime_ns, os.readlink(path)))
        elif path.is_file():
            data = path.read_bytes()
            rows.append((rel, "file", st.st_mode, st.st_size, st.st_mtime_ns, sha256_bytes(data)))
        elif path.is_dir():
            rows.append((rel, "dir", st.st_mode, st.st_size, st.st_mtime_ns))
        else:
            rows.append((rel, "other", st.st_mode, st.st_size, st.st_mtime_ns))
    return tuple(rows)


class MatterMaterialsCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="aios-matter-materials-test-")
        self.home = Path(self.tmp.name)
        self.aios = self.home / "aios"
        self.work = self.aios / "work"
        self.work.mkdir(parents=True)

        self.source_root = self.home / "registered-source"
        self.source = self.source_root / "docs" / "report.md"
        self.source.parent.mkdir(parents=True)
        self.source_bytes = b"# Fixture report\n\nEvidence alpha.\n"
        self.source.write_bytes(self.source_bytes)

        self.data_root = self.aios / "data"
        self.managed = self.data_root / "managed"
        self.managed.mkdir(parents=True)

        self.fixture_source = self.source_record(
            "fixture-source", self.source_root, sensitivity="internal", kind="worksite_root"
        )
        self.managed_source = self.source_record(
            "aios-managed-zone",
            self.data_root,
            sensitivity="mixed",
            kind="managed_zone",
            access_mode="curate_reversible",
            backup_status="planned",
        )
        self.write_registry(self.fixture_source, self.managed_source)
        self.active_worksite = self.create_matter("matter_active", state="active", attention="paused")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def source_record(
        self,
        source_id: str,
        root: Path,
        *,
        sensitivity: str,
        kind: str = "data_root",
        access_mode: str = "read_only_reference",
        backup_status: str = "unknown",
        locations: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": source_id,
            "name": source_id,
            "kind": kind,
            "aliases": [],
            "status": "active",
            "locations": locations if locations is not None else [{"kind": "local", "path": str(root)}],
            "authority": "source_registry",
            "owner_ref": f"source:{source_id}",
            "access_mode": access_mode,
            "sync_mode": "none",
            "backup_status": backup_status,
            "sensitivity": sensitivity,
            "include": [],
            "exclude": [],
            "notes": "",
        }

    def write_registry(self, *records: dict[str, Any]) -> None:
        registry = self.aios / "vault" / "ops" / "sources" / "registry.jsonl"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(
            "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records),
            encoding="utf-8",
        )

    def set_fixture_source(self, record: dict[str, Any]) -> None:
        self.fixture_source = record
        self.write_registry(self.fixture_source, self.managed_source)

    def create_matter(
        self,
        matter_id: str,
        *,
        state: str,
        attention: str = "current",
        formal: bool = True,
    ) -> Path:
        worksite = self.work / f"20260806-000000_{matter_id}"
        (worksite / "internal").mkdir(parents=True)
        (worksite / "mission.md").write_text(
            f"# {matter_id}\n\nstatus: {state}\n",
            encoding="utf-8",
        )
        if formal:
            (worksite / "internal" / "matter.json").write_text(
                json.dumps(
                    {
                        "schema": "aios.workflow.state.v0",
                        "id": matter_id,
                        "title": matter_id,
                        "status": state,
                        "lifecycle": {
                            "state": state,
                            "attention": attention,
                            "reopenable": state in {"active", "paused"},
                        },
                        "active_run": None,
                        "pending_interaction": None,
                        "current_wave": None,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        return worksite

    def invoke_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(self.home),
                "AIOS_ROOT": str(self.aios),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        env.pop("AIOS_HOME", None)
        return subprocess.run(
            [sys.executable, str(CLI), "--home", str(self.home), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            env=env,
        )

    def run_cli(self, *args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
        result = self.invoke_cli(*args)
        if ok and result.returncode != 0:
            self.fail(f"command failed: {args}\nstdout={result.stdout}\nstderr={result.stderr}")
        if not ok and result.returncode == 0:
            self.fail(f"command unexpectedly passed: {args}\nstdout={result.stdout}\nstderr={result.stderr}")
        return result

    def attach(
        self,
        *,
        matter_id: str = "matter_active",
        locator: str = "docs/report.md",
        role: str = "reference",
        custody: str = "reference_only",
        sensitivity: str = "internal",
        dry_run: bool = False,
        ok: bool = True,
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
        args = [
            "matter",
            "material",
            "attach",
            matter_id,
            "--source",
            "fixture-source",
            "--owner-ref",
            "worksite:fixture",
            "--locator",
            locator,
            "--role",
            role,
            "--custody",
            custody,
            "--sensitivity",
            sensitivity,
        ]
        if dry_run:
            args.append("--dry-run")
        args.append("--json")
        result = self.run_cli(*args, ok=ok)
        return result, json.loads(result.stdout)

    def materials_root(self, matter_id: str = "matter_active") -> Path:
        return self.managed / "matter-materials" / matter_id

    def manifest(self, matter_id: str = "matter_active") -> dict[str, Any]:
        return json.loads((self.materials_root(matter_id) / "materials.json").read_text(encoding="utf-8"))

    def assert_verify_read_only(
        self,
        *args: str,
        ok: bool,
    ) -> dict[str, Any]:
        before = tree_fingerprint(self.materials_root())
        result = self.run_cli("matter", "material", "verify", "matter_active", *args, "--json", ok=ok)
        after = tree_fingerprint(self.materials_root())
        self.assertEqual(after, before, "verify must not change material bytes or mtimes")
        return json.loads(result.stdout)

    def test_cli_requires_explicit_custody_and_sensitivity(self) -> None:
        common = [
            "matter",
            "material",
            "attach",
            "matter_active",
            "--source",
            "fixture-source",
            "--owner-ref",
            "worksite:fixture",
            "--locator",
            "docs/report.md",
            "--role",
            "reference",
        ]
        missing_both = self.run_cli(*common, "--json", ok=False)
        self.assertIn("--custody", missing_both.stderr)
        missing_sensitivity = self.run_cli(*common, "--custody", "reference_only", "--json", ok=False)
        self.assertIn("--sensitivity", missing_sensitivity.stderr)
        self.assertFalse(self.materials_root().exists())

    def test_explicit_sources_accept_domain_authorities_and_keep_manifest_authority(self) -> None:
        self.fixture_source["authority"] = "lll_protocol"
        self.managed_source["authority"] = "aios_source_registry"
        self.write_registry(self.fixture_source, self.managed_source)

        _, dry = self.attach(dry_run=True)
        self.assertEqual(dry["status"], "would_attach")
        self.assertFalse(self.materials_root().exists(), "dry-run must remain zero-write")

        _, applied = self.attach()
        self.assertEqual(applied["status"], "attached")
        self.assertEqual(applied["record"]["authority"], "source_canonical")
        self.assertEqual(self.manifest()["materials"][0]["authority"], "source_canonical")

    def test_missing_empty_or_non_string_source_authority_fails_closed(self) -> None:
        valid = copy.deepcopy(self.fixture_source)
        missing = object()
        for authority in [missing, "", 42]:
            with self.subTest(authority="missing" if authority is missing else authority):
                record = copy.deepcopy(valid)
                if authority is missing:
                    record.pop("authority")
                else:
                    record["authority"] = authority
                self.set_fixture_source(record)
                _, rejected = self.attach(dry_run=True, ok=False)
                self.assertEqual(rejected["status"], "source_metadata_conflict")
                self.assertFalse(self.materials_root().exists())

    def test_manifest_schema_and_material_id_are_deterministic(self) -> None:
        dry_result, dry = self.attach(dry_run=True)
        self.assertEqual(dry["status"], "would_attach")
        self.assertEqual(dry["record"]["source"]["sha256"], sha256_bytes(self.source_bytes))
        self.assertEqual(dry["record"]["source"]["bytes"], len(self.source_bytes))
        self.assertFalse(self.materials_root().exists(), "dry-run must create no directories or files")
        self.assertNotIn("Evidence alpha.", dry_result.stdout)

        _, applied = self.attach()
        identity = {
            "matter_id": "matter_active",
            "owner_ref": "worksite:fixture",
            "relative_path": "docs/report.md",
            "role": "reference",
            "source_id": "fixture-source",
        }
        expected_id = "mat_" + sha256_bytes(
            json.dumps(identity, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        self.assertEqual(applied["material_id"], expected_id)
        manifest = self.manifest()
        self.assertEqual(set(manifest), {"schema", "matter_id", "materials"})
        self.assertEqual(manifest["schema"], "aios.matter.materials.v0")
        self.assertEqual(manifest["matter_id"], "matter_active")
        self.assertEqual(len(manifest["materials"]), 1)
        record = manifest["materials"][0]
        self.assertEqual(record["material_id"], expected_id)
        self.assertEqual(record["matter_id"], "matter_active")
        self.assertEqual(record["authority"], "source_canonical")
        self.assertEqual(record["adoption"], "not_adopted")
        self.assertEqual(record["execution"], "none")
        self.assertEqual(record["lifecycle_effect"], "none")
        self.assertIsNone(record["snapshot_relative_path"])
        self.assertNotIn("Evidence alpha.", json.dumps(manifest, ensure_ascii=False))

    def test_reference_attach_is_idempotent_and_creates_no_snapshot(self) -> None:
        _, first = self.attach()
        before = tree_fingerprint(self.materials_root())
        _, second = self.attach()
        after = tree_fingerprint(self.materials_root())
        self.assertEqual(first["status"], "attached")
        self.assertEqual(second["status"], "already_attached")
        self.assertEqual(first["material_id"], second["material_id"])
        self.assertEqual(after, before)
        self.assertFalse((self.materials_root() / "snapshots").exists())
        self.assertEqual(len(self.manifest()["materials"]), 1)

    def test_snapshot_attach_is_source_preserving_no_replace_and_idempotent(self) -> None:
        source_before = tree_fingerprint(self.source_root)
        _, first = self.attach(custody="immutable_snapshot", sensitivity="internal_restricted")
        record = self.manifest()["materials"][0]
        snapshot = self.materials_root() / record["snapshot_relative_path"]
        self.assertEqual(snapshot.read_bytes(), self.source_bytes)
        before = tree_fingerprint(self.materials_root())
        _, second = self.attach(custody="immutable_snapshot", sensitivity="internal_restricted")
        self.assertEqual(second["status"], "already_attached")
        self.assertEqual(tree_fingerprint(self.materials_root()), before)
        self.assertEqual(tree_fingerprint(self.source_root), source_before)
        self.assertEqual(first["record"]["source"]["sha256"], sha256_bytes(snapshot.read_bytes()))

    def test_source_equal_to_manifest_is_rejected_without_any_mutation(self) -> None:
        self.attach()
        manifest_path = self.materials_root() / "materials.json"
        self.set_fixture_source(
            self.source_record(
                "fixture-source",
                self.data_root,
                sensitivity="mixed",
            )
        )
        source_bytes_before = manifest_path.read_bytes()
        source_stat_before = manifest_path.lstat()
        source_path_before = manifest_path.resolve(strict=True)
        tree_before = tree_fingerprint(self.materials_root())

        result = self.invoke_cli(
            "matter",
            "material",
            "attach",
            "matter_active",
            "--source",
            "fixture-source",
            "--owner-ref",
            "worksite:fixture",
            "--locator",
            "managed/matter-materials/matter_active/materials.json",
            "--role",
            "evidence",
            "--custody",
            "reference_only",
            "--sensitivity",
            "internal_restricted",
            "--json",
        )
        report = json.loads(result.stdout)

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(report["ok"])
        self.assertEqual(report["status"], "source_destination_overlap")
        self.assertNotEqual(report["status"], "attached")
        source_stat_after = manifest_path.lstat()
        self.assertEqual((source_stat_after.st_dev, source_stat_after.st_ino), (source_stat_before.st_dev, source_stat_before.st_ino))
        self.assertEqual(manifest_path.resolve(strict=True), source_path_before)
        self.assertEqual(manifest_path.read_bytes(), source_bytes_before)
        self.assertEqual(tree_fingerprint(self.materials_root()), tree_before)

    def test_source_inode_alias_to_manifest_is_rejected_without_any_mutation(self) -> None:
        self.attach()
        manifest_path = self.materials_root() / "materials.json"
        alias_path = self.source_root / "docs" / "manifest-hardlink.json"
        os.link(manifest_path, alias_path)
        alias_bytes_before = alias_path.read_bytes()
        alias_stat_before = alias_path.lstat()
        tree_before = tree_fingerprint(self.materials_root())

        result = self.invoke_cli(
            "matter",
            "material",
            "attach",
            "matter_active",
            "--source",
            "fixture-source",
            "--owner-ref",
            "worksite:fixture",
            "--locator",
            "docs/manifest-hardlink.json",
            "--role",
            "evidence",
            "--custody",
            "reference_only",
            "--sensitivity",
            "internal",
            "--json",
        )
        report = json.loads(result.stdout)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report["status"], "source_destination_overlap")
        alias_stat_after = alias_path.lstat()
        self.assertEqual((alias_stat_after.st_dev, alias_stat_after.st_ino), (alias_stat_before.st_dev, alias_stat_before.st_ino))
        self.assertEqual(alias_path.read_bytes(), alias_bytes_before)
        self.assertEqual(tree_fingerprint(self.materials_root()), tree_before)

    def test_reference_can_upgrade_but_snapshot_cannot_downgrade(self) -> None:
        _, first = self.attach(sensitivity="internal_restricted")
        attached_at = first["record"]["attached_at"]
        _, upgraded = self.attach(custody="immutable_snapshot", sensitivity="internal_restricted")
        self.assertEqual(upgraded["status"], "custody_upgraded")
        self.assertEqual(upgraded["material_id"], first["material_id"])
        record = self.manifest()["materials"][0]
        self.assertEqual(record["attached_at"], attached_at)
        self.assertEqual(record["custody"], "immutable_snapshot")
        snapshot = self.materials_root() / record["snapshot_relative_path"]
        self.assertTrue(snapshot.is_file())

        before = tree_fingerprint(self.materials_root())
        _, replay = self.attach(custody="reference_only", sensitivity="internal_restricted")
        self.assertEqual(replay["status"], "already_attached")
        self.assertEqual(replay["record"]["custody"], "immutable_snapshot")
        self.assertEqual(tree_fingerprint(self.materials_root()), before)

    def test_same_association_source_drift_is_conflict(self) -> None:
        self.attach()
        manifest_before = tree_fingerprint(self.materials_root())
        self.source.write_text("# changed but valid UTF-8\n", encoding="utf-8")
        _, rejected = self.attach(ok=False)
        self.assertEqual(rejected["status"], "source_drift_conflict")
        self.assertEqual(tree_fingerprint(self.materials_root()), manifest_before)
        self.assertEqual(self.manifest()["materials"][0]["source"]["sha256"], sha256_bytes(self.source_bytes))

    def test_concurrent_attach_has_one_record_one_snapshot_and_no_lost_update(self) -> None:
        args = [
            "matter",
            "material",
            "attach",
            "matter_active",
            "--source",
            "fixture-source",
            "--owner-ref",
            "worksite:fixture",
            "--locator",
            "docs/report.md",
            "--role",
            "evidence",
            "--custody",
            "immutable_snapshot",
            "--sensitivity",
            "internal_restricted",
            "--json",
        ]
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: self.invoke_cli(*args), range(6)))
        for result in results:
            self.assertEqual(result.returncode, 0, f"stdout={result.stdout}\nstderr={result.stderr}")
        statuses = [json.loads(result.stdout)["status"] for result in results]
        self.assertEqual(statuses.count("attached"), 1)
        self.assertEqual(statuses.count("already_attached"), 5)
        records = self.manifest()["materials"]
        self.assertEqual(len(records), 1)
        snapshots = list((self.materials_root() / "snapshots").iterdir())
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].name, sha256_bytes(self.source_bytes))
        self.assertEqual(snapshots[0].read_bytes(), self.source_bytes)

    def test_existing_mismatched_snapshot_is_never_overwritten(self) -> None:
        digest = sha256_bytes(self.source_bytes)
        snapshots = self.materials_root() / "snapshots"
        snapshots.mkdir(parents=True)
        target = snapshots / digest
        target.write_bytes(b"mismatched existing bytes\n")
        before = tree_fingerprint(self.materials_root())
        _, rejected = self.attach(custody="immutable_snapshot", sensitivity="internal_restricted", ok=False)
        self.assertEqual(rejected["status"], "snapshot_conflict")
        self.assertEqual(tree_fingerprint(self.materials_root()), before)
        self.assertFalse((self.materials_root() / "materials.json").exists())

    def test_regular_utf8_size_symlink_and_sensitivity_gates_fail_closed(self) -> None:
        invalid_utf8 = self.source_root / "docs" / "invalid.bin"
        invalid_utf8.write_bytes(b"\xff\xfe")
        nul_file = self.source_root / "docs" / "nul.txt"
        nul_file.write_bytes(b"hello\x00world")
        large = self.source_root / "docs" / "large.txt"
        large.write_bytes(b"x" * (MAX_BYTES + 1))
        fifo = self.source_root / "docs" / "pipe"
        os.mkfifo(fifo)
        link = self.source_root / "docs" / "link.md"
        link.symlink_to(self.source)
        linked_dir = self.source_root / "linked-docs"
        linked_dir.symlink_to(self.source.parent, target_is_directory=True)

        for locator in [
            "/absolute/report.md",
            "../report.md",
            "docs",
            "docs/invalid.bin",
            "docs/nul.txt",
            "docs/large.txt",
            "docs/pipe",
            "docs/link.md",
            "linked-docs/report.md",
        ]:
            with self.subTest(locator=locator):
                _, rejected = self.attach(locator=locator, custody="immutable_snapshot", sensitivity="internal_restricted", ok=False)
                self.assertFalse(rejected["ok"])
                self.assertFalse(self.materials_root().exists())

        sensitive = copy.deepcopy(self.fixture_source)
        sensitive["sensitivity"] = "sensitive"
        self.set_fixture_source(sensitive)
        _, rejected_sensitive = self.attach(custody="immutable_snapshot", sensitivity="internal_restricted", ok=False)
        self.assertEqual(rejected_sensitive["status"], "source_sensitivity_rejected")

        mixed = copy.deepcopy(self.fixture_source)
        mixed["sensitivity"] = "mixed"
        self.set_fixture_source(mixed)
        _, rejected_mixed = self.attach(custody="immutable_snapshot", sensitivity="internal", ok=False)
        self.assertEqual(rejected_mixed["status"], "source_sensitivity_requires_internal_restricted")
        _, allowed_mixed = self.attach(
            custody="immutable_snapshot", sensitivity="internal_restricted", dry_run=True
        )
        self.assertEqual(allowed_mixed["status"], "would_attach")
        self.assertFalse(self.materials_root().exists())

        conflicting = copy.deepcopy(self.fixture_source)
        conflicting["sensitivity"] = "internal"
        conflicting["locations"] = [
            {"kind": "local", "path": str(self.source_root)},
            {"kind": "local", "path": str(self.home / "other-root")},
        ]
        self.set_fixture_source(conflicting)
        _, rejected_conflict = self.attach(ok=False)
        self.assertEqual(rejected_conflict["status"], "source_metadata_conflict")
        self.assertFalse(self.materials_root().exists())

        unknown = copy.deepcopy(self.fixture_source)
        unknown["locations"] = [{"kind": "local", "path": str(self.source_root)}]
        unknown["sync_mode"] = "unknown_mode"
        self.set_fixture_source(unknown)
        _, rejected_unknown = self.attach(ok=False)
        self.assertEqual(rejected_unknown["status"], "source_metadata_conflict")
        self.assertFalse(self.materials_root().exists())

    def test_list_is_manifest_only_and_byte_for_byte_read_only(self) -> None:
        self.attach(role="reference")
        self.attach(role="evidence", custody="immutable_snapshot", sensitivity="internal_restricted")
        before = tree_fingerprint(self.materials_root())
        result = self.run_cli("matter", "material", "list", "matter_active", "--json")
        after = tree_fingerprint(self.materials_root())
        self.assertEqual(after, before)
        report = json.loads(result.stdout)
        self.assertEqual(report["schema"], "aios.matter.material-list.v0")
        self.assertEqual(report["count"], 2)
        self.assertEqual([row["material_id"] for row in report["materials"]], sorted(row["material_id"] for row in report["materials"]))
        states = {row["custody"]: (row["source_state"], row["snapshot_state"]) for row in report["materials"]}
        self.assertEqual(states["reference_only"], ("unchecked", "not_required"))
        self.assertEqual(states["immutable_snapshot"], ("unchecked", "unchecked"))
        self.assertNotIn("Evidence alpha.", result.stdout)

    def test_verify_state_matrix_is_byte_for_byte_read_only(self) -> None:
        _, reference = self.attach(role="reference")
        _, snapshot = self.attach(role="evidence", custody="immutable_snapshot", sensitivity="internal_restricted")
        reference_id = reference["material_id"]
        snapshot_id = snapshot["material_id"]

        all_pass = self.assert_verify_read_only("--all", ok=True)
        self.assertTrue(all_pass["ok"])
        self.assertEqual({row["verdict"] for row in all_pass["results"]}, {"pass"})

        reference_pass = self.assert_verify_read_only(reference_id, ok=True)["results"][0]
        self.assertEqual((reference_pass["source_state"], reference_pass["snapshot_state"], reference_pass["verdict"]), ("match", "not_required", "pass"))

        snapshot_pass = self.assert_verify_read_only(snapshot_id, ok=True)["results"][0]
        self.assertEqual((snapshot_pass["source_state"], snapshot_pass["snapshot_state"], snapshot_pass["verdict"]), ("match", "match", "pass"))

        self.source.write_text("# valid drift\n", encoding="utf-8")
        drift_warning = self.assert_verify_read_only(snapshot_id, ok=True)["results"][0]
        self.assertEqual((drift_warning["source_state"], drift_warning["snapshot_state"], drift_warning["verdict"]), ("drifted", "match", "recoverable_warning"))

        self.source.unlink()
        reference_missing = self.assert_verify_read_only(reference_id, ok=False)["results"][0]
        self.assertEqual((reference_missing["source_state"], reference_missing["verdict"]), ("missing", "fail"))
        snapshot_recoverable = self.assert_verify_read_only(snapshot_id, ok=True)["results"][0]
        self.assertEqual((snapshot_recoverable["source_state"], snapshot_recoverable["snapshot_state"], snapshot_recoverable["verdict"]), ("missing", "match", "recoverable_warning"))

        self.source.write_bytes(self.source_bytes)
        snapshot_path = self.materials_root() / snapshot["record"]["snapshot_relative_path"]
        snapshot_path.unlink()
        snapshot_missing = self.assert_verify_read_only(snapshot_id, ok=False)["results"][0]
        self.assertEqual((snapshot_missing["source_state"], snapshot_missing["snapshot_state"], snapshot_missing["verdict"]), ("match", "missing", "fail"))

        snapshot_path.write_bytes(b"valid but drifted snapshot\n")
        snapshot_drifted = self.assert_verify_read_only(snapshot_id, ok=False)["results"][0]
        self.assertEqual((snapshot_drifted["source_state"], snapshot_drifted["snapshot_state"], snapshot_drifted["verdict"]), ("match", "drifted", "fail"))

    def test_active_paused_matter_attach_has_zero_lifecycle_side_effects(self) -> None:
        paused = self.create_matter("matter_paused", state="paused", attention="paused")
        closed = self.create_matter("matter_closed", state="closed", attention="none")
        archived = self.create_matter("matter_archived", state="archived", attention="none")
        inferred = self.create_matter("inferred_only", state="active", formal=False)
        before = {
            "active": tree_fingerprint(self.active_worksite),
            "paused": tree_fingerprint(paused),
            "closed": tree_fingerprint(closed),
            "archived": tree_fingerprint(archived),
            "inferred": tree_fingerprint(inferred),
        }

        _, active_report = self.attach(matter_id="matter_active")
        _, paused_report = self.attach(
            matter_id="matter_paused",
            custody="immutable_snapshot",
            sensitivity="internal_restricted",
        )
        self.assertEqual(active_report["status"], "attached")
        self.assertEqual(paused_report["status"], "attached")
        self.assertEqual(tree_fingerprint(self.active_worksite), before["active"])
        self.assertEqual(tree_fingerprint(paused), before["paused"])
        self.assertFalse((self.aios / "state" / "matters" / "index.json").exists())

        inferred_id = f"worksite:{inferred.name}"
        for matter_id, key in [
            ("matter_closed", "closed"),
            ("matter_archived", "archived"),
            (inferred_id, "inferred"),
        ]:
            with self.subTest(matter_id=matter_id):
                _, rejected = self.attach(matter_id=matter_id, ok=False)
                self.assertEqual(rejected["status"], "matter_not_attachable")
                self.assertEqual(tree_fingerprint({"closed": closed, "archived": archived, "inferred": inferred}[key]), before[key])
                self.assertFalse(self.materials_root(matter_id).exists())

    def test_attach_requires_explicit_raw_active_or_paused_lifecycle(self) -> None:
        invalid_lifecycles: list[tuple[str, Any]] = [
            ("unknown_state", {"state": "mystery", "attention": "current"}),
            ("missing_lifecycle", None),
            ("missing_state", {"attention": "current"}),
            ("non_object_lifecycle", ["active"]),
            ("non_string_state", {"state": ["active"], "attention": "current"}),
        ]
        fixtures: list[tuple[str, Path]] = []
        for suffix, lifecycle in invalid_lifecycles:
            matter_id = f"matter_{suffix}"
            worksite = self.create_matter(matter_id, state="active")
            matter_path = worksite / "internal" / "matter.json"
            raw = json.loads(matter_path.read_text(encoding="utf-8"))
            if lifecycle is None:
                raw.pop("lifecycle")
            else:
                raw["lifecycle"] = lifecycle
            matter_path.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            fixtures.append((matter_id, worksite))

        managed_before = tree_fingerprint(self.managed)
        for matter_id, worksite in fixtures:
            with self.subTest(matter_id=matter_id):
                worksite_before = tree_fingerprint(worksite)
                result = self.invoke_cli(
                    "matter",
                    "material",
                    "attach",
                    matter_id,
                    "--source",
                    "fixture-source",
                    "--owner-ref",
                    "worksite:fixture",
                    "--locator",
                    "docs/report.md",
                    "--role",
                    "reference",
                    "--custody",
                    "reference_only",
                    "--sensitivity",
                    "internal",
                    "--json",
                )
                report = json.loads(result.stdout)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(report["ok"])
                self.assertEqual(report["status"], "matter_not_attachable")
                self.assertEqual(tree_fingerprint(worksite), worksite_before)
                self.assertFalse(self.materials_root(matter_id).exists())
                self.assertEqual(tree_fingerprint(self.managed), managed_before)

    def test_list_and_verify_ignore_malformed_raw_lifecycle_without_writes(self) -> None:
        _, attached = self.attach()
        matter_path = self.active_worksite / "internal" / "matter.json"
        raw = json.loads(matter_path.read_text(encoding="utf-8"))
        raw["lifecycle"] = {"state": ["malformed"], "attention": "paused"}
        matter_path.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        worksite_before = tree_fingerprint(self.active_worksite)
        materials_before = tree_fingerprint(self.materials_root())

        listed = self.run_cli("matter", "material", "list", "matter_active", "--json")
        verified = self.run_cli(
            "matter",
            "material",
            "verify",
            "matter_active",
            attached["material_id"],
            "--json",
        )

        self.assertTrue(json.loads(listed.stdout)["ok"])
        self.assertTrue(json.loads(verified.stdout)["ok"])
        self.assertEqual(tree_fingerprint(self.active_worksite), worksite_before)
        self.assertEqual(tree_fingerprint(self.materials_root()), materials_before)


if __name__ == "__main__":
    unittest.main()
