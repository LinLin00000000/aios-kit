# Maintenance Log Schema

`maintenance-log.jsonl` is append-only history. It is not the current-state database.

Each line is one JSON object. Prefer adding a `correction` or `supersede` event over editing old history.

## Authoritative write path

Use the native AIOS command from the installed `aios-kit` entrypoint:

```bash
aios ops log append \
  --actor hermes-agent \
  --type correction \
  --scope example-scope \
  --summary "One sentence summary" \
  --status done \
  --verification "readback passed" \
  --json
```

The command validates the existing JSONL prefix, obtains an exclusive lock, opens the file with `O_APPEND`, writes one complete line, calls `fsync`, and verifies that the old prefix and new line read back byte-for-byte. The read-only `scripts/aiops.py` interface is for index/query/check operations; it is not a write path.

Do not use `write_text`, `open(..., "w")`, `truncate`, `os.replace`, `cp`, `rsync`, or an ad-hoc Python script against the live log. On ext4, the active log should also be protected with `chmod 0600` and `chattr +a`.

## Recommended object

```json
{
  "schema_version": 1,
  "ts": "2026-01-01T12:00:00+00:00",
  "date": "2026-01-01",
  "actor": "human|agent|script|cron",
  "type": "maintenance|decision|inventory|check|incident|correction|supersede",
  "scope": "service-or-host-or-repo",
  "summary": "One sentence summary",
  "objects": ["host", "service", "path"],
  "changes": ["What changed"],
  "verification": ["Command/check and result summary"],
  "impact": ["Expected impact or none"],
  "followups": ["Open item or empty"],
  "artifacts": ["Evidence path or URL"],
  "status": "done|pending|failed|superseded",
  "tags": ["short-tag"]
}
```

## Rules

- Include an explicit timezone offset in `ts`.
- Do not store secret values.
- Keep summaries short; put large evidence in `evidence/` and reference paths.
- Current facts updated by the event should also be reflected in `resources.md` or service cards.
