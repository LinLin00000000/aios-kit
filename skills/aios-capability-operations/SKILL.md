---
name: aios-capability-operations
description: Discover and resolve provider-neutral Capability metadata and one explicit binding through existing ResourceRefs; load adapter refs only on demand.
version: 0.2.0
license: MIT
---

# AIOS Capability Operations

Use this skill when an Agent must discover or route a reusable semantic action across one or more accounts, organizations, apps, adapters, or providers.

```text
Capability definition -> explicit binding -> target ResourceRef
                      -> adapter ResourceRef (on demand)
                      -> domain/provider actuator
                      -> Matter/LLL receipt
```

## Owner model

- Capability semantics and redacted adapter/binding metadata live with the existing Project/Source resource owner, in its optional `capabilities[]` metadata.
- Provider endpoint/scope/token details stay with the provider skill or official API contract.
- Binding/current health facts stay with the domain/instance owner.
- Secret identity/consumer metadata stays with Secret Registry; Secret values stay outside the Agent and receipts.
- Invocation state/evidence stays with the current Matter/LLL Worksite.

There is no separate capability registry in this slice.

## Thin metadata shape

A capability definition supplies stable `id`, exact aliases/name, profile, status, health, maturity, adapter metadata, and explicit bindings. Each binding supplies stable identity/profile, status/health/maturity, and a `resource_query` (optionally a resource kind). Adapter metadata supplies an ID and may supply a ResourceRef query. `authorization_ref` is an opaque future extension pointer only.

Maturity is ordered `designed -> discovered -> configured -> verified -> available`. Resolution requires at least `verified`, `healthy`, and `active`; it never upgrades maturity from an API response or another binding. Action maturity/acceptance remains separate owner metadata and is not inferred or promoted by this route.

## CLI route

```bash
aios capability discover [--resource <exact-resource>] [--profile <profile>] --json
aios capability resolve <exact-id-alias-or-name> [--binding <exact-binding>] [--profile <profile>] --json
aios capability resolve <exact-id-alias-or-name> --load-adapter --json
```

1. Discovery reads existing Project/Source records and returns summaries with `adapter.load_state=deferred`.
2. Resolve requires one exact capability and one exact/unique binding; multiple candidates or profiles fail closed.
3. Resolve checks capability and binding status, health, and maturity, then resolves the target through `aios.resource-ref.v1`.
4. Only `--load-adapter` resolves the adapter ResourceRef. It does not import or execute provider code.
5. The receipt reports `authorization.state=NOT_EVALUATED`; this seam is metadata, not an approval/authorization engine or grant.
6. The domain/provider actuator performs any real operation under its existing safety contract and writes back to its owner.

## Fail closed and boundaries

Fail on missing/ambiguous/cross-profile capability or binding, disabled/unhealthy/immature metadata, stale/unavailable owner or target, and missing/stale adapter ref when on-demand loading is requested. Never select a "current organization" silently.

Do not read, print, copy, or persist Secret values. Do not create a daemon, broker, marketplace, database, second task/event truth, permission engine, approval engine, authorization engine, or provider-specific global orchestrator.
