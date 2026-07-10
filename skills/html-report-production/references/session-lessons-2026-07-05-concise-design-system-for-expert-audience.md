# Session lesson — concise design systems for expert business audiences

Use when polishing HTML-first business/product deliverables for a highly technical or senior product audience.

## Trigger

The user says the audience already understands the domain and asks to avoid long explanations, generic consulting prose, or "old truths". Examples: 清北博士/strong technical team, overseas product leaders, investor/founder review, expert GTM/product audience.

## Practice

1. Treat the design system as both visual and editorial.
   - Put the rule in the workdir/project design-system file, not only in chat.
   - The content rule should be: every module must carry one of core judgment, evidence, next action, or risk boundary.
   - Delete AI/GTM/product basics unless they directly support a decision.

2. Make typography rules explicit and executable.
   - Chinese body text: `letter-spacing: 0`.
   - Chinese display headings: only mild negative tracking, around `-0.01em` to `-0.02em`; avoid heavy values such as `-0.04em` or lower.
   - English eyebrow/version labels: moderate tracking around `0.06em`–`0.10em`; avoid mechanical large tracking such as `0.16em` unless very short and visually justified.
   - Keep cards short: 1–3 lines of body copy where possible.

3. Use one shared visual source of truth.
   - Root HTML files should load one shared CSS/theme file.
   - Avoid per-page inline `<style>` or ad-hoc visual language.
   - New visual components should be added to the shared theme first.

4. Verification pattern.
   - Check required files exist and are non-empty.
   - Search CSS for forbidden tracking patterns and `transition: all`.
   - Parse JSON/HTML when applicable.
   - Load representative HTML in browser and inspect computed styles: heading letter-spacing, label letter-spacing, CSS loaded, horizontal overflow.
   - If screenshot/vision QA is unavailable due to setup, record it as non-blocking and rely on deterministic DOM/CSS checks; do not claim visual QA was performed by sight.

## Good output shape

- `internal/report-kit/design-system.md` or equivalent: editorial + typography + component rules.
- `internal/report-kit/report-theme.css` or equivalent: executable tokens and component classes.
- Mission/recovery/handoff updated so future sessions inherit the compactness and visual rules.
- Focused validation report with PASS/PASS_WITH_NOTES and exact checks performed.
