# AIOps Vault Template

A lightweight, local-first, agent-friendly AIOps vault: Markdown/JSONL truth sources, low-token command interfaces, and thin companion skills for safe service operations.

It is not a CMDB SaaS, not a password manager, and not a deployment platform. It is a small filesystem contract that helps humans and AI agents operate services without copying private facts into prompts or skills.

## What this gives you

- **File truth source**: `resources.md` for current state, `maintenance-log.jsonl` for append-only history, optional service cards for local details.
- **Low-token CLI**: `scripts/aiops.py` extracts only the relevant section, service, host, or log summary before an agent reads full files; service/host/log lookups support lightweight multi-term natural-language matching so operators do not need exact continuous substrings.
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
├── templates/
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
| `resources.md` | Current resource state: hosts, services, domains, runtime paths, backup status, unknowns | Long history or raw command dumps |
| `maintenance-log.jsonl` | What changed, why, verification, impact, follow-ups | Current-state truth |
| `secrets-location.md` | Names and locations of secrets, access/rotation notes | Secret values, tokens, private keys, cookies, recovery codes |
| `services/<name>/service-card.md` | Detailed per-service runbooks when `resources.md` would get too large | Global inventory of unrelated services |
| `scripts/aiops.py` | Cheap slices of the vault for humans and agents, including lightweight natural-language lookup for service/host/log queries | A second database of facts |
| Skills | When and how agents should read, act, verify, and write back | Private inventories or drifting service facts |

## Core commands

From the vault root or with `AIOPS_ROOT=/path/to/vault`:

```bash
python3 scripts/aiops.py index
python3 scripts/aiops.py resources --section "Service Inventory"
python3 scripts/aiops.py service "example api docker"
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

1. Fill the smallest useful `resources.md`: one host, one service, backup status, and unknowns.
2. Create your private `secrets-location.md` from the example and keep it out of Git.
3. Run `python3 scripts/aiops.py index` and `python3 scripts/aiops.py check`.
4. Ask your agent to use the installed `aiops-vault` skill before operating services.
5. After the first real maintenance action, append one JSON line to `maintenance-log.jsonl`.

## Updating an installed vault

Pull this repo, then run the installer again. Existing user files are not overwritten unless you pass `--overwrite`; skipped files are reported.

```bash
git pull
python3 scripts/install.py --vault ~/aios/vault/ops --agent auto
```

## License

MIT. See [LICENSE](LICENSE).
