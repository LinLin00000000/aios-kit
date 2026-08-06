# Matter materials v0

Matter materials is a narrow, file-native CLI for associating one registered local text file with one existing formal Matter. The source remains canonical. A Matter may either retain only a hash-bound reference or keep a Matter-local immutable snapshot for recovery.

This feature does **not** create or reopen a Matter or Worksite, create tasks/waves/events, change attention, update recovery or Policy, adopt a decision, promote an asset, or write a global material index.

## Commands

```bash
aios matter material attach <matter-id> \
  --source <source-id> \
  --owner-ref <owner-ref> \
  --locator <source-root-relative-path> \
  --role reference|evidence|decision_input|deliverable \
  --custody reference_only|immutable_snapshot \
  --sensitivity internal|internal_restricted \
  [--dry-run] [--json]

aios matter material list <matter-id> [--json]
aios matter material verify <matter-id> [<material-id>|--all] [--json]
```

`--custody` and `--sensitivity` are always explicit; v0 has no automatic/default classification. `attach --dry-run` performs Matter/Source/Managed-Zone resolution, path and sensitivity gates, stable source reading, UTF-8 validation, hashing, and existing-record/snapshot checks, but creates no directory or file.

Only formal Matters whose canonical `internal/matter.json` has an explicit string `lifecycle.state` exactly equal to `active` or `paused` are attachable. Missing, unknown, or malformed raw lifecycle data fails closed rather than inheriting a derived index fallback. `attention=paused` is accepted and never triggers a reopen. Closed/archived Matters and inferred Worksites are rejected for attach. List and verify remain available for formal Matters without changing or admitting against lifecycle state.

## Canonical storage

The live explicit Source Registry record `aios-managed-zone` resolves the instance-specific data root. Under its existing `managed/` directory, each Matter owns one compact current-state manifest and optional snapshots:

```text
<aios-managed-zone>/managed/matter-materials/<matter-id>/
├── materials.json
└── snapshots/
    └── <full-lowercase-source-sha256>
```

There is no global CAS, global index, JSONL history, event, or separate receipt. Identical bytes may be reused inside one Matter, but v0 does not deduplicate across Matters.

The manifest shape is:

```json
{
  "schema": "aios.matter.materials.v0",
  "matter_id": "matter_example",
  "materials": []
}
```

Each material record contains only:

- deterministic `material_id`;
- Matter ID, role, and offset-qualified `attached_at`;
- canonical Source ID, explicit owner reference, root-relative locator, `regular_utf8_text`, SHA-256, and byte count;
- `authority=source_canonical`;
- explicit custody and optional canonical snapshot path;
- explicit `internal` or `internal_restricted` handling;
- `adoption=not_adopted`, `execution=none`, and `lifecycle_effect=none`.

The association ID is `mat_` plus the SHA-256 of compact sorted-key JSON over:

```json
{
  "matter_id": "...",
  "owner_ref": "...",
  "relative_path": "...",
  "role": "...",
  "source_id": "..."
}
```

Custody is intentionally excluded so the same association can be explicitly upgraded.

## Intake gates

Both custody modes apply the same source gates before any Matter-material write:

1. Resolve exactly one **explicit** Source Registry record and exactly one local root; project projections, missing/duplicate/conflicting records, non-local or multiple roots, and unknown metadata fail closed.
2. Require a canonical root-relative POSIX locator: no absolute path, empty component, `.`, `..`, backslash, or NUL.
3. Open every locator component and the leaf with no-follow semantics. Symlink components and non-regular files are unsafe.
4. Accept at most 16 MiB, strict UTF-8, and no NUL byte.
5. Read one file descriptor and require stable device, inode, size, and mtime before/after the read; confirm the locator still binds to that identity immediately before commit.
6. Reject a Source record classified `sensitive`. A `mixed` Source requires explicit `internal_restricted`. `private`, `internal`, and `public` Source metadata still require the caller's explicit v0 sensitivity; this does not claim that any content is safe for publication.
7. Enforce Source include/exclude path rules and reject invalid/unknown policy shapes.
8. Reject a source leaf inside this Matter's canonical materials directory, or an outside path whose inode aliases an existing manifest, snapshot, or staging file in that write surface.

For `immutable_snapshot`, the live Managed Zone `backup_status` must additionally be `planned` or `verified`. This reports the boundary only; it does not claim the newly attached snapshot has completed an off-host backup.

CLI and JSON output contain metadata, paths, enums, hashes, byte counts, states, and verdicts only—never source body, excerpt, or generated summary.

## Custody and idempotency

- `reference_only`: writes the association/hash record and creates no `snapshots/` directory.
- `immutable_snapshot`: installs exact source bytes at `snapshots/<sha256>` before the manifest points to them.
- Repeating the same association with the same source bytes is `already_attached` and byte/mtime no-op.
- `reference_only` may be explicitly upgraded to `immutable_snapshot`; `attached_at` and `material_id` remain stable.
- An existing snapshot is never downgraded or removed by a later reference request.
- The same association with changed source hash/bytes fails as `source_drift_conflict`.
- An existing canonical snapshot with mismatched, unsafe, or unreadable bytes fails as `snapshot_conflict` and is never overwritten.
- A sensitivity mismatch on the same association fails closed rather than silently changing metadata.

The v0 mutation path requires local directory `flock` support (implemented on Linux). It rereads and validates the manifest while locked. Snapshot bytes are staged, fsynced, read back, installed using Linux atomic `renameat2(RENAME_NOREPLACE)`, and read back again. The sorted manifest is staged, fsynced, atomically replaced, and followed by directory fsync. The source is never written, moved, renamed, or deleted. Unsupported mutation platforms fail closed without making the wider `aios` CLI unimportable.

## Read-only list and verify

`list` reads only `materials.json`; it does not hash source or snapshot bytes. JSON reports `source_state=unchecked` and `snapshot_state=unchecked` or `not_required`.

`verify` fresh-reads source and required snapshot bytes with the same no-follow text safety checks. It never updates a record, timestamp, event, index, or mtime.

Exact states:

- source: `match`, `missing`, `drifted`, `unreadable`, `unsafe`;
- snapshot: `not_required`, `match`, `missing`, `drifted`, `unreadable`, `unsafe`;
- verdict: `pass`, `recoverable_warning`, `fail`.

| Custody and states | Verdict | Exit status |
|---|---|---|
| reference + source `match` + snapshot `not_required` | `pass` | zero |
| snapshot + source `match` + snapshot `match` | `pass` | zero |
| snapshot + source non-match + snapshot `match` | `recoverable_warning` | zero |
| snapshot + snapshot non-match | `fail` | non-zero |
| reference + source non-match | `fail` | non-zero |

Verification does not repair, rebind, delete, downgrade, overwrite, adopt, or trigger work.

## v0 limits

V0 intentionally excludes directories, symlinks, binary/remote/large/secret intake, source rebinding/version lineage, detach/delete/purge, automatic adoption/promotion, cross-Matter search, global CAS/refcounts/GC, distributed locking, independent backup/restore proof, UI, daemon, event bus, and plugin automation.
