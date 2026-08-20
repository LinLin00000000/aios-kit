# Skill governance library-audit references

These references are the second-level read-only audit context formerly exposed through the local `skill-library-governance` entry. They support reconciliation and evidence; they do not own lifecycle mutation, install, projection, approval, or deletion authority.

Load only the reference matching the concrete audit question:

- `read-only-skill-reconciliation.md`: provenance, runtime tree, manifest, install-state, consumer, and rollback reconciliation.
- `bounded-overlap-audit.md`: focused semantic/lexical overlap and trigger-routing review.
- `aios-module-skill-package-boundary.md`: package/runtime/private-overlay merge boundaries.
- `asset-workflow-owner-audit.md`: cross-owner asset/workflow authority audit.
- `agent-runtime-vs-worksite-evaluation.md`: carrier fit versus Worksite/LLL evaluation.
- `aios-lll-lineage-and-provenance.md`: Matter/Worksite lineage and provenance.
- `continuation-lifecycle-reconciliation.md`: continuation and lifecycle state reconciliation.
- `canonical-synthesis-receipt-pattern.md`: evidence-bound synthesis receipts.
- `contract-derived-closeout-verifiers.md`: closeout verifier derivation.
- `context-engineering-audit-wave.md`: bounded context/audit waves.
- `context-loading-and-truth-ownership.md`: loading versus truth ownership.
- `delivery-preference-audit.md`: delivery-surface preference audit.
- `frozen-base-concurrent-drift.md`: frozen-base and concurrent-drift handling.
- `global-hermes-lll-workflow-simplification-audit.md`: broad simplification audit method.
- `hermes-self-improvement-curator-audit.md`: Curator/self-improvement audit.
- `provisional-user-workflow-compatibility-layers.md`: compatibility-layer evaluation.
- `skill-manage-addressability.md`: readable versus mutable Skill surfaces.
- `workflow-observability-preference-harvest.md`: workflow observability preference evidence.

The former active `skill-library-governance` entry is intentionally not reproduced. `skill-governance` is the sole first-party lifecycle owner; these files are references under its Git-managed package.
