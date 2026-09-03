---
name: aios-resource-resolver
description: Bind an already selected AIOS resource to an exact, hash-bound ResourceRef at the action boundary.
version: 0.3.0
author: Lin
license: MIT
---

# AIOS Resource Binding

Use this Skill only after the Agent has semantically selected a project or Source and a deterministic identity/location is needed for execution, recovery or audit.

This Skill is not the user's discovery interface and does not understand natural language. Dynamic discovery belongs to bounded context loading over Skill catalogs, AIOps service catalogs, project-local context, current Matter/Worksite files and official tooling.

```text
Human intent
  -> compact candidates
  -> Agent selects owner/resource
  -> this Skill binds final Project/Source facts
  -> ResourceRef receipt
  -> domain actuator
```

## When a ResourceRef is warranted

Bind a durable Project/Source record only when at least one is true:

- an action crosses a write, authorization, backup, sensitivity or recovery boundary;
- multiple locations/profiles exist and deterministic selection is required;
- a Matter/receipt must survive the current conversation and point to a stable owner;
- current owner context cannot recover the location safely;
- repeated real tasks have shown identity or path ambiguity.

For ordinary work in an already known local repository, prefer current realpath, project-local files and Git remote/commit/tree in the task receipt. Do not create or resolve a central Project record merely for completeness.

## Binding route

1. Confirm that the Agent has already selected one candidate from current context. If selection is still semantic or ambiguous, return to the owner catalog; do not fuzzy-match here.
2. Read the existing durable records only when required:
   - `$AIOS_ROOT/vault/ops/projects/registry.jsonl` and `aliases.yaml`;
   - `$AIOS_ROOT/vault/ops/sources/registry.jsonl` and `aliases.yaml`.
3. Run `aios resource resolve <selected-id-alias-or-name> [--kind project|source] [--profile <profile>] --json`.
4. The CLI matches exact case-insensitive ID, alias or full name only because it is binding an already selected candidate, not discovering one from user prose.
5. A unique active match returns `aios.resource-ref.v1`; otherwise stop with a structured failure.
6. Route any write to the record's owner and domain actuator; a ResourceRef is never permission.

Existing `aios project ...` and `aios source ...` commands are compatibility/narrow fact actuators. They are not mandatory entry points for every project, service, device, data asset or cloud resource. Live CLI help still says `manage the minimal AIOS project registry` and `resolve existing Project/Source records`; treat that leftover language as the compatibility/read-bind surface, not as a discovery product.

## ResourceRef contract

A resolved ref binds:

- canonical identity (`resource_kind:profile:id`), ID/name/kind/profile and match class;
- active status and owner ref;
- primary path/location plus declared locations;
- record version and deterministic record SHA-256;
- source registry owner/path/schema version/line and settled registry SHA-256;
- `failure_class: null` on success.

The receipt is provider-neutral and read-only. Registry or record drift requires fresh binding.

## Fail closed

Return `BLOCKED` for duplicate identity, ambiguous identity, missing resource, stale alias/resource, inactive resource, cross-profile ambiguity or profile mismatch. Candidate summaries may include IDs/statuses but never Secret values or private record bodies.

## Boundary

- Agent semantic discovery happens before this Skill; do not add fuzzy search, embeddings, an LLM call or a universal context service here.
- Facts stay with project-local context, official systems or existing Project/Source owners; do not put live inventory in this Skill.
- A public example is not private instance truth.
- Visibility, indexing, a local path or a successful hash check does not expand write authority.
- Do not add a daemon, database, broker, marketplace, global registry, Context Registry or broad filesystem scan.
