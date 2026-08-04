#!/usr/bin/env python3
"""Focused tests for generated-document translation mechanics."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("translate_docs", ROOT / "scripts" / "translate_docs.py")
assert SPEC and SPEC.loader
TRANSLATE_DOCS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRANSLATE_DOCS)


class TranslateDocsLinkTests(unittest.TestCase):
    def test_translatable_doc_link_targets_generated_counterpart(self) -> None:
        source = ROOT / "docs" / "architecture.md"
        target = ROOT / "translations" / "en" / "docs" / "architecture.md"
        rewritten = TRANSLATE_DOCS.rewrite_markdown_links(
            "See [protocol](./upstream-reconciliation.md#scope).",
            source,
            target,
            "en",
        )
        self.assertEqual(rewritten, "See [protocol](upstream-reconciliation.md#scope).")

    def test_nontranslated_repo_markdown_link_targets_canonical_source(self) -> None:
        source = ROOT / "docs" / "upstream-reconciliation.md"
        target = ROOT / "translations" / "en" / "docs" / "upstream-reconciliation.md"
        rewritten = TRANSLATE_DOCS.rewrite_markdown_links(
            "Use [template](../templates/upstream-reconciliation/UPSTREAM.md#gate).",
            source,
            target,
            "en",
        )
        self.assertEqual(
            rewritten,
            "Use [template](../../../templates/upstream-reconciliation/UPSTREAM.md#gate).",
        )

    def test_external_missing_and_outside_links_are_unchanged(self) -> None:
        source = ROOT / "docs" / "architecture.md"
        target = ROOT / "translations" / "en" / "docs" / "architecture.md"
        text = (
            "[external](https://example.com/doc.md) "
            "[missing](./not-created.md) "
            "[escape](../../../../outside.md) "
            "[absolute](/tmp/outside.md)"
        )
        self.assertEqual(
            TRANSLATE_DOCS.rewrite_markdown_links(text, source, target, "en"),
            text,
        )


class TranslateDocsFreshnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "README.md"
        self.source.write_bytes(b"# Canonical source\n")
        self.target = self.root / "translations" / "en" / "README.md"
        self.patches = [
            mock.patch.object(TRANSLATE_DOCS, "ROOT", self.root),
            mock.patch.object(TRANSLATE_DOCS, "SOURCE_FILES", [Path("README.md")]),
            mock.patch.object(TRANSLATE_DOCS, "SOURCE_GLOBS", []),
        ]
        for patcher in self.patches:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patches):
            patcher.stop()
        self.temp_dir.cleanup()

    def write_generated(self, source: Path | None = None, *, status: str = "generated") -> Path:
        source = source or self.source
        target = TRANSLATE_DOCS.target_path(source, "en")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            TRANSLATE_DOCS.generated_header(
                source,
                target,
                "en",
                "English",
                status=status,
            )
            + "# Translated body\n",
            encoding="utf-8",
        )
        return target

    def test_fresh_generated_target_passes(self) -> None:
        self.write_generated()
        fresh, detail = TRANSLATE_DOCS.check_translation_target(self.source, self.target)
        self.assertTrue(fresh, detail)
        self.assertIn("fresh", detail)

    def test_source_change_makes_generated_target_stale(self) -> None:
        self.write_generated()
        self.source.write_bytes(b"# Changed canonical source\n")
        fresh, detail = TRANSLATE_DOCS.check_translation_target(self.source, self.target)
        self.assertFalse(fresh)
        self.assertIn("stale", detail)

    def test_missing_target_fails(self) -> None:
        fresh, detail = TRANSLATE_DOCS.check_translation_target(self.source, self.target)
        self.assertFalse(fresh)
        self.assertIn("missing", detail)

    def test_malformed_metadata_fails(self) -> None:
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text(
            TRANSLATE_DOCS.GENERATED_MARKER
            + "\n<!-- AIOS-TRANSLATION-METADATA not-json -->\n\n"
            + TRANSLATE_DOCS.GENERATED_NOTICE
            + "\n\n# Body\n",
            encoding="utf-8",
        )
        fresh, detail = TRANSLATE_DOCS.check_translation_target(self.source, self.target)
        self.assertFalse(fresh)
        self.assertIn("malformed", detail)

    def test_stale_legacy_target_fails_without_unproven_sha(self) -> None:
        self.write_generated(status="stale-legacy")
        target_text = self.target.read_text(encoding="utf-8")
        self.assertNotIn("source_sha256", target_text.splitlines()[1])
        fresh, detail = TRANSLATE_DOCS.check_translation_target(self.source, self.target)
        self.assertFalse(fresh)
        self.assertIn("stale-legacy", detail)

    def test_owner_script_marks_legacy_header_without_changing_body_bytes(self) -> None:
        body = b"# Existing translation\n\nBody bytes stay exact.\n"
        old_header = (
            TRANSLATE_DOCS.GENERATED_MARKER
            + "\n\n[简体中文](../../README.md) | **English**\n\n> "
            + TRANSLATE_DOCS.GENERATED_NOTICE
            + "\n\n"
        ).encode("utf-8")
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_bytes(old_header + body)
        changed = TRANSLATE_DOCS.mark_stale_legacy(self.source, self.target, "en", "English")
        self.assertTrue(changed)
        self.assertEqual(TRANSLATE_DOCS.generated_body_bytes(self.target.read_bytes()), body)
        self.assertIn('"status":"stale-legacy"', self.target.read_text(encoding="utf-8").splitlines()[1])

    def test_check_all_aggregates_fresh_and_stale_targets_offline(self) -> None:
        extra_source = self.root / "docs" / "extra.md"
        extra_source.parent.mkdir(parents=True)
        extra_source.write_bytes(b"# Extra source\n")
        TRANSLATE_DOCS.SOURCE_FILES = [Path("README.md"), Path("docs/extra.md")]
        self.write_generated()
        extra_target = self.write_generated(extra_source, status="stale-legacy")

        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(sys, "argv", ["translate_docs.py", "--check-all"]), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = TRANSLATE_DOCS.main()

        self.assertEqual(result, 1)
        output = stdout.getvalue() + stderr.getvalue()
        self.assertIn(str(self.target.relative_to(self.root)), output)
        self.assertIn(str(extra_target.relative_to(self.root)), output)
        self.assertIn("stale-legacy", output)

    def test_normal_generation_writes_real_source_metadata(self) -> None:
        self.source.write_bytes(
            "# Canonical source\n\n**简体中文** | [English](translations/en/README.md)\n".encode("utf-8")
        )
        expected_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        with mock.patch.object(TRANSLATE_DOCS, "call_model", return_value="# Translated body\n"):
            target, content = TRANSLATE_DOCS.translate_file(self.source, {}, "en", "English")
        self.assertEqual(target, self.target)
        metadata_line = content.splitlines()[1]
        self.assertIn('"schema":"aios.translation.v1"', metadata_line)
        self.assertIn('"source_path":"README.md"', metadata_line)
        self.assertIn(f'"source_sha256":"{expected_hash}"', metadata_line)
        self.assertIn('"status":"generated"', metadata_line)

    def test_generation_hash_stays_bound_to_bytes_read_before_model_call(self) -> None:
        original = b"# Source bytes sent for translation\n"
        self.source.write_bytes(original)

        def mutate_source_during_generation(*_args: object, **_kwargs: object) -> str:
            self.source.write_bytes(b"# Source changed while translation was running\n")
            return "# Translation of original bytes\n"

        with mock.patch.object(
            TRANSLATE_DOCS,
            "call_model",
            side_effect=mutate_source_during_generation,
        ):
            _, content = TRANSLATE_DOCS.translate_file(self.source, {}, "en", "English")

        original_hash = hashlib.sha256(original).hexdigest()
        self.assertIn(f'"source_sha256":"{original_hash}"', content.splitlines()[1])
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text(content, encoding="utf-8")
        fresh, detail = TRANSLATE_DOCS.check_translation_target(self.source, self.target)
        self.assertFalse(fresh)
        self.assertIn("stale", detail)

    def test_invalid_check_target_returns_nonzero_without_api_config(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(
            sys,
            "argv",
            ["translate_docs.py", "--check", "translations/en/not-a-target.md"],
        ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = TRANSLATE_DOCS.main()
        self.assertEqual(result, 2)
        self.assertIn("invalid --check target", stderr.getvalue().lower())

    def test_check_target_cli_passes_offline_without_api_config(self) -> None:
        self.write_generated()
        stdout = io.StringIO()
        with mock.patch.object(
            sys,
            "argv",
            ["translate_docs.py", "--check", "translations/en/README.md"],
        ), mock.patch.object(
            TRANSLATE_DOCS,
            "api_config",
            side_effect=AssertionError("offline check must not load API configuration"),
        ), contextlib.redirect_stdout(stdout):
            result = TRANSLATE_DOCS.main()
        self.assertEqual(result, 0)
        self.assertIn("PASS fresh target: translations/en/README.md", stdout.getvalue())


class TranslateDocsWorkflowTests(unittest.TestCase):
    def test_workflow_checks_only_generated_changes_before_commit(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "translate-docs.yml").read_text(encoding="utf-8")
        generate_at = workflow.index("- name: Generate English docs")
        check_at = workflow.index("- name: Check generated translation freshness")
        commit_at = workflow.index("- name: Commit generated translations")
        self.assertLess(generate_at, check_at)
        self.assertLess(check_at, commit_at)
        check_step = workflow[check_at:commit_at]
        self.assertIn("git diff --name-only", check_step)
        self.assertIn('check_args+=(--check "$target")', check_step)
        self.assertNotIn("--check-all", check_step)


if __name__ == "__main__":
    unittest.main()