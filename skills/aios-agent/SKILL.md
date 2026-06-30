---
name: aios-agent
description: "Use when operating, evolving, updating, or governing AIOS itself: Agent-first workflows, aios-kit changes, skill/module adoption, local/private overlay boundaries, self-iteration, and upstream-instance reconciliation."
version: 0.1.0
license: MIT
---

# AIOS Agent

This is the umbrella policy skill for AIOS work. It is intentionally thin: it teaches agents how to reason about AIOS, where facts belong, when to use lower-level skills/CLI, and when to improve the system itself. It must not store private instance facts, resource inventories, secret values, or machine-specific paths except portable examples.

Core model:

```text
Human Intent -> Agent Policy -> Machine Actuation -> State/Evidence
```

- **Human Intent**: the user expresses goals, constraints, authorization, and acceptance criteria in natural language.
- **Agent Policy**: the agent uses skills, docs, registries, vault facts, and current context to decide what should happen.
- **Machine Actuation**: CLI commands, scripts, MCP tools, APIs, and file operations perform deterministic actions. Prefer dry-run, doctor, validate, JSON/status outputs, and idempotent commands.
- **State/Evidence**: long-lived facts and decisions are written to manifests, registries, vaults, install-state, logs, LLL workdirs, and evidence files.

Humans should not need to memorize low-level commands for normal AIOS operation. CLI/API surfaces exist primarily as stable actuators for agents and as fallback/debug tools for maintainers.

## Source-of-truth boundaries

| Layer | Belongs here | Does not belong here |
|---|---|---|
| Public base (`aios-kit`) | Portable installers, thin CLI, public skills, schemas, templates, docs, examples | Real private resources, personal overlay names, secret values, live operations facts |
| User instance (`$AIOS_ROOT`, usually `~/aios`) | Config, modules, workdirs, state, logs, cache | Public distribution source that should be upstreamed |
| Live OPS vault | Current/private resources, project registry, maintenance logs, private instance decisions | Generic public product documentation |
| Runtime skills | Skills loaded by a specific agent profile | Assumed canonical source unless explicitly adopted into Git |

If a user-specific fact matters, record it in the instance vault/state or a local-only profile layer. If a reusable workflow matters, upstream it as a public skill/doc/CLI improvement after removing private facts.

## Skill and module evolution

Do not create a new skill for every command or one-off workflow. Split by stable domain boundary.

Prefer an umbrella skill when:

- the work is cross-cutting across AIOS architecture, update policy, local/private boundaries, and agent operation;
- the workflow is still evolving;
- splitting would duplicate principles across many small skills;
- the main value is policy and routing.

Prefer a narrow companion skill when:

- the workflow is frequent, high-risk, or has its own validation model;
- the domain has distinct safety boundaries, such as secrets or service operations;
- the skill can stay useful without importing the whole AIOS operating model;
- loading it should not pollute unrelated AIOS tasks.

Examples:

- `aios-agent`: umbrella policy and routing.
- `aios-resource-resolver`: resource lookup and permission workflow.
- `aios-secret-management`: secret/control-plane workflows with strict safety rules.
- `aiops-vault` and `aiops-service-operations`: OPS vault and service operations workflows.

## Adopting a local skill into AIOS

When the user says something like “make this skill AIOS-managed” or “let AIOS host this skill,” do not expect the user to remember CLI syntax. The agent should:

1. Locate candidate runtime skill directories.
2. Decide whether it is public first-party, module-bound, independent module, local/private overlay, or not suitable for adoption.
3. Refuse or ask before publishing anything containing private infrastructure facts, secret handles, personal resource topology, or machine-specific assumptions.
4. Use the `aios skillpack adopt` actuator only after a dry run and boundary check.
5. Prefer `skills/<skill>` for portable AIOS-level skills. Use `modules/<module>/skills/<skill>` only when the skill is meaningless without that module.
6. Verify with skillpack doctor, public audit, diff checks, and a clean/fresh environment smoke when distribution behavior changed.
7. Remove or document same-name runtime overlays that would shadow the adopted source.

`adopt` is an actuator, not the human-facing UX. The human-facing instruction is natural language; the agent chooses commands.

## Evolution discipline

When changing AIOS architecture, modules, skills, CLI surfaces, automation, or project governance, use the public repo document `docs/evolution.md` as the source of truth for progressive enhancement, breadth-first module maturity, complexity budget, and upgrade triggers.

Do not create a new skill or heavy runtime just because a concept is useful. Prefer: document the current stage, define trigger conditions, patch existing docs/skills, and keep advanced mechanisms as roadmap candidates until real friction appears.

## Self-iteration duty

AIOS must improve through use. During any AIOS-related task, actively watch for:

- repeated manual steps that should become CLI/API actuators;
- unclear or stale skill instructions;
- commands that are too verbose for agents or unsafe for users;
- missing `doctor`, `status`, `validate`, `--dry-run`, or `--json` outputs;
- public/private boundary mistakes;
- update conflicts between upstream base and local instance evolution;
- validation gaps, brittle paths, duplicated state, or hidden assumptions.

When such a pattern appears, do one of the following before closing the task:

1. Patch the relevant skill/doc/tool immediately when the fix is safe and clearly within scope.
2. Propose a concise improvement to the user when the fix changes workflow, CLI surface, architecture, or compatibility.
3. Record the issue in an LLL error/trace report or OPS maintenance log when it should not be fixed immediately.

Do not treat self-iteration as ceremony. Improve only real failure modes, repeated friction, risky ambiguity, or verified simplification opportunities.

## Upstream-instance reconciliation

AIOS installations are not static copies of `aios-kit`. Over time, a user instance may accumulate local habits, edited skills, private overlays, changed modules, and agent-created workflows. Therefore updates must be reconciliation, not blind overwrite.

Model:

```text
aios-kit upstream = seed + reusable improvements
user instance = living local organism
update = propose/reconcile/merge/validate, not reset
```

Update policy:

1. Classify each object as upstream-managed, user-owned, local overlay, generated/cache, or external/app-owned.
2. For upstream-managed copies, use install-state hashes and refuse to overwrite local edits without explicit force or merge.
3. For local overlays and vault facts, never publish or overwrite from upstream defaults.
4. For user-edited skills, prefer a three-way mental model: upstream base, installed previous base, local evolved copy.
5. Present conflicts as proposals with evidence and safe choices, not as silent changes.
6. After merge/update, run doctor/validate and record evidence.

Future tools should make this explicit with commands such as status/diff/doctor/propose/reconcile rather than broad destructive update commands.

## Related skills

- Use `lins-living-loop` for durable, auditable, multi-step AIOS work and self-maintenance records.
- Use `aios-resource-resolver` before acting on projects, services, devices, vaults, or ambiguous resources.
- Use `aios-secret-management` for secret/credential workflows.
- Use `aiops-vault` for live OPS vault maintenance and private instance facts.
- Use `hermes-agent` only for Hermes Agent/Web UI/profile/tool configuration itself.
