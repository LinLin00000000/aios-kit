---
name: skill-governance
description: "Use when a Skill needs lifecycle, canonical-source, provenance/license, manifest, runtime projection, install-state, adoption, deprecation, deletion, or rollback governance. Route authoring and evaluation mechanics to skill-creator."
license: Apache-2.0
metadata:
  formal_id: skill-governance
  version: "0.1.0"
---

# Skill Governance

This is the narrow first-party owner for Skill lifecycle and source/projection integrity. It governs how a Skill moves between lifecycle states; it does not author every Skill, own every audit, or manage general workflows.

## Owner contract

For a lifecycle-changing request, establish one canonical source and classify every other surface before mutation:

| Surface | Classification |
|---|---|
| Canonical Skill package | The single editable source of truth |
| Owner manifest | First-party or external ownership declaration and routing metadata |
| Runtime path | Derived projection or owner-created link; never a second source |
| Install-state | Actuator-written deployment receipt; never an editable registry |
| External companion | Separately licensed package with its own source and owner |
| Audit material | Read-only evidence that may inform a gate but grants no write authority |

A path's existence does not establish ownership. Resolve its realpath, provenance, license, manifest class, install-state row, and active consumer before treating it as current.

## Non-ownership boundaries

This Skill does not own or choose:

- decision methods or human trade-offs;
- USER/profile preferences;
- Matter, LLL, task, recovery, or evidence state;
- workflow topology, worker orchestration, or domain acceptance criteria;
- CLI semantics, product direction, or general product governance;
- Policy, service, Capability, Resource, or Secret state.

It must not become a God Skill, universal workflow manager, registry, daemon, broker, approval engine, authorization engine, or background reconciliation service. Domain owners retain their criteria; deterministic actuators retain execution semantics.

## Provenance and companion boundary

Treat provenance and license as entry gates, not cleanup details.

- Record the origin, ownership class, license, and local-change policy before adoption or synthesis.
- Reuse concepts only when a new first-party Skill is synthesized from external practice; do not copy external prose, body text, scripts, templates, assets, or code without an explicit licensed vendoring decision.
- Keep Anthropic's external `skill-creator` package as an Apache-2.0 authoring, evaluation, viewer, description-optimization, and packaging companion. Its files, code, templates, and `LICENSE.txt` remain external and independently owned.
- Keep `skill-library-governance/references/` as specialized read-only audit material. Those references may support reconciliation evidence but do not own lifecycle mutation.

A license mismatch, missing provenance, ambiguous owner, or same-name competing source fails closed.

## Lifecycle gates

Every operation has a bounded gate and a receipt:

### Create

1. Confirm that no same-name canonical source, manifest entry, runtime target, or install-state row exists.
2. Select the canonical first-party source and license before creating content.
3. Prepare and validate a task-local candidate before touching live surfaces.
4. Add exactly one owner-manifest entry and project it only through the declared owner actuator.

### Revise

1. Freeze the expected-current source identity and full package manifest.
2. Classify sibling files, runtime projections, install-state, and unrelated Git dirt separately.
3. Change only the canonical source; let the owner actuator update derived state when required.
4. Reject stale-base or parallel-writer drift instead of rebasing silently.

### Validate

1. Run the narrow structural validator against the candidate or canonical source in an isolated interpreter.
2. Run the owner doctor and an actuator dry-run using installed syntax.
3. Read back source, manifest, projection, install-state, package siblings, provenance/license, and runtime inventory.
4. Report focused checks precisely; independent acceptance remains a separate gate.

### Adopt

1. Prove the external origin, license, complete package boundary, current consumer, and durable need.
2. Choose explicitly between keeping the package external, a concept-only first-party synthesis, and licensed vendoring.
3. Prevent same-name dual ownership and preserve upstream attribution when vendoring is actually authorized.
4. Never convert local runtime edits into first-party ownership implicitly.

### Deprecate

1. Identify current consumers and the replacement owner or explicit no-replacement outcome.
2. Freeze a recoverable preimage and define the compatibility interval.
3. Thin old entries to non-competing routing only when compatibility remains necessary.
4. Keep deprecation distinct from deletion and runtime removal.

### Delete

1. Require explicit deletion authority, zero current consumers, and a verified rollback source.
2. Remove only the exact owner-managed surface named by the transaction.
3. Refuse broad cleanup, reference deletion, or curator archival as an implied side effect.
4. Read back absence and preserve the deletion receipt with provenance.

## Serialized transaction protocol

Use one rollback-safe writer for shared Skill ownership surfaces.

1. **Freeze expected-current.** Record path, realpath, type, mode, bytes, SHA-256, full package manifests, owner manifest, install-state, Git HEAD/status/staged state, protected unrelated paths, and running writer processes.
2. **Bind scope.** Declare the exact live write set, task-local evidence root, owner actuator, required absences, and stop conditions. A runtime loader, audit result, or receipt does not expand authority.
3. **Seal preimages.** Copy exact mutable-file preimages and record absence identities for new paths, links, and rows before the first live write.
4. **Validate the candidate.** Use the package's structural validator in isolated mode. Inspect the owner actuator's help and dry-run; stop if it predicts unrelated mutation.
5. **Recheck immediately.** Compare every expected-current identity, package manifest, Git boundary, required absence, and writer gate immediately before the first live write.
6. **Apply through owners.** Write the canonical source and owner manifest, invoke the existing owner actuator for projection/install-state, and change a compatibility route only within its exact package boundary. Do not fabricate a runtime link or install-state row by hand.
7. **Read back exactly.** Verify one canonical source, one owner-manifest entry, one matching install-state row, one owner-derived projection, byte equality, unchanged pre-existing rows, preserved siblings/licenses, clean doctor/dry-run, and runtime inventory visibility.
8. **Rollback on any focused failure.** Atomically restore exact file preimages and remove a newly created source or projection only while each still matches this transaction's postimage. Then verify rollback and record the failure without claiming acceptance.
9. **Seal evidence.** Record preimage/postimage hashes, commands, exits, focused checks, rollback disposition, and `accepted=false` until independent validation.

Expected-current, preimage, postimage, rollback, and readback are one transaction contract. None may be inferred from an earlier audit.

## Safe owner routing

- Skill lifecycle, canonical source, ownership class, provenance/license, manifest/projection/install-state classification, adoption, deprecation, deletion, and rollback route here.
- Drafting, editing craft, trigger evaluation, benchmark/viewer operation, description optimization, and packaging mechanics route to the external `skill-creator` companion.
- Specialized library, loader, Curator, provenance-drift, overlap, consumer, and package-coherence investigations may use the compatibility package's read-only references.
- Decision framing routes to its decision-method owner; Matter/LLL, workflow topology, domain criteria, CLI behavior, Secret state, and product governance route to their exact owners.

When routing is ambiguous, resolve the current owner and stop before mutation rather than creating another source or management layer.

## Focused acceptance boundary

A successful producer transaction establishes an applied candidate only. Acceptance requires fresh independent validation of the sealed postimage. This Skill grants no commit, push, publication, deployment, restart, permission expansion, or cross-owner migration authority.

## First-party provenance

`skill-governance` is an Apache-2.0 first-party synthesis of lifecycle and source/projection governance concepts. It contains original narrow guidance. No external `skill-creator` prose, body text, scripts, templates, assets, or code is copied. The external companion remains separately licensed and owned.
