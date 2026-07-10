# Workflow protocols and HTML as a presentation context

Session lesson from an AIOS workflow-core/product-protocol design discussion.

## Core lesson

When a system has a machine-readable source of truth plus multiple human/tool views, polished HTML reports should be treated as a **Presentation Context**, not as a standalone truth store and not as superficial decoration.

Recommended layering:

```text
Canonical machine truth
  -> structured report slots / report schema
  -> HTML report-kit templates + fixed CSS/design system
  -> decision brief / PRD / roadmap / customer report
```

This mirrors the report-kit principle: agents should write structured content and semantic component choices, while templates own layout, styling, accessibility, and visual hierarchy.

## Product/protocol design implications

For AIOS-style workflow systems, human-readable deliverables can include Markdown and HTML, but they should be derived from or traceable to machine state and event logs:

- machine truth: JSON/JSONL/SQLite state, IDs, links, events, decisions;
- human contract: mission, PRD, domain model, ADRs, decision log;
- presentation: HTML decision briefs, project dashboards, roadmap reports, customer-facing summaries;
- execution projections: Kanban, GitHub Issues/PRs, CI runs, approval systems.

HTML is high-value because it improves attention routing, hierarchy, decision quality, team/customer communication, and commercialization credibility. Token savings are a benefit, not the deepest reason.

## Pitfall

Do not frame HTML report generation only as "make Markdown prettier" or "reduce token cost". In product workflows, the real value is a reusable presentation layer over a canonical protocol.

## Reusable phrasing

> The report is a view, not the source of truth. The source of truth is the workflow protocol; the HTML report is a high-fidelity human attention and decision surface generated from that protocol.
