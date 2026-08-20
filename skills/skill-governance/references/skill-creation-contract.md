# Skill Creation Contract

This is the second-level creation context for `skill-governance`. Load it only when a request may create, materially revise, adopt, or retire a reusable Skill. The main `skill-governance/SKILL.md` owns lifecycle and source/projection integrity; this reference owns the minimum creation decision and creation-shape rules.

## 1. Do not create a Skill when

Prefer an existing Skill, a task-local reference, an ordinary document, a Worksite artifact, or a one-off script when:

- the work is a one-time answer, conversion, lookup, or manual action;
- the content is a user preference, current resource fact, secret location/value, project state, Matter/Worksite state, or other instance data;
- an existing Skill already owns the behavior and only needs a narrow rule or reference;
- there is no stable user-intent trigger, independent owner, input/output boundary, or observable acceptance;
- the proposed value mainly hard-codes the current model, provider, CLI, machine path, or one temporary workflow;
- the candidate is only a script, template, schema, or external-package install with no conversational routing need;
- a longer prompt is being used to compensate for one unverified omission. First test a focused positive case and nearest negative case.

## 2. Minimum candidate shape

A candidate must let a new Agent answer: **when to enter, what it owns, what it consumes/produces, when to stop or route elsewhere, and how to verify the result.**

```yaml
---
name: narrow-skill-name
description: Use when <specific user intent and context>; do not use for <nearest negative case>.
license: <known license>
metadata:
  owner: <canonical owner>
  version: <version>
---
```

Keep `SKILL.md` to the smallest useful main path:

1. one owner/boundary statement;
2. a 3–7 step procedure for the common case;
3. inputs, outputs, stop/failure conditions;
4. which references/scripts are loaded after which concrete gate;
5. negative routing to neighboring owners;
6. one risk-matched verification and receipt rule.

There is no universal line-count quota. The goal is low repeated context cost without hiding load-bearing constraints.

## 3. Progressive disclosure

- **Main body:** trigger, owner, common path, boundary, stop conditions, minimum verification, and route pointers.
- **`references/`:** provider/version differences, long evidence matrices, detailed failure recovery, fixed schemas, historical compatibility, and exceptional paths. Each reference must state when it should be loaded.
- **`scripts/`:** deterministic, repeatable parsing/checking/conversion/collection. Scripts must not secretly make model decisions, expand write scope, or bypass authorization.
- **`assets/` / templates:** material required to produce the output; never credentials, caches, current instance facts, or an undeclared policy source.

A second-level context is successful when the common request loads the main body only, while an exceptional request can deterministically load the exact reference without losing the owner or safety boundary.

## 4. Trigger contract

Write descriptions as user intent + concrete context + nearest non-trigger. Avoid broad words such as `any`, `always`, `whenever`, or `all non-trivial work` unless omission is demonstrably more harmful than false triggering.

For each candidate, prepare at least:

- one representative positive prompt;
- one nearest-neighbor negative prompt;
- one ambiguous prompt and its intended route.

Umbrella Skills choose a family and route to a method; they must not repeat every child algorithm in their description or main body.

## 5. Minimum validation

Choose the smallest evidence that can falsify the candidate:

1. validate frontmatter, name, UTF-8/NUL, package structure, and reference paths;
2. run a positive, nearest-negative, and—when useful—ambiguous trigger probe;
3. run one representative deterministic check when output is objectively testable;
4. run script `--check`/dry-run and one synthetic input when scripts exist;
5. if source/projection/install-state changes, run the separate `skill-governance` transaction/readback gate.

Quantitative benchmark/viewer work is optional and must be justified by an objectively measurable question. An external authoring/evaluation companion may be used as an adapter, but its model, CLI, directory layout, or benchmark protocol is not part of this first-party contract.

## 6. Lifecycle decisions after creation

- **Keep:** stable owner, common trigger, independent value, and verified consumer.
- **Thin:** common path is sound but provider detail, long examples, or edge cases dominate the main body; move those sections to references first.
- **Shelf:** capability remains recoverable but has no recent consumer or is platform/provider-specific; preserve provenance, package, and restore path while removing the active descriptor.
- **Merge:** two entries have the same semantic owner, lifecycle, consumer route, and verification contract. Keep only one canonical source and explicit compatibility routing during migration.
- **Retire/delete:** replacement or no-replacement is explicit, current consumers are zero or migrated, recovery copy is verified, and the user authorizes the exact removal surface.

Any trigger regression, missing reference, ambiguous provenance/license, unexpected consumer, or failed rollback readback reopens the previous route. Do not silently rewrite an old package into a new owner.
