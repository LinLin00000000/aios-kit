# Session lesson: external-safe PDF-first HTML deliverables

Use this when polishing HTML reports that will be shared as PDF with partners, teams, executives, investors, or customers.

## Trigger

The user corrects an HTML report because it contains internal project rationale, private chat context, production notes, evidence/constraint tables, or interaction affordances that do not belong in a PDF handout.

## Lesson

A polished external HTML/PDF deliverable is not the same thing as an internal report workspace. Keep the workspace and audit trail in Markdown/JSONL under `internal/`; keep the root HTML/PDF as presentation-only.

## External deliverable hygiene

Before treating a root HTML file as partner/customer-facing, check and remove:

- personal motives, “why I made this”, or private self-positioning notes;
- internal workdir paths, timestamps, recovery notes, Agent workflow language, or production policy notes;
- source-tier labels such as “官网公开 / 团队初步沟通 / 待确认 / 用户提案” when those are only authoring constraints;
- sensitive cooperation details such as commission, equity, dividends, private chat names, screenshots, group-chat history, or unconfirmed customer/price claims;
- fixed timelines such as “30 天” when cooperation cadence has not been agreed;
- obvious AI-generated phrasing: “我的判断…”, “不是 X，而是 Y”, “核心在于…”, repetitive rule-of-three structures, and meta-commentary;
- jump links, hidden skip links, anchor navigation, or interactive-only affordances when the expected sharing surface is PDF or WeChat’s PDF viewer.

## PDF-first static rule

If the user plans to export HTML to PDF, assume the final reading surface may be a PDF viewer with weak or inconsistent link/navigation support. Do not rely on internal anchors or page interactions to convey meaning. Use plain visual hierarchy, section order, and page-readable headings.

A stylesheet `<link>` is fine. Public-body `<a>` links should be deliberate and rare; for a cover/index PDF, prefer no clickable navigation at all.

## Recommended rewrite pattern

1. Re-read the original objective, public product facts, and current HTML.
2. Split audiences:
   - public/external: root HTML/PDF;
   - internal/self: Markdown notes, constraints, traceability, recovery state.
3. Rewrite the cover/index as a pure presentation surface: title, one-sentence thesis, material structure, discussion objects.
4. Rewrite the strategy brief around the customer/product object, not the creator’s intent.
5. Convert private constraints into quiet public wording instead of exposing the constraint itself.
   - Internal: “do not claim customer case until verified.”
   - Public: avoid the claim entirely unless it is needed and sourced.
6. Run a deterministic hygiene check over public HTML for forbidden internal terms and anchors.

## Verification checklist

For each public root HTML file:

- `document.querySelectorAll('a').length === 0` unless external links are explicitly needed;
- no absolute user-home filesystem paths;
- no private names from chats or group exports;
- no “待确认 / 事实边界 / 证据来源 / 团队初步沟通” unless the document is explicitly an internal appendix;
- no fixed deadline language unless approved by the user;
- no sensitive cooperation terms;
- HTML parses and shared CSS loads;
- visible text still makes sense without knowing the author’s private conversation.
