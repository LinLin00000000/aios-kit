# Bounded Read-Only Skill Overlap Audit

Use this reference for a focused review of several workflow, policy, orchestration, domain, or meta-skill surfaces. It is a recommendation/evidence procedure, not an authorization to edit any source.

## 1. Scope and authority preflight

1. Read the current mission/contract and list the exact candidate files.
2. Read each current source directly before consulting old Worksites, session history, indexes, or reports.
3. Classify every source as current owner, projection/pointer, runtime/package detail, or historical evidence. Historical reports can explain why a boundary exists but cannot silently become the current policy.
4. Freeze the observed path, version/realpath when relevant, line count, and hash. Re-read volatile sources before delivery if concurrent owner movement is plausible.
5. Keep the audit write root separate from all source and shared state. Do not read or print Secret values.

## 2. Five-dimensional owner map

For each candidate object or rule, record:

| Dimension | Question |
|---|---|
| Semantic owner | Does it answer how to act, what is true now, what happened, or how to resume this run? |
| Lifecycle | Is it a versioned procedure, mutable instance policy, append-only history, package asset, or episodic Worksite state? |
| Consumer set | Is it consumed by a model, supervisor, worker, CLI/script, actuator, viewer, curator, or several of these? |
| Security/privacy boundary | Would copying it expose private facts, Secret metadata, runtime authority, or create a second writer? |
| Query/verification contract | Does it require freshness, exact filtering, schema/read-after-write, hashes, append semantics, or an independent verdict? |

If any dimension differs, keep the data/authority surfaces separate. Only duplicate prose, triggers, terminology, and routing glue should be candidates for consolidation.

## 3. Deterministic lexical scan

Run one bounded, reproducible scan over the candidate set. Record:

- exact input paths and observed timestamp;
- case-sensitive/case-insensitive and line-level counting rules;
- repeated concepts (`mission`, `recovery`, `validation`, `handoff`, `producer`, `reviewer`, `control plane`);
- exact command forms and flags (`lll ...`, `aios ...`, manager/curator commands);
- reciprocal route names and explicit exclusions;
- path/line numbers for each hit.

Interpret the scan conservatively:

- identical strings are candidate signals, never semantic proof;
- the same word may denote different owners (`validation` can mean Worksite validation, reviewer topology, product acceptance, or package doctoring);
- a command family should have one detailed schema/flag/algorithm owner; other skills may route to it;
- a high count in a reference can indicate contextual dominance even when the file is structurally subordinate.

Store the compact scan beside the audit artifact so a later reviewer can rerun it without importing raw source dumps.

## 4. Trigger and reciprocal-routing matrix

For each candidate skill, write:

| Field | Required answer |
|---|---|
| Primary trigger | What user intent makes this the first entry? |
| Optional companion | Which other skill is loaded only after a concrete gate? |
| Negative control | What superficially similar request must not load it? |
| Reciprocal pointer | Does the neighboring owner explain when to route here and what it does not own? |
| Active-surface cost | What unnecessary body/reference/command payload is avoided by route-first loading? |

Keep these axes separate:

- durable structure/recovery vs delegation carrier/topology;
- current instance policy vs portable procedure;
- product/protocol semantics vs daily execution;
- cross-domain subtraction method vs domain governance rules;
- skill-library ownership/upstream management vs ordinary task operation.

A missing reciprocal pointer is a routing defect, not proof that the skills should merge.

## 5. Disposition rules

Use the smallest honest disposition:

- **Keep orthogonal** when semantic owner, lifecycle, consumer, or verification differs materially.
- **Thin** when an entry skill should route and enforce a boundary but not repeat a full algorithm.
- **Merge duplicated prose/routing** when one owner can state the rule once without changing authority.
- **Move to reference** for exact commands, provider quirks, failure repair, long examples, evidence matrices, or session-specific detail.
- **Defer** physical merge, deletion, policy-engine creation, new registries, or carrier migration until a real trigger and reversible verification exist.

Common boundary decisions:

- Do not combine a durable Worksite kernel with a multi-agent topology skill into a mega-skill; connect them with short pointers.
- Do not copy a mutable Local Workflow Policy into a portable Skill or local sidecar; keep a pointer to the current owner.
- Do not turn product/protocol design, skill-library governance, and routine execution into one “everything” entry.
- Do not treat a historical Worksite recommendation or PASS as current implementation authority.

## 6. Minimal load order

1. Infer the smallest honest mode from current user intent and mission.
2. Load one narrow primary entry for the dominant job.
3. Read the current instance policy only when its scope/mode/precedence affects the task.
4. Add durable-workflow structure only when recovery, cross-stage evidence, or a durable write warrants it.
5. Add delegation/topology only when real independent tracks, worker ownership, reviewer independence, or cost gates warrant it.
6. Load exact references/actuators on demand.
7. Run one risk-matched focused verification and supervisor readback.

A large complete inventory is acceptable when the default/auto-trigger surface is narrow and heavier references remain on an explicit shelf.

## 7. Evidence artifact and closeout

A bounded read-only review should leave:

- one human-readable artifact with owner map, scan interpretation, disposition ledger, target structure, trigger matrix, limits, and evidence paths;
- one short handoff containing `status`, `verdict`, `outputs`, `checks`, `limits`, `next_owner`, and `next_action`;
- a task-local log of source reads, scans, writes, and verification;
- a fresh post-write check for UTF-8 decoding, zero NUL bytes, real newline bytes, required headings/records, exact write boundary, and SHA-256 hashes.

`PASS_WITH_NOTES` is appropriate when the bounded analysis is useful and grounded but live loader behavior, parent-worksite validation, or source-change verification remains outside the audit scope. Never report a recommendation as an applied change.
