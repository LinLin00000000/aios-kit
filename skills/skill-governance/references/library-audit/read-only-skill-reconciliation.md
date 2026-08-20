# Read-only Skill Reconciliation

Use this procedure when a runtime skill may be legacy, locally patched, externally installed, or only partially governed by a manifest. The objective is to establish provenance and recommend a reversible governance path without changing runtime content, install state, source repositories, or consumer configuration.

## Evidence surfaces

Keep these surfaces separate; none alone proves ownership or modification:

1. **Runtime tree** — exact path, realpath, symlink/copy status, file manifest, content hash, generated files, and observed timestamp.
2. **Owner manifest** — declared class (`external`, first-party, local-only), source, target, mode, and enabled state.
3. **Install state** — recorded installed path/hash and the state file the live CLI actually reads. A second legacy state file is evidence of metadata drift, not a co-owner.
4. **Installer lock** — source URL, skill path, subtree/folder hash, install/update timestamps, and package/plugin metadata.
5. **Pinned upstream** — the commit/tree/tag represented by the lock or visible version.
6. **Current upstream** — current repository HEAD plus the current subtree SHA at the skill path.
7. **Canonical successor/history** — Git history, prior Worksite snapshots, migration reports, and current canonical source.
8. **Consumers** — active loader configuration and runtime-visible inventory. Directory existence or an old session mention alone does not prove a current consumer.
9. **Publication boundary** — license plus whether the local overlay contains private paths, user facts, credentials, or non-portable policy.

Record `observed_at` for volatile surfaces and re-read them before delivery when parallel work may be occurring.

## Runtime inventory, enabled, trigger, and distribution surfaces

For a live library audit, keep four logical surfaces separate before judging size, duplication, or retirement:

1. **Complete runtime inventory** — the logical names the current loader can discover on the current platform/environment, including disabled entries. This is not a raw count of `SKILL.md` files: platform-gated packages, archives/caches, nested candidates, and same-name aliases can make filesystem counts differ.
2. **Enabled descriptor surface** — the config-qualified names and frontmatter descriptions eligible for prompt exposure. Record disabled-but-retained entries separately so shelfing is not mistaken for deletion.
3. **Trigger/body-load surface** — which descriptors are actually presented to the model and which full skill bodies are loaded for representative requests. Descriptor count or character volume is only a potential exposure metric; use fresh-session positive, negative, and ambiguous trigger cases before claiming context savings.
4. **Distribution/managed surface** — manifest declarations, install-state receipts, installer locks, deployment mode, and source ownership. A runtime may expose a skill that is unmanaged, or a manifest may manage a path that loses loader precedence to a same-name alias.

Use the runtime's own loader and prompt-builder implementation to explain precedence, deduplication, platform/tool/environment gates, and description injection. Do not assume a frontmatter field imported from another skill ecosystem is honored: prove that the installed runtime consumes it, and verify config/description changes in a fresh session. CLI source labels such as `local`, `builtin`, or `hub` describe one runtime classification; join them with manifest, lock, install-state, realpath, and curator ownership before declaring the truth source.

Treat doctor/validate commands as scoped assertions. Read their implementation or documented check list and report exactly what they prove. An existence/dependency/path doctor does not prove install-state hash reconciliation. Recompute drift only with the owner's exact hash algorithm and scope; classify mismatches as leads, not local-edit verdicts. For module packages, prefer component/member receipts when a whole-tree hash would let unrelated CLI, template, test, or documentation changes mark a skill payload stale.

Measure structural tax through broad/overlapping trigger descriptions, expected multi-body fan-in, duplicate semantic owners, copied private/current facts, and reconciliation ambiguity—not inventory count alone. A useful machine-readable evidence row includes logical name, enabled state, runtime source label, governance class, path, realpath, symlink/copy mode, manifest/state/lock membership, platform/environment qualification, frontmatter description, body/reference size, and observed timestamp.

## Three-axis verdict for moving runtime packages

Never collapse these three questions into one verdict:

1. **`semantic_verdict`** — whether the bounded bytes actually read express the required behavior.
2. **`current_live_binding`** — whether the evidence binds the current runtime bytes, rather than only a historical freeze or an earlier read.
3. **`publication_readiness`** — whether source ownership, provenance, management addressability, publication boundary, and a quiescent complete-package freeze are sufficient to publish or adopt.

A latest snapshot may be semantically correct while its historical freeze is stale and publication remains blocked. Keep the old freeze immutable: recompute its manifest/validation digests, compare each frozen member with live bytes, report exact unchanged/drifted counts, and separately inventory every current sibling file outside the old freeze. Do not silently widen a six-file receipt into approval of a larger package tree.

When a package changes during the audit, take timestamped bounded snapshots and record version, bytes, SHA-256, realpath/inode, and package-relative paths. A short stable interval is only a bounded observation, not proof of owner quiescence. Classify continued movement as concurrent owner evolution, retain useful semantic findings as `PASS_WITH_NOTES` when justified, and fail closed on live binding/publication until a serialized owner handoff and package-wide refreeze exist.

If bare and qualified names resolve the same runtime root but ownership metadata conflicts—such as `created_by=agent` on the bare record and `created_by=null` on the qualified record—classify management addressability as `SPLIT_NAMESPACE_UNPROVEN`. Readability is not mutability. Under a read-only contract, do not probe `skill_manage` by attempting a write. If no canonical source owner is proven, recommend runtime-only retention with a pending-owner decision; never create a parallel repository or same-name replacement merely to satisfy a publication/push expectation.

## Hash discipline

Do not compare hashes until their algorithms and scopes are known.

- A Git blob SHA identifies one file's bytes and mode-independent content.
- A Git tree/subtree SHA identifies names, modes, blobs, and nested trees.
- An installer `skillFolderHash` may be a Git subtree SHA, but verify it through the upstream API instead of assuming.
- A deployment `installed_hash` is tool-specific. Read or invoke the owner's exact hashing implementation, including ignored paths and delimiters.
- A locally computed directory SHA is useful only when its algorithm is recorded.

A mismatch between install-state and runtime is **not** sufficient evidence of a user patch. First compare the runtime tree with the pinned upstream subtree and current upstream subtree. Common outcomes:

| Runtime vs pin | Runtime vs current | Interpretation |
|---|---|---|
| exact | differs | pinned external copy; upstream update available |
| differs narrowly | pin/current same | genuine local patch |
| differs | differs | three-way review required |
| exact | exact | install-state/lock metadata drift if recorded hash differs |

## Directory-level comparison

For every external skill, report counts and path lists for:

- same files;
- locally modified files;
- local-only files;
- upstream-only files;
- generated/cache files excluded from source comparison.

Compare both `runtime -> pinned` and `runtime -> current`. Inspect changed file content only after the directory manifest identifies the small changed surface. For large public repositories, GitHub tree/blob APIs can establish the comparison without cloning or writing to disk.

When a visible skill version exists but no lock entry does, treat the matching upstream tag as an **inferred pin**, and label the inference. Require directory evidence (for example, all base files match except a documented local overlay), not just a matching version string.

## Legacy payload coverage

Before thinning or archiving a legacy skill, classify every source file:

1. **Exact Git-history coverage** — the same blob exists in canonical Git history.
2. **Exact Worksite/archive coverage** — the same bytes exist in an immutable historical workspace.
3. **Semantic migration** — a corresponding path/concept exists in the successor but was renamed or evolved.
4. **Runtime-only evidence** — no independent exact copy is proven.
5. **Generated artifact** — cache/bytecode that should not influence preservation decisions.

Use Git blob IDs to find exact historical coverage across renamed paths. For semantic migration, cite the migration commit/report and compare the legacy primary document with the successor's initial commit; never describe semantic similarity as byte-exact backup.

If any meaningful file remains runtime-only, do not delete the legacy payload. Make the future change set start with a content-addressed private archive, then thin/remove the runtime copy.

## Consumer proof

Rank consumer evidence:

1. enabled loader configuration plus current runtime-visible skill inventory;
2. an active symlink/install target documented by the consumer;
3. current process/workflow evidence;
4. recent session use as secondary historical context;
5. path presence or old mentions only — insufficient by themselves.

A skill explicitly disabled in the current loader should be reported as having no current consumer through that loader, even if it remains on disk. Do not infer all-agent consumption from a directory named `universal`.

## Governance decision patterns

- **Keep external / rebase** when local equals a pinned upstream or the local delta is redundant with a stronger canonical owner.
- **Adopt/self-host** only for durable, unique local policy that warrants ongoing maintenance and whose license/publication boundary permits it.
- **Private archive then remove** when no current consumer exists and the overlay contains historical or user-specific material.
- **Thin alias** when a legacy name still has compatibility value but its payload duplicates a canonical successor. Preserve runtime-only files first.
- **Retain temporarily** when consumer or backup proof is incomplete; state the exact evidence needed to unblock the decision.

Every recommendation should include: disposition, owner, delta value, risk, human-decision flag, exact future change steps, rollback, verification, and blockers. Keep implementation authorization separate from the read-only recommendation.

## Checkpoint and closeout discipline

Do not postpone both deliverables until the end of a long investigation. After each evidence phase, persist a bounded checkpoint inside the authorized task directory:

1. runtime/metadata inventory;
2. upstream comparison matrix;
3. legacy/history/consumer matrix;
4. final recommendations.

Before delivery:

- re-snapshot volatile paths and hashes;
- label any concurrent drift rather than silently mixing observations;
- validate JSON syntax/schema and every reported local path;
- scan only the new artifacts for secret patterns and redact values as `[REDACTED]`;
- verify the write set is limited to the authorized task directory;
- state explicitly which operations were not performed (sync, force, adopt, archive, stage, commit).

If the normal installer cannot be used during a read-only audit, continue provenance work through Git/GitHub read APIs and defer mutation. The durable lesson is to separate reconciliation from installation, not to encode a permanent claim about tool availability.
