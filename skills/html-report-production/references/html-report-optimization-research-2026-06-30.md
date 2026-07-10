# HTML report optimization research note — 2026-06-30

Use this note as condensed background when advising on AI-generated HTML reports and report-kit design.

## Research prompt

The user asked whether optimized HTML reports can beat Markdown when token cost, context engineering, visual encoding, emotion/attention value, brand compounding, and future adaptability are considered. They requested an LLL research run using skills search, GitHub search, and Reddit/community search, then a design recommendation if no ready-made solution exists.

## Evidence gathered

### Skills ecosystem

`npx skills find` returned relevant but incomplete pieces:

- `anthropics/skills@frontend-design`: very strong design-guidance signal; useful for visual direction and critique, not a report generator.
- `jimliu/baoyu-skills@baoyu-markdown-to-html` and `github/awesome-copilot@markdown-to-html`: strong Markdown-to-HTML conversion signals; useful for quick experiments or baselines.
- Several `html-report-*` or weekly-report skills exist, but many are low-install or low-star; treat as inspiration until inspected.
- Tailwind/design-system skills are useful for template authorship, but do not imply the Agent should emit raw Tailwind utility classes.

### GitHub candidates

Strong reusable components/projects by role:

- **Quarto**: mature technical/scientific/data report pipeline; good for Markdown/Jupyter/R/Python to HTML/PDF/sites.
- **Evidence**: Markdown + SQL static data apps; strong for data-heavy reports/dashboards.
- **Observable Framework**: interactive data applications; strong but more complex.
- **Astro**: good second-stage framework for report libraries/product-like interactive reports.
- **11ty**: lightweight static generator, template-first, low magic.
- **PicoCSS**: excellent MVP baseline CSS; low token and low configuration.
- **Tailwind CSS**: good inside templates/build pipelines, risky if LLM directly emits utilities.
- **Handlebars / Nunjucks / Eta**: high-fit template engines for schema/slot-to-HTML rendering.
- **Marked / markdown-it**: Markdown body-slot conversion.
- **Paged.js / Playwright print**: optional HTML-to-PDF/export layer.

Keyword search found many small single-purpose report generators, but few were mature enough to become core infrastructure. Use them as examples, not dependencies.

### Reddit/community

Direct Reddit JSON and search-engine `site:reddit.com` attempts timed out in that environment. Treat community evidence from that run as blocked/weak, not absent. Future runs should use a web/search tool or authenticated API when community evidence matters.

## Main conclusion

No single existing solution fully covers the target:

> low-token Agent generation + polished HTML visual encoding + reusable components/templates + long-lived report product protocol.

The reusable gap is not “a prettier template.” The gap is a **Report Product Protocol**:

- structured report schema;
- semantic component types;
- template/rendering layer;
- fixed design system/CSS;
- validation and delivery workflow.

## Recommended implementation shape

Start with a micro report-kit, not a heavy web framework:

```text
Agent outputs report.yaml/json or Markdown slots
  -> validate schema
  -> render with Nunjucks/Eta/Handlebars templates
  -> load fixed CSS/theme from project files
  -> optional Vega-Lite chart rendering
  -> optional screenshot/PDF validation
```

Default MVP stack:

- Node.js
- Nunjucks/Eta/Handlebars
- markdown-it or Marked
- PicoCSS plus small custom CSS variables
- optional Vega-Lite
- optional Playwright/Paged.js

First components:

1. hero
2. narrative
3. insight_grid
4. decision_matrix
5. source_list
6. next_actions

Upgrade later:

- Quarto for technical/data reports with notebooks/citations.
- Evidence/Observable for data applications and dashboards.
- 11ty for a lightweight report library.
- Astro for product-like interactive report sites.
- Next.js/React only if the artifact becomes a real app.

## Multi-output evolution

Later delivery work extended the original HTML-only framing into a multi-output information product:

```text
structured source / report schema
  -> HTML report-kit mother format
  -> formal PDF when needed
  -> ordered PNG cards for Xiaohongshu/WeChat/chat forwarding
  -> optional interactive HTML preview
```

This does not make every output a new truth source. Structured content/evidence remains canonical; HTML is the presentation/rendering mother format; PDF and PNGs are projections. The default external package depends on audience: formal professional delivery often benefits from one complete PDF plus selected forwarding cards, while public evidence-heavy social reports may export every self-contained HTML section as an ordered card package.

AI-generated images are a visual asset layer inside this architecture. Use schema-level `image_slots`; let image models handle atmosphere, metaphor, scene, material, and mood, while HTML/CSS/SVG keeps exact Chinese text, data, labels, QR codes, and formal structure deterministic.

The concrete public HTML → PNG cards → ZIP adapter is documented separately in `public-social-card-delivery-workflow.md`; keep this research note focused on architecture and tool selection.

## Pitfalls

- Do not store full CSS/templates inside the skill; keep the skill thin and put assets in a project repo.
- Do not let Tailwind utility strings become the new token sink.
- Do not overfit to a one-off visual style; keep component semantics stable and themes swappable.
- Do not claim Reddit/community absence if access failed; report it as a source limitation.
- When using `gh search repos --json`, check supported fields for the installed gh version; unsupported fields can make the whole search fail.
