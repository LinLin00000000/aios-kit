# Session lesson: standalone HTML reports and product-like UI samples

Use this when a public HTML report includes a static product/workbench/dashboard concept sample, especially when the final artifact may be opened outside the original project directory or converted to PDF.

## What happened

During an HTML-first proposal iteration, the user flagged two issues:

1. A section title read like internal implementation staging instead of a polished public proposal title.
2. A “future workbench sample” technically had CSS and card layout, but visually still read like unformatted content blocks rather than a real product interface.

The fix was to:

- rename the section from an internal-ish staging phrase to a public-facing product route title;
- turn phase cards into a clearer roadmap with time horizons and compact module pills;
- rebuild the workbench sample as an app shell: browser bar, sidebar, active lead list, main detail view, signal cards, conversation summary, AI recommendations panel, and bottom operations strip;
- inline CSS into the public HTML so opening or sharing the single file would not fail because a relative stylesheet did not load.

## Durable pattern

For public strategic deliverables, avoid section titles that expose production logic such as “first do high-yield modules, then future blueprint.” Prefer titles that describe the strategic product route, for example:

> AI 自动化落地路线：先形成销售闭环，再扩展为多 Agent 平台

When showing a future product/workbench concept, do not just place related content into cards. A product concept sample should visually encode real interface anatomy:

- shell/chrome: top bar, product name, current route;
- navigation: sidebar, tabs, active object;
- data objects: lead/customer rows, status, score, tags;
- workspace: selected object detail, summary, next actions;
- AI layer: recommendations, risk flags, handoff trigger;
- operations strip: feedback, objections, channel actions, product learnings.

## Standalone-public HTML rule

If the deliverable is meant to be sent as a single `.html` file or opened by non-technical readers, inline the final CSS into the public HTML. Keep the external CSS/theme file as the editable source if useful, but make the public HTML self-contained to avoid relative-path stylesheet failures.

Still verify:

- no links/images/scripts if the artifact is intended to be static and PDF-first;
- no hover/transition/animation/keyframes if static PDF-first constraints apply;
- browser console has no errors;
- computed styles confirm the intended grid/app shell is active;
- body has no horizontal overflow;
- if vision QA is unavailable, capture a screenshot and note the limitation rather than claiming visual review.
