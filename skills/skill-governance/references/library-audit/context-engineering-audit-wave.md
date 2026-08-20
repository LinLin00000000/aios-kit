# Context-Engineering Audit Wave

Use this reference for a durable, analysis-only review that spans Hermes memory/profile, project context, Skill loading, AIOS Project/Matter/Workflow semantics, LLL execution, delegated workers, and closeout. It complements `global-hermes-lll-workflow-simplification-audit.md` (classification) and `aios-lll-lineage-and-provenance.md` (lineage).

## Goal

Explain the **effective context and authority chain**, identify where one behavior has multiple executable owners, and compare simplification options without accidentally implementing them.

Optimize for one semantic owner plus thin projections—not one giant context file or the smallest directory count.

## Truth and precedence model

Keep these layers distinct:

```text
current user instruction
  > current Matter / Worksite mission
  > current instance Local Workflow Policy
  > portable product/Skill defaults

Hermes config       = runtime capacity, profiles, toolsets, loading/compression switches
memory / profile    = stable user preferences, stable environment facts, short owner pointers
project context     = repository-scoped development and safety constraints
Skill               = portable trigger, procedure, judgment, and routing
AIOS registry / OPS = current resources, bindings, and instance facts
Matter              = durable identity, lifecycle, owner, acceptance, and relations
LLL Worksite        = one execution/recovery/evidence scene
CLI / script        = deterministic query, mutation, and verification
session history     = interaction/provenance evidence, not current operational state
```

A projection becomes a second policy owner when it contains enough trigger, ordering, topology, reviewer count, receipt timing, delivery choice, or recovery semantics to execute independently.

## Durable admission and setup

1. Freeze the user's requested scope, especially `analysis-only`, no-publication, no-service-change, and protected-owner constraints.
2. Read current owner files first. Use old Worksites and session history only for provenance or rationale.
3. Verify the active profile, workspace/cwd, and non-secret root selectors before resolving registries or context files. Use explicit read-only selectors when the runtime provides them; do not persist a diagnostic override as policy.

### Carrier-scoped runtime observations

Parent WebUI/gateway, delegated child, cron run, and direct CLI may normalize `HOME`, `HERMES_HOME`/`HERMES_REAL_HOME`, `PATH`, `cwd`, or AIOS-root selectors differently. Bind each observation to `(surface, process/session, carrier, selector source, timestamp)` rather than collapsing them into one “current environment.” A child seeing a clean root does not invalidate parent-surface drift, and a parent observation does not prove the child’s effective context; treat the difference as a carrier-boundary fact. Validate the selected root through the owning CLI with an explicit read-only selector when available. A one-shot environment override is diagnostic evidence, not a durable workaround or policy change.

4. Decide the smallest honest structure:
   - chat-only for disposable, one-turn reasoning;
   - Lite for one durable producer;
   - full LLL only for genuinely orthogonal evidence tracks, recoverability, or independent validation.
5. When a durable Worksite is required, create `mission.md`, task records, recovery, and write boundaries before launching workers. If durable escalation happens after work already started, record the late registration honestly; never backdate or imply that pre-existing work was already governed by files that did not yet exist.

## Formal Matter↔Worksite attach and rollover

A human-readable `parent_matter_id` in `mission.md` is useful lineage evidence, but it is **not proof that the current Matter index or CLI consumes the relation**.

Before claiming formal attachment:

1. Read the current Matter schema/source and the Worksite's `internal/matter.json` contract, if any.
2. Query the current Matter discovery surface and exact Matter readback.
3. Distinguish a formal Matter from an `inferred_worksite` or other derived index row.
4. Verify parent/child or predecessor/successor relations in every direction required by the live schema.
5. Verify the current Worksite pointer/role and recovery locator; keep the predecessor Worksite read-only.

For a same-Matter successor wave, use the supported atomic rollover/`continues_in` contract. Do not blindly copy a duplicate Matter ID, mutate a completed snapshot, or invent a parallel `matter.json` merely to make a derived View look linked. If no supported attach/rollover actuator exists, persist an explicit partial relation in the new Worksite, report the projection gap, and avoid success-shaped claims.

## Evidence tracks and isolated-child context

Split only orthogonal questions, for example:

- AIOS / Matter / LLL authority and lifecycle;
- Hermes context assembly and loading modes;
- duplicate execution semantics and hotspot ranking;
- option design and long-term product consequences.

Workers must not share canonical write surfaces. Treat delegated children and fresh cron sessions as isolated consumers: they may not inherit parent memory, profile, project context, or prior tool results.

Pass a compact derived context bundle:

```yaml
mission: <absolute mission locator>
current_owner_locators:
  - <policy / registry / source paths>
owner_identity:
  - <optional hash, version, or updated_at>
scope:
  allowed_reads: [...]
  allowed_writes: [...]
constraints:
  - no secrets
  - no protected-owner mutation
  - no implementation
acceptance:
  - <task-specific evidence and verdict>
output:
  handoff: <task-local path>
```

The bundle is a frozen **read-set receipt**, never a new truth owner. Prefer locators plus bounded facts over copying complete memory, policy, or project documents into every prompt.

## Handoff and callback recovery

- A child return or live transcript is external evidence until the supervisor persists it in the task-local handoff and records provenance.
- Do not claim that a worker wrote files it could not or did not write.
- Missing completion delivery is a carrier/lifecycle problem, not automatically a content failure.
- Salvage only settled, verifiable evidence. If the source reads are complete but the final callback is missing, use an explicit `completed_with_notes`/`NO_VERDICT` classification and state which conclusion was supervisor-synthesized.
- Do not duplicate-dispatch while a live carrier may still write the same canonical target. Either wait for a bounded completion gate, prove the carrier is terminated, or give a replacement a disjoint output path and serialize the final promotion.

## Canonical synthesis and validation

1. Freeze all accepted evidence handoffs.
2. Assign exactly one canonical producer for each root deliverable. The supervisor remains the control plane unless it is explicitly the producer.
3. Allow the producer to write only the root report and its task-local receipt/handoff.
4. Freeze candidate bytes/hash after the last producer write.
5. Run one independent, read-only focused validator against the settled candidate. Validate facts, owner boundaries, option orthogonality, and no-implementation scope.
6. Any post-freeze candidate edit invalidates the verdict; refreeze and rerun the focused validation once.
7. Close task/queue/recovery state only after fresh readback. Keep worker logs and raw evidence internal; link the one canonical report to the user.

## Loading and ownership matrix

For each context surface, record:

| Field | Question |
|---|---|
| Semantic owner | What question does this source answer? |
| Discovery | Which loader, registry, Skill, or user locator finds it? |
| Load timing | Always-on, session-build, trigger-loaded, tool-call-loaded, task-local, or historical? |
| Scope/lifecycle | Global/profile, project, Matter, Worksite, task, or session? |
| Consumer | Parent agent, child, cron, CLI, viewer, or human? |
| Merge/precedence | What can override it, and how is a conflict surfaced? |
| Copy vs pointer | Does the consumer need full semantics, a bounded transport contract, or only a locator? |
| Verification | What readback proves the effective value? |

Classify findings as necessary layering, reasonable thin projection, duplicate executable semantics, explicit conflict, or immutable history.

## Option design discipline

Keep simplification routes orthogonal:

1. **Owner contraction + thin pointers** — lowest complexity; remove executable algorithms from memory, sidecars, and project projections while preserving genuine user preference and portable procedure.
2. **Derived per-run context manifest/receipt** — targets child/cron handoff and root drift; locators/hashes only, never a second policy registry.
3. **Declarative policy registry/compiler** — strongest generated-projection deduplication but introduces schema, generator, validation, and migration machinery. Consider only after repeated measured multi-owner drift.
4. **Profile/toolset/Skill-surface reduction** — targets always-on token/attention cost, not semantic ownership. Avoid profile splitting unless measured prompt noise justifies its synchronization tax.

Recommend the smallest route that fixes the measured failure. Do not combine all four into an unbounded platform project.

## Focused closeout checklist

- [ ] Current owners were read before history.
- [ ] Profile/workspace/root selectors were verified without exposing secrets.
- [ ] Context surfaces were classified by load timing and lifecycle.
- [ ] Matter/Worksite relation was read back; inferred linkage is not called formal.
- [ ] Worker contexts were explicit and task-local.
- [ ] Returned summaries have provenance; no worker-authorship fiction.
- [ ] One root canonical report exists.
- [ ] Four options are distinct and include cost, risk, reversibility, and trigger conditions.
- [ ] Candidate is frozen before independent validation.
- [ ] No policy, memory, Skill, project source, service, or publication boundary changed during an analysis-only wave.

## Pitfalls

- Do not assume a product concept has a same-named CLI actuator; inspect the installed command surface and current docs/source.
- Do not equate file count, symlink count, or loader visibility with multiple truth owners.
- Do not use memory as a compatibility patch for missing registry/actuator behavior.
- Do not copy a mutable current catalog into a thin sidecar.
- Do not make child prompts depend on implicit parent context.
- Do not launch parallel canonical producers or validators before the candidate is frozen.
- Do not let a long synthesis worker expand back into a fresh source audit; give it frozen handoffs and a narrow write contract.
- Do not turn an analysis report into implementation authorization through prescriptive language or hidden writes.
