---
name: html-report-production
description: Use whenever the user asks for a polished HTML report, AI-generated research/decision deliverable, reusable report-kit, Markdown/structured-content conversion, HTML-to-PDF flow, public report sanitization, Xiaohongshu/WeChat/social long-image cards, section-by-section PNG export, or a ZIP image package. Covers low-token schema/template architecture, evidence-first layout, reusable design systems, deterministic desktop Chromium rendering, public-deliverable hygiene, packaging, and validation rather than ad-hoc full HTML/CSS generation.
metadata:
  hermes:
    version: "1.2.0"
    platforms: [linux, macos, windows]
    tags: [html-report, reporting, templates, static-site, context-engineering, design-system, social-cards, playwright]
---

# HTML Report Production

For public reports that will become PDF or be shared through chat/mobile channels, first consult `references/static-pdf-first-external-deliverables.md`. It captures PDF-first static design rules, external-deliverable hygiene, image-slot workflow, and the requirement to align with the user before writing polished HTML/code.

Use this skill when the user wants a polished HTML report, a reusable report template system, Markdown/structured-content to HTML conversion, report visual design, HTML-to-PDF export, social-card/long-image PNG outputs, a ZIP image package, or an AI-friendly report-generation workflow.

Core principle:

> The Agent should usually generate **structured report content**, not full bespoke HTML/CSS. HTML structure, CSS, layout, and component classes should live in reusable templates and project files.

## When to use

Use this skill for:
- converting research/analysis into polished HTML deliverables;
- building a reusable report generator or report-kit;
- choosing between Markdown, Quarto, Astro, 11ty, Tailwind, PicoCSS, template engines, Evidence, Observable, or custom HTML;
- reducing token cost for repeated HTML report generation;
- designing report schemas, component libraries, themes, and validation checks;
- producing HTML reports that may later become PDF, static sites, dashboards, or public-facing artifacts.

Do not use this skill for quick scratch notes, plain internal Markdown, or ordinary diagrams/charts unless the user wants them embedded in an HTML report.

## Default architecture

Prefer a thin pipeline:

```text
User/report objective
  -> Agent writes report.yaml / report.json / Markdown slots
  -> schema validation
  -> template engine renders HTML components/layout
  -> fixed CSS/design system is loaded from files
  -> self-contained HTML review/rendering mother format
  -> optional PDF + ordered social-card PNGs
  -> deterministic audit + representative visual QA
  -> deliver report.html / report.pdf / report-cards.zip as requested
```

This keeps the expensive fixed costs out of the model context:
- CSS is a project asset, not repeated model output.
- Layout wrappers are templates, not regenerated prose.
- Component classes live in partials/macros, not in Agent-authored content.
- The Agent chooses semantic components such as `insight_grid`, `decision_matrix`, or `source_list`.

## Recommended phases

### Session-specific references

- `references/session-lessons-2026-07-06-delivery-readiness-and-product-philosophy.md`: delivery readiness review under time pressure; product-philosophy framing (`全 AI 自动化`, `自举分形`); broad collaboration-form patterns beyond a single private-group mechanism.

### Phase 0: quick experiment

Use an existing Markdown-to-HTML/report skill or a simple HTML template to test whether HTML actually improves the user's reading/decision experience. Keep this disposable.

### Phase 1: micro report-kit MVP

Start with the smallest reliable custom generator:
- Node.js runtime.
- Nunjucks, Eta, or Handlebars for templates.
- markdown-it or Marked for Markdown body slots.
- PicoCSS or a small custom CSS file for baseline style.
- Optional Vega-Lite specs for charts.
- Optional Playwright/Paged.js for screenshot/PDF export.

Build only a few components first:
1. `hero`
2. `narrative`
3. `insight_grid`
4. `decision_matrix`
5. `source_list`
6. `next_actions`

### Phase 2: static site / report library

Upgrade only when real needs appear:
- 11ty for a lightweight template-first static report library.
- Astro for richer components, islands, and product-like interactive report sites.
- Quarto for technical/scientific/data reports with code, notebooks, citations, and multi-format output.
- Evidence or Observable Framework for data-heavy, interactive dashboard/report artifacts.

Avoid starting with Next.js/React/shadcn unless the report is becoming a long-lived web application with app state, authentication, or complex interaction.

## Screenshot-first social / long-image reports

When the HTML must also become section-by-section images for Xiaohongshu, WeChat, social posting, or chat forwarding, load `references/public-social-card-delivery-workflow.md` and use the bundled renderer/auditor. The rules below are the compact decision layer; the reference holds exact commands, packaging layout, failure repairs, and verification steps.

1. **Design crop boundaries, not one continuous wall.** Use self-contained section cards/slices with a section number, heading, thesis, evidence, and a short boundary note. Keep each slice understandable after cropping away the rest of the page.
2. **Put conclusion before method.** A strong default order is conclusion → method/source credibility → detailed comparisons → routing/limitations → source note. Method should explain structured extraction and arithmetic without delaying the verdict.
3. **Treat the user's current decision function as the report contract.** Remove obsolete optimization narratives rather than preserving them as historical context. If cost is no longer the objective, it may remain as a diagnostic column but must not silently drive recommendations.
4. **For newly added baselines, recompute before polishing prose.** Use exact common evaluation identities, state baseline-configuration selection rules, and expose limited coverage. Never let an attractive pre-existing conclusion override a stronger new comparator.
5. **Use conditional conclusions when quality floors differ.** Example: a portfolio can remain optimal against a previous-generation floor while failing a newer flagship floor. State both conditions instead of flattening them into one ranking.
6. **Do not let the recommendation pre-filter its own evidence.** When the conclusion selects particular model/effort levels from a ladder, baseline pages should first show the complete relevant ladder for each series, then interpret why the selected levels survive. Split materially different quality floors—such as previous-generation high and xhigh—into separate cards. For external-model pages, use the same full-ladder structure; long evidence cards are acceptable when summary tables and per-benchmark detail remain readable.
7. **Keep the artifact self-contained without mixing in packaging metadata.** Inline CSS and avoid network assets. Treat title alternatives, caption drafts, channel notes, and publishing checklists as separate packaging material; do not place them inside the reader-facing HTML unless the user explicitly asks for them as content.
8. **Verify the actual capture geometry.** After final regeneration, open the HTML in a browser and check `body.scrollWidth == body.clientWidth`, table overflow, section widths/heights, first-screen hierarchy, and one visual screenshot. A full-page screenshot may look tiny when scaled for inspection; use DOM geometry to distinguish real overflow from preview scaling.
9. **Keep public cards free of production context.** Remove workdir paths, internal/recovery language, private rationale, title brainstorms, generator notes, maker-facing footers, and references to reusing snapshots or scraping steps. Source dates, calculation rules, limitations, and evidence provenance remain reader-facing transparency; phrase them as data basis and statistical method rather than production notes.
10. **Mark deterministic card boundaries.** Put a stable ASCII `data-card-name` on every independently exportable section, for example `<section class="slice" data-card-name="methodology">`. The export folder should contain only ordered PNG deliverables; keep manifests and QA evidence under the workdir's internal area.
11. **Export with real desktop Chromium, not an approximate HTML renderer.** The bundled `scripts/render_html_cards.cjs` uses a desktop Linux Chrome UA, waits for fonts, fails on page/table overflow or console errors, isolates each marked card, and exports at 960 CSS px × 2 DPR by default (1920 px wide). It first checks `PLAYWRIGHT_NODE_MODULES` and the active `npm root -g`, then common user/system global roots. This matters on hosts where NVM changes the active Node/npm prefix while Hermes keeps reusable packages under its own user-scoped Node prefix.

One-time setup on a persistent host:

```bash
npm install -g playwright
playwright install chromium
```

Use the already installed Playwright version when its browser cache exists. Do not pin an arbitrary older Playwright just for one report: that can download a duplicate Chromium build.

Reusable export and audit:

```bash
node <skill-dir>/scripts/render_html_cards.cjs \
  --input /absolute/path/report.html \
  --output-dir /absolute/path/report-cards \
  --selector '[data-card-name]' \
  --export-width 960 --dpr 2 --clean \
  --manifest /absolute/path/internal/card-render-manifest.json
python3 -m zipfile -c /absolute/path/report-cards.zip /absolute/path/report-cards
python3 <skill-dir>/scripts/audit_public_cards.py \
  --html /absolute/path/report.html \
  --cards /absolute/path/report-cards \
  --manifest /absolute/path/internal/card-render-manifest.json \
  --zip /absolute/path/report-cards.zip
```

Before delivery, inspect at least three representative PNGs: the cover, a dense/long section, and the most complex table. Confirm the PNG count matches marked cards and validate actual PNG dimensions independently of the renderer manifest.

See `references/session-lessons-2026-07-10-model-portfolio-decision-reports.md` for the paired analytical rules: exact common groups, external-baseline configuration policy, quality-floor-dependent conclusions, and screenshot-oriented verification.

## Schema-first report authoring

Ask the Agent to output a compact intermediate representation. Example shape:

```yaml
meta:
  title: "..."
  subtitle: "..."
  audience: "decision-maker | self | public"
  tone: "editorial | analytical | dashboard"
  theme: "clean | editorial | dashboard"
hero:
  thesis: "..."
  key_numbers:
    - label: "..."
      value: "..."
      note: "..."
sections:
  - type: narrative
    title: "..."
    body_md: "..."
  - type: insight_grid
    cards:
      - title: "..."
        body: "..."
        accent: blue
  - type: decision_matrix
    columns: ["方案", "优点", "代价", "结论"]
    rows: []
  - type: source_list
    rows:
      - name: "..."
        url: "..."
        confidence: high
```

The schema is the product contract. Templates and themes can evolve without changing how the Agent thinks.

## Framework decision guide

| Need | Prefer | Why |
|---|---|---|
| One-off polished report | existing HTML/Markdown-to-HTML skill + simple template | fastest validation |
| Repeatable AI-generated reports | custom micro report-kit | best context-engineering leverage |
| Technical/data report with code/citations | Quarto | mature report semantics |
| Data app / dashboard report | Evidence or Observable Framework | data and interaction first |
| Lightweight static report library | 11ty | template-first, low magic |
| Product-like interactive report site | Astro | component islands without full SPA weight |
| App with auth/state/backend | Next.js/React | only when it is truly an app |

## Token-cost discipline

- Do not ask the model to regenerate full CSS or layout for every report.
- Do not move the token problem into huge Tailwind utility-class strings. If using Tailwind, put classes in templates/partials.
- Keep skills as thin entrypoints: trigger conditions, schema summary, commands, and validation. Store full templates/CSS in the project repo.
- Prefer semantic component selection over raw HTML: `type: decision_matrix` beats a hand-authored table with repeated classes.
- Use chart specs/data rather than pre-rendered SVG/HTML when possible.

## Validation checklist

Before delivery, verify:
- schema validates;
- HTML file exists and opens/builds successfully;
- no large accidental inline CSS/JS was generated by the Agent unless intentional;
- mobile viewport remains readable;
- color contrast is acceptable;
- links and sources are preserved when the artifact is web-first;
- if the artifact is PDF-first or intended for WeChat/mobile PDF viewing, do not rely on jump links, hidden skip links, anchor navigation, or interactive-only affordances;
- public/partner-facing HTML contains no internal workdir paths, private chat context, personal production rationale, evidence-tier labels, unresolved constraint notes, or sensitive cooperation details;
- fixed timeline language appears only when the user has approved the cadence;
- external CDN/network dependencies are deliberate and documented;
- optional PDF/screenshot generation works if requested;
- if the public HTML may be opened/shared as a single file, inline the final CSS into the HTML while keeping the external theme as the editable source copy;
- product/workbench/dashboard concept samples look like real static app shells, not just text cards: include chrome, navigation, active object, data rows, status/score, main workspace, AI recommendation panel, and operations/feedback area where appropriate;
- final file paths are absolute Markdown links when sending files to the user.

## Related notes

- See `references/html-report-optimization-research-2026-06-30.md` for the condensed Skills/GitHub research, framework tradeoffs, micro report-kit architecture, and why the durable asset is a Report Product Protocol rather than one prettier template.
- See `references/public-social-card-delivery-workflow.md` for the complete public HTML → ordered desktop-Chromium PNG cards → ZIP workflow, including audience hygiene, evidence-before-recommendation layout, persistent Playwright setup, deterministic audit, representative visual QA, and stale-validation handling.
- See `references/workflow-protocol-presentation-context.md` for the pattern where HTML reports are a high-fidelity presentation context over a canonical machine-readable workflow protocol, useful for PRDs, decision briefs, roadmaps, and customer-facing AIOS/workflow reports.
- See `references/session-lessons-2026-07-10-model-portfolio-decision-reports.md` for role-first model/effort portfolio analysis: exact common-group isolation, marginal-upgrade economics, dual-method sensitivity, generated Markdown/HTML, deterministic regeneration, runtime compatibility checks, and validator-note repair.
- See `references/session-lessons-2026-07-05-polished-html-pdf-business-deliverables.md` for a kickoff/recovery pattern for serious multi-session business deliverable packages where HTML is the primary iterative review surface and PDFs are milestone/final snapshots.
- See `references/session-lessons-2026-07-05-concise-design-system-for-expert-audience.md` for the pattern of turning user feedback about expert audiences into a compact editorial+typography design system, including Chinese/English letter-spacing rules and deterministic HTML/CSS verification.
- See `references/session-lessons-2026-07-05-external-safe-pdf-first-deliverables.md` for the pattern of separating internal project/recovery notes from external partner-facing HTML/PDF, removing jump links for PDF-first sharing, and running hygiene checks for private context or sensitive terms.
- See `references/session-lessons-2026-07-06-ai-image-slots-multi-output-delivery.md` for using AI-generated images as a report visual-asset layer: schema-level `image_slots`, HTML/PDF/WeChat card multi-output delivery, and the rule that generated images handle atmosphere/metaphor while HTML/CSS/SVG handles Chinese text, data, labels, and formal structure.
- See `references/session-lessons-2026-07-06-standalone-html-product-ui-samples.md` for the pattern of making public HTML self-contained with inlined CSS when it may be shared as a single file, and for turning static product/workbench samples into real app-shell mockups rather than loosely styled text cards.
- See `references/session-lessons-2026-07-06-full-chain-sales-ops-ui.md` for the pattern of expressing full-chain AI sales-ops systems with two complementary visuals: an ecosystem map plus a command-center workbench that includes multi-platform discovery, private-domain/IM management, AI/human collaboration, guardrails, and productization feedback.
- See `references/session-lessons-2026-07-06-philosophy-and-collaboration-forms.md` for the pattern of elevating a user's core product philosophies (e.g. 全 AI 自动化 and 自举分形) into the proposal narrative, and for broadening “small group” ideas into multiple controlled collaboration-field patterns.
