---
name: aios-resource-resolver
description: Resolve AIOS resources by exact ID, alias, or name into a provider-neutral, hash-bound ResourceRef before routing any action.
version: 0.2.0
author: Lin
license: MIT
---

# AIOS Resource Resolver

Use this skill when the user names a project, Source, service, device, vault, data root, workflow, skill, or other resource whose canonical identity/location must be known before acting.

```text
Skill = lookup procedure
Project/Source registry = current resource facts
ResourceRef = read-only resolution receipt
Domain actuator = mutation owner
```

## Owner and lookup route

1. Read the existing instance records only:
   - `$AIOS_ROOT/vault/ops/projects/registry.jsonl` and `aliases.yaml`;
   - `$AIOS_ROOT/vault/ops/sources/registry.jsonl` and `aliases.yaml`.
2. Run `aios resource resolve <exact-id-alias-or-name> [--kind project|source] [--profile <profile>] --json`.
3. Match exact case-insensitive ID, alias, or full name only. Do not fuzzy-search, pick the first result, or silently choose a profile.
4. A unique active match returns `aios.resource-ref.v1`; otherwise stop with a structured failure.
5. Use targeted discovery only after a genuine missing result. Discovery does not create or mutate a resource record.
6. Route any write to the owner named by the record and its domain actuator; a ResourceRef is never permission.

Existing `aios project ...` and `aios source ...` commands remain the registry actuators. The resolver consumes those records and creates no second registry.

## ResourceRef contract

A resolved ref binds:

- canonical identity (`resource_kind:profile:id`), ID/name/kind/profile, and match class;
- active status and owner ref;
- primary path/location plus declared locations;
- record version and deterministic record SHA-256;
- source registry owner/path/schema version/line and settled registry SHA-256;
- `failure_class: null` on success.

The receipt is provider-neutral and read-only. Registry or record drift requires fresh resolution.

## Fail closed

Return `BLOCKED` for duplicate identity, ambiguous identity, missing resource, stale alias/resource, inactive resource, cross-profile ambiguity, or profile mismatch. Candidate summaries may include IDs/statuses but never Secret values or private record bodies.

## Boundary

- Facts stay in existing Project/Source records; do not put live inventory in this skill.
- A public example is not private instance truth.
- Visibility, indexing, a local path, or a successful hash check does not expand write authority.
- Do not add a daemon, database, broker, marketplace, global registry, or broad filesystem scan.
