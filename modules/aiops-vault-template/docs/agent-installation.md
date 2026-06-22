# Agent Installation Guide

This repo is intentionally simple so an agent can install it with ordinary filesystem and shell tools.

## Autonomous install contract

An installing agent should:

1. Clone the repository.
2. Pick the vault path from `$AIOPS_ROOT` or default to `~/aios/vault/ops`.
3. Run `python3 scripts/install.py --vault <path> --agent auto`.
4. Run `<vault>/scripts/aiops.py check`.
5. Install/copy skills only into the user's active agent skill directory.
6. Skip existing user files by default and report skipped paths.
7. Never create or print real secret values.

## Supported install targets

The installer can create a vault for any agent. Skill installation is best-effort:

- Hermes Agent: `~/.hermes/skills/aiops-vault/` and `~/.hermes/skills/aiops-service-operations/` by default.
- Claude Code or other agents: pass `--skills-dir <dir>`.
- Unknown runtime: vault files are installed; copy skills manually from `SKILL.md` and `skills/`.

## Manual skill copy

Primary skill:

```bash
mkdir -p ~/.hermes/skills/aiops-vault
cp SKILL.md ~/.hermes/skills/aiops-vault/SKILL.md
```

Optional service operations skill:

```bash
mkdir -p ~/.hermes/skills/aiops-service-operations
cp skills/aiops-service-operations/SKILL.md ~/.hermes/skills/aiops-service-operations/SKILL.md
```
