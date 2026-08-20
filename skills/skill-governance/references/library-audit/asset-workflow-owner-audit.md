# Asset and Workflow Owner Audit

Use this reference when a governance task crosses Worksites, policy, skills, deterministic CLI, OPS/registries, project sources, Managed Assets, and derived views.

## Audit order

1. Read the current Matter/Worksite contract and compact recovery/validation state.
2. Identify the current policy owner and precedence; treat old Worksites and decision reports as evidence, not current behavior.
3. Read the portable product/protocol owner, then the thin skill/sidecar entry that routes to it.
4. Inspect the deterministic CLI implementation and focused tests before proposing new state or a new actuator.
5. Inspect Managed Asset receipts/manifests and the current Source/Project/OPS owner metadata.
6. Read only the compact mission/protected-path boundary of parallel active work; avoid its bulky evidence/cache.

## Evidence matrix

For each disputed rule or asset, record:

| Field | Question |
|---|---|
| Fact class | Current policy, operational state, project source, current OPS fact, selected asset snapshot, or derived projection? |
| Canonical owner | Which exact file/repo/registry owns the current truth? |
| Other surfaces | Are they pointers, runtime links, indexes, views, snapshots, caches, or historical evidence? |
| Time semantics | Current mutable truth or frozen point-in-time evidence? |
| Allowed action | Read, rebuild, correct pointer, copy-only promote, owner-scoped edit, or append correction? |
| Prohibited action | Duplicate current truth, overwrite, move, delete, bulk curate, expose, or read secret values? |
| Gate | Owner quiet, Agent assessment, human authorization, production gate, exact restore, or destructive confirmation? |
| Verification | Exact readback, schema parse, hash/file-set check, registry doctor, focused test, or consumer-side probe? |

## Closeout projection

Default to:

```text
source Worksite retained as full provenance owner
  -> one canonical human deliverable
  -> exact evidence pointers (path + role; hash when frozen)
  -> explicit retention intent
  -> authorized copy-only/no-overwrite promotion
  -> Managed Asset receipt
```

Keep raw evidence, reviewer chains, derived HTML/PDF/screenshots, renderer diagnostics, virtual environments, and caches in the Worksite unless independently selected. Excluding them from the active/promotion surface is not deletion authorization.

A closeout plan, retention score, `asset_candidate` label, validation report, or undo precondition check is advice/evidence—not authorization to promote or delete.

## Split broad change sets by authority

| Change class | Typical owner/gate |
|---|---|
| Documentation or locator correction | Exact document/registry owner; focused readback |
| Registry identity or alias migration | Registry owner; dry-run/validate; no content move |
| Access, share, or exposure change | Service owner plus explicit human UX/security decision |
| Backup scope or sensitive app-state coverage | Data-protection owner, production gate, deployed readback, isolated restore |
| Cross-location or bulk move | Fresh inventory/projection plus explicit human confirmation and rollback manifest |
| Permanent deletion | Fresh recovery evidence plus separate destructive authorization |

Do not keep these bundled merely because an old report used one change-set id.

## Drift handling

- **Frozen receipt/manifest drift:** preserve the historical bytes and hashes; resolve the current locator separately and add a correction pointer in the current owning synthesis.
- **Thin catalog drift:** remove copied policy/current-state enumerations and keep a dynamic pointer to the owner instead of adding the newest missing item.
- **Runtime symlink drift:** classify realpath and install-state mismatch as projection/management metadata drift, not automatically as a content fork.
- **Historical summary omission:** inspect the machine change set/status before concluding that an omitted item never existed or ran.
- **Parallel dirty work:** treat declared paths as a hard no-overlap manifest; do not stage, reformat, migrate, or absorb them from a neighboring task.

## Thin reciprocal linkage between method and domain owners

Use this pattern when a portable, cross-domain method Skill and a domain-specific governance philosophy overlap and need durable reciprocal discovery without duplicated truth.

1. **Freeze the authority graph before designing links.** Separate the portable method owner, domain philosophy owner, current instance-policy owner, per-wave Worksite, implementation owner, and derived projections. A shared vocabulary does not collapse these roles.
2. **Audit reference and provenance status independently.** Search both canonical trees and any source manifest/receipt. Semantic overlap may justify a current applicability pointer, but if the manifest does not name the Skill, do not retroactively claim `derived_from`, authorship, or source provenance.
3. **Keep complete principles at their existing owners.** The method Skill owns its reusable procedure, classifications, output shapes, and anti-patterns. The domain source owns its accepted principles, authority map, lifecycle/admission gates, evidence lineage, and domain application results. Domain examples may use the method vocabulary without copying the method body.
4. **Prefer a two-pointer write set.** Add one responsibility sentence in the method Skill pointing to a stable domain object ID plus a verified resolver. Add one responsibility sentence in an already-current domain owner map or policy pointing back to the Skill ID. If the frozen domain snapshot already links that current map, use the existing chain instead of creating a third pointer document.
5. **Use portable identifiers, not locator snapshots.** Prefer a stable Skill name and Matter/asset ID with a demonstrated read-only resolver. Avoid profile-specific or dated absolute paths, fragile cross-home relative links, content hashes as “latest” locators, and invented URI schemes that no consumer currently resolves.
6. **Do not thaw completed evidence for link hygiene.** Leave completed Worksite mission, snapshot, matter/events, recovery, validation, source manifest, review packet, and closeout unchanged. A frozen packet and the current live reading surface may legitimately identify different timepoints—for example, an in-flight candidate versus a deterministic terminal-state update. Preserve both; verify the new work by pre/post equality of the live protected surface rather than backfilling old receipts.
7. **Escalate literal-link requirements honestly.** If acceptance explicitly requires each full canonical document to contain a direct backlink, and one document belongs to a completed Worksite, a current mutable bridge is not equivalent. Require a named owner and a bounded successor Worksite/current snapshot; never append an unvalidated sidecar or silently rewrite the predecessor.
8. **Run a focused closeout.** Freeze an exact changed-file allowlist; assert each reciprocal ID appears only where intended; ensure the diff contains no copied principle tables, dated paths, private roots, hash pins, or invented schemes; execute both resolvers; recompute protected hashes; and use one independent changed-surface review rather than replaying the predecessor's full registration validation.

This pattern optimizes for one fact owner, one current resolver path, and no synchronization duty. It is an owner-level reciprocal linkage; call it “direct document-to-document” only when both canonical documents literally contain the links.

## Candidate statuses

Use explicit dispositions:

- `implement_now`: same owner, low risk, reversible, focused verification available.
- `conditional_implement_now`: safe only after exact path claim and parallel-task deduplication.
- `keep_no_change`: current boundary already correct; more mechanism would add tax.
- `owner_gate`: wait for the authoritative owner or protected activity to quiesce.
- `human_gate`: access, exposure, bulk movement, publication, backup scope, or destructive impact.
- `defer`: no present friction or prerequisite evidence; retain the trigger for reopening.

## Read-only capability-gap audits in shared dirty repositories

Use this pattern when translating prior research or architecture decisions into a small, conflict-free implementation queue while another owner is actively changing nearby files.

1. Read the current mission/task contract and the prior synthesis; do not reopen completed ecosystem research unless the current implementation contradicts it.
2. Freeze two repository surfaces separately:
   - **protected owner surface:** branch, HEAD, exact dirty paths, and hashes for modified/untracked files owned by another task;
   - **candidate surface:** proposed code/test/doc paths, which must be tracked-diff empty before assignment.
3. Inspect current implementation, focused tests, and real CLI help. Classify each researched capability as `implemented`, `partial`, `missing`, or `parallel_covered_pending_acceptance`; never promote a worker self-report or dirty diff to accepted capability.
4. Identify the repeated deterministic labor still performed by the Agent: command discovery, argument/order selection, path/result inference, manifest/hash creation, stale-write checks, or state-projection reconciliation.
5. Apply the reduction order: **subtract duplicate state -> add the smallest typed contract -> add the smallest actuator -> add deterministic reconciliation -> measure before runtime/platform upgrade**.
6. Keep at most ten semantically orthogonal candidates. Each needs current evidence, exact owner/repo/path/function, smallest implementation, focused test, conflict/serialization decision, non-goals, and rollback. If several candidates touch the same central file, keep them in one serial owner lane rather than calling them parallel-safe.
7. For watcher/recovery ideas, distinguish a deterministic worker root from declared expected outputs. A conventional `handoff.md` path is not an output manifest, and worker-reported status is not canonical completion. Add typed outputs/finalize/readback before adding a watcher or model proposal.
8. Re-freeze both surfaces after the audit. Candidate-surface drift is a stop/serialize signal. Drift confined to the protected owner surface should be recorded with before/after hashes and current owner evidence, not attributed to the read-only auditor and not absorbed into its commit.
9. Keep external engines, observers, and cheap-model nodes deferred until named activation gates are observed. An engine cannot create missing semantic actuators or safely resolve duplicated authority.

A recommended first batch may contain only one cohesive candidate even when several later candidates are ready. Preserve that narrow acceptance surface instead of bundling independent repositories for symmetry.

## Evidence-gated simplification candidate ledgers

Use this pattern for a strictly read-only audit that spans Worksites, runtime Skills, Managed Data, and rebuildable/generated assets.

1. **Freeze scope and relationship metadata.** Name the exact roots, Project/Source/Matter registries, active parallel boundaries, allowed output files, and snapshot time. Inventory by metadata first; do not read secret values or broad private bodies merely to improve confidence.
2. **Separate semantic count from physical space.** Count canonical top-level Worksites and active skill roots, excluding nested evidence copies and registered legacy containers from the active population. Measure allocated bytes with a hardlink-aware tool such as `du -s --block-size=1`; naïvely summing `st_blocks` per pathname can double-count hardlinked content. Record that reflinks, sparse files, and concurrent writes can change actual reclaim.
3. **Compile projections without writing.** Compare persisted Matter `generated_at`, membership, and statuses with the owner compiler's explicit dry-run (for AIOS, `aios matter index --dry-run --json`). Compare the static View page set separately. Treat differences as projection drift and nominate an owner-CLI rebuild after active writers checkpoint; never repair the index or View by hand.
4. **Audit Skills on four surfaces.** Reconcile active runtime roots and frontmatter names, realpaths/symlink targets, manifest/install-state ownership, and an owner sync/doctor dry-run. Distinguish exact duplicate names/content from semantic trigger overlap. A first-party symlink whose source evolved is not a copied fork; a dry-run that says `SKIP locally modified` is stronger evidence of a protected external local patch. Usage-key aliases and stale absorbed-component records can split consumer history, so zero recorded use is only a profile-review signal, not deletion proof.
5. **Validate Managed Assets as immutable promotions.** Verify receipt/change-set schema, exact target file set, source and target hashes, owner resolution, and backup boundary with the owner validator. Separate real content divergence from historical/live metadata evolution. For example, a receipt frozen at backup `planned` while the live registry later becomes `verified` is normally a monotonic history/current-state difference, not a reason to rewrite the receipt; the validator should report it separately while still rejecting downgrades and hash drift. If source and target both diverge from the receipt and from each other, retain all versions, block overwrite, and require a human semantic owner plus a new superseding promotion.
6. **Demand five proofs before physical removal:** owner, rebuild, backup, consumer, and activity. For Git clones, check clean status, origin, exact HEAD, remote-tracking or network reachability, submodules/LFS, exact-path references, and current process cwd/fd consumers; persist a locator/commit manifest and retain one canonical copy when deduplicating. A broad inventory of clean remote-covered clones is not blanket deletion authorization.
7. **Protect active caches and weakly reproducible environments.** A cache label does not override active workers. For terminal virtual environments or vendored test dependencies, require a lock/version/rebuild receipt and a representative cold rebuild/test; a prior no-cleanup boundary remains binding until explicitly superseded.
8. **Produce a machine-checkable ledger.** Each candidate should carry `id`, classification, owner, evidence, current state, problem, value, cost, risk, reversibility, `decision_gate` (`auto|human|blocked`), recommendation, verification, exact paths, count, and allocated bytes or `null`. Keep protected assets, uncertainties, blockers, and actionability totals explicit.
9. **Default to retain when a gate is missing.** Only low-risk derived projections normally qualify for `auto`. Content authority, destructive deduplication, runtime-only skill retirement, external local patches, and rollback retention normally need a human. Active consumers, missing rebuild proof, and ambiguous semantic ownership are blocked.
10. **Verify the deliverable, not just the prose.** Parse JSON, assert every required field and gate enum, match `count` to exact path count, confirm candidate paths exist, reconcile gate totals, hash output files, and verify that only the authorized handoff/ledger files were written.

## Final checks

- One fact has one owner and every duplicate surface has a named projection role.
- Current truth and dated snapshots are not silently synchronized.
- `Cut` is labeled active-surface removal versus physical deletion.
- The source Worksite remains recoverable and the selected projection is independently understandable.
- No unexecuted change set is reported as applied.
- No active parallel path, secret value, registry, OPS truth, or Managed Asset was modified outside the granted boundary.
