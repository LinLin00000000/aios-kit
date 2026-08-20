# Global Hermes/LLL Workflow Simplification Audit

Use this reference when auditing an instance-wide Hermes/LLL workflow for structural tax, reviewer inflation, nested fan-out, or duplicated policy—not when reconciling one Worksite's task state.

## Core boundary

The audit proposes a smaller default without turning project-specific safety contracts into global rules:

```text
Hermes config       = runtime capacity and automation switches
Local Workflow Policy = current instance-wide behavior and precedence
memory/profile      = stable user preference and short routing hint
LLL local sidecar   = local LLL adapter and entry pointer
Matter/Worksite     = one run's state, authorization, evidence, and recovery
Skill               = portable procedure and judgment rules
CLI/script          = deterministic mechanics
```

Keep one truth owner per fact. A smaller file count is not success if it creates a second queue, hides provenance, weakens safety, or makes current behavior ambiguous.

## Read-only evidence wave

1. **Freeze scope and exclusions.** State that this is an instance-wide audit. Explicitly exclude remote-host names, one-shot admission IDs, project-specific permissions, task IDs, and Worksite-only constraints from global recommendations.
2. **Load the governing skills.** Read the active orchestration, simplification, skill-governance, and Hermes configuration guidance. Treat current installed source/docs as authoritative when skill prose and runtime behavior differ.
3. **Query effective configuration, not the whole file.** Use `hermes config get` for non-secret workflow keys and `hermes config path`. Do not print or inspect provider/key fields. At minimum capture:
   - `delegation.max_concurrent_children`
   - `delegation.max_spawn_depth`
   - `delegation.max_iterations`
   - `agent.max_turns`
   - `skills.creation_nudge_interval`
   - `skills.write_approval`
   - `curator.enabled`
   - `curator.consolidate`
4. **Confirm runtime semantics.** Inspect the installed Hermes docs/source if needed. In current Hermes semantics, `max_concurrent_children` caps batch/background delegation capacity; depth `1` is flat and depth `2` permits an orchestrator-to-leaf layer. Do not infer behavior from a stale default table.
5. **Separate automatic mechanisms.** `creation_nudge_interval=0` stops automatic post-turn Skill review but does not disable Skill loading or manual management. `skills.write_approval=true` stages writes and is an approval gate, not a noise switch. Curator lifecycle and LLM consolidation are separate; keep deterministic backup/archive safety unless evidence requires a quiet window.
6. **Read the current policy owner.** Find its declared authority, precedence, modes, and existing topology/reviewer rules. Do not copy the full policy into memory or a sidecar.
7. **Resolve the active LLL entry.** Reconcile runtime symlink/realpath, install-state or manifest, source repository, and any alternate clone. A sidecar next to the installed canonical source is active; a similarly named second clone is not automatically safe to delete. Treat it as an active-surface/ownership question, not a file-count question.
8. **Inspect memory/profile only for routing preferences.** Separate stable user preference from current host facts, Worksite state, provider facts, or project authorization. Flag entries that turn topology, review, receipt timing, delivery format, retry, or recovery into a second executable policy. Count entries and characters against effective limits, but classify by content rather than size.
9. **Run one bounded overlap scan.** Compare exact triggers and relevant rule contexts across policy, sidecar, memory, skills, and active project context files. Classify each hit as aligned, active conflict, conditional, or historical. A generic LLL rule that says every nontrivial task needs a model reviewer may conflict with a local risk-gated policy; resolve it by one owner/narrow pointer, not a second policy layer.
10. **Audit consumers, not only prose.** Record whether each surface is injected every session, trigger-loaded, repository-scoped, attached to cron/fresh-session prompts, or copied into delegated-worker contracts. A short projection becomes a second execution owner when it contains enough trigger, ordering, topology, or recovery semantics to drive behavior independently.
11. **Check runtime context and capability compatibility.** Compare non-secret root selectors such as `HERMES_HOME`, `HOME`, and an AIOS root override, then run a read-only status probe through the actual CLI. Separately compare effective capability gates with skill promises: a skill that authorizes child orchestrators requires a spawn-depth setting that lets those children spawn leaves. Treat a semantic/runtime mismatch as an explicit conflict, not prose overlap.
12. **Measure context tax by trigger × loaded body.** Record main-body bytes/chars/lines, trigger breadth, imperative-rule density, and reference split. Size alone is not a defect; a broadly triggered umbrella whose main body carries specialized repair protocols is. Prefer a compact trigger/invariant/routing body with low-frequency mechanics under `references/`.

## Classification discipline

Use five buckets:

- **Necessary layering:** semantic owner, lifecycle, consumer, or verification contract differs.
- **Reasonable projection:** a pointer or bounded consumer-specific summary cannot execute as an independent policy.
- **Suspicious duplicate execution semantics:** multiple live inputs state the same trigger, order, reviewer count, receipt timing, delivery decision, or recovery action.
- **Explicit conflict:** live surfaces require incompatible outcomes, or runtime capability/root resolution makes the documented behavior impossible.
- **Historical evidence—do not sync:** a frozen Worksite, event stream, validation receipt, or source manifest records capture-time truth. A later owner hash mismatch proves evolution, not permission to rewrite the snapshot.

Do not count path aliases as duplicate truth until realpath, inode, and content identity are checked. A source repo, module link, runtime Skill link, and compatibility work-root link can expose the same bytes. Conversely, similar wording in separately injected system memory and a selected Skill can be duplicate execution semantics even when the files live in different stores.

## Memory/profile and sidecar placement check

1. Confirm whether memory and user profile are enabled and how their frozen snapshot enters the system prompt.
2. Classify stable preferences and short owner pointers as valid; flag full mode gates, worker topology, retry/review algorithms, delivery matrices, and callback routing as policy/procedure candidates.
3. Compare `MEMORY.md` and `USER.md` for the same preference expressed twice. Two profile stores do not justify two active copies.
4. Compare a sidecar's declared role with its imperative content. A file that says “route only” but specifies first-reply behavior, worker-completion ordering, or history recovery is behavior-bearing.
5. Do not fix the audit by copying the current policy into memory or the sidecar. Identify which projections should become a pointer, parameterized override, or explicit transport contract.

## Default topology to recommend

- **Ordinary bounded work:** inline or one narrow worker, one focused deterministic readback, no separate model reviewer by default. Do not create workers merely to reach a count.
- **Complex durable work:** one Worksite, at most 2–3 genuinely orthogonal workers when independence and shared-runtime gates pass, one canonical producer per root deliverable, serial synthesis/closeout, and one independent validator only for non-trivial durable synthesis, multi-owner work, or an explicit risk gate.
- **Security/Secret/permission/public/irreversible/production-red-line work:** add the smallest independent validator surface that honestly covers the risk. Add another perspective only when the remaining risk axis is genuinely orthogonal; never use a fixed reviewer count as ceremony.
- **Reviewer/carrier failure:** classify transport/lifecycle failure separately from content verdict; repair the exact unresolved scope and use one bounded replacement review only when the material candidate changed. Do not recursively add reviewers.
- **Nested orchestration:** flat is the global default. Permit one child-orchestrator layer only when the subdomain has at least two orthogonal leaf scopes and flat routing would break bounded ownership or overload the controller. Enable it explicitly at a phase boundary, then restore the flat default.

A `2–3` figure is a ceiling/typical qualifying fan-out, never a quota. Shared files, ports, processes, locks, system units, one-shot budgets, and pending decisions can force serialization even when filesystem write roots are disjoint.

## Keep / Cut / Merge / Defer test

- **Keep:** one policy owner, one canonical producer, deterministic checks, frozen review surfaces, recovery/provenance, and red-line security gates.
- **Cut:** automatic reviewer for ordinary work, recursive reviewer-on-reviewer chains, duplicate policy prose, default nested trees, and unproven automation.
- **Merge:** duplicated routing/triggers into the owner; leave thin pointers in neighboring skills/sidecars; keep orthogonal state stores separate.
- **Defer:** physical deletion of an alternate clone, lowering iteration ceilings, new profiles/plugins, or Curator changes until ownership and usage evidence justify them.

## Config recommendation discipline

Recommend only changes that directly remove measured/default structural tax. A safe first pass often restores a runtime's flat/default capacity (for example, concurrency 3 and depth 1) and disables automatic Skill nudges while leaving iteration/turn ceilings unchanged until usage data shows truncation is not a risk. Apply changes only after active waves that depend on the old ceiling settle. Give exact rollback commands using the observed old values; do not claim a change was applied in a read-only audit.

## Strict read-only integrity

- Freeze hashes for audited policy, memory/profile, Skill/sidecar, project-context, and Matter targets; verify them again before delivery. Check scoped Git diffs separately from repository-wide pre-existing dirt.
- Distinguish audited-source immutability from tool-managed telemetry. Read/loader operations may update usage counters or access metadata; when strict no-write work cannot avoid platform bookkeeping, disclose the exact metadata surface and prove that no rule source changed.
- Treat a historical source manifest as immutable evidence unless its own contract says otherwise. Never refresh snapshot hashes merely because the current owner advanced.
- Keep root diagnostics process-local. A one-command environment override may prove a resolution split, but the audit must not persist it as a workaround.

## Hotspot ranking

Rank at most eight hotspots by `impact × trigger frequency`. Label the scale as an audit heuristic unless production counts exist. For each hotspot give the live surfaces, exact behavior at risk, why one edit currently needs several updates, and whether the remedy is owner consolidation, a thinner projection, runtime-config alignment, or historical non-action.

## Artifact and closeout

When writes are authorized, write one private Markdown proposal under the caller's work root. Include current values, recommendations, reasons, impact scope, owner/lifecycle/consumer placement, the five-category classification, Keep/Cut/Merge/Defer, hotspot ranking, rollback commands, and explicit no-change items. For a strictly read-only request, return the same evidence structure in the response and do not create an artifact merely for ceremony. In either case, fresh-read protected targets and verify hashes before delivery.

## Pitfalls

- Do not read the complete Hermes config when safe `config get` queries suffice.
- Do not equate `skills_list`/`skill_view` visibility with curator addressability or canonical ownership.
- Do not equate file count, symlink count, or stale snapshot hashes with duplicated current truth.
- Do not disable Curator merely to reduce file count, and do not confuse `creation_nudge`, write approval, Curator transitions, and LLM consolidation.
- Do not lower hard iteration caps solely because a workflow was verbose; truncation can create retries and more structural tax.
- Do not promote a project-specific remote/admission/security contract into global memory, config, or every LLL sidecar.
- Do not overwrite or delete a second sidecar until realpath, install-state, owner, and rollback are established.
- Do not treat project-context instructions as global policy without proving their repository scope and loader behavior.
- Do not claim “nothing changed” when platform usage telemetry moved; separate source integrity from bookkeeping and disclose both.
