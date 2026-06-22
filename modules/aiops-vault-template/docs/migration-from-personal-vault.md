# Migration from a Personal Vault

Do not publish your private vault directly. Create a clean repository and copy structure, not facts.

## Recommended process

1. Create a new clean repo.
2. Copy file roles and templates.
3. Convert `resources.md` into `resources.example.md` with fictional/reserved examples.
4. Convert `secrets-location.md` into `secrets-location.example.md` with no values.
5. Convert `maintenance-log.jsonl` into two or three fictional example events.
6. Make scripts configurable with `$AIOPS_ROOT` and relative paths.
7. Remove hard-coded usernames, home paths, hostnames, public IPs, real domains, tokens, and provider account names.
8. Run local tests and an independent safety review before publishing.

## What to keep private

- Real service inventory.
- Real maintenance history.
- Secret locations if they reveal too much about your environment.
- Evidence files containing logs, configs, screenshots, or account details.
