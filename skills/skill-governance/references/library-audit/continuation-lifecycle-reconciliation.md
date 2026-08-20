# Continuation-Owned Lifecycle Reconciliation

Use this reference when a producer's content artifacts are intentionally immutable but its receipt/status/log/handoff lifecycle claims contain stale, conflicting, or untrusted hashes.

## Contract and authority model

Keep three evidence classes separate:

1. **Live bytes** — the current regular, non-symlink files and their `sha256`, byte count, line count, mode, device, inode, and mtime.
2. **Declared identities** — the governing contract, sealed manifests, producer receipt fields, dispatcher scaffolds, and handoff claims.
3. **Authority gates** — whether content review, runtime execution, or integration is allowed.

A claim is not made true by appearing in a contract or handoff. A live hash is not automatically authoritative if the contract froze a different identity. Record both sides and classify the conflict before choosing a verdict.

## Read-only evidence sequence

1. Read the governing repository instructions, continuation task, and reconciliation contract in the mandated order.
2. Verify the contract's exact hash and identity metadata before trusting its semantic fields. For every authoritative input and current sealed manifest, compare every declared field that exists: hash, bytes, lines, mode, device, inode, and regular/non-link identity.
3. Snapshot the producer's complete declared file set before the reconciliation interval. Include mtime for lifecycle ordering, but never use mtime as a substitute for content hashing.
4. Check continuation preconditions: required receipt absent, recognized scaffolds exact, forbidden successor tasks absent, and no unexpected write surface.
5. Snapshot Git read-only: worktree status, `HEAD`/main/candidate resolution, all relevant refs, worktrees, and replace refs. Use lock-free/read-only Git settings where available; never refresh, prune, fetch, or write refs.
6. Compare live producer bytes against both the contract and any external declaration supplied by the task. If a prompt, contract, receipt, status, or handoff disagrees, preserve the disagreement as a named mismatch; do not silently normalize to the most convenient value.
7. On any identity, scaffold, required-absence, mtime-order, or concurrent-drift mismatch, use `NO_VERDICT` and preserve the producer evidence. Do not rewrite the producer, rerun its driver, perform content review, contact a remote, or grant runtime/integration authority.
8. Take a second exact snapshot after the read-only interval. A continuation-owned write is not permission to mutate producer/manifests/Git; prove those surfaces stayed byte/identity stable.

## Continuation receipt and write-order contract

Write only the explicitly allowlisted continuation files, in this order:

```text
artifacts/lifecycle-reconciliation-receipt.json
status.json
log.txt
handoff.md
```

The receipt is the root of the new chain:

- Bind only already-existing producer, sealed-manifest, contract, and Git facts.
- Do not embed hashes of the continuation's future `status.json`, `log.txt`, or `handoff.md`.
- Include the stale embedded/claimed values verbatim, alongside the live values they fail to match.
- State `content_evidence_retained=true`, `lifecycle_gate_pass=false`, `remote_execution_allowed=false`, and `integration_allowed=false` when lifecycle reconciliation is blocked.

After the receipt write returns, fresh-read the bytes and calculate its settled hash. Then write `status.json` with that receipt hash, fresh-read it, and use its settled hash in the log. The final handoff may bind the settled receipt/status/log hashes, but never its own hash. The handoff is the last write and the last tool call; do not verify, patch, or summarize the handoff with another tool call afterward. The write order is evidence, but report measured mtime order separately rather than assuming the filesystem honored it.

## Mismatch taxonomy

Use explicit fields rather than one undifferentiated failure flag:

- `contract_identity_mismatch`: contract bytes/stat differ from the required freeze.
- `authoritative_input_mismatch`: a listed input or sealed-manifest member differs.
- `live_vs_claim_mismatch`: current bytes differ from a producer/dispatcher/handoff claim.
- `embedded_hash_mismatch`: a receipt embeds an obsolete child hash.
- `handoff_claim_mismatch`: handoff claims hashes different from settled bytes.
- `mtime_order_mismatch`: lifecycle files do not satisfy the required settled order.
- `scaffold_mismatch`: continuation pre-existing scaffolds drifted before the continuation took ownership.
- `absence_or_surface_mismatch`: forbidden successor task, scratch, Git, or other protected surface is present/changed.

A mismatch can block lifecycle without proving a product, content, or remote failure. Preserve that distinction in `classification` and in the handoff.

## Minimal receipt fields

A useful receipt should make the next owner able to verify the decision without rereading the whole session:

```json
{
  "result": "NO_VERDICT",
  "content_evidence_retained": true,
  "lifecycle_gate_pass": false,
  "remote_execution_allowed": false,
  "integration_allowed": false,
  "producer_files": {"pre": [], "post": [], "exact_stable_pre_post": true},
  "sealed_manifests": {"T014": [], "T023": [], "exact_stable_pre_post": true},
  "mismatch_register": [],
  "required_absences": {},
  "git_surface": {"pre": {}, "post": {}, "stable_pre_post": true}
}
```

Do not collapse a detailed mismatch register into `lifecycle_gate_pass=true` merely because content evidence is useful. A continuation receipt is a reconciliation record, not a producer repair or an authorization token.

## Closeout checklist

Before the final handoff, confirm from fresh reads:

- receipt JSON parses and its settled hash is the one bound by status;
- status parses and its settled hash is the one bound by log/handoff;
- log contains the settled receipt/status hashes;
- producer five-file identities and sealed manifests match both snapshots;
- required absences remain absent;
- Git/main/candidate/refs/worktrees/replace refs are unchanged;
- no future continuation hash appears in the receipt;
- the verdict is one of the contract's allowed blocked outcomes, normally `NO_VERDICT` for any unresolved precondition;
- no tool call remains after writing the handoff.
