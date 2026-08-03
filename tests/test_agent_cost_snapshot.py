from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "agent_cost_snapshot.py"
AS_OF = "2026-08-03T00:00:00Z"
AS_OF_SECONDS = 1_785_715_200


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AgentCostSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="aios-cost-snapshot-test-")
        self.root = Path(self.tmp.name)
        self.hermes_db = self.root / "hermes.db"
        self.studio_db = self.root / "studio.db"
        self._create_hermes_fixture()
        self._create_studio_fixture()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_hermes_fixture(self) -> None:
        con = sqlite3.connect(self.hermes_db)
        con.executescript(
            """
            CREATE TABLE sessions (
              id TEXT PRIMARY KEY, source TEXT, parent_session_id TEXT, started_at REAL,
              api_call_count INTEGER, input_tokens INTEGER, output_tokens INTEGER,
              cache_read_tokens INTEGER, cache_write_tokens INTEGER, reasoning_tokens INTEGER
            );
            CREATE TABLE session_model_usage (
              session_id TEXT, model TEXT, task TEXT, api_call_count INTEGER,
              input_tokens INTEGER, output_tokens INTEGER, cache_read_tokens INTEGER,
              cache_write_tokens INTEGER, reasoning_tokens INTEGER
            );
            CREATE TABLE messages (
              id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT,
              timestamp REAL, active INTEGER
            );
            """
        )
        started = AS_OF_SECONDS - 3600
        con.executemany(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                ("root-a", "cli", None, started, 2, 100, 20, 1000, 0, 5),
                ("child-review", "subagent", "root-a", started + 1, 1, 50, 10, 500, 0, 2),
                ("root-b", "cli", None, started + 2, 1, 50, 20, 0, 5, 1),
            ],
        )
        con.executemany(
            "INSERT INTO session_model_usage VALUES (?,?,?,?,?,?,?,?,?)",
            [
                ("root-a", "fixture-model", "main", 1, 80, 15, 800, 0, 4),
                ("child-review", "fixture-model", "main", 1, 50, 10, 500, 0, 2),
            ],
        )
        con.executemany(
            "INSERT INTO messages VALUES (?,?,?,?,?,?)",
            [
                (1, "root-a", "user", "ordinary request", started, 1),
                (2, "child-review", "user", "Please audit this; PRIVATE_FIXTURE_VALUE", started + 1, 1),
                (3, "root-b", "user", "ordinary request", started + 2, 1),
            ],
        )
        con.commit()
        con.close()

    def _create_studio_fixture(self) -> None:
        con = sqlite3.connect(self.studio_db)
        con.executescript(
            """
            CREATE TABLE session_usage (
              id INTEGER PRIMARY KEY, session_id TEXT, created_at INTEGER, usage_scope TEXT,
              api_calls INTEGER, input_tokens INTEGER, output_tokens INTEGER,
              cache_read_tokens INTEGER, cache_write_tokens INTEGER, reasoning_tokens INTEGER
            );
            CREATE TABLE messages (
              id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT,
              tool_name TEXT, timestamp INTEGER
            );
            """
        )
        created = AS_OF_SECONDS * 1000 - 1000
        con.executemany(
            "INSERT INTO session_usage VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                (1, "root-a", created, "model_call", 1, 100, 10, 900, 0, 2),
                (2, "root-a", created + 1, "model_call", 1, 20, 5, 100, 0, 1),
                (3, "root-b", created + 2, "model_call", 1, 300000, 10, 0, 0, 2),
            ],
        )
        con.executemany(
            "INSERT INTO messages VALUES (?,?,?,?,?,?)",
            [
                (1, "root-a", "tool", "x" * 10 + "PRIVATE_FIXTURE_VALUE", "session_search", created),
                (2, "root-a", "tool", "y" * 100, "session_search", created + 1),
                (3, "root-a", "tool", "z" * 20, "read_file", created + 2),
                (4, "root-b", "tool", "q" * 999, "other_tool", created + 3),
            ],
        )
        con.commit()
        con.close()

    def run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.pop("PYTHONPYCACHEPREFIX", None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        cp = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            env=env,
        )
        if cp.returncode:
            self.fail(f"command failed {args}:\nstdout={cp.stdout}\nstderr={cp.stderr}")
        return cp

    def snapshot_args(self) -> tuple[str, ...]:
        return (
            "snapshot",
            "--hermes-db", str(self.hermes_db),
            "--studio-db", str(self.studio_db),
            "--as-of", AS_OF,
            "--window-days", "30",
        )

    def test_snapshot_reconciles_four_buckets_and_emits_five_signals(self) -> None:
        before = {self.hermes_db: digest(self.hermes_db), self.studio_db: digest(self.studio_db)}
        cp = self.run_script(*self.snapshot_args())
        after = {self.hermes_db: digest(self.hermes_db), self.studio_db: digest(self.studio_db)}
        self.assertEqual(before, after, "source ledgers must remain byte-identical")
        self.assertEqual(cp.stdout.count("\n"), 1)
        self.assertNotIn(": ", cp.stdout)
        self.assertNotIn("PRIVATE_FIXTURE_VALUE", cp.stdout)

        payload = json.loads(cp.stdout)
        self.assertEqual(payload["schema"], "aios.agent-cost.snapshot.v1")
        self.assertIs(payload["ok"], True)
        self.assertEqual(payload["metadata"]["payload_tokenizer"]["id"], "utf8-bytes-v1")
        self.assertEqual(payload["metadata"]["thresholds"]["long_context_prompt_tokens"], 272000)
        self.assertIn("narrow", payload["metadata"]["review_regex"])

        reconcile = payload["reconciliation"]
        self.assertEqual(
            reconcile["billable_buckets"],
            {
                "cache_read_tokens": 1500,
                "cache_write_tokens": 5,
                "input_tokens": 200,
                "output_tokens": 50,
            },
        )
        self.assertEqual(reconcile["billable_token_volume"], 1755)
        self.assertIs(reconcile["four_bucket_sum_matches"], True)
        self.assertIs(reconcile["reasoning_counted_as_extra_billable"], False)

        signals = payload["signals"]
        self.assertEqual(set(signals), {
            "root_calls_cache_replay",
            "subagent_billable_share",
            "review_like_billable_share",
            "tool_result_tail",
            "startup_and_long_context",
        })
        self.assertEqual(signals["root_calls_cache_replay"]["roots"], 2)
        self.assertEqual(signals["root_calls_cache_replay"]["api_calls"]["total"], 4)
        self.assertEqual(signals["root_calls_cache_replay"]["cache_read_tokens"]["total"], 1500)
        self.assertAlmostEqual(signals["subagent_billable_share"]["share_pct"], 31.908832, places=6)
        self.assertIs(signals["subagent_billable_share"]["over_threshold"], True)
        self.assertEqual(signals["review_like_billable_share"]["narrow"]["sessions"], 1)
        self.assertEqual(signals["tool_result_tail"]["all_tools"]["max"], 999)
        self.assertEqual(signals["tool_result_tail"]["focus_tools"]["session_search"]["max"], 100)
        self.assertEqual(signals["startup_and_long_context"]["model_calls"], 3)
        self.assertEqual(signals["startup_and_long_context"]["first_call_prompt_tokens"]["p50"], 1000)
        self.assertAlmostEqual(signals["startup_and_long_context"]["long_context_share_pct"], 33.333333, places=6)
        self.assertIs(payload["privacy"]["message_or_tool_bodies_emitted"], False)
        self.assertIs(payload["privacy"]["review_classification_reads_first_user_text_in_memory"], True)
        self.assertIs(payload["privacy"]["secret_values_emitted"], False)
        self.assertIs(payload["privacy"]["tool_payload_bodies_selected"], False)
        self.assertIs(payload["sources"]["studio_usage_added_to_canonical_ledger"], False)

    def test_file_output_and_delta_are_compact_and_comparability_checked(self) -> None:
        before_path = self.root / "before.json"
        receipt = json.loads(self.run_script(*self.snapshot_args(), "--output", str(before_path)).stdout)
        self.assertEqual(receipt["schema"], "aios.agent-cost.file-receipt.v1")
        self.assertEqual(receipt["document_schema"], "aios.agent-cost.snapshot.v1")
        self.assertTrue(before_path.exists())

        delta = json.loads(self.run_script("delta", str(before_path), str(before_path)).stdout)
        self.assertEqual(delta["schema"], "aios.agent-cost.delta.v1")
        self.assertIs(delta["comparability"]["comparable"], True)
        self.assertTrue(all(value == 0 for value in delta["delta"].values()))
        self.assertNotIn("PRIVATE_FIXTURE_VALUE", json.dumps(delta))


if __name__ == "__main__":
    unittest.main()
