from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "aios.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PromotionCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="aios-promotion-test-")
        self.home = Path(self.tmp.name)
        self.worksite = self.home / "aios" / "work" / "20260718-100000_source-research"
        self.worksite.mkdir(parents=True)
        (self.worksite / "mission.md").write_text("# Source research\n", encoding="utf-8")
        self.source = self.worksite / "report.md"
        self.source.write_text("# Frozen report\n\nEvidence.\n", encoding="utf-8")

        self.data_root = self.home / "aios" / "data"
        self.target_dir = self.data_root / "managed" / "technical-research" / "fixture"
        self.target_dir.mkdir(parents=True)
        self.target = self.target_dir / "report.md"
        shutil.copy2(self.source, self.target)

        self.run_cli(
            "source", "add",
            "--id", "aios-managed-zone",
            "--name", "AIOS Managed Zone",
            "--kind", "managed_zone",
            "--path", str(self.data_root),
            "--owner-ref", "source:aios-managed-zone",
            "--access-mode", "curate_reversible",
            "--sync-mode", "server_canonical_replica",
            "--backup-status", "planned",
            "--sensitivity", "mixed",
        )

        self.change_path = self.home / "aios" / "state" / "matters" / "change-sets" / "fixture.json"
        self.change_path.parent.mkdir(parents=True)
        self.receipt_path = self.target_dir / "promotion-receipt.json"
        digest = sha256(self.source)
        size = self.source.stat().st_size
        self.receipt = {
            "schema": "aios.asset-promotion-receipt.v0",
            "status": "applied_validated",
            "asset_id": "fixture",
            "asset_type": "technical_research/test",
            "owner_ref": "source:aios-managed-zone",
            "change_set_id": "pcs_fixture",
            "change_set_path": str(self.change_path),
            "source_worksite": {
                "worksite_id": "worksite:20260718-100000_source-research",
                "worksite_path": str(self.worksite),
                "lifecycle_state": "closed",
                "validation_verdict": "PASS",
            },
            "files": [{
                "name": "report.md",
                "source": str(self.source),
                "target": str(self.target),
                "sha256": digest,
                "bytes": size,
            }],
            "backup_boundary": {
                "managed_zone_backup_status": "planned",
                "allowed_scope": "one-file copy-only promotion with preserved independent source original",
                "does_not_authorize": ["move", "rename", "delete", "overwrite", "bulk curation", "source mutation"],
            },
            "undo": {"reversible": True, "source_restoration_required": False},
        }
        self.change = {
            "schema": "aios.asset-promotion-change-set.v0",
            "id": "pcs_fixture",
            "status": "applied_validated",
            "source": {
                "worksite_id": "worksite:20260718-100000_source-research",
                "worksite_path": str(self.worksite),
            },
            "target": {
                "owner_ref": "source:aios-managed-zone",
                "asset_type": "technical_research/test",
                "asset_id": "fixture",
                "directory": str(self.target_dir),
            },
            "scope": {
                "selected": [{
                    "source": str(self.source),
                    "target": str(self.target),
                    "sha256": digest,
                    "bytes": size,
                }],
                "excluded": ["mission.md", "internal/**"],
                "operation": "copy_if_absent",
                "overwrite": False,
                "source_mutation": False,
            },
            "gates": {"managed_zone_backup_status": "planned"},
            "undo": {"reversible": True, "source_restoration_required": False},
            "result": {
                "verdict": "PASS",
                "target_directory": str(self.target_dir),
                "promotion_receipt": str(self.receipt_path),
                "promotion_receipt_sha256": "filled-by-write-pair",
                "created_files": [str(self.target), str(self.receipt_path)],
                "source_files_unchanged": True,
            },
        }
        self.write_pair()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_cli(self, *args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(CLI), "--home", str(self.home), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if ok and result.returncode != 0:
            self.fail(f"command failed: {args}\nstdout={result.stdout}\nstderr={result.stderr}")
        if not ok and result.returncode == 0:
            self.fail(f"command unexpectedly passed: {args}\nstdout={result.stdout}")
        return result

    def write_pair(self, receipt: dict[str, object] | None = None, change: dict[str, object] | None = None) -> None:
        receipt_value = copy.deepcopy(receipt if receipt is not None else self.receipt)
        change_value = copy.deepcopy(change if change is not None else self.change)
        self.receipt_path.write_text(json.dumps(receipt_value, indent=2) + "\n", encoding="utf-8")
        change_value["result"]["promotion_receipt_sha256"] = sha256(self.receipt_path)  # type: ignore[index]
        self.change_path.write_text(json.dumps(change_value, indent=2) + "\n", encoding="utf-8")

    def assert_pair_fails(self, *, receipt: dict[str, object] | None = None, change: dict[str, object] | None = None, error_name: str) -> None:
        self.write_pair(receipt=receipt, change=change)
        report = json.loads(self.run_cli("promotion", "undo-check", str(self.receipt_path), ok=False).stdout)
        self.assertFalse(report["ok"])
        self.assertFalse(report["safe_to_remove_target_directory"])
        self.assertTrue(any(error_name in error for error in report["errors"]), report["errors"])

    def test_validate_change_set_receipt_and_undo_precondition(self) -> None:
        from_change = json.loads(self.run_cli("promotion", "validate", str(self.change_path), "--json").stdout)
        self.assertTrue(from_change["ok"])
        self.assertEqual(from_change["schema"], "aios.asset-promotion-validation.v1")
        self.assertTrue(from_change["safe_to_remove_target_directory"])
        self.assertTrue(from_change["warnings"])

        from_receipt = json.loads(self.run_cli("promotion", "validate", str(self.receipt_path)).stdout)
        self.assertTrue(from_receipt["ok"])
        undo = json.loads(self.run_cli("promotion", "undo-check", str(self.receipt_path)).stdout)
        self.assertEqual(undo["schema"], "aios.asset-promotion-undo-check.v1")
        self.assertTrue(undo["safe_to_remove_target_directory"])

    def test_identity_provenance_backup_and_undo_mismatches_fail_closed(self) -> None:
        owner_mismatch = copy.deepcopy(self.receipt)
        owner_mismatch["owner_ref"] = "source:other-owner"
        self.assert_pair_fails(receipt=owner_mismatch, error_name="owner_ref_binding")

        owner_missing = copy.deepcopy(self.receipt)
        del owner_missing["owner_ref"]
        self.assert_pair_fails(receipt=owner_missing, error_name="owner_ref_present")

        other_worksite = self.home / "aios" / "work" / "20260718-100001_other-source"
        other_worksite.mkdir()
        (other_worksite / "mission.md").write_text("# Other\n", encoding="utf-8")
        source_mismatch = copy.deepcopy(self.change)
        source_mismatch["source"] = {
            "worksite_id": "worksite:20260718-100001_other-source",
            "worksite_path": str(other_worksite),
        }
        self.assert_pair_fails(change=source_mismatch, error_name="source_worksite_id")

        asset_mismatch = copy.deepcopy(self.receipt)
        asset_mismatch["asset_id"] = "different"
        asset_mismatch["asset_type"] = "different/type"
        self.assert_pair_fails(receipt=asset_mismatch, error_name="asset_id")

        backup_mismatch = copy.deepcopy(self.receipt)
        backup_mismatch["backup_boundary"]["managed_zone_backup_status"] = "verified"
        self.assert_pair_fails(receipt=backup_mismatch, error_name="receipt_backup_status")

        undo_false = copy.deepcopy(self.receipt)
        undo_false["undo"]["reversible"] = False
        self.assert_pair_fails(receipt=undo_false, error_name="undo_reversible")

        undo_missing = copy.deepcopy(self.receipt)
        del undo_missing["undo"]
        self.assert_pair_fails(receipt=undo_missing, error_name="undo_reversible")

    def test_unknown_or_tampered_target_fails_closed(self) -> None:
        extra = self.target_dir / "unknown.txt"
        extra.write_text("unexpected\n", encoding="utf-8")
        unknown = json.loads(self.run_cli("promotion", "validate", str(self.receipt_path), ok=False).stdout)
        self.assertFalse(unknown["ok"])
        self.assertTrue(any("target_exact_set" in error for error in unknown["errors"]))
        extra.unlink()

        self.target.write_text("tampered\n", encoding="utf-8")
        tampered = json.loads(self.run_cli("promotion", "undo-check", str(self.receipt_path), ok=False).stdout)
        self.assertFalse(tampered["safe_to_remove_target_directory"])
        self.assertTrue(any("target_hash" in error for error in tampered["errors"]))


class PromotionApplyCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="aios-promotion-apply-test-")
        self.home = Path(self.tmp.name)
        self.worksite = self.home / "aios" / "work" / "20260719-130000_workflow-core"
        self.worksite.mkdir(parents=True)
        (self.worksite / "mission.md").write_text("# Workflow Core\n", encoding="utf-8")
        self.source = self.worksite / "decision.md"
        self.source.write_text("# Decision\n\nUse a thin adapter.\n", encoding="utf-8")
        self.data_root = self.home / "aios" / "data"
        self.target_dir = self.data_root / "managed" / "product-decisions" / "workflow-core" / "fixture"
        self.target = self.target_dir / self.source.name
        self.change_path = self.home / "aios" / "state" / "matters" / "change-sets" / "apply-fixture.json"
        self.change_path.parent.mkdir(parents=True)
        self.run_cli(
            "source", "add",
            "--id", "aios-managed-zone",
            "--name", "AIOS Managed Zone",
            "--kind", "managed_zone",
            "--path", str(self.data_root),
            "--owner-ref", "source:aios-managed-zone",
            "--access-mode", "curate_reversible",
            "--sync-mode", "server_canonical_replica",
            "--backup-status", "planned",
            "--sensitivity", "mixed",
        )
        digest = sha256(self.source)
        size = self.source.stat().st_size
        self.change = {
            "schema": "aios.asset-promotion-change-set.v0",
            "id": "pcs_apply_fixture",
            "status": "authorized_pending",
            "matter_ref": "matter_enterprise_ai_workflow_core",
            "trigger": {"kind": "explicit_user_instruction", "summary": "Persist this asset."},
            "assessment": {"score": 92, "confidence": "high", "main_caveat": "Fixture."},
            "source": {
                "worksite_id": "worksite:20260719-130000_workflow-core",
                "worksite_path": str(self.worksite),
                "lifecycle_state": "closed",
                "validation_verdict": "PASS_WITH_NOTES",
            },
            "target": {
                "owner_ref": "source:aios-managed-zone",
                "asset_type": "platform_adapter_adr/workflow-core",
                "asset_id": "workflow-core-fixture",
                "directory": str(self.target_dir),
            },
            "scope": {
                "selected": [{
                    "source": str(self.source),
                    "target": str(self.target),
                    "sha256": digest,
                    "bytes": size,
                }],
                "excluded": ["mission.md", "internal/**"],
                "operation": "copy_if_absent",
                "overwrite": False,
                "source_mutation": False,
            },
            "gates": {
                "explicit_authorization": "pass",
                "managed_zone_backup_status": "planned",
            },
            "undo": {"reversible": True, "source_restoration_required": False},
        }
        self.change_path.write_text(json.dumps(self.change, indent=2) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_cli(self, *args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(CLI), "--home", str(self.home), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if ok and result.returncode != 0:
            self.fail(f"command failed: {args}\nstdout={result.stdout}\nstderr={result.stderr}")
        if not ok and result.returncode == 0:
            self.fail(f"command unexpectedly passed: {args}\nstdout={result.stdout}")
        return result

    def test_apply_is_dry_run_by_default_then_applies_and_validates(self) -> None:
        plan = json.loads(self.run_cli("promotion", "apply", str(self.change_path)).stdout)
        self.assertEqual(plan["schema"], "aios.asset-promotion-apply.v1")
        self.assertEqual(plan["status"], "planned")
        self.assertFalse(self.target_dir.exists())

        applied = json.loads(self.run_cli("promotion", "apply", str(self.change_path), "--apply").stdout)
        self.assertTrue(applied["ok"])
        self.assertEqual(applied["status"], "applied_validated")
        self.assertTrue(self.target.is_file())
        self.assertEqual(sha256(self.target), sha256(self.source))

        validation = json.loads(self.run_cli("promotion", "validate", str(self.change_path)).stdout)
        self.assertTrue(validation["ok"])
        replay = json.loads(self.run_cli("promotion", "apply", str(self.change_path), "--apply").stdout)
        self.assertTrue(replay["ok"])
        self.assertEqual(replay["status"], "already_applied_validated")

    def test_apply_fails_closed_on_source_hash_mismatch(self) -> None:
        changed = copy.deepcopy(self.change)
        changed["scope"]["selected"][0]["sha256"] = "0" * 64
        self.change_path.write_text(json.dumps(changed, indent=2) + "\n", encoding="utf-8")
        report = json.loads(self.run_cli("promotion", "apply", str(self.change_path), "--apply", ok=False).stdout)
        self.assertFalse(report["ok"])
        self.assertTrue(any("source_hash" in error for error in report["errors"]))
        self.assertFalse(self.target_dir.exists())

    def test_apply_recovers_target_installed_before_change_set_finalize(self) -> None:
        first = json.loads(self.run_cli("promotion", "apply", str(self.change_path), "--apply").stdout)
        self.assertTrue(first["ok"])
        interrupted = json.loads(self.change_path.read_text(encoding="utf-8"))
        interrupted["status"] = "authorized_pending"
        interrupted.pop("result", None)
        self.change_path.write_text(json.dumps(interrupted, indent=2) + "\n", encoding="utf-8")

        plan = json.loads(self.run_cli("promotion", "apply", str(self.change_path)).stdout)
        self.assertEqual(plan["status"], "existing_target_ready_to_finalize")
        recovered = json.loads(self.run_cli("promotion", "apply", str(self.change_path), "--apply").stdout)
        self.assertTrue(recovered["ok"])
        self.assertEqual(recovered["status"], "applied_validated")
        self.assertTrue(json.loads(self.change_path.read_text(encoding="utf-8"))["result"]["source_files_unchanged"])

    def test_apply_rejects_existing_unowned_target_without_overwrite(self) -> None:
        self.target_dir.mkdir(parents=True)
        report = json.loads(self.run_cli("promotion", "apply", str(self.change_path), "--apply", ok=False).stdout)
        self.assertFalse(report["ok"])
        self.assertEqual(report["status"], "target_exists_invalid")
        self.assertEqual(list(self.target_dir.iterdir()), [])

    def test_apply_rejects_unsafe_boundaries_before_mutation(self) -> None:
        cases: list[tuple[str, Callable[[dict[str, Any]], None]]] = [
            ("explicit_authorization", lambda value: value["gates"].update(explicit_authorization="missing")),
            ("change_set_status", lambda value: value.update(status="draft")),
            ("change_set_id", lambda value: value.update(id="")),
            ("source_worksite_id", lambda value: value["source"].update(worksite_id="")),
            ("asset_id", lambda value: value["target"].update(asset_id="")),
            ("asset_type", lambda value: value["target"].update(asset_type="")),
            ("owner", lambda value: value["target"].update(owner_ref="source:missing")),
            ("copy_only_operation", lambda value: value["scope"].update(operation="copy")),
            ("overwrite", lambda value: value["scope"].update(overwrite=True)),
            ("source_mutation", lambda value: value["scope"].update(source_mutation=True)),
            ("undo", lambda value: value["undo"].update(reversible=False)),
            ("reserved_name", lambda value: value["scope"]["selected"][0].update(target=str(self.target_dir / "promotion-receipt.json"))),
        ]
        for expected, mutate in cases:
            with self.subTest(expected=expected):
                changed = copy.deepcopy(self.change)
                mutate(changed)
                self.change_path.write_text(json.dumps(changed, indent=2) + "\n", encoding="utf-8")
                report = json.loads(self.run_cli("promotion", "apply", str(self.change_path), "--apply", ok=False).stdout)
                self.assertFalse(report["ok"])
                self.assertTrue(any(expected in error for error in report["errors"]), report["errors"])
                self.assertFalse(self.target_dir.exists())

    def test_apply_rejects_target_inside_source_worksite(self) -> None:
        nested_root = self.worksite / "managed-zone"
        self.run_cli(
            "source", "add",
            "--id", "nested-zone",
            "--name", "Nested Managed Zone",
            "--kind", "managed_zone",
            "--path", str(nested_root),
            "--owner-ref", "source:nested-zone",
            "--access-mode", "curate_reversible",
            "--sync-mode", "server_canonical_replica",
            "--backup-status", "planned",
            "--sensitivity", "mixed",
        )
        changed = copy.deepcopy(self.change)
        nested_target = nested_root / "managed" / "fixture"
        changed["target"].update(owner_ref="source:nested-zone", directory=str(nested_target))
        changed["scope"]["selected"][0]["target"] = str(nested_target / self.source.name)
        self.change_path.write_text(json.dumps(changed, indent=2) + "\n", encoding="utf-8")
        report = json.loads(self.run_cli("promotion", "apply", str(self.change_path), "--apply", ok=False).stdout)
        self.assertFalse(report["ok"])
        self.assertTrue(any("source_target_disjoint" in error for error in report["errors"]))
        self.assertFalse(nested_target.parent.exists())

    def test_apply_rejects_unsupported_backup_state_before_mutation(self) -> None:
        unknown_root = self.home / "aios" / "unknown-data"
        self.run_cli(
            "source", "add",
            "--id", "unknown-zone",
            "--name", "Unknown Backup Zone",
            "--kind", "managed_zone",
            "--path", str(unknown_root),
            "--owner-ref", "source:unknown-zone",
            "--access-mode", "curate_reversible",
            "--sync-mode", "server_canonical_replica",
            "--backup-status", "unknown",
            "--sensitivity", "mixed",
        )
        changed = copy.deepcopy(self.change)
        changed_target_dir = unknown_root / "managed" / "fixture"
        changed["target"].update(owner_ref="source:unknown-zone", directory=str(changed_target_dir))
        changed["scope"]["selected"][0]["target"] = str(changed_target_dir / self.source.name)
        changed["gates"]["managed_zone_backup_status"] = "unknown"
        self.change_path.write_text(json.dumps(changed, indent=2) + "\n", encoding="utf-8")
        report = json.loads(self.run_cli("promotion", "apply", str(self.change_path), "--apply", ok=False).stdout)
        self.assertFalse(report["ok"])
        self.assertTrue(any("backup_status_supported" in error for error in report["errors"]))
        self.assertFalse(changed_target_dir.exists())


if __name__ == "__main__":
    unittest.main()
