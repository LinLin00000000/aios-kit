# AIOps Vault Template

A lightweight, local-first, agent-friendly AIOps vault: Markdown/JSONL truth sources, low-token command interfaces, and thin companion skills for safe service operations.

It is not a CMDB SaaS, not a password manager, and not a deployment platform. It is a small filesystem contract that helps humans and AI agents operate services without copying private facts into prompts or skills.

## What this gives you

- **File truth source**: `resources.md` for global current state, `services/<id>/service.json` for compact service discovery metadata/references, optional `service-card.md` for dedicated details, and `maintenance-log.jsonl` for append-only history.
- **Dynamic context CLI**: `scripts/aiops.py services --json` emits only `id + name + summary`; the Agent/LLM selects the relevant service semantically, then `service <id> --json` loads that service's metadata, details, and references. The CLI does not pretend token overlap is semantic understanding.
- **Thin skills**: portable agent instructions for reading the vault, respecting secret boundaries, verifying changes, and writing back only the right layer.
- **Safe defaults**: real secrets stay out of Git; the public repo ships examples only.

## Quick install prompt for an agent

Copy this prompt into Hermes Agent, Claude Code, Codex, or another filesystem-capable agent:

```text
Install the bundled AIOps Vault Template from the `modules/aiops-vault-template` directory of `https://github.com/LinLin00000000/aios-kit`.

Do it autonomously:
1. Clone the repository to a temporary or project directory.
2. Set `VAULT_PATH` to `$AIOPS_ROOT` if it exists, otherwise to `~/aios/vault/ops`.
3. From the cloned repo, run `python3 scripts/install.py --vault "$VAULT_PATH" --agent auto`.
4. Run `python3 "$VAULT_PATH/scripts/aiops.py" check`.
5. If your runtime supports skills, install/copy the included skills into the appropriate local skills directory, without overwriting unrelated user files unless the installer explicitly asks or creates backups.
6. Do not read, print, or create real secret values. Only create `secrets-location.md` from the example if it does not exist.
7. Report the vault path, installed skill paths, validation output, and any files you skipped because they already existed.
```

If you are doing it manually:

```bash
git clone https://github.com/LinLin00000000/aios-kit.git
cd aios-kit/modules/aiops-vault-template
python3 scripts/install.py --vault ~/aios/vault/ops --agent auto
python3 ~/aios/vault/ops/scripts/aiops.py check
```

## Repository layout

```text
.
├── README.md
├── SKILL.md                              # primary companion skill: aiops-vault
├── resources.example.md                  # sanitized current-state example
├── maintenance-log.schema.md             # append-only JSONL contract
├── maintenance-log.example.jsonl         # fictional example history
├── secrets-location.example.md           # secret-location metadata only
├── scripts/
│   ├── aiops.py                          # low-token query/check CLI
│   └── install.py                        # safe local installer
├── services/                              # private instance records; not shipped with real facts
│   └── <id>/
│       ├── service.json                   # compact metadata + references
│       └── service-card.md                # optional detailed runbook/current service context
├── templates/
│   ├── service.json
│   ├── service-card.md
│   ├── log-entry.json
│   └── resources-section.md
├── skills/
│   └── aiops-service-operations/SKILL.md # optional operation workflow skill
├── docs/
│   ├── security-boundaries.md
│   ├── migration-from-personal-vault.md
│   └── agent-installation.md
└── tests/
    └── test_smoke.py
```

## The model

Keep these layers separate:

| Layer | Owns | Should not own |
|---|---|---|
| `resources.md` | Global current resource state: hosts, domains, resource pools, cross-service infrastructure, unknowns | Detailed service runbooks or conversational alias lists |
| `maintenance-log.jsonl` | What changed, why, verification, impact, follow-ups | Current-state truth |
| `secrets-location.md` | Names and locations of secrets, access/rotation notes | Secret values, tokens, private keys, cookies, recovery codes |
| `services/<id>/service.json` | Stable discovery metadata: id, name, one short summary, exact aliases, optional details path, references | Dynamic status dumps, long symptom phrase lists, or secret values |
| `services/<id>/service-card.md` | Optional detailed runbook/current service context loaded only after selection; metadata references may point to existing canonical detail sources instead | Global inventory of unrelated services |
| `scripts/aiops.py` | Deterministic catalog/load/filter actuators for the Agent | An embedded LLM, semantic ranking engine, or second fact database |
| Skills | When and how agents should read, act, verify, and write back | Private inventories or drifting service facts |

## Core commands

From the vault root or with `AIOPS_ROOT=/path/to/vault`:

```bash
python3 scripts/aiops.py index
python3 scripts/aiops.py services --json
python3 scripts/aiops.py service example-api --json
python3 scripts/aiops.py resources --section "Service Inventory"
python3 scripts/aiops.py host demo-vps
python3 scripts/aiops.py log --query "example maintenance" --tail 20 --summary
python3 scripts/aiops.py check
```

## Safety rules

- Never commit `secrets-location.md`; only commit `secrets-location.example.md`.
- Do not store API keys, passwords, tokens, private keys, cookies, recovery codes, subscription URLs, or session values in vault documents or logs.
- Use fictional/reserved examples such as `example.com`, `demo-vps`, and `203.0.113.10` in public templates.
- Confirm high-risk operations before making irreversible changes: deleting data, rotating credentials, opening public ports, changing DNS, migrating storage, restoring backups, or modifying third-party resources.
- Treat databases as derived indexes, not the default truth source. Add SQLite/DuckDB only when Markdown/JSONL plus `aiops.py` is no longer enough.

## First-use checklist

1. Fill the smallest useful `resources.md`: one host, shared infrastructure, backup status, and unknowns.
2. For each service the Agent should discover, create `services/<id>/service.json` and keep only a short stable summary plus references there; add the adjacent `service-card.md` only when the service needs its own runbook.
3. Create your private `secrets-location.md` from the example and keep it out of Git.
4. Run `python3 scripts/aiops.py services --json` and `python3 scripts/aiops.py check`.
5. Ask your agent to use the installed `aiops-vault` skill before operating services.
6. After the first real maintenance action, append one JSON line to `maintenance-log.jsonl`.

## Updating an installed vault

Pull this repo, then run the installer again. Existing user files are not overwritten unless you pass `--overwrite`; skipped files are reported.

```bash
git pull
python3 scripts/install.py --vault ~/aios/vault/ops --agent auto
```

## License

MIT. See [LICENSE](LICENSE).
