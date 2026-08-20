# Workflow observability preference harvest

## Session signal

The user explicitly requested that future actual work/workflows expose a small amount of operational debugging information with an optional expandable view. The goal is to evaluate whether an evolving AIOS/LLL workflow is truly self-organizing, self-managing, recoverable, and able to connect multiple tasks—not to expose model reasoning or flood the answer with logs.

## Reusable output contract

Use a compact visible receipt:

```text
调试｜route=<chat/source/matter/lll> · matter=<explicit/inferred/none> · state=<...> · validation=<...> · writes=<...>
```

For nontrivial work, add a collapsed Markdown `<details>` section covering only operational evidence:

- route and Matter relation;
- Worksite path and lifecycle;
- task/agent topology;
- principal Sources/capabilities;
- durable writes and original-file impact;
- validation, blockers, incidents, and fallbacks;
- promotion/archive/next-event state.

Never include hidden chain-of-thought, secrets, tokens, or large raw logs.

## Managedness ladder

Avoid the binary phrase “AIOS-managed.” Report the strongest proven level:

1. **Discoverable** — found in a rebuildable derived index, possibly as an inferred Worksite.
2. **Explicit Matter** — stable `matter.json` identity, lifecycle, aliases, relationships, and delivery policy exist.
3. **Presentation-managed** — a curated Matter View was actually built and is current.
4. **Asset-managed** — selected outputs were promoted to an explicit long-lived owner with provenance.
5. **Lifecycle-applied** — archive/quarantine/promotion was actually executed with evidence and restore semantics.

Distinguish query-time index rebuild from a background watcher/reaction, and dry-run candidates from applied file movement.

## Library placement decision

- User-wide default: profile/memory.
- User-specific LLL behavior: `SKILL.local.md` sidecar.
- Portable reusable behavior: governing class-level workflow/AIOS skill.
- Session evidence and reproduction detail: this reference or the originating Worksite.

Do not create a narrow “workflow-debug-for-this-session” skill.

## Verification lesson

A runtime/system guard may require fresh verification after a Markdown/skill change even when there is no canonical test suite. Use an OS-safe temporary script created under `/tmp` with a `hermes-verify-` prefix; verify section uniqueness, Markdown structure, required fields, privacy guardrails, and runtime realpath; run it, clean it up, and explicitly call the result ad-hoc verification rather than suite green.

If a tool-mediated verification result is not recognized by the guard, rerun through the expected terminal execution surface rather than merely repeating the claim.