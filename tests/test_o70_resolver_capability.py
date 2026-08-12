#!/usr/bin/env python3
"""O70 RED/GREEN tests for ResourceRef, Capability, and Decision routes."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "aios.py"


class O70RouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="aios-o70-route-")
        self.home = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_cli(self, *args: str, ok: bool = True) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
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
        self.assertNotIn("Traceback", result.stderr)
        return result, json.loads(result.stdout)

    def write_registry(self, kind: str, records: list[dict[str, Any]], aliases: dict[str, str] | None = None) -> None:
        root = self.home / "aios" / "vault" / "ops" / kind
        root.mkdir(parents=True, exist_ok=True)
        (root / "registry.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in records),
            encoding="utf-8",
        )
        alias_lines = ["aliases:"] + [f"  {key}: {value}" for key, value in sorted((aliases or {}).items())]
        (root / "aliases.yaml").write_text("\n".join(alias_lines) + "\n", encoding="utf-8")

    @staticmethod
    def project(project_id: str, name: str, *, profile: str = "default", status: str = "active", aliases: list[str] | None = None, capabilities: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        return {
            "id": project_id,
            "kind": "project",
            "name": name,
            "aliases": aliases or [],
            "profile": profile,
            "status": status,
            "version": "fixture-v1",
            "locations": [{"kind": "local", "path": f"~/projects/{project_id}"}],
            "role_in_aios": "fixture",
            "capabilities": capabilities or [],
        }

    @staticmethod
    def source(source_id: str, name: str, *, profile: str = "default", status: str = "active") -> dict[str, Any]:
        return {
            "id": source_id,
            "kind": "data_root",
            "name": name,
            "aliases": [],
            "profile": profile,
            "status": status,
            "version": "fixture-v1",
            "locations": [{"kind": "local", "path": f"~/{source_id}"}],
            "authority": "source_registry",
            "owner_ref": f"source-owner:{source_id}",
            "access_mode": "read_only_reference",
            "sync_mode": "none",
            "backup_status": "unknown",
            "sensitivity": "private",
        }

    def test_resource_resolves_exact_id_alias_and_name_to_stable_ref(self) -> None:
        self.write_registry(
            "projects",
            [self.project("alpha", "Alpha Project", aliases=["inline-alpha"])],
            aliases={"kit": "alpha"},
        )
        for query, matched_by in (("alpha", "id"), ("kit", "alias"), ("Alpha Project", "name")):
            with self.subTest(query=query):
                _, receipt = self.run_cli("resource", "resolve", query, "--json")
                self.assertEqual(receipt["verdict"], "RESOLVED")
                self.assertIsNone(receipt["failure_class"])
                ref = receipt["resource_ref"]
                self.assertEqual(ref["schema"], "aios.resource-ref.v1")
                self.assertEqual(ref["canonical_id"], "project:default:alpha")
                self.assertEqual(ref["matched_by"], matched_by)
                self.assertEqual(ref["status"], "active")
                self.assertEqual(ref["version"], "fixture-v1")
                self.assertRegex(ref["record_sha256"], r"^[0-9a-f]{64}$")
                self.assertRegex(ref["source_ref"]["sha256"], r"^[0-9a-f]{64}$")
                self.assertEqual(ref["path"], str(self.home / "projects" / "alpha"))
                self.assertEqual(ref["owner_ref"], "project:alpha")

    def test_resource_duplicate_ambiguous_missing_stale_and_cross_profile_fail_closed(self) -> None:
        cases = [
            (
                [self.project("dup", "One"), self.project("dup", "Two")],
                ("dup",),
                "DUPLICATE_RESOURCE_ID",
            ),
            (
                [self.project("one", "Shared"), self.project("two", "Shared")],
                ("Shared",),
                "AMBIGUOUS_RESOURCE",
            ),
            (
                [self.project("old", "Old", status="archived")],
                ("old",),
                "STALE_RESOURCE",
            ),
            (
                [self.project("personal", "Shared", profile="personal"), self.project("work", "Shared", profile="work")],
                ("Shared",),
                "CROSS_PROFILE_AMBIGUOUS",
            ),
        ]
        for records, argv, failure_class in cases:
            with self.subTest(failure_class=failure_class):
                self.write_registry("projects", records)
                _, receipt = self.run_cli("resource", "resolve", *argv, "--json", ok=False)
                self.assertEqual(receipt["verdict"], "BLOCKED")
                self.assertEqual(receipt["failure_class"], failure_class)

        self.write_registry("projects", [self.project("work", "Shared", profile="work")])
        _, selected = self.run_cli("resource", "resolve", "Shared", "--profile", "work", "--json")
        self.assertEqual(selected["resource_ref"]["canonical_id"], "project:work:work")
        _, mismatch = self.run_cli("resource", "resolve", "Shared", "--profile", "personal", "--json", ok=False)
        self.assertEqual(mismatch["failure_class"], "CROSS_PROFILE_MISMATCH")
        _, missing = self.run_cli("resource", "resolve", "absent", "--json", ok=False)
        self.assertEqual(missing["failure_class"], "MISSING_RESOURCE")

    def capability_fixture(self, *, health: str = "healthy", maturity: str = "verified", adapter_query: str = "adapter-kit") -> None:
        capability = {
            "id": "document.publish",
            "name": "Publish Document",
            "aliases": ["publish-docs"],
            "profile": "default",
            "status": "active",
            "health": "healthy",
            "maturity": "verified",
            "adapter": {"id": "adapter.document.local", "resource_query": adapter_query},
            "bindings": [
                {
                    "id": "primary",
                    "name": "Primary",
                    "aliases": ["default"],
                    "profile": "default",
                    "status": "active",
                    "health": health,
                    "maturity": maturity,
                    "resource_query": "notes",
                    "resource_kind": "source",
                }
            ],
            "authorization_ref": "external-owner:document-publish",
        }
        self.write_registry(
            "projects",
            [
                self.project("capability-owner", "Capability Owner", capabilities=[capability]),
                self.project("adapter-kit", "Adapter Kit"),
            ],
        )
        self.write_registry("sources", [self.source("notes", "Notes")])

    def test_capability_discovery_and_resolution_are_lazy_and_provider_neutral(self) -> None:
        self.capability_fixture(adapter_query="missing-adapter")
        _, discovered = self.run_cli("capability", "discover", "--json")
        self.assertEqual(discovered["verdict"], "DISCOVERED")
        self.assertEqual(discovered["capabilities"][0]["adapter"]["load_state"], "deferred")
        self.assertNotIn("resource_ref", discovered["capabilities"][0]["adapter"])

        _, resolved = self.run_cli("capability", "resolve", "publish-docs", "--json")
        self.assertEqual(resolved["verdict"], "RESOLVED")
        self.assertEqual(resolved["target_resource_ref"]["canonical_id"], "source:default:notes")
        self.assertEqual(resolved["adapter"]["load_state"], "deferred")
        self.assertEqual(resolved["authorization"], {"implemented": False, "ref": "external-owner:document-publish", "state": "NOT_EVALUATED"})
        self.assertNotIn("provider", resolved)

        _, blocked = self.run_cli(
            "capability", "resolve", "document.publish", "--load-adapter", "--json", ok=False
        )
        self.assertEqual(blocked["failure_class"], "MISSING_ADAPTER_RESOURCE")

    def test_capability_loads_adapter_ref_only_on_demand(self) -> None:
        self.capability_fixture()
        _, receipt = self.run_cli(
            "capability", "resolve", "document.publish", "--binding", "default", "--load-adapter", "--json"
        )
        self.assertEqual(receipt["adapter"]["load_state"], "ready")
        self.assertEqual(receipt["adapter"]["resource_ref"]["canonical_id"], "project:default:adapter-kit")

    def test_capability_unhealthy_immature_ambiguous_and_missing_fail_closed(self) -> None:
        for health, maturity, failure_class in (
            ("unhealthy", "verified", "UNHEALTHY_BINDING"),
            ("healthy", "configured", "IMMATURE_BINDING"),
        ):
            with self.subTest(failure_class=failure_class):
                self.capability_fixture(health=health, maturity=maturity)
                _, receipt = self.run_cli("capability", "resolve", "document.publish", "--json", ok=False)
                self.assertEqual(receipt["failure_class"], failure_class)

        duplicate = {
            "id": "document.publish",
            "name": "Other Publisher",
            "aliases": [],
            "status": "active",
            "health": "healthy",
            "maturity": "verified",
            "adapter": {"id": "other.adapter"},
            "bindings": [],
        }
        self.capability_fixture()
        projects_path = self.home / "aios" / "vault" / "ops" / "projects" / "registry.jsonl"
        with projects_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(self.project("other-owner", "Other", capabilities=[duplicate])) + "\n")
        _, ambiguous = self.run_cli("capability", "resolve", "document.publish", "--json", ok=False)
        self.assertEqual(ambiguous["failure_class"], "AMBIGUOUS_CAPABILITY")
        _, missing = self.run_cli("capability", "resolve", "missing", "--json", ok=False)
        self.assertEqual(missing["failure_class"], "MISSING_CAPABILITY")

    def write_decision_fixture(self, question_count: int = 3) -> tuple[Path, Path, dict[str, Any]]:
        fixture = self.home / "decision-fixture"
        fixture.mkdir(parents=True, exist_ok=True)
        policy = fixture / "policy.md"
        policy.write_text(
            "---\nschema: workflow.local-policy.v1\n---\n\n"
            "# Policy\n\n<a id=\"policy-decision-surface\"></a>\n",
            encoding="utf-8",
        )
        policy_sha = hashlib.sha256(policy.read_bytes()).hexdigest()

        def option(question_id: str, suffix: str) -> dict[str, Any]:
            return {
                "id": f"{question_id}-{suffix}",
                "label": suffix.upper(),
                "description": "A shaped option",
                "advantages": [],
                "costs": [],
                "risks": [],
                "reversibility": "reversible",
                "future_bias": "neutral",
                "viable": True,
            }

        questions = []
        for number in range(1, question_count + 1):
            qid = f"q{number}"
            options = [option(qid, "a"), option(qid, "b")]
            if number == 3:
                hybrid = option(qid, "h")
                hybrid.update({"kind": "hybrid", "combines": [f"{qid}-a", f"{qid}-b"]})
                options.append(hybrid)
            questions.append(
                {
                    "id": qid,
                    "axis": f"axis-{number}",
                    "plain_language_question": f"Question {number}?",
                    "why_human_owned": "Long-term choice",
                    "depends_on": [],
                    "batch_id": "batch-1",
                    "options": options,
                    "recommendation": {"option_id": f"{qid}-a", "assumptions": []},
                    "authorization_effect": "records choice only",
                }
            )
        packet_data = {
            "schema": "aios.decision-packet.v1",
            "packet_id": "packet-1",
            "matter_ref": "matter:fixture",
            "mission_sha256": "a" * 64,
            "policy_refs": [
                {
                    "id": "decision-surface",
                    "route_id": "aios.decision-surface.route.v1",
                    "source_sha256": policy_sha,
                }
            ],
            "questions": questions,
            "dependency_batches": [
                {"id": "batch-1", "question_ids": [f"q{i}" for i in range(1, question_count + 1)]}
            ],
            "created_by": "fixture-producer",
        }
        packet = fixture / "packet.json"
        packet.write_text(json.dumps(packet_data, indent=2) + "\n", encoding="utf-8")
        return packet, policy, packet_data

    def decision_check(self, packet: Path, policy: Path, *extra: str, ok: bool = True) -> dict[str, Any]:
        _, receipt = self.run_cli(
            "decision", "check",
            "--packet", str(packet),
            "--policy-source", str(policy),
            "--policy-fragment", "#policy-decision-surface",
            "--policy-id", "decision-surface",
            "--route-id", "aios.decision-surface.route.v1",
            "--route-depth", "1",
            "--visited", "agent-workflow-cost-control",
            *extra,
            "--json",
            ok=ok,
        )
        return receipt

    def test_decision_packet_shape_passes_for_one_two_and_five_questions(self) -> None:
        for count in (1, 2, 5):
            with self.subTest(count=count):
                packet, policy, _ = self.write_decision_fixture(count)
                receipt = self.decision_check(packet, policy)
                self.assertEqual(receipt["verdict"], "PASS_SHAPE")
                self.assertIsNone(receipt["failure_class"])
                self.assertEqual(receipt["route"]["visited_ids"], ["agent-workflow-cost-control", "decision-surface"])
                self.assertEqual(receipt["packet"]["question_count"], count)

    def test_decision_zero_and_six_questions_fail_closed(self) -> None:
        for count in (0, 6):
            with self.subTest(count=count):
                packet, policy, _ = self.write_decision_fixture(count)
                receipt = self.decision_check(packet, policy, ok=False)
                self.assertEqual(receipt["verdict"], "FAIL_SHAPE")
                self.assertEqual(receipt["failure_class"], "MALFORMED_PACKET")

    def test_decision_route_depth_cycle_stale_and_missing_source_fail_closed(self) -> None:
        packet, policy, _ = self.write_decision_fixture()
        deep = self.decision_check(packet, policy, "--route-depth", "3", ok=False)
        self.assertEqual(deep["failure_class"], "DEPTH_EXCEEDED")
        cycle = self.decision_check(packet, policy, "--visited", "decision-surface", ok=False)
        self.assertEqual(cycle["failure_class"], "CYCLE_DETECTED")

        policy.write_text(policy.read_text(encoding="utf-8") + "drift\n", encoding="utf-8")
        stale = self.decision_check(packet, policy, ok=False)
        self.assertEqual(stale["verdict"], "STALE_REF")
        self.assertEqual(stale["failure_class"], "SOURCE_HASH_MISMATCH")

        packet, policy, _ = self.write_decision_fixture()
        policy.unlink()
        missing = self.decision_check(packet, policy, ok=False)
        self.assertEqual(missing["verdict"], "BLOCKED_MISSING_REF")
        self.assertEqual(missing["failure_class"], "MISSING_POLICY_SOURCE")

    def test_decision_missing_ref_fragment_dependency_and_cycle_fail_closed(self) -> None:
        packet, policy, packet_data = self.write_decision_fixture()
        packet_data["policy_refs"][0]["id"] = "other-policy"
        packet.write_text(json.dumps(packet_data, indent=2) + "\n", encoding="utf-8")
        missing_ref = self.decision_check(packet, policy, ok=False)
        self.assertEqual(missing_ref["verdict"], "BLOCKED_MISSING_REF")
        self.assertEqual(missing_ref["failure_class"], "MISSING_POLICY_REF")

        packet, policy, packet_data = self.write_decision_fixture()
        policy.write_text("---\nschema: workflow.local-policy.v1\n---\n# Wrong fragment\n", encoding="utf-8")
        packet_data["policy_refs"][0]["source_sha256"] = hashlib.sha256(policy.read_bytes()).hexdigest()
        packet.write_text(json.dumps(packet_data, indent=2) + "\n", encoding="utf-8")
        missing_fragment = self.decision_check(packet, policy, ok=False)
        self.assertEqual(missing_fragment["verdict"], "BLOCKED_MISSING_REF")
        self.assertEqual(missing_fragment["failure_class"], "MISSING_POLICY_FRAGMENT")

        packet, policy, packet_data = self.write_decision_fixture(2)
        packet_data["questions"][0]["depends_on"] = ["q2"]
        packet_data["questions"][1]["depends_on"] = ["q1"]
        packet.write_text(json.dumps(packet_data, indent=2) + "\n", encoding="utf-8")
        dep_cycle = self.decision_check(packet, policy, ok=False)
        self.assertEqual(dep_cycle["failure_class"], "DEPENDENCY_CYCLE")

        packet, policy, packet_data = self.write_decision_fixture(1)
        packet_data["questions"][0]["depends_on"] = ["missing"]
        packet.write_text(json.dumps(packet_data, indent=2) + "\n", encoding="utf-8")
        missing_dependency = self.decision_check(packet, policy, ok=False)
        self.assertEqual(missing_dependency["verdict"], "BLOCKED_MISSING_REF")
        self.assertEqual(missing_dependency["failure_class"], "MISSING_DEPENDENCY")

if __name__ == "__main__":
    unittest.main()
