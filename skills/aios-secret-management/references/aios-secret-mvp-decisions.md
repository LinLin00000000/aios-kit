# Session Notes: AIOS Secret Module MVP Decisions

These notes condense a design discussion that led to the initial `aios-secret-management` skill.

## Durable decisions

- `$AIOS_ROOT` is the AIOS instance root; `~/ai-ops` should be treated as a compatibility entry that may later move under `$AIOS_ROOT/vault/ops`.
- Secret module state belongs under `$AIOS_ROOT/vault/secrets/`, not as a subdirectory of ops.
- Agent-first files should be YAML/JSONL. Markdown is only for human-facing docs or generated views.
- `aios secret` is the formal CLI surface. A skill should guide workflow, not act as the runtime.
- Use a thin class-level skill for AIOS secret management instead of bloating `aiops-vault`.
- AI API credentials should be represented as shared AI API profiles, e.g. `ai-api.translation.default`.
- Project-specific env files such as `aios-kit-translation.env` are materializations, not sources of truth. Once the Secret module works, clean up such legacy artifacts rather than preserving indefinite compatibility layers.
- GitHub Secrets are external replicas / sync targets, not local sources of truth.
- SSH and Caddy secrets are app/OS-owned. Keep their native paths, index and verify them, but do not move or symlink them into AIOS.
- Request manifests are useful for dynamic agent-generated intake but should be short-lived transaction files. Long-term truth lives in items/consumers/replicas YAML and audit JSONL.

## MVP user story

1. User asks to configure a secret.
2. Agent decides the secret id, fields, consumers, replicas, and route.
3. Agent creates a request manifest with no values.
4. User runs `aios secret intake <request-id>` in their own shell.
5. CLI collects values using safe interactive input and hidden password fields.
6. CLI writes metadata, stores values through the backend, emits a receipt, and appends audit JSONL.
7. Agent reads only receipt/metadata and continues verification.

## Pitfalls

- Do not ask users to paste API keys into chat.
- Do not run interactive intake through an agent terminal if it might capture secret input.
- Do not turn Markdown tables into machine truth for secret registries.
- Do not keep generated env files as historical baggage once a canonical secret profile and consumer path exist.
- Do not centralize SSH/Caddy physically just to make AIOS look tidy.
