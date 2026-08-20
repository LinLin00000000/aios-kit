# Frozen-base implementation under concurrent drift

Use this checklist when a canonical producer is authorized against an exact target version/hash and the contract says to stop if that identity changes. This is an implementation boundary, not merely an audit freshness check.

## Authority rule

General advice to re-read and rebase an exact patch does not override an explicit frozen-base stop condition. Once the required preimage differs, the producer no longer owns a safe mutation surface. A file that already appears to contain some intended behavior is still not evidence that the producer may claim or complete the change.

## Fail-closed sequence

1. **Freeze before writing.** Record every canonical target's realpath/existence/SHA-256 and relevant repository status. For a protected dirty Git file, separately record content hash, worktree-diff hash, staged-diff hash/byte count, path status, and index blob when useful.
2. **Compare the named guard exactly.** Compare the required and observed version/hash without normalizing, rebasing, or bumping the version.
3. **Stop on mismatch.** Do not apply the stale patch, read detailed patch artifacts merely to recreate it, overwrite unrelated additions, create a success-shaped root deliverable, stage/commit/push, or mutate shared workflow state. Write only the worker-private blocker record allowed by the contract.
4. **Persist a compact blocker receipt.** Record expected/actual identity, canonical pre-state, related Git state, exact writes performed, skipped semantic checks, risks, and the re-entry condition. Use a terminal state such as `blocked` with a concrete code like `CONCURRENT_DRIFT`, not `completed` or a vague warning.
5. **Run post-readback.** Re-hash every canonical target and the protected dirty/staged surfaces. Confirm the intended root deliverable remains absent when no implementation occurred and that the write set stayed inside the worker-private allowlist.
6. **Classify verification honestly.** Boundary checks may pass: frontmatter parses, canonical bytes are unchanged, staged state is unchanged, and only private evidence was written. Mark implementation-semantic checks `NOT_RUN` rather than claiming they passed because no bytes changed.
7. **Require explicit re-entry.** Resume only after a serialized owner handoff supplies a fresh exact base or explicitly authorizes a rebase against the observed target. Never replay the old patch by default.

## Receipt shape

A useful implementation receipt contains:

```text
status/verdict
required identity vs observed identity
pre/post hashes for every canonical target
protected Git content/diff/staged state
canonical_modified_paths (empty on guard failure)
worker_private_paths_modified
boundary verification results
semantic checks marked NOT_RUN
risk/omissions and exact re-entry condition
```

A handoff cannot embed its own stable hash. Hash the durable receipt and other worker records; list the handoff itself as a self-reference or record its hash in an external final readback.

## Pitfalls

- Byte identity proves an ID count did not increase, but it does not prove the requested policy update exists.
- A parseable newer frontmatter version is evidence of drift, not permission to overwrite it.
- Do not turn a blocker report into the requested user deliverable; that can make a failed implementation look complete.
- Do not inspect or absorb another owner's unrelated dirty content beyond what is needed to establish and preserve the boundary.
