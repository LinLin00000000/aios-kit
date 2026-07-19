#!/usr/bin/env python3
"""Focused tests for generated-document link rewriting."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()