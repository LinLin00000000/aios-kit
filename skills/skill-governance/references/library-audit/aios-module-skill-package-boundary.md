# AIOS module / Skill package boundary

Use this reference when an AIOS, OPS, or Hermes review asks whether a local protocol should be a Skill, whether private data may live under a Skill package, or whether several package/runtime entries should be merged.

## Core decision

A procedure Skill and an instance-data protocol can be **one package** without becoming one semantic owner:

```text
AIOS module/package
  = Agent-facing Skill entry + deterministic CLI + schema/template + tests/migrations
private instance layer
  = current facts + mutable state + history + permissions + receipts
```

This is package-level unity with storage/semantic ownership separation. It is valid to place a private `local/` or overlay directory under a Skill-managed package, but the package must explicitly define exclusion, precedence, update, backup, migration, and consumer rules. A directory name alone is not a privacy or lifecycle boundary.

## Typed layers

Before merging a directory or Skill, classify the payload:

| Layer | Owns | Typical question |
|---|---|---|
| Procedure Skill | trigger, routing, stable method, safety boundary | How should the Agent act? |
| AIOS module | CLI, schema, template, migration, tests, public exports | What is the reusable protocol package? |
| OPS/registry instance | current resources, service state, stable cards, history pointers | What is true now? |
| LLL Worksite | one run's mission, recovery, evidence, acceptance | What happened in this work? |
| Local policy | current instance defaults and precedence | How does this instance behave? |
| Actuator | CLI/script/SSH/Ansible/API side effect | How is the deterministic action performed? |

The same Markdown/JSON directory can contain members of several layers, but physical co-location does not transfer semantic ownership.

## Five-dimensional merge test

For every proposed merge or thin adapter, record all five dimensions:

1. **Semantic owner** — how/procedure, current fact, history, episodic evidence, policy, or execution?
2. **Lifecycle** — versioned package, mutable instance, append-only history, or per-run state?
3. **Consumer set** — Hermes model only, or also CLI, Ansible, cron, other Agents, viewers, and recovery tools?
4. **Security/privacy boundary** — would copying this payload create public leakage, a second write authority, or a wider Secret surface?
5. **Query/verification contract** — does it require exact filtering, freshness, schema/migration checks, append semantics, or read-after-write proof?

Merge duplicated prose, triggers, and routing glue when one owner can be authoritative. Do not merge orthogonal stores merely because they use the same file format or progressive-loading pattern.

## Progressive disclosure versus loader boundaries

A catalog → selected object → detailed reference → live check sequence is nested progressive disclosure. Keep these boundaries explicit:

```text
Skill index → exact module/service export → CLI query → selected card/reference
           → current instance facts/history → verification → controlled write-back
```

A module may contain multiple Skills, but a recursive Skill loader should receive **exact Skill roots**, not an entire module root containing another `skills/` directory. Support directories such as `references/`, `scripts/`, `templates/`, and `assets/` are not equivalent to nested companion `SKILL.md` exports. A first-wins name de-duplication hides a duplicate candidate; it does not establish stable provenance.

Recommended package shape:

```text
modules/<module>/
  module-manifest
  skills/<exact-export>/SKILL.md
  cli-or-scripts/
  schemas-and-templates/
  tests-and-docs/
```

The manifest should export each `skills/<exact-export>` separately. Keep live instance data at an explicit instance root or an explicitly governed private overlay; never let the loader become a second registry.

## Public package + private overlay contract

Treat the overlay as valid only when all of these are explicit:

- one authoring owner and one runtime projection rule;
- clean-package exclusion and public/private audit;
- deterministic precedence for public, profile-local, and instance data;
- package, CLI, data-schema, and JSON-contract versions;
- dry-run/idempotent migration with backup and rollback receipt;
- protected current facts/history (no coarse overwrite);
- non-Hermes consumers can read the canonical data contract;
- restore proves realpath, component version, permissions, and consumer behavior.

A passing `check` or `doctor` only proves the checked surface is internally acceptable. It does not prove template/live semantic equivalence or migration compatibility.

## Live-surface drift and background writers

Skill and OPS audits must treat all writers as part of the lifecycle: foreground edits, profile projection, post-turn self-improvement, Curator maintenance, installer sync, and local instance mutation.

1. Read effective controls (`skills.creation_nudge_interval`, `skills.write_approval`, `curator.enabled`, `curator.consolidate`) and the relevant usage/provenance records.
2. Freeze the decision surface with path, realpath/inode when aliases matter, bytes, SHA-256, version, and mtime.
3. If a target changes, stop exact-surface promotion. Do not revert, overwrite, or keep chasing hashes until one repeats.
4. Separate the content verdict from the exact-surface/authorization verdict. Preserve the old receipt as historical evidence.
5. Identify the writer at the strongest supported level. `created_by: agent` is a management-policy marker, not cryptographic authorship proof.
6. After the writer quiesces, create one current-byte replacement freeze and run one focused semantic validator. Do not inherit the old verdict as authorization for new bytes.
7. Keep package/source, runtime projection, instance data, and Worksite evidence as separate receipts; reconcile through the owning CLI or a queue-only supervisor adapter, never by hand-editing a worker/source file.

## Disposition vocabulary

Use a small, explicit ledger:

- **Keep orthogonal** — different semantic owner or lifecycle;
- **Thin** — retain the entry, remove copied procedure and point to its owner;
- **Co-package** — release static members together while exporting separate Skills;
- **Move** — relocate current facts or host-specific detail to its existing owner;
- **Defer** — require consumer/trigger/provenance evidence before changing active state;
- **Do not merge** — preserve security, authority, recovery, or data boundaries.

For AIOps, the default is: `aiops-vault` owns catalog/current/history read-write procedure; a selected-service companion owns service mechanics; resolver, capability, Secret, LLL, and policy remain separate. Prefer package-layout and compatibility-contract fixes before moving live OPS data or deleting Skill entries.
