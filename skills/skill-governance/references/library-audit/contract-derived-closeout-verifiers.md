# Contract-derived closeout verifiers

Use this reference when a skill/repository/workflow closeout freezes an exact candidate, permits only a small terminal write set, requires `handoff.md` to be the last durable write, or validates existing gate receipts instead of rerunning expensive suites.

## Compile checks from authority

Freeze separately:

1. candidate identity: branch, commit, tree, parent(s), archive/patch hashes, owned paths;
2. authorized writes and the one exact cleanup root;
3. required terminal semantics and nonclaims;
4. fresh-execution versus receipt-validation requirements.

An explicit task write allowlist overrides generic closeout defaults. If a contract file must remain immutable, hash it and let the authorized status record carry terminal state rather than widening the write set.

Every assertion must trace to the contract, a frozen complete manifest, or a documented class invariant. Do not make the verifier stricter merely because a stronger condition is easy to code.

## Safe terminal order

1. Opening read-only tuple/path/clean probe.
2. Parse and hash canonical gate logs; label them `receipt_validated_not_reexecuted` when not rerun.
3. Delete only the declared task-local scratch root and verify it is absent.
4. Pre-verdict read-only probe.
5. Write verification, status, and append-only log in the authorized order.
6. Read back and hash those records.
7. Write handoff last.
8. Run the prepared final verifier read-only; print timestamp, verdict, and handoff hash to stdout.
9. Leave durable `final_checked_at` null when updating it would violate handoff-last; do not add a cosmetic success write afterward.

## Runner-owned dynamic state after handoff

Separate immutable reviewer/worker outputs from runner- or supervisor-owned lifecycle projections. A task contract, review artifact, verification artifact, and handoff can be hash-frozen while `status.json` or an append-only task log is legitimately advanced by the runner after the handoff appears.

Do not require runner-owned status/log files to retain their pre-verdict hashes unless the authority explicitly freezes them and prevents lifecycle updates. Instead, the final read-only verifier should:

1. keep the task contract and worker-owned artifacts byte/hash exact;
2. parse the live status/log semantically: task id, terminal state, verdict, blocker/finding reference, and append-only chronology must agree with the handoff;
3. when a lifecycle transition is expected after handoff, prove its modification time postdates the handoff and snapshot the dynamic files at verifier start and end to ensure they stayed stable during the check;
4. keep the exact root allowlist and scratch-absence checks independent of dynamic content;
5. classify a consistent owner-correct transition as a runner lifecycle projection, not as a worker write-scope violation.

An unexpected owner, contradictory verdict, missing blocker, malformed status, non-append log rewrite, or mutation during the verifier remains a real failure. Do not edit the status/log or back-write artifacts merely to reconcile the projection; correct only an over-strict verifier assertion and rerun the complete read-only check.

## Required subset is not an exact inventory

Treat required records as a subset unless the authority explicitly freezes the complete file manifest:

```python
required_present = required_records <= actual_records
exact_surface = actual_records == declared_complete_manifest  # only when explicitly required
```

Preserve non-scratch producer evidence such as RED logs, preflight receipts, and prior gate logs. Do not reject or delete it to satisfy an invented exact-file condition. Keep cleanup independent: prove only that the exact authorized scratch root is absent, and refuse deletion if its resolved path escapes the task root or is an unexpected symlink.

## Aggregate booleans only

Keep diagnostics out of the check map:

```python
checks = {
    "exact_tuple": exact_tuple,
    "required_records_present": required_records <= actual_records,
    "scratch_absent": not scratch.exists(),
}
diagnostics = {
    "line_count": len(lines),
    "worker_file_count": len(actual_records),
}
assert all(type(value) is bool for value in checks.values())
passed = all(checks.values())
```

Integers, hashes, timestamps, sizes, and lists are evidence, not booleans. Mixing them into `all(checks.values())` can create a false failure or pass.

For exact Git closeouts, normally recheck branch/commit/tree/parents, archive and patch hashes, exact changed paths/statuses, live owned tree entries when needed, empty porcelain plus explicit staged/unstaged diff exit codes, gate receipt hash/bytes/markers, terminal JSON semantics, handoff-last modification order, scratch absence, and authorization nonclaims. Use `GIT_OPTIONAL_LOCKS=0` and avoid index refresh, fetch, disk archives, or cache-producing commands.

## Preflight the exact final verifier program

A handoff-last verifier should not introduce new handwritten literals or JSON access paths after the write boundary. Compile it from the frozen structured contract and preflight the same core program before writing the handoff:

1. Split the verifier into an immutable **core** (tuple, ancestry, range paths/hashes, numstat, artifact schemas/hashes, cleanliness, remote containment, scratch policy) and a tiny **handoff envelope** (handoff exists, names the frozen tuple, carries the authorization nonclaim, and references artifact hashes).
2. Run the exact core before handoff. The final run must reuse that same check table/functions and add only the envelope checks; do not retype a path such as `tests/test_*.py`, duplicate a commit id, or invent another field lookup in the final inline command.
3. Parse one machine manifest and derive expected path lists, range endpoints, hash fields, and budgets from it. Represent repeated range checks as data rows consumed by one function rather than copy-pasted assertions.
4. Validate every structured access path during preflight. Check required keys first and fail with a diagnostic such as `missing changes.new_helpers`; do not let a post-handoff `KeyError` reveal that the verifier was written against an imagined schema.
5. Hash the prepared verifier source or check-table representation when practical. A final command assembled from different bytes is a new verifier and must not inherit the preflight claim.
6. Keep diagnostics separate from predicates and print which contract row failed. A typo in an expected path or field location is then visibly harness evidence, not an ambiguous candidate failure.

This pattern keeps the post-handoff surface small enough that a corrected rerun should be exceptional rather than routine. If a verifier-only defect still appears, preserve the candidate byte-for-byte and follow the recovery decision below; preserve the handoff unless the verifier source itself is inside the handoff-ordered surface and an explicit administrative-reopen allowlist requires a replacement handoff-last.

## Scope temporary environments through the last external read

Pass task-local `HOME`, `TMPDIR`, Ansible temp roots, cache paths, and similar overrides in the environment of the one subprocess that needs them. Do not export them into a shell whose environment can persist across later tool calls. Otherwise a later read-only command may reuse a deleted temporary home and silently recreate it.

Treat credential helpers as stateful external programs even when Git itself is only reading a ref. For example, a command-scoped `gh auth git-credential` invocation may create value-free helper state such as a device identifier beneath `HOME`. Therefore:

1. perform every credential-backed remote read before deleting the isolated home, or restore the canonical environment before any later read;
2. run the final scratch-absence probe only after the last credential/helper/cache-producing subprocess;
3. if a deleted scratch reappears, identify the exact task-owned path, correct the environment lifetime, remove only that path, and rerun the complete closeout verifier;
4. keep candidate cleanliness and scratch cleanliness as separate predicates—a clean Git tree does not prove that an out-of-tree scratch stayed deleted.

## Validate handoff semantics, not incidental prose

Derive handoff checks from structured status/receipt fields and stable semantic markers: task/candidate IDs, commit/tree/hash values, terminal verdict, authorization nonclaims, artifact paths, and next gate. Require an exact sentence only when the contract explicitly freezes that sentence or the handoff bytes.

For multilingual or human-oriented handoffs, do not encode one English phrase as the only proof of a concept such as “independent review.” Prefer a structured `next_gate` field or verify the relevant IDs plus a language-independent token. If an over-strict prose assertion is the sole failure, classify that run as invalid harness evidence, leave candidate and durable records unchanged, correct the probe, and rerun the entire final verifier.

Apply the same rule to machine records. Unless a complete record schema is frozen, compare a required semantic projection rather than whole dictionaries. For example, a durable file record with an extra presentation field such as `path` can still match a live `{bytes, sha256, mtime_ns}` record. Normalize path identity separately when the contract requires it; optional display/provenance fields must not create a false closeout failure.

## Post-handoff failure classification

A wrong tuple, dirty worktree, out-of-scope path, bad receipt, malformed terminal record, missing required record, or surviving scratch is a real closeout failure.

If only an assertion absent from the contract fails—for example exact-inventory equality where only a required subset exists, or a numeric diagnostic aggregated as a boolean—the verifier evidence is invalid, not the candidate. Then:

1. make no candidate, source, repaired-child, or producer-evidence changes;
2. label the first stdout result as a verifier-only false failure and retain its failed predicate plus no-write snapshot;
3. correct only the harness logic and rerun the complete read-only verifier, not only the failed predicate;
4. when the verifier source is outside the handoff-ordered surface, preserve the handoff byte-for-byte;
5. when the verifier source is inside that surface, change it only if the contract explicitly permits an administrative reopen: update only continuation-owned status/log, recompute their hashes, rewrite the continuation handoff as the final durable write, then rerun no-write; otherwise stop with a blocker;
6. report every attempt honestly in stdout/chat/parent handoff and never imply the original worker authored the repair.

A corrected rerun is an exception to the intended single final pass. Prepare and inspect the verifier before handoff to avoid it; if it happens, never claim there was only one attempt. The detailed generic procedure belongs to `agent-workflow-verification` under its semantic-complete lifecycle closeout reference; keep this governance reference focused on contract authority and ownership.

## Delivery

Report the authoritative verdict and timestamp, exact candidate tuple, path ownership and cleanliness, archive/patch hashes, absolute terminal-record paths and hashes, cleanup result, authorization boundary, and any invalid harness attempt. Do not promote receipt validation to fresh suite execution, compile-only evidence to runtime execution, or producer PASS to integration authorization.
