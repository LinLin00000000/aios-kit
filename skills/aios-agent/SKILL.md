---
name: aios-agent
description: "Use when operating, evolving, updating, or governing AIOS itself: route intent to the owning policy, ResourceRef, Matter/LLL, or actuator without duplicating their bodies."
license: MIT
metadata:
  version: "0.3.0"
---

# AIOS Agent

This is AIOS's thin Agent entry. It routes intent through bounded dynamic context; it is not a second policy, resource, capability, workflow, or runtime owner.

```text
Human intent
  -> bootstrap/compact context
  -> Agent semantic owner route
  -> owner context
  -> final action/resource binding
  -> domain actuator
  -> receipt/evidence
```

## Owner boundary

| Claim | Owner |
|---|---|
| Portable product/evolution rules | `docs/evolution.md` and the relevant public source |
| Current instance workflow behavior | the AIOS-managed local workflow policy |
| Project/Source facts | existing Project/Source records only when a durable boundary is needed; otherwise current owner context/local project facts |
| Action and executor facts | the owning resource record and domain/provider owner |
| Task state/recovery/evidence | Matter / LLL Worksite |
| Deterministic action | CLI, script, API, or provider skill |
| Secret value | Secret runtime/native secret owner; never this skill or a receipt |

A skill, index, viewer, runtime copy, or receipt is a pointer/projection unless its owner contract explicitly says otherwise. It must not write back to the source it projects.

## Route

1. Apply precedence: current user instruction, then current Matter/mission, then exact local policy, then portable product default.
2. Load only the smallest needed context: bootstrap rules, then a compact candidate catalog from existing Skills, AIOps services, current Worksite, project-local files or official tooling.
3. Select the owner semantically in the Agent; do not require the user to provide an exact ID, alias or path and do not add a generic semantic resolver.
4. Load the selected owner's Skill, service card, runbook or project context. Prefer the official CLI, official Skill or official MCP before a custom wrapper or traditional API.
5. Only at the action boundary bind the selected resource to a deterministic path, remote, canonical ID, version, profile and Secret consumer. Use `aios resource resolve ... --json` when a durable Project/Source record is genuinely required; otherwise keep an ephemeral binding in the current task/receipt.
6. Invoke the owner actuator directly. Do not insert a generic discovery, binding, adapter or health layer.
7. Keep disposable work in chat. Resolve/create a Matter and use LLL only when durable state, recovery, evidence or a validation boundary is needed.
8. Route mutation to the domain owner/actuator. A ResourceRef, receipt, policy index or Decision packet never grants write authority.
9. Return a structured result/receipt and leave current facts with their owner.

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
- Do not create a second registry, daemon, broker, marketplace, approval engine, authorization engine, hidden workflow state machine or global context platform for routing.
- Treat data, server, service, cloud, project and capability management as owner-specific dynamic context; do not create a manager merely to make the catalog look complete.
- Prefer official CLI, official Skill and official MCP before AIOps cards, thin guides, narrow scripts or traditional APIs.
- Exact IDs and paths are final binding/audit handles, not the primary natural-language discovery interface.
- Before an AIOS architecture or CLI expansion, follow `docs/evolution.md`; reuse the existing owner and leave one focused verification.

## Related skills

- `aios-resource-resolver` — exact ResourceRef lookup and owner pointer.
- `lins-living-loop` — durable Matter/Worksite execution and recovery.
- `aios-secret-management` — metadata and controlled runtime secret use.
