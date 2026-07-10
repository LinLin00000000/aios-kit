# Public HTML report → social-card delivery workflow

Use this reference when a polished HTML report must also become a public, low-friction PNG package for Xiaohongshu, WeChat, social posting, or chat forwarding.

This is an **output adapter over the HTML report**, not a new report truth source. The canonical analytical/content source remains structured data, report schema, Markdown, or project files. HTML is the review/rendering mother format; PNG cards and ZIP are derived delivery assets.

## Boundary model

Keep four layers distinct:

1. **Canonical content/evidence** — report YAML/JSON/Markdown, analysis tables, citations, and project truth.
2. **Presentation mother format** — self-contained HTML with stable semantic section/card boundaries.
3. **Delivery projections** — full HTML, optional PDF, ordered PNG cards, optional selected summary cards, ZIP package.
4. **Internal production state** — workdir paths, recovery state, prompts, title brainstorming, scraping/cache notes, manifests, logs, and QA evidence.

Only layers 2–3 are public. Layer 4 must not leak into the reader-facing artifact.

## End-to-end workflow

### 1. Freeze audience and delivery contract

Decide before polishing:

- public vs internal audience;
- full evidence cards vs a small summary-card subset;
- desktop layout geometry and output pixel width;
- whether HTML/PDF remain deliverables or only rendering surfaces;
- whether long tables may produce very tall cards.

For evidence-heavy analysis, prefer complete section cards over arbitrary fixed-height slices. A long card is acceptable when it preserves a coherent argument and remains readable at full resolution.

### 2. Build from structured truth

Prefer:

```text
structured source / report schema / canonical Markdown
  -> deterministic analysis
  -> deterministic HTML generator/template
  -> public HTML
```

Do not manually patch generated HTML as the primary fix. Repair the generator/template, regenerate, and verify.

### 3. Organize evidence before recommendation

When a recommendation selects levels from a ladder (model effort, plan tier, product option, architecture stage):

1. show the complete relevant ladder;
2. disclose common-sample coverage and missing observations;
3. provide a compact summary table;
4. retain per-item/per-benchmark detail when it materially supports the choice;
5. place the plain-language interpretation after the evidence.

Split distinct quality floors or decision baselines into separate cards. Do not combine them merely to reduce card count. The recommendation must be visibly derived from the evidence, not used to pre-filter it.

### 4. Sanitize the public surface

Remove:

- workdir and local filesystem paths;
- `mission.md`, `internal/`, recovery, worker, prompt, or agent-process references;
- statements about reusing snapshots, scraping retries, cache fallbacks, or generation mechanics;
- title alternatives, caption drafts, publishing checklists, and maker-facing footers;
- private rationale, chat context, unresolved internal constraints, and sensitive cooperation details.

Keep, but rewrite for readers:

- source/date → “数据依据 / 统计日期”;
- calculation mechanics → “统计口径 / 方法”；
- missing coverage → “证据边界 / 限制”；
- confidence and caveats → public interpretation guidance.

Packaging metadata belongs in a separate publishing note when needed, not inside the report.

### 5. Mark deterministic card boundaries

Every independently exportable section gets a stable ASCII slug:

```html
<section class="slice" data-card-name="methodology">
  ...
</section>
```

Rules:

- names are unique and stable;
- order in the DOM is delivery order;
- each card is independently understandable after cropping;
- the section includes its subject, comparator/direction, evidence, and essential limitation;
- do not put the render manifest in the public delivery folder.

### 6. Prepare a persistent Playwright runtime

One-time setup:

```bash
npm install -g playwright
playwright install chromium
```

Reuse the installed Playwright/browser pair. Do not pin an arbitrary older Playwright for one report: Playwright browser builds are version-coupled and can trigger a large duplicate Chromium download.

On multi-Node hosts, the renderer searches:

1. `PLAYWRIGHT_NODE_MODULES`;
2. active `npm root -g`;
3. `~/.hermes/node/lib/node_modules`;
4. `/usr/local/lib/node_modules`.

### 7. Export all marked cards

```bash
node <skill-dir>/scripts/render_html_cards.cjs \
  --input /absolute/path/report.html \
  --output-dir /absolute/path/report-cards \
  --selector '[data-card-name]' \
  --viewport-width 1200 --viewport-height 900 \
  --export-width 960 --dpr 2 --page-padding 24 \
  --clean \
  --manifest /absolute/path/internal/card-render-manifest.json
```

Default output is 960 CSS px at DPR 2 → 1920 px wide PNGs. The script uses a desktop Chrome UA, waits for fonts, disables animations, fails on body/table overflow and console errors, isolates cards, and writes ordered filenames.

`--clean` deletes only prior ordered PNG names matching the renderer pattern; keep the delivery directory dedicated to exported PNGs.

### 8. Package with ZIP

ZIP is the default broad-compatibility archive format:

```bash
rm -f /absolute/path/report-cards.zip
python3 -m zipfile -c \
  /absolute/path/report-cards.zip \
  /absolute/path/report-cards
```

Place the ZIP at the workdir/delivery root. Keep only ordered PNGs inside the delivery directory so the archive is immediately usable.

### 9. Run deterministic audit

```bash
python3 <skill-dir>/scripts/audit_public_cards.py \
  --html /absolute/path/report.html \
  --cards /absolute/path/report-cards \
  --manifest /absolute/path/internal/card-render-manifest.json \
  --zip /absolute/path/report-cards.zip \
  --forbid 'project-private-term' \
  --expected-count 15
```

It checks:

- unique card markers and expected count;
- default/additional forbidden public terms;
- unexpected remote assets;
- browser overflow and console errors from the manifest;
- PNG signatures, names, dimensions, and delivery-folder purity;
- ZIP CRC, DEFLATE compression, and exact filename parity.

This audit is structural, not aesthetic.

### 10. Perform representative visual QA

Inspect at least:

1. cover/first card;
2. method/source card;
3. longest evidence card;
4. densest table card when different from the longest.

Check the actual image pixels for:

- top and bottom completeness;
- clipped borders, tables, footnotes, or pseudo-elements;
- text overlap or mojibake;
- excessively small annotations;
- whether the card remains understandable without adjacent cards;
- whether the recommendation follows rather than precedes its evidence.

A scaled-down preview can make valid 1920 px cards look too small. Distinguish preview scaling from actual pixel readability.

### 11. Freeze, validate, then package again if changed

The validation surface is the generated HTML plus the exact PNG/ZIP package. Any content/template change makes prior visual and independent validation stale. Regenerate HTML, cards, manifest, and ZIP, then rerun the focused audit once.

## Delivery layout

Recommended workdir shape:

```text
<workdir>/
  report.html
  report-cards/                 # public: PNG only
    01-cover.png
    02-conclusion.png
    ...
  report-cards.zip              # public download package
  internal/
    card-render-manifest.json   # QA evidence, not public content
    scripts/                    # report-specific generator/verifier when needed
```

Do not add a second report truth source for cards. Card order and content come from the HTML markers; HTML comes from the canonical report source/generator.

## Failure modes and repairs

| Failure | Correct repair |
|---|---|
| Internal “workdir/snapshot/generator” wording appears publicly | Repair generator prose; regenerate; rerun hygiene scan |
| Title alternatives appear as a report section | Move them to separate publishing metadata or omit |
| Recommendation pages show only selected tiers | Expand to the full relevant ladder; put interpretation after evidence |
| GPT/plan/baseline floors are mixed in one overcrowded card | Split by materially different floor or decision question |
| Renderer downloads another large Chromium | Match Playwright to existing shared cache; avoid arbitrary old version pins |
| NVM changes `npm root -g` and Playwright cannot be found | Set `PLAYWRIGHT_NODE_MODULES` or rely on the renderer’s Hermes/system fallback roots |
| Screenshot clip is outside very tall page bounds | Isolate one card in the DOM and resize the viewport before full viewport screenshot |
| ZIP includes manifests/logs | Keep delivery directory PNG-only; rebuild ZIP from that directory |
| Visual validator reviewed an older surface | Mark verdict stale; freeze new surface and rerun one validator |

## Relationship to report-kit architecture

This workflow works with one-off self-contained HTML, but its durable form is:

```text
report schema / Markdown slots
  -> report-kit templates + fixed design system
  -> public HTML mother format
  -> PDF and/or social-card projections
```

Keep `SKILL.md` thin. Templates, CSS, component macros, and schema belong in a report-kit project when repeated report volume justifies it. The skill owns triggering, boundaries, commands, hygiene, and validation discipline—not the entire design system.
