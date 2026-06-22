# Maintenance Log Schema

`maintenance-log.jsonl` is append-only history. It is not the current-state database.

Each line is one JSON object. Prefer adding a `correction` or `supersede` event over editing old history.

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
