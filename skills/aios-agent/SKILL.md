---
name: aios-agent
description: "Use when operating, evolving, updating, or governing AIOS itself: Agent-first workflows, aios-kit changes, skill/module adoption, local/private overlay boundaries, self-iteration, and upstream-instance reconciliation."
version: 0.1.1
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

For conversational workflow routing, do not require magic phrases such as “use LLL.” Infer the smallest honest mode from intent: keep disposable chat as chat; resolve or create a Matter when the user is pursuing a durable outcome; use LLL automatically when the work needs a recoverable Worksite; and surface retention/promotion suggestions at natural checkpoints rather than interrupting every message. Human wording remains natural language, while Matter/LLL/Source commands are Agent-selected actuators.

For continuation intent such as “继续刚才那个”, “接着上次的事”, or a paraphrase of an earlier durable outcome, resolve before creating. Prefer the current active Worksite when one is explicit; otherwise use `aios lll list --json` (or the equivalent work-root inventory) and read compact `mission.md` + `internal/recovery.json` from a small set of recent semantic matches. Resume one unique match, ask one choice question for genuinely ambiguous matches, and create a new Matter only when no plausible durable Worksite exists. Session history is secondary context, not the authority for current task state.

Retention requests require provenance. “提取刚才的精华” may use content actually present in the current conversation, or an explicit session/file/source reference supplied by the user. If the referenced conversation is not accessible—especially in a fresh session—do not reconstruct “what we discussed” from global memory, similar topics, or assumptions and do not claim that anything was saved. State the missing scope briefly and ask for the conversation/reference, or offer to review the current visible exchange only. When content is available, classify it into durable preference/fact, project/Matter asset, reusable procedure, archived evidence, or noise before writing to the owning truth source.

Apply progressive disclosure to the human surface. For ordinary use, prefer the concepts “thing/work” and “material,” plus the actions save, organize, and delete. Treat Matter, Source, Registry, Managed Zone, Worksite, authority, provenance, and projection as internal or advanced vocabulary unless the user asks for technical detail or the distinction changes a real outcome. Interpret “save this” as durable findability with the original preserved and no overwrite/delete by default. If a reversible staging or link can absorb ambiguity, act and give a plain-language receipt. Ask at most one outcome-level question only when interpretations would change canonical ownership, sync direction, sensitive/public boundaries, overwrite/delete behavior, or large-batch scope. Receipts should say what was saved, whether the original changed, where/how it can be found, and whether it can be undone—without requiring protocol terminology.

Routing precedence: explicit “do not save / chat only” overrides ordinary durability inference; runtime hard boundaries and mass/cross-location/destructive/sensitive-to-public rules override direct autonomy or “do not ask”; split compound requests by sub-action so safe read-only work may proceed, durable outputs share one Matter, and high-risk writes become a separate change-set decision. Do not create a Matter merely because an action has a result: one-turn translation, rewriting, explanation, short calculation, or format conversion stays in chat unless it needs a durable file, continuing state, recovery, or acceptance boundary.

## Source-of-truth boundaries

| Layer | Belongs here | Does not belong here |
|---|---|---|
| Public base (`aios-kit`) | Portable installers, thin CLI, public skills, schemas, templates, docs, examples | Real private resources, personal overlay names, secret values, live operations facts |
| User instance (`$AIOS_ROOT`, usually `~/aios`) | Config, modules, workdirs, state, logs, cache | Public distribution source that should be upstreamed |
| Live OPS vault | Current/private resources, project registry, maintenance logs, private instance decisions | Generic public product documentation |
| Runtime skills | Skills loaded by a specific agent profile | Assumed canonical source unless explicitly adopted into Git |

If a user-specific fact matters, record it in the instance vault/state or a local-only profile layer. If a reusable workflow matters, upstream it as a public skill/doc/CLI improvement after removing private facts.

## Private actuator projects

An AIOS instance may keep private automation repositories or command bundles such as Ansible playbooks, Terraform stacks, shell scripts, or deployment artifacts. Treat these as **actuator adapters** governed by AIOS/AIOps, not as the canonical AIOS brain.

Good boundary:

```text
Human intent -> Agent policy -> OPS vault resource truth -> private actuator repo -> verification/write-back
```

Rules:

- Register private actuator projects in the local OPS vault/project registry so agents can discover them.
- Keep public reusable logic in `aios-kit`; keep private inventory, overlays, generated artifacts, and deploy-only binaries in private repos or vault/state.
- Prefer project-local `README.md`/`AGENTS.md` for role-specific runbooks, file ownership, and secret-adjacent handling.
- Do not move a private automation repo into public AIOS Kit just because AIOS uses it. First separate public reusable capability from private instance projection.
- Humans should be able to express host/network/service intent in natural language; agents choose whether to call Ansible, SSH, AIOS CLI, Tailscale/remote tools, or another actuator.
- When an actuator action changes real infrastructure, verify from the consumer side and write durable facts/history back to the OPS vault.

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
- `aios-secret-management`: secret registry/runtime workflows with strict safety rules.
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

When a task exposes an error or workflow lesson, choose one owning layer before writing it down. Put personal preferences in profile/memory, private current-state facts in the OPS vault, project conventions in project-local docs, cross-skill development discipline in the skill-authoring/governance layer, domain procedures in the relevant domain skill, and one-off incident evidence in LLL/OPS logs or issues. Avoid copying the same rule into multiple AIOS skills unless each copy has a distinct operational role.

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
