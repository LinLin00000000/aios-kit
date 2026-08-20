# Cross-surface delivery-preference audit

Use this reference when a user preference or product decision changes the default relationship between canonical Markdown, `workspace://` reading, HTML presentation, and PDF export across LLL, host UI skills, templates, or report generators.

## Contract to freeze

Record the current contract before interpreting older guidance:

```text
explicit current user preference
  > current Matter / mission
  > local Workflow Policy or user sidecar
  > generic skill/template defaults
```

A useful four-surface model is:

| Decision | Typical owner | Safe default for local LLL work |
|---|---|---|
| Canonical/editable source | Worksite/LLL deliverable owner | Markdown |
| Local human reading route | Host/WebUI integration | native `workspace://` |
| External/polished presentation | report/viewer skill | HTML only for external delivery or explicit request |
| Snapshot/export | PDF/report skill | milestone/final or explicit request |

Do not infer a default from the existence of a historical HTML/PDF file or from a renderer's ability to display that type.

## Evidence matrix

For each candidate rule, capture:

| Field | What to record |
|---|---|
| Path/owner | exact file, section, and line range |
| Quote | shortest text that changes routing or format choice |
| Scope | current default, conditional trigger, legacy/versioned workaround, or historical evidence |
| Classification | `active conflict`, `ambiguous`, `historical-neutral`, or `aligned` |
| Impact | what a future Agent would generate, link, or expose incorrectly |
| Smallest correction | one owner edit or pointer; avoid mass rewrites |

Search both positive and negative signals. Useful terms include:

```text
workspace://
absolute path
relative link
primary review surface
mother format
report.html
report.pdf
Markdown/HTML
PDF-first
when requested
external delivery
```

## Common findings and interpretation

### Active conflicts

- A generic design/report skill says to use absolute local paths as the Markdown link target.
- A report skill triggers on any “research/decision deliverable” and makes HTML the review mother format without an explicit HTML/external request.
- A final-delivery rule says to send absolute Markdown links even though the host has a native Workspace route.

Repair the owning rule to use `workspace://` for local final receipts and to make HTML/PDF conditional. Preserve absolute paths only for an explicit copy/audit need, an external address, or a version-scoped legacy fallback.

### Ambiguous gaps

- Human deliverables are described as “Markdown/HTML” without saying which is canonical/default.
- A generic link rule allows relative links, URLs, and absolute paths but does not distinguish links inside a document from the final local chat receipt.
- A local policy owns interaction behavior but has no pointer to the current delivery-surface contract.

Add one compact owner pointer. Do not replace ordinary relative links inside a Markdown document: the `workspace://` requirement normally applies to the user-facing local receipt, not every intra-document reference.

### Historical or conditional guidance

Treat dated session lessons, old Studio version workarounds, PDF-first external packages, and existing HTML artifacts as scoped evidence. Keep them available when useful, but add a scope guard if a generic skill can load them as if they were current defaults.

## Minimal repair sequence

1. Patch the strongest generic owner first (usually the local human-deliverable policy/sidecar or the class-level report-routing skill).
2. Change neighboring skills/templates to short pointers, not duplicate protocols.
3. Mark version-specific absolute-path preview workarounds as legacy and prefer native Workspace when available.
4. Restrict PDF generation to explicit/milestone/final conditions; do not create HTML merely because Workspace rendering has limitations.
5. Re-read every edited target and check the final text for stale `primary HTML`, `mother format`, or unconditional absolute-link wording.
6. If the skill is hub/external/user-owned or not curator-addressable, stop mutation, preserve the audit finding, and recommend foreground adoption instead of creating a duplicate.

## Verification checklist

- The precedence chain is explicit and current.
- Markdown remains the canonical/default local reading surface.
- Local final receipts use `workspace://` when the native route exists.
- HTML is external/explicit, not an automatic fallback for Workspace limitations.
- PDF is milestone/final/explicit, not a default companion artifact.
- Internal relative links remain valid and are not mass-converted.
- Historical/versioned references are labeled as such.
- Every changed skill points to this reference without creating a second preference owner.
