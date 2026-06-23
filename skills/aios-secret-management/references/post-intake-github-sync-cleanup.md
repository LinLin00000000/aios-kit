# Post-intake GitHub sync and superseded materialization cleanup

Use after the user reports `aios secret intake <request-id>` completed in a real TTY.

## Safe sequence

1. Read only metadata and receipt, never the value backend:
   - `./aios secret show <secret-id> --metadata`
   - parse the receipt JSON and confirm `secret_values_exposed: false`.
   - verify the receipt has field names/ids only, not a `values` object.
2. Local verification:
   - `./aios secret verify <secret-id> --offline`
   - `./aios secret run --consumer <consumer-id> -- <safe dry-run command>`
   - for AI API profiles, a minimal `--check-api --dry-run --limit 1` is acceptable when the user expects post-intake activation; it must print only redacted host/model/mode metadata.
3. GitHub sync:
   - run `./aios secret sync github <secret-id> --replica <replica-id> --dry-run` first and confirm `source_values_read: false`.
   - then run the actual sync with `--yes` only after intake and local verification are complete.
   - use `gh secret list --repo <owner/repo>` for metadata-only verification; never try to read secret values.
   - transient GitHub API/public-key timeouts can be retried a small number of times; record the retry without treating it as a credential failure.
4. Superseded materialization cleanup:
   - verify the project no longer defaults to the old `.env` materialization.
   - delete the superseded env file without reading or backing up its contents.
   - immediately re-run the `aios secret run --consumer ... --check-api --dry-run` path to prove the canonical Secret profile is the active source.
5. Final checks:
   - value and metadata files under `$AIOS_ROOT/vault/secrets` should be private, typically mode `0600` for value/receipt/item/consumer/replica/audit files in the MVP.
   - run public audit and ops-vault check if available.
   - update LLL/ops records with metadata-only facts.

## Pitfalls

- Some `aios secret` commands output human-readable text, not JSON. Only pipe commands documented/known as JSON (`list --json`, `show --metadata`, `request show`) into `json.tool`; for others grep for explicit redaction markers.
- `gh secret set` fetches the GitHub public key before upload; network timeouts at that step do not imply bad secret values. Retry once or twice before reporting a blocker.
- Do not preserve old env files as backups unless there is a separate encrypted/secret-safe backup path; copying them into LLL or chat-visible workdirs would violate the value boundary.
