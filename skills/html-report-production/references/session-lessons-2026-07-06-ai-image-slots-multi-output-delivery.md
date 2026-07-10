# Session lesson: AI image slots and multi-output report delivery

Use this note when a polished report should benefit from AI-generated visuals and low-friction social sharing.

## Core pattern

Treat AI-generated images as a **visual asset layer**, not as the report's source of truth.

Recommended production chain:

```text
structured source / report.yaml
  -> HTML report-kit as review/rendering mother format
  -> local image assets under assets/images/
  -> PDF formal deliverable
  -> WeChat/social PNG cards for low-friction forwarding
```

## Image slot contract

Add `image_slots` to the report schema. Each slot should include:

- `id`
- `purpose`
- `ratio` / target sizes
- `path`
- `alt`
- optional `caption`
- `prompt`
- `negative_prompt`
- `postprocess` instructions

Example:

```yaml
image_slots:
  - id: hero-ai-delivery-system
    purpose: "Report opening visual: AI-era professional delivery as a multi-output information product"
    ratio: "16:9"
    path: "assets/images/hero-ai-delivery-system.png"
    alt: "AI-assisted multi-output report delivery system"
    caption: "From structured source to HTML, PDF, and social cards"
    prompt: |
      A premium editorial illustration of an AI-assisted professional report production system,
      structured knowledge flowing into a polished web report, PDF document, and mobile social cards,
      elegant information architecture, modern strategy consulting aesthetic, warm neutral background,
      subtle blue and amber accents, high-end magazine layout feeling, no text, no logo, no watermark.
    negative_prompt: "text, letters, watermark, logo, distorted UI, cluttered layout"
    postprocess: "Overlay all Chinese title/data/labels in HTML/SVG, not inside the generated bitmap."
```

## Division of labor

AI image models are strong for:

- atmosphere, metaphor, scene, mood, material, texture;
- cover visuals, section illustrations, social-card backgrounds;
- concept images and visual hooks.

Do **not** rely on generated bitmaps for:

- long Chinese text;
- exact data labels or tables;
- QR codes;
- official logos or legally sensitive copy;
- searchable/copyable report substance.

Use HTML/CSS/SVG/PDF composition for these.

## Delivery recommendation

For external professional delivery through WeChat or similar chat tools, default to:

1. one formal PDF as the complete credible artifact;
2. 3–6 image cards as the low-friction forwarding layer;
3. HTML as the iterative/rendering mother format, not necessarily the final user-facing artifact.

Avoid making pure images the only deliverable unless the task is explicitly a lightweight poster/social share. Pure images are easy to forward but weak on search, copy, citation, accessibility, and evidence chain.

## PDF conversion notes

HTML images generally convert to PDF reliably when:

- images are local static assets;
- semantic images use `<img>`, not only CSS backgrounds;
- print CSS sets `max-width: 100%`, `height: auto`, `break-inside: avoid`;
- `print-color-adjust: exact` / `-webkit-print-color-adjust: exact` is used where needed;
- the renderer waits for assets before printing.

PDF will flatten most HTML interactions. Keep interaction in HTML; use PDF for formal archival; use PNG/JPG cards for social spread.
