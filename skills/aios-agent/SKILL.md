---
name: aios-agent
description: "Use when operating, evolving, updating, or governing AIOS itself: route intent to the owning policy, ResourceRef, Matter/LLL, or actuator without duplicating their bodies."
license: MIT
metadata:
  version: "0.2.1"
---

# AIOS Agent

This is AIOS's thin Agent entry. It routes intent; it is not a second policy, resource, capability, workflow, or runtime owner.

```text
Human intent -> exact owner/ref -> domain actuator -> receipt/evidence
```

## Owner boundary

| Claim | Owner |
|---|---|
| Portable product/evolution rules | `docs/evolution.md` and the relevant public source |
| Current instance workflow behavior | the AIOS-managed local workflow policy |
| Project/Source facts | existing Project/Source registries |
| Action and executor facts | the owning resource record and domain/provider owner |
| Task state/recovery/evidence | Matter / LLL Worksite |
| Deterministic action | CLI, script, API, or provider skill |
| Secret value | Secret runtime/native secret owner; never this skill or a receipt |

A skill, index, viewer, runtime copy, or receipt is a pointer/projection unless its owner contract explicitly says otherwise. It must not write back to the source it projects.

## Route

1. Apply precedence: current user instruction, then current Matter/mission, then exact local policy, then portable product default.
2. Resolve a mentioned project, Source, service, device, vault, or other resource through `aios-resource-resolver` and `aios resource resolve ... --json` before acting.
3. Follow the resolved `owner_ref` to the current domain/provider Skill or service card, then invoke that owner's existing CLI, MCP, or Skill script directly. Do not insert a generic discovery, binding, adapter, or health layer.
4. Keep disposable work in chat. Resolve/create a Matter and use LLL only when durable state, recovery, evidence, or a validation boundary is needed.
5. Route mutation to the domain owner/actuator. A ResourceRef, receipt, policy index, or Decision packet never grants write authority.
6. Return a structured result/receipt and leave current facts with their owner.

## Decision Surface pointer

For a genuine long-term human trade-off, use only:

- policy ID: `decision-surface`;
- route ID: `aios.decision-surface.route.v1`;
- packet schema: `aios.decision-packet.v1`;
- shape check: `aios decision check ... --json`.

Load the exact fragment directly from `$AIOS_ROOT/workflow/local-policy.md` and bind the packet to that policy source SHA-256; use `policy_id=decision-surface` and fragment `#policy-decision-surface` without an index or second locator. Route depth, visited IDs, missing refs/source/fragment, cycles, and hash drift fail closed. The CLI checks packet/ref shape only; it does not choose an option, evaluate authorization, or call a model. Ordinary reversible details and tool-answerable facts stay with the Agent.

## Closeout retention pointer

Worksite outputs are candidate deliverables. An Agent value assessment and explicit user retention intent are separate: until both are present, artifacts are not selected or authorized for durable asset creation or promotion. Retain at most one canonical deliverable plus exact evidence pointers; the full Worksite remains the provenance owner. A high score is advice, never authorization. Prohibited before that precondition: asset creation, copying, linking, and promotion.

The owning local policy/Worksite defines the complete closeout protocol; this skill keeps only the routing boundary above.

## Hard boundaries

- Public `aios-kit` contains portable routes and schemas, not private instance facts, organization IDs, endpoints, credentials, or Secret values.
- `$AIOS_ROOT` contains the user's instance and registries; runtime skills are projections, not automatically canonical source.
- Do not create a second registry, daemon, broker, marketplace, approval engine, authorization engine, or hidden workflow state machine for routing.
- Before an AIOS architecture or CLI expansion, follow `docs/evolution.md`; reuse the existing owner and leave one focused verification.

## Related skills

- `aios-resource-resolver` — exact ResourceRef lookup and owner pointer.
- `lins-living-loop` — durable Matter/Worksite execution and recovery.
- `aios-secret-management` — metadata and controlled runtime secret use.
