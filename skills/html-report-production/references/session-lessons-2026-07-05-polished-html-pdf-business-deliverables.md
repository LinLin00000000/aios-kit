# Session lesson: polished HTML/PDF business deliverable kickoff

When the user asks for multiple polished HTML source files plus PDFs for a serious business/product deliverable, the first step is not writing the report. The first step is to establish a durable alignment contract so the visual polish does not disguise weak assumptions.

## Recommended sequence

1. If the work is multi-session or explicitly LLL-backed, create/update the LLL workdir first and keep HTML/PDF artifacts as root deliverables while process state stays under `internal/`.
2. Capture the user's raw project brief under `internal/inputs/` before summarizing it into polished prose.
3. If the user provides a reference URL/workdir and it is inaccessible, record the access result as an input/status note and ask for screenshots, zip, or a public link; do not block the whole project if the reference is mainly stylistic.
4. Before drafting, ask a compact first-round alignment set:
   - primary audience and usage scenario;
   - role/identity the user wants to project;
   - confirmed product facts vs unknowns;
   - visual style direction;
   - deliverable count/scope;
   - sensitive topics to avoid or soften;
   - intended tone: discussion draft, operational plan, strategic proposal, or cofounder pitch.
5. Only after alignment, define the report package information architecture and the reusable HTML/CSS design system.

## Content safety for polished business reports

Polish increases persuasive force, so preserve epistemic boundaries:

- mark unconfirmed pricing, customer cases, partner policies, competitive claims, and product capabilities as assumptions or `[待确认]`;
- separate facts, strategic assumptions, proposed experiments, and founder/team decisions;
- avoid making legal/commercially sensitive structures such as multi-level distribution sound finalized unless confirmed and compliant.

## Format discipline

- Honor the user's requested final surface: if they ask for HTML and PDF, do not deliver Markdown as the final artifact, though internal LLL state may remain Markdown/JSONL.
- Treat HTML as the primary iterative review surface unless the user says otherwise. Users often need to reread, comment on, and aesthetically judge the HTML several times before a PDF snapshot is useful.
- Prefer a shared report kit: fixed CSS/templates plus structured content slots, not unrelated bespoke HTML/CSS per file.
- Do **not** rebuild/export PDFs after every content edit by default. Export PDFs at milestones, final delivery, or on explicit user request; keep the PDF as a snapshot of the current approved HTML.
- Before milestone/final delivery, export PDFs and visually inspect rendered pages. If vision tooling is unavailable, still verify HTML loads, CSS links resolve, console is clean, file sizes/paths exist, and record the visual-QA limitation.

## Multi-session recovery for report packages

- Add a root `README.md` in serious report workdirs that tells future sessions exactly how to resume, which root HTML files exist, and which internal files are Hot/Warm/Cold.
- Do not label every file as hot just because the workdir is young. Hot files are the task contract, product facts/evidence map, style brief, package outline, current HTML drafts, and recovery state; raw crawls, generated assets, logs, and full JSONL streams remain warm/cold.
- When evidence comes from a chat export or team discussion, create a concise evidence map under `internal/inputs/` and keep claims tiered as public source / team oral statement / user proposal /待确认.
