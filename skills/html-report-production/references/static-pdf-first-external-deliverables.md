# Static PDF-first external deliverables

Use this reference when producing HTML-first reports that will be converted to PDF and shared in low-friction channels such as WeChat.

## Core lesson

When the final artifact is PDF or image-based sharing, HTML is a high-fidelity layout surface, not an interaction surface. Spend effort on static hierarchy, typography, diagrams, information density, and image composition. Do not spend effort on motion, hover states, anchors, or interactive navigation.

## Public vs internal boundary

Polished HTML/PDF deliverables for partners, teams, customers, or investors must not expose internal production context:

- no workdir paths;
- no recovery notes;
- no chat references or private conversation background;
- no fact-tier labels such as “team oral” or “pending confirmation” unless the artifact is explicitly an internal review draft;
- no collaboration terms, commissions, equity, or other sensitive deal details unless explicitly approved for that audience;
- no “I/my judgment” chat framing when the document should read as an objective proposal.

Keep these in internal Markdown/JSONL project files instead. Public documents should naturally avoid overclaiming through wording, not by showing internal guardrails.

## PDF-first rules

- Remove all animations, transitions, hover movement, scroll effects, and hidden skip/jump links from public report CSS.
- Do not rely on anchors, intra-page navigation, collapses, tabs, tooltips, hover reveals, or clickable UI to carry meaning.
- Design every page so a static screenshot or PDF page is self-contained.
- Use HTML for layout richness: cards, matrices, callouts, diagrams, image slots, page rhythm, and typography.
- For WeChat/mobile reading, also consider standalone images or long images as companion artifacts.

## Image-slot workflow

When image generation is available, do not invent or embed decorative images unilaterally.

1. Mark an image slot in the content plan.
2. State the image’s job: what idea it must make clearer.
3. Specify target placement, aspect ratio, and local output path.
4. Write a prompt the user can send to their preferred image model.
5. Wait for the user to provide the generated image.
6. Embed local PNG/JPEG/WebP into HTML with constrained dimensions.
7. Verify HTML rendering, then verify PDF export/rendering.

Prefer local PNG/JPEG for maximum PDF converter compatibility. Avoid remote image URLs and lazy-loading.

## Recommended delivery shape for strategic proposals

For partner/team/investor persuasion over chat channels, prefer:

- one formal PDF generated from static HTML, for complete logic and archival value;
- a small set of standalone WeChat-friendly images/long images, for low-friction forwarding and quick internal spread;
- optional embedded images inside the PDF for high-level system maps, product concepts, and workflow diagrams.

Avoid pure image-only delivery as the sole artifact when the proposal needs rigorous structure, product judgment, or future reference. Use images as the fast propagation layer and the PDF as the durable decision layer.

## Alignment-before-code rule

For strategic/product deliverables where the user’s own philosophy and positioning matter, ask alignment questions before writing HTML/code. Confirm audience, disclosure boundary, naming, core thesis, artifact format, image slots, and what should remain internal. This prevents the agent from producing polished but off-voice “AI-flavored” documents that require heavy rework.