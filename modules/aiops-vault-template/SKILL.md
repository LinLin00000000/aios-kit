---
name: aiops-vault
description: Use this skill whenever the user asks to deploy, operate, troubleshoot, migrate, document, audit, inventory, back up, or clean up local/cloud services, servers, Docker/Compose apps, domains, DNS, reverse proxies, SSH entries, service directories, secret locations, or the AIOps vault itself. This skill treats the local AIOps vault as the source of truth, uses low-token command interfaces before full-file reads, enforces secret and high-risk boundaries, and records verified changes back to the right file layer.
version: 1.0.0
license: MIT
---

# AIOps Vault Companion Skill

This skill is a procedure layer. It does not contain the user's current assets. Current facts live in the local AIOS OPS vault, normally `$AIOPS_ROOT` or `~/aios/vault/ops`.

## Source-of-truth contract

Use this split:

- `README.md`: stable local rules, file roles, safety boundaries, and project-specific conventions.
- `resources.md`: current state that should be trusted now.
- `maintenance-log.jsonl`: append-only history of decisions, maintenance, checks, incidents, and corrections.
- `secrets-location.md`: secret names, storage locations, access/rotation notes only; never secret values.
- `services/<service>/service-card.md`: per-service runbooks and details when the central resource file would get too large.
- `scripts/aiops.py`: low-token command interface over the vault.

Do not infer current infrastructure from this skill. Read the vault and inspect live state where safe.

## Default read order

1. Resolve the vault path: `$AIOPS_ROOT` if set, otherwise `~/aios/vault/ops`.
2. Read the local vault `README.md` first if the task may change files, services, exposure, credentials, or backups.
3. Run the command layer before full reads:
   - `python3 "$AIOPS_ROOT/scripts/aiops.py" index`
   - `python3 "$AIOPS_ROOT/scripts/aiops.py" resources --section "<section>"`
   - `python3 "$AIOPS_ROOT/scripts/aiops.py" service "<name>"`
   - `python3 "$AIOPS_ROOT/scripts/aiops.py" host "<name>"`
   - `python3 "$AIOPS_ROOT/scripts/aiops.py" log --tail 20 --summary`
4. Read full `resources.md`, service cards, or log lines only when the sliced output is insufficient.
5. Use session history only when live state and vault docs cannot answer the question.

## Safety boundaries

- Do not read, print, copy, or store secret values. `secrets-location.md` is metadata, not a secret dump.
- Do not write secrets into `resources.md`, logs, service cards, prompts, issue comments, commits, or chat summaries.
- Confirm before irreversible or high-exposure operations: delete, overwrite, rotate, restore, open public ports, change DNS, migrate data, disable backups, or touch third-party/friend-owned resources.
- Keep resource pools explicit. Do not operate on third-party or friend-owned infrastructure unless the user specifically authorizes that target.
- Prefer least exposure: localhost behind reverse proxy or private network for admin paths; public HTTPS only when intended and authenticated.

## Maintenance workflow

1. Classify the target: host, service, domain/DNS, reverse proxy, data/backup, secret location, automation, or the vault itself.
2. Identify the resource pool and authority boundary.
3. Load minimal current context through `aiops.py` and service cards.
4. Inspect live state with safe commands where needed.
5. Plan the smallest reversible action and call out high-risk steps.
6. Execute with least privilege.
7. Verify with real output from the consumer side: health check, log, HTTP request, `systemctl`, `docker ps`, backup listing, or equivalent.
8. Update the right layer:
   - current facts -> `resources.md` or service card;
   - important history -> one appended `maintenance-log.jsonl` object;
   - secret locations -> `secrets-location.md` without values;
   - service-local details -> service README/card.
9. If a task crosses into secret intake, Secret Broker/CLI workflows, AI API profiles, consumers/replicas, GitHub Secrets sync, or preventing agents from seeing secret values, load `aios-secret-management`; this skill only records ops/current-state and does not own broker procedure.
10. If the change improves reusable AIOps workflow/tooling rather than only private local facts, sync the generic part to the template repo at `~/projects/aios-kit/modules/aiops-vault-template`, run its tests/checks, then commit and push so downstream AIOS Kit consumers receive the improvement. Never copy private resources, logs, or secrets into the public template.
11. Run `python3 "$AIOPS_ROOT/scripts/aiops.py" check` after vault changes.
12. Report changed files, commands, verification, skipped/blocked items, and follow-ups.

## Write-back rules

- Current state belongs in `resources.md` or a service card, not only in the history log.
- History belongs in `maintenance-log.jsonl`, one valid JSON object per line.
- Corrections should be new `correction` or `supersede` entries; do not rewrite history unless the user asks for a migration.
- Avoid duplicating the same fact across README, resources, service cards, and logs. Pick the owning layer.
- Large raw evidence should live under `evidence/` or outside the vault with a path reference.
- Do not put session history, deprecated paths, or migration baggage into active skills. Skills should describe the current workflow only; old lessons belong in `maintenance-log.jsonl`, `evidence/`, or current project docs when still useful.

## Validation checklist

Before finalizing:

- `python3 "$AIOPS_ROOT/scripts/aiops.py" check` passes or failures are explained.
- JSONL files parse.
- No obvious secret values were added.
- Secret metadata and secret-storage paths have sane permissions when they are in scope: `secrets-location.md` should not be world-readable or world-writable, secret directories should not be listable by unrelated users, and secret files should normally be `0600` or managed by a dedicated secret backend.
- Current-state changes are not only in the maintenance log.
- Claims in the response are backed by vault files or live command output.
- Any high-risk action was confirmed or explicitly left as a proposed step.

## If the vault is missing

If no AIOps vault exists and the user wants one, install the bundled AIOS OPS vault template or create the minimal layout under the AIOS instance root:

```text
~/aios/vault/ops/
  README.md
  resources.md
  maintenance-log.jsonl
  maintenance-log.schema.md
  secrets-location.md        # private, ignored by Git
  secrets-location.example.md
  scripts/aiops.py
```

Then run `python3 scripts/aiops.py check`.
