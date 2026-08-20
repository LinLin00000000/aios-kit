# Provisional user workflow compatibility layers

Use this pattern when a real user workflow needs an immediate manual bridge, but the bridge should disappear after the underlying product or protocol gains a native capability.

## Layering pattern

Keep the compatibility behavior thin and deliberately split by ownership:

1. **Product/project documentation** owns the rationale, scope, source-of-truth boundary, and removal condition.
2. **A user-local skill sidecar** owns the executable Agent behavior for that task class.
3. **User/profile memory** carries only the compact cross-session preference and compatibility id.
4. **Public portable skills** stay clean unless the behavior has become generally useful beyond one user or product gap.

Do not add a registry, database field, sequence file, or alternate recovery plane merely to support the bridge. The existing Matter/Worksite/project files remain authoritative.

## Searchable lifecycle marker

Use one stable id across every layer, with machine-searchable block markers where comments are supported:

```text
<!-- FEATURE_COMPAT_BEGIN id=<compat-id> status=provisional remove_when=<verified-native-condition> -->
...
<!-- FEATURE_COMPAT_END -->
```

The documented removal action should name every layer to delete. Do not migrate historical compatibility-only values unless the native protocol genuinely needs them.

## Trigger semantics

Write trigger logic as an explicit Boolean expression rather than a loose bullet list. A useful shape is:

```text
(message has closeout/handoff responsibility)
AND
(at least one durable signal is present)
```

Keep typical-use guidance separate from necessary conditions. For example, “likely to be copied into the next session” may explain why the bridge helps, but should not silently become a third gate unless that is intentional.

Define invariants that prevent drift: stable naming source, same-session behavior, continuation behavior, ordinary-chat exemption, and authority fallback when the hint conflicts with canonical files.

## Review and verification

1. Freeze the final behavior-bearing files with hashes before semantic review.
2. If a reviewer identifies a mismatch and the target changes, mark the old verdict stale and review the new frozen surface—not the previous text.
3. When no canonical suite exists, create an OS-safe temporary verification script with `tempfile`/`mktemp` under `/tmp` using a `hermes-verify-` prefix, run it through an observable terminal path after the **last substantive write**, and remove it.
4. Check markers, exact Boolean trigger semantics, public/private placement, source-of-truth boundaries, structured state parsing, evidence paths, and frozen hashes.
5. Report this as focused ad-hoc verification, never as project suite green.
6. If the final independent semantic reviewer remains unavailable after the bounded retry policy, preserve earlier concrete findings, verify their fixes deterministically, and use `PASS_WITH_NOTES` rather than claiming independent PASS.

## Common pitfalls

- Writing several bullets without saying whether they are AND or OR conditions.
- Letting a motivating example become an accidental required gate.
- Copying a personal compatibility rule into a public umbrella skill.
- Allowing a human-readable hint to become a second state authority.
- Re-running verification before final closeout/state writes, then calling the earlier evidence “final.”
- Retrying an unavailable reviewer indefinitely instead of using the bounded fallback and recording the caveat.
