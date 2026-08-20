# Canonical synthesis receipt pattern

Use this reference for durable LLL/AIOS synthesis work that turns several accepted handoffs or publication receipts into one human-facing root deliverable. It is a class-level pattern, not a template for any one project.

## 1. Freeze the evidence boundary

Read, in order:

1. current mission and recovery contract;
2. task contract and the current queue/status needed to establish ownership;
3. compact worker handoffs and exact review/publication receipts;
4. selected structured artifacts only when a handoff leaves a material claim unresolved.

Honor explicit sealed/excluded inputs. Exhaustive reading is not evidence quality. Keep the source list in the receipt so a future validator can tell what was consumed and what was intentionally not consumed.

## 2. Four-way claim classification

Every material statement in the root synthesis belongs to one and only one class:

| Class | Meaning | Minimum proof |
|---|---|---|
| Accepted decision | Owner/supervisor has explicitly accepted a policy or action boundary | decision record, accepted handoff, or applied owner receipt |
| Current/published fact | A current readback or publication receipt says the object exists in that state | exact status/hash/tree/readback receipt with timestamp |
| Worker recommendation | A producer/reviewer proposes a disposition or future action | handoff/artifact marked recommendation; never treat as authorization |
| Deferred/blocked | Deliberately postponed, fail-closed, or outside scope | explicit gate, exclusion, missing prerequisite, or blocker record |

Keep `integration_allowed`, `publication_allowed`, and actual publication/readback separate. A producer PASS is not a reviewer verdict; a reviewer verdict is not a push; a push is not proof that unrelated instance state changed.

## 3. Minimal canonical receipt

Use JSON for machine accounting and Markdown for the human view. Bind the receipt to the final root bytes, not to a draft:

```json
{
  "schema": "<domain>.canonical-receipt.v1",
  "task_id": "<task>",
  "verdict": "PASS | PASS_WITH_NOTES | FAIL",
  "blocking_findings": [],
  "canonical": {
    "path": "<absolute-or-owner-relative-path>",
    "language": "<requested-language>",
    "bytes": 0,
    "sha256": "<hash>",
    "line_count": 0,
    "non_whitespace_char_count": 0,
    "whitespace_token_count": 0
  },
  "summary": {
    "locator": "<stable heading range>",
    "bytes": 0,
    "sha256": "<hash>"
  },
  "input_receipts": [],
  "write_boundary": {
    "root_product_write": "<one canonical path>",
    "internal_write_root": "<task-local root>",
    "shared_state_modified": false
  },
  "next_owner": "<validator or closeout owner>"
}
```

Define the summary range precisely (for example, from an executive-summary heading to the next top-level heading) and hash the exact UTF-8 bytes of that range. If “word count” is reported for CJK text, label the metric rather than implying an English word segmentation algorithm.

## 4. Write and freeze order

1. Write the single root deliverable.
2. Compute its final byte/hash/summary metrics.
3. Write task-local receipt, handoff, status, and log records using those metrics.
4. Do not edit the root after the receipt is bound. If a correction is necessary, recompute every bound metric and rerun the validator; do not patch only the receipt.
5. Keep shared queue/recovery/validation writes under the supervisor or deterministic owner. A synthesis worker should not repair historical receipts or silently normalize unrelated status.

## 5. Final no-write probe

After the last durable edit, use an OS tempfile (prefix `hermes-verify-`) for a read-only verifier and remove it in the same shell operation. The probe should:

- assert the required root and task-local files exist;
- parse all task-local JSON records;
- recompute canonical and summary hashes/metrics and compare them with receipt/status;
- check required headings, language, scope/exclusion markers, and explicit next owner;
- scan for accidental secret-value patterns and forbidden sealed-input markers;
- verify no accidental direct-`$HOME` copy exists when the worksite policy requires an owner boundary;
- print a structured result, exit nonzero on failure, and report cleanup success.

Call this **structural/ad-hoc verification**. It is not a product test suite, build result, or publication authorization. A pending independent validator is a sequence gate, not a blocker, when all producer acceptance criteria and required artifacts are present.

## 6. Independent canonical-only validator

Use this pass when a producer has frozen a finite validation surface and the validator may write only task-local review records.

1. Copy the contract's exact file list, expected byte counts, hashes, and declared algorithms into the verifier. Recompute from raw bytes. Any target mismatch is a blocker: stop semantic review and recommend the smallest owner repair/refreeze.
2. Recompute text metrics with explicit definitions. `whitespace_token_count` normally means `len(text.split())`, not the number of whitespace characters; CJK coverage is a separate Unicode-range diagnostic, not an English word count.
3. Check semantic gates against the frozen bytes: required headings and order, requested language, scope/exclusions, accepted/current/recommendation/deferred separation, minimal lineage, and the next owner/gate.
4. Cross-read publication facts with exact commit/tree/parent, local cleanliness, remote ref/tree, and receipt time. Reproduce the receipt's exact diff rendering; `git diff --binary` and `git diff --binary --full-index` are different byte streams and their hashes are not interchangeable.
5. Treat `integration_allowed` as typed authority. A canonical closeout allowance does not grant push, merge, publish, force-update, or unrelated mutation rights.
6. Scan for secret **values**, not merely security terminology. Honor sealed paths without traversing them, and state that exclusion as an evidence boundary. Classify extra root files by declared role and receipt lineage before calling them a second canonical; scan direct `$HOME` children for task-slug or canonical orphans without broad home traversal.
7. Reconcile task, recovery, runner, and validation snapshots. An active validator plus pending shared validation is expected before closeout; record it as a future false-WIP risk if the supervisor fails to clear active/queued/running/delegation afterward. Treat documented legacy terminal aliases as terminal-compatible rather than inventing live work.
8. Use `PASS_WITH_NOTES` when blockers are zero and the frozen surface is exact but lifecycle cleanup, sealed-scope limits, or other nonblocking evidence boundaries remain visible.

## 7. Terminal order and verifier self-repair

Keep the validator's write set inside its declared task root; shared queue/recovery/validation remains supervisor-owned unless the contract explicitly grants otherwise.

1. Write review and verification artifacts.
2. Recompute their bytes/hashes.
3. Write a short handoff, append-only log, and task-local terminal status that bind those artifacts.
4. Run one final no-write probe: parse all outputs, recompute target and receipt hashes, verify downstream hash bindings, check the allowed file set, confirm shared/frozen surfaces stayed unchanged, and confirm scratch cleanup.
5. Treat handoff/status as provisional until this probe passes. If the validator discovers its own parser, metric, or assertion bug, do not touch the frozen target. Mark the earlier evidence invalid or superseded, fix only the probe/task-local evidence, recompute every downstream hash and handoff/status binding, preserve the log chronology, and rerun the complete final probe once.
6. If the contract forbids scratch, create none. Otherwise clean only the declared scratch root or OS tempfile and report cleanup; do not widen cleanup to unrelated files.

## Common pitfalls

- Reading every raw artifact after the contract explicitly narrows the input boundary.
- Writing a long narrative that blurs recommendations into decisions.
- Hashing a draft, then editing the root or handoff afterward.
- Treating a nonzero maintenance diagnostic on pre-existing stale data as a workflow blocker when the changed-target contract passes.
- Claiming “published” from `integration_allowed=true` without an exact remote/readback receipt.
- Creating a second root report, duplicate registry, or same-name skill when the procedural owner is not curator-addressable.
- Calling a structural verifier “all tests passed,” or hiding a verifier incident instead of correcting the probe once and rerunning it.
- Retrying a main-body patch after the curator reports a size ceiling; move durable detail into `references/`, keep the umbrella pointer small, and use an owner-led split rather than creating a same-name duplicate.