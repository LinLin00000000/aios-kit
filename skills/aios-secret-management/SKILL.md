---
name: aios-secret-management
description: "Use when designing, implementing, operating, or auditing AIOS secret management: secret intake, AI API profiles, credential routing, consumers/replicas/materialization, GitHub Secrets sync, SSH/Caddy secret indexing, Secret Broker workflows, or preventing agents from seeing secret values."
version: 0.1.0
license: MIT
---

# AIOS Secret Management

This skill governs AIOS secret/credential workflows. It is a procedure layer, not a place for concrete secret facts or values.

Core principle:

```text
Agent = control-plane planner and metadata maintainer
Secret CLI/Broker = value intake, storage, verification, sync, and run-time injection
User = value provider through a safe local channel
```

The agent must not ask the user to paste secret values into chat, and must not read, print, copy, or store secret values.

## Scope and ownership model

Use this skill for:

- `aios secret ...` CLI design/operation;
- AI API profile truth sources, e.g. `ai-api.translation.default`;
- secret request manifests, receipts, audit events, consumers, replicas, and materializations;
- GitHub repo/org secrets as external replicas or sync targets;
- local secret value backends under `$AIOS_ROOT/vault/secrets/`;
- indexing app/OS-owned secrets such as SSH keys and Caddy certificates;
- cleaning up legacy project-specific env files after a canonical AIOS secret source exists.

Do not use this skill to store actual paths and facts unless they are examples. Current instance facts belong in the AIOS vault / ops registry.

Classify every sensitive item before acting:

| Class | Canonical owner | AIOS role | Examples |
|---|---|---|---|
| AIOS-owned | AIOS Secret module | manage/store/verify/sync | AI API profiles, workflow tokens |
| App/OS-owned | the native app or OS | index/check only | `~/.ssh/*`, Caddy cert storage |
| External-managed | external service | record handle / sync target | GitHub Secrets, cloud secret managers, password managers |
| Materialized artifact | generated from a source | temporary/compat only | project-specific `.env` files |

## Canonical layout

Resolve `$AIOS_ROOT` from the environment or AIOS instance config. Do not hardcode `~/ai-ops` as canonical; it may be a compatibility link into the AIOS instance.

Recommended state layout:

```text
$AIOS_ROOT/vault/secrets/
  items/                     # long-lived secret/item metadata, one YAML per object
  consumers/                 # consumers, one YAML per object
  replicas/                  # external replicas/sync targets, one YAML per object
  requests/
    pending/
    done/
    expired/
  receipts/                  # JSON receipts, no secret values
  values/                    # backend-owned values; never read through agent tools
  policies/                  # optional policy YAML
  audit.jsonl                # append-only lifecycle events, no secret values
```

Agent-first data format rule:

- YAML for current state/config/registry, preferably one object per file.
- JSONL for events/audit/history.
- Markdown only for human-facing explanations or generated views, not as the machine truth source.

## Intake workflow

Default MVP flow:

1. Agent resolves the intended secret identity, fields, consumer(s), replica(s), and route.
2. Agent writes or asks the CLI to create a request manifest under `requests/pending/`; the request contains no secret values.
3. Agent tells the user to run a short shell command such as:

   ```bash
   aios secret intake <request-id>
   ```

4. User runs the command in a real local shell/TTY and enters values interactively.
5. CLI/Broker validates the request, hides password input, stores values, writes metadata, moves the request to `done/`, writes a receipt, and appends `audit.jsonl`.
6. User reports completion; agent reads only the receipt and metadata.
7. Agent verifies consumers/replicas through broker commands and updates ops records if needed.

Never run an interactive intake through an agent-controlled terminal if doing so would capture secret input into tool logs/transcripts. Prefer asking the user to run the command themselves.

## Request manifests

Use request manifests for dynamic agent-generated intake, multi-field secrets, multiple consumers/replicas, async user execution, retryability, or future Web UI reuse.

Treat request manifests as short-lived transaction files, not as long-term truth. Long-term truth lives in `items/`, `consumers/`, `replicas/`, and `audit.jsonl`.

Lifecycle:

```text
requests/pending/<id>.yaml -> requests/done/<id>.yaml or requests/expired/<id>.yaml
```

A request should include:

- `request_id`, `schema_version`, `kind`, `secret_id`, title;
- field definitions: name, label, type, required, a boolean secrecy marker, choices/defaults where useful;
- route/canonical backend metadata;
- consumers and replicas to create/update;
- no secret values.

CLI parameter mode is acceptable only for simple fixed-schema operations. Prefer manifests when an agent is dynamically deciding fields or routing.

## Receipts and audit

Receipts prove completion without exposing values. A receipt may include:

- request id;
- secret id;
- backend name;
- field names;
- status and timestamps;
- consumer/replica ids touched;
- verification status;
- `secret_values_exposed: false`.

`audit.jsonl` is append-only and must not contain values. It records lifecycle events such as intake, verify, sync, rotate, materialize, cleanup, and policy changes.

## AI API profiles

Represent shared model credentials as AI API profiles rather than project-specific env files.

Example identities:

```text
ai-api.translation.default      # source profile
aios-kit.translation            # consumer
github.aios-kit.translation     # external replica / GitHub Actions sync target
```

A project-specific env file such as `aios-kit-translation.env` is a materialized artifact, not the source of truth. After a canonical AIOS secret profile and consumer workflow exist, clean up legacy materializations instead of preserving indefinite compatibility layers.

## `aios secret` CLI expectations

MVP commands:

```bash
aios secret request show <request-id>
aios secret intake <request-id>
aios secret list
aios secret show <secret-id> --metadata
aios secret verify <secret-id>
aios secret sync github <secret-id> --replica <replica-id>
aios secret run --consumer <consumer-id> -- <command...>
```

Safety requirements:

- `intake` reads secret values only from a real TTY / safe local intake channel.
- Password fields use hidden input and optional confirmation.
- Do not support passing secret values via `--value`, command-line arguments, chat text, logs, or receipts.
- `show --metadata`, `list`, `verify`, and `sync` never print values.
- `run` injects values only into the child process environment and scrubs output where possible.

## App/OS-owned secrets

Do not physically centralize secrets that have strong native owner semantics.

For SSH:

- keep canonical paths under `~/.ssh/`;
- do not move or symlink important SSH keys into AIOS;
- index path, owner, expected mode, consumers, and verification method.

For Caddy certificates:

- keep Caddy-managed storage where Caddy expects it;
- do not move or symlink cert/private-key storage;
- index location, domains, owner, renewal/expiry checks, and `do_not_move` / `do_not_symlink`.

## Validation checklist

Before completing a secret-management task:

- No secret values were read through agent tools or copied into chat/files/logs.
- Long-lived state is YAML/JSONL, not Markdown truth.
- AIOS-owned secrets have canonical item/consumer/replica metadata.
- External platform secrets are recorded as replicas or handles, not treated as local source files.
- Materialized artifacts are marked temporary/compat and cleaned up when no longer needed.
- SSH/Caddy/app-owned secrets remain in native paths unless the user explicitly requests otherwise.
- Permissions on secret metadata/value paths are not world/group writable.
- Verification used broker/CLI outputs that redact values.

## Relationship to other skills

- Use `aiops-vault` for ops vault current-state/resource write-back and maintenance logs.
- Use `aios-resource-resolver` to resolve projects/services/resources before editing registry entries.
- Use `hermes-agent` only when configuring Hermes itself or Web UI/profile/tool behavior.

## References

- `references/aios-secret-mvp-decisions.md`: condensed session decisions and pitfalls behind the MVP shape.
