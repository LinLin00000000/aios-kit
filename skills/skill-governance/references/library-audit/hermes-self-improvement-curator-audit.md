# Hermes self-improvement and Curator audit reference

Use this reference when a Hermes profile appears to create, modify, or archive Skills without an explicit foreground request.

## Two separate automation paths

### Post-turn self-improvement review

The normal Agent turn accumulates two independent counters:

- `memory.nudge_interval`: user-turn counter for a memory review.
- `skills.creation_nudge_interval`: tool-iteration counter for a Skill review.

When a threshold is reached after a successful, non-interrupted response, Hermes starts a background review fork with a snapshot of the completed conversation. The Skill portion can use `skill_manage` to create or modify a Skill. It is a procedural-memory mechanism, not model training, and its work is not appended to the active conversation.

The effective configuration overrides defaults. A zero Skill interval disables this automatic Skill-review trigger; it does not disable Skill loading or explicit foreground `skill_manage`/`/learn` actions.

### Curator maintenance

Curator is a separate inactivity-triggered maintenance pass. It has:

- deterministic transitions: `active -> stale -> archived` for eligible, inactive Skills;
- optional LLM consolidation controlled by `curator.consolidate`;
- ownership and protection rules for managed, bundled, hub, external, pinned, and cron-referenced Skills;
- recoverable archive and backup behavior rather than automatic hard deletion.

`curator.consolidate: false` means prune-only, not Curator-off. `curator.enabled: false` is the complete Curator disable switch.

## Evidence and ownership checklist

1. Read effective values with `hermes config get`, not only the example/default file.
2. Read `hermes curator status` for current run gates, managed/unmanaged counts, and last summary.
3. Reconcile the active `~/.hermes/skills/` tree with usage/provenance records and external/bundled/hub inventories.
4. Treat `created_by: agent` as a Curator-management policy marker, not immutable authorship proof. Pre-marker and foreground-created records may be intentionally unmanaged.
5. Check both staged writes (`/skills pending` or `~/.hermes/pending/skills/`) and historical archives (`hermes curator list-archived`). An archive entry does not prove a recent Curator action.
6. Do not mutate a bundled, hub-installed, external, pinned, or unmanaged/user-owned Skill during autonomous review. Recommend foreground `hermes curator adopt <name>` when ownership transfer is desired.
7. Keep current counts and timestamps in an audit report or Worksite; keep this distinction and procedure in the class-level umbrella.

## Control matrix

| Goal | Control | Important boundary |
|---|---|---|
| Stop automatic post-turn Skill learning | `skills.creation_nudge_interval: 0` | Existing Skills and manual management still work |
| Review every Skill write | `skills.write_approval: true` | Stages `skill_manage` writes; does not by itself stop deterministic Curator archival |
| Stop all automatic Skill-library maintenance | `skills.creation_nudge_interval: 0` plus `curator.enabled: false` | Apply on the next Agent initialization/session; do not silently restart an active service |
| Hide review notifications | `display.memory_notifications: off` | Cosmetic only; review and writes continue |
| Disable bundled Skill seeding | `hermes skills opt-out` | Does not disable self-improvement, existing Skills, or Curator |
| Protect one Skill | foreground `hermes curator pin <name>` | Autonomous writers must not unpin or patch it |
| Preview maintenance | `hermes curator run --dry-run` | Read the report before any real pass |

## Source map

For implementation-level investigation, inspect the current checkout rather than relying on stale line numbers:

- `agent/agent_init.py`: reads memory and Skill nudge configuration.
- `agent/conversation_loop.py` and `agent/turn_context.py`: increment counters and decide whether a review is due.
- `agent/turn_finalizer.py`: starts the post-response background review after a valid response.
- `agent/background_review.py`: builds the isolated review fork and summarizes its writes.
- `agent/curator.py`: Curator gates, deterministic transitions, backups, and optional consolidation.
- `tools/skill_manager_tool.py`: Skill write actions, approval staging, provenance and ownership guards.
- `tools/skill_usage.py`: usage records and Curator-management marker semantics.

Official references:

- https://hermes-agent.nousresearch.com/docs/user-guide/features/skills
- https://hermes-agent.nousresearch.com/docs/user-guide/features/curator
- https://hermes-agent.nousresearch.com/docs/user-guide/features/memory
- https://hermes-agent.nousresearch.com/docs/user-guide/configuration
