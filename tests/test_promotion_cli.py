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


if __name__ == "__main__":
    unittest.main()
