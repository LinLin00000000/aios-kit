from __future__ import annotations

import fcntl
import hashlib
import json
import os
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "aios.py"
MATTER_ID = "matter_rollover_test"
AUTHORIZED_OPERATION = "B6 one exact Matter current Worksite rollover through a CAS/idempotent/receipt-backed actuator"


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MatterRolloverCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="aios-matter-rollover-test-")
        self.home = Path(self.tmp.name)
        self.work = self.home / "aios" / "work"
        self.owner = self.work / "20260801-100000_owner"
        self.target = self.work / "20260802-100000_target"
        self.current = {
            "id": "worksite_rollover_owner",
            "path": str(self.owner.resolve()),
            "role": "latest_completed_baseline",
            "recovery_path": "internal/recovery.json",
            "binding": "owned",
            "owner_matter_id": MATTER_ID,
        }
        self.matter = {
            "schema": "aios.workflow.state.v0",
            "id": MATTER_ID,
            "title": "Rollover Test",
            "status": "active",
            "updated_at": "2026-08-01T10:00:00+00:00",
            "owner": {"kind": "human", "id": "tester", "role": "owner"},
            "lifecycle": {"state": "active", "attention": "paused", "reopenable": True},
            "worksite": self.current,
            "delivery": {"featured": ["final-report.md"], "limit": 3},
        }
        self._create_worksite(self.owner, "worksite_rollover_owner", MATTER_ID, "completed")
        self._create_worksite(self.target, self.target.name, MATTER_ID, "completed")
        self.matter_path = self.owner / "internal" / "matter.json"
        self.events_path = self.owner / "internal" / "matter.events.jsonl"
        self.matter_path.write_bytes(json_bytes(self.matter))
        self.events_path.write_text(
            json.dumps(
                {
                    "schema": "aios.workflow.event.v0",
                    "event_id": "evt_initial",
                    "ts": "2026-08-01T10:00:00+00:00",
                    "type": "matter.created",
                    "subject": {"kind": "matter", "id": MATTER_ID},
                },
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        self.pre_matter_sha = sha256(self.matter_path)
        self.pre_events_sha = sha256(self.events_path)
        self.key = f"matter-rollover:{MATTER_ID}:{self.target.name}:fixture"
        self.authorization_path = self.home / "authorization.json"
        self._write_authorization()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_worksite(self, path: Path, mission_id: str, parent_id: str, status: str) -> None:
        (path / "internal").mkdir(parents=True, exist_ok=True)
        (path / "mission.md").write_text(
            f"# {mission_id}\n\nmission_id: {mission_id}\nparent_matter_id: {parent_id}\n"
            f"parent_worksite: {self.owner.resolve()}\nstatus: {status}\nphase: {status}\n",
            encoding="utf-8",
        )
        (path / "internal" / "recovery.json").write_bytes(
            json_bytes({"schema": "lll.recovery.v1", "status": status, "phase": status})
        )
        (path / "final-report.md").write_text("# final\n", encoding="utf-8")

    def _write_authorization(
        self,
        *,
        path: Path | None = None,
        scope: dict[str, str] | None = None,
        authorized: list[str] | None = None,
    ) -> Path:
        path = path or self.authorization_path
        value = {
            "schema": "aios.phase_b.authorization.v1",
            "authorization_id": "matter-rollover-test-authorization",
            "scope": scope
            or {
                "worksite": str(self.target.resolve()),
                "parent_worksite": str(self.owner.resolve()),
                "parent_matter": MATTER_ID,
            },
            "authorized": authorized or [AUTHORIZED_OPERATION],
        }
        path.write_bytes(json_bytes(value))
        return path

    def run_cli(
        self, *args: str, ok: bool = True, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        cp = subprocess.run(
            [sys.executable, str(CLI), "--home", str(self.home), *args],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            env={**os.environ, **(env or {})},
        )
        if ok and cp.returncode != 0:
            self.fail(f"command failed {args}:\nstdout={cp.stdout}\nstderr={cp.stderr}")
        return cp

    def _candidate(
        self,
        *,
        target: Path | None = None,
        target_id: str | None = None,
        to_role: str = "current_canonical",
        key: str | None = None,
        matter_sha: str | None = None,
        events_sha: str | None = None,
        event_count: int = 1,
        current_id: str = "worksite_rollover_owner",
        current_path: Path | None = None,
        current_role: str = "latest_completed_baseline",
    ) -> dict[str, Any]:
        target = (target or self.target).resolve()
        target_id = target_id or target.name
        key = key or self.key
        from_worksite = {
            "id": current_id,
            "path": str((current_path or self.owner).resolve()),
            "role": current_role,
            "recovery_path": "internal/recovery.json",
            "binding": "owned",
            "owner_matter_id": MATTER_ID,
        }
        to_worksite = {
            "id": target_id,
            "path": str(target),
            "role": to_role,
            "recovery_path": "internal/recovery.json",
            "binding": "owned",
            "owner_matter_id": MATTER_ID,
        }
        mission = target / "mission.md"
        recovery = target / "internal" / "recovery.json"
        candidate = {
            "schema": "aios.matter.rollover.candidate.v1",
            "matter_id": MATTER_ID,
            "matter_path": str(self.matter_path.resolve()),
            "expected_matter_sha256": matter_sha or self.pre_matter_sha,
            "expected_event_sha256": events_sha or self.pre_events_sha,
            "expected_event_sequence": event_count,
            "from_worksite": from_worksite,
            "to_worksite": to_worksite,
            "target_mission_sha256": sha256(mission),
            "target_recovery_sha256": sha256(recovery),
            "target_mission_status": "completed",
            "target_recovery_status": "completed",
            "target_parent_matter_id": MATTER_ID,
            "idempotency_key": key,
        }
        candidate["plan_digest"] = hashlib.sha256(
            json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return candidate

    def _args(self, *, apply: bool = False, authorization: bool = True, **overrides: Any) -> list[str]:
        candidate = self._candidate(**overrides)
        before = candidate["from_worksite"]
        after = candidate["to_worksite"]
        args = [
            "matter",
            "rollover",
            MATTER_ID,
            "--expected-current-id",
            before["id"],
            "--expected-current-path",
            before["path"],
            "--expected-current-role",
            before["role"],
            "--expected-matter-sha256",
            candidate["expected_matter_sha256"],
            "--expected-events-sha256",
            candidate["expected_event_sha256"],
            "--expected-event-line-count",
            str(candidate["expected_event_sequence"]),
            "--to-worksite",
            after["path"],
            "--to-worksite-id",
            after["id"],
            "--to-role",
            after["role"],
            "--idempotency-key",
            candidate["idempotency_key"],
            "--fence-token",
            "sha256:" + candidate["plan_digest"],
            "--json",
        ]
        if apply:
            args.append("--apply")
            if authorization:
                args.extend(["--authorization-ref", str(self.authorization_path)])
        return args

    @property
    def receipt_path(self) -> Path:
        return (
            self.home
            / "aios"
            / "state"
            / "matters"
            / "change-sets"
            / f"matter-rollover__{MATTER_ID}__{self.target.name}.json"
        )

    def _apply(self, **overrides: Any) -> dict[str, Any]:
        return json.loads(self.run_cli(*self._args(apply=True, **overrides)).stdout)

    def test_success_completed_target_and_two_pass_publication(self) -> None:
        initial_view = json.loads(self.run_cli("matter", "view", "build", "--json").stdout)
        initial_view_inode = Path(initial_view["path"]).stat().st_ino
        report = self._apply()
        self.assertEqual(report["state"], "projections_committed")
        self.assertFalse(report["replayed"])
        current = json.loads(self.matter_path.read_text(encoding="utf-8"))
        self.assertEqual(current["worksite"]["path"], str(self.target.resolve()))
        self.assertEqual(current["worksite"]["role"], "current_canonical")
        events = [json.loads(line) for line in self.events_path.read_text().splitlines()]
        self.assertEqual(len(events), 2)
        self.assertEqual(events[-1]["type"], "worksite.migrated")
        receipt = json.loads(self.receipt_path.read_text())
        self.assertEqual(receipt["state"], "projections_committed")
        index_path = self.home / "aios" / "state" / "matters" / "index.json"
        rows = json.loads(index_path.read_text())["records"]
        formal = [row for row in rows if row["id"] == MATTER_ID]
        inferred = [
            row
            for row in rows
            if row["record_type"] == "inferred_worksite"
            and row["worksite_path"] == str(self.target.resolve())
        ]
        self.assertEqual(len(formal), 1)
        self.assertEqual(formal[0]["owner_worksite_path"], str(self.owner.resolve()))
        self.assertEqual(formal[0]["worksite_path"], str(self.target.resolve()))
        self.assertEqual(inferred, [])
        view = self.home / "aios" / "view" / "matters"
        self.assertNotEqual(view.stat().st_ino, initial_view_inode, "existing View must publish as a new exchanged generation")
        self.assertTrue((view / MATTER_ID / "index.html").is_file())
        self.assertFalse((view / f"worksite-{self.target.name}" / "index.html").exists())

    def test_default_dry_run_is_zero_write(self) -> None:
        before = {path.relative_to(self.home).as_posix(): path.read_bytes() for path in self.home.rglob("*") if path.is_file()}
        report = json.loads(self.run_cli(*self._args()).stdout)
        after = {path.relative_to(self.home).as_posix(): path.read_bytes() for path in self.home.rglob("*") if path.is_file()}
        self.assertEqual(report["mode"], "dry-run")
        self.assertFalse(report["would_write"])
        self.assertEqual(before, after)
        self.assertFalse((self.home / "aios" / "state").exists())
        self.assertFalse((self.home / "aios" / "view").exists())

    def test_stale_current_hash_and_event_count_fail_closed(self) -> None:
        cases = [
            {"current_id": "stale-id"},
            {"current_path": self.target},
            {"current_role": "active_canonical"},
            {"matter_sha": "0" * 64},
            {"events_sha": "1" * 64},
            {"event_count": 2},
        ]
        frozen_matter = self.matter_path.read_bytes()
        frozen_events = self.events_path.read_bytes()
        for overrides in cases:
            with self.subTest(overrides=overrides):
                cp = self.run_cli(*self._args(apply=True, **overrides), ok=False)
                self.assertEqual(json.loads(cp.stdout)["code"], "EXPECTED_CURRENT_MISMATCH")
                self.assertEqual(self.matter_path.read_bytes(), frozen_matter)
                self.assertEqual(self.events_path.read_bytes(), frozen_events)
                self.assertFalse(self.receipt_path.exists())

    def test_stale_fence_token_fails_closed(self) -> None:
        args = self._args(apply=True)
        args[args.index("--fence-token") + 1] = "sha256:" + "0" * 64
        cp = self.run_cli(*args, ok=False)
        self.assertEqual(json.loads(cp.stdout)["code"], "FENCE_TOKEN_MISMATCH")
        self.assertEqual(sha256(self.matter_path), self.pre_matter_sha)
        self.assertEqual(sha256(self.events_path), self.pre_events_sha)
        self.assertFalse(self.receipt_path.exists())

    def test_completed_target_rejects_lifecycle_coupled_role(self) -> None:
        cp = self.run_cli(*self._args(apply=True, to_role="active_canonical"), ok=False)
        self.assertEqual(cp.returncode, 2)
        self.assertIn("invalid choice", cp.stderr)
        self.assertEqual(sha256(self.matter_path), self.pre_matter_sha)

    def test_target_status_outside_active_or_completed_fails_closed(self) -> None:
        self._create_worksite(self.target, self.target.name, MATTER_ID, "paused")
        cp = self.run_cli(*self._args(apply=True), ok=False)
        self.assertEqual(cp.returncode, 2)
        report = json.loads(cp.stdout)
        self.assertEqual(report["code"], "TARGET_RECOVERY_INVALID")
        self.assertEqual(report["target_status"], "paused")
        self.assertEqual(sha256(self.matter_path), self.pre_matter_sha)
        self.assertEqual(sha256(self.events_path), self.pre_events_sha)
        self.assertFalse(self.receipt_path.exists())

    def test_apply_requires_authorization_before_lock_or_receipt(self) -> None:
        cp = self.run_cli(*self._args(apply=True, authorization=False), ok=False)
        self.assertEqual(json.loads(cp.stdout)["code"], "OWNER_AUTHORIZATION_MISSING")
        self.assertFalse(self.receipt_path.exists())
        self.assertFalse((self.home / "aios" / "state" / "matters" / "locks").exists())

    def test_nonexistent_authorization_ref_fails_before_lock_receipt_or_canonical_write(self) -> None:
        missing = self.home / "absent-authorization.json"
        args = self._args(apply=True)
        args[args.index("--authorization-ref") + 1] = str(missing)
        frozen_matter = self.matter_path.read_bytes()
        frozen_events = self.events_path.read_bytes()
        cp = self.run_cli(*args, ok=False)
        self.assertEqual(json.loads(cp.stdout)["code"], "AUTHORIZATION_REF_NOT_FOUND")
        self.assertEqual(self.matter_path.read_bytes(), frozen_matter)
        self.assertEqual(self.events_path.read_bytes(), frozen_events)
        self.assertFalse(self.receipt_path.exists())
        self.assertFalse((self.home / "aios" / "state" / "matters" / "locks").exists())

    def test_wrong_scope_authorization_ref_fails_before_lock_receipt_or_canonical_write(self) -> None:
        wrong = self.home / "wrong-scope-authorization.json"
        self._write_authorization(
            path=wrong,
            scope={
                "worksite": str(self.owner.resolve()),
                "parent_worksite": "/wrong/parent",
                "parent_matter": "matter_other",
            },
        )
        args = self._args(apply=True)
        args[args.index("--authorization-ref") + 1] = str(wrong)
        frozen_matter = self.matter_path.read_bytes()
        frozen_events = self.events_path.read_bytes()
        cp = self.run_cli(*args, ok=False)
        self.assertEqual(json.loads(cp.stdout)["code"], "AUTHORIZATION_SCOPE_MISMATCH")
        self.assertEqual(self.matter_path.read_bytes(), frozen_matter)
        self.assertEqual(self.events_path.read_bytes(), frozen_events)
        self.assertFalse(self.receipt_path.exists())
        self.assertFalse((self.home / "aios" / "state" / "matters" / "locks").exists())

    def test_lock_busy_has_zero_canonical_or_receipt_writes(self) -> None:
        lock_path = self.home / "aios" / "state" / "matters" / "locks" / f"{MATTER_ID}.lock"
        lock_path.parent.mkdir(parents=True)
        with lock_path.open("w") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            cp = self.run_cli(*self._args(apply=True), ok=False)
        self.assertEqual(json.loads(cp.stdout)["code"], "LOCK_BUSY")
        self.assertEqual(sha256(self.matter_path), self.pre_matter_sha)
        self.assertEqual(sha256(self.events_path), self.pre_events_sha)
        self.assertFalse(self.receipt_path.exists())

    def test_same_plan_replay_does_not_append_a_second_event(self) -> None:
        first = self._apply()
        matter_hash = sha256(self.matter_path)
        events_hash = sha256(self.events_path)
        index_hash = sha256(self.home / "aios" / "state" / "matters" / "index.json")
        second = self._apply()
        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])
        self.assertEqual(sha256(self.matter_path), matter_hash)
        self.assertEqual(sha256(self.events_path), events_hash)
        self.assertEqual(sha256(self.home / "aios" / "state" / "matters" / "index.json"), index_hash)
        self.assertEqual(len(self.events_path.read_text().splitlines()), 2)

    def test_same_key_different_plan_is_idempotency_conflict(self) -> None:
        self._apply()
        target2 = self.work / "20260803-100000_other-target"
        self._create_worksite(target2, target2.name, MATTER_ID, "completed")
        cp = self.run_cli(
            *self._args(apply=True, target=target2, target_id=target2.name, key=self.key), ok=False
        )
        self.assertEqual(json.loads(cp.stdout)["code"], "IDEMPOTENCY_CONFLICT")
        self.assertEqual(len(self.events_path.read_text().splitlines()), 2)

    def test_tampered_receipt_cannot_drive_recovery(self) -> None:
        cp = self.run_cli(
            *self._args(apply=True),
            ok=False,
            env={"AIOS_TEST_MATTER_ROLLOVER_CRASH_AFTER": "matter_committed"},
        )
        self.assertNotEqual(cp.returncode, 0)
        receipt = json.loads(self.receipt_path.read_text())
        receipt["events"]["post_sha256"] = "0" * 64
        self.receipt_path.write_bytes(json_bytes(receipt))
        retry = self.run_cli(*self._args(apply=True), ok=False)
        self.assertEqual(json.loads(retry.stdout)["code"], "RECEIPT_INTEGRITY_MISMATCH")
        self.assertEqual(len(self.events_path.read_text().splitlines()), 1)

    def test_tampered_receipt_state_cannot_short_circuit_replay(self) -> None:
        args = self._args(apply=True)
        crashed = self.run_cli(
            *args,
            ok=False,
            env={"AIOS_TEST_MATTER_ROLLOVER_CRASH_AFTER": "receipt_prepared"},
        )
        self.assertNotEqual(crashed.returncode, 0)
        receipt = json.loads(self.receipt_path.read_text())
        receipt["state"] = "projections_committed"
        self.receipt_path.write_bytes(json_bytes(receipt))
        retry = self.run_cli(*args, ok=False)
        self.assertEqual(json.loads(retry.stdout)["code"], "RECEIPT_INTEGRITY_MISMATCH")
        self.assertEqual(sha256(self.matter_path), self.pre_matter_sha)
        self.assertEqual(sha256(self.events_path), self.pre_events_sha)

    def test_recovers_snapshot_then_event_split_commit(self) -> None:
        cp = self.run_cli(
            *self._args(apply=True),
            ok=False,
            env={"AIOS_TEST_MATTER_ROLLOVER_CRASH_AFTER": "matter_committed"},
        )
        self.assertNotEqual(cp.returncode, 0)
        self.assertEqual(json.loads(self.receipt_path.read_text())["state"], "prepared")
        self.assertEqual(len(self.events_path.read_text().splitlines()), 1)
        report = self._apply()
        self.assertTrue(report["replayed"])
        self.assertEqual(report["state"], "projections_committed")
        self.assertEqual(len(self.events_path.read_text().splitlines()), 2)

    def test_recovers_event_then_receipt_crash_window(self) -> None:
        cp = self.run_cli(
            *self._args(apply=True),
            ok=False,
            env={"AIOS_TEST_MATTER_ROLLOVER_CRASH_AFTER": "event_committed"},
        )
        self.assertNotEqual(cp.returncode, 0)
        self.assertEqual(json.loads(self.receipt_path.read_text())["state"], "prepared")
        self.assertEqual(len(self.events_path.read_text().splitlines()), 2)
        report = self._apply()
        self.assertTrue(report["replayed"])
        self.assertEqual(report["state"], "projections_committed")
        self.assertEqual(len(self.events_path.read_text().splitlines()), 2)

    def test_projection_pending_retries_without_canonical_rollback(self) -> None:
        initial_view = json.loads(self.run_cli("matter", "view", "build", "--json").stdout)
        initial_view_index = Path(initial_view["path"]) / "index.html"
        initial_view_hash = sha256(initial_view_index)
        args = self._args(apply=True)
        cp = self.run_cli(
            *args,
            ok=False,
            env={"AIOS_TEST_MATTER_ROLLOVER_FAIL_PROJECTION": "1"},
        )
        failure = json.loads(cp.stdout)
        self.assertEqual(failure["code"], "PROJECTION_REBUILD_PENDING")
        pending = json.loads(self.receipt_path.read_text())
        self.assertEqual(pending["state"], "projection_pending")
        self.assertEqual(json.loads(self.matter_path.read_text())["worksite"]["path"], str(self.target.resolve()))
        self.assertEqual(len(self.events_path.read_text().splitlines()), 2)
        self.assertEqual(sha256(initial_view_index), initial_view_hash, "failed publication must retain the old complete View")
        recovery_path = self.target / "internal" / "recovery.json"
        recovery = json.loads(recovery_path.read_text())
        recovery["legitimate_projection_churn"] = True
        recovery_path.write_bytes(json_bytes(recovery))
        report = json.loads(self.run_cli(*args).stdout)
        self.assertTrue(report["replayed"])
        self.assertEqual(report["state"], "projections_committed")
        self.assertEqual(len(self.events_path.read_text().splitlines()), 2)

    def test_canonical_matter_cas_hook_preserves_concurrent_fact_and_fails_closed(self) -> None:
        cp = self.run_cli(
            *self._args(apply=True),
            ok=False,
            env={"AIOS_TEST_MATTER_ROLLOVER_CONCURRENT_UPDATE_BEFORE": "matter"},
        )
        self.assertEqual(json.loads(cp.stdout)["code"], "CANONICAL_CAS_MISMATCH")
        current = json.loads(self.matter_path.read_text())
        self.assertTrue(current["test_concurrent_update"])
        self.assertEqual(current["worksite"], self.current)
        self.assertEqual(len(self.events_path.read_text().splitlines()), 1)

    def test_canonical_event_cas_hook_preserves_concurrent_fact_and_fails_closed(self) -> None:
        cp = self.run_cli(
            *self._args(apply=True),
            ok=False,
            env={"AIOS_TEST_MATTER_ROLLOVER_CONCURRENT_UPDATE_BEFORE": "events"},
        )
        self.assertEqual(json.loads(cp.stdout)["code"], "CANONICAL_CAS_MISMATCH")
        events = [json.loads(line) for line in self.events_path.read_text().splitlines()]
        self.assertEqual(events[-1]["type"], "test.concurrent_update")
        self.assertNotIn("worksite.migrated", [event.get("type") for event in events])

    def test_guarded_rollback_appends_compensation_and_replays(self) -> None:
        applied = self._apply()
        rollback_args = [
            "matter",
            "rollover",
            MATTER_ID,
            "--rollback",
            applied["receipt_path"],
            "--expected-receipt-id",
            applied["receipt_id"],
            "--apply",
            "--authorization-ref",
            str(self.authorization_path),
            "--json",
        ]
        rolled = json.loads(self.run_cli(*rollback_args).stdout)
        self.assertEqual(rolled["state"], "rolled_back")
        self.assertEqual(json.loads(self.matter_path.read_text())["worksite"], self.current)
        events = [json.loads(line) for line in self.events_path.read_text().splitlines()]
        self.assertEqual(len(events), 3)
        self.assertEqual(events[-1]["type"], "worksite.migration_compensated")
        replay = json.loads(self.run_cli(*rollback_args).stdout)
        self.assertTrue(replay["replayed"])
        self.assertEqual(len(self.events_path.read_text().splitlines()), 3)

    def test_rollback_missing_authorization_fails_before_receipt_or_canonical_write(self) -> None:
        applied = self._apply()
        missing = self.home / "absent-rollback-authorization.json"
        frozen_receipt = self.receipt_path.read_bytes()
        frozen_matter = self.matter_path.read_bytes()
        frozen_events = self.events_path.read_bytes()
        cp = self.run_cli(
            "matter",
            "rollover",
            MATTER_ID,
            "--rollback",
            applied["receipt_path"],
            "--expected-receipt-id",
            applied["receipt_id"],
            "--apply",
            "--authorization-ref",
            str(missing),
            "--json",
            ok=False,
        )
        self.assertEqual(json.loads(cp.stdout)["code"], "AUTHORIZATION_REF_NOT_FOUND")
        self.assertEqual(self.receipt_path.read_bytes(), frozen_receipt)
        self.assertEqual(self.matter_path.read_bytes(), frozen_matter)
        self.assertEqual(self.events_path.read_bytes(), frozen_events)

    def test_rollback_wrong_scope_authorization_fails_before_receipt_or_canonical_write(self) -> None:
        applied = self._apply()
        wrong = self.home / "wrong-scope-rollback-authorization.json"
        self._write_authorization(
            path=wrong,
            scope={
                "worksite": str(self.target.resolve()),
                "parent_worksite": str(self.owner.resolve()),
                "parent_matter": "matter_other",
            },
        )
        frozen_receipt = self.receipt_path.read_bytes()
        frozen_matter = self.matter_path.read_bytes()
        frozen_events = self.events_path.read_bytes()
        cp = self.run_cli(
            "matter",
            "rollover",
            MATTER_ID,
            "--rollback",
            applied["receipt_path"],
            "--expected-receipt-id",
            applied["receipt_id"],
            "--apply",
            "--authorization-ref",
            str(wrong),
            "--json",
            ok=False,
        )
        self.assertEqual(json.loads(cp.stdout)["code"], "AUTHORIZATION_SCOPE_MISMATCH")
        self.assertEqual(self.receipt_path.read_bytes(), frozen_receipt)
        self.assertEqual(self.matter_path.read_bytes(), frozen_matter)
        self.assertEqual(self.events_path.read_bytes(), frozen_events)

    def test_rollback_recovers_after_projection_receipt_crash_window(self) -> None:
        applied = self._apply()
        rollback_args = [
            "matter",
            "rollover",
            MATTER_ID,
            "--rollback",
            applied["receipt_path"],
            "--expected-receipt-id",
            applied["receipt_id"],
            "--apply",
            "--authorization-ref",
            str(self.authorization_path),
            "--json",
        ]
        cp = self.run_cli(
            *rollback_args,
            ok=False,
            env={"AIOS_TEST_MATTER_ROLLOVER_CRASH_AFTER": "rollback_projections_committed"},
        )
        self.assertNotEqual(cp.returncode, 0)
        receipt = json.loads(self.receipt_path.read_text())
        self.assertEqual(receipt["state"], "projections_committed")
        self.assertIn("rollback", receipt)
        self.assertEqual(json.loads(self.matter_path.read_text())["worksite"], self.current)
        self.assertEqual(len(self.events_path.read_text().splitlines()), 3)
        recovered = json.loads(self.run_cli(*rollback_args).stdout)
        self.assertEqual(recovered["state"], "rolled_back")
        self.assertEqual(len(self.events_path.read_text().splitlines()), 3)

    def test_rollback_rejects_a_later_domain_fact(self) -> None:
        applied = self._apply()
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"schema": "aios.workflow.event.v0", "event_id": "evt_later", "type": "fact.added"}) + "\n")
        cp = self.run_cli(
            "matter",
            "rollover",
            MATTER_ID,
            "--rollback",
            applied["receipt_path"],
            "--expected-receipt-id",
            applied["receipt_id"],
            "--apply",
            "--authorization-ref",
            str(self.authorization_path),
            "--json",
            ok=False,
        )
        self.assertEqual(json.loads(cp.stdout)["code"], "ROLLBACK_GUARD_MISMATCH")
        self.assertEqual(json.loads(self.matter_path.read_text())["worksite"]["path"], str(self.target.resolve()))
        self.assertEqual(len(self.events_path.read_text().splitlines()), 3)

    def test_duplicate_formal_target_claim_fails_closed(self) -> None:
        other = self.work / "20260804-100000_other-matter"
        self._create_worksite(other, other.name, "matter_other", "completed")
        other_matter = {
            "schema": "aios.workflow.state.v0",
            "id": "matter_other",
            "title": "Other",
            "lifecycle": {"state": "active"},
            "worksite": {
                "id": self.target.name,
                "path": str(self.target.resolve()),
                "role": "latest_completed_baseline",
                "recovery_path": "internal/recovery.json",
                "binding": "owned",
                "owner_matter_id": "matter_other",
            },
        }
        (other / "internal" / "matter.json").write_bytes(json_bytes(other_matter))
        cp = self.run_cli(*self._args(apply=True), ok=False)
        self.assertEqual(json.loads(cp.stdout)["code"], "TARGET_ALREADY_CLAIMED")
        self.assertFalse(self.receipt_path.exists())

    def test_formal_matter_sources_skip_top_level_symlink_escape(self) -> None:
        outside = self.home / "outside-owner"
        (outside / "internal").mkdir(parents=True)
        (outside / "internal" / "matter.json").write_bytes(
            json_bytes({"schema": "aios.workflow.state.v0", "id": "matter_outside_symlink"})
        )
        escaped = self.work / "escaped-owner"
        escaped.symlink_to(outside, target_is_directory=True)
        module = runpy.run_path(str(CLI), run_name="aios_rollover_test_module")
        found = module["formal_matter_sources"](self.home)
        self.assertNotIn("matter_outside_symlink", [value.get("id") for _path, value in found])


if __name__ == "__main__":
    unittest.main()
