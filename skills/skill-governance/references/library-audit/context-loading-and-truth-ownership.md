# Progressive Context Loading and Truth Ownership

Use this reference when an AIOS/Hermes library appears to duplicate Skill loading, a local registry, a Worksite, or an operations vault.

## Core distinction

Progressive disclosure answers **when and how much context to load**. It does not decide **which layer owns the facts**.

A single workflow may use several progressive loaders:

```text
Level 0: compact skill descriptions / resource catalog / Worksite status
Level 1: selected SKILL.md / service card / mission + recovery
Level 2: targeted references / current-state slices / evidence / live probes
```

The common loading pattern is valuable. The stores remain separate when their authority, lifecycle, consumers, or security boundary differ.

## Owner matrix

| Object | Primary question | Lifecycle | Canonical owner |
|---|---|---|---|
| Skill body | How should an Agent handle this class of task? | versioned procedure | Skill source/repository |
| Skill reference/template/script | What static detail or deterministic helper supports the procedure? | package asset | Skill package |
| Project context file | What local repository/ directory constraints apply? | project-local | `AGENTS.md` / equivalent |
| Instance registry / OPS | What private resource or service exists, and where? | mutable current state | instance vault/registry |
| Service card | How is one selected service run and constrained? | stable service contract with current pointers | service-owned docs |
| Maintenance log | What changed, why, and what was verified? | append-only history | OPS/event log |
| LLL Worksite | How do I resume and prove this one durable run? | episodic task lifecycle | Worksite files |
| Local workflow policy | Which cross-task behavior is enabled now? | instance policy with mode/lifecycle | Managed Zone/local policy |
| Actuator | How does a deterministic side effect or query execute? | executable implementation | CLI/script/API/Ansible |

## Merge test

Before merging two surfaces, answer all five questions:

1. Do they have the same semantic owner?
2. Do they change on the same lifecycle and cadence?
3. Are they consumed by the same runtime and authority boundary?
4. Do they require the same security/privacy treatment?
5. Do they need the same query, freshness, append, or read-after-write contract?

If any answer differs, do not merge the data stores just because both are text files or both are loaded on demand. Instead merge duplicated instructions and leave a short pointer at the boundary.

## Safe target flow

```text
natural-language intent
  -> thin class/domain Skill
  -> compact registry/catalog query
  -> semantic selection by the Agent
  -> exact detail load
  -> live inspection or deterministic actuator
  -> consumer-side verification
  -> current-state write-back
  -> append one historical summary
  -> retain detailed evidence in the Worksite
```

The same flow can use Hermes `skill_view`, an OPS CLI such as `services --json`/`service <id>`, and an LLL status projection without turning them into one runtime.

## Skill-directory data rule

Skill package files are appropriate for:

- stable procedural references;
- templates and examples;
- deterministic scripts;
- schemas and static fixtures;
- a pointer or non-secret path configuration to an instance data root.

Keep these outside the Skill package when they are mutable instance truth:

- host/service inventories and current status;
- maintenance or deployment history;
- Secret values or sensitive Secret metadata;
- per-run recovery, queue, validation, and evidence;
- generated runtime state or provider caches.

A `SKILL.local.md` or local sidecar can contain instance defaults and pointers, but it should explicitly defer to the current policy, registry, OPS, or Worksite owner rather than becoming a shadow database.

## Common overlap patterns

### Operations vault versus service-operations Skill

Keep the vault/registry contract separate from systemd/Docker/reverse-proxy procedures. Put the shared discovery and write-back protocol in the vault Skill; keep service runtime checks in the service-operations Skill. Do not copy the full sequence into both.

### Cloud/SSH entrypoint versus resource resolver/control plane

A cloud/SSH Skill may be useful as a natural-language trigger or domain adapter. It should route to resource resolution, OPS facts, and central/edge execution rules rather than maintain another host inventory, secret-location contract, or write-back protocol.

### LLL versus multi-agent orchestration

LLL owns durable Worksite structure, recovery, validation, and closeout. Multi-agent orchestration owns delegation topology, worker ownership, reviewer independence, and cost/parallelism gates. Shared terms such as handoff and validation need one short cross-reference, not duplicated algorithms.

### Current state versus history versus evidence

A current registry is not a maintenance log. A maintenance log is not a Worksite trace. A Worksite should keep full process evidence; the cross-task registry/log should receive a concise verified summary and a provenance pointer.

## Simplification checklist

- [ ] One owner is named for every recurring rule and fact class.
- [ ] Skill descriptions route without embedding private inventories.
- [ ] Current machine facts are not copied into portable or distributable Skills.
- [ ] One compact catalog precedes full detail loading where the collection is non-trivial.
- [ ] Service metadata, service procedure, current state, history, and evidence are distinguishable.
- [ ] Domain entry Skills do not repeat the complete OPS read/check/write-back workflow.
- [ ] LLL and Matter/portfolio views remain projections or semantic layers, not parallel recovery/state machines.
- [ ] Secret boundaries apply to every model-observable output channel, not only prompt text.
- [ ] Removing a duplicate entrypoint preserves an alias or pointer only when a real compatibility consumer exists.
- [ ] The final change is verified through the runtime-visible loader and the owning data check.

The objective is not minimum file count. It is minimum duplicated authority, minimum trigger noise, and minimum long-term synchronization burden while preserving the essential boundaries that make the system recoverable and safe.
