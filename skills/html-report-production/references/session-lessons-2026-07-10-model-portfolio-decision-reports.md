# Session lesson: model-effort portfolio decision reports

Use this pattern for analytical HTML reports that select a **small fixed routing portfolio** (such as fast / daily / flagship) rather than declaring one benchmark champion.

## Analytical contract

1. Define each role first: workload, failure cost, latency/cost tolerance, and escalation behavior.
2. Compare only exact common groups (`chart/spec + variant + mode`). Isolate model-only rows and incomplete effort coverage as context rather than silently mixing samples.
3. Preserve missing metrics. If a pure-dimension scenario has no usable metric for one benchmark, skip it instead of imputing or assigning a synthetic neutral value.
4. Report adjacent effort upgrades using paired quality, cost, latency, token, and quality-efficiency ratios. Separate “quality usually rises” from “worth making the default.”
5. Inspect near-zero baselines and named outliers; use medians, win counts, Pareto, and anomaly notes rather than raw or geometric means alone.
6. Use two plausible within-benchmark normalization/aggregation methods plus a weight scan. Present the stable decision structure across methods, not one objective-looking composite score.
7. Avoid unexplained token double-counting when estimated cost already reflects token usage.

## Portfolio synthesis

- Fast tier: lowest effort that preserves acceptable reasoning/tool reliability, not automatically the absolute latency baseline.
- Daily tier: the broad balanced sweet spot, even if higher effort wins raw quality more often.
- Flagship tier: high-value, high-failure-cost, or empirically nonlinear work.
- Intermediate efforts remain threshold-triggered fallbacks or A/B-proven exceptions, not extra permanent roles.
- Do not mechanically retry every effort; critical work may route directly from daily to flagship.

## Report architecture

Keep the report generated from machine-readable analysis:

- aggregate JSON + per-benchmark CSV;
- deterministic analyzer;
- Markdown/HTML generator using a reusable visual system;
- deterministic verifier that regenerates JSON, CSV, Markdown, and HTML byte-for-byte;
- independent validator that recalculates from the raw long table instead of importing the canonical analyzer.

The HTML should lead with three role cards and a routing chain, then show marginal-upgrade tables, sensitivity, exceptions, and limitations. The Markdown remains the complete audit-friendly narrative.

## Public screenshot adaptation and external baselines

A model-portfolio report may be repackaged as a screenshot-first social post without modifying the canonical audit report. Generate a separate HTML surface from the existing structured data and keep the original Markdown unchanged.

### Screenshot-oriented content contract

- Recommended order: **verdict → methodology/source → same-family upgrade curves → previous-generation anchors → external competitors → retry/time-to-acceptable-result → routing → confidence limits → source note**.
- Use independent section cards as crop units. A cropped card must retain its subject, metric direction, comparator, and limitation note.
- When a recommendation selects effort levels from a larger ladder, each baseline page should show the complete relevant Terra/Sol ladder before the interpretation. Split materially different floors such as prior-generation high and xhigh into separate cards; apply the same full-ladder pattern to external-model baselines. Long evidence cards are acceptable when summary and per-benchmark detail remain readable.
- Keep title alternatives, caption drafts, channel notes, and publishing checklists outside the reader-facing HTML unless explicitly requested as report content.
- Inline CSS and avoid remote assets so a single local HTML file renders deterministically.
- Preserve detailed tables, but pair each with one plain-language takeaway. Do not make the reader reverse-engineer the verdict from ratios alone.
- Validate real geometry in the browser: no body-level horizontal overflow, tables fit or have intentional local scrolling, and decorative pseudo-elements do not escape their clipped section.

### Adding a stronger external comparator

1. Inspect the structured rows before writing prose: model labels, efforts/configurations, common-group coverage, and missing latency.
2. Define a non-cherry-picked reference policy. A sound example is “use `max` wherever published; otherwise retain the sole published `adaptive` row,” rather than selecting the highest observed score independently for each benchmark.
3. Compare only exact common identities (`chart/spec + eval variant + code mode`) and disclose the resulting sample size. A 6–7 point overlap is a **limited same-surface comparison**, not a global leaderboard.
4. Report quality win/loss, median quality ratio, P10, ≥95% floor coverage, and latency ratio together. A faster candidate with slightly lower median quality is not an equal-quality replacement.
5. Independently recompute the external summaries before final prose. If the new comparator contradicts the existing narrative, change the narrative—not the arithmetic.
6. Make the conclusion conditional on the floor:
   - prior-generation floor satisfied → keep the speed-oriented daily tier;
   - stronger current-flagship floor not satisfied → route high-stakes work to the flagship tier or require real-task A/B.

This prevents a common reporting error: preserving a polished fixed recommendation after a newly added comparator has changed what “quality over the line” means.

## Closeout discipline

- Check runtime compatibility for every recommended model/effort and distinguish target routing from configuration already applied.
- If a validator finds a small narrative omission, repair the generator/template, regenerate both surfaces, rerun deterministic verification, and preserve the original validator verdict while recording the repaired final verdict in supervisor validation.
- Run DOM overflow/external-asset checks plus one real visual inspection after the final regeneration.
- Keep final hashes and reproducibility commands with the report workspace.
