# Changelog

## Unreleased

- Replaced token-overlap service lookup with a compact `services --json` catalog plus exact `service <id> --json` context loading; the calling Agent/LLM now owns semantic selection.
- Added `service.json` metadata/reference templates and validation while keeping detailed service cards lazily loaded.
- Kept `host` and `log --query` as explicit deterministic text filters rather than presenting them as semantic natural-language routing.
- Added provenance-aware public-fixture guidance and synthetic catalog/load smoke tests.

## 0.1.0 - 2026-06-15

- Initial public template.
- Added AIOps vault file contract, low-token CLI, installer, examples, safety docs, and companion skills.
