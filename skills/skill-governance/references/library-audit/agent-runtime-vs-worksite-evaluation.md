# Agent runtime mode versus Worksite evaluation

Use this reference when deciding whether an agent-native mode—standing goals, Ralph loops, autonomous continuation, native boards, delegated workers, cron, or another runtime feature—should drive a durable AIOS/LLL workflow.

## Decision target

Issue two separate verdicts:

1. **Carrier fit** — can the feature execute or continue a bounded unit of work?
2. **Protocol/authority fit** — can it own task state, recovery, evidence, validation, and promotion authority?

Many useful features pass the first and fail the second. That is normally an adapter decision, not a rejection.

## Evidence order

1. Read the current official feature, command, security, and orchestration documentation. Record every URL and one UTC retrieval timestamp.
2. Inspect the installed executable/version and the local source that implements command parsing, persistence, continuation, permissions, delegation, and completion judgment.
3. Compare official and local command surfaces. A documented subcommand or gate absent from local parsing/state is unavailable locally even if upstream calls it current behavior.
4. Read the compact Worksite truth: `mission.md`, `lll status --json --compact` when available, otherwise `internal/recovery.json`, `internal/validation.json`, and `internal/tasks.jsonl`; then only the relevant worker handoffs/audit tails.
5. Do not exercise a real autonomous goal, mutate configuration, or touch the Worksite when the authority is read-only. Static source plus safe help/status queries are enough for an architectural evaluation; list runtime behavior that remains unverified.

## Capability matrix

| Dimension | Questions | Durable-workflow requirement |
|---|---|---|
| Objective | One standing goal or many typed tasks? | Mission and task identity remain explicit. |
| Scope | Session, profile, project, Matter, or Worksite? | Stable Worksite/task identity, not only a chat session id. |
| Persistence | What object is saved, where, and transactionally or fail-soft? | Canonical snapshots plus inspectable history. |
| Recovery | Does state survive close, crash, restart, compression, and worker loss? | Resume order, checkpoints, leases/reclaim where needed. |
| Queue/lifecycle | Are dependencies, attempts, blocked states, and terminal states modeled? | Typed task state owned by one writer/runner. |
| Parallelism | Is fan-out automatic, explicit delegation, or absent? | Bounded workers mapped to durable task ids and outputs. |
| Permissions | Does the mode constrain tools, approvals, sandbox, path, account, and remote authority? | Enforced least privilege; prompt prose is not a capability boundary. |
| Verification | Does it execute checks, or only judge a response that claims checks ran? | Deterministic receipts plus independent mission validation. |
| Completion | Can `done` also mean blocked, unachievable, or needs input? | Success, blocked, failed, and no-verdict stay distinct. |
| Audit | Are transitions and evidence append-only and attributable? | Runs/trace/error history plus frozen evidence pointers. |
| Promotion | Can completion grant deploy/integration/admission? | Only a supervisor-owned gate may promote authority. |

## Standing-goal/Ralph-loop interpretation

Treat a typical standing-goal mode as an **intent and continuation carrier** unless evidence proves more:

- same-session continuation is serial iteration, not a task graph;
- persisted goal text/status is not a durable execution journal;
- a wait-on-pid/session/time barrier is not a lease, heartbeat, reaper, or ownership claim;
- subgoals are usually additional acceptance prose, not independently schedulable tasks;
- explicit delegation may provide parallel children, but the goal loop does not automatically bind them to Worksite task records;
- a model judge that reads the latest assistant response is self-assessment, even when the prompt asks for concrete evidence;
- deterministic shell/quality gates materially improve evidence, but still do not create dependencies, retries, independent review, or promotion authority;
- a `done` verdict that includes blocked/unachievable work must never map directly to `PASS` or `succeeded`.

Inspect version drift carefully. A current upstream feature may add deterministic gates while an installed release supports only prose completion contracts. Report the upstream specification and local capability separately instead of averaging them into one claim.

## Truth-owner composition

Recommended boundary:

```text
Human intent
  -> runtime goal/session loop (optional, advisory)
  -> supervisor resolves/creates one LLL task reference
  -> Worksite queue remains authoritative
  -> runner, command, or delegation adapter executes
  -> task-local artifacts/log/handoff
  -> deterministic check + independent validator
  -> supervisor records validation and grants any next authority
```

Never dual-write the runtime verdict and Worksite state as peer authorities. Store only a locator/provenance link when useful: runtime/session identifier, task id, dispatch timestamp, and accepted output paths. The Worksite owns current task/recovery/validation; the runtime owns only its ephemeral/session execution state.

## Low-risk pilot worksheet

Before a pilot, fill these fields:

```text
objective:
worksite/task:
runtime role: intent-only | carrier-only
allowed paths:
forbidden actions:
turn/attempt budget:
delegation allowed: no | bounded task ids
permission enforcement:
deterministic check:
independent validator:
recovery source:
terminal mapping:
```

Pilot defaults:

- disposable or frozen read-only surface;
- no secrets, remote hosts, public listeners, service changes, Git integration, or deployment;
- one bounded task and one canonical producer;
- explicit turn/attempt cap lower than the runtime maximum;
- no automatic `done -> succeeded` transition;
- false-success test: the validator should reject a completion claim lacking real evidence;
- interruption test: resume from Worksite files without trusting chat history or goal state alone;
- permission test: prove denied actions are blocked by tools/sandbox, not merely discouraged in the prompt.

Promote beyond pilot only after the adapter demonstrates idempotent dispatch, duplicate suppression, task/output binding, interruption recovery, permission isolation, and independent verdict consumption.

## Verdict rubric

- **Suitable as intent layer**: preserves a human objective and reduces repeated prompting.
- **Suitable as carrier**: can execute one bounded Worksite task and return attributable outputs.
- **Suitable as execution projection**: can mirror task state through an explicit one-way/controlled sync without becoming a second owner.
- **Suitable as protocol owner**: only if it truly owns durable queue, recovery, evidence, validation, and authority semantics. This is rare and requires a migration plan, not a prompt convention.

For high-impact, multi-host, security-sensitive, or long-running development, default to `intent/carrier only`; keep LLL/Worksite as the protocol owner.

## Closeout checklist

- Official URLs and UTC retrieval time recorded.
- Installed version/commit and relevant dirty-state caveat recorded.
- Docs/local differences listed feature-by-feature.
- No secret values or broad environment dump captured.
- No real autonomous mode executed under read-only authority.
- Worksite current validation and authority flags reported without upgrading them.
- Intent/carrier verdict separated from protocol-owner verdict.
- Pilot scope and unverified restart/permission/judge behavior named.
- Explicit statement that configuration, runtime goal state, repository, services, and Worksite were not changed.
