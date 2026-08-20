# AIOS/LLL Matter–Worksite lineage and provenance audit

Use this reference when a user sees many related “matters,” child objects, LLL workdirs, reports, or history entries and asks why they are split or whether they should be merged.

## 1. Evidence order

Read in this order:

1. The user's current clarification and requested scope.
2. Current formal Matter files (`internal/matter.json`) and their `parent`, `relations`, `lifecycle`, owner, and current focus.
3. The candidate Worksite `mission.md`, `internal/recovery.json`, `internal/validation.json`, and root canonical deliverable.
4. The current source implementation/docs for index and View behavior.
5. Historical Worksite missions/reports and session history, only to reconstruct why a decision was made.

Do not treat a chat summary, static Matter View, or persisted index as current truth without reading the source Worksite/Matter files.

## 2. Classification table

| Surface | Canonical role | Promote to a Matter? |
|---|---|---|
| Formal `internal/matter.json` | Stable identity, lifecycle, owner, acceptance boundary | Already a Matter |
| Canonical LLL Worksite | One file-backed execution/recovery scene for a Matter or mission | No, unless it is the newly formalized owner identity |
| `internal/agents/Txxx` / task rows | Bounded internal work unit or worker evidence | No by default |
| Root Markdown | One human canonical deliverable | No |
| Managed asset | Selected reusable snapshot/decision surface | No; it is an asset |
| Index/View | Rebuildable discovery/read projection | Never a second truth source |
| Session/history | Interaction and provenance evidence | Never current operational state |

A child Matter is justified only when it has an independent target, lifecycle, owner/security boundary, writer/recovery boundary, or acceptance gate. Ordinary chapters, research lanes, and temporary branches stay tasks or evidence.

## 3. Lineage decision

Use one of these relations explicitly and include its scope:

- `source` / `informs`: evidence or prior research used by a later mission;
- `absorbs`: a later canonical synthesis replaces several active outputs without deleting their provenance;
- `continues_in` / `successor`: a later Worksite carries the same durable subject after a closeout or material mission change;
- `supersedes_for_scope`: a later decision replaces an earlier decision only for a named scope;
- `policy_addendum_to`: a cross-task policy change belongs beside, not inside, the product Matter.

Reuse an active/reopenable Worksite for a narrow correction or addendum. Create a new Worksite when the mission, owner, acceptance contract, trust/publication boundary, or writer/recovery boundary materially changes, or when the predecessor is closed and non-reopenable. A new Worksite must name its predecessor and the superseded/continued scope; otherwise the discovery surface will look like duplicate work.

“Merge” normally means **merge the current decision/operational surface**, not delete or physically concatenate old Worksite directories. Retain historical Worksites read-only when receipts, hashes, raw evidence, or provenance depend on them.

## 4. Derived-index traps

Check the index implementation and live snapshot for these false signals:

- closed/inactive Worksites defaulting to a `current` attention label;
- generic `LLL Mission` titles masking semantic names in directory slugs;
- inferred Worksites lacking aliases or predecessor/successor fields;
- a full discovery index being used as the user's current-work queue;
- static HTML/View copies being mistaken for canonical state;
- a changing count being recorded as a durable product fact.

Fix grouping, title/alias extraction, lifecycle presentation, and lineage metadata before deleting evidence. The simplest current-work query is usually the active + reopenable subset, while the full index remains an audit/discovery surface.

## 5. Focused verification

Before closeout, verify:

- all historical claims point to a mission/report or session-history result;
- current claims point to live Matter/Worksite files or current source code;
- exactly one current canonical human deliverable exists for the mission;
- predecessor/successor relations identify scope and lifecycle;
- parent/child Matter IDs agree in both directions where applicable;
- the Worksite recovery and validation files are readable;
- no historical Worksite was silently moved, deleted, or overwritten;
- the final report distinguishes canonical truth, retained provenance, and derived projections.

Useful read-only probes:

```bash
aios matter index --dry-run --json
aios matter list --state active --reopenable --json
aios lll status <worksite> --compact --json
```

## 6. Reporting shape

Lead with the user's apparent duplication and answer it directly. Then provide:

1. a short timeline: source missions → merged baseline → successor/addendum;
2. a layer model: Matter / Worksite / task / artifact / projection / history;
3. necessary vs accidental complexity;
4. a minimal current operating rule;
5. exact evidence paths and a focused verification result.

Do not recommend a new registry, workflow engine, dashboard, or parallel state machine merely to make lineage visible. Prefer the existing Matter metadata, mission addenda, derived View grouping, aliases, and one canonical report.
